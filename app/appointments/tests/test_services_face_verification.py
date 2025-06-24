# appointments/tests/test_services_face_verification.py

import io
from datetime import date, timedelta
from unittest.mock import patch

import numpy as np
from PIL import Image
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment, AppointmentSlot
# Correctly importing the service and all its custom exceptions from the top level
from appointments.services.face_verification_service import (
    FaceVerificationService,
    NoFaceDetectedError,
    MultipleFacesDetectedError,
    FaceNotMatchedError,
    ProfilePictureMissingError,
    VerificationWindowExpiredError,
    FaceVerificationError,
)
from children.models import Child
from parents.models import Parent
from psychologists.models import Psychologist
from users.models import User


class FaceVerificationServiceTest(TestCase):
    """
    Test cases for the FaceVerificationService.
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
            first_name="Dr.",
            last_name="FaceTest",
            license_number="PSYTEST123",
            license_issuing_authority="State Board",
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
        )

        # Create a parent user
        cls.parent_user = User.objects.create_user(
            email="parent_face_test@example.com",
            password="testpassword",
            user_type="Parent",
            is_verified=True,
        )
        cls.parent = Parent.objects.get(user=cls.parent_user)

        # Create a child
        cls.child = Child.objects.create(
            parent=cls.parent,
            first_name="Test Child",
            date_of_birth=date(2015, 1, 1),
        )

        # Create a valid appointment
        cls.appointment = Appointment.objects.create(
            child=cls.child,
            psychologist=cls.psychologist,
            parent=cls.parent,
            session_type="InitialConsultation",
            appointment_status="Scheduled",
            scheduled_start_time=timezone.now() + timedelta(minutes=10),
            scheduled_end_time=timezone.now() + timedelta(hours=1, minutes=10),
        )

    def _create_dummy_image(self, color="blue"):
        """Creates a dummy image in memory."""
        img = Image.new("RGB", (100, 100), color=color)
        buffer = io.BytesIO()
        img.save(buffer, "jpeg")
        buffer.seek(0)
        return buffer.read()

    @patch("appointments.services.face_verification_service.face_recognition")
    def test_generate_face_embedding_success(self, mock_face_recognition):
        """Test successful generation of a face embedding."""
        mock_face_recognition.face_encodings.return_value = [np.random.rand(128)]
        image_data = self._create_dummy_image()

        embedding = FaceVerificationService.generate_face_embedding(image_data)
        self.assertIsNotNone(embedding)
        self.assertIsInstance(embedding, bytes)

    @patch("appointments.services.face_verification_service.face_recognition")
    def test_generate_face_embedding_no_face_detected(self, mock_face_recognition):
        """Test that NoFaceDetectedError is raised when no face is found."""
        mock_face_recognition.face_encodings.return_value = []
        image_data = self._create_dummy_image()

        with self.assertRaises(NoFaceDetectedError):
            FaceVerificationService.generate_face_embedding(image_data)

    @patch("appointments.services.face_verification_service.face_recognition")
    def test_generate_face_embedding_multiple_faces_detected(
        self, mock_face_recognition
    ):
        """Test that MultipleFacesDetectedError is raised for multiple faces."""
        mock_face_recognition.face_encodings.return_value = [
            np.random.rand(128),
            np.random.rand(128),
        ]
        image_data = self._create_dummy_image()

        with self.assertRaises(MultipleFacesDetectedError):
            FaceVerificationService.generate_face_embedding(image_data)

    def test_compare_faces_match(self):
        """Test that two similar embeddings are considered a match."""
        embedding1 = np.random.rand(128).tobytes()
        embedding2 = embedding1  # Identical embeddings

        self.assertTrue(FaceVerificationService.compare_faces(embedding1, embedding2))

    def test_compare_faces_no_match(self):
        """Test that two different embeddings do not match."""
        embedding1 = np.random.rand(128).tobytes()
        embedding2 = np.random.rand(128).tobytes()  # Different embeddings

        self.assertFalse(FaceVerificationService.compare_faces(embedding1, embedding2))

    @patch("appointments.services.face_verification_service.face_recognition")
    def test_verify_appointment_parent_success(self, mock_face_recognition):
        """Test the end-to-end verification of an appointment parent."""
        # Setup stored embedding and mock live image
        stored_embedding = np.random.rand(128)
        self.parent.face_embedding = stored_embedding.tobytes()
        self.parent.save()

        mock_face_recognition.face_encodings.return_value = [stored_embedding]
        # Set distance to be well within tolerance for a clear match
        mock_face_recognition.face_distance.return_value = [0.1]
        live_image_data = self._create_dummy_image()

        result = FaceVerificationService.verify_appointment_parent(
            self.appointment, live_image_data, self.psychologist
        )

        self.assertEqual(result["status"], "success")
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.appointment_status, "In_Progress")
        self.assertIsNotNone(self.appointment.session_verified_at)
        self.assertEqual(self.appointment.session_verified_by, self.psychologist)

    @patch("appointments.services.face_verification_service.face_recognition")
    def test_verify_appointment_parent_no_match(self, mock_face_recognition):
        """Test verification failure due to face mismatch."""
        self.parent.face_embedding = np.random.rand(128).tobytes()
        self.parent.save()

        mock_face_recognition.face_encodings.return_value = [np.random.rand(128)]
        # Set distance to be well above tolerance for a clear mismatch
        mock_face_recognition.face_distance.return_value = [0.9]

        with self.assertRaises(FaceNotMatchedError):
            FaceVerificationService.verify_appointment_parent(
                self.appointment, self._create_dummy_image(), self.psychologist
            )

    def test_verify_appointment_parent_no_embedding(self):
        """Test verification failure when parent has no stored embedding."""
        self.parent.face_embedding = None
        self.parent.save()

        with self.assertRaises(ProfilePictureMissingError):
            FaceVerificationService.verify_appointment_parent(
                self.appointment, self._create_dummy_image(), self.psychologist
            )

    def test_verify_appointment_parent_outside_window(self):
        """Test verification failure when outside the allowed time window."""
        self.appointment.scheduled_start_time = timezone.now() - timedelta(hours=1)
        self.appointment.save()

        with self.assertRaises(VerificationWindowExpiredError):
            FaceVerificationService.verify_appointment_parent(
                self.appointment, self._create_dummy_image(), self.psychologist
            )