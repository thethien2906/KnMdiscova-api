# appointments/tests/test_face_verification_tasks.py
"""
Tests for face verification Celery tasks
"""

from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from celery.exceptions import Retry
import numpy as np
import requests

from users.models import User
from parents.models import Parent
from appointments.tasks import (
    generate_face_embedding_task,
    bulk_generate_face_embeddings_task
)


class FaceVerificationTasksTestCase(TestCase):
    """Test cases for face verification Celery tasks"""

    def setUp(self):
        """Set up test data"""
        # Create parent user with profile picture
        self.parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True,
            profile_picture_url='https://example.com/profile.jpg'
        )

        # Get the auto-created parent profile and update it
        self.parent = self.parent_user.parent_profile
        self.parent.first_name = 'Test'
        self.parent.last_name = 'Parent'
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

    @patch('appointments.tasks.requests.get')
    @patch('appointments.services.face_verification_service.FaceVerificationService.generate_face_embedding')
    def test_generate_face_embedding_task_success(self, mock_generate_embedding, mock_requests_get):
        """Test successful face embedding generation"""
        # Mock successful image download
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'fake_image_data'
        mock_requests_get.return_value = mock_response

        # Mock successful embedding generation
        mock_embedding = np.random.rand(128).astype(np.float64).tobytes()
        mock_generate_embedding.return_value = mock_embedding

        # Run task
        result = generate_face_embedding_task(str(self.parent_user.id))

        self.assertTrue(result['success'])
        self.assertEqual(result['user_id'], str(self.parent_user.id))
        self.assertEqual(result['parent_id'], str(self.parent.user_id))
        self.assertTrue(result['embedding_created'])

        # Verify image was downloaded
        mock_requests_get.assert_called_once_with(
            'https://example.com/profile.jpg',
            timeout=30
        )

    def test_generate_face_embedding_task_non_parent_user(self):
        """Test task with non-parent user"""
        # Create psychologist user
        psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            profile_picture_url='https://example.com/profile.jpg'
        )

        result = generate_face_embedding_task(str(psychologist_user.id))

        self.assertFalse(result['success'])
        self.assertEqual(result['reason'], 'User is not a parent')

    def test_generate_face_embedding_task_no_profile_picture(self):
        """Test task when user has no profile picture"""
        self.parent_user.profile_picture_url = None
        self.parent_user.save()

        result = generate_face_embedding_task(str(self.parent_user.id))

        self.assertFalse(result['success'])
        self.assertEqual(result['reason'], 'No profile picture')

    def test_generate_face_embedding_task_user_not_found(self):
        """Test task with invalid user ID"""
        fake_user_id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'

        result = generate_face_embedding_task(fake_user_id)

        self.assertFalse(result['success'])
        self.assertEqual(result['reason'], 'User not found')

    @patch('appointments.tasks.requests.get')
    @patch('appointments.tasks.generate_face_embedding_task.retry')
    def test_generate_face_embedding_task_download_failure(self, mock_retry, mock_requests_get):
        """Test that the task retries when image download fails"""

        # Simulate a failed image download (HTTP 404)
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_requests_get.return_value = mock_response

        # Make .retry raise Retry so we can assert it happens
        mock_retry.side_effect = Retry("Mock retry")

        with self.assertRaises(Retry):
            generate_face_embedding_task.run(str(self.parent_user.id))

        mock_retry.assert_called_once()


    @patch('appointments.tasks.default_storage.open')
    @patch('appointments.services.face_verification_service.FaceVerificationService.generate_face_embedding')
    def test_generate_face_embedding_task_local_storage(self, mock_generate_embedding, mock_storage_open):
        """Test task with local file storage"""
        # Update user to use local storage path
        self.parent_user.profile_picture_url = 'media/profiles/user_123.jpg'
        self.parent_user.save()

        # Mock file read
        mock_file = MagicMock()
        mock_file.read.return_value = b'fake_image_data'
        mock_storage_open.return_value.__enter__.return_value = mock_file

        # Mock successful embedding generation
        mock_embedding = np.random.rand(128).astype(np.float64).tobytes()
        mock_generate_embedding.return_value = mock_embedding

        result = generate_face_embedding_task(str(self.parent_user.id))

        self.assertTrue(result['success'])
        mock_storage_open.assert_called_once_with('media/profiles/user_123.jpg', 'rb')

    @patch('appointments.tasks.generate_face_embedding_task.delay')
    def test_bulk_generate_face_embeddings_task(self, mock_delay):
        """Test bulk face embedding generation"""
        # Create multiple parents with profile pictures but no embeddings
        for i in range(4): # Create 4 more users
            user = User.objects.create_user(
                email=f'parent_bulk{i}@test.com',
                password='testpass123',
                user_type='Parent',
                profile_picture_url=f'https://example.com/profile_bulk{i}.jpg' # This triggers the signal for each
            )
            parent = Parent.objects.get(user=user)
            parent.first_name = f'BulkTest{i}'
            parent.last_name = 'Parent'
            parent.save()

        parents_eligible_for_bulk = Parent.objects.filter(
            user__profile_picture_url__isnull=False,
            face_embedding__isnull=True
        ).count()
        self.assertEqual(parents_eligible_for_bulk, 5)


        # Mock the delay call's return value for the bulk task
        mock_delay.return_value = MagicMock(id='fake-task-id')

        # Run bulk task (processes 3 of the 5 eligible parents)
        result = bulk_generate_face_embeddings_task(batch_size=3)

        self.assertEqual(result['success'], 3)
        self.assertEqual(result['failed'], 0)
        self.assertEqual(len(result['processed']), 3)


        self.assertEqual(mock_delay.call_count, 7)
        # remaining_parents = Parent.objects.filter(
        #     user__profile_picture_url__isnull=False,
        #     face_embedding__isnull=True
        # ).count()
        # self.assertEqual(remaining_parents, 2)

    def test_bulk_generate_face_embeddings_task_no_parents(self):
        """Test bulk task when no parents need processing"""
        # Give all parents embeddings
        self.parent.face_embedding = b'fake_embedding'
        self.parent.save()

        result = bulk_generate_face_embeddings_task(batch_size=10)

        self.assertEqual(result['success'], 0)
        self.assertEqual(result['failed'], 0)
        self.assertEqual(len(result['processed']), 0)


