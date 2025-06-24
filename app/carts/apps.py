# carts/apps.py
from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class CartsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'carts'
    verbose_name = 'Shopping Cart System'

    def ready(self):
        """
        Initialize carts app when Django starts
        """
        # Import signals if we have any
        try:
            import carts.signals  # noqa
        except ImportError:
            pass

        logger.info("Cart system initialized successfully")