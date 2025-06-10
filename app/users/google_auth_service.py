# users/google_auth_service.py
"""
Google OAuth authentication service following architectural guidelines.
Contains all Google authentication business logic.
"""

import logging
from typing import Dict, Tuple, Optional
from django.conf import settings
from django.db import transaction
from google.auth.transport import requests
from google.oauth2 import id_token
from google.auth.exceptions import GoogleAuthError as GoogleSDKError

from .models import User
from .exceptions import (
    InvalidGoogleTokenError,
    GoogleUserInfoError,
    EmailAlreadyExistsError,
    GoogleEmailNotVerifiedError,
    UserTypeRequiredError,
    GoogleConfigurationError
)

logger = logging.getLogger(__name__)


class GoogleAuthService:
    """
    Service class for Google OAuth authentication business logic
    """

    @staticmethod
    def verify_google_token(token: str) -> Dict[str, str]:
        """
        Verify Google ID token and extract user information.

        Args:
            token: Google ID token from client

        Returns:
            Dict containing user info from Google

        Raises:
            GoogleConfigurationError: If Google OAuth is not configured
            InvalidGoogleTokenError: If token is invalid or expired
            GoogleUserInfoError: If unable to extract user info
            GoogleEmailNotVerifiedError: If Google email is not verified
        """
        if not settings.GOOGLE_OAUTH2_CLIENT_ID:
            raise GoogleConfigurationError("Google OAuth is not configured")

        try:
            # Verify token with Google
            user_info = id_token.verify_oauth2_token(
                token,
                requests.Request(),
                settings.GOOGLE_OAUTH2_CLIENT_ID
            )

            # Validate required fields
            required_fields = ['email', 'sub', 'email_verified']
            missing_fields = [field for field in required_fields if field not in user_info]
            if missing_fields:
                raise GoogleUserInfoError(f"Missing required fields from Google: {missing_fields}")

            # Check if email is verified
            if not user_info.get('email_verified', False):
                raise GoogleEmailNotVerifiedError("Google account email is not verified")

            # Extract relevant information
            return {
                'email': user_info['email'],
                'google_id': user_info['sub'],
                'name': user_info.get('name', ''),
                'given_name': user_info.get('given_name', ''),
                'family_name': user_info.get('family_name', ''),
                'picture': user_info.get('picture', ''),
            }

        except GoogleSDKError as e:
            logger.warning(f"Google token verification failed: {str(e)}")
            raise InvalidGoogleTokenError("Invalid or expired Google token")
        except Exception as e:
            logger.error(f"Unexpected error during Google token verification: {str(e)}")
            raise GoogleUserInfoError("Unable to verify Google token")

    @staticmethod
    def authenticate_google_user(google_user_info: Dict[str, str]) -> Tuple[User, bool]:
        """
        Authenticate existing user with Google credentials.

        Args:
            google_user_info: Verified user info from Google

        Returns:
            Tuple of (User instance, is_new_user boolean)

        Raises:
            EmailAlreadyExistsError: If email exists with different auth method
        """
        email = google_user_info['email']
        google_id = google_user_info['google_id']

        try:
            # Try to find existing user by email
            user = User.objects.get(email=email)

            # Check if user already has Google ID
            if user.google_id:
                if user.google_id != google_id:
                    logger.warning(f"Google ID mismatch for user {email}")
                    raise InvalidGoogleTokenError("Google account mismatch")

                # Update last login
                from django.utils import timezone
                user.last_login_date = timezone.now()
                user.save(update_fields=['last_login_date'])

                logger.info(f"Google authentication successful for existing user: {email}")
                return user, False
            else:
                # User exists but doesn't have Google ID - link accounts
                user.google_id = google_id
                if google_user_info.get('picture') and not user.profile_picture_url:
                    user.profile_picture_url = google_user_info['picture']
                user.is_verified = True  # Google accounts are verified
                user.save(update_fields=['google_id', 'profile_picture_url', 'is_verified', 'updated_at'])

                logger.info(f"Linked Google account to existing user: {email}")
                return user, False

        except User.DoesNotExist:
            # User doesn't exist - return None to indicate registration needed
            return None, True

    @staticmethod
    @transaction.atomic
    def register_google_user(google_user_info: Dict[str, str], user_type: str) -> User:
        """
        Register new user with Google credentials.

        Args:
            google_user_info: Verified user info from Google
            user_type: Type of user (Parent, Psychologist, Admin)

        Returns:
            Newly created User instance

        Raises:
            UserTypeRequiredError: If user_type is missing or invalid
            EmailAlreadyExistsError: If email already exists
        """
        email = google_user_info['email']
        google_id = google_user_info['google_id']

        # Validate user type
        valid_user_types = [choice[0] for choice in User.USER_TYPE_CHOICES]
        if user_type not in valid_user_types:
            raise UserTypeRequiredError(f"Invalid user type. Must be one of: {valid_user_types}")

        # Check if user already exists
        if User.objects.filter(email=email).exists():
            raise EmailAlreadyExistsError(email, "Google")

        try:
            # Create user based on type
            user_data = {
                'email': email,
                'user_type': user_type,
                'google_id': google_id,
                'is_verified': True,  # Google accounts are pre-verified
                'is_active': True,
                'profile_picture_url': google_user_info.get('picture', ''),
            }

            # Use appropriate manager method based on user type
            if user_type == 'Parent':
                user = User.objects.create_parent(**user_data)
            elif user_type == 'Psychologist':
                user = User.objects.create_psychologist(**user_data)
            else:  # Admin
                user = User.objects.create_user(**user_data)

            logger.info(f"New {user_type} registered via Google: {email}")
            return user

        except Exception as e:
            logger.error(f"Failed to register Google user {email}: {str(e)}")
            raise

    @staticmethod
    def google_login_or_register(token: str, user_type: Optional[str] = None) -> Tuple[User, bool, str]:
        """
        Complete Google authentication flow - login existing user or register new one.

        Args:
            token: Google ID token
            user_type: Required for new user registration

        Returns:
            Tuple of (User instance, is_new_user boolean, action_taken string)

        Raises:
            Various Google auth exceptions based on specific failures
        """
        # Verify Google token and get user info
        google_user_info = GoogleAuthService.verify_google_token(token)

        # Try to authenticate existing user
        user, is_new = GoogleAuthService.authenticate_google_user(google_user_info)

        if user:
            # Existing user authenticated
            return user, False, "login"
        else:
            # New user - registration required
            if not user_type:
                raise UserTypeRequiredError("User type is required for new Google registrations")

            user = GoogleAuthService.register_google_user(google_user_info, user_type)
            return user, True, "registration"