# carts/serializers.py
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from .models import Cart, CartItem
from .services import CartService, CartItemCreationError, CheckoutError, SlotUnavailableError
from children.serializers import ChildSummarySerializer
from psychologists.serializers import PsychologistSummarySerializer
from children.models import Child
from psychologists.models import Psychologist


class CartItemSerializer(serializers.ModelSerializer):
    """
    Serializer for CartItem model
    """
    # Related object summaries
    child = ChildSummarySerializer(read_only=True)
    psychologist = PsychologistSummarySerializer(read_only=True)

    # Computed fields
    duration_hours = serializers.IntegerField(read_only=True)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    is_past_due = serializers.BooleanField(read_only=True)

    # Additional display fields
    psychologist_name = serializers.CharField(source='psychologist.display_name', read_only=True)
    child_name = serializers.CharField(source='child.display_name', read_only=True)
    session_type_display = serializers.CharField(source='get_session_type_display', read_only=True)

    class Meta:
        model = CartItem
        fields = [
            'item_id',
            'child',
            'child_name',
            'psychologist',
            'psychologist_name',
            'session_type',
            'session_type_display',
            'start_slot_id',
            'scheduled_start_time',
            'scheduled_end_time',
            'price',
            'currency',
            'parent_notes',
            'duration_hours',
            'total_price',
            'is_past_due',
            'metadata',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'item_id',
            'child',
            'child_name',
            'psychologist',
            'psychologist_name',
            'session_type_display',
            'scheduled_start_time',
            'scheduled_end_time',
            'price',
            'currency',
            'duration_hours',
            'total_price',
            'is_past_due',
            'metadata',
            'created_at',
            'updated_at',
        ]


class CartSerializer(serializers.ModelSerializer):
    """
    Serializer for Cart model with items
    """
    items = CartItemSerializer(many=True, read_only=True)

    # Computed fields
    total_items = serializers.IntegerField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    is_empty = serializers.BooleanField(read_only=True)

    class Meta:
        model = Cart
        fields = [
            'cart_id',
            'user',
            'items',
            'total_items',
            'total_amount',
            'is_empty',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'cart_id',
            'user',
            'items',
            'total_items',
            'total_amount',
            'is_empty',
            'created_at',
            'updated_at',
        ]


class AddToCartSerializer(serializers.Serializer):
    """
    Serializer for adding items to cart
    """
    child_id = serializers.UUIDField(
        help_text=_("ID of the child for the booking")
    )
    psychologist_id = serializers.UUIDField(
        help_text=_("ID of the psychologist for the booking")
    )
    session_type = serializers.ChoiceField(
        choices=CartItem.SESSION_TYPE_CHOICES,
        help_text=_("Type of session to book")
    )
    start_slot_id = serializers.IntegerField(
        help_text=_("ID of the starting appointment slot")
    )
    parent_notes = serializers.CharField(
        max_length=1000,
        required=False,
        allow_blank=True,
        help_text=_("Optional notes from parent")
    )
    currency = serializers.ChoiceField(
        choices=['USD'],
        default='USD',
        help_text=_("Currency for pricing")
    )

    def validate_child_id(self, value):
        """Validate child ID and ownership"""
        try:
            child = Child.objects.get(id=value)

            # Check if child belongs to requesting parent
            user = self.context['request'].user
            if hasattr(user, 'parent_profile') and child.parent != user.parent_profile:
                raise serializers.ValidationError(_("You can only add bookings for your own children"))

            return child
        except Child.DoesNotExist:
            raise serializers.ValidationError(_("Child not found"))

    def validate_psychologist_id(self, value):
        """Validate psychologist ID"""
        try:
            psychologist = Psychologist.objects.get(user__id=value)

            if not psychologist.is_marketplace_visible:
                raise serializers.ValidationError(_("Psychologist is not available for bookings"))

            return psychologist
        except Psychologist.DoesNotExist:
            raise serializers.ValidationError(_("Psychologist not found"))

    def validate(self, attrs):
        """Cross-field validation"""
        psychologist = attrs['psychologist_id']  # This is now a Psychologist instance
        session_type = attrs['session_type']

        # Validate psychologist offers this session type
        if session_type == 'OnlineMeeting' and not psychologist.offers_online_sessions:
            raise serializers.ValidationError(_("Psychologist does not offer online sessions"))

        if session_type == 'InitialConsultation' and not psychologist.offers_initial_consultation:
            raise serializers.ValidationError(_("Psychologist does not offer initial consultations"))

        return attrs

    def create(self, validated_data):
        """Add item to cart"""
        user = self.context['request'].user
        child = validated_data['child_id']  # Now a Child instance
        psychologist = validated_data['psychologist_id']  # Now a Psychologist instance
        session_type = validated_data['session_type']
        start_slot_id = validated_data['start_slot_id']
        parent_notes = validated_data.get('parent_notes', '')
        currency = validated_data['currency']

        return CartService.add_item_to_cart(
            user=user,
            child=child,
            psychologist=psychologist,
            session_type=session_type,
            start_slot_id=start_slot_id,
            parent_notes=parent_notes,
            currency=currency
        )


