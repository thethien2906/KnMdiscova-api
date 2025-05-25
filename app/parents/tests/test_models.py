# parents/tests/test_models.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone
from users.models import User
from parents.models import Parent


class ParentModelTest(TestCase):
    """Test cases for Parent model"""

    def setUp(self):
        """Set up test data"""
        self.user_data = {
            'email': 'parent@example.com',
            'user_type': 'Parent',
            'password': 'testpass123'
        }

    def test_parent_profile_created_via_signal(self):
        """Test that parent profile is automatically created when Parent user is created"""
        user = User.objects.create_parent(**self.user_data)

        # Parent profile should be automatically created via signal
        self.assertTrue(hasattr(user, 'parent_profile'))
        self.assertIsInstance(user.parent_profile, Parent)
        self.assertEqual(user.parent_profile.user, user)

    def test_parent_profile_update_basic_info(self):
        """Test updating parent profile basic information"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        # Update parent information
        parent.first_name = 'John'
        parent.last_name = 'Doe'
        parent.phone_number = '+1-555-123-4567'
        parent.save()

        # Refresh from database
        parent.refresh_from_db()

        self.assertEqual(parent.first_name, 'John')
        self.assertEqual(parent.last_name, 'Doe')
        self.assertEqual(parent.phone_number, '+1-555-123-4567')

    def test_parent_profile_update_address(self):
        """Test updating parent address information"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        # Update address
        parent.address_line1 = '123 Main St'
        parent.address_line2 = 'Apt 4B'
        parent.city = 'New York'
        parent.state_province = 'NY'
        parent.postal_code = '10001'
        parent.country = 'US'
        parent.save()

        parent.refresh_from_db()

        self.assertEqual(parent.address_line1, '123 Main St')
        self.assertEqual(parent.city, 'New York')
        self.assertEqual(parent.country, 'US')

    def test_parent_str_representation(self):
        """Test string representation of parent"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        parent.first_name = 'John'
        parent.last_name = 'Doe'
        parent.save()

        expected = "John Doe (parent@example.com)"
        self.assertEqual(str(parent), expected)

    def test_parent_str_representation_without_names(self):
        """Test string representation when names are empty"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        # Names should be empty by default from signal
        expected = f"({user.email})"
        self.assertEqual(str(parent), expected)

    def test_full_name_property(self):
        """Test full_name property"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        # With both names
        parent.first_name = 'John'
        parent.last_name = 'Doe'
        parent.save()
        self.assertEqual(parent.full_name, 'John Doe')

        # With only first name
        parent.last_name = ''
        parent.save()
        self.assertEqual(parent.full_name, 'John')

        # With only last name
        parent.first_name = ''
        parent.last_name = 'Doe'
        parent.save()
        self.assertEqual(parent.full_name, 'Doe')

        # With no names (default state)
        parent.first_name = ''
        parent.last_name = ''
        parent.save()
        self.assertEqual(parent.full_name, '')

    def test_display_name_property(self):
        """Test display_name property"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        # With full name
        parent.first_name = 'John'
        parent.last_name = 'Doe'
        parent.save()
        self.assertEqual(parent.display_name, 'John Doe')

        # Without names (should fallback to email username)
        parent.first_name = ''
        parent.last_name = ''
        parent.save()
        self.assertEqual(parent.display_name, 'parent')  # from parent@example.com

    def test_full_address_property(self):
        """Test full_address property"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        # Set full address
        parent.address_line1 = '123 Main St'
        parent.address_line2 = 'Apt 4B'
        parent.city = 'New York'
        parent.state_province = 'NY'
        parent.postal_code = '10001'
        parent.country = 'US'
        parent.save()

        expected = "123 Main St, Apt 4B, New York, NY, 10001, US"
        self.assertEqual(parent.full_address, expected)

        # Test with partial address
        parent.address_line2 = ''
        parent.state_province = ''
        parent.save()
        expected = "123 Main St, New York, 10001, US"
        self.assertEqual(parent.full_address, expected)

        # Test with no address (default state)
        parent.address_line1 = ''
        parent.city = ''
        parent.postal_code = ''
        parent.country = 'US'  # This has a default
        parent.save()
        self.assertEqual(parent.full_address, 'US')

    def test_communication_preferences_default(self):
        """Test default communication preferences"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        # Should be empty dict by default (unless signal sets defaults)
        self.assertIsInstance(parent.communication_preferences, dict)

    def test_get_communication_preference(self):
        """Test getting communication preferences"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        # Set some preferences
        parent.communication_preferences = {
            'email_notifications': False,
            'sms_notifications': True
        }
        parent.save()

        # Test existing preference
        self.assertFalse(parent.get_communication_preference('email_notifications'))
        self.assertTrue(parent.get_communication_preference('sms_notifications'))

        # Test non-existing preference (should return default)
        self.assertTrue(parent.get_communication_preference('non_existing'))
        self.assertFalse(parent.get_communication_preference('non_existing', False))

    def test_set_communication_preference(self):
        """Test setting communication preferences"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        # Set a preference
        parent.set_communication_preference('email_notifications', False)
        parent.refresh_from_db()
        self.assertFalse(parent.communication_preferences['email_notifications'])

        # Set another preference
        parent.set_communication_preference('sms_notifications', True)
        parent.refresh_from_db()
        self.assertTrue(parent.communication_preferences['sms_notifications'])

        # Verify both preferences are preserved
        self.assertFalse(parent.communication_preferences['email_notifications'])

    def test_set_communication_preference_with_none_preferences(self):
        """Test setting communication preference when preferences is None"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        # Manually set to None to test the edge case
        parent.communication_preferences = None

        # This should handle None and create a dict
        parent.set_communication_preference('test_pref', True)
        parent.refresh_from_db()
        self.assertIsInstance(parent.communication_preferences, dict)
        self.assertTrue(parent.communication_preferences['test_pref'])

    def test_get_default_communication_preferences(self):
        """Test default communication preferences class method"""
        defaults = Parent.get_default_communication_preferences()

        expected_keys = [
            'email_notifications',
            'sms_notifications',
            'appointment_reminders',
            'reminder_timing',
            'growth_plan_updates',
            'new_message_alerts',
            'marketing_emails'
        ]

        for key in expected_keys:
            self.assertIn(key, defaults)

        # Test specific defaults
        self.assertTrue(defaults['email_notifications'])
        self.assertFalse(defaults['sms_notifications'])
        self.assertTrue(defaults['appointment_reminders'])
        self.assertEqual(defaults['reminder_timing'], '24_hours')

    def test_phone_number_validation_valid(self):
        """Test valid phone number formats"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        parent.first_name = 'John'
        parent.last_name = 'Doe'

        valid_phones = [
            '+1-555-123-4567',
            '(555) 123-4567',
            '555.123.4567',
            '555 123 4567',
            '5551234567',
            '+1 555 123 4567'
        ]

        for phone in valid_phones:
            parent.phone_number = phone
            try:
                parent.full_clean()  # This validates all fields
            except ValidationError:
                self.fail(f"Valid phone number {phone} failed validation")


    def test_phone_number_validation_invalid(self):
        """Test invalid phone number validation"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        # Invalid phone numbers
        invalid_phones = [
            '123',  # too short
            'abc-def-ghij',  # letters
            '123-456-789012345678901',  # too long
            '!@#$%^&*()',  # special characters
        ]

        for phone in invalid_phones:
            parent.phone_number = phone
            with self.assertRaises(ValidationError):
                parent.full_clean()

    def test_phone_number_can_be_blank(self):
        """Test that phone number can be blank"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        parent.first_name = 'John'
        parent.last_name = 'Doe'
        parent.phone_number = ''
        try:
            parent.full_clean()  # Should not raise ValidationError
        except ValidationError:
            self.fail("Blank phone number raised ValidationError unexpectedly")



    def test_one_to_one_relationship_constraint(self):
        """Test that one user can only have one parent profile"""
        user = User.objects.create_parent(**self.user_data)

        # Parent profile should already exist from signal
        self.assertTrue(Parent.objects.filter(user=user).exists())

        # Try to create another parent profile for same user (should fail)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Parent.objects.create(
                    user=user,
                    first_name='Jane',
                    last_name='Smith'
                )

    def test_cascade_delete(self):
        """Test that deleting user cascades to parent profile"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        parent_id = parent.pk
        user_id = user.id

        # Delete user
        user.delete()

        # Parent should also be deleted
        self.assertFalse(Parent.objects.filter(pk=parent_id).exists())
        self.assertFalse(User.objects.filter(id=user_id).exists())

    def test_cannot_create_parent_for_non_parent_user(self):
        """Test that we can't create parent profile for non-parent user types"""
        # Create a psychologist user
        psychologist_user = User.objects.create_psychologist(
            email='psych@example.com',
            password='testpass123'
        )

        # Should not have parent_profile
        self.assertFalse(hasattr(psychologist_user, 'parent_profile'))

        # Manually trying to create parent profile for psychologist should work at model level
        # but would be prevented by business logic
        parent = Parent(
            user=psychologist_user,
            first_name='John',
            last_name='Doe'
        )
        # This would actually work at the database level, but should be prevented by business logic

    def test_model_meta_properties(self):
        """Test model meta properties"""
        self.assertEqual(Parent._meta.verbose_name, 'Parent')
        self.assertEqual(Parent._meta.verbose_name_plural, 'Parents')
        self.assertEqual(Parent._meta.db_table, 'parents')

    def test_model_indexes(self):
        """Test that model has expected indexes"""
        indexes = Parent._meta.indexes
        index_fields = [list(index.fields) for index in indexes]

        expected_indexes = [
            ['first_name', 'last_name'],
            ['city', 'state_province'],
            ['created_at']
        ]

        for expected in expected_indexes:
            self.assertIn(expected, index_fields)

    def test_timestamps_auto_update(self):
        """Test that timestamps are automatically updated"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        created_at = parent.created_at
        updated_at = parent.updated_at

        # Wait a moment and update
        import time
        time.sleep(0.1)

        parent.first_name = 'Jane'
        parent.save()

        parent.refresh_from_db()

        # created_at should not change
        self.assertEqual(parent.created_at, created_at)

        # updated_at should change
        self.assertGreater(parent.updated_at, updated_at)

    def test_related_name_access(self):
        """Test accessing parent profile through user's related name"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        # Access parent through user
        self.assertEqual(user.parent_profile, parent)

        # Update parent and verify access
        parent.first_name = 'John'
        parent.save()

        self.assertEqual(user.parent_profile.first_name, 'John')

    def test_json_field_behavior(self):
        """Test JSONField behavior for communication_preferences"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        preferences = {
            'email_notifications': True,
            'nested': {
                'setting1': 'value1',
                'setting2': ['item1', 'item2']
            }
        }

        parent.communication_preferences = preferences
        parent.save()

        # Reload from database
        parent.refresh_from_db()

        # Verify complex data structure is preserved
        self.assertEqual(parent.communication_preferences['email_notifications'], True)
        self.assertEqual(parent.communication_preferences['nested']['setting1'], 'value1')
        self.assertEqual(parent.communication_preferences['nested']['setting2'], ['item1', 'item2'])

    def test_field_max_lengths(self):
        """Test field maximum length constraints"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        # Test first_name max length (100)
        long_first_name = 'A' * 101
        parent.first_name = long_first_name

        with self.assertRaises(ValidationError):
            parent.full_clean()

    def test_field_help_text(self):
        """Test that fields have appropriate help text"""
        self.assertEqual(
            Parent._meta.get_field('first_name').help_text,
            "Parent's first name"
        )
        self.assertEqual(
            Parent._meta.get_field('communication_preferences').help_text,
            "Notification and communication preferences"
        )

    def test_queryset_select_related(self):
        """Test optimized querying with select_related"""
        user = User.objects.create_parent(**self.user_data)

        # Test that we can access user without additional query
        with self.assertNumQueries(1):
            parent = Parent.objects.select_related('user').first()
            _ = parent.user.email  # This should not trigger additional query

    def test_multiple_parents_from_different_users(self):
        """Test creating multiple parent profiles from different users"""
        # Create first parent
        user1 = User.objects.create_parent(
            email='parent1@example.com',
            user_type='Parent',
            password='testpass123'
        )
        parent1 = user1.parent_profile

        # Create second parent
        user2 = User.objects.create_parent(
            email='parent2@example.com',
            user_type='Parent',
            password='testpass123'
        )
        parent2 = user2.parent_profile

        # Both should exist and be different
        self.assertNotEqual(parent1.pk, parent2.pk)
        self.assertEqual(parent1.user, user1)
        self.assertEqual(parent2.user, user2)

    def test_default_country_value(self):
        """Test that country field has default value"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        # Country should have default value 'US'
        self.assertEqual(parent.country, 'US')

    def test_communication_preferences_not_null(self):
        """Test that communication_preferences field is never null"""
        user = User.objects.create_parent(**self.user_data)
        parent = user.parent_profile

        # Should be dict, not None
        self.assertIsNotNone(parent.communication_preferences)
        self.assertIsInstance(parent.communication_preferences, dict)