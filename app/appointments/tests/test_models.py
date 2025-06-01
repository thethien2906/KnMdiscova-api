# appointments/tests/test_models.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import IntegrityError
from datetime import date, time, datetime, timedelta
from decimal import Decimal
import uuid

from users.models import User
from parents.models import Parent
from psychologists.models import Psychologist, PsychologistAvailability
from children.models import Child
from appointments.models import AppointmentSlot, Appointment


class AppointmentSlotModelTest(TestCase):
    """Test cases for AppointmentSlot model"""

    def setUp(self):
        """Set up test data"""
        # Create user and psychologist
        self.user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist'
        )
        self.user.is_verified = True
        self.user.save()

        self.psychologist = Psychologist.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Test St, Test City'
        )

        # Create availability block
        self.availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time=time(9, 0),
            end_time=time(12, 0),
            is_recurring=True
        )

        # Future date (next Monday)
        today = timezone.now().date()
        days_ahead = 7 - today.weekday()  # Days until next Monday
        if days_ahead <= 0:
            days_ahead += 7  # Ensure it's next week
        self.future_date = today + timedelta(days=days_ahead)

    def test_appointment_slot_creation(self):
        """Test basic appointment slot creation"""
        slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.future_date,
            start_time=time(9, 0)
        )

        self.assertEqual(slot.psychologist, self.psychologist)
        self.assertEqual(slot.availability_block, self.availability_block)
        self.assertEqual(slot.slot_date, self.future_date)
        self.assertEqual(slot.start_time, time(9, 0))
        self.assertEqual(slot.end_time, time(10, 0))  # Auto-generated
        self.assertFalse(slot.is_booked)

    def test_appointment_slot_auto_end_time(self):
        """Test automatic end_time generation"""
        slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.future_date,
            start_time=time(14, 30)  # 2:30 PM
        )

        self.assertEqual(slot.end_time, time(15, 30))  # 3:30 PM

    def test_appointment_slot_string_representation(self):
        """Test string representation"""
        slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.future_date,
            start_time=time(9, 0)
        )

        expected_str = f"Dr. John Doe - {self.future_date} 09:00"
        self.assertEqual(str(slot), expected_str)

    def test_appointment_slot_datetime_properties(self):
        """Test datetime properties"""
        slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.future_date,
            start_time=time(9, 0)
        )

        expected_start = timezone.make_aware(datetime.combine(self.future_date, time(9, 0)))
        expected_end = timezone.make_aware(datetime.combine(self.future_date, time(10, 0)))


        self.assertEqual(slot.datetime_start, expected_start)
        self.assertEqual(slot.datetime_end, expected_end)

    def test_appointment_slot_availability_check(self):
        """Test availability checking"""
        # Future slot
        future_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.future_date,
            start_time=time(9, 0)
        )

        self.assertTrue(future_slot.is_available_for_booking)

        # Mark as booked
        future_slot.mark_as_booked()
        self.assertFalse(future_slot.is_available_for_booking)

    def test_appointment_slot_booking_methods(self):
        """Test booking and unbooking methods"""
        slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.future_date,
            start_time=time(9, 0)
        )

        # Test booking
        self.assertFalse(slot.is_booked)
        slot.mark_as_booked()
        slot.refresh_from_db()
        self.assertTrue(slot.is_booked)

        # Test double booking should raise error
        with self.assertRaises(ValidationError):
            slot.mark_as_booked()

        # Test unbooking
        slot.mark_as_available()
        slot.refresh_from_db()
        self.assertFalse(slot.is_booked)

        # Test double unbooking should raise error
        with self.assertRaises(ValidationError):
            slot.mark_as_available()


    def test_appointment_slot_unique_constraint(self):
        """Test unique constraint on psychologist, slot_date, start_time"""
        AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.future_date,
            start_time=time(9, 0)
        )

        # Attempt to create duplicate slot
        with self.assertRaises(ValidationError) as context:
            AppointmentSlot.objects.create(
                psychologist=self.psychologist,
                availability_block=self.availability_block,
                slot_date=self.future_date,
                start_time=time(9, 0)
            )

        self.assertIn(
            "Appointment Slot with this Psychologist, Slot date and Start time already exists.",
            str(context.exception)
        )


    def test_get_available_slots_class_method(self):
        """Test get_available_slots class method"""
        # Create multiple slots
        slot1 = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.future_date,
            start_time=time(9, 0)
        )

        slot2 = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.future_date,
            start_time=time(10, 0)
        )

        # Book one slot
        slot1.mark_as_booked()

        # Get available slots
        available_slots = AppointmentSlot.get_available_slots(self.psychologist)
        self.assertEqual(available_slots.count(), 1)
        self.assertEqual(available_slots.first(), slot2)

    def test_find_consecutive_slots_class_method(self):
        """Test find_consecutive_slots class method"""
        # Create consecutive slots
        slot1 = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.future_date,
            start_time=time(9, 0)
        )

        slot2 = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.future_date,
            start_time=time(10, 0)
        )

        # Test finding 2 consecutive slots
        consecutive_slots = AppointmentSlot.find_consecutive_slots(
            self.psychologist, self.future_date, time(9, 0), 2
        )
        self.assertEqual(len(consecutive_slots), 2)
        self.assertEqual(consecutive_slots[0], slot1)
        self.assertEqual(consecutive_slots[1], slot2)

        # Book one slot and test again
        slot1.mark_as_booked()
        consecutive_slots = AppointmentSlot.find_consecutive_slots(
            self.psychologist, self.future_date, time(9, 0), 2
        )
        self.assertEqual(len(consecutive_slots), 0)


