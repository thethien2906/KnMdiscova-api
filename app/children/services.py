# children/services.py
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from datetime import date, timedelta
import logging
from typing import Optional, Dict, Any, List, Tuple

from .models import Child
from parents.models import Parent
from users.models import User

logger = logging.getLogger(__name__)


class ChildProfileError(Exception):
    """Base exception for child profile related errors"""
    pass


class ChildNotFoundError(ChildProfileError):
    """Raised when child profile is not found"""
    pass


class ChildAccessDeniedError(ChildProfileError):
    """Raised when user doesn't have access to child profile"""
    pass


class ChildAgeValidationError(ChildProfileError):
    """Raised when child age validation fails"""
    pass


class ConsentManagementError(ChildProfileError):
    """Raised when consent management operations fail"""
    pass


class ChildService:
    """
    Service class for child profile management and business logic
    """

    @staticmethod
    def get_child_by_id(child_id: str) -> Optional[Child]:
        """
        Get child by ID - access control handled by permissions
        """
        try:
            return Child.objects.select_related('parent__user').get(id=child_id)
        except Child.DoesNotExist:
            logger.warning(f"Child {child_id} not found")
            return None

    @staticmethod
    def get_child_by_id_or_raise(child_id: str) -> Child:
        """
        Get child by ID or raise exception if not found
        """
        child = ChildService.get_child_by_id(child_id)
        if not child:
            raise ChildNotFoundError(f"Child {child_id} not found")
        return child

    @staticmethod
    def get_children_for_parent(parent: Parent) -> List[Child]:
        """
        Get all children for a specific parent
        """
        return Child.objects.filter(parent=parent).order_by('first_name', 'last_name')

    @staticmethod
    def create_child_profile(parent: Parent, child_data: Dict[str, Any]) -> Child:
        """
        Create a new child profile with business logic validation
        """
        # Validate parent is active and verified
        if not parent.user.is_active:
            error_msg = "Parent account is inactive"
            logger.error(f"Failed to create child profile for parent {parent.user.email}: {error_msg}")
            raise ChildProfileError(error_msg)
        if not parent.user.is_verified:
            error_msg = "Parent email must be verified before adding children"
            logger.error(f"Failed to create child profile for parent {parent.user.email}: {error_msg}")
            raise ChildProfileError(error_msg)
        # Validate parent type
        if not parent.user.is_parent:
            error_msg = "Only parents can create child profiles"
            logger.error(f"Failed to create child profile for parent {parent.user.email}: {error_msg}")
            raise ChildProfileError(error_msg)

        try:
            with transaction.atomic():
                # Validate child data according to business rules
                validated_data = ChildService.validate_child_data(child_data)
                # Check for duplicate children (same name + DOB for same parent)
                ChildService._check_duplicate_child(parent, validated_data)
                # Create child with parent relationship
                validated_data['parent'] = parent
                child = Child.objects.create(**validated_data)
                # Set default consent forms if not provided
                if not child.consent_forms_signed:
                    ChildService._initialize_default_consents(child)
                logger.info(f"Child profile created: {child.full_name} for parent {parent.user.email}")
                return child
        except Exception as e:
            logger.error(f"Failed to create child profile for parent {parent.user.email}: {str(e)}")
            raise ChildProfileError(f"Failed to create child profile: {str(e)}")
    @staticmethod
    def update_child_profile(child: Child, update_data: Dict[str, Any]) -> Child:
        """
        Update child profile with business logic validation
        Access control handled by permissions
        """
        # Validate parent is still active
        if not child.parent.user.is_active:
            raise ChildProfileError("Parent account is inactive")

        try:
            with transaction.atomic():
                # Validate update data
                validated_data = ChildService.validate_child_data(update_data, is_update=True)

                # Handle consent forms separately if included
                if 'consent_forms_signed' in validated_data:
                    consent_data = validated_data.pop('consent_forms_signed')
                    ChildService._update_consent_forms(child, consent_data)

                # Update other fields
                updated_fields = []
                allowed_fields = [
                    'first_name', 'last_name', 'nickname', 'date_of_birth', 'gender',
                    'profile_picture_url', 'height_cm', 'weight_kg', 'health_status',
                    'medical_history', 'vaccination_status', 'emotional_issues',
                    'social_behavior', 'developmental_concerns', 'family_peer_relationship',
                    'has_seen_psychologist', 'has_received_therapy', 'parental_goals',
                    'activity_tips', 'parental_notes', 'primary_language', 'school_grade_level'
                ]

                for field, value in validated_data.items():
                    if field in allowed_fields and hasattr(child, field):
                        setattr(child, field, value)
                        updated_fields.append(field)

                if updated_fields:
                    updated_fields.append('updated_at')
                    child.save(update_fields=updated_fields)
                    logger.info(f"Updated child profile {child.full_name}: {updated_fields}")

                return child

        except Exception as e:
            logger.error(f"Failed to update child profile {child.id}: {str(e)}")
            raise ChildProfileError(f"Failed to update child profile: {str(e)}")

    @staticmethod
    def delete_child_profile(child: Child) -> bool:
        """
        Delete child profile (soft delete consideration for future)
        Access control handled by permissions
        """
        try:
            with transaction.atomic():
                child_name = child.full_name
                parent_email = child.parent.user.email

                # In the future, consider soft delete for audit trail
                # For now, hard delete
                child.delete()

                logger.info(f"Child profile deleted: {child_name} for parent {parent_email}")
                return True

        except Exception as e:
            logger.error(f"Failed to delete child profile {child.id}: {str(e)}")
            raise ChildProfileError(f"Failed to delete child profile: {str(e)}")

    @staticmethod
    def get_child_profile_data(child: Child) -> Dict[str, Any]:
        """
        Get comprehensive child profile data with computed fields
        """
        return {
            'id': str(child.id),
            'parent_id': str(child.parent.user.id),
            'parent_email': child.parent.user.email,

            # Demographics
            'first_name': child.first_name,
            'last_name': child.last_name,
            'nickname': child.nickname,
            'full_name': child.full_name,
            'display_name': child.display_name,
            'date_of_birth': child.date_of_birth,
            'age': child.age,
            'age_in_months': child.age_in_months,
            'gender': child.gender,
            'profile_picture_url': child.profile_picture_url,

            # Physical information
            'height_cm': child.height_cm,
            'weight_kg': child.weight_kg,
            'bmi': child.bmi,

            # Health information
            'health_status': child.health_status,
            'medical_history': child.medical_history,
            'vaccination_status': child.vaccination_status,
            'is_vaccination_current': child.is_vaccination_current,

            # Behavioral information
            'emotional_issues': child.emotional_issues,
            'social_behavior': child.social_behavior,
            'developmental_concerns': child.developmental_concerns,
            'family_peer_relationship': child.family_peer_relationship,

            # Psychology history
            'has_seen_psychologist': child.has_seen_psychologist,
            'has_received_therapy': child.has_received_therapy,
            'has_psychology_history': child.has_psychology_history,

            # Parental input
            'parental_goals': child.parental_goals,
            'activity_tips': child.activity_tips,
            'parental_notes': child.parental_notes,

            # Educational information
            'primary_language': child.primary_language,
            'school_grade_level': child.school_grade_level,
            'age_appropriate_grades': child.get_age_appropriate_grade_suggestions(),

            # Consent management
            'consent_forms_signed': child.consent_forms_signed,
            'consent_summary': ChildService.get_consent_summary(child),

            # Profile metrics
            'profile_completeness': child.get_profile_completeness(),

            # Timestamps
            'created_at': child.created_at,
            'updated_at': child.updated_at,
        }

    @staticmethod
    def manage_consent(child: Child, consent_type: str, granted: bool,
                      parent_signature: str = None, notes: str = None) -> Child:
        """
        Manage consent for a specific child with audit trail
        Access control handled by permissions
        """
        # Validate consent type
        valid_consent_types = Child.get_default_consent_types().keys()
        if consent_type not in valid_consent_types:
            raise ConsentManagementError(f"Invalid consent type: {consent_type}")

        try:
            # Use the model's consent management method
            child.set_consent(
                consent_type=consent_type,
                granted=granted,
                parent_signature=parent_signature,
                notes=notes
            )

            action = "granted" if granted else "revoked"
            logger.info(f"Consent {action} for child {child.full_name}: {consent_type}")

            return child

        except Exception as e:
            logger.error(f"Failed to manage consent for child {child.id}: {str(e)}")
            raise ConsentManagementError(f"Failed to manage consent: {str(e)}")

    @staticmethod
    def bulk_consent_update(child: Child, consent_types: List[str], granted: bool,
                           parent_signature: str = None, notes: str = None) -> Child:
        """
        Update multiple consent types at once
        Access control handled by permissions
        """
        valid_consent_types = Child.get_default_consent_types().keys()

        # Validate all consent types
        for consent_type in consent_types:
            if consent_type not in valid_consent_types:
                raise ConsentManagementError(f"Invalid consent type: {consent_type}")

        try:
            with transaction.atomic():
                for consent_type in consent_types:
                    child.set_consent(
                        consent_type=consent_type,
                        granted=granted,
                        parent_signature=parent_signature,
                        notes=notes
                    )

                action = "granted" if granted else "revoked"
                logger.info(f"Bulk consent {action} for child {child.full_name}: {consent_types}")

                return child

        except Exception as e:
            logger.error(f"Failed to update bulk consent for child {child.id}: {str(e)}")
            raise ConsentManagementError(f"Failed to update bulk consent: {str(e)}")

    @staticmethod
    def get_consent_summary(child: Child) -> Dict[str, Any]:
        """
        Get consent status summary for a child
        """
        consent_types = Child.get_default_consent_types()
        summary = {
            'total_consents': len(consent_types),
            'granted_count': 0,
            'revoked_count': 0,
            'pending_count': 0,
            'consents': {}
        }

        for consent_type, description in consent_types.items():
            status = child.get_consent_status(consent_type)
            consent_details = child.consent_forms_signed.get(consent_type, {}) if child.consent_forms_signed else {}

            if consent_details:
                if status:
                    summary['granted_count'] += 1
                else:
                    summary['revoked_count'] += 1
            else:
                summary['pending_count'] += 1

            summary['consents'][consent_type] = {
                'description': description,
                'granted': status,
                'date_signed': consent_details.get('date_signed'),
                'parent_signature': consent_details.get('parent_signature'),
                'notes': consent_details.get('notes'),
                'version': consent_details.get('version', '1.0')
            }

        return summary


    @staticmethod
    def search_children(search_params: Dict[str, Any], user: User) -> List[Child]:
        """
        Search children with filters and proper access control
        """
        queryset = Child.objects.select_related('parent__user')

        # Apply access control filtering based on user type
        if user.user_type == 'Parent':
            # Parents can only see their own children
            try:
                parent = Parent.objects.get(user=user)
                queryset = queryset.filter(parent=parent)
            except Parent.DoesNotExist:
                # If parent profile doesn't exist, return empty queryset
                logger.warning(f"Parent profile not found for user {user.email}")
                return []
        elif user.user_type == 'Psychologist':
            # Psychologists can see all children (or implement specific logic)
            # TODO: Implement logic to filter children psychologist has worked with
            pass  # No additional filtering needed for now
        elif user.is_superuser or user.user_type == 'Admin':
            # Admins can see all children
            pass  # No additional filtering needed
        else:
            # Unknown user type, return empty results for security
            logger.warning(f"Unknown user type {user.user_type} attempting child search")
            return []

        # Apply search filters
        if search_params.get('first_name'):
            queryset = queryset.filter(first_name__icontains=search_params['first_name'])

        if search_params.get('last_name'):
            queryset = queryset.filter(last_name__icontains=search_params['last_name'])

        if search_params.get('parent_email'):
            queryset = queryset.filter(parent__user__email__icontains=search_params['parent_email'])

        if search_params.get('gender'):
            # Use exact match for gender instead of icontains to avoid partial matches
            # icontains would match "Male" in "Female", so we use exact matching
            queryset = queryset.filter(gender__iexact=search_params['gender'])

        if search_params.get('school_grade_level'):
            queryset = queryset.filter(school_grade_level__icontains=search_params['school_grade_level'])

        if search_params.get('has_psychology_history') is not None:
            has_history = search_params['has_psychology_history']
            if has_history:
                queryset = queryset.filter(
                    Q(has_seen_psychologist=True) | Q(has_received_therapy=True)
                )
            else:
                queryset = queryset.filter(has_seen_psychologist=False, has_received_therapy=False)

        # Age filtering
        age_min = search_params.get('age_min')
        age_max = search_params.get('age_max')
        if age_min or age_max:
            today = date.today()
            if age_max:
                min_birth_date = date(today.year - age_max - 1, today.month, today.day)
                queryset = queryset.filter(date_of_birth__gte=min_birth_date)
            if age_min:
                max_birth_date = date(today.year - age_min, today.month, today.day)
                queryset = queryset.filter(date_of_birth__lte=max_birth_date)

        # Date range filtering
        if search_params.get('created_after'):
            queryset = queryset.filter(created_at__gte=search_params['created_after'])

        if search_params.get('created_before'):
            queryset = queryset.filter(created_at__lte=search_params['created_before'])

        # Debug logging to help identify the issue
        logger.debug(f"User {user.email} search query: {queryset.query}")
        logger.debug(f"Search params: {search_params}")

        result = list(queryset.order_by('first_name', 'last_name'))
        logger.debug(f"Search results count: {len(result)} for user {user.email}")

        return result

    @staticmethod
    def validate_child_data(child_data: Dict[str, Any], is_update: bool = False) -> Dict[str, Any]:
        """
        Validate child data according to business rules
        """
        errors = {}

        # Validate required fields for creation
        if not is_update:
            if not child_data.get('first_name') or not child_data['first_name'].strip():
                errors['first_name'] = "First name is required"

            if not child_data.get('date_of_birth'):
                errors['date_of_birth'] = "Date of birth is required"

        # Validate age if date_of_birth is provided
        date_of_birth = child_data.get('date_of_birth')
        if date_of_birth:
            try:
                age = ChildService._calculate_age(date_of_birth)
                if age < 5:
                    errors['date_of_birth'] = "Child must be at least 5 years old"
                elif age > 17:
                    errors['date_of_birth'] = "Child must be 17 years old or younger"
            except (ValueError, TypeError):
                errors['date_of_birth'] = "Invalid date of birth"

        # Validate height/weight relationship
        height_cm = child_data.get('height_cm')
        weight_kg = child_data.get('weight_kg')
        if height_cm and weight_kg:
            try:
                bmi = weight_kg / ((height_cm / 100) ** 2)
                if bmi < 10 or bmi > 40:
                    errors['weight_kg'] = "Height and weight combination seems unusual"
            except (ValueError, ZeroDivisionError):
                errors['weight_kg'] = "Invalid height or weight values"

        # Validate consent forms structure if provided
        consent_forms = child_data.get('consent_forms_signed')
        if consent_forms is not None:
            consent_errors = ChildService._validate_consent_structure(consent_forms)
            if consent_errors:
                errors['consent_forms_signed'] = consent_errors

        if errors:
            raise ValidationError(errors)

        return child_data

    # Private helper methods

    @staticmethod
    def _user_can_access_child(user: User, child: Child) -> bool:
        """Check if user can access child profile"""
        # Admins can access all children
        if user.is_admin or user.is_staff:
            return True

        # Parents can access their own children
        if user.is_parent and child.parent.user == user:
            return True

        # Psychologists can access children they work with (future implementation)
        if user.is_psychologist:
            # TODO: Check if psychologist has worked with this child
            return False

        return False

    @staticmethod
    def _user_can_modify_child(user: User, child: Child) -> bool:
        """Check if user can modify child profile"""
        # Admins can modify all children
        if user.is_admin or user.is_staff:
            return True

        # Parents can modify their own children
        if user.is_parent and child.parent.user == user:
            return True

        # Psychologists cannot modify child profiles (only assessments/plans)
        return False

    @staticmethod
    def _check_duplicate_child(parent: Parent, child_data: Dict[str, Any]):
        """Check for duplicate children (same name + DOB)"""
        first_name = child_data.get('first_name')
        date_of_birth = child_data.get('date_of_birth')

        if first_name and date_of_birth:
            existing = Child.objects.filter(
                parent=parent,
                first_name__iexact=first_name,
                date_of_birth=date_of_birth
            ).exists()

            if existing:
                raise ChildProfileError(
                    f"A child with name '{first_name}' and date of birth '{date_of_birth}' already exists"
                )

    @staticmethod
    def _initialize_default_consents(child: Child):
        """Initialize default consent forms for new child"""
        default_consents = Child.get_default_consent_types()
        consent_data = {}

        for consent_type in default_consents.keys():
            consent_data[consent_type] = {
                'granted': False,
                'date_signed': None,
                'parent_signature': None,
                'notes': 'Default initialization - consent pending',
                'version': '1.0'
            }

        child.consent_forms_signed = consent_data
        child.save(update_fields=['consent_forms_signed', 'updated_at'])

    @staticmethod
    def _update_consent_forms(child: Child, consent_data: Dict[str, Any]):
        """Update consent forms with validation"""
        current_consents = child.consent_forms_signed or {}

        # Validate and merge consent data
        for consent_type, consent_info in consent_data.items():
            if consent_type in Child.get_default_consent_types().keys():
                current_consents[consent_type] = consent_info

        child.consent_forms_signed = current_consents
        child.save(update_fields=['consent_forms_signed', 'updated_at'])

    @staticmethod
    def _validate_consent_structure(consent_forms: Dict[str, Any]) -> List[str]:
        """Validate consent forms structure"""
        errors = []

        if not isinstance(consent_forms, dict):
            return ["Consent forms must be a dictionary"]

        valid_consent_types = Child.get_default_consent_types().keys()

        for consent_type, consent_data in consent_forms.items():
            if consent_type not in valid_consent_types:
                errors.append(f"Invalid consent type: {consent_type}")
                continue

            if not isinstance(consent_data, dict):
                errors.append(f"Consent data for {consent_type} must be a dictionary")
                continue

            if 'granted' not in consent_data:
                errors.append(f"Consent {consent_type} must include 'granted' field")
            elif not isinstance(consent_data['granted'], bool):
                errors.append(f"Consent {consent_type} 'granted' must be boolean")

        return errors

    @staticmethod
    def _calculate_age(date_of_birth) -> int:
        """Calculate age from date of birth"""
        if isinstance(date_of_birth, str):
            from datetime import datetime
            date_of_birth = datetime.strptime(date_of_birth, '%Y-%m-%d').date()

        today = date.today()
        age = today.year - date_of_birth.year

        if today.month < date_of_birth.month or (today.month == date_of_birth.month and today.day < date_of_birth.day):
            age -= 1

        return age