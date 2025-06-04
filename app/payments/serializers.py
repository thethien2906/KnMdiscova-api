# payments/serializers.py
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
from typing import Dict, Any

from .models import Order, Payment, Transaction
from .services import PricingService, OrderService, PaymentService
from users.serializers import UserSerializer
from psychologists.serializers import PsychologistSummarySerializer


class OrderSerializer(serializers.ModelSerializer):
    """
    Serializer for Order model
    """
    user = UserSerializer(read_only=True)
    psychologist = PsychologistSummarySerializer(read_only=True)

    # Computed fields
    can_be_paid = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_pending = serializers.BooleanField(read_only=True)
    display_description = serializers.CharField(source='get_display_description', read_only=True)

    class Meta:
        model = Order
        fields = [
            'order_id',
            'order_type',
            'user',
            'psychologist',
            'amount',
            'currency',
            'status',
            'payment_provider',
            'description',
            'display_description',
            'metadata',
            'expires_at',
            'paid_at',
            'can_be_paid',
            'is_expired',
            'is_pending',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'order_id',
            'user',
            'psychologist',
            'amount',
            'currency',
            'status',
            'payment_provider',
            'description',
            'display_description',
            'metadata',
            'expires_at',
            'paid_at',
            'can_be_paid',
            'is_expired',
            'is_pending',
            'created_at',
            'updated_at',
        ]


class PaymentSerializer(serializers.ModelSerializer):
    """
    Serializer for Payment model
    """
    order = OrderSerializer(read_only=True)

    # Computed fields
    is_successful = serializers.BooleanField(read_only=True)
    can_be_refunded = serializers.BooleanField(read_only=True)
    remaining_refundable_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = Payment
        fields = [
            'payment_id',
            'order',
            'provider_payment_id',
            'provider_payment_intent_id',
            'payment_method',
            'status',
            'amount',
            'currency',
            'refunded_amount',
            'failure_reason',
            'processed_at',
            'is_successful',
            'can_be_refunded',
            'remaining_refundable_amount',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'payment_id',
            'order',
            'provider_payment_id',
            'provider_payment_intent_id',
            'payment_method',
            'status',
            'amount',
            'currency',
            'refunded_amount',
            'failure_reason',
            'processed_at',
            'is_successful',
            'can_be_refunded',
            'remaining_refundable_amount',
            'created_at',
            'updated_at',
        ]


class TransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for Transaction model
    """
    order = OrderSerializer(read_only=True)
    payment = PaymentSerializer(read_only=True)
    initiated_by = UserSerializer(read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'transaction_id',
            'order',
            'payment',
            'transaction_type',
            'amount',
            'currency',
            'previous_status',
            'new_status',
            'description',
            'metadata',
            'provider_reference',
            'initiated_by',
            'ip_address',
            'created_at',
        ]
        read_only_fields = [
            'transaction_id',
            'order',
            'payment',
            'transaction_type',
            'amount',
            'currency',
            'previous_status',
            'new_status',
            'description',
            'metadata',
            'provider_reference',
            'initiated_by',
            'ip_address',
            'created_at',
        ]


class CreateRegistrationOrderSerializer(serializers.Serializer):
    """
    Serializer for creating psychologist registration orders
    """
    currency = serializers.ChoiceField(
        choices=['USD'],  # Can be expanded later
        default='USD',
        help_text=_("Currency for the payment")
    )
    provider = serializers.ChoiceField(
        choices=['stripe'],  # Can be expanded later
        default='stripe',
        help_text=_("Payment provider to use")
    )

    def validate(self, attrs):
        """Validate registration order creation"""
        # Check if user is a psychologist
        user = self.context['request'].user
        if not user.is_psychologist:
            raise serializers.ValidationError(_("Only psychologists can create registration orders"))

        # Check if psychologist profile exists
        try:
            from psychologists.models import Psychologist
            psychologist = Psychologist.objects.get(user=user)
        except Psychologist.DoesNotExist:
            raise serializers.ValidationError(_("Psychologist profile not found"))

        # Check if psychologist already has a pending or paid registration order
        existing_order = Order.objects.filter(
            order_type='psychologist_registration',
            psychologist=psychologist,
            status__in=['pending', 'paid']
        ).first()

        if existing_order:
            raise serializers.ValidationError(
                _("You already have an active registration order")
            )

        attrs['psychologist'] = psychologist
        return attrs

    def create(self, validated_data):
        """Create registration order"""
        psychologist = validated_data['psychologist']
        currency = validated_data['currency']
        provider = validated_data['provider']

        return OrderService.create_psychologist_registration_order(
            psychologist=psychologist,
            currency=currency,
            provider_name=provider
        )


class CreateAppointmentOrderSerializer(serializers.Serializer):
    """
    Serializer for creating appointment booking orders
    """
    psychologist_id = serializers.UUIDField(
        help_text=_("ID of the psychologist for the appointment")
    )
    session_type = serializers.ChoiceField(
        choices=['online_session', 'initial_consultation'],
        help_text=_("Type of session to book")
    )
    # appointment_date = serializers.DateTimeField(
    #     help_text=_("Preferred appointment date and time")
    # )  # Will be uncommented when appointments app is ready
    currency = serializers.ChoiceField(
        choices=['USD'],
        default='USD',
        help_text=_("Currency for the payment")
    )
    provider = serializers.ChoiceField(
        choices=['stripe'],
        default='stripe',
        help_text=_("Payment provider to use")
    )

    def validate_psychologist_id(self, value):
        """Validate psychologist ID"""
        try:
            from psychologists.models import Psychologist
            psychologist = Psychologist.objects.get(user__id=value)

            if not psychologist.is_marketplace_visible:
                raise serializers.ValidationError(_("Psychologist is not available for bookings"))

            return psychologist
        except Psychologist.DoesNotExist:
            raise serializers.ValidationError(_("Psychologist not found"))

    def validate(self, attrs):
        """Validate appointment order creation"""
        user = self.context['request'].user
        psychologist = attrs['psychologist_id']  # This is now a Psychologist instance
        session_type = attrs['session_type']

        # Check if user is a parent
        if not user.is_parent:
            raise serializers.ValidationError(_("Only parents can book appointments"))

        # Validate psychologist offers this session type
        if session_type == 'online_session' and not psychologist.offers_online_sessions:
            raise serializers.ValidationError(_("Psychologist does not offer online sessions"))

        if session_type == 'initial_consultation' and not psychologist.offers_initial_consultation:
            raise serializers.ValidationError(_("Psychologist does not offer initial consultations"))

        attrs['psychologist'] = psychologist
        return attrs

    def create(self, validated_data):
        """Create appointment order"""
        user = self.context['request'].user
        psychologist = validated_data['psychologist']
        session_type = validated_data['session_type']
        currency = validated_data['currency']
        provider = validated_data['provider']

        return OrderService.create_appointment_booking_order(
            user=user,
            psychologist=psychologist,
            session_type=session_type,
            currency=currency,
            provider_name=provider
        )


class InitiatePaymentSerializer(serializers.Serializer):
    """
    Serializer for initiating payment for an order
    """
    success_url = serializers.URLField(
        help_text=_("URL to redirect to after successful payment")
    )
    cancel_url = serializers.URLField(
        help_text=_("URL to redirect to after cancelled payment")
    )
    provider = serializers.ChoiceField(
        choices=['stripe'],
        required=False,
        help_text=_("Payment provider to use (optional, defaults to order's provider)")
    )

    def validate(self, attrs):
        """Validate payment initiation"""
        order = self.context['order']

        if not order.can_be_paid:
            raise serializers.ValidationError(
                _("Order cannot be paid (status: {})").format(order.status)
            )

        return attrs

    def save(self):
        """Initiate payment"""
        order = self.context['order']
        success_url = self.validated_data['success_url']
        cancel_url = self.validated_data['cancel_url']
        provider = self.validated_data.get('provider')

        return PaymentService.initiate_payment(
            order=order,
            success_url=success_url,
            cancel_url=cancel_url,
            provider_name=provider
        )


class RefundPaymentSerializer(serializers.Serializer):
    """
    Serializer for processing payment refunds
    """
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        help_text=_("Refund amount (leave empty for full refund)")
    )
    reason = serializers.ChoiceField(
        choices=[
            ('requested_by_customer', _('Requested by customer')),
            ('duplicate', _('Duplicate payment')),
            ('fraudulent', _('Fraudulent payment')),
            ('subscription_canceled', _('Subscription canceled')),
            ('product_unsatisfactory', _('Product unsatisfactory')),
            ('other', _('Other')),
        ],
        default='requested_by_customer',
        help_text=_("Reason for the refund")
    )

    def validate_amount(self, value):
        """Validate refund amount"""
        if value is not None:
            payment = self.context['payment']

            if value <= 0:
                raise serializers.ValidationError(_("Refund amount must be positive"))

            if value > payment.remaining_refundable_amount:
                raise serializers.ValidationError(
                    _("Refund amount cannot exceed remaining refundable amount: {}").format(
                        payment.remaining_refundable_amount
                    )
                )

        return value

    def validate(self, attrs):
        """Validate refund request"""
        payment = self.context['payment']

        if not payment.can_be_refunded:
            raise serializers.ValidationError(_("Payment cannot be refunded"))

        return attrs

    def save(self):
        """Process refund"""
        payment = self.context['payment']
        amount = self.validated_data.get('amount')
        reason = self.validated_data['reason']

        return PaymentService.process_refund(
            payment=payment,
            amount=amount,
            reason=reason
        )


class PricingSerializer(serializers.Serializer):
    """
    Serializer for pricing information
    """
    currency = serializers.ChoiceField(
        choices=['USD'],
        default='USD',
        help_text=_("Currency to get prices for")
    )

    def to_representation(self, instance):
        """Return pricing information"""
        currency = self.validated_data.get('currency', 'USD')

        return {
            'currency': currency,
            'services': PricingService.get_all_service_prices(currency),
            'fees_example': PricingService.calculate_total_with_fees(
                Decimal('100.00'), currency, 'stripe'
            )
        }


class PaymentStatusSerializer(serializers.Serializer):
    """
    Serializer for payment status updates
    """
    payment_intent_id = serializers.CharField(
        help_text=_("Payment intent ID from provider")
    )

    def save(self):
        """Check and update payment status"""
        payment_intent_id = self.validated_data['payment_intent_id']

        try:
            payment = Payment.objects.get(provider_payment_id=payment_intent_id)
            PaymentService.confirm_payment(payment)
            return payment
        except Payment.DoesNotExist:
            raise serializers.ValidationError(_("Payment not found"))


class WebhookEventSerializer(serializers.Serializer):
    """
    Serializer for webhook event processing
    """
    event_type = serializers.CharField(read_only=True)
    event_id = serializers.CharField(read_only=True)
    processed = serializers.BooleanField(read_only=True)
    result = serializers.DictField(read_only=True)


# Summary serializers for listings

class OrderSummarySerializer(serializers.ModelSerializer):
    """
    Summary serializer for orders (for listings)
    """
    psychologist_name = serializers.CharField(source='psychologist.full_name', read_only=True)
    can_be_paid = serializers.BooleanField(read_only=True)
    display_description = serializers.CharField(source='get_display_description', read_only=True)

    class Meta:
        model = Order
        fields = [
            'order_id',
            'order_type',
            'psychologist_name',
            'amount',
            'currency',
            'status',
            'display_description',
            'can_be_paid',
            'expires_at',
            'created_at',
        ]


class PaymentSummarySerializer(serializers.ModelSerializer):
    """
    Summary serializer for payments (for listings)
    """
    order_type = serializers.CharField(source='order.order_type', read_only=True)
    psychologist_name = serializers.CharField(source='order.psychologist.full_name', read_only=True)

    class Meta:
        model = Payment
        fields = [
            'payment_id',
            'order_type',
            'psychologist_name',
            'payment_method',
            'status',
            'amount',
            'currency',
            'processed_at',
            'created_at',
        ]