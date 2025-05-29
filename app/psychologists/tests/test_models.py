# psychologists/tests.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
import datetime

from psychologists.models import Psychologist, PsychologistAvailability

User = get_user_model()


class PsychologistModelTest(TestCase):
    """Test cases for Psychologist model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )

        self.psychologist_data = {
            'user': self.user,
            'first_name': 'John',
            'last_name': 'Doe',
            'license_number': 'PSY123456',
            'license_issuing_authority': 'State Board of Psychology',
            'license_expiry_date': datetime.date(2025, 12, 31),
            'years_of_experience': 10,
            'biography': 'Experienced child psychologist',
            'education': [
                {'degree': 'PhD Psychology', 'institution': 'University of Test', 'year': 2010}
            ],
            'certifications': [
                {'name': 'Child Psychology Certification', 'institution': 'Test Institute', 'year': 2015}
            ],
            'hourly_rate': Decimal('150.00'),
            'verification_status': 'Approved',
            'website_url': 'https://example.com',
            'linkedin_url': 'https://linkedin.com/in/johndoe'
        }

    def test_psychologist_creation(self):
        """Test creating a psychologist with valid data"""
        psychologist = Psychologist.objects.create(**self.psychologist_data)

        self.assertEqual(psychologist.user, self.user)
        self.assertEqual(psychologist.first_name, 'John')
        self.assertEqual(psychologist.last_name, 'Doe')
        self.assertEqual(psychologist.license_number, 'PSY123456')
        self.assertEqual(psychologist.years_of_experience, 10)
        self.assertEqual(psychologist.hourly_rate, Decimal('150.00'))
        self.assertTrue(psychologist.created_at)
        self.assertTrue(psychologist.updated_at)

    def test_psychologist_str_representation(self):
        """Test string representation of psychologist"""
        psychologist = Psychologist.objects.create(**self.psychologist_data)
        expected_str = "Dr. John Doe"
        self.assertEqual(str(psychologist), expected_str)

    def test_psychologist_full_name_property(self):
        """Test full_name property"""
        psychologist = Psychologist.objects.create(**self.psychologist_data)
        self.assertEqual(psychologist.full_name, "John Doe")

    def test_psychologist_display_name_property(self):
        """Test display_name property"""
        psychologist = Psychologist.objects.create(**self.psychologist_data)
        self.assertEqual(psychologist.display_name, "Dr. John Doe")

    def test_psychologist_is_verified_property(self):
        """Test is_verified property"""
        # Test approved psychologist
        self.psychologist_data['verification_status'] = 'Approved'
        approved_psychologist = Psychologist.objects.create(**self.psychologist_data)
        self.assertTrue(approved_psychologist.is_verified)

        # Test pending psychologist
        user2 = User.objects.create_user(
            email='psychologist2@test.com',
            password='testpass123',
            user_type='Psychologist'
        )
        pending_data = self.psychologist_data.copy()
        pending_data['user'] = user2
        pending_data['license_number'] = 'PSY654321'
        pending_data['verification_status'] = 'Pending'

        pending_psychologist = Psychologist.objects.create(**pending_data)
        self.assertFalse(pending_psychologist.is_verified)

    def test_can_accept_appointments_method(self):
        """Test can_accept_appointments method"""
        # Test fully qualified psychologist
        psychologist = Psychologist.objects.create(**self.psychologist_data)
        self.assertTrue(psychologist.can_accept_appointments())

        # Test with inactive user
        self.user.is_active = False
        self.user.save()
        self.assertFalse(psychologist.can_accept_appointments())

        # Reset user to active
        self.user.is_active = True
        self.user.is_verified = False
        self.user.save()
        self.assertFalse(psychologist.can_accept_appointments())

        # Reset user verification and test rejected psychologist
        self.user.is_verified = True
        self.user.save()
        psychologist.verification_status = 'Rejected'
        psychologist.save()
        self.assertFalse(psychologist.can_accept_appointments())

    def test_unique_license_number(self):
        """Test that license numbers must be unique"""
        Psychologist.objects.create(**self.psychologist_data)

        # Try to create another psychologist with same license number
        user2 = User.objects.create_user(
            email='psychologist2@test.com',
            password='testpass123',
            user_type='Psychologist'
        )

        duplicate_data = self.psychologist_data.copy()
        duplicate_data['user'] = user2
        # Same license number should raise IntegrityError

        with self.assertRaises(IntegrityError):
            Psychologist.objects.create(**duplicate_data)

    def test_years_experience_validation(self):
        """Test years of experience validation"""
        # Test negative years (should be prevented by PositiveIntegerField)
        invalid_data = self.psychologist_data.copy()
        invalid_data['years_of_experience'] = -5

        psychologist = Psychologist(**invalid_data)
        with self.assertRaises(ValidationError):
            psychologist.full_clean()

    def test_hourly_rate_validation(self):
        """Test hourly rate validation"""
        # Test negative hourly rate
        invalid_data = self.psychologist_data.copy()
        invalid_data['hourly_rate'] = Decimal('-50.00')

        psychologist = Psychologist(**invalid_data)
        with self.assertRaises(ValidationError):
            psychologist.full_clean()

    def test_json_fields_default_values(self):
        """Test that JSON fields have proper default values"""
        minimal_data = {
            'user': self.user,
            'first_name': 'Jane',
            'last_name': 'Smith',
            'license_number': 'PSY789012',
            'years_of_experience': 5
        }

        psychologist = Psychologist.objects.create(**minimal_data)
        self.assertEqual(psychologist.education, [])
        self.assertEqual(psychologist.certifications, [])

    def test_optional_fields(self):
        """Test that optional fields can be blank"""
        minimal_data = {
            'user': self.user,
            'first_name': 'Jane',
            'last_name': 'Smith',
            'license_number': 'PSY789012',
            'years_of_experience': 5
        }

        psychologist = Psychologist.objects.create(**minimal_data)
        self.assertEqual(psychologist.biography, '')
        self.assertEqual(psychologist.license_issuing_authority, '')
        self.assertIsNone(psychologist.license_expiry_date)
        self.assertIsNone(psychologist.hourly_rate)
        self.assertEqual(psychologist.admin_notes, '')
        self.assertEqual(psychologist.website_url, '')
        self.assertEqual(psychologist.linkedin_url, '')


class PsychologistAvailabilityModelTest(TestCase):
    """Test cases for PsychologistAvailability model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist'
        )

        self.psychologist = Psychologist.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            license_number='PSY123456',
            years_of_experience=10
        )

        self.availability_data = {
            'psychologist': self.psychologist,
            'day_of_week': 1,  # Monday
            'start_time': datetime.time(9, 0),
            'end_time': datetime.time(17, 0),
            'is_recurring': True
        }

    def test_availability_creation(self):
        """Test creating availability with valid data"""
        availability = PsychologistAvailability.objects.create(**self.availability_data)

        self.assertEqual(availability.psychologist, self.psychologist)
        self.assertEqual(availability.day_of_week, 1)
        self.assertEqual(availability.start_time, datetime.time(9, 0))
        self.assertEqual(availability.end_time, datetime.time(17, 0))
        self.assertTrue(availability.is_recurring)
        self.assertFalse(availability.is_booked)
        self.assertIsNone(availability.specific_date)

    def test_availability_str_representation(self):
        """Test string representation of availability"""
        availability = PsychologistAvailability.objects.create(**self.availability_data)
        expected_str = "Dr. John Doe - Monday 09:00:00-17:00:00"
        self.assertEqual(str(availability), expected_str)

    def test_specific_date_availability_str(self):
        """Test string representation for specific date availability"""
        specific_date_data = self.availability_data.copy()
        specific_date_data['is_recurring'] = False
        specific_date_data['specific_date'] = datetime.date(2024, 1, 15)

        availability = PsychologistAvailability.objects.create(**specific_date_data)
        expected_str = "Dr. John Doe - 2024-01-15 09:00:00-17:00:00"
        self.assertEqual(str(availability), expected_str)

    def test_duration_hours_property(self):
        """Test duration_hours property calculation"""
        availability = PsychologistAvailability.objects.create(**self.availability_data)
        self.assertEqual(availability.duration_hours, 8.0)  # 9 AM to 5 PM = 8 hours

        # Test shorter duration
        short_availability_data = self.availability_data.copy()
        short_availability_data['day_of_week'] = 2  # Different day to avoid uniqueness conflict
        short_availability_data['start_time'] = datetime.time(14, 0)
        short_availability_data['end_time'] = datetime.time(16, 30)

        short_availability = PsychologistAvailability.objects.create(**short_availability_data)
        self.assertEqual(short_availability.duration_hours, 2.5)  # 2 hours 30 minutes

    def test_is_available_for_date_recurring(self):
        """Test is_available_for_date method for recurring availability"""
        availability = PsychologistAvailability.objects.create(**self.availability_data)

        # Monday availability should be available on Mondays
        monday_date = datetime.date(2024, 1, 8)  # A Monday
        self.assertTrue(availability.is_available_for_date(monday_date))

        # Should not be available on Tuesday
        tuesday_date = datetime.date(2024, 1, 9)  # A Tuesday
        self.assertFalse(availability.is_available_for_date(tuesday_date))

    def test_is_available_for_date_specific(self):
        """Test is_available_for_date method for specific date availability"""
        specific_date = datetime.date(2024, 1, 15)
        specific_data = self.availability_data.copy()
        specific_data['is_recurring'] = False
        specific_data['specific_date'] = specific_date

        availability = PsychologistAvailability.objects.create(**specific_data)

        # Should be available on the specific date
        self.assertTrue(availability.is_available_for_date(specific_date))

        # Should not be available on other dates
        other_date = datetime.date(2024, 1, 16)
        self.assertFalse(availability.is_available_for_date(other_date))

    def test_clean_method_start_time_validation(self):
        """Test clean method validates start time before end time"""
        invalid_data = self.availability_data.copy()
        invalid_data['start_time'] = datetime.time(17, 0)
        invalid_data['end_time'] = datetime.time(9, 0)  # End before start

        availability = PsychologistAvailability(**invalid_data)
        with self.assertRaises(ValidationError):
            availability.clean()

    def test_clean_method_non_recurring_needs_date(self):
        """Test clean method validates non-recurring availability has specific date"""
        invalid_data = self.availability_data.copy()
        invalid_data['is_recurring'] = False
        # Missing specific_date

        availability = PsychologistAvailability(**invalid_data)
        with self.assertRaises(ValidationError):
            availability.clean()

    def test_clean_method_recurring_no_specific_date(self):
        """Test clean method validates recurring availability doesn't have specific date"""
        invalid_data = self.availability_data.copy()
        invalid_data['is_recurring'] = True
        invalid_data['specific_date'] = datetime.date(2024, 1, 15)  # Should not have specific date

        availability = PsychologistAvailability(**invalid_data)
        with self.assertRaises(ValidationError):
            availability.clean()

    def test_unique_recurring_availability_constraint(self):
        """Test unique constraint for recurring availability"""
        PsychologistAvailability.objects.create(**self.availability_data)

        # Try to create duplicate recurring availability
        with self.assertRaises(IntegrityError):
            PsychologistAvailability.objects.create(**self.availability_data)

    def test_unique_specific_date_availability_constraint(self):
        """Test unique constraint for specific date availability"""
        specific_date = datetime.date(2024, 1, 15)
        specific_data = self.availability_data.copy()
        specific_data['is_recurring'] = False
        specific_data['specific_date'] = specific_date

        PsychologistAvailability.objects.create(**specific_data)

        # Try to create duplicate specific date availability
        with self.assertRaises(IntegrityError):
            PsychologistAvailability.objects.create(**specific_data)

    def test_different_psychologists_same_time_allowed(self):
        """Test that different psychologists can have same availability times"""
        # Create first availability
        PsychologistAvailability.objects.create(**self.availability_data)

        # Create second psychologist
        user2 = User.objects.create_user(
            email='psychologist2@test.com',
            password='testpass123',
            user_type='Psychologist'
        )

        psychologist2 = Psychologist.objects.create(
            user=user2,
            first_name='Jane',
            last_name='Smith',
            license_number='PSY654321',
            years_of_experience=8
        )

        # Same time slot for different psychologist should be allowed
        availability_data_2 = self.availability_data.copy()
        availability_data_2['psychologist'] = psychologist2

        # This should not raise an exception
        availability2 = PsychologistAvailability.objects.create(**availability_data_2)
        self.assertEqual(availability2.psychologist, psychologist2)

    def test_day_of_week_choices(self):
        """Test day of week choices are correctly defined"""
        choices_dict = dict(PsychologistAvailability.DAY_OF_WEEK_CHOICES)
        self.assertEqual(choices_dict[0], 'Sunday')
        self.assertEqual(choices_dict[1], 'Monday')
        self.assertEqual(choices_dict[6], 'Saturday')

    def test_model_meta_options(self):
        """Test model meta options"""
        meta = PsychologistAvailability._meta
        self.assertEqual(meta.db_table, 'psychologist_availability')
        self.assertEqual(str(meta.verbose_name), 'Psychologist Availability')
        self.assertEqual(str(meta.verbose_name_plural), 'Psychologist Availabilities')

    def test_related_name_access(self):
        """Test accessing availability through psychologist's related name"""
        availability = PsychologistAvailability.objects.create(**self.availability_data)

        # Test related name access
        availabilities = self.psychologist.availability_slots.all()
        self.assertIn(availability, availabilities)
        self.assertEqual(availabilities.count(), 1)