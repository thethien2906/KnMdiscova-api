# carts/tests/test_models.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
import uuid

from users.models import User
from parents.models import Parent
from children.models import Child
from psychologists.models import Psychologist
from appointments.models import AppointmentSlot, PsychologistAvailability
from carts.models import Cart, CartItem


class CartModelTest(TestCase):
    """Test cases for Cart model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='testparent@example.com',
            password='testpassword123',
            user_type='Parent'
        )
        self.cart = Cart.objects.create(user=self.user)

    def test_cart_creation(self):
        """Test that a cart is created successfully."""
        self.assertIsInstance(self.cart, Cart)
        self.assertEqual(self.cart.user, self.user)
        self.assertIsNotNone(self.cart.created_at)
        self.assertIsNotNone(self.cart.updated_at)

    def test_cart_str_representation(self):
        """Test the string representation of the Cart model."""
        self.assertEqual(str(self.cart), f"Cart for {self.user.email}")

    def test_cart_is_empty_property(self):
        """Test the is_empty property of the Cart model."""
        self.assertTrue(self.cart.is_empty)
        # You would add items to the cart here to test the False case.

    def test_cart_clear_method(self):
        """Test the clear method of the Cart model."""
        # You would add items to the cart here before clearing.
        self.cart.clear()
        self.assertEqual(self.cart.total_items, 0)


class CartItemModelTest(TestCase):
    """Test cases for CartItem model"""

    def setUp(self):
        """Set up test data"""
        self.parent_user = User.objects.create_user(
            email='parent@example.com',
            password='testpassword123',
            user_type='Parent',
            is_verified=True
        )
        self.parent = Parent.objects.get(user=self.parent_user)
        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Test Child',
            date_of_birth=date(2015, 1, 1)
        )
        self.psychologist_user = User.objects.create_user(
            email='psychologist@example.com',
            password='testpassword123',
            user_type='Psychologist',
            is_verified=True

        )
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='John',
            last_name='Doe',
            license_number='PSY67890',
            license_issuing_authority='State Board',
            license_expiry_date=date.today() + timedelta(days=365),
            years_of_experience=5,
            verification_status='Approved',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='456 Oak Ave, City, State'
        )
        self.cart = Cart.objects.create(user=self.parent_user)
        self.availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,
            start_time='09:00:00',
            end_time='17:00:00',
            is_recurring=True,
        )
        self.availability_block = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time='09:00',
            end_time='17:00',
            is_recurring=True
        )

        # Helper function to get next Monday from today
        def get_next_monday():
            today = date.today()
            days_ahead = (7 - today.weekday()) % 7  # Days until Monday
            if days_ahead == 0:
                days_ahead = 7  # If today is Monday, get next Monday
            return today + timedelta(days=days_ahead)

        monday_date = get_next_monday()

        # Create future appointment slot for Zoom meeting creation tests
        self.slot = AppointmentSlot.objects.create(
            psychologist=self.psychologist,
            availability_block=self.availability_block,
            slot_date=monday_date,
            start_time='14:00',
            end_time='15:00',
            is_booked=True
        )
        future_start_time = timezone.now() + timedelta(days=1)
        future_end_time = future_start_time + timedelta(hours=1)
        self.cart_item = CartItem.objects.create(
            cart=self.cart,
            child=self.child,
            psychologist=self.psychologist,
            session_type='OnlineMeeting',
            start_slot_id=self.slot.slot_id,
            scheduled_start_time=future_start_time,
            scheduled_end_time=future_end_time,
            price=Decimal('150.00')
        )

    def test_cart_item_creation(self):
        """Test that a cart item is created successfully."""
        self.assertIsInstance(self.cart_item, CartItem)
        self.assertEqual(self.cart_item.child, self.child)
        self.assertEqual(self.cart_item.psychologist, self.psychologist)
        self.assertEqual(self.cart_item.session_type, 'OnlineMeeting')

    def test_cart_item_str_representation(self):
        """Test the string representation of the CartItem model."""
        expected_str = (f"Cart Item: {self.child.display_name} - "
                        f"{self.psychologist.display_name} (OnlineMeeting)")
        self.assertEqual(str(self.cart_item), expected_str)

    def test_cart_item_clean_method(self):
        """Test the clean method for validation."""
        # Test validation error when child does not belong to cart owner
        other_parent_user = User.objects.create_user(
            email='otherparent@example.com',
            password='testpassword123',
            user_type='Parent'
        )
        other_parent = Parent.objects.get(user=other_parent_user)
        other_child = Child.objects.create(
            parent=other_parent,
            first_name='Other Child',
            date_of_birth=date(2016, 1, 1)
        )
        with self.assertRaises(ValidationError):
            CartItem(
                cart=self.cart,
                child=other_child,
                psychologist=self.psychologist,
                session_type='OnlineMeeting',
                start_slot_id=self.slot.slot_id,
                scheduled_start_time=timezone.now() + timedelta(days=2),
                scheduled_end_time=timezone.now() + timedelta(days=2, hours=1),
                price=Decimal('150.00')
            ).clean()

    def test_cart_item_properties(self):
        """Test the properties of the CartItem model."""
        self.assertEqual(self.cart_item.total_price, Decimal('150.00'))
        self.assertEqual(self.cart_item.duration_hours, 1)
        self.assertFalse(self.cart_item.is_past_due)

    def test_get_slot_ids_needed(self):
        """Test the get_slot_ids_needed method."""
        self.assertEqual(self.cart_item.get_slot_ids_needed(), [self.slot.slot_id])
        self.cart_item.session_type = 'InitialConsultation'
        self.cart_item.save()
        # This is a simplified test; a real scenario would need to ensure the next slot exists
        self.assertEqual(self.cart_item.get_slot_ids_needed(), [self.slot.slot_id, self.slot.slot_id + 1])