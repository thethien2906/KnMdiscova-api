# parents/tests/test_services.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import transaction
from unittest.mock import patch, MagicMock
import logging

from users.models import User
from parents.models import Parent
from parents.services import ParentService, ParentProfileError, ParentNotFoundError


class ParentServiceTestCase(TestCase):
    """Test cases for ParentService"""

    def setUp(self):
        """Set up test data"""
        # Create a parent user (this will trigger the signal to create Parent profile)
        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True,
            is_active=True
        )

        # Get the automatically created parent profile
        self.parent = Parent.objects.get(user=self.parent_user)

        # Create a non-parent user for testing
        self.non_parent_user = User.objects.create_user(
            email='student@test.com',
            password='testpass123',
            user_type='Student',
            is_verified=True,
            is_active=True
        )

    def tearDown(self):
        """Clean up after tests"""
        User.objects.all().delete()
        Parent.objects.all().delete()


class TestGetParentByUser(ParentServiceTestCase):
    """Test get_parent_by_user method"""

    def test_get_existing_parent(self):
        """Test getting an existing parent profile"""
        parent = ParentService.get_parent_by_user(self.parent_user)

        self.assertIsNotNone(parent)
        self.assertEqual(parent.user, self.parent_user)
        self.assertIsInstance(parent, Parent)

    def test_get_non_existing_parent(self):
        """Test getting parent profile for non-parent user"""
        parent = ParentService.get_parent_by_user(self.non_parent_user)

        self.assertIsNone(parent)

    @patch('parents.services.logger')
    def test_get_non_existing_parent_logs_warning(self, mock_logger):
        """Test that warning is logged when parent not found"""
        ParentService.get_parent_by_user(self.non_parent_user)

        mock_logger.warning.assert_called_once_with(
            f"Parent profile not found for user {self.non_parent_user.email}"
        )

    def test_get_parent_with_select_related(self):
        """Test that the method uses select_related optimization"""
        with self.assertNumQueries(1):
            parent = ParentService.get_parent_by_user(self.parent_user)
            # Accessing user should not trigger additional query
            _ = parent.user.email


class TestGetParentByUserOrRaise(ParentServiceTestCase):
    """Test get_parent_by_user_or_raise method"""

    def test_get_existing_parent_or_raise(self):
        """Test getting existing parent profile or raise"""
        parent = ParentService.get_parent_by_user_or_raise(self.parent_user)

        self.assertIsNotNone(parent)
        self.assertEqual(parent.user, self.parent_user)

    def test_raise_when_parent_not_found(self):
        """Test that exception is raised when parent not found"""
        with self.assertRaises(ParentNotFoundError) as context:
            ParentService.get_parent_by_user_or_raise(self.non_parent_user)

        self.assertIn(self.non_parent_user.email, str(context.exception))


