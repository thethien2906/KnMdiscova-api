# psychologists/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
import logging

from users.models import User
from .models import Psychologist

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_psychologist_profile(sender, instance, created, **kwargs):
    """
    Create Psychologist profile when a new user with type 'Psychologist' is created
    """
    if created and instance.user_type == 'Psychologist':
        try:
            with transaction.atomic():
                # Create psychologist with minimal data to avoid validation errors
                # Set offers_initial_consultation=False initially to avoid office_address requirement
                Psychologist.objects.create(
                    user=instance,
                    first_name='',
                    last_name='',
                    license_number='',
                    license_issuing_authority='',
                    license_expiry_date=None,
                    years_of_experience=0,
                    verification_status='Pending',
                    education=[],
                    certifications=[],
                    offers_initial_consultation=False,  # Set to False initially
                    offers_online_sessions=True,        # At least one service must be offered
                    office_address=''                   # Can be empty since initial_consultation=False
                )
                logger.info(f"Psychologist profile created for user: {instance.email}")
        except Exception as e:
            logger.error(f"Failed to create psychologist profile for user {instance.email}: {str(e)}")
            # Don't raise the exception to avoid breaking user creation