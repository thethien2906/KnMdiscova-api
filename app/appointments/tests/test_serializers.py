# appointments/tests/test_serializers.py
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import date, time, datetime, timedelta
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.request import Request

from appointments.models import AppointmentSlot, Appointment
from appointments.serializers import (
    AppointmentSlotSerializer,
    AppointmentSlotCreateSerializer,
    AppointmentSerializer,
    AppointmentCreateSerializer,
    AppointmentUpdateSerializer,
    AppointmentDetailSerializer,
    QRVerificationSerializer,
    AppointmentSearchSerializer,
    AppointmentCancellationSerializer
)
from psychologists.models import Psychologist, PsychologistAvailability
from parents.models import Parent
from children.models import Child

User = get_user_model()


class AppointmentSlotSerializerTests(TestCase):
    """Test AppointmentSlotSerializer"""

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
            first_name='Jane',
            last_name='Smith',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        # Create availability block
        self.availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time=time(9, 0),
            end_time=time(12, 0),
            is_recurring=True
        )

        # Create appointment slot
        tomorrow = date.today() + timedelta(days=1)
        # Ensure tomorrow is a Monday (day_of_week=1)
        while tomorrow.weekday() != 0:  # 0 = Monday in Python
            tomorrow += timedelta(days=1)

        self.slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability,
            slot_date=tomorrow,
            start_time=time(9, 0),
            end_time=time(10, 0)
        )

    def test_appointment_slot_serialization(self):
        """Test basic AppointmentSlot serialization"""
        serializer = AppointmentSlotSerializer(self.slot)
        data = serializer.data

        self.assertEqual(data['slot_id'], self.slot.slot_id)
        self.assertEqual(str(data['psychologist']), str(self.psychologist.user.id))
        self.assertEqual(data['psychologist_name'], 'Dr. Jane Smith')
        self.assertEqual(data['slot_date'], self.slot.slot_date.isoformat())
        self.assertEqual(data['start_time'], '09:00:00')
        self.assertEqual(data['end_time'], '10:00:00')
        self.assertFalse(data['is_booked'])
        self.assertTrue(data['is_available_for_booking'])

    def test_appointment_slot_create_serializer_valid(self):
        """Test valid AppointmentSlotCreateSerializer"""
        tomorrow = date.today() + timedelta(days=2)
        data = {
            'psychologist': self.psychologist.user.id,
            'availability_block': self.availability.availability_id,
            'slot_date': tomorrow,
            'start_time': '10:00:00',
            'end_time': '11:00:00'
        }

        serializer = AppointmentSlotCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_appointment_slot_create_serializer_past_date(self):
        """Test AppointmentSlotCreateSerializer with past date"""
        yesterday = date.today() - timedelta(days=1)
        data = {
            'psychologist': self.psychologist.user.id,
            'availability_block': self.availability.availability_id,
            'slot_date': yesterday,
            'start_time': '10:00:00',
            'end_time': '11:00:00'
        }

        serializer = AppointmentSlotCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('slot_date', serializer.errors)

    def test_appointment_slot_create_serializer_invalid_duration(self):
        """Test AppointmentSlotCreateSerializer with invalid duration"""
        tomorrow = date.today() + timedelta(days=1)
        data = {
            'psychologist': self.psychologist.user.id,
            'availability_block': self.availability.availability_id,
            'slot_date': tomorrow,
            'start_time': '10:00:00',
            'end_time': '10:30:00'  # Only 30 minutes
        }

        serializer = AppointmentSlotCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('end_time', serializer.errors)