class AppointmentModelTest(TestCase):
    """Test cases for Appointment model"""

    def setUp(self):
        """Set up test data"""
        # Create psychologist
        self.psych_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist'
        )
        self.psych_user.is_verified = True
        self.psych_user.save()

        self.psychologist = Psychologist.objects.create(
            user=self.psych_user,
            first_name='John',
            last_name='Doe',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Test St, Test City'
        )

        # Create parent
        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent'
        )
        self.parent_user.is_verified = True
        self.parent_user.save()

        self.parent = Parent.objects.get(user=self.parent_user)
        self.parent.first_name = 'Jane'
        self.parent.last_name = 'Smith'
        self.parent.save()

        # Create child
        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Tommy',
            date_of_birth=date.today() - timedelta(days=8*365)  # 8 years old
        )

        # Create availability and slots
        self.availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time=time(9, 0),
            end_time=time(12, 0),
            is_recurring=True
        )

        # Future date (next Monday)
        today = timezone.now().date()
        days_ahead = 7 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7  # Ensure it's next week
        self.future_date = today + timedelta(days=days_ahead)

        self.slot1 = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.future_date,
            start_time=time(9, 0)
        )

        self.slot2 = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.future_date,
            start_time=time(10, 0)
        )

        # Future datetime for appointment
        self.future_datetime = timezone.make_aware(
            datetime.combine(self.future_date, time(9, 0))
        )

    def test_appointment_creation_online_meeting(self):
        """Test creating online meeting appointment"""
        appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='OnlineMeeting',
            scheduled_start_time=self.future_datetime,
            scheduled_end_time=self.future_datetime + timedelta(hours=1),
            meeting_link='https://meet.example.com/123'
        )

        # Add appointment slot
        appointment.appointment_slots.add(self.slot1)

        self.assertEqual(appointment.child, self.child)
        self.assertEqual(appointment.psychologist, self.psychologist)
        self.assertEqual(appointment.parent, self.parent)
        self.assertEqual(appointment.session_type, 'OnlineMeeting')
        self.assertEqual(appointment.appointment_status, 'Payment_Pending')
        self.assertEqual(appointment.payment_status, 'Pending')
        self.assertEqual(appointment.duration_hours, 1)

    def test_appointment_creation_initial_consultation(self):
        """Test creating initial consultation appointment"""
        appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='InitialConsultation',
            scheduled_start_time=self.future_datetime,
            scheduled_end_time=self.future_datetime + timedelta(hours=2),
            meeting_address=self.psychologist.office_address
        )

        # Add two consecutive slots
        appointment.appointment_slots.add(self.slot1, self.slot2)

        self.assertEqual(appointment.session_type, 'InitialConsultation')
        self.assertEqual(appointment.duration_hours, 2)
        self.assertEqual(appointment.meeting_address, self.psychologist.office_address)
        self.assertIsNotNone(appointment.qr_verification_code)  # Auto-generated

    def test_appointment_string_representation(self):
        """Test string representation"""
        appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='OnlineMeeting',
            scheduled_start_time=self.future_datetime,
            scheduled_end_time=self.future_datetime + timedelta(hours=1)
        )

        expected_str = f"Tommy - Dr. John Doe (OnlineMeeting) - {self.future_datetime.strftime('%Y-%m-%d %H:%M')}"
        self.assertEqual(str(appointment), expected_str)

    def test_appointment_auto_defaults(self):
        """Test automatic defaults for InitialConsultation"""
        appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='InitialConsultation',
            scheduled_start_time=self.future_datetime,
            scheduled_end_time=self.future_datetime + timedelta(hours=2)
        )

        # Meeting address should default to psychologist office address
        self.assertEqual(appointment.meeting_address, self.psychologist.office_address)
        # QR code should be auto-generated
        self.assertIsNotNone(appointment.qr_verification_code)
        self.assertEqual(len(appointment.qr_verification_code), 16)

    def test_appointment_validation_child_parent_mismatch(self):
        """Test validation when child doesn't belong to parent"""
        # Create another parent
        other_parent_user = User.objects.create_user(
            email='other@test.com',
            password='testpass123',
            user_type='Parent'
        )
        other_parent_user.is_verified = True
        other_parent_user.save()

        other_parent = Parent.objects.get(user=other_parent_user)
        other_parent.first_name = 'Other'
        other_parent.last_name = 'Parent'
        other_parent.save()

        # Create appointment instance without saving
        appointment = Appointment(
            child=self.child,  # Belongs to self.parent
            psychologist=self.psychologist,
            parent=other_parent,  # Different parent
            session_type='OnlineMeeting',
            scheduled_start_time=self.future_datetime,
            scheduled_end_time=self.future_datetime + timedelta(hours=1)
        )

        # Manually set the cache attributes that Django's validation expects
        appointment._child_cache = self.child
        appointment._parent_cache = other_parent

        with self.assertRaises(ValidationError) as context:
            appointment.full_clean()

        self.assertIn('child', context.exception.message_dict)

    def test_appointment_validation_duration(self):
        """Test validation of appointment duration"""
        # Wrong duration for OnlineMeeting
        with self.assertRaises(ValidationError) as context:
            appointment = Appointment(
                child=self.child,
                psychologist=self.psychologist,
                parent=self.parent,
                session_type='OnlineMeeting',
                scheduled_start_time=self.future_datetime,
                scheduled_end_time=self.future_datetime + timedelta(hours=2)  # Should be 1 hour
            )
            appointment.full_clean()

        self.assertIn('scheduled_end_time', context.exception.message_dict)

        # Wrong duration for InitialConsultation
        with self.assertRaises(ValidationError) as context:
            appointment = Appointment(
                child=self.child,
                psychologist=self.psychologist,
                parent=self.parent,
                session_type='InitialConsultation',
                scheduled_start_time=self.future_datetime,
                scheduled_end_time=self.future_datetime + timedelta(hours=1)  # Should be 2 hours
            )
            appointment.full_clean()

        self.assertIn('scheduled_end_time', context.exception.message_dict)

    def test_appointment_properties(self):
        """Test appointment properties"""
        appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='OnlineMeeting',
            scheduled_start_time=self.future_datetime,
            scheduled_end_time=self.future_datetime + timedelta(hours=1),

        )

        self.assertTrue(appointment.is_upcoming)
        self.assertFalse(appointment.is_past)
        self.assertTrue(appointment.can_be_cancelled)

        # Test past appointment
        past_datetime = timezone.now() - timedelta(hours=2)
        past_appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='OnlineMeeting',
            scheduled_start_time=past_datetime,
            scheduled_end_time=past_datetime + timedelta(hours=1),
        )

        self.assertFalse(past_appointment.is_upcoming)
        self.assertTrue(past_appointment.is_past)
        self.assertFalse(past_appointment.can_be_cancelled)

    def test_appointment_status_transitions(self):
        """Test appointment status transition methods"""
        appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='OnlineMeeting',
            scheduled_start_time=self.future_datetime,
            scheduled_end_time=self.future_datetime + timedelta(hours=1)
        )

        # Mark as scheduled
        self.assertEqual(appointment.appointment_status, 'Payment_Pending')
        appointment.mark_as_scheduled()
        appointment.refresh_from_db()
        self.assertEqual(appointment.appointment_status, 'Scheduled')
        self.assertEqual(appointment.payment_status, 'Paid')

        # Mark as completed
        appointment.mark_as_completed()
        appointment.refresh_from_db()
        self.assertEqual(appointment.appointment_status, 'Completed')
        self.assertIsNotNone(appointment.actual_end_time)

    def test_appointment_cancellation(self):
        """Test appointment cancellation"""
        appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='OnlineMeeting',
            scheduled_start_time=self.future_datetime,
            scheduled_end_time=self.future_datetime + timedelta(hours=1)
        )

        # Add and book slots
        appointment.appointment_slots.add(self.slot1)
        self.slot1.mark_as_booked()

        # Cancel appointment
        appointment.cancel_appointment("Changed mind")
        appointment.refresh_from_db()
        self.slot1.refresh_from_db()

        self.assertEqual(appointment.appointment_status, 'Cancelled')
        self.assertEqual(appointment.cancellation_reason, "Changed mind")
        self.assertFalse(self.slot1.is_booked)  # Slot should be released

    def test_appointment_qr_verification(self):
        """Test QR verification for InitialConsultation"""
        # Create appointment scheduled for now (timezone-aware)
        now = timezone.now()
        appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='InitialConsultation',
            scheduled_start_time=now,
            scheduled_end_time=now + timedelta(hours=2),
            appointment_status='Scheduled'
        )

        # Test can_be_verified property
        self.assertTrue(appointment.can_be_verified)

        # Verify session
        appointment.verify_session()
        appointment.refresh_from_db()

        self.assertIsNotNone(appointment.session_verified_at)
        self.assertIsNotNone(appointment.actual_start_time)

    def test_get_upcoming_appointments_parent(self):
        """Test get_upcoming_appointments for parent"""
        appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='OnlineMeeting',
            scheduled_start_time=self.future_datetime,
            scheduled_end_time=self.future_datetime + timedelta(hours=1),
            appointment_status='Scheduled'
        )


        upcoming = Appointment.get_upcoming_appointments(self.parent_user)
        self.assertEqual(upcoming.count(), 1)
        self.assertEqual(upcoming.first(), appointment)

    def test_get_upcoming_appointments_psychologist(self):
        """Test get_upcoming_appointments for psychologist"""
        appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='OnlineMeeting',
            scheduled_start_time=self.future_datetime,
            scheduled_end_time=self.future_datetime + timedelta(hours=1),
            appointment_status='Scheduled'
        )

        upcoming = Appointment.get_upcoming_appointments(self.psych_user)
        self.assertEqual(upcoming.count(), 1)
        self.assertEqual(upcoming.first(), appointment)

    def test_appointment_validation_meeting_constraints(self):
        """Test validation of meeting-specific constraints"""
        # Online meeting should not have QR code
        with self.assertRaises(ValidationError) as context:
            appointment = Appointment(
                child=self.child,
                psychologist=self.psychologist,
                parent=self.parent,
                session_type='OnlineMeeting',
                scheduled_start_time=self.future_datetime,
                scheduled_end_time=self.future_datetime + timedelta(hours=1),
                qr_verification_code='TESTCODE123'
            )
            appointment.full_clean()

        self.assertIn('qr_verification_code', context.exception.message_dict)

        # Initial consultation should not have meeting link
        with self.assertRaises(ValidationError) as context:
            appointment = Appointment(
                child=self.child,
                psychologist=self.psychologist,
                parent=self.parent,
                session_type='InitialConsultation',
                scheduled_start_time=self.future_datetime,
                scheduled_end_time=self.future_datetime + timedelta(hours=2),
                meeting_link='https://meet.example.com/123'
            )
            appointment.full_clean()

        self.assertIn('meeting_link', context.exception.message_dict)

    def test_appointment_qr_code_uniqueness(self):
        """Test QR code uniqueness"""
        appointment1 = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='InitialConsultation',
            scheduled_start_time=self.future_datetime,
            scheduled_end_time=self.future_datetime + timedelta(hours=2)
        )

        # Create second appointment on different day
        future_datetime2 = self.future_datetime + timedelta(days=1)
        appointment2 = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='InitialConsultation',
            scheduled_start_time=future_datetime2,
            scheduled_end_time=future_datetime2 + timedelta(hours=2)
        )

        # QR codes should be different
        self.assertNotEqual(appointment1.qr_verification_code, appointment2.qr_verification_code)
        self.assertEqual(len(appointment1.qr_verification_code), 16)
        self.assertEqual(len(appointment2.qr_verification_code), 16)