from django.db import models

# Create your models here.
# psychologists/models.py
import uuid
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator

User = get_user_model()


class Psychologist(models.Model):
    """
    Profile information specific to psychologists
    """

    # Verification Status Choices
    VERIFICATION_STATUS_CHOICES = [
        ('Pending', _('Pending')),
        ('Approved', _('Approved')),
        ('Rejected', _('Rejected')),
    ]

    # Primary key - One-to-One with User
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        limit_choices_to={'user_type': 'Psychologist'},
        help_text=_("Reference to the base User account")
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

    # Professional Information
    license_number = models.CharField(
        _('license number'),
        max_length=100,
        unique=True,
        help_text=_("Professional license number")
    )
    license_issuing_authority = models.CharField(
        _('license issuing authority'),
        max_length=255,
        blank=True,
        help_text=_("Authority that issued the license")
    )
    license_expiry_date = models.DateField(
        _('license expiry date'),
        blank=True,
        null=True,
        help_text=_("When the professional license expires")
    )
    years_of_experience = models.PositiveIntegerField(
        _('years of experience'),
        validators=[MinValueValidator(0), MaxValueValidator(50)],
        help_text=_("Number of years of professional experience")
    )

    # Profile Information
    biography = models.TextField(
        _('biography'),
        blank=True,
        help_text=_("Professional biography and background")
    )
    education = models.JSONField(
        _('education'),
        default=list,
        blank=True,
        help_text=_("Array of education objects: {degree, institution, year}")
    )
    certifications = models.JSONField(
        _('certifications'),
        default=list,
        blank=True,
        help_text=_("Array of certification objects: {name, institution, year}")
    )

    # Business Information
    hourly_rate = models.DecimalField(
    _('hourly rate'),
    max_digits=10,
    decimal_places=2,
    blank=True,
    null=True,
    validators=[MinValueValidator(Decimal('0'))],
    help_text=_("Hourly rate in USD")
    )

    # Verification Status
    verification_status = models.CharField(
        _('verification status'),
        max_length=20,
        choices=VERIFICATION_STATUS_CHOICES,
        default='Pending',
        help_text=_("Current verification status of the psychologist")
    )
    admin_notes = models.TextField(
        _('admin notes'),
        blank=True,
        help_text=_("Internal review notes for administrators")
    )

    # Optional URLs
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
            models.Index(fields=['verification_status']),
            models.Index(fields=['license_number']),
            models.Index(fields=['years_of_experience']),
            models.Index(fields=['hourly_rate']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Dr. {self.first_name} {self.last_name}"

    @property
    def full_name(self):
        """Return the full name of the psychologist"""
        return f"{self.first_name} {self.last_name}"

    @property
    def is_verified(self):
        """Check if psychologist is verified and approved"""
        return self.verification_status == 'Approved'

    @property
    def display_name(self):
        """Return display name with professional title"""
        return f"Dr. {self.full_name}"

    def can_accept_appointments(self):
        """Check if psychologist can accept new appointments"""
        return (
            self.user.is_active and
            self.user.is_verified and
            self.verification_status == 'Approved'
        )


class PsychologistAvailability(models.Model):
    """
    Psychologist availability schedule
    """

    # Day of Week Choices
    DAY_OF_WEEK_CHOICES = [
        (0, _('Sunday')),
        (1, _('Monday')),
        (2, _('Tuesday')),
        (3, _('Wednesday')),
        (4, _('Thursday')),
        (5, _('Friday')),
        (6, _('Saturday')),
    ]

    id = models.BigAutoField(primary_key=True)

    psychologist = models.ForeignKey(
        Psychologist,
        on_delete=models.CASCADE,
        related_name='availability_slots',
        help_text=_("The psychologist this availability belongs to")
    )

    # Schedule Information
    day_of_week = models.PositiveSmallIntegerField(
        _('day of week'),
        choices=DAY_OF_WEEK_CHOICES,
        null=True,
        blank=True,
        help_text=_("Day of the week (0=Sunday, 1=Monday, etc.)")
    )
    start_time = models.TimeField(
        _('start time'),
        help_text=_("Start time for availability")
    )
    end_time = models.TimeField(
        _('end time'),
        help_text=_("End time for availability")
    )

    # Availability Type
    is_recurring = models.BooleanField(
        _('is recurring'),
        default=True,
        help_text=_("Whether this is a recurring weekly availability")
    )
    specific_date = models.DateField(
        _('specific date'),
        blank=True,
        null=True,
        help_text=_("For non-recurring availability overrides on specific dates")
    )

    # Booking Status
    is_booked = models.BooleanField(
        _('is booked'),
        default=False,
        help_text=_("Whether this time slot is currently booked")
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
            models.Index(fields=['is_booked']),
            models.Index(fields=['start_time', 'end_time']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(start_time__lt=models.F('end_time')),
                name='start_time_before_end_time'
            ),
            models.UniqueConstraint(
                fields=['psychologist', 'day_of_week', 'start_time', 'end_time'],
                condition=models.Q(specific_date__isnull=True),
                name='unique_recurring_availability'
            ),
            models.UniqueConstraint(
                fields=['psychologist', 'specific_date', 'start_time', 'end_time'],
                condition=models.Q(specific_date__isnull=False),
                name='unique_specific_date_availability'
            ),
        ]

    def __str__(self):
        if self.is_recurring:
            day_name = dict(self.DAY_OF_WEEK_CHOICES)[self.day_of_week]
            return f"{self.psychologist.display_name} - {day_name} {self.start_time}-{self.end_time}"
        else:
            return f"{self.psychologist.display_name} - {self.specific_date} {self.start_time}-{self.end_time}"

    @property
    def duration_hours(self):
        """Calculate duration in hours"""
        import datetime
        start_datetime = datetime.datetime.combine(datetime.date.today(), self.start_time)
        end_datetime = datetime.datetime.combine(datetime.date.today(), self.end_time)
        duration = end_datetime - start_datetime
        return duration.total_seconds() / 3600

    def is_available_for_date(self, target_date):
        """Check if this availability slot is available for a specific date"""
        if not self.is_recurring and self.specific_date:
            return self.specific_date == target_date
        elif self.is_recurring:
            return target_date.weekday() == (self.day_of_week - 1) % 7
        return False

    def clean(self):
        """Custom validation"""
        from django.core.exceptions import ValidationError

        if self.start_time >= self.end_time:
            raise ValidationError(_('Start time must be before end time'))

        if not self.is_recurring and not self.specific_date:
            raise ValidationError(_('Non-recurring availability must have a specific date'))

        if self.is_recurring and self.specific_date:
            raise ValidationError(_('Recurring availability cannot have a specific date'))