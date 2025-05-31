# appointments/tests/test_services.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
from datetime import date, datetime, timedelta, time
from decimal import Decimal
import uuid

from users.models import User
from parents.models import Parent
from children.models import Child
from psychologists.models import Psychologist, PsychologistAvailability
from appointments.models import Appointment, AppointmentSlot
from appointments.services import (
    AppointmentSlotService,
    AppointmentBookingService,
    AppointmentManagementService,
    AppointmentAnalyticsService,
    AppointmentUtilityService,
    # Exceptions
    AppointmentServiceError,
    AppointmentBookingError,
    SlotNotAvailableError,
    InsufficientConsecutiveSlotsError,
    AppointmentNotFoundError,
    AppointmentAccessDeniedError,
    AppointmentCancellationError,
    QRVerificationError,
    SlotGenerationError
)


class AppointmentSlotServiceTest(TestCase):
    """Test AppointmentSlotService functionality"""

    def setUp(self):
        # Create test users
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )

        # Create psychologist profile
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Dr. Jane',
            last_name='Smith',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        # Create availability block
        self.availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time=time(9, 0),
            end_time=time(12, 0),
            is_recurring=True
        )

    def test_generate_slots_from_recurring_availability(self):
        """Test slot generation from recurring availability block"""
        date_from = date.today()
        date_to = date_from + timedelta(days=7)
        slots = AppointmentSlotService.generate_slots_from_availability_block(
            self.availability_block, date_from, date_to
        )

        # Should generate slots for Monday within the date range
        self.assertGreater(len(slots), 0)

        # Sort slots by start_time to check them in order
        slots.sort(key=lambda s: (s.slot_date, s.start_time))

        # Check slot properties
        for slot in slots:
            self.assertEqual(slot.psychologist, self.psychologist)
            self.assertEqual(slot.availability_block, self.availability_block)
            self.assertFalse(slot.is_booked)

        # Check that first slot starts at 9 AM
        first_slot = slots[0]
        self.assertEqual(first_slot.start_time.hour, 9)

        # Check that we have the expected number of slots (9-10, 10-11, 11-12 = 3 slots)
        monday_slots = [s for s in slots if s.slot_date.weekday() == 0]  # Monday = 0
        self.assertEqual(len(monday_slots), 3)

        # Verify the time progression
        expected_hours = [9, 10, 11]
        for i, slot in enumerate(monday_slots):
            self.assertEqual(slot.start_time.hour, expected_hours[i])

    def test_generate_slots_for_specific_date_availability(self):
        """Test slot generation from specific date availability"""
        specific_date = date.today() + timedelta(days=3)
        specific_availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=0,
            start_time=time(14, 0),
            end_time=time(16, 0),
            is_recurring=False,
            specific_date=specific_date
        )

        slots = AppointmentSlotService.generate_slots_from_availability_block(
            specific_availability, specific_date, specific_date
        )

        # Should generate 2 slots (14:00-15:00, 15:00-16:00)
        self.assertEqual(len(slots), 2)
        self.assertEqual(slots[0].slot_date, specific_date)
        self.assertEqual(slots[0].start_time, time(14, 0))
        self.assertEqual(slots[1].start_time, time(15, 0))

    def test_bulk_generate_slots_for_psychologist(self):
        """Test bulk slot generation for psychologist"""
        date_from = date.today()
        date_to = date_from + timedelta(days=14)

        result = AppointmentSlotService.bulk_generate_slots_for_psychologist(
            self.psychologist, date_from, date_to
        )

        self.assertIn('total_slots_created', result)
        self.assertIn('availability_blocks_processed', result)
        self.assertGreater(result['total_slots_created'], 0)
        self.assertEqual(result['availability_blocks_processed'], 1)

    def test_cleanup_past_slots(self):
        """Test cleanup of past unbooked slots"""
        # Create slots first, then manipulate their dates to bypass validation
        current_date = date.today()

        # Get the day of week for current date
        current_day_of_week = (current_date.weekday() + 1) % 7

        # Create an availability block that matches today's day of week
        availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            is_recurring=True,
            day_of_week=current_day_of_week,
            start_time=time(9, 0),
            end_time=time(17, 0)
        )

        # Create slots with current date first (to pass validation)
        past_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=availability_block,
            slot_date=current_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_booked=False
        )

        booked_past_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=availability_block,
            slot_date=current_date,
            start_time=time(10, 0),
            end_time=time(11, 0),
            is_booked=True
        )

        recent_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=availability_block,
            slot_date=current_date,
            start_time=time(11, 0),
            end_time=time(12, 0),
            is_booked=False
        )

        # Now update the dates directly in the database to bypass validation
        past_date = date.today() - timedelta(days=10)
        recent_date = date.today() - timedelta(days=3)

        # Update dates using raw SQL or update() to bypass model validation
        AppointmentSlot.objects.filter(slot_id=past_slot.slot_id).update(slot_date=past_date)
        AppointmentSlot.objects.filter(slot_id=booked_past_slot.slot_id).update(slot_date=past_date)
        AppointmentSlot.objects.filter(slot_id=recent_slot.slot_id).update(slot_date=recent_date)

        # Refresh instances from database
        past_slot.refresh_from_db()
        booked_past_slot.refresh_from_db()
        recent_slot.refresh_from_db()

        # Verify our setup is correct
        self.assertEqual(past_slot.slot_date, past_date)
        self.assertEqual(booked_past_slot.slot_date, past_date)
        self.assertEqual(recent_slot.slot_date, recent_date)

        # Test cleanup with days_past=7 (should only delete slots older than 7 days)
        deleted_count = AppointmentSlotService.cleanup_past_slots(days_past=7)

        # Verify results
        self.assertEqual(deleted_count, 1)  # Only the 10-day-old unbooked slot should be deleted
        self.assertFalse(AppointmentSlot.objects.filter(slot_id=past_slot.slot_id).exists())
        self.assertTrue(AppointmentSlot.objects.filter(slot_id=booked_past_slot.slot_id).exists())
        self.assertTrue(AppointmentSlot.objects.filter(slot_id=recent_slot.slot_id).exists())
    def test_prevent_duplicate_slot_generation(self):
        """Test that duplicate slots are not generated"""
        date_from = date.today()
        date_to = date_from + timedelta(days=1)

        # Generate slots first time
        slots1 = AppointmentSlotService.generate_slots_from_availability_block(
            self.availability_block, date_from, date_to
        )

        # Generate slots second time
        slots2 = AppointmentSlotService.generate_slots_from_availability_block(
            self.availability_block, date_from, date_to
        )

        # Second generation should not create new slots
        self.assertEqual(len(slots2), 0)

    def test_slot_generation_error_handling(self):
        """Test error handling in slot generation"""
        # Test with invalid availability block
        invalid_availability = PsychologistAvailability(
            psychologist=self.psychologist,
            day_of_week=1,
            start_time=time(12, 0),
            end_time=time(9, 0),  # Invalid: end before start
            is_recurring=True
        )

        with self.assertRaises(SlotGenerationError):
            AppointmentSlotService.generate_slots_from_availability_block(invalid_availability)


