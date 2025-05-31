# appointments/serializers.py
from rest_framework import serializers
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import date, datetime, timedelta, time
from django.core.exceptions import ValidationError

from .models import AppointmentSlot, Appointment
from psychologists.models import Psychologist
from parents.models import Parent
from children.models import Child
from psychologists.serializers import PsychologistSummarySerializer
from parents.serializers import ParentSummarySerializer
from children.serializers import ChildSummarySerializer


class AppointmentSlotSerializer(serializers.ModelSerializer):
    """
    Basic serializer for AppointmentSlot model
    """
    # Read-only computed fields
    psychologist_name = serializers.CharField(source='psychologist.display_name', read_only=True)
    datetime_start = serializers.DateTimeField(read_only=True)
    datetime_end = serializers.DateTimeField(read_only=True)
    is_available_for_booking = serializers.BooleanField(read_only=True)

    class Meta:
        model = AppointmentSlot
        fields = [
            'slot_id',
            'psychologist',
            'psychologist_name',
            'availability_block',
            'slot_date',
            'start_time',
            'end_time',
            'is_booked',
            'datetime_start',
            'datetime_end',
            'is_available_for_booking',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'slot_id',
            'psychologist_name',
            'datetime_start',
            'datetime_end',
            'is_available_for_booking',
            'created_at',
            'updated_at',
        ]


class AppointmentSlotCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating appointment slots (system/admin use)
    """

    class Meta:
        model = AppointmentSlot
        fields = [
            'psychologist',
            'availability_block',
            'slot_date',
            'start_time',
            'end_time',
        ]

    def validate_slot_date(self, value):
        """Validate slot date is not in the past"""
        if value < date.today():
            raise serializers.ValidationError(_("Slot date cannot be in the past"))
        return value

    def validate(self, attrs):
        """Cross-field validation"""
        start_time = attrs.get('start_time')
        end_time = attrs.get('end_time')

        if start_time and end_time:
            # Validate end_time is start_time + 1 hour
            expected_end_time = (datetime.combine(date.today(), start_time) + timedelta(hours=1)).time()
            if end_time != expected_end_time:
                raise serializers.ValidationError({
                    'end_time': _("End time must be exactly 1 hour after start time")
                })

        return attrs


class AppointmentSerializer(serializers.ModelSerializer):
    """
    Basic serializer for Appointment model
    """
    # Read-only computed fields
    duration_hours = serializers.IntegerField(read_only=True)
    is_upcoming = serializers.BooleanField(read_only=True)
    is_past = serializers.BooleanField(read_only=True)
    can_be_cancelled = serializers.BooleanField(read_only=True)
    can_be_verified = serializers.BooleanField(read_only=True)

    # Related model summary fields
    child_name = serializers.CharField(source='child.display_name', read_only=True)
    psychologist_name = serializers.CharField(source='psychologist.display_name', read_only=True)
    parent_email = serializers.EmailField(source='parent.user.email', read_only=True)

    class Meta:
        model = Appointment
        fields = [
            # Identity
            'appointment_id',
            'child',
            'child_name',
            'psychologist',
            'psychologist_name',
            'parent',
            'parent_email',

            # Appointment details
            'session_type',
            'appointment_status',
            'scheduled_start_time',
            'scheduled_end_time',
            'actual_start_time',
            'actual_end_time',

            # Meeting details
            'meeting_address',
            'meeting_link',
            'meeting_id',
            'qr_verification_code',
            'session_verified_at',

            # Notes
            'parent_notes',
            'psychologist_notes',
            'cancellation_reason',

            # Computed fields
            'duration_hours',
            'is_upcoming',
            'is_past',
            'can_be_cancelled',
            'can_be_verified',

            # Timestamps
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'appointment_id',
            'child_name',
            'psychologist_name',
            'parent_email',
            'duration_hours',
            'is_upcoming',
            'is_past',
            'can_be_cancelled',
            'can_be_verified',
            'created_at',
            'updated_at',
        ]


class AppointmentCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating appointments (booking)
    """
    # Slot selection - will be converted to M2M relationship during creation
    start_slot_id = serializers.IntegerField(
        write_only=True,
        help_text=_("ID of the first slot to book (for consecutive booking)")
    )
    child = serializers.PrimaryKeyRelatedField(queryset=Child.objects.all())

    class Meta:
        model = Appointment
        fields = [
            'child',
            'psychologist',
            'session_type',
            'start_slot_id',
            'parent_notes',
        ]

    def validate_child(self, value):
        """Validate child exists and belongs to requesting parent"""
        print(f"[DEBUG] validate_child: value.parent = {value.parent}, request.user = {self.context.get('request').user}")
        request = self.context.get('request')
        if request and hasattr(request.user, 'parent_profile'):
            if value.parent != request.user.parent_profile:
                raise serializers.ValidationError(_("You can only book appointments for your own children"))
        return value

    def validate_session_type(self, value):
        """Validate session type is valid"""
        if value not in ['OnlineMeeting', 'InitialConsultation']:
            raise serializers.ValidationError(_("Invalid session type"))
        return value

    def validate(self, attrs):
        """Cross-field validation and business logic checks"""
        psychologist = attrs.get('psychologist')
        session_type = attrs.get('session_type')
        start_slot_id = attrs.get('start_slot_id')

        # Validate psychologist offers the requested service type
        if session_type == 'OnlineMeeting' and not psychologist.offers_online_sessions:
            raise serializers.ValidationError({
                'session_type': _("This psychologist does not offer online sessions")
            })

        if session_type == 'InitialConsultation' and not psychologist.offers_initial_consultation:
            raise serializers.ValidationError({
                'session_type': _("This psychologist does not offer initial consultations")
            })

        # Validate psychologist is marketplace visible
        if not psychologist.is_marketplace_visible:
            raise serializers.ValidationError({
                'psychologist': _("This psychologist is not available for booking")
            })

        # Validate slot availability (business logic will be in service layer)
        try:
            start_slot = AppointmentSlot.objects.get(
                slot_id=start_slot_id,
                psychologist=psychologist
            )

            if not start_slot.is_available_for_booking:
                raise serializers.ValidationError({
                    'start_slot_id': _("This slot is not available for booking")
                })

            # NEW: Validate consecutive slots for InitialConsultation
            if session_type == 'InitialConsultation':
                slots_needed = 2
                consecutive_slots = AppointmentSlot.find_consecutive_slots(
                    psychologist, start_slot.slot_date, start_slot.start_time, slots_needed
                )

                if len(consecutive_slots) < slots_needed:
                    raise serializers.ValidationError({
                        'start_slot_id': _("Not enough consecutive slots available for 2-hour appointment")
                    })

            # Store for service layer
            attrs['_start_slot'] = start_slot

        except AppointmentSlot.DoesNotExist:
            raise serializers.ValidationError({
                'start_slot_id': _("Invalid slot ID")
            })

        return attrs

    def create(self, validated_data):
        """
        Create appointment - delegate to service layer
        Business logic for consecutive slot booking will be handled in service
        """
        # Remove non-model fields
        start_slot = validated_data.pop('_start_slot')
        start_slot_id = validated_data.pop('start_slot_id')

        # Get parent from request context
        request = self.context.get('request')
        if request and hasattr(request.user, 'parent_profile'):
            validated_data['parent'] = request.user.parent_profile

        # Set scheduled times from start slot
        validated_data['scheduled_start_time'] = start_slot.datetime_start

        # Calculate end time based on session type
        if validated_data['session_type'] == 'OnlineMeeting':
            validated_data['scheduled_end_time'] = start_slot.datetime_end
        else:  # InitialConsultation
            validated_data['scheduled_end_time'] = start_slot.datetime_start + timedelta(hours=2)

        # Store slot info for service layer
        validated_data['_booking_slot_id'] = start_slot_id

        return validated_data  # Return validated data for service layer processing


class AppointmentUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating appointments (limited fields)
    """

    class Meta:
        model = Appointment
        fields = [
            'parent_notes',
            'psychologist_notes',
            'cancellation_reason',
        ]

    def validate(self, attrs):
        """Validate update permissions based on user type"""
        request = self.context.get('request')
        instance = self.instance

        if request:
            # Validate appointment can be updated
            if instance and instance.appointment_status == 'Completed':
                # Only notes can be updated for completed appointments
                if 'cancellation_reason' in attrs:
                    raise serializers.ValidationError({
                        'cancellation_reason': _("Cannot modify cancellation reason for completed appointments")
                    })

        return attrs


class AppointmentDetailSerializer(AppointmentSerializer):
    """
    Extended serializer for detailed appointment information
    """
    # Include full related object information
    child = ChildSummarySerializer(read_only=True)
    psychologist = PsychologistSummarySerializer(read_only=True)
    parent = ParentSummarySerializer(read_only=True)

    # Include appointment slots information
    appointment_slots = AppointmentSlotSerializer(many=True, read_only=True)

    # Additional computed fields
    meeting_info = serializers.SerializerMethodField()
    verification_info = serializers.SerializerMethodField()

    class Meta(AppointmentSerializer.Meta):
        fields = AppointmentSerializer.Meta.fields + [
            'appointment_slots',
            'meeting_info',
            'verification_info',
        ]

    def get_meeting_info(self, obj):
        """Get meeting information based on session type"""
        if obj.session_type == 'OnlineMeeting':
            return {
                'type': 'online',
                'meeting_link': obj.meeting_link,
                'meeting_id': obj.meeting_id,
                'instructions': _("Join the video call at the scheduled time using the meeting link provided.")
            }
        else:  # InitialConsultation
            return {
                'type': 'in_person',
                'address': obj.meeting_address,
                'qr_code': obj.qr_verification_code,
                'instructions': _("Please arrive at the office address 5 minutes before your appointment. Scan the QR code when you arrive.")
            }

    def get_verification_info(self, obj):
        """Get verification status information"""
        if obj.session_type == 'InitialConsultation':
            return {
                'requires_verification': True,
                'is_verified': bool(obj.session_verified_at),
                'verified_at': obj.session_verified_at,
                'can_verify_now': obj.can_be_verified,
                'qr_code': obj.qr_verification_code if obj.can_be_verified else None
            }
        return {
            'requires_verification': False,
            'is_verified': True,  # Online meetings don't need verification
            'verified_at': None,
            'can_verify_now': False,
            'qr_code': None
        }


class AppointmentSummarySerializer(serializers.ModelSerializer):
    """
    Minimal serializer for appointment summary (listings, calendars, etc.)
    """
    child_name = serializers.CharField(source='child.display_name', read_only=True)
    psychologist_name = serializers.CharField(source='psychologist.display_name', read_only=True)
    duration_hours = serializers.IntegerField(read_only=True)
    is_upcoming = serializers.BooleanField(read_only=True)

    class Meta:
        model = Appointment
        fields = [
            'appointment_id',
            'child_name',
            'psychologist_name',
            'session_type',
            'appointment_status',
            'scheduled_start_time',
            'scheduled_end_time',
            'duration_hours',
            'is_upcoming',
            'meeting_address',  # For quick location reference
            'created_at',
        ]
        read_only_fields = [
            'appointment_id',
            'child_name',
            'psychologist_name',
            'duration_hours',
            'is_upcoming',
            'created_at',
        ]


class QRVerificationSerializer(serializers.Serializer):
    """
    Dedicated serializer for QR code verification
    """
    qr_code = serializers.CharField(
        max_length=32,
        help_text=_("QR verification code scanned by parent")
    )

    def validate_qr_code(self, value):
        """Validate QR code exists and is verifiable"""
        try:
            appointment = Appointment.objects.get(qr_verification_code=value)

            if not appointment.can_be_verified:
                raise serializers.ValidationError(
                    _("This appointment cannot be verified at this time")
                )

            # Store appointment for use in service layer
            self._appointment = appointment
            return value

        except Appointment.DoesNotExist:
            raise serializers.ValidationError(_("Invalid QR code"))

    def save(self):
        """Verify the appointment"""
        if hasattr(self, '_appointment'):
            self._appointment.verify_session()
            return self._appointment
        raise ValidationError(_("No appointment to verify"))


class AppointmentSearchSerializer(serializers.Serializer):
    """
    Serializer for appointment search and filtering
    """
    # Date range filters
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    # Status filters
    appointment_status = serializers.ChoiceField(
        choices=Appointment.APPOINTMENT_STATUS_CHOICES,
        required=False
    )

    # Session type filter
    session_type = serializers.ChoiceField(
        choices=Appointment.SESSION_TYPE_CHOICES,
        required=False
    )

    # User-specific filters
    child_id = serializers.UUIDField(required=False)
    psychologist_id = serializers.UUIDField(required=False)

    # Time-based filters
    is_upcoming = serializers.BooleanField(required=False)
    is_past = serializers.BooleanField(required=False)

    def validate(self, attrs):
        """Validate search parameters"""
        date_from = attrs.get('date_from')
        date_to = attrs.get('date_to')

        # Validate date range
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError({
                'date_from': _("Start date must be before end date")
            })

        # Validate conflicting time filters
        is_upcoming = attrs.get('is_upcoming')
        is_past = attrs.get('is_past')

        if is_upcoming and is_past:
            raise serializers.ValidationError(
                _("Cannot filter for both upcoming and past appointments")
            )

        return attrs


class AvailableSlotDisplaySerializer(serializers.Serializer):
    """
    Serializer for displaying available booking slots to parents
    Handles the display logic for 1-hour vs 2-hour blocks
    """
    slot_id = serializers.IntegerField()
    psychologist_id = serializers.UUIDField()
    date = serializers.DateField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    session_types = serializers.ListField(
        child=serializers.CharField(),
        help_text=_("Which session types can book this slot/block")
    )

    # For 2-hour blocks (InitialConsultation)
    is_consecutive_block = serializers.BooleanField(default=False)
    consecutive_slot_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text=_("IDs of slots that make up this 2-hour block")
    )


class BookingAvailabilitySerializer(serializers.Serializer):
    """
    Serializer for displaying booking availability for a specific psychologist and session type
    """
    psychologist_id = serializers.UUIDField()
    psychologist_name = serializers.CharField()
    session_type = serializers.ChoiceField(choices=Appointment.SESSION_TYPE_CHOICES)
    date_from = serializers.DateField()
    date_to = serializers.DateField()

    available_slots = AvailableSlotDisplaySerializer(many=True, read_only=True)
    total_slots = serializers.IntegerField(read_only=True)


class AppointmentCancellationSerializer(serializers.Serializer):
    """
    Serializer for appointment cancellation
    """
    cancellation_reason = serializers.CharField(
        max_length=1000,
        required=False,
        allow_blank=True,
        help_text=_("Reason for cancelling the appointment")
    )

    def validate(self, attrs):
        """Validate cancellation is allowed"""
        appointment = self.context.get('appointment')

        if appointment and not appointment.can_be_cancelled:
            raise serializers.ValidationError(
                _("This appointment cannot be cancelled")
            )

        return attrs