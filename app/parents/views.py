# parents/views.py
from rest_framework import status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound, PermissionDenied
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from .models import Parent
from .serializers import (
    ParentSerializer,
    ParentProfileUpdateSerializer,
    CommunicationPreferencesSerializer,
    CommunicationPreferenceUpdateSerializer
)
from .permissions import IsParent


class ParentProfileView(generics.RetrieveUpdateAPIView):
    """
    Retrieve or update the current parent's profile
    """
    serializer_class = ParentSerializer
    permission_classes = [IsAuthenticated, IsParent]

    def get_object(self):
        """Get the current parent's profile"""
        try:
            return self.request.user.parent_profile
        except Parent.DoesNotExist:
            raise NotFound(_("Parent profile not found"))

    def get_serializer_class(self):
        """Use different serializer for updates"""
        if self.request.method in ['PUT', 'PATCH']:
            return ParentProfileUpdateSerializer
        return ParentSerializer

    @extend_schema(
        summary="Get current parent's profile",
        description="Retrieve the profile information for the currently authenticated parent",
        responses={
            200: ParentSerializer,
            404: OpenApiResponse(description="Parent profile not found")
        }
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Update parent's profile",
        description="Update the profile information for the currently authenticated parent",
        request=ParentProfileUpdateSerializer,
        responses={
            200: ParentSerializer,
            400: OpenApiResponse(description="Invalid data"),
            404: OpenApiResponse(description="Parent profile not found")
        }
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @extend_schema(
        summary="Partial update parent's profile",
        description="Partially update the profile information for the currently authenticated parent",
        request=ParentProfileUpdateSerializer,
        responses={
            200: ParentSerializer,
            400: OpenApiResponse(description="Invalid data"),
            404: OpenApiResponse(description="Parent profile not found")
        }
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)


class CommunicationPreferencesView(APIView):
    """
    Manage communication preferences for the current parent
    """
    permission_classes = [IsAuthenticated, IsParent]

    def get_parent(self):
        """Get the current parent's profile"""
        try:
            return self.request.user.parent_profile
        except Parent.DoesNotExist:
            raise NotFound(_("Parent profile not found"))

    @extend_schema(
        summary="Get communication preferences",
        description="Retrieve all communication preferences for the current parent",
        responses={
            200: CommunicationPreferencesSerializer,
            404: OpenApiResponse(description="Parent profile not found")
        }
    )
    def get(self, request):
        """Get all communication preferences"""
        parent = self.get_parent()
        preferences = parent.communication_preferences or Parent.get_default_communication_preferences()
        serializer = CommunicationPreferencesSerializer(data=preferences)
        serializer.is_valid()
        return Response(serializer.data)

    @extend_schema(
        summary="Update all communication preferences",
        description="Update all communication preferences at once",
        request=CommunicationPreferencesSerializer,
        responses={
            200: CommunicationPreferencesSerializer,
            400: OpenApiResponse(description="Invalid data"),
            404: OpenApiResponse(description="Parent profile not found")
        }
    )
    def put(self, request):
        """Update all communication preferences"""
        parent = self.get_parent()
        serializer = CommunicationPreferencesSerializer(data=request.data)

        if serializer.is_valid():
            parent.communication_preferences = serializer.validated_data
            parent.save(update_fields=['communication_preferences', 'updated_at'])
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Update specific communication preference",
        description="Update a single communication preference",
        request=CommunicationPreferenceUpdateSerializer,
        responses={
            200: OpenApiResponse(
                description="Preference updated successfully",
                examples={
                    'application/json': {
                        'preference_key': 'email_notifications',
                        'value': True,
                        'message': 'Preference updated successfully'
                    }
                }
            ),
            400: OpenApiResponse(description="Invalid data"),
            404: OpenApiResponse(description="Parent profile not found")
        }
    )
    def patch(self, request):
        """Update a specific communication preference"""
        parent = self.get_parent()
        serializer = CommunicationPreferenceUpdateSerializer(data=request.data)

        if serializer.is_valid():
            preference_key = serializer.validated_data['preference_key']
            value = serializer.validated_data['value']

            parent.set_communication_preference(preference_key, value)

            return Response({
                'preference_key': preference_key,
                'value': value,
                'message': _('Preference updated successfully')
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ParentOnboardingStatusView(APIView):
    """
    Check parent's onboarding status
    """
    permission_classes = [IsAuthenticated, IsParent]

    @extend_schema(
        summary="Get parent onboarding status",
        description="Check if parent has completed profile setup",
        responses={
            200: OpenApiResponse(
                description="Onboarding status",
                examples={
                    'application/json': {
                        'is_profile_complete': True,
                        'missing_fields': [],
                        'has_children': False,
                        'total_children': 0
                    }
                }
            ),
            404: OpenApiResponse(description="Parent profile not found")
        }
    )
    def get(self, request):
        """Get parent's onboarding status"""
        try:
            parent = request.user.parent_profile
        except Parent.DoesNotExist:
            raise NotFound(_("Parent profile not found"))

        # Check required fields
        required_fields = ['first_name', 'last_name']
        missing_fields = []

        for field in required_fields:
            if not getattr(parent, field):
                missing_fields.append(field)

        # Check if parent has added any children (for future implementation)
        # has_children = parent.children.exists()
        # total_children = parent.children.count()

        return Response({
            'is_profile_complete': len(missing_fields) == 0,
            'missing_fields': missing_fields,
            'has_children': False,  # Placeholder for future implementation
            'total_children': 0     # Placeholder for future implementation
        })