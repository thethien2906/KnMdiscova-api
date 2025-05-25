# parents/services.py
from typing import Dict, Optional
from django.db import transaction
from django.utils.translation import gettext_lazy as _
import logging

from .models import Parent
from users.models import User

logger = logging.getLogger(__name__)


class ParentService:
    """Service layer for parent-related operations"""

    @staticmethod
    @transaction.atomic
    def create_parent_profile(user: User, **kwargs) -> Parent:
        """
        Create a parent profile for a user

        Args:
            user: User instance
            **kwargs: Additional parent fields

        Returns:
            Parent instance

        Raises:
            ValueError: If user is not of type 'Parent'
            RuntimeError: If parent profile already exists
        """
        if user.user_type != 'Parent':
            raise ValueError(_("User must be of type 'Parent'"))

        if hasattr(user, 'parent_profile'):
            raise RuntimeError(_("Parent profile already exists for this user"))

        # Set default communication preferences if not provided
        if 'communication_preferences' not in kwargs:
            kwargs['communication_preferences'] = Parent.get_default_communication_preferences()

        parent = Parent.objects.create(user=user, **kwargs)
        logger.info(f"Parent profile created for user: {user.email}")

        return parent

    @staticmethod
    def update_communication_preferences(
        parent: Parent,
        preferences: Dict[str, bool]
    ) -> Parent:
        """
        Update multiple communication preferences at once

        Args:
            parent: Parent instance
            preferences: Dictionary of preference keys and values

        Returns:
            Updated Parent instance
        """
        current_prefs = parent.communication_preferences or {}
        current_prefs.update(preferences)
        parent.communication_preferences = current_prefs
        parent.save(update_fields=['communication_preferences', 'updated_at'])

        logger.info(f"Updated communication preferences for parent: {parent.user.email}")
        return parent

    @staticmethod
    def check_profile_completeness(parent: Parent) -> Dict[str, any]:
        """
        Check if parent profile is complete

        Args:
            parent: Parent instance

        Returns:
            Dictionary with completeness status and missing fields
        """
        required_fields = {
            'first_name': _('First name'),
            'last_name': _('Last name'),
            'phone_number': _('Phone number'),
            'city': _('City'),
            'country': _('Country')
        }

        missing_fields = []
        missing_field_labels = []

        for field, label in required_fields.items():
            value = getattr(parent, field)
            if not value or (isinstance(value, str) and not value.strip()):
                missing_fields.append(field)
                missing_field_labels.append(label)

        # Calculate completion percentage
        total_fields = len(required_fields)
        completed_fields = total_fields - len(missing_fields)
        completion_percentage = (completed_fields / total_fields) * 100

        return {
            'is_complete': len(missing_fields) == 0,
            'missing_fields': missing_fields,
            'missing_field_labels': missing_field_labels,
            'completion_percentage': round(completion_percentage, 1),
            'total_fields': total_fields,
            'completed_fields': completed_fields
        }

    @staticmethod
    def get_parent_statistics(parent: Parent) -> Dict[str, any]:
        """
        Get statistics for a parent account

        Args:
            parent: Parent instance

        Returns:
            Dictionary with parent statistics
        """
        # This is a placeholder for future functionality
        # Will be expanded when children, appointments, etc. are implemented
        return {
            'total_children': 0,  # parent.children.count() when implemented
            'active_growth_plans': 0,  # parent.children.filter(growth_plans__status='Active').count()
            'upcoming_appointments': 0,  # parent.appointments.filter(status='Scheduled', scheduled_start_time__gte=now()).count()
            'completed_appointments': 0,  # parent.appointments.filter(status='Completed').count()
            'account_age_days': (parent.created_at.date() - parent.created_at.date()).days if parent.created_at else 0
        }