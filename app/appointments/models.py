# appointments/models.py
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, datetime, timedelta, time
import secrets
import string

from psychologists.models import Psychologist, PsychologistAvailability
from parents.models import Parent
from children.models import Child


class AppointmentSlot(models.Model):
    """
    Individual 1-hour bookable time slots generated from psychologist availability blocks
    """

    # Primary key
    slot_id = models.BigAutoField(
        primary_key=True,
        help_text=_("Unique identifier for the appointment slot")
    )

    # Relationships
    psychologist = models.ForeignKey(
        Psychologist,
        on_delete=models.CASCADE,
        related_name='appointment_slots',
        help_text=_("Psychologist this slot belongs to")
    )

    availability_block = models.ForeignKey(
        PsychologistAvailability,
        on_delete=models.CASCADE,
        related_name='generated_slots',
        help_text=_("Availability block this slot was generated from")
    )

    # Slot timing
    slot_date = models.DateField(
        _('slot date'),
        help_text=_("Date of this appointment slot")
    )

    start_time = models.TimeField(
        _('start time'),
        help_text=_("Start time of this 1-hour slot")
    )

    end_time = models.TimeField(
        _('end time'),
        help_text=_("End time of this 1-hour slot (start_time + 1 hour)")
    )

    # Booking status
    is_booked = models.BooleanField(
        _('is booked'),
        default=False,
        help_text=_("Whether this slot is currently booked")
    )

    # Timestamps
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('updated at'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Appointment Slot')
        verbose_name_plural = _('Appointment Slots')
        db_table = 'appointment_slots'
        indexes = [
            models.Index(fields=['psychologist', 'slot_date', 'start_time']),
            models.Index(fields=['psychologist', 'is_booked']),
            models.Index(fields=['slot_date', 'is_booked']),
            models.Index(fields=['availability_block']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            # Ensure end_time is exactly 1 hour after start_time
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')),
                name='slot_end_time_after_start_time'
            ),
        ]
        # Prevent duplicate slots for same psychologist, date, and time
        unique_together = [
            ['psychologist', 'slot_date', 'start_time']
        ]

    def __str__(self):
        return f"{self.psychologist.display_name} - {self.slot_date} {self.start_time.strftime('%H:%M')}"

    def clean(self):
        """Model validation"""
        errors = {}

        # Validate slot is in the future (for new slots)
        if not self.pk:  # Only for new slots
            slot_datetime = datetime.combine(self.slot_date, self.start_time)
            if timezone.is_naive(slot_datetime):
                slot_datetime = timezone.make_aware(slot_datetime)

            if slot_datetime <= timezone.now():
                errors['slot_date'] = _("Slot must be in the future")

        # Validate end_time is start_time + 1 hour
        if self.start_time and self.end_time:
            expected_end_time = (datetime.combine(date.today(), self.start_time) + timedelta(hours=1)).time()
            if self.end_time != expected_end_time:
                errors['end_time'] = _("End time must be exactly 1 hour after start time")

        # Validate slot date matches availability block pattern
        if self.availability_block and self.slot_date:
            if self.availability_block.is_recurring:
                # Check if slot date's day of week matches availability block
                day_of_week = self.slot_date.weekday()
                # Convert Python weekday (0=Monday) to our format (0=Sunday)
                day_of_week = (day_of_week + 1) % 7

                if day_of_week != self.availability_block.day_of_week:
                    errors['slot_date'] = _("Slot date doesn't match availability block day of week")
            else:
                # For specific date availability, slot date must match
                if self.slot_date != self.availability_block.specific_date:
                    errors['slot_date'] = _("Slot date doesn't match availability block specific date")

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Override save to set end_time automatically"""
        if self.start_time and not self.end_time:
            # Automatically set end_time to start_time + 1 hour
            start_dt = datetime.combine(date.today(), self.start_time)
            end_dt = start_dt + timedelta(hours=1)
            self.end_time = end_dt.time()

        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def datetime_start(self):
        dt = datetime.combine(self.slot_date, self.start_time)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt

    @property
    def datetime_end(self):
        """Get datetime object for slot end"""
        dt = datetime.combine(self.slot_date, self.end_time)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt

    @property
    def is_available_for_booking(self):
        """Check if slot is available for booking"""
        return (
            not self.is_booked and
            self.datetime_start > timezone.now() and
            self.psychologist.can_book_appointments()
        )

    def mark_as_booked(self):
        """Mark slot as booked"""
        if self.is_booked:
            raise ValidationError(_("Slot is already booked"))

        self.is_booked = True
        self.save(update_fields=['is_booked', 'updated_at'])

    def mark_as_available(self):
        """Mark slot as available (unbook it)"""
        if not self.is_booked:
            raise ValidationError(_("Slot is already available"))

        self.is_booked = False
        self.save(update_fields=['is_booked', 'updated_at'])

    @classmethod
    def get_available_slots(cls, psychologist, date_from=None, date_to=None):
        """Get available slots for a psychologist within date range"""
        queryset = cls.objects.filter(
            psychologist=psychologist,
            is_booked=False
        )

        if date_from:
            queryset = queryset.filter(slot_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(slot_date__lte=date_to)

        return queryset.order_by('slot_date', 'start_time')

    @classmethod
    def find_consecutive_slots(cls, psychologist, slot_date, start_time, num_slots=2):
        """
        Find consecutive available slots for multi-hour appointments
        Used for InitialConsultation (2 hours = 2 consecutive slots)
        """
        slots = []
        current_time = start_time

        for i in range(num_slots):
            try:
                slot = cls.objects.get(
                    psychologist=psychologist,
                    slot_date=slot_date,
                    start_time=current_time,
                    is_booked=False
                )
                slots.append(slot)

                # Calculate next hour
                current_dt = datetime.combine(date.today(), current_time)
                next_dt = current_dt + timedelta(hours=1)
                current_time = next_dt.time()

            except cls.DoesNotExist:
                return []  # Not enough consecutive slots available

        return slots


class Appointment(models.Model):
    """
    Appointment booking linking child, parent, psychologist, and appointment slots
    """

    # Session Type Choices
    SESSION_TYPE_CHOICES = [
        ('OnlineMeeting', _('Online Session - 1 hour')),
        ('InitialConsultation', _('Initial Consultation - 2 hours (In-Person)')),
    ]

    # Appointment Status Choices
    APPOINTMENT_STATUS_CHOICES = [
        ('Payment_Pending', _('Payment Pending')),
        ('Scheduled', _('Scheduled')),
        ('Completed', _('Completed')),
        ('Cancelled', _('Cancelled')),
        ('No_Show', _('No Show')),
    ]

    # Payment Status Choices
    PAYMENT_STATUS_CHOICES = [
        ('Pending', _('Pending')),
        ('Paid', _('Paid')),
        ('Failed', _('Failed')),
        ('Refunded', _('Refunded')),
    ]

    # Primary key
    appointment_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique identifier for the appointment")
    )

    # Core relationships
    child = models.ForeignKey(
        Child,
        on_delete=models.CASCADE,
        related_name='appointments',
        help_text=_("Child this appointment is for")
    )

    psychologist = models.ForeignKey(
        Psychologist,
        on_delete=models.CASCADE,
        related_name='appointments',
        help_text=_("Psychologist providing the service")
    )

    parent = models.ForeignKey(
        Parent,
        on_delete=models.CASCADE,
        related_name='appointments',
        help_text=_("Parent who booked the appointment")
    )

    # Appointment slots (1 for OnlineMeeting, 2 for InitialConsultation)
    appointment_slots = models.ManyToManyField(
        AppointmentSlot,
        related_name='appointments',
        help_text=_("Appointment slots reserved for this appointment")
    )

    # Appointment details
    session_type = models.CharField(
        _('session type'),
        max_length=20,
        choices=SESSION_TYPE_CHOICES,
        help_text=_("Type of session: online or in-person consultation")
    )

    appointment_status = models.CharField(
        _('appointment status'),
        max_length=20,
        choices=APPOINTMENT_STATUS_CHOICES,
        default='Payment_Pending',
        help_text=_("Current status of the appointment")
    )

    payment_status = models.CharField(
        _('payment status'),
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='Pending',
        help_text=_("Payment status for this appointment")
    )

    # Scheduled times (from slots)
    scheduled_start_time = models.DateTimeField(
        _('scheduled start time'),
        help_text=_("When the appointment is scheduled to start")
    )

    scheduled_end_time = models.DateTimeField(
        _('scheduled end time'),
        help_text=_("When the appointment is scheduled to end")
    )

    # Actual times (filled during appointment)
    actual_start_time = models.DateTimeField(
        _('actual start time'),
        null=True,
        blank=True,
        help_text=_("When the appointment actually started")
    )

    actual_end_time = models.DateTimeField(
        _('actual end time'),
        null=True,
        blank=True,
        help_text=_("When the appointment actually ended")
    )

    # Meeting details
    meeting_address = models.TextField(
        _('meeting address'),
        blank=True,
        help_text=_("Address for in-person meetings (defaults from psychologist profile)")
    )

    meeting_link = models.URLField(
        _('meeting link'),
        max_length=512,
        blank=True,
        null=True,
        help_text=_("Video meeting link for online sessions")
    )

    meeting_id = models.CharField(
        _('meeting ID'),
        max_length=100,
        blank=True,
        help_text=_("Meeting ID for video sessions")
    )

    # QR verification for in-person sessions
    qr_verification_code = models.CharField(
        _('QR verification code'),
        max_length=32,
        blank=True,
        null=True,
        unique=True,
        help_text=_("QR code for verifying in-person session attendance")
    )

    session_verified_at = models.DateTimeField(
        _('session verified at'),
        null=True,
        blank=True,
        help_text=_("When the session was verified via QR code")
    )

    # Notes
    parent_notes = models.TextField(
        _('parent notes'),
        blank=True,
        help_text=_("Notes from parent about the appointment")
    )

    psychologist_notes = models.TextField(
        _('psychologist notes'),
        blank=True,
        help_text=_("Private notes from psychologist")
    )

    cancellation_reason = models.TextField(
        _('cancellation reason'),
        blank=True,
        help_text=_("Reason for cancellation if cancelled")
    )

    # Timestamps
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('updated at'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Appointment')
        verbose_name_plural = _('Appointments')
        db_table = 'appointments'
        indexes = [
            models.Index(fields=['psychologist', 'scheduled_start_time']),
            models.Index(fields=['parent', 'scheduled_start_time']),
            models.Index(fields=['child', 'scheduled_start_time']),
            models.Index(fields=['appointment_status', 'scheduled_start_time']),
            models.Index(fields=['session_type', 'scheduled_start_time']),
            models.Index(fields=['qr_verification_code']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.child.display_name} - {self.psychologist.display_name} ({self.session_type}) - {self.scheduled_start_time.strftime('%Y-%m-%d %H:%M')}"

    def clean(self):
        """Model validation"""
        errors = {}

        # Validate child belongs to parent
        if self.child and self.parent and self.child.parent != self.parent:
            errors['child'] = _("Child must belong to the booking parent")

        # Validate scheduled times are in the future (for new appointments)
        if not self.pk and self.scheduled_start_time:
            if self.scheduled_start_time <= timezone.now():
                errors['scheduled_start_time'] = _("Appointment must be scheduled in the future")

        # Validate session type and duration
        if self.session_type and self.scheduled_start_time and self.scheduled_end_time:
            duration = self.scheduled_end_time - self.scheduled_start_time

            if self.session_type == 'OnlineMeeting':
                if duration != timedelta(hours=1):
                    errors['scheduled_end_time'] = _("Online sessions must be exactly 1 hour")
            elif self.session_type == 'InitialConsultation':
                if duration != timedelta(hours=2):
                    errors['scheduled_end_time'] = _("Initial consultations must be exactly 2 hours")

        # QR code should only exist for InitialConsultation
        if self.qr_verification_code and self.session_type != 'InitialConsultation':
            errors['qr_verification_code'] = _("QR verification only applies to in-person consultations")

        # Meeting link should only exist for OnlineMeeting
        if self.meeting_link and self.session_type != 'OnlineMeeting':
            errors['meeting_link'] = _("Meeting link only applies to online sessions")

        # Meeting address should exist for InitialConsultation
        if self.session_type == 'InitialConsultation' and not self.meeting_address:
            errors['meeting_address'] = _("Meeting address is required for in-person consultations")

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Override save to set defaults and generate codes"""
        # Set meeting address default for InitialConsultation
        if self.session_type == 'InitialConsultation' and not self.meeting_address:
            self.meeting_address = self.psychologist.office_address

        # Generate QR verification code for InitialConsultation
        if self.session_type == 'InitialConsultation' and not self.qr_verification_code:
            self.qr_verification_code = self._generate_qr_code()

        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def duration_hours(self):
        """Get appointment duration in hours"""
        if self.session_type == 'OnlineMeeting':
            return 1
        elif self.session_type == 'InitialConsultation':
            return 2
        return 0

    @property
    def is_upcoming(self):
        """Check if appointment is upcoming"""
        return self.scheduled_start_time > timezone.now()

    @property
    def is_past(self):
        """Check if appointment is in the past"""
        return self.scheduled_end_time < timezone.now()

    @property
    def can_be_cancelled(self):
        """Check if appointment can be cancelled"""
        return (
            self.appointment_status in ['Payment_Pending', 'Scheduled'] and
            self.is_upcoming
        )

    @property
    def can_be_verified(self):
        """Check if appointment can be verified via QR code"""
        return (
            self.session_type == 'InitialConsultation' and
            self.appointment_status == 'Scheduled' and
            not self.session_verified_at and
            # Allow verification 30 minutes before to 30 minutes after scheduled start
            abs((timezone.now() - self.scheduled_start_time).total_seconds()) <= 1800
        )

    def mark_as_scheduled(self):
        """Mark appointment as scheduled (after payment)"""
        if self.appointment_status != 'Payment_Pending':
            raise ValidationError(_("Only pending appointments can be marked as scheduled"))

        self.appointment_status = 'Scheduled'
        self.payment_status = 'Paid'
        self.save(update_fields=['appointment_status', 'payment_status', 'updated_at'])

    def mark_as_completed(self):
        """Mark appointment as completed"""
        if self.appointment_status != 'Scheduled':
            raise ValidationError(_("Only scheduled appointments can be marked as completed"))

        self.appointment_status = 'Completed'
        if not self.actual_end_time:
            self.actual_end_time = timezone.now()
        self.save(update_fields=['appointment_status', 'actual_end_time', 'updated_at'])

    def cancel_appointment(self, reason=""):
        """Cancel appointment and release slots"""
        if not self.can_be_cancelled:
            raise ValidationError(_("Appointment cannot be cancelled"))

        # Release appointment slots
        for slot in self.appointment_slots.all():
            slot.mark_as_available()

        self.appointment_status = 'Cancelled'
        self.cancellation_reason = reason
        self.save(update_fields=['appointment_status', 'cancellation_reason', 'updated_at'])

    def verify_session(self):
        """Verify in-person session attendance via QR code"""
        if not self.can_be_verified:
            raise ValidationError(_("Session cannot be verified at this time"))

        self.session_verified_at = timezone.now()
        if not self.actual_start_time:
            self.actual_start_time = timezone.now()

        self.save(update_fields=['session_verified_at', 'actual_start_time', 'updated_at'])

    def _generate_qr_code(self):
        """Generate unique QR verification code"""
        code = str(uuid.uuid4()).replace('-', '').upper()[:16]

        # Double-check uniqueness (very unlikely to collide with UUID)
        while Appointment.objects.filter(qr_verification_code=code).exists():
            code = str(uuid.uuid4()).replace('-', '').upper()[:16]

        return code

    @classmethod
    def get_upcoming_appointments(cls, user, days_ahead=30):
        """Get upcoming appointments for a user"""
        end_date = timezone.now() + timedelta(days=days_ahead)

        if hasattr(user, 'parent_profile'):
            return cls.objects.filter(
                parent=user.parent_profile,
                scheduled_start_time__gte=timezone.now(),
                scheduled_start_time__lte=end_date,
                appointment_status__in=['Scheduled', 'Payment_Pending']
            ).order_by('scheduled_start_time')

        elif hasattr(user, 'psychologist_profile'):
            return cls.objects.filter(
                psychologist=user.psychologist_profile,
                scheduled_start_time__gte=timezone.now(),
                scheduled_start_time__lte=end_date,
                appointment_status__in=['Scheduled']
            ).order_by('scheduled_start_time')

        return cls.objects.none()