class AppointmentSerializerTests(TestCase):
    """Test AppointmentSerializer"""

    def setUp(self):
        # Create test users and profiles
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )

        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )

        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Jane',
            last_name='Smith',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        # Parent profile is created automatically via Django signal
        self.parent = self.parent_user.parent_profile

        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            date_of_birth=date.today() - timedelta(days=365 * 8)  # 8 years old
        )

        self.availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time=time(9, 0),
            end_time=time(12, 0),
            is_recurring=True
        )

        # Create appointment slot - ensure date is a Monday
        tomorrow = date.today() + timedelta(days=1)
        # Ensure tomorrow is a Monday (day_of_week=1)
        while tomorrow.weekday() != 0:  # 0 = Monday in Python
            tomorrow += timedelta(days=1)

        self.slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability,
            slot_date=tomorrow,
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_booked=False
        )

        # Create appointment
        scheduled_start = timezone.make_aware(
            datetime.combine(tomorrow, time(9, 0))
        )

        self.appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='OnlineMeeting',
            scheduled_start_time=scheduled_start,
            scheduled_end_time=scheduled_start + timedelta(hours=1),
            appointment_status='Scheduled'
        )
        self.appointment.appointment_slots.add(self.slot)

    def test_appointment_serialization(self):
        """Test basic Appointment serialization"""
        serializer = AppointmentSerializer(self.appointment)
        data = serializer.data

        self.assertEqual(str(data['appointment_id']), str(self.appointment.appointment_id))
        self.assertEqual(data['child_name'], 'Alice')
        self.assertEqual(data['psychologist_name'], 'Dr. Jane Smith')
        self.assertEqual(data['parent_email'], 'parent@test.com')
        self.assertEqual(data['session_type'], 'OnlineMeeting')
        self.assertEqual(data['appointment_status'], 'Scheduled')
        self.assertEqual(data['duration_hours'], 1)
        self.assertTrue(data['is_upcoming'])
        self.assertFalse(data['is_past'])

    def test_appointment_detail_serialization(self):
        """Test AppointmentDetailSerializer"""
        serializer = AppointmentDetailSerializer(self.appointment)
        data = serializer.data

        # Should include related objects
        self.assertIn('child', data)
        self.assertIn('psychologist', data)
        self.assertIn('parent', data)
        self.assertIn('appointment_slots', data)
        self.assertIn('meeting_info', data)
        self.assertIn('verification_info', data)

        # Check meeting info for online session
        meeting_info = data['meeting_info']
        self.assertEqual(meeting_info['type'], 'online')

        # Check verification info for online session
        verification_info = data['verification_info']
        self.assertFalse(verification_info['requires_verification'])


