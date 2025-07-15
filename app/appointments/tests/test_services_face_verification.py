# app/appointments/tests/test_business_logic_face_verification.py

import io
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import numpy as np
from PIL import Image
from django.test import TestCase
from django.utils import timezone
import pickle

from appointments.models import Appointment
from appointments.services import FaceVerificationService, FaceVerificationError, NoFaceDetectedError, \
    MultipleFacesDetectedError, ParentEmbeddingNotFoundError
from children.models import Child
from parents.models import Parent
from psychologists.models import Psychologist
from users.models import User


class FaceVerificationBusinessLogicTest(TestCase):
    """
    Test cases for the business logic of the face verification flow.
    """

    @classmethod
    def setUpTestData(cls):
        """Set up data for the entire test case class."""
        # Create a psychologist user
        cls.psychologist_user = User.objects.create_user(
            email="psychologist_face_test@example.com",
            password="testpassword",
            user_type="Psychologist",
            is_verified=True,
        )
        cls.psychologist = Psychologist.objects.create(
            user=cls.psychologist_user,
            first_name='Jane',
            last_name='Smith',
            license_number='PSY12345',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State'
        )

        # Create a parent user with a face embedding
        cls.parent_user = User.objects.create_user(
            email="parent_face_test@example.com",
            password="testpassword",
            user_type="Parent",
            is_verified=True,
        )
        cls.parent = Parent.objects.get(user=cls.parent_user)
        # Simulate a stored face embedding
        cls.parent.face_embedding = pickle.dumps(np.random.rand(128))
        cls.parent.save()

        # Create another parent without a face embedding
        cls.parent_user_no_embedding = User.objects.create_user(
            email="parent_no_embedding@example.com",
            password="testpassword",
            user_type="Parent",
            is_verified=True,
        )
        cls.parent_no_embedding = Parent.objects.get(user=cls.parent_user_no_embedding)

        # Create a child for the parent
        cls.child = Child.objects.create(
            parent=cls.parent,
            first_name="Test Child",
            date_of_birth=date(2015, 1, 1),
        )

        # Create a valid 'InitialConsultation' appointment
        cls.initial_consultation_appointment = Appointment.objects.create(
            child=cls.child,
            psychologist=cls.psychologist,
            parent=cls.parent,
            session_type="InitialConsultation",
            appointment_status="Scheduled",
            scheduled_start_time=timezone.now(),
            scheduled_end_time=timezone.now() + timedelta(hours=2),
        )

        # Create an 'OnlineMeeting' appointment for testing incorrect appointment type
        cls.online_meeting_appointment = Appointment.objects.create(
            child=cls.child,
            psychologist=cls.psychologist,
            parent=cls.parent,
            session_type="OnlineMeeting",
            appointment_status="Scheduled",
            scheduled_start_time=timezone.now(),
            scheduled_end_time=timezone.now() + timedelta(hours=1),
        )

    def _create_dummy_image_bytes(self, color="blue"):
        """Creates a dummy image and returns its byte representation."""
        img = Image.new("RGB", (100, 100), color=color)
        buffer = io.BytesIO()
        img.save(buffer, "jpeg")
        buffer.seek(0)
        return buffer.read()

    @patch('appointments.services.face_verification_service.FaceVerificationService._extract_face_encoding_from_bytes')
    @patch('appointments.services.face_verification_service.FaceVerificationService._compare_face_encodings')
    def test_verify_parent_for_initial_consultation_success(self, mock_compare_faces,
                                                            mock_extract_encoding):
        """
        Test the primary success path: a valid face matching the stored embedding for an InitialConsultation.
        """
        # Arrange
        mock_extract_encoding.return_value = np.random.rand(128)
        mock_compare_faces.return_value = True
        live_image_data = self._create_dummy_image_bytes()

        # Act
        result = FaceVerificationService.verify_parent_for_session(
            self.initial_consultation_appointment,
            live_image_data
        )

        # Assert
        self.assertTrue(result['is_match'])
        self.assertTrue(result['appointment_updated'])
        self.assertEqual(result['new_status'], 'In_Progress')

        # Refresh the appointment from the database to check for updates
        self.initial_consultation_appointment.refresh_from_db()
        self.assertEqual(self.initial_consultation_appointment.appointment_status, 'In_Progress')
        self.assertIsNotNone(self.initial_consultation_appointment.session_verified_at)
        self.assertIsNotNone(self.initial_consultation_appointment.actual_start_time)
        self.assertEqual(self.initial_consultation_appointment.session_verified_by, self.psychologist)

    @patch('appointments.services.face_verification_service.FaceVerificationService._extract_face_encoding_from_bytes')
    def test_verify_parent_face_not_matched(self, mock_extract_encoding):
        """
        Test the scenario where the captured face does not match the stored embedding.
        """
        # Arrange
        mock_extract_encoding.return_value = np.random.rand(128)
        # The default comparison will fail because embeddings are different
        live_image_data = self._create_dummy_image_bytes()

        # Act
        result = FaceVerificationService.verify_parent_for_session(
            self.initial_consultation_appointment,
            live_image_data
        )

        # Assert
        self.assertFalse(result['is_match'])
        self.assertFalse(result['appointment_updated'])
        # The appointment status should remain 'Scheduled'
        self.initial_consultation_appointment.refresh_from_db()
        self.assertEqual(self.initial_consultation_appointment.appointment_status, 'Scheduled')

    @patch('appointments.services.face_verification_service.FaceVerificationService._extract_face_encoding_from_bytes',
           side_effect=NoFaceDetectedError("No face detected"))
    def test_verify_parent_no_face_detected_in_live_image(self, mock_extract_encoding):
        """
        Test that a NoFaceDetectedError is raised when the live image contains no face.
        """
        # Arrange
        live_image_data = self._create_dummy_image_bytes()

        # Act & Assert
        with self.assertRaises(NoFaceDetectedError):
            FaceVerificationService.verify_parent_for_session(
                self.initial_consultation_appointment,
                live_image_data
            )

    @patch('appointments.services.face_verification_service.FaceVerificationService._extract_face_encoding_from_bytes',
           side_effect=MultipleFacesDetectedError("Multiple faces detected"))
    def test_verify_parent_multiple_faces_detected_in_live_image(self, mock_extract_encoding):
        """
        Test that a MultipleFacesDetectedError is raised when the live image contains multiple faces.
        """
        # Arrange
        live_image_data = self._create_dummy_image_bytes()

        # Act & Assert
        with self.assertRaises(MultipleFacesDetectedError):
            FaceVerificationService.verify_parent_for_session(
                self.initial_consultation_appointment,
                live_image_data
            )

    def test_verify_parent_no_embedding_stored(self):
        """
        Test that a ParentEmbeddingNotFoundError is raised when the parent has no stored face embedding.
        """
        # Arrange
        appointment_with_no_embedding = Appointment.objects.create(
            child=self.child,
            psychologist=self.psychologist,
            parent=self.parent_no_embedding,
            session_type="InitialConsultation",
            appointment_status="Scheduled",
            scheduled_start_time=timezone.now(),
            scheduled_end_time=timezone.now() + timedelta(hours=2),
        )
        live_image_data = self._create_dummy_image_bytes()

        # Act & Assert
        with self.assertRaises(ParentEmbeddingNotFoundError):
            FaceVerificationService.verify_parent_for_session(
                appointment_with_no_embedding,
                live_image_data
            )

    def test_verify_parent_incorrect_appointment_type(self):
        """
        Test that face verification fails for appointment types other than 'InitialConsultation'.
        """
        # Arrange
        live_image_data = self._create_dummy_image_bytes()

        # Act & Assert
        with self.assertRaises(FaceVerificationError) as cm:
            FaceVerificationService.verify_parent_for_session(
                self.online_meeting_appointment,
                live_image_data
            )
        self.assertIn("only available for Initial Consultations", str(cm.exception))

    def test_verify_parent_incorrect_appointment_status(self):
        """
        Test that face verification fails if the appointment is not in 'Scheduled' status.
        """
        # Arrange
        self.initial_consultation_appointment.appointment_status = 'Completed'
        self.initial_consultation_appointment.save()
        live_image_data = self._create_dummy_image_bytes()

        # Act & Assert
        with self.assertRaises(FaceVerificationError) as cm:
            FaceVerificationService.verify_parent_for_session(
                self.initial_consultation_appointment,
                live_image_data
            )
        self.assertIn("only verify scheduled appointments", str(cm.exception))