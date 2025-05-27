# children/serializers.py
from rest_framework import serializers
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import date, timedelta
from django.core.exceptions import ValidationError

from .models import Child
from parents.models import Parent
from parents.serializers import ParentSummarySerializer


class ChildSerializer(serializers.ModelSerializer):
    """
    Basic serializer for Child model
    """
    # Read-only computed fields
    age = serializers.IntegerField(read_only=True)
    age_in_months = serializers.IntegerField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    bmi = serializers.FloatField(read_only=True)
    has_psychology_history = serializers.BooleanField(read_only=True)
    is_vaccination_current = serializers.BooleanField(read_only=True)

    # Parent email for reference (read-only)
    parent_email = serializers.EmailField(source='parent.user.email', read_only=True)

    class Meta:
        model = Child
        fields = [
            # Identity
            'id',
            'parent',
            'parent_email',

            # Demographics
            'first_name',
            'last_name',
            'nickname',
            'date_of_birth',
            'gender',
            'profile_picture_url',

            # Physical info
            'height_cm',
            'weight_kg',

            # Health info
            'health_status',
            'medical_history',
            'vaccination_status',

            # Behavioral info
            'emotional_issues',
            'social_behavior',
            'developmental_concerns',
            'family_peer_relationship',

            # Psychology history
            'has_seen_psychologist',
            'has_received_therapy',

            # Parental input
            'parental_goals',
            'activity_tips',
            'parental_notes',

            # Educational info
            'primary_language',
            'school_grade_level',

            # Consent
            'consent_forms_signed',

            # Computed fields
            'age',
            'age_in_months',
            'full_name',
            'display_name',
            'bmi',
            'has_psychology_history',
            'is_vaccination_current',

            # Timestamps
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'parent_email',
            'age',
            'age_in_months',
            'full_name',
            'display_name',
            'bmi',
            'has_psychology_history',
            'is_vaccination_current',
            'created_at',
            'updated_at',
        ]

    def validate_date_of_birth(self, value):
        """
        Validate date of birth for age requirements
        """
        if not value:
            raise serializers.ValidationError(_("Date of birth is required"))

        today = date.today()
        age = today.year - value.year

        # Adjust if birthday hasn't occurred this year
        if today.month < value.month or (today.month == value.month and today.day < value.day):
            age -= 1

        # Age validation (5-17 years)
        if age < 5:
            raise serializers.ValidationError(_("Child must be at least 5 years old"))
        elif age > 17:
            raise serializers.ValidationError(_("Child must be 17 years old or younger"))

        # Date cannot be in the future
        if value > today:
            raise serializers.ValidationError(_("Date of birth cannot be in the future"))

        return value

    def validate_height_cm(self, value):
        """Validate height is within reasonable bounds"""
        if value is not None:
            if value < 50:
                raise serializers.ValidationError(_("Height must be at least 50cm"))
            elif value > 250:
                raise serializers.ValidationError(_("Height must be less than 250cm"))
        return value

    def validate_weight_kg(self, value):
        """Validate weight is within reasonable bounds"""
        if value is not None:
            if value < 10:
                raise serializers.ValidationError(_("Weight must be at least 10kg"))
            elif value > 200:
                raise serializers.ValidationError(_("Weight must be less than 200kg"))
        return value

    def validate_consent_forms_signed(self, value):
        """
        Validate consent forms structure
        """
        if value is None:
            return {}

        if not isinstance(value, dict):
            raise serializers.ValidationError(_("Consent forms must be a dictionary"))

        # Validate each consent entry
        valid_consent_types = Child.get_default_consent_types().keys()

        for consent_type, consent_data in value.items():
            if consent_type not in valid_consent_types:
                raise serializers.ValidationError(
                    _(f"Invalid consent type: {consent_type}")
                )

            if not isinstance(consent_data, dict):
                raise serializers.ValidationError(
                    _(f"Consent data for {consent_type} must be a dictionary")
                )

            # Validate required fields in consent data
            if 'granted' not in consent_data:
                raise serializers.ValidationError(
                    _(f"Consent {consent_type} must include 'granted' field")
                )

            if not isinstance(consent_data['granted'], bool):
                raise serializers.ValidationError(
                    _(f"Consent {consent_type} 'granted' must be boolean")
                )

        return value

    def validate(self, attrs):
        """
        Cross-field validation
        """
        # Validate height/weight relationship if both provided
        height_cm = attrs.get('height_cm')
        weight_kg = attrs.get('weight_kg')

        if height_cm and weight_kg:
            # Basic BMI validation for children
            bmi = weight_kg / ((height_cm / 100) ** 2)
            if bmi < 10 or bmi > 40:
                raise serializers.ValidationError({
                    'weight_kg': _("Height and weight combination seems unusual")
                })

        return attrs


class ChildCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new child profiles
    """
    parent = serializers.PrimaryKeyRelatedField(read_only=True)  # Will be set in view

    class Meta:
        model = Child
        fields = [
            # Required fields
            'parent',
            'first_name',
            'date_of_birth',

            # Optional demographics
            'last_name',
            'nickname',
            'gender',
            'profile_picture_url',

            # Optional physical info
            'height_cm',
            'weight_kg',

            # Optional health info
            'health_status',
            'medical_history',
            'vaccination_status',

            # Optional behavioral info
            'emotional_issues',
            'social_behavior',
            'developmental_concerns',
            'family_peer_relationship',

            # Psychology history
            'has_seen_psychologist',
            'has_received_therapy',

            # Parental input
            'parental_goals',
            'activity_tips',
            'parental_notes',

            # Educational info
            'primary_language',
            'school_grade_level',

            # Consent (optional at creation)
            'consent_forms_signed',
        ]

    def validate_date_of_birth(self, value):
        """Validate date of birth"""
        if not value:
            raise serializers.ValidationError(_("Date of birth is required"))

        today = date.today()
        age = today.year - value.year

        if today.month < value.month or (today.month == value.month and today.day < value.day):
            age -= 1

        if age < 5:
            raise serializers.ValidationError(_("Child must be at least 5 years old"))
        elif age > 17:
            raise serializers.ValidationError(_("Child must be 17 years old or younger"))

        if value > today:
            raise serializers.ValidationError(_("Date of birth cannot be in the future"))

        return value

    def validate_first_name(self, value):
        """Validate first name is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError(_("First name is required"))
        return value.strip()

    def validate_last_name(self, value):
        """Validate last name if provided"""
        if value is not None:
            return value.strip()
        return value

    def validate_nickname(self, value):
        """Validate nickname if provided"""
        if value is not None:
            return value.strip()
        return value

    def create(self, validated_data):
        """
        Create child - parent will be set by the service layer
        """
        # The parent assignment will be handled by the service layer
        return super().create(validated_data)


class ChildUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating child profiles (excludes parent relationship)
    """

    class Meta:
        model = Child
        fields = [
            # Demographics (excluding parent)
            'first_name',
            'last_name',
            'nickname',
            'date_of_birth',
            'gender',
            'profile_picture_url',

            # Physical info
            'height_cm',
            'weight_kg',

            # Health info
            'health_status',
            'medical_history',
            'vaccination_status',

            # Behavioral info
            'emotional_issues',
            'social_behavior',
            'developmental_concerns',
            'family_peer_relationship',

            # Psychology history
            'has_seen_psychologist',
            'has_received_therapy',

            # Parental input
            'parental_goals',
            'activity_tips',
            'parental_notes',

            # Educational info
            'primary_language',
            'school_grade_level',

            # Consent
            'consent_forms_signed',
        ]

    def validate_date_of_birth(self, value):
        """Validate date of birth"""
        if value:
            today = date.today()
            age = today.year - value.year

            if today.month < value.month or (today.month == value.month and today.day < value.day):
                age -= 1

            if age < 5:
                raise serializers.ValidationError(_("Child must be at least 5 years old"))
            elif age > 17:
                raise serializers.ValidationError(_("Child must be 17 years old or younger"))

            if value > today:
                raise serializers.ValidationError(_("Date of birth cannot be in the future"))

        return value

    def validate_first_name(self, value):
        """Validate first name"""
        if value is not None and (not value or not value.strip()):
            raise serializers.ValidationError(_("First name cannot be empty"))
        return value.strip() if value else value

    def validate(self, attrs):
        """Cross-field validation for updates"""
        # Height/weight validation
        height_cm = attrs.get('height_cm')
        weight_kg = attrs.get('weight_kg')

        # Get current values if not in update data
        if self.instance:
            height_cm = height_cm if height_cm is not None else self.instance.height_cm
            weight_kg = weight_kg if weight_kg is not None else self.instance.weight_kg

        if height_cm and weight_kg:
            bmi = weight_kg / ((height_cm / 100) ** 2)
            if bmi < 10 or bmi > 40:
                raise serializers.ValidationError({
                    'weight_kg': _("Height and weight combination seems unusual")
                })

        return attrs


class ChildDetailSerializer(ChildSerializer):
    """
    Extended serializer for detailed child information
    """
    # Include parent information
    parent = ParentSummarySerializer(read_only=True)

    # Additional computed fields
    profile_completeness = serializers.SerializerMethodField()
    age_appropriate_grades = serializers.SerializerMethodField()
    consent_summary = serializers.SerializerMethodField()

    class Meta(ChildSerializer.Meta):
        fields = ChildSerializer.Meta.fields + [
            'profile_completeness',
            'age_appropriate_grades',
            'consent_summary',
        ]

    def get_profile_completeness(self, obj):
        """Get profile completeness percentage"""
        return obj.get_profile_completeness()

    def get_age_appropriate_grades(self, obj):
        """Get age-appropriate grade suggestions"""
        return obj.get_age_appropriate_grade_suggestions()

    def get_consent_summary(self, obj):
        """Get consent status summary"""
        consent_types = Child.get_default_consent_types()
        summary = {}

        for consent_type, description in consent_types.items():
            status = obj.get_consent_status(consent_type)
            summary[consent_type] = {
                'description': description,
                'granted': status,
                'details': obj.consent_forms_signed.get(consent_type, {}) if obj.consent_forms_signed else {}
            }

        return summary


class ChildSummarySerializer(serializers.ModelSerializer):
    """
    Minimal serializer for child summary (for listings, selections, etc.)
    """
    full_name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    age = serializers.IntegerField(read_only=True)
    parent_email = serializers.EmailField(source='parent.user.email', read_only=True)

    class Meta:
        model = Child
        fields = [
            'id',
            'parent',
            'parent_email',
            'first_name',
            'last_name',
            'nickname',
            'full_name',
            'display_name',
            'date_of_birth',
            'age',
            'gender',
            'profile_picture_url',
            'school_grade_level',
        ]
        read_only_fields = [
            'id',
            'parent',
            'parent_email',
            'full_name',
            'display_name',
            'age',
        ]


class ConsentManagementSerializer(serializers.Serializer):
    """
    Dedicated serializer for managing consent forms
    """
    consent_type = serializers.ChoiceField(
        choices=[],  # Will be populated in __init__
        help_text=_("Type of consent being granted/revoked")
    )
    granted = serializers.BooleanField(
        help_text=_("Whether consent is granted")
    )
    parent_signature = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        help_text=_("Parent's digital signature or confirmation")
    )
    notes = serializers.CharField(
        max_length=1000,
        required=False,
        allow_blank=True,
        help_text=_("Additional notes about the consent")
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate consent type choices
        consent_types = Child.get_default_consent_types()
        self.fields['consent_type'].choices = [
            (key, value) for key, value in consent_types.items()
        ]

    def validate(self, attrs):
        """Validate consent data"""
        granted = attrs.get('granted')
        parent_signature = attrs.get('parent_signature')

        # If granting consent, signature is recommended
        if granted and not parent_signature:
            # This is a warning, not an error - allow but log
            pass

        return attrs

    def save(self, child_instance):
        """
        Save consent to child instance
        """
        consent_type = self.validated_data['consent_type']
        granted = self.validated_data['granted']
        parent_signature = self.validated_data.get('parent_signature')
        notes = self.validated_data.get('notes')

        # Use the model method to set consent
        child_instance.set_consent(
            consent_type=consent_type,
            granted=granted,
            parent_signature=parent_signature,
            notes=notes
        )

        return child_instance


class ChildSearchSerializer(serializers.Serializer):
    """
    Serializer for child search/filtering
    """
    first_name = serializers.CharField(max_length=100, required=False)
    last_name = serializers.CharField(max_length=100, required=False)
    parent_email = serializers.EmailField(required=False)
    age_min = serializers.IntegerField(min_value=5, max_value=17, required=False)
    age_max = serializers.IntegerField(min_value=5, max_value=17, required=False)
    gender = serializers.CharField(max_length=50, required=False)
    school_grade_level = serializers.CharField(max_length=50, required=False)
    has_psychology_history = serializers.BooleanField(required=False)
    created_after = serializers.DateTimeField(required=False)
    created_before = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        """Validate search parameters"""
        age_min = attrs.get('age_min')
        age_max = attrs.get('age_max')
        created_after = attrs.get('created_after')
        created_before = attrs.get('created_before')

        # Validate age range
        if age_min and age_max and age_min > age_max:
            raise serializers.ValidationError({
                'age_min': _("Minimum age must be less than or equal to maximum age")
            })

        # Validate date range
        if created_after and created_before and created_after > created_before:
            raise serializers.ValidationError({
                'created_after': _("Start date must be before end date")
            })

        return attrs


class BulkConsentSerializer(serializers.Serializer):
    """
    Serializer for bulk consent operations
    """
    consent_types = serializers.ListField(
        child=serializers.ChoiceField(choices=[]),  # Will be populated in __init__
        allow_empty=False,
        help_text=_("List of consent types to update")
    )
    granted = serializers.BooleanField(
        help_text=_("Whether to grant or revoke all specified consents")
    )
    parent_signature = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        help_text=_("Parent's digital signature")
    )
    notes = serializers.CharField(
        max_length=1000,
        required=False,
        allow_blank=True,
        help_text=_("Notes for all consent updates")
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate consent type choices
        consent_types = Child.get_default_consent_types()
        choices = [(key, value) for key, value in consent_types.items()]
        self.fields['consent_types'].child.choices = choices

    def save(self, child_instance):
        """
        Apply bulk consent updates to child instance
        """
        consent_types = self.validated_data['consent_types']
        granted = self.validated_data['granted']
        parent_signature = self.validated_data.get('parent_signature')
        notes = self.validated_data.get('notes')

        # Apply each consent
        for consent_type in consent_types:
            child_instance.set_consent(
                consent_type=consent_type,
                granted=granted,
                parent_signature=parent_signature,
                notes=notes
            )

        return child_instance