# appointments/management/commands/test_profile_upload_flow.py
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.test.client import Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from datetime import timedelta
import json
import time
import tempfile
import os
from PIL import Image, ImageDraw
import threading
from unittest.mock import patch, Mock

from parents.models import Parent
from users.models import User
from appointments.services.face_verification_service import FaceVerificationService
from appointments.tasks import generate_face_embedding_task

User = get_user_model()


class Command(BaseCommand):
    help = 'Test complete profile picture upload flow: Upload → Validation → Signal → Celery Task → Embedding'

    def add_arguments(self, parser):
        parser.add_argument(
            '--profile-picture-url',
            type=str,
            default='https://res.cloudinary.com/du7snch3r/image/upload/v1748936085/iv1llyy5epvtacgn2pza.jpg',
            help='Real profile picture URL to test with (default: Cloudinary test image)'
        )
        parser.add_argument(
            '--use-real-celery',
            action='store_true',
            help='Use real Celery tasks instead of mocking (requires Redis/Celery worker)'
        )
        parser.add_argument(
            '--create-bad-image',
            action='store_true',
            help='Test with a bad image (no face) to verify validation'
        )
        parser.add_argument(
            '--create-blurry-image',
            action='store_true',
            help='Test with a blurry image to verify blur detection'
        )
        parser.add_argument(
            '--create-multiple-faces',
            action='store_true',
            help='Test with multiple faces to verify validation'
        )
        parser.add_argument(
            '--skip-cleanup',
            action='store_true',
            help='Skip cleanup of test data (for debugging)'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("================= DEBUGGING =================="))
        self.stdout.write(f"DEBUG: Current ALLOWED_HOSTS setting is: {settings.ALLOWED_HOSTS}")
        self.stdout.write(self.style.WARNING("=============================================="))
        self.stdout.write(self.style.NOTICE("=== Testing Complete Profile Picture Upload Flow ===\n"))

        profile_picture_url = options.get('profile_picture_url')
        use_real_celery = options.get('use_real_celery')
        create_bad_image = options.get('create_bad_image')
        create_blurry_image = options.get('create_blurry_image')
        create_multiple_faces = options.get('create_multiple_faces')
        skip_cleanup = options.get('skip_cleanup')

        test_data = None
        temp_files = []

        try:
            # Step 1: Create test parent
            self.stdout.write(self.style.NOTICE("Step 1: Creating test parent..."))
            test_data = self.create_test_parent()
            self.stdout.write(self.style.SUCCESS("✓ Test parent created\n"))

            # Step 2: Determine which image to use
            if create_bad_image or create_blurry_image or create_multiple_faces:
                self.stdout.write(self.style.NOTICE("Step 2: Creating synthetic test image for validation testing..."))
                if create_bad_image:
                    test_image_path = self.create_bad_image()
                    profile_picture_url = self.upload_temp_image_to_mock_url(test_image_path)
                    self.stdout.write(self.style.WARNING("Created bad image (no face) for validation testing"))
                elif create_blurry_image:
                    test_image_path = self.create_blurry_image()
                    profile_picture_url = self.upload_temp_image_to_mock_url(test_image_path)
                    self.stdout.write(self.style.WARNING("Created blurry image for validation testing"))
                elif create_multiple_faces:
                    test_image_path = self.create_multiple_faces_image()
                    profile_picture_url = self.upload_temp_image_to_mock_url(test_image_path)
                    self.stdout.write(self.style.WARNING("Created multiple faces image for validation testing"))

                temp_files.append(test_image_path)
                self.stdout.write(self.style.SUCCESS(f"✓ Test image created and mock URL generated\n"))
            else:
                self.stdout.write(self.style.NOTICE("Step 2: Using real profile picture URL..."))
                self.stdout.write(f"  - Using URL: {profile_picture_url}")
                self.stdout.write(self.style.SUCCESS("✓ Real profile picture URL ready\n"))

            # Step 3: Test profile update API with validation
            self.stdout.write(self.style.NOTICE("Step 3: Testing profile update API with validation..."))
            api_success = self.test_profile_update_api(test_data, profile_picture_url)

            if not api_success:
                if create_bad_image or create_blurry_image or create_multiple_faces:
                    self.stdout.write(self.style.SUCCESS("✓ API correctly rejected invalid image\n"))
                    # For negative tests, we stop here as expected
                    self.stdout.write(self.style.SUCCESS("🎉 Negative validation test PASSED! 🎉\n"))
                    return
                else:
                    raise Exception("Profile update API failed unexpectedly")

            self.stdout.write(self.style.SUCCESS("✓ Profile update API succeeded with valid image\n"))

            # Step 4: Test signal triggering and Celery task
            self.stdout.write(self.style.NOTICE("Step 4: Testing signal triggering and Celery task..."))
            if use_real_celery:
                self.test_real_celery_workflow(test_data, profile_picture_url)
            else:
                self.test_mocked_celery_workflow(test_data, profile_picture_url)

            # Step 5: Verify embedding generation
            self.stdout.write(self.style.NOTICE("Step 5: Verifying face embedding generation..."))
            self.verify_embedding_generation(test_data['parent'])

            # Step 6: Test parent checking embedding status
            self.stdout.write(self.style.NOTICE("Step 6: Testing parent checking embedding status..."))
            self.test_embedding_status_api(test_data)

            self.stdout.write(self.style.SUCCESS("\n🎉 Complete profile picture upload flow test PASSED! 🎉\n"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Test FAILED: {str(e)}\n"))
            raise

        finally:
            # Cleanup
            if not skip_cleanup and test_data:
                self.cleanup_test_data(test_data)

            # Clean up temporary files
            for temp_file in temp_files:
                try:
                    os.unlink(temp_file)
                except Exception:
                    pass

    def create_test_parent(self):
        """Create test parent user"""
        with transaction.atomic():
            # Create parent user (without profile picture initially)
            parent_user = User.objects.create_user(
                email='test_parent_upload_flow@kmdiscova.com',
                password='testpass123',
                user_type='Parent',
                is_verified=True,
                is_active=True,
            )

            parent = Parent.objects.get(user=parent_user)
            parent.first_name = 'Emma'
            parent.last_name = 'TestUpload'
            parent.save()

            # Create authentication token
            token, created = Token.objects.get_or_create(user=parent_user)

            self.stdout.write(f"  - Created parent: {parent.full_name}")
            self.stdout.write(f"  - Email: {parent_user.email}")
            self.stdout.write(f"  - Auth token: {token.key}")

            return {
                'parent': parent,
                'parent_user': parent_user,
                'token': token
            }

    def create_good_face_image(self):
        """Create a good quality face image"""
        img = Image.new('RGB', (400, 400), color='lightblue')
        draw = ImageDraw.Draw(img)

        # Draw a detailed face
        # Head (oval)
        draw.ellipse([50, 50, 350, 350], fill='peachpuff', outline='black', width=2)

        # Eyes
        draw.ellipse([100, 140, 150, 180], fill='white', outline='black', width=2)
        draw.ellipse([250, 140, 300, 180], fill='white', outline='black', width=2)
        draw.ellipse([115, 155, 135, 175], fill='blue')  # Left iris
        draw.ellipse([265, 155, 285, 175], fill='blue')  # Right iris
        draw.ellipse([120, 160, 130, 170], fill='black')  # Left pupil
        draw.ellipse([270, 160, 280, 170], fill='black')  # Right pupil

        # Eyebrows
        draw.arc([95, 120, 155, 140], 0, 180, fill='brown', width=4)
        draw.arc([245, 120, 305, 140], 0, 180, fill='brown', width=4)

        # Nose
        draw.polygon([(200, 200), (185, 230), (215, 230)], fill='peachpuff', outline='black')

        # Mouth
        draw.arc([170, 250, 230, 290], 0, 180, fill='red', width=4)

        # Hair
        draw.arc([40, 40, 360, 200], 180, 360, fill='brown', width=20)

        temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        img.save(temp_file.name, 'JPEG', quality=95)
        return temp_file.name

    def create_bad_image(self):
        """Create an image with no face"""
        img = Image.new('RGB', (400, 400), color='green')
        draw = ImageDraw.Draw(img)

        # Draw a landscape instead of a face
        draw.rectangle([0, 300, 400, 400], fill='brown')  # Ground
        draw.ellipse([50, 50, 150, 150], fill='yellow')   # Sun
        draw.rectangle([200, 150, 250, 300], fill='brown')  # Tree trunk
        draw.ellipse([150, 100, 300, 200], fill='green')   # Tree top

        temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        img.save(temp_file.name, 'JPEG', quality=95)
        return temp_file.name

    def create_blurry_image(self):
        """Create a blurry face image"""
        # Create a normal face first
        img = Image.new('RGB', (400, 400), color='lightblue')
        draw = ImageDraw.Draw(img)

        # Simple face
        draw.ellipse([100, 100, 300, 300], fill='peachpuff', outline='black')
        draw.ellipse([140, 160, 170, 190], fill='black')  # Left eye
        draw.ellipse([230, 160, 260, 190], fill='black')  # Right eye
        draw.arc([180, 220, 220, 260], 0, 180, fill='black', width=3)  # Mouth

        # Apply blur by downsampling and upsampling
        small = img.resize((50, 50), Image.LANCZOS)
        img = small.resize((400, 400), Image.LANCZOS)  # This creates blur

        temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        img.save(temp_file.name, 'JPEG', quality=50)  # Lower quality
        return temp_file.name

    def create_multiple_faces_image(self):
        """Create an image with multiple faces"""
        img = Image.new('RGB', (400, 400), color='white')
        draw = ImageDraw.Draw(img)

        # Face 1
        draw.ellipse([50, 50, 150, 150], fill='peachpuff', outline='black')
        draw.ellipse([70, 80, 85, 95], fill='black')  # Left eye
        draw.ellipse([115, 80, 130, 95], fill='black')  # Right eye
        draw.arc([85, 110, 115, 130], 0, 180, fill='black', width=2)  # Mouth

        # Face 2
        draw.ellipse([250, 50, 350, 150], fill='lightcoral', outline='black')
        draw.ellipse([270, 80, 285, 95], fill='black')  # Left eye
        draw.ellipse([315, 80, 330, 95], fill='black')  # Right eye
        draw.arc([285, 110, 315, 130], 0, 180, fill='black', width=2)  # Mouth

        temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        img.save(temp_file.name, 'JPEG', quality=95)
        return temp_file.name

    def upload_temp_image_to_mock_url(self, image_path):
        """Create a mock URL for temporary images (for validation testing)"""
        # For validation testing with bad images, we'll create a simple mock URL
        # In a real scenario, these would be uploaded to actual cloud storage
        return f"file://{os.path.abspath(image_path)}"

    def test_profile_update_api(self, test_data, profile_picture_url):
        """Test the profile update API with image validation"""
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {test_data["token"].key}')

        url = '/api/parents/profile/update_profile/'  # Adjust URL as needed

        # Make API request to update profile with real URL
        data = {
            'profile_picture_url': profile_picture_url,
            'first_name': test_data['parent'].first_name,
            'last_name': test_data['parent'].last_name,
        }

        self.stdout.write(f"  - Making API request to: {url}")
        self.stdout.write(f"  - Profile picture URL: {profile_picture_url}")

        response = client.patch(url, data, format='json')

        self.stdout.write(f"  - Response status: {response.status_code}")

        if response.status_code == 200:
            self.stdout.write("  - API request successful")

            # Verify the profile was updated
            test_data['parent'].refresh_from_db()
            test_data['parent_user'].refresh_from_db()

            if test_data['parent_user'].profile_picture_url == profile_picture_url:
                self.stdout.write("  ✓ Profile picture URL saved to database")
                return True
            else:
                self.stdout.write("  ✗ Profile picture URL not saved correctly")
                return False

        else:
            # API validation failed (expected for bad images)
            try:
                response_data = response.json()
            except:
                response_data = {'error': 'Unknown error'}

            self.stdout.write(f"  - API validation failed: {response_data}")
            return False

    def test_mocked_celery_workflow(self, test_data, profile_picture_url):
        """Test signal triggering and Celery task (mocked)"""

        # Mock the Celery task
        with patch('appointments.tasks.generate_face_embedding_task.delay') as mock_task:
            mock_result = Mock()
            mock_result.id = 'test-task-123'
            mock_task.return_value = mock_result

            # Trigger the signal by updating profile picture
            self.stdout.write("  - Triggering signal by updating profile picture...")

            # Update the profile picture URL (this should trigger the signal)
            original_url = test_data['parent_user'].profile_picture_url
            test_data['parent_user'].profile_picture_url = profile_picture_url
            test_data['parent_user'].save()

            # Give signals time to process
            time.sleep(0.1)

            # Verify the task was called
            if mock_task.called:
                self.stdout.write("  ✓ Celery task was queued by signal")
                call_args = mock_task.call_args
                if call_args and str(test_data['parent_user'].id) in str(call_args):
                    self.stdout.write(f"  ✓ Task called with correct user ID: {test_data['parent_user'].id}")
                else:
                    self.stdout.write(f"  ⚠ Task called but with unexpected args: {call_args}")
            else:
                self.stdout.write("  ✗ Celery task was NOT queued by signal")
                raise Exception("Signal did not trigger Celery task")

        # Manually execute the task logic for testing
        self.stdout.write("  - Manually executing task logic...")
        self.execute_embedding_task_logic(test_data['parent_user'], profile_picture_url)

    def test_real_celery_workflow(self, test_data, profile_picture_url):
        """Test signal triggering and real Celery task"""
        self.stdout.write("  - Testing with REAL Celery tasks...")

        # Check if we have the initial state
        initial_embedding = test_data['parent'].face_embedding
        self.stdout.write(f"  - Initial embedding state: {'Present' if initial_embedding else 'None'}")

        # Update the profile picture URL (this should trigger real signal and task)
        test_data['parent_user'].profile_picture_url = profile_picture_url
        test_data['parent_user'].save()

        self.stdout.write("  - Profile updated, signal should have triggered task...")

        # Wait for Celery task to complete (with timeout)
        max_wait = 30  # seconds
        wait_interval = 2  # seconds
        waited = 0

        while waited < max_wait:
            test_data['parent'].refresh_from_db()
            if test_data['parent'].face_embedding:
                self.stdout.write(f"  ✓ Celery task completed after {waited} seconds")
                break

            self.stdout.write(f"  - Waiting for task completion... ({waited}s)")
            time.sleep(wait_interval)
            waited += wait_interval

        if not test_data['parent'].face_embedding:
            self.stdout.write("  ⚠ Celery task did not complete within timeout")
            self.stdout.write("  - This might indicate Celery worker is not running")
            # Fall back to manual execution
            self.execute_embedding_task_logic(test_data['parent_user'], profile_picture_url)

    def execute_embedding_task_logic(self, user, profile_picture_url):
        """Manually execute the embedding generation logic"""

        # Execute the task logic directly with real URL
        from appointments.tasks import generate_face_embedding_task

        # Execute it directly
        self.stdout.write("  - Executing embedding generation manually...")
        self.stdout.write(f"  - Processing URL: {profile_picture_url}")

        result = task_func = generate_face_embedding_task(str(user.id))

        self.stdout.write(f"  - Task result: {result}")

        if result.get('success'):
            self.stdout.write("  ✓ Embedding generation task completed successfully")
        else:
            self.stdout.write(f"  ✗ Embedding generation failed: {result.get('error')}")
            raise Exception(f"Embedding generation failed: {result.get('error')}")

    def verify_embedding_generation(self, parent):
        """Verify that face embedding was generated"""
        parent.refresh_from_db()

        self.stdout.write(f"  - Checking embedding for parent: {parent.full_name}")

        if parent.face_embedding:
            self.stdout.write("  ✓ Face embedding exists")
            self.stdout.write(f"  - Embedding size: {len(parent.face_embedding)} bytes")

            if parent.face_embedding_created_at:
                self.stdout.write(f"  - Created at: {parent.face_embedding_created_at}")
                self.stdout.write("  ✓ Embedding timestamp recorded")
            else:
                self.stdout.write("  ⚠ Embedding timestamp missing")

            # Test that we can load the embedding
            try:
                embedding = FaceVerificationService._load_face_embedding(parent)
                self.stdout.write(f"  ✓ Embedding loaded successfully (shape: {embedding.shape})")
            except Exception as e:
                self.stdout.write(f"  ✗ Could not load embedding: {e}")
                raise
        else:
            self.stdout.write("  ✗ Face embedding missing")
            raise Exception("Face embedding was not generated")

    def test_embedding_status_api(self, test_data):
        """Test parent checking their embedding status via API"""
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {test_data["token"].key}')

        url = '/api/parents/profile/face-verification-status/'

        self.stdout.write(f"  - Making API request to: {url}")

        response = client.get(url)

        self.stdout.write(f"  - Response status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            self.stdout.write("  ✓ API request successful")
            self.stdout.write(f"  - Has embedding: {data.get('has_embedding')}")
            self.stdout.write(f"  - Has profile picture: {data.get('has_profile_picture')}")
            self.stdout.write(f"  - Can verify sessions: {data.get('can_verify_sessions')}")
            self.stdout.write(f"  - Status message: {data.get('message')}")
            self.stdout.write(f"  - Action required: {data.get('action_required')}")

            if data.get('can_verify_sessions'):
                self.stdout.write("  ✓ Parent can now verify sessions")
            else:
                self.stdout.write("  ✗ Parent cannot verify sessions")
                raise Exception("Parent should be able to verify sessions after embedding generation")
        else:
            self.stdout.write(f"  ✗ API request failed: {response.status_code}")
            raise Exception("Face verification status API failed")

    def cleanup_test_data(self, test_data):
        """Clean up test data"""
        self.stdout.write(self.style.NOTICE("Cleaning up test data..."))

        try:
            with transaction.atomic():
                if 'parent' in test_data and test_data['parent'].pk:
                    test_data['parent'].delete()
                    self.stdout.write("  ✓ Parent profile deleted")

                if 'parent_user' in test_data and test_data['parent_user'].pk:
                    test_data['parent_user'].delete()
                    self.stdout.write("  ✓ Parent user deleted")

                if 'token' in test_data and test_data['token'].pk:
                    test_data['token'].delete()
                    self.stdout.write("  ✓ Auth token deleted")

            self.stdout.write(self.style.SUCCESS("✓ All test data cleaned up successfully\n"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error during cleanup: {str(e)}"))