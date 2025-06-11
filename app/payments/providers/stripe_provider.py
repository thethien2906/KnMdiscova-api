# payments/providers/stripe_provider.py
import stripe
from typing import Dict, Any, Optional, List
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import logging

from .base_provider import (
    BasePaymentProvider,
    PaymentProviderConfigError,
    PaymentCreateError,
    PaymentProcessError,
    WebhookVerificationError,
    RefundError
)

logger = logging.getLogger(__name__)


class StripePaymentProvider(BasePaymentProvider):
    """
    Stripe payment provider implementation
    Handles Stripe API integration for payments, refunds, and webhooks
    """

    def __init__(self):
        super().__init__()
        # Configure Stripe with API key
        stripe.api_key = self.config['SECRET_KEY']
        stripe.api_version = "2023-10-16"  # Pin to specific API version for consistency

    def _get_provider_name(self) -> str:
        return 'stripe'

    def _get_provider_config(self) -> Dict[str, Any]:
        """Get Stripe configuration from Django settings"""
        return settings.PAYMENT_PROVIDERS.get('STRIPE', {})

    def _validate_config(self) -> None:
        """Validate Stripe configuration"""
        required_keys = ['SECRET_KEY', 'PUBLISHABLE_KEY', 'WEBHOOK_SECRET']

        for key in required_keys:
            if not self.config.get(key):
                raise PaymentProviderConfigError(f"Stripe {key} is required but not configured")

        # Validate API key format
        secret_key = self.config['SECRET_KEY']
        if not secret_key.startswith(('sk_test_', 'sk_live_')):
            raise PaymentProviderConfigError("Invalid Stripe secret key format")

        publishable_key = self.config['PUBLISHABLE_KEY']
        if not publishable_key.startswith(('pk_test_', 'pk_live_')):
            raise PaymentProviderConfigError("Invalid Stripe publishable key format")

        # Ensure test/live keys match
        is_secret_test = secret_key.startswith('sk_test_')
        is_publishable_test = publishable_key.startswith('pk_test_')

        if is_secret_test != is_publishable_test:
            raise PaymentProviderConfigError("Stripe secret and publishable keys must both be test or live keys")

    def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        metadata: Dict[str, Any],
        success_url: str,
        cancel_url: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Create Stripe payment intent"""
        try:
            # Validate inputs
            if not self.validate_currency_support(currency):
                raise PaymentCreateError(f"Currency {currency} not supported by Stripe")

            if not self.validate_amount_limits(amount, currency):
                raise PaymentCreateError(f"Amount {amount} {currency} is invalid")

            # Format amount for Stripe (in cents/smallest unit)
            stripe_amount = self.format_amount_for_provider(amount, currency)

            # Prepare metadata for Stripe
            stripe_metadata = self.prepare_metadata(metadata)

            # Create payment intent
            payment_intent_params = {
                'amount': stripe_amount,
                'currency': currency.lower(),
                'metadata': stripe_metadata,
                'automatic_payment_methods': {
                    'enabled': True,
                },
                'capture_method': 'automatic',  # Auto-capture when payment is confirmed
            }

            # Add description if provided
            if 'description' in kwargs:
                payment_intent_params['description'] = kwargs['description']

            # Add customer if provided
            if 'customer_id' in kwargs:
                payment_intent_params['customer'] = kwargs['customer_id']

            # Create the payment intent
            payment_intent = stripe.PaymentIntent.create(**payment_intent_params)

            self.log_provider_interaction('create_payment_intent', {
                'payment_intent_id': payment_intent.id,
                'amount': stripe_amount,
                'currency': currency,
                'status': payment_intent.status
            })

            return {
                'payment_intent_id': payment_intent.id,
                'client_secret': payment_intent.client_secret,
                'payment_url': None,  # Stripe uses client_secret for frontend integration
                'expires_at': timezone.now() + timedelta(minutes=settings.PAYMENT_SETTINGS['ORDER_EXPIRY_MINUTES']),
                'status': payment_intent.status,
                'provider_data': {
                    'stripe_payment_intent_id': payment_intent.id,
                    'stripe_client_secret': payment_intent.client_secret,
                    'stripe_status': payment_intent.status,
                    'stripe_amount': stripe_amount,
                    'stripe_currency': currency.lower(),
                    'raw_response': payment_intent.to_dict_recursive(),
                    'payment_method_type': 'card',
                }
            }

        except stripe.error.StripeError as e:
            self.log_provider_interaction('create_payment_intent', {
                'error': str(e),
                'error_type': type(e).__name__
            }, success=False)
            raise PaymentCreateError(f"Stripe error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error creating Stripe payment intent: {str(e)}")
            raise PaymentCreateError(f"Failed to create payment intent: {str(e)}")

    def confirm_payment(
        self,
        payment_intent_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Confirm/retrieve Stripe payment intent status"""
        try:
            # Retrieve payment intent to get current status
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)

            # Map Stripe status to our standard status
            status_mapping = {
                'succeeded': 'succeeded',
                'requires_payment_method': 'failed',
                'requires_confirmation': 'processing',
                'requires_action': 'processing',
                'processing': 'processing',
                'requires_capture': 'processing',
                'canceled': 'failed'
            }

            our_status = status_mapping.get(payment_intent.status, 'processing')
            payment_method_info = {
                'payment_method_type': 'card',  # Default to card
                'payment_method_details': {}
            }
            payment_method_info = {}
            try:
                # Safe access to charges
                if (hasattr(payment_intent, 'charges') and
                    payment_intent.charges and
                    hasattr(payment_intent.charges, 'data') and
                    payment_intent.charges.data):

                    charge = payment_intent.charges.data[0]
                    if hasattr(charge, 'payment_method_details') and charge.payment_method_details:
                        payment_method_info = {
                            'payment_method_type': charge.payment_method_details.type,
                            'payment_method_details': charge.payment_method_details.to_dict_recursive()
                        }
                elif hasattr(payment_intent, 'latest_charge') and payment_intent.latest_charge:
                    # Alternative: use latest_charge if charges collection is not available
                    charge = stripe.Charge.retrieve(payment_intent.latest_charge)
                    if hasattr(charge, 'payment_method_details') and charge.payment_method_details:
                        payment_method_info = {
                            'payment_method_type': charge.payment_method_details.type,
                            'payment_method_details': charge.payment_method_details.to_dict_recursive()
                        }
            except Exception as charge_error:
                # Log the error but don't fail the whole confirmation
                logger.warning(f"Could not retrieve charge details for payment intent {payment_intent_id}: {str(charge_error)}")
                payment_method_info = {}

            self.log_provider_interaction('confirm_payment', {
                'payment_intent_id': payment_intent_id,
                'stripe_status': payment_intent.status,
                'our_status': our_status,
                'amount': payment_intent.amount
            })

            return {
                'status': our_status,
                'payment_id': payment_intent.id,
                'amount': self.format_amount_from_provider(payment_intent.amount, payment_intent.currency),
                'currency': payment_intent.currency.upper(),
                'payment_method_info': payment_method_info,
                'provider_data': {
                    'stripe_payment_intent_id': payment_intent.id,
                    'stripe_status': payment_intent.status,
                    'stripe_amount': payment_intent.amount,
                    'stripe_currency': payment_intent.currency,
                    'raw_response': payment_intent.to_dict_recursive()
                }
            }

        except stripe.error.StripeError as e:
            self.log_provider_interaction('confirm_payment', {
                'payment_intent_id': payment_intent_id,
                'error': str(e),
                'error_type': type(e).__name__
            }, success=False)
            raise PaymentProcessError(f"Stripe error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error confirming Stripe payment: {str(e)}")
            raise PaymentProcessError(f"Failed to confirm payment: {str(e)}")

    def get_payment_status(
        self,
        payment_intent_id: str
    ) -> Dict[str, Any]:
        """Get Stripe payment intent status"""
        return self.confirm_payment(payment_intent_id)

    def create_refund(
        self,
        payment_id: str,
        amount: Optional[Decimal] = None,
        reason: str = "requested_by_customer",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create Stripe refund"""
        try:
            # First, get the payment intent to find the charge
            payment_intent = stripe.PaymentIntent.retrieve(payment_id)

            if not payment_intent.charges or not payment_intent.charges.data:
                raise RefundError("No charges found for this payment intent")

            # Get the latest charge
            charge = payment_intent.charges.data[0]

            if charge.status != 'succeeded':
                raise RefundError(f"Cannot refund charge with status: {charge.status}")

            # Prepare refund parameters
            refund_params = {
                'charge': charge.id,
                'reason': reason
            }

            # Add amount if specified (partial refund)
            if amount is not None:
                stripe_amount = self.format_amount_for_provider(amount, payment_intent.currency)
                refund_params['amount'] = stripe_amount

            # Add metadata if provided
            if metadata:
                refund_params['metadata'] = self.prepare_metadata(metadata)

            # Create refund
            refund = stripe.Refund.create(**refund_params)

            self.log_provider_interaction('create_refund', {
                'refund_id': refund.id,
                'charge_id': charge.id,
                'amount': refund.amount,
                'status': refund.status
            })

            return {
                'refund_id': refund.id,
                'amount': self.format_amount_from_provider(refund.amount, refund.currency),
                'currency': refund.currency.upper(),
                'status': refund.status,
                'provider_data': {
                    'stripe_refund_id': refund.id,
                    'stripe_charge_id': charge.id,
                    'stripe_status': refund.status,
                    'stripe_amount': refund.amount,
                    'stripe_currency': refund.currency,
                    'raw_response': refund.to_dict_recursive()
                }
            }

        except stripe.error.StripeError as e:
            self.log_provider_interaction('create_refund', {
                'payment_id': payment_id,
                'error': str(e),
                'error_type': type(e).__name__
            }, success=False)
            raise RefundError(f"Stripe error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error creating Stripe refund: {str(e)}")
            raise RefundError(f"Failed to create refund: {str(e)}")

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        endpoint_secret: str
    ) -> bool:
        """Verify Stripe webhook signature"""
        try:
            stripe.Webhook.construct_event(
                payload=payload,
                sig_header=signature,
                secret=endpoint_secret
            )
            return True
        except stripe.error.SignatureVerificationError:
            return False
        except Exception as e:
            logger.error(f"Error verifying Stripe webhook signature: {str(e)}")
            return False

    def parse_webhook_event(
        self,
        payload: bytes,
        signature: str
    ) -> Dict[str, Any]:
        """Parse and validate Stripe webhook event"""
        try:
            # Verify and construct event
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=signature,
                secret=self.config['WEBHOOK_SECRET']
            )

            self.log_provider_interaction('parse_webhook_event', {
                'event_type': event['type'],
                'event_id': event['id']
            })

            # Extract relevant information based on event type
            event_data = {
                'event_type': event['type'],
                'event_id': event['id'],
                'created': event['created'],
                'livemode': event['livemode'],
                'data': event['data'],
                'provider_data': event
            }

            # Extract payment intent ID if available
            if 'object' in event['data'] and 'id' in event['data']['object']:
                obj = event['data']['object']

                if obj.get('object') == 'payment_intent':
                    event_data['payment_intent_id'] = obj['id']
                    event_data['payment_id'] = obj['id']
                elif obj.get('object') == 'charge':
                    event_data['payment_id'] = obj.get('payment_intent')
                    event_data['payment_intent_id'] = obj.get('payment_intent')
                    event_data['charge_id'] = obj['id']
                elif obj.get('object') == 'refund':
                    event_data['refund_id'] = obj['id']
                    event_data['charge_id'] = obj.get('charge')
                    # Try to get payment intent from charge
                    if obj.get('charge'):
                        try:
                            charge = stripe.Charge.retrieve(obj['charge'])
                            event_data['payment_intent_id'] = charge.payment_intent
                            event_data['payment_id'] = charge.payment_intent
                        except:
                            pass

            return event_data

        except stripe.error.SignatureVerificationError as e:
            self.log_provider_interaction('parse_webhook_event', {
                'error': 'Invalid signature',
                'error_type': 'SignatureVerificationError'
            }, success=False)
            raise WebhookVerificationError(f"Invalid webhook signature: {str(e)}")
        except Exception as e:
            logger.error(f"Error parsing Stripe webhook event: {str(e)}")
            raise WebhookVerificationError(f"Failed to parse webhook event: {str(e)}")

    def get_supported_currencies(self) -> List[str]:
        """Get currencies supported by Stripe"""
        # Stripe supports many currencies, but we'll return our configured ones
        return settings.PAYMENT_SETTINGS.get('SUPPORTED_CURRENCIES', ['USD'])

    def get_payment_methods(self) -> List[str]:
        """Get payment methods supported by Stripe"""
        return ['card', 'bank_transfer', 'digital_wallet']

    def validate_amount_limits(self, amount: Decimal, currency: str) -> bool:
        """Validate amount against Stripe limits"""
        # Stripe minimum amounts vary by currency
        minimums = {
            'USD': Decimal('0.50'),
            'EUR': Decimal('0.50'),
            'GBP': Decimal('0.30'),
        }

        minimum = minimums.get(currency.upper(), Decimal('0.50'))

        # Stripe maximum is typically $999,999.99 for most currencies
        maximum = Decimal('999999.99')

        return minimum <= amount <= maximum

    def get_provider_fees(self, amount: Decimal, currency: str) -> Dict[str, Decimal]:
        """
        Estimate Stripe fees (for display purposes only)
        Note: Actual fees may vary based on card type, country, etc.
        """
        # Basic Stripe fee structure (as of 2024)
        if currency.upper() == 'USD':
            percentage_fee = Decimal('0.029')  # 2.9%
            fixed_fee = Decimal('0.30')  # $0.30
        else:
            # International cards typically have higher fees
            percentage_fee = Decimal('0.034')  # 3.4%
            fixed_fee = Decimal('0.30')

        provider_fee = (amount * percentage_fee) + fixed_fee

        return {
            'provider_fee': provider_fee,
            'platform_fee': Decimal('0.00')  # We're not adding additional platform fees
        }

    def create_customer(self, email: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Create Stripe customer (useful for storing payment methods)
        """
        try:
            customer_params = {
                'email': email
            }

            if metadata:
                customer_params['metadata'] = self.prepare_metadata(metadata)

            customer = stripe.Customer.create(**customer_params)

            self.log_provider_interaction('create_customer', {
                'customer_id': customer.id,
                'email': email
            })

            return customer.id

        except stripe.error.StripeError as e:
            self.log_provider_interaction('create_customer', {
                'email': email,
                'error': str(e),
                'error_type': type(e).__name__
            }, success=False)
            raise PaymentCreateError(f"Failed to create Stripe customer: {str(e)}")

    def get_webhook_events_to_monitor(self) -> List[str]:
        """
        Get list of Stripe webhook events we want to monitor
        """
        return [
            'payment_intent.succeeded',
            'payment_intent.payment_failed',
            'payment_intent.requires_action',
            'payment_intent.canceled',
            'charge.succeeded',
            'charge.failed',
            'charge.dispute.created',
            'invoice.payment_succeeded',
            'invoice.payment_failed',
            'customer.subscription.created',
            'customer.subscription.updated',
            'customer.subscription.deleted',
            'refund.created',
            'refund.updated'
        ]