class CartSummarySerializer(serializers.Serializer):
    """
    Serializer for cart summary information
    """
    cart_id = serializers.UUIDField(read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    currency = serializers.CharField(read_only=True)
    expired_items_count = serializers.IntegerField(read_only=True)
    has_expired_items = serializers.BooleanField(read_only=True)
    is_empty = serializers.BooleanField(read_only=True)
    last_updated = serializers.DateTimeField(read_only=True)


class CheckoutCartItemSerializer(serializers.Serializer):
    """
    Serializer for checking out a cart item
    """
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

    def validate(self, attrs):
        """Validate checkout request"""
        cart_item = self.context.get('cart_item')

        if not cart_item:
            raise serializers.ValidationError(_("Cart item not found"))

        if cart_item.is_past_due:
            raise serializers.ValidationError(_("Cannot checkout expired appointment"))

        return attrs

    def save(self):
        """Checkout the cart item"""
        cart_item = self.context['cart_item']
        user = self.context['request'].user
        currency = self.validated_data['currency']
        provider = self.validated_data['provider']

        try:
            return CartService.checkout_cart_item(
                user=user,
                item_id=str(cart_item.item_id),
                currency=currency,
                provider_name=provider
            )
        except SlotUnavailableError as e:
            raise serializers.ValidationError(str(e))
        except CheckoutError as e:
            raise serializers.ValidationError(f"Checkout failed: {str(e)}")


class CartItemAvailabilitySerializer(serializers.Serializer):
    """
    Serializer for checking cart item availability
    """
    available = serializers.BooleanField(read_only=True)
    reason = serializers.CharField(read_only=True)
    expired = serializers.BooleanField(read_only=True)


class RemoveCartItemSerializer(serializers.Serializer):
    """
    Serializer for removing items from cart
    """
    # No fields needed - item_id comes from URL
    pass


class CartItemUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating cart item notes
    """
    class Meta:
        model = CartItem
        fields = ['parent_notes']

    def validate(self, attrs):
        """Validate update request"""
        cart_item = self.instance

        if cart_item.is_past_due:
            raise serializers.ValidationError(_("Cannot update expired appointment"))

        return attrs


class BookingOverviewSerializer(serializers.Serializer):
    """
    Serializer for booking overview display before checkout
    """
    cart_item = CartItemSerializer(read_only=True)
    availability_status = CartItemAvailabilitySerializer(read_only=True)
    pricing_breakdown = serializers.DictField(read_only=True)
    booking_summary = serializers.DictField(read_only=True)


class CartValidationSerializer(serializers.Serializer):
    """
    Serializer for validating entire cart
    """
    valid_items = CartItemSerializer(many=True, read_only=True)
    expired_items = CartItemSerializer(many=True, read_only=True)
    unavailable_items = serializers.ListField(
        child=serializers.DictField(),
        read_only=True
    )
    total_valid_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    can_checkout = serializers.BooleanField(read_only=True)
    issues_found = serializers.ListField(child=serializers.CharField(), read_only=True)