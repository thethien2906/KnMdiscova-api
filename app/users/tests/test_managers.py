from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from unittest.mock import patch


User = get_user_model()


class UserManagerTest(TestCase):
    """Test cases for UserManager"""

    def setUp(self):
        """Set up test data"""
        self.manager = User.objects
        self.valid_email = 'test@example.com'
        self.valid_password = 'testpassword123'

    def test_email_validator_with_valid_email(self):
        """Test email validator with valid email"""
        # Should not raise any exception
        try:
            self.manager.email_validator(self.valid_email)
        except ValueError:
            self.fail("email_validator raised ValueError unexpectedly!")

    def test_email_validator_with_invalid_email(self):
        """Test email validator with invalid email"""
        invalid_emails = [
            'invalid_email',
            '@example.com',
            'test@',
            'test..test@example.com',
            '',
            'test@.com',
            'test@com',
        ]

        for invalid_email in invalid_emails:
            with self.subTest(email=invalid_email):
                with self.assertRaises(ValueError) as context:
                    self.manager.email_validator(invalid_email)
                self.assertIn('Invalid email address', str(context.exception))

    def test_create_user_success(self):
        """Test creating a user successfully"""
        user = self.manager.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent'
        )

        self.assertEqual(user.email, self.valid_email)
        self.assertTrue(user.check_password(self.valid_password))
        self.assertEqual(user.user_type, 'Parent')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_user_without_email(self):
        """Test creating user without email raises ValueError"""
        with self.assertRaises(ValueError) as context:
            self.manager.create_user(
                email='',
                password=self.valid_password
            )
        self.assertIn('The Email field must be set', str(context.exception))

        with self.assertRaises(ValueError) as context:
            self.manager.create_user(
                email=None,
                password=self.valid_password
            )
        self.assertIn('The Email field must be set', str(context.exception))

    def test_create_user_with_invalid_email(self):
        """Test creating user with invalid email"""
        with self.assertRaises(ValueError) as context:
            self.manager.create_user(
                email='invalid_email',
                password=self.valid_password
            )
        self.assertIn('Invalid email address', str(context.exception))

    def test_create_user_email_normalization(self):
        """Test that email is normalized when creating user"""
        email = 'Test.User+tag@EXAMPLE.COM'
        user = self.manager.create_user(
            email=email,
            password=self.valid_password,
            user_type='Parent'
        )

        # Django normalizes email to lowercase domain
        self.assertEqual(user.email, 'Test.User+tag@example.com')

    def test_create_user_with_extra_fields(self):
        """Test creating user with extra fields"""
        user = self.manager.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent',
            is_verified=True,
            user_timezone='America/New_York'
        )

        self.assertEqual(user.email, self.valid_email)
        self.assertEqual(user.user_type, 'Parent')
        self.assertTrue(user.is_verified)
        self.assertEqual(user.user_timezone, 'America/New_York')

    def test_create_superuser_success(self):
        """Test creating superuser successfully"""
        user = self.manager.create_superuser(
            email=self.valid_email,
            password=self.valid_password
        )

        self.assertEqual(user.email, self.valid_email)
        self.assertTrue(user.check_password(self.valid_password))
        self.assertEqual(user.user_type, 'Admin')
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_create_superuser_without_is_staff(self):
        """Test creating superuser with is_staff=False raises ValueError"""
        with self.assertRaises(ValueError) as context:
            self.manager.create_superuser(
                email=self.valid_email,
                password=self.valid_password,
                is_staff=False
            )
        self.assertIn('Superuser must have is_staff=True', str(context.exception))

    def test_create_superuser_without_is_superuser(self):
        """Test creating superuser with is_superuser=False raises ValueError"""
        with self.assertRaises(ValueError) as context:
            self.manager.create_superuser(
                email=self.valid_email,
                password=self.valid_password,
                is_superuser=False
            )
        self.assertIn('Superuser must have is_superuser=True', str(context.exception))

    def test_create_superuser_with_extra_fields(self):
        """Test creating superuser with extra fields"""
        user = self.manager.create_superuser(
            email=self.valid_email,
            password=self.valid_password,
            user_timezone='Europe/London'
        )

        self.assertEqual(user.email, self.valid_email)
        self.assertEqual(user.user_type, 'Admin')
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertEqual(user.user_timezone, 'Europe/London')

    def test_create_parent_success(self):
        """Test creating parent user successfully"""
        user = self.manager.create_parent(
            email=self.valid_email,
            password=self.valid_password
        )

        self.assertEqual(user.email, self.valid_email)
        self.assertTrue(user.check_password(self.valid_password))
        self.assertEqual(user.user_type, 'Parent')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_verified)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_parent_with_extra_fields(self):
        """Test creating parent with extra fields"""
        user = self.manager.create_parent(
            email=self.valid_email,
            password=self.valid_password,
            is_verified=True,
            user_timezone='Asia/Tokyo'
        )

        self.assertEqual(user.email, self.valid_email)
        self.assertEqual(user.user_type, 'Parent')
        self.assertTrue(user.is_verified)  # Extra field should override default
        self.assertEqual(user.user_timezone, 'Asia/Tokyo')

    def test_create_psychologist_success(self):
        """Test creating psychologist user successfully"""
        user = self.manager.create_psychologist(
            email=self.valid_email,
            password=self.valid_password
        )

        self.assertEqual(user.email, self.valid_email)
        self.assertTrue(user.check_password(self.valid_password))
        self.assertEqual(user.user_type, 'Psychologist')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_verified)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_psychologist_with_extra_fields(self):
        """Test creating psychologist with extra fields"""
        user = self.manager.create_psychologist(
            email=self.valid_email,
            password=self.valid_password,
            is_verified=True,
            user_timezone='Australia/Sydney'
        )

        self.assertEqual(user.email, self.valid_email)
        self.assertEqual(user.user_type, 'Psychologist')
        self.assertTrue(user.is_verified)  # Extra field should override default
        self.assertEqual(user.user_timezone, 'Australia/Sydney')

    def test_create_parent_without_password(self):
        """Test creating parent without password"""
        user = self.manager.create_parent(email=self.valid_email)

        self.assertEqual(user.email, self.valid_email)
        self.assertEqual(user.user_type, 'Parent')
        self.assertFalse(user.has_usable_password())

    def test_create_psychologist_without_password(self):
        """Test creating psychologist without password"""
        user = self.manager.create_psychologist(email=self.valid_email)

        self.assertEqual(user.email, self.valid_email)
        self.assertEqual(user.user_type, 'Psychologist')
        self.assertFalse(user.has_usable_password())

    def test_duplicate_email_raises_integrity_error(self):
        """Test that creating users with duplicate emails raises IntegrityError"""
        self.manager.create_user(
            email=self.valid_email,
            password=self.valid_password,
            user_type='Parent'
        )

        with self.assertRaises(IntegrityError):
            self.manager.create_user(
                email=self.valid_email,
                password='anotherpassword',
                user_type='Psychologist'
            )

    @patch('users.managers.validate_email')
    def test_email_validator_with_validation_error(self, mock_validate_email):
        """Test email validator when validate_email raises ValidationError"""
        mock_validate_email.side_effect = ValidationError('Invalid email')

        with self.assertRaises(ValueError) as context:
            self.manager.email_validator('test@example.com')

        self.assertIn('Invalid email address', str(context.exception))
        mock_validate_email.assert_called_once_with('test@example.com')