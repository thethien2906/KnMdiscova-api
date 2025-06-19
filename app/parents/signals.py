# parents/signals.py
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db import transaction
import logging
from appointments.services.face_verification_service import FaceVerificationService
from django.core.files.storage import default_storage
import requests
from users.models import User
from .models import Parent
from django.conf import settings
logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_parent_profile(sender, instance, created, **kwargs):
    """
    Create Parent profile when a new user with type 'Parent' is created
    """
    if created and instance.user_type == 'Parent':
        try:
            with transaction.atomic():
                Parent.objects.create(
                    user=instance,
                    first_name='',
                    last_name='',
                    communication_preferences=Parent.get_default_communication_preferences()
                )
                logger.info(f"Parent profile created for user: {instance.email}")
        except Exception as e:
            logger.error(f"Failed to create parent profile for user {instance.email}: {str(e)}")
            # Don't raise the exception to avoid breaking user creation

_user_profile_picture_cache = {}


@receiver(pre_save, sender=User)
def store_old_profile_picture(sender, instance, **kwargs):
    """
    Store the old profile picture URL before saving.
    """
    if instance.pk and instance.user_type == 'Parent':
        try:
            old_user = User.objects.get(pk=instance.pk)
            _user_profile_picture_cache[instance.pk] = old_user.profile_picture_url
        except User.DoesNotExist:
            pass


@receiver(post_save, sender=User)
def trigger_face_embedding_generation(sender, instance, created, **kwargs):
    """
    Trigger face embedding generation when parent updates profile picture.
    Uses Celery task for async processing.
    """
    # Skip if not a parent
    if instance.user_type != 'Parent':
        return

    # Skip if face embedding generation is disabled
    if not getattr(settings, 'AUTO_GENERATE_FACE_EMBEDDINGS', True):
        logger.info(f"Face embedding auto-generation disabled, skipping for user {instance.email}")
        return

    try:
        # Check if this is a profile picture update
        profile_picture_changed = False

        if created and instance.profile_picture_url:
            # New user with profile picture
            profile_picture_changed = True
        elif instance.pk in _user_profile_picture_cache:
            # Existing user - check if profile picture changed
            old_url = _user_profile_picture_cache.get(instance.pk)
            if old_url != instance.profile_picture_url and instance.profile_picture_url:
                profile_picture_changed = True

            # Clean up cache
            del _user_profile_picture_cache[instance.pk]

        if profile_picture_changed:

            # Import here to avoid circular imports
            from appointments.tasks import generate_face_embedding_task

            logger.info(f"Triggering face embedding generation for user {instance.email}")

            # Queue the task
            result = generate_face_embedding_task.delay(str(instance.id))

            logger.info(f"Face embedding task queued with ID: {result.id} for user {instance.email}")

    except Exception as e:
        logger.error(f"Failed to trigger face embedding generation task for user {instance.email}: {str(e)}")
        # Don't raise exception - profile picture update should still succeed


# Optional: Add a signal for manual face embedding generation
from django.dispatch import Signal

# Custom signal that can be triggered manually
face_embedding_requested = Signal()


@receiver(face_embedding_requested)
def handle_face_embedding_request(sender, user_id, **kwargs):
    """
    Handle manual face embedding generation requests.
    """
    try:
        from appointments.tasks import generate_face_embedding_task

        logger.info(f"Manual face embedding generation requested for user {user_id}")
        result = generate_face_embedding_task.delay(str(user_id))

        return result.id

    except Exception as e:
        logger.error(f"Failed to queue manual face embedding generation: {str(e)}")
        raise