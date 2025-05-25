# parents/views.py
from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes
import logging

from .models import Parent
from .serializers import (
    ParentSerializer,
    ParentProfileUpdateSerializer,
    ParentDetailSerializer,
    ParentSummarySerializer,
    CommunicationPreferencesSerializer,
    ParentSearchSerializer
)
from .services import ParentService, ParentProfileError, ParentNotFoundError
from .permissions import IsParentOwnerOrReadOnly, IsParentOwner

logger = logging.getLogger(__name__)


class ParentProfileViewSet(GenericViewSet):
    """
    ViewSet for parent profile management
    """
    queryset = Parent.objects.select_related('user').all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'update_profile':
            return ParentProfileUpdateSerializer
        elif self.action == 'detail':
            return ParentDetailSerializer
        elif self.action in ['communication_preferences', 'update_communication_preferences']:
            return CommunicationPreferencesSerializer
        elif self.action == 'reset_communication_preferences':
            return None
        return ParentSerializer

    def get_permissions(self):
        """Set permissions based on action"""
        if self.action in ['profile', 'update_profile', 'completeness',
                          'communication_preferences', 'update_communication_preferences',
                          'reset_communication_preferences']:
            permission_classes = [IsParentOwner]
        elif self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticated, IsParentOwnerOrReadOnly]
        else:
            permission_classes = [permissions.IsAuthenticated]

        return [permission() for permission in permission_classes]

    def get_current_parent(self):
        """Get current user's parent profile"""
        try:
            return ParentService.get_parent_by_user_or_raise(self.request.user)
        except ParentNotFoundError as e:
            logger.warning(f"Parent profile access attempt by non-parent user: {self.request.user.email}")
            raise ParentProfileError(_("Parent profile not found. Please ensure you have a parent account."))

    @extend_schema(
        responses={
            200: ParentDetailSerializer,
            404: {'description': 'Parent profile not found'}
        },
        description="Get current parent's profile with detailed information",
        tags=['Parent Profile']
    )
    @action(detail=False, methods=['get'])
    def profile(self, request):
        """
        Get current parent's profile
        GET /api/parents/profile/
        """
        try:
            parent = self.get_current_parent()
            profile_data = ParentService.get_parent_profile_data(parent)

            logger.info(f"Parent profile accessed by: {request.user.email}")
            return Response(profile_data, status=status.HTTP_200_OK)

        except ParentProfileError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Unexpected error accessing parent profile for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to retrieve profile')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=ParentProfileUpdateSerializer,
        responses={
            200: {
                'description': 'Profile updated successfully',
                'example': {
                    'message': 'Profile updated successfully',
                    'profile': {'first_name': 'John', 'last_name': 'Doe'}
                }
            },
            400: {'description': 'Invalid data provided'},
            403: {'description': 'Profile update not allowed'}
        },
        description="Update current parent's profile",
        tags=['Parent Profile']
    )
    @action(detail=False, methods=['patch'])
    def update_profile(self, request):
        """
        Update current parent's profile
        PATCH /api/parents/profile/
        """
        try:
            parent = self.get_current_parent()

            # Validate user can update profile
            if not request.user.is_verified:
                return Response({
                    'error': _('Email must be verified before updating profile')
                }, status=status.HTTP_403_FORBIDDEN)

            serializer = self.get_serializer(data=request.data, partial=True)

            if serializer.is_valid():
                try:
                    # Validate profile data according to business rules
                    validated_data = ParentService.validate_profile_data(serializer.validated_data)

                    # Update profile using service
                    updated_parent = ParentService.update_parent_profile(parent, validated_data)

                    # Return updated profile data
                    profile_data = ParentService.get_parent_profile_data(updated_parent)

                    logger.info(f"Parent profile updated by: {request.user.email}")
                    return Response({
                        'message': _('Profile updated successfully'),
                        'profile': profile_data
                    }, status=status.HTTP_200_OK)

                except ParentProfileError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except ParentProfileError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Unexpected error updating parent profile for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to update profile')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: {
                'description': 'Profile completeness information',
                'example': {
                    'overall_score': 75.5,
                    'required_score': 100.0,
                    'optional_score': 60.0,
                    'is_complete': True,
                    'missing_required_fields': [],
                    'missing_optional_fields': ['address_line1', 'postal_code']
                }
            }
        },
        description="Get profile completeness score and missing fields",
        tags=['Parent Profile']
    )
    @action(detail=False, methods=['get'])
    def completeness(self, request):
        """
        Get profile completeness information
        GET /api/parents/profile/completeness/
        """
        try:
            parent = self.get_current_parent()
            completeness_data = ParentService.calculate_profile_completeness(parent)

            return Response(completeness_data, status=status.HTTP_200_OK)

        except ParentProfileError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error calculating profile completeness for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to calculate profile completeness')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: CommunicationPreferencesSerializer,
        },
        description="Get current communication preferences",
        tags=['Parent Profile']
    )
    @action(detail=False, methods=['get', 'patch'], url_path='communication-preferences')
    def communication_preferences(self, request):
        """
        Get or update communication preferences
        GET /api/parents/profile/communication-preferences/
        PATCH /api/parents/profile/communication-preferences/
        """
        try:
            parent = self.get_current_parent()

            if request.method == 'GET':
                # Get preferences - ensure we always return a complete preferences dict
                preferences = parent.communication_preferences
                if not preferences:
                    preferences = Parent.get_default_communication_preferences()

                return Response(preferences, status=status.HTTP_200_OK)

            elif request.method == 'PATCH':
                # Update preferences
                serializer = CommunicationPreferencesSerializer(data=request.data, partial=True)

                if serializer.is_valid():
                    try:
                        # Update preferences using service
                        ParentService._update_communication_preferences(parent, serializer.validated_data)

                        # Return updated preferences
                        updated_preferences = parent.communication_preferences

                        logger.info(f"Communication preferences updated by: {request.user.email}")
                        return Response({
                            'message': _('Communication preferences updated successfully'),
                            'preferences': updated_preferences
                        }, status=status.HTTP_200_OK)

                    except ParentProfileError as e:
                        return Response({
                            'error': str(e)
                        }, status=status.HTTP_400_BAD_REQUEST)

                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except ParentProfileError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error with communication preferences for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to process communication preferences')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: {
                'description': 'Communication preferences reset to defaults',
                'example': {
                    'message': 'Communication preferences reset to defaults',
                    'preferences': {'email_notifications': True, 'sms_notifications': False}
                }
            }
        },
        description="Reset communication preferences to default values",
        tags=['Parent Profile']
    )
    @action(detail=False, methods=['post'], url_path='communication-preferences/reset')
    def reset_communication_preferences(self, request):
        """
        Reset communication preferences to defaults
        POST /api/parents/communication-preferences/reset/
        """
        try:
            parent = self.get_current_parent()

            # Reset to defaults using service
            updated_parent = ParentService.reset_communication_preferences_to_default(parent)

            logger.info(f"Communication preferences reset to defaults by: {request.user.email}")
            return Response({
                'message': _('Communication preferences reset to defaults'),
                'preferences': updated_parent.communication_preferences
            }, status=status.HTTP_200_OK)

        except ParentProfileError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error resetting communication preferences for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to reset communication preferences')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ParentManagementViewSet(GenericViewSet, ListModelMixin, RetrieveModelMixin):
    """
    ViewSet for parent management (Admin and limited access for psychologists)
    """
    queryset = Parent.objects.select_related('user').all()
    permission_classes = [permissions.IsAuthenticated, IsParentOwnerOrReadOnly]

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'retrieve':
            return ParentDetailSerializer
        elif self.action == 'search':
            return ParentSearchSerializer
        elif self.action == 'list':
            return ParentSummarySerializer
        return ParentSerializer

    def get_queryset(self):
        """Filter queryset based on user permissions"""
        queryset = super().get_queryset()

        # Admins can see all parents
        if self.request.user.is_admin or self.request.user.is_staff:
            return queryset

        # Parents can only see their own profile
        elif self.request.user.is_parent:
            return queryset.filter(user=self.request.user)

        # Psychologists can see parents they have worked with
        # (This would need implementation once appointments/relationships are built)
        elif self.request.user.is_psychologist:
            # For now, return empty queryset
            # Later: return queryset.filter(children__appointments__psychologist__user=self.request.user).distinct()
            return queryset.none()

        # Default: no access
        return queryset.none()

    @extend_schema(
        description="List parents (filtered by permissions)",
        responses={200: ParentSummarySerializer(many=True)},
        tags=['Parent Management']
    )
    def list(self, request, *args, **kwargs):
        """List parents with permission filtering"""
        return super().list(request, *args, **kwargs)

    @extend_schema(
        description="Retrieve specific parent profile",
        responses={200: ParentDetailSerializer},
        tags=['Parent Management']
    )
    def retrieve(self, request, *args, **kwargs):
        """Retrieve specific parent profile"""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        request=ParentSearchSerializer,
        responses={
            200: ParentSummarySerializer(many=True),
            400: {'description': 'Invalid search parameters'}
        },
        description="Search parents by various criteria (Admin only)",
        tags=['Parent Management']
    )
    @action(detail=False, methods=['post'])
    def search(self, request):
        """
        Search parents by criteria
        POST /api/parents/search/
        """
        # Only admins can search all parents
        if not (request.user.is_admin or request.user.is_staff):
            return Response({
                'error': _('Permission denied')
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            try:
                # Build filter conditions
                filters = {}
                search_data = serializer.validated_data

                # Direct field filters
                direct_filters = [
                    'first_name', 'last_name', 'city', 'state_province', 'country'
                ]
                for field in direct_filters:
                    if search_data.get(field):
                        filters[f'{field}__icontains'] = search_data[field]

                # User-related filters
                if search_data.get('email'):
                    filters['user__email__icontains'] = search_data['email']
                if search_data.get('is_verified') is not None:
                    filters['user__is_verified'] = search_data['is_verified']

                # Date range filters
                if search_data.get('created_after'):
                    filters['created_at__gte'] = search_data['created_after']
                if search_data.get('created_before'):
                    filters['created_at__lte'] = search_data['created_before']

                # Apply filters
                queryset = self.get_queryset().filter(**filters)

                # Serialize results
                serializer = ParentSummarySerializer(queryset, many=True)

                logger.info(f"Parent search performed by admin {request.user.email}")
                return Response({
                    'count': queryset.count(),
                    'results': serializer.data
                }, status=status.HTTP_200_OK)

            except Exception as e:
                logger.error(f"Error in parent search by {request.user.email}: {str(e)}")
                return Response({
                    'error': _('Search failed')
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)