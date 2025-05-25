# parents/tests/test_views.py
import json
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token
from unittest.mock import patch, MagicMock

from users.models import User
from parents.models import Parent
from parents.services import ParentService, ParentProfileError, ParentNotFoundError

User = get_user_model()


class ParentProfileViewSetTestCase(APITestCase):
    """Test cases for ParentProfileViewSet"""

    def setUp(self):
        """Set up test data"""
        # Create parent user and profile (profile created via signal)
        self.parent_user = User.objects.create_parent(
            email='parent@test.com',
            password='testpass123',
            user_timezone='UTC'
        )
        self.parent_user.is_verified = True
        self.parent_user.save()

        # Get the automatically created parent profile
        self.parent_profile = Parent.objects.get(user=self.parent_user)

        # Update parent profile with test data
        self.parent_profile.first_name = 'John'
        self.parent_profile.last_name = 'Doe'
        self.parent_profile.phone_number = '+1234567890'
        self.parent_profile.city = 'Test City'
        self.parent_profile.save()

        # Create parent token for authentication
        self.parent_token = Token.objects.create(user=self.parent_user)

        # Create psychologist user for permission tests
        self.psychologist_user = User.objects.create_psychologist(
            email='psychologist@test.com',
            password='testpass123'
        )
        self.psychologist_token = Token.objects.create(user=self.psychologist_user)

        # Create admin user for permission tests
        self.admin_user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123'
        )
        self.admin_token = Token.objects.create(user=self.admin_user)

        self.client = APIClient()

    def authenticate_as_parent(self):
        """Helper method to authenticate as parent"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

    def authenticate_as_psychologist(self):
        """Helper method to authenticate as psychologist"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

    def authenticate_as_admin(self):
        """Helper method to authenticate as admin"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')

    def test_get_profile_success(self):
        """Test successful profile retrieval"""
        self.authenticate_as_parent()
        url = reverse('parent-profile-profile')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Check expected fields are present
        self.assertEqual(data['email'], self.parent_user.email)
        self.assertEqual(data['first_name'], 'John')
        self.assertEqual(data['last_name'], 'Doe')
        self.assertEqual(data['full_name'], 'John Doe')
        self.assertEqual(data['phone_number'], '+1234567890')
        self.assertIn('profile_completeness', data)
        self.assertIn('communication_preferences', data)

    def test_get_profile_unauthenticated(self):
        """Test profile retrieval without authentication"""
        url = reverse('parent-profile-profile')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_profile_non_parent_user(self):
        """Test profile retrieval by non-parent user"""
        self.authenticate_as_psychologist()
        url = reverse('parent-profile-profile')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('parents.views.ParentService.get_parent_by_user_or_raise')
    def test_get_profile_parent_not_found(self, mock_get_parent):
        """Test profile retrieval when parent profile doesn't exist"""
        mock_get_parent.side_effect = ParentNotFoundError("Parent profile not found")

        self.authenticate_as_parent()
        url = reverse('parent-profile-profile')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error', response.json())

    def test_update_profile_success(self):
        """Test successful profile update"""
        self.authenticate_as_parent()
        url = reverse('parent-profile-update-profile')

        update_data = {
            'first_name': 'Jane',
            'last_name': 'Smith',
            'phone_number': '+9876543210',
            'city': 'New City',
            'state_province': 'New State'
        }

        response = self.client.patch(url, update_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertIn('message', data)
        self.assertIn('profile', data)

        # Verify data was updated
        self.parent_profile.refresh_from_db()
        self.assertEqual(self.parent_profile.first_name, 'Jane')
        self.assertEqual(self.parent_profile.last_name, 'Smith')
        self.assertEqual(self.parent_profile.city, 'New City')

    def test_update_profile_unverified_user(self):
        """Test profile update with unverified user"""
        self.parent_user.is_verified = False
        self.parent_user.save()

        self.authenticate_as_parent()
        url = reverse('parent-profile-update-profile')

        update_data = {'first_name': 'Jane'}

        response = self.client.patch(url, update_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('Email must be verified', response.json()['error'])

    def test_update_profile_invalid_phone(self):
        """Test profile update with invalid phone number"""
        self.authenticate_as_parent()
        url = reverse('parent-profile-update-profile')

        update_data = {
            'phone_number': 'invalid-phone'
        }

        response = self.client.patch(url, update_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('phone_number', response.json())

    @patch('parents.views.ParentService.update_parent_profile')
    def test_update_profile_service_error(self, mock_update):
        """Test profile update when service raises error"""
        mock_update.side_effect = ParentProfileError("Update failed")

        self.authenticate_as_parent()
        url = reverse('parent-profile-update-profile')

        update_data = {'first_name': 'Jane'}

        response = self.client.patch(url, update_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())

    def test_get_completeness(self):
        """Test profile completeness calculation"""
        self.authenticate_as_parent()
        url = reverse('parent-profile-completeness')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Check expected fields
        self.assertIn('overall_score', data)
        self.assertIn('required_score', data)
        self.assertIn('optional_score', data)
        self.assertIn('is_complete', data)
        self.assertIn('missing_required_fields', data)
        self.assertIn('missing_optional_fields', data)

    def test_get_communication_preferences(self):
        """Test retrieving communication preferences"""
        self.authenticate_as_parent()
        # The URL path in the view uses 'communication-preferences' with hyphens
        url = '/api/parents/profile/communication-preferences/'

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Check default preferences are present
        self.assertIn('email_notifications', data)
        self.assertIn('sms_notifications', data)
        self.assertIn('appointment_reminders', data)
        self.assertIn('reminder_timing', data)

    def test_update_communication_preferences_success(self):
        """Test successful communication preferences update"""
        self.authenticate_as_parent()
        # The URL path in the view uses 'communication-preferences' with hyphens
        url = '/api/parents/profile/communication-preferences/'

        update_data = {
            'email_notifications': False,
            'sms_notifications': True,
            'reminder_timing': '2_hours'
        }

        response = self.client.patch(url, update_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertIn('message', data)
        self.assertIn('preferences', data)

        # Verify preferences were updated
        self.parent_profile.refresh_from_db()
        prefs = self.parent_profile.communication_preferences
        self.assertEqual(prefs['email_notifications'], False)
        self.assertEqual(prefs['sms_notifications'], True)
        self.assertEqual(prefs['reminder_timing'], '2_hours')

    def test_update_communication_preferences_invalid_timing(self):
        """Test that updating communication preferences with an invalid timing value returns 400"""

        # Authenticate as a parent user (your custom method)
        self.authenticate_as_parent()

        # Use reverse() to future-proof the URL
        url = reverse('parent-profile-communication-preferences')

        # Invalid timing value (should trigger validation error in serializer)
        update_data = {
            'reminder_timing': 'invalid_timing'  # Expecting e.g. '1_hour_before', '30_minutes_before', etc.
        }

        response = self.client.patch(url, update_data, format='json')

        # Ensure a 400 BAD REQUEST is returned
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Optional: Assert specific error message if your serializer defines it
        self.assertIn('reminder_timing', response.data)

    def test_reset_communication_preferences(self):
        """Test resetting communication preferences to defaults"""
        # First update preferences
        self.parent_profile.communication_preferences = {
            'email_notifications': False,
            'sms_notifications': True
        }
        self.parent_profile.save()

        self.authenticate_as_parent()
        # The URL path in the view uses 'communication-preferences/reset' with hyphens
        url = '/api/parents/profile/communication-preferences/reset/'

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertIn('message', data)
        self.assertIn('preferences', data)

        # Verify preferences were reset to defaults
        self.parent_profile.refresh_from_db()
        defaults = Parent.get_default_communication_preferences()
        self.assertEqual(self.parent_profile.communication_preferences, defaults)

    @patch('parents.views.ParentService.reset_communication_preferences_to_default')
    def test_reset_communication_preferences_service_error(self, mock_reset):
        """Test reset preferences when service raises error"""
        mock_reset.side_effect = ParentProfileError("Reset failed")

        self.authenticate_as_parent()
        # The URL path in the view uses 'communication-preferences/reset' with hyphens
        url = '/api/parents/profile/communication-preferences/reset/'

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())


class ParentManagementViewSetTestCase(APITestCase):
    """Test cases for ParentManagementViewSet"""

    def setUp(self):
        """Set up test data"""
        # Create multiple parent users
        self.parent1_user = User.objects.create_parent(
            email='parent1@test.com',
            password='testpass123'
        )
        self.parent1_profile = Parent.objects.get(user=self.parent1_user)
        self.parent1_profile.first_name = 'John'
        self.parent1_profile.last_name = 'Doe'
        self.parent1_profile.city = 'City1'
        self.parent1_profile.save()

        self.parent2_user = User.objects.create_parent(
            email='parent2@test.com',
            password='testpass123'
        )
        self.parent2_profile = Parent.objects.get(user=self.parent2_user)
        self.parent2_profile.first_name = 'Jane'
        self.parent2_profile.last_name = 'Smith'
        self.parent2_profile.city = 'City2'
        self.parent2_profile.save()

        # Create tokens
        self.parent1_token = Token.objects.create(user=self.parent1_user)
        self.parent2_token = Token.objects.create(user=self.parent2_user)

        # Create psychologist user
        self.psychologist_user = User.objects.create_psychologist(
            email='psychologist@test.com',
            password='testpass123'
        )
        self.psychologist_token = Token.objects.create(user=self.psychologist_user)

        # Create admin user
        self.admin_user = User.objects.create_superuser(
            email='admin@test.com',
            password='testpass123'
        )
        self.admin_token = Token.objects.create(user=self.admin_user)

        self.client = APIClient()

    def authenticate_as_parent1(self):
        """Helper method to authenticate as parent1"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent1_token.key}')

    def authenticate_as_parent2(self):
        """Helper method to authenticate as parent2"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent2_token.key}')

    def authenticate_as_psychologist(self):
        """Helper method to authenticate as psychologist"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

    def authenticate_as_admin(self):
        """Helper method to authenticate as admin"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')

    def test_list_parents_as_admin(self):
        """Test listing parents as admin (should see all)"""
        self.authenticate_as_admin()
        url = reverse('parent-management-list')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Admin should see all parents
        self.assertEqual(len(data['results']), 2)

    def test_list_parents_as_parent(self):
        """Test listing parents as parent (should see only own)"""
        self.authenticate_as_parent1()
        url = reverse('parent-management-list')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Parent should see only their own profile
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['email'], self.parent1_user.email)

    def test_list_parents_as_psychologist(self):
        """Test listing parents as psychologist (should see none for now)"""
        self.authenticate_as_psychologist()
        url = reverse('parent-management-list')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Psychologist should see no parents (until relationships are implemented)
        self.assertEqual(len(data['results']), 0)

    def test_retrieve_parent_as_admin(self):
        """Test retrieving specific parent as admin"""
        self.authenticate_as_admin()
        url = reverse('parent-management-detail', kwargs={'pk': self.parent1_profile.user.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data['email'], self.parent1_user.email)
        self.assertEqual(data['first_name'], 'John')

    def test_retrieve_parent_as_owner(self):
        """Test retrieving own profile as parent"""
        self.authenticate_as_parent1()
        url = reverse('parent-management-detail', kwargs={'pk': self.parent1_profile.user.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data['email'], self.parent1_user.email)

    def test_retrieve_other_parent_as_parent(self):
        """Test retrieving another parent's profile as parent (should fail)"""
        self.authenticate_as_parent1()
        url = reverse('parent-management-detail', kwargs={'pk': self.parent2_profile.user.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_parent_as_psychologist(self):
        """Test retrieving parent as psychologist (read-only access)"""
        self.authenticate_as_psychologist()
        url = reverse('parent-management-detail', kwargs={'pk': self.parent1_profile.user.id})

        response = self.client.get(url)

        # Based on the permission logic, psychologist should get 404 for now
        # since there are no relationships implemented yet
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_search_parents_as_admin_success(self):
        """Test searching parents as admin"""
        self.authenticate_as_admin()
        url = reverse('parent-management-search')

        search_data = {
            'first_name': 'John',
            'city': 'City1'
        }

        response = self.client.post(url, search_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data['count'], 1)
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['email'], self.parent1_user.email)

    def test_search_parents_by_email(self):
        """Test searching parents by email"""
        self.authenticate_as_admin()
        url = reverse('parent-management-search')

        search_data = {
            'email': 'parent2@test.com'  # Use full email instead of partial
        }

        response = self.client.post(url, search_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['email'], self.parent2_user.email)

    def test_search_parents_by_verification_status(self):
        """Test searching parents by verification status"""
        self.parent1_user.is_verified = True
        self.parent1_user.save()

        self.authenticate_as_admin()
        url = reverse('parent-management-search')

        search_data = {
            'is_verified': True
        }

        response = self.client.post(url, search_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Should find the verified parent
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['email'], self.parent1_user.email)

    def test_search_parents_date_range(self):
        """Test searching parents by date range"""
        from django.utils import timezone
        from datetime import timedelta

        # Set different creation dates
        past_date = timezone.now() - timedelta(days=10)
        recent_date = timezone.now() - timedelta(days=1)

        self.parent1_profile.created_at = past_date
        self.parent1_profile.save()
        self.parent2_profile.created_at = recent_date
        self.parent2_profile.save()

        self.authenticate_as_admin()
        url = reverse('parent-management-search')

        search_data = {
            'created_after': (timezone.now() - timedelta(days=5)).isoformat()
        }

        response = self.client.post(url, search_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Should only find parent2 (created more recently)
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['email'], self.parent2_user.email)

    def test_search_parents_invalid_date_range(self):
        """Test searching with invalid date range"""
        from django.utils import timezone
        from datetime import timedelta

        self.authenticate_as_admin()
        url = reverse('parent-management-search')

        search_data = {
            'created_after': timezone.now().isoformat(),
            'created_before': (timezone.now() - timedelta(days=1)).isoformat()
        }

        response = self.client.post(url, search_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('created_after', response.json())

    def test_search_parents_as_non_admin(self):
        """Test searching parents as non-admin (should fail)"""
        self.authenticate_as_parent1()
        url = reverse('parent-management-search')

        search_data = {
            'first_name': 'John'
        }

        response = self.client.post(url, search_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('Permission denied', response.json()['error'])

    def test_search_parents_empty_results(self):
        """Test searching parents with no matching results"""
        self.authenticate_as_admin()
        url = reverse('parent-management-search')

        search_data = {
            'first_name': 'NonExistent'
        }

        response = self.client.post(url, search_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data['count'], 0)
        self.assertEqual(len(data['results']), 0)

    def test_search_parents_multiple_criteria(self):
        """Test searching parents with multiple criteria"""
        self.authenticate_as_admin()
        url = reverse('parent-management-search')

        search_data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'city': 'City1'
        }

        response = self.client.post(url, search_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['email'], self.parent1_user.email)

    def test_unauthenticated_access(self):
        """Test unauthenticated access to management endpoints"""
        url = reverse('parent-management-list')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ParentViewSetIntegrationTestCase(APITestCase):
    """Integration tests that test the full flow"""

    def setUp(self):
        """Set up test data"""
        self.parent_user = User.objects.create_parent(
            email='integration@test.com',
            password='testpass123'
        )
        self.parent_user.is_verified = True
        self.parent_user.save()

        self.parent_profile = Parent.objects.get(user=self.parent_user)
        self.parent_token = Token.objects.create(user=self.parent_user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

    def test_complete_profile_update_flow(self):
        """Test the complete flow of updating a parent profile"""
        # 1. Get initial profile
        profile_url = reverse('parent-profile-profile')
        response = self.client.get(profile_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        initial_data = response.json()

        # Check initial completeness (should be low)
        completeness_url = reverse('parent-profile-completeness')
        response = self.client.get(completeness_url)
        initial_completeness = response.json()

        # 2. Update profile information
        update_url = reverse('parent-profile-update-profile')
        update_data = {
            'first_name': 'Integration',
            'last_name': 'Test',
            'phone_number': '+1555123456',
            'address_line1': '123 Test St',
            'city': 'Test City',
            'state_province': 'Test State',
            'postal_code': '12345',
            'country': 'US'
        }

        response = self.client.patch(update_url, update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 3. Check updated profile
        response = self.client.get(profile_url)
        updated_data = response.json()

        self.assertEqual(updated_data['first_name'], 'Integration')
        self.assertEqual(updated_data['last_name'], 'Test')
        self.assertEqual(updated_data['full_name'], 'Integration Test')

        # 4. Check improved completeness
        response = self.client.get(completeness_url)
        updated_completeness = response.json()

        self.assertGreater(
            updated_completeness['overall_score'],
            initial_completeness['overall_score']
        )

        # 5. Update communication preferences
        prefs_url = '/api/parents/profile/communication-preferences/'
        prefs_data = {
            'email_notifications': False,
            'sms_notifications': True,
            'reminder_timing': '2_hours'
        }

        response = self.client.patch(prefs_url, prefs_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 6. Verify preferences were updated
        response = self.client.get(prefs_url)
        final_prefs = response.json()

        self.assertEqual(final_prefs['email_notifications'], False)
        self.assertEqual(final_prefs['sms_notifications'], True)
        self.assertEqual(final_prefs['reminder_timing'], '2_hours')

    def test_profile_data_persistence(self):
        """Test that profile data persists correctly across requests"""
        update_url = reverse('parent-profile-update-profile')

        # Update profile
        update_data = {
            'first_name': 'Persistent',
            'last_name': 'Data',
            'city': 'Persistence City'
        }

        response = self.client.patch(update_url, update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Clear client credentials and re-authenticate
        self.client.credentials()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

        # Verify data persisted
        profile_url = reverse('parent-profile-profile')
        response = self.client.get(profile_url)

        data = response.json()
        self.assertEqual(data['first_name'], 'Persistent')
        self.assertEqual(data['last_name'], 'Data')
        self.assertEqual(data['city'], 'Persistence City')

    def test_error_handling_and_recovery(self):
        """Test error handling and recovery scenarios"""
        update_url = reverse('parent-profile-update-profile')

        # Try to update with invalid data
        invalid_data = {
            'phone_number': 'invalid',
            'first_name': '',  # Empty required field
        }

        response = self.client.patch(update_url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Verify original data is unchanged
        profile_url = reverse('parent-profile-profile')
        response = self.client.get(profile_url)
        data = response.json()

        # Original data should be intact
        self.assertNotEqual(data['phone_number'], 'invalid')

        # Now update with valid data
        valid_data = {
            'first_name': 'Valid',
            'phone_number': '+1555987654'
        }
        response = self.client.patch(update_url, valid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Verify data was updated
        response = self.client.get(profile_url)
        data = response.json()
        self.assertEqual(data['first_name'], 'Valid')
        self.assertEqual(data['phone_number'], '+1555987654')
