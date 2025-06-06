# payments/tests/test_serializers.py
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from rest_framework.test import APIRequestFactory

from users.models import User
from psychologists.models import Psychologist
from payments.models import Order
from payments.serializers import CreateRegistrationOrderSerializer
from payments.services import OrderService


class CreateRegistrationOrderSerializerTest(TestCase):
    def setUp(self):
        """Set up test data"""
        # Create psychologist user
        self.user = User.objects.create_user(
            email='psychologist@test.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )

        # Create psychologist profile
        self.psychologist = Psychologist.objects.create(
            user=self.user,
            first_name='Dr. Test',
            last_name='Psychologist',
            license_number='PSY123456',
            license_issuing_authority='Test Authority',
            license_expiry_date='2025-12-31',
            years_of_experience=5,
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Test St'
        )

        # Create request factory
        self.factory = APIRequestFactory()

    def test_expired_order_should_allow_new_order_creation(self):
        """Test that expired orders don't block new order creation"""
        # Create an expired order
        expired_order = Order.objects.create(
            order_type='psychologist_registration',
            user=self.user,
            psychologist=self.psychologist,
            amount=Decimal('100.00'),
            currency='USD',
            payment_provider='stripe',
            description='Test registration order',
            status='pending',  # Initially pending
            expires_at=timezone.now() - timedelta(hours=1),  # Expired 1 hour ago
            metadata={
                'psychologist_id': str(self.psychologist.user.id),
                'service_type': 'psychologist_registration'
            }
        )
        print(expired_order.is_expired)
        # Manually expire the order (simulating what should happen automatically)
        OrderService.expire_order(expired_order)
        print(expired_order.is_expired)
        # Verify the order is expired
        expired_order.refresh_from_db()
        self.assertEqual(expired_order.status, 'expired')

        # Now try to create a new registration order
        request = self.factory.post('/api/payments/orders/create-registration-order/')
        request.user = self.user

        serializer_data = {
            'currency': 'USD',
            'provider': 'stripe'
        }

        serializer = CreateRegistrationOrderSerializer(
            data=serializer_data,
            context={'request': request}
        )

        # This should be valid - expired orders shouldn't block new orders
        self.assertTrue(
            serializer.is_valid(),
            f"Serializer should be valid but got errors: {serializer.errors}"
        )

        # Should be able to create the order
        new_order = serializer.save()
        self.assertIsNotNone(new_order)
        self.assertEqual(new_order.status, 'pending')
        self.assertEqual(new_order.psychologist, self.psychologist)

    def test_pending_order_blocks_new_order_creation(self):
        """Test that active pending orders do block new order creation"""
        # Create a pending (non-expired) order
        pending_order = Order.objects.create(
            order_type='psychologist_registration',
            user=self.user,
            psychologist=self.psychologist,
            amount=Decimal('100.00'),
            currency='USD',
            payment_provider='stripe',
            description='Test registration order',
            status='pending',
            expires_at=timezone.now() + timedelta(hours=1),  # Not expired yet
            metadata={
                'psychologist_id': str(self.psychologist.user.id),
                'service_type': 'psychologist_registration'
            }
        )

        # Try to create another registration order
        request = self.factory.post('/api/payments/orders/create-registration-order/')
        request.user = self.user

        serializer_data = {
            'currency': 'USD',
            'provider': 'stripe'
        }

        serializer = CreateRegistrationOrderSerializer(
            data=serializer_data,
            context={'request': request}
        )

        # This should be invalid - pending orders should block new orders
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)
        self.assertIn('You already have an active registration order', str(serializer.errors))

    def test_paid_order_blocks_new_order_creation(self):
        """Test that paid orders block new order creation"""
        # Create a paid order
        paid_order = Order.objects.create(
            order_type='psychologist_registration',
            user=self.user,
            psychologist=self.psychologist,
            amount=Decimal('100.00'),
            currency='USD',
            payment_provider='stripe',
            description='Test registration order',
            status='paid',
            paid_at=timezone.now(),
            metadata={
                'psychologist_id': str(self.psychologist.user.id),
                'service_type': 'psychologist_registration'
            }
        )

        # Try to create another registration order
        request = self.factory.post('/api/payments/orders/create-registration-order/')
        request.user = self.user

        serializer_data = {
            'currency': 'USD',
            'provider': 'stripe'
        }

        serializer = CreateRegistrationOrderSerializer(
            data=serializer_data,
            context={'request': request}
        )

        # This should be invalid - paid orders should block new orders
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)
        self.assertIn('You already have an active registration order', str(serializer.errors))