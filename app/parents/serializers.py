# parents/serializers.py
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .models import Parent
from users.serializers import UserSerializer


class CommunicationPreferencesSerializer(serializers.Serializer):
    """Serializer for communication preferences"""
    email_notifications = serializers.BooleanField(default=True)
    sms_notifications = serializers.BooleanField(default=False)
    appointment_reminders = serializers.BooleanField(default=True)
    reminder_timing = serializers.ChoiceField(
        choices=['24_hours', '2_hours', '30_minutes'],
        default='24_hours'
    )
    growth_plan_updates = serializers.BooleanField(default=True)
    new_message_alerts = serializers.BooleanField(default=True)
    marketing_emails = serializers.BooleanField(default=False)


class ParentSerializer(serializers.ModelSerializer):
    """Serializer for Parent model"""
    user = UserSerializer(read_only=True)
    full_name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    full_address = serializers.CharField(read_only=True)
    communication_preferences = CommunicationPreferencesSerializer(required=False)

    class Meta:
        model = Parent
        fields = [
            'user',
            'first_name',
            'last_name',
            'full_name',
            'display_name',
            'phone_number',
            'address_line1',
            'address_line2',
            'city',
            'state_province',
            'postal_code',
            'country',
            'full_address',
            'communication_preferences',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']

    def validate_communication_preferences(self, value):
        """Validate communication preferences"""
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                _("Communication preferences must be a dictionary")
            )
        return value

    def update(self, instance, validated_data):
        """Update parent profile"""
        # Handle communication preferences separately
        comm_prefs_data = validated_data.pop('communication_preferences', None)

        # Update basic fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Update communication preferences if provided
        if comm_prefs_data is not None:
            # Merge with existing preferences
            current_prefs = instance.communication_preferences or {}
            current_prefs.update(comm_prefs_data)
            instance.communication_preferences = current_prefs

        instance.save()
        return instance


class ParentProfileUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating parent profile (without nested user data)"""
    communication_preferences = CommunicationPreferencesSerializer(required=False)

    class Meta:
        model = Parent
        fields = [
            'first_name',
            'last_name',
            'phone_number',
            'address_line1',
            'address_line2',
            'city',
            'state_province',
            'postal_code',
            'country',
            'communication_preferences'
        ]

    def validate_first_name(self, value):
        """Ensure first name is not empty when updating"""
        if value is not None and not value.strip():
            raise serializers.ValidationError(_("First name cannot be empty"))
        return value

    def validate_last_name(self, value):
        """Ensure last name is not empty when updating"""
        if value is not None and not value.strip():
            raise serializers.ValidationError(_("Last name cannot be empty"))
        return value


class ParentPublicSerializer(serializers.ModelSerializer):
    """Public serializer for Parent (used by psychologists to view parent info)"""
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = Parent
        fields = [
            'display_name',
            'city',
            'state_province',
            'country'
        ]
        read_only_fields = fields


class CommunicationPreferenceUpdateSerializer(serializers.Serializer):
    """Serializer for updating individual communication preferences"""
    preference_key = serializers.CharField()
    value = serializers.BooleanField()

    def validate_preference_key(self, value):
        """Validate that the preference key is valid"""
        valid_keys = [
            'email_notifications',
            'sms_notifications',
            'appointment_reminders',
            'growth_plan_updates',
            'new_message_alerts',
            'marketing_emails'
        ]
        if value not in valid_keys:
            raise serializers.ValidationError(
                _("Invalid preference key. Valid keys are: {}").format(', '.join(valid_keys))
            )
        return value