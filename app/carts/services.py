# carts/services.py
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import logging

from .models import Cart, CartItem
from users.models import User
from children.models import Child
from psychologists.models import Psychologist
from appointments.models import AppointmentSlot
from payments.services import PricingService, OrderService, PaymentServiceError
from payments.models import Order

logger = logging.getLogger(__name__)


# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class CartServiceError(Exception):
    """Base exception for cart service related errors"""
    pass


class CartItemCreationError(CartServiceError):
    """Raised when cart item creation fails"""
    pass


class CartItemNotFoundError(CartServiceError):
    """Raised when cart item is not found"""
    pass


class SlotUnavailableError(CartServiceError):
    """Raised when slot is no longer available during checkout"""
    pass


class CheckoutError(CartServiceError):
    """Raised when checkout fails"""
    pass


# ============================================================================
# CART SERVICE
# ============================================================================

class CartService:
    """
    Service for managing shopping cart functionality
    """

    @staticmethod
    def get_or_create_cart(user: User) -> Cart:
        """
        Get or create cart for user

        Args:
            user: User instance

        Returns:
            Cart instance
        """
        try:
            cart, created = Cart.objects.get_or_create(user=user)
            if created:
                logger.info(f"Created new cart for user {user.email}")
            return cart
        except Exception as e:
            logger.error(f"Failed to get/create cart for user {user.email}: {str(e)}")
            raise CartServiceError(f"Failed to get cart: {str(e)}")

    @staticmethod
    def add_item_to_cart(
        user: User,
        child: Child,
        psychologist: Psychologist,
        session_type: str,
        start_slot_id: int,
        parent_notes: str = '',
        currency: str = 'USD'
    ) -> CartItem:
        """
        Add booking item to cart

        Args:
            user: User adding the item
            child: Child for the booking
            psychologist: Psychologist for the booking
            session_type: 'OnlineMeeting' or 'InitialConsultation'
            start_slot_id: ID of the starting slot
            parent_notes: Optional notes from parent
            currency: Currency for pricing

        Returns:
            Created CartItem instance

        Raises:
            CartItemCreationError: If item creation fails
        """
        try:
            with transaction.atomic():
                # Validate business rules
                CartService._validate_add_item_request(user, child, psychologist, session_type)

                # Get or create cart
                cart = CartService.get_or_create_cart(user)

                # Get slot information for scheduling details
                slot_info = CartService._get_slot_scheduling_info(
                    psychologist, start_slot_id, session_type
                )

                # Get pricing
                service_type = session_type.lower().replace('meeting', '_session')
                price = PricingService.get_service_price(service_type, currency)

                # Check if similar item already exists in cart
                existing_item = CartItem.objects.filter(
                    cart=cart,
                    child=child,
                    psychologist=psychologist,
                    start_slot_id=start_slot_id
                ).first()

                if existing_item:
                    # Update existing item
                    existing_item.session_type = session_type
                    existing_item.parent_notes = parent_notes
                    existing_item.price = price
                    existing_item.currency = currency
                    existing_item.scheduled_start_time = slot_info['start_time']
                    existing_item.scheduled_end_time = slot_info['end_time']
                    existing_item.save()

                    logger.info(f"Updated cart item {existing_item.item_id} for user {user.email}")
                    return existing_item
                else:
                    # Create new cart item
                    cart_item = CartItem.objects.create(
                        cart=cart,
                        child=child,
                        psychologist=psychologist,
                        session_type=session_type,
                        start_slot_id=start_slot_id,
                        scheduled_start_time=slot_info['start_time'],
                        scheduled_end_time=slot_info['end_time'],
                        price=price,
                        currency=currency,
                        parent_notes=parent_notes,
                        metadata={
                            'psychologist_name': psychologist.display_name,
                            'child_name': child.display_name,
                            'slot_date': slot_info['start_time'].date().isoformat(),
                            'duration_hours': 1 if session_type == 'OnlineMeeting' else 2
                        }
                    )

                    logger.info(f"Added cart item {cart_item.item_id} for user {user.email}")
                    return cart_item

        except Exception as e:
            logger.error(f"Failed to add item to cart for user {user.email}: {str(e)}")
            if isinstance(e, CartServiceError):
                raise
            raise CartItemCreationError(f"Failed to add item to cart: {str(e)}")

    @staticmethod
    def _validate_add_item_request(user: User, child: Child, psychologist: Psychologist, session_type: str):
        """Validate add item business rules"""
        # Check if user is a parent
        if not user.is_parent:
            raise CartItemCreationError("Only parents can add items to cart")

        # Check if child belongs to parent
        if not hasattr(user, 'parent_profile') or child.parent != user.parent_profile:
            raise CartItemCreationError("Child must belong to the booking parent")

        # Validate psychologist offers the service
        if session_type == 'OnlineMeeting' and not psychologist.offers_online_sessions:
            raise CartItemCreationError("Psychologist does not offer online sessions")

        if session_type == 'InitialConsultation' and not psychologist.offers_initial_consultation:
            raise CartItemCreationError("Psychologist does not offer initial consultations")

        # Check if psychologist is marketplace visible
        if not psychologist.is_marketplace_visible:
            raise CartItemCreationError("Psychologist is not available for booking")

    @staticmethod
    def _get_slot_scheduling_info(psychologist: Psychologist, start_slot_id: int, session_type: str) -> Dict[str, Any]:
        """Get scheduling information from slots (without reserving them)"""
        try:
            # Get the starting slot
            start_slot = AppointmentSlot.objects.get(
                slot_id=start_slot_id,
                psychologist=psychologist
            )

            start_time = start_slot.datetime_start

            if session_type == 'OnlineMeeting':
                end_time = start_slot.datetime_end
            else:  # InitialConsultation - 2 hours
                end_time = start_time + timedelta(hours=2)

            return {
                'start_time': start_time,
                'end_time': end_time,
                'slot_date': start_slot.slot_date,
                'start_slot': start_slot
            }

        except AppointmentSlot.DoesNotExist:
            raise CartItemCreationError(f"Slot {start_slot_id} not found for psychologist")

    @staticmethod
    def get_cart_items(user: User) -> List[CartItem]:
        """
        Get all items in user's cart

        Args:
            user: User instance

        Returns:
            List of CartItem instances
        """
        try:
            cart = CartService.get_or_create_cart(user)
            return list(cart.items.select_related(
                'child', 'psychologist', 'psychologist__user'
            ).order_by('-created_at'))
        except Exception as e:
            logger.error(f"Failed to get cart items for user {user.email}: {str(e)}")
            return []

    @staticmethod
    def remove_item_from_cart(user: User, item_id: str) -> bool:
        """
        Remove item from cart

        Args:
            user: User instance
            item_id: CartItem UUID

        Returns:
            True if removed successfully
        """
        try:
            cart = CartService.get_or_create_cart(user)
            cart_item = cart.items.get(item_id=item_id)
            cart_item.delete()

            logger.info(f"Removed cart item {item_id} for user {user.email}")
            return True
        except CartItem.DoesNotExist:
            logger.warning(f"Cart item {item_id} not found for user {user.email}")
            return False
        except Exception as e:
            logger.error(f"Failed to remove cart item {item_id} for user {user.email}: {str(e)}")
            return False

    @staticmethod
    def clear_cart(user: User) -> bool:
        """
        Clear all items from user's cart

        Args:
            user: User instance

        Returns:
            True if cleared successfully
        """
        try:
            cart = CartService.get_or_create_cart(user)
            cart.clear()

            logger.info(f"Cleared cart for user {user.email}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear cart for user {user.email}: {str(e)}")
            return False

    @staticmethod
    def get_cart_summary(user: User) -> Dict[str, Any]:
        """
        Get cart summary with totals

        Args:
            user: User instance

        Returns:
            Dict with cart summary
        """
        try:
            cart = CartService.get_or_create_cart(user)
            items = CartService.get_cart_items(user)

            # Check for expired items (appointments in the past)
            expired_items = [item for item in items if item.is_past_due]
            valid_items = [item for item in items if not item.is_past_due]

            total_amount = sum(item.total_price for item in valid_items)

            return {
                'cart_id': str(cart.cart_id),
                'total_items': len(valid_items),
                'total_amount': total_amount,
                'currency': valid_items[0].currency if valid_items else 'USD',
                'expired_items_count': len(expired_items),
                'has_expired_items': len(expired_items) > 0,
                'is_empty': len(valid_items) == 0,
                'last_updated': cart.updated_at
            }
        except Exception as e:
            logger.error(f"Failed to get cart summary for user {user.email}: {str(e)}")
            return {
                'cart_id': None,
                'total_items': 0,
                'total_amount': 0,
                'currency': 'USD',
                'expired_items_count': 0,
                'has_expired_items': False,
                'is_empty': True,
                'last_updated': None
            }

    @staticmethod
    def checkout_cart_item(
        user: User,
        item_id: str,
        currency: str = 'USD',
        provider_name: str = 'stripe'
    ) -> Order:
        """
        Checkout a specific cart item by creating an order with slot reservation

        Args:
            user: User checking out
            item_id: CartItem UUID to checkout
            currency: Payment currency
            provider_name: Payment provider

        Returns:
            Created Order instance

        Raises:
            CheckoutError: If checkout fails
            SlotUnavailableError: If slots are no longer available
        """
        try:
            with transaction.atomic():
                # Get cart item
                cart = CartService.get_or_create_cart(user)
                cart_item = cart.items.select_related(
                    'child', 'psychologist'
                ).get(item_id=item_id)

                # Validate item is not expired
                if cart_item.is_past_due:
                    raise CheckoutError("Cannot checkout expired appointment")

                # Use the enhanced OrderService method that handles slot reservation
                order = OrderService.create_appointment_booking_order_with_reservation(
                    user=user,
                    child=cart_item.child,
                    psychologist=cart_item.psychologist,
                    session_type=cart_item.session_type,
                    start_slot_id=cart_item.start_slot_id,
                    parent_notes=cart_item.parent_notes,
                    currency=currency,
                    provider_name=provider_name
                )

                # Remove item from cart after successful order creation
                cart_item.delete()

                logger.info(f"Checked out cart item {item_id} as order {order.order_id} for user {user.email}")
                return order

        except CartItem.DoesNotExist:
            raise CartItemNotFoundError(f"Cart item {item_id} not found")
        except PaymentServiceError as e:
            # Check if it's a slot availability error
            if "slot" in str(e).lower() and ("booked" in str(e).lower() or "available" in str(e).lower()):
                raise SlotUnavailableError(
                    "The slot(s) of this Psychologist has been booked, please choose other time schedule"
                )
            raise CheckoutError(f"Checkout failed: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to checkout cart item {item_id} for user {user.email}: {str(e)}")
            if isinstance(e, CartServiceError):
                raise
            raise CheckoutError(f"Checkout failed: {str(e)}")

    @staticmethod
    def validate_cart_item_availability(cart_item: CartItem) -> Dict[str, Any]:
        """
        Validate if a cart item's slots are still available for booking

        Args:
            cart_item: CartItem instance

        Returns:
            Dict with availability status
        """
        try:
            # Check if appointment time has passed
            if cart_item.is_past_due:
                return {
                    'available': False,
                    'reason': 'Appointment time has passed',
                    'expired': True
                }

            # Check if starting slot still exists and is available
            try:
                start_slot = AppointmentSlot.objects.get(
                    slot_id=cart_item.start_slot_id,
                    psychologist=cart_item.psychologist
                )

                if start_slot.is_booked:
                    return {
                        'available': False,
                        'reason': 'Starting slot is already booked',
                        'expired': False
                    }

                # For InitialConsultation, check consecutive slot
                if cart_item.session_type == 'InitialConsultation':
                    consecutive_slots = AppointmentSlot.find_consecutive_slots(
                        cart_item.psychologist,
                        start_slot.slot_date,
                        start_slot.start_time,
                        2
                    )

                    if len(consecutive_slots) < 2:
                        return {
                            'available': False,
                            'reason': 'Not enough consecutive slots available',
                            'expired': False
                        }

                return {
                    'available': True,
                    'reason': 'Slots are available',
                    'expired': False
                }

            except AppointmentSlot.DoesNotExist:
                return {
                    'available': False,
                    'reason': 'Appointment slot no longer exists',
                    'expired': False
                }

        except Exception as e:
            logger.error(f"Error validating cart item availability: {str(e)}")
            return {
                'available': False,
                'reason': f'Validation error: {str(e)}',
                'expired': False
            }

    @staticmethod
    def cleanup_expired_cart_items(user: User = None) -> int:
        """
        Clean up expired cart items (appointments in the past)

        Args:
            user: Optional user to filter by

        Returns:
            Number of items cleaned up
        """
        try:
            queryset = CartItem.objects.filter(
                scheduled_start_time__lte=timezone.now()
            )

            if user:
                queryset = queryset.filter(cart__user=user)

            deleted_count = queryset.delete()[0]

            logger.info(f"Cleaned up {deleted_count} expired cart items")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup expired cart items: {str(e)}")
            return 0