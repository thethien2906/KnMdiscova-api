# users/facebook_auth_service.py
"""
Facebook OAuth authentication service following architectural guidelines.
Contains all Facebook authentication business logic.
"""

import logging
import requests
from typing import Dict, Tuple, Optional
from django.conf import settings
from django.db import transaction

from .models import User
from .exceptions import (
    InvalidFacebookTokenError,
    FacebookUserInfoError,
    FacebookConfigurationError,
    FacebookEmailNotAvailableError,
    EmailAlreadyExistsError,
    UserTypeRequiredError
)

logger = logging.getLogger(__name__)


class FacebookAuthService:
    """
    Service class for Facebook OAuth authentication business logic
    """

    @staticmethod
    def verify_facebook_token(token: str) -> Dict[str, str]:
        """
        Verify Facebook access token and extract user information.

        Args:
            token: Facebook access token from client

        Returns:
            Dict containing user info from Facebook

        Raises:
            FacebookConfigurationError: If Facebook OAuth is not configured
            InvalidFacebookTokenError: If token is invalid or expired
            FacebookUserInfoError: If unable to extract user info
            FacebookEmailNotAvailableError: If Facebook email is not available
        """
        if not settings.FACEBOOK_APP_ID or not settings.FACEBOOK_APP_SECRET:
            raise FacebookConfigurationError("Facebook OAuth is not configured")

        try:
            # First, verify token with Facebook's debug endpoint
            debug_url = "https://graph.facebook.com/debug_token"
            debug_params = {
                'input_token': token,
                'access_token': f"{settings.FACEBOOK_APP_ID}|{settings.FACEBOOK_APP_SECRET}"
            }

            debug_response = requests.get(debug_url, params=debug_params, timeout=10)
            debug_data = debug_response.json()

            if 'error' in debug_data or not debug_data.get('data', {}).get('is_valid'):
                logger.warning("Facebook token verification failed")
                raise InvalidFacebookTokenError("Invalid or expired Facebook token")

            # Verify the app_id matches
            token_app_id = debug_data.get('data', {}).get('app_id')
            if token_app_id != settings.FACEBOOK_APP_ID:
                logger.warning(f"Facebook token app_id mismatch: {token_app_id}")
                raise InvalidFacebookTokenError("Facebook token app_id mismatch")

            # Get user information from Facebook Graph API
            user_url = "https://graph.facebook.com/me"
            user_params = {
                'access_token': token,
                'fields': 'id,email,name,first_name,last_name,picture.type(large)'
            }

            user_response = requests.get(user_url, params=user_params, timeout=10)
            user_data = user_response.json()

            if 'error' in user_data:
                logger.error(f"Facebook user info error: {user_data['error']}")
                raise FacebookUserInfoError("Unable to get user info from Facebook")

            # Validate required fields
            required_fields = ['id', 'name']
            missing_fields = [field for field in required_fields if field not in user_data]
            if missing_fields:
                raise FacebookUserInfoError(f"Missing required fields from Facebook: {missing_fields}")

            # Check if email is available (Facebook doesn't always provide it)
            if not user_data.get('email'):
                raise FacebookEmailNotAvailableError(
                    "Facebook account does not provide email address. "
                    "Please ensure email permission is granted or use a different sign-in method."
                )

            # Extract relevant information
            picture_url = ''
            if 'picture' in user_data and 'data' in user_data['picture']:
                picture_url = user_data['picture']['data'].get('url', '')

            return {
                'email': user_data['email'],
                'facebook_id': user_data['id'],
                'name': user_data.get('name', ''),
                'first_name': user_data.get('first_name', ''),
                'last_name': user_data.get('last_name', ''),
                'picture': picture_url,
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook API request failed: {str(e)}")
            raise FacebookUserInfoError("Unable to connect to Facebook API")
        except InvalidFacebookTokenError:
            raise  # Re-raise our custom exceptions
        except FacebookUserInfoError:
            raise
        except FacebookEmailNotAvailableError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during Facebook token verification: {str(e)}")
            raise FacebookUserInfoError("Unable to verify Facebook token")

    @staticmethod
    def authenticate_facebook_user(facebook_user_info: Dict[str, str]) -> Tuple[User, bool]:
        """
        Authenticate existing user with Facebook credentials.

        Args:
            facebook_user_info: Verified user info from Facebook

        Returns:
            Tuple of (User instance, is_new_user boolean)

        Raises:
            EmailAlreadyExistsError: If email exists with different auth method
        """
        email = facebook_user_info['email']
        facebook_id = facebook_user_info['facebook_id']

        try:
            # Try to find existing user by email
            user = User.objects.get(email=email)

            # Check if user already has Facebook ID
            if user.facebook_id:
                if user.facebook_id != facebook_id:
                    logger.warning(f"Facebook ID mismatch for user {email}")
                    raise InvalidFacebookTokenError("Facebook account mismatch")

                # Update last login
                from django.utils import timezone
                user.last_login_date = timezone.now()
                user.save(update_fields=['last_login_date'])

                logger.info(f"Facebook authentication successful for existing user: {email}")
                return user, False
            else:
                # User exists but doesn't have Facebook ID - link accounts
                user.facebook_id = facebook_id
                if facebook_user_info.get('picture') and not user.profile_picture_url:
                    user.profile_picture_url = facebook_user_info['picture']
                user.is_verified = True  # Facebook accounts are verified
                user.save(update_fields=['facebook_id', 'profile_picture_url', 'is_verified', 'updated_at'])

                logger.info(f"Linked Facebook account to existing user: {email}")
                return user, False

        except User.DoesNotExist:
            # User doesn't exist - return None to indicate registration needed
            return None, True

    @staticmethod
    @transaction.atomic
    def register_facebook_user(facebook_user_info: Dict[str, str], user_type: str) -> User:
        """
        Register new user with Facebook credentials.

        Args:
            facebook_user_info: Verified user info from Facebook
            user_type: Type of user (Parent, Psychologist, Admin)

        Returns:
            Newly created User instance

        Raises:
            UserTypeRequiredError: If user_type is missing or invalid
            EmailAlreadyExistsError: If email already exists
        """
        email = facebook_user_info['email']
        facebook_id = facebook_user_info['facebook_id']

        # Validate user type
        valid_user_types = [choice[0] for choice in User.USER_TYPE_CHOICES]
        if user_type not in valid_user_types:
            raise UserTypeRequiredError(f"Invalid user type. Must be one of: {valid_user_types}")

        # Check if email already exists
        if User.objects.filter(email=email).exists():
            raise EmailAlreadyExistsError(email, "Email already registered")

        # Check if Facebook ID already exists (shouldn't happen, but safety check)
        if User.objects.filter(facebook_id=facebook_id).exists():
            raise EmailAlreadyExistsError(email, "Facebook account already registered")

        try:
            # Create new user
            user = User.objects.create_user(
                email=email,
                user_type=user_type,
                facebook_id=facebook_id,
                is_verified=True,  # Facebook accounts are verified
                profile_picture_url=facebook_user_info.get('picture', ''),
                password=None  # No password for social auth users
            )

            logger.info(f"Facebook registration successful for new user: {email}")
            return user

        except Exception as e:
            logger.error(f"Failed to create Facebook user {email}: {str(e)}")
            raise

    @staticmethod
    def link_facebook_account(user: User, facebook_token: str) -> User:
        """
        Link Facebook account to existing user.

        Args:
            user: Existing authenticated user
            facebook_token: Facebook access token

        Returns:
            Updated user instance

        Raises:
            InvalidFacebookTokenError: If token is invalid
            EmailAlreadyExistsError: If Facebook email doesn't match user email
        """
        try:
            # Verify Facebook token
            facebook_user_info = FacebookAuthService.verify_facebook_token(facebook_token)

            # Ensure Facebook email matches user email
            if facebook_user_info['email'].lower() != user.email.lower():
                raise EmailAlreadyExistsError(
                    facebook_user_info['email'],
                    "Different email address"
                )

            # Check if Facebook ID is already linked to another account
            facebook_id = facebook_user_info['facebook_id']
            existing_user = User.objects.filter(facebook_id=facebook_id).first()
            if existing_user and existing_user.id != user.id:
                raise EmailAlreadyExistsError(
                    facebook_user_info['email'],
                    "Facebook account already linked to another user"
                )

            # Link the account
            user.facebook_id = facebook_id
            if facebook_user_info.get('picture') and not user.profile_picture_url:
                user.profile_picture_url = facebook_user_info['picture']
            user.is_verified = True
            user.save(update_fields=['facebook_id', 'profile_picture_url', 'is_verified', 'updated_at'])

            logger.info(f"Facebook account linked successfully for user: {user.email}")
            return user

        except Exception as e:
            logger.error(f"Failed to link Facebook account for user {user.email}: {str(e)}")
            raise

    @staticmethod
    def unlink_facebook_account(user: User) -> User:
        """
        Unlink Facebook account from user.

        Args:
            user: User with linked Facebook account

        Returns:
            Updated user instance

        Raises:
            ValueError: If user doesn't have Facebook account linked or no password auth
        """
        if not user.facebook_id:
            raise ValueError("User doesn't have Facebook account linked")

        if not user.has_password_auth and not user.google_id:
            raise ValueError("Cannot unlink Facebook: user has no other authentication method")

        try:
            user.facebook_id = None
            user.save(update_fields=['facebook_id', 'updated_at'])

            logger.info(f"Facebook account unlinked successfully for user: {user.email}")
            return user

        except Exception as e:
            logger.error(f"Failed to unlink Facebook account for user {user.email}: {str(e)}")
            raise