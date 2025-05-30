from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils.translation import gettext_lazy as _

from .serializers import (
    PsychologistRegistrationSerializer,
    PsychologistProfileSerializer,
    PsychologistPublicProfileSerializer,
    AvailabilityCreateUpdateSerializer,
    AvailabilityListSerializer,
    PsychologistSearchSerializer,
    PsychologistVerificationSerializer,
    AvailabilityBulkSerializer,
)
from .services import (
    PsychologistService,
    PsychologistRegistrationError,
    PsychologistNotFoundError,
    AvailabilityService,
    AvailabilityConflictError,
    VerificationError,
)
from .permissions import IsPsychologist, IsAdmin, IsParent  # Adjust based on your permissions
from .models import PsychologistAvailability
from rest_framework.permissions import IsAuthenticated


class PsychologistRegistrationView(APIView):
    """
    API endpoint for psychologist registration
    """
    permission_classes = []

    def post(self, request):
        serializer = PsychologistRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            try:
                psychologist = PsychologistService.register_psychologist(serializer.validated_data)
                output_serializer = PsychologistProfileSerializer(psychologist)
                return Response(output_serializer.data, status=status.HTTP_201_CREATED)
            except PsychologistRegistrationError as e:
                return Response(
                    {"error": str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PsychologistProfileView(APIView):
    """
    API endpoint for retrieving and updating psychologist profile
    """
    permission_classes = [IsAuthenticated, IsPsychologist]

    def get(self, request):
        try:
            psychologist = PsychologistService.get_psychologist_by_user_id(request.user.id)
            serializer = PsychologistProfileSerializer(psychologist)
            return Response(serializer.data)
        except PsychologistNotFoundError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND
            )

    def patch(self, request):
        try:
            psychologist = PsychologistService.get_psychologist_by_user_id(request.user.id)
            serializer = PsychologistProfileSerializer(psychologist, data=request.data, partial=True)
            if serializer.is_valid():
                updated_psychologist = PsychologistService.update_psychologist_profile(
                    psychologist, serializer.validated_data
                )
                output_serializer = PsychologistProfileSerializer(updated_psychologist)
                return Response(output_serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except PsychologistNotFoundError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND
            )
        except PsychologistRegistrationError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class PsychologistSearchView(APIView):
    """
    API endpoint for searching psychologists
    """
    permission_classes = [IsAuthenticated, IsParent]
    serializer_class = PsychologistSearchSerializer

    def get(self, request):
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            search_results = PsychologistService.search_psychologists(**serializer.validated_data)
            output_serializer = PsychologistPublicProfileSerializer(search_results['psychologists'], many=True)
            return Response({
                'psychologists': output_serializer.data,
                'total_count': search_results['total_count'],
                'search_params': serializer.validated_data,
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        serializer = PsychologistRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            psychologist = PsychologistService.register_psychologist(**serializer.validated_data)
            output_serializer = PsychologistProfileSerializer(psychologist)
            return Response(output_serializer.data, status=status.HTTP_201_CREATED)
        except PsychologistRegistrationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AvailabilityCreateView(APIView):
    """
    API endpoint for creating a new availability slot
    """
    permission_classes = [IsAuthenticated, IsPsychologist]

    def post(self, request):
        serializer = AvailabilityCreateUpdateSerializer(data=request.data)
        if serializer.is_valid():
            try:
                psychologist = PsychologistService.get_psychologist_by_user_id(request.user.id)
                availability = AvailabilityService.create_availability_slot(
                    psychologist, serializer.validated_data
                )
                output_serializer = AvailabilityListSerializer(availability)
                return Response(output_serializer.data, status=status.HTTP_201_CREATED)
            except (PsychologistNotFoundError, AvailabilityConflictError) as e:
                return Response(
                    {"error": str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AvailabilityDetailView(APIView):
    """
    API endpoint for updating or deleting an availability slot
    """
    permission_classes = [IsAuthenticated, IsPsychologist]

    def patch(self, request, availability_id):
        try:
            slot = PsychologistAvailability.objects.get(
                id=availability_id,
                psychologist__user=request.user
            )
            serializer = AvailabilityCreateUpdateSerializer(slot, data=request.data, partial=True)
            if serializer.is_valid():
                updated_slot = AvailabilityService.update_availability_slot(
                    slot, serializer.validated_data
                )
                output_serializer = AvailabilityListSerializer(updated_slot)
                return Response(output_serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except PsychologistAvailability.DoesNotExist:
            return Response(
                {"error": _("Availability slot not found")},
                status=status.HTTP_404_NOT_FOUND
            )
        except AvailabilityConflictError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def delete(self, request, availability_id):
        try:
            slot = PsychologistAvailability.objects.get(
                id=availability_id,
                psychologist__user=request.user
            )
            AvailabilityService.delete_availability_slot(slot)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except PsychologistAvailability.DoesNotExist:
            return Response(
                {"error": _("Availability slot not found")},
                status=status.HTTP_404_NOT_FOUND
            )
        except AvailabilityConflictError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class AvailabilityListView(APIView):
    """
    API endpoint for listing psychologist's availability
    """
    permission_classes = [IsAuthenticated, IsPsychologist]

    def get(self, request):
        try:
            psychologist = PsychologistService.get_psychologist_by_user_id(request.user.id)
            date_range = None
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            if start_date and end_date:
                date_range = (start_date, end_date)
            slots = AvailabilityService.get_psychologist_availability(psychologist, date_range)
            serializer = AvailabilityListSerializer(slots, many=True)
            return Response(serializer.data)
        except PsychologistNotFoundError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND
            )


class AvailabilityBulkView(APIView):
    """
    API endpoint for bulk availability operations
    """
    permission_classes = [IsAuthenticated, IsPsychologist]

    def post(self, request):
        serializer = AvailabilityBulkSerializer(data=request.data)
        if serializer.is_valid():
            try:
                psychologist = PsychologistService.get_psychologist_by_user_id(request.user.id)
                results = AvailabilityService.bulk_manage_availability(
                    psychologist, serializer.validated_data
                )
                return Response(results, status=status.HTTP_200_OK)
            except (PsychologistNotFoundError, AvailabilityConflictError) as e:
                return Response(
                    {"error": str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PsychologistVerificationView(APIView):
    """
    API endpoint for admin verification of psychologists
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def patch(self, request, psychologist_id):
        try:
            psychologist = PsychologistService.get_psychologist_by_user_id(psychologist_id)
            serializer = PsychologistVerificationSerializer(psychologist, data=request.data, partial=True)
            if serializer.is_valid():
                updated_psychologist = PsychologistService.verify_psychologist(
                    psychologist, serializer.validated_data
                )
                output_serializer = PsychologistVerificationSerializer(updated_psychologist)
                return Response(output_serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except PsychologistNotFoundError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND
            )
        except VerificationError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )