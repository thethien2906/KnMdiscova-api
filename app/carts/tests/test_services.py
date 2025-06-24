# app/carts/tests/test_services.py

from django.test import TestCase
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from carts.models import Cart, CartItem
from carts.services import (
    CartService,
    CheckoutError,
    SlotUnavailableError,
)
from users.models import User
from parents.models import Parent
from children.models import Child
from psychologists.models import Psychologist, PsychologistAvailability
from appointments.models import AppointmentSlot
from payments.models import Order


class BaseCartTestCase(TestCase):
    """
    Base test case with common setup for cart-related tests.
    """

    def setUp(self):
        # Create users
        self.parent_user = User.objects.create_user(
            email="parent@example.com",
            password="password123",
            user_type="Parent",
            is_verified=True,
        )
        self.psychologist_user = User.objects.create_user(
            email="psychologist@example.com",
            password="password123",
            user_type="Psychologist",
            is_verified=True,
        )

        # Create profiles
        self.parent = Parent.objects.get(user=self.parent_user)
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name="Dr.",
            last_name="Test",
            license_number="PSY123",
            license_issuing_authority="State Board",
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status="Approved",
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address="123 Main St",
        )
        self.child = Child.objects.create(
            parent=self.parent,
            first_name="Test",
            last_name="Child",
            date_of_birth=date(2015, 1, 1),
        )

        # Create cart
        self.cart = Cart.objects.create(user=self.parent_user)

        # Create appointment slots
        self.availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time="09:00:00",
            end_time="17:00:00",
            is_recurring=True,
        )
        def get_next_monday():
            today = date.today()
            days_ahead = (7 - today.weekday()) % 7  # Days until Monday
            if days_ahead == 0:
                days_ahead = 7  # If today is Monday, get next Monday
            return today + timedelta(days=days_ahead)

        monday_date = get_next_monday()
        self.slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability,
            slot_date=monday_date,
            start_time='14:00',
            end_time='15:00',
            is_booked=True
        )


