from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from decimal import Decimal
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class PaymentProviderError(Exception):
    """Base exception for payment provider errors"""
    pass


class PaymentProviderConfigError(PaymentProviderError):
    """Raised when provider configuration is invalid"""
    pass


class PaymentCreateError(PaymentProviderError):
    """Raised when payment creation fails"""
    pass


class PaymentProcessError(PaymentProviderError):
    """Raised when payment processing fails"""
    pass


class WebhookVerificationError(PaymentProviderError):
    """Raised when webhook verification fails"""
    pass


class RefundError(PaymentProviderError):
    """Raised when refund processing fails"""
    pass


class BasePaymentProvider(ABC):
    """
    Abstract base class for payment providers
    Defines the interface that all payment providers must implement
    """

    def __init__(self):
        self.provider_name = self._get_provider_name()
        self.config = self._get_provider_config()
        self._validate_config()

    @abstractmethod
    def _get_provider_name(self) -> str:
        """Return the provider name (e.g., 'stripe', 'paypal')"""
        pass

    @abstractmethod
    def _get_provider_config(self) -> Dict[str, Any]:
        """Return provider-specific configuration from settings"""
        pass

    @abstractmethod
    def _validate_config(self) -> None:
        """Validate provider configuration, raise PaymentProviderConfigError if invalid"""
        pass

    @abstractmethod
    def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        metadata: Dict[str, Any],
        success_url: str,
        cancel_url: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a payment intent with the provider

        Args:
            amount: Payment amount
            currency: Currency code (e.g., 'USD')
            metadata: Additional metadata to store with payment
            success_url: URL to redirect to on successful payment
            cancel_url: URL to redirect to on cancelled payment
            **kwargs: Provider-specific additional parameters

        Returns:
            Dict containing:
                - payment_intent_id: Provider's payment intent ID
                - client_secret: Secret for client-side payment confirmation (if applicable)
                - payment_url: URL to redirect user for payment (if applicable)
                - expires_at: When the payment intent expires
                - provider_data: Raw provider response data

        Raises:
            PaymentCreateError: If payment intent creation fails
        """
        pass

    @abstractmethod
    def confirm_payment(
        self,
        payment_intent_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Confirm/capture a payment

        Args:
            payment_intent_id: Provider's payment intent ID
            **kwargs: Provider-specific parameters

        Returns:
            Dict containing:
                - status: Payment status ('succeeded', 'failed', 'processing')
                - payment_id: Provider's payment ID
                - amount: Confirmed amount
                - currency: Payment currency
                - provider_data: Raw provider response data

        Raises:
            PaymentProcessError: If payment confirmation fails
        """
        pass

    @abstractmethod
    def get_payment_status(
        self,
        payment_intent_id: str
    ) -> Dict[str, Any]:
        """
        Get current payment status from provider

        Args:
            payment_intent_id: Provider's payment intent ID

        Returns:
            Dict containing:
                - status: Current payment status
                - payment_id: Provider's payment ID (if available)
                - amount: Payment amount
                - currency: Payment currency
                - provider_data: Raw provider response data

        Raises:
            PaymentProcessError: If status retrieval fails
        """
        pass

    @abstractmethod
    def create_refund(
        self,
        payment_id: str,
        amount: Optional[Decimal] = None,
        reason: str = "requested_by_customer",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a refund for a payment

        Args:
            payment_id: Provider's payment ID
            amount: Refund amount (None for full refund)
            reason: Reason for refund
            metadata: Additional refund metadata

        Returns:
            Dict containing:
                - refund_id: Provider's refund ID
                - amount: Refunded amount
                - currency: Refund currency
                - status: Refund status
                - provider_data: Raw provider response data

        Raises:
            RefundError: If refund creation fails
        """
        pass

    @abstractmethod
    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        endpoint_secret: str
    ) -> bool:
        """
        Verify webhook signature from provider

        Args:
            payload: Raw webhook payload
            signature: Webhook signature header
            endpoint_secret: Webhook endpoint secret

        Returns:
            True if signature is valid, False otherwise

        Raises:
            WebhookVerificationError: If verification fails
        """
        pass

    @abstractmethod
    def parse_webhook_event(
        self,
        payload: bytes,
        signature: str
    ) -> Dict[str, Any]:
        """
        Parse and validate webhook event

        Args:
            payload: Raw webhook payload
            signature: Webhook signature header

        Returns:
            Dict containing:
                - event_type: Type of webhook event
                - event_id: Unique event ID
                - payment_intent_id: Associated payment intent ID (if applicable)
                - payment_id: Associated payment ID (if applicable)
                - data: Event data
                - provider_data: Raw provider event data

        Raises:
            WebhookVerificationError: If webhook verification fails
        """
        pass

    def is_enabled(self) -> bool:
        """Check if provider is enabled"""
        return self.config.get('ENABLED', False)

    def get_supported_currencies(self) -> List[str]:
        """Get list of currencies supported by this provider"""
        # Default implementation - override in provider classes if needed
        return settings.PAYMENT_SETTINGS.get('SUPPORTED_CURRENCIES', ['USD'])

    def get_webhook_endpoint_url(self, base_url: str) -> str:
        """Get full webhook endpoint URL for this provider"""
        endpoint = self.config.get('WEBHOOK_ENDPOINT', f'/api/payments/webhooks/{self.provider_name}/')
        return f"{base_url.rstrip('/')}{endpoint}"

    def format_amount_for_provider(self, amount: Decimal, currency: str) -> int:
        """
        Format amount for provider API (most providers use cents/smallest unit)
        Override this method if provider has different formatting requirements
        """
        # Convert to smallest currency unit (e.g., cents for USD)
        if currency.upper() in ['USD', 'EUR', 'GBP', 'CAD', 'AUD']:
            return int(amount * 100)  # Convert to cents
        elif currency.upper() in ['JPY', 'KRW']:
            return int(amount)  # No decimal places
        else:
            # Default: assume 2 decimal places, convert to smallest unit
            return int(amount * 100)

    def format_amount_from_provider(self, amount: int, currency: str) -> Decimal:
        """
        Format amount from provider API back to Decimal
        """
        if currency.upper() in ['USD', 'EUR', 'GBP', 'CAD', 'AUD']:
            return Decimal(amount) / 100  # Convert from cents
        elif currency.upper() in ['JPY', 'KRW']:
            return Decimal(amount)  # No conversion needed
        else:
            # Default: assume amount is in smallest unit
            return Decimal(amount) / 100

    def log_provider_interaction(self, action: str, data: Dict[str, Any], success: bool = True):
        """Log provider interactions for debugging and audit"""
        log_data = {
            'provider': self.provider_name,
            'action': action,
            'success': success,
            'data_keys': list(data.keys()) if isinstance(data, dict) else 'non-dict'
        }

        if success:
            logger.info(f"Payment provider interaction: {log_data}")
        else:
            logger.error(f"Payment provider interaction failed: {log_data}")

    def get_payment_methods(self) -> List[str]:
        """
        Get available payment methods for this provider
        Override in provider classes
        """
        return ['card']  # Default to card payments

    def get_provider_fees(self, amount: Decimal, currency: str) -> Dict[str, Decimal]:
        """
        Calculate provider fees (if needed for display purposes)
        Override in provider classes if you want to show fee estimates
        """
        return {
            'provider_fee': Decimal('0.00'),
            'platform_fee': Decimal('0.00')
        }

    def validate_currency_support(self, currency: str) -> bool:
        """Check if currency is supported by this provider"""
        supported = self.get_supported_currencies()
        return currency.upper() in [c.upper() for c in supported]

    def validate_amount_limits(self, amount: Decimal, currency: str) -> bool:
        """
        Validate amount against provider limits
        Override in provider classes with specific limits
        """
        # Default validation: amount must be positive
        return amount > Decimal('0.00')

    def prepare_metadata(self, order_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Prepare metadata for provider API
        Most providers require string values in metadata
        """
        metadata = {}

        # Add common metadata fields
        if 'order_id' in order_data:
            metadata['order_id'] = str(order_data['order_id'])

        if 'order_type' in order_data:
            metadata['order_type'] = str(order_data['order_type'])

        if 'user_id' in order_data:
            metadata['user_id'] = str(order_data['user_id'])

        if 'psychologist_id' in order_data:
            metadata['psychologist_id'] = str(order_data['psychologist_id'])

        if 'appointment_id' in order_data:
            metadata['appointment_id'] = str(order_data['appointment_id'])

        # Limit metadata size (many providers have limits)
        limited_metadata = {}
        total_size = 0
        max_size = 1000  # Conservative limit

        for key, value in metadata.items():
            item_size = len(f"{key}:{value}")
            if total_size + item_size < max_size:
                limited_metadata[key] = value
                total_size += item_size

        return limited_metadata