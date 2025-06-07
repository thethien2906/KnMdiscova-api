# psychologists/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date
from users.models import User
import logging
logger = logging.getLogger(__name__)


class Psychologist(models.Model):
    """
    Psychologist profile model - extends the base User model
    """

    # Verification Status Choices
    VERIFICATION_STATUS_CHOICES = [
        ('Pending', _('Pending')),
        ('Approved', _('Approved')),
        ('Rejected', _('Rejected')),
    ]

    # Primary key linking to User
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='psychologist_profile',
        help_text=_("Link to the base user account")
    )

    # Personal Information
    first_name = models.CharField(
        _('first name'),
        max_length=100,
        help_text=_("Psychologist's first name")
    )
    last_name = models.CharField(
        _('last name'),
        max_length=100,
        help_text=_("Psychologist's last name")
    )

    # Professional Credentials
    license_number = models.CharField(
        _('license number'),
        max_length=100,
        unique=True,
        help_text=_("Professional license number")
    )
    license_issuing_authority = models.CharField(
        _('license issuing authority'),
        max_length=255,
        help_text=_("Authority that issued the license")
    )
    license_expiry_date = models.DateField(
        _('license expiry date'),
        help_text=_("When the license expires")
    )
    years_of_experience = models.PositiveIntegerField(
        _('years of experience'),
        validators=[
            MinValueValidator(0, message=_("Years of experience cannot be negative")),
            MaxValueValidator(60, message=_("Years of experience seems too high"))
        ],
        help_text=_("Total years of professional experience")
    )

    # Professional Profile
    biography = models.TextField(
        _('biography'),
        blank=True,
        help_text=_("Professional biography and approach")
    )
    education = models.JSONField(
        _('education'),
        default=list,
        blank=True,
        help_text=_("Educational background (degree, institution, year)")
    )
    certifications = models.JSONField(
        _('certifications'),
        default=list,
        blank=True,
        help_text=_("Professional certifications (name, institution, year)")
    )

    # Verification System
    verification_status = models.CharField(
        _('verification status'),
        max_length=20,
        choices=VERIFICATION_STATUS_CHOICES,
        default='Pending',
        help_text=_("Current verification status")
    )
    admin_notes = models.TextField(
        _('admin notes'),
        blank=True,
        help_text=_("Internal notes for verification process")
    )

    # Service Offerings
    offers_initial_consultation = models.BooleanField(
        _('offers initial consultation'),
        default=True,
        help_text=_("Offers 2-hour in-person initial consultations")
    )
    offers_online_sessions = models.BooleanField(
        _('offers online sessions'),
        default=True,
        help_text=_("Offers 1-hour online video sessions")
    )

    # Office Information (Required for in-person consultations)
    office_address = models.TextField(
        _('office address'),
        blank=True,
        help_text=_("Complete office address for in-person consultations")
    )

    # Professional URLs
    website_url = models.URLField(
        _('website URL'),
        max_length=512,
        blank=True,
        help_text=_("Professional website URL")
    )
    linkedin_url = models.URLField(
        _('LinkedIn URL'),
        max_length=512,
        blank=True,
        help_text=_("LinkedIn profile URL")
    )

    # Pricing (will be used for appointments)
    hourly_rate = models.DecimalField(
        _('hourly rate'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(0, message=_("Hourly rate cannot be negative"))
        ],
        help_text=_("Hourly rate in USD for online sessions")
    )
    initial_consultation_rate = models.DecimalField(
        _('initial consultation rate'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(0, message=_("Initial consultation rate cannot be negative"))
        ],
        help_text=_("Rate for 2-hour initial consultation")
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
        verbose_name = _('Psychologist')
        verbose_name_plural = _('Psychologists')
        db_table = 'psychologists'
        indexes = [
            models.Index(fields=['first_name', 'last_name']),
            models.Index(fields=['verification_status']),
            models.Index(fields=['license_number']),
            models.Index(fields=['offers_initial_consultation', 'offers_online_sessions']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Dr. {self.first_name} {self.last_name} ({self.user.email})"

    def clean(self):
        """Model validation"""
        errors = {}

        # Business Rule: Office address required if offering initial consultations
        if self.offers_initial_consultation and not self.office_address:
            errors['office_address'] = _(
                "Office address is required when offering initial consultations"
            )

        # Business Rule: Must offer at least one service type
        if not self.offers_initial_consultation and not self.offers_online_sessions:
            errors['offers_online_sessions'] = _(
                "Must offer at least one service type (online sessions or initial consultations)"
            )

        # Validate license expiry date is not in the past
        if self.license_expiry_date and self.license_expiry_date < date.today():
            errors['license_expiry_date'] = _(
                "License expiry date cannot be in the past"
            )

        # Validate education structure
        if self.education:
            education_errors = self._validate_education_structure()
            if education_errors:
                errors['education'] = education_errors

        # Validate certifications structure
        if self.certifications:
            certification_errors = self._validate_certifications_structure()
            if certification_errors:
                errors['certifications'] = certification_errors

        # MVP: Pricing validation removed for now
        # Pricing fields are optional in MVP version
        # TODO: Add pricing validation when dynamic pricing is implemented

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        """Return full name with Dr. prefix"""
        return f"Dr. {self.first_name} {self.last_name}".strip()

    @property
    def display_name(self):
        """Return name for display purposes"""
        if self.first_name or self.last_name:
            return self.full_name
        return self.user.email.split('@')[0]  # fallback to email username

    @property
    def is_verified(self):
        """Check if psychologist is verified and approved"""
        return self.verification_status == 'Approved'

    @property
    def is_marketplace_visible(self):
        """Check if psychologist should appear in marketplace"""
        return (
            self.is_verified and
            self.user.is_active and
            self.user.is_verified and
            (self.offers_initial_consultation or self.offers_online_sessions)
        )

    @property
    def license_is_valid(self):
        """Check if license is still valid"""
        if not self.license_expiry_date:
            return False
        return self.license_expiry_date >= date.today()

    @property
    def services_offered(self):
        """Return list of services offered"""
        services = []
        if self.offers_online_sessions:
            services.append('Online Sessions')
        if self.offers_initial_consultation:
            services.append('Initial Consultations')
        return services

    def get_profile_completeness(self):
        """Calculate profile completeness percentage"""
        # Required fields for basic profile
        required_fields = {
            'first_name': self.first_name,
            'last_name': self.last_name,
            'license_number': self.license_number,
            'license_issuing_authority': self.license_issuing_authority,
            'license_expiry_date': self.license_expiry_date,
            'years_of_experience': self.years_of_experience,
        }

        # Important optional fields
        important_fields = {
            'biography': self.biography,
            'education': self.education,
            'certifications': self.certifications,
            # MVP: Pricing fields are no implementable for now
            # 'hourly_rate': self.hourly_rate if self.offers_online_sessions else True,
            # 'initial_consultation_rate': self.initial_consultation_rate if self.offers_initial_consultation else True,
        }
        if self.offers_initial_consultation:
            important_fields['office_address'] = self.office_address
        # Count completed fields
        completed_required = sum(1 for value in required_fields.values()
                               if value is not None and str(value).strip())

        completed_important = sum(1 for value in important_fields.values()
                                if value and (not isinstance(value, str) or value.strip()))

        # Calculate percentage (required fields weighted more heavily)
        required_score = (completed_required / len(required_fields)) * 70
        important_score = (completed_important / len(important_fields)) * 30

        return round(required_score + important_score, 1)

    def get_verification_requirements(self):
        """Get list of requirements for verification"""
        requirements = []

        if not self.license_number:
            requirements.append("License number required")

        if not self.license_issuing_authority:
            requirements.append("License issuing authority required")

        if not self.license_expiry_date:
            requirements.append("License expiry date required")

        if not self.license_is_valid:
            requirements.append("License is expired")

        if self.years_of_experience is None:
            requirements.append("Years of experience required")

        if not self.biography:
            requirements.append("Professional biography recommended")

        if not self.education:
            requirements.append("Educational background recommended")

        if self.offers_initial_consultation and not self.office_address:
            requirements.append("Office address required for initial consultations")

        # MVP: Pricing requirements removed for now
        # TODO: Re-enable when dynamic pricing is implemented
        # if self.offers_online_sessions and not self.hourly_rate:
        #     requirements.append("Hourly rate required for online sessions")
        # if self.offers_initial_consultation and not self.initial_consultation_rate:
        #     requirements.append("Initial consultation rate required")

        return requirements

    def can_book_appointments(self):
        """Check if psychologist can receive appointment bookings - MVP version"""
        return (
            self.is_marketplace_visible and
            self.license_is_valid and
            (self.offers_online_sessions or self.offers_initial_consultation) and
            # MVP: Pricing not required yet, office address still required for initial consultations
            (not self.offers_initial_consultation or self.office_address)
        )

    @classmethod
    def get_marketplace_psychologists(cls):
        """Get all psychologists visible in marketplace"""
        return cls.objects.filter(
            verification_status='Approved',
            user__is_active=True,
            user__is_verified=True,
            license_expiry_date__gte=date.today()
        ).select_related('user').order_by('first_name', 'last_name')

    def _validate_education_structure(self):
        """Validate education JSON structure"""
        if not isinstance(self.education, list):
            return "Education must be a list of educational entries"

        errors = []
        for i, edu in enumerate(self.education):
            if not isinstance(edu, dict):
                errors.append(f"Education entry {i+1} must be a dictionary")
                continue

            required_keys = ['degree', 'institution', 'year']
            for key in required_keys:
                if key not in edu:
                    errors.append(f"Education entry {i+1} missing required field: {key}")

            # Validate year if present
            if 'year' in edu:
                try:
                    year = int(edu['year'])
                    current_year = date.today().year
                    if year < 1950 or year > current_year:
                        errors.append(f"Education entry {i+1} has invalid year: {year}")
                except (ValueError, TypeError):
                    errors.append(f"Education entry {i+1} year must be a number")

        return errors

    def _validate_certifications_structure(self):
        """Validate certifications JSON structure"""
        if not isinstance(self.certifications, list):
            return "Certifications must be a list of certification entries"

        errors = []
        for i, cert in enumerate(self.certifications):
            if not isinstance(cert, dict):
                errors.append(f"Certification entry {i+1} must be a dictionary")
                continue

            required_keys = ['name', 'institution', 'year']
            for key in required_keys:
                if key not in cert:
                    errors.append(f"Certification entry {i+1} missing required field: {key}")

            # Validate year if present
            if 'year' in cert:
                try:
                    year = int(cert['year'])
                    current_year = date.today().year
                    if year < 1950 or year > current_year:
                        errors.append(f"Certification entry {i+1} has invalid year: {year}")
                except (ValueError, TypeError):
                    errors.append(f"Certification entry {i+1} year must be a number")

        return errors

    @classmethod
    def get_default_education_template(cls):
        """Return template for education entry"""
        return {
            'degree': '',
            'institution': '',
            'year': '',
            'field_of_study': '',
            'honors': ''
        }

    @classmethod
    def get_default_certification_template(cls):
        """Return template for certification entry"""
        return {
            'name': '',
            'institution': '',
            'year': '',
            'expiry_date': '',
            'certification_id': ''
        }


class PsychologistAvailability(models.Model):
    """
    Psychologist availability blocks - creates time blocks that will be broken down into 1-hour appointable slots
    """

    # Primary key
    availability_id = models.BigAutoField(
        primary_key=True,
        help_text=_("Unique identifier for availability block")
    )

    # Psychologist relationship
    psychologist = models.ForeignKey(
        Psychologist,
        on_delete=models.CASCADE,
        related_name='availability_blocks',
        help_text=_("Psychologist this availability belongs to")
    )

    # Day and Time Configuration
    day_of_week = models.IntegerField(
        _('day of week'),
        validators=[
            MinValueValidator(0, message=_("Day of week must be 0-6 (0=Sunday)")),
            MaxValueValidator(6, message=_("Day of week must be 0-6 (6=Saturday)"))
        ],
        help_text=_("Day of week: 0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday, 5=Friday, 6=Saturday")
    )

    start_time = models.TimeField(
        _('start time'),
        help_text=_("Start time of availability block")
    )

    end_time = models.TimeField(
        _('end time'),
        help_text=_("End time of availability block")
    )

    # Recurring vs Specific Date
    is_recurring = models.BooleanField(
        _('is recurring'),
        default=True,
        help_text=_("Whether this availability repeats weekly")
    )

    specific_date = models.DateField(
        _('specific date'),
        null=True,
        blank=True,
        help_text=_("For non-recurring availability overrides on specific dates")
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
        verbose_name = _('Psychologist Availability')
        verbose_name_plural = _('Psychologist Availabilities')
        db_table = 'psychologist_availability'
        indexes = [
            models.Index(fields=['psychologist', 'day_of_week']),
            models.Index(fields=['psychologist', 'specific_date']),
            models.Index(fields=['is_recurring']),
            models.Index(fields=['day_of_week', 'start_time']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            # Ensure end time is after start time
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')),
                name='end_time_after_start_time'
            ),
            # For recurring availability, specific_date should be null
            models.CheckConstraint(
                check=models.Q(is_recurring=False) | models.Q(specific_date__isnull=True),
                name='recurring_no_specific_date'
            ),
            # For non-recurring availability, specific_date should be provided
            models.CheckConstraint(
                check=models.Q(is_recurring=True) | models.Q(specific_date__isnull=False),
                name='non_recurring_has_specific_date'
            ),
        ]
        # Prevent duplicate availability blocks for same psychologist, day, and time
        unique_together = [
            ['psychologist', 'day_of_week', 'start_time', 'end_time', 'specific_date']
        ]

    def __str__(self):
        if self.is_recurring:
            day_name = self.get_day_name()
            return f"{self.psychologist.display_name} - {day_name} {self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}"
        else:
            return f"{self.psychologist.display_name} - {self.specific_date} {self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}"

    def clean(self):
        """Model validation"""
        errors = {}

        # Validate time range
        if self.start_time and self.end_time:
            if self.end_time <= self.start_time:
                errors['end_time'] = _("End time must be after start time")

            # Validate minimum duration (at least 1 hour for appointable slots)
            from datetime import datetime, timedelta
            start_dt = datetime.combine(date.today(), self.start_time)
            end_dt = datetime.combine(date.today(), self.end_time)
            duration = end_dt - start_dt

            if duration < timedelta(hours=1):
                errors['end_time'] = _("Availability block must be at least 1 hour long")

        # Validate recurring vs specific date logic
        if self.is_recurring and self.specific_date:
            errors['specific_date'] = _("Recurring availability should not have a specific date")
        elif not self.is_recurring and not self.specific_date:
            errors['specific_date'] = _("Non-recurring availability must have a specific date")

        # Validate specific date is not in the past (for non-recurring)
        if not self.is_recurring and self.specific_date and self.specific_date < date.today():
            errors['specific_date'] = _("Specific date cannot be in the past")

        # Validate psychologist is approved for booking
        if self.psychologist and not self.psychologist.can_book_appointments():
            errors['psychologist'] = _("Psychologist must be approved and have valid credentials to set availability")

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def duration_hours(self):
        """Calculate duration of availability block in hours"""
        from datetime import datetime
        start_dt = datetime.combine(date.today(), self.start_time)
        end_dt = datetime.combine(date.today(), self.end_time)
        duration = end_dt - start_dt
        return duration.total_seconds() / 3600

    @property
    def max_appointable_slots(self):
        """Calculate maximum number of 1-hour slots this block can generate"""
        return int(self.duration_hours)

    def get_day_name(self):
        """Get human-readable day name"""
        days = [
            _('Sunday'), _('Monday'), _('Tuesday'), _('Wednesday'),
            _('Thursday'), _('Friday'), _('Saturday')
        ]
        return days[self.day_of_week]

    def get_time_range_display(self):
        """Get formatted time range string"""
        return f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"

    def get_display_date(self):
        """Get display date for the availability"""
        if self.is_recurring:
            return f"Every {self.get_day_name()}"
        else:
            return self.specific_date.strftime('%Y-%m-%d')

    def generate_slot_times(self):
        """
        Generate list of 1-hour slot start times within this availability block
        Returns list of time objects representing each hour slot
        """
        from datetime import datetime, timedelta

        slots = []
        current_time = datetime.combine(date.today(), self.start_time)
        end_time = datetime.combine(date.today(), self.end_time)

        while current_time + timedelta(hours=1) <= end_time:
            slots.append(current_time.time())
            current_time += timedelta(hours=1)

        return slots

    def overlaps_with(self, other_availability):
        """
        Check if this availability block overlaps with another
        """
        # Must be same day (for recurring) or same specific date
        if self.is_recurring and other_availability.is_recurring:
            if self.day_of_week != other_availability.day_of_week:
                return False
        elif not self.is_recurring and not other_availability.is_recurring:
            if self.specific_date != other_availability.specific_date:
                return False
        else:
            # One recurring, one specific - no overlap
            return False

        # Check time overlap
        return (
            self.start_time < other_availability.end_time and
            self.end_time > other_availability.start_time
        )

    @classmethod
    def get_psychologist_recurring_availability(cls, psychologist):
        """Get all recurring availability for a psychologist, ordered by day and time"""
        return cls.objects.filter(
            psychologist=psychologist,
            is_recurring=True
        ).order_by('day_of_week', 'start_time')

    @classmethod
    def get_psychologist_specific_availability(cls, psychologist, date_from=None, date_to=None):
        """Get specific date availability for a psychologist within date range"""
        queryset = cls.objects.filter(
            psychologist=psychologist,
            is_recurring=False
        )

        if date_from:
            queryset = queryset.filter(specific_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(specific_date__lte=date_to)

        return queryset.order_by('specific_date', 'start_time')

    @classmethod
    def get_availability_for_date(cls, psychologist, target_date):
        """
        Get all availability blocks for a psychologist on a specific date
        Combines recurring availability for that day of week with specific date overrides
        """
        day_of_week = target_date.weekday()
        # Convert Python weekday (0=Monday) to our format (0=Sunday)
        day_of_week = (day_of_week + 1) % 7

        # Get recurring availability for that day
        recurring = cls.objects.filter(
            psychologist=psychologist,
            is_recurring=True,
            day_of_week=day_of_week
        )

        # Get specific date availability
        specific = cls.objects.filter(
            psychologist=psychologist,
            is_recurring=False,
            specific_date=target_date
        )

        # Combine and return
        from django.db.models import Q
        return cls.objects.filter(
            Q(psychologist=psychologist) &
            (
                Q(is_recurring=True, day_of_week=day_of_week) |
                Q(is_recurring=False, specific_date=target_date)
            )
        ).order_by('start_time')

    def is_active_on_date(self, target_date):
        """
        Check if this availability block is active on a specific date
        """
        if self.is_recurring:
            day_of_week = target_date.weekday()
            # Convert Python weekday (0=Monday) to our format (0=Sunday)
            day_of_week = (day_of_week + 1) % 7
            return self.day_of_week == day_of_week
        else:
            return self.specific_date == target_date

    def can_be_deleted(self):
        """Check if availability block can be safely deleted"""
        booked_slots = self.generated_slots.filter(is_booked=True)
        return not booked_slots.exists()

    def get_deletion_impact(self):
        """Get information about what would be affected by deletion"""
        total_slots = self.generated_slots.count()
        booked_slots = self.generated_slots.filter(is_booked=True).count()
        unbooked_slots = total_slots - booked_slots

        return {
            'total_slots': total_slots,
            'booked_slots': booked_slots,
            'unbooked_slots': unbooked_slots,
            'can_delete': booked_slots == 0,
            'booked_appointments': self.generated_slots.filter(
                is_booked=True
            ).prefetch_related('appointments').count()
        }

    def delete(self, *args, **kwargs):
        """Override delete to handle slot cleanup properly"""
        from django.core.exceptions import ValidationError

        # Check if there are booked slots
        booked_slots = self.generated_slots.filter(is_booked=True)

        if booked_slots.exists():
            booked_count = booked_slots.count()
            raise ValidationError(
                f"Cannot delete availability block: {booked_count} slots have active bookings. "
                f"Cancel or complete the appointments first."
            )

        # Delete only unbooked slots first
        unbooked_slots_deleted = self.generated_slots.filter(is_booked=False).delete()[0]

        # Now safe to delete the availability block
        result = super().delete(*args, **kwargs)

        logger.info(
            f"Deleted availability block {self.availability_id} and {unbooked_slots_deleted} unbooked slots"
        )

        return result

    def safe_delete_with_cleanup(self):
        """Alternative method for controlled deletion with detailed response"""
        impact = self.get_deletion_impact()

        if not impact['can_delete']:
            return {
                'success': False,
                'message': f"Cannot delete: {impact['booked_slots']} slots have active bookings",
                'impact': impact
            }

        # Delete unbooked slots
        unbooked_deleted = self.generated_slots.filter(is_booked=False).delete()[0]

        # Delete the availability block
        block_info = {
            'availability_id': self.availability_id,
            'day_name': self.get_day_name() if self.is_recurring else str(self.specific_date),
            'time_range': self.get_time_range_display()
        }

        self.delete()

        return {
            'success': True,
            'message': f"Availability block deleted successfully",
            'deleted_slots': unbooked_deleted,
            'block_info': block_info,
            'impact': impact
        }