class CartServiceTests(BaseCartTestCase):
    """Test cases for the CartService"""

    def test_get_or_create_cart(self):
        """Test retrieving or creating a cart."""
        cart = CartService.get_or_create_cart(self.parent_user)
        self.assertIsNotNone(cart)
        self.assertEqual(cart.user, self.parent_user)
        self.assertEqual(Cart.objects.count(), 1) # Ensure no new cart was made

    @patch("carts.services.PricingService.get_service_price")
    def test_add_item_to_cart_new_item(self, mock_get_price):
        """Test adding a completely new item to the cart."""
        mock_get_price.return_value = Decimal("150.00")
        item = CartService.add_item_to_cart(
            user=self.parent_user,
            child=self.child,
            psychologist=self.psychologist,
            session_type="OnlineMeeting",
            start_slot_id=self.slot.slot_id,
        )
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(item.child, self.child)
        self.assertEqual(item.psychologist, self.psychologist)
        self.assertEqual(item.price, Decimal("150.00"))

    @patch("carts.services.PricingService.get_service_price")
    def test_add_item_to_cart_updates_existing_item(self, mock_get_price):
        """Test that adding an existing item updates it instead of creating a new one."""
        mock_get_price.return_value = Decimal("150.00")
        # Add item for the first time
        CartService.add_item_to_cart(
            user=self.parent_user,
            child=self.child,
            psychologist=self.psychologist,
            session_type="OnlineMeeting",
            start_slot_id=self.slot.slot_id,
            parent_notes="Initial notes."
        )
        self.assertEqual(CartItem.objects.count(), 1)

        # Add the same item again, but with different notes
        item = CartService.add_item_to_cart(
            user=self.parent_user,
            child=self.child,
            psychologist=self.psychologist,
            session_type="OnlineMeeting",
            start_slot_id=self.slot.slot_id,
            parent_notes="Updated notes.",
        )
        self.assertEqual(CartItem.objects.count(), 1) # Should not create a new item
        self.assertEqual(item.parent_notes, "Updated notes.")

    def test_remove_item_from_cart(self):
        """Test removing an item from the cart."""
        item = CartItem.objects.create(
            cart=self.cart,
            child=self.child,
            psychologist=self.psychologist,
            session_type="OnlineMeeting",
            start_slot_id=self.slot.slot_id,
            scheduled_start_time=timezone.now() + timedelta(days=1),
            scheduled_end_time=timezone.now() + timedelta(days=1, hours=1),
            price=Decimal("150.00"),
        )
        self.assertEqual(self.cart.items.count(), 1)
        removed = CartService.remove_item_from_cart(self.parent_user, item.item_id)
        self.assertTrue(removed)
        self.assertEqual(self.cart.items.count(), 0)

    def test_clear_cart(self):
        """Test clearing all items from the cart."""
        CartItem.objects.create(
            cart=self.cart,
            child=self.child,
            psychologist=self.psychologist,
            session_type="OnlineMeeting",
            start_slot_id=self.slot.slot_id,
            scheduled_start_time=timezone.now() + timedelta(days=1),
            scheduled_end_time=timezone.now() + timedelta(days=1, hours=1),
            price=Decimal("150.00"),
        )
        self.assertEqual(self.cart.items.count(), 1)
        cleared = CartService.clear_cart(self.parent_user)
        self.assertTrue(cleared)
        self.assertEqual(self.cart.items.count(), 0)

    @patch("carts.services.OrderService.create_appointment_booking_order_with_reservation")
    def test_checkout_cart_item_success(self, mock_create_order):
        """Test a successful checkout of a cart item."""
        mock_create_order.return_value = Order(
            order_id="c8f4b9f2-9b6a-4b7e-8b0a-9b0a9b0a9b0a"
        )
        item = CartItem.objects.create(
            cart=self.cart,
            child=self.child,
            psychologist=self.psychologist,
            session_type="OnlineMeeting",
            start_slot_id=self.slot.slot_id,
            scheduled_start_time=timezone.now() + timedelta(days=1),
            scheduled_end_time=timezone.now() + timedelta(days=1, hours=1),
            price=Decimal("150.00"),
        )

        order = CartService.checkout_cart_item(self.parent_user, item.item_id)
        self.assertIsNotNone(order)
        self.assertEqual(CartItem.objects.count(), 0) # Item should be removed after checkout

    def test_checkout_cart_item_expired(self):
        """Test that checking out an expired item raises an error."""
        # 1. Create a valid item with a future start time first.
        item = CartItem.objects.create(
            cart=self.cart,
            child=self.child,
            psychologist=self.psychologist,
            session_type="OnlineMeeting",
            start_slot_id=self.slot.slot_id,
            scheduled_start_time=timezone.now() + timedelta(days=1), # Valid future time
            scheduled_end_time=timezone.now() + timedelta(days=1, hours=1),
            price=Decimal("150.00"),
        )

        # 2. Use .update() to bypass validation and make the item expired.
        CartItem.objects.filter(pk=item.pk).update(
            scheduled_start_time=timezone.now() - timedelta(minutes=1) # Now it's in the past
        )
        item.refresh_from_db() # Refresh the instance to reflect the change

        # 3. Now, assert that the service correctly raises the CheckoutError.
        with self.assertRaises(CheckoutError):
            CartService.checkout_cart_item(self.parent_user, item.item_id)

    @patch("carts.services.OrderService.create_appointment_booking_order_with_reservation")
    def test_checkout_cart_item_slot_unavailable(self, mock_create_order):
        """Test checkout fails if the slot becomes unavailable."""
        mock_create_order.side_effect = SlotUnavailableError
        item = CartItem.objects.create(
            cart=self.cart,
            child=self.child,
            psychologist=self.psychologist,
            session_type="OnlineMeeting",
            start_slot_id=self.slot.slot_id,
            scheduled_start_time=timezone.now() + timedelta(days=1),
            scheduled_end_time=timezone.now() + timedelta(days=1, hours=1),
            price=Decimal("150.00"),
        )
        with self.assertRaises(SlotUnavailableError):
            CartService.checkout_cart_item(self.parent_user, item.item_id)