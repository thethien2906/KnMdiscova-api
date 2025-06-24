# carts/models.py
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

from users.models import User
from children.models import Child
from psychologists.models import Psychologist


class Cart(models.Model):
    """
    Shopping cart for users to store booking items before checkout
    """

    # Primary key
    cart_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique identifier for the cart")
    )

    # User relationship
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='cart',
        help_text=_("User who owns this cart")
    )

    # Timestamps
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('updated at'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Cart')
        verbose_name_plural = _('Carts')
        db_table = 'carts'
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['created_at']),
            models.Index(fields=['updated_at']),
        ]

    def __str__(self):
        return f"Cart for {self.user.email}"

    @property
    def total_items(self):
        """Get total number of items in cart"""
        return self.items.count()

    @property
    def total_amount(self):
        """Calculate total amount of all items in cart"""
        return sum(item.total_price for item in self.items.all())

    @property
    def is_empty(self):
        """Check if cart is empty"""
        return self.total_items == 0

    def clear(self):
        """Remove all items from cart"""
        self.items.all().delete()
        self.save(update_fields=['updated_at'])


class CartItem(models.Model):
    """
    Individual booking item in the cart
    """

    # Session Type Choices (matching Appointment model)
    SESSION_TYPE_CHOICES = [
        ('OnlineMeeting', _('Online Session - 1 hour')),
        ('InitialConsultation', _('Initial Consultation - 2 hours (In-Person)')),
    ]

    # Primary key
    item_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique identifier for the cart item")
    )

    # Cart relationship
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items',
        help_text=_("Cart this item belongs to")
    )

    # Booking details
    child = models.ForeignKey(
        Child,
        on_delete=models.CASCADE,
        related_name='cart_items',
        help_text=_("Child this booking is for")
    )

    psychologist = models.ForeignKey(
        Psychologist,
        on_delete=models.CASCADE,
        related_name='cart_items',
        help_text=_("Psychologist for the booking")
    )

    session_type = models.CharField(
        _('session type'),
        max_length=20,
        choices=SESSION_TYPE_CHOICES,
        help_text=_("Type of session: online or in-person consultation")
    )

    start_slot_id = models.IntegerField(
        _('start slot ID'),
        help_text=_("ID of the first slot to book (for consecutive booking)")
    )

    # Session details
    scheduled_start_time = models.DateTimeField(
        _('scheduled start time'),
        help_text=_("When the session is scheduled to start")
    )

    scheduled_end_time = models.DateTimeField(
        _('scheduled end time'),
        help_text=_("When the session is scheduled to end")
    )

    # Pricing
    price = models.DecimalField(
        _('price'),
        max_digits=10,
        decimal_places=2,
        help_text=_("Price for this booking")
    )

    currency = models.CharField(
        _('currency'),
        max_length=3,
        default='USD',
        help_text=_("Currency code")
    )

    # Notes
    parent_notes = models.TextField(
        _('parent notes'),
        blank=True,
        help_text=_("Notes from parent about the booking")
    )

    # Metadata
    metadata = models.JSONField(
        _('metadata'),
        default=dict,
        blank=True,
        help_text=_("Additional booking metadata")
    )

    # Timestamps
    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('updated at'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Cart Item')
        verbose_name_plural = _('Cart Items')
        db_table = 'cart_items'
        indexes = [
            models.Index(fields=['cart']),
            models.Index(fields=['child']),
            models.Index(fields=['psychologist']),
            models.Index(fields=['session_type']),
            models.Index(fields=['scheduled_start_time']),
            models.Index(fields=['start_slot_id']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            # Ensure one booking per child per psychologist per time slot
            models.UniqueConstraint(
                fields=['cart', 'child', 'psychologist', 'start_slot_id'],
                name='unique_cart_booking_per_child_psychologist_slot'
            ),
        ]

    def __str__(self):
        return f"Cart Item: {self.child.display_name} - {self.psychologist.display_name} ({self.session_type})"

    def clean(self):
        """Model validation"""
        errors = {}

        # Validate child belongs to cart owner
        if self.cart and self.child:
            try:
                if hasattr(self.cart.user, 'parent_profile'):
                    if self.child.parent != self.cart.user.parent_profile:
                        errors['child'] = _("Child must belong to the cart owner")
            except:
                pass

        # Validate psychologist offers the service
        if self.psychologist and self.session_type:
            if self.session_type == 'OnlineMeeting' and not self.psychologist.offers_online_sessions:
                errors['session_type'] = _("Psychologist does not offer online sessions")

            if self.session_type == 'InitialConsultation' and not self.psychologist.offers_initial_consultation:
                errors['session_type'] = _("Psychologist does not offer initial consultations")

        # Validate scheduling times
        if self.scheduled_start_time and self.scheduled_end_time:
            if self.scheduled_start_time >= self.scheduled_end_time:
                errors['scheduled_end_time'] = _("End time must be after start time")

            # Validate appointment is in the future
            if self.scheduled_start_time <= timezone.now():
                errors['scheduled_start_time'] = _("Appointment must be in the future")

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def total_price(self):
        """Get total price for this item"""
        return self.price

    @property
    def duration_hours(self):
        """Get duration in hours"""
        if self.session_type == 'OnlineMeeting':
            return 1
        elif self.session_type == 'InitialConsultation':
            return 2
        return 0

    @property
    def is_past_due(self):
        """Check if the scheduled time has passed"""
        return self.scheduled_start_time <= timezone.now()

    def get_slot_ids_needed(self):
        """Get list of slot IDs needed for this booking"""
        if self.session_type == 'OnlineMeeting':
            return [self.start_slot_id]
        else:  # InitialConsultation needs 2 consecutive slots
            return [self.start_slot_id, self.start_slot_id + 1]  # Simplified assumption