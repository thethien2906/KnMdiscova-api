# payments/services.py
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
from datetime import timedelta
from typing import Dict, Any, Optional, Tuple
import logging
import uuid

from .models import Order, Payment, Transaction
from .providers import get_payment_provider, get_default_payment_provider, PaymentProviderConfigError
from users.models import User
from psychologists.models import Psychologist
# from appointments.models import Appointment  # Will be imported when appointments app is ready

logger = logging.getLogger(__name__)


class PaymentServiceError(Exception):
    """Base exception for payment service errors"""
    pass


class OrderCreationError(PaymentServiceError):
    """Raised when order creation fails"""
    pass


class PaymentProcessingError(PaymentServiceError):
    """Raised when payment processing fails"""
    pass


class RefundError(PaymentServiceError):
    """Raised when refund processing fails"""
    pass


class PricingService:
    """
    Service for handling pricing calculations and configurations
    """

    @staticmethod
    def get_service_price(service_type: str, currency: str = 'USD') -> Decimal:
        """
        Get price for a specific service type

        Args:
            service_type: 'psychologist_registration', 'online_session', or 'initial_consultation'
            currency: Currency code (default: USD)

        Returns:
            Price as Decimal

        Raises:
            PaymentServiceError: If service type or currency not supported
        """
        try:
            service_key = service_type.upper()
            if service_key not in settings.PAYMENT_AMOUNTS:
                raise PaymentServiceError(f"Unknown service type: {service_type}")

            currency_prices = settings.PAYMENT_AMOUNTS[service_key]
            if currency not in currency_prices:
                raise PaymentServiceError(f"Currency {currency} not supported for {service_type}")

            return currency_prices[currency]

        except KeyError as e:
            raise PaymentServiceError(f"Pricing configuration error: {str(e)}")

    @staticmethod
    def get_all_service_prices(currency: str = 'USD') -> Dict[str, Decimal]:
        """
        Get all service prices for a currency

        Args:
            currency: Currency code

        Returns:
            Dict mapping service types to prices
        """
        prices = {}

        try:
            for service_type in settings.PAYMENT_AMOUNTS.keys():
                service_name = service_type.lower()
                prices[service_name] = PricingService.get_service_price(service_name, currency)
        except Exception as e:
            logger.error(f"Error getting service prices: {str(e)}")

        return prices

    @staticmethod
    def calculate_total_with_fees(base_amount: Decimal, currency: str = 'USD',
                                 provider_name: str = 'stripe') -> Dict[str, Decimal]:
        """
        Calculate total amount including provider fees

        Args:
            base_amount: Base service amount
            currency: Currency code
            provider_name: Payment provider name

        Returns:
            Dict with breakdown of amounts
        """
        try:
            provider = get_payment_provider(provider_name)
            fees = provider.get_provider_fees(base_amount, currency)

            return {
                'base_amount': base_amount,
                'provider_fee': fees.get('provider_fee', Decimal('0.00')),
                'platform_fee': fees.get('platform_fee', Decimal('0.00')),
                'total_amount': base_amount + fees.get('provider_fee', Decimal('0.00')) + fees.get('platform_fee', Decimal('0.00'))
            }
        except Exception as e:
            logger.error(f"Error calculating fees: {str(e)}")
            return {
                'base_amount': base_amount,
                'provider_fee': Decimal('0.00'),
                'platform_fee': Decimal('0.00'),
                'total_amount': base_amount
            }


