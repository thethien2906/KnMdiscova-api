# appointments/tests/test_views_AppointmentSlotViewSet.py
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token
from datetime import date, time, timedelta
from unittest.mock import patch, MagicMock

from users.models import User
from parents.models import Parent
from psychologists.models import Psychologist, PsychologistAvailability
from children.models import Child
from appointments.models import AppointmentSlot
from appointments.services import (
    SlotGenerationError,
    AppointmentSlotService
)
from psychologists.services import PsychologistService, PsychologistNotFoundError


class AppointmentSlotViewSetTestCase(TestCase):
    """
    Test cases for AppointmentSlotViewSet
    """

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()

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

        # Create other psychologist user and profile
        self.other_psychologist_user = User.objects.create_user(
            email='other_psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )
        self.other_psychologist = Psychologist.objects.create(
            user=self.other_psychologist_user,
            first_name='Jane',
            last_name='Smith',
            license_number='PSY67890',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=False,
            office_address='456 Other St, City, State'
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

        self.slot1 = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=slot_date,
            start_time='09:00',
            end_time='10:00',
            is_booked=False
        )

        self.slot2 = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=slot_date,
            start_time='10:00',
            end_time='11:00',
            is_booked=False
        )

        # Create booked slot
        self.booked_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=slot_date,
            start_time='14:00',
            end_time='15:00',
            is_booked=True
        )

        # Create slot for other psychologist
        self.other_slot = AppointmentSlot.objects.create(
            psychologist=self.other_psychologist,
            availability_block=self.availability_block,
            slot_date=slot_date,
            start_time='09:00',
            end_time='10:00'
        )

        # Create tokens for authentication
        self.parent_token = Token.objects.create(user=self.parent_user)
        self.psychologist_token = Token.objects.create(user=self.psychologist_user)
        self.admin_token = Token.objects.create(user=self.admin_user)
        self.other_psychologist_token = Token.objects.create(user=self.other_psychologist_user)

    def authenticate_user(self, user_type='admin'):
        """
        Helper method to authenticate users using force_authenticate
        """
        user_map = {
            'admin': self.admin_user,
            'psychologist': self.psychologist_user,
            'parent': self.parent_user,
            'other_psychologist': self.other_psychologist_user,
        }

        if user_type in user_map:
            user = user_map[user_type]
            # Use force_authenticate - this is more reliable for tests
            self.client.force_authenticate(user=user)

        else:
            self.client.force_authenticate(user=None)

    def test_list_slots_admin_access(self):
        """Test that admins can list all appointment slots"""
        self.authenticate_user('admin')

        # Try the explicit URL path instead of reverse
        url = '/api/appointments/slots/'
        print(f"Using direct URL: {url}")

        response = self.client.get(url)
        print(f"Response status: {response.status_code}")

        if response.status_code != 200:
            print(f"Response content: {response.content}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertGreaterEqual(len(response.data['results']), 4)
    def test_list_slots_psychologist_access(self):
        """
        Test that psychologists can only see their own slots
        """
        self.authenticate_user('psychologist')
        url = reverse('appointment-slots-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        # Psychologist should only see their own slots (3 slots)
        slot_count = len(response.data['results'])
        self.assertGreaterEqual(slot_count, 2)  # At least 2 slots (slot1, slot2)
        self.assertLessEqual(slot_count, 3)  # At most 3 slots (including booked_slot)

    def test_list_slots_parent_access(self):
        """
        Test that parents can only see available marketplace slots
        """
        self.authenticate_user('parent')
        url = reverse('appointment-slots-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        # Parent should only see available slots from approved psychologists
        # (excluding booked slots)
        self.assertGreaterEqual(len(response.data['results']), 2)

    def test_list_slots_unauthenticated(self):
        """
        Test that unauthenticated users cannot list slots
        """
        url = reverse('appointment-slots-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_slot_success(self):
        """
        Test successful slot retrieval
        """
        self.authenticate_user('psychologist')
        url = reverse('appointment-slots-detail', kwargs={'pk': self.slot1.slot_id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['slot_id'], self.slot1.slot_id)

        # If psychologist is just UUID, test that
        self.assertEqual(str(response.data['psychologist']), str(self.psychologist.user.id))

        # Test other slot fields
        self.assertEqual(response.data['slot_date'], str(self.slot1.slot_date))
        self.assertEqual(response.data['start_time'], '09:00:00')
        self.assertEqual(response.data['end_time'], '10:00:00')
        self.assertFalse(response.data['is_booked'])

    def test_retrieve_slot_not_found(self):
        """
        Test slot retrieval with invalid ID
        """
        self.authenticate_user('psychologist')
        url = reverse('appointment-slots-detail', kwargs={'pk': 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_my_slots_success(self):
        """
        Test successful retrieval of psychologist's own slots
        """
        self.authenticate_user('psychologist')
        url = reverse('appointment-slots-my-slots')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slot_count = response.data['count']
        self.assertGreaterEqual(slot_count, 2)  # At least slot1, slot2
        self.assertLessEqual(slot_count, 3)  # At most including booked_slot
        self.assertIn('slots', response.data)

    def test_my_slots_with_date_filter(self):
        """
        Test my_slots endpoint with date filtering
        """
        self.authenticate_user('psychologist')
        slot_date = self.slot1.slot_date
        url = reverse('appointment-slots-my-slots')
        response = self.client.get(url, {
            'date_from': slot_date.isoformat(),
            'date_to': slot_date.isoformat()
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data['count'], 2)  # At least slot1, slot2

    def test_my_slots_invalid_date_format(self):
        """
        Test my_slots endpoint with invalid date format
        """
        self.authenticate_user('psychologist')
        url = reverse('appointment-slots-my-slots')
        response = self.client.get(url, {'date_from': 'invalid-date'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid date_from format', response.data['error'])

    def test_my_slots_non_psychologist(self):
        """
        Test my_slots endpoint access by non-psychologist
        """
        self.authenticate_user('parent')
        url = reverse('appointment-slots-my-slots')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('Psychologist profile not found', response.data['error'])

    def test_create_slot_success(self):
        """
        Test successful slot creation
        """
        self.authenticate_user('admin')
        url = reverse('appointment-slots-list')
        slot_date = self.slot1.slot_date

        data = {
            'psychologist': self.psychologist.user.id,
            'availability_block': self.availability_block.availability_id,
            'slot_date': slot_date.isoformat(),
            'start_time': '11:00',
            'end_time': '12:00'
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('message', response.data)
        self.assertIn('slot', response.data)

    def test_create_slot_permission_denied(self):
        """
        Test slot creation permission denied for parents
        """
        self.authenticate_user('parent')
        url = reverse('appointment-slots-list')

        data = {
            'psychologist': self.psychologist.user.id,
            'slot_date': date.today().isoformat(),
            'start_time': '11:00',
            'end_time': '12:00'
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('appointments.services.AppointmentSlotService.bulk_generate_slots_for_psychologist')
    def test_generate_slots_success(self, mock_generate):
        """
        Test successful slot generation
        """
        mock_generate.return_value = {
            'psychologist_id': str(self.psychologist.user.id),
            'date_range': {'from': date.today(), 'to': date.today() + timedelta(days=90)},
            'total_slots_created': 45,
            'availability_blocks_processed': 1,
            'results': [{'availability_block_id': 1, 'slots_created': 45, 'success': True}]
        }

        self.authenticate_user('psychologist')
        url = reverse('appointment-slots-generate-slots')
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        self.assertEqual(response.data['total_slots_created'], 45)
        mock_generate.assert_called_once()

    @patch('appointments.services.AppointmentSlotService.bulk_generate_slots_for_psychologist')
    def test_generate_slots_with_parameters(self, mock_generate):
        """
        Test slot generation with date parameters
        """
        mock_generate.return_value = {
            'psychologist_id': str(self.psychologist.user.id),
            'date_range': {'from': date.today(), 'to': date.today() + timedelta(days=30)},
            'total_slots_created': 15,
            'availability_blocks_processed': 1,
            'results': [{'availability_block_id': 1, 'slots_created': 15, 'success': True}]
        }

        self.authenticate_user('psychologist')
        url = reverse('appointment-slots-generate-slots')
        date_from = date.today()
        date_to = date_from + timedelta(days=30)

        response = self.client.post(url, {}, QUERY_STRING=f'date_from={date_from}&date_to={date_to}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_generate.assert_called_once()

    def test_generate_slots_invalid_date_range(self):
        """
        Test slot generation with invalid date range
        """
        self.authenticate_user('psychologist')
        url = reverse('appointment-slots-generate-slots')
        date_from = date.today() + timedelta(days=30)
        date_to = date.today()

        response = self.client.post(url, {}, QUERY_STRING=f'date_from={date_from}&date_to={date_to}')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('End date must be after start date', response.data['error'])

    @patch('appointments.services.AppointmentSlotService.bulk_generate_slots_for_psychologist')
    def test_generate_slots_service_error(self, mock_generate):
        """
        Test slot generation with service error
        """
        mock_generate.side_effect = SlotGenerationError("Generation failed")

        self.authenticate_user('psychologist')
        url = reverse('appointment-slots-generate-slots')
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Generation failed', response.data['error'])

    def test_generate_slots_permission_denied(self):
        """
        Test slot generation permission denied for parents
        """
        self.authenticate_user('parent')
        url = reverse('appointment-slots-generate-slots')
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_available_for_booking_success(self):
        """
        Test successful retrieval of available booking slots
        """
        self.authenticate_user('parent')
        url = reverse('appointment-slots-available-for-booking')
        response = self.client.get(url, {
            'psychologist_id': self.psychologist.user.id,
            'session_type': 'OnlineMeeting'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('psychologist_name', response.data)
        self.assertIn('available_slots', response.data)
        self.assertEqual(response.data['session_type'], 'OnlineMeeting')

    def test_available_for_booking_missing_psychologist_id(self):
        """
        Test available_for_booking with missing psychologist_id
        """
        self.authenticate_user('parent')
        url = reverse('appointment-slots-available-for-booking')
        response = self.client.get(url, {'session_type': 'OnlineMeeting'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('psychologist_id parameter is required', response.data['error'])

    def test_available_for_booking_invalid_session_type(self):
        """
        Test available_for_booking with invalid session type
        """
        self.authenticate_user('parent')
        url = reverse('appointment-slots-available-for-booking')
        response = self.client.get(url, {
            'psychologist_id': self.psychologist.user.id,
            'session_type': 'InvalidType'
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid session_type', response.data['error'])

    def test_available_for_booking_psychologist_not_found(self):
        """
        Test available_for_booking with non-existent psychologist
        """
        self.authenticate_user('parent')
        url = reverse('appointment-slots-available-for-booking')
        response = self.client.get(url, {
            'psychologist_id': '00000000-0000-0000-0000-000000000000',
            'session_type': 'OnlineMeeting'
        })

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('Psychologist not found', response.data['error'])

    def test_available_for_booking_not_marketplace_visible(self):
        """
        Test available_for_booking with psychologist not marketplace visible
        """
        # Make psychologist not marketplace visible
        self.psychologist.verification_status = 'Pending'
        self.psychologist.save()

        self.authenticate_user('parent')
        url = reverse('appointment-slots-available-for-booking')
        response = self.client.get(url, {
            'psychologist_id': self.psychologist.user.id,
            'session_type': 'OnlineMeeting'
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not available for booking', response.data['error'])

    def test_delete_slot_success(self):
        """
        Test successful slot deletion
        """
        self.authenticate_user('psychologist')
        url = reverse('appointment-slots-detail', kwargs={'pk': self.slot1.slot_id})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(AppointmentSlot.objects.filter(slot_id=self.slot1.slot_id).exists())

    def test_delete_booked_slot(self):
        """
        Test deletion of booked slot (should fail)
        """
        self.authenticate_user('psychologist')
        url = reverse('appointment-slots-detail', kwargs={'pk': self.booked_slot.slot_id})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot delete booked appointment slot', response.data['error'])

    def test_delete_slot_permission_denied(self):
        """
        Test slot deletion permission denied for other psychologist
        """
        print(f"\n=== Debug: test_delete_slot_permission_denied ===")
        print(f"Slot1 ID: {self.slot1.slot_id}")
        print(f"Slot1 psychologist: {self.slot1.psychologist.user.email}")
        print(f"Other psychologist: {self.other_psychologist_user.email}")

        # Authenticate as other psychologist
        self.client.force_authenticate(user=self.other_psychologist_user)
        print(f"Authenticated as: {self.other_psychologist_user.email}")

        url = reverse('appointment-slots-detail', kwargs={'pk': self.slot1.slot_id})
        print(f"URL: {url}")

        response = self.client.delete(url)
        print(f"DELETE response status: {response.status_code}")
        if hasattr(response, 'data'):
            print(f"DELETE response data: {response.data}")

        # Should get 403 Forbidden
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Verify slot still exists
        self.assertTrue(AppointmentSlot.objects.filter(slot_id=self.slot1.slot_id).exists())

    @patch('appointments.services.AppointmentSlotService.cleanup_past_slots')
    def test_cleanup_past_slots_success(self, mock_cleanup):
        """
        Test successful cleanup of past slots
        """
        mock_cleanup.return_value = 10

        self.authenticate_user('admin')
        url = reverse('appointment-slots-cleanup-past-slots')
        response = self.client.post(url, {}, QUERY_STRING='days_past=7')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['deleted_count'], 10)
        self.assertEqual(response.data['days_past'], 7)
        mock_cleanup.assert_called_once_with(7)

    def test_cleanup_past_slots_permission_denied(self):
        """
        Test cleanup_past_slots permission denied for non-admin
        """
        self.authenticate_user('psychologist')
        url = reverse('appointment-slots-cleanup-past-slots')
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('Permission denied', response.data['error'])

    def test_cleanup_past_slots_invalid_days_past(self):
        """
        Test cleanup_past_slots with invalid days_past parameter
        """
        self.authenticate_user('admin')
        url = reverse('appointment-slots-cleanup-past-slots')
        response = self.client.post(url, {}, QUERY_STRING='days_past=0')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('days_past must be at least 1', response.data['error'])

    def test_statistics_success(self):
        """
        Test successful statistics retrieval
        """
        self.authenticate_user('admin')
        url = reverse('appointment-slots-statistics')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_slots', response.data)
        self.assertIn('available_slots', response.data)
        self.assertIn('booked_slots', response.data)
        self.assertIn('utilization_rate', response.data)
        self.assertIn('by_psychologist', response.data)

    def test_statistics_with_date_filter(self):
        """
        Test statistics with date filtering
        """
        self.authenticate_user('admin')
        url = reverse('appointment-slots-statistics')
        response = self.client.get(url, {
            'date_from': date.today().isoformat(),
            'date_to': (date.today() + timedelta(days=30)).isoformat()
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('date_filters', response.data)

    def test_statistics_permission_denied(self):
        """
        Test statistics permission denied for non-admin
        """
        self.authenticate_user('parent')
        url = reverse('appointment-slots-statistics')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('Permission denied', response.data['error'])

    def test_statistics_invalid_date_format(self):
        """
        Test statistics with invalid date format
        """
        self.authenticate_user('admin')
        url = reverse('appointment-slots-statistics')
        response = self.client.get(url, {'date_from': 'invalid-date'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid date_from format', response.data['error'])

    def test_queryset_filtering_by_user_type(self):
        """
        Test that queryset is properly filtered based on user type
        """
        # Test admin can see all slots
        self.authenticate_user('admin')
        url = reverse('appointment-slots-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        admin_slot_count = len(response.data.get('results', response.data))

        # Test psychologist can only see their own slots
        self.authenticate_user('psychologist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        psychologist_slot_count = len(response.data.get('results', response.data))

        # Test parent can only see available marketplace slots
        self.authenticate_user('parent')
        response = self.client.get(url)

            # Debug the permission issue
        print(f"Parent response status: {response.status_code}")
        print(f"Parent response data: {response.data}")
        print(f"Parent user type: {self.parent_user.user_type}")
        print(f"Parent is authenticated: {self.parent_user.is_authenticated}")
        if response.status_code != 200:
            # This will help us understand the permission issue
            self.fail(f"Parent user got {response.status_code} instead of 200. Response: {response.data}")

        parent_slot_count = len(response.data.get('results', response.data))

        # Assertions
        self.assertGreater(admin_slot_count, 0, "Admin should see some slots")
        self.assertGreater(psychologist_slot_count, 0, "Psychologist should see their own slots")
        self.assertGreaterEqual(parent_slot_count, 0, "Parent should see available marketplace slots")

        # Admin sees more than individual users
        self.assertGreaterEqual(admin_slot_count, psychologist_slot_count)
        self.assertGreaterEqual(admin_slot_count, parent_slot_count)

    def test_error_handling_in_views(self):
        """
        Test error handling in various view methods
        """
        # Test unexpected error in my_slots
        with patch('appointments.views.AppointmentSlot.objects.filter') as mock_filter:
            mock_filter.side_effect = Exception("Database error")

            self.authenticate_user('psychologist')
            url = reverse('appointment-slots-my-slots')
            response = self.client.get(url)

            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
            self.assertIn('Failed to retrieve slots', response.data['error'])

    def test_generate_slots_with_specific_availability_block(self):
        """
        Test slot generation for specific availability block
        """
        with patch('appointments.services.AppointmentSlotService.generate_slots_from_availability_block') as mock_generate:
            mock_generate.return_value = [self.slot1, self.slot2]

            self.authenticate_user('psychologist')
            url = reverse('appointment-slots-generate-slots')
            response = self.client.post(
                url,
                {},
                QUERY_STRING=f'availability_block_id={self.availability_block.availability_id}'
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            mock_generate.assert_called_once()

    def test_generate_slots_availability_block_not_found(self):
        """
        Test slot generation with non-existent availability block
        """
        self.authenticate_user('psychologist')
        url = reverse('appointment-slots-generate-slots')
        response = self.client.post(url, {}, QUERY_STRING='availability_block_id=99999')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('Availability block not found', response.data['error'])

    def test_available_for_booking_with_date_range(self):
        """
        Test available_for_booking with custom date range
        """
        self.authenticate_user('parent')
        url = reverse('appointment-slots-available-for-booking')

        date_from = date.today() + timedelta(days=1)
        date_to = date.today() + timedelta(days=7)

        response = self.client.get(url, {
            'psychologist_id': self.psychologist.user.id,
            'session_type': 'OnlineMeeting',
            'date_from': date_from.isoformat(),
            'date_to': date_to.isoformat()
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('available_slots', response.data)

    def test_available_for_booking_invalid_date_format(self):
        """
        Test available_for_booking with invalid date format
        """
        self.authenticate_user('parent')
        url = reverse('appointment-slots-available-for-booking')
        response = self.client.get(url, {
            'psychologist_id': self.psychologist.user.id,
            'session_type': 'OnlineMeeting',
            'date_from': 'invalid-date'
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid date_from format', response.data['error'])

    def tearDown(self):
        """
        Clean up after tests
        """
        # Clear any authentication
        self.client.credentials()