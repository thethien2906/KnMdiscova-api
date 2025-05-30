# psychologists/tests/test_serializers.py
from decimal import Decimal
from datetime import date, time, datetime, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from ..models import Psychologist, PsychologistAvailability
from ..serializers import (
    PsychologistRegistrationSerializer,
    PsychologistProfileSerializer,
    PsychologistPublicProfileSerializer,
    AvailabilityCreateUpdateSerializer,
    AvailabilityListSerializer,
    PsychologistSearchSerializer,
    PsychologistVerificationSerializer,
    AvailabilityBulkSerializer,
)

User = get_user_model()


class PsychologistRegistrationSerializerTest(TestCase):
    """Test psychologist registration serializer"""

    def setUp(self):
        self.valid_data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'password_confirm': 'testpass123',
            'first_name': 'John',
            'last_name': 'Doe',
            'license_number': 'PSY-123456',
            'license_issuing_authority': 'State Board',
            'license_expiry_date': date.today() + timedelta(days=365),
            'years_of_experience': 5,
            'biography': 'Experienced psychologist',
            'education': [
                {'degree': 'PhD Psychology', 'institution': 'University X', 'year': '2015'}
            ],
            'certifications': [
                {'name': 'CBT Certification', 'institution': 'Institute Y', 'year': '2016'}
            ],
            'hourly_rate': Decimal('100.00'),
            'website_url': 'https://example.com',
            'linkedin_url': 'https://linkedin.com/in/johndoe'
        }

    def test_valid_registration_data(self):
        """Test registration with valid data"""
        serializer = PsychologistRegistrationSerializer(data=self.valid_data)
        self.assertTrue(serializer.is_valid())

    def test_password_confirmation_mismatch(self):
        """Test password confirmation validation"""
        data = self.valid_data.copy()
        data['password_confirm'] = 'different_password'

        serializer = PsychologistRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('password_confirm', serializer.errors)

    def test_duplicate_email_validation(self):
        """Test email uniqueness validation"""
        # Create a user first
        User.objects.create_user(
            email='test@example.com',
            password='password123',
            user_type='Client'
        )

        serializer = PsychologistRegistrationSerializer(data=self.valid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('email', serializer.errors)

    def test_duplicate_license_number_validation(self):
        """Test license number uniqueness validation"""
        # Create a user and psychologist first
        user = User.objects.create_user(
            email='existing@example.com',
            password='password123',
            user_type='Psychologist'
        )
        Psychologist.objects.create(
            user=user,
            first_name='Jane',
            last_name='Smith',
            license_number='PSY-123456',
            years_of_experience=3
        )

        serializer = PsychologistRegistrationSerializer(data=self.valid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('license_number', serializer.errors)

    def test_invalid_license_number_format(self):
        """Test license number format validation"""
        data = self.valid_data.copy()
        data['license_number'] = 'invalid_format!'

        serializer = PsychologistRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('license_number', serializer.errors)

    def test_password_minimum_length(self):
        """Test password minimum length validation"""
        data = self.valid_data.copy()
        data['password'] = 'short'
        data['password_confirm'] = 'short'

        serializer = PsychologistRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('password', serializer.errors)

    def test_years_of_experience_validation(self):
        """Test years of experience range validation"""
        # Test negative value
        data = self.valid_data.copy()
        data['years_of_experience'] = -1

        serializer = PsychologistRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('years_of_experience', serializer.errors)

        # Test too high value
        data['years_of_experience'] = 100
        serializer = PsychologistRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('years_of_experience', serializer.errors)

    def test_education_structure_validation(self):
        """Test education structure validation"""
        data = self.valid_data.copy()

        # Test missing required keys
        data['education'] = [{'degree': 'PhD', 'institution': 'University'}]  # Missing year
        serializer = PsychologistRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('education', serializer.errors)

        # Test invalid year
        data['education'] = [{'degree': 'PhD', 'institution': 'University', 'year': '1800'}]
        serializer = PsychologistRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('education', serializer.errors)

    def test_certifications_structure_validation(self):
        """Test certifications structure validation"""
        data = self.valid_data.copy()

        # Test missing required keys
        data['certifications'] = [{'name': 'Cert', 'institution': 'Institute'}]  # Missing year
        serializer = PsychologistRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('certifications', serializer.errors)

    def test_license_expiry_date_validation(self):
        """Test license expiry date validation"""
        data = self.valid_data.copy()
        data['license_expiry_date'] = date.today() - timedelta(days=1)  # Past date

        serializer = PsychologistRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('license_expiry_date', serializer.errors)

    def test_required_fields(self):
        """Test required field validation"""
        required_fields = ['email', 'password', 'first_name', 'last_name', 'license_number', 'years_of_experience']

        for field in required_fields:
            data = self.valid_data.copy()
            del data[field]

            serializer = PsychologistRegistrationSerializer(data=data)
            self.assertFalse(serializer.is_valid())
            self.assertIn(field, serializer.errors)


class PsychologistProfileSerializerTest(TestCase):
    """Test psychologist profile serializer"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='password123',
            user_type='Psychologist',
            is_verified=True
        )
        self.psychologist = Psychologist.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            license_number='PSY-123456',
            years_of_experience=5,
            verification_status='Approved'
        )

    def test_profile_serialization(self):
        """Test profile data serialization"""
        serializer = PsychologistProfileSerializer(instance=self.psychologist)
        data = serializer.data

        self.assertEqual(data['email'], self.user.email)
        self.assertEqual(data['first_name'], 'John')
        self.assertEqual(data['last_name'], 'Doe')
        self.assertEqual(data['full_name'], 'John Doe')
        self.assertEqual(data['display_name'], 'Dr. John Doe')
        self.assertTrue(data['can_accept_appointments'])

    def test_profile_update_validation(self):
        """Test profile update validation"""
        data = {
            'first_name': 'Jane',
            'last_name': 'Smith',
            'years_of_experience': 10,
            'biography': 'Updated biography'
        }

        serializer = PsychologistProfileSerializer(instance=self.psychologist, data=data, partial=True)
        self.assertTrue(serializer.is_valid())

    def test_license_number_uniqueness_on_update(self):
        """Test license number uniqueness validation on update"""
        # Create another psychologist
        other_user = User.objects.create_user(
            email='other@example.com',
            password='password123',
            user_type='Psychologist'
        )
        other_psychologist = Psychologist.objects.create(
            user=other_user,
            first_name='Other',
            last_name='Doctor',
            license_number='PSY-789012',
            years_of_experience=3
        )

        # Try to update current psychologist with other's license number
        data = {'license_number': 'PSY-789012'}
        serializer = PsychologistProfileSerializer(instance=self.psychologist, data=data, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn('license_number', serializer.errors)

    def test_education_validation(self):
        """Test education validation on update"""
        # Test invalid structure
        data = {'education': 'not a list'}
        serializer = PsychologistProfileSerializer(instance=self.psychologist, data=data, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn('education', serializer.errors)

        # Test invalid object structure
        data = {'education': [{'degree': 'PhD'}]}  # Missing required keys
        serializer = PsychologistProfileSerializer(instance=self.psychologist, data=data, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn('education', serializer.errors)

    def test_read_only_fields(self):
        """Test that read-only fields cannot be updated"""
        data = {
            'email': 'newemail@example.com',
            'user_type': 'Client',
            'verification_status': 'Rejected',
            'can_accept_appointments': False
        }

        serializer = PsychologistProfileSerializer(instance=self.psychologist, data=data, partial=True)
        self.assertTrue(serializer.is_valid())

        # These fields should not change
        updated_instance = serializer.save()
        self.assertEqual(updated_instance.user.email, 'test@example.com')
        self.assertEqual(updated_instance.verification_status, 'Approved')


class PsychologistPublicProfileSerializerTest(TestCase):
    """Test public profile serializer"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='password123',
            user_type='Psychologist',
            is_verified=True
        )
        self.psychologist = Psychologist.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            license_number='PSY-123456',
            years_of_experience=5,
            education=[
                {'degree': 'PhD Psychology', 'institution': 'University X', 'year': '2015'}
            ],
            certifications=[
                {'name': 'CBT Certification', 'institution': 'Institute Y', 'year': '2016'}
            ],
            verification_status='Approved'
        )

    def test_public_profile_serialization(self):
        """Test public profile data serialization"""
        serializer = PsychologistPublicProfileSerializer(instance=self.psychologist)
        data = serializer.data

        # Should include public fields
        self.assertIn('display_name', data)
        self.assertIn('years_of_experience', data)
        self.assertIn('biography', data)
        self.assertIn('public_education', data)
        self.assertIn('public_certifications', data)

        # Should not include sensitive fields
        self.assertNotIn('license_number', data)
        self.assertNotIn('email', data)

    def test_public_education_formatting(self):
        """Test education formatting for public view"""
        serializer = PsychologistPublicProfileSerializer(instance=self.psychologist)
        data = serializer.data

        self.assertEqual(len(data['public_education']), 1)
        education = data['public_education'][0]
        self.assertEqual(education['degree'], 'PhD Psychology')
        self.assertEqual(education['institution'], 'University X')
        self.assertEqual(education['year'], '2015')

    def test_public_certifications_formatting(self):
        """Test certifications formatting for public view"""
        serializer = PsychologistPublicProfileSerializer(instance=self.psychologist)
        data = serializer.data

        self.assertEqual(len(data['public_certifications']), 1)
        certification = data['public_certifications'][0]
        self.assertEqual(certification['name'], 'CBT Certification')
        self.assertEqual(certification['institution'], 'Institute Y')
        self.assertEqual(certification['year'], '2016')