class OrderService:
    """
    Service for managing payment orders
    """
    @staticmethod
    def cleanup_expired_orders(user=None):
        """Clean up expired orders automatically"""
        from django.utils import timezone

        expired_orders = Order.objects.filter(
            status='pending',
            expires_at__lt=timezone.now()
        )

        if user:
            expired_orders = expired_orders.filter(user=user)

        cancelled_count = 0
        for order in expired_orders:
            if OrderService.cancel_order(order, "Auto-cancelled: Order expired"):
                cancelled_count += 1

        return cancelled_count
    @staticmethod
    def create_psychologist_registration_order(
        psychologist: Psychologist,
        currency: str = 'USD',
        provider_name: str = 'stripe'
    ) -> Order:
        """
        Create order for psychologist registration payment

        Args:
            psychologist: Psychologist instance
            currency: Currency code
            provider_name: Payment provider name

        Returns:
            Created Order instance

        Raises:
            OrderCreationError: If order creation fails
        """

        try:
            with transaction.atomic():
                # Get service price
                amount = PricingService.get_service_price('psychologist_registration', currency)

                # Create order
                order = Order.objects.create(
                    order_type='psychologist_registration',
                    user=psychologist.user,
                    psychologist=psychologist,
                    amount=amount,
                    currency=currency,
                    payment_provider=provider_name,
                    description=f"Registration fee for {psychologist.full_name}",
                    expires_at=timezone.now() + timedelta(
                        minutes=settings.PAYMENT_SETTINGS['ORDER_EXPIRY_MINUTES']
                    ),
                    metadata={
                        'psychologist_id': str(psychologist.user.id),
                        'psychologist_name': psychologist.full_name,
                        'service_type': 'psychologist_registration'
                    }
                )

                # Create transaction record
                Transaction.create_transaction(
                    order=order,
                    transaction_type='order_created',
                    description=f"Registration order created for {psychologist.full_name}",
                    amount=amount,
                    currency=currency,
                    initiated_by=psychologist.user,
                    metadata={
                        'order_type': 'psychologist_registration',
                        'psychologist_id': str(psychologist.user.id)
                    }
                )

                logger.info(f"Created registration order {order.order_id} for psychologist {psychologist.user.email}")
                return order

        except Exception as e:
            logger.error(f"Failed to create registration order for {psychologist.user.email}: {str(e)}")
            raise OrderCreationError(f"Failed to create registration order: {str(e)}")

    @staticmethod
    def create_appointment_booking_order(
        user: User,
        psychologist: Psychologist,
        # appointment: Appointment,  # Will be uncommented when appointments app is ready
        session_type: str,  # 'online_session' or 'initial_consultation'
        currency: str = 'USD',
        provider_name: str = 'stripe',
        appointment_date: str = None  # Temporary for testing
    ) -> Order:
        """
        Create order for appointment booking payment

        Args:
            user: User booking the appointment (parent)
            psychologist: Psychologist for the appointment
            session_type: Type of session ('online_session' or 'initial_consultation')
            currency: Currency code
            provider_name: Payment provider name

        Returns:
            Created Order instance

        Raises:
            OrderCreationError: If order creation fails
        """
        try:
            with transaction.atomic():
                # Validate session type
                if session_type not in ['online_session', 'initial_consultation']:
                    raise OrderCreationError(f"Invalid session type: {session_type}")

                # Get service price
                amount = PricingService.get_service_price(session_type, currency)

                # Create order (temporarily without appointment constraint)
                order = Order.objects.create(
                    order_type='appointment_booking',
                    user=user,
                    psychologist=psychologist,
                    # appointment=appointment,  # Will be uncommented when appointments app is ready
                    amount=amount,
                    currency=currency,
                    payment_provider=provider_name,
                    description=f"{session_type.replace('_', ' ').title()} with {psychologist.full_name}",
                    expires_at=timezone.now() + timedelta(
                        minutes=settings.PAYMENT_SETTINGS['ORDER_EXPIRY_MINUTES']
                    ),
                    metadata={
                        'user_id': str(user.id),
                        'psychologist_id': str(psychologist.user.id),
                        'psychologist_name': psychologist.full_name,
                        'session_type': session_type,
                        'appointment_date': appointment_date or 'TBD',  # Temporary
                        # 'appointment_id': str(appointment.id),  # Will be uncommented
                        # 'appointment_date': appointment.appointment_date.isoformat(),  # Will be uncommented
                    }
                )

                # Create transaction record
                Transaction.create_transaction(
                    order=order,
                    transaction_type='order_created',
                    description=f"Appointment booking order created for {session_type} with {psychologist.full_name}",
                    amount=amount,
                    currency=currency,
                    initiated_by=user,
                    metadata={
                        'order_type': 'appointment_booking',
                        'session_type': session_type,
                        'psychologist_id': str(psychologist.user.id)
                    }
                )

                logger.info(f"Created appointment order {order.order_id} for user {user.email}")
                return order

        except Exception as e:
            logger.error(f"Failed to create appointment order for {user.email}: {str(e)}")
            raise OrderCreationError(f"Failed to create appointment order: {str(e)}")

    @staticmethod
    def get_order_by_id(order_id: str, user: User = None) -> Optional[Order]:
        """
        Get order by ID with optional user filtering

        Args:
            order_id: Order UUID
            user: Optional user to filter by

        Returns:
            Order instance or None
        """
        try:
            queryset = Order.objects.select_related('user', 'psychologist', 'psychologist__user')

            if user:
                queryset = queryset.filter(user=user)

            return queryset.get(order_id=order_id)

        except Order.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error retrieving order {order_id}: {str(e)}")
            return None

    @staticmethod
    def cancel_order(order: Order, reason: str = "Cancelled by user") -> bool:
        """
        Cancel an order with improved error handling
        """
        try:
            with transaction.atomic():
                if order.status != 'pending':
                    logger.warning(f"Cannot cancel order {order.order_id} with status: {order.status}")
                    raise PaymentServiceError(f"Cannot cancel order with status: {order.status}")

                # Update order status
                old_status = order.status
                order.status = 'cancelled'
                order.save(update_fields=['status', 'updated_at'])

                # Create transaction record with error handling
                try:
                    Transaction.create_transaction(
                        order=order,
                        transaction_type='status_change',
                        description=f"Order cancelled: {reason}",
                        previous_status=old_status,
                        new_status='cancelled',
                        metadata={'cancellation_reason': reason}
                    )
                except Exception as transaction_error:
                    logger.error(f"Failed to create transaction record for order {order.order_id}: {str(transaction_error)}")
                    # Continue anyway - the order status is already updated
                    pass

                logger.info(f"Cancelled order {order.order_id}: {reason}")
                return True

        except Exception as e:
            logger.error(f"Failed to cancel order {order.order_id}: {str(e)}")
            import traceback
            logger.error(f"Cancel order traceback: {traceback.format_exc()}")
            return False

    @staticmethod
    def expire_order(order: Order) -> bool:
        """
        Mark order as expired

        Args:
            order: Order instance

        Returns:
            True if expired successfully
        """
        try:
            with transaction.atomic():
                if order.status != 'pending':
                    return False

                # Update order status
                old_status = order.status
                order.status = 'expired'
                order.save(update_fields=['status', 'updated_at'])

                # Create transaction record
                Transaction.create_transaction(
                    order=order,
                    transaction_type='order_expired',
                    description="Order expired due to timeout",
                    previous_status=old_status,
                    new_status='expired'
                )

                logger.info(f"Expired order {order.order_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to expire order {order.order_id}: {str(e)}")
            return False


