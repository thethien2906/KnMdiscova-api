# carts/tests/test_serializers.py
from django.test import TestCase
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from rest_framework.test import APIRequestFactory
from rest_framework.request import Request

from carts.models import Cart, CartItem
from carts.serializers import (
    CartItemSerializer,
    AddToCartSerializer,
    CartSerializer,
    CheckoutCartItemSerializer,
    CartItemUpdateSerializer,
    CartItemAvailabilitySerializer,
)
from users.models import User
from parents.models import Parent
from children.models import Child
from psychologists.models import Psychologist, PsychologistAvailability
from appointments.models import AppointmentSlot


class BaseCartTestCase(TestCase):
    """
    Base test case with common setup for cart-related tests.
    """

    def setUp(self):
        self.factory = APIRequestFactory()

        # Create a parent user and their profile
        self.parent_user = User.objects.create_user(
            email="parent@example.com",
            password="testpassword123",
            user_type="Parent",
            is_verified=True,
        )
        self.parent = Parent.objects.get(user=self.parent_user)

        # Create a psychologist user and their profile
        self.psychologist_user = User.objects.create_user(
            email="psychologist@example.com",
            password="testpassword123",
            user_type="Psychologist",
            is_verified=True,
        )
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name="Dr.",
            last_name="Test",
            license_number="PSY12345",
            license_issuing_authority="State Board",
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=10,
            verification_status="Approved",
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address="123 Main St",
        )

        # Create a child for the parent
        self.child = Child.objects.create(
            parent=self.parent,
            first_name="Test Child",
            date_of_birth=date(2015, 1, 1),
        )

        # Create a cart for the parent
        self.cart = Cart.objects.create(user=self.parent_user)

        # Create appointment slots
        self.availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time="09:00:00",
            end_time="17:00:00",
            is_recurring=True,
        )

        def get_next_monday():
            today = date.today()
            days_ahead = (7 - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)

        self.slot_date = get_next_monday()

        self.available_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.slot_date,
            start_time='10:00',
            end_time='11:00',
        )
        self.booked_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.slot_date,
            start_time='11:00',
            end_time='12:00',
            is_booked=True,
        )
        future_start_time = timezone.now() + timedelta(days=1)
        future_end_time = future_start_time + timedelta(hours=1)
        # Create a cart item
        self.cart_item = CartItem.objects.create(
            cart=self.cart,
            child=self.child,
            psychologist=self.psychologist,
            session_type="OnlineMeeting",
            start_slot_id=self.available_slot.slot_id,
            scheduled_start_time=future_start_time,
            scheduled_end_time=future_end_time,
            price=Decimal("150.00"),
        )



class CartItemSerializerTests(BaseCartTestCase):
    def test_cart_item_serializer(self):
        serializer = CartItemSerializer(self.cart_item)
        data = serializer.data
        self.assertEqual(data["item_id"], str(self.cart_item.item_id))
        self.assertEqual(data["child_name"], self.child.display_name)
        self.assertEqual(
            data["psychologist_name"], self.psychologist.display_name
        )
        self.assertEqual(data["duration_hours"], 1)
        self.assertEqual(Decimal(data["total_price"]), self.cart_item.price)
        self.assertFalse(data["is_past_due"])


class AddToCartSerializerTests(BaseCartTestCase):
    def test_add_to_cart_serializer_valid(self):
        request = self.factory.post("/api/carts/add-item/")
        request.user = self.parent_user
        context = {"request": request}
        data = {
            "child_id": str(self.child.id),
            "psychologist_id": str(self.psychologist.user.id),
            "session_type": "OnlineMeeting",
            "start_slot_id": self.available_slot.slot_id,
        }
        serializer = AddToCartSerializer(data=data, context=context)
        self.assertTrue(serializer.is_valid(raise_exception=True))

    def test_add_to_cart_serializer_invalid_child(self):
        request = self.factory.post("/api/carts/add-item/")
        request.user = self.parent_user
        context = {"request": request}
        data = {
            "child_id": "00000000-0000-0000-0000-000000000000",
            "psychologist_id": str(self.psychologist.user.id),
            "session_type": "OnlineMeeting",
            "start_slot_id": self.available_slot.slot_id,
        }
        serializer = AddToCartSerializer(data=data, context=context)
        self.assertFalse(serializer.is_valid())

    def test_add_to_cart_serializer_invalid_psychologist(self):
        request = self.factory.post("/api/carts/add-item/")
        request.user = self.parent_user
        context = {"request": request}
        data = {
            "child_id": str(self.child.id),
            "psychologist_id": "00000000-0000-0000-0000-000000000000",
            "session_type": "OnlineMeeting",
            "start_slot_id": self.available_slot.slot_id,
        }
        serializer = AddToCartSerializer(data=data, context=context)
        self.assertFalse(serializer.is_valid())