class TestUpdateParentProfile(ParentServiceTestCase):
    """Test update_parent_profile method"""

    def test_update_basic_fields(self):
        """Test updating basic parent profile fields"""
        update_data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'phone_number': '+1234567890',
            'city': 'New York',
            'country': 'US'
        }

        updated_parent = ParentService.update_parent_profile(self.parent, update_data)

        self.assertEqual(updated_parent.first_name, 'John')
        self.assertEqual(updated_parent.last_name, 'Doe')
        self.assertEqual(updated_parent.phone_number, '+1234567890')
        self.assertEqual(updated_parent.city, 'New York')
        self.assertEqual(updated_parent.country, 'US')

    def test_update_address_fields(self):
        """Test updating address fields"""
        update_data = {
            'address_line1': '123 Main St',
            'address_line2': 'Apt 4B',
            'city': 'Boston',
            'state_province': 'MA',
            'postal_code': '02101'
        }

        updated_parent = ParentService.update_parent_profile(self.parent, update_data)

        self.assertEqual(updated_parent.address_line1, '123 Main St')
        self.assertEqual(updated_parent.address_line2, 'Apt 4B')
        self.assertEqual(updated_parent.city, 'Boston')
        self.assertEqual(updated_parent.state_province, 'MA')
        self.assertEqual(updated_parent.postal_code, '02101')

    def test_update_communication_preferences(self):
        """Test updating communication preferences"""
        update_data = {
            'communication_preferences': {
                'email_notifications': False,
                'sms_notifications': True,
                'reminder_timing': '2_hours'
            }
        }

        updated_parent = ParentService.update_parent_profile(self.parent, update_data)

        prefs = updated_parent.communication_preferences
        self.assertFalse(prefs['email_notifications'])
        self.assertTrue(prefs['sms_notifications'])
        self.assertEqual(prefs['reminder_timing'], '2_hours')

    def test_update_non_parent_user_raises_error(self):
        """Test that updating non-parent user raises error"""
        # Create a parent profile for non-parent user (shouldn't happen in real app)
        fake_parent = Parent.objects.create(
            user=self.non_parent_user,
            first_name='Test',
            last_name='User'
        )

        with self.assertRaises(ParentProfileError) as context:
            ParentService.update_parent_profile(fake_parent, {'first_name': 'New Name'})

        self.assertIn("User is not a parent", str(context.exception))

    def test_update_inactive_user_raises_error(self):
        """Test that updating inactive user raises error"""
        self.parent_user.is_active = False
        self.parent_user.save()

        with self.assertRaises(ParentProfileError) as context:
            ParentService.update_parent_profile(self.parent, {'first_name': 'New Name'})

        self.assertIn("User account is inactive", str(context.exception))

    def test_update_ignores_invalid_fields(self):
        """Test that invalid fields are ignored during update"""
        update_data = {
            'first_name': 'John',
            'invalid_field': 'should be ignored',
            'user': 'should not be updatable'
        }

        updated_parent = ParentService.update_parent_profile(self.parent, update_data)

        self.assertEqual(updated_parent.first_name, 'John')
        # Original user should remain unchanged
        self.assertEqual(updated_parent.user, self.parent_user)

    @patch('parents.services.logger')
    def test_update_logs_success(self, mock_logger):
        """Test that successful update is logged"""
        update_data = {'first_name': 'John'}

        ParentService.update_parent_profile(self.parent, update_data)

        mock_logger.info.assert_called()
        log_call = mock_logger.info.call_args[0][0]
        self.assertIn(self.parent_user.email, log_call)
        self.assertIn('first_name', log_call)

    @patch('parents.services.logger')
    def test_update_logs_error_on_exception(self, mock_logger):
        """Test that errors are logged when update fails"""
        with patch('parents.models.Parent.save', side_effect=Exception("Database error")):
            with self.assertRaises(ParentProfileError):
                ParentService.update_parent_profile(self.parent, {'first_name': 'John'})

            mock_logger.error.assert_called()
            log_call = mock_logger.error.call_args[0][0]
            self.assertIn(self.parent_user.email, log_call)
            self.assertIn("Database error", log_call)


class TestUpdateCommunicationPreferences(ParentServiceTestCase):
    """Test _update_communication_preferences method"""

    def test_update_valid_preferences(self):
        """Test updating valid communication preferences"""
        preferences = {
            'email_notifications': False,
            'sms_notifications': True,
            'appointment_reminders': False,
            'reminder_timing': '30_minutes'
        }

        ParentService._update_communication_preferences(self.parent, preferences)

        self.parent.refresh_from_db()
        prefs = self.parent.communication_preferences

        self.assertFalse(prefs['email_notifications'])
        self.assertTrue(prefs['sms_notifications'])
        self.assertFalse(prefs['appointment_reminders'])
        self.assertEqual(prefs['reminder_timing'], '30_minutes')

    def test_update_preferences_preserves_existing(self):
        """Test that updating preferences preserves existing values"""
        # Set initial preferences
        self.parent.communication_preferences = {
            'email_notifications': True,
            'sms_notifications': False,
            'marketing_emails': True
        }
        self.parent.save()

        # Update only some preferences
        new_preferences = {
            'email_notifications': False,
            'reminder_timing': '2_hours'
        }

        ParentService._update_communication_preferences(self.parent, new_preferences)

        self.parent.refresh_from_db()
        prefs = self.parent.communication_preferences

        self.assertFalse(prefs['email_notifications'])  # Updated
        self.assertFalse(prefs['sms_notifications'])    # Preserved
        self.assertTrue(prefs['marketing_emails'])      # Preserved
        self.assertEqual(prefs['reminder_timing'], '2_hours')  # Added

    def test_invalid_preferences_type_raises_error(self):
        """Test that invalid preferences type raises error"""
        with self.assertRaises(ParentProfileError) as context:
            ParentService._update_communication_preferences(self.parent, "not a dict")

        self.assertIn("must be a dictionary", str(context.exception))

    def test_invalid_reminder_timing_raises_error(self):
        """Test that invalid reminder timing raises error"""
        preferences = {'reminder_timing': 'invalid_timing'}

        with self.assertRaises(ParentProfileError) as context:
            ParentService._update_communication_preferences(self.parent, preferences)

        self.assertIn("Invalid reminder timing", str(context.exception))

    def test_invalid_boolean_preference_raises_error(self):
        """Test that invalid boolean preference raises error"""
        preferences = {'email_notifications': 'not a boolean'}

        with self.assertRaises(ParentProfileError) as context:
            ParentService._update_communication_preferences(self.parent, preferences)

        self.assertIn("must be a boolean", str(context.exception))

    @patch('parents.services.logger')
    def test_unknown_preference_key_logs_warning(self, mock_logger):
        """Test that unknown preference keys log warnings"""
        preferences = {
            'unknown_preference': True,
            'email_notifications': False
        }

        ParentService._update_communication_preferences(self.parent, preferences)

        mock_logger.warning.assert_called_with("Unknown communication preference key: unknown_preference")

    @patch('parents.services.logger')
    def test_successful_update_logs_info(self, mock_logger):
        """Test that successful preference update logs info"""
        preferences = {'email_notifications': False}

        ParentService._update_communication_preferences(self.parent, preferences)

        mock_logger.info.assert_called_with(
            f"Updated communication preferences for {self.parent_user.email}"
        )


