# appointments/tasks.py
from celery import shared_task
from django.utils import timezone
import logging
from django.core.files.storage import default_storage
from psychologists.models import PsychologistAvailability
from parents.models import Parent
from users.models import User
import requests
from django.db import transaction

from .services import (
    AppointmentSlotService,
    FaceVerificationService,
    FaceVerificationError,
    NoFaceDetectedError,
    MultipleFacesDetectedError,
    ImageProcessingError
)
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
    Celery task to generate face embedding for a parent's profile picture

    Args:
        user_id: UUID string of the user

    Returns:
        Dict with task result information
    """
    try:
        # Get user and validate they're a parent
        user = User.objects.get(id=user_id)

        if user.user_type != 'Parent':
            logger.warning(f"Attempted to generate face embedding for non-parent user: {user.email}")
            return {
                'success': False,
                'error': 'User is not a parent',
                'user_id': user_id
            }

        if not user.profile_picture_url:
            logger.warning(f"No profile picture URL for user: {user.email}")
            return {
                'success': False,
                'error': 'No profile picture URL',
                'user_id': user_id
            }

        # Get parent profile
        try:
            parent = Parent.objects.get(user=user)
        except Parent.DoesNotExist:
            logger.error(f"Parent profile not found for user: {user.email}")
            return {
                'success': False,
                'error': 'Parent profile not found',
                'user_id': user_id
            }

        logger.info(f"Starting face embedding generation for user: {user.email}")

        # Validate profile picture
        validation_result = FaceVerificationService.validate_profile_picture_for_embedding(
            user.profile_picture_url
        )

        if not validation_result['valid']:
            logger.warning(
                f"Profile picture validation failed for user {user.email}: "
                f"{validation_result['error']}"
            )
            return {
                'success': False,
                'error': validation_result['error'],
                'error_code': validation_result.get('error_code'),
                'user_id': user_id
            }

        # Generate face embedding
        try:
            embedding_data = FaceVerificationService.generate_face_embedding_from_url(
                user.profile_picture_url
            )

            if embedding_data:
                # Save embedding to parent with atomic transaction
                with transaction.atomic():
                    parent.face_embedding = embedding_data
                    parent.face_embedding_created_at = timezone.now()
                    parent.save(update_fields=['face_embedding', 'face_embedding_created_at', 'updated_at'])

                logger.info(f"Face embedding successfully generated and saved for user: {user.email}")

                return {
                    'success': True,
                    'message': 'Face embedding generated successfully',
                    'user_id': user_id,
                    'embedding_created_at': parent.face_embedding_created_at.isoformat(),
                    'profile_picture_url': user.profile_picture_url
                }
            else:
                logger.error(f"Face embedding generation returned None for user: {user.email}")
                return {
                    'success': False,
                    'error': 'Failed to generate face embedding',
                    'user_id': user_id
                }

        except NoFaceDetectedError:
            error_msg = "No face detected in profile picture"
            logger.warning(f"{error_msg} for user: {user.email}")
            return {
                'success': False,
                'error': error_msg,
                'error_code': 'NO_FACE_DETECTED',
                'user_id': user_id
            }

        except MultipleFacesDetectedError:
            error_msg = "Multiple faces detected in profile picture"
            logger.warning(f"{error_msg} for user: {user.email}")
            return {
                'success': False,
                'error': error_msg,
                'error_code': 'MULTIPLE_FACES',
                'user_id': user_id
            }

        except ImageProcessingError as e:
            error_msg = f"Image processing error: {str(e)}"
            logger.warning(f"{error_msg} for user: {user.email}")
            return {
                'success': False,
                'error': error_msg,
                'error_code': 'IMAGE_PROCESSING_ERROR',
                'user_id': user_id
            }

        except FaceVerificationError as e:
            error_msg = f"Face verification error: {str(e)}"
            logger.error(f"{error_msg} for user: {user.email}")
            return {
                'success': False,
                'error': error_msg,
                'error_code': 'FACE_VERIFICATION_ERROR',
                'user_id': user_id
            }

    except User.DoesNotExist:
        logger.error(f"User not found for face embedding generation: {user_id}")
        return {
            'success': False,
            'error': 'User not found',
            'user_id': user_id
        }

    except Exception as e:
        logger.error(f"Unexpected error in face embedding task for user {user_id}: {str(e)}")

        # Retry the task for unexpected errors
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying face embedding task for user {user_id} (attempt {self.request.retries + 1})")
            raise self.retry(exc=e)

        return {
            'success': False,
            'error': f'Task failed after {self.max_retries} retries: {str(e)}',
            'user_id': user_id
        }


@shared_task(bind=True)
def bulk_generate_face_embeddings_task(self, batch_size: int = 50):
    """
    Bulk generate face embeddings for parents who have profile pictures but no embeddings
    Useful for migrating existing users or fixing failed generations

    Args:
        batch_size: Number of users to process in this batch

    Returns:
        Dict with batch processing results
    """
    try:
        # Find parents with profile pictures but no face embeddings
        parents_needing_embeddings = Parent.objects.filter(
            user__profile_picture_url__isnull=False,
            face_embedding__isnull=True,
            user__user_type='Parent',
            user__is_active=True
        ).select_related('user')[:batch_size]

        if not parents_needing_embeddings:
            logger.info("No parents found needing face embedding generation")
            return {
                'success': True,
                'message': 'No parents need face embedding generation',
                'processed_count': 0,
                'batch_size': batch_size
            }

        results = {
            'success': True,
            'processed_count': 0,
            'successful_count': 0,
            'failed_count': 0,
            'batch_size': batch_size,
            'failures': []
        }

        logger.info(f"Starting bulk face embedding generation for {len(parents_needing_embeddings)} parents")

        for parent in parents_needing_embeddings:
            try:
                # Queue individual embedding generation task
                task_result = generate_face_embedding_task.delay(str(parent.user.id))

                results['processed_count'] += 1

                # For bulk processing, we don't wait for individual results
                # The individual tasks will handle their own success/failure logging

            except Exception as e:
                logger.error(f"Failed to queue embedding task for parent {parent.user.email}: {str(e)}")
                results['failed_count'] += 1
                results['failures'].append({
                    'user_id': str(parent.user.id),
                    'email': parent.user.email,
                    'error': str(e)
                })

        logger.info(
            f"Bulk face embedding generation queued: {results['processed_count']} tasks queued, "
            f"{results['failed_count']} failed to queue"
        )

        return results

    except Exception as e:
        logger.error(f"Bulk face embedding generation task failed: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'processed_count': 0,
            'batch_size': batch_size
        }


@shared_task
def cleanup_failed_face_embeddings_task():
    """
    Cleanup task to identify and retry failed face embedding generations
    Can be run periodically to ensure all eligible parents have embeddings
    """
    try:
        # Find parents with recent profile picture updates but no embeddings
        from datetime import timedelta

        cutoff_time = timezone.now() - timedelta(hours=24)  # Look at last 24 hours

        failed_parents = Parent.objects.filter(
            user__profile_picture_url__isnull=False,
            face_embedding__isnull=True,
            user__user_type='Parent',
            user__is_active=True,
            user__updated_at__gte=cutoff_time  # Recently updated profile
        ).select_related('user')

        if not failed_parents:
            logger.info("No failed face embedding generations found to retry")
            return {
                'success': True,
                'message': 'No failed generations to retry',
                'retry_count': 0
            }

        retry_count = 0
        for parent in failed_parents:
            try:
                # Retry embedding generation
                generate_face_embedding_task.delay(str(parent.user.id))
                retry_count += 1

            except Exception as e:
                logger.error(f"Failed to retry embedding for parent {parent.user.email}: {str(e)}")

        logger.info(f"Cleanup task queued {retry_count} face embedding retries")

        return {
            'success': True,
            'message': f'Queued {retry_count} embedding retries',
            'retry_count': retry_count
        }

    except Exception as e:
        logger.error(f"Cleanup failed face embeddings task failed: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'retry_count': 0
        }