# appointments/services/reservation_service
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from datetime import timedelta, datetime, date
from typing import List, Optional, Dict, Any
import logging

from ..models import AppointmentSlot, Appointment
from users.models import User
from psychologists.models import Psychologist

logger = logging.getLogger(__name__)


class SlotReservationError(Exception):
    """Base exception for slot reservation errors"""
    pass


class SlotNotAvailableError(SlotReservationError):
    """Raised when slot is not available for reservation"""
    pass


class ReservationNotFoundError(SlotReservationError):
    """Raised when trying to access a reservation that doesn't exist"""
    pass


class SlotReservationService:
    """
    Service for managing temporary slot reservations during payment process
    """

    # Default reservation duration (30 minutes should be enough for payment)
    DEFAULT_RESERVATION_DURATION_MINUTES = 30

    @staticmethod
    def reserve_slots_for_appointment(
        psychologist: Psychologist,
        start_slot_id: int,
        session_type: str,
        user: User,
        duration_minutes: int = None
    ) -> List[AppointmentSlot]:
        """
        Reserve slots for an appointment (handles both 1-hour and 2-hour bookings)

        Args:
            psychologist: Psychologist for the appointment
            start_slot_id: ID of the first slot to reserve
            session_type: 'OnlineMeeting' or 'InitialConsultation'
            user: User making the reservation
            duration_minutes: Reservation duration (defaults to DEFAULT_RESERVATION_DURATION_MINUTES)

        Returns:
            List of reserved AppointmentSlot instances

        Raises:
            SlotNotAvailableError: If slots are not available
            SlotReservationError: If reservation fails
        """
        if duration_minutes is None:
            duration_minutes = SlotReservationService.DEFAULT_RESERVATION_DURATION_MINUTES

        try:
            with transaction.atomic():
                # Determine number of slots needed
                slots_needed = 1 if session_type == 'OnlineMeeting' else 2

                # Get the starting slot
                try:
                    start_slot = AppointmentSlot.objects.select_for_update().get(
                        slot_id=start_slot_id,
                        psychologist=psychologist
                    )
                except AppointmentSlot.DoesNotExist:
                    raise SlotNotAvailableError(f"Starting slot {start_slot_id} not found")

                # Find consecutive slots
                slots_to_reserve = SlotReservationService._find_consecutive_slots_for_reservation(
                    start_slot, slots_needed
                )

                # Reserve all slots
                reserved_slots = []
                for slot in slots_to_reserve:
                    try:
                        slot.reserve_for_payment(user, duration_minutes)
                        reserved_slots.append(slot)
                    except ValidationError as e:
                        # If any slot fails to reserve, release all previously reserved slots
                        SlotReservationService._release_slots(reserved_slots, user)
                        raise SlotNotAvailableError(f"Failed to reserve slot {slot.slot_id}: {str(e)}")

                logger.info(
                    f"Reserved {len(reserved_slots)} slots for user {user.email} "
                    f"(session: {session_type}, duration: {duration_minutes}min)"
                )
                return reserved_slots

        except Exception as e:
            logger.error(f"Failed to reserve slots for user {user.email}: {str(e)}")
            if isinstance(e, SlotReservationError):
                raise
            raise SlotReservationError(f"Slot reservation failed: {str(e)}")

    @staticmethod
    def _find_consecutive_slots_for_reservation(
        start_slot: AppointmentSlot,
        slots_needed: int
    ) -> List[AppointmentSlot]:
        """
        Find consecutive slots starting from the given slot

        Args:
            start_slot: Starting slot
            slots_needed: Number of consecutive slots needed

        Returns:
            List of consecutive slots

        Raises:
            SlotNotAvailableError: If not enough consecutive slots available
        """
        slots = [start_slot]

        if slots_needed == 1:
            # Validate the single slot is available
            if start_slot.is_booked:
                raise SlotNotAvailableError("Starting slot is already booked")
            if (start_slot.reservation_status == 'reserved' and
                start_slot.reserved_until and
                start_slot.reserved_until > timezone.now()):
                raise SlotNotAvailableError("Starting slot is already reserved")
            return slots

        # For multi-slot appointments (InitialConsultation)
        current_slot = start_slot

        for i in range(1, slots_needed):
            # Calculate next hour slot time
            current_start_dt = datetime.combine(date.today(), current_slot.start_time)
            next_start_dt = current_start_dt + timedelta(hours=1)
            next_start_time = next_start_dt.time()

            try:
                next_slot = AppointmentSlot.objects.select_for_update().get(
                    psychologist=current_slot.psychologist,
                    slot_date=current_slot.slot_date,
                    start_time=next_start_time
                )

                # Check if next slot is available
                if next_slot.is_booked:
                    raise SlotNotAvailableError(
                        f"Consecutive slot at {next_start_time} is already booked"
                    )
                if (next_slot.reservation_status == 'reserved' and
                    next_slot.reserved_until and
                    next_slot.reserved_until > timezone.now()):
                    raise SlotNotAvailableError(
                        f"Consecutive slot at {next_start_time} is already reserved"
                    )

                slots.append(next_slot)
                current_slot = next_slot

            except AppointmentSlot.DoesNotExist:
                raise SlotNotAvailableError(
                    f"No consecutive slot available at {next_start_time}"
                )

        return slots

    @staticmethod
    def release_user_reservations(
        user: User,
        appointment_id: str = None,
        psychologist: Psychologist = None
    ) -> int:
        """
        Release all reservations made by a user

        Args:
            user: User whose reservations to release
            appointment_id: Optional specific appointment ID
            psychologist: Optional filter by psychologist

        Returns:
            Number of slots released
        """
        try:
            with transaction.atomic():
                queryset = AppointmentSlot.objects.filter(
                    reserved_by=user,
                    reservation_status='reserved'
                )

                if psychologist:
                    queryset = queryset.filter(psychologist=psychologist)

                # If appointment_id provided, we can filter by slots used in that appointment
                # (This would require additional logic to link reservations to appointments)

                slots_to_release = list(queryset.select_for_update())

                for slot in slots_to_release:
                    slot.release_reservation(user)

                logger.info(f"Released {len(slots_to_release)} reservations for user {user.email}")
                return len(slots_to_release)

        except Exception as e:
            logger.error(f"Failed to release reservations for user {user.email}: {str(e)}")
            return 0

    @staticmethod
    def _release_slots(slots: List[AppointmentSlot], user: User):
        """Helper method to release a list of slots"""
        for slot in slots:
            try:
                slot.release_reservation(user)
            except Exception as e:
                logger.warning(f"Failed to release slot {slot.slot_id}: {str(e)}")

    @staticmethod
    def confirm_reservations_to_bookings(
        user: User,
        psychologist: 'Psychologist',  # Change this parameter
        appointment: Appointment = None  # Make this optional
    ) -> List[AppointmentSlot]:
        """
        Convert user's reservations to permanent bookings

        Args:
            user: User who made the reservations
            psychologist: Psychologist for the appointment
            appointment: Optional appointment (for logging purposes)

        Returns:
            List of confirmed slots

        Raises:
            ReservationNotFoundError: If no reservations found
            SlotReservationError: If confirmation fails
        """
        try:
            with transaction.atomic():
                # Find all slots reserved by this user for this psychologist
                reserved_slots = AppointmentSlot.objects.filter(
                    reserved_by=user,
                    reservation_status='reserved',
                    psychologist=psychologist,
                    reserved_until__gt=timezone.now()  # Only non-expired reservations
                ).select_for_update()

                if not reserved_slots.exists():
                    raise ReservationNotFoundError(
                        f"No valid reservations found for user {user.email}"
                    )

                confirmed_slots = []
                for slot in reserved_slots:
                    try:
                        slot.confirm_reservation_to_booking(user)
                        confirmed_slots.append(slot)
                    except ValidationError as e:
                        logger.error(f"Failed to confirm slot {slot.slot_id}: {str(e)}")
                        # Continue with other slots rather than failing completely

                appointment_ref = appointment.appointment_id if appointment else "new appointment"
                logger.info(
                    f"Confirmed {len(confirmed_slots)} slot reservations for {appointment_ref}"
                )
                return confirmed_slots

        except Exception as e:
            appointment_ref = appointment.appointment_id if appointment else "new appointment"
            logger.error(f"Failed to confirm reservations for {appointment_ref}: {str(e)}")
            if isinstance(e, SlotReservationError):
                raise
            raise SlotReservationError(f"Reservation confirmation failed: {str(e)}")

    @staticmethod
    def cleanup_expired_reservations() -> Dict[str, int]:
        """
        Clean up all expired reservations across the system

        Returns:
            Dict with cleanup statistics
        """
        try:
            expired_count = AppointmentSlot.cleanup_expired_reservations()

            logger.info(f"Cleaned up {expired_count} expired slot reservations")
            return {
                'expired_reservations_cleaned': expired_count,
                'cleanup_timestamp': timezone.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to cleanup expired reservations: {str(e)}")
            return {
                'expired_reservations_cleaned': 0,
                'error': str(e),
                'cleanup_timestamp': timezone.now().isoformat()
            }

    @staticmethod
    def get_user_reservations(
        user: User,
        include_expired: bool = False
    ) -> List[AppointmentSlot]:
        """
        Get all reservations for a user

        Args:
            user: User to get reservations for
            include_expired: Whether to include expired reservations

        Returns:
            List of reserved slots
        """
        queryset = AppointmentSlot.objects.filter(
            reserved_by=user,
            reservation_status='reserved'
        ).select_related('psychologist__user')

        if not include_expired:
            queryset = queryset.filter(reserved_until__gt=timezone.now())

        return list(queryset.order_by('slot_date', 'start_time'))

    @staticmethod
    def extend_reservation(
        slot: AppointmentSlot,
        user: User,
        additional_minutes: int = 15
    ) -> AppointmentSlot:
        """
        Extend an existing reservation

        Args:
            slot: Slot to extend reservation for
            user: User who owns the reservation
            additional_minutes: Minutes to add to reservation

        Returns:
            Updated slot

        Raises:
            SlotReservationError: If extension fails
        """
        try:
            if not slot.is_reserved_by_user(user):
                raise SlotReservationError("No valid reservation found for this user")

            if slot.reserved_until <= timezone.now():
                raise SlotReservationError("Cannot extend expired reservation")

            slot.reserved_until = slot.reserved_until + timedelta(minutes=additional_minutes)
            slot.save(update_fields=['reserved_until', 'updated_at'])

            logger.info(f"Extended reservation for slot {slot.slot_id} by {additional_minutes} minutes")
            return slot

        except Exception as e:
            logger.error(f"Failed to extend reservation for slot {slot.slot_id}: {str(e)}")
            raise SlotReservationError(f"Reservation extension failed: {str(e)}")

    @staticmethod
    def check_slot_availability_for_booking(
        psychologist: Psychologist,
        start_slot_id: int,
        session_type: str,
        user: User = None
    ) -> Dict[str, Any]:
        """
        Check if slots are available for booking (considering reservations)

        Args:
            psychologist: Psychologist for the appointment
            start_slot_id: Starting slot ID
            session_type: Session type ('OnlineMeeting' or 'InitialConsultation')
            user: Optional user (to allow their own reservations)

        Returns:
            Dict with availability information
        """
        try:
            slots_needed = 1 if session_type == 'OnlineMeeting' else 2

            # Get starting slot
            try:
                start_slot = AppointmentSlot.objects.get(
                    slot_id=start_slot_id,
                    psychologist=psychologist
                )
            except AppointmentSlot.DoesNotExist:
                return {
                    'available': False,
                    'reason': 'Starting slot not found',
                    'slots_checked': 0
                }

            # Check consecutive slots availability
            slots_to_check = SlotReservationService._get_consecutive_slots_for_check(
                start_slot, slots_needed
            )

            if len(slots_to_check) < slots_needed:
                return {
                    'available': False,
                    'reason': f'Only {len(slots_to_check)} consecutive slots found, need {slots_needed}',
                    'slots_checked': len(slots_to_check)
                }

            # Check each slot's availability
            for i, slot in enumerate(slots_to_check):
                if slot.is_booked:
                    return {
                        'available': False,
                        'reason': f'Slot {i+1} is already booked',
                        'blocked_slot_id': slot.slot_id,
                        'slots_checked': i + 1
                    }

                # Check reservations (allow if reserved by the same user)
                if (slot.reservation_status == 'reserved' and
                    slot.reserved_until and
                    slot.reserved_until > timezone.now()):
                    if not user or slot.reserved_by != user:
                        return {
                            'available': False,
                            'reason': f'Slot {i+1} is reserved by another user',
                            'blocked_slot_id': slot.slot_id,
                            'reserved_until': slot.reserved_until.isoformat(),
                            'slots_checked': i + 1
                        }

            return {
                'available': True,
                'slots_checked': len(slots_to_check),
                'slot_ids': [slot.slot_id for slot in slots_to_check]
            }

        except Exception as e:
            logger.error(f"Error checking slot availability: {str(e)}")
            return {
                'available': False,
                'reason': f'Availability check failed: {str(e)}',
                'slots_checked': 0
            }

    @staticmethod
    def _get_consecutive_slots_for_check(
        start_slot: AppointmentSlot,
        slots_needed: int
    ) -> List[AppointmentSlot]:
        """
        Get consecutive slots for availability checking (doesn't lock them)
        """
        slots = [start_slot]

        if slots_needed == 1:
            return slots

        current_slot = start_slot

        for i in range(1, slots_needed):
            current_start_dt = datetime.combine(date.today(), current_slot.start_time)
            next_start_dt = current_start_dt + timedelta(hours=1)
            next_start_time = next_start_dt.time()

            try:
                next_slot = AppointmentSlot.objects.get(
                    psychologist=current_slot.psychologist,
                    slot_date=current_slot.slot_date,
                    start_time=next_start_time
                )
                slots.append(next_slot)
                current_slot = next_slot
            except AppointmentSlot.DoesNotExist:
                break  # Return partial list

        return slots