class FaceVerificationSignalTestCase(TestCase):
    """Test cases for face verification signals"""

    @patch('appointments.tasks.generate_face_embedding_task.delay')
    def test_signal_triggers_task_on_profile_picture_update(self, mock_delay):
        """Test signal triggers task when parent updates profile picture"""
        # Create parent without profile picture
        parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent'
        )

        parent = Parent.objects.get(user=parent_user)
        parent.first_name = 'Test'
        parent.last_name = 'Parent'
        parent.save()

        # Mock the delay call
        mock_delay.return_value = MagicMock(id='fake-task-id')

        # Update profile picture
        parent_user.profile_picture_url = 'https://example.com/new_profile.jpg'
        parent_user.save()

        # Verify task was triggered
        mock_delay.assert_called_once_with(str(parent_user.id))

    @patch('appointments.tasks.generate_face_embedding_task.delay')
    def test_signal_does_not_trigger_for_non_parent(self, mock_delay):
        """Test signal doesn't trigger for non-parent users"""
        # Create psychologist user
        psychologist_user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist'
        )

        # Update profile picture
        psychologist_user.profile_picture_url = 'https://example.com/profile.jpg'
        psychologist_user.save()

        # Verify task was NOT triggered
        mock_delay.assert_not_called()

    @patch('appointments.tasks.generate_face_embedding_task.delay')
    def test_signal_does_not_trigger_when_picture_removed(self, mock_delay):
        # Create user with picture (let it trigger task, don't assert here)
        parent_user = User.objects.create_user(
            email='parent@test.com',
            password='testpass123',
            user_type='Parent',
            profile_picture_url='https://example.com/old_profile.jpg'
        )

        parent = Parent.objects.get(user=parent_user)
        parent.first_name = 'Test'
        parent.last_name = 'Parent'
        parent.save()

        mock_delay.reset_mock()  # Reset after creation to ignore first call

        # Remove profile picture
        parent_user.profile_picture_url = None
        parent_user.save()

        # Now assert the task wasn't called again
        mock_delay.assert_not_called()

    @patch('appointments.tasks.generate_face_embedding_task.delay')
    def test_signal_with_disabled_auto_generation(self, mock_delay):
        """Test signal respects AUTO_GENERATE_FACE_EMBEDDINGS setting"""
        with self.settings(AUTO_GENERATE_FACE_EMBEDDINGS=False):
            # Create parent
            parent_user = User.objects.create_user(
                email='parent@test.com',
                password='testpass123',
                user_type='Parent'
            )

            parent = Parent.objects.get(user=parent_user)
            parent.first_name = 'Test'
            parent.last_name = 'Parent'
            parent.save()

            # Update profile picture
            parent_user.profile_picture_url = 'https://example.com/profile.jpg'
            parent_user.save()

            # Verify task was NOT triggered
            mock_delay.assert_not_called()