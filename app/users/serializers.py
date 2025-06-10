# users/serializers.py
from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import User
from .services import AuthenticationService

class UserSerializer(serializers.ModelSerializer):
    """
    Basic serializer for User model - returns user data
    """
    class Meta:
        model = User
        fields = [
            'id', 'email', 'user_type', 'is_active', 'is_verified',
            'profile_picture_url', 'user_timezone', 'registration_date',
            'last_login_date'
        ]
        read_only_fields = [
            'id', 'registration_date', 'last_login_date', 'is_verified'
        ]


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['email', 'user_type', 'password', 'password_confirm', 'user_timezone']

    def validate(self, attrs):
        # Only validation logic here
        password = attrs.get('password')
        password_confirm = attrs.pop('password_confirm')

        if password != password_confirm:
            raise serializers.ValidationError("Passwords do not match")

        return attrs

    def create(self, validated_data):
        # Delegate to service
        return AuthenticationService.register_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    """
    Serializer for user login
    """
    email = serializers.EmailField(
        help_text=_("Your email address")
    )
    password = serializers.CharField(
        style={'input_type': 'password'},
        help_text=_("Your password")
    )

    def validate(self, attrs):
        """
        Validate credentials and return user
        """
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            # Authenticate user
            user = authenticate(
                request=self.context.get('request'),
                username=email,  # We use email as username
                password=password
            )

            if not user:
                raise serializers.ValidationError(
                    _("Invalid email or password"),
                    code='authorization'
                )

            if not user.is_active:
                raise serializers.ValidationError(
                    _("User account is disabled"),
                    code='authorization'
                )
            if not user.is_verified:
                raise serializers.ValidationError(
                    _("User account is not verified"),
                    code='authorization'
                )
            attrs['user'] = user
            return attrs
        else:
            raise serializers.ValidationError(
                _("Must include email and password"),
                code='authorization'
            )


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def save(self):
        # Delegate to service
        email = self.validated_data['email']
        return AuthenticationService.request_password_reset(email)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Simplified serializer that delegates to AuthenticationService
    """
    uidb64 = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        """
        Only handle data validation here
        """
        password = attrs.get('password')
        password_confirm = attrs.pop('password_confirm')

        # Basic password validation
        if password != password_confirm:
            raise serializers.ValidationError({
                'password_confirm': _("Passwords do not match")
            })

        # Django password strength validation
        try:
            validate_password(password)
        except ValidationError as e:
            raise serializers.ValidationError({
                'password': list(e.messages)
            })

        return attrs

    def save(self):
        """
        Delegate business logic to service
        """
        uidb64 = self.validated_data['uidb64']
        token = self.validated_data['token']
        password = self.validated_data['password']

        user, message = AuthenticationService.reset_password(uidb64, token, password)

        if not user:
            raise serializers.ValidationError(message)

        return {'user': user, 'message': message}



class GoogleAuthSerializer(serializers.Serializer):
    """
    Serializer for Google OAuth token validation.
    Handles input validation only - business logic in service layer.
    """
    google_token = serializers.CharField(
        max_length=2048,  # Google tokens can be quite long
        help_text=_("Google ID token from client-side OAuth flow")
    )
    user_type = serializers.ChoiceField(
        choices=User.USER_TYPE_CHOICES,
        required=False,
        help_text=_("Required for new user registration: Parent, Psychologist, or Admin")
    )

    def validate_google_token(self, value):
        """
        Basic token format validation
        """
        if not value.strip():
            raise serializers.ValidationError(_("Google token cannot be empty"))

        # Basic format check - Google JWT tokens have 3 parts separated by dots
        parts = value.split('.')
        if len(parts) != 3:
            raise serializers.ValidationError(_("Invalid Google token format"))

        return value.strip()

    def validate(self, attrs):
        """
        Cross-field validation - no complex business logic here
        """
        return attrs


class GoogleLinkAccountSerializer(serializers.Serializer):
    """
    Serializer for linking existing account with Google.
    Used when user wants to add Google auth to existing account.
    """
    google_token = serializers.CharField(
        max_length=2048,
        help_text=_("Google ID token to link with current account")
    )
    password = serializers.CharField(
        write_only=True,
        help_text=_("Current account password for verification")
    )

    def validate_google_token(self, value):
        """Basic token validation"""
        if not value.strip():
            raise serializers.ValidationError(_("Google token cannot be empty"))

        parts = value.split('.')
        if len(parts) != 3:
            raise serializers.ValidationError(_("Invalid Google token format"))

        return value.strip()

    def validate(self, attrs):
        """
        Validate password against current user
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError(_("Authentication required"))

        password = attrs.get('password')
        if not request.user.check_password(password):
            raise serializers.ValidationError({
                'password': _("Current password is incorrect")
            })

        return attrs