class TestGetParentProfileData(ParentServiceTestCase):
    """Test get_parent_profile_data method"""

    def test_get_complete_profile_data(self):
        """Test getting complete parent profile data"""
        # Set up parent with complete data
        self.parent.first_name = 'John'
        self.parent.last_name = 'Doe'
        self.parent.phone_number = '+1234567890'
        self.parent.address_line1 = '123 Main St'
        self.parent.city = 'Boston'
        self.parent.state_province = 'MA'
        self.parent.postal_code = '02101'
        self.parent.country = 'US'
        self.parent.user.profile_picture_url = 'http://example.com/profile.jpg'
        self.parent.communication_preferences = {'email_notifications': True}
        self.parent.save()

        profile_data = ParentService.get_parent_profile_data(self.parent)

        # Check user-related fields
        self.assertEqual(profile_data['user_id'], str(self.parent_user.id))
        self.assertEqual(profile_data['email'], self.parent_user.email)
        self.assertEqual(profile_data['user_type'], 'Parent')
        self.assertTrue(profile_data['is_verified'])
        self.assertTrue(profile_data['is_active'])
        self.assertTrue(profile_data['profile_picture_url'])

        # Check profile fields
        self.assertEqual(profile_data['first_name'], 'John')
        self.assertEqual(profile_data['last_name'], 'Doe')
        self.assertEqual(profile_data['full_name'], 'John Doe')
        self.assertEqual(profile_data['phone_number'], '+1234567890')

        # Check address fields
        self.assertEqual(profile_data['address_line1'], '123 Main St')
        self.assertEqual(profile_data['city'], 'Boston')
        self.assertEqual(profile_data['state_province'], 'MA')
        self.assertEqual(profile_data['postal_code'], '02101')
        self.assertEqual(profile_data['country'], 'US')

        # Check computed fields
        self.assertIn('profile_completeness', profile_data)
        self.assertIn('created_at', profile_data)
        self.assertIn('updated_at', profile_data)

    def test_get_profile_data_with_empty_fields(self):
        """Test getting profile data with empty fields"""
        profile_data = ParentService.get_parent_profile_data(self.parent)

        self.assertEqual(profile_data['first_name'], '')
        self.assertEqual(profile_data['last_name'], '')
        self.assertEqual(profile_data['phone_number'], '')
        self.assertIsNotNone(profile_data['profile_completeness'])


