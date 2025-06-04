# payments/tests/test_views.py
import json
import uuid
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.authtoken.models import Token

from users.models import User
from psychologists.models import Psychologist
from payments.models import Order, Payment, Transaction
from payments.services import OrderService, PaymentService


class PsychologistRegistrationPaymentTestCase(APITestCase):
    """
    Test cases for the complete psychologist registration payment flow:
    1. Psychologist Registration → Profile Creation → Payment Processing → Verification Status → Approved
    """

    def setUp(self):
        """Set up test data"""
        # Create psychologist user with verified email
        self.psychologist_user = User.objects.create_user(
            email='test.psychologist@example.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )

        # Create psychologist profile
        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Dr. Jane',
            last_name='Smith',
            license_number='PSY123456',
            license_issuing_authority='State Board of Psychology',
            license_expiry_date='2025-12-31',
            years_of_experience=5,
            biography='Experienced child psychologist',
            offers_online_sessions=True,
            offers_initial_consultation=True,
            office_address='123 Main St, City, State',
            verification_status='Pending'
        )

        # Create authentication token
        self.token = Token.objects.create(user=self.psychologist_user)

        # Set up API client authentication
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        # Test data for API calls
        self.registration_order_data = {
            'currency': 'USD',
            'provider': 'stripe'
        }

        self.payment_initiation_data = {
            'success_url': 'http://localhost:3000/payment/success',
            'cancel_url': 'http://localhost:3000/payment/cancel'
        }

    def test_complete_registration_payment_flow(self):
        """
        Test the complete registration payment flow:
        Registration Order → Payment Initiation → Payment Success → Auto-approval
        """
        # Step 1: Create registration order
        with patch('payments.providers.stripe_provider.stripe.PaymentIntent.create') as mock_stripe_create:
            # Mock Stripe response
            mock_payment_intent = MagicMock()
            mock_payment_intent.id = 'pi_test_123456789'
            mock_payment_intent.client_secret = 'pi_test_123456789_secret_test'
            mock_payment_intent.status = 'requires_payment_method'
            mock_payment_intent.to_dict_recursive.return_value = {'id': 'pi_test_123456789'}
            mock_stripe_create.return_value = mock_payment_intent

            # Create registration order
            url = reverse('orders-create-registration-order')
            response = self.client.post(url, self.registration_order_data, format='json')

            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertIn('order', response.data)

            order_data = response.data['order']
            self.assertEqual(order_data['order_type'], 'psychologist_registration')
            self.assertEqual(Decimal(order_data['amount']), Decimal('100.00'))  # From settings
            self.assertEqual(order_data['currency'], 'USD')
            self.assertEqual(order_data['status'], 'pending')

            # Verify order was created in database
            order = Order.objects.get(order_id=order_data['order_id'])
            self.assertEqual(order.user, self.psychologist_user)
            self.assertEqual(order.psychologist, self.psychologist)
            self.assertEqual(order.order_type, 'psychologist_registration')

            # Step 2: Initiate payment
            payment_url = reverse('orders-initiate-payment', kwargs={'pk': order.order_id})
            payment_response = self.client.post(payment_url, self.payment_initiation_data, format='json')

            self.assertEqual(payment_response.status_code, status.HTTP_200_OK)
            self.assertIn('payment_data', payment_response.data)

            payment_data = payment_response.data['payment_data']
            self.assertEqual(payment_data['order_id'], str(order.order_id))
            self.assertIn('payment_intent_id', payment_data)
            self.assertIn('client_secret', payment_data)

            # Verify payment record was created
            payment = Payment.objects.get(order=order)
            self.assertEqual(payment.provider_payment_id, 'pi_test_123456789')
            self.assertEqual(payment.amount, order.amount)
            self.assertEqual(payment.currency, order.currency)

            # Verify transaction records
            self.assertTrue(Transaction.objects.filter(
                order=order,
                transaction_type='order_created'
            ).exists())
            self.assertTrue(Transaction.objects.filter(
                order=order,
                payment=payment,
                transaction_type='payment_initiated'
            ).exists())

    @patch('payments.providers.stripe_provider.stripe.PaymentIntent.retrieve')
    def test_payment_confirmation_and_auto_approval(self, mock_stripe_retrieve):
        """
        Test payment confirmation and automatic psychologist approval
        """
        # Create order and payment
        order = OrderService.create_psychologist_registration_order(
            psychologist=self.psychologist,
            currency='USD',
            provider_name='stripe'
        )

        payment = Payment.objects.create(
            order=order,
            provider_payment_id='pi_test_success_123',
            amount=order.amount,
            currency=order.currency,
            payment_method='card'
        )

        # Mock successful Stripe payment intent
        mock_payment_intent = MagicMock()
        mock_payment_intent.id = 'pi_test_success_123'
        mock_payment_intent.status = 'succeeded'
        mock_payment_intent.amount = 10000  # $100.00 in cents
        mock_payment_intent.currency = 'usd'
        mock_payment_intent.charges.data = [MagicMock(
            payment_method_details=MagicMock(
                type='card',
                to_dict_recursive=lambda: {'type': 'card'}
            )
        )]
        mock_payment_intent.to_dict_recursive.return_value = {'id': 'pi_test_success_123'}
        mock_stripe_retrieve.return_value = mock_payment_intent

        # Confirm payment
        success = PaymentService.confirm_payment(payment)

        self.assertTrue(success)

        # Verify payment status updated
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'succeeded')
        self.assertIsNotNone(payment.processed_at)

        # Verify order status updated
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertIsNotNone(order.paid_at)

        # Verify psychologist auto-approval
        self.psychologist.refresh_from_db()
        self.assertEqual(self.psychologist.verification_status, 'Approved')

        # Verify transaction record
        self.assertTrue(Transaction.objects.filter(
            order=order,
            payment=payment,
            transaction_type='payment_succeeded'
        ).exists())

    def test_registration_order_creation_validation(self):
        """Test validation for registration order creation"""
        # Test: Only psychologists can create registration orders
        parent_user = User.objects.create_user(
            email='parent@example.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        parent_token = Token.objects.create(user=parent_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {parent_token.key}')

        url = reverse('orders-create-registration-order')
        response = self.client.post(url, self.registration_order_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Only psychologists can create registration orders', str(response.data))

        # Reset authentication
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

    def test_duplicate_registration_order_prevention(self):
        """Test prevention of duplicate registration orders"""
        # Create first order
        with patch('payments.providers.stripe_provider.stripe.PaymentIntent.create'):
            url = reverse('orders-create-registration-order')
            response1 = self.client.post(url, self.registration_order_data, format='json')
            self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

            # Try to create second order
            response2 = self.client.post(url, self.registration_order_data, format='json')
            self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('already have an active registration order', str(response2.data))

    def test_order_cancellation(self):
        """Test order cancellation functionality"""
        # Create order
        with patch('payments.providers.stripe_provider.stripe.PaymentIntent.create'):
            url = reverse('orders-create-registration-order')
            response = self.client.post(url, self.registration_order_data, format='json')
            order_id = response.data['order']['order_id']

            # Cancel order
            cancel_url = reverse('orders-cancel', kwargs={'pk': order_id})
            cancel_response = self.client.post(cancel_url)

            self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)
            self.assertIn('Order cancelled successfully', cancel_response.data['message'])

            # Verify order status
            order = Order.objects.get(order_id=order_id)
            self.assertEqual(order.status, 'cancelled')

    def test_payment_initiation_validation(self):
        """Test payment initiation validation"""
        # Create order
        order = OrderService.create_psychologist_registration_order(
            psychologist=self.psychologist,
            currency='USD',
            provider_name='stripe'
        )

        # Mark order as paid to test validation (need to set paid_at timestamp)
        order.status = 'paid'
        order.paid_at = timezone.now()
        order.save()

        # Try to initiate payment on paid order
        payment_url = reverse('orders-initiate-payment', kwargs={'pk': order.order_id})
        response = self.client.post(payment_url, self.payment_initiation_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot be paid', str(response.data))

    def test_order_status_endpoint(self):
        """Test order status retrieval"""
        # Create order
        order = OrderService.create_psychologist_registration_order(
            psychologist=self.psychologist,
            currency='USD',
            provider_name='stripe'
        )

        # Get order status
        status_url = reverse('orders-status', kwargs={'pk': order.order_id})
        response = self.client.get(status_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['order_id'], str(order.order_id))
        self.assertEqual(response.data['status'], 'pending')
        self.assertTrue(response.data['can_be_paid'])
        self.assertFalse(response.data['is_expired'])

    def test_order_list_and_retrieve(self):
        """Test order listing and retrieval"""
        # Create order
        order = OrderService.create_psychologist_registration_order(
            psychologist=self.psychologist,
            currency='USD',
            provider_name='stripe'
        )

        # Test list orders
        list_url = reverse('orders-list')
        list_response = self.client.get(list_url)

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.data['results']), 1)
        self.assertEqual(list_response.data['results'][0]['order_id'], str(order.order_id))

        # Test retrieve order
        detail_url = reverse('orders-detail', kwargs={'pk': order.order_id})
        detail_response = self.client.get(detail_url)

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data['order_id'], str(order.order_id))
        self.assertIn('psychologist', detail_response.data)

    def test_payment_failure_handling(self):
        """Test payment failure handling"""
        with patch('payments.providers.stripe_provider.stripe.PaymentIntent.retrieve') as mock_retrieve:
            # Create order and payment
            order = OrderService.create_psychologist_registration_order(
                psychologist=self.psychologist,
                currency='USD',
                provider_name='stripe'
            )

            payment = Payment.objects.create(
                order=order,
                provider_payment_id='pi_test_failed_123',
                amount=order.amount,
                currency=order.currency,
                payment_method='card'
            )

            # Mock failed payment intent
            mock_payment_intent = MagicMock()
            mock_payment_intent.id = 'pi_test_failed_123'
            mock_payment_intent.status = 'requires_payment_method'
            mock_payment_intent.amount = 10000
            mock_payment_intent.currency = 'usd'
            mock_payment_intent.charges.data = []
            mock_payment_intent.to_dict_recursive.return_value = {'id': 'pi_test_failed_123'}
            mock_retrieve.return_value = mock_payment_intent

            # Confirm payment (should result in failed status)
            success = PaymentService.confirm_payment(payment)

            self.assertFalse(success)

            # Verify payment status
            payment.refresh_from_db()
            self.assertEqual(payment.status, 'failed')

            # Verify psychologist is NOT auto-approved
            self.psychologist.refresh_from_db()
            self.assertEqual(self.psychologist.verification_status, 'Pending')

    def test_pricing_endpoint(self):
        """Test pricing information endpoint"""
        # Test without authentication (pricing should be public)
        self.client.credentials()  # Remove authentication

        url = reverse('pricing')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['currency'], 'USD')
        self.assertIn('services', response.data)
        self.assertIn('psychologist_registration', response.data['services'])
        self.assertEqual(
            Decimal(response.data['services']['psychologist_registration']),
            Decimal('100.00')
        )

    def test_user_isolation(self):
        """Test that users can only see their own orders"""
        # Create another psychologist
        other_user = User.objects.create_user(
            email='other.psychologist@example.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )

        other_psychologist = Psychologist.objects.create(
            user=other_user,
            first_name='Dr. John',
            last_name='Doe',
            license_number='PSY789012',
            license_issuing_authority='State Board',
            license_expiry_date='2025-12-31',
            years_of_experience=3,
            offers_online_sessions=True,
            offers_initial_consultation=False,  # Set to False to avoid office_address requirement
            verification_status='Pending'
        )

        # Create order for other psychologist
        other_order = OrderService.create_psychologist_registration_order(
            psychologist=other_psychologist,
            currency='USD',
            provider_name='stripe'
        )

        # Create order for current psychologist
        my_order = OrderService.create_psychologist_registration_order(
            psychologist=self.psychologist,
            currency='USD',
            provider_name='stripe'
        )

        # Current user should only see their own order
        list_url = reverse('orders-list')
        response = self.client.get(list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['order_id'], str(my_order.order_id))

        # Should not be able to access other user's order
        other_detail_url = reverse('orders-detail', kwargs={'pk': other_order.order_id})
        other_response = self.client.get(other_detail_url)
        self.assertEqual(other_response.status_code, status.HTTP_404_NOT_FOUND)

    # def test_stripe_error_handling(self):
    #     """Test Stripe API error handling"""
    #     with patch('payments.services.get_payment_provider') as mock_get_provider:
    #         # Mock the provider to raise an error
    #         mock_provider = MagicMock()
    #         mock_provider.create_payment_intent.side_effect = Exception("Stripe API Error")
    #         mock_get_provider.return_value = mock_provider

    #         url = reverse('orders-create-registration-order')
    #         response = self.client.post(url, self.registration_order_data, format='json')

    #         self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    #         self.assertIn('Failed to create registration order', str(response.data))

    def tearDown(self):
        """Clean up test data"""
        # Clear all test data
        Transaction.objects.all().delete()
        Payment.objects.all().delete()
        Order.objects.all().delete()
        Psychologist.objects.all().delete()
        User.objects.all().delete()


class WebhookTestCase(APITestCase):
    """
    Test cases for webhook handling in the registration flow
    """

    def setUp(self):
        """Set up test data for webhook tests"""
        self.psychologist_user = User.objects.create_user(
            email='webhook.test@example.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )

        self.psychologist = Psychologist.objects.create(
            user=self.psychologist_user,
            first_name='Dr. Webhook',
            last_name='Test',
            license_number='PSY-WEBHOOK-123',
            license_issuing_authority='Test Board',
            license_expiry_date='2025-12-31',
            years_of_experience=5,
            offers_online_sessions=True,
            offers_initial_consultation=False,  # Set to False to avoid office_address requirement
            verification_status='Pending'
        )

    @patch('payments.providers.stripe_provider.stripe.Webhook.construct_event')
    @patch('payments.providers.stripe_provider.stripe.PaymentIntent.retrieve')
    def test_successful_payment_webhook(self, mock_retrieve, mock_construct_event):
        """Test webhook handling for successful payment"""
        # Create order and payment
        order = OrderService.create_psychologist_registration_order(
            psychologist=self.psychologist,
            currency='USD',
            provider_name='stripe'
        )

        payment = Payment.objects.create(
            order=order,
            provider_payment_id='pi_webhook_test_123',
            amount=order.amount,
            currency=order.currency,
            payment_method='card'
        )

        # Mock webhook event
        mock_event = {
            'id': 'evt_test_webhook',
            'type': 'payment_intent.succeeded',
            'created': 1234567890,
            'livemode': False,
            'data': {
                'object': {
                    'id': 'pi_webhook_test_123',
                    'object': 'payment_intent',
                    'status': 'succeeded',
                    'amount': 10000,
                    'currency': 'usd'
                }
            }
        }
        mock_construct_event.return_value = mock_event

        # Mock payment intent retrieval
        mock_payment_intent = MagicMock()
        mock_payment_intent.id = 'pi_webhook_test_123'
        mock_payment_intent.status = 'succeeded'
        mock_payment_intent.amount = 10000
        mock_payment_intent.currency = 'usd'
        mock_payment_intent.charges.data = [MagicMock(
            payment_method_details=MagicMock(
                type='card',
                to_dict_recursive=lambda: {'type': 'card'}
            )
        )]
        mock_payment_intent.to_dict_recursive.return_value = {'id': 'pi_webhook_test_123'}
        mock_retrieve.return_value = mock_payment_intent

        # Send webhook
        webhook_url = reverse('stripe-webhook')
        webhook_payload = json.dumps(mock_event).encode('utf-8')

        response = self.client.post(
            webhook_url,
            data=webhook_payload,
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='test_signature'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['event_type'], 'payment_intent.succeeded')

        # Verify payment was confirmed
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'succeeded')

        # Verify psychologist was auto-approved
        self.psychologist.refresh_from_db()
        self.assertEqual(self.psychologist.verification_status, 'Approved')

    def tearDown(self):
        """Clean up webhook test data"""
        Transaction.objects.all().delete()
        Payment.objects.all().delete()
        Order.objects.all().delete()
        Psychologist.objects.all().delete()
        User.objects.all().delete()


# Additional test settings for payment tests
@override_settings(
    PAYMENT_PROVIDERS={
        'STRIPE': {
            'ENABLED': True,
            'SECRET_KEY': 'sk_test_fake_key_for_testing',
            'PUBLISHABLE_KEY': 'pk_test_fake_key_for_testing',
            'WEBHOOK_SECRET': 'whsec_test_fake_secret_for_testing',
        }
    },
    PAYMENT_AMOUNTS={
        'PSYCHOLOGIST_REGISTRATION': {'USD': Decimal('100.00')},
    }
)
class PaymentConfigTestCase(APITestCase):
    """Test payment configuration and settings"""

    def test_payment_configuration_validation(self):
        """Test that payment configuration is properly validated"""
        from payments.providers import get_payment_provider

        # This should work with our test settings
        provider = get_payment_provider('stripe')
        self.assertEqual(provider.provider_name, 'stripe')
        self.assertTrue(provider.is_enabled())