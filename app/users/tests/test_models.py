import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from datetime import datetime, timedelta


User = get_user_model()


class UserModelTest(TestCase):
    """Test cases for User model"""

    def setUp(self):
        """Set up test data"""
        self.valid_email = 'test@example.com'
        self.valid_password = 'testpassword123'

    def test_create_user_with_all_fields(self):
        """Test creating user with all fields"""
        user = User.objects.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent',
            profile_picture_url='https://example.com/pic.jpg',
            user_timezone='America/New_York',
            is_verified=True
        )

        self.assertEqual(user.email, self.valid_email)
        self.assertEqual(user.user_type, 'Parent')
        self.assertEqual(user.profile_picture_url, 'https://example.com/pic.jpg')
        self.assertEqual(user.user_timezone, 'America/New_York')
        self.assertTrue(user.is_verified)
        self.assertTrue(user.is_active)  # Default value
        self.assertFalse(user.is_staff)  # Default value
        self.assertFalse(user.is_superuser)  # Default value

    def test_user_id_is_uuid(self):
        """Test that user ID is a UUID"""
        user = User.objects.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent'
        )

        self.assertIsInstance(user.id, uuid.UUID)
        self.assertIsNotNone(user.id)

    def test_user_id_is_unique(self):
        """Test that each user gets a unique UUID"""
        user1 = User.objects.create_user(
            email='user1@example.com',
            password=self.valid_password,
            user_type='Parent'
        )
        user2 = User.objects.create_user(
            email='user2@example.com',
            password=self.valid_password,
            user_type='Psychologist'
        )

        self.assertNotEqual(user1.id, user2.id)

    def test_email_is_required(self):
        """Test that email is required"""
        with self.assertRaises(ValueError):
            User.objects.create_user(
                email='',
                password=self.valid_password,
                user_type='Parent'
            )

    def test_email_is_unique(self):
        """Test that email must be unique"""
        User.objects.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent'
        )

        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                email=self.valid_email,
                password='differentpassword',
                user_type='Psychologist'
            )

    def test_user_type_choices(self):
        """Test valid user type choices"""
        valid_types = ['Parent', 'Psychologist', 'Admin']

        for user_type in valid_types:
            with self.subTest(user_type=user_type):
                user = User.objects.create_user(
                    email=f'{user_type.lower()}@example.com',
                    password=self.valid_password,
                    user_type=user_type
                )
                self.assertEqual(user.user_type, user_type)

    def test_user_type_invalid_choice(self):
        """Test that invalid user type raises error during validation"""
        user = User(
            email=self.valid_email,
            user_type='InvalidType'
        )

        with self.assertRaises(ValidationError):
            user.full_clean()

    def test_default_values(self):
        """Test default field values"""
        user = User.objects.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent'
        )

        self.assertTrue(user.is_active)
        self.assertFalse(user.is_verified)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.user_timezone, 'UTC')
        self.assertIsNone(user.profile_picture_url)
        self.assertIsNone(user.last_login_date)

    def test_timestamp_fields(self):
        """Test that timestamp fields are set correctly"""
        before_creation = timezone.now()
        user = User.objects.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent'
        )
        after_creation = timezone.now()

        # Test registration_date
        self.assertGreaterEqual(user.registration_date, before_creation)
        self.assertLessEqual(user.registration_date, after_creation)

        # Test created_at
        self.assertGreaterEqual(user.created_at, before_creation)
        self.assertLessEqual(user.created_at, after_creation)

        # Test updated_at
        self.assertGreaterEqual(user.updated_at, before_creation)
        self.assertLessEqual(user.updated_at, after_creation)

        # Test that created_at and updated_at are close in time
        time_diff = user.updated_at - user.created_at
        self.assertLess(time_diff.total_seconds(), 1)

    def test_updated_at_changes_on_save(self):
        """Test that updated_at field changes when model is saved"""
        user = User.objects.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent'
        )
        original_updated_at = user.updated_at

        # Wait a small amount and update
        import time
        time.sleep(0.1)
        user.user_timezone = 'Europe/London'
        user.save()

        self.assertGreater(user.updated_at, original_updated_at)

    def test_str_representation(self):
        """Test string representation of user"""
        user = User.objects.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent'
        )

        expected_str = f"{self.valid_email} (Parent)"
        self.assertEqual(str(user), expected_str)

    def test_is_parent_property(self):
        """Test is_parent property"""
        parent_user = User.objects.create_user(
            email='parent@example.com',
            password=self.valid_password,
            user_type='Parent'
        )
        psychologist_user = User.objects.create_user(
            email='psychologist@example.com',
            password=self.valid_password,
            user_type='Psychologist'
        )
        admin_user = User.objects.create_user(
            email='admin@example.com',
            password=self.valid_password,
            user_type='Admin'
        )

        self.assertTrue(parent_user.is_parent)
        self.assertFalse(psychologist_user.is_parent)
        self.assertFalse(admin_user.is_parent)

    def test_is_psychologist_property(self):
        """Test is_psychologist property"""
        parent_user = User.objects.create_user(
            email='parent@example.com',
            password=self.valid_password,
            user_type='Parent'
        )
        psychologist_user = User.objects.create_user(
            email='psychologist@example.com',
            password=self.valid_password,
            user_type='Psychologist'
        )
        admin_user = User.objects.create_user(
            email='admin@example.com',
            password=self.valid_password,
            user_type='Admin'
        )

        self.assertFalse(parent_user.is_psychologist)
        self.assertTrue(psychologist_user.is_psychologist)
        self.assertFalse(admin_user.is_psychologist)

    def test_is_admin_property(self):
        """Test is_admin property"""
        parent_user = User.objects.create_user(
            email='parent@example.com',
            password=self.valid_password,
            user_type='Parent'
        )
        psychologist_user = User.objects.create_user(
            email='psychologist@example.com',
            password=self.valid_password,
            user_type='Psychologist'
        )
        admin_user = User.objects.create_user(
            email='admin@example.com',
            password=self.valid_password,
            user_type='Admin'
        )

        self.assertFalse(parent_user.is_admin)
        self.assertFalse(psychologist_user.is_admin)
        self.assertTrue(admin_user.is_admin)

    def test_profile_picture_url_field(self):
        """Test profile picture URL field"""
        valid_url = 'https://example.com/profile.jpg'
        user = User.objects.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent',
            profile_picture_url=valid_url
        )

        self.assertEqual(user.profile_picture_url, valid_url)

    def test_profile_picture_url_can_be_null(self):
        """Test that profile picture URL can be null"""
        user = User.objects.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent'
        )

        self.assertIsNone(user.profile_picture_url)

    def test_user_timezone_field(self):
        """Test user timezone field"""
        timezone_value = 'America/New_York'
        user = User.objects.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent',
            user_timezone=timezone_value
        )

        self.assertEqual(user.user_timezone, timezone_value)

    def test_last_login_date_can_be_null(self):
        """Test that last login date can be null"""
        user = User.objects.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent'
        )

        self.assertIsNone(user.last_login_date)

    def test_last_login_date_can_be_set(self):
        """Test that last login date can be set"""
        login_time = timezone.now()
        user = User.objects.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent',
            last_login_date=login_time
        )

        self.assertEqual(user.last_login_date, login_time)

    def test_model_meta_options(self):
        """Test model meta options"""
        self.assertEqual(User._meta.verbose_name, 'User')
        self.assertEqual(User._meta.verbose_name_plural, 'Users')
        self.assertEqual(User._meta.db_table, 'users')

    def test_username_field_is_email(self):
        """Test that USERNAME_FIELD is set to email"""
        self.assertEqual(User.USERNAME_FIELD, 'email')

    def test_required_fields(self):
        """Test REQUIRED_FIELDS configuration"""
        self.assertEqual(User.REQUIRED_FIELDS, ['user_type'])

    def test_boolean_field_defaults(self):
        """Test boolean field default values"""
        user = User.objects.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent'
        )

        # Test defaults
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_verified)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_boolean_field_override_defaults(self):
        """Test that boolean field defaults can be overridden"""
        user = User.objects.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent',
            is_active=False,
            is_verified=True,
            is_staff=True
        )

        self.assertFalse(user.is_active)
        self.assertTrue(user.is_verified)
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)  # Not overridden

    def test_user_manager_is_custom(self):
        """Test that the model uses our custom manager"""
        from users.managers import UserManager
        self.assertIsInstance(User.objects, UserManager)

    def test_max_length_constraints(self):
        """Test field max length constraints"""
        # Test email max length (should be handled by EmailField)
        long_email = 'a' * 240 + '@example.com'  # Creates a 252 char email
        user = User(
            email=long_email,
            user_type='Parent'
        )

        with self.assertRaises(ValidationError):
            user.full_clean()

        # Test user_timezone max length
        long_timezone = 'A' * 51  # 51 characters, exceeds max_length=50
        user = User(
            email=self.valid_email,
            user_type='Parent',
            user_timezone=long_timezone
        )

        with self.assertRaises(ValidationError):
            user.full_clean()

    def test_user_type_max_length(self):
        """Test user_type field max length"""
        long_user_type = 'A' * 21  # 21 characters, exceeds max_length=20
        user = User(
            email=self.valid_email,
            user_type=long_user_type
        )

        with self.assertRaises(ValidationError):
            user.full_clean()

    def test_email_field_validation(self):
        """Test email field validation"""
        invalid_emails = [
            'invalid',
            '@example.com',
            'test@',
            'test..test@example.com'
        ]

        for invalid_email in invalid_emails:
            with self.subTest(email=invalid_email):
                user = User(
                    email=invalid_email,
                    user_type='Parent'
                )
                with self.assertRaises(ValidationError):
                    user.full_clean()