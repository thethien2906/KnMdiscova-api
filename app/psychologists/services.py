# psychologists/services.py
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from datetime import date, datetime, timedelta, time
import logging
from typing import Optional, Dict, Any, List, Tuple

from .models import Psychologist, PsychologistAvailability
from users.models import User
from users.services import EmailService

logger = logging.getLogger(__name__)


class PsychologistProfileError(Exception):
    """Base exception for psychologist profile related errors"""
    pass


class PsychologistNotFoundError(PsychologistProfileError):
    """Raised when psychologist profile is not found"""
    pass


class PsychologistAccessDeniedError(PsychologistProfileError):
    """Raised when user doesn't have access to psychologist profile"""
    pass


class PsychologistVerificationError(PsychologistProfileError):
    """Raised when psychologist verification fails"""
    pass


class AvailabilityManagementError(PsychologistProfileError):
    """Raised when availability management operations fail"""
    pass


class PsychologistService:
    """
    Service class for psychologist profile management and business logic
    """

    @staticmethod
    def get_psychologist_by_user(user: User) -> Optional[Psychologist]:
        """
        Get psychologist profile by user, return None if not found
        """
        try:
            return Psychologist.objects.select_related('user').get(user=user)
        except Psychologist.DoesNotExist:
            logger.warning(f"Psychologist profile not found for user {user.email}")
            return None

    @staticmethod
    def get_psychologist_by_user_or_raise(user: User) -> Psychologist:
        """
        Get psychologist profile by user, raise exception if not found
        """
        psychologist = PsychologistService.get_psychologist_by_user(user)
        if not psychologist:
            raise PsychologistNotFoundError(f"Psychologist profile not found for user {user.email}")
        return psychologist

    @staticmethod
    def get_psychologist_by_id(psychologist_id: str) -> Optional[Psychologist]:
        """
        Get psychologist by user ID
        """
        try:
            return Psychologist.objects.select_related('user').get(user__id=psychologist_id)
        except Psychologist.DoesNotExist:
            logger.warning(f"Psychologist {psychologist_id} not found")
            return None

    @staticmethod
    def create_psychologist_profile(user: User, profile_data: Dict[str, Any]) -> Psychologist:
        """
        Create a new psychologist profile after user registration
        This is called after email verification is complete
        """
        # Validate user is eligible to create psychologist profile
        if not user.is_psychologist:
            raise PsychologistProfileError("User is not registered as a psychologist")

        if not user.is_verified:
            raise PsychologistProfileError("Email must be verified before creating psychologist profile")

        if not user.is_active:
            raise PsychologistProfileError("User account must be active")

        # Check if profile already exists
        if PsychologistService.get_psychologist_by_user(user):
            raise PsychologistProfileError("Psychologist profile already exists for this user")

        try:
            with transaction.atomic():
                # Validate profile data according to business rules
                validated_data = PsychologistService.validate_psychologist_data(profile_data)

                # Create psychologist profile
                validated_data['user'] = user
                psychologist = Psychologist.objects.create(**validated_data)

                logger.info(f"Psychologist profile created: {psychologist.full_name} for user {user.email}")
                return psychologist

        except Exception as e:
            logger.error(f"Failed to create psychologist profile for user {user.email}: {str(e)}")
            raise PsychologistProfileError(f"Failed to create psychologist profile: {str(e)}")

    @staticmethod
    def update_psychologist_profile(psychologist: Psychologist, update_data: Dict[str, Any]) -> Psychologist:
        """
        Update psychologist profile with business logic validation
        """
        # Validate user is still active
        if not psychologist.user.is_active:
            raise PsychologistProfileError("User account is inactive")

        try:
            with transaction.atomic():
                # Validate update data
                validated_data = PsychologistService.validate_psychologist_data(update_data, is_update=True)

                # Update fields
                updated_fields = []
                allowed_fields = [
                    'first_name', 'last_name', 'license_number', 'license_issuing_authority',
                    'license_expiry_date', 'years_of_experience', 'biography', 'education',
                    'certifications', 'offers_initial_consultation', 'offers_online_sessions',
                    'office_address', 'website_url', 'linkedin_url', 'hourly_rate',
                    'initial_consultation_rate'
                ]

                for field, value in validated_data.items():
                    if field in allowed_fields and hasattr(psychologist, field):
                        setattr(psychologist, field, value)
                        updated_fields.append(field)

                if updated_fields:
                    updated_fields.append('updated_at')
                    psychologist.save(update_fields=updated_fields)
                    logger.info(f"Updated psychologist profile {psychologist.full_name}: {updated_fields}")

                return psychologist

        except Exception as e:
            logger.error(f"Failed to update psychologist profile {psychologist.user.email}: {str(e)}")
            raise PsychologistProfileError(f"Failed to update psychologist profile: {str(e)}")

    @staticmethod
    def get_psychologist_profile_data(psychologist: Psychologist) -> Dict[str, Any]:
        """
        Get comprehensive psychologist profile data
        """
        return {
            'user_id': str(psychologist.user.id),
            'email': psychologist.user.email,
            'user_type': psychologist.user.user_type,
            'is_user_verified': psychologist.user.is_verified,
            'is_user_active': psychologist.user.is_active,

            # Profile information
            'first_name': psychologist.first_name,
            'last_name': psychologist.last_name,
            'full_name': psychologist.full_name,
            'display_name': psychologist.display_name,

            # Professional credentials
            'license_number': psychologist.license_number,
            'license_issuing_authority': psychologist.license_issuing_authority,
            'license_expiry_date': psychologist.license_expiry_date,
            'years_of_experience': psychologist.years_of_experience,
            'license_is_valid': psychologist.license_is_valid,

            # Professional profile
            'biography': psychologist.biography,
            'education': psychologist.education,
            'certifications': psychologist.certifications,

            # Verification
            'verification_status': psychologist.verification_status,
            'is_verified': psychologist.is_verified,
            'is_marketplace_visible': psychologist.is_marketplace_visible,

            # Service offerings
            'offers_initial_consultation': psychologist.offers_initial_consultation,
            'offers_online_sessions': psychologist.offers_online_sessions,
            'services_offered': psychologist.services_offered,
            'office_address': psychologist.office_address,

            # Professional URLs
            'website_url': psychologist.website_url,
            'linkedin_url': psychologist.linkedin_url,

            # Pricing (MVP: optional)
            'hourly_rate': psychologist.hourly_rate,
            'initial_consultation_rate': psychologist.initial_consultation_rate,

            # Profile metrics
            'profile_completeness': psychologist.get_profile_completeness(),
            'verification_requirements': psychologist.get_verification_requirements(),
            'can_book_appointments': psychologist.can_book_appointments(),

            # Timestamps
            'created_at': psychologist.created_at,
            'updated_at': psychologist.updated_at,
        }

    @staticmethod
    def send_profile_creation_welcome_email(psychologist: Psychologist) -> bool:
        """
        Send welcome email after psychologist completes profile creation and payment
        """
        try:
            context = {
                'psychologist': psychologist,
                'psychologist_name': psychologist.full_name,
                'profile_url': f"{EmailService.get_email_context_base()['site_url']}/psychologist/profile",
                'next_steps': [
                    'Complete your availability schedule',
                    'Wait for admin verification (usually 1-2 business days)',
                    'Start receiving appointment bookings'
                ]
            }

            success = EmailService.send_email(
                subject=_('Welcome to K&Mdiscova - Profile Created Successfully'),
                template_name='psychologist_welcome',
                context=context,
                recipient_email=psychologist.user.email
            )

            if success:
                logger.info(f"Welcome email sent to psychologist {psychologist.user.email}")

            return success

        except Exception as e:
            logger.error(f"Failed to send welcome email to psychologist {psychologist.user.email}: {str(e)}")
            return False

    @staticmethod
    def get_marketplace_psychologists(filters: Dict[str, Any] = None) -> List[Psychologist]:
        """
        Get psychologists visible in marketplace with optional filtering
        """
        queryset = Psychologist.get_marketplace_psychologists()

        if filters:
            queryset = PsychologistService._apply_marketplace_filters(queryset, filters)

        return list(queryset)

    @staticmethod
    def search_psychologists(search_params: Dict[str, Any], user: User) -> List[Psychologist]:
        """
        Search psychologists with filters and proper access control
        """
        # Base queryset depends on user type
        if user.is_admin or user.is_staff:
            # Admins can see all psychologists
            queryset = Psychologist.objects.select_related('user')
        elif user.is_parent:
            # Parents can only see marketplace-visible psychologists
            queryset = Psychologist.get_marketplace_psychologists()
        elif user.is_psychologist:
            # Psychologists can see marketplace psychologists (for reference)
            queryset = Psychologist.get_marketplace_psychologists()
        else:
            # Unknown user type, return empty for security
            logger.warning(f"Unknown user type {user.user_type} attempting psychologist search")
            return []

        # Apply search filters
        queryset = PsychologistService._apply_search_filters(queryset, search_params)

        return list(queryset.order_by('first_name', 'last_name'))

    @staticmethod
    def validate_psychologist_data(profile_data: Dict[str, Any], is_update: bool = False) -> Dict[str, Any]:
        """
        Validate psychologist data according to business rules
        """
        errors = {}

        # Validate required fields for creation
        if not is_update:
            required_fields = ['first_name', 'last_name', 'license_number',
                             'license_issuing_authority', 'license_expiry_date', 'years_of_experience']

            for field in required_fields:
                if not profile_data.get(field):
                    errors[field] = f"{field.replace('_', ' ').title()} is required"

        # Validate license expiry date
        license_expiry = profile_data.get('license_expiry_date')
        if license_expiry:
            if isinstance(license_expiry, str):
                try:
                    license_expiry = datetime.strptime(license_expiry, '%Y-%m-%d').date()
                except ValueError:
                    errors['license_expiry_date'] = "Invalid date format"

            if license_expiry and license_expiry < date.today():
                errors['license_expiry_date'] = "License expiry date cannot be in the past"

        # Validate years of experience
        years_exp = profile_data.get('years_of_experience')
        if years_exp is not None:
            try:
                years_exp = int(years_exp)
                if years_exp < 0:
                    errors['years_of_experience'] = "Years of experience cannot be negative"
                elif years_exp > 60:
                    errors['years_of_experience'] = "Years of experience seems too high"
            except (ValueError, TypeError):
                errors['years_of_experience'] = "Years of experience must be a number"

        # Validate service offerings and office address
        offers_initial = profile_data.get('offers_initial_consultation')
        offers_online = profile_data.get('offers_online_sessions')
        office_address = profile_data.get('office_address')

        # Must offer at least one service
        if offers_initial is False and offers_online is False:
            errors['offers_online_sessions'] = "Must offer at least one service type"

        # Office address required for initial consultations
        if offers_initial is True and not office_address:
            errors['office_address'] = "Office address is required when offering initial consultations"

        # Validate education structure
        education = profile_data.get('education')
        if education is not None:
            education_errors = PsychologistService._validate_education_structure(education)
            if education_errors:
                errors['education'] = education_errors

        # Validate certifications structure
        certifications = profile_data.get('certifications')
        if certifications is not None:
            certification_errors = PsychologistService._validate_certifications_structure(certifications)
            if certification_errors:
                errors['certifications'] = certification_errors

        if errors:
            raise ValidationError(errors)

        return profile_data

    # Availability Management Methods

    @staticmethod
    def create_availability_block(psychologist: Psychologist, availability_data: Dict[str, Any]) -> PsychologistAvailability:
        """
        Create availability block for psychologist
        """
        # Validate psychologist can set availability
        if not psychologist.user.is_active:
            raise AvailabilityManagementError("Psychologist account is inactive")

        try:
            with transaction.atomic():
                # Validate availability data
                validated_data = PsychologistService._validate_availability_data(availability_data)

                # Check for overlapping availability
                PsychologistService._check_availability_overlap(psychologist, validated_data)

                # Create availability block
                validated_data['psychologist'] = psychologist
                availability = PsychologistAvailability.objects.create(**validated_data)

                logger.info(f"Availability block created for {psychologist.full_name}: {availability}")
                return availability

        except Exception as e:
            logger.error(f"Failed to create availability for {psychologist.user.email}: {str(e)}")
            raise AvailabilityManagementError(f"Failed to create availability: {str(e)}")

    @staticmethod
    def update_availability_block(availability: PsychologistAvailability, update_data: Dict[str, Any]) -> PsychologistAvailability:
        """
        Update availability block
        """
        try:
            with transaction.atomic():
                # Validate update data
                validated_data = PsychologistService._validate_availability_data(update_data, is_update=True)

                # Check for overlapping availability (excluding current block)
                PsychologistService._check_availability_overlap(
                    availability.psychologist, validated_data, exclude_id=availability.availability_id
                )

                # Update fields
                updated_fields = []
                allowed_fields = ['day_of_week', 'start_time', 'end_time', 'is_recurring', 'specific_date']

                for field, value in validated_data.items():
                    if field in allowed_fields and hasattr(availability, field):
                        setattr(availability, field, value)
                        updated_fields.append(field)

                if updated_fields:
                    updated_fields.append('updated_at')
                    availability.save(update_fields=updated_fields)
                    logger.info(f"Updated availability block {availability.availability_id}: {updated_fields}")

                return availability

        except Exception as e:
            logger.error(f"Failed to update availability {availability.availability_id}: {str(e)}")
            raise AvailabilityManagementError(f"Failed to update availability: {str(e)}")

    @staticmethod
    def delete_availability_block(availability: PsychologistAvailability) -> bool:
        """
        Delete availability block
        """
        try:
            availability_info = str(availability)
            psychologist_email = availability.psychologist.user.email

            availability.delete()

            logger.info(f"Availability block deleted: {availability_info} for {psychologist_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete availability {availability.availability_id}: {str(e)}")
            raise AvailabilityManagementError(f"Failed to delete availability: {str(e)}")

    @staticmethod
    def get_psychologist_availability(psychologist: Psychologist, date_from: date = None,
                                    date_to: date = None) -> Dict[str, Any]:
        """
        Get psychologist availability with generated appointment slots
        """
        if not date_from:
            date_from = date.today()

        if not date_to:
            date_to = date_from + timedelta(days=30)  # Default 30 days ahead

        # Get recurring availability
        recurring_availability = PsychologistAvailability.get_psychologist_recurring_availability(psychologist)

        # Get specific date availability
        specific_availability = PsychologistAvailability.get_psychologist_specific_availability(
            psychologist, date_from, date_to
        )

        # Generate appointment slots for date range
        appointment_slots = PsychologistService._generate_appointment_slots(
            psychologist, date_from, date_to, recurring_availability, specific_availability
        )

        return {
            'psychologist_id': str(psychologist.user.id),
            'psychologist_name': psychologist.full_name,
            'date_range': {
                'from': date_from,
                'to': date_to
            },
            'recurring_availability': [
                {
                    'availability_id': avail.availability_id,
                    'day_of_week': avail.day_of_week,
                    'day_name': avail.get_day_name(),
                    'start_time': avail.start_time,
                    'end_time': avail.end_time,
                    'duration_hours': avail.duration_hours,
                    'max_slots': avail.max_appointable_slots
                }
                for avail in recurring_availability
            ],
            'specific_availability': [
                {
                    'availability_id': avail.availability_id,
                    'specific_date': avail.specific_date,
                    'start_time': avail.start_time,
                    'end_time': avail.end_time,
                    'duration_hours': avail.duration_hours,
                    'max_slots': avail.max_appointable_slots
                }
                for avail in specific_availability
            ],
            'appointment_slots': appointment_slots
        }

    # Private helper methods

    @staticmethod
    def _apply_marketplace_filters(queryset, filters: Dict[str, Any]):
        """Apply filters for marketplace search"""
        # Service type filters
        if filters.get('offers_online_sessions') is not None:
            queryset = queryset.filter(offers_online_sessions=filters['offers_online_sessions'])

        if filters.get('offers_initial_consultation') is not None:
            queryset = queryset.filter(offers_initial_consultation=filters['offers_initial_consultation'])

        # Experience filters
        if filters.get('min_years_experience'):
            queryset = queryset.filter(years_of_experience__gte=filters['min_years_experience'])

        if filters.get('max_years_experience'):
            queryset = queryset.filter(years_of_experience__lte=filters['max_years_experience'])

        # Location filter for office address
        if filters.get('location_keywords'):
            queryset = queryset.filter(office_address__icontains=filters['location_keywords'])

        return queryset

    @staticmethod
    def _apply_search_filters(queryset, search_params: Dict[str, Any]):
        """Apply search filters to psychologist queryset"""
        # Name search
        if search_params.get('name'):
            name_query = Q(first_name__icontains=search_params['name']) | Q(last_name__icontains=search_params['name'])
            queryset = queryset.filter(name_query)

        # Biography keywords
        if search_params.get('bio_keywords'):
            queryset = queryset.filter(biography__icontains=search_params['bio_keywords'])

        # Service filters
        if search_params.get('offers_online_sessions') is not None:
            queryset = queryset.filter(offers_online_sessions=search_params['offers_online_sessions'])

        if search_params.get('offers_initial_consultation') is not None:
            queryset = queryset.filter(offers_initial_consultation=search_params['offers_initial_consultation'])

        # Experience range
        if search_params.get('min_years_experience'):
            queryset = queryset.filter(years_of_experience__gte=search_params['min_years_experience'])

        if search_params.get('max_years_experience'):
            queryset = queryset.filter(years_of_experience__lte=search_params['max_years_experience'])

        # License authority
        if search_params.get('license_authority'):
            queryset = queryset.filter(license_issuing_authority__icontains=search_params['license_authority'])

        # Location search
        if search_params.get('location_keywords'):
            queryset = queryset.filter(office_address__icontains=search_params['location_keywords'])

        # Verification status (admin only typically)
        if search_params.get('verification_status'):
            queryset = queryset.filter(verification_status=search_params['verification_status'])

        # Date range
        if search_params.get('created_after'):
            queryset = queryset.filter(created_at__gte=search_params['created_after'])

        if search_params.get('created_before'):
            queryset = queryset.filter(created_at__lte=search_params['created_before'])

        return queryset

    @staticmethod
    def _validate_education_structure(education: List[Dict[str, Any]]) -> List[str]:
        """Validate education JSON structure"""
        if not isinstance(education, list):
            return ["Education must be a list of educational entries"]

        errors = []
        for i, edu in enumerate(education):
            if not isinstance(edu, dict):
                errors.append(f"Education entry {i+1} must be a dictionary")
                continue

            required_keys = ['degree', 'institution', 'year']
            for key in required_keys:
                if key not in edu or not str(edu[key]).strip():
                    errors.append(f"Education entry {i+1} missing required field: {key}")

            # Validate year
            if 'year' in edu:
                try:
                    year = int(edu['year'])
                    current_year = date.today().year
                    if year < 1950 or year > current_year:
                        errors.append(f"Education entry {i+1} has invalid year: {year}")
                except (ValueError, TypeError):
                    errors.append(f"Education entry {i+1} year must be a number")

        return errors

    @staticmethod
    def _validate_certifications_structure(certifications: List[Dict[str, Any]]) -> List[str]:
        """Validate certifications JSON structure"""
        if not isinstance(certifications, list):
            return ["Certifications must be a list of certification entries"]

        errors = []
        for i, cert in enumerate(certifications):
            if not isinstance(cert, dict):
                errors.append(f"Certification entry {i+1} must be a dictionary")
                continue

            required_keys = ['name', 'institution', 'year']
            for key in required_keys:
                if key not in cert or not str(cert[key]).strip():
                    errors.append(f"Certification entry {i+1} missing required field: {key}")

            # Validate year
            if 'year' in cert:
                try:
                    year = int(cert['year'])
                    current_year = date.today().year
                    if year < 1950 or year > current_year:
                        errors.append(f"Certification entry {i+1} has invalid year: {year}")
                except (ValueError, TypeError):
                    errors.append(f"Certification entry {i+1} year must be a number")

        return errors

    @staticmethod
    def _validate_availability_data(availability_data: Dict[str, Any], is_update: bool = False) -> Dict[str, Any]:
        """Validate availability data"""
        errors = {}

        # Required fields for creation
        if not is_update:
            required_fields = ['day_of_week', 'start_time', 'end_time', 'is_recurring']
            for field in required_fields:
                if availability_data.get(field) is None:
                    errors[field] = f"{field.replace('_', ' ').title()} is required"

        # Validate day_of_week
        day_of_week = availability_data.get('day_of_week')
        if day_of_week is not None and (day_of_week < 0 or day_of_week > 6):
            errors['day_of_week'] = "Day of week must be 0-6 (0=Sunday, 6=Saturday)"

        # Validate time range
        start_time = availability_data.get('start_time')
        end_time = availability_data.get('end_time')

        if start_time and end_time:
            # Convert string times to time objects if needed
            if isinstance(start_time, str):
                try:
                    start_time = datetime.strptime(start_time, '%H:%M').time()
                except ValueError:
                    errors['start_time'] = "Invalid time format. Use HH:MM"

            if isinstance(end_time, str):
                try:
                    end_time = datetime.strptime(end_time, '%H:%M').time()
                except ValueError:
                    errors['end_time'] = "Invalid time format. Use HH:MM"

            # Validate time ordering and duration
            if isinstance(start_time, time) and isinstance(end_time, time):
                # *** FIX START ***
                # Check if end_time is after start_time FIRST
                if end_time <= start_time:
                    errors['end_time'] = "End time must be after start time"
                else:
                    # Only check duration if the times are in the correct order
                    start_dt = datetime.combine(date.today(), start_time)
                    end_dt = datetime.combine(date.today(), end_time)
                    duration = end_dt - start_dt

                    if duration.total_seconds() < 3600:  # 1 hour
                        errors['end_time'] = "Availability block must be at least 1 hour long"
                # *** FIX END ***

        # Validate recurring vs specific date logic
        is_recurring = availability_data.get('is_recurring')
        specific_date = availability_data.get('specific_date')

        if is_recurring and specific_date:
            errors['specific_date'] = "Recurring availability should not have a specific date"
        elif is_recurring is False and not specific_date:
            errors['specific_date'] = "Non-recurring availability must have a specific date"

        # Validate specific date is not in the past
        if specific_date:
            if isinstance(specific_date, str):
                try:
                    specific_date = datetime.strptime(specific_date, '%Y-%m-%d').date()
                except ValueError:
                    errors['specific_date'] = "Invalid date format. Use YYYY-MM-DD"

            # Use date.today() from the datetime module for comparison
            if isinstance(specific_date, date) and specific_date < date.today():
                errors['specific_date'] = "Specific date cannot be in the past"

        if errors:
            raise ValidationError(errors)

        return availability_data

    @staticmethod
    def _check_availability_overlap(psychologist: Psychologist, availability_data: Dict[str, Any], exclude_id: int = None):
        """Check for overlapping availability blocks"""
        queryset = PsychologistAvailability.objects.filter(psychologist=psychologist)

        if exclude_id:
            queryset = queryset.exclude(availability_id=exclude_id)

        is_recurring = availability_data.get('is_recurring')

        if is_recurring:
            # Check for overlapping recurring availability on same day
            day_of_week = availability_data.get('day_of_week')
            overlapping = queryset.filter(
                is_recurring=True,
                day_of_week=day_of_week
            )
        else:
            # Check for overlapping specific date availability
            specific_date = availability_data.get('specific_date')
            overlapping = queryset.filter(
                is_recurring=False,
                specific_date=specific_date
            )

        # Check time overlap
        start_time = availability_data.get('start_time')
        end_time = availability_data.get('end_time')

        for existing in overlapping:
            if (start_time < existing.end_time and end_time > existing.start_time):
                raise AvailabilityManagementError(
                    f"Time slot overlaps with existing availability: {existing.get_time_range_display()}"
                )

    @staticmethod
    def _generate_appointment_slots(psychologist: Psychologist, date_from: date, date_to: date,
                                  recurring_availability, specific_availability) -> List[Dict[str, Any]]:
        """
        Generate 1-hour appointment slots from availability blocks
        """
        slots = []
        current_date = date_from

        while current_date <= date_to:
            # Get availability for this specific date
            date_availability = PsychologistAvailability.get_availability_for_date(psychologist, current_date)

            for availability_block in date_availability:
                # Generate 1-hour slots for this block
                slot_times = availability_block.generate_slot_times()

                for slot_start_time in slot_times:
                    slot_end_time = (datetime.combine(date.today(), slot_start_time) + timedelta(hours=1)).time()

                    slots.append({
                        'date': current_date,
                        'start_time': slot_start_time,
                        'end_time': slot_end_time,
                        'datetime_start': datetime.combine(current_date, slot_start_time),
                        'datetime_end': datetime.combine(current_date, slot_end_time),
                        'availability_block_id': availability_block.availability_id,
                        'is_available': True,  # Will be updated by appointment booking logic
                        'slot_type': 'hourly'
                    })

            current_date += timedelta(days=1)

        # Sort slots by datetime
        slots.sort(key=lambda x: x['datetime_start'])

        return slots


