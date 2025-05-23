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