class AvailabilityCreateUpdateSerializerTest(TestCase):
    """Test availability create/update serializer"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='password123',
            user_type='Psychologist'
        )
        self.psychologist = Psychologist.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            license_number='PSY-123456',
            years_of_experience=5
        )

    def test_valid_recurring_availability(self):
        """Test valid recurring availability creation"""
        data = {
            'day_of_week': 1,  # Monday
            'start_time': time(9, 0),
            'end_time': time(17, 0),
            'is_recurring': True
        }

        serializer = AvailabilityCreateUpdateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_valid_specific_date_availability(self):
        """Test valid specific date availability creation"""
        future_date = date.today() + timedelta(days=7)
        data = {
            'day_of_week': 1,
            'start_time': time(9, 0),
            'end_time': time(17, 0),
            'is_recurring': False,
            'specific_date': future_date
        }

        serializer = AvailabilityCreateUpdateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_end_time_before_start_time_validation(self):
        """Test time sequence validation"""
        data = {
            'day_of_week': 1,
            'start_time': time(17, 0),
            'end_time': time(9, 0),  # End before start
            'is_recurring': True
        }

        serializer = AvailabilityCreateUpdateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('end_time', serializer.errors)

    def test_non_recurring_without_specific_date(self):
        """Test non-recurring availability without specific date"""
        data = {
            'day_of_week': 1,
            'start_time': time(9, 0),
            'end_time': time(17, 0),
            'is_recurring': False
            # Missing specific_date
        }

        serializer = AvailabilityCreateUpdateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('specific_date', serializer.errors)

    def test_recurring_with_specific_date(self):
        """Test recurring availability with specific date"""
        data = {
            'day_of_week': 1,
            'start_time': time(9, 0),
            'end_time': time(17, 0),
            'is_recurring': True,
            'specific_date': date.today() + timedelta(days=7)
        }

        serializer = AvailabilityCreateUpdateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('specific_date', serializer.errors)

    def test_specific_date_in_past(self):
        """Test specific date validation"""
        past_date = date.today() - timedelta(days=1)
        data = {
            'day_of_week': 1,
            'start_time': time(9, 0),
            'end_time': time(17, 0),
            'is_recurring': False,
            'specific_date': past_date
        }

        serializer = AvailabilityCreateUpdateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('specific_date', serializer.errors)

    def test_day_of_week_validation(self):
        """Test day of week range validation"""
        # Test invalid day
        data = {
            'day_of_week': 8,  # Invalid day
            'start_time': time(9, 0),
            'end_time': time(17, 0),
            'is_recurring': True
        }

        serializer = AvailabilityCreateUpdateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('day_of_week', serializer.errors)


class AvailabilityListSerializerTest(TestCase):
    """Test availability list serializer"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='password123',
            user_type='Psychologist'
        )
        self.psychologist = Psychologist.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            license_number='PSY-123456',
            years_of_experience=5
        )
        self.availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_recurring=True
        )

    def test_availability_serialization(self):
        """Test availability data serialization"""
        serializer = AvailabilityListSerializer(instance=self.availability)
        data = serializer.data

        self.assertEqual(data['day_of_week'], 1)
        self.assertEqual(data['day_name'], 'Monday')
        self.assertEqual(data['formatted_time'], '09:00 - 17:00')
        self.assertEqual(data['duration_hours'], 8.0)
        self.assertEqual(data['psychologist_name'], 'Dr. John Doe')

    def test_specific_date_availability_serialization(self):
        """Test specific date availability serialization"""
        specific_date = date.today() + timedelta(days=7)
        specific_availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,
            start_time=time(10, 0),
            end_time=time(12, 0),
            is_recurring=False,
            specific_date=specific_date
        )

        serializer = AvailabilityListSerializer(instance=specific_availability)
        data = serializer.data

        self.assertIsNone(data['day_name'])  # No day name for specific dates
        self.assertEqual(data['specific_date'], specific_date.isoformat())