class PsychologistVerificationService:
    """
    Service class for psychologist verification workflow
    Handles admin verification process and status changes
    """

    @staticmethod
    def update_verification_status(psychologist: Psychologist, new_status: str,
                                 admin_user: User, admin_notes: str = "") -> Psychologist:
        """
        Update psychologist verification status with proper workflow
        """
        # Validate admin permissions
        if not (admin_user.is_admin or admin_user.is_staff):
            raise PsychologistVerificationError("Only admins can update verification status")

        if new_status not in ['Pending', 'Approved', 'Rejected']:
            raise PsychologistVerificationError("Invalid verification status")

        old_status = psychologist.verification_status

        try:
            with transaction.atomic():
                # Update verification status
                psychologist.verification_status = new_status
                psychologist.admin_notes = admin_notes
                psychologist.save(update_fields=['verification_status', 'admin_notes', 'updated_at'])

                # Send notification emails based on status change
                if old_status != new_status:
                    PsychologistVerificationService._send_verification_status_email(
                        psychologist, new_status, old_status
                    )

                logger.info(
                    f"Verification status updated for {psychologist.full_name}: "
                    f"{old_status} -> {new_status} by admin {admin_user.email}"
                )

                return psychologist

        except Exception as e:
            logger.error(f"Failed to update verification status for {psychologist.user.email}: {str(e)}")
            raise PsychologistVerificationError(f"Failed to update verification status: {str(e)}")

    @staticmethod
    def get_verification_requirements_check(psychologist: Psychologist) -> Dict[str, Any]:
        """
        Comprehensive check of verification requirements
        """
        requirements = psychologist.get_verification_requirements()

        # Additional business logic checks
        verification_check = {
            'is_eligible_for_approval': len(requirements) == 0,
            'missing_requirements': requirements,
            'profile_completeness': psychologist.get_profile_completeness(),
            'license_status': {
                'is_valid': psychologist.license_is_valid,
                'expiry_date': psychologist.license_expiry_date,
                'days_until_expiry': (psychologist.license_expiry_date - date.today()).days if psychologist.license_expiry_date else None
            },
            'service_configuration': {
                'offers_services': psychologist.offers_initial_consultation or psychologist.offers_online_sessions,
                'has_office_address': bool(psychologist.office_address) if psychologist.offers_initial_consultation else True
            },
            'can_be_approved': (
                len(requirements) == 0 and
                psychologist.license_is_valid and
                psychologist.user.is_verified and
                psychologist.user.is_active
            )
        }

        return verification_check

    @staticmethod
    def _send_verification_status_email(psychologist: Psychologist, new_status: str, old_status: str):
        """
        Send email notification when verification status changes
        """
        try:
            if new_status == 'Approved':
                PsychologistVerificationService._send_approval_email(psychologist)
            elif new_status == 'Rejected':
                PsychologistVerificationService._send_rejection_email(psychologist)
            # No email for 'Pending' status (that's the initial state)

        except Exception as e:
            logger.error(f"Failed to send verification email to {psychologist.user.email}: {str(e)}")
            # Don't raise exception - verification status update should still succeed

    @staticmethod
    def _send_approval_email(psychologist: Psychologist):
        """Send approval email to psychologist"""
        context = {
            'psychologist': psychologist,
            'psychologist_name': psychologist.full_name,
            'marketplace_url': f"{EmailService.get_email_context_base()['site_url']}/marketplace",
            'profile_url': f"{EmailService.get_email_context_base()['site_url']}/psychologist/profile",
            'next_steps': [
                'Your profile is now visible in the marketplace',
                'Set up your availability schedule',
                'Start receiving appointment bookings from parents'
            ]
        }

        EmailService.send_email(
            subject=_('Congratulations! Your K&Mdiscova Profile Has Been Approved'),
            template_name='psychologist_approved',
            context=context,
            recipient_email=psychologist.user.email
        )

    @staticmethod
    def _send_rejection_email(psychologist: Psychologist):
        """Send rejection email to psychologist"""
        context = {
            'psychologist': psychologist,
            'psychologist_name': psychologist.full_name,
            'admin_notes': psychologist.admin_notes,
            'profile_url': f"{EmailService.get_email_context_base()['site_url']}/psychologist/profile",
            'support_email': EmailService.get_email_context_base()['support_email'],
            'resubmission_info': [
                'Review the feedback provided',
                'Update your profile with the required information',
                'Contact support if you need assistance'
            ]
        }

        EmailService.send_email(
            subject=_('K&Mdiscova Profile Verification Update Required'),
            template_name='psychologist_rejected',
            context=context,
            recipient_email=psychologist.user.email
        )


