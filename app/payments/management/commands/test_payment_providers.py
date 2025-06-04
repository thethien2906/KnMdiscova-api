from django.core.management.base import BaseCommand
from django.conf import settings
from decimal import Decimal
import json

from payments.providers import PaymentProviderFactory, PaymentProviderConfigError


class Command(BaseCommand):
    help = 'Test payment provider configurations and basic functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--provider',
            type=str,
            help='Test specific provider (e.g., stripe, paypal)',
        )
        parser.add_argument(
            '--test-create-intent',
            action='store_true',
            help='Test creating a payment intent (uses test amount)',
        )

    def handle(self, *args, **options):
        self.stdout.write("Testing payment providers...")

        provider_name = options.get('provider')
        test_create_intent = options.get('test_create_intent', False)

        if provider_name:
            self._test_single_provider(provider_name, test_create_intent)
        else:
            self._test_all_providers(test_create_intent)

    def _test_all_providers(self, test_create_intent=False):
        """Test all registered providers"""
        provider_names = PaymentProviderFactory.get_provider_names()

        self.stdout.write(f"Found {len(provider_names)} registered providers")

        for provider_name in provider_names:
            self.stdout.write(f"\n{'='*50}")
            self.stdout.write(f"Testing provider: {provider_name}")
            self.stdout.write('='*50)

            self._test_single_provider(provider_name, test_create_intent)

    def _test_single_provider(self, provider_name, test_create_intent=False):
        """Test a single provider"""
        try:
            # Get provider instance
            provider = PaymentProviderFactory.get_provider(provider_name)

            self.stdout.write(
                self.style.SUCCESS(f"✅ Provider '{provider_name}' instance created successfully")
            )

            # Test basic configuration
            self._test_provider_config(provider)

            # Test enabled status
            if provider.is_enabled():
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Provider '{provider_name}' is enabled")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"⚠️  Provider '{provider_name}' is disabled")
                )
                return

            # Test supported currencies
            self._test_supported_currencies(provider)

            # Test payment methods
            self._test_payment_methods(provider)

            # Test amount validation
            self._test_amount_validation(provider)

            # Test create payment intent (if requested)
            if test_create_intent:
                self._test_create_payment_intent(provider)

        except PaymentProviderConfigError as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Configuration error for '{provider_name}': {str(e)}")
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Unexpected error testing '{provider_name}': {str(e)}")
            )

    def _test_provider_config(self, provider):
        """Test provider configuration"""
        try:
            config = provider.config

            self.stdout.write(f"Provider configuration:")
            for key, value in config.items():
                if 'secret' in key.lower() or 'key' in key.lower():
                    # Hide sensitive values
                    display_value = f"{value[:8]}..." if value and len(value) > 8 else "***"
                else:
                    display_value = value

                self.stdout.write(f"  {key}: {display_value}")

            self.stdout.write(
                self.style.SUCCESS("✅ Provider configuration loaded")
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Error testing configuration: {str(e)}")
            )

    def _test_supported_currencies(self, provider):
        """Test supported currencies"""
        try:
            currencies = provider.get_supported_currencies()
            self.stdout.write(f"Supported currencies: {', '.join(currencies)}")

            # Test currency validation
            for currency in ['USD', 'EUR', 'GBP']:
                is_supported = provider.validate_currency_support(currency)
                status = "✅" if is_supported else "❌"
                self.stdout.write(f"  {currency}: {status}")

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Error testing currencies: {str(e)}")
            )

    def _test_payment_methods(self, provider):
        """Test payment methods"""
        try:
            methods = provider.get_payment_methods()
            self.stdout.write(f"Payment methods: {', '.join(methods)}")

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Error testing payment methods: {str(e)}")
            )

    def _test_amount_validation(self, provider):
        """Test amount validation"""
        try:
            test_amounts = [
                (Decimal('0.50'), 'USD'),  # Minimum
                (Decimal('100.00'), 'USD'),  # Normal
                (Decimal('999999.99'), 'USD'),  # Maximum
                (Decimal('0.01'), 'USD'),  # Too small
                (Decimal('9999999.99'), 'USD'),  # Too large
            ]

            self.stdout.write("Amount validation tests:")
            for amount, currency in test_amounts:
                is_valid = provider.validate_amount_limits(amount, currency)
                status = "✅" if is_valid else "❌"
                self.stdout.write(f"  {amount} {currency}: {status}")

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Error testing amount validation: {str(e)}")
            )

    def _test_create_payment_intent(self, provider):
        """Test creating a payment intent (BE CAREFUL - this might create real charges in live mode!)"""
        try:
            self.stdout.write(
                self.style.WARNING("⚠️  Testing payment intent creation...")
            )

            # Use test data
            test_data = {
                'amount': Decimal('10.00'),  # $10 test amount
                'currency': 'USD',
                'metadata': {
                    'order_id': 'test-order-123',
                    'order_type': 'test',
                    'user_id': 'test-user-456'
                },
                'success_url': 'https://example.com/success',
                'cancel_url': 'https://example.com/cancel',
                'description': 'Test payment intent'
            }

            result = provider.create_payment_intent(**test_data)

            self.stdout.write(
                self.style.SUCCESS("✅ Payment intent created successfully")
            )

            self.stdout.write("Payment intent details:")
            for key, value in result.items():
                if key == 'provider_data':
                    self.stdout.write(f"  {key}: [Provider-specific data]")
                else:
                    self.stdout.write(f"  {key}: {value}")

            # Test getting payment status
            if 'payment_intent_id' in result:
                self.stdout.write("\nTesting payment status retrieval...")
                status_result = provider.get_payment_status(result['payment_intent_id'])
                self.stdout.write(f"Payment status: {status_result.get('status', 'unknown')}")

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Error testing payment intent creation: {str(e)}")
            )
            self.stdout.write(
                self.style.WARNING("Note: This could be due to test API limits or configuration issues")
            )