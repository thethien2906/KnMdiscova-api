# psychologists/serializers.py
from rest_framework import serializers
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import date, time, datetime
from django.core.exceptions import ValidationError

from .models import Psychologist, PsychologistAvailability
from users.models import User
from users.serializers import UserSerializer


class PsychologistSerializer(serializers.ModelSerializer):
    """
    Basic serializer for Psychologist model - for general read operations
    """
    # Read-only fields from related User model
    email = serializers.EmailField(source='user.email', read_only=True)
    user_type = serializers.CharField(source='user.user_type', read_only=True)
    is_user_verified = serializers.BooleanField(source='user.is_verified', read_only=True)
    is_user_active = serializers.BooleanField(source='user.is_active', read_only=True)

    # Computed fields
    full_name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    is_verified = serializers.BooleanField(read_only=True)
    is_marketplace_visible = serializers.BooleanField(read_only=True)
    license_is_valid = serializers.BooleanField(read_only=True)
    services_offered = serializers.ListField(read_only=True)

    class Meta:
        model = Psychologist
        fields = [
            # User-related fields (read-only)
            'email',
            'user_type',
            'is_user_verified',
            'is_user_active',

            # Basic profile fields
            'first_name',
            'last_name',
            'license_number',
            'license_issuing_authority',
            'license_expiry_date',
            'years_of_experience',

            # Professional profile
            'biography',
            'education',
            'certifications',

            # Verification
            'verification_status',
            'admin_notes',

            # Service offerings
            'offers_initial_consultation',
            'offers_online_sessions',
            'office_address',

            # Professional URLs
            'website_url',
            'linkedin_url',

            # Pricing (MVP: Optional)
            'hourly_rate',
            'initial_consultation_rate',

            # Computed fields
            'full_name',
            'display_name',
            'is_verified',
            'is_marketplace_visible',
            'license_is_valid',
            'services_offered',

            # Timestamps
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'email',
            'user_type',
            'is_user_verified',
            'is_user_active',
            'full_name',
            'display_name',
            'is_verified',
            'is_marketplace_visible',
            'license_is_valid',
            'services_offered',
            'created_at',
            'updated_at',
        ]

    def validate_license_expiry_date(self, value):
        """Validate license expiry date is not in the past"""
        if value and value < date.today():
            raise serializers.ValidationError(_("License expiry date cannot be in the past"))
        return value

    def validate_years_of_experience(self, value):
        """Validate years of experience is reasonable"""
        if value is not None:
            if value < 0:
                raise serializers.ValidationError(_("Years of experience cannot be negative"))
            elif value > 60:
                raise serializers.ValidationError(_("Years of experience seems too high"))
        return value

    def validate_education(self, value):
        """Validate education structure"""
        if value is None:
            return []

        if not isinstance(value, list):
            raise serializers.ValidationError(_("Education must be a list of educational entries"))

        for i, edu in enumerate(value):
            if not isinstance(edu, dict):
                raise serializers.ValidationError(_(f"Education entry {i+1} must be a dictionary"))

            required_keys = ['degree', 'institution', 'year']
            for key in required_keys:
                if key not in edu or not edu[key]:
                    raise serializers.ValidationError(_(f"Education entry {i+1} missing required field: {key}"))

            # Validate year
            try:
                year = int(edu['year'])
                current_year = date.today().year
                if year < 1950 or year > current_year:
                    raise serializers.ValidationError(_(f"Education entry {i+1} has invalid year: {year}"))
            except (ValueError, TypeError):
                raise serializers.ValidationError(_(f"Education entry {i+1} year must be a number"))

        return value

    def validate_certifications(self, value):
        """Validate certifications structure"""
        if value is None:
            return []

        if not isinstance(value, list):
            raise serializers.ValidationError(_("Certifications must be a list of certification entries"))

        for i, cert in enumerate(value):
            if not isinstance(cert, dict):
                raise serializers.ValidationError(_(f"Certification entry {i+1} must be a dictionary"))

            required_keys = ['name', 'institution', 'year']
            for key in required_keys:
                if key not in cert or not cert[key]:
                    raise serializers.ValidationError(_(f"Certification entry {i+1} missing required field: {key}"))

            # Validate year
            try:
                year = int(cert['year'])
                current_year = date.today().year
                if year < 1950 or year > current_year:
                    raise serializers.ValidationError(_(f"Certification entry {i+1} has invalid year: {year}"))
            except (ValueError, TypeError):
                raise serializers.ValidationError(_(f"Certification entry {i+1} year must be a number"))

        return value

    def validate(self, attrs):
        """Cross-field validation"""
        # Business Rule: Office address required if offering initial consultations
        offers_initial_consultation = attrs.get('offers_initial_consultation')
        office_address = attrs.get('office_address')

        # For updates, get current values if not in attrs
        if self.instance:
            offers_initial_consultation = offers_initial_consultation if offers_initial_consultation is not None else self.instance.offers_initial_consultation
            office_address = office_address if office_address is not None else self.instance.office_address

        if offers_initial_consultation and not office_address:
            raise serializers.ValidationError({
                'office_address': _("Office address is required when offering initial consultations")
            })

        # Business Rule: Must offer at least one service type
        offers_online_sessions = attrs.get('offers_online_sessions')
        if self.instance:
            offers_online_sessions = offers_online_sessions if offers_online_sessions is not None else self.instance.offers_online_sessions

        if not offers_initial_consultation and not offers_online_sessions:
            raise serializers.ValidationError({
                'offers_online_sessions': _("Must offer at least one service type (online sessions or initial consultations)")
            })

        return attrs


class PsychologistProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for psychologists to update their own profiles
    Excludes verification status and admin notes (only admins can edit these)
    """

    class Meta:
        model = Psychologist
        fields = [
            # Basic profile fields
            'first_name',
            'last_name',
            'license_number',
            'license_issuing_authority',
            'license_expiry_date',
            'years_of_experience',

            # Professional profile
            'biography',
            'education',
            'certifications',

            # Service offerings
            'offers_initial_consultation',
            'offers_online_sessions',
            'office_address',

            # Professional URLs
            'website_url',
            'linkedin_url',

            # Pricing (MVP: Optional)
            'hourly_rate',
            'initial_consultation_rate',
        ]

    def validate_license_number(self, value):
        """Validate license number uniqueness (excluding current instance)"""
        if value:
            queryset = Psychologist.objects.filter(license_number=value)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                raise serializers.ValidationError(_("A psychologist with this license number already exists"))
        return value

    def validate_license_expiry_date(self, value):
        """Validate license expiry date"""
        if value and value < date.today():
            raise serializers.ValidationError(_("License expiry date cannot be in the past"))
        return value

    def validate_years_of_experience(self, value):
        """Validate years of experience"""
        if value is not None:
            if value < 0:
                raise serializers.ValidationError(_("Years of experience cannot be negative"))
            elif value > 60:
                raise serializers.ValidationError(_("Years of experience seems too high"))
        return value

    def validate_first_name(self, value):
        """Validate first name is not empty"""
        if value is not None and not value.strip():
            raise serializers.ValidationError(_("First name cannot be empty"))
        return value.strip() if value else value

    def validate_last_name(self, value):
        """Validate last name is not empty"""
        if value is not None and not value.strip():
            raise serializers.ValidationError(_("Last name cannot be empty"))
        return value.strip() if value else value

    def validate_hourly_rate(self, value):
        """Validate hourly rate"""
        if value is not None and value < 0:
            raise serializers.ValidationError(_("Hourly rate cannot be negative"))
        return value

    def validate_initial_consultation_rate(self, value):
        """Validate initial consultation rate"""
        if value is not None and value < 0:
            raise serializers.ValidationError(_("Initial consultation rate cannot be negative"))
        return value

    def validate_education(self, value):
        """Validate education structure"""
        if value is None:
            return []

        if not isinstance(value, list):
            raise serializers.ValidationError(_("Education must be a list"))

        for i, edu in enumerate(value):
            if not isinstance(edu, dict):
                raise serializers.ValidationError(_(f"Education entry {i+1} must be a dictionary"))

            required_keys = ['degree', 'institution', 'year']
            for key in required_keys:
                if key not in edu or not str(edu[key]).strip():
                    raise serializers.ValidationError(_(f"Education entry {i+1} missing required field: {key}"))

        return value

    def validate_certifications(self, value):
        """Validate certifications structure"""
        if value is None:
            return []

        if not isinstance(value, list):
            raise serializers.ValidationError(_("Certifications must be a list"))

        for i, cert in enumerate(value):
            if not isinstance(cert, dict):
                raise serializers.ValidationError(_(f"Certification entry {i+1} must be a dictionary"))

            required_keys = ['name', 'institution', 'year']
            for key in required_keys:
                if key not in cert or not str(cert[key]).strip():
                    raise serializers.ValidationError(_(f"Certification entry {i+1} missing required field: {key}"))

        return value

    def validate(self, attrs):
        """Cross-field validation for profile updates"""
        # Business rule validation
        offers_initial_consultation = attrs.get('offers_initial_consultation')
        office_address = attrs.get('office_address')

        # Get current values if not in update data
        if self.instance:
            offers_initial_consultation = offers_initial_consultation if offers_initial_consultation is not None else self.instance.offers_initial_consultation
            office_address = office_address if office_address is not None else self.instance.office_address

        if offers_initial_consultation and not office_address:
            raise serializers.ValidationError({
                'office_address': _("Office address is required when offering initial consultations")
            })

        # Must offer at least one service
        offers_online_sessions = attrs.get('offers_online_sessions')
        if self.instance:
            offers_online_sessions = offers_online_sessions if offers_online_sessions is not None else self.instance.offers_online_sessions

        if not offers_initial_consultation and not offers_online_sessions:
            raise serializers.ValidationError({
                'offers_online_sessions': _("Must offer at least one service type")
            })

        return attrs


class PsychologistMarketplaceSerializer(serializers.ModelSerializer):
    """
    Public-facing serializer for marketplace display
    Only includes public information, filters sensitive data
    """
    full_name = serializers.CharField(read_only=True)
    services_offered = serializers.ListField(read_only=True)
    profile_completeness = serializers.SerializerMethodField()

    class Meta:
        model = Psychologist
        fields = [
            # Basic public information
            'user',  # For linking/identification
            'full_name',
            'years_of_experience',
            'biography',

            # Service information
            'offers_initial_consultation',
            'offers_online_sessions',
            'services_offered',

            # Location (for initial consultations)
            'office_address',

            # Professional URLs (public)
            'website_url',
            'linkedin_url',

            # Pricing (MVP: Optional but public when available)
            'hourly_rate',
            'initial_consultation_rate',

            # Profile quality indicator
            'profile_completeness',

            # Public credentials (no sensitive details)
            'license_issuing_authority',
            'education',
            'certifications',

            # Registration date (helps with credibility)
            'created_at',
        ]
        read_only_fields = [
            'user',
            'full_name',
            'services_offered',
            'profile_completeness',
            'created_at',
        ]

    def get_profile_completeness(self, obj):
        """Get profile completeness percentage"""
        return obj.get_profile_completeness()

    def to_representation(self, instance):
        """Filter to only show approved, marketplace-visible psychologists"""
        if not instance.is_marketplace_visible:
            return {}
        return super().to_representation(instance)


class PsychologistDetailSerializer(PsychologistSerializer):
    """
    Extended serializer for detailed psychologist information
    Includes comprehensive profile with computed fields
    """
    # Include user information
    user = UserSerializer(read_only=True)

    # Additional computed fields
    profile_completeness = serializers.SerializerMethodField()
    verification_requirements = serializers.SerializerMethodField()
    can_book_appointments = serializers.SerializerMethodField()

    class Meta(PsychologistSerializer.Meta):
        fields = PsychologistSerializer.Meta.fields + [
            'user',
            'profile_completeness',
            'verification_requirements',
            'can_book_appointments',
        ]

    def get_profile_completeness(self, obj):
        """Get profile completeness percentage"""
        return obj.get_profile_completeness()

    def get_verification_requirements(self, obj):
        """Get list of verification requirements"""
        return obj.get_verification_requirements()

    def get_can_book_appointments(self, obj):
        """Check if psychologist can receive bookings"""
        return obj.can_book_appointments()


class PsychologistVerificationSerializer(serializers.ModelSerializer):
    """
    Admin-only serializer for verification workflow
    Handles verification status changes and admin notes
    """

    class Meta:
        model = Psychologist
        fields = [
            # Basic identification
            'user',
            'full_name',
            'email',

            # Verification fields (admin-editable)
            'verification_status',
            'admin_notes',

            # License validation info
            'license_number',
            'license_issuing_authority',
            'license_expiry_date',
            'license_is_valid',

            # Service offerings for validation
            'offers_initial_consultation',
            'offers_online_sessions',
            'office_address',

            # Profile completeness for admin review
            'profile_completeness',
            'verification_requirements',

            # Timestamps
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'user',
            'full_name',
            'email',
            'license_is_valid',
            'profile_completeness',
            'verification_requirements',
            'created_at',
            'updated_at',
        ]

    def validate_verification_status(self, value):
        """Validate verification status changes"""
        if value not in ['Pending', 'Approved', 'Rejected']:
            raise serializers.ValidationError(_("Invalid verification status"))
        return value

    def validate(self, attrs):
        """Cross-field validation for verification"""
        verification_status = attrs.get('verification_status')

        # If approving, ensure all requirements are met
        if verification_status == 'Approved' and self.instance:
            requirements = self.instance.get_verification_requirements()
            if requirements:
                raise serializers.ValidationError({
                    'verification_status': _(f"Cannot approve: Missing requirements: {', '.join(requirements)}")
                })

        return attrs

    profile_completeness = serializers.SerializerMethodField()
    verification_requirements = serializers.SerializerMethodField()
    full_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    license_is_valid = serializers.BooleanField(read_only=True)

    def get_profile_completeness(self, obj):
        return obj.get_profile_completeness()

    def get_verification_requirements(self, obj):
        return obj.get_verification_requirements()


class PsychologistSearchSerializer(serializers.Serializer):
    """
    Serializer for search and filtering parameters
    """
    # Text search
    name = serializers.CharField(max_length=200, required=False)
    bio_keywords = serializers.CharField(max_length=500, required=False)

    # Service filters
    offers_online_sessions = serializers.BooleanField(required=False)
    offers_initial_consultation = serializers.BooleanField(required=False)

    # Experience filters
    min_years_experience = serializers.IntegerField(min_value=0, max_value=60, required=False)
    max_years_experience = serializers.IntegerField(min_value=0, max_value=60, required=False)

    # License filters
    license_authority = serializers.CharField(max_length=255, required=False)

    # Location filters (for initial consultations)
    location_keywords = serializers.CharField(max_length=500, required=False)

    # Verification filters
    verification_status = serializers.ChoiceField(
        choices=Psychologist.VERIFICATION_STATUS_CHOICES,
        required=False
    )

    # Pricing filters (MVP: Optional)
    min_hourly_rate = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    max_hourly_rate = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    min_consultation_rate = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    max_consultation_rate = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)

    # Date filters
    created_after = serializers.DateTimeField(required=False)
    created_before = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        """Validate search parameters"""
        # Validate experience range
        min_exp = attrs.get('min_years_experience')
        max_exp = attrs.get('max_years_experience')
        if min_exp and max_exp and min_exp > max_exp:
            raise serializers.ValidationError({
                'min_years_experience': _("Minimum experience must be less than maximum experience")
            })

        # Validate hourly rate range
        min_rate = attrs.get('min_hourly_rate')
        max_rate = attrs.get('max_hourly_rate')
        if min_rate and max_rate and min_rate > max_rate:
            raise serializers.ValidationError({
                'min_hourly_rate': _("Minimum hourly rate must be less than maximum hourly rate")
            })

        # Validate consultation rate range
        min_consult = attrs.get('min_consultation_rate')
        max_consult = attrs.get('max_consultation_rate')
        if min_consult and max_consult and min_consult > max_consult:
            raise serializers.ValidationError({
                'min_consultation_rate': _("Minimum consultation rate must be less than maximum consultation rate")
            })

        # Validate date range
        created_after = attrs.get('created_after')
        created_before = attrs.get('created_before')
        if created_after and created_before and created_after > created_before:
            raise serializers.ValidationError({
                'created_after': _("Start date must be before end date")
            })

        return attrs


class PsychologistAvailabilitySerializer(serializers.ModelSerializer):
    """
    Serializer for managing psychologist availability blocks
    """
    psychologist_name = serializers.CharField(source='psychologist.display_name', read_only=True)
    day_name = serializers.SerializerMethodField()
    time_range_display = serializers.CharField(source='get_time_range_display', read_only=True)
    display_date = serializers.CharField(source='get_display_date', read_only=True)
    duration_hours = serializers.FloatField(read_only=True)
    max_appointable_slots = serializers.IntegerField(read_only=True)

    class Meta:
        model = PsychologistAvailability
        fields = [
            'availability_id',
            'psychologist',
            'psychologist_name',

            # Time configuration
            'day_of_week',
            'day_name',
            'start_time',
            'end_time',
            'time_range_display',

            # Recurring vs specific
            'is_recurring',
            'specific_date',
            'display_date',

            # Computed fields
            'duration_hours',
            'max_appointable_slots',

            # Timestamps
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'availability_id',
            'psychologist_name',
            'day_name',
            'time_range_display',
            'display_date',
            'duration_hours',
            'max_appointable_slots',
            'created_at',
            'updated_at',
        ]

    def get_day_name(self, obj):
        """Get human-readable day name"""
        return obj.get_day_name()

    def validate_day_of_week(self, value):
        """Validate day of week is in valid range"""
        if value is not None and (value < 0 or value > 6):
            raise serializers.ValidationError(_("Day of week must be 0-6 (0=Sunday, 6=Saturday)"))
        return value

    def validate_start_time(self, value):
        """Validate start time format"""
        if not isinstance(value, time):
            raise serializers.ValidationError(_("Start time must be a valid time"))
        return value

    def validate_end_time(self, value):
        """Validate end time format"""
        if not isinstance(value, time):
            raise serializers.ValidationError(_("End time must be a valid time"))
        return value

    def validate_specific_date(self, value):
        """Validate specific date is not in the past"""
        if value and value < date.today():
            raise serializers.ValidationError(_("Specific date cannot be in the past"))
        return value

    def validate(self, attrs):
        """Cross-field validation"""
        start_time = attrs.get('start_time')
        end_time = attrs.get('end_time')
        is_recurring = attrs.get('is_recurring')
        specific_date = attrs.get('specific_date')

        # Get current values for updates
        if self.instance:
            start_time = start_time if start_time is not None else self.instance.start_time
            end_time = end_time if end_time is not None else self.instance.end_time
            is_recurring = is_recurring if is_recurring is not None else self.instance.is_recurring
            specific_date = specific_date if specific_date is not None else self.instance.specific_date

        # Validate time range
        if start_time and end_time:
            if end_time <= start_time:
                raise serializers.ValidationError({
                    'end_time': _("End time must be after start time")
                })

            # Validate minimum duration (1 hour)
            start_dt = datetime.combine(date.today(), start_time)
            end_dt = datetime.combine(date.today(), end_time)
            duration = end_dt - start_dt

            if duration.total_seconds() < 3600:  # 1 hour = 3600 seconds
                raise serializers.ValidationError({
                    'end_time': _("Availability block must be at least 1 hour long")
                })

        # Validate recurring vs specific date logic
        if is_recurring and specific_date:
            raise serializers.ValidationError({
                'specific_date': _("Recurring availability should not have a specific date")
            })
        elif is_recurring is False and not specific_date:
            raise serializers.ValidationError({
                'specific_date': _("Non-recurring availability must have a specific date")
            })

        return attrs


class PsychologistSummarySerializer(serializers.ModelSerializer):
    """
    Minimal serializer for psychologist summary (listings, selections, etc.)
    """
    full_name = serializers.CharField(read_only=True)
    services_offered = serializers.ListField(read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = Psychologist
        fields = [
            'user',
            'email',
            'full_name',
            'years_of_experience',
            'verification_status',
            'offers_initial_consultation',
            'offers_online_sessions',
            'services_offered',
            'office_address',
            'created_at',
        ]
        read_only_fields = [
            'user',
            'email',
            'full_name',
            'services_offered',
            'created_at',
        ]


class EducationEntrySerializer(serializers.Serializer):
    """
    Helper serializer for individual education entries
    """
    degree = serializers.CharField(max_length=200)
    institution = serializers.CharField(max_length=200)
    year = serializers.IntegerField(min_value=1950, max_value=date.today().year)
    field_of_study = serializers.CharField(max_length=200, required=False, allow_blank=True)
    honors = serializers.CharField(max_length=200, required=False, allow_blank=True)


class CertificationEntrySerializer(serializers.Serializer):
    """
    Helper serializer for individual certification entries
    """
    name = serializers.CharField(max_length=200)
    institution = serializers.CharField(max_length=200)
    year = serializers.IntegerField(min_value=1950, max_value=date.today().year)
    expiry_date = serializers.CharField(max_length=20, required=False, allow_blank=True)
    certification_id = serializers.CharField(max_length=100, required=False, allow_blank=True)


class PsychologistEducationSerializer(serializers.Serializer):
    """
    Dedicated serializer for managing education entries
    """
    education = EducationEntrySerializer(many=True)

    def validate_education(self, value):
        """Validate education entries"""
        if not isinstance(value, list):
            raise serializers.ValidationError(_("Education must be a list"))

        if len(value) == 0:
            raise serializers.ValidationError(_("At least one education entry is required"))

        return value

    def update(self, instance, validated_data):
        """Update psychologist's education"""
        if not isinstance(instance, Psychologist):
            raise serializers.ValidationError(_("Instance must be a Psychologist object"))

        instance.education = validated_data['education']
        instance.save(update_fields=['education', 'updated_at'])
        return instance


class PsychologistCertificationSerializer(serializers.Serializer):
    """
    Dedicated serializer for managing certification entries
    """
    certifications = CertificationEntrySerializer(many=True)

    def validate_certifications(self, value):
        """Validate certification entries"""
        if not isinstance(value, list):
            raise serializers.ValidationError(_("Certifications must be a list"))

        # Certifications are optional, so empty list is allowed
        return value

    def update(self, instance, validated_data):
        """Update psychologist's certifications"""
        if not isinstance(instance, Psychologist):
            raise serializers.ValidationError(_("Instance must be a Psychologist object"))

        instance.certifications = validated_data['certifications']
        instance.save(update_fields=['certifications', 'updated_at'])
        return instance