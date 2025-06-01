# psychologists/tests/test_services.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, time, timedelta
from unittest.mock import patch, MagicMock

from users.models import User
from psychologists.models import Psychologist, PsychologistAvailability
from psychologists.services import (
    PsychologistService,
    PsychologistVerificationService,
    PsychologistAvailabilityService,
    PsychologistProfileError,
    PsychologistNotFoundError,
    PsychologistVerificationError,
    AvailabilityManagementError
)


class PsychologistServiceTests(TestCase):
    """Tests for PsychologistService"""

    def setUp(self):
        # Create test users
        self.psychologist_user = User.objects.create_user(
            email='psych@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )

        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            user_type='Admin',
            is_staff=True,
            is_verified=True,
            is_active=True
        )

        # Create test psychologist profile
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Dr. John',
            last_name='Smith',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            biography='Experienced child psychologist',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

    def test_get_psychologist_by_user_success(self):
        """Test successfully getting psychologist by user"""
        result = PsychologistService.get_psychologist_by_user(self.psychologist_user)
        self.assertEqual(result, self.psychologist)

    def test_get_psychologist_by_user_not_found(self):
        """Test getting psychologist by user when not found"""
        other_user = User.objects.create_user(
            email='other@test.com',
            password='testpass123',
            user_type='Parent'
        )
        result = PsychologistService.get_psychologist_by_user(other_user)
        self.assertIsNone(result)

    def test_get_psychologist_by_user_or_raise_success(self):
        """Test successfully getting psychologist or raising exception"""
        result = PsychologistService.get_psychologist_by_user_or_raise(self.psychologist_user)
        self.assertEqual(result, self.psychologist)

    def test_get_psychologist_by_user_or_raise_not_found(self):
        """Test raising exception when psychologist not found"""
        other_user = User.objects.create_user(
            email='other@test.com',
            password='testpass123',
            user_type='Parent'
        )
        with self.assertRaises(PsychologistNotFoundError):
            PsychologistService.get_psychologist_by_user_or_raise(other_user)

    def test_create_psychologist_profile_success(self):
        """Test successfully creating psychologist profile"""
        new_user = User.objects.create_user(
            email='newpsych@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )

        profile_data = {
            'first_name': 'Dr. Jane',
            'last_name': 'Doe',
            'license_number': 'PSY789012',
            'license_issuing_authority': 'State Board',
            'license_expiry_date': date.today() + timedelta(days=365),
            'years_of_experience': 5,
            'offers_online_sessions': True,
            'offers_initial_consultation': False
        }

        result = PsychologistService.create_psychologist_profile(new_user, profile_data)

        self.assertIsInstance(result, Psychologist)
        self.assertEqual(result.user, new_user)
        self.assertEqual(result.first_name, 'Dr. Jane')
        self.assertEqual(result.license_number, 'PSY789012')

    def test_create_psychologist_profile_user_not_psychologist(self):
        """Test creating profile with non-psychologist user fails"""
        parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent'
        )

        with self.assertRaises(PsychologistProfileError) as context:
            PsychologistService.create_psychologist_profile(parent_user, {})

        self.assertIn("not registered as a psychologist", str(context.exception))

    def test_create_psychologist_profile_user_not_verified(self):
        """Test creating profile with unverified user fails"""
        unverified_user = User.objects.create_user(
            email='unverified@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=False
        )

        with self.assertRaises(PsychologistProfileError) as context:
            PsychologistService.create_psychologist_profile(unverified_user, {})

        self.assertIn("Email must be verified", str(context.exception))

    def test_create_psychologist_profile_already_exists(self):
        """Test creating profile when one already exists fails"""
        profile_data = {
            'first_name': 'Dr. Jane',
            'last_name': 'Doe',
            'license_number': 'PSY789012',
            'license_issuing_authority': 'State Board',
            'license_expiry_date': date.today() + timedelta(days=365),
            'years_of_experience': 5,
            'offers_online_sessions': True
        }

        with self.assertRaises(PsychologistProfileError) as context:
            PsychologistService.create_psychologist_profile(self.psychologist_user, profile_data)

        self.assertIn("already exists", str(context.exception))

    def test_update_psychologist_profile_success(self):
        """Test successfully updating psychologist profile"""
        update_data = {
            'biography': 'Updated biography',
            'years_of_experience': 15,
            'website_url': 'https://example.com'
        }

        result = PsychologistService.update_psychologist_profile(self.psychologist, update_data)

        self.assertEqual(result.biography, 'Updated biography')
        self.assertEqual(result.years_of_experience, 15)
        self.assertEqual(result.website_url, 'https://example.com')

    def test_update_psychologist_profile_inactive_user(self):
        """Test updating profile with inactive user fails"""
        self.psychologist_user.is_active = False
        self.psychologist_user.save()

        with self.assertRaises(PsychologistProfileError) as context:
            PsychologistService.update_psychologist_profile(self.psychologist, {})

        self.assertIn("inactive", str(context.exception))

    def test_get_psychologist_profile_data(self):
        """Test getting comprehensive profile data"""
        result = PsychologistService.get_psychologist_profile_data(self.psychologist)

        self.assertIn('user_id', result)
        self.assertIn('email', result)
        self.assertIn('full_name', result)
        self.assertIn('verification_status', result)
        self.assertIn('profile_completeness', result)
        self.assertEqual(result['email'], self.psychologist_user.email)
        self.assertEqual(result['first_name'], 'Dr. John')

    def test_get_marketplace_psychologists(self):
        """Test getting marketplace-visible psychologists"""
        # Set psychologist as approved to make marketplace visible
        self.psychologist.verification_status = 'Approved'
        self.psychologist.save()

        result = PsychologistService.get_marketplace_psychologists()

        self.assertIn(self.psychologist, result)

    def test_get_marketplace_psychologists_with_filters(self):
        """Test getting marketplace psychologists with filters"""
        self.psychologist.verification_status = 'Approved'
        self.psychologist.save()

        filters = {
            'offers_online_sessions': True,
            'min_years_experience': 5
        }

        result = PsychologistService.get_marketplace_psychologists(filters)

        self.assertIn(self.psychologist, result)

    def test_validate_psychologist_data_success(self):
        """Test validating psychologist data successfully"""
        valid_data = {
            'first_name': 'Dr. Jane',
            'last_name': 'Doe',
            'license_number': 'PSY789012',
            'license_issuing_authority': 'State Board',
            'license_expiry_date': date.today() + timedelta(days=365),
            'years_of_experience': 5,
            'offers_online_sessions': True,
            'offers_initial_consultation': False
        }

        result = PsychologistService.validate_psychologist_data(valid_data)
        self.assertEqual(result, valid_data)

    def test_validate_psychologist_data_missing_required_fields(self):
        """Test validation fails with missing required fields"""
        invalid_data = {
            'first_name': 'Dr. Jane'
            # Missing other required fields
        }

        with self.assertRaises(ValidationError):
            PsychologistService.validate_psychologist_data(invalid_data)

    def test_validate_psychologist_data_expired_license(self):
        """Test validation fails with expired license"""
        invalid_data = {
            'first_name': 'Dr. Jane',
            'last_name': 'Doe',
            'license_number': 'PSY789012',
            'license_issuing_authority': 'State Board',
            'license_expiry_date': date.today() - timedelta(days=30),  # Expired
            'years_of_experience': 5,
            'offers_online_sessions': True
        }

        with self.assertRaises(ValidationError) as context:
            PsychologistService.validate_psychologist_data(invalid_data)

        self.assertIn("cannot be in the past", str(context.exception))

    def test_validate_psychologist_data_no_services_offered(self):
        """Test validation fails when no services are offered"""
        invalid_data = {
            'first_name': 'Dr. Jane',
            'last_name': 'Doe',
            'license_number': 'PSY789012',
            'license_issuing_authority': 'State Board',
            'license_expiry_date': date.today() + timedelta(days=365),
            'years_of_experience': 5,
            'offers_online_sessions': False,
            'offers_initial_consultation': False
        }

        with self.assertRaises(ValidationError) as context:
            PsychologistService.validate_psychologist_data(invalid_data)

        self.assertIn("Must offer at least one service", str(context.exception))

    def test_validate_psychologist_data_initial_consultation_without_office(self):
        """Test validation fails when offering initial consultation without office address"""
        invalid_data = {
            'first_name': 'Dr. Jane',
            'last_name': 'Doe',
            'license_number': 'PSY789012',
            'license_issuing_authority': 'State Board',
            'license_expiry_date': date.today() + timedelta(days=365),
            'years_of_experience': 5,
            'offers_online_sessions': False,
            'offers_initial_consultation': True,
            'office_address': ''  # Required but empty
        }

        with self.assertRaises(ValidationError) as context:
            PsychologistService.validate_psychologist_data(invalid_data)

        self.assertIn("Office address is required", str(context.exception))

    @patch('psychologists.services.EmailService.send_email')
    def test_send_profile_creation_welcome_email_success(self, mock_send_email):
        """Test sending welcome email successfully"""
        mock_send_email.return_value = True

        result = PsychologistService.send_profile_creation_welcome_email(self.psychologist)

        self.assertTrue(result)
        mock_send_email.assert_called_once()

    @patch('psychologists.services.EmailService.send_email')
    def test_send_profile_creation_welcome_email_failure(self, mock_send_email):
        """Test handling welcome email failure"""
        mock_send_email.side_effect = Exception("Email failed")

        result = PsychologistService.send_profile_creation_welcome_email(self.psychologist)

        self.assertFalse(result)


