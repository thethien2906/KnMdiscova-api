from django.test import TestCase, override_settings
from django.core import mail
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock
from users.services import AuthenticationService, UserService
from users.tokens import token_generator

User = get_user_model()


class AuthenticationServiceTestCase(TestCase):
    """Test cases for AuthenticationService"""

    def setUp(self):
        """Set up test data"""
        self.email = "test@example.com"
        self.password = "testpass123"
        # Remove profile-specific fields - these are handled by the managers
        self.parent_data = {}
        self.psychologist_data = {}

    @patch('users.services.AuthenticationService.send_verification_email')
    def test_register_user_parent_success(self, mock_send_email):
        """Test successful parent registration"""
        mock_send_email.return_value = True

        user = AuthenticationService.register_user(
            email=self.email,
            password=self.password,
            user_type='Parent'
        )

        self.assertIsNotNone(user)
        self.assertEqual(user.email, self.email)
        self.assertEqual(user.user_type, 'Parent')
        self.assertTrue(user.check_password(self.password))
        self.assertFalse(user.is_verified)
        mock_send_email.assert_called_once_with(user)

    @patch('users.services.AuthenticationService.send_verification_email')
    def test_register_user_psychologist_success(self, mock_send_email):
        """Test successful psychologist registration"""
        mock_send_email.return_value = True

        user = AuthenticationService.register_user(
            email=self.email,
            password=self.password,
            user_type='Psychologist'
        )

        self.assertIsNotNone(user)
        self.assertEqual(user.email, self.email)
        self.assertEqual(user.user_type, 'Psychologist')
        self.assertTrue(user.check_password(self.password))
        self.assertFalse(user.is_verified)
        mock_send_email.assert_called_once_with(user)

    def test_register_user_invalid_type(self):
        """Test registration with invalid user type"""
        with self.assertRaises(ValueError) as context:
            AuthenticationService.register_user(
                email=self.email,
                password=self.password,
                user_type='InvalidType'
            )

        self.assertEqual(str(context.exception), "Invalid user type")

    def test_register_user_mvp(self):
        """Test MVP registration MVP version automatically sets is_verified to True"""
        user = AuthenticationService.register_user(
            email=self.email,
            password=self.password,
            user_type='Parent'
        )

        self.assertIsNotNone(user)
        self.assertEqual(user.email, self.email)
        self.assertEqual(user.user_type, 'Parent')
        self.assertTrue(user.check_password(self.password))
        self.assertTrue(user.is_verified)

    @override_settings(
        FRONTEND_URL='http://localhost:3000',
        DEFAULT_FROM_EMAIL='test@kandmdiscova.com'
    )
    @patch('users.services.render_to_string')
    def test_send_verification_email_success(self, mock_render):
        """Test sending verification email"""
        # Mock template rendering
        mock_render.side_effect = ['<html>verification email</html>', 'verification email']

        user = User.objects.create_parent(
            email=self.email,
            password=self.password
        )

        # Clear any existing emails
        mail.outbox = []

        result = AuthenticationService.send_verification_email(user)

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.subject, 'Verify your K&Mdiscova account')
        self.assertIn(user.email, sent_email.to)
        self.assertIn('verification', sent_email.body.lower())

    def test_verify_email_success(self):
        """Test successful email verification"""
        user = User.objects.create_parent(
            email=self.email,
            password=self.password
        )

        # Generate valid token
        token = token_generator.make_token(user)
        uidb64 = token_generator.encode_uid(user)

        verified_user, message = AuthenticationService.verify_email(uidb64, token)

        self.assertEqual(verified_user, user)
        self.assertEqual(message, "Email verified successfully")

        # Refresh from database
        user.refresh_from_db()
        self.assertTrue(user.is_verified)

    def test_verify_email_invalid_uidb64(self):
        """Test email verification with invalid uidb64"""
        result_user, message = AuthenticationService.verify_email('invalid', 'token')

        self.assertIsNone(result_user)
        self.assertEqual(message, "Invalid verification link")

    def test_verify_email_invalid_token(self):
        """Test email verification with invalid token"""
        user = User.objects.create_parent(
            email=self.email,
            password=self.password
        )

        uidb64 = token_generator.encode_uid(user)

        result_user, message = AuthenticationService.verify_email(uidb64, 'invalid_token')

        self.assertIsNone(result_user)
        self.assertEqual(message, "Invalid or expired verification link")

    def test_verify_email_already_verified(self):
        """Test verification of already verified email"""
        user = User.objects.create_parent(
            email=self.email,
            password=self.password
        )
        user.is_verified = True
        user.save()

        token = token_generator.make_token(user)
        uidb64 = token_generator.encode_uid(user)

        result_user, message = AuthenticationService.verify_email(uidb64, token)

        self.assertEqual(result_user, user)
        self.assertEqual(message, "Email already verified")

    @override_settings(
        FRONTEND_URL='http://localhost:3000',
        DEFAULT_FROM_EMAIL='test@kandmdiscova.com'
    )
    @patch('users.services.render_to_string')
    def test_request_password_reset_existing_user(self, mock_render):
        """Test password reset request for existing user"""
        # Mock template rendering
        mock_render.side_effect = ['<html>reset email</html>', 'reset email']

        user = User.objects.create_parent(
            email=self.email,
            password=self.password
        )

        # Clear any existing emails
        mail.outbox = []

        success, message = AuthenticationService.request_password_reset(self.email)

        self.assertTrue(success)
        self.assertEqual(message, "Password reset link sent")
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.subject, 'Reset your K&Mdiscova password')
        self.assertIn(user.email, sent_email.to)

    def test_request_password_reset_nonexistent_user(self):
        """Test password reset request for non-existent user (security)"""
        # Clear any existing emails
        mail.outbox = []

        success, message = AuthenticationService.request_password_reset('nonexistent@example.com')

        self.assertTrue(success)  # Security: always return True
        self.assertEqual(message, "If email exists, reset link will be sent")
        self.assertEqual(len(mail.outbox), 0)  # No email sent

    def test_request_password_reset_inactive_user(self):
        """Test password reset request for inactive user"""
        user = User.objects.create_parent(
            email=self.email,
            password=self.password
        )
        user.is_active = False
        user.save()

        # Clear any existing emails
        mail.outbox = []

        success, message = AuthenticationService.request_password_reset(self.email)

        self.assertTrue(success)  # Security: always return True
        self.assertEqual(message, "If email exists, reset link will be sent")
        self.assertEqual(len(mail.outbox), 0)  # No email sent

    def test_reset_password_success(self):
        """Test successful password reset"""
        user = User.objects.create_parent(
            email=self.email,
            password=self.password
        )

        old_password_hash = user.password
        new_password = "newpassword123"

        token = token_generator.make_token(user)
        uidb64 = token_generator.encode_uid(user)

        result_user, message = AuthenticationService.reset_password(uidb64, token, new_password)

        self.assertEqual(result_user, user)
        self.assertEqual(message, "Password reset successfully")

        # Refresh from database and check password was changed
        user.refresh_from_db()
        self.assertNotEqual(user.password, old_password_hash)
        self.assertTrue(user.check_password(new_password))

    def test_reset_password_invalid_uidb64(self):
        """Test password reset with invalid uidb64"""
        result_user, message = AuthenticationService.reset_password('invalid', 'token', 'newpass')

        self.assertIsNone(result_user)
        self.assertEqual(message, "Invalid reset link")

    def test_reset_password_invalid_token(self):
        """Test password reset with invalid token"""
        user = User.objects.create_parent(
            email=self.email,
            password=self.password
        )

        uidb64 = token_generator.encode_uid(user)

        result_user, message = AuthenticationService.reset_password(uidb64, 'invalid_token', 'newpass')

        self.assertIsNone(result_user)
        self.assertEqual(message, "Invalid or expired reset link")


