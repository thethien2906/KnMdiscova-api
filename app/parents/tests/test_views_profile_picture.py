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

        self.valid_image_url = 'https://whichfaceisreal.blob.core.windows.net/public/realimages/22787.jpeg'
        self.invalid_image_url = 'https://valleyeyecareaz.com/wp-content/uploads/2019/10/Blurry-Vision.jpg'

    @patch('appointments.services.face_verification_service.FaceVerificationService.validate_profile_picture_for_embedding')
    def test_upload_valid_profile_picture_api(self, mock_validate_picture):
        """
        Ensure we can update a parent's profile picture with a valid image URL via the API.
        """
        # Arrange
        mock_validate_picture.return_value = {'valid': True}
        data = {'profile_picture_url': self.valid_image_url}

        # Act
        response = self.client.patch("/api/parents/profile/update_profile/", data, format='json')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.parent.user.refresh_from_db()
        self.assertEqual(self.parent.user.profile_picture_url, self.valid_image_url)
        mock_validate_picture.assert_called_once_with(self.valid_image_url)

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
        response = self.client.patch("/api/parents/profile/update_profile/", data, format='json')
        print(response.data,error_message)  # Debugging output to see the response data
        # Assert
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(error_message, response.data['error'])
        mock_validate_picture.assert_called_once_with(self.invalid_image_url)

    def test_clear_profile_picture_api(self):
        """
        Ensure we can clear a parent's profile picture and its associated face embedding via the API.
        """
        # Arrange
        # First, set a profile picture and a dummy embedding to ensure they get cleared.
        self.parent.user.profile_picture_url = self.valid_image_url
        self.parent.user.save()
        self.parent.face_embedding = b'some_dummy_embedding'
        self.parent.save()

        data = {'profile_picture_url': ''}

        # Act
        response = self.client.patch("/api/parents/profile/update_profile/", data, format='json')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.parent.user.refresh_from_db()
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.user.profile_picture_url, '')
        self.assertIsNone(self.parent.face_embedding)

    def test_unauthenticated_user_cannot_update_profile_picture(self):
        """
        Ensure that an unauthenticated user receives a 401 Unauthorized error.
        """
        # Arrange
        self.client.force_authenticate(user=None)  # De-authenticate
        data = {'profile_picture_url': self.valid_image_url}

        # Act
        response = self.client.patch("/api/parents/profile/update_profile/", data, format='json')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)