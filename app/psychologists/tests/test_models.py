# psychologists/tests/test_models.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from datetime import date, time, timedelta
from decimal import Decimal

from users.models import User
from psychologists.models import Psychologist, PsychologistAvailability


class PsychologistModelTests(TestCase):
    """Test cases for Psychologist model"""

    def setUp(self):
        """Set up test data"""
        # Create a user for psychologist
        self.user = User.objects.create_user(
            email='test.psychologist@example.com',
            password='testpass123',
            user_type='Psychologist'
        )
        # Note: Signal will auto-create psychologist profile

    def test_psychologist_profile_auto_creation(self):
        """Test that psychologist profile is automatically created when user is created"""
        # Create a new psychologist user
        new_user = User.objects.create_user(
            email='new.psychologist@example.com',
            password='testpass123',
            user_type='Psychologist'
        )

        # Check that psychologist profile was created
        self.assertTrue(hasattr(new_user, 'psychologist_profile'))
        psychologist = new_user.psychologist_profile

        # Verify default values from signal
        self.assertEqual(psychologist.first_name, '')
        self.assertEqual(psychologist.last_name, '')
        self.assertEqual(psychologist.license_number, '')
        self.assertEqual(psychologist.verification_status, 'Pending')
        self.assertFalse(psychologist.offers_initial_consultation)
        self.assertTrue(psychologist.offers_online_sessions)
        self.assertEqual(psychologist.years_of_experience, 0)

    def test_psychologist_profile_not_created_for_parent(self):
        """Test that psychologist profile is not created for parent users"""
        parent_user = User.objects.create_user(
            email='parent@example.com',
            password='testpass123',
            user_type='Parent'
        )

        # Check that psychologist profile was not created
        self.assertFalse(hasattr(parent_user, 'psychologist_profile'))

    def test_psychologist_str_representation(self):
        """Test string representation of psychologist"""
        psychologist = self.user.psychologist_profile
        psychologist.first_name = 'John'
        psychologist.last_name = 'Smith'
        # Need to set required fields to avoid validation errors
        psychologist.license_number = 'PSY12345'
        psychologist.license_issuing_authority = 'State Board'
        psychologist.license_expiry_date = date.today() + timedelta(days=365)
        psychologist.save()

        self.assertEqual(str(psychologist), 'Dr. John Smith (test.psychologist@example.com)')

    def test_full_name_property(self):
        """Test full_name property"""
        psychologist = self.user.psychologist_profile
        psychologist.first_name = 'Jane'
        psychologist.last_name = 'Doe'

        self.assertEqual(psychologist.full_name, 'Dr. Jane Doe')

    def test_display_name_property(self):
        """Test display_name property with and without names"""
        psychologist = self.user.psychologist_profile

        # Without names, should use email username
        self.assertEqual(psychologist.display_name, 'test.psychologist')

        # With names, should use full name
        psychologist.first_name = 'Jane'
        psychologist.last_name = 'Doe'
        self.assertEqual(psychologist.display_name, 'Dr. Jane Doe')

    def test_is_verified_property(self):
        """Test is_verified property"""
        psychologist = self.user.psychologist_profile

        # Default is Pending
        self.assertFalse(psychologist.is_verified)

        # Test Approved
        psychologist.verification_status = 'Approved'
        self.assertTrue(psychologist.is_verified)

        # Test Rejected
        psychologist.verification_status = 'Rejected'
        self.assertFalse(psychologist.is_verified)

    def test_license_is_valid_property(self):
        """Test license_is_valid property"""
        psychologist = self.user.psychologist_profile

        # No expiry date
        self.assertFalse(psychologist.license_is_valid)

        # Future expiry date
        psychologist.license_expiry_date = date.today() + timedelta(days=365)
        self.assertTrue(psychologist.license_is_valid)

        # Past expiry date
        psychologist.license_expiry_date = date.today() - timedelta(days=1)
        self.assertFalse(psychologist.license_is_valid)

        # Today's date
        psychologist.license_expiry_date = date.today()
        self.assertTrue(psychologist.license_is_valid)

    def test_services_offered_property(self):
        """Test services_offered property"""
        psychologist = self.user.psychologist_profile

        # Default: only online sessions
        self.assertEqual(psychologist.services_offered, ['Online Sessions'])

        # Add initial consultation
        psychologist.offers_initial_consultation = True
        psychologist.office_address = '123 Main St, City, State'
        expected = ['Online Sessions', 'Initial Consultations']
        self.assertEqual(psychologist.services_offered, expected)

        # Only initial consultation
        psychologist.offers_online_sessions = False
        self.assertEqual(psychologist.services_offered, ['Initial Consultations'])

    def test_is_marketplace_visible_property(self):
        """Test is_marketplace_visible property"""
        psychologist = self.user.psychologist_profile

        # Setup required fields first
        psychologist.first_name = 'John'
        psychologist.last_name = 'Doe'
        psychologist.license_number = 'PSY12345'
        psychologist.license_issuing_authority = 'State Board'
        psychologist.license_expiry_date = date.today() + timedelta(days=365)
        psychologist.verification_status = 'Approved'
        self.user.is_active = True
        self.user.is_verified = True
        self.user.save()
        psychologist.save()

        # Should be visible now
        self.assertTrue(psychologist.is_marketplace_visible)

        # Test each condition
        psychologist.verification_status = 'Pending'
        psychologist.save()
        self.assertFalse(psychologist.is_marketplace_visible)

        psychologist.verification_status = 'Approved'
        psychologist.save()
        self.user.is_active = False
        self.user.save()
        self.assertFalse(psychologist.is_marketplace_visible)

    def test_get_profile_completeness(self):
        """Test profile completeness calculation"""
        psychologist = self.user.psychologist_profile

        # Empty profile should have low completeness
        initial_completeness = psychologist.get_profile_completeness()
        self.assertLessEqual(initial_completeness, 30)

        # Fill required fields
        psychologist.first_name = 'John'
        psychologist.last_name = 'Doe'
        psychologist.license_number = 'PSY12345'
        psychologist.license_issuing_authority = 'State Board'
        psychologist.license_expiry_date = date.today() + timedelta(days=365)
        psychologist.years_of_experience = 5

        improved_completeness = psychologist.get_profile_completeness()
        self.assertGreater(improved_completeness, initial_completeness)

        # Add optional fields
        psychologist.biography = 'Experienced psychologist specializing in child development.'
        psychologist.education = [{'degree': 'PhD Psychology', 'institution': 'University', 'year': 2015}]
        psychologist.certifications = [{'name': 'Child Psychology', 'institution': 'Board', 'year': 2016}]

        full_completeness = psychologist.get_profile_completeness()
        self.assertGreater(full_completeness, improved_completeness)

    def test_can_book_appointments(self):
        """Test can_book_appointments method"""
        psychologist = self.user.psychologist_profile

        # Setup for booking capability
        psychologist.first_name = 'John'
        psychologist.last_name = 'Doe'
        psychologist.license_number = 'PSY12345'
        psychologist.license_issuing_authority = 'State Board'
        psychologist.license_expiry_date = date.today() + timedelta(days=365)
        psychologist.years_of_experience = 5
        psychologist.verification_status = 'Approved'
        self.user.is_active = True
        self.user.is_verified = True
        self.user.save()
        psychologist.save()

        # Should be able to book (offers online sessions by default)
        self.assertTrue(psychologist.can_book_appointments())

        # Test with initial consultation requirement
        psychologist.offers_online_sessions = False
        psychologist.offers_initial_consultation = True
        # Don't save yet - would cause validation error without office address

        # Should fail without office address
        self.assertFalse(psychologist.can_book_appointments())

        # Should pass with office address
        psychologist.office_address = '123 Main St'
        psychologist.save()
        self.assertTrue(psychologist.can_book_appointments())

    def test_education_validation(self):
        """Test education field validation"""
        psychologist = self.user.psychologist_profile

        # Set required fields first
        psychologist.first_name = 'John'
        psychologist.last_name = 'Doe'
        psychologist.license_number = 'PSY12345'
        psychologist.license_issuing_authority = 'State Board'
        psychologist.license_expiry_date = date.today() + timedelta(days=365)

        # Valid education
        valid_education = [
            {'degree': 'PhD Psychology', 'institution': 'University of X', 'year': 2015},
            {'degree': 'MS Psychology', 'institution': 'College Y', 'year': 2010}
        ]
        psychologist.education = valid_education

        # Should not raise validation error
        try:
            psychologist.full_clean()
        except ValidationError:
            self.fail("Valid education should not raise ValidationError")

        # Invalid education structure
        psychologist.education = [{'degree': 'PhD'}]  # Missing required fields

        with self.assertRaises(ValidationError):
            psychologist.full_clean()

    def test_certifications_validation(self):
        """Test certifications field validation"""
        psychologist = self.user.psychologist_profile

        # Set required fields first
        psychologist.first_name = 'John'
        psychologist.last_name = 'Doe'
        psychologist.license_number = 'PSY12345'
        psychologist.license_issuing_authority = 'State Board'
        psychologist.license_expiry_date = date.today() + timedelta(days=365)

        # Valid certifications
        valid_certs = [
            {'name': 'Child Psychology', 'institution': 'Board X', 'year': 2016}
        ]
        psychologist.certifications = valid_certs

        # Should not raise validation error
        try:
            psychologist.full_clean()
        except ValidationError:
            self.fail("Valid certifications should not raise ValidationError")

        # Invalid certifications structure
        psychologist.certifications = [{'name': 'Cert'}]  # Missing required fields

        with self.assertRaises(ValidationError):
            psychologist.full_clean()

    def test_business_rules_validation(self):
        """Test business rule validations"""
        psychologist = self.user.psychologist_profile

        # Test: Office address required for initial consultations
        psychologist.offers_initial_consultation = True
        psychologist.office_address = ''

        with self.assertRaises(ValidationError) as cm:
            psychologist.full_clean()

        self.assertIn('office_address', cm.exception.message_dict)

        # Test: Must offer at least one service
        psychologist.offers_initial_consultation = False
        psychologist.offers_online_sessions = False

        with self.assertRaises(ValidationError) as cm:
            psychologist.full_clean()

        self.assertIn('offers_online_sessions', cm.exception.message_dict)

        # Test: License expiry in past
        psychologist.offers_online_sessions = True  # Fix previous error
        psychologist.license_expiry_date = date.today() - timedelta(days=1)

        with self.assertRaises(ValidationError) as cm:
            psychologist.full_clean()

        self.assertIn('license_expiry_date', cm.exception.message_dict)

    def test_get_marketplace_psychologists(self):
        """Test get_marketplace_psychologists class method"""
        # Setup first psychologist (from setUp)
        psychologist1 = self.user.psychologist_profile
        psychologist1.first_name = 'John'
        psychologist1.last_name = 'Doe'
        psychologist1.license_number = 'PSY12345'
        psychologist1.license_issuing_authority = 'State Board'
        psychologist1.license_expiry_date = date.today() + timedelta(days=365)
        psychologist1.years_of_experience = 5
        psychologist1.verification_status = 'Approved'
        self.user.is_active = True
        self.user.is_verified = True
        self.user.save()
        psychologist1.save()

        # Create second psychologist
        user2 = User.objects.create_user(
            email='psychologist2@example.com',
            password='testpass123',
            user_type='Psychologist'
        )
        psychologist2 = user2.psychologist_profile
        psychologist2.first_name = 'Jane'
        psychologist2.last_name = 'Smith'
        psychologist2.license_number = 'PSY67890'
        psychologist2.license_issuing_authority = 'State Board'
        psychologist2.license_expiry_date = date.today() + timedelta(days=365)
        psychologist2.years_of_experience = 3
        psychologist2.verification_status = 'Approved'
        user2.is_active = True
        user2.is_verified = True
        user2.save()
        psychologist2.save()

        # Create third psychologist (not approved)
        user3 = User.objects.create_user(
            email='psychologist3@example.com',
            password='testpass123',
            user_type='Psychologist'
        )
        # psychologist3 remains in Pending status

        marketplace_psychologists = Psychologist.get_marketplace_psychologists()

        # Should return 2 approved psychologists, ordered by name
        self.assertEqual(marketplace_psychologists.count(), 2)
        self.assertEqual(marketplace_psychologists[0].first_name, 'Jane')  # Smith comes before Doe
        self.assertEqual(marketplace_psychologists[1].first_name, 'John')

    def test_unique_license_number(self):
        """Test that license numbers must be unique"""
        psychologist1 = self.user.psychologist_profile
        psychologist1.first_name = 'John'
        psychologist1.last_name = 'Doe'
        psychologist1.license_number = 'PSY12345'
        psychologist1.license_issuing_authority = 'State Board'
        psychologist1.license_expiry_date = date.today() + timedelta(days=365)
        psychologist1.years_of_experience = 5
        psychologist1.save()

        # Create second psychologist with same license number
        user2 = User.objects.create_user(
            email='psychologist2@example.com',
            password='testpass123',
            user_type='Psychologist'
        )
        psychologist2 = user2.psychologist_profile
        psychologist2.first_name = 'Jane'
        psychologist2.last_name = 'Smith'
        psychologist2.license_number = 'PSY12345'  # Same as first
        psychologist2.license_issuing_authority = 'State Board'
        psychologist2.license_expiry_date = date.today() + timedelta(days=365)
        psychologist2.years_of_experience = 3

        # Should raise ValidationError during full_clean (called by save)
        with self.assertRaises(ValidationError) as cm:
            psychologist2.save()

        # Check that the error is about license number uniqueness
        self.assertIn('license_number', cm.exception.message_dict)


