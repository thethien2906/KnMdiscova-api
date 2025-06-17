# appointments/tests/test_zoom_service.py

from unittest.mock import patch, Mock, MagicMock
from decimal import Decimal
from datetime import datetime, timedelta, date
from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.cache import cache

from appointments.services.zoom_service import (
    ZoomService,
    ZoomAuthenticationError,
    ZoomMeetingCreationError,
    ZoomMeetingUpdateError,
    ZoomMeetingDeletionError
)
from appointments.models import Appointment, AppointmentSlot, PsychologistAvailability
from psychologists.models import Psychologist
from parents.models import Parent
from children.models import Child
from users.models import User


class ZoomServiceTestCase(TestCase):
    """Test cases for Zoom service"""

    def setUp(self):
        """Set up test data"""
        # Clear cache before each test
        cache.clear()

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

        # Create future appointment slot for Zoom meeting creation tests
        self.future_appointment_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=monday_date,
            start_time='14:00',
            end_time='15:00',
            is_booked=True
        )

        # Calculate future datetime for the appointment
        future_start_time = timezone.now() + timedelta(days=1)
        future_end_time = future_start_time + timedelta(hours=1)

        # Create test appointment for Zoom service tests
        self.appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            scheduled_start_time=future_start_time,
            scheduled_end_time=future_end_time,
            session_type='OnlineMeeting',
            appointment_status='Scheduled',
            payment_status='Paid',
            meeting_link='https://meet.example.com/abc123',
        )
        self.appointment.appointment_slots.add(self.future_appointment_slot)

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
            meeting_link='https://meet.example.com/past123',
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
            meeting_link='https://meet.example.com/recent456',
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
            meeting_link='https://meet.example.com/progress789',
        )
        self.in_progress_appointment.appointment_slots.add(self.in_progress_appointment_slot)

    @override_settings(
        ZOOM_CONFIG={
            'ENABLED': True,
            'ACCOUNT_ID': 'test_account_id',
            'CLIENT_ID': 'test_client_id',
            'CLIENT_SECRET': 'test_client_secret',
            'OAUTH_TOKEN_URL': 'https://zoom.us/oauth/token',
            'API_BASE_URL': 'https://api.zoom.us/v2',
            'MEETING_DEFAULTS': {
                'TIMEZONE': 'UTC',
                'DURATION_MINUTES': 60,
                'ENABLE_WAITING_ROOM': True,
                'ENABLE_JOIN_BEFORE_HOST': False,
                'JOIN_BEFORE_HOST_MINUTES': 5,
                'AUTO_RECORDING': 'none',
                'MUTE_UPON_ENTRY': False,
            },
            'SECURITY': {
                'REQUIRE_MEETING_PASSWORD': True,
                'ENFORCE_LOGIN': False,
                'ENFORCE_LOGIN_DOMAINS': '',
                'ALTERNATIVE_HOSTS': '',
            }
        }
    )
    def test_zoom_service_enabled(self):
        """Test Zoom service enabled check"""
        service = ZoomService()
        self.assertTrue(service.is_enabled())

    @override_settings(
        ZOOM_CONFIG={
            'ENABLED': False,
            'ACCOUNT_ID': 'test_account_id',
            'CLIENT_ID': 'test_client_id',
            'CLIENT_SECRET': 'test_client_secret',
        }
    )
    def test_zoom_service_disabled(self):
        """Test Zoom service disabled check"""
        service = ZoomService()
        self.assertFalse(service.is_enabled())

    @override_settings(
        ZOOM_CONFIG={
            'ENABLED': True,
            'ACCOUNT_ID': '',  # Missing account ID
            'CLIENT_ID': 'test_client_id',
            'CLIENT_SECRET': 'test_client_secret',
        }
    )
    def test_zoom_service_missing_config(self):
        """Test Zoom service with missing configuration"""
        service = ZoomService()
        self.assertFalse(service.is_enabled())

    @override_settings(ZOOM_CONFIG={
        'ENABLED': True,
        'ACCOUNT_ID': 'test_account_id',
        'CLIENT_ID': 'test_client_id',
        'CLIENT_SECRET': 'test_client_secret',
        'OAUTH_TOKEN_URL': 'https://zoom.us/oauth/token',
    })
    @patch('appointments.services.requests.post')
    def test_get_access_token_success(self, mock_post):
        """Test successful OAuth token retrieval"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'test_access_token',
            'expires_in': 3600
        }
        mock_post.return_value = mock_response

        service = ZoomService()
        token = service._get_access_token()

        self.assertEqual(token, 'test_access_token')

        # Verify token is cached
        cached_token = cache.get('zoom_oauth_token')
        self.assertEqual(cached_token, 'test_access_token')

        # Verify OAuth request
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertEqual(call_args[0][0], 'https://zoom.us/oauth/token')
        self.assertEqual(call_args[1]['params']['grant_type'], 'account_credentials')
        self.assertEqual(call_args[1]['auth'], ('test_client_id', 'test_client_secret'))

    @override_settings(ZOOM_CONFIG={
        'ENABLED': True,
        'ACCOUNT_ID': 'test_account_id',
        'CLIENT_ID': 'test_client_id',
        'CLIENT_SECRET': 'test_client_secret',
        'OAUTH_TOKEN_URL': 'https://zoom.us/oauth/token',
    })
    @patch('appointments.services.requests.post')
    def test_get_access_token_failure(self, mock_post):
        """Test failed OAuth token retrieval"""
        # Mock failed response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = 'Unauthorized'
        mock_post.return_value = mock_response

        service = ZoomService()

        with self.assertRaises(ZoomAuthenticationError):
            service._get_access_token()

    @override_settings(ZOOM_CONFIG={
        'ENABLED': True,
        'ACCOUNT_ID': 'test_account_id',
        'CLIENT_ID': 'test_client_id',
        'CLIENT_SECRET': 'test_client_secret',
        'OAUTH_TOKEN_URL': 'https://zoom.us/oauth/token',
        'API_BASE_URL': 'https://api.zoom.us/v2',
        'MEETING_DEFAULTS': {
            'TIMEZONE': 'UTC',
            'DURATION_MINUTES': 60,
            'ENABLE_WAITING_ROOM': True,
            'ENABLE_JOIN_BEFORE_HOST': False,
            'JOIN_BEFORE_HOST_MINUTES': 5,
            'AUTO_RECORDING': 'none',
            'MUTE_UPON_ENTRY': False,
        },
        'SECURITY': {
            'REQUIRE_MEETING_PASSWORD': True,
            'ENFORCE_LOGIN': False,
            'ENFORCE_LOGIN_DOMAINS': '',
            'ALTERNATIVE_HOSTS': '',
        }
    })
    @patch('appointments.services.ZoomService._get_access_token')
    @patch('appointments.services.requests.request')
    def test_create_meeting_success(self, mock_request, mock_get_token):
        """Test successful meeting creation"""
        # Mock access token
        mock_get_token.return_value = 'test_access_token'

        # Mock successful meeting creation response
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': '12345678901',
            'join_url': 'https://zoom.us/j/12345678901',
            'start_url': 'https://zoom.us/s/12345678901',
            'topic': 'Session with Dr. Test Psychologist',
            'duration': 60,
            'timezone': 'UTC'
        }
        mock_request.return_value = mock_response

        service = ZoomService()
        result = service.create_meeting_for_appointment(self.appointment)

        self.assertEqual(result['meeting_id'], '12345678901')
        self.assertEqual(result['meeting_link'], 'https://zoom.us/j/12345678901')
        self.assertIn('meeting_password', result)
        self.assertIn('host_start_url', result)

        # Verify API request
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        self.assertEqual(call_args[1]['method'], 'POST')
        self.assertIn('/users/me/meetings', call_args[1]['url'])
        self.assertEqual(
            call_args[1]['headers']['Authorization'],
            'Bearer test_access_token'
        )

    def test_create_meeting_wrong_session_type(self):
        """Test meeting creation with wrong session type"""
        # Create appointment with wrong session type, bypassing validation
        self.appointment.session_type = 'InitialConsultation'
        # Use update() to bypass model validation, or save with update_fields
        Appointment.objects.filter(appointment_id=self.appointment.appointment_id).update(session_type='InitialConsultation')
        self.appointment.refresh_from_db()

        service = ZoomService()

        with self.assertRaises(ValueError) as context:
            service.create_meeting_for_appointment(self.appointment)

        self.assertIn('Zoom meetings are only for online sessions', str(context.exception))


    @override_settings(
        ZOOM_CONFIG={
            'ENABLED': False,
            'ACCOUNT_ID': 'test_account_id',
            'CLIENT_ID': 'test_client_id',
            'CLIENT_SECRET': 'test_client_secret',
            'OAUTH_TOKEN_URL': 'https://zoom.us/oauth/token',
            'API_BASE_URL': 'https://api.zoom.us/v2',
            'MEETING_DEFAULTS': {
                'TIMEZONE': 'UTC',
                'DURATION_MINUTES': 60,
                'ENABLE_WAITING_ROOM': True,
                'ENABLE_JOIN_BEFORE_HOST': False,
                'JOIN_BEFORE_HOST_MINUTES': 5,
                'AUTO_RECORDING': 'none',
                'MUTE_UPON_ENTRY': False,
            },
            'SECURITY': {
                'REQUIRE_MEETING_PASSWORD': True,
                'ENFORCE_LOGIN': False,
                'ENFORCE_LOGIN_DOMAINS': '',
                'ALTERNATIVE_HOSTS': '',
            }
        }
    )
    def test_create_meeting_zoom_disabled(self):
        """Test meeting creation when Zoom is disabled"""
        service = ZoomService()

        with self.assertRaises(ZoomMeetingCreationError) as context:
            service.create_meeting_for_appointment(self.appointment)

        self.assertIn('not enabled', str(context.exception))

    @override_settings(ZOOM_CONFIG={
        'ENABLED': True,
        'ACCOUNT_ID': 'test_account_id',
        'CLIENT_ID': 'test_client_id',
        'CLIENT_SECRET': 'test_client_secret',
        'API_BASE_URL': 'https://api.zoom.us/v2',
    })
    @patch('appointments.services.ZoomService._get_access_token')
    @patch('appointments.services.requests.request')
    def test_delete_meeting_success(self, mock_request, mock_get_token):
        """Test successful meeting deletion"""
        mock_get_token.return_value = 'test_access_token'

        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.content = b''
        mock_request.return_value = mock_response

        service = ZoomService()
        service.delete_meeting('12345678901')

        # Verify API request
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        self.assertEqual(call_args[1]['method'], 'DELETE')
        self.assertIn('/meetings/12345678901', call_args[1]['url'])

    def test_generate_meeting_password(self):
        """Test meeting password generation"""
        service = ZoomService()

        # Generate multiple passwords and check requirements
        for _ in range(10):
            password = service._generate_meeting_password()

            # Check length
            self.assertEqual(len(password), 8)

            # Check characters are alphanumeric
            self.assertTrue(password.isalnum())

            # Ensure no ambiguous characters
            ambiguous = set('0OIl1')
            self.assertFalse(any(c in ambiguous for c in password))