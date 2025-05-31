# appointments/tests/test_views_AppointmentViewSet.py
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token
from unittest.mock import patch, MagicMock
from datetime import date, datetime, timedelta
import uuid

from users.models import User
from parents.models import Parent
from psychologists.models import Psychologist, PsychologistAvailability
from children.models import Child
from appointments.models import Appointment, AppointmentSlot
from appointments.services import (
    AppointmentBookingService,
    AppointmentManagementService,
    AppointmentBookingError,
    AppointmentNotFoundError,
    SlotNotAvailableError,
    InsufficientConsecutiveSlotsError,
    AppointmentCancellationError,
    QRVerificationError
)

def get_next_weekday(weekday: int) -> date:
    """Returns the next date that matches the given weekday (0=Monday, ..., 6=Sunday)"""
    today = date.today()
    days_ahead = (weekday - today.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7  # get *next* weekday, not today
    return today + timedelta(days=days_ahead)
class AppointmentViewSetTestCase(APITestCase):
    """
    Test cases for AppointmentViewSet
    """

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

        # Create appointment slots
        self.availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time='09:00',
            end_time='17:00',
            is_recurring=True
        )

        # Create appointment slots for testing
        today = date.today()
        days_ahead = (7 - today.weekday()) % 7  # Days until Monday
        if days_ahead == 0:
            days_ahead = 7  # If today is Monday, get next Monday
        slot_date = today + timedelta(days=days_ahead)

        self.appointment_slot1 = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=slot_date,
            start_time='09:00',
            end_time='10:00',
            is_booked=False
        )

        self.appointment_slot2 = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=slot_date,
            start_time='10:00',
            end_time='11:00',
            is_booked=False
        )

        # Create a sample appointment
        self.appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            scheduled_start_time=timezone.make_aware(
                datetime.combine(slot_date, datetime.strptime('10:00', '%H:%M').time())
            ),
            scheduled_end_time=timezone.make_aware(
                datetime.combine(slot_date, datetime.strptime('11:00', '%H:%M').time())
            ),
            session_type='OnlineMeeting',
            appointment_status='Scheduled',
            meeting_link='https://meet.example.com/abc123',
        )

        # Link appointment to slot
        self.appointment_slot2.is_booked = True
        self.appointment_slot2.save()
        self.appointment.appointment_slots.add(self.appointment_slot2)

        # Create tokens for authentication
        self.parent_token = Token.objects.create(user=self.parent_user)
        self.psychologist_token = Token.objects.create(user=self.psychologist_user)
        self.admin_token = Token.objects.create(user=self.admin_user)

        # Set up API client
        self.client = APIClient()

    def authenticate_parent(self):
        """Authenticate as parent"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

    def authenticate_psychologist(self):
        """Authenticate as psychologist"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

    def authenticate_admin(self):
        """Authenticate as admin"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')

    def test_list_appointments_as_parent(self):
        """Test listing appointments as a parent"""
        self.authenticate_parent()

        url = reverse('appointment-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['appointment_id'], str(self.appointment.appointment_id))

    def test_list_appointments_as_psychologist(self):
        """Test listing appointments as a psychologist"""
        self.authenticate_psychologist()

        url = reverse('appointment-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 1)

    def test_list_appointments_unauthenticated(self):
        """Test listing appointments without authentication"""
        url = reverse('appointment-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_appointment_as_parent(self):
        """Test retrieving specific appointment as parent"""
        self.authenticate_parent()

        url = reverse('appointment-detail', kwargs={'pk': self.appointment.appointment_id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['appointment_id'], str(self.appointment.appointment_id))
        self.assertEqual(response.data['child']['first_name'], 'Alice')

    def test_retrieve_appointment_as_psychologist(self):
        """Test retrieving specific appointment as psychologist"""
        self.authenticate_psychologist()

        url = reverse('appointment-detail', kwargs={'pk': self.appointment.appointment_id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['appointment_id'], str(self.appointment.appointment_id))

    def test_retrieve_appointment_unauthorized(self):
        """Test retrieving appointment by unauthorized user"""
        # Create another parent who shouldn't access this appointment
        other_parent_user = User.objects.create_user(
            email='other@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        other_token = Token.objects.create(user=other_parent_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {other_token.key}')

        url = reverse('appointment-detail', kwargs={'pk': self.appointment.appointment_id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('detail', response.data)  # Changed from 'error' to 'detail'
        self.assertIn('permission', response.data['detail'].lower())  # Optional: check message content

    @patch('appointments.services.AppointmentBookingService.book_appointment')
    def test_create_appointment_success(self, mock_book_appointment):
        """Test successful appointment creation"""
        self.authenticate_parent()

        # Mock the booking service to return our appointment
        mock_book_appointment.return_value = self.appointment

        data = {
            'child': str(self.child.id),
            'psychologist': str(self.psychologist.user.id),
            'session_type': 'OnlineMeeting',
            'start_slot_id': self.appointment_slot1.slot_id,  # Correct field name
            'parent_notes': 'Looking forward to the session'
        }

        url = reverse('appointment-list')
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('message', response.data)
        self.assertIn('appointment', response.data)

        # Verify the service was called with correct parameters
        mock_book_appointment.assert_called_once()
        args, kwargs = mock_book_appointment.call_args
        self.assertEqual(kwargs['parent'], self.parent)
        self.assertEqual(kwargs['child'], self.child)
        self.assertEqual(kwargs['session_type'], 'OnlineMeeting')

    @patch('appointments.services.AppointmentBookingService.book_appointment')
    def test_create_appointment_slot_not_available(self, mock_book_appointment):
        """Test appointment creation when slot is not available"""
        self.authenticate_parent()

        # Mock the service to raise SlotNotAvailableError
        mock_book_appointment.side_effect = SlotNotAvailableError("Selected slot is no longer available")

        data = {
            'child': str(self.child.id),
            'psychologist': str(self.psychologist.user.id),
            'session_type': 'OnlineMeeting',
            'start_slot_id': self.appointment_slot1.slot_id,  # Correct field name
            'parent_notes': 'Looking forward to the session'
        }

        url = reverse('appointment-list')
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    @patch('appointments.serializers.AppointmentSlot.find_consecutive_slots')
    def test_create_appointment_insufficient_slots(self, mock_find_consecutive):
        """Test appointment creation with insufficient consecutive slots"""
        self.authenticate_parent()

        # Mock to return insufficient slots
        mock_find_consecutive.return_value = [self.appointment_slot1]  # Only 1 slot instead of 2

        data = {
            'child': str(self.child.id),
            'psychologist': str(self.psychologist.user.id),
            'session_type': 'InitialConsultation',  # This requires 2 slots
            'start_slot_id': self.appointment_slot1.slot_id,
            'parent_notes': 'Looking forward to the session'
        }

        url = reverse('appointment-list')
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('start_slot_id', response.data)

    def test_create_appointment_invalid_data(self):
        """Test appointment creation with invalid data"""
        self.authenticate_parent()

        data = {
            'child': 'invalid-uuid',
            'psychologist': str(self.psychologist.user.id),
            'session_type': 'InvalidType'
        }

        url = reverse('appointment-list')
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_appointment_as_psychologist_forbidden(self):
        """Test that psychologists cannot create appointments"""
        self.authenticate_psychologist()

        data = {
            'child': str(self.child.id),
            'psychologist': str(self.psychologist.user.id),
            'session_type': 'OnlineMeeting',
            'start_slot_id': self.appointment_slot1.slot_id
        }

        url = reverse('appointment-list')
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_my_appointments_as_parent(self):
        """Test getting user's own appointments as parent"""
        self.authenticate_parent()

        url = reverse('appointment-my-appointments')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('count', response.data)
        self.assertIn('appointments', response.data)
        self.assertEqual(response.data['count'], 1)

    def test_my_appointments_with_status_filter(self):
        """Test getting appointments with status filter"""
        self.authenticate_parent()

        url = reverse('appointment-my-appointments')
        response = self.client.get(url, {'status': 'Scheduled'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_my_appointments_with_upcoming_filter(self):
        """Test getting upcoming appointments"""
        self.authenticate_parent()

        url = reverse('appointment-my-appointments')
        response = self.client.get(url, {'upcoming': 'true'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('appointments', response.data)

    def test_partial_update_appointment_as_parent(self):
        """Test updating appointment notes as parent"""
        self.authenticate_parent()

        data = {
            'parent_notes': 'Updated notes for the appointment'
        }

        url = reverse('appointment-detail', kwargs={'pk': self.appointment.appointment_id})
        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        self.assertIn('appointment', response.data)

    def test_partial_update_appointment_as_psychologist(self):
        """Test updating appointment as psychologist"""
        self.authenticate_psychologist()

        data = {
            'psychologist_notes_private': 'Private notes about the session'
        }

        url = reverse('appointment-detail', kwargs={'pk': self.appointment.appointment_id})
        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_partial_update_completed_appointment_invalid(self):
        """Test updating completed appointment should fail for certain fields"""
        self.authenticate_parent()

        # Mark appointment as completed
        self.appointment.appointment_status = 'Completed'
        self.appointment.save()

        data = {
            'cancellation_reason': 'Should not be allowed'
        }

        url = reverse('appointment-detail', kwargs={'pk': self.appointment.appointment_id})
        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('appointments.services.AppointmentManagementService.cancel_appointment')
    def test_cancel_appointment_as_parent(self, mock_cancel):
        """Test cancelling appointment as parent"""
        self.authenticate_parent()

        # Mock the cancellation service
        cancelled_appointment = self.appointment
        cancelled_appointment.appointment_status = 'CancelledByParent'
        mock_cancel.return_value = cancelled_appointment

        data = {
            'cancellation_reason': 'Family emergency'
        }

        url = reverse('appointment-cancel', kwargs={'pk': self.appointment.appointment_id})
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        self.assertIn('refund_info', response.data)

        # Verify the service was called
        mock_cancel.assert_called_once()

    @patch('appointments.services.AppointmentManagementService.cancel_appointment')
    def test_cancel_appointment_as_psychologist(self, mock_cancel):
        """Test cancelling appointment as psychologist"""
        self.authenticate_psychologist()

        cancelled_appointment = self.appointment
        cancelled_appointment.appointment_status = 'CancelledByPsychologist'
        mock_cancel.return_value = cancelled_appointment

        data = {
            'cancellation_reason': 'Emergency scheduling conflict'
        }

        url = reverse('appointment-cancel', kwargs={'pk': self.appointment.appointment_id})
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('appointments.services.AppointmentManagementService.cancel_appointment')
    def test_cancel_appointment_error(self, mock_cancel):
        """Test appointment cancellation with error"""
        self.authenticate_parent()

        # Mock the service to raise an error
        mock_cancel.side_effect = AppointmentCancellationError("Cannot cancel appointment less than 24 hours before")

        data = {
            'cancellation_reason': 'Changed my mind'
        }

        url = reverse('appointment-cancel', kwargs={'pk': self.appointment.appointment_id})
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_cancel_appointment_unauthorized(self):
        """Test cancelling appointment by unauthorized user"""
        # Create another parent user with proper profile
        other_parent_user = User.objects.create_user(
            email='other@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True,
            is_active=True  # Add this for consistency
        )

        # Create parent profile (your signals should handle this, but let's be explicit)
        other_parent = Parent.objects.get(user=other_parent_user)

        other_token = Token.objects.create(user=other_parent_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {other_token.key}')

        data = {
            'cancellation_reason': 'Should not be allowed'
        }
        url = reverse('appointment-cancel', kwargs={'pk': self.appointment.appointment_id})
        response = self.client.post(url, data, format='json')

        # Debug output for troubleshooting
        if response.status_code != status.HTTP_403_FORBIDDEN:
            print(f"Unexpected status code: {response.status_code}")
            print(f"Response content: {response.content}")
            if hasattr(response, 'data'):
                print(f"Response data: {response.data}")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_verify_qr_code_success(self):
        """Test successful QR code verification"""
        self.authenticate_parent()

        # Set up the appointment to be verifiable
        self.appointment.qr_verification_code = 'QR12345'
        self.appointment.session_type = 'InitialConsultation'
        self.appointment.appointment_status = 'Scheduled'
        self.appointment.meeting_link = None
        # Set appointment time to be within verification window
        self.appointment.scheduled_start_time = timezone.now() + timedelta(minutes=10)
        self.appointment.scheduled_end_time = self.appointment.scheduled_start_time + timedelta(hours=2)
        self.appointment.save()

        data = {
            'qr_code': 'QR12345'
        }

        url = reverse('appointment-verify-qr')
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        self.assertIn('appointment', response.data)

        # Verify the appointment was actually updated
        self.appointment.refresh_from_db()
        self.assertIsNotNone(self.appointment.session_verified_at)

    @patch('appointments.services.AppointmentManagementService.verify_qr_code')
    def test_verify_qr_code_invalid(self, mock_verify):
        """Test QR code verification with invalid code"""
        self.authenticate_parent()

        # Mock the service to raise error
        mock_verify.side_effect = QRVerificationError("Invalid QR code")

        data = {
            'qr_code': 'INVALID123'
        }

        url = reverse('appointment-verify-qr')
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_search_appointments(self):
        """Test searching appointments with filters"""
        self.authenticate_parent()

        data = {
            'appointment_status': 'Scheduled',
            'session_type': 'OnlineMeeting',
            'date_from': (date.today() - timedelta(days=1)).isoformat(),
            'date_to': (date.today() + timedelta(days=7)).isoformat()
        }

        url = reverse('appointment-search')
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('count', response.data)
        self.assertIn('results', response.data)
        self.assertIn('search_params', response.data)

    def test_search_appointments_invalid_data(self):
        """Test searching appointments with invalid data"""
        self.authenticate_parent()

        data = {
            'date_from': 'invalid-date',
            'session_type': 'InvalidType'
        }

        url = reverse('appointment-search')
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('appointments.services.AppointmentBookingService.get_available_booking_slots')
    def test_available_slots(self, mock_get_slots):
        """Test getting available appointment slots"""
        self.authenticate_parent()

        # Mock the service response
        mock_slots_data = {
            'psychologist_name': 'Dr. Jane Smith',
            'session_type': 'OnlineMeeting',
            'total_slots': 10,
            'available_slots': [
                {
                    'slot_id': self.appointment_slot1.slot_id,
                    'date': '2024-01-15',
                    'start_time': '09:00',
                    'end_time': '10:00',
                    'session_types': ['OnlineMeeting']
                }
            ]
        }
        mock_get_slots.return_value = mock_slots_data

        url = reverse('appointment-available-slots')
        response = self.client.get(url, {
            'psychologist_id': str(self.psychologist.user.id),
            'session_type': 'OnlineMeeting',
            'date_from': date.today().isoformat(),
            'date_to': (date.today() + timedelta(days=7)).isoformat()
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['psychologist_name'], 'Dr. Jane Smith')
        self.assertEqual(response.data['total_slots'], 10)

    def test_available_slots_missing_parameters(self):
        """Test getting available slots with missing required parameters"""
        self.authenticate_parent()

        url = reverse('appointment-available-slots')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_available_slots_invalid_session_type(self):
        """Test getting available slots with invalid session type"""
        self.authenticate_parent()

        url = reverse('appointment-available-slots')
        response = self.client.get(url, {
            'psychologist_id': str(self.psychologist.user.id),
            'session_type': 'InvalidType'
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_available_slots_psychologist_not_found(self):
        """Test getting available slots for non-existent psychologist"""
        self.authenticate_parent()

        url = reverse('appointment-available-slots')
        response = self.client.get(url, {
            'psychologist_id': str(uuid.uuid4()),
            'session_type': 'OnlineMeeting'
        })

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch('appointments.services.AppointmentManagementService.complete_appointment')
    def test_complete_appointment_as_psychologist(self, mock_complete):
        """Test completing appointment as psychologist"""
        self.authenticate_psychologist()

        # Mock the completion service
        completed_appointment = self.appointment
        completed_appointment.appointment_status = 'Completed'
        completed_appointment.actual_end_time = timezone.now()
        mock_complete.return_value = completed_appointment

        data = {
            'psychologist_notes': 'Session completed successfully'
        }

        url = reverse('appointment-complete', kwargs={'pk': self.appointment.appointment_id})
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        self.assertIn('appointment', response.data)

    def test_complete_appointment_as_parent_forbidden(self):
        """Test that parents cannot complete appointments"""
        self.authenticate_parent()

        data = {
            'psychologist_notes': 'Should not be allowed'
        }

        url = reverse('appointment-complete', kwargs={'pk': self.appointment.appointment_id})
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_upcoming_appointments(self):
        """Test getting upcoming appointments"""
        self.authenticate_parent()

        url = reverse('appointment-upcoming')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('count', response.data)
        self.assertIn('next_appointment', response.data)
        self.assertIn('appointments', response.data)

    def test_appointment_history(self):
        """Test getting appointment history"""
        self.authenticate_parent()

        # Create a past appointment
        past_date = date.today() - timedelta(days=7)
        past_appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            scheduled_start_time=timezone.make_aware(
                datetime.combine(past_date, datetime.strptime('10:00', '%H:%M').time())
            ),
            scheduled_end_time=timezone.make_aware(
                datetime.combine(past_date, datetime.strptime('11:00', '%H:%M').time())
            ),
            session_type='OnlineMeeting',
            appointment_status='Completed'
        )

        url = reverse('appointment-history')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('count', response.data)
        self.assertIn('appointments', response.data)

    def test_appointment_permissions_isolation(self):
        """Test that users can only see their own appointments"""
        # Create another parent with appointment
        other_parent_user = User.objects.create_user(
            email='other@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        other_parent = Parent.objects.get(user=other_parent_user)
        other_child = Child.objects.create(
            parent=other_parent,
            first_name='Other',
            last_name='Child',
            date_of_birth=date.today() - timedelta(days=2555)
        )
        start_time = timezone.now() + timedelta(days=1)
        other_appointment = Appointment.objects.create(
            child=other_child,
            psychologist=self.psychologist,
            parent=other_parent,
            scheduled_start_time=start_time,
            scheduled_end_time=start_time + timedelta(hours=1),
            session_type='OnlineMeeting',
            appointment_status='Scheduled'
        )

        # Authenticate as original parent
        self.authenticate_parent()

        # Should only see own appointments
        url = reverse('appointment-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        appointment_ids = [apt['appointment_id'] for apt in response.data['results']]
        self.assertIn(str(self.appointment.appointment_id), appointment_ids)
        self.assertNotIn(str(other_appointment.appointment_id), appointment_ids)

    def test_admin_can_see_all_appointments(self):
        """Test that admin users can see all appointments"""
        self.authenticate_admin()

        url = reverse('appointment-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Admin should see at least our test appointment
        self.assertGreaterEqual(len(response.data['results']), 1)

    def tearDown(self):
        """Clean up after tests"""
        # Clear any authentication
        self.client.credentials()

        # Django will handle database cleanup in test database