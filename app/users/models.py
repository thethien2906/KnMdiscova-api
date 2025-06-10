# users/models.py
import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model where email is the unique identifier
    """

    # User Type Choices
    USER_TYPE_CHOICES = [
        ('Parent', _('Parent')),
        ('Psychologist', _('Psychologist')),
        ('Admin', _('Admin')),
    ]

    # Primary fields
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique identifier for the user")
    )
    email = models.EmailField(
        _('email address'),
        unique=True,
        help_text=_("User's email address, used for login")
    )
    google_id = models.CharField(
        _('google id'),
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text=_("Google account identifier for OAuth authentication")
    )
    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPE_CHOICES,
        help_text=_("Type of user: Parent, Psychologist, or Admin")
    )

    # Status fields
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_("Designates whether this user should be treated as active.")
    )
    is_verified = models.BooleanField(
        _('verified'),
        default=False,
        help_text=_("Designates whether user has verified their email address.")
    )
    is_staff = models.BooleanField(
        _('staff status'),
        default=False,
        help_text=_("Designates whether the user can log into the admin site.")
    )

    # Profile fields
    profile_picture_url = models.URLField(
        _('profile picture'),
        max_length=512,
        blank=True,
        null=True,
        help_text=_("URL to user's profile picture")
    )
    user_timezone = models.CharField(
        _('timezone'),
        max_length=50,
        default='UTC',
        help_text=_("User's timezone for scheduling appointments")
    )

    # Timestamp fields
    registration_date = models.DateTimeField(
        _('registration date'),
        default=timezone.now,
        help_text=_("When the user registered")
    )
    last_login_date = models.DateTimeField(
        _('last login'),
        blank=True,
        null=True,
        help_text=_("Last time user logged in")
    )
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('updated at'),
        auto_now=True
    )

    # Custom manager
    objects = UserManager()

    # Django auth settings
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['user_type']

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        db_table = 'users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['user_type']),
            models.Index(fields=['is_active', 'is_verified']),
            models.Index(fields=['created_at']),
            models.Index(fields=['google_id']),
        ]

    def __str__(self):
        return f"{self.email} ({self.user_type})"

    @property
    def is_parent(self):
        """Check if user is a parent"""
        return self.user_type == 'Parent'

    @property
    def is_psychologist(self):
        """Check if user is a psychologist"""
        return self.user_type == 'Psychologist'

    @property
    def is_admin(self):
        """Check if user is an admin"""
        return self.user_type == 'Admin'

    @property
    def is_google_user(self):
        """Check if user registered/authenticated via Google"""
        return bool(self.google_id)

    @property
    def has_password_auth(self):
        """Check if user has password authentication"""
        return bool(self.password)