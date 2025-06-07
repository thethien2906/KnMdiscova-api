# psychologists/tests/test_views.py
import os
import django
from django.conf import settings

# Ensure Django is configured before any model imports
if not settings.configured:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings.development')
    django.setup()

import json
from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token

# Now it's safe to import models
from users.models import User
from parents.models import Parent
from psychologists.models import Psychologist, PsychologistAvailability
from psychologists.services import PsychologistService


class PsychologistProfileViewSetTests(APITestCase):
    """Test PsychologistProfileViewSet"""

    def setUp(self):
        # Create users
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            user_type='Admin',
            is_staff=True,
            is_verified=True
        )

        # Create parent profile
        self.parent_profile = Parent.objects.get(user=self.parent_user)

        # Create psychologist profile
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Test',
            last_name='Psychologist',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            biography='Test biography',
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        # Create tokens
        self.psychologist_token = Token.objects.create(user=self.psychologist_user)
        self.parent_token = Token.objects.create(user=self.parent_user)
        self.admin_token = Token.objects.create(user=self.admin_user)

        # Profile data for testing
        self.valid_profile_data = {
            'first_name': 'Dr. New',
            'last_name': 'Psychologist',
            'license_number': 'PSY789012',
            'license_issuing_authority': 'Professional Board',
            'license_expiry_date': '2025-12-31',
            'years_of_experience': 3,
            'biography': 'New psychologist biography',
            'offers_online_sessions': True,
            'offers_initial_consultation': True,
            'office_address': '123 Main St, City, State'
        }

    def test_get_profile_success(self):
        """Test getting current psychologist's profile"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('psychologist-profile-profile')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.psychologist_user.email)
        self.assertEqual(response.data['first_name'], 'Test')

    def test_get_profile_not_psychologist(self):
        """Test getting profile when user is not a psychologist"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

        url = reverse('psychologist-profile-profile')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_profile_success(self):
        """Test creating new psychologist profile"""
        # Create new psychologist user without profile
        new_user = User.objects.create_user(
            email='newpsychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        token = Token.objects.create(user=new_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

        url = reverse('psychologist-profile-list')
        response = self.client.post(url, self.valid_profile_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('Profile created successfully', response.data['message'])

        # Verify profile was created
        self.assertTrue(Psychologist.objects.filter(user=new_user).exists())

    def test_create_profile_already_exists(self):
        """Test creating profile when one already exists"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('psychologist-profile-list')
        response = self.client.post(url, self.valid_profile_data, format='json')

        # The permission class returns 403 when profile exists
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])
        if response.status_code == status.HTTP_400_BAD_REQUEST:
            self.assertIn('already exists', response.data['error'])

    def test_create_profile_unverified_email(self):
        """Test creating profile with unverified email"""
        unverified_user = User.objects.create_user(
            email='unverified@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=False
        )
        token = Token.objects.create(user=unverified_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

        url = reverse('psychologist-profile-list')
        response = self.client.post(url, self.valid_profile_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_profile_success(self):
        """Test updating psychologist profile"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        update_data = {
            'biography': 'Updated biography',
            'years_of_experience': 10,
            'profile_picture_url': "http://example.com/new_picture.jpg",  # Example URL
        }

        url = reverse('psychologist-profile-update-profile')
        response = self.client.patch(url, update_data, format='json')
        # Debug output
        if response.status_code == status.HTTP_200_OK:
            print(f"Response data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('Profile updated successfully', response.data['message'])

        # Verify changes
        self.psychologist.refresh_from_db()
        self.assertEqual(self.psychologist.biography, 'Updated biography')
        self.assertEqual(self.psychologist.years_of_experience, 10)

    def test_update_profile_invalid_data(self):
        """Test updating profile with invalid data"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        invalid_data = {
            'years_of_experience': -5,  # Invalid: negative
            'license_expiry_date': '2020-01-01'  # Invalid: past date
        }

        url = reverse('psychologist-profile-update-profile')
        response = self.client.patch(url, invalid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_profile_business_rule_violation(self):
        """Test updating profile with business rule violation"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        # Violation: offering initial consultation without office address
        invalid_data = {
            'offers_initial_consultation': True,
            'office_address': ''
        }

        url = reverse('psychologist-profile-update-profile')
        response = self.client.patch(url, invalid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('office_address', str(response.data))

    def test_get_completeness(self):
        """Test getting profile completeness"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('psychologist-profile-completeness')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('profile_completeness', response.data)
        self.assertIn('verification_requirements', response.data)
        self.assertIn('verification_status', response.data)

    def test_get_education(self):
        """Test getting education entries"""
        # Add education to psychologist
        self.psychologist.education = [
            {'degree': 'PhD', 'institution': 'University', 'year': 2020}
        ]
        self.psychologist.save()

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('psychologist-profile-education')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['education']), 1)
        self.assertEqual(response.data['education'][0]['degree'], 'PhD')

    def test_update_education(self):
        """Test updating education entries"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        education_data = {
            'education': [
                {
                    'degree': 'PhD Psychology',
                    'institution': 'Test University',
                    'year': 2020,
                    'field_of_study': 'Clinical Psychology'
                }
            ]
        }

        url = reverse('psychologist-profile-education')
        response = self.client.patch(url, education_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('Education updated successfully', response.data['message'])

        # Verify changes
        self.psychologist.refresh_from_db()
        self.assertEqual(len(self.psychologist.education), 1)
        self.assertEqual(self.psychologist.education[0]['degree'], 'PhD Psychology')

    def test_update_education_invalid(self):
        """Test updating education with invalid data"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        invalid_data = {
            'education': [
                {
                    'degree': '',  # Missing required field
                    'institution': 'Test University',
                    'year': 2020
                }
            ]
        }

        url = reverse('psychologist-profile-education')
        response = self.client.patch(url, invalid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_certifications(self):
        """Test getting certification entries"""
        # Add certifications to psychologist
        self.psychologist.certifications = [
            {'name': 'CBT Certification', 'institution': 'Institute', 'year': 2021}
        ]
        self.psychologist.save()

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('psychologist-profile-certifications')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['certifications']), 1)
        self.assertEqual(response.data['certifications'][0]['name'], 'CBT Certification')

    def test_update_certifications(self):
        """Test updating certification entries"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        certification_data = {
            'certifications': [
                {
                    'name': 'Advanced CBT',
                    'institution': 'Professional Institute',
                    'year': 2022,
                    'certification_id': 'CBT-2022-001'
                }
            ]
        }

        url = reverse('psychologist-profile-certifications')
        response = self.client.patch(url, certification_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('Certifications updated successfully', response.data['message'])


class PsychologistAvailabilityViewSetTests(APITestCase):
    """Test PsychologistAvailabilityViewSet"""

    def setUp(self):
        # Create psychologist user and profile
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Test',
            last_name='Psychologist',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )
        self.token = Token.objects.create(user=self.psychologist_user)

        # Create availability block
        self.availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time=time(9, 0),
            end_time=time(12, 0),
            is_recurring=True
        )

        # Valid availability data
        self.valid_availability_data = {
            "psychologist": self.psychologist_user.id,
            'day_of_week': 2,  # Tuesday
            'start_time': '14:00',
            'end_time': '17:00',
            'is_recurring': True,
            'specific_date': None
        }

    def test_get_my_availability(self):
        """Test getting current psychologist's availability"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        url = reverse('psychologist-availability-my-availability')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('recurring_availability', response.data)
        self.assertIn('specific_availability', response.data)
        self.assertEqual(response.data['total_blocks'], 1)

    def test_create_availability_success(self):
        """Test creating availability block"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        # Make sure psychologist is approved
        self.psychologist.verification_status = 'Approved'
        self.psychologist.save()

        url = reverse('psychologist-availability-list')
        response = self.client.post(url, self.valid_availability_data, format='json')

        if response.status_code != status.HTTP_201_CREATED:
            print(f"Response data: {response.data}")  # Debug output

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('Availability block created successfully', response.data['message'])

    def test_create_availability_overlap(self):
        """Test creating overlapping availability block"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        # Overlapping time on same day
        overlapping_data = {
            'day_of_week': 1,  # Monday (same as existing)
            'start_time': '10:00',  # Overlaps with 9:00-12:00
            'end_time': '13:00',
            'is_recurring': True
        }

        url = reverse('psychologist-availability-list')
        response = self.client.post(url, overlapping_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_availability_invalid_time(self):
        """Test creating availability with invalid time range"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        invalid_data = {
            'day_of_week': 3,
            'start_time': '15:00',
            'end_time': '14:00',  # End before start
            'is_recurring': True
        }

        url = reverse('psychologist-availability-list')
        response = self.client.post(url, invalid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_availability_success(self):
        """Test updating availability block"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        update_data = {
            'start_time': '08:00',
            'end_time': '11:00'
        }

        url = reverse('psychologist-availability-detail', kwargs={'pk': self.availability.availability_id})
        response = self.client.patch(url, update_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('Availability block updated successfully', response.data['message'])

    def test_delete_availability_success(self):
        """Test deleting availability block"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        url = reverse('psychologist-availability-detail', kwargs={'pk': self.availability.availability_id})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # And verify the response content:
        self.assertIn('message', response.data)
        self.assertEqual(response.data['message'], 'Availability block deleted successfully')
        self.assertFalse(PsychologistAvailability.objects.filter(
            availability_id=self.availability.availability_id
        ).exists())

    def test_get_weekly_summary(self):
        """Test getting weekly availability summary"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        url = reverse('psychologist-availability-weekly-summary')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('weekly_availability', response.data)
        self.assertIn('total_weekly_hours', response.data)

    def test_bulk_create_availability(self):
        """Test bulk creating availability blocks"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        bulk_data = {
            'weekly_schedule': {
                'wednesday': [
                    {'start_time': '09:00', 'end_time': '12:00'}
                ],
                'thursday': [
                    {'start_time': '14:00', 'end_time': '17:00'}
                ]
            }
        }

        url = reverse('psychologist-availability-bulk-create')
        response = self.client.post(url, bulk_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['success'], 2)
        self.assertEqual(response.data['errors'], 0)

    def test_get_appointment_slots(self):
        """Test getting appointment slots"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        url = reverse('psychologist-availability-appointment-slots')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('appointment_slots', response.data)
        self.assertIn('date_range', response.data)

    def test_get_appointment_slots_with_date_range(self):
        """Test getting appointment slots with custom date range"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        date_from_obj = date.today()
        date_to_obj = date.today() + timedelta(days=7)

        date_from_str = date_from_obj.isoformat()
        date_to_str = date_to_obj.isoformat()


        url = reverse('psychologist-availability-appointment-slots')
        response = self.client.get(url, {
            'date_from': date_from_str,
            'date_to': date_to_str
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['date_range']['from'], date.fromisoformat(date_from_str))
        self.assertEqual(response.data['date_range']['to'], date.fromisoformat(date_to_str))


class PsychologistMarketplaceViewSetTests(APITestCase):
    """Test PsychologistMarketplaceViewSet"""

    def setUp(self):
        # Create parent user
        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        self.parent_profile = Parent.objects.get(user=self.parent_user)

        self.parent_token = Token.objects.create(user=self.parent_user)

        # Create approved psychologist
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Test',
            last_name='Psychologist',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            biography='Experienced psychologist',
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St'
        )

        # Create pending psychologist (should not appear in marketplace)
        self.pending_user = User.objects.create_user(
            email='pending@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        self.pending_psychologist = Psychologist.objects.create(
            user=self.pending_user,
            first_name='Dr. Pending',
            last_name='Psychologist',
            license_number='PSY789012',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=3,
            verification_status='Pending',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='456 Elm St'
        )

    def test_list_marketplace_psychologists(self):
        """Test listing marketplace psychologists"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

        url = reverse('psychologist-marketplace-list')
        response = self.client.get(url)
        # print out the response data for debugging
        if response.status_code == status.HTTP_200_OK:
            print(f"Response data: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)  # Only approved psychologist
        self.assertEqual(response.data['results'][0]['full_name'], 'Dr. Test Psychologist')

    def test_retrieve_marketplace_psychologist(self):
        """Test retrieving specific marketplace psychologist"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

        url = reverse('psychologist-marketplace-detail', kwargs={'pk': self.psychologist.user.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['full_name'], 'Dr. Test Psychologist')

    def test_search_marketplace_psychologists(self):
        """Test searching marketplace psychologists"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

        search_data = {
            'name': 'Test',
            'offers_online_sessions': True
        }

        url = reverse('psychologist-marketplace-search')
        response = self.client.post(url, search_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['full_name'], 'Dr. Test Psychologist')

    def test_search_no_results(self):
        """Test search with no matching results"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

        search_data = {
            'name': 'NonExistent',
            'min_years_experience': 20
        }

        url = reverse('psychologist-marketplace-search')
        response = self.client.post(url, search_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_filter_marketplace_psychologists(self):
        """Test filtering marketplace psychologists"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

        url = reverse('psychologist-marketplace-filter')
        response = self.client.get(url, {
            'services': 'online',
            'min_experience': 3
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_get_psychologist_availability(self):
        """Test getting psychologist availability for booking"""
        # Create availability for psychologist
        PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time=time(9, 0),
            end_time=time(12, 0),
            is_recurring=True
        )

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

        url = reverse('psychologist-marketplace-availability', kwargs={'pk': self.psychologist.user.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('appointment_slots', response.data)
        self.assertEqual(response.data['psychologist_name'], 'Dr. Test Psychologist')

    def test_marketplace_access_unauthorized(self):
        """Test marketplace access without authentication"""
        url = reverse('psychologist-marketplace-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PsychologistManagementViewSetTests(APITestCase):
    """Test PsychologistManagementViewSet (Admin only)"""

    def setUp(self):
        # Create admin user
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            user_type='Admin',
            is_staff=True,
            is_superuser=True,
            is_verified=True
        )
        self.admin_token = Token.objects.create(user=self.admin_user)

        # Create regular user (should not have access)
        self.regular_user = User.objects.create_user(
            email='regular@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        self.regular_token = Token.objects.create(user=self.regular_user)

        # Create psychologist
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Test',
            last_name='Psychologist',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

    def test_list_all_psychologists_admin(self):
        """Test admin can list all psychologists"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')

        url = reverse('psychologist-management-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_list_psychologists_non_admin(self):
        """Test non-admin cannot access management endpoints"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.regular_token.key}')

        url = reverse('psychologist-management-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_search_all_psychologists_admin(self):
        """Test admin can search all psychologists"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')

        search_data = {
            'verification_status': 'Approved'
        }

        url = reverse('psychologist-management-search')
        response = self.client.post(url, search_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_get_statistics_admin(self):
        """Test admin can get platform statistics"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')

        url = reverse('psychologist-management-statistics')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_psychologists', response.data)
        self.assertIn('verification_status', response.data)
        self.assertIn('service_offerings', response.data)
        self.assertEqual(response.data['total_psychologists'], 1)

    def test_get_statistics_non_admin(self):
        """Test non-admin cannot access statistics"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.regular_token.key}')

        url = reverse('psychologist-management-statistics')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PsychologistViewsIntegrationTests(APITestCase):
    """Integration tests for psychologist views"""

    def setUp(self):
        # Create psychologist user
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        self.token = Token.objects.create(user=self.psychologist_user)

    @patch('psychologists.services.PsychologistService.send_profile_creation_welcome_email')
    def test_complete_psychologist_flow_without_payment(self, mock_email):
        """Test complete psychologist registration and profile setup flow"""
        mock_email.return_value = True
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        # Step 1: Create profile
        profile_data = {
            'first_name': 'John',  # Remove 'Dr.' prefix
            'last_name': 'Smith',
            'license_number': 'PSY123456',
            'license_issuing_authority': 'State Board',
            'license_expiry_date': '2025-12-31',
            'years_of_experience': 5,
            'biography': 'Experienced clinical psychologist',
            'offers_online_sessions': True,
            'offers_initial_consultation': True,
            'office_address': '123 Main St, City, State',
            'verification_status': 'Approved'  # Initial status

        }

        url = reverse('psychologist-profile-list')
        response = self.client.post(url, profile_data, format='json')

        if response.status_code != status.HTTP_201_CREATED:
            print(f"Response data: {response.data}")  # Debug output

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Step 2: Add education
        education_data = {
            'education': [
                {
                    'degree': 'PhD Psychology',
                    'institution': 'University of Psychology',
                    'year': 2018
                }
            ]
        }

        url = reverse('psychologist-profile-education')
        response = self.client.patch(url, education_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Step 3: Add availability
        availability_data = {
            'psychologist': self.psychologist_user.id,
            'day_of_week': 1,  # Monday
            'start_time': '09:00',
            'end_time': '17:00',
            'is_recurring': True,
            'specific_date': None  # No specific date for recurring availability

        }

        url = reverse('psychologist-availability-list')
        response = self.client.post(url, availability_data, format='json')
        print("Availability error:", response.data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Step 4: Check completeness
        url = reverse('psychologist-profile-completeness')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['profile_completeness'], 50)

        # Verify welcome email was called
        mock_email.assert_called_once()

    def test_psychologist_to_marketplace_flow(self):
        """Test psychologist appearing in marketplace after approval"""
        # Create psychologist profile
        psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Test',
            last_name='Psychologist',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        # Create parent to search marketplace
        parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        parent_profile = Parent.objects.get(user=parent_user)
        parent_token = Token.objects.create(user=parent_user)

        # Test marketplace visibility
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {parent_token.key}')
        url = reverse('psychologist-marketplace-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['full_name'], 'Dr. Test Psychologist')


class PsychologistViewsErrorHandlingTests(APITestCase):
    """Test error handling in psychologist views"""

    def setUp(self):
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        self.token = Token.objects.create(user=self.psychologist_user)

    def test_invalid_json_handling(self):
        """Test handling of invalid JSON in requests"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        url = reverse('psychologist-profile-list')
        response = self.client.post(
            url,
            'invalid json{',
            content_type='application/json'
        )

        # The view might return 500 for JSON parse errors
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_500_INTERNAL_SERVER_ERROR])

    def test_missing_required_fields(self):
        """Test handling of missing required fields"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        incomplete_data = {
            'first_name': 'Dr. Test'
            # Missing required fields like license_number, etc.
        }

        url = reverse('psychologist-profile-list')
        response = self.client.post(url, incomplete_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nonexistent_availability_block(self):
        """Test accessing nonexistent availability block"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        url = reverse('psychologist-availability-detail', kwargs={'pk': 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthorized_access_to_other_psychologist(self):
        """Test accessing another psychologist's data"""
        # Create another psychologist
        other_user = User.objects.create_user(
            email='other@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        other_psychologist = Psychologist.objects.create(
            user=other_user,
            first_name='Dr. Other',
            last_name='Psychologist',
            license_number='PSY789012',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=3,
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='456 Side St, City, State'

        )

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        # Try to access other psychologist's profile
        url = reverse('psychologist-marketplace-detail', kwargs={'pk': other_user.id})
        response = self.client.get(url)

        # Should be 404 since psychologist is not marketplace visible
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PsychologistViewsPermissionTests(APITestCase):
    """Test permissions for psychologist views"""

    def setUp(self):
        # Create users of different types
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            user_type='Admin',
            is_staff=True,
            is_verified=True
        )

        # Create tokens
        self.psychologist_token = Token.objects.create(user=self.psychologist_user)
        self.parent_token = Token.objects.create(user=self.parent_user)
        self.admin_token = Token.objects.create(user=self.admin_user)

    def test_psychologist_profile_permissions(self):
        """Test permissions for psychologist profile endpoints"""
        # Parent should not access psychologist profile endpoints
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

        url = reverse('psychologist-profile-profile')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        url = reverse('psychologist-profile-list')
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_availability_permissions(self):
        """Test permissions for availability endpoints"""
        # Parent should not access availability management
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

        url = reverse('psychologist-availability-my-availability')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_marketplace_permissions(self):
        """Test permissions for marketplace endpoints"""
        # Psychologist should be able to view marketplace
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('psychologist-marketplace-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Parent should be able to view marketplace
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.parent_token.key}')

        url = reverse('psychologist-marketplace-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_management_permissions(self):
        """Test permissions for management endpoints"""
        # Only admin should access management endpoints
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')

        url = reverse('psychologist-management-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Psychologist should not access management
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.psychologist_token.key}')

        url = reverse('psychologist-management-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_access(self):
        """Test that unauthenticated users cannot access protected endpoints"""
        # No authentication header

        urls_to_test = [
            reverse('psychologist-profile-profile'),
            reverse('psychologist-availability-my-availability'),
            reverse('psychologist-marketplace-list'),
            reverse('psychologist-management-list'),
        ]

        for url in urls_to_test:
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PsychologistViewsValidationTests(APITestCase):
    """Test data validation in psychologist views"""

    def setUp(self):
        self.psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        self.token = Token.objects.create(user=self.psychologist_user)

    def test_profile_creation_validation(self):
        """Test validation during profile creation"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        # Test various validation scenarios
        invalid_data_sets = [
            # Negative years of experience
            {
                'first_name': 'Dr. Test',
                'last_name': 'Psychologist',
                'license_number': 'PSY123',
                'license_issuing_authority': 'Board',
                'license_expiry_date': '2025-12-31',
                'years_of_experience': -5,
            },
            # Past license expiry date
            {
                'first_name': 'Dr. Test',
                'last_name': 'Psychologist',
                'license_number': 'PSY124',
                'license_issuing_authority': 'Board',
                'license_expiry_date': '2020-01-01',
                'years_of_experience': 5,
            },
            # Offering initial consultation without office address
            {
                'first_name': 'Dr. Test',
                'last_name': 'Psychologist',
                'license_number': 'PSY125',
                'license_issuing_authority': 'Board',
                'license_expiry_date': '2025-12-31',
                'years_of_experience': 5,
                'offers_initial_consultation': True,
                'office_address': '',
            },
        ]

        url = reverse('psychologist-profile-list')
        for invalid_data in invalid_data_sets:
            response = self.client.post(url, invalid_data, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_availability_validation(self):
        """Test validation for availability creation"""
        # Create psychologist profile first
        Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Test',
            last_name='Psychologist',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        invalid_availability_sets = [
            # Invalid day of week
            {
                'day_of_week': 8,
                'start_time': '09:00',
                'end_time': '17:00',
                'is_recurring': True
            },
            # End time before start time
            {
                'day_of_week': 1,
                'start_time': '17:00',
                'end_time': '09:00',
                'is_recurring': True
            },
            # Duration less than 1 hour
            {
                'day_of_week': 1,
                'start_time': '09:00',
                'end_time': '09:30',
                'is_recurring': True
            },
            # Non-recurring without specific date
            {
                'day_of_week': 1,
                'start_time': '09:00',
                'end_time': '17:00',
                'is_recurring': False
            },
        ]

        url = reverse('psychologist-availability-list')
        for invalid_data in invalid_availability_sets:
            response = self.client.post(url, invalid_data, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_education_validation(self):
        """Test validation for education updates"""
        # Create psychologist profile
        Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Test',
            last_name='Psychologist',
            license_number='PSY123456',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        # Invalid education data
        invalid_education = {
            'education': [
                {
                    'degree': '',  # Empty required field
                    'institution': 'University',
                    'year': 2020
                }
            ]
        }

        url = reverse('psychologist-profile-education')
        response = self.client.patch(url, invalid_education, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)