class TestCalculateProfileCompleteness(ParentServiceTestCase):
    """Test calculate_profile_completeness method"""

    def test_empty_profile_completeness(self):
        """Test completeness calculation for empty profile"""
        completeness = ParentService.calculate_profile_completeness(self.parent)

        # Required: 0/3 = 0%, Optional: 1/5 = 20% (only country has default 'US')
        # Overall: (0 * 0.7) + (20 * 0.3) = 0 + 6 = 6%
        self.assertEqual(completeness['overall_score'], 6.0)
        self.assertEqual(completeness['required_score'], 0.0)
        self.assertEqual(completeness['optional_score'], 20.0)  # Only country has default 'US'
        self.assertFalse(completeness['is_complete'])
        self.assertEqual(len(completeness['missing_required_fields']), 3)  # first_name, last_name, phone_number
        self.assertEqual(completeness['completed_required'], 0)
        self.assertEqual(completeness['total_required'], 3)
        self.assertEqual(completeness['completed_optional'], 1)  # Only country
        self.assertEqual(completeness['total_optional'], 5)

    def test_complete_profile_completeness(self):
        """Test completeness calculation for complete profile"""
        self.parent.first_name = 'John'
        self.parent.last_name = 'Doe'
        self.parent.phone_number = '+1234567890'
        self.parent.address_line1 = '123 Main St'
        self.parent.city = 'Boston'
        self.parent.state_province = 'MA'
        self.parent.postal_code = '02101'
        self.parent.save()

        completeness = ParentService.calculate_profile_completeness(self.parent)

        self.assertEqual(completeness['overall_score'], 100.0)
        self.assertEqual(completeness['required_score'], 100.0)
        self.assertEqual(completeness['optional_score'], 100.0)
        self.assertTrue(completeness['is_complete'])
        self.assertEqual(len(completeness['missing_required_fields']), 0)
        self.assertEqual(len(completeness['missing_optional_fields']), 0)

    def test_partial_profile_completeness(self):
        """Test completeness calculation for partially complete profile"""
        self.parent.first_name = 'John'
        self.parent.last_name = 'Doe'
        # phone_number missing
        self.parent.city = 'Boston'
        # Other address fields missing
        self.parent.save()

        completeness = ParentService.calculate_profile_completeness(self.parent)

        # Required: 2/3 = 66.67%, Optional: 2/5 = 40% (city + country default)
        # Overall: (66.67 * 0.7) + (40 * 0.3) = 46.67 + 12 = 58.67
        expected_required = round(2/3 * 100, 1)  # 66.7%
        expected_optional = round(2/5 * 100, 1)  # 40%
        expected_overall = round((expected_required * 0.7) + (expected_optional * 0.3), 1)

        self.assertEqual(completeness['required_score'], expected_required)
        self.assertEqual(completeness['optional_score'], expected_optional)
        self.assertEqual(completeness['overall_score'], expected_overall)
        self.assertFalse(completeness['is_complete'])
        self.assertIn('phone_number', completeness['missing_required_fields'])
        self.assertEqual(completeness['completed_required'], 2)
        self.assertEqual(completeness['completed_optional'], 2)  # city + country

    def test_whitespace_only_fields_treated_as_empty(self):
        """Test that whitespace-only fields are treated as empty"""
        self.parent.first_name = '   '  # Only whitespace
        self.parent.last_name = 'Doe'
        self.parent.phone_number = '+1234567890'
        self.parent.save()

        completeness = ParentService.calculate_profile_completeness(self.parent)

        self.assertFalse(completeness['is_complete'])
        self.assertIn('first_name', completeness['missing_required_fields'])
        self.assertEqual(completeness['completed_required'], 2)  # last_name and phone_number


class TestResetCommunicationPreferences(ParentServiceTestCase):
    """Test reset_communication_preferences_to_default method"""

    def test_reset_preferences_to_default(self):
        """Test resetting preferences to default values"""
        # Set custom preferences
        self.parent.communication_preferences = {
            'email_notifications': False,
            'sms_notifications': True,
            'marketing_emails': True
        }
        self.parent.save()

        # Reset to defaults
        updated_parent = ParentService.reset_communication_preferences_to_default(self.parent)

        defaults = Parent.get_default_communication_preferences()
        self.assertEqual(updated_parent.communication_preferences, defaults)

    @patch('parents.services.logger')
    def test_reset_preferences_logs_success(self, mock_logger):
        """Test that successful reset logs info"""
        ParentService.reset_communication_preferences_to_default(self.parent)

        mock_logger.info.assert_called_with(
            f"Reset communication preferences to default for {self.parent_user.email}"
        )

    @patch('parents.services.logger')
    @patch('parents.models.Parent.save', side_effect=Exception("Database error"))
    def test_reset_preferences_logs_error_on_exception(self, mock_save, mock_logger):
        """Test that reset errors are logged and raised"""
        with self.assertRaises(ParentProfileError):
            ParentService.reset_communication_preferences_to_default(self.parent)

        mock_logger.error.assert_called()
        log_call = mock_logger.error.call_args[0][0]
        self.assertIn(self.parent_user.email, log_call)
        self.assertIn("Database error", log_call)


