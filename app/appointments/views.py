# appointments/views.py
from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes
import logging
from django.http import Http404
from rest_framework.exceptions import PermissionDenied
from datetime import date, timedelta
from django.utils import timezone
from django.db.models import Q
from django.db import models
from psychologists.models import PsychologistAvailability
from .models import Appointment, AppointmentSlot
from .serializers import (
    AppointmentSerializer,
    AppointmentCreateSerializer,
    AppointmentUpdateSerializer,
    AppointmentDetailSerializer,
    AppointmentSummarySerializer,
    QRVerificationSerializer,
    AppointmentSearchSerializer,
    AppointmentCancellationSerializer,
    BookingAvailabilitySerializer,
    AvailableSlotDisplaySerializer,
    AppointmentSlotCreateSerializer,
    AppointmentSlotSerializer,
    NoShowSerializer,
    StartOnlineSessionSerializer
)
from .services import (
    AppointmentBookingService,
    AppointmentManagementService,
    AppointmentServiceError,
    AppointmentBookingError,
    AppointmentNotFoundError,
    AppointmentAccessDeniedError,
    AppointmentCancellationError,
    QRVerificationError,
    SlotNotAvailableError,
    InsufficientConsecutiveSlotsError,
    AppointmentSlotService,
    SlotGenerationError

)
from .permissions import (
    IsAppointmentParticipant,
    CanBookAppointments,
    CanManageAppointments,
    CanCancelAppointment,
    CanVerifyQRCode,
    IsMarketplaceUser,
    AppointmentViewPermissions,
    IsPsychologistAppointmentProvider,
    IsParentAppointmentBooker,
    CanCompleteAppointment,
    AppointmentSlotPermissions,
    CanManageSlots
)
from psychologists.models import Psychologist
from parents.services import ParentService, ParentNotFoundError
from children.models import Child

logger = logging.getLogger(__name__)


