# parents/tests/test_serializers.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework import serializers
from unittest.mock import patch, Mock

from users.models import User
from parents.models import Parent
from parents.serializers import (
    ParentSerializer,
    ParentProfileUpdateSerializer,
    ParentDetailSerializer,
    ParentSummarySerializer,
    CommunicationPreferencesSerializer,
    ParentSearchSerializer
)


class ParentSerializerTest(TestCase):
    """Test cases for ParentSerializer"""

    def setUp(self):
        # Create user with Parent type - signal will auto-create parent profile
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            user_type='Parent'
        )
        # Get the auto-created parent profile and update it
        self.parent = self.user.parent_profile
        self.parent.first_name = 'John'
        self.parent.last_name = 'Doe'
        self.parent.phone_number = '+1234567890'
        self.parent.address_line1 = '123 Main St'
        self.parent.city = 'Test City'
        self.parent.state_province = 'Test State'
        self.parent.postal_code = '12345'
        self.parent.country = 'US'
        self.parent.communication_preferences = {
            'email_notifications': True,
            'sms_notifications': False
        }
        self.parent.save()

    def test_serialization(self):
        """Test serializing a parent instance"""
        serializer = ParentSerializer(self.parent)
        data = serializer.data

        # Check read-only user fields
        self.assertEqual(data['email'], 'test@example.com')
        self.assertEqual(data['user_type'], 'Parent')
        self.assertEqual(data['is_verified'], False)

        # Check parent fields
        self.assertEqual(data['first_name'], 'John')
        self.assertEqual(data['last_name'], 'Doe')
        self.assertEqual(data['phone_number'], '+1234567890')

        # Check computed fields
        self.assertEqual(data['full_name'], 'John Doe')
        self.assertEqual(data['display_name'], 'John Doe')

    def test_phone_number_validation_valid(self):
        """Test valid phone number formats"""
        valid_numbers = [
            '+1234567890',
            '123-456-7890',
            '(123) 456-7890',
            '123.456.7890',
            '+1 234 567 8901'
        ]

        for number in valid_numbers:
            serializer = ParentSerializer(data={
                'first_name': 'Test',
                'last_name': 'User',
                'phone_number': number
            })
            self.assertTrue(serializer.is_valid(), f"Phone number {number} should be valid")

    def test_phone_number_validation_invalid(self):
        """Test invalid phone number formats"""
        invalid_numbers = [
            '123456789',  # Too short
            '12345678901234567890123',  # Too long
            'abc1234567890',  # Contains letters
            '123-456-789a'  # Contains invalid characters
        ]

        for number in invalid_numbers:
            serializer = ParentSerializer(data={
                'first_name': 'Test',
                'last_name': 'User',
                'phone_number': number
            })
            self.assertFalse(serializer.is_valid(), f"Phone number {number} should be invalid")

    def test_phone_number_empty_allowed(self):
        """Test that empty phone number is allowed"""
        serializer = ParentSerializer(data={
            'first_name': 'Test',
            'last_name': 'User',
            'phone_number': ''
        })
        self.assertTrue(serializer.is_valid())

    def test_communication_preferences_validation_none(self):
        """Test that None communication preferences returns defaults"""
        serializer = ParentSerializer()
        result = serializer.validate_communication_preferences(None)
        expected = Parent.get_default_communication_preferences()
        self.assertEqual(result, expected)

    def test_communication_preferences_validation_invalid_type(self):
        """Test invalid communication preferences type"""
        serializer = ParentSerializer()
        with self.assertRaises(serializers.ValidationError):
            serializer.validate_communication_preferences("invalid")

    def test_communication_preferences_validation_invalid_reminder_timing(self):
        """Test invalid reminder timing value"""
        serializer = ParentSerializer()
        prefs = {'reminder_timing': 'invalid_timing'}
        with self.assertRaises(serializers.ValidationError):
            serializer.validate_communication_preferences(prefs)

    def test_communication_preferences_validation_valid(self):
        """Test valid communication preferences"""
        serializer = ParentSerializer()
        prefs = {
            'email_notifications': True,
            'sms_notifications': False,
            'reminder_timing': '24_hours'
        }
        result = serializer.validate_communication_preferences(prefs)
        self.assertEqual(result, prefs)


