"""
Test cases for new appointment features:
1. No Show Management
2. In_Progress Status & Session Management
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import datetime, date, timedelta
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token
from unittest.mock import patch, MagicMock

from users.models import User
from parents.models import Parent
from psychologists.models import Psychologist, PsychologistAvailability
from children.models import Child
from appointments.models import Appointment, AppointmentSlot


class NoShowManagementTestCase(TestCase):
    """Test cases for No Show Management feature"""

    def setUp(self):
        """Set up test data"""
        # Create parent user and profile
        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True,
            is_active=True
        )
        self.parent = Parent.objects.get(user=self.parent_user)

        # Create psychologist user and profile
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Jane',
            last_name='Smith',
            license_number='PSY12345',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        # Create another psychologist for testing permissions
        self.other_psychologist_user = User.objects.create_user(
            email='other_psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )
        self.other_psychologist = Psychologist.objects.create(
            user=self.other_psychologist_user,
            first_name='John',
            last_name='Doe',
            license_number='PSY67890',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='456 Oak Ave, City, State'
        )

        # Create admin user
        self.admin_user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123',
            user_type='Admin'
        )

        # Create child
        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            last_name='Doe',
            date_of_birth=date.today() - timedelta(days=2555)  # ~7 years old
        )

        # Create appointment slots and availability
        self.availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time='09:00',
            end_time='17:00',
            is_recurring=True
        )

        # Helper function to get next Monday from today
        def get_next_monday():
            today = date.today()
            days_ahead = (7 - today.weekday()) % 7  # Days until Monday
            if days_ahead == 0:
                days_ahead = 7  # If today is Monday, get next Monday
            return today + timedelta(days=days_ahead)

        monday_date = get_next_monday()

        # Create appointment that ended >30 minutes ago (can be marked no-show)
        # Use fixed times to avoid validation issues
        self.past_appointment_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=monday_date,
            start_time='10:00',
            end_time='11:00',
            is_booked=True
        )

        # Calculate actual datetime for the appointment (in the past)
        past_end_time = timezone.now() - timedelta(minutes=35)
        past_start_time = past_end_time - timedelta(hours=1)

        self.past_appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            scheduled_start_time=past_start_time,
            scheduled_end_time=past_end_time,
            session_type='OnlineMeeting',
            appointment_status='Scheduled',
            meeting_link='https://meet.example.com/abc123',
        )
        self.past_appointment.appointment_slots.add(self.past_appointment_slot)

        # Create appointment that ended <30 minutes ago (cannot be marked no-show)
        self.recent_appointment_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=monday_date,
            start_time='11:00',
            end_time='12:00',
            is_booked=True
        )

        # Calculate actual datetime for the appointment (recent)
        recent_end_time = timezone.now() - timedelta(minutes=15)
        recent_start_time = recent_end_time - timedelta(hours=1)

        self.recent_appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            scheduled_start_time=recent_start_time,
            scheduled_end_time=recent_end_time,
            session_type='OnlineMeeting',
            appointment_status='Scheduled',
            meeting_link='https://meet.example.com/def456',
        )
        self.recent_appointment.appointment_slots.add(self.recent_appointment_slot)

        # Create appointment in progress
        self.in_progress_appointment_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=monday_date,
            start_time='12:00',
            end_time='13:00',
            is_booked=True
        )

        # Calculate actual datetime for the appointment (in progress)
        in_progress_start_time = timezone.now() - timedelta(minutes=30)
        in_progress_end_time = timezone.now() + timedelta(minutes=30)

        self.in_progress_appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            scheduled_start_time=in_progress_start_time,
            scheduled_end_time=in_progress_end_time,
            session_type='OnlineMeeting',
            appointment_status='In_Progress',
            meeting_link='https://meet.example.com/ghi789',
        )
        self.in_progress_appointment.appointment_slots.add(self.in_progress_appointment_slot)

        # Create tokens for authentication
        self.parent_token = Token.objects.create(user=self.parent_user)
        self.psychologist_token = Token.objects.create(user=self.psychologist_user)
        self.other_psychologist_token = Token.objects.create(user=self.other_psychologist_user)
        self.admin_token = Token.objects.create(user=self.admin_user)

        # Set up API client
        self.client = APIClient()

    def test_can_be_marked_no_show_property(self):
        """Test the can_be_marked_no_show property"""
        # Past appointment (>30 mins after end) should be markable
        self.assertTrue(self.past_appointment.can_be_marked_no_show)

        # Recent appointment (<30 mins after end) should not be markable
        self.assertFalse(self.recent_appointment.can_be_marked_no_show)

        # In progress appointment should be markable if >30 mins after end
        self.assertFalse(self.in_progress_appointment.can_be_marked_no_show)




    def test_mark_no_show_without_reason(self):
        """Test marking no-show without providing reason"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('appointment-mark-no-show', kwargs={'pk': self.past_appointment.appointment_id})
        data = {}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Refresh appointment from database
        self.past_appointment.refresh_from_db()
        self.assertEqual(self.past_appointment.appointment_status, 'No_Show')

    def test_mark_no_show_too_early(self):
        """Test marking no-show too early (within 30 minutes of end time)"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('appointment-mark-no-show', kwargs={'pk': self.recent_appointment.appointment_id})
        data = {'reason': 'Trying to mark early'}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Appointment status should remain unchanged
        self.recent_appointment.refresh_from_db()
        self.assertEqual(self.recent_appointment.appointment_status, 'Scheduled')

    def test_mark_no_show_wrong_psychologist(self):
        """Test marking no-show by different psychologist"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.other_psychologist_token.key}')

        url = reverse('appointment-mark-no-show', kwargs={'pk': self.past_appointment.appointment_id})
        data = {'reason': 'Wrong psychologist'}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


    def test_mark_no_show_as_parent(self):
        """Test marking no-show as parent (should fail)"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

        url = reverse('appointment-mark-no-show', kwargs={'pk': self.past_appointment.appointment_id})
        data = {'reason': 'Parent trying to mark'}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_mark_no_show_unauthenticated(self):
        """Test marking no-show without authentication"""
        url = reverse('appointment-mark-no-show', kwargs={'pk': self.past_appointment.appointment_id})
        data = {'reason': 'Unauthenticated request'}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)



    def test_mark_already_no_show_appointment(self):
        """Test marking an already no-show appointment"""
        # First mark as no-show
        self.past_appointment.mark_as_no_show("First time")

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('appointment-mark-no-show', kwargs={'pk': self.past_appointment.appointment_id})
        data = {'reason': 'Already marked'}

        response = self.client.post(url, data, format='json')

        # Should fail because appointment is already No_Show status
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_slot_release_on_no_show(self):
        """Test that appointment slots are properly released when marked no-show"""
        # Verify slot is initially booked
        self.assertTrue(self.past_appointment_slot.is_booked)

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('appointment-mark-no-show', kwargs={'pk': self.past_appointment.appointment_id})
        data = {'reason': 'Testing slot release'}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify slot is released
        self.past_appointment_slot.refresh_from_db()
        self.assertFalse(self.past_appointment_slot.is_booked)


class InProgressSessionManagementTestCase(TestCase):
    """Test cases for In_Progress Status & Session Management feature"""

    def setUp(self):
        """Set up test data"""
        # Create parent user and profile
        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True,
            is_active=True
        )
        self.parent = Parent.objects.get(user=self.parent_user)

        # Create psychologist user and profile
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Jane',
            last_name='Smith',
            license_number='PSY12345',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        # Create another psychologist for permission testing
        self.other_psychologist_user = User.objects.create_user(
            email='other_psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )
        self.other_psychologist = Psychologist.objects.create(
            user=self.other_psychologist_user,
            first_name='John',
            last_name='Doe',
            license_number='PSY67890',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='456 Oak Ave, City, State'
        )

        # Create admin user
        self.admin_user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123',
            user_type='Admin'
        )

        # Create child
        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            last_name='Doe',
            date_of_birth=date.today() - timedelta(days=2555)  # ~7 years old
        )

        # Create appointment slots and availability
        self.availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time='09:00',
            end_time='17:00',
            is_recurring=True
        )

        # Helper function to get next Monday from today
        def get_next_monday():
            today = date.today()
            days_ahead = (7 - today.weekday()) % 7  # Days until Monday
            if days_ahead == 0:
                days_ahead = 7  # If today is Monday, get next Monday
            return today + timedelta(days=days_ahead)

        monday_date = get_next_monday()

        # Create online appointment that can be started (within start window)
        self.online_appointment_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=monday_date,
            start_time='10:00',
            end_time='11:00',
            is_booked=True
        )

        # Calculate actual datetime for the appointment (near future)
        start_time = timezone.now() + timedelta(minutes=5)
        end_time = start_time + timedelta(hours=1)

        self.online_appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            scheduled_start_time=start_time,
            scheduled_end_time=end_time,
            session_type='OnlineMeeting',
            appointment_status='Scheduled',
            meeting_link='https://meet.example.com/abc123',
        )
        self.online_appointment.appointment_slots.add(self.online_appointment_slot)

        # Create online appointment that's too early to start (more than 15 mins before)
        self.early_appointment_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=monday_date,
            start_time='11:00',
            end_time='12:00',
            is_booked=True
        )

        # Calculate actual datetime for the appointment (too early)
        early_start_time = timezone.now() + timedelta(minutes=20)
        early_end_time = early_start_time + timedelta(hours=1)

        self.early_appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            scheduled_start_time=early_start_time,
            scheduled_end_time=early_end_time,
            session_type='OnlineMeeting',
            appointment_status='Scheduled',
            meeting_link='https://meet.example.com/def456',
        )
        self.early_appointment.appointment_slots.add(self.early_appointment_slot)

        # Create online appointment that's too late to start (after end time)
        self.late_appointment_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=monday_date,
            start_time='12:00',
            end_time='13:00',
            is_booked=True
        )

        # Calculate actual datetime for the appointment (too late)
        late_start_time = timezone.now() - timedelta(hours=2)
        late_end_time = late_start_time + timedelta(hours=1)

        self.late_appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            scheduled_start_time=late_start_time,
            scheduled_end_time=late_end_time,
            session_type='OnlineMeeting',
            appointment_status='Scheduled',
            meeting_link='https://meet.example.com/ghi789',
        )
        self.late_appointment.appointment_slots.add(self.late_appointment_slot)

        # Create in-person appointment (should not be startable via online endpoint)
        self.in_person_appointment_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=monday_date,
            start_time='13:00',
            end_time='14:00',
            is_booked=True
        )

        # Calculate actual datetime for the appointment (in-person, near future)
        in_person_start_time = timezone.now() + timedelta(minutes=5)
        in_person_end_time = in_person_start_time + timedelta(hours=2)

        self.in_person_appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            scheduled_start_time=in_person_start_time,
            scheduled_end_time=in_person_end_time,
            session_type='InitialConsultation',
            appointment_status='Scheduled',
            meeting_address='123 Main St, City, State',
        )
        self.in_person_appointment.appointment_slots.add(self.in_person_appointment_slot)

        # Create tokens for authentication
        self.parent_token = Token.objects.create(user=self.parent_user)
        self.psychologist_token = Token.objects.create(user=self.psychologist_user)
        self.other_psychologist_token = Token.objects.create(user=self.other_psychologist_user)
        self.admin_token = Token.objects.create(user=self.admin_user)

        # Set up API client
        self.client = APIClient()

    def test_can_start_online_session_property(self):
        """Test the can_start_online_session property"""
        # Online appointment within start window should be startable
        self.assertTrue(self.online_appointment.can_start_online_session)

        # Early appointment (>15 mins before start) should not be startable
        self.assertFalse(self.early_appointment.can_start_online_session)

        # Late appointment (after end time) should not be startable
        self.assertFalse(self.late_appointment.can_start_online_session)

        # In-person appointment should not be startable via online method
        self.assertFalse(self.in_person_appointment.can_start_online_session)

    def test_start_online_session_success(self):
        """Test successful online session start by assigned psychologist"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('appointment-start-online-session', kwargs={'pk': self.online_appointment.appointment_id})
        data = {}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        self.assertIn('appointment', response.data)

        # Refresh appointment from database
        self.online_appointment.refresh_from_db()
        self.assertEqual(self.online_appointment.appointment_status, 'In_Progress')
        self.assertIsNotNone(self.online_appointment.actual_start_time)

    def test_start_online_session_too_early(self):
        """Test starting online session too early (>15 minutes before start)"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('appointment-start-online-session', kwargs={'pk': self.early_appointment.appointment_id})
        data = {}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Appointment status should remain unchanged
        self.early_appointment.refresh_from_db()
        self.assertEqual(self.early_appointment.appointment_status, 'Scheduled')

    def test_start_online_session_too_late(self):
        """Test starting online session too late (after end time)"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('appointment-start-online-session', kwargs={'pk': self.late_appointment.appointment_id})
        data = {}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Appointment status should remain unchanged
        self.late_appointment.refresh_from_db()
        self.assertEqual(self.late_appointment.appointment_status, 'Scheduled')

    def test_start_in_person_session_online_endpoint(self):
        """Test starting in-person session via online endpoint (should fail)"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('appointment-start-online-session', kwargs={'pk': self.in_person_appointment.appointment_id})
        data = {}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Appointment status should remain unchanged
        self.in_person_appointment.refresh_from_db()
        self.assertEqual(self.in_person_appointment.appointment_status, 'Scheduled')

    def test_start_online_session_wrong_psychologist(self):
        """Test starting online session by different psychologist"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.other_psychologist_token.key}')
        url = reverse('appointment-start-online-session', kwargs={'pk': self.online_appointment.appointment_id})
        data = {}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_start_online_session_as_parent(self):
        """Test starting online session as parent (should fail)"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

        url = reverse('appointment-start-online-session', kwargs={'pk': self.online_appointment.appointment_id})
        data = {}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_start_online_session_unauthenticated(self):
        """Test starting online session without authentication"""
        url = reverse('appointment-start-online-session', kwargs={'pk': self.online_appointment.appointment_id})
        data = {}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


    def test_start_already_in_progress_session(self):
        """Test starting session that's already in progress"""
        # First start the session
        self.online_appointment.start_online_session()

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('appointment-start-online-session', kwargs={'pk': self.online_appointment.appointment_id})
        data = {}

        response = self.client.post(url, data, format='json')

        # Should fail because appointment is already In_Progress status
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_actual_start_time_recorded(self):
        """Test that actual_start_time is properly recorded when starting session"""
        # Verify no actual start time initially
        self.assertIsNone(self.online_appointment.actual_start_time)

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('appointment-start-online-session', kwargs={'pk': self.online_appointment.appointment_id})
        data = {}

        before_request = timezone.now()
        response = self.client.post(url, data, format='json')
        after_request = timezone.now()

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify actual start time is recorded
        self.online_appointment.refresh_from_db()
        self.assertIsNotNone(self.online_appointment.actual_start_time)
        self.assertGreaterEqual(self.online_appointment.actual_start_time, before_request)
        self.assertLessEqual(self.online_appointment.actual_start_time, after_request)


