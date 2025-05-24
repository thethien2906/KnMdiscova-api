from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode


class EmailVerificationTokenGenerator:
    """
    Generate tokens for email verification and password reset
    Uses Django's built-in token generator (no DB fields needed)
    """

    def __init__(self):
        self.token_generator = PasswordResetTokenGenerator()

    def make_token(self, user):
        """
        Generate a token for the user
        """
        return self.token_generator.make_token(user)

    def check_token(self, user, token):
        """
        Check if token is valid for the user
        """
        return self.token_generator.check_token(user, token)

    def encode_uid(self, user):
        """
        Encode user ID for URL
        """
        return urlsafe_base64_encode(force_bytes(user.pk))

    def decode_uid(self, uidb64):
        """
        Decode user ID from URL
        """
        try:
            from .models import User
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid)
            return user
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return None


# Instance to use throughout the app
token_generator = EmailVerificationTokenGenerator()