class CartSerializerTests(BaseCartTestCase):
    def test_cart_serializer(self):
        serializer = CartSerializer(self.cart)
        data = serializer.data
        self.assertEqual(data["cart_id"], str(self.cart.cart_id))
        self.assertEqual(data["total_items"], 1)
        self.assertEqual(Decimal(data["total_amount"]), self.cart_item.price)
        self.assertFalse(data["is_empty"])


class CheckoutCartItemSerializerTests(BaseCartTestCase):
    def test_checkout_cart_item_serializer_valid(self):
        request = self.factory.post(
            f"/api/carts/items/{self.cart_item.item_id}/checkout/"
        )
        request.user = self.parent_user
        context = {"request": request, "cart_item": self.cart_item}
        data = {"currency": "USD", "provider": "stripe"}
        serializer = CheckoutCartItemSerializer(data=data, context=context)
        self.assertTrue(serializer.is_valid())

    def test_checkout_cart_item_serializer_expired(self):
        # Use update() to bypass model validation for testing purposes
        CartItem.objects.filter(pk=self.cart_item.pk).update(
            scheduled_start_time=timezone.now() - timedelta(days=1)
        )
        self.cart_item.refresh_from_db()

        request = self.factory.post(
            f"/api/carts/items/{self.cart_item.item_id}/checkout/"
        )
        request.user = self.parent_user
        context = {"request": request, "cart_item": self.cart_item}
        data = {"currency": "USD", "provider": "stripe"}
        serializer = CheckoutCartItemSerializer(data=data, context=context)
        self.assertFalse(serializer.is_valid())


class CartItemUpdateSerializerTests(BaseCartTestCase):
    def test_update_cart_item_serializer_valid(self):
        data = {"parent_notes": "Updated notes"}
        serializer = CartItemUpdateSerializer(
            instance=self.cart_item, data=data, partial=True
        )
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.cart_item.refresh_from_db()
        self.assertEqual(self.cart_item.parent_notes, "Updated notes")

    def test_update_cart_item_serializer_expired(self):
        # Use update() to bypass model validation for testing purposes
        CartItem.objects.filter(pk=self.cart_item.pk).update(
            scheduled_start_time=timezone.now() - timedelta(days=1)
        )
        self.cart_item.refresh_from_db()

        data = {"parent_notes": "Updated notes"}
        serializer = CartItemUpdateSerializer(
            instance=self.cart_item, data=data, partial=True
        )
        self.assertFalse(serializer.is_valid())


class CartItemAvailabilitySerializerTests(BaseCartTestCase):
    def test_cart_item_availability_serializer_available(self):
        from carts.services import CartService

        availability = CartService.validate_cart_item_availability(
            self.cart_item
        )
        serializer = CartItemAvailabilitySerializer(availability)
        data = serializer.data
        self.assertTrue(data["available"])
        self.assertFalse(data["expired"])

    def test_cart_item_availability_serializer_unavailable(self):
        from carts.services import CartService

        self.cart_item.start_slot_id = self.booked_slot.slot_id
        self.cart_item.save()
        availability = CartService.validate_cart_item_availability(
            self.cart_item
        )
        serializer = CartItemAvailabilitySerializer(availability)
        data = serializer.data
        self.assertFalse(data["available"])
        self.assertFalse(data["expired"])

    def test_cart_item_availability_serializer_expired(self):
        from carts.services import CartService

        # Use update() to bypass model validation for testing purposes
        CartItem.objects.filter(pk=self.cart_item.pk).update(
            scheduled_start_time=timezone.now() - timedelta(days=1)
        )
        self.cart_item.refresh_from_db()

        availability = CartService.validate_cart_item_availability(
            self.cart_item
        )
        serializer = CartItemAvailabilitySerializer(availability)
        data = serializer.data
        self.assertFalse(data["available"])
        self.assertTrue(data["expired"])