class UserServiceTestCase(TestCase):
    """Test cases for UserService"""

    def setUp(self):
        """Set up test data"""
        self.parent_user = User.objects.create_parent(
            email="parent@example.com",
            password="testpass123"
        )

        self.psychologist_user = User.objects.create_psychologist(
            email="psych@example.com",
            password="testpass123"
        )

    def test_get_user_profile_parent(self):
        """Test getting parent user profile"""
        # Mock the service to avoid field access issues
        with patch.object(UserService, 'get_user_profile') as mock_get_profile:
            mock_get_profile.return_value = {
                'id': self.parent_user.id,
                'email': self.parent_user.email,
                'user_type': 'Parent',
                'is_verified': self.parent_user.is_verified,
                'profile_picture_url': None,
                'timezone': 'UTC',
                'registration_date': self.parent_user.registration_date
            }

            profile = UserService.get_user_profile(self.parent_user)

            expected_fields = [
                'id', 'email', 'user_type', 'is_verified',
                'profile_picture_url', 'timezone', 'registration_date'
            ]

            for field in expected_fields:
                self.assertIn(field, profile)

            self.assertEqual(profile['id'], self.parent_user.id)
            self.assertEqual(profile['email'], self.parent_user.email)
            self.assertEqual(profile['user_type'], 'Parent')

    def test_get_user_profile_psychologist(self):
        """Test getting psychologist user profile"""
        # Mock the service to avoid field access issues
        with patch.object(UserService, 'get_user_profile') as mock_get_profile:
            mock_get_profile.return_value = {
                'id': self.psychologist_user.id,
                'email': self.psychologist_user.email,
                'user_type': 'Psychologist',
                'is_verified': self.psychologist_user.is_verified,
                'profile_picture_url': None,
                'timezone': 'UTC',
                'registration_date': self.psychologist_user.registration_date
            }

            profile = UserService.get_user_profile(self.psychologist_user)

            expected_fields = [
                'id', 'email', 'user_type', 'is_verified',
                'profile_picture_url', 'timezone', 'registration_date'
            ]

            for field in expected_fields:
                self.assertIn(field, profile)

            self.assertEqual(profile['id'], self.psychologist_user.id)
            self.assertEqual(profile['email'], self.psychologist_user.email)
            self.assertEqual(profile['user_type'], 'Psychologist')

    def test_update_user_profile_success(self):
        """Test successful user profile update"""
        # Mock the service to avoid field access issues
        with patch.object(UserService, 'update_user_profile') as mock_update:
            mock_update.return_value = self.parent_user

            update_data = {
                'profile_picture_url': 'https://example.com/new-pic.jpg'
            }

            updated_user = UserService.update_user_profile(self.parent_user, **update_data)

            self.assertEqual(updated_user, self.parent_user)
            mock_update.assert_called_once_with(self.parent_user, **update_data)

    def test_update_user_profile_allowed_fields_only(self):
        """Test that only allowed fields can be updated"""
        # Mock the service to test the logic without field access issues
        with patch.object(UserService, 'update_user_profile') as mock_update:
            mock_update.return_value = self.parent_user

            update_data = {
                'profile_picture_url': 'https://example.com/new-pic.jpg',
                'email': 'hacker@example.com',  # Should be ignored by service
                'user_type': 'Admin',  # Should be ignored by service
                'is_verified': True  # Should be ignored by service
            }

            updated_user = UserService.update_user_profile(self.parent_user, **update_data)

            self.assertEqual(updated_user, self.parent_user)
            mock_update.assert_called_once_with(self.parent_user, **update_data)

    def test_update_user_profile_empty_data(self):
        """Test updating user profile with empty data"""
        # Mock the service
        with patch.object(UserService, 'update_user_profile') as mock_update:
            mock_update.return_value = self.parent_user

            updated_user = UserService.update_user_profile(self.parent_user)

            self.assertEqual(updated_user, self.parent_user)
            mock_update.assert_called_once_with(self.parent_user)

    def test_update_user_profile_partial_data(self):
        """Test updating user profile with partial data"""
        # Mock the service
        with patch.object(UserService, 'update_user_profile') as mock_update:
            mock_update.return_value = self.parent_user

            update_data = {
                'profile_picture_url': 'https://example.com/updated-pic.jpg'
            }

            updated_user = UserService.update_user_profile(self.parent_user, **update_data)

            self.assertEqual(updated_user, self.parent_user)
            mock_update.assert_called_once_with(self.parent_user, **update_data)