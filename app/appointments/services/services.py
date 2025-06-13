# appointments/services/services.py
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from django.conf import settings
from datetime import date, datetime, timedelta, time
import logging
from typing import Optional, Dict, Any, List, Tuple
import uuid
from .reservation_service import SlotReservationService, SlotReservationError

from ..models import Appointment, AppointmentSlot
from psychologists.models import Psychologist, PsychologistAvailability
from parents.models import Parent
from children.models import Child
from users.models import User

logger = logging.getLogger(__name__)


# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class AppointmentServiceError(Exception):
    """Base exception for appointment service related errors"""
    pass


class AppointmentBookingError(AppointmentServiceError):
    """Raised when appointment booking fails"""
    pass


class SlotNotAvailableError(AppointmentBookingError):
    """Raised when requested slot is not available"""
    pass


class InsufficientConsecutiveSlotsError(AppointmentBookingError):
    """Raised when not enough consecutive slots available for multi-hour appointments"""
    pass


class AppointmentNotFoundError(AppointmentServiceError):
    """Raised when appointment is not found"""
    pass


class AppointmentAccessDeniedError(AppointmentServiceError):
    """Raised when user doesn't have access to appointment"""
    pass


class AppointmentCancellationError(AppointmentServiceError):
    """Raised when appointment cancellation fails"""
    pass


class QRVerificationError(AppointmentServiceError):
    """Raised when QR verification fails"""
    pass


class SlotGenerationError(AppointmentServiceError):
    """Raised when slot generation fails"""
    pass

# ============================================================================
# SLOT GENERATION SERVICE
# ============================================================================