class ParentProfileUpdateSerializerTest(TestCase):
    """Test cases for ParentProfileUpdateSerializer"""

    def setUp(self):
        # Create user with Parent type - signal will auto-create parent profile
        self.user = User.objects.create_user(
            email='test2@example.com',  # Different email
            password='testpass123',
            user_type='Parent'
        )
        # Get the auto-created parent profile and update it
        self.parent = self.user.parent_profile
        self.parent.first_name = 'John'
        self.parent.last_name = 'Doe'
        self.parent.save()

    def test_update_profile(self):
        """Test updating parent profile"""
        data = {
            'first_name': 'Jane',
            'last_name': 'Smith',
            'phone_number': '+9876543210',
            'city': 'New City'
        }
        serializer = ParentProfileUpdateSerializer(self.parent, data=data)
        self.assertTrue(serializer.is_valid())

        updated_parent = serializer.save()
        self.assertEqual(updated_parent.first_name, 'Jane')
        self.assertEqual(updated_parent.last_name, 'Smith')
        self.assertEqual(updated_parent.phone_number, '+9876543210')
        self.assertEqual(updated_parent.city, 'New City')

    def test_excludes_sensitive_fields(self):
        """Test that sensitive fields are not included"""
        serializer = ParentProfileUpdateSerializer()
        fields = serializer.Meta.fields

        # Should not include user-related fields
        self.assertNotIn('email', fields)
        self.assertNotIn('user_type', fields)
        self.assertNotIn('is_verified', fields)



class ParentDetailSerializerTest(TestCase):
    """Test cases for ParentDetailSerializer"""

    def setUp(self):
        # Create user with Parent type - signal will auto-create parent profile
        self.user = User.objects.create_user(
            email='detail_test@example.com',  # Different email
            password='testpass123',
            user_type='Parent'
        )
        # Get the auto-created parent profile and update it
        self.parent = self.user.parent_profile
        self.parent.first_name = 'John'
        self.parent.last_name = 'Doe'
        self.parent.save()

    def test_includes_user_data(self):
        """Test that detailed serializer includes user data"""
        serializer = ParentDetailSerializer(self.parent)
        data = serializer.data

        self.assertIn('user', data)
        self.assertEqual(data['user']['email'], 'detail_test@example.com')
        self.assertEqual(data['user']['user_type'], 'Parent')


class ParentSummarySerializerTest(TestCase):
    """Test cases for ParentSummarySerializer"""

    def setUp(self):
        # Create user with Parent type - signal will auto-create parent profile
        self.user = User.objects.create_user(
            email='summary_test@example.com',  # Different email
            password='testpass123',
            user_type='Parent'
        )
        # Get the auto-created parent profile and update it
        self.parent = self.user.parent_profile
        self.parent.first_name = 'John'
        self.parent.last_name = 'Doe'
        self.parent.city = 'Test City'
        self.parent.save()

    def test_minimal_fields(self):
        """Test that only minimal fields are included"""
        serializer = ParentSummarySerializer(self.parent)
        data = serializer.data

        expected_fields = [
            'user', 'email', 'full_name', 'display_name',
            'city', 'state_province', 'country'
        ]
        self.assertEqual(set(data.keys()), set(expected_fields))

    def test_read_only_fields(self):
        """Test that appropriate fields are read-only"""
        serializer = ParentSummarySerializer()
        read_only_fields = serializer.Meta.read_only_fields

        expected_read_only = ['user', 'email', 'full_name', 'display_name']
        self.assertEqual(set(read_only_fields), set(expected_read_only))


