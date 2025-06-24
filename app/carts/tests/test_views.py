# carts/tests/test_views.py
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal
from unittest.mock import patch

from carts.models import Cart, CartItem
from carts.services import CartService
from users.models import User
from parents.models import Parent
from children.models import Child
from payments.models import Order
from psychologists.models import Psychologist, PsychologistAvailability
from appointments.models import AppointmentSlot


class BaseCartTestCase(APITestCase):
    """
    Base test case with common setup for cart-related tests.
    """

    def setUp(self):
        # Create a parent user and their profile
        self.parent_user = User.objects.create_user(
            email="parent@example.com",
            password="testpassword123",
            user_type="Parent",
            is_verified=True,
        )
        self.parent = Parent.objects.get(user=self.parent_user)
        self.parent_token = Token.objects.create(user=self.parent_user)

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
        self.psychologist_token = Token.objects.create(
            user=self.psychologist_user
        )

        # Create a child for the parent
        self.child = Child.objects.create(
            parent=self.parent,
            first_name="Test Child",
            date_of_birth=date(2015, 1, 1),
        )

        # Create a cart for the parent
        self.cart = CartService.get_or_create_cart(self.parent_user)

        # Create appointment slots
        self.availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time="09:00:00",
            end_time="17:00:00",
            is_recurring=True,
        )

        self.slot_date = date.today() + timedelta(
            days=(7 - date.today().weekday()) % 7
        )
        self.available_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.slot_date,
            start_time="10:00:00",
            end_time="11:00:00",
        )

        # Create a cart item
        self.cart_item = CartService.add_item_to_cart(
            user=self.parent_user,
            child=self.child,
            psychologist=self.psychologist,
            session_type="OnlineMeeting",
            start_slot_id=self.available_slot.pk,
        )


class CartViewSetTests(BaseCartTestCase):
    def test_get_my_cart(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + self.parent_token.key
        )
        url = reverse("cart-my-cart")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["cart_id"], str(self.cart.cart_id))
        self.assertEqual(len(response.data["items"]), 1)

    def test_add_item_to_cart(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + self.parent_token.key
        )
        new_slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=self.slot_date,
            start_time="12:00:00",
            end_time="13:00:00",
            is_booked=False,
        )
        url = reverse("cart-add-item")
        data = {
            "child_id": str(self.child.id),
            "psychologist_id": str(self.psychologist_user.id),
            "session_type": "OnlineMeeting",
            "start_slot_id": new_slot.pk,
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.cart.items.count(), 2)

    def test_get_cart_summary(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + self.parent_token.key
        )
        url = reverse("cart-summary")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_items"], 1)
        self.assertEqual(
            Decimal(response.data["total_amount"]), self.cart_item.price
        )

    def test_clear_cart(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + self.parent_token.key
        )
        url = reverse("cart-clear")
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.items.count(), 0)

    def test_validate_cart(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + self.parent_token.key
        )
        url = reverse("cart-validate-cart")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["can_checkout"])

    def test_cleanup_expired_items(self):
        # Use update() to bypass model validation for testing purposes
        CartItem.objects.filter(pk=self.cart_item.pk).update(
            scheduled_start_time=timezone.now() - timedelta(days=1)
        )
        self.cart_item.refresh_from_db()

        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + self.parent_token.key
        )
        url = reverse("cart-cleanup-expired")
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items_removed"], 1)
        self.assertEqual(self.cart.items.count(), 0)


class CartItemViewSetTests(BaseCartTestCase):
    def test_retrieve_cart_item(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + self.parent_token.key
        )
        url = reverse("cart-items-detail", kwargs={"pk": self.cart_item.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["item_id"], str(self.cart_item.pk))

    @patch("carts.services.CartService.checkout_cart_item")
    def test_checkout_cart_item(self, mock_checkout):
        # The service returns an Order instance. We create one here for the
        # mock to return, ensuring it passes the Order model's validation.
        mock_order = Order.objects.create(
            user=self.parent_user,
            order_type='appointment_booking',
            psychologist=self.psychologist,
            amount=self.cart_item.price,
            currency=self.cart_item.currency,
            payment_provider='stripe',
            status='pending'
        )
        mock_checkout.return_value = mock_order

        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + self.parent_token.key
        )
        url = reverse("cart-items-checkout", kwargs={"pk": self.cart_item.pk})
        data = {"currency": "USD", "provider": "stripe"}
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['order']['order_id'], str(mock_order.order_id))
        mock_checkout.assert_called_once()

    def test_check_item_availability(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + self.parent_token.key
        )
        url = reverse(
            "cart-items-check-availability", kwargs={"pk": self.cart_item.pk}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["available"])

    def test_remove_item_from_cart(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + self.parent_token.key
        )
        url = reverse("cart-items-remove", kwargs={"pk": self.cart_item.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.cart.items.count(), 0)

    def test_update_cart_item_notes(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + self.parent_token.key
        )
        url = reverse(
            "cart-items-update-notes", kwargs={"pk": self.cart_item.pk}
        )
        data = {"parent_notes": "Updated notes"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.cart_item.refresh_from_db()
        self.assertEqual(self.cart_item.parent_notes, "Updated notes")

    def test_get_booking_overview(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Token " + self.parent_token.key
        )
        url = reverse(
            "cart-items-booking-overview", kwargs={"pk": self.cart_item.pk}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("booking_summary", response.data)
        self.assertIn("pricing_breakdown", response.data)