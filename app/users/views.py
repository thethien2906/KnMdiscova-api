# users/views.py
from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.authtoken.models import Token
from django.contrib.auth import login, logout
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes

from .models import User
from .serializers import (
    UserSerializer,
    UserRegistrationSerializer,
    LoginSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer
)
from .services import AuthenticationService, UserService


class AuthViewSet(GenericViewSet):
    """
    ViewSet for authentication endpoints
    """

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=UserRegistrationSerializer,
        responses={
            201: {
                'description': 'Registration successful',
                'example': {
                    'message': 'Registration successful. Please check your email for verification.',
                    'user': {'id': 1, 'email': 'user@example.com', 'user_type': 'Parent'},
                    'token': 'your-auth-token'
                }
            },
            400: {'description': 'Bad request'}
        },
        description="Register a new user",
        tags=['Authentication']
    )
    @action(detail=False, methods=['post'])
    def register(self, request):
        """
        Register a new user
        POST /api/auth/register/
        """
        serializer = UserRegistrationSerializer(data=request.data)

        if serializer.is_valid():
            try:
                user = serializer.save()
                print(f"User created successfully: {user}")  # Debug line

                # Create token for immediate login (optional)
                token, created = Token.objects.get_or_create(user=user)
                print(f"Token created: {token.key}")  # Debug line

                user_data = UserSerializer(user).data
                print(f"User serialized: {user_data}")  # Debug line

                return Response({
                    'message': _('Registration successful. Please check your email for verification.'),
                    'user': user_data,
                    'token': token.key
                }, status=status.HTTP_201_CREATED)

            except Exception as e:
                print(f"Registration error: {str(e)}")  # Debug line
                print(f"Error type: {type(e)}")  # Debug line
                import traceback
                traceback.print_exc()  # This will print the full stack trace

                return Response({
                    'error': _('Registration failed. Please try again.')
                }, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=LoginSerializer,
        responses={
            200: {
                'description': 'Login successful',
                'example': {
                    'message': 'Login successful',
                    'user': {'id': 1, 'email': 'user@example.com', 'user_type': 'Parent'},
                    'token': 'your-auth-token'
                }
            },
            400: {'description': 'Invalid credentials'}
        },
        description="User login",
        tags=['Authentication']
    )
    @action(detail=False, methods=['post'])
    def login(self, request):
        """
        User login
        POST /api/auth/login/
        """
        serializer = LoginSerializer(data=request.data, context={'request': request})

        if serializer.is_valid():
            user = serializer.validated_data['user']

            # Create or get token
            token, created = Token.objects.get_or_create(user=user)

            # Update last login
            from django.utils import timezone
            user.last_login_date = timezone.now()
            user.save(update_fields=['last_login_date'])

            return Response({
                'message': _('Login successful'),
                'user': UserSerializer(user).data,
                'token': token.key
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=None,
        responses={
            200: {'description': 'Logged out successfully'},
            400: {'description': 'Logout failed'}
        },
        description="User logout - deletes authentication token",
        tags=['Authentication']
    )
    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def logout(self, request):
        """
        User logout
        POST /api/auth/logout/
        """
        try:
            # Delete the user's token
            request.user.auth_token.delete()
            return Response({
                'message': _('Logged out successfully')
            }, status=status.HTTP_200_OK)
        except Exception:
            return Response({
                'error': _('Logout failed')
            }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        responses={
            200: UserSerializer,
        },
        description="Get current authenticated user's profile",
        tags=['Authentication']
    )
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        """
        Get current user profile
        GET /api/auth/me/
        """
        profile_data = UserService.get_user_profile(request.user)
        return Response(profile_data, status=status.HTTP_200_OK)

    @extend_schema(
        request=UserSerializer(partial=True),
        responses={
            200: {
                'description': 'Profile updated successfully',
                'example': {
                    'message': 'Profile updated successfully',
                    'user': {'id': 1, 'email': 'user@example.com', 'user_type': 'Parent'}
                }
            },
            400: {'description': 'Profile update failed'}
        },
        description="Update current user's profile",
        tags=['Authentication']
    )
    @action(detail=False, methods=['patch'], permission_classes=[permissions.IsAuthenticated])
    def update_profile(self, request):
        """
        Update current user profile
        PATCH /api/auth/update-profile/
        """
        try:
            user = UserService.update_user_profile(request.user, **request.data)
            return Response({
                'message': _('Profile updated successfully'),
                'user': UserSerializer(user).data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'error': _('Profile update failed')
            }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['Authentication'])
class EmailVerificationView(APIView):
    """
    Email verification endpoint
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='uidb64',
                location=OpenApiParameter.PATH,
                description='Base64 encoded user ID',
                required=True,
                type=str
            ),
            OpenApiParameter(
                name='token',
                location=OpenApiParameter.PATH,
                description='Email verification token',
                required=True,
                type=str
            )
        ],
        responses={
            200: {
                'description': 'Email verified successfully',
                'example': {
                    'message': 'Email verified successfully',
                    'user': {'id': 1, 'email': 'user@example.com', 'is_verified': True}
                }
            },
            400: {'description': 'Invalid or expired token'}
        },
        description="Verify email address using token from email"
    )
    def get(self, request, uidb64, token):
        """
        Verify email using token from email link
        GET /api/auth/verify-email/<uidb64>/<token>/
        """
        user, message = AuthenticationService.verify_email(uidb64, token)

        if user:
            return Response({
                'message': message,
                'user': UserSerializer(user).data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': message
            }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['Authentication'])
class PasswordResetRequestView(APIView):
    """
    Password reset request endpoint
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={
            200: {
                'description': 'Password reset email sent',
                'example': {'message': 'Password reset email sent if account exists'}
            },
            400: {'description': 'Bad request'}
        },
        description="Request a password reset email"
    )
    def post(self, request):
        """
        Request password reset email
        POST /api/auth/password-reset/
        """
        serializer = PasswordResetRequestSerializer(data=request.data)

        if serializer.is_valid():
            success, message = serializer.save()

            return Response({
                'message': message
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['Authentication'])
class PasswordResetConfirmView(APIView):
    """
    Password reset confirmation endpoint
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=PasswordResetConfirmSerializer,
        responses={
            200: {
                'description': 'Password reset successful',
                'example': {'message': 'Password has been reset successfully'}
            },
            400: {'description': 'Invalid token or password'}
        },
        description="Confirm password reset with token and new password"
    )
    def post(self, request, *args, **kwargs):  # Changed this line
        """
        Confirm password reset using token
        POST /api/auth/password-reset-confirm/
        """
        serializer = PasswordResetConfirmSerializer(data=request.data)

        if serializer.is_valid():
            try:
                result = serializer.save()
                return Response({
                    'message': result['message']
                }, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({
                    'error': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@extend_schema(tags=['User Management'])
class UserViewSet(GenericViewSet, ListModelMixin, RetrieveModelMixin):
    """
    ViewSet for user management (admin use)
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAdminUser]
        else:
            permission_classes = [permissions.IsAuthenticated]

        return [permission() for permission in permission_classes]

    @extend_schema(
        description="List all users (Admin only)",
        responses={200: UserSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        description="Retrieve a specific user (Admin only)",
        responses={200: UserSerializer}
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)