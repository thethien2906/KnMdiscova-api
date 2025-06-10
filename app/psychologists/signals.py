# psychologists/signals.py
from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.conf import settings
import logging

from .models import PsychologistAvailability

logger = logging.getLogger(__name__)


@receiver(post_save, sender=PsychologistAvailability)
def auto_generate_slots_on_availability_change(sender, instance, created, **kwargs):
    """
    Signal handler to automatically generate/regenerate appointment slots
    when availability blocks are created or updated
    """
    # Check if auto-generation is enabled
    if not getattr(settings, 'AUTO_GENERATE_APPOINTMENT_SLOTS', True):
        logger.info(f"Auto-generation disabled, skipping slot generation for availability {instance.availability_id}")
        return

    try:
        # Import here to avoid circular imports
        from appointments.tasks import auto_generate_slots_task, auto_regenerate_slots_task

        if created:
            # New availability block - generate slots
            logger.info(f"Triggering auto-generation for new availability block {instance.availability_id}")
            auto_generate_slots_task.delay(instance.availability_id)

        else:
            # Updated availability block - regenerate slots
            logger.info(f"Triggering auto-regeneration for updated availability block {instance.availability_id}")
            auto_regenerate_slots_task.delay(instance.availability_id)

    except Exception as e:
        logger.error(f"Failed to trigger slot generation task for availability {instance.availability_id}: {str(e)}")
        # Don't raise exception - availability should still be saved even if slot generation fails


# Store availability data before deletion for cleanup
_availability_to_delete = {}

@receiver(pre_delete, sender=PsychologistAvailability)
def store_availability_before_delete(sender, instance, **kwargs):
    """
    Store availability information before deletion for cleanup
    """
    global _availability_to_delete
    _availability_to_delete[instance.pk] = {
        'availability_id': instance.availability_id,
        'psychologist_id': str(instance.psychologist.user.id)
    }


# @receiver(post_delete, sender=PsychologistAvailability)
# def auto_cleanup_slots_on_availability_delete(sender, **kwargs):
#     """
#     Signal handler to automatically clean up appointment slots
#     when availability blocks are deleted
#     """
#     # Check if auto-generation is enabled
#     if not getattr(settings, 'AUTO_GENERATE_APPOINTMENT_SLOTS', True):
#         return

#     try:
#         # Get the stored availability data
#         global _availability_to_delete
#         availability_data = _availability_to_delete.get(kwargs['instance'].pk)

#         if availability_data:
#             # Import here to avoid circular imports
#             from appointments.tasks import auto_cleanup_slots_task

#             logger.info(f"Triggering auto-cleanup for deleted availability block {availability_data['availability_id']}")
#             auto_cleanup_slots_task.delay(
#                 availability_data['availability_id'],
#                 availability_data['psychologist_id']
#             )

#             # Clean up stored data
#             del _availability_to_delete[kwargs['instance'].pk]

#     except Exception as e:
#         logger.error(f"Failed to trigger slot cleanup task: {str(e)}")