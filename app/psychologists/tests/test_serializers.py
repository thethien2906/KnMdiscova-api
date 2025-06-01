# psychologists/tests/test_serializers.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, time, timedelta
from decimal import Decimal
from rest_framework.exceptions import ValidationError as DRFValidationError

from users.models import User
from psychologists.models import Psychologist, PsychologistAvailability
from psychologists.serializers import (
    PsychologistSerializer,
    PsychologistProfileUpdateSerializer,
    PsychologistMarketplaceSerializer,
    PsychologistDetailSerializer,
    PsychologistVerificationSerializer,
    PsychologistSearchSerializer,
    PsychologistAvailabilitySerializer,
    PsychologistSummarySerializer,
    EducationEntrySerializer,
    CertificationEntrySerializer,
    PsychologistEducationSerializer,
    PsychologistCertificationSerializer
)


class PsychologistSerializerTestCase(TestCase):
    """Test cases for PsychologistSerializer"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True  # Make user verified for marketplace visibility
        )
        self.psychologist = Psychologist.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            license_number='PSY12345',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            biography='Experienced psychologist',
            education=[{
                'degree': 'PhD Psychology',
                'institution': 'University Test',
                'year': '2015'
            }],
            certifications=[{
                'name': 'Child Psychology Certification',
                'institution': 'Professional Board',
                'year': '2016'
            }],
            verification_status='Approved',
            offers_initial_consultation=True,
            offers_online_sessions=True,
            office_address='123 Test St, Test City',  # Required for initial consultations
            initial_consultation_rate=Decimal('300.00')
        )


    def test_serializer_fields(self):
        """Test that serializer includes all expected fields"""
        serializer = PsychologistSerializer(instance=self.psychologist)
        data = serializer.data

        # Check basic fields
        self.assertEqual(data['first_name'], 'John')
        self.assertEqual(data['last_name'], 'Doe')
        self.assertEqual(data['license_number'], 'PSY12345')
        self.assertEqual(data['email'], 'psychologist@test.com')
        self.assertEqual(data['years_of_experience'], 5)

        # Check computed fields
        self.assertEqual(data['full_name'], 'Dr. John Doe')
        self.assertEqual(data['is_verified'], True)
        self.assertTrue(data['is_marketplace_visible'])
        self.assertTrue(data['license_is_valid'])
        self.assertIn('Online Sessions', data['services_offered'])

    def test_education_validation_valid_structure(self):
        """Test valid education structure passes validation"""
        valid_education = [
            {
                'degree': 'PhD Psychology',
                'institution': 'Test University',
                'year': '2015'
            }
        ]

        serializer = PsychologistSerializer()
        result = serializer.validate_education(valid_education)
        self.assertEqual(result, valid_education)

    def test_education_validation_invalid_structure(self):
        """Test invalid education structure fails validation"""
        # Test non-list input
        with self.assertRaises(DRFValidationError):
            serializer = PsychologistSerializer()
            serializer.validate_education("not a list")

        # Test missing required fields
        invalid_education = [{'degree': 'PhD'}]  # Missing institution and year
        with self.assertRaises(DRFValidationError):
            serializer = PsychologistSerializer()
            serializer.validate_education(invalid_education)

        # Test invalid year
        invalid_year_education = [{
            'degree': 'PhD',
            'institution': 'Test',
            'year': '2050'  # Future year
        }]
        with self.assertRaises(DRFValidationError):
            serializer = PsychologistSerializer()
            serializer.validate_education(invalid_year_education)

    def test_license_expiry_validation(self):
        """Test license expiry date validation"""
        serializer = PsychologistSerializer()

        # Valid future date
        future_date = date.today() + timedelta(days=30)
        result = serializer.validate_license_expiry_date(future_date)
        self.assertEqual(result, future_date)

        # Invalid past date
        past_date = date.today() - timedelta(days=30)
        with self.assertRaises(DRFValidationError):
            serializer.validate_license_expiry_date(past_date)

    def test_cross_field_validation(self):
        """Test cross-field validation rules"""
        # Test office address required for initial consultations - use complete valid data
        invalid_data = {
            'first_name': 'Test',
            'last_name': 'Doctor',
            'license_number': 'PSY999',
            'license_issuing_authority': 'Test Board',
            'license_expiry_date': (date.today() + timedelta(days=365)).isoformat(),
            'years_of_experience': 5,
            'offers_initial_consultation': True,
            'offers_online_sessions': False,
            'office_address': ''  # Empty office address
        }

        serializer = PsychologistSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('office_address', serializer.errors)

        # Test must offer at least one service
        invalid_service_data = {
            'first_name': 'Test',
            'last_name': 'Doctor',
            'license_number': 'PSY998',
            'license_issuing_authority': 'Test Board',
            'license_expiry_date': (date.today() + timedelta(days=365)).isoformat(),
            'years_of_experience': 5,
            'offers_initial_consultation': False,
            'offers_online_sessions': False
        }

        serializer = PsychologistSerializer(data=invalid_service_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('offers_online_sessions', serializer.errors)


class PsychologistProfileUpdateSerializerTestCase(TestCase):
    """Test cases for PsychologistProfileUpdateSerializer"""

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
            license_number='PSY12345',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            offers_initial_consultation=True,
            offers_online_sessions=True,
            office_address='123 Test St'  # Required for initial consultations
        )

    def test_valid_profile_update(self):
        """Test valid profile update data"""
        update_data = {
            'first_name': 'Jane',
            'biography': 'Updated biography',
            'years_of_experience': 7,
            'hourly_rate': '175.00'
        }

        serializer = PsychologistProfileUpdateSerializer(
            instance=self.psychologist,
            data=update_data,
            partial=True
        )

        self.assertTrue(serializer.is_valid())
        updated_psychologist = serializer.save()
        self.assertEqual(updated_psychologist.first_name, 'Jane')
        self.assertEqual(updated_psychologist.biography, 'Updated biography')

    def test_license_number_uniqueness(self):
        """Test license number uniqueness validation"""
        # Create another psychologist
        other_user = User.objects.create_user(
            email='other@test.com',
            password='testpass123',
            user_type='Psychologist'
        )
        Psychologist.objects.create(
            user=other_user,
            first_name='Other',
            last_name='Doc',
            license_number='PSY67890',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=3,
            offers_initial_consultation=False,  # Don't require office address
            offers_online_sessions=True
        )

        # Try to update with existing license number
        update_data = {'license_number': 'PSY67890'}
        serializer = PsychologistProfileUpdateSerializer(
            instance=self.psychologist,
            data=update_data,
            partial=True
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('license_number', serializer.errors)

    def test_name_validation(self):
        """Test name field validation"""
        # Test empty name
        invalid_data = {'first_name': '   '}
        serializer = PsychologistProfileUpdateSerializer(
            instance=self.psychologist,
            data=invalid_data,
            partial=True
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('first_name', serializer.errors)

    def test_rate_validation(self):
        """Test rate validation"""
        # Test negative rate
        invalid_data = {'hourly_rate': '-50.00'}
        serializer = PsychologistProfileUpdateSerializer(
            instance=self.psychologist,
            data=invalid_data,
            partial=True
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('hourly_rate', serializer.errors)


class PsychologistMarketplaceSerializerTestCase(TestCase):
    """Test cases for PsychologistMarketplaceSerializer"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True  # User must be verified
        )
        self.psychologist = Psychologist.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            license_number='PSY12345',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',  # Must be approved
            offers_online_sessions=True,
            offers_initial_consultation=False,  # Don't require office address
            biography='Test biography'
        )

    def test_marketplace_visible_psychologist(self):
        """Test serialization for marketplace-visible psychologist"""
        serializer = PsychologistMarketplaceSerializer(instance=self.psychologist)
        data = serializer.data

        # Should include public information
        self.assertEqual(data['full_name'], 'Dr. John Doe')
        self.assertEqual(data['years_of_experience'], 5)
        self.assertEqual(data['biography'], 'Test biography')
        self.assertIn('Online Sessions', data['services_offered'])

        # Should include MVP pricing information
        self.assertIn('pricing', data)
        pricing = data['pricing']
        self.assertEqual(pricing['currency'], 'USD')
        self.assertEqual(Decimal(str(pricing['online_session_rate'])), Decimal('150.00'))
        self.assertEqual(Decimal(str(pricing['initial_consultation_rate'])), Decimal('280.00'))

        # Should not include sensitive information
        self.assertNotIn('license_number', data)
        self.assertNotIn('admin_notes', data)

    def test_marketplace_invisible_psychologist(self):
        """Test serialization for non-marketplace psychologist"""
        # Make psychologist not marketplace visible
        self.psychologist.verification_status = 'Pending'
        self.psychologist.save()

        serializer = PsychologistMarketplaceSerializer(instance=self.psychologist)
        data = serializer.data

        # Should return empty dict for non-visible psychologists
        self.assertEqual(data, {})

    def test_profile_completeness_calculation(self):
        """Test profile completeness method"""
        serializer = PsychologistMarketplaceSerializer(instance=self.psychologist)
        data = serializer.data

        self.assertIn('profile_completeness', data)
        self.assertIsInstance(data['profile_completeness'], float)

    def test_pricing_for_different_service_offerings(self):
        """Test pricing display for different service combinations"""
        # Test online sessions only
        serializer = PsychologistMarketplaceSerializer(instance=self.psychologist)
        data = serializer.data

        self.assertEqual(data['offers_online_sessions'], True)
        self.assertEqual(data['offers_initial_consultation'], False)
        # Pricing should still show both rates (MVP fixed pricing)
        self.assertIn('pricing', data)

    def test_psychologist_with_both_services(self):
        """Test psychologist offering both services"""
        # Update to offer both services
        self.psychologist.offers_initial_consultation = True
        self.psychologist.office_address = "123 Main St, City, State"
        self.psychologist.save()

        serializer = PsychologistMarketplaceSerializer(instance=self.psychologist)
        data = serializer.data

        # Should show both services
        services = data['services_offered']
        self.assertIn('Online Sessions', services)
        self.assertIn('Initial Consultations', services)

        # Should include office address for initial consultations
        self.assertEqual(data['office_address'], "123 Main St, City, State")

        # Pricing should be the same (MVP fixed rates)
        pricing = data['pricing']
        self.assertEqual(Decimal(str(pricing['online_session_rate'])), Decimal('150.00'))
        self.assertEqual(Decimal(str(pricing['initial_consultation_rate'])), Decimal('280.00'))

    def test_pricing_consistency_across_psychologists(self):
        """Test that all psychologists get the same MVP pricing"""
        # Create another psychologist
        user2 = User.objects.create_user(
            email='psychologist2@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        psychologist2 = Psychologist.objects.create(
            user=user2,
            first_name='Jane',
            last_name='Smith',
            license_number='PSY67890',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,  # Different experience
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address="456 Oak Ave, City, State",
            biography='Different biography'
        )

        # Serialize both psychologists
        serializer1 = PsychologistMarketplaceSerializer(instance=self.psychologist)
        serializer2 = PsychologistMarketplaceSerializer(instance=psychologist2)

        data1 = serializer1.data
        data2 = serializer2.data

        # Pricing should be identical (MVP fixed pricing)
        self.assertEqual(data1['pricing'], data2['pricing'])

        # But other details should be different
        self.assertNotEqual(data1['full_name'], data2['full_name'])
        self.assertNotEqual(data1['years_of_experience'], data2['years_of_experience'])

    def test_serializer_fields_structure(self):
        """Test that all expected fields are present"""
        serializer = PsychologistMarketplaceSerializer(instance=self.psychologist)
        data = serializer.data

        expected_fields = [
            'user', 'full_name', 'years_of_experience', 'biography',
            'offers_initial_consultation', 'offers_online_sessions', 'services_offered',
            'office_address', 'website_url', 'linkedin_url',
            'profile_completeness', 'license_issuing_authority',
            'education', 'certifications', 'created_at', 'pricing'
        ]

        for field in expected_fields:
            self.assertIn(field, data, f"Field '{field}' should be present in serialized data")

    def test_pricing_respects_settings(self):
        """Test that pricing uses values from Django settings"""
        serializer = PsychologistMarketplaceSerializer(instance=self.psychologist)
        data = serializer.data

        pricing = data['pricing']
        self.assertEqual(Decimal(str(pricing['online_session_rate'])), Decimal('150.00'))
        self.assertEqual(Decimal(str(pricing['initial_consultation_rate'])), Decimal('280.00'))


