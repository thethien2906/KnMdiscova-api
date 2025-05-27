# children/models.py
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from datetime import date, timedelta
from parents.models import Parent


class Child(models.Model):
    """
    Child profile model - stores information about children linked to parents
    """

    # Primary key
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique identifier for the child")
    )

    # Parent relationship
    parent = models.ForeignKey(
        Parent,
        on_delete=models.CASCADE,
        related_name='children',
        help_text=_("Parent this child belongs to")
    )

    # Required Demographics
    first_name = models.CharField(
        _('first name'),
        max_length=100,
        help_text=_("Child's first name")
    )
    date_of_birth = models.DateField(
        _('date of birth'),
        help_text=_("Child's date of birth")
    )

    # Optional Demographics
    last_name = models.CharField(
        _('last name'),
        max_length=100,
        blank=True,
        help_text=_("Child's last name")
    )
    nickname = models.CharField(
        _('nickname'),
        max_length=100,
        blank=True,
        help_text=_("Child's preferred nickname")
    )
    gender = models.CharField(
        _('gender'),
        max_length=50,
        blank=True,
        help_text=_("Child's gender identity")
    )
    profile_picture_url = models.URLField(
        _('profile picture'),
        max_length=512,
        blank=True,
        null=True,
        help_text=_("URL to child's profile picture")
    )

    # Physical Information (Optional)
    height_cm = models.PositiveIntegerField(
        _('height (cm)'),
        blank=True,
        null=True,
        validators=[
            MinValueValidator(50, message=_("Height must be at least 50cm")),
            MaxValueValidator(250, message=_("Height must be less than 250cm"))
        ],
        help_text=_("Child's height in centimeters")
    )
    weight_kg = models.PositiveIntegerField(
        _('weight (kg)'),
        blank=True,
        null=True,
        validators=[
            MinValueValidator(10, message=_("Weight must be at least 10kg")),
            MaxValueValidator(200, message=_("Weight must be less than 200kg"))
        ],
        help_text=_("Child's weight in kilograms")
    )

    # Health Information (Optional)
    health_status = models.CharField(
        _('health status'),
        max_length=255,
        blank=True,
        help_text=_("General health status or concerns")
    )
    medical_history = models.TextField(
        _('medical history'),
        blank=True,
        help_text=_("Relevant medical history")
    )
    vaccination_status = models.BooleanField(
        _('vaccination up to date'),
        null=True,
        blank=True,
        help_text=_("Whether child's vaccinations are current")
    )

    # Behavioral & Developmental Information (Optional)
    emotional_issues = models.TextField(
        _('emotional issues'),
        blank=True,
        help_text=_("Any emotional concerns or challenges")
    )
    social_behavior = models.TextField(
        _('social behavior'),
        blank=True,
        help_text=_("Observations about social interactions")
    )
    developmental_concerns = models.TextField(
        _('developmental concerns'),
        blank=True,
        help_text=_("Any developmental concerns or delays")
    )
    family_peer_relationship = models.TextField(
        _('family and peer relationships'),
        blank=True,
        help_text=_("How child relates to family and peers")
    )

    # Previous Psychology Experience
    has_seen_psychologist = models.BooleanField(
        _('has seen psychologist'),
        default=False,
        help_text=_("Whether child has previously seen a psychologist")
    )
    has_received_therapy = models.BooleanField(
        _('has received therapy'),
        default=False,
        help_text=_("Whether child has received therapy services")
    )

    # Parental Input (Optional)
    parental_goals = models.TextField(
        _('parental goals'),
        blank=True,
        help_text=_("Parent's goals for the child's development")
    )
    activity_tips = models.TextField(
        _('activity tips'),
        blank=True,
        help_text=_("Suggested activities or interventions")
    )
    parental_notes = models.TextField(
        _('parental notes'),
        blank=True,
        help_text=_("Additional notes from parent")
    )

    # Educational Information (Optional)
    primary_language = models.CharField(
        _('primary language'),
        max_length=50,
        blank=True,
        help_text=_("Child's primary language")
    )
    school_grade_level = models.CharField(
        _('school grade level'),
        max_length=50,
        blank=True,
        help_text=_("Current grade level (international system)")
    )

    # Consent Management (Optional)
    consent_forms_signed = models.JSONField(
        _('consent forms signed'),
        default=dict,
        blank=True,
        help_text=_("Record of signed consent forms")
    )

    # Timestamps
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('updated at'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Child')
        verbose_name_plural = _('Children')
        db_table = 'children'
        indexes = [
            models.Index(fields=['parent']),
            models.Index(fields=['first_name', 'last_name']),
            models.Index(fields=['date_of_birth']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['first_name', 'last_name']

    def __str__(self):
        if self.last_name:
            return f"{self.first_name} {self.last_name} (Age {self.age})"
        return f"{self.first_name} (Age {self.age})"

    def clean(self):
        """Model validation"""
        from django.core.exceptions import ValidationError

        errors = {}

        # Validate age range (5-17 years for school-aged/adolescents)
        if self.date_of_birth:
            age = self.age
            if age < 5:
                errors['date_of_birth'] = _("Child must be at least 5 years old")
            elif age > 17:
                errors['date_of_birth'] = _("Child must be 17 years old or younger")

        # Validate height/weight relationship if both provided
        if self.height_cm and self.weight_kg:
            # Basic BMI validation for children (very loose bounds)
            bmi = self.weight_kg / ((self.height_cm / 100) ** 2)
            if bmi < 10 or bmi > 40:
                errors['weight_kg'] = _("Height and weight combination seems unusual")

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def age(self):
        """Calculate child's current age in years"""
        if not self.date_of_birth:
            return None

        today = date.today()
        age = today.year - self.date_of_birth.year

        # Adjust if birthday hasn't occurred this year
        if today.month < self.date_of_birth.month or \
           (today.month == self.date_of_birth.month and today.day < self.date_of_birth.day):
            age -= 1

        return age

    @property
    def age_in_months(self):
        """Calculate child's age in months for more precise tracking"""
        if not self.date_of_birth:
            return None

        today = date.today()
        months = (today.year - self.date_of_birth.year) * 12
        months += today.month - self.date_of_birth.month

        # Adjust for day of month
        if today.day < self.date_of_birth.day:
            months -= 1

        return max(0, months)

    @property
    def full_name(self):
        """Return child's full name"""
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name

    @property
    def display_name(self):
        """Return preferred display name (nickname or first name)"""
        return self.nickname if self.nickname else self.first_name

    @property
    def bmi(self):
        """Calculate BMI if height and weight are available"""
        if not (self.height_cm and self.weight_kg):
            return None

        height_m = self.height_cm / 100
        return round(self.weight_kg / (height_m ** 2), 1)

    @property
    def is_vaccination_current(self):
        """Return vaccination status with fallback"""
        return self.vaccination_status if self.vaccination_status is not None else False

    @property
    def has_psychology_history(self):
        """Check if child has any psychology/therapy history"""
        return self.has_seen_psychologist or self.has_received_therapy

    def get_consent_status(self, consent_type):
        """Get consent status for a specific type"""
        if not self.consent_forms_signed:
            return False

        consent_data = self.consent_forms_signed.get(consent_type, {})
        return consent_data.get('granted', False)

    def set_consent(self, consent_type, granted, parent_signature=None, notes=None):
        """Set consent for a specific type"""
        if not isinstance(self.consent_forms_signed, dict):
            self.consent_forms_signed = {}

        self.consent_forms_signed[consent_type] = {
            'granted': granted,
            'date_signed': timezone.now().isoformat() if granted else None,
            'parent_signature': parent_signature if granted else None,
            'notes': notes,
            'version': '1.0'  # For future consent form versioning
        }

        # Save the changes
        self.save(update_fields=['consent_forms_signed', 'updated_at'])

    @classmethod
    def get_default_consent_types(cls):
        """Return default consent form types"""
        return {
            'service_consent': _('General psychological services'),
            'assessment_consent': _('Psychological testing and evaluation'),
            'communication_consent': _('Communication with other providers'),
            'data_sharing_consent': _('Sharing of assessment results')
        }

    def get_profile_completeness(self):
        """Calculate profile completeness percentage"""
        # Required fields (always count as needed)
        required_fields = ['first_name', 'date_of_birth']

        # Important optional fields for completeness
        important_fields = [
            'last_name', 'gender', 'primary_language', 'school_grade_level',
            'health_status', 'parental_goals'
        ]

        # Count completed fields
        completed_required = sum(1 for field in required_fields
                               if getattr(self, field, None))

        completed_important = sum(1 for field in important_fields
                                if getattr(self, field, None) and
                                str(getattr(self, field, '')).strip())

        # Calculate percentage (required fields weighted more heavily)
        required_score = (completed_required / len(required_fields)) * 60
        important_score = (completed_important / len(important_fields)) * 40

        return round(required_score + important_score, 1)

    def get_age_appropriate_grade_suggestions(self):
        """Suggest appropriate grade levels based on age"""
        age = self.age
        if not age:
            return []

        # International grade suggestions (flexible)
        grade_mapping = {
            5: ['Kindergarten', 'Reception', 'Year 1'],
            6: ['Grade 1', 'Year 1', 'Year 2'],
            7: ['Grade 2', 'Year 2', 'Year 3'],
            8: ['Grade 3', 'Year 3', 'Year 4'],
            9: ['Grade 4', 'Year 4', 'Year 5'],
            10: ['Grade 5', 'Year 5', 'Year 6'],
            11: ['Grade 6', 'Year 6', 'Year 7'],
            12: ['Grade 7', 'Year 7', 'Year 8'],
            13: ['Grade 8', 'Year 8', 'Year 9'],
            14: ['Grade 9', 'Year 9', 'Year 10'],
            15: ['Grade 10', 'Year 10', 'Year 11'],
            16: ['Grade 11', 'Year 11', 'Year 12'],
            17: ['Grade 12', 'Year 12', 'Year 13']
        }

        return grade_mapping.get(age, [])