class AppointmentSlotService:
    """
    Service for generating and managing appointment slots from availability blocks
    """

    @staticmethod
    def generate_slots_from_availability_block(availability_block: PsychologistAvailability,
                                             date_from: date = None, date_to: date = None) -> List[AppointmentSlot]:
        """
        Generate 1-hour appointment slots from a psychologist availability block

        Args:
            availability_block: PsychologistAvailability instance
            date_from: Start date for slot generation (default: today)
            date_to: End date for slot generation (default: +30 days)

        Returns:
            List of created AppointmentSlot instances
        """
        if availability_block.end_time <= availability_block.start_time:
            raise SlotGenerationError("Availability block has invalid time range: end time must be after start time.")

        if not date_from:
            date_from = date.today()
        if not date_to:
            date_to = date_from + timedelta(days=settings.AUTO_GENERATION_DAYS_AHEAD)

        created_slots = []

        try:
            if availability_block.is_recurring:
                # Generate slots for recurring availability
                current_date = date_from
                while current_date <= date_to:
                    # Check if current date matches the availability block's day of week
                    day_of_week = current_date.weekday()
                    # Convert Python weekday (0=Monday) to our format (0=Sunday)
                    day_of_week = (day_of_week + 1) % 7

                    if day_of_week == availability_block.day_of_week:
                        slots = AppointmentSlotService._generate_slots_for_date(
                            availability_block, current_date
                        )
                        created_slots.extend(slots)

                    current_date += timedelta(days=1)

            else:
                # Generate slots for specific date availability
                if date_from <= availability_block.specific_date <= date_to:
                    slots = AppointmentSlotService._generate_slots_for_date(
                        availability_block, availability_block.specific_date
                    )
                    created_slots.extend(slots)

            logger.info(f"Generated {len(created_slots)} slots for availability block {availability_block.availability_id}")
            return created_slots

        except Exception as e:
            logger.error(f"Failed to generate slots for availability block {availability_block.availability_id}: {str(e)}")
            raise SlotGenerationError(f"Failed to generate slots: {str(e)}")

    @staticmethod
    def _generate_slots_for_date(availability_block: PsychologistAvailability, target_date: date) -> List[AppointmentSlot]:
        """
        Generate slots for a specific date from an availability block
        """
        slots = []
        current_time = availability_block.start_time

        while True:
            # Calculate end time for this slot (1 hour later)
            current_dt = datetime.combine(date.today(), current_time)
            slot_end_dt = current_dt + timedelta(hours=1)
            slot_end_time = slot_end_dt.time()

            # Check if this slot would exceed the availability block's end time
            if slot_end_time > availability_block.end_time:
                break

            # Check if slot already exists (prevent duplicates)
            existing_slot = AppointmentSlot.objects.filter(
                psychologist=availability_block.psychologist,
                slot_date=target_date,
                start_time=current_time
            ).first()

            if not existing_slot:
                # Create the slot
                try:
                    slot = AppointmentSlot.objects.create(
                        psychologist=availability_block.psychologist,
                        availability_block=availability_block,
                        slot_date=target_date,
                        start_time=current_time,
                        end_time=slot_end_time
                    )
                    slots.append(slot)
                except ValidationError as e:
                    logger.warning(f"Failed to create slot for {target_date} {current_time}: {str(e)}")

            # Move to next hour
            current_time = slot_end_time

        return slots

    @staticmethod
    def bulk_generate_slots_for_psychologist(psychologist: Psychologist,
                                           date_from: date = None, date_to: date = None) -> Dict[str, Any]:
        """
        Generate all slots for a psychologist's availability blocks
        """
        if not date_from:
            date_from = date.today()
        if not date_to:
            date_to = date_from + timedelta(days=90)

        try:
            # Get all availability blocks for the psychologist
            availability_blocks = PsychologistAvailability.objects.filter(
                psychologist=psychologist
            )

            total_slots_created = 0
            results = []

            for block in availability_blocks:
                try:
                    slots = AppointmentSlotService.generate_slots_from_availability_block(
                        block, date_from, date_to
                    )
                    total_slots_created += len(slots)
                    results.append({
                        'availability_block_id': block.availability_id,
                        'slots_created': len(slots),
                        'success': True
                    })
                except SlotGenerationError as e:
                    results.append({
                        'availability_block_id': block.availability_id,
                        'slots_created': 0,
                        'success': False,
                        'error': str(e)
                    })

            logger.info(f"Bulk slot generation for {psychologist.display_name}: {total_slots_created} total slots")
            return {
                'psychologist_id': str(psychologist.user.id),
                'date_range': {'from': date_from, 'to': date_to},
                'total_slots_created': total_slots_created,
                'availability_blocks_processed': len(results),
                'results': results
            }

        except Exception as e:
            logger.error(f"Bulk slot generation failed for {psychologist.display_name}: {str(e)}")
            raise SlotGenerationError(f"Bulk slot generation failed: {str(e)}")

    @staticmethod
    def cleanup_past_slots(days_past: int = 7):
        """
        Clean up appointment slots that are older than specified days
        Only removes unbooked slots
        """
        cutoff_date = date.today() - timedelta(days=days_past)

        deleted_count = AppointmentSlot.objects.filter(
            slot_date__lt=cutoff_date,
            is_booked=False
        ).delete()[0]

        logger.info(f"Cleaned up {deleted_count} past appointment slots")
        return deleted_count
    @staticmethod
    def auto_generate_slots_for_new_availability(availability_block: PsychologistAvailability) -> Dict[str, Any]:
        """
        Automatically generate slots for a new availability block
        Used by signals when new availability is created
        """
        try:
            date_from = date.today()
            date_to = date_from + timedelta(days=settings.AUTO_GENERATION_DAYS_AHEAD)

            slots = AppointmentSlotService.generate_slots_from_availability_block(
                availability_block, date_from, date_to
            )

            result = {
                'success': True,
                'availability_block_id': availability_block.availability_id,
                'slots_created': len(slots),
                'date_range': {'from': date_from, 'to': date_to},
                'psychologist_id': str(availability_block.psychologist.user.id)
            }

            logger.info(
                f"Auto-generated {len(slots)} slots for availability block {availability_block.availability_id}"
            )
            return result

        except Exception as e:
            logger.error(
                f"Failed to auto-generate slots for availability {availability_block.availability_id}: {str(e)}"
            )
            return {
                'success': False,
                'error': str(e),
                'availability_block_id': availability_block.availability_id
            }

    @staticmethod
    def auto_regenerate_slots_for_updated_availability(availability_block: PsychologistAvailability,
                                                     old_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Regenerate slots for updated availability block
        Preserves booked slots, only regenerates unbooked ones
        """
        try:
            date_from = date.today()
            date_to = date_from + timedelta(days=90)

            # Delete only unbooked slots for this availability block
            deleted_slots = availability_block.generated_slots.filter(
                is_booked=False,
                slot_date__gte=date_from,
                slot_date__lte=date_to
            ).delete()[0]

            # Generate new slots
            new_slots = AppointmentSlotService.generate_slots_from_availability_block(
                availability_block, date_from, date_to
            )

            result = {
                'success': True,
                'availability_block_id': availability_block.availability_id,
                'deleted_unbooked_slots': deleted_slots,
                'new_slots_created': len(new_slots),
                'date_range': {'from': date_from, 'to': date_to},
                'psychologist_id': str(availability_block.psychologist.user.id)
            }

            logger.info(
                f"Auto-regenerated slots for availability block {availability_block.availability_id}: "
                f"deleted {deleted_slots} unbooked slots, created {len(new_slots)} new slots"
            )
            return result

        except Exception as e:
            logger.error(
                f"Failed to auto-regenerate slots for availability {availability_block.availability_id}: {str(e)}"
            )
            return {
                'success': False,
                'error': str(e),
                'availability_block_id': availability_block.availability_id
            }

    # @staticmethod
    # def auto_cleanup_slots_for_deleted_availability(availability_block_id: int,
    #                                                psychologist_id: str) -> Dict[str, Any]:
    #     """
    #     Clean up slots when availability block is deleted
    #     Only removes unbooked slots to preserve appointment history
    #     """
    #     try:
    #         from .models import AppointmentSlot

    #         # Delete only unbooked slots for this availability block
    #         deleted_count = AppointmentSlot.objects.filter(
    #             availability_block_id=availability_block_id,
    #             is_booked=False
    #         ).delete()[0]

    #         result = {
    #             'success': True,
    #             'availability_block_id': availability_block_id,
    #             'deleted_unbooked_slots': deleted_count,
    #             'psychologist_id': psychologist_id
    #         }

    #         logger.info(
    #             f"Auto-cleaned up {deleted_count} unbooked slots for deleted availability block {availability_block_id}"
    #         )
    #         return result

    #     except Exception as e:
    #         logger.error(
    #             f"Failed to auto-cleanup slots for deleted availability {availability_block_id}: {str(e)}"
    #         )
    #         return {
    #             'success': False,
    #             'error': str(e),
    #             'availability_block_id': availability_block_id
    #         }

# ============================================================================
# APPOINTMENT BOOKING SERVICE
# ============================================================================

class AppointmentBookingService:
    """
    Service for booking, managing, and cancelling appointments
    """

    @staticmethod
    def book_appointment(parent: Parent, child: Child, psychologist: Psychologist,
                        session_type: str, start_slot_id: int, parent_notes: str = "") -> Appointment:
        """
        Book an appointment for a child with a psychologist

        Args:
            parent: Parent booking the appointment
            child: Child the appointment is for
            psychologist: Psychologist providing the service
            session_type: 'OnlineMeeting' or 'InitialConsultation'
            start_slot_id: ID of the first slot to book
            parent_notes: Optional notes from parent

        Returns:
            Created Appointment instance
        """
        # Validate business rules first
        AppointmentBookingService._validate_booking_request(
            parent, child, psychologist, session_type
        )

        try:
            with transaction.atomic():
                # Get the starting slot
                try:
                    start_slot = AppointmentSlot.objects.select_for_update().get(
                        slot_id=start_slot_id,
                        psychologist=psychologist
                    )
                except AppointmentSlot.DoesNotExist:
                    raise SlotNotAvailableError("Starting slot not found")

                # Determine number of slots needed
                slots_needed = 1 if session_type == 'OnlineMeeting' else 2

                # Find and reserve consecutive slots
                slots_to_book = AppointmentBookingService._find_and_reserve_consecutive_slots(
                    start_slot, slots_needed
                )

                # Create appointment
                appointment = AppointmentBookingService._create_appointment(
                    parent=parent,
                    child=child,
                    psychologist=psychologist,
                    session_type=session_type,
                    slots=slots_to_book,
                    parent_notes=parent_notes
                )

                # TODO: PAYMENT_INTEGRATION_PLACEHOLDER
                # For now, directly mark as scheduled. In future:
                # 1. Create payment intent
                # 2. Return payment URL/token
                # 3. Mark as Payment_Pending
                # 4. Update to Scheduled after payment confirmation
                appointment = AppointmentBookingService._mark_as_scheduled_direct(appointment)

                # TODO: EMAIL_NOTIFICATION_PLACEHOLDER
                # AppointmentNotificationService.send_booking_confirmation(appointment)

                logger.info(f"Appointment booked: {appointment.appointment_id} for {child.display_name}")
                return appointment

        except (SlotNotAvailableError, InsufficientConsecutiveSlotsError, AppointmentBookingError):
            # Re-raise specific booking errors without wrapping them
            raise
        except Exception as e:
            # Only wrap unexpected exceptions
            logger.error(f"Appointment booking failed: {str(e)}")
            raise AppointmentBookingError(f"Booking failed: {str(e)}")

    @staticmethod
    def _validate_booking_request(parent: Parent, child: Child, psychologist: Psychologist, session_type: str):
        """
        Validate appointment booking business rules
        """
        # Validate child belongs to parent
        if child.parent != parent:
            raise AppointmentBookingError("Child must belong to the booking parent")

        # Validate parent is active and verified
        if not parent.user.is_active or not parent.user.is_verified:
            raise AppointmentBookingError("Parent account must be active and verified")

        # Validate psychologist can provide requested service
        if session_type == 'OnlineMeeting' and not psychologist.offers_online_sessions:
            raise AppointmentBookingError("Psychologist does not offer online sessions")

        if session_type == 'InitialConsultation' and not psychologist.offers_initial_consultation:
            raise AppointmentBookingError("Psychologist does not offer initial consultations")

        # Validate psychologist is marketplace visible
        if not psychologist.is_marketplace_visible:
            raise AppointmentBookingError("Psychologist is not available for booking")

    @staticmethod
    def _find_and_reserve_consecutive_slots(start_slot: AppointmentSlot, slots_needed: int) -> List[AppointmentSlot]:
        """
        Find and reserve consecutive slots starting from the given slot
        """
        if not start_slot.is_available_for_booking:
            raise SlotNotAvailableError("Starting slot is not available")

        slots_to_book = []
        current_slot = start_slot

        for i in range(slots_needed):
            if i == 0:
                # First slot is the start_slot
                if not current_slot.is_available_for_booking:
                    raise SlotNotAvailableError(f"Slot {current_slot.slot_id} is not available")
                slots_to_book.append(current_slot)
            else:
                # Find next consecutive slot
                next_start_time = (datetime.combine(date.today(), current_slot.start_time) + timedelta(hours=1)).time()

                try:
                    next_slot = AppointmentSlot.objects.select_for_update().get(
                        psychologist=current_slot.psychologist,
                        slot_date=current_slot.slot_date,
                        start_time=next_start_time
                    )

                    if not next_slot.is_available_for_booking:
                        raise InsufficientConsecutiveSlotsError(f"Not enough consecutive slots available (need {slots_needed})")

                    slots_to_book.append(next_slot)
                    current_slot = next_slot

                except AppointmentSlot.DoesNotExist:
                    raise InsufficientConsecutiveSlotsError(f"Not enough consecutive slots available (need {slots_needed})")

        # Reserve all slots
        for slot in slots_to_book:
            slot.mark_as_booked()

        return slots_to_book

    @staticmethod
    def _create_appointment(parent: Parent, child: Child, psychologist: Psychologist,
                          session_type: str, slots: List[AppointmentSlot], parent_notes: str) -> Appointment:
        """
        Create appointment instance with proper defaults
        """
        # Calculate scheduled times from slots
        scheduled_start_time = slots[0].datetime_start
        scheduled_end_time = slots[-1].datetime_end

        # Set meeting address for in-person appointments
        meeting_address = ""
        if session_type == 'InitialConsultation':
            meeting_address = psychologist.office_address or ""

        # Create appointment
        appointment = Appointment.objects.create(
            child=child,
            psychologist=psychologist,
            parent=parent,
            session_type=session_type,
            appointment_status='Payment_Pending',
            payment_status='Pending',
            scheduled_start_time=scheduled_start_time,
            scheduled_end_time=scheduled_end_time,
            meeting_address=meeting_address,
            parent_notes=parent_notes
        )

        # Link appointment to slots
        appointment.appointment_slots.set(slots)

        # Generate meeting specifics
        if session_type == 'OnlineMeeting':
            AppointmentBookingService._setup_online_meeting(appointment)
        elif session_type == 'InitialConsultation':
            AppointmentBookingService._setup_in_person_meeting(appointment)

        return appointment

    @staticmethod
    def _setup_online_meeting(appointment: Appointment):
        """
        Setup online meeting details
        """
        # TODO: ZOOM_INTEGRATION_PLACEHOLDER
        # Future implementation:
        # 1. Create Zoom meeting via API
        # 2. Store meeting_id and meeting_link
        # 3. Configure meeting settings (waiting room, etc.)

        # For now, generate placeholder meeting details
        meeting_id = f"meeting_{appointment.appointment_id.hex[:10]}"
        meeting_link = f"https://zoom.us/j/{meeting_id}"  # Placeholder

        appointment.meeting_id = meeting_id
        appointment.meeting_link = meeting_link
        appointment.save(update_fields=['meeting_id', 'meeting_link', 'updated_at'])

    @staticmethod
    def _setup_in_person_meeting(appointment: Appointment):
        """
        Setup in-person meeting details (QR code generation handled by model)
        """
        # QR verification code is automatically generated in the model's save method
        # No additional setup needed for MVP
        pass

    @staticmethod
    def _mark_as_scheduled_direct(appointment: Appointment) -> Appointment:
        """
        Directly mark appointment as scheduled (MVP without payment processing)
        """
        appointment.appointment_status = 'Scheduled'
        appointment.payment_status = 'Paid'
        appointment.save(update_fields=['appointment_status', 'payment_status', 'updated_at'])
        return appointment

    # TODO: PAYMENT_INTEGRATION_PLACEHOLDER
    @staticmethod
    def process_payment_and_schedule(appointment: Appointment, payment_token: str) -> Appointment:
        """
        Process payment and mark appointment as scheduled

        PLACEHOLDER for future payment integration:
        1. Validate payment token
        2. Process payment via payment gateway
        3. Handle payment success/failure
        4. Update appointment status accordingly
        5. Send confirmation emails
        """
        # Future implementation will go here
        pass

    @staticmethod
    def get_available_booking_slots(psychologist: Psychologist, session_type: str,
                                  date_from: date = None, date_to: date = None) -> Dict[str, Any]:
        """
        Get available slots for booking, formatted for frontend display
        """
        if not date_from:
            date_from = date.today()
        if not date_to:
            date_to = date_from + timedelta(days=30)

        # Get available slots
        available_slots = AppointmentSlot.get_available_slots(psychologist, date_from, date_to)

        if session_type == 'OnlineMeeting':
            # For 1-hour sessions, all available slots can be booked
            booking_options = [
                {
                    'slot_id': slot.slot_id,
                    'date': slot.slot_date,
                    'start_time': slot.start_time,
                    'end_time': slot.end_time,
                    'session_types': ['OnlineMeeting'],
                    'is_consecutive_block': False
                }
                for slot in available_slots
            ]
        else:
            # For 2-hour sessions, find consecutive slot pairs
            booking_options = []
            processed_slots = set()

            for slot in available_slots:
                if slot.slot_id in processed_slots:
                    continue

                # Try to find consecutive slot
                consecutive_slots = AppointmentSlot.find_consecutive_slots(
                    psychologist, slot.slot_date, slot.start_time, 2
                )

                if len(consecutive_slots) == 2:
                    booking_options.append({
                        'slot_id': slot.slot_id,  # Start slot ID for booking
                        'date': slot.slot_date,
                        'start_time': slot.start_time,
                        'end_time': consecutive_slots[1].end_time,
                        'session_types': ['InitialConsultation'],
                        'is_consecutive_block': True,
                        'consecutive_slot_ids': [s.slot_id for s in consecutive_slots]
                    })
                    # Mark both slots as processed
                    for s in consecutive_slots:
                        processed_slots.add(s.slot_id)

        return {
            'psychologist_id': str(psychologist.user.id),
            'psychologist_name': psychologist.display_name,
            'session_type': session_type,
            'date_from': date_from,
            'date_to': date_to,
            'available_slots': booking_options,
            'total_slots': len(booking_options)
        }


# ============================================================================
# APPOINTMENT MANAGEMENT SERVICE
# ============================================================================

class AppointmentManagementService:
    """
    Service for managing existing appointments (updates, cancellations, completion)
    """

    @staticmethod
    def get_appointment_by_id(appointment_id: str, user: User) -> Appointment:
        """
        Get appointment by ID with access control
        """
        try:
            appointment = Appointment.objects.select_related(
                'child', 'psychologist__user', 'parent__user'
            ).prefetch_related('appointment_slots').get(appointment_id=appointment_id)

            # Check access permissions
            if not AppointmentManagementService._user_can_access_appointment(user, appointment):
                raise AppointmentAccessDeniedError("User does not have access to this appointment")

            return appointment

        except Appointment.DoesNotExist:
            raise AppointmentNotFoundError(f"Appointment {appointment_id} not found")

    @staticmethod
    def _user_can_access_appointment(user: User, appointment: Appointment) -> bool:
        """
        Check if user can access appointment
        """
        # Admins can access all appointments
        if user.is_admin or user.is_staff:
            return True

        # Parents can access their own appointments
        if user.is_parent and hasattr(user, 'parent_profile'):
            return appointment.parent == user.parent_profile

        # Psychologists can access their appointments
        if user.is_psychologist and hasattr(user, 'psychologist_profile'):
            return appointment.psychologist == user.psychologist_profile

        return False

    @staticmethod
    def cancel_appointment(appointment: Appointment, cancelled_by_user: User, reason: str = "") -> Appointment:
        """
        Cancel appointment with proper business logic
        """
        if not appointment.can_be_cancelled:
            raise AppointmentCancellationError("Appointment cannot be cancelled")

        try:
            with transaction.atomic():
                # Release appointment slots
                for slot in appointment.appointment_slots.all():
                    slot.mark_as_available()

                # Update appointment status
                appointment.appointment_status = 'Cancelled'
                appointment.cancellation_reason = reason
                appointment.save(update_fields=['appointment_status', 'cancellation_reason', 'updated_at'])

                # TODO: REFUND_LOGIC_PLACEHOLDER
                refund_info = AppointmentManagementService._calculate_refund_amount(appointment)
                logger.info(f"Appointment {appointment.appointment_id} cancelled. Refund calculation: {refund_info}")

                # TODO: EMAIL_NOTIFICATION_PLACEHOLDER
                # AppointmentNotificationService.send_cancellation_notification(appointment, cancelled_by_user)

                logger.info(f"Appointment {appointment.appointment_id} cancelled by {cancelled_by_user.email}")
                return appointment

        except Exception as e:
            logger.error(f"Failed to cancel appointment {appointment.appointment_id}: {str(e)}")
            raise AppointmentCancellationError(f"Cancellation failed: {str(e)}")

    @staticmethod
    def _calculate_refund_amount(appointment: Appointment) -> Dict[str, Any]:
        """
        Calculate refund amount based on cancellation policy

        PLACEHOLDER for future refund logic:
        - Full refund if cancelled 24h+ before
        - 50% refund if cancelled 2-24h before
        - No refund if cancelled <2h before or no-show
        """
        time_until_appointment = appointment.scheduled_start_time - timezone.now()
        hours_until = time_until_appointment.total_seconds() / 3600

        # TODO: Get actual payment amount from payment records
        original_amount = 150.00  # Placeholder - should come from payment record

        if hours_until >= 24:
            refund_percentage = 100
            refund_reason = "Full refund - cancelled 24+ hours before"
        elif hours_until >= 2:
            refund_percentage = 50
            refund_reason = "Partial refund - cancelled 2-24 hours before"
        else:
            refund_percentage = 0
            refund_reason = "No refund - cancelled less than 2 hours before"

        refund_amount = original_amount * (refund_percentage / 100)

        return {
            'original_amount': original_amount,
            'refund_percentage': refund_percentage,
            'refund_amount': refund_amount,
            'refund_reason': refund_reason,
            'hours_until_appointment': hours_until
        }

    @staticmethod
    def complete_appointment(appointment: Appointment, psychologist_notes: str = "") -> Appointment:
        """
        Mark appointment as completed
        """
        if appointment.appointment_status != 'Scheduled':
            raise AppointmentServiceError("Only scheduled appointments can be marked as completed")

        appointment.appointment_status = 'Completed'
        if psychologist_notes:
            appointment.psychologist_notes = psychologist_notes
        if not appointment.actual_end_time:
            appointment.actual_end_time = timezone.now()

        appointment.save(update_fields=['appointment_status', 'psychologist_notes', 'actual_end_time', 'updated_at'])

        logger.info(f"Appointment {appointment.appointment_id} marked as completed")
        return appointment

    @staticmethod
    def verify_qr_code(qr_code: str) -> Appointment:
        """
        Verify QR code for in-person appointment
        """
        try:
            appointment = Appointment.objects.get(qr_verification_code=qr_code)

            if not appointment.can_be_verified:
                raise QRVerificationError("Appointment cannot be verified at this time")

            appointment.verify_session()

            logger.info(f"QR code verified for appointment {appointment.appointment_id}")
            return appointment

        except Appointment.DoesNotExist:
            raise QRVerificationError("Invalid QR code")

    @staticmethod
    def get_user_appointments(user: User, status_filter: str = None, date_from: date = None,
                            date_to: date = None, is_upcoming: bool = None) -> List[Appointment]:
        """
        Get appointments for a user with filtering
        """
        queryset = Appointment.objects.select_related(
            'child', 'psychologist__user', 'parent__user'
        ).prefetch_related('appointment_slots')

        # Filter by user type
        if user.is_parent and hasattr(user, 'parent_profile'):
            queryset = queryset.filter(parent=user.parent_profile)
        elif user.is_psychologist and hasattr(user, 'psychologist_profile'):
            queryset = queryset.filter(psychologist=user.psychologist_profile)
        elif user.is_admin or user.is_staff:
            # Admins can see all appointments
            pass
        else:
            return []

        # Apply filters
        if status_filter:
            queryset = queryset.filter(appointment_status=status_filter)

        if date_from:
            queryset = queryset.filter(scheduled_start_time__date__gte=date_from)

        if date_to:
            queryset = queryset.filter(scheduled_start_time__date__lte=date_to)

        if is_upcoming is not None:
            now = timezone.now()
            if is_upcoming:
                queryset = queryset.filter(scheduled_start_time__gt=now)
            else:
                queryset = queryset.filter(scheduled_end_time__lt=now)

        return list(queryset.order_by('scheduled_start_time'))


# ============================================================================
# NOTIFICATION SERVICE (PLACEHOLDER)
# ============================================================================

class AppointmentNotificationService:
    """
    Service for sending appointment-related notifications

    PLACEHOLDER for future email notification implementation
    """

    @staticmethod
    def send_booking_confirmation(appointment: Appointment):
        """
        Send booking confirmation email to parent and psychologist

        TODO: Implement using EmailService
        - Parent: appointment details, meeting info, preparation instructions
        - Psychologist: new appointment notification with child/parent info
        """
        pass

    @staticmethod
    def send_cancellation_notification(appointment: Appointment, cancelled_by: User):
        """
        Send cancellation notification

        TODO: Implement cancellation emails
        - Notify other party about cancellation
        - Include refund information if applicable
        """
        pass

    @staticmethod
    def send_appointment_reminders():
        """
        Send appointment reminders (to be called by scheduled task)

        TODO: Implement reminder system
        - 24 hours before appointment
        - 2 hours before appointment
        - Different content for online vs in-person
        """
        pass

    @staticmethod
    def send_qr_verification_confirmation(appointment: Appointment):
        """
        Send confirmation when QR code is scanned

        TODO: Implement QR verification notifications
        """
        pass


# ============================================================================
# APPOINTMENT ANALYTICS SERVICE
# ============================================================================

class AppointmentAnalyticsService:
    """
    Service for appointment analytics and reporting
    """

    @staticmethod
    def get_psychologist_appointment_stats(psychologist: Psychologist, date_from: date = None,
                                         date_to: date = None) -> Dict[str, Any]:
        """
        Get appointment statistics for a psychologist
        """
        if not date_from:
            date_from = date.today() - timedelta(days=30)
        if not date_to:
            date_to = date.today()

        appointments = Appointment.objects.filter(
            psychologist=psychologist,
            scheduled_start_time__date__gte=date_from,
            scheduled_start_time__date__lte=date_to
        )

        stats = {
            'total_appointments': appointments.count(),
            'completed_appointments': appointments.filter(appointment_status='Completed').count(),
            'cancelled_appointments': appointments.filter(appointment_status='Cancelled').count(),
            'no_show_appointments': appointments.filter(appointment_status='No_Show').count(),
            'online_sessions': appointments.filter(session_type='OnlineMeeting').count(),
            'initial_consultations': appointments.filter(session_type='InitialConsultation').count(),
            'upcoming_appointments': appointments.filter(
                appointment_status__in=['Scheduled', 'Payment_Pending'],
                scheduled_start_time__gt=timezone.now()
            ).count()
        }

        # Calculate completion rate
        total_concluded = stats['completed_appointments'] + stats['cancelled_appointments'] + stats['no_show_appointments']
        stats['completion_rate'] = (stats['completed_appointments'] / total_concluded * 100) if total_concluded > 0 else 0

        return stats

    @staticmethod
    def get_platform_appointment_stats(date_from: date = None, date_to: date = None) -> Dict[str, Any]:
        """
        Get platform-wide appointment statistics (admin only)
        """
        if not date_from:
            date_from = date.today() - timedelta(days=30)
        if not date_to:
            date_to = date.today()

        appointments = Appointment.objects.filter(
            scheduled_start_time__date__gte=date_from,
            scheduled_start_time__date__lte=date_to
        )

        return {
            'total_appointments': appointments.count(),
            'by_status': {
                status_code: appointments.filter(appointment_status=status_code).count()
                for status_code, _ in Appointment.APPOINTMENT_STATUS_CHOICES
            },
            'by_session_type': {
                session_type: appointments.filter(session_type=session_type).count()
                for session_type, _ in Appointment.SESSION_TYPE_CHOICES
            },
            'by_payment_status': {
                payment_status: appointments.filter(payment_status=payment_status).count()
                for payment_status, _ in Appointment.PAYMENT_STATUS_CHOICES
            },
            'completion_rate': AppointmentAnalyticsService._calculate_platform_completion_rate(appointments),
            'average_appointments_per_psychologist': AppointmentAnalyticsService._calculate_avg_appointments_per_psychologist(appointments),
            'busiest_time_slots': AppointmentAnalyticsService._get_busiest_time_slots(appointments),
            'date_range': {'from': date_from, 'to': date_to}
        }

    @staticmethod
    def _calculate_platform_completion_rate(appointments):
        """Calculate platform-wide completion rate"""
        total_concluded = appointments.filter(
            appointment_status__in=['Completed', 'Cancelled', 'No_Show']
        ).count()
        completed = appointments.filter(appointment_status='Completed').count()

        return (completed / total_concluded * 100) if total_concluded > 0 else 0

    @staticmethod
    def _calculate_avg_appointments_per_psychologist(appointments):
        """Calculate average appointments per psychologist"""
        psychologist_counts = appointments.values('psychologist').distinct().count()
        total_appointments = appointments.count()

        return (total_appointments / psychologist_counts) if psychologist_counts > 0 else 0

    @staticmethod
    def _get_busiest_time_slots(appointments):
        """Get busiest time slots across the platform"""
        from django.db.models import Count

        # Group by hour of day
        busiest_hours = appointments.extra(
            select={'hour': 'EXTRACT(hour FROM scheduled_start_time)'}
        ).values('hour').annotate(
            count=Count('appointment_id')
        ).order_by('-count')[:5]

        return list(busiest_hours)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

class AppointmentUtilityService:
    """
    Utility service for appointment-related helper functions
    """

    @staticmethod
    def get_appointment_duration_minutes(session_type: str) -> int:
        """Get appointment duration in minutes for a session type"""
        if session_type == 'OnlineMeeting':
            return 60
        elif session_type == 'InitialConsultation':
            return 120
        return 0

    @staticmethod
    def format_appointment_time_display(appointment: Appointment) -> Dict[str, str]:
        """Format appointment times for display"""
        start_time = appointment.scheduled_start_time
        end_time = appointment.scheduled_end_time

        return {
            'date': start_time.strftime('%Y-%m-%d'),
            'day_name': start_time.strftime('%A'),
            'start_time': start_time.strftime('%H:%M'),
            'end_time': end_time.strftime('%H:%M'),
            'duration': f"{appointment.duration_hours} hour{'s' if appointment.duration_hours > 1 else ''}",
            'timezone': str(start_time.tzinfo)
        }

    @staticmethod
    def generate_appointment_summary(appointment: Appointment) -> Dict[str, Any]:
        """Generate comprehensive appointment summary"""
        return {
            'appointment_id': str(appointment.appointment_id),
            'child_name': appointment.child.display_name,
            'child_age': appointment.child.age,
            'psychologist_name': appointment.psychologist.display_name,
            'parent_name': appointment.parent.full_name,
            'session_type': appointment.get_session_type_display(),
            'status': appointment.get_appointment_status_display(),
            'payment_status': appointment.get_payment_status_display(),
            'time_info': AppointmentUtilityService.format_appointment_time_display(appointment),
            'meeting_info': {
                'type': 'online' if appointment.session_type == 'OnlineMeeting' else 'in_person',
                'address': appointment.meeting_address if appointment.session_type == 'InitialConsultation' else None,
                'meeting_link': appointment.meeting_link if appointment.session_type == 'OnlineMeeting' else None,
                'qr_required': appointment.session_type == 'InitialConsultation',
                'qr_verified': bool(appointment.session_verified_at) if appointment.session_type == 'InitialConsultation' else None
            },
            'notes': {
                'parent_notes': appointment.parent_notes,
                'psychologist_notes': appointment.psychologist_notes if appointment.appointment_status == 'Completed' else None
            },
            'created_at': appointment.created_at,
            'updated_at': appointment.updated_at
        }

    @staticmethod
    def validate_appointment_time_constraints(scheduled_start_time: datetime, session_type: str) -> List[str]:
        """
        Validate appointment time constraints and return list of validation errors
        """
        errors = []

        # Check if appointment is in the past
        if scheduled_start_time <= timezone.now():
            errors.append("Appointment cannot be scheduled in the past")

        # Check business hours (example: 8 AM to 6 PM)
        hour = scheduled_start_time.hour
        if hour < 8 or hour > 18:
            errors.append("Appointments can only be scheduled between 8 AM and 6 PM")

        # Check if it's a weekend (optional business rule)
        if scheduled_start_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
            errors.append("Appointments cannot be scheduled on weekends")

        # Check minimum advance booking (example: 24 hours)
        time_until_appointment = scheduled_start_time - timezone.now()
        if time_until_appointment.total_seconds() < 24 * 3600:  # 24 hours
            errors.append("Appointments must be booked at least 24 hours in advance")

        # Check maximum advance booking (example: 90 days)
        if time_until_appointment.days > 90:
            errors.append("Appointments cannot be booked more than 90 days in advance")

        return errors

    @staticmethod
    def get_recommended_booking_times(psychologist: Psychologist, session_type: str,
                                    preferred_date: date = None) -> List[Dict[str, Any]]:
        """
        Get recommended booking times for a psychologist and session type
        """
        if not preferred_date:
            preferred_date = date.today() + timedelta(days=1)  # Tomorrow as default

        # Get available slots for the preferred date
        available_slots = AppointmentSlot.get_available_slots(
            psychologist, preferred_date, preferred_date
        )

        recommendations = []

        # Prioritize morning slots (9 AM - 12 PM)
        morning_slots = [slot for slot in available_slots if 9 <= slot.start_time.hour < 12]

        # Afternoon slots (1 PM - 5 PM)
        afternoon_slots = [slot for slot in available_slots if 13 <= slot.start_time.hour < 17]

        # Evening slots (5 PM - 7 PM)
        evening_slots = [slot for slot in available_slots if 17 <= slot.start_time.hour < 19]

        for time_period, slots in [('morning', morning_slots), ('afternoon', afternoon_slots), ('evening', evening_slots)]:
            if slots:
                if session_type == 'OnlineMeeting':
                    recommendations.extend([
                        {
                            'slot_id': slot.slot_id,
                            'date': slot.slot_date,
                            'start_time': slot.start_time,
                            'end_time': slot.end_time,
                            'time_period': time_period,
                            'recommendation_reason': f"Available {time_period} slot"
                        }
                        for slot in slots[:3]  # Limit to 3 recommendations per period
                    ])
                else:  # InitialConsultation - need consecutive slots
                    for slot in slots:
                        consecutive_slots = AppointmentSlot.find_consecutive_slots(
                            psychologist, slot.slot_date, slot.start_time, 2
                        )
                        if len(consecutive_slots) == 2:
                            recommendations.append({
                                'slot_id': slot.slot_id,
                                'date': slot.slot_date,
                                'start_time': slot.start_time,
                                'end_time': consecutive_slots[1].end_time,
                                'time_period': time_period,
                                'recommendation_reason': f"Available {time_period} 2-hour block"
                            })
                            if len(recommendations) >= 3:  # Limit total recommendations
                                break

        return recommendations[:6]  # Return top 6 recommendations