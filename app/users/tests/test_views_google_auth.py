# tests/test_google_auth.py
import json
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token
from unittest.mock import patch, MagicMock
from google.auth.exceptions import GoogleAuthError

from users.models import User
from users.google_auth_service import GoogleAuthService
from users.exceptions import (
    InvalidGoogleTokenError,
    GoogleUserInfoError,
    EmailAlreadyExistsError,
    GoogleEmailNotVerifiedError,
    UserTypeRequiredError,
    GoogleConfigurationError
)

User = get_user_model()


class GoogleAuthServiceTestCase(TestCase):
    """Test cases for GoogleAuthService business logic"""

    def setUp(self):
        self.valid_google_user_info = {
            'email': 'test@example.com',
            'google_id': 'google123',
            'name': 'Test User',
            'given_name': 'Test',
            'family_name': 'User',
            'picture': 'https://example.com/picture.jpg'
        }

        self.mock_google_response = {
            'email': 'test@example.com',
            'sub': 'google123',
            'name': 'Test User',
            'given_name': 'Test',
            'family_name': 'User',
            'picture': 'https://example.com/picture.jpg',
            'email_verified': True
        }

    @patch('users.google_auth_service.settings')
    @patch('users.google_auth_service.id_token.verify_oauth2_token')
    def test_verify_google_token_success(self, mock_verify, mock_settings):
        """Test successful Google token verification"""
        mock_settings.GOOGLE_OAUTH2_CLIENT_ID = 'test-client-id'
        mock_verify.return_value = self.mock_google_response

        result = GoogleAuthService.verify_google_token('valid-token')

        self.assertEqual(result['email'], 'test@example.com')
        self.assertEqual(result['google_id'], 'google123')
        self.assertEqual(result['name'], 'Test User')
        mock_verify.assert_called_once()

    @patch('users.google_auth_service.settings')
    def test_verify_google_token_no_config(self, mock_settings):
        """Test token verification without Google configuration"""
        mock_settings.GOOGLE_OAUTH2_CLIENT_ID = None

        with self.assertRaises(GoogleConfigurationError):
            GoogleAuthService.verify_google_token('token')

    @patch('users.google_auth_service.settings')
    @patch('users.google_auth_service.id_token.verify_oauth2_token')
    def test_verify_google_token_invalid_token(self, mock_verify, mock_settings):
        """Test verification with invalid Google token"""
        mock_settings.GOOGLE_OAUTH2_CLIENT_ID = 'test-client-id'
        mock_verify.side_effect = GoogleAuthError("Invalid token")

        with self.assertRaises(InvalidGoogleTokenError):
            GoogleAuthService.verify_google_token('invalid-token')


    @patch('users.google_auth_service.settings')
    @patch('users.google_auth_service.id_token.verify_oauth2_token')
    def test_verify_google_token_missing_fields(self, mock_verify, mock_settings):
        """Test verification with missing required fields"""
        mock_settings.GOOGLE_OAUTH2_CLIENT_ID = 'test-client-id'
        mock_response = {'email': 'test@example.com'}  # Missing 'sub' and 'email_verified'
        mock_verify.return_value = mock_response

        with self.assertRaises(GoogleUserInfoError):
            GoogleAuthService.verify_google_token('token')

    def test_authenticate_google_user_existing_with_google_id(self):
        """Test authentication of existing user with Google ID"""
        user = User.objects.create_user(
            email='test@example.com',
            user_type='Parent',
            google_id='google123'
        )

        result_user, is_new = GoogleAuthService.authenticate_google_user(
            self.valid_google_user_info
        )

        self.assertEqual(result_user.id, user.id)
        self.assertFalse(is_new)
        self.assertIsNotNone(result_user.last_login_date)

    def test_authenticate_google_user_existing_without_google_id(self):
        """Test authentication of existing user without Google ID (account linking)"""
        user = User.objects.create_user(
            email='test@example.com',
            user_type='Parent'
        )

        result_user, is_new = GoogleAuthService.authenticate_google_user(
            self.valid_google_user_info
        )

        self.assertEqual(result_user.id, user.id)
        self.assertFalse(is_new)
        self.assertEqual(result_user.google_id, 'google123')
        self.assertTrue(result_user.is_verified)

    def test_authenticate_google_user_google_id_mismatch(self):
        """Test authentication with Google ID mismatch"""
        User.objects.create_user(
            email='test@example.com',
            user_type='Parent',
            google_id='different-google-id'
        )

        with self.assertRaises(InvalidGoogleTokenError):
            GoogleAuthService.authenticate_google_user(self.valid_google_user_info)

    def test_authenticate_google_user_new_user(self):
        """Test authentication of non-existing user"""
        result_user, is_new = GoogleAuthService.authenticate_google_user(
            self.valid_google_user_info
        )

        self.assertIsNone(result_user)
        self.assertTrue(is_new)

    def test_register_google_user_parent(self):
        """Test Google user registration as Parent"""
        user = GoogleAuthService.register_google_user(
            self.valid_google_user_info, 'Parent'
        )

        self.assertEqual(user.email, 'test@example.com')
        self.assertEqual(user.user_type, 'Parent')
        self.assertEqual(user.google_id, 'google123')
        self.assertTrue(user.is_verified)
        self.assertTrue(user.is_active)

    def test_register_google_user_psychologist(self):
        """Test Google user registration as Psychologist"""
        user = GoogleAuthService.register_google_user(
            self.valid_google_user_info, 'Psychologist'
        )

        self.assertEqual(user.user_type, 'Psychologist')

    def test_register_google_user_invalid_type(self):
        """Test Google user registration with invalid user type"""
        with self.assertRaises(UserTypeRequiredError):
            GoogleAuthService.register_google_user(
                self.valid_google_user_info, 'InvalidType'
            )

    def test_register_google_user_existing_email(self):
        """Test Google user registration with existing email"""
        User.objects.create_user(
            email='test@example.com',
            user_type='Parent'
        )

        with self.assertRaises(EmailAlreadyExistsError):
            GoogleAuthService.register_google_user(
                self.valid_google_user_info, 'Parent'
            )

    @patch.object(GoogleAuthService, 'verify_google_token')
    @patch.object(GoogleAuthService, 'authenticate_google_user')
    def test_google_login_or_register_existing_user(self, mock_auth, mock_verify):
        """Test complete flow for existing user"""
        mock_verify.return_value = self.valid_google_user_info

        existing_user = User.objects.create_user(
            email='test@example.com',
            user_type='Parent',
            google_id='google123'
        )
        mock_auth.return_value = (existing_user, False)

        user, is_new, action = GoogleAuthService.google_login_or_register('token')

        self.assertEqual(user.id, existing_user.id)
        self.assertFalse(is_new)
        self.assertEqual(action, 'login')

    @patch.object(GoogleAuthService, 'verify_google_token')
    @patch.object(GoogleAuthService, 'authenticate_google_user')
    @patch.object(GoogleAuthService, 'register_google_user')
    def test_google_login_or_register_new_user(self, mock_register, mock_auth, mock_verify):
        """Test complete flow for new user"""
        mock_verify.return_value = self.valid_google_user_info
        mock_auth.return_value = (None, True)

        new_user = User.objects.create_user(
            email='test@example.com',
            user_type='Parent',
            google_id='google123'
        )
        mock_register.return_value = new_user

        user, is_new, action = GoogleAuthService.google_login_or_register(
            'token', 'Parent'
        )

        self.assertEqual(user.id, new_user.id)
        self.assertTrue(is_new)
        self.assertEqual(action, 'registration')

    @patch.object(GoogleAuthService, 'verify_google_token')
    @patch.object(GoogleAuthService, 'authenticate_google_user')
    def test_google_login_or_register_new_user_no_type(self, mock_auth, mock_verify):
        """Test complete flow for new user without user type"""
        mock_verify.return_value = self.valid_google_user_info
        mock_auth.return_value = (None, True)

        with self.assertRaises(UserTypeRequiredError):
            GoogleAuthService.google_login_or_register('token')


