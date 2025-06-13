# users/services.py
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from django.utils.html import strip_tags
import logging
from typing import Tuple, Optional
import time
from functools import wraps

from .models import User
from .tokens import token_generator
from django.conf import settings
from .facebook_auth_service import FacebookAuthService
from .google_auth_service import GoogleAuthService
from .exceptions import (
    InvalidGoogleTokenError,
    GoogleUserInfoError,
    EmailAlreadyExistsError,
    GoogleEmailNotVerifiedError,
    UserTypeRequiredError,
    GoogleConfigurationError
)
# Set up logging
logger = logging.getLogger(__name__)


def retry_on_email_failure(max_attempts=3, delay=1):
    """Decorator to retry email sending on failure"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(
                        f"Email sending attempt {attempt + 1} failed: {str(e)}"
                    )
                    if attempt < max_attempts - 1:
                        time.sleep(delay * (attempt + 1))  # Exponential backoff

            # Log the final failure
            logger.error(
                f"Failed to send email after {max_attempts} attempts: {str(last_exception)}"
            )

            # Re-raise if not in debug mode
            if not settings.DEBUG:
                raise last_exception

            return False
        return wrapper
    return decorator


class EmailService:
    """
    Centralized email service for all email operations
    """

    @staticmethod
    def get_email_context_base():
        """Get base context for all emails"""
        return {
            'site_name': 'K&Mdiscova',
            'site_url': settings.FRONTEND_URL,
            'support_email': getattr(settings, 'SUPPORT_EMAIL', 'support@kmdiscova.com'),
            'company_address': getattr(settings, 'COMPANY_ADDRESS', ''),
        }

    @staticmethod
    @retry_on_email_failure(max_attempts=3)
    def send_email(subject: str, template_name: str, context: dict,
                   recipient_email: str, from_email: str = None) -> bool:
        """
        Send an email using templates with retry mechanism

        Args:
            subject: Email subject
            template_name: Base name of template (without .html/.txt extension)
            context: Context dictionary for template rendering
            recipient_email: Recipient email address
            from_email: Sender email (defaults to DEFAULT_FROM_EMAIL)

        Returns:
            bool: True if email sent successfully
        """
        try:
            # Merge with base context
            full_context = {**EmailService.get_email_context_base(), **context}

            # Render templates
            html_content = render_to_string(f'emails/{template_name}.html', full_context)
            text_content = render_to_string(f'emails/{template_name}.txt', full_context)

            # Create email
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email or settings.DEFAULT_FROM_EMAIL,
                to=[recipient_email],
            )

            # Attach HTML version
            email.attach_alternative(html_content, "text/html")

            # Send email
            email.send(fail_silently=False)

            logger.info(f"Email sent successfully to {recipient_email}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to send email to {recipient_email}: {str(e)}",
                exc_info=True
            )
            raise

    @staticmethod
    def send_bulk_email(subject: str, template_name: str,
                       recipients_contexts: list) -> dict:
        """
        Send bulk emails with individual contexts

        Args:
            subject: Email subject
            template_name: Base name of template
            recipients_contexts: List of tuples (email, context)

        Returns:
            dict: {'success': list, 'failed': list}
        """
        results = {'success': [], 'failed': []}

        for recipient_email, context in recipients_contexts:
            try:
                EmailService.send_email(
                    subject=subject,
                    template_name=template_name,
                    context=context,
                    recipient_email=recipient_email
                )
                results['success'].append(recipient_email)
            except Exception as e:
                results['failed'].append((recipient_email, str(e)))
                logger.error(f"Failed to send bulk email to {recipient_email}: {str(e)}")

        return results


class AuthenticationService:
    """
    Service class for authentication-related business logic
    Enhanced with better email handling
    """

    @staticmethod
    def register_user(email: str, password: str, user_type: str, **extra_data) -> User:
        """
        Register a new user and send verification email
        """
        # Validate user type
        if user_type not in ['Parent', 'Psychologist']:
            raise ValueError("Invalid user type")

        try:
            # Create user using appropriate manager method
            if user_type == 'Parent':
                user = User.objects.create_parent(
                    email=email,
                    password=password,
                    is_verified = True,
                    **extra_data
                )
            else:  # Psychologist
                user = User.objects.create_psychologist(
                    email=email,
                    password=password,
                    is_verified = True,
                    **extra_data
                )

            # Send verification email (don't fail registration if email fails)
            # try:
            #     AuthenticationService.send_verification_email(user)
            # except Exception as e:
            #     logger.error(f"Failed to send verification email for user {user.email}: {str(e)}")
            #     # Consider queuing for retry or notifying admin

            logger.info(f"New {user_type} registered: {user.email}")
            return user

        except Exception as e:
            logger.error(f"Failed to register user {email}: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def send_verification_email(user: User) -> bool:
        """
        Send email verification link to user
        """
        token = token_generator.make_token(user)
        uidb64 = token_generator.encode_uid(user)

        verification_link = f"{settings.FRONTEND_URL}/api/auth/verify-email/{uidb64}/{token}/"

        context = {
            'user': user,
            'user_name': user.email,
            'verification_link': verification_link,
            'expiry_days': getattr(settings, 'EMAIL_VERIFICATION_TIMEOUT_DAYS', 3),
        }

        return EmailService.send_email(
            subject=_('Verify your K&Mdiscova account'),
            template_name='verify_email',
            context=context,
            recipient_email=user.email
        )

    @staticmethod
    def verify_email(uidb64: str, token: str) -> Tuple[Optional[User], str]:
        """
        Verify email using token
        """
        user = token_generator.decode_uid(uidb64)
        if not user:
            logger.warning(f"Invalid uidb64 in email verification: {uidb64}")
            return None, "Invalid verification link"

        if not token_generator.check_token(user, token):
            logger.warning(f"Invalid or expired token for user {user.email}")
            return None, "Invalid or expired verification link"

        if user.is_verified:
            logger.info(f"Email already verified for user {user.email}")
            return user, "Email already verified"

        user.is_verified = True
        user.save(update_fields=['is_verified', 'updated_at'])

        logger.info(f"Email verified successfully for user {user.email}")

        # Send welcome email after verification
        try:
            AuthenticationService.send_welcome_email(user)
        except Exception as e:
            logger.error(f"Failed to send welcome email to {user.email}: {str(e)}")

        return user, "Email verified successfully"


    @staticmethod
    def request_password_reset(email: str) -> Tuple[bool, str]:
        """
        Send password reset email with rate limiting
        """
        try:
            user = User.objects.get(email=email, is_active=True)

            # Check for rate limiting (example: max 3 requests per hour)
            # You might want to implement this with cache or database

            token = token_generator.make_token(user)
            uidb64 = token_generator.encode_uid(user)

            reset_link = f"{settings.FRONTEND_URL}/reset-password/{uidb64}/{token}/"

            context = {
                'user': user,
                'user_name': user.email,
                'reset_link': reset_link,
                'expiry_hours': 24,  # Token typically expires in 24 hours
                'ip_address': getattr(user, '_request_ip', 'Unknown'),  # Pass from view
            }

            success = EmailService.send_email(
                subject=_('Reset your K&Mdiscova password'),
                template_name='password_reset',
                context=context,
                recipient_email=user.email
            )

            if success:
                logger.info(f"Password reset email sent to {user.email}")

            return True, "Password reset link sent"

        except User.DoesNotExist:
            # Security: Don't reveal if email exists
            logger.info(f"Password reset requested for non-existent email: {email}")
            return True, "If email exists, reset link will be sent"
        except Exception as e:
            logger.error(f"Failed to send password reset email: {str(e)}", exc_info=True)
            return False, "Failed to send reset email. Please try again."

    @staticmethod
    def reset_password(uidb64: str, token: str, new_password: str) -> Tuple[Optional[User], str]:
        """
        Reset password using token
        """
        user = token_generator.decode_uid(uidb64)
        if not user:
            logger.warning(f"Invalid uidb64 in password reset: {uidb64}")
            return None, "Invalid reset link"

        if not token_generator.check_token(user, token):
            logger.warning(f"Invalid or expired password reset token for user {user.email}")
            return None, "Invalid or expired reset link"

        user.set_password(new_password)
        user.save(update_fields=['password', 'updated_at'])

        logger.info(f"Password reset successfully for user {user.email}")

        # Send confirmation email
        try:
            AuthenticationService.send_password_change_confirmation(user)
        except Exception as e:
            logger.error(f"Failed to send password change confirmation to {user.email}: {str(e)}")

        return user, "Password reset successfully"

    @staticmethod
    def send_password_change_confirmation(user: User) -> bool:
        """
        Send confirmation email after password change
        """
        context = {
            'user': user,
            'user_name': user.email,
            'support_url': f"{settings.FRONTEND_URL}/support",
        }

        return EmailService.send_email(
            subject=_('Your K&Mdiscova password has been changed'),
            template_name='password_change_confirmation',
            context=context,
            recipient_email=user.email
        )

    @staticmethod
    def google_authenticate(google_token: str, user_type: str = None) -> Tuple[User, bool, str]:
        """
        Authenticate user with Google OAuth token.

        Args:
            google_token: Google ID token from client
            user_type: Required for new user registration

        Returns:
            Tuple of (User, is_new_user, action_taken)

        Raises:
            Various Google auth exceptions
        """
        try:
            return GoogleAuthService.google_login_or_register(google_token, user_type)
        except Exception as e:
            logger.error(f"Google authentication failed: {str(e)}")
            raise

    @staticmethod
    def link_google_account(user: User, google_token: str) -> User:
        """
        Link Google account to existing user.

        Args:
            user: Existing authenticated user
            google_token: Google ID token

        Returns:
            Updated user instance

        Raises:
            InvalidGoogleTokenError: If token is invalid
            EmailAlreadyExistsError: If Google email doesn't match user email
        """
        try:
            # Verify Google token
            google_user_info = GoogleAuthService.verify_google_token(google_token)

            # Ensure Google email matches user email
            if google_user_info['email'].lower() != user.email.lower():
                raise EmailAlreadyExistsError(
                    google_user_info['email'],
                    "Different email address"
                )

            # Check if Google ID is already linked to another account
            google_id = google_user_info['google_id']
            existing_user = User.objects.filter(google_id=google_id).first()
            if existing_user and existing_user.id != user.id:
                raise EmailAlreadyExistsError(
                    google_user_info['email'],
                    "Google account already linked to another user"
                )

            # Link the account
            user.google_id = google_id
            if google_user_info.get('picture') and not user.profile_picture_url:
                user.profile_picture_url = google_user_info['picture']
            user.is_verified = True
            user.save(update_fields=['google_id', 'profile_picture_url', 'is_verified', 'updated_at'])

            logger.info(f"Google account linked successfully for user: {user.email}")
            return user

        except Exception as e:
            logger.error(f"Failed to link Google account for user {user.email}: {str(e)}")
            raise

    @staticmethod
    def unlink_google_account(user: User) -> User:
        """
        Unlink Google account from user.

        Args:
            user: User with linked Google account

        Returns:
            Updated user instance

        Raises:
            ValueError: If user doesn't have Google account linked or no password auth
        """
        if not user.google_id:
            raise ValueError("User doesn't have Google account linked")

        if not user.has_password_auth:
            raise ValueError("Cannot unlink Google: user has no password authentication")

        try:
            user.google_id = None
            user.save(update_fields=['google_id', 'updated_at'])

            logger.info(f"Google account unlinked successfully for user: {user.email}")
            return user

        except Exception as e:
            logger.error(f"Failed to unlink Google account for user {user.email}: {str(e)}")
            raise

    @staticmethod
    def facebook_authenticate(token: str, user_type: Optional[str] = None) -> Tuple[User, bool, str]:
        """
        Authenticate or register user with Facebook credentials.

        Args:
            token: Facebook access token
            user_type: Required for new user registration

        Returns:
            Tuple of (User instance, is_new_user boolean, action_taken string)

        Raises:
            Various Facebook auth exceptions based on specific failures
        """
        # Verify Facebook token and get user info
        facebook_user_info = FacebookAuthService.verify_facebook_token(token)

        # Try to authenticate existing user
        user, is_new = FacebookAuthService.authenticate_facebook_user(facebook_user_info)

        if user:
            # Existing user authenticated
            return user, False, "login"
        else:
            # New user - registration required
            if not user_type:
                raise UserTypeRequiredError("User type is required for new Facebook registrations")

            user = FacebookAuthService.register_facebook_user(facebook_user_info, user_type)
            return user, True, "registration"

    @staticmethod
    def link_facebook_account(user: User, facebook_token: str) -> User:
        """
        Link Facebook account to existing user.
        Delegates to FacebookAuthService.
        """
        return FacebookAuthService.link_facebook_account(user, facebook_token)

    @staticmethod
    def unlink_facebook_account(user: User) -> User:
        """
        Unlink Facebook account from user.
        Delegates to FacebookAuthService.
        """
        return FacebookAuthService.unlink_facebook_account(user)


class UserService:
    """
    Service class for user-related business logic
    """

    @staticmethod
    def get_user_profile(user: User) -> dict:
        """
        Get user profile with additional computed data
        """
        profile_data = {
            'id': user.id,
            'email': user.email,
            'user_type': user.user_type,
            'is_verified': user.is_verified,
            'profile_picture_url': user.profile_picture_url,
            'user_timezone': user.user_timezone,
            'registration_date': user.registration_date,
        }

        # Add type-specific data
        if user.is_parent:
            profile_data['is_parent'] = True
            # Could add children count, etc.
        elif user.is_psychologist:
            profile_data['is_psychologist'] = True
            # Could add verification status, ratings, etc.

        return profile_data

    @staticmethod
    def update_user_profile(user: User, **update_data) -> User:
        """
        Update user profile with validation
        """
        allowed_fields = ['profile_picture_url', 'user_timezone']
        updated_fields = []

        for field, value in update_data.items():
            if field in allowed_fields and hasattr(user, field):
                setattr(user, field, value)
                updated_fields.append(field)

        if updated_fields:
            updated_fields.append('updated_at')
            user.save(update_fields=updated_fields)
            logger.info(f"Updated profile for user {user.email}: {updated_fields}")

        return user

    @staticmethod
    def create_user(email: str, password: str, **extra_fields) -> User:
        """
        Create a new user with the given email and password.
        """
        user = User.objects.create_user(email=email, password=password, **extra_fields)
        return user