class AppointmentCreateSerializerTests(TestCase):
    """Test AppointmentCreateSerializer"""

    def setUp(self):
        # Create test users and profiles
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )

        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )

        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Dr. Jane',
            last_name='Smith',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        # Parent profile is created automatically via Django signal
        self.parent = self.parent_user.parent_profile

        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            date_of_birth=date.today() - timedelta(days=365 * 8)
        )

        # Create availability block (this was missing!)
        self.availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time=time(9, 0),
            end_time=time(12, 0),
            is_recurring=True
        )

        # Create available slot with proper availability block
        tomorrow = date.today() + timedelta(days=1)
        # Ensure tomorrow is a Monday (day_of_week=1) to match availability
        while tomorrow.weekday() != 0:  # 0 = Monday in Python
            tomorrow += timedelta(days=1)

        self.slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability,  # Now properly set
            slot_date=tomorrow,
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_booked=False
        )

        # Create request context
        factory = APIRequestFactory()
        request = factory.post('/test/')
        request.user = self.parent_user
        self.request_context = Request(request)

    def test_appointment_create_serializer_valid(self):
        """Test valid appointment creation"""
        data = {
            'child': self.child.id,
            'psychologist': self.psychologist.user.id,
            'session_type': 'OnlineMeeting',
            'start_slot_id': self.slot.slot_id,
            'parent_notes': 'Test appointment'
        }

        serializer = AppointmentCreateSerializer(
            data=data,
            context={'request': self.request_context}
        )
        self.assertTrue(serializer.is_valid())

    def test_appointment_create_child_not_belongs_to_parent(self):
        """Test appointment creation with child not belonging to parent"""

        # Create another parent and child
        other_user = User.objects.create_user(
            email='other@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        other_parent = other_user.parent_profile
        other_child = Child.objects.create(
            parent=other_parent,
            first_name='Bob',
            date_of_birth=date.today() - timedelta(days=365 * 6)
        )

        data = {
            'child': other_child.id,
            'psychologist': self.psychologist.user.id,
            'session_type': 'OnlineMeeting',
            'start_slot_id': self.slot.slot_id
        }

        factory = APIRequestFactory()
        request = factory.post('/appointments/')
        request.user = self.parent_user  # make sure this is the parent you're testing with

        serializer = AppointmentCreateSerializer(
            data=data,
            context={'request': request}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('child', serializer.errors)


    def test_appointment_create_psychologist_not_offering_service(self):
        """Test appointment creation when psychologist doesn't offer the service"""
        # Update psychologist to not offer online sessions
        self.psychologist.offers_online_sessions = False
        self.psychologist.save()

        data = {
            'child': self.child.id,
            'psychologist': self.psychologist.user.id,
            'session_type': 'OnlineMeeting',
            'start_slot_id': self.slot.slot_id
        }

        serializer = AppointmentCreateSerializer(
            data=data,
            context={'request': self.request_context}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('session_type', serializer.errors)

    def test_appointment_create_slot_not_available(self):
        """Test appointment creation with unavailable slot"""
        # Mark slot as booked
        self.slot.is_booked = True
        self.slot.save()

        data = {
            'child': self.child.id,
            'psychologist': self.psychologist.user.id,
            'session_type': 'OnlineMeeting',
            'start_slot_id': self.slot.slot_id
        }

        serializer = AppointmentCreateSerializer(
            data=data,
            context={'request': self.request_context}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('start_slot_id', serializer.errors)

    def test_appointment_create_invalid_slot_id(self):
        """Test appointment creation with invalid slot ID"""
        data = {
            'child': self.child.id,
            'psychologist': self.psychologist.user.id,
            'session_type': 'OnlineMeeting',
            'start_slot_id': 99999  # Non-existent slot
        }

        serializer = AppointmentCreateSerializer(
            data=data,
            context={'request': self.request_context}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('start_slot_id', serializer.errors)


class AppointmentUpdateSerializerTests(TestCase):
    """Test AppointmentUpdateSerializer"""

    def setUp(self):
        # Create test users
        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )

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
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        # Parent profile is created automatically via Django signal
        self.parent = self.parent_user.parent_profile

        # Create child
        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            date_of_birth=date.today() - timedelta(days=365 * 8)  # 8 years old
        )

        # Create appointment with proper instances and exactly 1 hour duration
        start_time = timezone.now() + timedelta(hours=24)
        end_time = start_time + timedelta(hours=1)  # Exactly 1 hour

        self.appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='OnlineMeeting',
            scheduled_start_time=start_time,
            scheduled_end_time=end_time,
            appointment_status='Scheduled'
        )

        # Create request contexts properly
        factory = APIRequestFactory()

        # Parent context
        parent_request = factory.patch('/test/')
        force_authenticate(parent_request, user=self.parent_user)
        self.parent_context = Request(parent_request)  # Wrap with DRF Request

        # Psychologist context
        psychologist_request = factory.patch('/test/')
        force_authenticate(psychologist_request, user=self.psychologist_user)
        self.psychologist_context = Request(psychologist_request)


    def test_cannot_update_cancellation_reason_for_completed_appointment(self):
        """Test cannot update cancellation reason for completed appointments"""
        self.appointment.appointment_status = 'Completed'
        self.appointment.save()

        data = {'cancellation_reason': 'Trying to cancel completed appointment'}

        serializer = AppointmentUpdateSerializer(
            instance=self.appointment,
            data=data,
            context={'request': self.parent_context}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('cancellation_reason', serializer.errors)


class QRVerificationSerializerTests(TestCase):
    """Test QRVerificationSerializer"""

    def setUp(self):
        # Create test users
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )

        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
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
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        # Parent profile is created automatically via Django signal
        self.parent = self.parent_user.parent_profile

        # Create child
        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            date_of_birth=date.today() - timedelta(days=365 * 8)  # 8 years old
        )

        # Create appointment with QR code
        tomorrow = timezone.now() + timedelta(days=1)
        self.appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            session_type='InitialConsultation',
            scheduled_start_time=tomorrow,
            scheduled_end_time=tomorrow + timedelta(hours=2),
            appointment_status='Scheduled',
            meeting_address='123 Main St, City, State',  # Required for InitialConsultation
            qr_verification_code='TEST123QR456'
        )

    def test_valid_qr_verification(self):
        """Test valid QR code verification"""
        # Set appointment time to now (within verification window)
        now = timezone.now()
        self.appointment.scheduled_start_time = now
        self.appointment.scheduled_end_time = now + timedelta(hours=2)
        self.appointment.save()

        data = {'qr_code': 'TEST123QR456'}
        serializer = QRVerificationSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_invalid_qr_code(self):
        """Test invalid QR code"""
        data = {'qr_code': 'INVALID_CODE'}
        serializer = QRVerificationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('qr_code', serializer.errors)

    def test_qr_code_outside_verification_window(self):
        """Test QR code verification outside time window"""
        # Set appointment time far in the future
        future_time = timezone.now() + timedelta(hours=24)
        self.appointment.scheduled_start_time = future_time
        self.appointment.scheduled_end_time = future_time + timedelta(hours=2)
        self.appointment.save()

        data = {'qr_code': 'TEST123QR456'}
        serializer = QRVerificationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('qr_code', serializer.errors)


