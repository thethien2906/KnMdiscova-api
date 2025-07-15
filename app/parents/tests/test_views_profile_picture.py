# app/parents/tests/test_api.py

from unittest.mock import patch

from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse

from users.models import User
from parents.models import Parent


class ParentProfilePictureAPITest(APITestCase):
    """
    Test cases for the API endpoint of the parent profile picture upload flow.
    """

    def setUp(self):
        """Set up test data and authenticate the client."""
        self.parent_user = User.objects.create_user(
            email='parent_api_test@example.com',
            password='testpassword123',
            user_type='Parent',
            is_verified=True,
        )
        self.parent = Parent.objects.get(user=self.parent_user)

        self.client.force_authenticate(user=self.parent_user)

        self.update_url = "/api/parents/profile/update_profile/"
        self.valid_image_url = 'https://whichfaceisreal.blob.core.windows.net/public/realimages/22787.jpeg'
        self.invalid_image_url = 'https://valleyeyecareaz.com/wp-content/uploads/2019/10/Blurry-Vision.jpg'

    # --- CORRECTED CELERY TASK TESTING ADDED VIA ADDITIONAL PATCH ---
    @patch('appointments.tasks.generate_face_embedding_task.delay')
    @patch('appointments.services.face_verification_service.FaceVerificationService.validate_profile_picture_for_embedding')
    def test_upload_valid_profile_picture_api_triggers_task(self, mock_validate_picture, mock_task_delay):
        """
        Ensure we can update a parent's profile picture and that it triggers the Celery task.
        """
        # Arrange
        mock_validate_picture.return_value = {'valid': True}
        data = {'profile_picture_url': self.valid_image_url}

        # Act
        response = self.client.patch(self.update_url, data, format='json')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.parent.user.refresh_from_db()
        self.assertEqual(self.parent.user.profile_picture_url, self.valid_image_url)
        mock_validate_picture.assert_called_once_with(self.valid_image_url)

        # Assert Celery task was called by the signal triggered from the user save
        mock_task_delay.assert_called_once_with(str(self.parent_user.id))


    @patch('appointments.services.face_verification_service.FaceVerificationService.validate_profile_picture_for_embedding')
    def test_upload_profile_picture_with_validation_error_api(self, mock_validate_picture):
        """
        Ensure the API returns a 400 Bad Request when the face validation service returns an error.
        """
        # Arrange
        error_message = "No face detected in the image."
        mock_validate_picture.return_value = {
            'valid': False,
            'error': error_message
        }
        data = {'profile_picture_url': self.invalid_image_url}

        # Act
        response = self.client.patch(self.update_url, data, format='json')
        # Assert
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(error_message, response.data['error'])
        mock_validate_picture.assert_called_once_with(self.invalid_image_url)

    @patch('appointments.tasks.generate_face_embedding_task.delay')
    def test_clear_profile_picture_api_does_not_trigger_task(self, mock_task_delay):
        """
        Ensure clearing a profile picture does not trigger the face embedding task.
        """
        # Arrange
        self.parent.user.profile_picture_url = self.valid_image_url
        self.parent.user.save()
        self.parent.face_embedding = b'some_dummy_embedding'
        self.parent.save()
        mock_task_delay.reset_mock()

        data = {'profile_picture_url': ''}

        # Act
        response = self.client.patch(self.update_url, data, format='json')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.parent.user.refresh_from_db()
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.user.profile_picture_url, '')
        self.assertIsNone(self.parent.face_embedding)

        # Assert Celery task was NOT called because the new URL is empty
        mock_task_delay.assert_not_called()

    def test_unauthenticated_user_cannot_update_profile_picture(self):
        """
        Ensure that an unauthenticated user receives a 401 Unauthorized error.
        """
        # Arrange
        self.client.force_authenticate(user=None)  # De-authenticate
        data = {'profile_picture_url': self.valid_image_url}

        # Act
        response = self.client.patch(self.update_url, data, format='json')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)