class PaymentService:
    """
    Service for processing payments
    """

    @staticmethod
    def initiate_payment(
        order: Order,
        success_url: str,
        cancel_url: str,
        provider_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initiate payment for an order

        Args:
            order: Order instance
            success_url: URL to redirect on successful payment
            cancel_url: URL to redirect on cancelled payment
            provider_name: Optional specific provider to use

        Returns:
            Dict containing payment initiation data

        Raises:
            PaymentProcessingError: If payment initiation fails
        """
        try:
            with transaction.atomic():
                # Validate order
                if not order.can_be_paid:
                    raise PaymentProcessingError(f"Order {order.order_id} cannot be paid (status: {order.status})")

                # Get payment provider
                if provider_name:
                    provider = get_payment_provider(provider_name)
                else:
                    provider = get_payment_provider(order.payment_provider)

                # Prepare metadata
                metadata = {
                    'order_id': str(order.order_id),
                    'order_type': order.order_type,
                    'user_id': str(order.user.id),
                    'amount': str(order.amount),
                    'currency': order.currency
                }

                if order.psychologist:
                    metadata['psychologist_id'] = str(order.psychologist.user.id)

                # Create payment intent with provider
                payment_intent_data = provider.create_payment_intent(
                    amount=order.amount,
                    currency=order.currency,
                    metadata=metadata,
                    success_url=success_url,
                    cancel_url=cancel_url,
                    description=order.description
                )

                # Create payment record
                payment = Payment.objects.create(
                    order=order,
                    provider_payment_id=payment_intent_data['payment_intent_id'],
                    provider_payment_intent_id=payment_intent_data.get('payment_intent_id'),
                    payment_method='card',  # Default for now
                    amount=order.amount,
                    currency=order.currency,
                    provider_response=payment_intent_data.get('provider_data', {})
                )

                # Create transaction record
                Transaction.create_transaction(
                    order=order,
                    payment=payment,
                    transaction_type='payment_initiated',
                    description=f"Payment initiated via {provider.provider_name}",
                    amount=order.amount,
                    currency=order.currency,
                    provider_reference=payment_intent_data['payment_intent_id'],
                    provider_response=payment_intent_data.get('provider_data', {}),
                    initiated_by=order.user
                )

                logger.info(f"Initiated payment for order {order.order_id} via {provider.provider_name}")

                return {
                    'order_id': str(order.order_id),
                    'payment_id': str(payment.payment_id),
                    'provider': provider.provider_name,
                    'payment_intent_id': payment_intent_data['payment_intent_id'],
                    'client_secret': payment_intent_data.get('client_secret'),
                    'payment_url': payment_intent_data.get('payment_url'),
                    'expires_at': payment_intent_data.get('expires_at'),
                    'amount': order.amount,
                    'currency': order.currency,
                    'description': order.description
                }

        except PaymentProviderConfigError as e:
            raise PaymentProcessingError(f"Payment provider error: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to initiate payment for order {order.order_id}: {str(e)}")
            raise PaymentProcessingError(f"Failed to initiate payment: {str(e)}")

    @staticmethod
    def confirm_payment(payment: Payment) -> bool:
        """
        Confirm payment with provider and update records

        Args:
            payment: Payment instance

        Returns:
            True if payment confirmed successfully
        """
        try:
            with transaction.atomic():
                # Get provider
                provider = get_payment_provider(payment.order.payment_provider)

                # Confirm payment with provider
                confirmation_data = provider.confirm_payment(payment.provider_payment_id)

                # Update payment record
                old_status = payment.status
                payment.status = confirmation_data['status']
                payment.provider_response = {
                    **payment.provider_response,
                    'confirmation_data': confirmation_data.get('provider_data', {})
                }

                if confirmation_data['status'] == 'succeeded':
                    payment.processed_at = timezone.now()
                    payment.order.mark_as_paid(payment.processed_at)
                elif confirmation_data['status'] == 'failed':
                    payment.mark_as_failed(confirmation_data.get('failure_reason'))

                payment.save(update_fields=['status', 'provider_response', 'processed_at', 'updated_at'])

                # Create transaction record
                Transaction.create_transaction(
                    order=payment.order,
                    payment=payment,
                    transaction_type='payment_succeeded' if confirmation_data['status'] == 'succeeded' else 'payment_failed',
                    description=f"Payment {confirmation_data['status']} via {provider.provider_name}",
                    amount=payment.amount,
                    currency=payment.currency,
                    previous_status=old_status,
                    new_status=payment.status,
                    provider_reference=payment.provider_payment_id,
                    provider_response=confirmation_data.get('provider_data', {})
                )

                # Handle post-payment actions
                if confirmation_data['status'] == 'succeeded':
                    PaymentService._handle_successful_payment(payment)

                logger.info(f"Confirmed payment {payment.payment_id}: {confirmation_data['status']}")
                return confirmation_data['status'] == 'succeeded'

        except Exception as e:
            logger.error(f"Failed to confirm payment {payment.payment_id}: {str(e)}")
            return False

    @staticmethod
    def _handle_successful_payment(payment: Payment):
        """
        Handle post-payment success actions

        Args:
            payment: Successful payment instance
        """
        try:
            order = payment.order

            if order.order_type == 'psychologist_registration':
                # Auto-approve psychologist
                if order.psychologist:
                    order.psychologist.verification_status = 'Approved'
                    order.psychologist.save(update_fields=['verification_status', 'updated_at'])

                    logger.info(f"Auto-approved psychologist {order.psychologist.user.email} after payment")

                    # TODO: Send approval email

            elif order.order_type == 'appointment_booking':
                # Confirm appointment
                # TODO: Update appointment status when appointments app is ready
                pass

        except Exception as e:
            logger.error(f"Error handling successful payment {payment.payment_id}: {str(e)}")

    @staticmethod
    def process_refund(
        payment: Payment,
        amount: Optional[Decimal] = None,
        reason: str = "requested_by_customer"
    ) -> Dict[str, Any]:
        """
        Process refund for a payment

        Args:
            payment: Payment instance
            amount: Refund amount (None for full refund)
            reason: Refund reason

        Returns:
            Dict containing refund data

        Raises:
            RefundError: If refund processing fails
        """
        try:
            with transaction.atomic():
                if not payment.can_be_refunded:
                    raise RefundError(f"Payment {payment.payment_id} cannot be refunded")

                # Get provider
                provider = get_payment_provider(payment.order.payment_provider)

                # Process refund with provider
                refund_data = provider.create_refund(
                    payment_id=payment.provider_payment_id,
                    amount=amount,
                    reason=reason
                )

                # Update payment record
                refund_amount = refund_data['amount']
                payment.add_refund(refund_amount)

                # Update order status if fully refunded
                if payment.status == 'refunded':
                    payment.order.mark_as_refunded()

                # Create transaction record
                Transaction.create_transaction(
                    order=payment.order,
                    payment=payment,
                    transaction_type='refund_succeeded',
                    description=f"Refund processed: {reason}",
                    amount=refund_amount,
                    currency=payment.currency,
                    provider_reference=refund_data['refund_id'],
                    provider_response=refund_data.get('provider_data', {}),
                    metadata={
                        'refund_reason': reason,
                        'refund_type': 'full' if amount is None else 'partial'
                    }
                )

                logger.info(f"Processed refund for payment {payment.payment_id}: {refund_amount} {payment.currency}")

                return {
                    'refund_id': refund_data['refund_id'],
                    'amount': refund_amount,
                    'currency': payment.currency,
                    'status': refund_data['status'],
                    'payment_id': str(payment.payment_id)
                }

        except Exception as e:
            logger.error(f"Failed to process refund for payment {payment.payment_id}: {str(e)}")
            raise RefundError(f"Failed to process refund: {str(e)}")


class WebhookService:
    """
    Service for handling webhook events from payment providers
    """

    @staticmethod
    def process_webhook_event(
        provider_name: str,
        payload: bytes,
        signature: str,
        headers: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """
        Process webhook event from payment provider

        Args:
            provider_name: Payment provider name
            payload: Raw webhook payload
            signature: Webhook signature
            headers: Optional request headers

        Returns:
            Dict containing processing result
        """
        try:
            # Get provider
            provider = get_payment_provider(provider_name)

            # Parse webhook event
            event_data = provider.parse_webhook_event(payload, signature)

            # Create transaction record for webhook
            if event_data.get('payment_intent_id'):
                try:
                    # Try to find the order/payment
                    payment = Payment.objects.filter(
                        provider_payment_id=event_data['payment_intent_id']
                    ).first()

                    if payment:
                        Transaction.create_transaction(
                            order=payment.order,
                            payment=payment,
                            transaction_type='webhook_received',
                            description=f"Webhook received: {event_data['event_type']}",
                            provider_reference=event_data.get('event_id'),
                            provider_response=event_data.get('provider_data', {}),
                            metadata={
                                'webhook_event_type': event_data['event_type'],
                                'webhook_event_id': event_data.get('event_id')
                            }
                        )
                except Exception as e:
                    logger.warning(f"Could not create webhook transaction record: {str(e)}")

            # Process specific event types
            result = WebhookService._process_specific_event(event_data)

            logger.info(f"Processed webhook event: {event_data['event_type']} from {provider_name}")

            return {
                'status': 'success',
                'event_type': event_data['event_type'],
                'event_id': event_data.get('event_id'),
                'processed': True,
                'result': result
            }

        except Exception as e:
            logger.error(f"Failed to process webhook from {provider_name}: {str(e)}")
            return {
                'status': 'error',
                'error': str(e),
                'processed': False
            }

    @staticmethod
    def _process_specific_event(event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process specific webhook event types

        Args:
            event_data: Parsed event data

        Returns:
            Processing result
        """
        event_type = event_data.get('event_type', '')
        result = {'action_taken': 'none'}

        try:
            if 'payment_intent.succeeded' in event_type:
                result = WebhookService._handle_payment_succeeded(event_data)
            elif 'payment_intent.payment_failed' in event_type:
                result = WebhookService._handle_payment_failed(event_data)
            elif 'refund.created' in event_type:
                result = WebhookService._handle_refund_created(event_data)
            # Add more event handlers as needed

        except Exception as e:
            logger.error(f"Error processing webhook event {event_type}: {str(e)}")
            result = {'action_taken': 'error', 'error': str(e)}

        return result

    @staticmethod
    def _handle_payment_succeeded(event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle payment succeeded webhook"""
        payment_intent_id = event_data.get('payment_intent_id')
        if not payment_intent_id:
            return {'action_taken': 'none', 'reason': 'no payment intent ID'}

        try:
            payment = Payment.objects.get(provider_payment_id=payment_intent_id)

            if payment.status != 'succeeded':
                if PaymentService.confirm_payment(payment):
                    return {'action_taken': 'payment_confirmed', 'payment_id': str(payment.payment_id)}

            return {'action_taken': 'already_processed'}

        except Payment.DoesNotExist:
            logger.warning(f"Payment not found for webhook payment_intent_id: {payment_intent_id}")
            return {'action_taken': 'payment_not_found'}

    @staticmethod
    def _handle_payment_failed(event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle payment failed webhook"""
        payment_intent_id = event_data.get('payment_intent_id')
        if not payment_intent_id:
            return {'action_taken': 'none', 'reason': 'no payment intent ID'}

        try:
            payment = Payment.objects.get(provider_payment_id=payment_intent_id)

            if payment.status not in ['failed', 'cancelled']:
                failure_reason = event_data.get('data', {}).get('object', {}).get('last_payment_error', {}).get('message', 'Payment failed')
                payment.mark_as_failed(failure_reason)
                return {'action_taken': 'payment_marked_failed', 'payment_id': str(payment.payment_id)}

            return {'action_taken': 'already_processed'}

        except Payment.DoesNotExist:
            logger.warning(f"Payment not found for webhook payment_intent_id: {payment_intent_id}")
            return {'action_taken': 'payment_not_found'}

    @staticmethod
    def _handle_refund_created(event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle refund created webhook"""
        # Implementation depends on specific refund handling needs
        return {'action_taken': 'refund_logged'}