import logging
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.utils import timezone
from datetime import timedelta
import face_recognition
import numpy as np
from PIL import Image
import io

from users.models import User
from parents.models import Parent
from psychologists.models import Psychologist
from appointments.models import Appointment
from appointments.services.face_verification_service import FaceVerificationService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test face verification functionality'

    def handle(self, *args, **options):
        logging.basicConfig(level=logging.DEBUG)
        self.stdout.write("Testing Face Verification Service...")

        try:
            # Create test image
            self.stdout.write("Creating test image...")
            test_image = self.create_test_image()

            # Test 1: Generate face embedding
            self.stdout.write("\nTest 1: Generating face embedding...")
            embedding = None
            try:
                embedding = FaceVerificationService.generate_face_embedding(test_image)
                logger.debug(f"Generated embedding: {embedding}")
                if embedding:
                    self.stdout.write(self.style.SUCCESS("✓ Face embedding generated successfully"))
                    self.stdout.write(f"  Embedding size: {len(embedding)} bytes")
                else:
                    self.stdout.write(self.style.ERROR("✗ No face detected in test image"))
            except Exception as e:
                logger.exception("Exception in Test 1")
                self.stdout.write(self.style.ERROR(f"✗ Error: {str(e)}"))

            # Test 2: Compare embeddings
            self.stdout.write("\nTest 2: Comparing face embeddings...")
            if embedding:
                try:
                    embedding2 = FaceVerificationService.generate_face_embedding(test_image)
                    logger.debug(f"Second embedding: {embedding2}")
                    match = FaceVerificationService.compare_faces(embedding, embedding2)
                    logger.debug(f"Face match result: {match}")
                    if match:
                        self.stdout.write(self.style.SUCCESS("✓ Face matching works correctly"))
                    else:
                        self.stdout.write(self.style.WARNING("⚠ Same face did not match (tolerance may be too strict)"))
                except Exception as e:
                    logger.exception("Exception in Test 2")
                    self.stdout.write(self.style.ERROR(f"✗ Error during comparison: {str(e)}"))
            else:
                self.stdout.write(self.style.WARNING("⚠ Skipping Test 2 because embedding wasn't generated."))

            # Test 3: Sample face placeholder
            self.stdout.write("\nTest 3: Testing with sample face...")
            self.test_with_sample_face()

            # Test 4: DB Integration
            self.stdout.write("\nTest 4: Testing database integration...")
            self.test_database_integration()

        except Exception as e:
            logger.exception("General failure in test runner")
            self.stdout.write(self.style.ERROR(f"Test failed: {str(e)}"))

    # def create_test_image(self):
    #     """Create a simple white image (not a real face)"""
    #     img = Image.new('RGB', (300, 300), color='white')
    #     buffer = io.BytesIO()
    #     img.save(buffer, format='JPEG')
    #     logger.debug("Test image created (white square)")
    #     return buffer.getvalue()
    def create_test_image(self):
        """Load a real test face image from disk"""
        path = "/app/appointments/management/commands/fixtures/cum.jpg"
        with open(path, "rb") as f:
            logger.debug("Loaded real face image from disk")
            return f.read()

    def test_with_sample_face(self):
        try:
            self.stdout.write("  Would test with real face image in production")
            logger.debug("Sample face test placeholder ran")
            self.stdout.write(self.style.SUCCESS("  ✓ Sample face test placeholder"))
        except Exception as e:
            logger.exception("Error in sample face test")
            self.stdout.write(self.style.ERROR(f"  ✗ Sample face test failed: {str(e)}"))

    def test_database_integration(self):
        try:
            user = User.objects.filter(email='test_parent@example.com').first()
            if not user:
                self.stdout.write("  Creating new test user...")
                user = User.objects.create_user(
                    email='test_parent@example.com',
                    password='testpass123',
                    user_type='Parent'
                )
                logger.debug("Test user created")

            parent, created = Parent.objects.get_or_create(
                user=user,
                defaults={'first_name': 'Test', 'last_name': 'Parent'}
            )
            logger.debug(f"Parent object: {parent}, created: {created}")

            test_embedding = np.random.rand(128).astype(np.float64).tobytes()
            parent.face_embedding = test_embedding
            parent.face_embedding_created_at = timezone.now()
            parent.save()
            logger.debug("Saved test embedding to DB")

            retrieved_parent = Parent.objects.get(user=user)
            if retrieved_parent.face_embedding == test_embedding:
                self.stdout.write(self.style.SUCCESS("  ✓ Database storage and retrieval working"))
            else:
                self.stdout.write(self.style.ERROR("  ✗ Database retrieval mismatch"))
                logger.warning("Mismatch between saved and retrieved embeddings")

        except Exception as e:
            logger.exception("Error in DB integration test")
            self.stdout.write(self.style.ERROR(f"  ✗ Database test failed: {str(e)}"))
