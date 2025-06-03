# parents/serializers.py
from rest_framework import serializers
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _
from django.db import transaction

from .models import Parent
from users.models import User
from users.serializers import UserSerializer


class ParentSerializer(serializers.ModelSerializer):
    """
    Basic serializer for Parent model
    """
    # Read-only fields from related User model
    email = serializers.EmailField(source='user.email', read_only=True)
    user_type = serializers.CharField(source='user.user_type', read_only=True)
    is_verified = serializers.BooleanField(source='user.is_verified', read_only=True)
    profile_picture_url = serializers.URLField(source='user.profile_picture_url', read_only=True)

    # Computed fields
    full_name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    full_address = serializers.CharField(read_only=True)

    class Meta:
        model = Parent
        fields = [
            # User-related fields (read-only)
            'email',
            'user_type',
            'is_verified',
            'profile_picture_url',
            # Parent profile fields
            'first_name',
            'last_name',
            'phone_number',
            'address_line1',
            'address_line2',
            'city',
            'state_province',
            'postal_code',
            'country',
            'communication_preferences',

            # Computed fields
            'full_name',
            'display_name',
            'full_address',

            # Timestamps
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'email',
            'user_type',
            'is_verified',

            'full_name',
            'display_name',
            'full_address',
            'created_at',
            'updated_at',
        ]

    def validate_phone_number(self, value):
        """
        Validate phone number format
        """
        if value:  # Only validate if not empty
            validator = RegexValidator(
                regex=r'^[\+]?[\d\s\-\(\)\.]{10,20}$',
                message=_("Please enter a valid phone number (10-20 characters, may include +, spaces, hyphens, parentheses, or dots)")
            )
            validator(value)
        return value

    def validate_communication_preferences(self, value):
        """
        Validate communication preferences structure
        """
        if value is None:
            return Parent.get_default_communication_preferences()

        if not isinstance(value, dict):
            raise serializers.ValidationError(_("Communication preferences must be a dictionary"))

        # Validate known preference keys and values
        valid_preferences = {
            'email_notifications': bool,
            'sms_notifications': bool,
            'appointment_reminders': bool,
            'reminder_timing': str,
            'growth_plan_updates': bool,
            'new_message_alerts': bool,
            'marketing_emails': bool,
        }

        valid_reminder_timings = ['24_hours', '2_hours', '30_minutes']

        for key, val in value.items():
            if key in valid_preferences:
                expected_type = valid_preferences[key]
                if not isinstance(val, expected_type):
                    raise serializers.ValidationError(
                        _(f"Preference '{key}' must be of type {expected_type.__name__}")
                    )

                # Special validation for reminder_timing
                if key == 'reminder_timing' and val not in valid_reminder_timings:
                    raise serializers.ValidationError(
                        _(f"Invalid reminder timing. Must be one of: {', '.join(valid_reminder_timings)}")
                    )

        return value


class ParentProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating parent profile (excludes sensitive fields)
    """
    profile_picture_url = serializers.URLField(required=False, allow_blank=True)

    class Meta:
        model = Parent
        fields = [
            'profile_picture_url',
            'first_name',
            'last_name',
            'phone_number',
            'address_line1',
            'address_line2',
            'city',
            'state_province',
            'postal_code',
            'country',
            'communication_preferences',
        ]

    def validate_phone_number(self, value):
        """Validate phone number format"""
        if value:
            validator = RegexValidator(
                regex=r'^[\+]?[\d\s\-\(\)\.]{10,20}$',
                message=_("Please enter a valid phone number")
            )
            validator(value)
        return value

    def validate_communication_preferences(self, value):
        """Validate communication preferences structure"""
        if value is None:
            return Parent.get_default_communication_preferences()

        if not isinstance(value, dict):
            raise serializers.ValidationError(_("Communication preferences must be a dictionary"))

        return value


class ParentDetailSerializer(ParentSerializer):
    """
    Extended serializer for detailed parent information
    """
    # Include user information
    user = UserSerializer(read_only=True)

    class Meta(ParentSerializer.Meta):
        fields = ParentSerializer.Meta.fields + ['user']


class ParentSummarySerializer(serializers.ModelSerializer):
    """
    Minimal serializer for parent summary (for listings, selections, etc.)
    """
    full_name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    profile_picture_url = serializers.URLField(source='user.profile_picture_url', read_only=True)

    class Meta:
        model = Parent
        fields = [
            'user',  # The user ID/primary key
            'email',
            'full_name',
            'display_name',
            'city',
            'state_province',
            'country',
            'profile_picture_url',
        ]
        read_only_fields = ['user', 'email', 'full_name', 'display_name']


class CommunicationPreferencesSerializer(serializers.Serializer):
    """
    Dedicated serializer for communication preferences
    """
    email_notifications = serializers.BooleanField(default=True)
    sms_notifications = serializers.BooleanField(default=False)
    appointment_reminders = serializers.BooleanField(default=True)
    reminder_timing = serializers.ChoiceField(
        choices=[
            ('24_hours', _('24 hours before')),
            ('2_hours', _('2 hours before')),
            ('30_minutes', _('30 minutes before')),
        ],
        default='24_hours'
    )
    growth_plan_updates = serializers.BooleanField(default=True)
    new_message_alerts = serializers.BooleanField(default=True)
    marketing_emails = serializers.BooleanField(default=False)

    def update(self, instance, validated_data):
        """Update parent's communication preferences"""
        if not isinstance(instance, Parent):
            raise serializers.ValidationError(_("Instance must be a Parent object"))

        # Ensure we have a dictionary to work with
        current_prefs = instance.communication_preferences or {}

        # Update with new values
        current_prefs.update(validated_data)

        # Save to parent
        instance.communication_preferences = current_prefs
        instance.save(update_fields=['communication_preferences', 'updated_at'])

        return current_prefs


class ParentSearchSerializer(serializers.Serializer):
    """
    Serializer for parent search/filtering
    """
    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(max_length=100, required=False)
    last_name = serializers.CharField(max_length=100, required=False)
    city = serializers.CharField(max_length=100, required=False)
    state_province = serializers.CharField(max_length=100, required=False)
    country = serializers.CharField(max_length=50, required=False)
    is_verified = serializers.BooleanField(required=False)
    created_after = serializers.DateTimeField(required=False)
    created_before = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        """Validate date ranges"""
        created_after = attrs.get('created_after')
        created_before = attrs.get('created_before')

        if created_after and created_before and created_after > created_before:
            raise serializers.ValidationError({
                'created_after': _("Start date must be before end date")
            })

        return attrs