class PsychologistAvailabilityModelTests(TestCase):
    """Test cases for PsychologistAvailability model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='psychologist@example.com',
            password='testpass123',
            user_type='Psychologist'
        )
        self.psychologist = self.user.psychologist_profile

        # Setup psychologist for booking capability
        self.psychologist.first_name = 'John'
        self.psychologist.last_name = 'Doe'
        self.psychologist.license_number = 'PSY12345'
        self.psychologist.license_issuing_authority = 'State Board'
        self.psychologist.license_expiry_date = date.today() + timedelta(days=365)
        self.psychologist.years_of_experience = 5
        self.psychologist.verification_status = 'Approved'
        self.user.is_active = True
        self.user.is_verified = True
        self.user.save()
        self.psychologist.save()

    def test_availability_creation(self):
        """Test creating availability block"""
        availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_recurring=True
        )

        self.assertEqual(availability.psychologist, self.psychologist)
        self.assertEqual(availability.day_of_week, 1)
        self.assertTrue(availability.is_recurring)
        self.assertIsNone(availability.specific_date)

    def test_availability_str_representation(self):
        """Test string representation of availability"""
        availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_recurring=True
        )

        expected = f"{self.psychologist.display_name} - Monday 09:00-17:00"
        self.assertEqual(str(availability), expected)

    def test_specific_date_availability(self):
        """Test specific date availability"""
        specific_date = date.today() + timedelta(days=7)
        availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=specific_date.weekday(),
            start_time=time(10, 0),
            end_time=time(14, 0),
            is_recurring=False,
            specific_date=specific_date
        )

        self.assertFalse(availability.is_recurring)
        self.assertEqual(availability.specific_date, specific_date)

    def test_duration_hours_property(self):
        """Test duration_hours property"""
        availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_recurring=True
        )

        self.assertEqual(availability.duration_hours, 8.0)

    def test_max_appointable_slots_property(self):
        """Test max_appointable_slots property"""
        availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_recurring=True
        )

        self.assertEqual(availability.max_appointable_slots, 8)

    def test_get_day_name(self):
        """Test get_day_name method"""
        availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_recurring=True
        )

        self.assertEqual(availability.get_day_name(), 'Monday')

    def test_generate_slot_times(self):
        """Test generate_slot_times method"""
        availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,
            start_time=time(9, 0),
            end_time=time(12, 0),  # 3 hours
            is_recurring=True
        )

        slots = availability.generate_slot_times()
        expected_slots = [time(9, 0), time(10, 0), time(11, 0)]
        self.assertEqual(slots, expected_slots)

    def test_overlaps_with(self):
        """Test overlaps_with method"""
        availability1 = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,
            start_time=time(9, 0),
            end_time=time(13, 0),
            is_recurring=True
        )

        # Overlapping availability
        availability2 = PsychologistAvailability(
            psychologist=self.psychologist,
            day_of_week=1,
            start_time=time(11, 0),
            end_time=time(15, 0),
            is_recurring=True
        )

        self.assertTrue(availability1.overlaps_with(availability2))

        # Non-overlapping availability
        availability3 = PsychologistAvailability(
            psychologist=self.psychologist,
            day_of_week=1,
            start_time=time(14, 0),
            end_time=time(18, 0),
            is_recurring=True
        )

        self.assertFalse(availability1.overlaps_with(availability3))

    def test_validation_end_time_after_start_time(self):
        """Test validation that end time must be after start time"""
        with self.assertRaises(ValidationError):
            availability = PsychologistAvailability(
                psychologist=self.psychologist,
                day_of_week=1,
                start_time=time(17, 0),
                end_time=time(9, 0),  # End before start
                is_recurring=True
            )
            availability.full_clean()

    def test_validation_minimum_duration(self):
        """Test validation for minimum 1-hour duration"""
        with self.assertRaises(ValidationError):
            availability = PsychologistAvailability(
                psychologist=self.psychologist,
                day_of_week=1,
                start_time=time(9, 0),
                end_time=time(9, 30),  # Only 30 minutes
                is_recurring=True
            )
            availability.full_clean()

    def test_validation_recurring_no_specific_date(self):
        """Test validation that recurring availability should not have specific date"""
        with self.assertRaises(ValidationError):
            availability = PsychologistAvailability(
                psychologist=self.psychologist,
                day_of_week=1,
                start_time=time(9, 0),
                end_time=time(17, 0),
                is_recurring=True,
                specific_date=date.today()  # Should be None for recurring
            )
            availability.full_clean()

    def test_validation_specific_date_required_for_non_recurring(self):
        """Test validation that non-recurring availability must have specific date"""
        with self.assertRaises(ValidationError):
            availability = PsychologistAvailability(
                psychologist=self.psychologist,
                day_of_week=1,
                start_time=time(9, 0),
                end_time=time(17, 0),
                is_recurring=False
                # Missing specific_date
            )
            availability.full_clean()

    def test_validation_specific_date_not_in_past(self):
        """Test validation that specific date cannot be in the past"""
        past_date = date.today() - timedelta(days=1)

        with self.assertRaises(ValidationError):
            availability = PsychologistAvailability(
                psychologist=self.psychologist,
                day_of_week=1,
                start_time=time(9, 0),
                end_time=time(17, 0),
                is_recurring=False,
                specific_date=past_date
            )
            availability.full_clean()

    def test_get_availability_for_date(self):
        """Test get_availability_for_date class method"""
        # Create recurring availability for Monday (day_of_week=1)
        recurring_availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_recurring=True
        )

        # Create specific date availability for next Monday
        next_monday = date.today() + timedelta(days=(7 - date.today().weekday()))
        specific_availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,
            start_time=time(10, 0),
            end_time=time(14, 0),
            is_recurring=False,
            specific_date=next_monday
        )

        # Get availability for next Monday
        availability_blocks = PsychologistAvailability.get_availability_for_date(
            self.psychologist, next_monday
        )

        # Should return both recurring and specific availability
        self.assertEqual(availability_blocks.count(), 2)

    def test_is_active_on_date(self):
        """Test is_active_on_date method"""
        # Recurring availability for Monday
        availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday in our system (0=Sunday, 1=Monday, etc.)
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_recurring=True
        )

        # Find next Monday
        today = date.today()
        # Python's weekday: 0=Monday, 6=Sunday
        # Our system: 0=Sunday, 1=Monday, 6=Saturday
        # So we need to convert: Python Monday (0) = Our Monday (1)
        current_weekday = today.weekday()  # 0=Monday in Python
        days_until_monday = (0 - current_weekday) % 7  # Days until next Monday
        if days_until_monday == 0 and today.weekday() == 0:
            # If today is Monday, use today
            next_monday = today
        else:
            next_monday = today + timedelta(days=days_until_monday if days_until_monday > 0 else 7)

        self.assertTrue(availability.is_active_on_date(next_monday))

        # Should not be active on Tuesday
        next_tuesday = next_monday + timedelta(days=1)
        self.assertFalse(availability.is_active_on_date(next_tuesday))

    def test_unique_together_constraint(self):
        """Test unique together constraint"""
        # Create first availability
        PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_recurring=False,
            specific_date=date(2025, 12, 25)

        )

        # Try to create duplicate - should raise ValidationError or IntegrityError
        with self.assertRaises((IntegrityError, ValidationError)):
            duplicate_availability = PsychologistAvailability.objects.create(
                psychologist=self.psychologist,
                day_of_week=1,
                start_time=time(9, 0),
                end_time=time(17, 0),
                is_recurring=False,
                specific_date=date(2025, 12, 25)
            )