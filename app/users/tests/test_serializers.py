"""
Tests for users app serializers
"""
from unittest.mock import patch, Mock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIRequestFactory
from rest_framework import serializers

from users.serializers import (
    UserSerializer,
    UserRegistrationSerializer,
    LoginSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer
)

User = get_user_model()


class UserSerializerTests(TestCase):
    """Test suite for UserSerializer"""

    def setUp(self):
        self.user_data = {
            'email': 'test@example.com',
            'user_type': 'Parent',
            'is_active': True,
            'is_verified': False,
            'profile_picture_url': 'https://example.com/pic.jpg',
            'user_timezone': 'UTC'
        }
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            user_type='Parent'
        )

    def test_serialization(self):
        """Test that user data is properly serialized"""
        serializer = UserSerializer(instance=self.user)
        data = serializer.data

        # Check that all expected fields are present
        expected_fields = [
            'id', 'email', 'user_type', 'is_active', 'is_verified',
            'profile_picture_url', 'user_timezone', 'registration_date',
            'last_login_date'
        ]
        for field in expected_fields:
            self.assertIn(field, data)

        # Check values
        self.assertEqual(data['email'], self.user.email)
        self.assertEqual(data['user_type'], self.user.user_type)
        self.assertEqual(data['is_active'], self.user.is_active)

    def test_read_only_fields(self):
        """Test that read-only fields cannot be updated"""
        serializer = UserSerializer()
        read_only_fields = ['id', 'registration_date', 'last_login_date', 'is_verified']

        for field in read_only_fields:
            self.assertIn(field, serializer.Meta.read_only_fields)

    def test_partial_update(self):
        """Test partial update of user data"""
        update_data = {'user_timezone': 'America/New_York'}
        serializer = UserSerializer(instance=self.user, data=update_data, partial=True)

        self.assertTrue(serializer.is_valid())
        updated_user = serializer.save()
        self.assertEqual(updated_user.user_timezone, 'America/New_York')


class UserRegistrationSerializerTests(TestCase):
    """Test suite for UserRegistrationSerializer"""

    def setUp(self):
        self.valid_data = {
            'email': 'newuser@example.com',
            'user_type': 'Parent',
            'password': 'strongpassword123',
            'password_confirm': 'strongpassword123',
            'user_timezone': 'UTC'
        }

    @patch('users.serializers.AuthenticationService.register_user')
    def test_valid_registration(self, mock_register):
        """Test successful user registration"""
        mock_user = Mock()
        mock_register.return_value = mock_user

        serializer = UserRegistrationSerializer(data=self.valid_data)
        self.assertTrue(serializer.is_valid())

        user = serializer.save()
        self.assertEqual(user, mock_user)
        mock_register.assert_called_once_with(
            email='newuser@example.com',
            user_type='Parent',
            password='strongpassword123',
            user_timezone='UTC'
        )

    def test_password_mismatch(self):
        """Test validation error when passwords don't match"""
        data = self.valid_data.copy()
        data['password_confirm'] = 'differentpassword'

        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)
        self.assertEqual(
            serializer.errors['non_field_errors'][0],
            "Passwords do not match"
        )

    def test_missing_email(self):
        """Test validation error when email is missing"""
        data = self.valid_data.copy()
        del data['email']

        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('email', serializer.errors)

    def test_missing_user_type(self):
        """Test validation error when user_type is missing"""
        data = self.valid_data.copy()
        del data['user_type']

        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('user_type', serializer.errors)

    def test_short_password(self):
        """Test validation error for password too short"""
        data = self.valid_data.copy()
        data['password'] = '123'
        data['password_confirm'] = '123'

        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('password', serializer.errors)

    def test_invalid_email_format(self):
        """Test validation error for invalid email format"""
        data = self.valid_data.copy()
        data['email'] = 'invalid-email'

        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('email', serializer.errors)

    def test_password_confirm_not_in_validated_data(self):
        """Test that password_confirm is removed from validated_data"""
        serializer = UserRegistrationSerializer(data=self.valid_data)
        self.assertTrue(serializer.is_valid())

        # password_confirm should be popped during validation
        self.assertNotIn('password_confirm', serializer.validated_data)
        self.assertIn('password', serializer.validated_data)