class AppointmentStatusChoicesTestCase(TestCase):
    """Test that In_Progress status is properly included in choices"""

    def test_in_progress_in_status_choices(self):
        """Test that In_Progress is in the appointment status choices"""
        from appointments.models import Appointment

        status_choices = [choice[0] for choice in Appointment.APPOINTMENT_STATUS_CHOICES]
        self.assertIn('In_Progress', status_choices)

    def test_appointment_can_be_created_with_in_progress_status(self):
        """Test that appointments can be created with In_Progress status"""
        from appointments.models import Appointment
        from users.models import User
        from parents.models import Parent
        from psychologists.models import Psychologist
        from children.models import Child

        # Set up required related objects
        parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True,
            is_active=True
        )
        parent = Parent.objects.get(user=parent_user)

        psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )
        psychologist = Psychologist.objects.create(
            user=psychologist_user,
            first_name='Jane',
            last_name='Smith',
            license_number='PSY12345',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        child = Child.objects.create(
            parent=parent,
            first_name='Alice',
            last_name='Doe',
            date_of_birth=date.today() - timedelta(days=2555)
        )

        # Create appointment with In_Progress status
        start_time = timezone.now()
        end_time = start_time + timedelta(hours=1)  # Exactly 1 hour for online session

        appointment = Appointment.objects.create(
            child=child,
            psychologist=psychologist,
            parent=parent,
            scheduled_start_time=start_time,
            scheduled_end_time=end_time,
            session_type='OnlineMeeting',
            appointment_status='In_Progress',
            meeting_link='https://meet.example.com/test123',
        )

        self.assertEqual(appointment.appointment_status, 'In_Progress')
        appointment.refresh_from_db()
        self.assertEqual(appointment.appointment_status, 'In_Progress')


class IntegrationTestCase(TestCase):
    """Integration tests for both features working together"""

    def setUp(self):
        """Set up test data for integration tests"""
        # Create parent user and profile
        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True,
            is_active=True
        )
        self.parent = Parent.objects.get(user=self.parent_user)

        # Create psychologist user and profile
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Jane',
            last_name='Smith',
            license_number='PSY12345',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        # Create child
        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            last_name='Doe',
            date_of_birth=date.today() - timedelta(days=2555)
        )

        # Create appointment that can be started and later marked no-show
        self.availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,
            start_time='09:00',
            end_time='17:00',
            is_recurring=True
        )

        # Helper function to get next Monday from today
        def get_next_monday():
            today = date.today()
            days_ahead = (7 - today.weekday()) % 7  # Days until Monday
            if days_ahead == 0:
                days_ahead = 7  # If today is Monday, get next Monday
            return today + timedelta(days=days_ahead)

        monday_date = get_next_monday()

        # Create appointment slot
        self.appointment_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=monday_date,
            start_time='10:00',
            end_time='11:00',
            is_booked=True
        )

        # Calculate actual datetime for the appointment
        start_time = timezone.now() + timedelta(minutes=5)
        end_time = start_time + timedelta(hours=1)

        self.appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            scheduled_start_time=start_time,
            scheduled_end_time=end_time,
            session_type='OnlineMeeting',
            appointment_status='Scheduled',
            meeting_link='https://meet.example.com/integration123',
        )
        self.appointment.appointment_slots.add(self.appointment_slot)

        # Create token for authentication
        self.psychologist_token = Token.objects.create(user=self.psychologist_user)
        self.client = APIClient()

    def test_in_progress_appointment_can_be_marked_no_show_after_time(self):
        """Test that In_Progress appointments can be marked no-show after 30 minutes past end time"""
        # Start the session
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        start_url = reverse('appointment-start-online-session', kwargs={'pk': self.appointment.appointment_id})
        start_response = self.client.post(start_url, {}, format='json')
        self.assertEqual(start_response.status_code, status.HTTP_200_OK)

        # Verify it's in progress
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.appointment_status, 'In_Progress')

        # Mock time to be 35 minutes after scheduled end time
        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = self.appointment.scheduled_end_time + timedelta(minutes=35)

            # Now try to mark as no-show
            no_show_url = reverse('appointment-mark-no-show', kwargs={'pk': self.appointment.appointment_id})
            no_show_response = self.client.post(no_show_url, {'reason': 'Patient left early'}, format='json')

            self.assertEqual(no_show_response.status_code, status.HTTP_200_OK)

            # Verify appointment is marked no-show
            self.appointment.refresh_from_db()
            self.assertEqual(self.appointment.appointment_status, 'No_Show')

            # Verify slot is released
            self.appointment_slot.refresh_from_db()
            self.assertFalse(self.appointment_slot.is_booked)

    def test_workflow_start_session_then_complete_lifecycle(self):
        """Test complete workflow: start session -> in progress -> complete cycle"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        # 1. Start online session
        start_url = reverse('appointment-start-online-session', kwargs={'pk': self.appointment.appointment_id})
        start_response = self.client.post(start_url, {}, format='json')

        self.assertEqual(start_response.status_code, status.HTTP_200_OK)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.appointment_status, 'In_Progress')

        # 2. Verify that appointment cannot be marked no-show while in window
        no_show_url = reverse('appointment-mark-no-show', kwargs={'pk': self.appointment.appointment_id})
        early_no_show_response = self.client.post(no_show_url, {'reason': 'Too early'}, format='json')

        self.assertEqual(early_no_show_response.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. Mock time advancement and verify no-show becomes available
        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = self.appointment.scheduled_end_time + timedelta(minutes=35)

            # Should be able to mark no-show now
            self.assertTrue(self.appointment.can_be_marked_no_show)

            late_no_show_response = self.client.post(no_show_url, {'reason': 'Patient disappeared'}, format='json')
            self.assertEqual(late_no_show_response.status_code, status.HTTP_200_OK)