class PsychologistVerificationServiceTests(TestCase):
    """Tests for PsychologistVerificationService"""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            user_type='Admin',
            is_staff=True,
            is_active=True
        )

        self.psychologist_user = User.objects.create_user(
            email='psych@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )

        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Dr. John',
            last_name='Smith',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            biography='Experienced child psychologist',
            offers_online_sessions=True,
            offers_initial_consultation=False,  # Explicitly set to False
            verification_status='Pending'
        )

    def test_update_verification_status_to_approved(self):
        """Test updating verification status to approved"""
        result = PsychologistVerificationService.update_verification_status(
            self.psychologist,
            'Approved',
            self.admin_user,
            'Profile meets all requirements'
        )

        self.assertEqual(result.verification_status, 'Approved')
        self.assertEqual(result.admin_notes, 'Profile meets all requirements')

    def test_update_verification_status_to_rejected(self):
        """Test updating verification status to rejected"""
        result = PsychologistVerificationService.update_verification_status(
            self.psychologist,
            'Rejected',
            self.admin_user,
            'Missing required documentation'
        )

        self.assertEqual(result.verification_status, 'Rejected')
        self.assertEqual(result.admin_notes, 'Missing required documentation')

    def test_update_verification_status_non_admin_fails(self):
        """Test non-admin cannot update verification status"""
        non_admin_user = User.objects.create_user(
            email='user@test.com',
            password='testpass123',
            user_type='Parent'
        )

        with self.assertRaises(PsychologistVerificationError) as context:
            PsychologistVerificationService.update_verification_status(
                self.psychologist,
                'Approved',
                non_admin_user
            )

        self.assertIn("Only admins can update", str(context.exception))

    def test_update_verification_status_invalid_status(self):
        """Test updating to invalid verification status fails"""
        with self.assertRaises(PsychologistVerificationError) as context:
            PsychologistVerificationService.update_verification_status(
                self.psychologist,
                'InvalidStatus',
                self.admin_user
            )

        self.assertIn("Invalid verification status", str(context.exception))

    def test_get_verification_requirements_check(self):
        """Test getting verification requirements check"""
        result = PsychologistVerificationService.get_verification_requirements_check(self.psychologist)

        self.assertIn('is_eligible_for_approval', result)
        self.assertIn('missing_requirements', result)
        self.assertIn('profile_completeness', result)
        self.assertIn('license_status', result)
        self.assertIn('service_configuration', result)
        self.assertIn('can_be_approved', result)

    @patch('psychologists.services.PsychologistVerificationService._send_approval_email')
    def test_send_verification_status_email_approved(self, mock_send_approval):
        """Test sending approval email when status changes to approved"""
        PsychologistVerificationService.update_verification_status(
            self.psychologist,
            'Approved',
            self.admin_user
        )

        mock_send_approval.assert_called_once_with(self.psychologist)

    @patch('psychologists.services.PsychologistVerificationService._send_rejection_email')
    def test_send_verification_status_email_rejected(self, mock_send_rejection):
        """Test sending rejection email when status changes to rejected"""
        PsychologistVerificationService.update_verification_status(
            self.psychologist,
            'Rejected',
            self.admin_user
        )

        mock_send_rejection.assert_called_once_with(self.psychologist)