class LoginSerializerTests(TestCase):
    """Test suite for LoginSerializer"""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            user_type='Parent'
        )
        self.valid_data = {
            'email': 'test@example.com',
            'password': 'testpass123'
        }

    def test_valid_login(self):
        """Test successful login with valid credentials"""
        request = self.factory.post('/login/')
        serializer = LoginSerializer(
            data=self.valid_data,
            context={'request': request}
        )

        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['user'], self.user)

    def test_invalid_password(self):
        """Test login failure with incorrect password"""
        data = self.valid_data.copy()
        data['password'] = 'wrongpassword'

        request = self.factory.post('/login/')
        serializer = LoginSerializer(
            data=data,
            context={'request': request}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)
        self.assertEqual(
            serializer.errors['non_field_errors'][0],
            "Invalid email or password"
        )

    def test_invalid_email(self):
        """Test login failure with non-existent email"""
        data = self.valid_data.copy()
        data['email'] = 'nonexistent@example.com'

        request = self.factory.post('/login/')
        serializer = LoginSerializer(
            data=data,
            context={'request': request}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)

    def test_inactive_user(self):
        """Test login failure for inactive user"""
        self.user.is_active = False
        self.user.save()

        request = self.factory.post('/login/')
        serializer = LoginSerializer(
            data=self.valid_data,
            context={'request': request}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)
        # Django's authenticate() returns None for inactive users,
        # so we get "Invalid email or password" instead of "User account is disabled"
        self.assertEqual(
            serializer.errors['non_field_errors'][0],
            "Invalid email or password"
        )

    def test_missing_email(self):
        """Test validation error when email is missing"""
        data = {'password': 'testpass123'}

        request = self.factory.post('/login/')
        serializer = LoginSerializer(
            data=data,
            context={'request': request}
        )

        self.assertFalse(serializer.is_valid())
        # Field-level validation occurs before custom validate() method
        self.assertIn('email', serializer.errors)
        self.assertEqual(
            serializer.errors['email'][0],
            "This field is required."
        )

    def test_missing_password(self):
        """Test validation error when password is missing"""
        data = {'email': 'test@example.com'}

        request = self.factory.post('/login/')
        serializer = LoginSerializer(
            data=data,
            context={'request': request}
        )

        self.assertFalse(serializer.is_valid())
        # Field-level validation occurs before custom validate() method
        self.assertIn('password', serializer.errors)
        self.assertEqual(
            serializer.errors['password'][0],
            "This field is required."
        )

    def test_empty_credentials(self):
        """Test validation error with empty credentials"""
        data = {'email': '', 'password': ''}

        request = self.factory.post('/login/')
        serializer = LoginSerializer(
            data=data,
            context={'request': request}
        )

        self.assertFalse(serializer.is_valid())
        # Empty strings pass field validation but fail in custom validate()
        self.assertEqual(
            serializer.errors['email'][0],"This field may not be blank."
        )
        self.assertEqual(
            serializer.errors['password'][0],"This field may not be blank."
        )



class PasswordResetRequestSerializerTests(TestCase):
    """Test suite for PasswordResetRequestSerializer"""

    @patch('users.serializers.AuthenticationService.request_password_reset')
    def test_valid_email(self, mock_reset_request):
        """Test password reset request with valid email"""
        mock_reset_request.return_value = True

        data = {'email': 'test@example.com'}
        serializer = PasswordResetRequestSerializer(data=data)

        self.assertTrue(serializer.is_valid())
        result = serializer.save()

        mock_reset_request.assert_called_once_with('test@example.com')
        self.assertTrue(result)

    def test_invalid_email_format(self):
        """Test validation error for invalid email format"""
        data = {'email': 'invalid-email'}
        serializer = PasswordResetRequestSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn('email', serializer.errors)

    def test_missing_email(self):
        """Test validation error when email is missing"""
        data = {}
        serializer = PasswordResetRequestSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn('email', serializer.errors)

    @patch('users.serializers.AuthenticationService.request_password_reset')
    def test_service_delegation(self, mock_reset_request):
        """Test that the serializer properly delegates to the service"""
        mock_reset_request.return_value = False

        data = {'email': 'nonexistent@example.com'}
        serializer = PasswordResetRequestSerializer(data=data)

        self.assertTrue(serializer.is_valid())
        result = serializer.save()

        mock_reset_request.assert_called_once_with('nonexistent@example.com')
        self.assertFalse(result)