class GoogleUnlinkAccountSerializer(serializers.Serializer):
    """
    Serializer for unlinking Google from account.
    """
    password = serializers.CharField(
        write_only=True,
        help_text=_("Current account password for verification")
    )

    def validate(self, attrs):
        """
        Validate password and ensure user has password auth available
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError(_("Authentication required"))

        user = request.user
        password = attrs.get('password')

        if not user.check_password(password):
            raise serializers.ValidationError({
                'password': _("Current password is incorrect")
            })

        if not user.google_id:
            raise serializers.ValidationError(_("Google account is not linked"))

        if not user.has_password_auth:
            raise serializers.ValidationError(_(
                "Cannot unlink Google account: no password authentication available. "
                "Please set a password first."
            ))

        return attrs


class FacebookAuthSerializer(serializers.Serializer):
    """
    Serializer for Facebook OAuth authentication.
    Handles both login and registration cases.
    """
    facebook_token = serializers.CharField(
        max_length=2048,
        help_text=_("Facebook access token obtained from Facebook SDK")
    )
    user_type = serializers.ChoiceField(
        choices=User.USER_TYPE_CHOICES,
        required=False,
        help_text=_("Required for new user registration: Parent, Psychologist, or Admin")
    )

    def validate_facebook_token(self, value):
        """Basic token validation"""
        if not value.strip():
            raise serializers.ValidationError(_("Facebook token cannot be empty"))

        # Facebook access tokens are typically long strings
        if len(value.strip()) < 50:
            raise serializers.ValidationError(_("Invalid Facebook token format"))

        return value.strip()

    def validate(self, attrs):
        """
        Cross-field validation - no complex business logic here
        """
        return attrs


class FacebookLinkAccountSerializer(serializers.Serializer):
    """
    Serializer for linking existing account with Facebook.
    Used when user wants to add Facebook auth to existing account.
    """
    facebook_token = serializers.CharField(
        max_length=2048,
        help_text=_("Facebook access token to link with current account")
    )
    password = serializers.CharField(
        write_only=True,
        help_text=_("Current account password for verification")
    )

    def validate_facebook_token(self, value):
        """Basic token validation"""
        if not value.strip():
            raise serializers.ValidationError(_("Facebook token cannot be empty"))

        if len(value.strip()) < 50:
            raise serializers.ValidationError(_("Invalid Facebook token format"))

        return value.strip()

    def validate(self, attrs):
        """
        Validate password against current user
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError(_("Authentication required"))

        password = attrs.get('password')
        if not request.user.check_password(password):
            raise serializers.ValidationError({
                'password': _("Current password is incorrect")
            })

        return attrs


class FacebookUnlinkAccountSerializer(serializers.Serializer):
    """
    Serializer for unlinking Facebook from account.
    """
    password = serializers.CharField(
        write_only=True,
        help_text=_("Current account password for verification")
    )

    def validate(self, attrs):
        """
        Validate password and ensure user has another auth method available
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError(_("Authentication required"))

        user = request.user
        password = attrs.get('password')

        if not user.check_password(password):
            raise serializers.ValidationError({
                'password': _("Current password is incorrect")
            })

        if not user.facebook_id:
            raise serializers.ValidationError(_("Facebook account is not linked"))

        if not user.has_password_auth and not user.google_id:
            raise serializers.ValidationError(_(
                "Cannot unlink Facebook account: no other authentication method available. "
                "Please set a password or link Google account first."
            ))

        return attrs