class PsychologistAvailabilityService:
    """
    Dedicated service for psychologist availability management
    """

    @staticmethod
    def get_weekly_availability_summary(psychologist: Psychologist) -> Dict[str, Any]:
        """
        Get a weekly summary of psychologist's recurring availability
        """
        recurring_blocks = PsychologistAvailability.get_psychologist_recurring_availability(psychologist)

        # Group by day of week
        weekly_summary = {}
        days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

        for day_num in range(7):
            day_name = days[day_num]
            day_blocks = [block for block in recurring_blocks if block.day_of_week == day_num]

            total_hours = sum(block.duration_hours for block in day_blocks)
            total_slots = sum(block.max_appointable_slots for block in day_blocks)

            weekly_summary[day_name.lower()] = {
                'day_of_week': day_num,
                'day_name': day_name,
                'blocks_count': len(day_blocks),
                'total_hours': total_hours,
                'total_slots': total_slots,
                'blocks': [
                    {
                        'availability_id': block.availability_id,
                        'start_time': block.start_time,
                        'end_time': block.end_time,
                        'duration_hours': block.duration_hours,
                        'max_slots': block.max_appointable_slots
                    }
                    for block in day_blocks
                ]
            }

        return {
            'psychologist_id': str(psychologist.user.id),
            'psychologist_name': psychologist.full_name,
            'weekly_availability': weekly_summary,
            'total_weekly_hours': sum(summary['total_hours'] for summary in weekly_summary.values()),
            'total_weekly_slots': sum(summary['total_slots'] for summary in weekly_summary.values())
        }

    @staticmethod
    def get_availability_conflicts(psychologist: Psychologist,
                                 new_availability_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Check for conflicts before creating/updating availability
        """
        conflicts = []

        try:
            # Temporarily validate the data to check for conflicts
            validated_data = PsychologistService._validate_availability_data(new_availability_data)

            # Check for existing overlapping blocks
            existing_blocks = PsychologistAvailability.objects.filter(psychologist=psychologist)

            is_recurring = validated_data.get('is_recurring')

            if is_recurring:
                day_of_week = validated_data.get('day_of_week')
                overlapping_blocks = existing_blocks.filter(
                    is_recurring=True,
                    day_of_week=day_of_week
                )
            else:
                specific_date = validated_data.get('specific_date')
                overlapping_blocks = existing_blocks.filter(
                    is_recurring=False,
                    specific_date=specific_date
                )

            start_time = validated_data.get('start_time')
            end_time = validated_data.get('end_time')

            for block in overlapping_blocks:
                if start_time < block.end_time and end_time > block.start_time:
                    conflicts.append({
                        'availability_id': block.availability_id,
                        'existing_time_range': block.get_time_range_display(),
                        'conflict_type': 'time_overlap',
                        'message': f"Overlaps with existing availability: {block.get_time_range_display()}"
                    })

        except ValidationError as e:
            # Add validation errors as conflicts
            for field, messages in e.message_dict.items():
                for message in messages:
                    conflicts.append({
                        'field': field,
                        'conflict_type': 'validation_error',
                        'message': message
                    })

        return conflicts

    @staticmethod
    def bulk_create_weekly_availability(psychologist: Psychologist,
                                      weekly_schedule: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Create multiple availability blocks for a weekly schedule
        """
        created_blocks = []
        errors = []

        for day_name, time_blocks in weekly_schedule.items():
            # Convert day name to day_of_week number
            days_map = {
                'sunday': 0, 'monday': 1, 'tuesday': 2, 'wednesday': 3,
                'thursday': 4, 'friday': 5, 'saturday': 6
            }

            day_of_week = days_map.get(day_name.lower())
            if day_of_week is None:
                errors.append(f"Invalid day name: {day_name}")
                continue

            for time_block in time_blocks:
                try:
                    availability_data = {
                        'day_of_week': day_of_week,
                        'start_time': time_block['start_time'],
                        'end_time': time_block['end_time'],
                        'is_recurring': True
                    }

                    # Check for conflicts first
                    conflicts = PsychologistAvailabilityService.get_availability_conflicts(
                        psychologist, availability_data
                    )

                    if conflicts:
                        errors.append(f"{day_name} {time_block['start_time']}-{time_block['end_time']}: {conflicts[0]['message']}")
                        continue

                    # Create the availability block
                    availability = PsychologistService.create_availability_block(
                        psychologist, availability_data
                    )
                    created_blocks.append(availability)

                except Exception as e:
                    errors.append(f"{day_name} {time_block.get('start_time', 'N/A')}: {str(e)}")

        return {
            'success': len(created_blocks),
            'errors': len(errors),
            'created_blocks': [
                {
                    'availability_id': block.availability_id,
                    'day_name': block.get_day_name(),
                    'time_range': block.get_time_range_display()
                }
                for block in created_blocks
            ],
            'error_details': errors
        }