class PsychologistSearchSerializerTestCase(TestCase):
    """Test cases for PsychologistSearchSerializer"""

    def test_valid_search_parameters(self):
        """Test valid search parameters"""
        search_data = {
            'name': 'John Doe',
            'min_years_experience': 5,
            'max_years_experience': 10,
            'offers_online_sessions': True,
            'verification_status': 'Approved'
        }

        serializer = PsychologistSearchSerializer(data=search_data)
        self.assertTrue(serializer.is_valid())

    def test_experience_range_validation(self):
        """Test experience range validation"""
        invalid_data = {
            'min_years_experience': 10,
            'max_years_experience': 5  # min > max
        }

        serializer = PsychologistSearchSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('min_years_experience', serializer.errors)

    def test_rate_range_validation(self):
        """Test rate range validation"""
        invalid_data = {
            'min_hourly_rate': '200.00',
            'max_hourly_rate': '100.00'  # min > max
        }

        serializer = PsychologistSearchSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('min_hourly_rate', serializer.errors)

    def test_date_range_validation(self):
        """Test date range validation"""
        future_date = timezone.now() + timedelta(days=10)
        past_date = timezone.now() - timedelta(days=10)

        invalid_data = {
            'created_after': future_date,
            'created_before': past_date  # after > before
        }

        serializer = PsychologistSearchSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('created_after', serializer.errors)


