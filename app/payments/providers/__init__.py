from typing import Dict, Type, Optional, List
from django.conf import settings
import logging

from .base_provider import BasePaymentProvider, PaymentProviderConfigError
from .stripe_provider import StripePaymentProvider

logger = logging.getLogger(__name__)


class PaymentProviderFactory:
    """
    Factory class for creating payment provider instances
    Manages provider registration and instantiation
    """

    # Registry of available providers
    _providers: Dict[str, Type[BasePaymentProvider]] = {
        'stripe': StripePaymentProvider,
        # 'paypal': PayPalPaymentProvider,  # Will be added later
    }

    # Cache for provider instances
    _instances: Dict[str, BasePaymentProvider] = {}

    @classmethod
    def register_provider(cls, name: str, provider_class: Type[BasePaymentProvider]) -> None:
        """
        Register a new payment provider

        Args:
            name: Provider name (e.g., 'stripe', 'paypal')
            provider_class: Provider class that extends BasePaymentProvider
        """
        if not issubclass(provider_class, BasePaymentProvider):
            raise ValueError(f"Provider class must extend BasePaymentProvider")

        cls._providers[name.lower()] = provider_class

        # Clear cached instance if it exists
        if name.lower() in cls._instances:
            del cls._instances[name.lower()]

        logger.info(f"Registered payment provider: {name}")

    @classmethod
    def get_provider(cls, name: str) -> BasePaymentProvider:
        """
        Get payment provider instance by name

        Args:
            name: Provider name (e.g., 'stripe', 'paypal')

        Returns:
            Payment provider instance

        Raises:
            PaymentProviderConfigError: If provider not found or misconfigured
        """
        name = name.lower()

        # Return cached instance if available
        if name in cls._instances:
            return cls._instances[name]

        # Check if provider is registered
        if name not in cls._providers:
            available = ', '.join(cls._providers.keys())
            raise PaymentProviderConfigError(
                f"Payment provider '{name}' not found. Available providers: {available}"
            )

        try:
            # Create new instance
            provider_class = cls._providers[name]
            instance = provider_class()

            # Cache the instance
            cls._instances[name] = instance

            logger.info(f"Created payment provider instance: {name}")
            return instance

        except Exception as e:
            logger.error(f"Failed to create payment provider '{name}': {str(e)}")
            raise PaymentProviderConfigError(f"Failed to initialize payment provider '{name}': {str(e)}")

    @classmethod
    def get_enabled_providers(cls) -> List[BasePaymentProvider]:
        """
        Get all enabled payment providers

        Returns:
            List of enabled payment provider instances
        """
        enabled_providers = []

        for name in cls._providers.keys():
            try:
                provider = cls.get_provider(name)
                if provider.is_enabled():
                    enabled_providers.append(provider)
            except PaymentProviderConfigError as e:
                logger.warning(f"Skipping provider '{name}' due to configuration error: {str(e)}")
            except Exception as e:
                logger.error(f"Unexpected error checking provider '{name}': {str(e)}")

        return enabled_providers

    @classmethod
    def get_provider_names(cls) -> List[str]:
        """
        Get list of all registered provider names

        Returns:
            List of provider names
        """
        return list(cls._providers.keys())

    @classmethod
    def get_enabled_provider_names(cls) -> List[str]:
        """
        Get list of enabled provider names

        Returns:
            List of enabled provider names
        """
        enabled_names = []

        for name in cls._providers.keys():
            try:
                provider = cls.get_provider(name)
                if provider.is_enabled():
                    enabled_names.append(name)
            except Exception:
                pass  # Skip providers with configuration issues

        return enabled_names

    @classmethod
    def get_default_provider(cls) -> BasePaymentProvider:
        """
        Get the default payment provider

        Returns:
            Default payment provider instance

        Raises:
            PaymentProviderConfigError: If no providers are enabled
        """
        enabled_providers = cls.get_enabled_providers()

        if not enabled_providers:
            raise PaymentProviderConfigError("No payment providers are enabled")

        # Priority order: Stripe first, then others
        provider_priority = ['stripe', 'paypal']

        for provider_name in provider_priority:
            for provider in enabled_providers:
                if provider.provider_name.lower() == provider_name:
                    return provider

        # If no priority provider found, return the first enabled one
        return enabled_providers[0]

    @classmethod
    def validate_all_providers(cls) -> Dict[str, bool]:
        """
        Validate configuration for all registered providers

        Returns:
            Dict mapping provider names to validation status
        """
        validation_results = {}

        for name in cls._providers.keys():
            try:
                provider = cls.get_provider(name)
                validation_results[name] = provider.is_enabled()
            except Exception as e:
                logger.error(f"Validation failed for provider '{name}': {str(e)}")
                validation_results[name] = False

        return validation_results

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached provider instances"""
        cls._instances.clear()
        logger.info("Cleared payment provider cache")


# Convenience functions for easy access
def get_payment_provider(name: str) -> BasePaymentProvider:
    """Get payment provider by name"""
    return PaymentProviderFactory.get_provider(name)


def get_default_payment_provider() -> BasePaymentProvider:
    """Get default payment provider"""
    return PaymentProviderFactory.get_default_provider()


def get_enabled_payment_providers() -> List[BasePaymentProvider]:
    """Get all enabled payment providers"""
    return PaymentProviderFactory.get_enabled_providers()