class AppointmentViewSet(GenericViewSet, ListModelMixin, RetrieveModelMixin):
    """
    ViewSet for appointment management
    Handles booking, viewing, updating, and cancelling appointments
    """
    queryset = Appointment.objects.select_related(
        'child', 'psychologist__user', 'parent__user'
    ).prefetch_related('appointment_slots').all()
    permission_classes = [permissions.IsAuthenticated]
    def get_object(self):
        """
        Override to use service layer for access control
        """
        appointment_id = self.kwargs.get('pk')

        try:
            # Use service to get appointment with access control
            appointment = AppointmentManagementService.get_appointment_by_id(
                appointment_id, self.request.user
            )

            # Still check DRF permissions
            self.check_object_permissions(self.request, appointment)

            return appointment

        except AppointmentNotFoundError:
            from django.http import Http404
            raise Http404(_("Appointment not found"))
        except AppointmentAccessDeniedError:
            raise PermissionDenied(_("You don't have permission to access this appointment"))
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return AppointmentCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return AppointmentUpdateSerializer
        elif self.action in ['retrieve', 'my_appointment_detail']:
            return AppointmentDetailSerializer
        elif self.action == 'verify_qr':
            return QRVerificationSerializer
        elif self.action == 'mark_no_show':  # NEW
            return NoShowSerializer
        elif self.action == 'start_online_session':  # NEW
            return StartOnlineSessionSerializer
        elif self.action == 'search':
            return AppointmentSearchSerializer
        elif self.action == 'cancel':
            return AppointmentCancellationSerializer
        elif self.action in ['list', 'my_appointments']:
            return AppointmentSummarySerializer
        elif self.action == 'available_slots':
            return BookingAvailabilitySerializer
        return AppointmentSerializer

    def get_permissions(self):
        """Set permissions based on action"""
        if self.action == 'create':
            permission_classes = [permissions.IsAuthenticated, CanBookAppointments]
        elif self.action in ['update', 'partial_update']:
            permission_classes = [permissions.IsAuthenticated, CanManageAppointments]
        elif self.action == 'cancel':
            permission_classes = [permissions.IsAuthenticated, CanCancelAppointment]
        elif self.action == 'verify_qr':
            permission_classes = [permissions.IsAuthenticated, CanVerifyQRCode]
        elif self.action == 'complete':
            permission_classes = [permissions.IsAuthenticated, CanCompleteAppointment]
        elif self.action in ['available_slots', 'recommended_times']:
            permission_classes = [permissions.IsAuthenticated, IsMarketplaceUser]
        elif self.action in ['list', 'retrieve', 'my_appointments']:
            permission_classes = [permissions.IsAuthenticated, IsAppointmentParticipant]
        elif self.action in ['mark_no_show', 'start_online_session']:
            permission_classes = [permissions.IsAuthenticated, IsPsychologistAppointmentProvider]

        else:
            permission_classes = [permissions.IsAuthenticated, AppointmentViewPermissions]

        return [permission() for permission in permission_classes]

    def get_queryset(self):
        """Filter queryset based on user permissions"""
        queryset = super().get_queryset()

        # Admins can see all appointments
        if self.request.user.is_admin or self.request.user.is_staff:
            return queryset

        # Parents can only see their own appointments
        elif self.request.user.is_parent:
            try:
                parent = ParentService.get_parent_by_user(self.request.user)
                if parent:
                    return queryset.filter(parent=parent)
            except ParentNotFoundError:
                pass
            return queryset.none()

        # Psychologists can see their appointments
        elif self.request.user.is_psychologist:
            try:
                if hasattr(self.request.user, 'psychologist_profile'):
                    return queryset.filter(psychologist=self.request.user.psychologist_profile)
            except Exception:
                pass
            return queryset.none()

        # Default: no access
        return queryset.none()

    def get_current_parent(self):
        """Get current user's parent profile"""
        try:
            return ParentService.get_parent_by_user_or_raise(self.request.user)
        except ParentNotFoundError as e:
            raise AppointmentBookingError(_("Parent profile not found. Please ensure you have a parent account."))

    @extend_schema(
        responses={
            200: AppointmentSummarySerializer(many=True),
            403: {'description': 'Permission denied'}
        },
        description="List appointments with permission filtering",
        tags=['Appointments']
    )
    def list(self, request, *args, **kwargs):
        """List appointments with permission filtering"""
        return super().list(request, *args, **kwargs)

    @extend_schema(
        responses={
            200: AppointmentDetailSerializer,
            404: {'description': 'Appointment not found'}
        },
        description="Get detailed appointment information",
        tags=['Appointments']
    )
    def retrieve(self, request, *args, **kwargs):
        """Get detailed appointment information"""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        request=AppointmentCreateSerializer,
        responses={
            201: {
                'description': 'Appointment booked successfully',
                'example': {
                    'message': 'Appointment booked successfully',
                    'appointment': {
                        'appointment_id': 'uuid',
                        'child_name': 'John Doe',
                        'psychologist_name': 'Dr. Jane Smith',
                        'session_type': 'OnlineMeeting',
                        'scheduled_start_time': '2024-01-15T10:00:00Z'
                    }
                }
            },
            400: {'description': 'Invalid booking data or slots not available'},
            403: {'description': 'Booking not allowed'}
        },
        description="Book a new appointment",
        tags=['Appointments']
    )
    def create(self, request):
        """
        Book a new appointment
        POST /api/appointments/
        """
        try:
            parent = self.get_current_parent()
            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                try:
                    # Extract validated data
                    validated_data = serializer.validated_data
                    child = validated_data['child']
                    psychologist = validated_data['psychologist']
                    session_type = validated_data['session_type']
                    start_slot_id = validated_data['start_slot_id']  # Use direct field name
                    parent_notes = validated_data.get('parent_notes', '')

                    # Book appointment using service (this is what your mock is targeting)
                    appointment = AppointmentBookingService.book_appointment(
                        parent=parent,
                        child=child,
                        psychologist=psychologist,
                        session_type=session_type,
                        start_slot_id=start_slot_id,
                        parent_notes=parent_notes
                    )

                    # Return created appointment data
                    result_serializer = AppointmentDetailSerializer(appointment)

                    logger.info(f"Appointment booked: {appointment.appointment_id} by {request.user.email}")
                    return Response({
                        'message': _('Appointment booked successfully'),
                        'appointment': result_serializer.data
                    }, status=status.HTTP_201_CREATED)

                except (SlotNotAvailableError, InsufficientConsecutiveSlotsError, AppointmentBookingError) as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Unexpected error booking appointment for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to book appointment')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: AppointmentSummarySerializer(many=True),
            404: {'description': 'User profile not found'}
        },
        description="Get current user's appointments",
        tags=['Appointments']
    )
    @action(detail=False, methods=['get'])
    def my_appointments(self, request):
        """
        Get current user's appointments
        GET /api/appointments/my-appointments/
        """
        try:
            # Get appointments using service with proper filtering
            appointments = AppointmentManagementService.get_user_appointments(
                user=request.user,
                status_filter=request.query_params.get('status'),
                is_upcoming=request.query_params.get('upcoming') == 'true' if 'upcoming' in request.query_params else None
            )

            serializer = self.get_serializer(appointments, many=True)

            logger.info(f"Retrieved {len(appointments)} appointments for user: {request.user.email}")
            return Response({
                'count': len(appointments),
                'appointments': serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error retrieving appointments for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to retrieve appointments')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=AppointmentUpdateSerializer,
        responses={
            200: {
                'description': 'Appointment updated successfully',
                'example': {
                    'message': 'Appointment updated successfully',
                    'appointment': {'appointment_id': 'uuid', 'parent_notes': 'Updated notes'}
                }
            },
            400: {'description': 'Invalid update data'},
            404: {'description': 'Appointment not found'},
            403: {'description': 'Permission denied'}
        },
        description="Update appointment details (notes)",
        tags=['Appointments']
    )
    def partial_update(self, request, pk=None):
        """
        Update appointment details
        PATCH /api/appointments/{id}/
        """
        try:
            appointment = self.get_object()

            # Additional business logic validation
            if appointment.appointment_status == 'Completed' and 'cancellation_reason' in request.data:
                return Response({
                    'error': _('Cannot modify cancellation reason for completed appointments')
                }, status=status.HTTP_400_BAD_REQUEST)

            serializer = self.get_serializer(appointment, data=request.data, partial=True)

            if serializer.is_valid():
                # Save the updates
                updated_appointment = serializer.save()

                # Return updated appointment data
                result_serializer = AppointmentDetailSerializer(updated_appointment)

                logger.info(f"Appointment updated: {appointment.appointment_id} by {request.user.email}")
                return Response({
                    'message': _('Appointment updated successfully'),
                    'appointment': result_serializer.data
                }, status=status.HTTP_200_OK)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except PermissionDenied:
            return Response({
                'error': _('Permission denied')
            }, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            logger.error(f"Error updating appointment {pk} for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to update appointment')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=AppointmentCancellationSerializer,
        responses={
            200: {
                'description': 'Appointment cancelled successfully',
                'example': {
                    'message': 'Appointment cancelled successfully',
                    'refund_info': {
                        'refund_amount': 150.00,
                        'refund_percentage': 100,
                        'refund_reason': 'Full refund - cancelled 24+ hours before'
                    }
                }
            },
            400: {'description': 'Cannot cancel appointment'},
            404: {'description': 'Appointment not found'},
            403: {'description': 'Permission denied'}
        },
        description="Cancel an appointment",
        tags=['Appointments']
    )
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancel an appointment
        POST /api/appointments/{id}/cancel/
        """
        try:
            # First, try to get the appointment using the service which handles access control
            try:
                appointment = AppointmentManagementService.get_appointment_by_id(pk, request.user)
            except AppointmentNotFoundError:
                return Response({
                    'error': _('Appointment not found')
                }, status=status.HTTP_404_NOT_FOUND)
            except AppointmentAccessDeniedError:
                return Response({
                    'error': _('Permission denied')
                }, status=status.HTTP_403_FORBIDDEN)

            # Check if user can cancel this appointment
            self.check_object_permissions(request, appointment)

            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                try:
                    reason = serializer.validated_data.get('cancellation_reason', '')

                    # Cancel appointment using service
                    cancelled_appointment = AppointmentManagementService.cancel_appointment(
                        appointment, request.user, reason
                    )

                    # Calculate refund information (placeholder)
                    refund_info = {
                        'message': _('Refund will be processed according to our cancellation policy'),
                        'processing_time': _('3-5 business days')
                    }

                    logger.info(f"Appointment cancelled: {appointment.appointment_id} by {request.user.email}")
                    return Response({
                        'message': _('Appointment cancelled successfully'),
                        'appointment_id': str(cancelled_appointment.appointment_id),
                        'refund_info': refund_info
                    }, status=status.HTTP_200_OK)

                except AppointmentCancellationError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except PermissionDenied:
            return Response({
                'error': _('Permission denied')
            }, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            logger.error(f"Error cancelling appointment {pk} for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to cancel appointment')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=QRVerificationSerializer,
        responses={
            200: {
                'description': 'QR code verified successfully',
                'example': {
                    'message': 'Session verified successfully',
                    'appointment': {
                        'appointment_id': 'uuid',
                        'session_verified_at': '2024-01-15T10:00:00Z',
                        'actual_start_time': '2024-01-15T10:00:00Z'
                    }
                }
            },
            400: {'description': 'Invalid QR code or verification not allowed'},
            404: {'description': 'QR code not found'}
        },
        description="Verify in-person appointment using QR code",
        tags=['Appointments']
    )
    @action(detail=False, methods=['post'])
    def verify_qr(self, request):
        """
        Verify in-person appointment using QR code
        POST /api/appointments/verify-qr/
        """
        try:
            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                try:
                    # The serializer stores the appointment in _appointment
                    if hasattr(serializer, '_appointment'):
                        # Verify using the appointment from serializer
                        verified_appointment = serializer._appointment
                        verified_appointment.verify_session()
                    else:
                        # Use the save method which handles verification
                        verified_appointment = serializer.save()

                    # Return verification result
                    result_serializer = AppointmentDetailSerializer(verified_appointment)

                    logger.info(f"QR code verified for appointment {verified_appointment.appointment_id} by {request.user.email}")
                    return Response({
                        'message': _('Session verified successfully'),
                        'appointment': result_serializer.data
                    }, status=status.HTTP_200_OK)

                except QRVerificationError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                # Format validation errors properly
                if 'qr_code' in serializer.errors:
                    # Extract the error message from the serializer
                    error_msg = serializer.errors['qr_code'][0]
                    return Response({
                        'error': str(error_msg)
                    }, status=status.HTTP_400_BAD_REQUEST)

                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Error verifying QR code for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to verify QR code')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=AppointmentSearchSerializer,
        responses={
            200: AppointmentSummarySerializer(many=True),
            400: {'description': 'Invalid search parameters'}
        },
        description="Search appointments with filters",
        tags=['Appointments']
    )
    @action(detail=False, methods=['post'])
    def search(self, request):
        """
        Search appointments with filters
        POST /api/appointments/search/
        """
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            try:
                search_params = serializer.validated_data

                # Get appointments using service with search parameters
                appointments = AppointmentManagementService.get_user_appointments(
                    user=request.user,
                    status_filter=search_params.get('appointment_status'),
                    date_from=search_params.get('date_from'),
                    date_to=search_params.get('date_to'),
                    is_upcoming=search_params.get('is_upcoming')
                )

                # Additional filtering by session type
                if search_params.get('session_type'):
                    appointments = [a for a in appointments if a.session_type == search_params['session_type']]

                # Additional filtering by child or psychologist (for parents/psychologists respectively)
                if search_params.get('child_id'):
                    appointments = [a for a in appointments if str(a.child.id) == str(search_params['child_id'])]

                if search_params.get('psychologist_id'):
                    appointments = [a for a in appointments if str(a.psychologist.user.id) == str(search_params['psychologist_id'])]

                # Serialize results
                result_serializer = AppointmentSummarySerializer(appointments, many=True)

                logger.info(f"Appointment search performed by {request.user.email}: {len(appointments)} results")
                return Response({
                    'count': len(appointments),
                    'search_params': search_params,
                    'results': result_serializer.data
                }, status=status.HTTP_200_OK)

            except Exception as e:
                logger.error(f"Error in appointment search by {request.user.email}: {str(e)}")
                return Response({
                    'error': _('Search failed')
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='psychologist_id',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Psychologist ID to get availability for'
            ),
            OpenApiParameter(
                name='session_type',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Session type: OnlineMeeting or InitialConsultation'
            ),
            OpenApiParameter(
                name='date_from',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='Start date for availability search (default: today)'
            ),
            OpenApiParameter(
                name='date_to',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='End date for availability search (default: +30 days)'
            )
        ],
        responses={
            200: {
                'description': 'Available booking slots',
                'example': {
                    'psychologist_name': 'Dr. Jane Smith',
                    'session_type': 'OnlineMeeting',
                    'total_slots': 25,
                    'available_slots': [
                        {
                            'slot_id': 123,
                            'date': '2024-01-15',
                            'start_time': '10:00',
                            'end_time': '11:00',
                            'session_types': ['OnlineMeeting']
                        }
                    ]
                }
            },
            400: {'description': 'Invalid parameters'},
            404: {'description': 'Psychologist not found'}
        },
        description="Get available appointment slots for booking",
        tags=['Appointments']
    )
    @action(detail=False, methods=['get'])
    def available_slots(self, request):
        """
        Get available appointment slots for booking
        GET /api/appointments/available-slots/?psychologist_id=uuid&session_type=OnlineMeeting
        """
        try:
            # Parse and validate query parameters
            psychologist_id = request.query_params.get('psychologist_id')
            session_type = request.query_params.get('session_type')
            date_from_str = request.query_params.get('date_from')
            date_to_str = request.query_params.get('date_to')

            if not psychologist_id:
                return Response({
                    'error': _('psychologist_id parameter is required')
                }, status=status.HTTP_400_BAD_REQUEST)

            if not session_type:
                return Response({
                    'error': _('session_type parameter is required')
                }, status=status.HTTP_400_BAD_REQUEST)

            if session_type not in ['OnlineMeeting', 'InitialConsultation']:
                return Response({
                    'error': _('Invalid session_type. Must be OnlineMeeting or InitialConsultation')
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get psychologist
            try:
                psychologist = Psychologist.objects.get(user__id=psychologist_id)
            except Psychologist.DoesNotExist:
                return Response({
                    'error': _('Psychologist not found')
                }, status=status.HTTP_404_NOT_FOUND)

            # Parse dates
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

            # Get available slots using service
            availability_data = AppointmentBookingService.get_available_booking_slots(
                psychologist, session_type, date_from, date_to
            )

            return Response(availability_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting available slots for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to get available slots')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: {
                'description': 'Appointment marked as completed',
                'example': {
                    'message': 'Appointment marked as completed',
                    'appointment': {
                        'appointment_id': 'uuid',
                        'appointment_status': 'Completed',
                        'actual_end_time': '2024-01-15T11:00:00Z'
                    }
                }
            },
            400: {'description': 'Cannot complete appointment'},
            403: {'description': 'Permission denied - only psychologists can complete appointments'},
            404: {'description': 'Appointment not found'}
        },
        description="Mark appointment as completed (psychologists only)",
        tags=['Appointments']
    )
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """
        Mark appointment as completed
        POST /api/appointments/{id}/complete/
        """
        try:
            appointment = self.get_object()

            # Check object-level permissions
            self.check_object_permissions(request, appointment)

            # Get psychologist notes from request data
            psychologist_notes = request.data.get('psychologist_notes', '')

            try:
                # Complete appointment using service
                completed_appointment = AppointmentManagementService.complete_appointment(
                    appointment, psychologist_notes
                )

                # Return updated appointment data
                result_serializer = AppointmentDetailSerializer(completed_appointment)

                logger.info(f"Appointment completed: {appointment.appointment_id} by {request.user.email}")
                return Response({
                    'message': _('Appointment marked as completed'),
                    'appointment': result_serializer.data
                }, status=status.HTTP_200_OK)

            except AppointmentServiceError as e:
                return Response({
                    'error': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)

        except PermissionDenied:
            return Response({
                'error': _('Only psychologists can mark appointments as completed')
            }, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            logger.error(f"Error completing appointment {pk} for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to complete appointment')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='status',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by appointment status'
            ),
            OpenApiParameter(
                name='upcoming',
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description='Filter for upcoming appointments only'
            )
        ],
        responses={
            200: {
                'description': 'Upcoming appointments',
                'example': {
                    'count': 3,
                    'next_appointment': {
                        'appointment_id': 'uuid',
                        'scheduled_start_time': '2024-01-15T10:00:00Z',
                        'child_name': 'John Doe'
                    },
                    'appointments': []
                }
            }
        },
        description="Get upcoming appointments with next appointment highlighted",
        tags=['Appointments']
    )
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """
        Get upcoming appointments
        GET /api/appointments/upcoming/
        """
        try:
            # Get upcoming appointments using service
            appointments = AppointmentManagementService.get_user_appointments(
                user=request.user,
                status_filter=request.query_params.get('status'),
                is_upcoming=True
            )

            # Find next appointment
            next_appointment = None
            if appointments:
                # Appointments are already ordered by scheduled_start_time
                next_appointment = appointments[0]

            serializer = AppointmentSummarySerializer(appointments, many=True)
            next_appointment_serializer = AppointmentSummarySerializer(next_appointment) if next_appointment else None

            return Response({
                'count': len(appointments),
                'next_appointment': next_appointment_serializer.data if next_appointment_serializer else None,
                'appointments': serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting upcoming appointments for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to get upcoming appointments')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: {
                'description': 'Past appointments',
                'example': {
                    'count': 10,
                    'appointments': []
                }
            }
        },
        description="Get past appointments",
        tags=['Appointments']
    )
    @action(detail=False, methods=['get'])
    def history(self, request):
        """
        Get past appointments
        GET /api/appointments/history/
        """
        try:
            # Get past appointments
            appointments = AppointmentManagementService.get_user_appointments(
                user=request.user,
                is_upcoming=False
            )

            serializer = AppointmentSummarySerializer(appointments, many=True)

            return Response({
                'count': len(appointments),
                'appointments': serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting appointment history for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to get appointment history')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    @extend_schema(
        request=NoShowSerializer,
        responses={
            200: {
                'description': 'Appointment marked as no-show successfully',
                'example': {
                    'message': 'Appointment marked as no-show successfully',
                    'appointment': {
                        'appointment_id': 'uuid',
                        'appointment_status': 'No_Show',
                        'actual_end_time': '2024-01-15T11:30:00Z'
                    }
                }
            },
            400: {'description': 'Cannot mark as no-show at this time'},
            403: {'description': 'Permission denied'},
            404: {'description': 'Appointment not found'}
        },
        description="Mark appointment as no-show (only available 30 minutes after scheduled end time)",
        tags=['Appointments']
    )
    @action(detail=True, methods=['post'])
    def mark_no_show(self, request, pk=None):
        """
        Mark appointment as no-show (psychologists only, 30 mins after scheduled end time)
        POST /api/appointments/{id}/mark-no-show/
        """
        try:
            try:
                appointment = self.get_object()
            except Http404:
                return Response({
                    'error': _('Appointment not found')
                }, status=status.HTTP_404_NOT_FOUND)

            # Validate and process no-show
            serializer = self.get_serializer(
                data=request.data,
                context={'request': request, 'appointment': appointment}
            )

            if serializer.is_valid():
                updated_appointment = serializer.save()

                # Return success response
                result_serializer = AppointmentDetailSerializer(updated_appointment)

                logger.info(f"Appointment {appointment.appointment_id} marked as no-show by {request.user.email}")
                return Response({
                    'message': _('Appointment marked as no-show successfully'),
                    'appointment': result_serializer.data
                }, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Appointment.DoesNotExist:
            return Response({
                'error': _('Appointment not found')
            }, status=status.HTTP_404_NOT_FOUND)
        except PermissionDenied:
            return Response({
                'error': _('Permission denied')
            }, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            logger.error(f"Error marking no-show for appointment {pk} by {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to mark appointment as no-show')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # NEW ACTION: Start online session
    @extend_schema(
        request=StartOnlineSessionSerializer,
        responses={
            200: {
                'description': 'Online session started successfully',
                'example': {
                    'message': 'Online session started successfully',
                    'appointment': {
                        'appointment_id': 'uuid',
                        'appointment_status': 'In_Progress',
                        'actual_start_time': '2024-01-15T10:00:00Z',
                        'meeting_link': 'https://zoom.us/j/123456789'
                    }
                }
            },
            400: {'description': 'Cannot start session at this time'},
            403: {'description': 'Permission denied'},
            404: {'description': 'Appointment not found'}
        },
        description="Start online session and set status to In_Progress",
        tags=['Appointments']
    )
    @action(detail=True, methods=['post'])
    def start_online_session(self, request, pk=None):
        """
        Start online session and set status to In_Progress (psychologists only)
        POST /api/appointments/{id}/start-online-session/
        """
        try:
            appointment = self.get_object()

            # Validate and process session start
            serializer = self.get_serializer(
                data=request.data,
                context={'request': request, 'appointment': appointment}
            )
            if serializer.is_valid():
                updated_appointment = serializer.save()
                # Return success response
                result_serializer = AppointmentDetailSerializer(updated_appointment)
                logger.info(f"Online session started for appointment {appointment.appointment_id} by {request.user.email}")
                return Response({
                    'message': _('Online session started successfully'),
                    'appointment': result_serializer.data
                }, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Appointment.DoesNotExist:
            return Response({
                'error': _('Appointment not found')
            }, status=status.HTTP_404_NOT_FOUND)
        except PermissionDenied:
            return Response({
                'error': _('Permission denied')
            }, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            logger.error(f"Error starting online session for appointment {pk} by {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to start online session')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class AppointmentSlotViewSet(GenericViewSet, ListModelMixin, RetrieveModelMixin):
    """
    ViewSet for appointment slot management and generation
    - Psychologists: Create and manage their slots
    - Parents: View available slots for booking
    - Admins: Full access to all slots
    """
    queryset = AppointmentSlot.objects.select_related('psychologist__user', 'availability_block').all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return AppointmentSlotCreateSerializer
        elif self.action in ['available_for_booking', 'booking_availability']:
            return AvailableSlotDisplaySerializer
        return AppointmentSlotSerializer

    def get_permissions(self):
        """Set permissions based on action"""
        if self.action in ['create', 'update', 'destroy', 'generate_slots']:
            # Only psychologists and admins can manage slots
            permission_classes = [permissions.IsAuthenticated, CanManageSlots]
        elif self.action in ['available_for_booking', 'booking_availability']:
            # Marketplace users can view booking availability
            permission_classes = [permissions.IsAuthenticated, IsMarketplaceUser]
        elif self.action in ['list', 'my_slots']:
            # Basic auth for list actions (filtering in get_queryset)
            permission_classes = [permissions.IsAuthenticated]
        elif self.action == 'retrieve':
            # Use slot-specific permissions for individual access
            permission_classes = [permissions.IsAuthenticated, AppointmentSlotPermissions]
        else:
            permission_classes = [permissions.IsAuthenticated]

        return [permission() for permission in permission_classes]

    def get_queryset(self):
        """Filter queryset based on user permissions and action"""
        queryset = super().get_queryset()


        # For list actions, apply filtering to show appropriate slots
        if self.action == 'list':
            print("Branch: list action")
            # Admins can see all slots
            if self.request.user.is_admin or self.request.user.is_staff:
                print("Returning admin view")
                return queryset

            # Psychologists can see their own slots
            elif self.request.user.user_type == 'Psychologist':
                print("Branch: list - psychologist filtering")
                try:
                    psychologist = PsychologistService.get_psychologist_by_user(self.request.user)
                    if psychologist:
                        filtered = queryset.filter(psychologist=psychologist)
                        print(f"Filtered queryset count: {filtered.count()}")
                        return filtered
                except Exception as e:
                    print(f"Exception getting psychologist: {e}")
                    pass
                print("Returning empty queryset for psychologist")
                return queryset.none()

            # Parents can see available slots from marketplace-visible psychologists
            elif self.request.user.user_type == 'Parent':
                print("Branch: list - parent filtering")
                filtered = queryset.filter(
                    is_booked=False,
                    slot_date__gte=date.today(),
                    psychologist__verification_status='Approved',
                    psychologist__user__is_active=True,
                    psychologist__user__is_verified=True,
                ).filter(
                    models.Q(psychologist__offers_initial_consultation=True) |
                    models.Q(psychologist__offers_online_sessions=True)
                )
                print(f"Parent filtered queryset count: {filtered.count()}")
                return filtered

            # Default for list: no access
            print("Branch: list - default no access")
            return queryset.none()

        # For marketplace/booking actions, apply parent filtering
        elif self.action in ['available_for_booking', 'booking_availability']:
            print("Branch: marketplace/booking actions")
            filtered = queryset.filter(
                is_booked=False,
                slot_date__gte=date.today(),
                psychologist__verification_status='Approved',
                psychologist__user__is_active=True,
                psychologist__user__is_verified=True,
            ).filter(
                models.Q(psychologist__offers_initial_consultation=True) |
                models.Q(psychologist__offers_online_sessions=True)
            )
            print(f"Marketplace filtered queryset count: {filtered.count()}")
            return filtered

        # For psychologist-specific actions
        elif self.action == 'my_slots':
            print("Branch: my_slots action")
            if self.request.user.user_type == 'Psychologist':
                try:
                    psychologist = PsychologistService.get_psychologist_by_user(self.request.user)
                    if psychologist:
                        filtered = queryset.filter(psychologist=psychologist)
                        print(f"My slots filtered queryset count: {filtered.count()}")
                        return filtered
                except Exception as e:
                    print(f"Exception in my_slots: {e}")
                    pass
            print("Returning empty queryset for my_slots")
            return queryset.none()

        # For detail actions (retrieve, update, destroy), return ALL slots
        else:
            print(f"Branch: detail action ({self.action}) - returning full queryset")
            print(f"Full queryset count: {queryset.count()}")
            return queryset

    def get_current_psychologist(self):
        """Get current user's psychologist profile"""
        try:
            return PsychologistService.get_psychologist_by_user_or_raise(self.request.user)
        except PsychologistNotFoundError as e:
            raise SlotGenerationError(_("Psychologist profile not found."))

    @extend_schema(
        responses={
            200: AppointmentSlotSerializer(many=True),
            404: {'description': 'Psychologist profile not found'}
        },
        description="Get current psychologist's appointment slots",
        tags=['Appointment Slots']
    )
    @action(detail=False, methods=['get'])
    def my_slots(self, request):
        """
        Get current psychologist's appointment slots
        GET /api/appointments/slots/my-slots/
        """
        try:
            psychologist = self.get_current_psychologist()

            # Get slots with optional date filtering
            date_from = request.query_params.get('date_from')
            date_to = request.query_params.get('date_to')

            queryset = AppointmentSlot.objects.filter(psychologist=psychologist)

            if date_from:
                try:
                    date_from = date.fromisoformat(date_from)
                    queryset = queryset.filter(slot_date__gte=date_from)
                except ValueError:
                    return Response({
                        'error': _('Invalid date_from format. Use YYYY-MM-DD')
                    }, status=status.HTTP_400_BAD_REQUEST)

            if date_to:
                try:
                    date_to = date.fromisoformat(date_to)
                    queryset = queryset.filter(slot_date__lte=date_to)
                except ValueError:
                    return Response({
                        'error': _('Invalid date_to format. Use YYYY-MM-DD')
                    }, status=status.HTTP_400_BAD_REQUEST)

            # Order by date and time
            slots = queryset.order_by('slot_date', 'start_time')
            serializer = AppointmentSlotSerializer(slots, many=True)

            logger.info(f"Retrieved {len(slots)} slots for psychologist: {request.user.email}")
            return Response({
                'count': len(slots),
                'slots': serializer.data
            }, status=status.HTTP_200_OK)

        except SlotGenerationError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error retrieving slots for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to retrieve slots')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        request=AppointmentSlotCreateSerializer,
        responses={
            201: {
                'description': 'Appointment slot created successfully',
                'example': {
                    'message': 'Appointment slot created successfully',
                    'slot': {'slot_id': 1, 'slot_date': '2024-01-15', 'start_time': '09:00'}
                }
            },
            400: {'description': 'Invalid slot data'}
        },
        description="Create new appointment slot (Admin/System use)",
        tags=['Appointment Slots']
    )
    def create(self, request):
        """
        Create appointment slot (primarily for admin/system use)
        POST /api/appointments/slots/
        """
        try:
            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                try:
                    # Create slot
                    slot = serializer.save()

                    # Return created slot data
                    result_serializer = AppointmentSlotSerializer(slot)

                    logger.info(f"Appointment slot created by: {request.user.email}")
                    return Response({
                        'message': _('Appointment slot created successfully'),
                        'slot': result_serializer.data
                    }, status=status.HTTP_201_CREATED)

                except SlotGenerationError as e:
                    return Response({
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Error creating appointment slot for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to create appointment slot')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='date_from',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='Start date for slot generation (default: today)'
            ),
            OpenApiParameter(
                name='date_to',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='End date for slot generation (default: +90 days)'
            ),
            OpenApiParameter(
                name='availability_block_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Generate slots for specific availability block only'
            )
        ],
        responses={
            200: {
                'description': 'Slots generated successfully',
                'example': {
                    'message': 'Slots generated successfully',
                    'total_slots_created': 45,
                    'date_range': {'from': '2024-01-15', 'to': '2024-04-15'},
                    'results': [{'availability_block_id': 1, 'slots_created': 15, 'success': True}]
                }
            },
            400: {'description': 'Invalid parameters'}
        },
        description="Generate appointment slots from psychologist's availability blocks",
        tags=['Appointment Slots']
    )
    @action(detail=False, methods=['post'])
    def generate_slots(self, request):
        """
        Generate appointment slots from availability blocks
        POST /api/appointments/slots/generate-slots/
        """
        try:
            psychologist = self.get_current_psychologist()

            # Parse date parameters
            date_from_str = request.query_params.get('date_from')
            date_to_str = request.query_params.get('date_to')
            availability_block_id = request.query_params.get('availability_block_id')

            date_from = date.today()
            date_to = date_from + timedelta(days=90)

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

            # Validate date range
            if date_from >= date_to:
                return Response({
                    'error': _('End date must be after start date')
                }, status=status.HTTP_400_BAD_REQUEST)

            # Generate slots using service
            if availability_block_id:
                # Generate for specific availability block
                try:
                    availability_block = PsychologistAvailability.objects.get(
                        availability_id=availability_block_id,
                        psychologist=psychologist
                    )
                    slots = AppointmentSlotService.generate_slots_from_availability_block(
                        availability_block, date_from, date_to
                    )
                    result = {
                        'psychologist_id': str(psychologist.user.id),
                        'date_range': {'from': date_from, 'to': date_to},
                        'total_slots_created': len(slots),
                        'availability_blocks_processed': 1,
                        'results': [{
                            'availability_block_id': availability_block.availability_id,
                            'slots_created': len(slots),
                            'success': True
                        }]
                    }
                except PsychologistAvailability.DoesNotExist:
                    return Response({
                        'error': _('Availability block not found')
                    }, status=status.HTTP_404_NOT_FOUND)
            else:
                # Generate for all availability blocks
                result = AppointmentSlotService.bulk_generate_slots_for_psychologist(
                    psychologist, date_from, date_to
                )

            logger.info(f"Slots generated by {request.user.email}: {result['total_slots_created']} slots")
            return Response({
                'message': _('Slots generated successfully'),
                **result
            }, status=status.HTTP_200_OK)

        except SlotGenerationError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error generating slots for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to generate slots')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='psychologist_id',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Psychologist UUID to get slots for'
            ),
            OpenApiParameter(
                name='session_type',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Session type: OnlineMeeting or InitialConsultation'
            ),
            OpenApiParameter(
                name='date_from',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='Start date for available slots (default: today)'
            ),
            OpenApiParameter(
                name='date_to',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='End date for available slots (default: +30 days)'
            )
        ],
        responses={
            200: {
                'description': 'Available booking slots',
                'example': {
                    'psychologist_name': 'Dr. John Doe',
                    'session_type': 'OnlineMeeting',
                    'total_slots': 25,
                    'available_slots': [
                        {
                            'slot_id': 1,
                            'date': '2024-01-15',
                            'start_time': '09:00',
                            'end_time': '10:00',
                            'session_types': ['OnlineMeeting'],
                            'is_consecutive_block': False
                        }
                    ]
                }
            },
            400: {'description': 'Invalid parameters'}
        },
        description="Get available appointment slots for booking",
        tags=['Appointment Slots']
    )
    @action(detail=False, methods=['get'])
    def available_for_booking(self, request):
        """
        Get available appointment slots for booking
        GET /api/appointments/slots/available-for-booking/
        """
        try:
            # Parse query parameters
            psychologist_id = request.query_params.get('psychologist_id')
            session_type = request.query_params.get('session_type', 'OnlineMeeting')
            date_from_str = request.query_params.get('date_from')
            date_to_str = request.query_params.get('date_to')

            # Validate required parameters
            if not psychologist_id:
                return Response({
                    'error': _('psychologist_id parameter is required')
                }, status=status.HTTP_400_BAD_REQUEST)

            if session_type not in ['OnlineMeeting', 'InitialConsultation']:
                return Response({
                    'error': _('Invalid session_type. Must be OnlineMeeting or InitialConsultation')
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get psychologist
            try:
                psychologist = Psychologist.objects.get(user__id=psychologist_id)
            except Psychologist.DoesNotExist:
                return Response({
                    'error': _('Psychologist not found')
                }, status=status.HTTP_404_NOT_FOUND)

            # Validate psychologist is marketplace visible
            if not psychologist.is_marketplace_visible:
                return Response({
                    'error': _('Psychologist is not available for booking')
                }, status=status.HTTP_400_BAD_REQUEST)

            # Parse dates
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

            # Get available booking slots using service
            booking_data = AppointmentBookingService.get_available_booking_slots(
                psychologist, session_type, date_from, date_to
            )

            return Response(booking_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting available booking slots: {str(e)}")
            return Response({
                'error': _('Failed to get available slots')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: AppointmentSlotSerializer,
            404: {'description': 'Appointment slot not found'}
        },
        description="Get specific appointment slot details",
        tags=['Appointment Slots']
    )
    def retrieve(self, request, pk=None):
        """
        Get specific appointment slot
        GET /api/appointments/slots/{id}/
        """
        try:
            slot = self.get_object()
            serializer = self.get_serializer(slot)

            logger.info(f"Appointment slot accessed: {pk} by {request.user.email}")
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error retrieving appointment slot {pk}: {str(e)}")
            return Response({
                'error': _('Appointment slot not found')
            }, status=status.HTTP_404_NOT_FOUND)

    @extend_schema(
        responses={
            204: {'description': 'Appointment slot deleted successfully'},
            404: {'description': 'Appointment slot not found'},
            400: {'description': 'Cannot delete booked slot'}
        },
        description="Delete appointment slot",
        tags=['Appointment Slots']
    )
    def destroy(self, request, pk=None):
        """
        Delete appointment slot
        DELETE /api/appointments/slots/{id}/
        """
        # Force set the action if needed
        if self.action != 'destroy':
            print(f"WARNING: Action is {self.action}, forcing to 'destroy'")
            self.action = 'destroy'

        try:
            print("Calling get_object()...")
            slot = self.get_object()
            print(f"Found slot: {slot.slot_id} - {slot.psychologist.user.email}")

            # Check if slot is booked
            if slot.is_booked:
                return Response({
                    'error': _('Cannot delete booked appointment slot')
                }, status=status.HTTP_400_BAD_REQUEST)

            slot_info = f"{slot.slot_date} {slot.start_time}"
            slot.delete()

            logger.info(f"Appointment slot deleted: {slot_info} by {request.user.email}")
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            print(f"Exception in destroy: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='days_past',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Number of days past to clean up (default: 7)'
            )
        ],
        responses={
            200: {
                'description': 'Cleanup completed',
                'example': {
                    'message': 'Cleanup completed successfully',
                    'deleted_count': 150
                }
            }
        },
        description="Clean up past unbooked appointment slots (Admin only)",
        tags=['Appointment Slots']
    )
    @action(detail=False, methods=['post'])
    def cleanup_past_slots(self, request):
        """
        Clean up past unbooked appointment slots
        POST /api/appointments/slots/cleanup-past-slots/
        """
        # Only admins can perform cleanup
        if not (request.user.is_admin or request.user.is_staff):
            return Response({
                'error': _('Permission denied')
            }, status=status.HTTP_403_FORBIDDEN)

        try:
            days_past = int(request.query_params.get('days_past', 7))

            if days_past < 1:
                return Response({
                    'error': _('days_past must be at least 1')
                }, status=status.HTTP_400_BAD_REQUEST)

            # Perform cleanup using service
            deleted_count = AppointmentSlotService.cleanup_past_slots(days_past)

            logger.info(f"Appointment slots cleanup by admin {request.user.email}: {deleted_count} slots deleted")
            return Response({
                'message': _('Cleanup completed successfully'),
                'deleted_count': deleted_count,
                'days_past': days_past
            }, status=status.HTTP_200_OK)

        except ValueError:
            return Response({
                'error': _('Invalid days_past parameter')
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error during slots cleanup by {request.user.email}: {str(e)}")
            return Response({
                'error': _('Cleanup failed')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={
            200: {
                'description': 'Slot statistics',
                'example': {
                    'total_slots': 500,
                    'available_slots': 325,
                    'booked_slots': 175,
                    'utilization_rate': 35.0,
                    'by_psychologist': [
                        {'psychologist_name': 'Dr. Jane Doe', 'total_slots': 100, 'booked_slots': 45}
                    ]
                }
            }
        },
        description="Get appointment slot statistics (Admin only)",
        tags=['Appointment Slots']
    )
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Get appointment slot statistics
        GET /api/appointments/slots/statistics/
        """
        # Only admins can view platform statistics
        if not (request.user.is_admin or request.user.is_staff):
            return Response({
                'error': _('Permission denied')
            }, status=status.HTTP_403_FORBIDDEN)

        try:
            # Parse date filters
            date_from_str = request.query_params.get('date_from')
            date_to_str = request.query_params.get('date_to')

            queryset = AppointmentSlot.objects.all()

            if date_from_str:
                try:
                    date_from = date.fromisoformat(date_from_str)
                    queryset = queryset.filter(slot_date__gte=date_from)
                except ValueError:
                    return Response({
                        'error': _('Invalid date_from format. Use YYYY-MM-DD')
                    }, status=status.HTTP_400_BAD_REQUEST)

            if date_to_str:
                try:
                    date_to = date.fromisoformat(date_to_str)
                    queryset = queryset.filter(slot_date__lte=date_to)
                except ValueError:
                    return Response({
                        'error': _('Invalid date_to format. Use YYYY-MM-DD')
                    }, status=status.HTTP_400_BAD_REQUEST)

            # Calculate basic statistics
            total_slots = queryset.count()
            available_slots = queryset.filter(is_booked=False).count()
            booked_slots = queryset.filter(is_booked=True).count()
            utilization_rate = (booked_slots / total_slots * 100) if total_slots > 0 else 0

            # Statistics by psychologist
            from django.db.models import Count, Q
            psychologist_stats = queryset.values(
                'psychologist__user__id',
                'psychologist__first_name',
                'psychologist__last_name'
            ).annotate(
                total_slots=Count('slot_id'),
                booked_slots=Count('slot_id', filter=Q(is_booked=True))
            ).order_by('-total_slots')

            by_psychologist = [
                {
                    'psychologist_id': stat['psychologist__user__id'],
                    'psychologist_name': f"Dr. {stat['psychologist__first_name']} {stat['psychologist__last_name']}",
                    'total_slots': stat['total_slots'],
                    'booked_slots': stat['booked_slots'],
                    'available_slots': stat['total_slots'] - stat['booked_slots'],
                    'utilization_rate': (stat['booked_slots'] / stat['total_slots'] * 100) if stat['total_slots'] > 0 else 0
                }
                for stat in psychologist_stats
            ]

            statistics = {
                'total_slots': total_slots,
                'available_slots': available_slots,
                'booked_slots': booked_slots,
                'utilization_rate': round(utilization_rate, 1),
                'by_psychologist': by_psychologist,
                'date_filters': {
                    'date_from': date_from_str,
                    'date_to': date_to_str
                }
            }

            logger.info(f"Appointment slot statistics accessed by admin {request.user.email}")
            return Response(statistics, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error generating slot statistics for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to generate statistics')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from .serializers import (
    AppointmentSerializer,
    AppointmentCreateSerializer,
    AppointmentUpdateSerializer,
    AppointmentDetailSerializer,
    AppointmentSummarySerializer,
    QRVerificationSerializer,
    AppointmentSearchSerializer,
    AppointmentCancellationSerializer,
    BookingAvailabilitySerializer,
    AvailableSlotDisplaySerializer
)
from .services import (
    AppointmentBookingService,
    AppointmentManagementService,
    AppointmentAnalyticsService,
    AppointmentServiceError,
    AppointmentBookingError,
    AppointmentNotFoundError,
    AppointmentAccessDeniedError,
    AppointmentCancellationError,
    QRVerificationError,
    SlotNotAvailableError,
    InsufficientConsecutiveSlotsError
)
from .permissions import (
    IsAppointmentParticipant,
    CanBookAppointments,
    CanManageAppointments,
    CanCancelAppointment,
    CanVerifyQRCode,
    IsMarketplaceUser,
    AppointmentViewPermissions,
    IsPsychologistAppointmentProvider,
    IsParentAppointmentBooker,
    CanCompleteAppointment,
    CanAccessAnalytics
)
from psychologists.models import Psychologist
from psychologists.services import PsychologistService, PsychologistNotFoundError
from parents.services import ParentService, ParentNotFoundError
from children.models import Child

logger = logging.getLogger(__name__)


class AppointmentAnalyticsViewSet(GenericViewSet):
    """
    ViewSet for appointment analytics and reporting
    """
    permission_classes = [permissions.IsAuthenticated, CanAccessAnalytics]

    def get_permissions(self):
        """Set permissions based on action"""
        if self.action == 'platform_stats':
            # Only admins can access platform-wide statistics
            permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
        elif self.action == 'psychologist_stats':
            # Psychologists can see their own stats, admins can see all
            permission_classes = [permissions.IsAuthenticated, CanAccessAnalytics]
        else:
            permission_classes = [permissions.IsAuthenticated, CanAccessAnalytics]

        return [permission() for permission in permission_classes]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='psychologist_id',
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description='Psychologist ID (optional - defaults to current user if psychologist)',
                required=False
            ),
            OpenApiParameter(
                name='date_from',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='Start date for statistics (default: 30 days ago)',
                required=False
            ),
            OpenApiParameter(
                name='date_to',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='End date for statistics (default: today)',
                required=False
            )
        ],
        responses={
            200: {
                'description': 'Psychologist appointment statistics',
                'example': {
                    'psychologist_id': 'uuid',
                    'psychologist_name': 'Dr. John Doe',
                    'date_range': {'from': '2024-01-01', 'to': '2024-01-31'},
                    'statistics': {
                        'total_appointments': 45,
                        'completed_appointments': 38,
                        'cancelled_appointments': 5,
                        'no_show_appointments': 2,
                        'completion_rate': 84.4,
                        'online_sessions': 25,
                        'initial_consultations': 20,
                        'upcoming_appointments': 12
                    }
                }
            },
            403: {'description': 'Permission denied'},
            404: {'description': 'Psychologist not found'}
        },
        description="Get appointment statistics for a psychologist",
        tags=['Appointment Analytics']
    )
    @action(detail=False, methods=['get'])
    def psychologist_stats(self, request):
        """
        Get appointment statistics for a psychologist
        GET /api/appointments/analytics/psychologist-stats/
        """
        try:
            # Parse parameters
            psychologist_id = request.query_params.get('psychologist_id')
            date_from_str = request.query_params.get('date_from')
            date_to_str = request.query_params.get('date_to')

            # Default date range (last 30 days)
            date_to = date.today()
            date_from = date_to - timedelta(days=30)

            # Parse date parameters
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

            # Validate date range
            if date_from > date_to:
                return Response({
                    'error': _('Start date must be before end date')
                }, status=status.HTTP_400_BAD_REQUEST)

            # Determine which psychologist to get stats for
            if psychologist_id:
                # Admin requesting stats for specific psychologist
                if not (request.user.is_admin or request.user.is_staff):
                    return Response({
                        'error': _('Only admins can view other psychologists\' statistics')
                    }, status=status.HTTP_403_FORBIDDEN)

                try:
                    psychologist = PsychologistService.get_psychologist_by_id(psychologist_id)
                    if not psychologist:
                        return Response({
                            'error': _('Psychologist not found')
                        }, status=status.HTTP_404_NOT_FOUND)
                except Exception:
                    return Response({
                        'error': _('Psychologist not found')
                    }, status=status.HTTP_404_NOT_FOUND)

            else:
                # Psychologist requesting their own stats
                if request.user.user_type == 'Psychologist':
                    try:
                        psychologist = PsychologistService.get_psychologist_by_user_or_raise(request.user)
                    except PsychologistNotFoundError:
                        return Response({
                            'error': _('Psychologist profile not found')
                        }, status=status.HTTP_404_NOT_FOUND)
                else:
                    return Response({
                        'error': _('psychologist_id parameter is required for non-psychologist users')
                    }, status=status.HTTP_400_BAD_REQUEST)

            # Get statistics using service
            stats = AppointmentAnalyticsService.get_psychologist_appointment_stats(
                psychologist, date_from, date_to
            )

            # Format response
            response_data = {
                'psychologist_id': str(psychologist.user.id),
                'psychologist_name': psychologist.display_name,
                'date_range': {
                    'from': date_from,
                    'to': date_to
                },
                'statistics': stats,
                'generated_at': timezone.now()
            }

            logger.info(f"Psychologist statistics accessed: {psychologist.display_name} by {request.user.email}")
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting psychologist statistics for {request.user.email}: {str(e)}")
            return Response({
                'error': _('Failed to generate statistics')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)