class PsychologistAvailabilitySerializerTestCase(TestCase):
    """Test cases for PsychologistAvailabilitySerializer"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True  # User must be verified for availability
        )
        self.psychologist = Psychologist.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            license_number='PSY12345',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,  # Only offer online sessions
            offers_initial_consultation=False  # Don't require office address
        )
        self.psychologist.refresh_from_db()



    def test_valid_recurring_availability(self):
        """Test valid recurring availability data"""
        availability_data = {
            'psychologist': self.psychologist.pk,
            'day_of_week': 1,  # Monday
            'start_time': '09:00:00',
            'end_time': '17:00:00',
            'is_recurring': True,
            'specific_date': None  # Not a specific date
        }
        serializer = PsychologistAvailabilitySerializer(data=availability_data)
        self.assertTrue(serializer.is_valid())

        availability = serializer.save()
        self.assertEqual(availability.day_of_week, 1)
        self.assertEqual(availability.start_time, time(9, 0))
        self.assertTrue(availability.is_recurring)

    def test_valid_specific_date_availability(self):
        """Test valid specific date availability"""
        future_date = date.today() + timedelta(days=7)
        availability_data = {
            'psychologist': self.psychologist.pk,
            'day_of_week': 1,
            'start_time': '10:00:00',
            'end_time': '14:00:00',
            'is_recurring': False,
            'specific_date': future_date.isoformat()
        }

        serializer = PsychologistAvailabilitySerializer(data=availability_data)
        self.assertTrue(serializer.is_valid())

    def test_time_validation(self):
        """Test time validation rules"""
        # Test end time before start time
        invalid_data = {
            'psychologist': self.psychologist.pk,
            'day_of_week': 1,
            'start_time': '17:00:00',
            'end_time': '09:00:00',  # Before start time
            'is_recurring': True,
            'specific_date': None
        }

        serializer = PsychologistAvailabilitySerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('end_time', serializer.errors)

    def test_minimum_duration_validation(self):
        """Test minimum duration validation"""
        # Test duration less than 1 hour
        invalid_data = {
            'psychologist': self.psychologist.pk,
            'day_of_week': 1,
            'start_time': '09:00:00',
            'end_time': '09:30:00',  # Only 30 minutes
            'is_recurring': True,
            'specific_date': None  # Not a specific date
        }

        serializer = PsychologistAvailabilitySerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('end_time', serializer.errors)

    def test_recurring_specific_date_validation(self):
        """Test recurring vs specific date validation"""
        # Test recurring with specific date (should fail)
        invalid_data = {
            'psychologist': self.psychologist.pk,
            'day_of_week': 1,
            'start_time': '09:00:00',
            'end_time': '17:00:00',
            'is_recurring': True,
            'specific_date': date.today().isoformat()
        }

        serializer = PsychologistAvailabilitySerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('specific_date', serializer.errors)

        # Test non-recurring without specific date (should fail)
        invalid_data2 = {
            'psychologist': self.psychologist.pk,
            'day_of_week': 1,
            'start_time': '09:00:00',
            'end_time': '17:00:00',
            'is_recurring': False
        }

        serializer2 = PsychologistAvailabilitySerializer(data=invalid_data2)
        self.assertFalse(serializer2.is_valid())
        self.assertIn('specific_date', serializer2.errors)

    def test_past_date_validation(self):
        """Test validation of past specific dates"""
        past_date = date.today() - timedelta(days=1)
        invalid_data = {
            'psychologist': self.psychologist.pk,
            'day_of_week': 1,
            'start_time': '09:00:00',
            'end_time': '17:00:00',
            'is_recurring': False,
            'specific_date': past_date.isoformat()
        }

        serializer = PsychologistAvailabilitySerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('specific_date', serializer.errors)

    def test_computed_fields(self):
        """Test computed fields in serializer"""
        availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_recurring=True
        )

        serializer = PsychologistAvailabilitySerializer(instance=availability)
        data = serializer.data

        self.assertEqual(data['day_name'], 'Monday')
        self.assertEqual(data['duration_hours'], 8.0)
        self.assertEqual(data['max_appointable_slots'], 8)
        self.assertEqual(data['time_range_display'], '09:00 - 17:00')


class EducationCertificationSerializerTestCase(TestCase):
    """Test cases for education and certification serializers"""

    def test_education_entry_serializer(self):
        """Test EducationEntrySerializer"""
        valid_data = {
            'degree': 'PhD Psychology',
            'institution': 'Test University',
            'year': 2015,
            'field_of_study': 'Clinical Psychology'
        }

        serializer = EducationEntrySerializer(data=valid_data)
        self.assertTrue(serializer.is_valid())

        # Test invalid year
        invalid_data = valid_data.copy()
        invalid_data['year'] = 2050  # Future year

        serializer = EducationEntrySerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('year', serializer.errors)

    def test_certification_entry_serializer(self):
        """Test CertificationEntrySerializer"""
        valid_data = {
            'name': 'Board Certification',
            'institution': 'Professional Board',
            'year': 2016,
            'certification_id': 'CERT123'
        }

        serializer = CertificationEntrySerializer(data=valid_data)
        self.assertTrue(serializer.is_valid())

    def test_psychologist_education_serializer(self):
        """Test PsychologistEducationSerializer"""
        user = User.objects.create_user(
            email='test@test.com',
            password='testpass123',
            user_type='Psychologist'
        )
        psychologist = Psychologist.objects.create(
            user=user,
            first_name='Test',
            last_name='Doc',
            license_number='PSY123',
            license_issuing_authority='State',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            offers_online_sessions=True,  # Only offer online sessions
            offers_initial_consultation=False  # Don't require office address
        )

        education_data = {
            'education': [
                {
                    'degree': 'PhD Psychology',
                    'institution': 'Test University',
                    'year': 2015
                }
            ]
        }

        serializer = PsychologistEducationSerializer(data=education_data)
        self.assertTrue(serializer.is_valid())

        updated_psychologist = serializer.update(psychologist, serializer.validated_data)
        self.assertEqual(len(updated_psychologist.education), 1)
        self.assertEqual(updated_psychologist.education[0]['degree'], 'PhD Psychology')

    def test_psychologist_certification_serializer(self):
        """Test PsychologistCertificationSerializer"""
        user = User.objects.create_user(
            email='test2@test.com',
            password='testpass123',
            user_type='Psychologist'
        )
        psychologist = Psychologist.objects.create(
            user=user,
            first_name='Test',
            last_name='Doc',
            license_number='PSY456',
            license_issuing_authority='State',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            offers_online_sessions=True,  # Only offer online sessions
            offers_initial_consultation=False  # Don't require office address
        )

        certification_data = {
            'certifications': [
                {
                    'name': 'Test Certification',
                    'institution': 'Test Board',
                    'year': 2016
                }
            ]
        }

        serializer = PsychologistCertificationSerializer(data=certification_data)
        self.assertTrue(serializer.is_valid())

        updated_psychologist = serializer.update(psychologist, serializer.validated_data)
        self.assertEqual(len(updated_psychologist.certifications), 1)
        self.assertEqual(updated_psychologist.certifications[0]['name'], 'Test Certification')


class PsychologistVerificationSerializerTestCase(TestCase):
    """Test cases for PsychologistVerificationSerializer"""

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
            license_number='PSY12345',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            biography='Complete profile',
            education=[{'degree': 'PhD', 'institution': 'University', 'year': '2015'}],
            offers_online_sessions=True,
            offers_initial_consultation=False,  # Don't require office address
            verification_status='Pending'
        )

    def test_valid_verification_status_change(self):
        """Test valid verification status changes"""
        update_data = {
            'verification_status': 'Approved',
            'admin_notes': 'All requirements met'
        }

        serializer = PsychologistVerificationSerializer(
            instance=self.psychologist,
            data=update_data,
            partial=True
        )

        self.assertTrue(serializer.is_valid())
        updated_psychologist = serializer.save()
        self.assertEqual(updated_psychologist.verification_status, 'Approved')
        self.assertEqual(updated_psychologist.admin_notes, 'All requirements met')

    def test_approval_with_missing_requirements(self):
        """Test approval fails when requirements are missing"""
        # Remove biography to create missing requirement
        self.psychologist.biography = ''
        self.psychologist.save()

        update_data = {'verification_status': 'Approved'}

        serializer = PsychologistVerificationSerializer(
            instance=self.psychologist,
            data=update_data,
            partial=True
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('verification_status', serializer.errors)

    def test_invalid_verification_status(self):
        """Test invalid verification status"""
        update_data = {'verification_status': 'InvalidStatus'}

        serializer = PsychologistVerificationSerializer(
            instance=self.psychologist,
            data=update_data,
            partial=True
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('verification_status', serializer.errors)

    def test_computed_fields(self):
        """Test computed fields in verification serializer"""
        serializer = PsychologistVerificationSerializer(instance=self.psychologist)
        data = serializer.data

        self.assertIn('profile_completeness', data)
        self.assertIn('verification_requirements', data)
        self.assertEqual(data['full_name'], 'Dr. John Doe')
        self.assertEqual(data['email'], 'psychologist@test.com')
        self.assertTrue(data['license_is_valid'])


class PsychologistSummarySerializerTestCase(TestCase):
    """Test cases for PsychologistSummarySerializer"""

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
            license_number='PSY12345',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Test St'  # Required for initial consultations
        )

    def test_summary_serializer_fields(self):
        """Test summary serializer includes correct fields"""
        serializer = PsychologistSummarySerializer(instance=self.psychologist)
        data = serializer.data

        # Should include summary information
        self.assertEqual(data['full_name'], 'Dr. John Doe')
        self.assertEqual(data['email'], 'psychologist@test.com')
        self.assertEqual(data['years_of_experience'], 5)
        self.assertEqual(data['verification_status'], 'Approved')
        self.assertIn('Online Sessions', data['services_offered'])
        self.assertIn('Initial Consultations', data['services_offered'])

        # Should include office address for initial consultations
        self.assertEqual(data['office_address'], '123 Test St')

        # Should not include sensitive information
        self.assertNotIn('license_number', data)
        self.assertNotIn('admin_notes', data)
        self.assertNotIn('biography', data)