class PsychologistAvailabilityServiceTests(TestCase):
    """Tests for PsychologistAvailabilityService"""

    def setUp(self):
        self.psychologist_user = User.objects.create_user(
            email='psych@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )

        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Dr. John',
            last_name='Smith',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            offers_online_sessions=True,
            offers_initial_consultation=False,  # Explicitly set to False
            verification_status='Approved'
        )

        # Create test availability
        self.availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time=time(9, 0),
            end_time=time(12, 0),
            is_recurring=True
        )

    def test_create_availability_block_success(self):
        """Test successfully creating availability block"""
        availability_data = {
            'day_of_week': 2,  # Tuesday
            'start_time': time(14, 0),
            'end_time': time(17, 0),
            'is_recurring': True
        }

        result = PsychologistService.create_availability_block(self.psychologist, availability_data)

        self.assertIsInstance(result, PsychologistAvailability)
        self.assertEqual(result.psychologist, self.psychologist)
        self.assertEqual(result.day_of_week, 2)
        self.assertEqual(result.start_time, time(14, 0))

    def test_create_availability_block_inactive_psychologist(self):
        """Test creating availability block for inactive psychologist fails"""
        self.psychologist_user.is_active = False
        self.psychologist_user.save()

        availability_data = {
            'day_of_week': 2,
            'start_time': time(14, 0),
            'end_time': time(17, 0),
            'is_recurring': True
        }

        with self.assertRaises(AvailabilityManagementError) as context:
            PsychologistService.create_availability_block(self.psychologist, availability_data)

        self.assertIn("inactive", str(context.exception))

    def test_create_availability_block_overlapping_times(self):
        """Test creating overlapping availability block fails"""
        availability_data = {
            'day_of_week': 1,  # Monday (same as existing)
            'start_time': time(10, 0),  # Overlaps with existing 9-12
            'end_time': time(13, 0),
            'is_recurring': True
        }

        with self.assertRaises(AvailabilityManagementError) as context:
            PsychologistService.create_availability_block(self.psychologist, availability_data)

        self.assertIn("overlaps", str(context.exception))

    def test_update_availability_block_success(self):
        """Test successfully updating availability block"""
        update_data = {
            'start_time': time(10, 0),
            'end_time': time(13, 0)
        }

        result = PsychologistService.update_availability_block(self.availability, update_data)

        self.assertEqual(result.start_time, time(10, 0))
        self.assertEqual(result.end_time, time(13, 0))

    def test_delete_availability_block_success(self):
        """Test successfully deleting availability block"""
        availability_id = self.availability.availability_id

        result = PsychologistService.delete_availability_block(self.availability)

        self.assertTrue(result)
        with self.assertRaises(PsychologistAvailability.DoesNotExist):
            PsychologistAvailability.objects.get(availability_id=availability_id)

    def test_get_psychologist_availability(self):
        """Test getting psychologist availability with slots"""
        date_from = date.today()
        date_to = date.today() + timedelta(days=7)

        result = PsychologistService.get_psychologist_availability(
            self.psychologist, date_from, date_to
        )

        self.assertIn('psychologist_id', result)
        self.assertIn('recurring_availability', result)
        self.assertIn('appointment_slots', result)
        self.assertEqual(result['psychologist_name'], self.psychologist.full_name)

    def test_get_weekly_availability_summary(self):
        """Test getting weekly availability summary"""
        result = PsychologistAvailabilityService.get_weekly_availability_summary(self.psychologist)

        self.assertIn('psychologist_id', result)
        self.assertIn('weekly_availability', result)
        self.assertIn('total_weekly_hours', result)
        self.assertIn('total_weekly_slots', result)

        # Check Monday has availability
        monday_data = result['weekly_availability']['monday']
        self.assertEqual(monday_data['blocks_count'], 1)
        self.assertEqual(monday_data['total_hours'], 3.0)

    def test_get_availability_conflicts(self):
        """Test checking for availability conflicts"""
        conflicting_data = {
            'day_of_week': 1,  # Monday (same as existing)
            'start_time': time(10, 0),  # Overlaps with existing 9-12
            'end_time': time(13, 0),
            'is_recurring': True
        }

        result = PsychologistAvailabilityService.get_availability_conflicts(
            self.psychologist, conflicting_data
        )

        self.assertTrue(len(result) > 0)
        self.assertEqual(result[0]['conflict_type'], 'time_overlap')

    def test_bulk_create_weekly_availability_success(self):
        """Test bulk creating weekly availability"""
        weekly_schedule = {
            'wednesday': [
                {'start_time': time(9, 0), 'end_time': time(12, 0)},
                {'start_time': time(14, 0), 'end_time': time(17, 0)}
            ],
            'friday': [
                {'start_time': time(10, 0), 'end_time': time(15, 0)}
            ]
        }

        result = PsychologistAvailabilityService.bulk_create_weekly_availability(
            self.psychologist, weekly_schedule
        )

        self.assertEqual(result['success'], 3)  # 2 + 1 blocks created
        self.assertEqual(result['errors'], 0)
        self.assertEqual(len(result['created_blocks']), 3)

    def test_bulk_create_weekly_availability_with_conflicts(self):
        """Test bulk creating with some conflicts"""
        weekly_schedule = {
            'monday': [  # Conflicts with existing Monday 9-12
                {'start_time': time(10, 0), 'end_time': time(13, 0)}
            ],
            'tuesday': [  # Should succeed
                {'start_time': time(9, 0), 'end_time': time(12, 0)}
            ]
        }

        result = PsychologistAvailabilityService.bulk_create_weekly_availability(
            self.psychologist, weekly_schedule
        )

        self.assertEqual(result['success'], 1)  # Only Tuesday should succeed
        self.assertEqual(result['errors'], 1)   # Monday should fail
        self.assertTrue(len(result['error_details']) > 0)

    def test_validate_availability_data_invalid_time_range(self):
        """Test validation fails with invalid time range"""
        invalid_data = {
            'day_of_week': 1,
            'start_time': time(15, 0),
            'end_time': time(14, 0),  # End before start
            'is_recurring': True
        }

        with self.assertRaises(ValidationError) as context:
            PsychologistService._validate_availability_data(invalid_data)

        self.assertIn("End time must be after start time", str(context.exception))

    def test_validate_availability_data_too_short_duration(self):
        """Test validation fails with duration less than 1 hour"""
        invalid_data = {
            'day_of_week': 1,
            'start_time': time(9, 0),
            'end_time': time(9, 30),  # Only 30 minutes
            'is_recurring': True
        }

        with self.assertRaises(ValidationError) as context:
            PsychologistService._validate_availability_data(invalid_data)

        self.assertIn("must be at least 1 hour long", str(context.exception))

    def test_validate_availability_data_recurring_with_specific_date(self):
        """Test validation fails when recurring availability has specific date"""
        invalid_data = {
            'day_of_week': 1,
            'start_time': time(9, 0),
            'end_time': time(12, 0),
            'is_recurring': True,
            'specific_date': date.today()  # Should not have specific date
        }

        with self.assertRaises(ValidationError) as context:
            PsychologistService._validate_availability_data(invalid_data)

        self.assertIn("should not have a specific date", str(context.exception))

    def test_validate_availability_data_non_recurring_without_specific_date(self):
        """Test validation fails when non-recurring availability lacks specific date"""
        invalid_data = {
            'day_of_week': 1,
            'start_time': time(9, 0),
            'end_time': time(12, 0),
            'is_recurring': False
            # Missing specific_date
        }

        with self.assertRaises(ValidationError) as context:
            PsychologistService._validate_availability_data(invalid_data)

        self.assertIn("must have a specific date", str(context.exception))