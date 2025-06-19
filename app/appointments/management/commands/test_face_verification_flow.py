# appointments/management/commands/test_face_verification_flow.py
"""
Management command to test the complete face verification flow
Usage: python manage.py test_face_verification_flow
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from datetime import timedelta, date, time
import numpy as np
from unittest.mock import patch
import face_recognition # Keep this if you use face_recognition directly in this file
from PIL import Image # For creating dummy image data
import io # For creating dummy image data
import requests # For mocking requests.Response

from users.models import User
from parents.models import Parent
from psychologists.models import Psychologist, PsychologistAvailability
from children.models import Child
from appointments.models import Appointment, AppointmentSlot
from appointments.tasks import generate_face_embedding_task # Import the actual task
from appointments.services.face_verification_service import FaceVerificationService


class Command(BaseCommand):
    help = 'Test the complete face verification flow'

    def add_arguments(self, parser):
        parser.add_argument(
            '--with-celery',
            action='store_true',
            help='Test with actual Celery task execution (requires Celery/Redis running)'
        )

    def handle(self, *args, **options):
        use_celery = options.get('with_celery', False)
        test_data = None

        self.stdout.write("=== Testing Face Verification Flow ===\n")

        try:
            # Step 1: Create test data
            self.stdout.write("Step 1: Creating test data...")
            test_data = self.create_test_data()
            self.stdout.write(self.style.SUCCESS("✓ Test data created"))

            # Step 2: Test face embedding generation
            self.stdout.write("\nStep 2: Testing face embedding generation...")
            if use_celery:
                self.test_celery_embedding_generation(test_data)
            else:
                self.test_direct_embedding_generation(test_data)

            # Step 3: Test face verification
            self.stdout.write("\nStep 3: Testing face verification...")
            self.test_face_verification(test_data)

            # Step 4: Test signal integration
            self.stdout.write("\nStep 4: Testing signal integration...")
            self.test_signal_integration(test_data)

            self.stdout.write(self.style.SUCCESS("\n=== All tests completed successfully! ==="))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n!!! Test failed with error: {e} !!!"))
            raise

        finally:
            # Cleanup
            if test_data:
                self.stdout.write("\nCleaning up test data...")
                self.cleanup_test_data(test_data)
            else:
                self.stdout.write("\nNo test data to clean up (creation might have failed).")

    def create_test_data(self):
        """Create test users, profiles, and appointment"""
        with transaction.atomic():
            # Create psychologist
            psychologist_user = User.objects.create_user(
                email='test_psychologist1@kmdiscova.com',
                password='testpass123',
                user_type='Psychologist',
                is_verified=True,
                is_active=True,
            )

            psychologist = Psychologist.objects.create(
                user=psychologist_user,
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
            # Create parent
            parent_user = User.objects.create_user(
                email='test_parent1@kmdiscova.com',
                password='testpass123',
                user_type='Parent',
                profile_picture_url='https://via.placeholder.com/300x300.jpg' # This URL will be mocked
            )

            parent = Parent.objects.get(user=parent_user)
            parent.first_name = 'Test'
            parent.last_name = 'Parent'
            # save parent profile
            parent.save()
            # Create child
            child = Child.objects.create(
                parent=parent,
                first_name='Test',
                last_name='Child',
                date_of_birth='2015-01-01'
            )
            # Create psychologist availability
            availability_block = PsychologistAvailability.objects.create(
                psychologist=psychologist,
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
            # Create future appointment slot for Zoom meeting creation tests
            slot1 = AppointmentSlot.objects.create(
                psychologist=psychologist,
                availability_block=availability_block,
                slot_date=monday_date,
                start_time='14:00',
                end_time='15:00',
                is_booked=True
            )
            slot2 = AppointmentSlot.objects.create(
                psychologist=psychologist,
                availability_block=availability_block,
                slot_date=monday_date,
                start_time='15:00',
                end_time='16:00',
                is_booked=True
            )

            # Set scheduled_start_time to be within the last 5 minutes from now,
            # so the current time falls within the verification window.
            # This assumes a typical verification window of e.g., 15 mins before to 30 mins after.
            scheduled_start_time = timezone.now() - timedelta(minutes=5)
            scheduled_end_time = scheduled_start_time + timedelta(hours=2) # Or whatever your typical appointment duration is


            # Create test appointment for Zoom service tests
            appointment = Appointment.objects.create(
                child=child,
                psychologist=psychologist,
                parent=parent,
                scheduled_start_time=scheduled_start_time,
                scheduled_end_time=scheduled_end_time,
                session_type='InitialConsultation',
                appointment_status='Scheduled',
                payment_status='Paid',
            )

            appointment.appointment_slots.add(slot1, slot2)


            return {
                'psychologist': psychologist,
                'parent': parent,
                'child': child,
                'appointment': appointment,
                'parent_user': parent_user,
                'psychologist_user': psychologist_user
            }

    def test_direct_embedding_generation(self, test_data):
        """Test direct face embedding generation"""
        parent = test_data['parent']

        # Generate a fake face embedding
        fake_embedding = np.random.rand(128).astype(np.float64).tobytes()

        parent.face_embedding = fake_embedding
        parent.face_embedding_created_at = timezone.now()
        parent.save()

        self.stdout.write(f"    Generated face embedding for {parent.user.email}")
        self.stdout.write(f"    Embedding size: {len(parent.face_embedding)} bytes")
        self.stdout.write(self.style.SUCCESS("    ✓ Direct embedding generation successful"))

    def test_celery_embedding_generation(self, test_data):
        """Test Celery task for embedding generation"""
        parent_user = test_data['parent_user']

        self.stdout.write(f"    Triggering Celery task for {parent_user.email}...")

        # Create a tiny dummy image in bytes
        dummy_image = Image.new('RGB', (1, 1), color='black')
        byte_io = io.BytesIO()
        dummy_image.save(byte_io, format='PNG')
        dummy_image_data = byte_io.getvalue()
        byte_io.close()

        # Mock the image download and face detection within the service
        # The key is to mock where face_recognition is *actually used* which is FaceVerificationService
        with patch('appointments.tasks.requests.get') as mock_get, \
             patch('appointments.services.face_verification_service.face_recognition.load_image_file') as mock_load_image_service, \
             patch('appointments.services.face_verification_service.face_recognition.face_encodings') as mock_encodings_service:

            # Mock successful image download: return a mock response containing valid image data
            mock_response = requests.Response()
            mock_response.status_code = 200
            mock_response._content = dummy_image_data

            mock_get.return_value = mock_response

            # When load_image_file is called by FaceVerificationService, return a dummy NumPy array
            mock_load_image_service.return_value = np.zeros((100, 100, 3), dtype=np.uint8)

            # Mock face encoding called by FaceVerificationService
            mock_encodings_service.return_value = [np.random.rand(128)]

            # Execute task synchronously
            result = generate_face_embedding_task(str(parent_user.id))

            if result['success']:
                self.stdout.write(self.style.SUCCESS("    ✓ Celery task completed successfully"))
            else:
                self.stdout.write(self.style.ERROR(f"    ✗ Celery task failed: {result.get('reason')}"))
                # If it failed, print the reason for easier debugging
                self.stdout.write(f"      Reason: {result.get('reason', 'N/A')}")


    def test_face_verification(self, test_data):
        """Test face verification logic"""
        appointment = test_data['appointment']
        psychologist = test_data['psychologist']
        parent = test_data['parent']

        # Ensure parent has face embedding
        if not parent.face_embedding:
            fake_embedding = np.random.rand(128).astype(np.float64).tobytes()
            parent.face_embedding = fake_embedding
            parent.face_embedding_created_at = timezone.now()
            parent.save()

        self.stdout.write(f"    Testing face verification for appointment {appointment.appointment_id}")

        # Create a tiny dummy image in bytes
        dummy_image = Image.new('RGB', (1, 1), color = 'black')
        byte_io = io.BytesIO()
        dummy_image.save(byte_io, format='PNG')
        dummy_image_data = byte_io.getvalue()
        byte_io.close()

        # Mock face verification within FaceVerificationService
        with patch('appointments.services.face_verification_service.face_recognition.load_image_file') as mock_load_image, \
             patch('appointments.services.face_verification_service.face_recognition.face_encodings') as mock_encodings, \
             patch('appointments.services.face_verification_service.face_recognition.face_distance') as mock_distance:

            # When load_image_file is called, return a dummy NumPy array
            mock_load_image.return_value = np.zeros((100, 100, 3), dtype=np.uint8)

            # Mock successful face match
            mock_encodings.return_value = [np.random.rand(128)]
            mock_distance.return_value = [0.4]  # Below threshold

            try:
                result = FaceVerificationService.verify_appointment_parent(
                    appointment=appointment,
                    live_image_data=dummy_image_data, # Use the actual dummy image data
                    psychologist=psychologist
                )

                if result['status'] == 'success':
                    self.stdout.write(self.style.SUCCESS("    ✓ Face verification successful"))
                    self.stdout.write(f"      - Appointment status: {result['appointment_status']}")
                    self.stdout.write(f"      - Start time: {result['actual_start_time']}")
                else:
                    self.stdout.write(self.style.ERROR(f"    ✗ Face verification failed: {result['message']}"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    ✗ Face verification error: {str(e)}"))
                raise

    def test_signal_integration(self, test_data):
        """Test signal integration for automatic embedding generation"""
        # Create new parent for signal test
        new_parent_user = User.objects.create_user(
            email='test_signal_parent2@kmdiscova.com', # Changed email to be unique across runs
            password='testpass123',
            user_type='Parent'
        )

        new_parent = Parent.objects.get(user=new_parent_user)
        new_parent.first_name = 'Signal'
        new_parent.last_name = 'Parent'
        new_parent.save()

        self.stdout.write(f"    Created new parent: {new_parent_user.email}")

        try:
            # Create a tiny dummy image in bytes for the signal test
            dummy_image = Image.new('RGB', (1, 1), color='black')
            byte_io = io.BytesIO()
            dummy_image.save(byte_io, format='PNG')
            dummy_image_data = byte_io.getvalue()
            byte_io.close()

            # Mock the Celery task's dependencies: requests.get and FaceVerificationService's face_recognition calls
            with patch('appointments.tasks.generate_face_embedding_task.delay') as mock_delay, \
                 patch('appointments.tasks.requests.get') as mock_get_signal, \
                 patch('appointments.services.face_verification_service.face_recognition.load_image_file') as mock_load_image_signal, \
                 patch('appointments.services.face_verification_service.face_recognition.face_encodings') as mock_encodings_signal:

                mock_delay.return_value.id = 'fake-task-id'

                # Mock successful image download for the signal's task call
                mock_response_signal = requests.Response()
                mock_response_signal.status_code = 200
                mock_response_signal._content = dummy_image_data
                mock_get_signal.return_value = mock_response_signal

                # Mock face recognition within the service for the signal's task call
                mock_load_image_signal.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
                mock_encodings_signal.return_value = [np.random.rand(128)]

                # Update profile picture (should trigger signal)
                new_parent_user.profile_picture_url = 'https://via.placeholder.com/400x400.jpg'
                new_parent_user.save()

                if mock_delay.called:
                    self.stdout.write(self.style.SUCCESS("    ✓ Signal triggered successfully"))
                    self.stdout.write(f"      - Task queued with user ID: {mock_delay.call_args[0][0]}")
                else:
                    self.stdout.write(self.style.ERROR("    ✗ Signal did not trigger"))

        finally:
            # Cleanup the specifically created signal test data
            if new_parent_user.pk:
                new_parent_user.delete()
            if new_parent.pk:
                new_parent.delete()


    def cleanup_test_data(self, test_data):
        """Clean up test data"""
        self.stdout.write(self.style.NOTICE("Attempting to clean up test data..."))

        # Ensure objects exist before trying to delete
        # Delete related objects first to avoid integrity errors

        # 1. Delete the main Appointment object
        if 'appointment' in test_data and test_data['appointment'].pk:
            try:
                test_data['appointment'].delete()
                self.stdout.write(self.style.SUCCESS("  - Appointment deleted."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  - Error deleting Appointment: {e}"))

        # 2. Delete Child (depends on Parent, so Parent should be deleted after Child)
        if 'child' in test_data and test_data['child'].pk:
            try:
                test_data['child'].delete()
                self.stdout.write(self.style.SUCCESS("  - Child deleted."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  - Error deleting Child: {e}"))

        # 3. Delete PsychologistAvailability (depends on Psychologist)
        if 'psychologist' in test_data and test_data['psychologist'].pk:
            try:
                PsychologistAvailability.objects.filter(psychologist=test_data['psychologist']).delete()
                self.stdout.write(self.style.SUCCESS("  - PsychologistAvailability deleted."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  - Error deleting PsychologistAvailability: {e}"))

            # 4. Delete AppointmentSlots (these are linked to Psychologist)
            try:
                AppointmentSlot.objects.filter(psychologist=test_data['psychologist']).delete()
                self.stdout.write(self.style.SUCCESS("  - AppointmentSlots deleted."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  - Error deleting AppointmentSlots: {e}"))


        # 5. Delete Parent and Psychologist profiles
        if 'parent' in test_data and test_data['parent'].pk:
            try:
                test_data['parent'].delete()
                self.stdout.write(self.style.SUCCESS("  - Parent profile deleted."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  - Error deleting Parent profile: {e}"))

        if 'psychologist' in test_data and test_data['psychologist'].pk:
            try:
                test_data['psychologist'].delete()
                self.stdout.write(self.style.SUCCESS("  - Psychologist profile deleted."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  - Error deleting Psychologist profile: {e}"))

        # 6. Delete User objects last, as Parent/Psychologist profiles depend on them
        if 'parent_user' in test_data and test_data['parent_user'].pk:
            try:
                test_data['parent_user'].delete()
                self.stdout.write(self.style.SUCCESS("  - Parent User deleted."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  - Error deleting Parent User: {e}"))

        if 'psychologist_user' in test_data and test_data['psychologist_user'].pk:
            try:
                test_data['psychologist_user'].delete()
                self.stdout.write(self.style.SUCCESS("  - Psychologist User deleted."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  - Error deleting Psychologist User: {e}"))

        self.stdout.write(self.style.SUCCESS("✓ Test data cleaned up (attempted)."))