# psychologists/views.py
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
from datetime import date, timedelta
from .models import Psychologist, PsychologistAvailability
from .serializers import (
    PsychologistSerializer,
    PsychologistProfileUpdateSerializer,
    PsychologistDetailSerializer,
    PsychologistMarketplaceSerializer,
    PsychologistSummarySerializer,
    PsychologistSearchSerializer,
    PsychologistAvailabilitySerializer,
    PsychologistEducationSerializer,
    PsychologistCertificationSerializer
)
from .services import (
    PsychologistService,
    PsychologistProfileError,
    PsychologistNotFoundError,
    PsychologistAccessDeniedError,
    AvailabilityManagementError,
    PsychologistAvailabilityService,

)
from .permissions import (
    IsPsychologistOwner,
    IsPsychologistOwnerOrReadOnly,
    CanCreatePsychologistProfile,
    CanManagePsychologistAvailability,
    CanSearchPsychologists,
    IsMarketplaceVisible,
    PsychologistProfilePermissions,
    PsychologistAvailabilityPermissions,
    PsychologistMarketplacePermissions
)

logger = logging.getLogger(__name__)


class PsychologistProfileViewSet(GenericViewSet):
    """
    ViewSet for psychologist profile management by psychologists themselves
    """
    queryset = Psychologist.objects.select_related('user').all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action in ['update_profile', 'partial_update']:
            return PsychologistProfileUpdateSerializer
        elif self.action == 'detail':
            return PsychologistDetailSerializer
        elif self.action == 'education':
            return PsychologistEducationSerializer
        elif self.action == 'certifications':
            return PsychologistCertificationSerializer
        return PsychologistSerializer

    def get_permissions(self):
        """Set permissions based on action"""
        if self.action == 'create':
            permission_classes = [permissions.IsAuthenticated, CanCreatePsychologistProfile]
        elif self.action in ['profile', 'update_profile', 'completeness', 'education', 'certifications']:
            permission_classes = [IsPsychologistOwner]
        elif self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticated, IsPsychologistOwnerOrReadOnly]
        else:
            permission_classes = [permissions.IsAuthenticated, PsychologistProfilePermissions]

        return [permission() for permission in permission_classes]

    def get_current_psychologist(self):
        """Get current user's psychologist profile"""
        try:
            return PsychologistService.get_psychologist_by_user_or_raise(self.request.user)
        except PsychologistNotFoundError as e:
            logger.warning(f"Psychologist profile access attempt by non-psychologist user: {self.request.user.email}")
            raise PsychologistProfileError(_("Psychologist profile not found. Please ensure you have a psychologist account."))

    @extend_schema(
        responses={
            200: PsychologistDetailSerializer,
            404: {'description': 'Psychologist profile not found'}
        },
        description="Get current psychologist's profile with detailed information",
        tags=['Psychologist Profile']
    )
    @action(detail=False, methods=['get'])
    def profile(self, request):
        """
        Get current psychologist's profile
        GET /api/psychologists/profile/
        """
        try:
            psychologist = self.get_current_psychologist()
            profile_data = PsychologistService.get_psychologist_profile_data(psychologist)

            logger.info(f"Psychologist profile accessed by: {request.user.email}")
            return Response(profile_data, status=status.HTTP_200_OK)

        except PsychologistProfileError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Unexpected error accessing psychologist profile for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to retrieve profile')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=PsychologistProfileUpdateSerializer,
        responses={
            201: {
                'description': 'Psychologist profile created successfully',
                'example': {
                    'message': 'Profile created successfully',
                    'profile': {'id': 'uuid', 'full_name': 'Dr. John Doe', 'verification_status': 'Pending'}
                }
            },
            400: {'description': 'Invalid data provided'},
            403: {'description': 'Profile creation not allowed'}
        },
        description="Create psychologist profile (after user registration and email verification)",
        tags=['Psychologist Profile']
    )
    def create(self, request):
        """
        Create psychologist profile
        POST /api/psychologists/profile/
        """
        try:
            # Check if profile already exists
            existing_psychologist = PsychologistService.get_psychologist_by_user(request.user)
            if existing_psychologist:
                return Response({
                    'error': _('Psychologist profile already exists')
                }, status=status.HTTP_400_BAD_REQUEST)

            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                try:
                    # Create psychologist profile using service
                    psychologist = PsychologistService.create_psychologist_profile(
                        request.user, serializer.validated_data
                    )

                    # Return created profile data
                    profile_data = PsychologistService.get_psychologist_profile_data(psychologist)

                    # Send welcome email
                    PsychologistService.send_profile_creation_welcome_email(psychologist)

                    logger.info(f"Psychologist profile created: {psychologist.full_name} for user {request.user.email}")
                    return Response({
                        'message': _('Profile created successfully'),
                        'profile': profile_data
                    }, status=status.HTTP_201_CREATED)

                except PsychologistProfileError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Unexpected error creating psychologist profile for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to create profile')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=PsychologistProfileUpdateSerializer,
        responses={
            200: {
                'description': 'Profile updated successfully',
                'example': {
                    'message': 'Profile updated successfully',
                    'profile': {'id': 'uuid', 'full_name': 'Dr. John Doe'}
                }
            },
            400: {'description': 'Invalid data provided'},
            403: {'description': 'Profile update not allowed'}
        },
        description="Update current psychologist's profile",
        tags=['Psychologist Profile']
    )
    @action(detail=False, methods=['patch'])
    def update_profile(self, request):
        """
        Update current psychologist's profile (both User and Psychologist data)
        PATCH /api/psychologists/profile/
        """
        try:
            psychologist = self.get_current_psychologist()
            user = psychologist.user

            # Validate user can update profile
            if not request.user.is_verified:
                return Response({
                    'error': _('Email must be verified before updating profile')
                }, status=status.HTTP_403_FORBIDDEN)

            # Separate user fields from psychologist fields
            user_fields = {}
            psychologist_fields = {}

            # Define which fields belong to User model
            user_updateable_fields = ['profile_picture_url', 'user_timezone']

            for field, value in request.data.items():
                if field in user_updateable_fields:
                    user_fields[field] = value
                else:
                    psychologist_fields[field] = value

            # Update User model if there are user fields
            if user_fields:
                try:
                    from users.services import UserService
                    UserService.update_user_profile(user, **user_fields)
                    logger.info(f"User profile updated for psychologist: {request.user.email}")
                except Exception as e:
                    logger.error(f"Failed to update user profile for {request.user.email}: {str(e)}")
                    return Response({
                        'error': _('Failed to update user profile')
                    }, status=status.HTTP_400_BAD_REQUEST)

            # Update Psychologist model if there are psychologist fields
            if psychologist_fields:
                serializer = self.get_serializer(psychologist, data=psychologist_fields, partial=True)

                if serializer.is_valid():
                    try:
                        # Update profile using service
                        updated_psychologist = PsychologistService.update_psychologist_profile(
                            psychologist, serializer.validated_data
                        )
                        logger.info(f"Psychologist profile updated by: {request.user.email}")

                    except PsychologistProfileError as e:
                        return Response({
                            'error': str(e)
                        }, status=status.HTTP_400_BAD_REQUEST)
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Return updated profile data (refresh from DB to get latest changes)
            refreshed_psychologist = self.get_current_psychologist()
            profile_data = PsychologistService.get_psychologist_profile_data(refreshed_psychologist)

            return Response({
                'message': _('Profile updated successfully'),
                'profile': profile_data
            }, status=status.HTTP_200_OK)

        except PsychologistProfileError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Unexpected error updating psychologist profile for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to update profile')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: {
                'description': 'Profile completeness information',
                'example': {
                    'profile_completeness': 85.5,
                    'verification_requirements': ['Office address required for initial consultations'],
                    'can_book_appointments': True,
                    'is_marketplace_visible': False
                }
            }
        },
        description="Get profile completeness score and verification status",
        tags=['Psychologist Profile']
    )
    @action(detail=False, methods=['get'])
    def completeness(self, request):
        """
        Get profile completeness information
        GET /api/psychologists/profile/completeness/
        """
        try:
            psychologist = self.get_current_psychologist()

            completeness_data = {
                'profile_completeness': psychologist.get_profile_completeness(),
                'verification_requirements': psychologist.get_verification_requirements(),
                'verification_status': psychologist.verification_status,
                'is_verified': psychologist.is_verified,
                'is_marketplace_visible': psychologist.is_marketplace_visible,
                'can_book_appointments': psychologist.can_book_appointments(),
                'license_is_valid': psychologist.license_is_valid,
                'services_offered': psychologist.services_offered
            }

            return Response(completeness_data, status=status.HTTP_200_OK)

        except PsychologistProfileError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error calculating profile completeness for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to calculate profile completeness')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=PsychologistEducationSerializer,
        responses={
            200: {
                'description': 'Education updated successfully',
                'example': {
                    'message': 'Education updated successfully',
                    'education': [{'degree': 'PhD Psychology', 'institution': 'University', 'year': 2020}]
                }
            },
            400: {'description': 'Invalid education data'}
        },
        description="Update psychologist's education entries",
        tags=['Psychologist Profile']
    )
    @action(detail=False, methods=['get', 'patch'])
    def education(self, request):
        """
        Get or update psychologist's education
        GET /api/psychologists/profile/education/
        PATCH /api/psychologists/profile/education/
        """
        try:
            psychologist = self.get_current_psychologist()

            if request.method == 'GET':
                return Response({
                    'education': psychologist.education or []
                }, status=status.HTTP_200_OK)

            elif request.method == 'PATCH':
                serializer = self.get_serializer(data=request.data)

                if serializer.is_valid():
                    try:
                        # Update education using serializer
                        updated_psychologist = serializer.update(psychologist, serializer.validated_data)

                        logger.info(f"Education updated for psychologist: {request.user.email}")
                        return Response({
                            'message': _('Education updated successfully'),
                            'education': updated_psychologist.education
                        }, status=status.HTTP_200_OK)

                    except PsychologistProfileError as e:
                        return Response({
                            'error': str(e)
                        }, status=status.HTTP_400_BAD_REQUEST)

                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except PsychologistProfileError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error managing education for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to manage education')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=PsychologistCertificationSerializer,
        responses={
            200: {
                'description': 'Certifications updated successfully',
                'example': {
                    'message': 'Certifications updated successfully',
                    'certifications': [{'name': 'CBT Certification', 'institution': 'Institute', 'year': 2021}]
                }
            },
            400: {'description': 'Invalid certification data'}
        },
        description="Update psychologist's certification entries",
        tags=['Psychologist Profile']
    )
    @action(detail=False, methods=['get', 'patch'])
    def certifications(self, request):
        """
        Get or update psychologist's certifications
        GET /api/psychologists/profile/certifications/
        PATCH /api/psychologists/profile/certifications/
        """
        try:
            psychologist = self.get_current_psychologist()

            if request.method == 'GET':
                return Response({
                    'certifications': psychologist.certifications or []
                }, status=status.HTTP_200_OK)

            elif request.method == 'PATCH':
                serializer = self.get_serializer(data=request.data)

                if serializer.is_valid():
                    try:
                        # Update certifications using serializer
                        updated_psychologist = serializer.update(psychologist, serializer.validated_data)

                        logger.info(f"Certifications updated for psychologist: {request.user.email}")
                        return Response({
                            'message': _('Certifications updated successfully'),
                            'certifications': updated_psychologist.certifications
                        }, status=status.HTTP_200_OK)

                    except PsychologistProfileError as e:
                        return Response({
                            'error': str(e)
                        }, status=status.HTTP_400_BAD_REQUEST)

                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except PsychologistProfileError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error managing certifications for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to manage certifications')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PsychologistAvailabilityViewSet(GenericViewSet):
    """
    ViewSet for psychologist availability management
    """
    queryset = PsychologistAvailability.objects.select_related('psychologist__user').all()
    serializer_class = PsychologistAvailabilitySerializer
    permission_classes = [permissions.IsAuthenticated, PsychologistAvailabilityPermissions]

    def get_queryset(self):
        """Filter queryset based on user permissions"""
        queryset = super().get_queryset()

        # Admins can see all availability
        if self.request.user.is_admin or self.request.user.is_staff:
            return queryset

        # Psychologists can only see their own availability
        elif self.request.user.is_psychologist:
            try:
                psychologist = PsychologistService.get_psychologist_by_user(self.request.user)
                if psychologist:
                    return queryset.filter(psychologist=psychologist)
            except Exception:
                pass
            return queryset.none()

        # Default: no access
        return queryset.none()

    def get_current_psychologist(self):
        """Get current user's psychologist profile"""
        try:
            return PsychologistService.get_psychologist_by_user_or_raise(self.request.user)
        except PsychologistNotFoundError as e:
            raise AvailabilityManagementError(_("Psychologist profile not found."))

    @extend_schema(
        responses={
            200: PsychologistAvailabilitySerializer(many=True),
            404: {'description': 'Psychologist profile not found'}
        },
        description="Get current psychologist's availability blocks",
        tags=['Psychologist Availability']
    )
    @action(detail=False, methods=['get'])
    def my_availability(self, request):
        """
        Get current psychologist's availability blocks
        GET /api/psychologists/availability/my-availability/
        """
        try:
            psychologist = self.get_current_psychologist()

            # Get recurring availability
            recurring_blocks = PsychologistAvailability.get_psychologist_recurring_availability(psychologist)

            # Get specific date availability for next 30 days
            date_from = date.today()
            date_to = date_from + timedelta(days=30)
            specific_blocks = PsychologistAvailability.get_psychologist_specific_availability(
                psychologist, date_from, date_to
            )

            recurring_serializer = self.get_serializer(recurring_blocks, many=True)
            specific_serializer = self.get_serializer(specific_blocks, many=True)

            logger.info(f"Retrieved availability for psychologist: {request.user.email}")
            return Response({
                'recurring_availability': recurring_serializer.data,
                'specific_availability': specific_serializer.data,
                'total_blocks': len(recurring_blocks) + len(specific_blocks)
            }, status=status.HTTP_200_OK)

        except AvailabilityManagementError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error retrieving availability for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to retrieve availability')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=PsychologistAvailabilitySerializer,
        responses={
            201: {
                'description': 'Availability block created successfully',
                'example': {
                    'message': 'Availability block created successfully',
                    'availability': {'availability_id': 1, 'day_name': 'Monday', 'time_range_display': '09:00 - 12:00'}
                }
            },
            400: {'description': 'Invalid availability data'}
        },
        description="Create new availability block",
        tags=['Psychologist Availability']
    )
    def create(self, request):
        """
        Create availability block
        POST /api/psychologists/availability/
        """
        try:
            psychologist = self.get_current_psychologist()

            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                try:
                    # Create availability using service
                    availability = PsychologistService.create_availability_block(
                        psychologist, serializer.validated_data
                    )

                    # Return created availability data
                    result_serializer = self.get_serializer(availability)

                    logger.info(f"Availability block created by: {request.user.email}")
                    return Response({
                        'message': _('Availability block created successfully'),
                        'availability': result_serializer.data
                    }, status=status.HTTP_201_CREATED)

                except AvailabilityManagementError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except AvailabilityManagementError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error creating availability for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to create availability')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: PsychologistAvailabilitySerializer,
            404: {'description': 'Availability block not found'}
        },
        description="Get specific availability block",
        tags=['Psychologist Availability']
    )
    def retrieve(self, request, pk=None):
        """
        Get specific availability block
        GET /api/psychologists/availability/{id}/
        """
        try:
            availability = self.get_object()
            serializer = self.get_serializer(availability)

            logger.info(f"Availability block accessed: {pk} by {request.user.email}")
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error retrieving availability block {pk}: {str(e)}")
            return Response({
                'error': _('Availability block not found')
            }, status=status.HTTP_404_NOT_FOUND)

    @extend_schema(
        request=PsychologistAvailabilitySerializer,
        responses={
            200: {
                'description': 'Availability block updated successfully',
                'example': {
                    'message': 'Availability block updated successfully',
                    'availability': {'availability_id': 1, 'day_name': 'Monday', 'time_range_display': '09:00 - 12:00'}
                }
            },
            400: {'description': 'Invalid availability data'},
            404: {'description': 'Availability block not found'}
        },
        description="Update availability block",
        tags=['Psychologist Availability']
    )
    def partial_update(self, request, pk=None):
        """
        Update availability block
        PATCH /api/psychologists/availability/{id}/
        """
        try:
            availability = self.get_object()

            serializer = self.get_serializer(availability, data=request.data, partial=True)

            if serializer.is_valid():
                try:
                    # Update availability using service
                    updated_availability = PsychologistService.update_availability_block(
                        availability, serializer.validated_data
                    )

                    # Return updated availability data
                    result_serializer = self.get_serializer(updated_availability)

                    logger.info(f"Availability block updated: {pk} by {request.user.email}")
                    return Response({
                        'message': _('Availability block updated successfully'),
                        'availability': result_serializer.data
                    }, status=status.HTTP_200_OK)

                except AvailabilityManagementError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Error updating availability block {pk}: {str(e)}")
            return Response({
                'error': _('Failed to update availability block')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            204: {'description': 'Availability block deleted successfully'},
            404: {'description': 'Availability block not found'}
        },
        description="Delete availability block",
        tags=['Psychologist Availability']
    )
    def destroy(self, request, pk=None):
        """
        Delete availability block with proper validation
        DELETE /api/psychologists/availability/{id}/
        """
        try:
            availability = self.get_object()

            # Check deletion impact first
            impact = PsychologistService.check_availability_deletion_impact(availability)

            if not impact['can_delete']:
                return Response({
                    'error': _('Cannot delete availability block'),
                    'reason': f"{impact['booked_slots']} slots have active bookings",
                    'impact': impact,
                    'suggestion': _('Cancel or complete the associated appointments first')
                }, status=status.HTTP_400_BAD_REQUEST)

             # Perform safe deletion
            result = PsychologistService.delete_availability_block_safe(availability)
            print(f"DEBUG VIEW: Service returned result = {result}")

            logger.info(f"Availability block deleted: {pk} by {request.user.email}")

            response_data = {
                'message': _('Availability block deleted successfully'),
                'deleted_slots': result['deleted_slots'],  # ⭐ Check this value
                'impact': result['impact']
            }
            print(f"DEBUG VIEW: About to return response_data = {response_data}")

            return Response(response_data, status=status.HTTP_200_OK)

        except AvailabilityManagementError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error deleting availability block {pk}: {str(e)}")
            return Response({
                'error': _('Failed to delete availability block')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    @extend_schema(
        responses={
            200: {
                'description': 'Weekly availability summary',
                'example': {
                    'psychologist_name': 'Dr. John Doe',
                    'total_weekly_hours': 40,
                    'total_weekly_slots': 40,
                    'weekly_availability': {'monday': {'blocks_count': 2, 'total_hours': 8}}
                }
            }
        },
        description="Get weekly availability summary",
        tags=['Psychologist Availability']
    )
    @action(detail=False, methods=['get'])
    def weekly_summary(self, request):
        """
        Get weekly availability summary
        GET /api/psychologists/availability/weekly-summary/
        """
        try:
            psychologist = self.get_current_psychologist()

            weekly_summary = PsychologistAvailabilityService.get_weekly_availability_summary(psychologist)

            return Response(weekly_summary, status=status.HTTP_200_OK)

        except AvailabilityManagementError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error getting weekly summary for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to get weekly summary')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request={
            'type': 'object',
            'properties': {
                'weekly_schedule': {
                    'type': 'object',
                    'example': {
                        'monday': [{'start_time': '09:00', 'end_time': '12:00'}],
                        'tuesday': [{'start_time': '14:00', 'end_time': '17:00'}]
                    }
                }
            }
        },
        responses={
            200: {
                'description': 'Bulk availability created',
                'example': {
                    'success': 5,
                    'errors': 0,
                    'created_blocks': [{'availability_id': 1, 'day_name': 'Monday'}]
                }
            },
            400: {'description': 'Invalid schedule data'}
        },
        description="Create multiple availability blocks for weekly schedule",
        tags=['Psychologist Availability']
    )
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """
        Create multiple availability blocks for weekly schedule
        POST /api/psychologists/availability/bulk-create/
        """
        try:
            psychologist = self.get_current_psychologist()

            weekly_schedule = request.data.get('weekly_schedule', {})
            if not weekly_schedule:
                return Response({
                    'error': _('Weekly schedule is required')
                }, status=status.HTTP_400_BAD_REQUEST)

            # Create bulk availability using service
            result = PsychologistAvailabilityService.bulk_create_weekly_availability(
                psychologist, weekly_schedule
            )

            logger.info(f"Bulk availability created by {request.user.email}: {result['success']} blocks")
            return Response({
                'message': _('Bulk availability creation completed'),
                **result
            }, status=status.HTTP_200_OK)

        except AvailabilityManagementError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error creating bulk availability for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to create bulk availability')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='date_from',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='Start date for availability slots (default: today)'
            ),
            OpenApiParameter(
                name='date_to',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='End date for availability slots (default: +30 days)'
            )
        ],
        responses={
            200: {
                'description': 'Available appointment slots',
                'example': {
                    'psychologist_name': 'Dr. John Doe',
                    'date_range': {'from': '2024-01-01', 'to': '2024-01-31'},
                    'appointment_slots': [
                        {'date': '2024-01-01', 'start_time': '09:00', 'is_available': True}
                    ]
                }
            }
        },
        description="Get available appointment slots for booking",
        tags=['Psychologist Availability']
    )
    @action(detail=False, methods=['get'])
    def appointment_slots(self, request):
        """
        Get available appointment slots for booking
        GET /api/psychologists/availability/appointment-slots/
        """
        try:
            psychologist = self.get_current_psychologist()

            # Parse date parameters
            date_from_str = request.query_params.get('date_from')
            date_to_str = request.query_params.get('date_to')

            date_from = date.today()
            date_to = date_from + timedelta(days=30)

            if date_from_str:
                try:
                    date_from = date.fromisoformat(date_from_str)
                except ValueError:
                    return Response({
                        'error': _('Invalid date_from format. Use YYYY-MM-DD')
                    }, status=status.HTTP_400_BAD_REQUEST)

            if date_to_str:
                try:
                    date_to = date.fromisoformat(date_to_str)
                except ValueError:
                    return Response({
                        'error': _('Invalid date_to format. Use YYYY-MM-DD')
                    }, status=status.HTTP_400_BAD_REQUEST)

            # Get availability with appointment slots
            availability_data = PsychologistService.get_psychologist_availability(
                psychologist, date_from, date_to
            )

            return Response(availability_data, status=status.HTTP_200_OK)

        except AvailabilityManagementError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error getting appointment slots for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to get appointment slots')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    @extend_schema(
        responses={
            200: {
                'description': 'Deletion impact analysis',
                'example': {
                    'can_delete': False,
                    'total_slots': 45,
                    'booked_slots': 3,
                    'unbooked_slots': 42,
                    'booked_appointments': 3,
                    'warning': 'This availability block has 3 booked appointments'
                }
            }
        },
        description="Check what would happen if this availability block is deleted",
        tags=['Psychologist Availability']
    )
    @action(detail=True, methods=['get'])
    def deletion_impact(self, request, pk=None):
        """
        Check deletion impact for availability block
        GET /api/psychologists/availability/{id}/deletion-impact/
        """
        try:
            availability = self.get_object()
            impact = PsychologistService.check_availability_deletion_impact(availability)

            return Response({
                **impact,
                'warning': f"This availability block has {impact['booked_slots']} booked appointments" if impact['booked_slots'] > 0 else None
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error checking deletion impact for {pk}: {str(e)}")
            return Response({
                'error': _('Failed to check deletion impact')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PsychologistMarketplaceViewSet(GenericViewSet, ListModelMixin, RetrieveModelMixin):
    """
    ViewSet for public marketplace where parents browse psychologists
    """
    queryset = Psychologist.get_marketplace_psychologists()
    serializer_class = PsychologistMarketplaceSerializer
    permission_classes = [permissions.IsAuthenticated, PsychologistMarketplacePermissions]

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'retrieve':
            return PsychologistDetailSerializer
        elif self.action == 'search':
            return PsychologistSearchSerializer
        return PsychologistMarketplaceSerializer

    @extend_schema(
        description="List marketplace psychologists (approved and visible)",
        responses={200: PsychologistMarketplaceSerializer(many=True)},
        tags=['Psychologist Marketplace']
    )
    def list(self, request, *args, **kwargs):
        """List marketplace psychologists"""
        return super().list(request, *args, **kwargs)

    @extend_schema(
        description="Get detailed psychologist profile for marketplace",
        responses={200: PsychologistDetailSerializer},
        tags=['Psychologist Marketplace']
    )
    def retrieve(self, request, *args, **kwargs):
        """Get detailed psychologist profile"""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        request=PsychologistSearchSerializer,
        responses={
            200: PsychologistMarketplaceSerializer(many=True),
            400: {'description': 'Invalid search parameters'}
        },
        description="Search psychologists in marketplace",
        tags=['Psychologist Marketplace']
    )
    @action(detail=False, methods=['post'])
    def search(self, request):
        """
        Search psychologists in marketplace
        POST /api/psychologists/marketplace/search/
        """
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            try:
                # Perform search using service
                psychologists = PsychologistService.search_psychologists(
                    serializer.validated_data, request.user
                )

                # Serialize results
                result_serializer = PsychologistMarketplaceSerializer(psychologists, many=True)

                logger.info(f"Marketplace search performed by {request.user.email}: {len(psychologists)} results")
                return Response({
                    'count': len(psychologists),
                    'results': result_serializer.data
                }, status=status.HTTP_200_OK)

            except Exception as e:
                logger.error(f"Error in marketplace search by {request.user.email}: {str(e)}")
                return Response({
                    'error': _('Search failed')
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='services',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by services: online, consultation, or both'
            ),
            OpenApiParameter(
                name='min_experience',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Minimum years of experience'
            ),
            OpenApiParameter(
                name='location',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Location keywords for office address'
            )
        ],
        responses={
            200: PsychologistMarketplaceSerializer(many=True),
        },
        description="Filter psychologists by query parameters",
        tags=['Psychologist Marketplace']
    )
    @action(detail=False, methods=['get'])
    def filter(self, request):
        """
        Filter psychologists by query parameters
        GET /api/psychologists/marketplace/filter/
        """
        try:
            # Build filter parameters from query params
            filters = {}

            services = request.query_params.get('services')
            if services:
                if services == 'online':
                    filters['offers_online_sessions'] = True
                elif services == 'consultation':
                    filters['offers_initial_consultation'] = True

            min_experience = request.query_params.get('min_experience')
            if min_experience:
                try:
                    filters['min_years_experience'] = int(min_experience)
                except ValueError:
                    return Response({
                        'error': _('Invalid min_experience value')
                    }, status=status.HTTP_400_BAD_REQUEST)

            location = request.query_params.get('location')
            if location:
                filters['location_keywords'] = location

            # Get filtered psychologists
            psychologists = PsychologistService.get_marketplace_psychologists(filters)

            # Serialize results
            serializer = self.get_serializer(psychologists, many=True)

            return Response({
                'count': len(psychologists),
                'filters_applied': filters,
                'results': serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error filtering marketplace psychologists: {str(e)}")
            return Response({
                'error': _('Filter failed')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='psychologist_id',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description='Psychologist user ID'
            ),
            OpenApiParameter(
                name='date_from',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='Start date for availability (default: today)'
            ),
            OpenApiParameter(
                name='date_to',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='End date for availability (default: +30 days)'
            )
        ],
        responses={
            200: {
                'description': 'Psychologist availability for booking',
                'example': {
                    'psychologist_name': 'Dr. John Doe',
                    'appointment_slots': [
                        {'date': '2024-01-01', 'start_time': '09:00', 'is_available': True}
                    ]
                }
            },
            404: {'description': 'Psychologist not found'}
        },
        description="Get psychologist availability for appointment booking",
        tags=['Psychologist Marketplace']
    )
    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        """
        Get psychologist availability for appointment booking
        GET /api/psychologists/marketplace/{id}/availability/
        """
        try:
            psychologist = self.get_object()

            # Parse date parameters
            date_from_str = request.query_params.get('date_from')
            date_to_str = request.query_params.get('date_to')

            date_from = date.today()
            date_to = date_from + timedelta(days=30)

            if date_from_str:
                try:
                    date_from = date.fromisoformat(date_from_str)
                except ValueError:
                    return Response({
                        'error': _('Invalid date_from format. Use YYYY-MM-DD')
                    }, status=status.HTTP_400_BAD_REQUEST)

            if date_to_str:
                try:
                    date_to = date.fromisoformat(date_to_str)
                except ValueError:
                    return Response({
                        'error': _('Invalid date_to format. Use YYYY-MM-DD')
                    }, status=status.HTTP_400_BAD_REQUEST)

            # Get availability data
            availability_data = PsychologistService.get_psychologist_availability(
                psychologist, date_from, date_to
            )

            return Response(availability_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting psychologist availability {pk}: {str(e)}")
            return Response({
                'error': _('Failed to get availability')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PsychologistManagementViewSet(GenericViewSet, ListModelMixin, RetrieveModelMixin):
    """
    ViewSet for psychologist management (Admin access)
    """
    queryset = Psychologist.objects.select_related('user').all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'retrieve':
            return PsychologistDetailSerializer
        elif self.action == 'search':
            return PsychologistSearchSerializer
        return PsychologistSummarySerializer

    def get_permissions(self):
        """Set permissions based on action"""
        # Only admins can access management endpoints
        permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
        return [permission() for permission in permission_classes]

    @extend_schema(
        description="List all psychologists (Admin only)",
        responses={200: PsychologistSummarySerializer(many=True)},
        tags=['Psychologist Management']
    )
    def list(self, request, *args, **kwargs):
        """List all psychologists"""
        return super().list(request, *args, **kwargs)

    @extend_schema(
        description="Get detailed psychologist profile (Admin only)",
        responses={200: PsychologistDetailSerializer},
        tags=['Psychologist Management']
    )
    def retrieve(self, request, *args, **kwargs):
        """Get detailed psychologist profile"""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        request=PsychologistSearchSerializer,
        responses={
            200: PsychologistSummarySerializer(many=True),
            400: {'description': 'Invalid search parameters'}
        },
        description="Search all psychologists (Admin only)",
        tags=['Psychologist Management']
    )
    @action(detail=False, methods=['post'])
    def search(self, request):
        """
        Search all psychologists
        POST /api/psychologists/manage/search/
        """
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            try:
                # Perform search using service
                psychologists = PsychologistService.search_psychologists(
                    serializer.validated_data, request.user
                )

                # Serialize results
                result_serializer = PsychologistSummarySerializer(psychologists, many=True)

                logger.info(f"Admin psychologist search performed by {request.user.email}: {len(psychologists)} results")
                return Response({
                    'count': len(psychologists),
                    'results': result_serializer.data
                }, status=status.HTTP_200_OK)

            except Exception as e:
                logger.error(f"Error in admin psychologist search by {request.user.email}: {str(e)}")
                return Response({
                    'error': _('Search failed')
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        responses={
            200: {
                'description': 'Platform-wide psychologist statistics',
                'example': {
                    'total_psychologists': 50,
                    'by_verification_status': {'Approved': 35, 'Pending': 10, 'Rejected': 5},
                    'by_services': {'online_only': 20, 'consultation_only': 5, 'both': 25}
                }
            }
        },
        description="Get platform-wide psychologist statistics (Admin only)",
        tags=['Psychologist Management']
    )
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Get platform-wide psychologist statistics
        GET /api/psychologists/manage/statistics/
        """
        try:
            queryset = Psychologist.objects.all()

            # Basic counts
            total_psychologists = queryset.count()

            # Verification status distribution
            verification_stats = {}
            for status_code, status_label in Psychologist.VERIFICATION_STATUS_CHOICES:
                verification_stats[status_code] = queryset.filter(verification_status=status_code).count()

            # Service offerings
            online_only = queryset.filter(offers_online_sessions=True, offers_initial_consultation=False).count()
            consultation_only = queryset.filter(offers_online_sessions=False, offers_initial_consultation=True).count()
            both_services = queryset.filter(offers_online_sessions=True, offers_initial_consultation=True).count()

            # License validity
            valid_licenses = queryset.filter(license_expiry_date__gte=date.today()).count()
            expired_licenses = queryset.filter(license_expiry_date__lt=date.today()).count()

            # Marketplace visibility
            marketplace_visible = queryset.filter(
                verification_status='Approved',
                user__is_active=True,
                user__is_verified=True,
                license_expiry_date__gte=date.today()
            ).count()

            statistics = {
                'total_psychologists': total_psychologists,
                'verification_status': verification_stats,
                'service_offerings': {
                    'online_only': online_only,
                    'consultation_only': consultation_only,
                    'both_services': both_services
                },
                'license_status': {
                    'valid_licenses': valid_licenses,
                    'expired_licenses': expired_licenses
                },
                'marketplace_visible': marketplace_visible,
                'user_status': {
                    'active_users': queryset.filter(user__is_active=True).count(),
                    'verified_emails': queryset.filter(user__is_verified=True).count()
                }
            }

            logger.info(f"Psychologist statistics accessed by admin {request.user.email}")
            return Response(statistics, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error generating psychologist statistics for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to generate statistics')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)