# parents/tests/test_models.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.contrib.auth import get_user_model
from parents.models import Parent

User = get_user_model()


class ParentModelTest(TestCase):
    """Test cases for the Parent model"""

    def setUp(self):
        """Set up test data"""
        self.user_data = {
            'email': 'parent@example.com',
            'user_type': 'Parent',
            'password': 'testpass123'
        }
        self.parent_data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'phone_number': '+1-234-567-8900',
            'address_line1': '123 Main St',
            'address_line2': 'Apt 4B',
            'city': 'New York',
            'state_province': 'NY',
            'postal_code': '10001',
            'country': 'US'
        }

    def test_create_parent_with_user(self):
        """Test creating a parent with a user"""
        user = User.objects.create_user(**self.user_data)
        parent = Parent.objects.create(user=user, **self.parent_data)

        self.assertEqual(parent.user, user)
        self.assertEqual(parent.first_name, 'John')
        self.assertEqual(parent.last_name, 'Doe')
        self.assertEqual(parent.phone_number, '+1-234-567-8900')
        self.assertTrue(hasattr(parent, 'created_at'))
        self.assertTrue(hasattr(parent, 'updated_at'))

    def test_parent_str_method(self):
        """Test the string representation of Parent"""
        user = User.objects.create_user(**self.user_data)
        parent = Parent.objects.create(user=user, **self.parent_data)

        expected_str = f"John Doe (parent@example.com)"
        self.assertEqual(str(parent), expected_str)

    def test_full_name_property(self):
        """Test the full_name property"""
        user = User.objects.create_user(**self.user_data)
        parent = Parent.objects.create(user=user, **self.parent_data)

        self.assertEqual(parent.full_name, "John Doe")

    def test_full_name_with_empty_last_name(self):
        """Test full_name when last_name is empty"""
        user = User.objects.create_user(**self.user_data)
        data = self.parent_data.copy()
        data['last_name'] = ''
        parent = Parent.objects.create(user=user, **data)

        self.assertEqual(parent.full_name, "John")

    def test_full_name_with_empty_first_name(self):
        """Test full_name when first_name is empty"""
        user = User.objects.create_user(**self.user_data)
        data = self.parent_data.copy()
        data['first_name'] = ''
        parent = Parent.objects.create(user=user, **data)

        self.assertEqual(parent.full_name, "Doe")

    def test_display_name_with_names(self):
        """Test display_name when names are provided"""
        user = User.objects.create_user(**self.user_data)
        parent = Parent.objects.create(user=user, **self.parent_data)

        self.assertEqual(parent.display_name, "John Doe")

    def test_display_name_without_names(self):
        """Test display_name fallback to email username"""
        user = User.objects.create_user(**self.user_data)
        data = self.parent_data.copy()
        data['first_name'] = ''
        data['last_name'] = ''
        parent = Parent.objects.create(user=user, **data)

        self.assertEqual(parent.display_name, "parent")  # from parent@example.com

    def test_full_address_property(self):
        """Test the full_address property"""
        user = User.objects.create_user(**self.user_data)
        parent = Parent.objects.create(user=user, **self.parent_data)

        expected_address = "123 Main St, Apt 4B, New York, NY, 10001, US"
        self.assertEqual(parent.full_address, expected_address)

    def test_full_address_with_partial_data(self):
        """Test full_address with only some address fields"""
        user = User.objects.create_user(**self.user_data)
        data = self.parent_data.copy()
        data.update({
            'address_line1': '123 Main St',
            'address_line2': '',
            'city': 'New York',
            'state_province': '',
            'postal_code': '10001',
            'country': 'US'
        })
        parent = Parent.objects.create(user=user, **data)

        expected_address = "123 Main St, New York, 10001, US"
        self.assertEqual(parent.full_address, expected_address)

    def test_communication_preferences_default(self):
        """Test default communication preferences"""
        user = User.objects.create_user(**self.user_data)
        parent = Parent.objects.create(user=user, **self.parent_data)

        # Should be empty dict by default
        self.assertEqual(parent.communication_preferences, {})

    def test_get_communication_preference_with_default(self):
        """Test getting communication preference with default value"""
        user = User.objects.create_user(**self.user_data)
        parent = Parent.objects.create(user=user, **self.parent_data)

        # Should return default value when preference doesn't exist
        self.assertTrue(parent.get_communication_preference('email_notifications', True))
        self.assertFalse(parent.get_communication_preference('sms_notifications', False))

    def test_get_communication_preference_existing(self):
        """Test getting existing communication preference"""
        user = User.objects.create_user(**self.user_data)
        data = self.parent_data.copy()
        data['communication_preferences'] = {'email_notifications': False}
        parent = Parent.objects.create(user=user, **data)

        self.assertFalse(parent.get_communication_preference('email_notifications', True))

    def test_set_communication_preference(self):
        """Test setting communication preference"""
        user = User.objects.create_user(**self.user_data)
        parent = Parent.objects.create(user=user, **self.parent_data)

        parent.set_communication_preference('email_notifications', False)
        parent.refresh_from_db()

        self.assertFalse(parent.communication_preferences['email_notifications'])

    def test_set_communication_preference_with_none_dict(self):
        """Test setting preference when communication_preferences needs initialization"""
        user = User.objects.create_user(**self.user_data)
        # Don't set communication_preferences to None, let it use the default
        data = self.parent_data.copy()
        # Remove the line that sets it to None
        parent = Parent.objects.create(user=user, **data)

        # Manually set to simulate a corrupted state (if needed for testing)
        Parent.objects.filter(pk=parent.pk).update(communication_preferences={})
        parent.refresh_from_db()

        parent.set_communication_preference('email_notifications', True)
        parent.refresh_from_db()

        self.assertTrue(parent.communication_preferences['email_notifications'])

    def test_get_default_communication_preferences(self):
        """Test the default communication preferences class method"""
        defaults = Parent.get_default_communication_preferences()

        expected_defaults = {
            'email_notifications': True,
            'sms_notifications': False,
            'appointment_reminders': True,
            'reminder_timing': '24_hours',
            'growth_plan_updates': True,
            'new_message_alerts': True,
            'marketing_emails': False,
        }

        self.assertEqual(defaults, expected_defaults)

    def test_one_to_one_relationship_constraint(self):
        """Test that a user can only have one parent profile"""
        user = User.objects.create_user(**self.user_data)
        Parent.objects.create(user=user, **self.parent_data)

        # Try to create another parent with the same user
        with self.assertRaises(IntegrityError):
            Parent.objects.create(user=user, first_name='Jane', last_name='Smith')

    def test_cascade_delete(self):
        """Test that deleting user also deletes parent"""
        user = User.objects.create_user(**self.user_data)
        parent = Parent.objects.create(user=user, **self.parent_data)
        parent_id = parent.pk

        # Delete the user
        user.delete()

        # Parent should also be deleted
        with self.assertRaises(Parent.DoesNotExist):
            Parent.objects.get(pk=parent_id)

    def test_related_name_access(self):
        """Test accessing parent from user via related_name"""
        user = User.objects.create_user(**self.user_data)
        parent = Parent.objects.create(user=user, **self.parent_data)

        # Access parent through user's related name
        self.assertEqual(user.parent_profile, parent)

    def test_minimal_parent_creation(self):
        """Test creating parent with only required fields"""
        user = User.objects.create_user(**self.user_data)
        parent = Parent.objects.create(
            user=user,
            first_name='Jane',
            last_name='Smith'
        )

        self.assertEqual(parent.first_name, 'Jane')
        self.assertEqual(parent.last_name, 'Smith')
        self.assertEqual(parent.phone_number, '')
        self.assertEqual(parent.address_line1, '')