class AppointmentBookingServiceTest(TestCase):
    """Test AppointmentBookingService functionality"""

    def setUp(self):
        # Create parent user and profile
        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        self.parent = Parent.objects.get(user=self.parent_user)

        # Create child
        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            date_of_birth=date.today() - timedelta(days=2555)  # ~7 years old
        )

        # Create psychologist
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Dr. Jane',
            last_name='Smith',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        # Create availability and slots
        self.availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time=time(9, 0),
            end_time=time(12, 0),
            is_recurring=True
        )

        # Calculate the next Monday
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7  # Monday is 0 in weekday()
        if days_until_monday == 0:  # Today is Monday
            days_until_monday = 7  # Get next Monday
        next_monday = today + timedelta(days=days_until_monday)

        # Create appointment slots for next Monday
        self.slot1 = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=next_monday,
            start_time=time(9, 0),
            end_time=time(10, 0)
        )
        self.slot2 = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=next_monday,
            start_time=time(10, 0),
            end_time=time(11, 0)
        )

    def test_book_online_appointment_success(self):
        """Test successful online appointment booking"""
        appointment = AppointmentBookingService.book_appointment(
            parent=self.parent,
            child=self.child,
            psychologist=self.psychologist,
            session_type='OnlineMeeting',
            start_slot_id=self.slot1.slot_id,
            parent_notes='Looking forward to the session'
        )

        self.assertIsInstance(appointment, Appointment)
        self.assertEqual(appointment.child, self.child)
        self.assertEqual(appointment.psychologist, self.psychologist)
        self.assertEqual(appointment.parent, self.parent)
        self.assertEqual(appointment.session_type, 'OnlineMeeting')
        self.assertEqual(appointment.appointment_status, 'Scheduled')  # MVP: directly scheduled
        self.assertEqual(appointment.parent_notes, 'Looking forward to the session')

        # Check slot is booked
        self.slot1.refresh_from_db()
        self.assertTrue(self.slot1.is_booked)

        # Check meeting link is generated
        self.assertIsNotNone(appointment.meeting_link)

    def test_book_initial_consultation_success(self):
        """Test successful initial consultation booking (2 consecutive slots)"""
        appointment = AppointmentBookingService.book_appointment(
            parent=self.parent,
            child=self.child,
            psychologist=self.psychologist,
            session_type='InitialConsultation',
            start_slot_id=self.slot1.slot_id
        )

        self.assertEqual(appointment.session_type, 'InitialConsultation')
        self.assertEqual(appointment.duration_hours, 2)

        # Check both slots are booked
        self.slot1.refresh_from_db()
        self.slot2.refresh_from_db()
        self.assertTrue(self.slot1.is_booked)
        self.assertTrue(self.slot2.is_booked)

        # Check QR code is generated
        self.assertIsNotNone(appointment.qr_verification_code)
        self.assertEqual(appointment.meeting_address, self.psychologist.office_address)

    def test_booking_validation_child_not_belong_to_parent(self):
        """Test booking validation when child doesn't belong to parent"""
        # Create another parent and child
        other_parent_user = User.objects.create_user(
            email='other@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        other_parent = Parent.objects.get(user=other_parent_user)
        other_child = Child.objects.create(
            parent=other_parent,
            first_name='Bob',
            date_of_birth=date.today() - timedelta(days=2555)
        )

        with self.assertRaises(AppointmentBookingError) as cm:
            AppointmentBookingService.book_appointment(
                parent=self.parent,  # Wrong parent
                child=other_child,
                psychologist=self.psychologist,
                session_type='OnlineMeeting',
                start_slot_id=self.slot1.slot_id
            )

        self.assertIn("Child must belong to the booking parent", str(cm.exception))

    def test_booking_validation_psychologist_service_not_offered(self):
        """Test booking validation when psychologist doesn't offer requested service"""
        # Create psychologist who only offers online sessions
        online_only_psychologist = Psychologist.objects.create(
            user=User.objects.create_user(
                email='online_only@test.com',
                password='testpass123',
                user_type='Psychologist',
                is_verified=True
            ),
            first_name='Dr. Online',
            last_name='Only',
            license_number='PSY789012',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=False  # Doesn't offer consultations
        )

        with self.assertRaises(AppointmentBookingError) as cm:
            AppointmentBookingService.book_appointment(
                parent=self.parent,
                child=self.child,
                psychologist=online_only_psychologist,
                session_type='InitialConsultation',
                start_slot_id=self.slot1.slot_id
            )

        self.assertIn("does not offer initial consultations", str(cm.exception))

    def test_booking_insufficient_consecutive_slots(self):
        """Test booking failure when insufficient consecutive slots for 2-hour appointment"""
        # Book the second slot to make consecutive booking impossible
        self.slot2.mark_as_booked()

        with self.assertRaises(InsufficientConsecutiveSlotsError):
            AppointmentBookingService.book_appointment(
                parent=self.parent,
                child=self.child,
                psychologist=self.psychologist,
                session_type='InitialConsultation',
                start_slot_id=self.slot1.slot_id
            )

    def test_booking_slot_not_available(self):
        """Test booking failure when slot is not available"""
        # Mark slot as booked
        self.slot1.mark_as_booked()

        with self.assertRaises(SlotNotAvailableError):
            AppointmentBookingService.book_appointment(
                parent=self.parent,
                child=self.child,
                psychologist=self.psychologist,
                session_type='OnlineMeeting',
                start_slot_id=self.slot1.slot_id
            )

    def test_get_available_booking_slots_online(self):
        """Test getting available slots for online sessions"""
        date_from = date.today()
        date_to = date_from + timedelta(days=7)

        result = AppointmentBookingService.get_available_booking_slots(
            self.psychologist, 'OnlineMeeting', date_from, date_to
        )

        self.assertIn('available_slots', result)
        self.assertIn('total_slots', result)
        self.assertEqual(result['session_type'], 'OnlineMeeting')
        self.assertGreater(len(result['available_slots']), 0)

        # Check slot format
        slot = result['available_slots'][0]
        self.assertIn('slot_id', slot)
        self.assertIn('date', slot)
        self.assertIn('start_time', slot)
        self.assertIn('session_types', slot)
        self.assertIn('OnlineMeeting', slot['session_types'])

    def test_get_available_booking_slots_consultation(self):
        """Test getting available slots for initial consultations (consecutive pairs)"""
        date_from = date.today()
        date_to = date_from + timedelta(days=7)

        result = AppointmentBookingService.get_available_booking_slots(
            self.psychologist, 'InitialConsultation', date_from, date_to
        )

        self.assertEqual(result['session_type'], 'InitialConsultation')

        if result['available_slots']:  # If there are consecutive slots available
            slot = result['available_slots'][0]
            self.assertIn('InitialConsultation', slot['session_types'])
            self.assertTrue(slot['is_consecutive_block'])
            self.assertIn('consecutive_slot_ids', slot)


class AppointmentManagementServiceTest(TestCase):
    """Test AppointmentManagementService functionality"""

    def setUp(self):
        # Create test data similar to booking test
        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        self.parent = Parent.objects.get(user=self.parent_user)
        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            date_of_birth=date.today() - timedelta(days=2555)
        )
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Dr. Jane',
            last_name='Smith',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St'
        )

        # Find next Monday for the appointment
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7  # 0 = Monday, 6 = Sunday
        if days_until_monday == 0 and today.weekday() == 0:
            # If today is Monday, use today
            next_monday = today
        else:
            # Otherwise find next Monday
            next_monday = today + timedelta(days=days_until_monday if days_until_monday > 0 else 7)

        # Create availability block for Monday
        self.availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=0,  # Monday (0=Monday in your system based on the service code)
            start_time=time(9, 0),
            end_time=time(12, 0),
            is_recurring=True
        )

        # Create appointment for next Monday
        appointment_start = timezone.make_aware(datetime.combine(next_monday, time(10, 0)))
        self.appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='OnlineMeeting',
            appointment_status='Scheduled',
            scheduled_start_time=appointment_start,
            scheduled_end_time=appointment_start + timedelta(hours=1)
        )


    def test_get_appointment_by_id_success(self):
        """Test successful appointment retrieval"""
        appointment = AppointmentManagementService.get_appointment_by_id(
            str(self.appointment.appointment_id), self.parent_user
        )

        self.assertEqual(appointment, self.appointment)

    def test_get_appointment_by_id_access_denied(self):
        """Test appointment access denied for unauthorized user"""
        unauthorized_user = User.objects.create_user(
            email='unauthorized@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )

        with self.assertRaises(AppointmentAccessDeniedError):
            AppointmentManagementService.get_appointment_by_id(
                str(self.appointment.appointment_id), unauthorized_user
            )

    def test_get_appointment_by_id_not_found(self):
        """Test appointment not found error"""
        fake_uuid = str(uuid.uuid4())

        with self.assertRaises(AppointmentNotFoundError):
            AppointmentManagementService.get_appointment_by_id(fake_uuid, self.parent_user)

    def test_cancel_appointment_success(self):
        """Test successful appointment cancellation"""

        # Use a specific date and create availability block to match
        # Let's use today + 7 days to ensure it's in the future
        target_date = date.today() + timedelta(days=7)
        target_weekday = target_date.weekday()  # Python weekday (0=Monday)

        # Convert to your system's day_of_week format (0=Sunday)
        system_day_of_week = (target_weekday + 1) % 7

        # Create availability block for the target day
        availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=system_day_of_week,
            start_time=time(9, 0),
            end_time=time(12, 0),
            is_recurring=True
        )

        # Create appointment for the target date
        appointment_start = timezone.make_aware(datetime.combine(target_date, time(10, 0)))
        appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='OnlineMeeting',
            appointment_status='Scheduled',
            scheduled_start_time=appointment_start,
            scheduled_end_time=appointment_start + timedelta(hours=1)
        )

        # Create appointment slot - this should now pass validation
        slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=availability_block,
            slot_date=target_date,
            start_time=time(10, 0),
            end_time=time(11, 0),
            is_booked=True
        )
        appointment.appointment_slots.add(slot)

        # Test the cancellation
        cancelled_appointment = AppointmentManagementService.cancel_appointment(
            appointment, self.parent_user, "Change of plans"
        )

        self.assertEqual(cancelled_appointment.appointment_status, 'Cancelled')
        self.assertEqual(cancelled_appointment.cancellation_reason, "Change of plans")

        # Check slot is released
        slot.refresh_from_db()
        self.assertFalse(slot.is_booked)

    def test_cancel_appointment_not_cancellable(self):
        """Test cancellation failure when appointment cannot be cancelled"""
        # Mark appointment as completed
        self.appointment.appointment_status = 'Completed'
        self.appointment.save()

        with self.assertRaises(AppointmentCancellationError):
            AppointmentManagementService.cancel_appointment(
                self.appointment, self.parent_user, "Too late"
            )

    def test_complete_appointment_success(self):
        """Test successful appointment completion"""
        completed_appointment = AppointmentManagementService.complete_appointment(
            self.appointment, "Great session with good progress"
        )

        self.assertEqual(completed_appointment.appointment_status, 'Completed')
        self.assertEqual(completed_appointment.psychologist_notes, "Great session with good progress")
        self.assertIsNotNone(completed_appointment.actual_end_time)

    def test_complete_appointment_invalid_status(self):
        """Test completion failure for invalid appointment status"""
        self.appointment.appointment_status = 'Cancelled'
        self.appointment.save()

        with self.assertRaises(AppointmentServiceError):
            AppointmentManagementService.complete_appointment(self.appointment)

    def test_verify_qr_code_success(self):
        """Test successful QR code verification"""
        start_time = timezone.now() + timedelta(minutes=10)
        end_time = start_time + timedelta(hours=2)

        # Create in-person appointment with QR code
        qr_appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='InitialConsultation',
            appointment_status='Scheduled',
            scheduled_start_time=start_time,
            scheduled_end_time=end_time,
            qr_verification_code='TEST123456'
        )

        verified_appointment = AppointmentManagementService.verify_qr_code('TEST123456')

        self.assertEqual(verified_appointment, qr_appointment)
        self.assertIsNotNone(verified_appointment.session_verified_at)

    def test_verify_qr_code_invalid(self):
        """Test QR code verification with invalid code"""
        with self.assertRaises(QRVerificationError):
            AppointmentManagementService.verify_qr_code('INVALID123')

    def test_get_user_appointments_parent(self):
        """Test getting appointments for parent user"""
        appointments = AppointmentManagementService.get_user_appointments(self.parent_user)

        self.assertEqual(len(appointments), 1)
        self.assertEqual(appointments[0], self.appointment)

    def test_get_user_appointments_psychologist(self):
        """Test getting appointments for psychologist user"""
        appointments = AppointmentManagementService.get_user_appointments(self.psychologist_user)

        self.assertEqual(len(appointments), 1)
        self.assertEqual(appointments[0], self.appointment)

    def test_get_user_appointments_with_filters(self):
        """Test getting appointments with status filter"""
        appointments = AppointmentManagementService.get_user_appointments(
            self.parent_user, status_filter='Scheduled'
        )

        self.assertEqual(len(appointments), 1)

        # Test with different status
        appointments = AppointmentManagementService.get_user_appointments(
            self.parent_user, status_filter='Completed'
        )

        self.assertEqual(len(appointments), 0)


