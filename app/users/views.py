from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from rest_framework.authtoken.models import Token
from django.contrib.auth import login, logout
from django.utils.translation import gettext_lazy as _

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

                # Create token for immediate login (optional)
                token, created = Token.objects.get_or_create(user=user)

                return Response({
                    'message': _('Registration successful. Please check your email for verification.'),
                    'user': UserSerializer(user).data,
                    'token': token.key
                }, status=status.HTTP_201_CREATED)

            except Exception as e:
                return Response({
                    'error': _('Registration failed. Please try again.')
                }, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        """
        Get current user profile
        GET /api/auth/me/
        """
        profile_data = UserService.get_user_profile(request.user)
        return Response(profile_data, status=status.HTTP_200_OK)

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


class EmailVerificationView(APIView):
    """
    Email verification endpoint
    """
    permission_classes = [permissions.AllowAny]

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


class PasswordResetRequestView(APIView):
    """
    Password reset request endpoint
    """
    permission_classes = [permissions.AllowAny]

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


class PasswordResetConfirmView(APIView):
    """
    Password reset confirmation endpoint
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
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


class UserViewSet(GenericViewSet):
    """
    ViewSet for user management (future use)
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