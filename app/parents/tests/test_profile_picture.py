# app/parents/tests/test_business_logic.py

from django.test import TestCase
from unittest.mock import patch, MagicMock
from django.utils import timezone
import numpy as np

from users.models import User
from parents.models import Parent
from parents.services import ParentService, ParentProfileError
from appointments.services.face_verification_service import (
    FaceVerificationService,
    NoFaceDetectedError,
    MultipleFacesDetectedError,
    ImageProcessingError
)

class ParentProfileImageUploadFlow(TestCase):
    """
    Test cases for the business logic of the parent profile picture upload flow.
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
        self.valid_image_url = 'https://whichfaceisreal.blob.core.windows.net/public/realimages/22787.jpeg'
        self.no_face_image_url = 'https://images.pexels.com/photos/346529/pexels-photo-346529.jpeg'
        self.multiple_faces_image_url = 'https://media.gettyimages.com/id/469651008/photo/jimmy-kimmel-live-jimmy-kimmel-live-welcomed-robert-downey-jr-chris-hemsworth-mark-ruffalo.jpg?s=612x612&w=gi&k=20&c=JFawnYTYWTy3SNjiu3iZRL5lURmx46hM_myUxIDm_ho='
        self.blurry_image_url = 'https://valleyeyecareaz.com/wp-content/uploads/2019/10/Blurry-Vision.jpg'

    @patch('appointments.services.face_verification_service.FaceVerificationService.validate_profile_picture_for_embedding')
    def test_valid_profile_picture_upload(self, mock_validate_picture):
        """
        Test that a valid profile picture URL updates the user's profile picture
        and triggers the embedding generation process.
        """
        # Arrange
        mock_validate_picture.return_value = {'valid': True}
        update_data = {'profile_picture_url': self.valid_image_url}

        # Act
        updated_parent = ParentService.update_parent_profile_with_image_validation(self.parent, update_data)

        # Assert
        self.parent_user.refresh_from_db()
        self.assertEqual(self.parent_user.profile_picture_url, self.valid_image_url)
        mock_validate_picture.assert_called_once_with(self.valid_image_url)

    @patch('appointments.services.face_verification_service.FaceVerificationService.validate_profile_picture_for_embedding')
    def test_profile_picture_with_no_face(self, mock_validate_picture):
        """
        Test that uploading a picture with no face results in a ParentProfileError.
        """
        # Arrange
        mock_validate_picture.return_value = {
            'valid': False,
            'error': 'No face detected in the image.'
        }
        update_data = {'profile_picture_url': self.no_face_image_url}

        # Act & Assert
        with self.assertRaises(ParentProfileError) as context:
            ParentService.update_parent_profile_with_image_validation(self.parent, update_data)

        self.assertIn('No face detected', str(context.exception))
        mock_validate_picture.assert_called_once_with(self.no_face_image_url)

    @patch('appointments.services.face_verification_service.FaceVerificationService.validate_profile_picture_for_embedding')
    def test_profile_picture_with_multiple_faces(self, mock_validate_picture):
        """
        Test that uploading a picture with multiple faces results in a ParentProfileError.
        """
        # Arrange
        mock_validate_picture.return_value = {
            'valid': False,
            'error': 'Multiple faces detected in the image.'
        }
        update_data = {'profile_picture_url': self.multiple_faces_image_url}

        # Act & Assert
        with self.assertRaises(ParentProfileError) as context:
            ParentService.update_parent_profile_with_image_validation(self.parent, update_data)

        self.assertIn('Multiple faces detected', str(context.exception))
        mock_validate_picture.assert_called_once_with(self.multiple_faces_image_url)

    @patch('appointments.services.face_verification_service.FaceVerificationService.validate_profile_picture_for_embedding')
    def test_blurry_profile_picture(self, mock_validate_picture):
        """
        Test that uploading a blurry picture results in a ParentProfileError.
        """
        # Arrange
        mock_validate_picture.return_value = {
            'valid': False,
            'error': 'Image is too blurry for face recognition'
        }
        update_data = {'profile_picture_url': self.blurry_image_url}

        # Act & Assert
        with self.assertRaises(ParentProfileError) as context:
            ParentService.update_parent_profile_with_image_validation(self.parent, update_data)

        self.assertIn('Image is too blurry', str(context.exception))
        mock_validate_picture.assert_called_once_with(self.blurry_image_url)

    def test_clearing_profile_picture_removes_embedding(self):
        """
        Test that clearing the profile picture also clears the face embedding.
        """
        # Arrange
        self.parent.face_embedding = b'some_embedding_data'
        self.parent.face_embedding_created_at = timezone.now()
        self.parent.save()

        update_data = {'profile_picture_url': ''}

        # Act
        updated_parent = ParentService.update_parent_profile_with_image_validation(self.parent, update_data)

        # Assert
        self.parent_user.refresh_from_db()
        self.parent.refresh_from_db()
        self.assertEqual(self.parent_user.profile_picture_url, '')
        self.assertIsNone(self.parent.face_embedding)
        self.assertIsNone(self.parent.face_embedding_created_at)

    # --- CORRECTED CELERY TASK TESTING ADDED BELOW ---

    @patch('appointments.tasks.generate_face_embedding_task.delay')
    def test_user_save_with_new_picture_triggers_celery_task(self, mock_task_delay):
        """
        Test that saving the User model with a new profile picture URL triggers the Celery task.
        """
        # Arrange
        self.assertIsNone(self.parent_user.profile_picture_url)

        # Act
        self.parent_user.profile_picture_url = self.valid_image_url
        self.parent_user.save()

        # Assert
        # The task, defined in appointments.tasks, should be called by the signal.
        mock_task_delay.assert_called_once_with(str(self.parent_user.id))

    @patch('appointments.tasks.generate_face_embedding_task.delay')
    def test_user_save_without_picture_change_does_not_trigger_celery_task(self, mock_task_delay):
        """
        Test that re-saving the User model without changing the picture URL does not trigger the task.
        """
        # Arrange
        self.parent_user.profile_picture_url = self.valid_image_url
        self.parent_user.save()
        mock_task_delay.reset_mock() # Reset mock after initial save

        # Act
        # Re-save the user without changing the profile picture URL
        self.parent_user.is_active = False
        self.parent_user.save()

        # Assert
        # The task should not have been called again.
        mock_task_delay.assert_not_called()