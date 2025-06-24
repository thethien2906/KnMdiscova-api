# app/parents/tests/test_face_verification_business.py

from django.test import TestCase
from unittest.mock import patch, MagicMock
from django.utils import timezone
import numpy as np

from users.models import User
from parents.models import Parent
from appointments.services.face_verification_service import (
    FaceVerificationService,
    NoFaceDetectedError,
    MultipleFacesDetectedError,
)
from parents.signals import trigger_face_embedding_generation

class FaceVerificationBusinessLogicTest(TestCase):
    """
    Test cases for the face verification business logic,
    focusing on the FaceVerificationService and related signals.
    """

    def setUp(self):
        """Set up test data"""
        self.parent_user = User.objects.create_user(
            email='parent_test@example.com',
            password='testpassword123',
            user_type='Parent',
            is_verified=True,
        )
        self.parent = Parent.objects.get(user=self.parent_user)

    def create_mock_image_data(self, faces=1):
        """Creates mock image data and patches face_recognition."""
        if faces == 0:
            return patch('face_recognition.face_encodings', return_value=[])
        elif faces > 1:
            return patch('face_recognition.face_encodings', return_value=[np.random.rand(128), np.random.rand(128)])
        else:
            return patch('face_recognition.face_encodings', return_value=[np.random.rand(128)])

    def test_generate_face_embedding_single_face(self):
        """Test generating a face embedding from an image with a single face."""
        with self.create_mock_image_data(faces=1):
            embedding = FaceVerificationService.generate_face_embedding(b'fake_image_data')
            self.assertIsNotNone(embedding)

    def test_generate_face_embedding_no_face(self):
        """Test that NoFaceDetectedError is raised for an image with no faces."""
        with self.create_mock_image_data(faces=0):
            with self.assertRaises(NoFaceDetectedError):
                FaceVerificationService.generate_face_embedding(b'fake_image_data')

    def test_generate_face_embedding_multiple_faces(self):
        """Test that MultipleFacesDetectedError is raised for an image with multiple faces."""
        with self.create_mock_image_data(faces=2):
            with self.assertRaises(MultipleFacesDetectedError):
                FaceVerificationService.generate_face_embedding(b'fake_image_data')

    def test_compare_faces_matching(self):
        """Test comparing two matching face embeddings."""
        embedding1 = np.random.rand(128).tobytes()
        embedding2 = embedding1  # Identical embeddings
        self.assertTrue(FaceVerificationService.compare_faces(embedding1, embedding2))

    def test_compare_faces_not_matching(self):
        """Test comparing two non-matching face embeddings."""
        embedding1 = np.random.rand(128).tobytes()
        embedding2 = np.random.rand(128).tobytes()  # Different embeddings
        self.assertFalse(FaceVerificationService.compare_faces(embedding1, embedding2))

    @patch('appointments.services.face_verification_service.FaceVerificationService.generate_face_embedding')
    def test_update_parent_face_embedding(self, mock_generate_embedding):
        """Test updating the parent's face embedding."""
        mock_embedding = np.random.rand(128).tobytes()
        mock_generate_embedding.return_value = mock_embedding

        FaceVerificationService.update_parent_face_embedding(self.parent, b'fake_image_data')

        self.parent.refresh_from_db()
        self.assertEqual(self.parent.face_embedding, mock_embedding)
        self.assertIsNotNone(self.parent.face_embedding_created_at)

    @patch('parents.signals.generate_face_embedding_task.delay')
    def test_signal_triggers_on_profile_picture_update(self, mock_task_delay):
        """Test that the signal triggers the Celery task on profile picture update."""
        self.parent_user.profile_picture_url = 'http://example.com/new_picture.jpg'
        self.parent_user.save()
        mock_task_delay.assert_called_once_with(str(self.parent_user.id))

    @patch('parents.signals.generate_face_embedding_task.delay')
    def test_signal_not_triggered_for_other_updates(self, mock_task_delay):
        """Test that the signal is not triggered for other user updates."""
        self.parent_user.email = 'new_email@example.com'
        self.parent_user.save()
        mock_task_delay.assert_not_called()