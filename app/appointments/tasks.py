# appointments/tasks.py
from celery import shared_task
from django.utils import timezone
import logging
from django.core.files.storage import default_storage
from .services import AppointmentSlotService, FaceVerificationService
from psychologists.models import PsychologistAvailability
from parents.models import Parent
from users.models import User
import requests

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def auto_generate_slots_task(self, availability_block_id: int):
    """
    Celery task to automatically generate slots for new availability block
    """
    try:
        availability_block = PsychologistAvailability.objects.get(
            availability_id=availability_block_id
        )

        result = AppointmentSlotService.auto_generate_slots_for_new_availability(availability_block)

        if result['success']:
            logger.info(f"Celery task completed: auto-generated slots for availability {availability_block_id}")
            return result
        else:
            logger.error(f"Celery task failed: {result.get('error', 'Unknown error')}")
            raise Exception(result.get('error', 'Unknown error'))

    except PsychologistAvailability.DoesNotExist:
        logger.error(f"Availability block {availability_block_id} not found for slot generation")
        raise
    except Exception as e:
        logger.error(f"Celery task error for availability {availability_block_id}: {str(e)}")
        # Retry the task
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def auto_regenerate_slots_task(self, availability_block_id: int, old_data: dict = None):
    """
    Celery task to automatically regenerate slots for updated availability block
    """
    try:
        availability_block = PsychologistAvailability.objects.get(
            availability_id=availability_block_id
        )

        result = AppointmentSlotService.auto_regenerate_slots_for_updated_availability(
            availability_block, old_data
        )

        if result['success']:
            logger.info(f"Celery task completed: auto-regenerated slots for availability {availability_block_id}")
            return result
        else:
            logger.error(f"Celery task failed: {result.get('error', 'Unknown error')}")
            raise Exception(result.get('error', 'Unknown error'))

    except PsychologistAvailability.DoesNotExist:
        logger.error(f"Availability block {availability_block_id} not found for slot regeneration")
        raise
    except Exception as e:
        logger.error(f"Celery task error for availability {availability_block_id}: {str(e)}")
        # Retry the task
        raise self.retry(exc=e)


@shared_task(bind=True)
def auto_cleanup_past_slots_task(self, days_past=7):
    """
    Automatically clean up past unbooked slots
    Runs daily via cron schedule
    """
    try:
        from .services import AppointmentSlotService

        deleted_count = AppointmentSlotService.cleanup_past_slots(days_past)

        logger.info(f"Auto-cleanup completed: {deleted_count} past slots deleted")
        return {
            'success': True,
            'deleted_count': deleted_count,
            'days_past': days_past,
            'cleanup_date': timezone.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Auto-cleanup failed: {str(e)}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def generate_face_embedding_task(self, user_id: str):
    """
    Celery task to generate face embedding for a parent user
    when their profile picture is updated.

    Args:
        user_id: UUID string of the user
    """
    try:
        # Get user and parent profile
        user = User.objects.get(id=user_id)

        if user.user_type != 'Parent':
            logger.info(f"User {user_id} is not a parent, skipping face embedding generation")
            return {
                'success': False,
                'reason': 'User is not a parent'
            }

        if not user.profile_picture_url:
            logger.warning(f"User {user_id} has no profile picture")
            return {
                'success': False,
                'reason': 'No profile picture'
            }

        # Get parent profile
        try:
            parent = user.parent_profile
        except Parent.DoesNotExist:
            logger.error(f"Parent profile not found for user {user_id}")
            return {
                'success': False,
                'reason': 'Parent profile not found'
            }

        # Download image data
        image_data = None

        if user.profile_picture_url.startswith('http'):
            # Remote URL (e.g., S3, CDN)
            logger.info(f"Downloading profile picture from URL: {user.profile_picture_url}")
            response = requests.get(user.profile_picture_url, timeout=30)

            if response.status_code == 200:
                image_data = response.content
            else:
                logger.error(f"Failed to download image: HTTP {response.status_code}")
                raise Exception(f"Failed to download image: HTTP {response.status_code}")
        else:
            # Local file storage
            logger.info(f"Reading profile picture from local storage: {user.profile_picture_url}")
            with default_storage.open(user.profile_picture_url, 'rb') as f:
                image_data = f.read()

        if not image_data:
            raise Exception("No image data retrieved")

        # Generate face embedding
        logger.info(f"Generating face embedding for parent {user.email}")
        FaceVerificationService.update_parent_face_embedding(parent, image_data)

        logger.info(f"Successfully generated face embedding for user {user_id}")
        return {
            'success': True,
            'user_id': user_id,
            'parent_id': str(parent.user_id),
            'embedding_created': True
        }

    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return {
            'success': False,
            'reason': 'User not found'
        }
    except Exception as e:
        logger.error(f"Failed to generate face embedding for user {user_id}: {str(e)}")
        # Retry the task
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def bulk_generate_face_embeddings_task(self, batch_size=10):
    """
    Celery task to bulk generate face embeddings for parents
    who have profile pictures but no embeddings.

    Args:
        batch_size: Number of parents to process in this batch
    """
    try:
        # Find parents with profile pictures but no face embeddings
        parents_to_process = Parent.objects.filter(
            user__profile_picture_url__isnull=False,
            face_embedding__isnull=True
        ).select_related('user')[:batch_size]

        results = {
            'success': 0,
            'failed': 0,
            'processed': []
        }

        for parent in parents_to_process:
            try:
                # Trigger individual task for each parent
                generate_face_embedding_task.delay(str(parent.user.id))
                results['success'] += 1
                results['processed'].append({
                    'user_id': str(parent.user.id),
                    'email': parent.user.email,
                    'status': 'queued'
                })
            except Exception as e:
                logger.error(f"Failed to queue embedding generation for {parent.user.email}: {str(e)}")
                results['failed'] += 1
                results['processed'].append({
                    'user_id': str(parent.user.id),
                    'email': parent.user.email,
                    'status': 'failed',
                    'error': str(e)
                })

        logger.info(f"Bulk face embedding generation: {results['success']} queued, {results['failed']} failed")
        return results

    except Exception as e:
        logger.error(f"Bulk face embedding generation failed: {str(e)}")
        raise self.retry(exc=e)