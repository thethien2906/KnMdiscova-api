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
    ParentSearchSerializer,
    FaceVerificationStatusSerializer,
    RegenerateFaceEmbeddingSerializer
)
from .services import ParentService, ParentProfileError, ParentNotFoundError
from appointments.services import FaceVerificationService, FaceVerificationError
from .permissions import IsParentOwnerOrReadOnly, IsParentOwner
from .signals import face_embedding_requested
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
            400: {'description': 'Invalid data provided or image validation failed'},
            403: {'description': 'Profile update not allowed'}
        },
        description="Update current parent's profile with image validation",
        tags=['Parent Profile']
    )
    @action(detail=False, methods=['patch'])
    def update_profile(self, request):
        """
        Update current parent's profile
        PATCH /api/parents/profile/update_profile/  # Note: update this to match your URL
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

                    # Update profile using service with image validation
                    updated_parent = ParentService.update_parent_profile_with_image_validation(parent, validated_data)

                    # Return updated profile data
                    profile_data = ParentService.get_parent_profile_data(updated_parent)

                    logger.info(f"Parent profile updated by: {request.user.email}")
                    return Response({
                        'message': _('Profile updated successfully'),
                        'profile': profile_data
                    }, status=status.HTTP_200_OK)

                except ParentProfileError as e:
                    # Handle validation errors (including image validation failures)
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
    from parents.signals import face_embedding_requested

    @extend_schema(
        responses={
            200: FaceVerificationStatusSerializer,
            404: {'description': 'Parent profile not found'}
        },
        description="Get current parent's face verification status",
        tags=['Parent Profile']
    )
    @action(detail=False, methods=['get'], url_path='face-verification-status')
    def face_verification_status(self, request):
        """
        Get face verification status for current parent
        GET /api/parents/profile/face-verification-status/
        """
        try:
            parent = self.get_current_parent()

            status_data = FaceVerificationService.get_parent_embedding_status(parent)

            serializer = FaceVerificationStatusSerializer(status_data)

            logger.info(f"Face verification status accessed by: {request.user.email}")

            # NOW THIS WORKS: `status` refers to the imported module
            return Response(serializer.data, status=status.HTTP_200_OK)

        except ParentProfileError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error getting face verification status for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to get face verification status')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    @extend_schema(
        request=RegenerateFaceEmbeddingSerializer,
        responses={
            200: {
                'description': 'Face embedding generation triggered',
                'example': {
                    'message': 'Face embedding generation started',
                    'task_id': 'celery-task-uuid',
                    'estimated_completion': '2-3 minutes'
                }
            },
            400: {'description': 'Cannot generate embedding'},
            404: {'description': 'Parent profile not found'}
        },
        description="Trigger face embedding generation/regeneration",
        tags=['Parent Profile']
    )
    @action(detail=False, methods=['post'], url_path='generate-face-embedding')
    def generate_face_embedding(self, request):
        """
        Trigger face embedding generation for current parent
        POST /api/parents/profile/generate-face-embedding/
        """
        try:
            parent = self.get_current_parent()

            serializer = RegenerateFaceEmbeddingSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            force_regenerate = serializer.validated_data.get('force_regenerate', False)

            # Check if parent has profile picture
            if not parent.user.profile_picture_url:
                return Response({
                    'error': _('Please upload a profile picture first'),
                    'action_required': 'UPLOAD_PICTURE'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check if embedding already exists and force_regenerate is False
            if parent.face_embedding and not force_regenerate:
                return Response({
                    'message': _('Face embedding already exists. Use force_regenerate=true to regenerate.'),
                    'has_embedding': True,
                    'embedding_created_at': parent.face_embedding_created_at
                }, status=status.HTTP_200_OK)

            try:
                # Validate profile picture first
                validation_result = FaceVerificationService.validate_profile_picture_for_embedding(
                    parent.user.profile_picture_url
                )

                if not validation_result['valid']:
                    return Response({
                        'error': validation_result['error'],
                        'error_code': validation_result.get('error_code'),
                        'action_required': 'UPDATE_PICTURE'
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Trigger embedding generation via signal
                task_id = face_embedding_requested.send(
                    sender=self.__class__,
                    user_id=str(parent.user.id)
                )

                response_data = {
                    'message': _('Face embedding generation started'),
                    'profile_picture_url': parent.user.profile_picture_url,
                    'estimated_completion': '2-3 minutes'
                }

                # Include task ID if available
                if task_id and len(task_id) > 0:
                    task_result = task_id[0][1]  # Signal returns list of (receiver, result) tuples
                    if task_result:
                        response_data['task_id'] = str(task_result)

                logger.info(f"Face embedding generation triggered by: {request.user.email}")
                return Response(response_data, status=status.HTTP_200_OK)

            except FaceVerificationError as e:
                return Response({
                    'error': str(e),
                    'error_code': 'VERIFICATION_ERROR'
                }, status=status.HTTP_400_BAD_REQUEST)

        except ParentProfileError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error generating face embedding for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to generate face embedding')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    @extend_schema(
        responses={
            200: {
                'description': 'Face embedding cleared successfully',
                'example': {
                    'message': 'Face embedding cleared successfully',
                    'privacy_note': 'All biometric data has been removed'
                }
            },
            404: {'description': 'Parent profile not found'}
        },
        description="Clear face embedding data (for privacy/GDPR compliance)",
        tags=['Parent Profile']
    )
    @action(detail=False, methods=['delete'], url_path='clear-face-embedding')
    def clear_face_embedding(self, request):
        """
        Clear face embedding data for privacy/GDPR compliance
        DELETE /api/parents/profile/clear-face-embedding/
        """
        try:
            parent = self.get_current_parent()

            if not parent.face_embedding:
                return Response({
                    'message': _('No face embedding data to clear'),
                    'has_embedding': False
                }, status=status.HTTP_200_OK)

            # Clear the embedding
            parent.clear_face_embedding()

            logger.info(f"Face embedding cleared for user: {request.user.email}")
            return Response({
                'message': _('Face embedding cleared successfully'),
                'privacy_note': _('All biometric data has been removed'),
                'has_embedding': False
            }, status=status.HTTP_200_OK)

        except ParentProfileError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error clearing face embedding for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to clear face embedding')
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