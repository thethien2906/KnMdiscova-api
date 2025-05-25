import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator
from users.models import User


class Parent(models.Model):
    """
    Parent profile model - extends the base User model
    """

    # Primary key linking to User
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='parent_profile',
        help_text=_("Link to the base user account")
    )

    # Personal Information
    first_name = models.CharField(
        _('first name'),
        max_length=100,
        help_text=_("Parent's first name")
    )
    last_name = models.CharField(
        _('last name'),
        max_length=100,
        help_text=_("Parent's last name")
    )

    # Contact Information
    phone_number = models.CharField(
        _('phone number'),
        max_length=20,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^\+?1?\d{9,15}$',
                message=_("Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.")
            )
        ],
        help_text=_("Contact phone number")
    )

    # Address Fields (all optional)
    address_line1 = models.CharField(
        _('address line 1'),
        max_length=255,
        blank=True,
        help_text=_("Street address, P.O. box, company name, c/o")
    )
    address_line2 = models.CharField(
        _('address line 2'),
        max_length=255,
        blank=True,
        help_text=_("Apartment, suite, unit, building, floor, etc.")
    )
    city = models.CharField(
        _('city'),
        max_length=100,
        blank=True,
        help_text=_("City or town")
    )
    state_province = models.CharField(
        _('state/province'),
        max_length=100,
        blank=True,
        help_text=_("State, province, or region")
    )
    postal_code = models.CharField(
        _('postal code'),
        max_length=20,
        blank=True,
        help_text=_("ZIP or postal code")
    )
    country = models.CharField(
        _('country'),
        max_length=50,
        blank=True,
        default='US',
        help_text=_("Country")
    )

    # Communication Preferences
    communication_preferences = models.JSONField(
        _('communication preferences'),
        default=dict,
        blank=True,
        help_text=_("Notification and communication preferences")
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
        verbose_name = _('Parent')
        verbose_name_plural = _('Parents')
        db_table = 'parents'
        indexes = [
            models.Index(fields=['first_name', 'last_name']),
            models.Index(fields=['city', 'state_province']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.user.email})"

    @property
    def full_name(self):
        """Return full name"""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_name(self):
        """Return name for display purposes"""
        if self.first_name or self.last_name:
            return self.full_name
        return self.user.email.split('@')[0]  # fallback to email username

    @property
    def full_address(self):
        """Return formatted full address"""
        address_parts = [
            self.address_line1,
            self.address_line2,
            self.city,
            self.state_province,
            self.postal_code,
            self.country
        ]
        return ', '.join([part for part in address_parts if part])

    def get_communication_preference(self, preference_key, default=True):
        """Get a specific communication preference"""
        return self.communication_preferences.get(preference_key, default)

    def set_communication_preference(self, preference_key, value):
        """Set a specific communication preference"""
        if not isinstance(self.communication_preferences, dict):
            self.communication_preferences = {}
        self.communication_preferences[preference_key] = value
        self.save(update_fields=['communication_preferences', 'updated_at'])

    @classmethod
    def get_default_communication_preferences(cls):
        """Return default communication preferences"""
        return {
            'email_notifications': True,
            'sms_notifications': False,
            'appointment_reminders': True,
            'reminder_timing': '24_hours',  # 24_hours, 2_hours, 30_minutes
            'growth_plan_updates': True,
            'new_message_alerts': True,
            'marketing_emails': False,
        }