class GoogleAuthViewTestCase(TestCase):
    """Test cases for Google Auth API endpoints"""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse('auth-google-auth')  # Adjust URL name as needed
        self.link_url = reverse('auth-link-google')  # Adjust URL name as needed
        self.unlink_url = reverse('auth-unlink-google')  # Adjust URL name as needed

        self.valid_payload = {
            'google_token': 'valid.google.token',
            'user_type': 'Parent'
        }

    @patch('users.google_auth_service.GoogleAuthService.google_login_or_register')
    def test_google_auth_new_user_success(self, mock_service):
        """Test successful Google authentication for new user"""
        new_user = User.objects.create_user(
            email='test@example.com',
            user_type='Parent',
            google_id='google123'
        )
        mock_service.return_value = (new_user, True, 'registration')

        response = self.client.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('user', response.data)
        self.assertIn('token', response.data)
        self.assertTrue(response.data['is_new_user'])
        self.assertIn('Google registration successful', response.data['message'])

    @patch('users.google_auth_service.GoogleAuthService.google_login_or_register')
    def test_google_auth_existing_user_success(self, mock_service):
        """Test successful Google authentication for existing user"""
        existing_user = User.objects.create_user(
            email='test@example.com',
            user_type='Parent',
            google_id='google123'
        )
        mock_service.return_value = (existing_user, False, 'login')

        response = self.client.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('user', response.data)
        self.assertIn('token', response.data)
        self.assertFalse(response.data['is_new_user'])
        self.assertIn('Google login successful', response.data['message'])

    @patch('users.google_auth_service.GoogleAuthService.google_login_or_register')
    def test_google_auth_user_type_required(self, mock_service):
        """Test Google authentication when user type is required"""
        mock_service.side_effect = UserTypeRequiredError("User type required")

        response = self.client.post(self.url, {'google_token': 'valid.google.token'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('requires_user_type', response.data)
        self.assertTrue(response.data['requires_user_type'])
        self.assertIn('available_types', response.data)

    @patch('users.google_auth_service.GoogleAuthService.google_login_or_register')
    def test_google_auth_email_exists(self, mock_service):
        """Test Google authentication when email exists with different provider"""
        mock_service.side_effect = EmailAlreadyExistsError(
            'test@example.com', 'password'
        )

        response = self.client.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('email', response.data)
        self.assertIn('existing_provider', response.data)

    @patch('users.google_auth_service.GoogleAuthService.google_login_or_register')
    def test_google_auth_invalid_token(self, mock_service):
        """Test Google authentication with invalid token"""
        mock_service.side_effect = InvalidGoogleTokenError("Invalid token")

        response = self.client.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid or expired Google token', response.data['error'])

    @patch('users.google_auth_service.GoogleAuthService.google_login_or_register')
    def test_google_auth_unverified_email(self, mock_service):
        """Test Google authentication with unverified email"""
        mock_service.side_effect = GoogleEmailNotVerifiedError("Email not verified")

        response = self.client.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Google account email is not verified', response.data['error'])

    @patch('users.google_auth_service.GoogleAuthService.google_login_or_register')
    def test_google_auth_configuration_error(self, mock_service):
        """Test Google authentication when service is unavailable"""
        mock_service.side_effect = GoogleConfigurationError("Service unavailable")

        response = self.client.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn('Google authentication is not available', response.data['error'])

    def test_google_auth_invalid_serializer(self):
        """Test Google authentication with invalid data"""
        invalid_payload = {
            'google_token': '',  # Empty token
            'user_type': 'InvalidType'  # Invalid user type
        }

        response = self.client.post(self.url, invalid_payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('google_token', response.data)

    def test_google_auth_missing_token(self):
        """Test Google authentication without token"""
        response = self.client.post(self.url, {'user_type': 'Parent'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('google_token', response.data)

    def test_google_link_account_unauthorized(self):
        """Test linking Google account without authentication"""
        response = self.client.post(self.link_url, {
            'google_token': 'valid.google.token',
            'password': 'testpass'
        })

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_google_unlink_account_unauthorized(self):
        """Test unlinking Google account without authentication"""
        response = self.client.post(self.unlink_url, {
            'password': 'testpass'
        })

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class GoogleAuthIntegrationTestCase(TestCase):
    """Integration tests for Google Auth flow"""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse('auth-google-auth')

    @patch('users.google_auth_service.settings')
    @patch('users.google_auth_service.id_token.verify_oauth2_token')
    def test_complete_google_registration_flow(self, mock_verify, mock_settings):
        """Test complete Google registration flow end-to-end"""
        mock_settings.GOOGLE_OAUTH2_CLIENT_ID = 'test-client-id'
        mock_verify.return_value = {
            'email': 'newuser@example.com',
            'sub': 'google123',
            'name': 'New User',
            'given_name': 'New',
            'family_name': 'User',
            'picture': 'https://example.com/pic.jpg',
            'email_verified': True
        }

        payload = {
            'google_token': 'valid.google.token',
            'user_type': 'Parent'
        }

        response = self.client.post(self.url, payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['is_new_user'])

        # Verify user was created
        user = User.objects.get(email='newuser@example.com')
        self.assertEqual(user.user_type, 'Parent')
        self.assertEqual(user.google_id, 'google123')
        self.assertTrue(user.is_verified)
        self.assertTrue(user.is_active)

        # Verify token was created
        self.assertIn('token', response.data)
        token = Token.objects.get(key=response.data['token'])
        self.assertEqual(token.user, user)

    @patch('users.google_auth_service.settings')
    @patch('users.google_auth_service.id_token.verify_oauth2_token')
    def test_complete_google_login_flow(self, mock_verify, mock_settings):
        """Test complete Google login flow for existing user"""
        # Create existing user
        existing_user = User.objects.create_user(
            email='existing@example.com',
            user_type='Psychologist',
            google_id='google456'
        )

        mock_settings.GOOGLE_OAUTH2_CLIENT_ID = 'test-client-id'
        mock_verify.return_value = {
            'email': 'existing@example.com',
            'sub': 'google456',
            'name': 'Existing User',
            'email_verified': True
        }

        payload = {
            'google_token': 'valid.google.token'
        }

        response = self.client.post(self.url, payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_new_user'])

        # Verify user data
        self.assertEqual(response.data['user']['email'], 'existing@example.com')
        self.assertEqual(response.data['user']['user_type'], 'Psychologist')

        # Verify last login was updated
        existing_user.refresh_from_db()
        self.assertIsNotNone(existing_user.last_login_date)


class GoogleAuthSerializerTestCase(TestCase):
    """Test cases for Google Auth serializers"""

    def test_google_auth_serializer_valid_data(self):
        """Test GoogleAuthSerializer with valid data"""
        from users.serializers import GoogleAuthSerializer

        data = {
            'google_token': 'valid.google.token',
            'user_type': 'Parent'
        }

        serializer = GoogleAuthSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['google_token'], 'valid.google.token')
        self.assertEqual(serializer.validated_data['user_type'], 'Parent')

    def test_google_auth_serializer_invalid_token_format(self):
        """Test GoogleAuthSerializer with invalid token format"""
        from users.serializers import GoogleAuthSerializer

        data = {
            'google_token': 'invalid-token',  # Should have 3 parts
            'user_type': 'Parent'
        }

        serializer = GoogleAuthSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('google_token', serializer.errors)

    def test_google_auth_serializer_empty_token(self):
        """Test GoogleAuthSerializer with empty token"""
        from users.serializers import GoogleAuthSerializer

        data = {
            'google_token': '',
            'user_type': 'Parent'
        }

        serializer = GoogleAuthSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('google_token', serializer.errors)

    def test_google_auth_serializer_invalid_user_type(self):
        """Test GoogleAuthSerializer with invalid user type"""
        from users.serializers import GoogleAuthSerializer

        data = {
            'google_token': 'valid.google.token',
            'user_type': 'InvalidType'
        }

        serializer = GoogleAuthSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('user_type', serializer.errors)

    def test_google_auth_serializer_no_user_type(self):
        """Test GoogleAuthSerializer without user type (should be valid)"""
        from users.serializers import GoogleAuthSerializer

        data = {
            'google_token': 'valid.google.token'
        }

        serializer = GoogleAuthSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertNotIn('user_type', serializer.validated_data)