class PasswordResetConfirmSerializerTests(TestCase):
    """Test suite for PasswordResetConfirmSerializer"""

    def setUp(self):
        self.valid_data = {
            'uidb64': 'valid-uid',
            'token': 'valid-token',
            'password': 'newstrongpassword123',
            'password_confirm': 'newstrongpassword123'
        }

    @patch('users.serializers.AuthenticationService.reset_password')
    def test_valid_password_reset(self, mock_reset_password):
        """Test successful password reset"""
        mock_user = Mock()
        mock_reset_password.return_value = (mock_user, "Password reset successful")

        serializer = PasswordResetConfirmSerializer(data=self.valid_data)
        self.assertTrue(serializer.is_valid())

        result = serializer.save()

        mock_reset_password.assert_called_once_with(
            'valid-uid', 'valid-token', 'newstrongpassword123'
        )
        self.assertEqual(result['user'], mock_user)
        self.assertEqual(result['message'], "Password reset successful")

    def test_password_mismatch(self):
        """Test validation error when passwords don't match"""
        data = self.valid_data.copy()
        data['password_confirm'] = 'differentpassword'

        serializer = PasswordResetConfirmSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('password_confirm', serializer.errors)

    @patch('django.contrib.auth.password_validation.validate_password')
    def test_weak_password_validation(self, mock_validate_password):
        """Test validation error for weak password"""
        mock_validate_password.side_effect = ValidationError([
            "This password is too common.",
            "This password is entirely numeric."
        ])

        data = self.valid_data.copy()
        data['password'] = '123456789'
        data['password_confirm'] = '123456789'

        serializer = PasswordResetConfirmSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('password', serializer.errors)
        self.assertIn("This password is too common.", serializer.errors['password'])

    def test_short_password(self):
        """Test validation error for password too short"""
        data = self.valid_data.copy()
        data['password'] = '123'
        data['password_confirm'] = '123'

        serializer = PasswordResetConfirmSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('password', serializer.errors)

    def test_missing_required_fields(self):
        """Test validation error when required fields are missing"""
        incomplete_data = {'password': 'newpassword123'}

        serializer = PasswordResetConfirmSerializer(data=incomplete_data)
        self.assertFalse(serializer.is_valid())

        required_fields = ['uidb64', 'token', 'password_confirm']
        for field in required_fields:
            self.assertIn(field, serializer.errors)

    @patch('users.serializers.AuthenticationService.reset_password')
    def test_invalid_token_handling(self, mock_reset_password):
        """Test handling of invalid reset token"""
        mock_reset_password.return_value = (None, "Invalid or expired token")

        serializer = PasswordResetConfirmSerializer(data=self.valid_data)
        self.assertTrue(serializer.is_valid())

        with self.assertRaises(serializers.ValidationError):
            serializer.save()

        mock_reset_password.assert_called_once_with(
            'valid-uid', 'valid-token', 'newstrongpassword123'
        )

    def test_password_confirm_not_in_validated_data(self):
        """Test that password_confirm is removed from validated_data"""
        serializer = PasswordResetConfirmSerializer(data=self.valid_data)
        self.assertTrue(serializer.is_valid())

        # password_confirm should be popped during validation
        self.assertNotIn('password_confirm', serializer.validated_data)
        self.assertIn('password', serializer.validated_data)
        self.assertIn('uidb64', serializer.validated_data)
        self.assertIn('token', serializer.validated_data)

    @patch('users.serializers.AuthenticationService.reset_password')
    def test_service_error_propagation(self, mock_reset_password):
        """Test that service errors are properly propagated"""
        mock_reset_password.return_value = (None, "Token has expired")

        serializer = PasswordResetConfirmSerializer(data=self.valid_data)
        self.assertTrue(serializer.is_valid())

        with self.assertRaises(serializers.ValidationError) as context:
            serializer.save()

        # The error message from the service should be in the ValidationError
        self.assertEqual(str(context.exception.detail[0]), "Token has expired")