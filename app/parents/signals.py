# parents/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
import logging

from users.models import User
from .models import Parent

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
