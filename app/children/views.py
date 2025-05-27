# children/views.py
from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes
import logging
from rest_framework.exceptions import PermissionDenied


from .models import Child
from .serializers import (
    ChildSerializer,
    ChildCreateSerializer,
    ChildUpdateSerializer,
    ChildDetailSerializer,
    ChildSummarySerializer,
    ConsentManagementSerializer,
    BulkConsentSerializer,
    ChildSearchSerializer
)
from .services import (
    ChildService,
    ChildProfileError,
    ChildNotFoundError,
    ChildAccessDeniedError,
    ConsentManagementError
)
from .permissions import (
    IsChildOwner,
    IsChildOwnerOrReadOnly,
    CanCreateChildForParent,
    CanManageChildConsent,
    CanSearchChildren,
    ChildProfilePermissions
)
from parents.services import ParentService, ParentNotFoundError

logger = logging.getLogger(__name__)


class ChildProfileViewSet(GenericViewSet):
    """
    ViewSet for child profile management by parents
    """
    queryset = Child.objects.select_related('parent__user').all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return ChildCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ChildUpdateSerializer
        elif self.action == 'detail':
            return ChildDetailSerializer
        elif self.action in ['manage_consent']:
            return ConsentManagementSerializer
        elif self.action == 'bulk_consent':
            return BulkConsentSerializer
        elif self.action == 'list':
            return ChildSummarySerializer
        return ChildSerializer

    def get_permissions(self):
        """Set permissions based on action"""
        if self.action == 'create':
            permission_classes = [permissions.IsAuthenticated, CanCreateChildForParent]
        elif self.action in ['update', 'partial_update', 'destroy']:
            # Allow both child owners AND admins
            permission_classes = [permissions.IsAuthenticated, IsChildOwnerOrReadOnly]
        elif self.action in ['manage_consent', 'bulk_consent']:
            permission_classes = [permissions.IsAuthenticated, CanManageChildConsent]
        elif self.action in ['list', 'my_children']:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['retrieve', 'profile_summary']:
            permission_classes = [permissions.IsAuthenticated, IsChildOwnerOrReadOnly]
        else:
            permission_classes = [permissions.IsAuthenticated, ChildProfilePermissions]

        return [permission() for permission in permission_classes]

    def get_current_parent(self):
        """Get current user's parent profile"""
        try:
            return ParentService.get_parent_by_user_or_raise(self.request.user)
        except ParentNotFoundError as e:
            logger.warning(f"Child profile access attempt by non-parent user: {self.request.user.email}")
            raise ChildProfileError(_("Parent profile not found. Please ensure you have a parent account."))

    @extend_schema(
        responses={
            200: ChildSummarySerializer(many=True),
            404: {'description': 'Parent profile not found'}
        },
        description="Get current parent's children list",
        tags=['Child Profile']
    )
    @action(detail=False, methods=['get'])
    def my_children(self, request):
        """
        Get current parent's children
        GET /api/children/my-children/
        """
        try:
            parent = self.get_current_parent()
            children = ChildService.get_children_for_parent(parent)

            serializer = ChildSummarySerializer(children, many=True)

            logger.info(f"Retrieved {len(children)} children for parent: {request.user.email}")
            return Response({
                'count': len(children),
                'children': serializer.data
            }, status=status.HTTP_200_OK)

        except ChildProfileError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Unexpected error retrieving children for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to retrieve children')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=ChildCreateSerializer,
        responses={
            201: {
                'description': 'Child profile created successfully',
                'example': {
                    'message': 'Child profile created successfully',
                    'child': {'id': 'uuid', 'first_name': 'John', 'age': 8}
                }
            },
            400: {'description': 'Invalid data provided'},
            403: {'description': 'Child creation not allowed'}
        },
        description="Create a new child profile",
        tags=['Child Profile']
    )
    def create(self, request):
        """
        Create a new child profile
        POST /api/children/profile/
        """
        try:
            # Handle JSON parsing errors early
            if request.content_type == 'application/json' and request.body:
                try:
                    import json
                    json.loads(request.body.decode('utf-8'))
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    logger.warning(f"Invalid JSON received: {str(e)}")
                    return Response({
                        'error': _('Invalid JSON format')
                    }, status=status.HTTP_400_BAD_REQUEST)

            # Get parent - this might raise ChildProfileError if parent not found
            try:
                parent = self.get_current_parent()
            except ChildProfileError as e:
                return Response({
                    'error': str(e)
                }, status=status.HTTP_404_NOT_FOUND)

            # Validate serializer data
            serializer = self.get_serializer(data=request.data)

            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            try:
                # Create child using service
                child = ChildService.create_child_profile(parent, serializer.validated_data)

                # Return created child data
                child_data = ChildService.get_child_profile_data(child)

                logger.info(f"Child profile created: {child.full_name} for parent {request.user.email}")
                return Response({
                    'message': _('Child profile created successfully'),
                    'child': child_data
                }, status=status.HTTP_201_CREATED)

            except ChildProfileError as e:
                return Response({
                    'error': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Unexpected error creating child profile for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to create child profile')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: ChildDetailSerializer,
            404: {'description': 'Child not found'}
        },
        description="Get detailed child profile",
        tags=['Child Profile']
    )
    def retrieve(self, request, pk=None):
        """
        Get detailed child profile
        GET /api/children/{id}/
        """
        try:
            # Validate UUID format first
            try:
                import uuid
                uuid.UUID(pk)
            except (ValueError, TypeError):
                return Response({
                    'error': _('Invalid child ID format')
                }, status=status.HTTP_404_NOT_FOUND)

            child = ChildService.get_child_by_id_or_raise(pk)

            # Permission check happens at permission level
            self.check_object_permissions(request, child)

            child_data = ChildService.get_child_profile_data(child)

            logger.info(f"Child profile accessed: {child.full_name} by {request.user.email}")
            return Response(child_data, status=status.HTTP_200_OK)

        except ChildNotFoundError:
            return Response({
                'error': _('Child not found')
            }, status=status.HTTP_404_NOT_FOUND)
        except PermissionDenied:  # Changed from PermissionError
            return Response({
                'error': _('Permission denied')
            }, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            logger.error(f"Error retrieving child profile {pk} for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to retrieve child profile')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=ChildUpdateSerializer,
        responses={
            200: {
                'description': 'Child profile updated successfully',
                'example': {
                    'message': 'Child profile updated successfully',
                    'child': {'id': 'uuid', 'first_name': 'John', 'age': 8}
                }
            },
            400: {'description': 'Invalid data provided'},
            404: {'description': 'Child not found'}
        },
        description="Update child profile",
        tags=['Child Profile']
    )
    def partial_update(self, request, pk=None):
        """
        Update child profile
        PATCH /api/children/{id}/
        """
        try:
            # Validate UUID format first
            try:
                import uuid
                uuid.UUID(pk)
            except (ValueError, TypeError):
                return Response({
                    'error': _('Invalid child ID format')
                }, status=status.HTTP_404_NOT_FOUND)

            child = ChildService.get_child_by_id_or_raise(pk)

            # Permission check
            self.check_object_permissions(request, child)

            serializer = self.get_serializer(data=request.data, partial=True)

            if serializer.is_valid():
                try:
                    # Update child using service
                    updated_child = ChildService.update_child_profile(child, serializer.validated_data)

                    # Return updated child data
                    child_data = ChildService.get_child_profile_data(updated_child)

                    logger.info(f"Child profile updated: {child.full_name} by {request.user.email}")
                    return Response({
                        'message': _('Child profile updated successfully'),
                        'child': child_data
                    }, status=status.HTTP_200_OK)

                except ChildProfileError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except ChildNotFoundError:
            return Response({
                'error': _('Child not found')
            }, status=status.HTTP_404_NOT_FOUND)
        except PermissionDenied:
            return Response({
                'error': _('Permission denied')
            }, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            logger.error(f"Error updating child profile {pk} for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to update child profile')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            204: {'description': 'Child profile deleted successfully'},
            404: {'description': 'Child not found'},
            403: {'description': 'Permission denied'}
        },
        description="Delete child profile",
        tags=['Child Profile']
    )
    def destroy(self, request, pk=None):
        """
        Delete child profile
        DELETE /api/children/{id}/
        """
        try:
            # Validate UUID format first
            try:
                import uuid
                uuid.UUID(pk)
            except (ValueError, TypeError):
                return Response({
                    'error': _('Invalid child ID format')
                }, status=status.HTTP_404_NOT_FOUND)

            child = ChildService.get_child_by_id_or_raise(pk)

            # Permission check
            self.check_object_permissions(request, child)

            child_name = child.full_name

            # Delete child using service
            ChildService.delete_child_profile(child)

            logger.info(f"Child profile deleted: {child_name} by {request.user.email}")
            return Response({
                'message': _('Child profile deleted successfully')
            }, status=status.HTTP_204_NO_CONTENT)

        except ChildNotFoundError:
            return Response({
                'error': _('Child not found')
            }, status=status.HTTP_404_NOT_FOUND)
        except PermissionDenied:
            return Response({
                'error': _('Permission denied')
            }, status=status.HTTP_403_FORBIDDEN)
        except ChildProfileError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error deleting child profile {pk} for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to delete child profile')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: {
                'description': 'Child profile summary',
                'example': {
                    'profile_completeness': 85.5,
                    'consent_summary': {'granted_count': 3, 'total_consents': 4},
                    'age_info': {'age': 8, 'age_in_months': 96}
                }
            },
            404: {'description': 'Child not found'}
        },
        description="Get child profile summary with metrics",
        tags=['Child Profile']
    )
    @action(detail=True, methods=['get'])
    def profile_summary(self, request, pk=None):
        """
        Get child profile summary with completeness and metrics
        GET /api/children/{id}/profile-summary/
        """
        try:
            child = ChildService.get_child_by_id_or_raise(pk)

            # Permission check
            self.check_object_permissions(request, child)

            summary_data = {
                'id': str(child.id),
                'full_name': child.full_name,
                'display_name': child.display_name,
                'age': child.age,
                'age_in_months': child.age_in_months,
                'profile_completeness': child.get_profile_completeness(),
                'consent_summary': ChildService.get_consent_summary(child),
                'has_psychology_history': child.has_psychology_history,
                'age_appropriate_grades': child.get_age_appropriate_grade_suggestions(),
                'last_updated': child.updated_at
            }

            return Response(summary_data, status=status.HTTP_200_OK)

        except ChildNotFoundError:
            return Response({
                'error': _('Child not found')
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error getting child summary {pk} for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to get child summary')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=ConsentManagementSerializer,
        responses={
            200: {
                'description': 'Consent updated successfully',
                'example': {
                    'message': 'Consent updated successfully',
                    'consent_summary': {'granted_count': 3, 'total_consents': 4}
                }
            },
            400: {'description': 'Invalid consent data'},
            404: {'description': 'Child not found'}
        },
        description="Manage consent for a child",
        tags=['Child Profile']
    )
    @action(detail=True, methods=['post'])
    def manage_consent(self, request, pk=None):
        """
        Manage consent for a specific child
        POST /api/children/{id}/manage-consent/
        """
        try:
            # Validate UUID format first
            try:
                import uuid
                uuid.UUID(pk)
            except (ValueError, TypeError):
                return Response({
                    'error': _('Invalid child ID format')
                }, status=status.HTTP_404_NOT_FOUND)

            child = ChildService.get_child_by_id_or_raise(pk)

            # Permission check
            self.check_object_permissions(request, child)

            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                try:
                    # Save consent using serializer method
                    updated_child = serializer.save(child_instance=child)

                    # Return updated consent summary
                    consent_summary = ChildService.get_consent_summary(updated_child)

                    action = "granted" if serializer.validated_data['granted'] else "revoked"
                    consent_type = serializer.validated_data['consent_type']

                    logger.info(f"Consent {action} for child {child.full_name}: {consent_type} by {request.user.email}")
                    return Response({
                        'message': _('Consent updated successfully'),
                        'consent_summary': consent_summary
                    }, status=status.HTTP_200_OK)

                except ConsentManagementError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except ChildNotFoundError:
            return Response({
                'error': _('Child not found')
            }, status=status.HTTP_404_NOT_FOUND)
        except PermissionDenied:
            return Response({
                'error': _('Permission denied')
            }, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            logger.error(f"Error managing consent for child {pk} by {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to manage consent')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=BulkConsentSerializer,
        responses={
            200: {
                'description': 'Bulk consent updated successfully',
                'example': {
                    'message': 'Bulk consent updated successfully',
                    'updated_consents': ['service_consent', 'assessment_consent'],
                    'consent_summary': {'granted_count': 4, 'total_consents': 4}
                }
            },
            400: {'description': 'Invalid consent data'},
            404: {'description': 'Child not found'}
        },
        description="Update multiple consent types at once",
        tags=['Child Profile']
    )
    @action(detail=True, methods=['post'])
    def bulk_consent(self, request, pk=None):
        """
        Update multiple consent types at once
        POST /api/children/{id}/bulk-consent/
        """
        try:
            child = ChildService.get_child_by_id_or_raise(pk)

            # Permission check
            self.check_object_permissions(request, child)

            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                try:
                    # Save bulk consent using serializer method
                    updated_child = serializer.save(child_instance=child)

                    # Return updated consent summary
                    consent_summary = ChildService.get_consent_summary(updated_child)

                    action = "granted" if serializer.validated_data['granted'] else "revoked"
                    consent_types = serializer.validated_data['consent_types']

                    logger.info(f"Bulk consent {action} for child {child.full_name}: {consent_types} by {request.user.email}")
                    return Response({
                        'message': _('Bulk consent updated successfully'),
                        'updated_consents': consent_types,
                        'consent_summary': consent_summary
                    }, status=status.HTTP_200_OK)

                except ConsentManagementError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except ChildNotFoundError:
            return Response({
                'error': _('Child not found')
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error updating bulk consent for child {pk} by {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to update bulk consent')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ChildManagementViewSet(GenericViewSet, ListModelMixin, RetrieveModelMixin):
    """
    ViewSet for child management (Admin and limited access for psychologists)
    """
    queryset = Child.objects.select_related('parent__user').all()
    permission_classes = [permissions.IsAuthenticated, IsChildOwnerOrReadOnly]

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'retrieve':
            return ChildDetailSerializer
        elif self.action == 'search':
            return ChildSearchSerializer
        elif self.action == 'list':
            return ChildSummarySerializer
        return ChildSerializer

    def get_queryset(self):
        """Filter queryset based on user permissions"""
        queryset = super().get_queryset()

        # Admins can see all children
        if self.request.user.is_admin or self.request.user.is_staff:
            return queryset

        # Parents can only see their own children
        elif self.request.user.is_parent:
            try:
                parent = ParentService.get_parent_by_user(self.request.user)
                if parent:
                    return queryset.filter(parent=parent)
            except Exception:
                pass
            return queryset.none()

        # Psychologists can see children they have worked with
        # (This would need implementation once appointments/relationships are built)
        elif self.request.user.is_psychologist:
            # For now, return empty queryset
            # Later: return queryset.filter(appointments__psychologist__user=self.request.user).distinct()
            return queryset.none()

        # Default: no access
        return queryset.none()

    @extend_schema(
        description="List children (filtered by permissions)",
        responses={200: ChildSummarySerializer(many=True)},
        tags=['Child Management']
    )
    def list(self, request, *args, **kwargs):
        """List children with permission filtering"""
        return super().list(request, *args, **kwargs)

    @extend_schema(
        description="Retrieve specific child profile",
        responses={200: ChildDetailSerializer},
        tags=['Child Management']
    )
    def retrieve(self, request, *args, **kwargs):
        """Retrieve specific child profile"""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        request=ChildSearchSerializer,
        responses={
            200: ChildSummarySerializer(many=True),
            400: {'description': 'Invalid search parameters'}
        },
        description="Search children by various criteria",
        tags=['Child Management']
    )
    @action(detail=False, methods=['post'])
    def search(self, request):
        """
        Search children by criteria
        POST /api/children/manage/search/
        """
        # Check search permission
        if not CanSearchChildren().has_permission(request, self):
            return Response({
                'error': _('Permission denied')
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            try:
                # Perform search using service - but pass user for proper filtering
                children = ChildService.search_children(serializer.validated_data, request.user)

                # No additional filtering needed here - the service should handle it correctly

                # Serialize results
                result_serializer = ChildSummarySerializer(children, many=True)

                logger.info(f"Child search performed by {request.user.email}: {len(children)} results")
                return Response({
                    'count': len(children),
                    'results': result_serializer.data
                }, status=status.HTTP_200_OK)

            except Exception as e:
                logger.error(f"Error in child search by {request.user.email}: {str(e)}")
                return Response({
                    'error': _('Search failed')
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        responses={
            200: {
                'description': 'Platform-wide child statistics',
                'example': {
                    'total_children': 150,
                    'age_distribution': {'5-8': 45, '9-12': 65, '13-17': 40},
                    'consent_stats': {'fully_consented': 120, 'partial_consent': 25, 'no_consent': 5}
                }
            },
            403: {'description': 'Permission denied'}
        },
        description="Get platform-wide child statistics (Admin only)",
        tags=['Child Management']
    )
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Get platform-wide child statistics
        GET /api/children/manage/statistics/
        """
        # Only admins can view platform statistics
        if not (request.user.is_admin or request.user.is_staff):
            return Response({
                'error': _('Permission denied')
            }, status=status.HTTP_403_FORBIDDEN)

        try:
            queryset = Child.objects.all()

            # Basic counts
            total_children = queryset.count()

            # Age distribution
            from django.db import models
            age_distribution = {
                '5-8': queryset.filter(date_of_birth__gte='2016-01-01', date_of_birth__lte='2019-12-31').count(),
                '9-12': queryset.filter(date_of_birth__gte='2012-01-01', date_of_birth__lte='2015-12-31').count(),
                '13-17': queryset.filter(date_of_birth__gte='2007-01-01', date_of_birth__lte='2011-12-31').count()
            }

            # Psychology history
            has_psychology_history = queryset.filter(
                models.Q(has_seen_psychologist=True) | models.Q(has_received_therapy=True)
            ).count()

            # Gender distribution (excluding null/empty)
            gender_stats = {}
            for gender in queryset.exclude(gender__isnull=True).exclude(gender='').values_list('gender', flat=True).distinct():
                gender_stats[gender] = queryset.filter(gender=gender).count()

            statistics = {
                'total_children': total_children,
                'age_distribution': age_distribution,
                'psychology_history': {
                    'with_history': has_psychology_history,
                    'without_history': total_children - has_psychology_history
                },
                'gender_distribution': gender_stats,
                'verified_parents': queryset.filter(parent__user__is_verified=True).count(),
                'active_profiles': queryset.filter(parent__user__is_active=True).count()
            }

            logger.info(f"Child statistics accessed by admin {request.user.email}")
            return Response(statistics, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error generating child statistics for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to generate statistics')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)