class PsychologistSearchSerializerTest(TestCase):
    """Test psychologist search serializer"""

    def test_valid_search_parameters(self):
        """Test valid search parameters"""
        data = {
            'search': 'therapy',
            'min_experience': 2,
            'max_experience': 10,
            'min_rate': Decimal('50.00'),
            'max_rate': Decimal('200.00'),
            'verification_status': 'Approved',
            'available_on': date.today() + timedelta(days=7),
            'ordering': '-years_of_experience'
        }

        serializer = PsychologistSearchSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_experience_range_validation(self):
        """Test experience range validation"""
        data = {
            'min_experience': 10,
            'max_experience': 5  # Max less than min
        }

        serializer = PsychologistSearchSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('max_experience', serializer.errors)

    def test_rate_range_validation(self):
        """Test rate range validation"""
        data = {
            'min_rate': Decimal('200.00'),
            'max_rate': Decimal('100.00')  # Max less than min
        }

        serializer = PsychologistSearchSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('max_rate', serializer.errors)

    def test_available_on_past_date_validation(self):
        """Test available_on date validation"""
        data = {
            'available_on': date.today() - timedelta(days=1)  # Past date
        }

        serializer = PsychologistSearchSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('available_on', serializer.errors)

    def test_default_ordering(self):
        """Test default ordering"""
        serializer = PsychologistSearchSerializer(data={})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['ordering'], '-created_at')


