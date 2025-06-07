# appointments/tasks.py
from celery import shared_task
from django.utils import timezone
import logging

from .services import AppointmentSlotService
from psychologists.models import PsychologistAvailability

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