class CommunicationPreferencesSerializerTest(TestCase):
    """Test cases for CommunicationPreferencesSerializer"""

    def setUp(self):
        # Create user with Parent type - signal will auto-create parent profile
        self.user = User.objects.create_user(
            email='comm_prefs_test@example.com',  # Different email
            password='testpass123',
            user_type='Parent'
        )
        # Get the auto-created parent profile and update it
        self.parent = self.user.parent_profile
        self.parent.first_name = 'John'
        self.parent.last_name = 'Doe'
        self.parent.save()

    def test_default_values(self):
        """Test default values for communication preferences"""
        serializer = CommunicationPreferencesSerializer()
        data = serializer.to_representation({})

        self.assertTrue(data['email_notifications'])
        self.assertFalse(data['sms_notifications'])
        self.assertTrue(data['appointment_reminders'])
        self.assertEqual(data['reminder_timing'], '24_hours')
        self.assertTrue(data['growth_plan_updates'])
        self.assertTrue(data['new_message_alerts'])
        self.assertFalse(data['marketing_emails'])

    def test_valid_reminder_timing_choices(self):
        """Test valid reminder timing choices"""
        valid_choices = ['24_hours', '2_hours', '30_minutes']

        for choice in valid_choices:
            serializer = CommunicationPreferencesSerializer(data={
                'reminder_timing': choice
            })
            self.assertTrue(serializer.is_valid())

    def test_invalid_reminder_timing(self):
        """Test invalid reminder timing choice"""
        serializer = CommunicationPreferencesSerializer(data={
            'reminder_timing': 'invalid_choice'
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('reminder_timing', serializer.errors)

    def test_update_parent_preferences(self):
        """Test updating parent communication preferences"""
        data = {
            'email_notifications': False,
            'sms_notifications': True,
            'reminder_timing': '2_hours'
        }

        serializer = CommunicationPreferencesSerializer()
        result = serializer.update(self.parent, data)

        # Refresh from database
        self.parent.refresh_from_db()

        self.assertFalse(self.parent.communication_preferences['email_notifications'])
        self.assertTrue(self.parent.communication_preferences['sms_notifications'])
        self.assertEqual(self.parent.communication_preferences['reminder_timing'], '2_hours')

    def test_update_invalid_instance(self):
        """Test updating with invalid instance type"""
        serializer = CommunicationPreferencesSerializer()

        with self.assertRaises(serializers.ValidationError):
            serializer.update("invalid", {})


class ParentSearchSerializerTest(TestCase):
    """Test cases for ParentSearchSerializer"""

    def test_valid_search_data(self):
        """Test valid search parameters"""
        data = {
            'email': 'test@example.com',
            'first_name': 'John',
            'city': 'Test City',
            'is_verified': True
        }

        serializer = ParentSearchSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_date_range_validation_valid(self):
        """Test valid date range"""
        from datetime import datetime, timezone

        data = {
            'created_after': datetime(2023, 1, 1, tzinfo=timezone.utc),
            'created_before': datetime(2023, 12, 31, tzinfo=timezone.utc)
        }

        serializer = ParentSearchSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_date_range_validation_invalid(self):
        """Test invalid date range (start after end)"""
        from datetime import datetime, timezone

        data = {
            'created_after': datetime(2023, 12, 31, tzinfo=timezone.utc),
            'created_before': datetime(2023, 1, 1, tzinfo=timezone.utc)
        }

        serializer = ParentSearchSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('created_after', serializer.errors)

    def test_all_fields_optional(self):
        """Test that all search fields are optional"""
        serializer = ParentSearchSerializer(data={})
        self.assertTrue(serializer.is_valid())

    def test_email_validation(self):
        """Test email field validation"""
        # Valid email
        serializer = ParentSearchSerializer(data={'email': 'test@example.com'})
        self.assertTrue(serializer.is_valid())

        # Invalid email
        serializer = ParentSearchSerializer(data={'email': 'invalid-email'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('email', serializer.errors)


class ParentSerializerIntegrationTest(TestCase):
    """Integration tests for parent serializers"""

    def test_full_registration_flow(self):
        """Test complete user registration and parent profile update flow"""

        # 1. Register the user
        user = User.objects.create_user(
            email='integration@example.com',
            password='strongpassword123',
            user_type='Parent',
            user_timezone='UTC'
        )

        # 2. Check if Parent profile was auto-created
        parent = user.parent_profile
        self.assertIsInstance(parent, Parent)

        # 3. Update parent profile with extra info
        update_data = {
            'first_name': 'Integration',
            'last_name': 'Test',
            'phone_number': '+1234567890',
            'city': 'Test City',
            'communication_preferences': {
                'email_notifications': False,
                'sms_notifications': True
            }
        }

        update_serializer = ParentProfileUpdateSerializer(parent, data=update_data)
        self.assertTrue(update_serializer.is_valid(), update_serializer.errors)
        updated_parent = update_serializer.save()

        # 4. Assert data was saved correctly
        self.assertEqual(updated_parent.first_name, 'Integration')
        self.assertEqual(updated_parent.user.email, 'integration@example.com')
        self.assertEqual(updated_parent.communication_preferences['sms_notifications'], True)

        # 5. Test ParentDetailSerializer
        detail_serializer = ParentDetailSerializer(updated_parent)
        detail_data = detail_serializer.data
        self.assertEqual(detail_data['first_name'], 'Integration')
        self.assertEqual(detail_data['user']['email'], 'integration@example.com')

    def test_communication_preferences_flow(self):
        """Test communication preferences update flow"""
        # Create parent (signal will auto-create profile)
        user = User.objects.create_user(
            email='comm_flow_test@example.com',
            password='testpass123',
            user_type='Parent'
        )
        parent = user.parent_profile
        parent.first_name = 'Comm'
        parent.last_name = 'Test'
        parent.save()

        # Update preferences
        prefs_data = {
            'email_notifications': False,
            'sms_notifications': True,
            'reminder_timing': '30_minutes'
        }

        prefs_serializer = CommunicationPreferencesSerializer()
        updated_prefs = prefs_serializer.update(parent, prefs_data)

        # Verify update
        parent.refresh_from_db()
        self.assertFalse(parent.communication_preferences['email_notifications'])
        self.assertTrue(parent.communication_preferences['sms_notifications'])
        self.assertEqual(parent.communication_preferences['reminder_timing'], '30_minutes')