class TestValidateProfileData(ParentServiceTestCase):
    """Test validate_profile_data method"""

    def test_validate_valid_data(self):
        """Test validation of valid profile data"""
        valid_data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'phone_number': '+1234567890',
            'country': 'US'
        }

        result = ParentService.validate_profile_data(valid_data)
        self.assertEqual(result, valid_data)

    def test_validate_invalid_phone_number(self):
        """Test validation fails for invalid phone number"""
        invalid_data = {
            'phone_number': 'invalid-phone'
        }

        with self.assertRaises(ValidationError) as context:
            ParentService.validate_profile_data(invalid_data)

        self.assertIn('phone_number', context.exception.message_dict)

    def test_validate_empty_required_fields(self):
        """Test validation fails for empty required fields"""
        invalid_data = {
            'first_name': '   ',  # Only whitespace
            'last_name': ''       # Empty string
        }

        with self.assertRaises(ValidationError) as context:
            ParentService.validate_profile_data(invalid_data)

        errors = context.exception.message_dict
        self.assertIn('first_name', errors)
        self.assertIn('last_name', errors)

    def test_validate_long_country_name(self):
        """Test validation fails for overly long country name"""
        invalid_data = {
            'country': 'A' * 51  # 51 characters, limit is 50
        }

        with self.assertRaises(ValidationError) as context:
            ParentService.validate_profile_data(invalid_data)

        self.assertIn('country', context.exception.message_dict)

    def test_validate_valid_phone_number_formats(self):
        """Test validation passes for various valid phone formats"""
        valid_phones = [
            '+1234567890',
            '(123) 456-7890',
            '123-456-7890',
            '123.456.7890',
            '+1 (234) 567-8900'
        ]

        for phone in valid_phones:
            data = {'phone_number': phone}
            result = ParentService.validate_profile_data(data)
            self.assertEqual(result['phone_number'], phone)

    def test_validate_empty_phone_number_allowed(self):
        """Test that empty phone number is allowed"""
        data = {'phone_number': ''}
        result = ParentService.validate_profile_data(data)
        self.assertEqual(result['phone_number'], '')

    def test_validate_none_values_skip_validation(self):
        """Test that None values skip validation"""
        data = {
            'first_name': None,
            'phone_number': None
        }

        result = ParentService.validate_profile_data(data)
        self.assertEqual(result, data)


class TestParentServiceIntegration(ParentServiceTestCase):
    """Integration tests for ParentService"""

    def test_complete_profile_workflow(self):
        """Test complete workflow from creation to update"""
        # Verify parent was created by signal
        self.assertIsNotNone(self.parent)
        self.assertEqual(self.parent.user, self.parent_user)

        # Update profile
        update_data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'phone_number': '+1234567890',
            'city': 'Boston',
            'communication_preferences': {
                'email_notifications': False,
                'reminder_timing': '2_hours'
            }
        }

        updated_parent = ParentService.update_parent_profile(self.parent, update_data)

        # Verify updates
        self.assertEqual(updated_parent.first_name, 'John')
        self.assertEqual(updated_parent.last_name, 'Doe')
        self.assertEqual(updated_parent.full_name, 'John Doe')
        self.assertFalse(updated_parent.communication_preferences['email_notifications'])

        # Get profile data
        profile_data = ParentService.get_parent_profile_data(updated_parent)
        self.assertEqual(profile_data['full_name'], 'John Doe')
        self.assertTrue(profile_data['profile_completeness']['overall_score'] > 50)

    def test_service_with_transaction_rollback(self):
        """Test that service properly handles transaction rollbacks"""
        original_first_name = self.parent.first_name

        with patch('parents.models.Parent.save', side_effect=Exception("Database error")):
            with self.assertRaises(ParentProfileError):
                ParentService.update_parent_profile(self.parent, {'first_name': 'Should Not Save'})

        # Verify rollback - data should be unchanged
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.first_name, original_first_name)