# payments/apps.py
from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class PaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payments'
    verbose_name = 'Payment System'

    def ready(self):
        """
        Initialize payments app when Django starts
        """
        # Import signals if we have any
        try:
            import payments.signals  # noqa
        except ImportError:
            pass

        # Validate payment provider configuration
        self._validate_payment_configuration()

    def _validate_payment_configuration(self):
        """Validate payment provider configuration on startup"""
        try:
            from django.conf import settings
            from .providers import PaymentProviderFactory

            # Check if payment providers are configured
            if not hasattr(settings, 'PAYMENT_PROVIDERS'):
                logger.warning("PAYMENT_PROVIDERS not configured in settings")
                return

            # Validate each provider
            validation_results = PaymentProviderFactory.validate_all_providers()

            enabled_count = sum(1 for valid in validation_results.values() if valid)
            total_count = len(validation_results)

            logger.info(f"Payment providers validation: {enabled_count}/{total_count} enabled")

            for provider_name, is_valid in validation_results.items():
                if is_valid:
                    logger.info(f"✅ Payment provider '{provider_name}' is enabled and configured")
                else:
                    logger.warning(f"⚠️  Payment provider '{provider_name}' is disabled or misconfigured")

            if enabled_count == 0:
                logger.error("❌ No payment providers are enabled! Payment functionality will not work.")

        except Exception as e:
            logger.error(f"Error validating payment configuration: {str(e)}")