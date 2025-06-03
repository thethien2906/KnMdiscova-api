# parents/services.py
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
import logging
from typing import Optional, Dict, Any

from .models import Parent
from users.models import User

logger = logging.getLogger(__name__)


class ParentProfileError(Exception):
    """Base exception for parent profile related errors"""
    pass


class ParentNotFoundError(ParentProfileError):
    """Raised when parent profile is not found"""
    pass


class ParentService:
    """
    Service class for parent profile management
    """

    @staticmethod
    def get_parent_by_user(user: User) -> Optional[Parent]:
        """
        Get parent profile by user, return None if not found
        """
        try:
            return Parent.objects.select_related('user').get(user=user)
        except Parent.DoesNotExist:
            logger.warning(f"Parent profile not found for user {user.email}")
            return None

    @staticmethod
    def get_parent_by_user_or_raise(user: User) -> Parent:
        """
        Get parent profile by user, raise exception if not found
        """
        parent = ParentService.get_parent_by_user(user)
        if not parent:
            raise ParentNotFoundError(f"Parent profile not found for user {user.email}")
        return parent

    @staticmethod
    def update_parent_profile(parent: Parent, update_data: Dict[str, Any]) -> Parent:
        """
        Update parent profile and related user fields with business logic validation
        """
        # Validate that user is actually a parent
        if not parent.user.is_parent:
            raise ParentProfileError("User is not a parent")

        # Validate user is active
        if not parent.user.is_active:
            raise ParentProfileError("User account is inactive")

        try:
            with transaction.atomic():
                # Handle user fields
                user_fields = {}
                user_allowed_fields = ['profile_picture_url', 'user_timezone']

                for field in user_allowed_fields:
                    if field in update_data:
                        user_fields[field] = update_data.pop(field)

                # Update user fields if any
                if user_fields:
                    updated_user_fields = []
                    for field, value in user_fields.items():
                        setattr(parent.user, field, value)
                        updated_user_fields.append(field)

                    if updated_user_fields:
                        updated_user_fields.append('updated_at')
                        parent.user.save(update_fields=updated_user_fields)
                        logger.info(f"Updated user fields for {parent.user.email}: {updated_user_fields}")

                # Handle communication preferences specially
                if 'communication_preferences' in update_data:
                    prefs = update_data.pop('communication_preferences')
                    ParentService._update_communication_preferences(parent, prefs)

                # Update other parent fields
                updated_fields = []
                allowed_fields = [
                    'first_name', 'last_name', 'phone_number',
                    'address_line1', 'address_line2', 'city',
                    'state_province', 'postal_code', 'country'
                ]

                for field, value in update_data.items():
                    if field in allowed_fields and hasattr(parent, field):
                        setattr(parent, field, value)
                        updated_fields.append(field)

                if updated_fields:
                    updated_fields.append('updated_at')
                    parent.save(update_fields=updated_fields)
                    logger.info(f"Updated parent profile for {parent.user.email}: {updated_fields}")

                return parent

        except Exception as e:
            logger.error(f"Failed to update parent profile for {parent.user.email}: {str(e)}")
            raise ParentProfileError(f"Failed to update profile: {str(e)}")

    @staticmethod
    def _update_communication_preferences(parent: Parent, preferences: Dict[str, Any]) -> None:
        """
        Update communication preferences with validation
        """
        if not isinstance(preferences, dict):
            raise ParentProfileError("Communication preferences must be a dictionary")

        # Get current preferences or defaults
        current_prefs = parent.communication_preferences or Parent.get_default_communication_preferences()

        # Validate and update preferences
        valid_keys = [
            'email_notifications', 'sms_notifications', 'appointment_reminders',
            'reminder_timing', 'growth_plan_updates', 'new_message_alerts',
            'marketing_emails'
        ]

        valid_reminder_timings = ['24_hours', '2_hours', '30_minutes']

        for key, value in preferences.items():
            if key not in valid_keys:
                logger.warning(f"Unknown communication preference key: {key}")
                continue

            # Type validation
            if key == 'reminder_timing':
                if value not in valid_reminder_timings:
                    raise ParentProfileError(f"Invalid reminder timing: {value}")
            else:
                if not isinstance(value, bool):
                    raise ParentProfileError(f"Preference '{key}' must be a boolean")

            current_prefs[key] = value

        # Save updated preferences
        parent.communication_preferences = current_prefs
        parent.save(update_fields=['communication_preferences', 'updated_at'])

        logger.info(f"Updated communication preferences for {parent.user.email}")

    @staticmethod
    def get_parent_profile_data(parent: Parent) -> Dict[str, Any]:
        """
        Get comprehensive parent profile data
        """
        return {
            'user_id': str(parent.user.id),
            'email': parent.user.email,
            'user_type': parent.user.user_type,
            'is_verified': parent.user.is_verified,
            'is_active': parent.user.is_active,
            'profile_picture_url': parent.user.profile_picture_url,
            # Profile information
            'first_name': parent.first_name,
            'last_name': parent.last_name,
            'full_name': parent.full_name,
            'display_name': parent.display_name,
            'phone_number': parent.phone_number,

            # Address
            'address_line1': parent.address_line1,
            'address_line2': parent.address_line2,
            'city': parent.city,
            'state_province': parent.state_province,
            'postal_code': parent.postal_code,
            'country': parent.country,
            'full_address': parent.full_address,

            # Preferences
            'communication_preferences': parent.communication_preferences,

            # Profile completeness
            'profile_completeness': ParentService.calculate_profile_completeness(parent),

            # Timestamps
            'created_at': parent.created_at,
            'updated_at': parent.updated_at,
        }

    @staticmethod
    def calculate_profile_completeness(parent: Parent) -> Dict[str, Any]:
        """
        Calculate profile completeness score and missing fields
        """
        required_fields = {
            'first_name': parent.first_name,
            'last_name': parent.last_name,
            'phone_number': parent.phone_number,
        }

        optional_fields = {
            'address_line1': parent.address_line1,
            'city': parent.city,
            'state_province': parent.state_province,
            'postal_code': parent.postal_code,
            'country': parent.country,
        }

        # Check required fields
        completed_required = sum(1 for value in required_fields.values() if value and value.strip())
        total_required = len(required_fields)

        # Check optional fields
        completed_optional = sum(1 for value in optional_fields.values() if value and value.strip())
        total_optional = len(optional_fields)

        # Calculate scores
        required_score = (completed_required / total_required) * 100 if total_required > 0 else 100
        optional_score = (completed_optional / total_optional) * 100 if total_optional > 0 else 100

        # Overall score (required fields weighted more heavily)
        overall_score = (required_score * 0.7) + (optional_score * 0.3)

        # Missing fields
        missing_required = [field for field, value in required_fields.items()
                          if not value or not value.strip()]
        missing_optional = [field for field, value in optional_fields.items()
                          if not value or not value.strip()]

        return {
            'overall_score': round(overall_score, 1),
            'required_score': round(required_score, 1),
            'optional_score': round(optional_score, 1),
            'is_complete': len(missing_required) == 0,
            'missing_required_fields': missing_required,
            'missing_optional_fields': missing_optional,
            'completed_required': completed_required,
            'total_required': total_required,
            'completed_optional': completed_optional,
            'total_optional': total_optional,
        }

    @staticmethod
    def reset_communication_preferences_to_default(parent: Parent) -> Parent:
        """
        Reset communication preferences to default values
        """
        try:
            parent.communication_preferences = Parent.get_default_communication_preferences()
            parent.save(update_fields=['communication_preferences', 'updated_at'])

            logger.info(f"Reset communication preferences to default for {parent.user.email}")
            return parent

        except Exception as e:
            logger.error(f"Failed to reset preferences for {parent.user.email}: {str(e)}")
            raise ParentProfileError(f"Failed to reset preferences: {str(e)}")

    @staticmethod
    def validate_profile_data(profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate profile data according to business rules
        """
        errors = {}

        # Validate phone number format if provided
        phone_number = profile_data.get('phone_number')
        if phone_number and phone_number.strip():
            import re
            phone_pattern = r'^[\+]?[\d\s\-\(\)\.]{10,20}$'
            if not re.match(phone_pattern, phone_number):
                errors['phone_number'] = "Invalid phone number format"

        # Validate required fields are not empty if provided
        required_fields = ['first_name', 'last_name']
        for field in required_fields:
            value = profile_data.get(field)
            if value is not None and not value.strip():
                errors[field] = f"{field.replace('_', ' ').title()} cannot be empty"

        # Validate country code if provided
        country = profile_data.get('country')
        if country and len(country) > 50:
            errors['country'] = "Country name too long"

        if errors:
            raise ValidationError(errors)

        return profile_data