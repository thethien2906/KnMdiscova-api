# psychologists/services.py
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q, F, Count, Avg, Case, When, Value, BooleanField
from django.utils.translation import gettext_lazy as _
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional, Tuple, Any
import logging

from .models import Psychologist, PsychologistAvailability
from users.services import UserService

User = get_user_model()
logger = logging.getLogger(__name__)


class PsychologistRegistrationError(Exception):
    """Raised when psychologist registration fails due to business rules"""
    pass


class PsychologistNotFoundError(Exception):
    """Raised when psychologist is not found"""
    pass


class AvailabilityConflictError(Exception):
    """Raised when there's a scheduling conflict"""
    pass


class VerificationError(Exception):
    """Raised when verification business rules are violated"""
    pass


class PsychologistService:
    """
    Service layer for psychologist-related business logic
    """

    @staticmethod
    @transaction.atomic
    def register_psychologist(validated_data: Dict[str, Any]) -> Psychologist:
        """
        Register a new psychologist with complete profile setup

        Args:
            validated_data: Already validated data from serializer

        Returns:
            Psychologist: Newly created psychologist instance

        Raises:
            PsychologistRegistrationError: If business rules are violated
        """
        try:
            # Extract user data
            user_data = {
                'email': validated_data.pop('email'),
                'password': validated_data.pop('password'),
                'user_type': 'Psychologist'
            }
            validated_data.pop('password_confirm', None)  # Remove confirmation field

            # Create user through UserService
            user = UserService.create_user(**user_data)

            # Create psychologist profile
            psychologist = Psychologist.objects.create(
                user=user,
                **validated_data
            )

            logger.info(f"Psychologist registered successfully: {psychologist.user.email}")
            return psychologist

        except Exception as e:
            logger.error(f"Psychologist registration failed: {str(e)}")
            raise PsychologistRegistrationError(f"Registration failed: {str(e)}")

    @staticmethod
    def get_psychologist_by_user_id(user_id: str) -> Psychologist:
        """
        Get psychologist by user ID

        Args:
            user_id: User ID

        Returns:
            Psychologist: Psychologist instance

        Raises:
            PsychologistNotFoundError: If psychologist not found
        """
        try:
            return Psychologist.objects.select_related('user').get(user_id=user_id)
        except Psychologist.DoesNotExist:
            raise PsychologistNotFoundError(f"Psychologist with user ID {user_id} not found")

    @staticmethod
    def get_psychologist_by_license(license_number: str) -> Psychologist:
        """
        Get psychologist by license number

        Args:
            license_number: License number

        Returns:
            Psychologist: Psychologist instance

        Raises:
            PsychologistNotFoundError: If psychologist not found
        """
        try:
            return Psychologist.objects.select_related('user').get(
                license_number=license_number
            )
        except Psychologist.DoesNotExist:
            raise PsychologistNotFoundError(f"Psychologist with license {license_number} not found")

    @staticmethod
    def update_psychologist_profile(psychologist: Psychologist, validated_data: Dict[str, Any]) -> Psychologist:
        """
        Update psychologist profile with business rule validation

        Args:
            psychologist: Psychologist instance to update
            validated_data: Already validated data from serializer

        Returns:
            Psychologist: Updated psychologist instance

        Raises:
            PsychologistRegistrationError: If business rules are violated
        """
        try:
            # Check if psychologist can update certain fields based on verification status
            restricted_fields = ['license_number', 'license_issuing_authority', 'license_expiry_date']

            if (psychologist.verification_status == 'Approved' and
                any(field in validated_data for field in restricted_fields)):

                # Log the attempt for audit purposes
                logger.warning(f"Approved psychologist {psychologist.user.email} attempted to modify restricted fields")

                # Allow update but trigger re-verification
                psychologist.verification_status = 'Pending'
                logger.info(f"Psychologist {psychologist.user.email} status changed to Pending due to profile changes")

            # Update fields
            for field, value in validated_data.items():
                setattr(psychologist, field, value)

            psychologist.save()
            logger.info(f"Psychologist profile updated: {psychologist.user.email}")
            return psychologist

        except Exception as e:
            logger.error(f"Profile update failed for {psychologist.user.email}: {str(e)}")
            raise PsychologistRegistrationError(f"Profile update failed: {str(e)}")

    @staticmethod
    def search_psychologists(search_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search psychologists with advanced filtering

        Args:
            search_params: Search parameters from validated serializer

        Returns:
            Dict containing queryset and metadata
        """
        queryset = Psychologist.objects.select_related('user').filter(
            user__is_active=True,
            verification_status='Approved'
        )

        # Text search
        search_query = search_params.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(biography__icontains=search_query)
            )

        # Experience filters
        min_experience = search_params.get('min_experience')
        if min_experience is not None:
            queryset = queryset.filter(years_of_experience__gte=min_experience)

        max_experience = search_params.get('max_experience')
        if max_experience is not None:
            queryset = queryset.filter(years_of_experience__lte=max_experience)

        # Rate filters
        min_rate = search_params.get('min_rate')
        if min_rate is not None:
            queryset = queryset.filter(hourly_rate__gte=min_rate)

        max_rate = search_params.get('max_rate')
        if max_rate is not None:
            queryset = queryset.filter(hourly_rate__lte=max_rate)

        # Verification status filter
        verification_status = search_params.get('verification_status')
        if verification_status:
            queryset = queryset.filter(verification_status=verification_status)

        # Availability filter
        available_on = search_params.get('available_on')
        if available_on:
            queryset = PsychologistService._filter_by_availability(queryset, available_on)

        # Annotate with computed fields
        queryset = queryset.annotate(
            can_accept_appointments_flag=Case(
                When(
                    Q(user__is_active=True) &
                    Q(verification_status='Approved'),
                    then=Value(True)
                ),
                default=Value(False),
                output_field=BooleanField()
            )
        )

        # Apply ordering
        ordering = search_params.get('ordering', '-created_at')
        queryset = queryset.order_by(ordering)

        return {
            'queryset': queryset,
            'total_count': queryset.count(),
            'search_params': search_params
        }

    @staticmethod
    def _filter_by_availability(queryset, available_date: date):
        """
        Filter psychologists by availability on a specific date

        Args:
            queryset: Base queryset
            available_date: Date to check availability

        Returns:
            Filtered queryset
        """
        day_of_week = available_date.weekday()
        # Convert to our format (0=Sunday, 6=Saturday)
        day_of_week = (day_of_week + 1) % 7

        # Get psychologists with availability on that day
        available_psychologist_ids = PsychologistAvailability.objects.filter(
            Q(
                is_recurring=True,
                day_of_week=day_of_week,
                is_booked=False
            ) |
            Q(
                is_recurring=False,
                specific_date=available_date,
                is_booked=False
            )
        ).values_list('psychologist_id', flat=True).distinct()

        return queryset.filter(user_id__in=available_psychologist_ids)

    @staticmethod
    def verify_psychologist(psychologist: Psychologist, verification_data: Dict[str, Any]) -> Psychologist:
        """
        Handle psychologist verification process

        Args:
            psychologist: Psychologist to verify
            verification_data: Verification data from admin

        Returns:
            Updated psychologist instance

        Raises:
            VerificationError: If verification rules are violated
        """
        try:
            new_status = verification_data.get('verification_status')
            admin_notes = verification_data.get('admin_notes', '')

            # Business rule: Cannot go from Approved back to Pending
            if (psychologist.verification_status == 'Approved' and
                new_status == 'Pending'):
                raise VerificationError("Cannot change status from Approved back to Pending")

            # Business rule: Rejection requires admin notes
            if new_status == 'Rejected' and not admin_notes.strip():
                raise VerificationError("Admin notes are required when rejecting a psychologist")

            # Check license expiry for approval
            if new_status == 'Approved':
                if (psychologist.license_expiry_date and
                    psychologist.license_expiry_date <= timezone.now().date()):
                    raise VerificationError("Cannot approve psychologist with expired license")

            # Update verification status
            psychologist.verification_status = new_status
            psychologist.admin_notes = admin_notes
            psychologist.save()

            # Log verification action
            logger.info(f"Psychologist {psychologist.user.email} verification status changed to {new_status}")

            return psychologist

        except Exception as e:
            logger.error(f"Verification failed for {psychologist.user.email}: {str(e)}")
            raise VerificationError(f"Verification failed: {str(e)}")


class AvailabilityService:
    """
    Service layer for psychologist availability management
    """

    @staticmethod
    def create_availability_slot(psychologist: Psychologist, slot_data: Dict[str, Any]) -> PsychologistAvailability:
        """
        Create a new availability slot with conflict checking

        Args:
            psychologist: Psychologist instance
            slot_data: Validated slot data

        Returns:
            Created availability slot

        Raises:
            AvailabilityConflictError: If there's a scheduling conflict
        """
        try:
            # Check for overlapping slots
            conflicts = AvailabilityService._check_conflicts(psychologist, slot_data)
            if conflicts.exists():
                raise AvailabilityConflictError("Time slot conflicts with existing availability")

            # Create the slot
            availability_slot = PsychologistAvailability.objects.create(
                psychologist=psychologist,
                **slot_data
            )

            logger.info(f"Availability slot created for {psychologist.user.email}")
            return availability_slot

        except Exception as e:
            logger.error(f"Failed to create availability slot: {str(e)}")
            raise AvailabilityConflictError(f"Failed to create availability slot: {str(e)}")

    @staticmethod
    def update_availability_slot(slot, update_data):
        """Update an availability slot"""
        # Check if slot is booked
        if slot.is_booked:
            raise AvailabilityConflictError("Cannot modify booked availability slot")

        # Create a copy of the slot data for conflict checking
        check_data = {
            'day_of_week': update_data.get('day_of_week', slot.day_of_week),
            'start_time': update_data.get('start_time', slot.start_time),
            'end_time': update_data.get('end_time', slot.end_time),
            'specific_date': update_data.get('specific_date', slot.specific_date),
            'is_recurring': update_data.get('is_recurring', slot.is_recurring)
        }

        # Check for conflicts with other slots (excluding current slot)
        conflicts = AvailabilityService._check_conflicts(
            slot.psychologist,
            check_data,
            exclude_slot_id=slot.id
        )

        if conflicts.exists():  # Make sure this line exists and works correctly
            raise AvailabilityConflictError("Time slot conflicts with existing availability")

        # Update the slot
        for field, value in update_data.items():
            setattr(slot, field, value)

        slot.save()
        return slot

    @staticmethod
    def delete_availability_slot(slot: PsychologistAvailability) -> None:
        """
        Delete an availability slot

        Args:
            slot: Availability slot to delete

        Raises:
            AvailabilityConflictError: If slot is booked
        """
        try:
            if slot.is_booked:
                raise AvailabilityConflictError("Cannot delete booked availability slot")

            psychologist_email = slot.psychologist.user.email
            slot.delete()

            logger.info(f"Availability slot deleted for {psychologist_email}")

        except Exception as e:
            logger.error(f"Failed to delete availability slot: {str(e)}")
            raise AvailabilityConflictError(f"Failed to delete availability slot: {str(e)}")

    @staticmethod
    def bulk_manage_availability(psychologist: Psychologist, bulk_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle bulk availability operations

        Args:
            psychologist: Psychologist instance
            bulk_data: Validated bulk operation data

        Returns:
            Operation results

        Raises:
            AvailabilityConflictError: If bulk operation fails
        """
        operation = bulk_data.get('operation')
        results = {
            'operation': operation,
            'successful': [],
            'failed': [],
            'total_processed': 0
        }

        try:
            with transaction.atomic():
                if operation == 'create':
                    return AvailabilityService._bulk_create(psychologist, bulk_data, results)
                elif operation == 'update':
                    return AvailabilityService._bulk_update(psychologist, bulk_data, results)
                elif operation == 'delete':
                    return AvailabilityService._bulk_delete(psychologist, bulk_data, results)
                else:
                    raise AvailabilityConflictError(f"Unknown operation: {operation}")

        except Exception as e:
            logger.error(f"Bulk availability operation failed: {str(e)}")
            raise AvailabilityConflictError(f"Bulk operation failed: {str(e)}")

    @staticmethod
    def _bulk_create(psychologist: Psychologist, bulk_data: Dict[str, Any], results: Dict[str, Any]) -> Dict[str, Any]:
        """Handle bulk create operation"""
        slots_data = bulk_data.get('availability_slots', [])

        for slot_data in slots_data:
            try:
                slot = AvailabilityService.create_availability_slot(psychologist, slot_data)
                results['successful'].append({
                    'id': slot.id,
                    'day_of_week': slot.day_of_week,
                    'start_time': slot.start_time,
                    'end_time': slot.end_time
                })
            except Exception as e:
                results['failed'].append({
                    'data': slot_data,
                    'error': str(e)
                })

        results['total_processed'] = len(slots_data)
        return results

    @staticmethod
    def _bulk_update(psychologist: Psychologist, bulk_data: Dict[str, Any], results: Dict[str, Any]) -> Dict[str, Any]:
        """Handle bulk update operation"""
        slots_data = bulk_data.get('availability_slots', [])

        for slot_data in slots_data:
            try:
                slot_id = slot_data.get('id')
                if not slot_id:
                    raise ValueError("Slot ID is required for update operation")

                slot = PsychologistAvailability.objects.get(
                    id=slot_id,
                    psychologist=psychologist
                )

                updated_slot = AvailabilityService.update_availability_slot(slot, slot_data)
                results['successful'].append({
                    'id': updated_slot.id,
                    'day_of_week': updated_slot.day_of_week,
                    'start_time': updated_slot.start_time,
                    'end_time': updated_slot.end_time
                })
            except Exception as e:
                results['failed'].append({
                    'data': slot_data,
                    'error': str(e)
                })

        results['total_processed'] = len(slots_data)
        return results

    @staticmethod
    def _bulk_delete(psychologist: Psychologist, bulk_data: Dict[str, Any], results: Dict[str, Any]) -> Dict[str, Any]:
        """Handle bulk delete operation"""
        slot_ids = bulk_data.get('slot_ids', [])

        for slot_id in slot_ids:
            try:
                slot = PsychologistAvailability.objects.get(
                    id=slot_id,
                    psychologist=psychologist
                )
                AvailabilityService.delete_availability_slot(slot)
                results['successful'].append({'id': slot_id})
            except Exception as e:
                results['failed'].append({
                    'id': slot_id,
                    'error': str(e)
                })

        results['total_processed'] = len(slot_ids)
        return results

    @staticmethod
    def _check_conflicts(psychologist, slot_data, exclude_slot_id=None):
        """Check for availability conflicts"""
        queryset = PsychologistAvailability.objects.filter(
            psychologist=psychologist
        )

        if exclude_slot_id:
            queryset = queryset.exclude(id=exclude_slot_id)

        # Check conflicts based on whether it's recurring or specific date
        if slot_data.get('is_recurring', False):
            # Check recurring slots on same day
            conflicts = queryset.filter(
                day_of_week=slot_data['day_of_week'],
                is_recurring=True
            )
        else:
            # Check specific date slots
            conflicts = queryset.filter(
                specific_date=slot_data['specific_date'],
                is_recurring=False
            )

        # Filter by time overlap
        start_time = slot_data['start_time']
        end_time = slot_data['end_time']

        # A conflict exists if:
        # - New start time is before existing end time AND
        # - New end time is after existing start time
        time_conflicts = conflicts.filter(
            start_time__lt=end_time,
            end_time__gt=start_time
        )

        return time_conflicts

    @staticmethod
    def get_psychologist_availability(psychologist: Psychologist, date_range: Optional[Tuple[date, date]] = None):
        """
        Get psychologist's availability within a date range

        Args:
            psychologist: Psychologist instance
            date_range: Optional tuple of (start_date, end_date)

        Returns:
            Queryset of availability slots
        """
        queryset = PsychologistAvailability.objects.filter(
            psychologist=psychologist
        ).order_by('day_of_week', 'start_time', 'specific_date')

        if date_range:
            start_date, end_date = date_range
            # Filter specific date slots within range
            queryset = queryset.filter(
                Q(is_recurring=True) |  # Include all recurring slots
                Q(is_recurring=False, specific_date__range=(start_date, end_date))
            )

        return queryset