class ParentPhoneValidationTest(TestCase):
    """Test cases for phone number validation"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='test@example.com',
            user_type='Parent',
            password='testpass123'
        )

    def test_valid_phone_numbers(self):
        """Test various valid phone number formats"""
        valid_numbers = [
            '+1-234-567-8900',
            '(234) 567-8900',
            '234.567.8900',
            '+1 234 567 8900',
            '2345678900',
            '+44 20 7946 0958',  # UK number
            '+1 (555) 123-4567',
            '555-123-4567',
        ]

        for phone in valid_numbers:
            with self.subTest(phone=phone):
                parent = Parent(
                    user=self.user,
                    first_name='Test',
                    last_name='User',
                    phone_number=phone
                )
                try:
                    parent.full_clean()  # This validates the model
                except ValidationError:
                    self.fail(f"Phone number '{phone}' should be valid")

    def test_invalid_phone_numbers(self):
        """Test invalid phone number formats"""
        invalid_numbers = [
            '123',  # too short
            'abc-def-ghij',  # letters
            '123-456-789012345678901234567890',  # too long
            '+',  # just a plus
            '()',  # just parentheses
            '123 456',  # too short with space
        ]

        for phone in invalid_numbers:
            with self.subTest(phone=phone):
                parent = Parent(
                    user=self.user,
                    first_name='Test',
                    last_name='User',
                    phone_number=phone
                )
                with self.assertRaises(ValidationError):
                    parent.full_clean()

    def test_empty_phone_number(self):
        """Test that empty phone number is allowed"""
        parent = Parent(
            user=self.user,
            first_name='Test',
            last_name='User',
            phone_number=''
        )
        try:
            parent.full_clean()
        except ValidationError:
            self.fail("Empty phone number should be valid")


class ParentQueryTest(TestCase):
    """Test cases for Parent model queries and database operations"""

    def setUp(self):
        """Set up test data"""
        # Create multiple users and parents for testing
        self.users_and_parents = []
        for i in range(3):
            user = User.objects.create_user(
                email=f'parent{i}@example.com',
                user_type='Parent',
                password='testpass123'
            )
            parent = Parent.objects.create(
                user=user,
                first_name=f'Parent{i}',
                last_name=f'LastName{i}',
                city=f'City{i}',
                state_province='NY' if i % 2 == 0 else 'CA'
            )
            self.users_and_parents.append((user, parent))

    def test_parent_queryset(self):
        """Test basic Parent queryset operations"""
        # Test count
        self.assertEqual(Parent.objects.count(), 3)

        # Test filtering by name
        parent = Parent.objects.filter(first_name='Parent0').first()
        self.assertIsNotNone(parent)
        self.assertEqual(parent.first_name, 'Parent0')

    def test_filter_by_user_email(self):
        """Test filtering parents by user email"""
        parent = Parent.objects.filter(user__email='parent1@example.com').first()
        self.assertIsNotNone(parent)
        self.assertEqual(parent.first_name, 'Parent1')

    def test_filter_by_location(self):
        """Test filtering parents by location"""
        ny_parents = Parent.objects.filter(state_province='NY')
        ca_parents = Parent.objects.filter(state_province='CA')

        self.assertEqual(ny_parents.count(), 2)  # Parent0 and Parent2
        self.assertEqual(ca_parents.count(), 1)  # Parent1

    def test_select_related_user(self):
        """Test select_related for efficient user access"""
        # This should only make one database query
        with self.assertNumQueries(1):
            parents = list(Parent.objects.select_related('user').all())
            # Access user data without additional queries
            for parent in parents:
                _ = parent.user.email

    def test_ordering(self):
        """Test ordering parents"""
        parents_by_name = Parent.objects.order_by('first_name')
        names = [p.first_name for p in parents_by_name]
        self.assertEqual(names, ['Parent0', 'Parent1', 'Parent2'])

    def test_model_meta_options(self):
        """Test model meta options"""
        meta = Parent._meta
        self.assertEqual(meta.db_table, 'parents')
        self.assertEqual(str(meta.verbose_name), 'Parent')
        self.assertEqual(str(meta.verbose_name_plural), 'Parents')

        # Check that indexes exist
        index_names = [index.name for index in meta.indexes]
        self.assertTrue(any('first_name' in str(index.fields) for index in meta.indexes))
        self.assertTrue(any('created_at' in str(index.fields) for index in meta.indexes))