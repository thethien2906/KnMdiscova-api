# psychologists/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import datetime, time, date
import re

from .models import Psychologist, PsychologistAvailability

User = get_user_model()


class PsychologistRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for psychologist registration with input validation
    """
    # User fields
    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={'input_type': 'password'},
        help_text=_("Password must be at least 8 characters long")
    )
    password_confirm = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'},
        help_text=_("Confirm your password")
    )

    # Professional validation
    license_number = serializers.CharField(
        max_length=100,
        validators=[
            RegexValidator(
                regex=r'^[A-Z0-9\-]+$',
                message=_("License number must contain only uppercase letters, numbers, and hyphens")
            )
        ]
    )

    # Education and certifications as structured data
    education = serializers.ListField(
        child=serializers.DictField(
            child=serializers.CharField(max_length=255)
        ),
        required=False,
        allow_empty=True,
        help_text=_("Array of education objects with keys: degree, institution, year")
    )

    certifications = serializers.ListField(
        child=serializers.DictField(
            child=serializers.CharField(max_length=255)
        ),
        required=False,
        allow_empty=True,
        help_text=_("Array of certification objects with keys: name, institution, year")
    )

    class Meta:
        model = Psychologist
        fields = [
            'email', 'password', 'password_confirm',
            'first_name', 'last_name', 'license_number',
            'license_issuing_authority', 'license_expiry_date',
            'years_of_experience', 'biography', 'education',
            'certifications', 'hourly_rate', 'website_url',
            'linkedin_url'
        ]
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True},
            'years_of_experience': {'required': True, 'min_value': 0, 'max_value': 50},
            'hourly_rate': {'min_value': 0},
        }

    def validate_password_confirm(self, value):
        """Validate password confirmation matches"""
        password = self.initial_data.get('password')
        if password and value != password:
            raise serializers.ValidationError(_("Password confirmation does not match"))
        return value

    def validate_email(self, value):
        """Check if email is already registered"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(_("User with this email already exists"))
        return value

    def validate_license_number(self, value):
        """Check if license number is unique"""
        if Psychologist.objects.filter(license_number=value).exists():
            raise serializers.ValidationError(_("Psychologist with this license number already exists"))
        return value

    def validate_education(self, value):
        """Validate education structure"""
        required_keys = {'degree', 'institution', 'year'}
        for item in value:
            if not all(key in item for key in required_keys):
                raise serializers.ValidationError(
                    _("Each education entry must have 'degree', 'institution', and 'year' keys")
                )
            # Validate year is reasonable
            try:
                year = int(item['year'])
                if year < 1950 or year > timezone.now().year:
                    raise serializers.ValidationError(_("Education year must be between 1950 and current year"))
            except (ValueError, TypeError):
                raise serializers.ValidationError(_("Education year must be a valid number"))
        return value

    def validate_certifications(self, value):
        """Validate certifications structure"""
        required_keys = {'name', 'institution', 'year'}
        for item in value:
            if not all(key in item for key in required_keys):
                raise serializers.ValidationError(
                    _("Each certification entry must have 'name', 'institution', and 'year' keys")
                )
            # Validate year is reasonable
            try:
                year = int(item['year'])
                if year < 1950 or year > timezone.now().year:
                    raise serializers.ValidationError(_("Certification year must be between 1950 and current year"))
            except (ValueError, TypeError):
                raise serializers.ValidationError(_("Certification year must be a valid number"))
        return value

    def validate_license_expiry_date(self, value):
        """Validate license expiry date is in the future"""
        if value and value <= timezone.now().date():
            raise serializers.ValidationError(_("License expiry date must be in the future"))
        return value


class PsychologistProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for full psychologist profile CRUD operations
    """
    email = serializers.EmailField(source='user.email', read_only=True)
    user_type = serializers.CharField(source='user.user_type', read_only=True)
    is_active = serializers.BooleanField(source='user.is_active', read_only=True)
    is_verified = serializers.BooleanField(source='user.is_verified', read_only=True)

    # Computed properties
    full_name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    can_accept_appointments = serializers.SerializerMethodField()

    class Meta:
        model = Psychologist
        fields = [
            'email', 'user_type', 'is_active', 'is_verified',
            'first_name', 'last_name', 'full_name', 'display_name',
            'license_number', 'license_issuing_authority', 'license_expiry_date',
            'years_of_experience', 'biography', 'education', 'certifications',
            'hourly_rate', 'verification_status', 'website_url', 'linkedin_url',
            'can_accept_appointments', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'email', 'user_type', 'is_active', 'is_verified',
            'full_name', 'display_name', 'verification_status',
            'can_accept_appointments', 'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'years_of_experience': {'min_value': 0, 'max_value': 50},
            'hourly_rate': {'min_value': 0},
        }

    def get_can_accept_appointments(self, obj):
        """Check if psychologist can accept appointments"""
        return obj.can_accept_appointments()

    def validate_license_number(self, value):
        """Check license number uniqueness on update"""
        instance = getattr(self, 'instance', None)
        if instance and instance.license_number != value:
            if Psychologist.objects.filter(license_number=value).exists():
                raise serializers.ValidationError(_("Psychologist with this license number already exists"))
        return value

    def validate_education(self, value):
        """Validate education structure"""
        if not isinstance(value, list):
            raise serializers.ValidationError(_("Education must be a list"))

        required_keys = {'degree', 'institution', 'year'}
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError(_("Each education entry must be an object"))
            if not all(key in item for key in required_keys):
                raise serializers.ValidationError(
                    _("Each education entry must have 'degree', 'institution', and 'year' keys")
                )
        return value

    def validate_certifications(self, value):
        """Validate certifications structure"""
        if not isinstance(value, list):
            raise serializers.ValidationError(_("Certifications must be a list"))

        required_keys = {'name', 'institution', 'year'}
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError(_("Each certification entry must be an object"))
            if not all(key in item for key in required_keys):
                raise serializers.ValidationError(
                    _("Each certification entry must have 'name', 'institution', and 'year' keys")
                )
        return value


class PsychologistPublicProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for public-facing psychologist profile display (read-only)
    """
    full_name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    is_verified = serializers.BooleanField(read_only=True)

    # Filtered education and certifications for public view
    public_education = serializers.SerializerMethodField()
    public_certifications = serializers.SerializerMethodField()

    class Meta:
        model = Psychologist
        fields = [
            'display_name', 'full_name', 'is_verified',
            'years_of_experience', 'biography', 'public_education',
            'public_certifications', 'hourly_rate', 'website_url'
        ]

    def get_public_education(self, obj):
        """Return sanitized education info for public view"""
        education = obj.education or []
        return [
            {
                'degree': item.get('degree', ''),
                'institution': item.get('institution', ''),
                'year': item.get('year', '')
            }
            for item in education
        ]

    def get_public_certifications(self, obj):
        """Return sanitized certifications for public view"""
        certifications = obj.certifications or []
        return [
            {
                'name': item.get('name', ''),
                'institution': item.get('institution', ''),
                'year': item.get('year', '')
            }
            for item in certifications
        ]


class AvailabilityCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for individual availability slot management
    """
    class Meta:
        model = PsychologistAvailability
        fields = [
            'id', 'day_of_week', 'start_time', 'end_time',
            'is_recurring', 'specific_date', 'is_booked'
        ]
        read_only_fields = ['id', 'is_booked']

    def validate(self, data):
        """Cross-field validation"""
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        is_recurring = data.get('is_recurring', True)
        specific_date = data.get('specific_date')

        # Validate time sequence
        if start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError({
                'end_time': _("End time must be after start time")
            })

        # Validate recurring vs specific date logic
        if not is_recurring and not specific_date:
            raise serializers.ValidationError({
                'specific_date': _("Non-recurring availability must have a specific date")
            })

        if is_recurring and specific_date:
            raise serializers.ValidationError({
                'specific_date': _("Recurring availability cannot have a specific date")
            })

        # Validate specific date is in the future
        if specific_date and specific_date <= timezone.now().date():
            raise serializers.ValidationError({
                'specific_date': _("Specific date must be in the future")
            })

        return data

    def validate_day_of_week(self, value):
        """Validate day of week is in valid range"""
        if value < 0 or value > 6:
            raise serializers.ValidationError(_("Day of week must be between 0 (Sunday) and 6 (Saturday)"))
        return value


class AvailabilityListSerializer(serializers.ModelSerializer):
    """
    Serializer for displaying availability slots (read-only)
    """
    day_name = serializers.SerializerMethodField()
    duration_hours = serializers.ReadOnlyField()
    formatted_time = serializers.SerializerMethodField()
    psychologist_name = serializers.CharField(source='psychologist.display_name', read_only=True)

    class Meta:
        model = PsychologistAvailability
        fields = [
            'id', 'day_of_week', 'day_name', 'start_time', 'end_time',
            'formatted_time', 'duration_hours', 'is_recurring',
            'specific_date', 'is_booked', 'psychologist_name',
            'created_at', 'updated_at'
        ]

    def get_day_name(self, obj):
        """Get human-readable day name"""
        if obj.is_recurring:
            day_choices = dict(PsychologistAvailability.DAY_OF_WEEK_CHOICES)
            return day_choices.get(obj.day_of_week, '')
        return None

    def get_formatted_time(self, obj):
        """Get formatted time range"""
        return f"{obj.start_time.strftime('%H:%M')} - {obj.end_time.strftime('%H:%M')}"


class PsychologistSearchSerializer(serializers.Serializer):
    """
    Serializer for psychologist search filtering and query parameters
    """
    search = serializers.CharField(
        required=False,
        max_length=255,
        help_text=_("Search in name, biography, or specialties")
    )
    min_experience = serializers.IntegerField(
        required=False,
        min_value=0,
        max_value=50,
        help_text=_("Minimum years of experience")
    )
    max_experience = serializers.IntegerField(
        required=False,
        min_value=0,
        max_value=50,
        help_text=_("Maximum years of experience")
    )
    min_rate = serializers.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=2,
        min_value=0,
        help_text=_("Minimum hourly rate")
    )
    max_rate = serializers.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=2,
        min_value=0,
        help_text=_("Maximum hourly rate")
    )
    verification_status = serializers.ChoiceField(
        choices=Psychologist.VERIFICATION_STATUS_CHOICES,
        required=False,
        help_text=_("Filter by verification status")
    )
    available_on = serializers.DateField(
        required=False,
        help_text=_("Filter psychologists available on specific date")
    )

    # Ordering options
    ordering = serializers.ChoiceField(
        choices=[
            ('created_at', _('Newest first')),
            ('-created_at', _('Oldest first')),
            ('years_of_experience', _('Least experienced first')),
            ('-years_of_experience', _('Most experienced first')),
            ('hourly_rate', _('Lowest rate first')),
            ('-hourly_rate', _('Highest rate first')),
            ('first_name', _('Name A-Z')),
            ('-first_name', _('Name Z-A')),
        ],
        required=False,
        default='-created_at'
    )

    def validate(self, data):
        """Cross-field validation for search parameters"""
        min_exp = data.get('min_experience')
        max_exp = data.get('max_experience')
        min_rate = data.get('min_rate')
        max_rate = data.get('max_rate')
        available_on = data.get('available_on')

        # Validate experience range
        if min_exp is not None and max_exp is not None and min_exp > max_exp:
            raise serializers.ValidationError({
                'max_experience': _("Maximum experience must be greater than minimum experience")
            })

        # Validate rate range
        if min_rate is not None and max_rate is not None and min_rate > max_rate:
            raise serializers.ValidationError({
                'max_rate': _("Maximum rate must be greater than minimum rate")
            })

        # Validate available_on date
        if available_on and available_on < timezone.now().date():
            raise serializers.ValidationError({
                'available_on': _("Available date cannot be in the past")
            })

        return data


class PsychologistVerificationSerializer(serializers.ModelSerializer):
    """
    Serializer for admin verification workflow
    """
    class Meta:
        model = Psychologist
        fields = [
            'user', 'full_name', 'display_name', 'license_number',
            'license_issuing_authority', 'license_expiry_date',
            'years_of_experience', 'verification_status', 'admin_notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'user', 'full_name', 'display_name', 'license_number',
            'license_issuing_authority', 'license_expiry_date',
            'years_of_experience', 'created_at', 'updated_at'
        ]

    def validate_verification_status(self, value):
        """Validate verification status transitions"""
        instance = getattr(self, 'instance', None)
        if instance:
            current_status = instance.verification_status

            # Business rule: Once approved, cannot be set back to pending
            if current_status == 'Approved' and value == 'Pending':
                raise serializers.ValidationError(
                    _("Cannot change status from Approved back to Pending")
                )

        return value

    def validate(self, data):
        """Validate admin notes are provided for rejection"""
        verification_status = data.get('verification_status')
        admin_notes = data.get('admin_notes', '').strip()

        if verification_status == 'Rejected' and not admin_notes:
            raise serializers.ValidationError({
                'admin_notes': _("Admin notes are required when rejecting a psychologist")
            })

        return data


class AvailabilityBulkSerializer(serializers.Serializer):
    """
    Serializer for bulk availability operations
    """
    operation = serializers.ChoiceField(
        choices=[
            ('create', _('Create multiple slots')),
            ('update', _('Update multiple slots')),
            ('delete', _('Delete multiple slots')),
        ],
        help_text=_("Type of bulk operation to perform")
    )

    availability_slots = serializers.ListField(
        child=AvailabilityCreateUpdateSerializer(),
        min_length=1,
        max_length=50,  # Reasonable limit for bulk operations
        allow_empty=True,  # Still needs validation in `validate`
        required=False,  # ✅ Add this line to make it optional
        help_text=_("List of availability slots to process")
    )

    # For delete operations
    slot_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text=_("List of availability slot IDs to delete (for delete operation)")
    )

    def validate(self, data):
        """Validate bulk operation data"""
        operation = data.get('operation')
        availability_slots = data.get('availability_slots', [])
        slot_ids = data.get('slot_ids', [])

        if operation == 'delete':
            if not slot_ids:
                raise serializers.ValidationError({
                    'slot_ids': _("Slot IDs are required for delete operation")
                })
            if availability_slots:
                raise serializers.ValidationError({
                    'availability_slots': _("Availability slots should not be provided for delete operation")
                })
        elif operation in ['create', 'update']:
            if not availability_slots:
                raise serializers.ValidationError({
                    'availability_slots': _("Availability slots are required for create/update operations")
                })

        return data

    def validate_availability_slots(self, value):
        """Additional validation for bulk slots"""
        if len(value) > 50:
            raise serializers.ValidationError(_("Cannot process more than 50 slots at once"))

        # Check for duplicate time slots in the same request
        seen_slots = set()
        for slot_data in value:
            day_of_week = slot_data.get('day_of_week')
            start_time = slot_data.get('start_time')
            end_time = slot_data.get('end_time')
            specific_date = slot_data.get('specific_date')

            slot_key = (day_of_week, start_time, end_time, specific_date)
            if slot_key in seen_slots:
                raise serializers.ValidationError(_("Duplicate time slots detected in request"))
            seen_slots.add(slot_key)

        return value