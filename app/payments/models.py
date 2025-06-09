# payments/models.py
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

from users.models import User
from psychologists.models import Psychologist
from appointments.models import Appointment


class Order(models.Model):
    """
    Order model for tracking payment orders in the system
    Supports both psychologist registration and appointment booking payments
    """

    # Order Type Choices
    ORDER_TYPE_CHOICES = [
        ('psychologist_registration', _('Psychologist Registration')),
        ('appointment_booking', _('Appointment Booking')),
    ]

    # Order Status Choices
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('paid', _('Paid')),
        ('failed', _('Failed')),
        ('refunded', _('Refunded')),
        ('cancelled', _('Cancelled')),
        ('expired', _('Expired')),
    ]

    # Payment Provider Choices
    PROVIDER_CHOICES = [
        ('stripe', _('Stripe')),
        ('paypal', _('PayPal')),
    ]

    # Currency Choices (expandable)
    CURRENCY_CHOICES = [
        ('USD', _('US Dollar')),
        ('EUR', _('Euro')),
        ('GBP', _('British Pound')),
    ]

    # Primary fields
    face = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique identifier for the order")
    )

    order_type = models.CharField(
        _('order type'),
        max_length=30,
        choices=ORDER_TYPE_CHOICES,
        help_text=_("Type of order: registration or appointment booking")
    )

    # User relationships
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='orders',
        help_text=_("User who placed the order")
    )

    psychologist = models.ForeignKey(
        Psychologist,
        on_delete=models.CASCADE,
        related_name='orders',
        null=True,
        blank=True,
        help_text=_("Psychologist associated with the order (for registration or booking)")
    )

    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name='orders',
        null=True,
        blank=True,
        help_text=_("Appointment associated with the order (for booking only)")
    )

    # Financial fields
    amount = models.DecimalField(
        _('amount'),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_("Order amount")
    )

    currency = models.CharField(
        _('currency'),
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='USD',
        help_text=_("Currency code")
    )

    # Payment processing fields
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text=_("Current order status")
    )

    payment_provider = models.CharField(
        _('payment provider'),
        max_length=20,
        choices=PROVIDER_CHOICES,
        help_text=_("Payment provider used for this order")
    )

    # Provider-specific fields
    provider_order_id = models.CharField(
        _('provider order ID'),
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Order ID from payment provider")
    )

    # Metadata
    description = models.TextField(
        _('description'),
        blank=True,
        help_text=_("Order description")
    )

    metadata = models.JSONField(
        _('metadata'),
        default=dict,
        blank=True,
        help_text=_("Additional order metadata")
    )

    # Timing fields
    expires_at = models.DateTimeField(
        _('expires at'),
        null=True,
        blank=True,
        help_text=_("When the order expires if not paid")
    )

    paid_at = models.DateTimeField(
        _('paid at'),
        null=True,
        blank=True,
        help_text=_("When the order was paid")
    )

    # Audit fields
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        _('updated at'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Order')
        verbose_name_plural = _('Orders')
        db_table = 'orders'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['order_type', 'status']),
            models.Index(fields=['payment_provider', 'status']),
            models.Index(fields=['psychologist', 'order_type']),
            models.Index(fields=['appointment']),
            models.Index(fields=['provider_order_id']),
            models.Index(fields=['created_at']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['status', 'created_at']),
        ]
        constraints = [
            # For registration orders, psychologist must be provided
            models.CheckConstraint(
                check=models.Q(order_type='appointment_booking') | models.Q(psychologist__isnull=False),
                name='registration_order_has_psychologist'
            ),
            # For appointment orders, both psychologist and appointment must be provided
            models.CheckConstraint(
                check=models.Q(order_type='psychologist_registration') |
                      (models.Q(psychologist__isnull=False)),
                name='appointment_order_has_psychologist'
            ),
            # Amount must be positive
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name='positive_amount'
            ),
        ]

    def __str__(self):
        return f"Order {self.order_id} - {self.get_order_type_display()} - {self.amount} {self.currency}"

    def clean(self):
        """Model validation"""
        errors = {}

        # Business rule validation based on order type
        if self.order_type == 'psychologist_registration':
            if not self.psychologist:
                errors['psychologist'] = _("Psychologist is required for registration orders")

            if self.appointment:
                errors['appointment'] = _("Appointment should not be set for registration orders")

            # Validate that user is the psychologist
            if self.psychologist and self.user != self.psychologist.user:
                errors['user'] = _("User must be the psychologist for registration orders")

        elif self.order_type == 'appointment_booking':
            if not self.psychologist:
                errors['psychologist'] = _("Psychologist is required for appointment booking orders")

            # if not self.appointment:
            #     errors['appointment'] = _("Appointment is required for appointment booking orders")

            # # Validate appointment-psychologist relationship
            # if self.appointment and self.psychologist:
            #     if self.appointment.psychologist != self.psychologist:
            #         errors['appointment'] = _("Appointment must belong to the specified psychologist")

        # Validate expiry date
        # if self.expires_at and self.expires_at <= timezone.now():
        #     errors['expires_at'] = _("Expiry date must be in the future")

        # Validate paid_at timestamp
        if self.paid_at and self.status != 'paid':
            errors['paid_at'] = _("Paid timestamp can only be set when status is 'paid'")

        if self.status == 'paid' and not self.paid_at:
            errors['status'] = _("Paid timestamp is required when status is 'paid'")

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        """Check if order has expired"""
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at

    @property
    def is_pending(self):
        """Check if order is pending payment"""
        return self.status == 'pending' and not self.is_expired

    @property
    def can_be_paid(self):
        """Check if order can be paid"""
        return self.status == 'pending' and not self.is_expired

    def mark_as_paid(self, paid_at=None):
        """Mark order as paid"""
        self.status = 'paid'
        self.paid_at = paid_at or timezone.now()
        self.save(update_fields=['status', 'paid_at', 'updated_at'])

    def mark_as_failed(self):
        """Mark order as failed"""
        self.status = 'failed'
        self.save(update_fields=['status', 'updated_at'])

    def mark_as_refunded(self):
        """Mark order as refunded"""
        self.status = 'refunded'
        self.save(update_fields=['status', 'updated_at'])

    def mark_as_expired(self):
        """Mark order as expired"""
        self.status = 'expired'
        self.save(update_fields=['status', 'updated_at'])

    def get_display_description(self):
        """Get human-readable order description"""
        if self.order_type == 'psychologist_registration':
            return f"Registration fee for {self.psychologist.full_name if self.psychologist else 'psychologist'}"
        elif self.order_type == 'appointment_booking':
            if self.appointment:
                return f"Appointment with {self.psychologist.full_name} on {self.appointment.appointment_date}"
            return f"Appointment booking with {self.psychologist.full_name if self.psychologist else 'psychologist'}"
        return "Unknown order type"

