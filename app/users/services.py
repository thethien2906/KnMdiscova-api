from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from .models import User
from .tokens import token_generator


class AuthenticationService:
    """
    Service class for authentication-related business logic
    Similar to a .NET service class
    """

    @staticmethod
    def register_user(email, password, user_type, **extra_data):
        """
        Register a new user and send verification email
        """
        # Create user using appropriate manager method
        if user_type == 'Parent':
            user = User.objects.create_parent(
                email=email,
                password=password,
                **extra_data
            )
        elif user_type == 'Psychologist':
            user = User.objects.create_psychologist(
                email=email,
                password=password,
                **extra_data
            )
        else:
            raise ValueError("Invalid user type")

        # Send verification email
        AuthenticationService.send_verification_email(user)

        return user

    @staticmethod
    def send_verification_email(user):
        """
        Send email verification link to user
        """
        token = token_generator.make_token(user)
        uidb64 = token_generator.encode_uid(user)

        verification_link = f"{settings.FRONTEND_URL}/verify-email/{uidb64}/{token}/"

        context = {
            'user': user,
            'verification_link': verification_link,
            'site_name': 'K&Mdiscova'
        }

        subject = _('Verify your K&Mdiscova account')
        html_message = render_to_string('emails/verify_email.html', context)
        plain_message = render_to_string('emails/verify_email.txt', context)

        send_mail(
            subject=subject,
            message=plain_message,
            html_message=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False
        )

        return True

    @staticmethod
    def verify_email(uidb64, token):
        """
        Verify email using token
        """
        user = token_generator.decode_uid(uidb64)
        if not user:
            return None, "Invalid verification link"

        if not token_generator.check_token(user, token):
            return None, "Invalid or expired verification link"

        if user.is_verified:
            return user, "Email already verified"

        user.is_verified = True
        user.save(update_fields=['is_verified'])

        return user, "Email verified successfully"

    @staticmethod
    def request_password_reset(email):
        """
        Send password reset email
        """
        try:
            user = User.objects.get(email=email, is_active=True)

            token = token_generator.make_token(user)
            uidb64 = token_generator.encode_uid(user)

            reset_link = f"{settings.FRONTEND_URL}/reset-password/{uidb64}/{token}/"

            context = {
                'user': user,
                'reset_link': reset_link,
                'site_name': 'K&Mdiscova'
            }

            subject = _('Reset your K&Mdiscova password')
            html_message = render_to_string('emails/password_reset.html', context)
            plain_message = render_to_string('emails/password_reset.txt', context)

            send_mail(
                subject=subject,
                message=plain_message,
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False
            )

            return True, "Password reset link sent"

        except User.DoesNotExist:
            # Security: Don't reveal if email exists
            return True, "If email exists, reset link will be sent"

    @staticmethod
    def reset_password(uidb64, token, new_password):
        """
        Reset password using token
        """
        user = token_generator.decode_uid(uidb64)
        if not user:
            return None, "Invalid reset link"

        if not token_generator.check_token(user, token):
            return None, "Invalid or expired reset link"

        user.set_password(new_password)
        user.save(update_fields=['password'])

        return user, "Password reset successfully"


class UserService:
    """
    Service class for user-related business logic
    """

    @staticmethod
    def get_user_profile(user):
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
            # Could add children count, etc.
            pass
        elif user.is_psychologist:
            # Could add verification status, ratings, etc.
            pass

        return profile_data

    @staticmethod
    def update_user_profile(user, **update_data):
        """
        Update user profile with validation
        """
        allowed_fields = ['profile_picture_url', 'timezone']

        for field, value in update_data.items():
            if field in allowed_fields:
                setattr(user, field, value)

        user.save(update_fields=list(update_data.keys()))
        return user