class AppointmentAnalyticsServiceTest(TestCase):
    """Test AppointmentAnalyticsService functionality"""

    def setUp(self):
        # Create minimal test data
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Dr. Jane',
            last_name='Smith',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )
        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        self.parent = Parent.objects.get(user=self.parent_user)

        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            date_of_birth=date.today() - timedelta(days=2555)
        )
        # Create some test appointments with different statuses
        base_time = timezone.now() - timedelta(days=5)

        Appointment.objects.create(
            appointment_id=uuid.uuid4(),
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='OnlineMeeting',
            appointment_status='Completed',
            scheduled_start_time=base_time,
            scheduled_end_time=base_time + timedelta(hours=1)
        )

        Appointment.objects.create(
            appointment_id=uuid.uuid4(),
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='InitialConsultation',
            appointment_status='Cancelled',
            scheduled_start_time=base_time + timedelta(days=1),
            scheduled_end_time=base_time + timedelta(days=1, hours=2)
        )

    def test_get_psychologist_appointment_stats(self):
        """Test psychologist appointment statistics"""
        stats = AppointmentAnalyticsService.get_psychologist_appointment_stats(
            self.psychologist
        )

        self.assertIn('total_appointments', stats)
        self.assertIn('completed_appointments', stats)
        self.assertIn('cancelled_appointments', stats)
        self.assertIn('online_sessions', stats)
        self.assertIn('initial_consultations', stats)
        self.assertIn('completion_rate', stats)

        self.assertEqual(stats['total_appointments'], 2)
        self.assertEqual(stats['completed_appointments'], 1)
        self.assertEqual(stats['cancelled_appointments'], 1)

    def test_get_platform_appointment_stats(self):
        """Test platform-wide appointment statistics"""
        stats = AppointmentAnalyticsService.get_platform_appointment_stats()

        self.assertIn('total_appointments', stats)
        self.assertIn('by_status', stats)
        self.assertIn('by_session_type', stats)
        self.assertIn('completion_rate', stats)
        self.assertIn('date_range', stats)

        self.assertEqual(stats['total_appointments'], 2)
        self.assertIsInstance(stats['by_status'], dict)
        self.assertIsInstance(stats['by_session_type'], dict)