class Payment(models.Model):
    """
    Payment model for tracking individual payment attempts
    Links to payment provider responses and transaction details
    """

    # Payment Status Choices
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('processing', _('Processing')),
        ('succeeded', _('Succeeded')),
        ('failed', _('Failed')),
        ('cancelled', _('Cancelled')),
        ('refunded', _('Refunded')),
        ('partially_refunded', _('Partially Refunded')),
    ]

    # Payment Method Choices
    PAYMENT_METHOD_CHOICES = [
        ('card', _('Credit/Debit Card')),
        ('paypal', _('PayPal')),
        ('bank_transfer', _('Bank Transfer')),
        ('digital_wallet', _('Digital Wallet')),
    ]

    # Primary fields
    payment_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique identifier for the payment")
    )

    # Order relationship
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='payments',
        help_text=_("Order this payment belongs to")
    )

    # Provider integration fields
    provider_payment_id = models.CharField(
        _('provider payment ID'),
        max_length=255,
        help_text=_("Payment ID from payment provider (Stripe, PayPal, etc.)")
    )

    provider_payment_intent_id = models.CharField(
        _('provider payment intent ID'),
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Payment intent ID from provider (for Stripe)")
    )

    # Payment details
    payment_method = models.CharField(
        _('payment method'),
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        help_text=_("Method used for payment")
    )

    status = models.CharField(
        _('status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text=_("Current payment status")
    )

    amount = models.DecimalField(
        _('amount'),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_("Payment amount")
    )

    currency = models.CharField(
        _('currency'),
        max_length=3,
        help_text=_("Currency code")
    )

    # Provider response and metadata
    provider_response = models.JSONField(
        _('provider response'),
        default=dict,
        blank=True,
        help_text=_("Raw response data from payment provider")
    )

    failure_reason = models.TextField(
        _('failure reason'),
        blank=True,
        null=True,
        help_text=_("Reason for payment failure")
    )

    # Refund tracking
    refunded_amount = models.DecimalField(
        _('refunded amount'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_("Amount that has been refunded")
    )

    # Timing fields
    processed_at = models.DateTimeField(
        _('processed at'),
        null=True,
        blank=True,
        help_text=_("When the payment was processed by provider")
    )

    # Audit fields
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        _('updated at'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Payment')
        verbose_name_plural = _('Payments')
        db_table = 'payments'
        indexes = [
            models.Index(fields=['order', 'status']),
            models.Index(fields=['provider_payment_id']),
            models.Index(fields=['provider_payment_intent_id']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['order', 'created_at']),
            models.Index(fields=['amount', 'currency']),
        ]
        constraints = [
            # Refunded amount cannot exceed payment amount
            models.CheckConstraint(
                check=models.Q(refunded_amount__lte=models.F('amount')),
                name='refunded_amount_not_exceed_payment'
            ),
        ]

    def __str__(self):
        return f"Payment {self.payment_id} - {self.amount} {self.currency} - {self.status}"

    def clean(self):
        """Model validation"""
        errors = {}

        # Validate currency matches order currency
        if self.order and self.currency != self.order.currency:
            errors['currency'] = _("Payment currency must match order currency")

        # Validate amount matches order amount for new payments
        if self.order and self.amount != self.order.amount:
            errors['amount'] = _("Payment amount must match order amount")

        # Validate refunded amount
        if self.refunded_amount > self.amount:
            errors['refunded_amount'] = _("Refunded amount cannot exceed payment amount")

        # Validate processed timestamp
        if self.processed_at and self.status not in ['succeeded', 'failed', 'refunded', 'partially_refunded']:
            errors['processed_at'] = _("Processed timestamp can only be set for finalized payments")

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_successful(self):
        """Check if payment was successful"""
        return self.status == 'succeeded'

    @property
    def can_be_refunded(self):
        """Check if payment can be refunded"""
        return (
            self.status in ['succeeded', 'partially_refunded'] and
            self.refunded_amount < self.amount
        )

    @property
    def remaining_refundable_amount(self):
        """Get remaining amount that can be refunded"""
        return self.amount - self.refunded_amount

    def mark_as_succeeded(self, processed_at=None):
        """Mark payment as succeeded"""
        self.status = 'succeeded'
        self.processed_at = processed_at or timezone.now()
        self.save(update_fields=['status', 'processed_at', 'updated_at'])

    def mark_as_failed(self, failure_reason=None, processed_at=None):
        """Mark payment as failed"""
        self.status = 'failed'
        if failure_reason:
            self.failure_reason = failure_reason
        self.processed_at = processed_at or timezone.now()
        update_fields = ['status', 'processed_at', 'updated_at']
        if failure_reason:
            update_fields.append('failure_reason')
        self.save(update_fields=update_fields)

    def add_refund(self, refund_amount):
        """Add refund amount and update status"""
        self.refunded_amount += Decimal(str(refund_amount))

        if self.refunded_amount >= self.amount:
            self.status = 'refunded'
        else:
            self.status = 'partially_refunded'

        self.save(update_fields=['refunded_amount', 'status', 'updated_at'])


class Transaction(models.Model):
    """
    Transaction model for comprehensive audit trail
    Records all payment-related events and state changes
    """

    # Transaction Type Choices
    TRANSACTION_TYPE_CHOICES = [
        ('order_created', _('Order Created')),
        ('payment_initiated', _('Payment Initiated')),
        ('payment_processing', _('Payment Processing')),
        ('payment_succeeded', _('Payment Succeeded')),
        ('payment_failed', _('Payment Failed')),
        ('payment_cancelled', _('Payment Cancelled')),
        ('refund_initiated', _('Refund Initiated')),
        ('refund_succeeded', _('Refund Succeeded')),
        ('refund_failed', _('Refund Failed')),
        ('order_expired', _('Order Expired')),
        ('webhook_received', _('Webhook Received')),
        ('webhook_processed', _('Webhook Processed')),
        ('status_change', _('Status Change')),
    ]

    # Primary fields
    transaction_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique identifier for the transaction")
    )

    # Related objects
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='transactions',
        help_text=_("Order this transaction relates to")
    )

    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name='transactions',
        null=True,
        blank=True,
        help_text=_("Payment this transaction relates to")
    )

    # Transaction details
    transaction_type = models.CharField(
        _('transaction type'),
        max_length=30,
        choices=TRANSACTION_TYPE_CHOICES,
        help_text=_("Type of transaction")
    )

    amount = models.DecimalField(
        _('amount'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Transaction amount (if applicable)")
    )

    currency = models.CharField(
        _('currency'),
        max_length=3,
        null=True,
        blank=True,
        help_text=_("Currency code (if applicable)")
    )

    # Status tracking
    previous_status = models.CharField(
        _('previous status'),
        max_length=20,
        blank=True,
        null=True,
        help_text=_("Previous status before change")
    )

    new_status = models.CharField(
        _('new status'),
        max_length=20,
        blank=True,
        null=True,
        help_text=_("New status after change")
    )

    # Details and metadata
    description = models.TextField(
        _('description'),
        help_text=_("Human-readable description of the transaction")
    )

    metadata = models.JSONField(
        _('metadata'),
        default=dict,
        blank=True,
        help_text=_("Additional transaction metadata")
    )

    # Provider information
    provider_reference = models.CharField(
        _('provider reference'),
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Reference ID from payment provider")
    )

    provider_response = models.JSONField(
        _('provider response'),
        default=dict,
        blank=True,
        help_text=_("Response data from payment provider")
    )

    # User context
    initiated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='initiated_transactions',
        null=True,
        blank=True,
        help_text=_("User who initiated the transaction")
    )

    # IP and context tracking
    ip_address = models.GenericIPAddressField(
        _('IP address'),
        null=True,
        blank=True,
        help_text=_("IP address where transaction was initiated")
    )

    user_agent = models.TextField(
        _('user agent'),
        blank=True,
        null=True,
        help_text=_("User agent string")
    )

    # Audit fields
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True
    )

    class Meta:
        verbose_name = _('Transaction')
        verbose_name_plural = _('Transactions')
        db_table = 'transactions'
        indexes = [
            models.Index(fields=['order', 'created_at']),
            models.Index(fields=['payment', 'created_at']),
            models.Index(fields=['transaction_type', 'created_at']),
            models.Index(fields=['provider_reference']),
            models.Index(fields=['initiated_by', 'created_at']),
            models.Index(fields=['order', 'transaction_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Transaction {self.transaction_id} - {self.get_transaction_type_display()}"

    def clean(self):
        """Model validation"""
        errors = {}

        # Validate that payment belongs to the same order
        if self.payment and self.payment.order != self.order:
            errors['payment'] = _("Payment must belong to the same order")

        # Validate amount and currency for transaction types that require them
        amount_required_types = [
            'payment_succeeded', 'payment_failed', 'refund_initiated',
            'refund_succeeded', 'refund_failed'
        ]

        if self.transaction_type in amount_required_types:
            if not self.amount:
                errors['amount'] = _("Amount is required for this transaction type")
            if not self.currency:
                errors['currency'] = _("Currency is required for this transaction type")

        # Validate status change transactions
        if self.transaction_type == 'status_change':
            if not self.previous_status or not self.new_status:
                errors['new_status'] = _("Both previous and new status are required for status change transactions")

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def create_transaction(cls, order, transaction_type, description, **kwargs):
        """
        Helper method to create transaction records
        """
        transaction_data = {
            'order': order,
            'transaction_type': transaction_type,
            'description': description,
        }

        # Add optional fields if provided
        optional_fields = [
            'payment', 'amount', 'currency', 'previous_status', 'new_status',
            'metadata', 'provider_reference', 'provider_response', 'initiated_by',
            'ip_address', 'user_agent'
        ]

        for field in optional_fields:
            if field in kwargs:
                transaction_data[field] = kwargs[field]

        return cls.objects.create(**transaction_data)