class AppointmentSearchSerializerTests(TestCase):
    """Test AppointmentSearchSerializer"""

    def test_valid_search_parameters(self):
        """Test valid search parameters"""
        data = {
            'date_from': date.today(),
            'date_to': date.today() + timedelta(days=30),
            'appointment_status': 'Scheduled',
            'session_type': 'OnlineMeeting',
            'is_upcoming': True
        }

        serializer = AppointmentSearchSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_invalid_date_range(self):
        """Test invalid date range"""
        data = {
            'date_from': date.today() + timedelta(days=30),
            'date_to': date.today(),  # End date before start date
        }

        serializer = AppointmentSearchSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('date_from', serializer.errors)

    def test_conflicting_time_filters(self):
        """Test conflicting time filters"""
        data = {
            'is_upcoming': True,
            'is_past': True  # Cannot be both upcoming and past
        }

        serializer = AppointmentSearchSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_valid_individual_filters(self):
        """Test individual filter parameters"""
        # Test each filter individually
        filters = [
            {'appointment_status': 'Scheduled'},
            {'session_type': 'InitialConsultation'},
            {'is_upcoming': True},
            {'is_past': False}
        ]

        for filter_data in filters:
            with self.subTest(filter_data=filter_data):
                serializer = AppointmentSearchSerializer(data=filter_data)
                self.assertTrue(serializer.is_valid())


class AppointmentCancellationSerializerTests(TestCase):
    """Test AppointmentCancellationSerializer"""

    def setUp(self):
        # Create all necessary objects first
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )

        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )

        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Dr. Jane',
            last_name='Smith',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            office_address='123 Main St'
        )

        # Parent profile should be created automatically via signal
        self.parent = self.parent_user.parent_profile

        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            date_of_birth=date.today() - timedelta(days=365 * 8)
        )

        # Now create appointment with actual objects
        tomorrow = timezone.now() + timedelta(days=1)
        self.appointment = Appointment.objects.create(
            child=self.child,  # Use actual child object
            psychologist=self.psychologist,  # Use actual psychologist object
            parent=self.parent,  # Use actual parent object
            session_type='OnlineMeeting',
            scheduled_start_time=tomorrow,
            scheduled_end_time=tomorrow + timedelta(hours=1),
            appointment_status='Scheduled'
        )

    def test_valid_cancellation_with_reason(self):
        """Test valid cancellation with reason"""
        data = {'cancellation_reason': 'Child is sick'}

        serializer = AppointmentCancellationSerializer(
            data=data,
            context={'appointment': self.appointment}
        )
        self.assertTrue(serializer.is_valid())

    def test_valid_cancellation_without_reason(self):
        """Test valid cancellation without reason"""
        data = {}

        serializer = AppointmentCancellationSerializer(
            data=data,
            context={'appointment': self.appointment}
        )
        self.assertTrue(serializer.is_valid())

    def test_cannot_cancel_non_cancellable_appointment(self):
        """Test cannot cancel non-cancellable appointment"""
        # Mark appointment as completed
        self.appointment.appointment_status = 'Completed'
        self.appointment.save()

        data = {'cancellation_reason': 'Trying to cancel completed appointment'}

        serializer = AppointmentCancellationSerializer(
            data=data,
            context={'appointment': self.appointment}
        )
        self.assertFalse(serializer.is_valid())