class PsychologistVerificationSerializerTest(TestCase):
    """Test psychologist verification serializer"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='password123',
            user_type='Psychologist'
        )
        self.psychologist = Psychologist.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            license_number='PSY-123456',
            years_of_experience=5,
            verification_status='Pending'
        )

    def test_verification_status_update(self):
        """Test verification status update"""
        data = {
            'verification_status': 'Approved',
            'admin_notes': 'All documents verified'
        }

        serializer = PsychologistVerificationSerializer(instance=self.psychologist, data=data, partial=True)
        self.assertTrue(serializer.is_valid())

    def test_rejection_requires_admin_notes(self):
        """Test that rejection requires admin notes"""
        data = {
            'verification_status': 'Rejected'
            # Missing admin_notes
        }

        serializer = PsychologistVerificationSerializer(instance=self.psychologist, data=data, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn('admin_notes', serializer.errors)

    def test_approved_to_pending_transition_validation(self):
        """Test invalid status transition from Approved to Pending"""
        # First approve the psychologist
        self.psychologist.verification_status = 'Approved'
        self.psychologist.save()

        # Try to change back to pending
        data = {'verification_status': 'Pending'}
        serializer = PsychologistVerificationSerializer(instance=self.psychologist, data=data, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn('verification_status', serializer.errors)

    def test_read_only_fields(self):
        """Test that read-only fields cannot be updated"""
        data = {
            'license_number': 'NEW-123',
            'years_of_experience': 100
        }

        serializer = PsychologistVerificationSerializer(instance=self.psychologist, data=data, partial=True)
        self.assertTrue(serializer.is_valid())

        # These fields should not change
        updated_instance = serializer.save()
        self.assertEqual(updated_instance.license_number, 'PSY-123456')
        self.assertEqual(updated_instance.years_of_experience, 5)


class AvailabilityBulkSerializerTest(TestCase):
    """Test availability bulk operations serializer"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='password123',
            user_type='Psychologist'
        )
        self.psychologist = Psychologist.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            license_number='PSY-123456',
            years_of_experience=5
        )

    def test_valid_bulk_create_operation(self):
        """Test valid bulk create operation"""
        data = {
            'operation': 'create',
            'availability_slots': [
                {
                    'day_of_week': 1,
                    'start_time': time(9, 0),
                    'end_time': time(12, 0),
                    'is_recurring': True
                },
                {
                    'day_of_week': 2,
                    'start_time': time(14, 0),
                    'end_time': time(17, 0),
                    'is_recurring': True
                }
            ]
        }

        serializer = AvailabilityBulkSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_valid_bulk_delete_operation(self):
        data = {
        'operation': 'delete',
        'slot_ids': [1, 2, 3]  # Only slot_ids, no availability_slots
        }
        serializer = AvailabilityBulkSerializer(data=data)
        is_valid = serializer.is_valid()
        print("Is Valid:", is_valid)
        print("Serializer Errors:", serializer.errors)
        self.assertTrue(is_valid)



    def test_delete_operation_missing_slot_ids(self):
        """Test delete operation validation without slot IDs"""
        data = {
            'operation': 'delete',
            'availability_slots': []
        }

        serializer = AvailabilityBulkSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('availability_slots', serializer.errors)

    def test_create_operation_missing_slots(self):
        """Test create operation validation without slots"""
        data = {
            'operation': 'create'
            # Missing availability_slots
        }

        serializer = AvailabilityBulkSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('availability_slots', serializer.errors)

    def test_duplicate_slots_validation(self):
        """Test duplicate slots validation"""
        data = {
            'operation': 'create',
            'availability_slots': [
                {
                    'day_of_week': 1,
                    'start_time': time(9, 0),
                    'end_time': time(12, 0),
                    'is_recurring': True
                },
                {
                    'day_of_week': 1,
                    'start_time': time(9, 0),
                    'end_time': time(12, 0),
                    'is_recurring': True
                }  # Duplicate slot
            ]
        }

        serializer = AvailabilityBulkSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('availability_slots', serializer.errors)

    def test_too_many_slots_validation(self):
        """Test validation for too many slots"""
        # Create 51 slots (over the limit of 50)
        slots = []
        for i in range(51):
            slots.append({
                'day_of_week': i % 7,
                'start_time': time(9, 0),
                'end_time': time(10, 0),
                'is_recurring': True
            })

        data = {
            'operation': 'create',
            'availability_slots': slots
        }

        serializer = AvailabilityBulkSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('availability_slots', serializer.errors)

    def test_delete_operation_with_slots_validation(self):
        """Test delete operation should not have availability slots"""
        data = {
            'operation': 'delete',
            'slot_ids': [1, 2],
            'availability_slots': [
                {
                    'day_of_week': 1,
                    'start_time': time(9, 0),
                    'end_time': time(12, 0),
                    'is_recurring': True
                }
            ]
        }

        serializer = AvailabilityBulkSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('availability_slots', serializer.errors)