class AppointmentUtilityServiceTest(TestCase):
    """Test AppointmentUtilityService functionality"""

    def setUp(self):
        # Create minimal appointment for utility tests
        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        self.parent = Parent.objects.get(user=self.parent_user)
        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            date_of_birth=date.today() - timedelta(days=2555)
        )

        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Jane',
            last_name='Smith',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )
        start_time = timezone.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        self.appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='OnlineMeeting',
            appointment_status='Scheduled',
            scheduled_start_time=start_time,
            scheduled_end_time=end_time,
            parent_notes='Test notes',
            meeting_link='https://zoom.us/test'
        )

    def test_get_appointment_duration_minutes(self):
        """Test appointment duration calculation"""
        online_duration = AppointmentUtilityService.get_appointment_duration_minutes('OnlineMeeting')
        consultation_duration = AppointmentUtilityService.get_appointment_duration_minutes('InitialConsultation')
        invalid_duration = AppointmentUtilityService.get_appointment_duration_minutes('Invalid')

        self.assertEqual(online_duration, 60)
        self.assertEqual(consultation_duration, 120)
        self.assertEqual(invalid_duration, 0)

    def test_format_appointment_time_display(self):
        """Test appointment time formatting"""
        time_display = AppointmentUtilityService.format_appointment_time_display(self.appointment)

        self.assertIn('date', time_display)
        self.assertIn('day_name', time_display)
        self.assertIn('start_time', time_display)
        self.assertIn('end_time', time_display)
        self.assertEqual(time_display['date'], self.appointment.scheduled_start_time.date().isoformat())
        self.assertEqual(time_display['day_name'], self.appointment.scheduled_start_time.strftime('%A'))
        self.assertEqual(time_display['start_time'], self.appointment.scheduled_start_time.strftime('%H:%M'))
        self.assertEqual(time_display['end_time'], self.appointment.scheduled_end_time.strftime('%H:%M'))
