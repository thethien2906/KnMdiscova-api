# appointments/tests/test_face_verification_api.py
"""
Tests for face verification API endpoints
"""

import json
from datetime import datetime, timedelta, date
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient
from PIL import Image
import io
import numpy as np

from users.models import User
from parents.models import Parent
from psychologists.models import Psychologist, PsychologistAvailability
from appointments.models import Appointment, AppointmentSlot
from children.models import Child


class FaceVerificationAPITestCase(TestCase):
    """Test cases for face verification API"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()

        # Create psychologist user
        self.psychologist_user = User.objects.create_user(
            email='test_psychologist1@kmdiscova.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True,
        )

        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Test',
            last_name='Psychologist',
            license_number='PSY123451',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        # Create parent user
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            user_type='Parent'
        )
        # Get the auto-created parent profile and update it
        self.parent = self.user.parent_profile
        self.parent.first_name = 'John'
        self.parent.last_name = 'Doe'
        self.parent.phone_number = '+1234567890'
        self.parent.address_line1 = '123 Main St'
        self.parent.city = 'Test City'
        self.parent.state_province = 'Test State'
        self.parent.postal_code = '12345'
        self.parent.country = 'US'
        self.parent.communication_preferences = {
            'email_notifications': True,
            'sms_notifications': False
        }
        self.parent.save()

        # Create child
        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Test',
            last_name='Child',
            date_of_birth='2015-01-01'
        )
        self.availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time='09:00',
            end_time='17:00',
            is_recurring=True
        )
        # Helper function to get next Monday from today
        def get_next_monday():
            today = date.today()
            days_ahead = (7 - today.weekday()) % 7  # Days until Monday
            if days_ahead == 0:
                days_ahead = 7  # If today is Monday, get next Monday
            return today + timedelta(days=days_ahead)

        monday_date = get_next_monday()
        self.slot1 = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=monday_date,
            start_time='11:00',
            end_time='12:00',
            is_booked=True
        )
        self.slot2 = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=monday_date,
            start_time='12:00',
            end_time='13:00',
            is_booked=True
        )

        # Create appointment for Initial Consultation
        scheduled_start_time = timezone.now() - timedelta(minutes=5)
        scheduled_end_time = scheduled_start_time + timedelta(hours=2) # Or whatever your typical appointment duration is


        # Create test appointment for Zoom service tests
        self.appointment = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent,
            scheduled_start_time=scheduled_start_time,
            scheduled_end_time=scheduled_end_time,
            session_type='InitialConsultation',
            appointment_status='Scheduled',
            payment_status='Paid',
        )

        self.appointment.appointment_slots.add(self.slot1, self.slot2)

        # Create test image
        self.test_image = self.create_test_image()

        # Store a fake face embedding for the parent
        self.parent.face_embedding = np.random.rand(128).astype(np.float64).tobytes()
        self.parent.face_embedding_created_at = timezone.now()
        self.parent.save()

    def create_test_image(self):
        """Create a test image file"""
        # Create a simple RGB image
        img = Image.new('RGB', (300, 300), color='white')
        img_io = io.BytesIO()
        img.save(img_io, format='JPEG')
        img_io.seek(0)
        return SimpleUploadedFile('test_face.jpg', img_io.getvalue(), content_type='image/jpeg')

    def test_verify_face_success(self):
        """Test successful face verification"""
        # Authenticate as psychologist
        self.client.force_authenticate(user=self.psychologist_user)

        url = reverse('appointment-verify-face', kwargs={'pk': self.appointment.appointment_id})

        # Mock face recognition functions
        with patch('appointments.services.face_verification_service.face_recognition.face_encodings') as mock_encodings, \
             patch('appointments.services.face_verification_service.face_recognition.face_distance') as mock_distance:

            # Mock successful face detection and match
            mock_encodings.return_value = [np.random.rand(128)]
            mock_distance.return_value = [0.4]  # Below threshold

            response = self.client.post(url, {
                'image': self.create_test_image()
            }, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['message'], 'Session verified successfully.')
        self.assertEqual(response.data['appointment_status'], 'In_Progress')
        self.assertIsNotNone(response.data.get('actual_start_time'))

        # Verify appointment was updated
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.appointment_status, 'In_Progress')
        self.assertIsNotNone(self.appointment.session_verified_at)
        self.assertEqual(self.appointment.session_verified_by, self.psychologist)

    def test_verify_face_no_face_detected(self):
        """Test when no face is detected in image"""
        self.client.force_authenticate(user=self.psychologist_user)

        url = reverse('appointment-verify-face', kwargs={'pk': self.appointment.appointment_id})

        with patch('appointments.services.face_verification_service.face_recognition.face_encodings') as mock_encodings:
            # Mock no face detected
            mock_encodings.return_value = []

            response = self.client.post(url, {
                'image': self.create_test_image()
            }, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'failure')
        self.assertIn('No face detected', response.data['message'])

    def test_verify_face_multiple_faces_detected(self):
        """Test when multiple faces are detected"""
        self.client.force_authenticate(user=self.psychologist_user)

        url = reverse('appointment-verify-face', kwargs={'pk': self.appointment.appointment_id})

        with patch('appointments.services.face_verification_service.face_recognition.face_encodings') as mock_encodings:
            # Mock multiple faces detected
            mock_encodings.return_value = [np.random.rand(128), np.random.rand(128)]

            response = self.client.post(url, {
                'image': self.create_test_image()
            }, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'failure')
        self.assertIn('Multiple faces detected', response.data['message'])

    def test_verify_face_no_match(self):
        """Test when face doesn't match"""
        self.client.force_authenticate(user=self.psychologist_user)

        url = reverse('appointment-verify-face', kwargs={'pk': self.appointment.appointment_id})

        with patch('appointments.services.face_verification_service.face_recognition.face_encodings') as mock_encodings, \
             patch('appointments.services.face_verification_service.face_recognition.face_distance') as mock_distance:

            # Mock face detected but no match
            mock_encodings.return_value = [np.random.rand(128)]
            mock_distance.return_value = [0.8]  # Above threshold

            response = self.client.post(url, {
                'image': self.create_test_image()
            }, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'failure')
        self.assertEqual(response.data['message'], 'Face not recognized.')
        self.assertEqual(response.data['appointment_status'], 'Scheduled')

    def test_verify_face_profile_picture_missing(self):
        """Test when parent has no face embedding"""
        # Remove parent's face embedding
        self.parent.face_embedding = None
        self.parent.save()

        self.client.force_authenticate(user=self.psychologist_user)

        url = reverse('appointment-verify-face', kwargs={'pk': self.appointment.appointment_id})

        response = self.client.post(url, {
            'image': self.create_test_image()
        }, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_428_PRECONDITION_REQUIRED)
        self.assertEqual(response.data['status'], 'failure')
        self.assertIn('profile picture', response.data['message'].lower())

    def test_verify_face_time_window_expired(self):
        """Test verification outside allowed time window"""
        # Set appointment time to past
        self.appointment.scheduled_start_time = timezone.now() - timedelta(hours=2)
        self.appointment.scheduled_end_time = timezone.now()
        self.appointment.save()

        self.client.force_authenticate(user=self.psychologist_user)

        url = reverse('appointment-verify-face', kwargs={'pk': self.appointment.appointment_id})

        response = self.client.post(url, {
            'image': self.create_test_image()
        }, format='multipart')
        print(response.data)  # Debugging output
        self.assertEqual(response.status_code, status.HTTP_408_REQUEST_TIMEOUT)
        self.assertEqual(response.data['status'], 'failure')
        self.assertIn('time window', response.data['message'].lower())

    def test_verify_face_unauthorized_psychologist(self):
        """Test when psychologist tries to verify another's appointment"""
        # Create another psychologist
        other_user = User.objects.create_user(
            email='other@test.com',
            password='testpass123',
            user_type='Psychologist'
        )
        other_psychologist = Psychologist.objects.create(
            user=other_user,
            first_name='Other',
            last_name='Psychologist',
            license_number='PSY99999',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        self.client.force_authenticate(user=other_user)

        url = reverse('appointment-verify-face', kwargs={'pk': self.appointment.appointment_id})

        response = self.client.post(url, {
            'image': self.create_test_image()
        }, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


    # def test_verify_face_base64_endpoint(self):
    #     """Test base64 image endpoint"""
    #     self.client.force_authenticate(user=self.psychologist_user)

    #     url = reverse('appointment-verify-face-base64', kwargs={'pk': self.appointment.appointment_id})

    #     # Create base64 image
    #     img = Image.new('RGB', (300, 300), color='white')
    #     img_io = io.BytesIO()
    #     img.save(img_io, format='JPEG')
    #     img_io.seek(0)
    #     import base64
    #     img_base64 = base64.b64encode(img_io.getvalue()).decode()

    #     with patch('appointments.services.face_verification_service.face_recognition.face_encodings') as mock_encodings, \
    #          patch('appointments.services.face_verification_service.face_recognition.face_distance') as mock_distance:

    #         mock_encodings.return_value = [np.random.rand(128)]
    #         mock_distance.return_value = [0.4]

    #         response = self.client.post(url, {
    #             'image': f'data:image/jpeg;base64,{img_base64}'
    #         }, format='json')

    #     self.assertEqual(response.status_code, status.HTTP_200_OK)
    #     self.assertEqual(response.data['status'], 'success')

    def test_verify_face_invalid_image(self):
        """Test with invalid image data"""
        self.client.force_authenticate(user=self.psychologist_user)

        url = reverse('appointment-verify-face', kwargs={'pk': self.appointment.appointment_id})

        # Create invalid image file
        invalid_file = SimpleUploadedFile('test.txt', b'not an image', content_type='text/plain')

        response = self.client.post(url, {
            'image': invalid_file
        }, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('image', response.data)

    def test_verify_face_unauthenticated(self):
        """Test without authentication"""
        url = reverse('appointment-verify-face', kwargs={'pk': self.appointment.appointment_id})

        response = self.client.post(url, {
            'image': self.create_test_image()
        }, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)