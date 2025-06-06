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
from datetime import date, datetime, timedelta

from users.models import User
from psychologists.models import Psychologist, PsychologistAvailability
from parents.models import Parent
from children.models import Child
from appointments.models import AppointmentSlot, Appointment
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



class AppointmentBookingPaymentTestCase(APITestCase):
    """
    Test cases for the complete appointment booking payment flow:
    1. Parent Books Appointment → Slot Reservation → Payment Processing → Appointment Confirmed
    """

    def setUp(self):
        """Set up test data"""
        # Create parent user with verified email
        self.parent_user = User.objects.create_user(
            email='test.parent@example.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True,
            is_active=True
        )

        # Create parent profile
        self.parent = Parent.objects.get(user=self.parent_user)

        # Create child for the parent
        self.child = Child.objects.create(
            parent=self.parent,
            first_name='Alice',
            last_name='Doe',
            date_of_birth=date.today() - timedelta(days=2555)  # ~7 years old
        )

        # Create psychologist user
        self.psychologist_user = User.objects.create_user(
            email='test.psychologist@example.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True,
            is_active=True
        )

        # Create approved psychologist profile (marketplace visible)
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
            verification_status='Approved',  # Important: Must be approved for marketplace
            hourly_rate=Decimal('150.00'),
            initial_consultation_rate=Decimal('280.00')
        )

        # Create psychologist availability (Monday 9 AM - 5 PM)
        self.availability = PsychologistAvailability.objects.create(
            psychologist=self.psychologist,
            day_of_week=1,  # Monday
            start_time='09:00:00',
            end_time='17:00:00',
            is_recurring=True
        )

        # Generate appointment slots for next Monday
        self.next_monday = self._get_next_monday()
        self.slots = self._create_appointment_slots_for_date(self.next_monday)

        # Create authentication token for parent
        self.token = Token.objects.create(user=self.parent_user)

        # Set up API client authentication
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        # Test data for API calls
        self.appointment_order_data = {
            'psychologist_id': str(self.psychologist_user.id),
            'child_id': str(self.child.id),
            'session_type': 'OnlineMeeting',
            'start_slot_id': self.slots[0].slot_id,  # 9 AM slot
            'parent_notes': 'Looking forward to the session',
            'currency': 'USD',
            'provider': 'stripe'
        }

        self.payment_initiation_data = {
            'success_url': 'http://localhost:3000/payment/success',
            'cancel_url': 'http://localhost:3000/payment/cancel'
        }

    def _get_next_monday(self):
        """Get the next Monday from today"""
        today = date.today()
        days_ahead = 0 - today.weekday()  # Monday is 0
        if days_ahead <= 0:  # Today is Monday or later
            days_ahead += 7
        return today + timedelta(days=days_ahead)

    def _create_appointment_slots_for_date(self, slot_date):
        """Create appointment slots for a specific date"""
        slots = []
        current_time = datetime.strptime('09:00', '%H:%M').time()
        end_time = datetime.strptime('17:00', '%H:%M').time()

        while current_time < end_time:
            slot_end_time = (datetime.combine(date.today(), current_time) + timedelta(hours=1)).time()
            slot = AppointmentSlot.objects.create(
                psychologist=self.psychologist,
                availability_block=self.availability,
                slot_date=slot_date,
                start_time=current_time,
                end_time=slot_end_time,
                is_booked=False
            )
            slots.append(slot)
            current_time = slot_end_time

        return slots

    # def test_complete_appointment_booking_flow(self):
    #     """
    #     Test the complete appointment booking flow:
    #     Create Order with Reservation → Payment Initiation → Payment Success → Appointment Confirmed
    #     """
    #     # Step 1: Create appointment order with slot reservation
    #     with patch('payments.providers.stripe_provider.stripe.PaymentIntent.create') as mock_stripe_create:
    #         # Mock Stripe response
    #         mock_payment_intent = MagicMock()
    #         mock_payment_intent.id = 'pi_test_appointment_123'
    #         mock_payment_intent.client_secret = 'pi_test_appointment_123_secret'
    #         mock_payment_intent.status = 'requires_payment_method'
    #         mock_payment_intent.to_dict_recursive.return_value = {'id': 'pi_test_appointment_123'}
    #         mock_stripe_create.return_value = mock_payment_intent

    #         # Create appointment order
    #         url = reverse('orders-create-appointment-order-with-reservation')
    #         response = self.client.post(url, self.appointment_order_data, format='json')

    #         self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    #         self.assertIn('order', response.data)
    #         self.assertIn('reserved_slots_count', response.data)

    #         order_data = response.data['order']
    #         self.assertEqual(order_data['order_type'], 'appointment_booking')
    #         self.assertEqual(Decimal(order_data['amount']), Decimal('150.00'))  # Online session price
    #         self.assertEqual(order_data['currency'], 'USD')
    #         self.assertEqual(order_data['status'], 'pending')
    #         self.assertEqual(response.data['reserved_slots_count'], 1)  # One slot for online session

    #         # Verify order was created in database
    #         order = Order.objects.get(order_id=order_data['order_id'])
    #         self.assertEqual(order.user, self.parent_user)
    #         self.assertEqual(order.psychologist, self.psychologist)
    #         self.assertEqual(order.order_type, 'appointment_booking')

    #         # Verify slot reservation
    #         reserved_slot = AppointmentSlot.objects.get(slot_id=self.slots[0].slot_id)
    #         self.assertEqual(reserved_slot.reservation_status, 'reserved')
    #         self.assertEqual(reserved_slot.reserved_by, self.parent_user)
    #         self.assertIsNotNone(reserved_slot.reserved_until)

    #         # Step 2: Initiate payment
    #         payment_url = reverse('orders-initiate-payment', kwargs={'pk': order.order_id})
    #         payment_response = self.client.post(payment_url, self.payment_initiation_data, format='json')

    #         self.assertEqual(payment_response.status_code, status.HTTP_200_OK)
    #         self.assertIn('payment_data', payment_response.data)

    #         payment_data = payment_response.data['payment_data']
    #         self.assertEqual(payment_data['order_id'], str(order.order_id))
    #         self.assertIn('payment_intent_id', payment_data)
    #         self.assertIn('client_secret', payment_data)

    #         # Verify payment record was created
    #         payment = Payment.objects.get(order=order)
    #         self.assertEqual(payment.provider_payment_id, 'pi_test_appointment_123')
    #         self.assertEqual(payment.amount, order.amount)
    #         self.assertEqual(payment.currency, order.currency)

    @patch('payments.providers.stripe_provider.stripe.PaymentIntent.retrieve')
    # def test_payment_confirmation_creates_appointment(self, mock_stripe_retrieve):
    #     """
    #     Test payment confirmation creates appointment and confirms slot booking
    #     """
    #     # Create order with reservation metadata
    #     order = Order.objects.create(
    #         order_type='appointment_booking',
    #         user=self.parent_user,
    #         psychologist=self.psychologist,
    #         amount=Decimal('150.00'),
    #         currency='USD',
    #         payment_provider='stripe',
    #         status='pending',
    #         description=f"OnlineMeeting with {self.psychologist.full_name} for {self.child.display_name}",
    #         expires_at=timezone.now() + timedelta(minutes=30),
    #         metadata={
    #             'user_id': str(self.parent_user.id),
    #             'child_id': str(self.child.id),
    #             'child_name': self.child.display_name,
    #             'psychologist_id': str(self.psychologist.user.id),
    #             'psychologist_name': self.psychologist.full_name,
    #             'session_type': 'OnlineMeeting',
    #             'parent_notes': 'Test booking',
    #             'reserved_slot_ids': [self.slots[0].slot_id],
    #             'start_slot_id': self.slots[0].slot_id,
    #             'slots_count': 1
    #         }
    #     )

    #     # Reserve the slot
    #     self.slots[0].reserve_for_payment(self.parent_user, 30)

    #     payment = Payment.objects.create(
    #         order=order,
    #         provider_payment_id='pi_test_booking_success',
    #         amount=order.amount,
    #         currency=order.currency,
    #         payment_method='card'
    #     )

    #     # Mock successful Stripe payment intent
    #     mock_payment_intent = MagicMock()
    #     mock_payment_intent.id = 'pi_test_booking_success'
    #     mock_payment_intent.status = 'succeeded'
    #     mock_payment_intent.amount = 15000  # $150.00 in cents
    #     mock_payment_intent.currency = 'usd'
    #     mock_payment_intent.charges.data = [MagicMock(
    #         payment_method_details=MagicMock(
    #             type='card',
    #             to_dict_recursive=lambda: {'type': 'card'}
    #         )
    #     )]
    #     mock_payment_intent.to_dict_recursive.return_value = {'id': 'pi_test_booking_success'}
    #     mock_stripe_retrieve.return_value = mock_payment_intent

    #     # Confirm payment
    #     success = PaymentService.confirm_payment(payment)

    #     self.assertTrue(success)

    #     # Verify payment status updated
    #     payment.refresh_from_db()
    #     self.assertEqual(payment.status, 'succeeded')
    #     self.assertIsNotNone(payment.processed_at)

    #     # Verify order status updated
    #     order.refresh_from_db()
    #     self.assertEqual(order.status, 'paid')
    #     self.assertIsNotNone(order.paid_at)

    #     # Verify appointment was created
    #     appointment = Appointment.objects.filter(
    #         child=self.child,
    #         psychologist=self.psychologist,
    #         parent=self.parent
    #     ).first()
    #     self.assertIsNotNone(appointment)
    #     self.assertEqual(appointment.session_type, 'OnlineMeeting')
    #     self.assertEqual(appointment.appointment_status, 'Scheduled')
    #     self.assertEqual(appointment.payment_status, 'Paid')

    #     # Verify slot was marked as booked
    #     self.slots[0].refresh_from_db()
    #     self.assertTrue(self.slots[0].is_booked)
    #     self.assertEqual(self.slots[0].reservation_status, 'available')  # Reservation cleared
    #     self.assertIsNone(self.slots[0].reserved_by)

    def test_initial_consultation_booking(self):
        """Test booking a 2-hour initial consultation"""
        # Update test data for initial consultation
        self.appointment_order_data['session_type'] = 'InitialConsultation'

        with patch('payments.providers.stripe_provider.stripe.PaymentIntent.create') as mock_stripe_create:
            mock_payment_intent = MagicMock()
            mock_payment_intent.id = 'pi_test_consultation_123'
            mock_payment_intent.client_secret = 'pi_test_consultation_123_secret'
            mock_payment_intent.status = 'requires_payment_method'
            mock_payment_intent.to_dict_recursive.return_value = {'id': 'pi_test_consultation_123'}
            mock_stripe_create.return_value = mock_payment_intent

            url = reverse('orders-create-appointment-order-with-reservation')

            # Debug: Print the request data
            print(f"Request data: {self.appointment_order_data}")

            response = self.client.post(url, self.appointment_order_data, format='json')

            # Debug: Print response details
            print(f"Response status: {response.status_code}")
            print(f"Response data: {response.data}")
            print(f"Response content: {response.content}")

            # This will now show you what the actual error is
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

            # Rest of your test assertions...
            order_data = response.data['order']
            self.assertEqual(Decimal(order_data['amount']), Decimal('280.00'))
            self.assertEqual(response.data['reserved_slots_count'], 2)

            # Verify two consecutive slots were reserved
            reserved_slots = AppointmentSlot.objects.filter(
                reserved_by=self.parent_user,
                reservation_status='reserved'
            ).order_by('start_time')
            self.assertEqual(reserved_slots.count(), 2)
            self.assertEqual(reserved_slots[0].start_time, self.slots[0].start_time)
            self.assertEqual(reserved_slots[1].start_time, self.slots[1].start_time)
    def test_appointment_order_validation(self):
        """Test validation for appointment order creation"""
        # Test: Only parents can book appointments
        psychologist_token = Token.objects.create(user=self.psychologist_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {psychologist_token.key}')

        url = reverse('orders-create-appointment-order-with-reservation')
        response = self.client.post(url, self.appointment_order_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Only parents can book appointments', str(response.data))

        # Reset authentication
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

    def test_child_ownership_validation(self):
        """Test that parents can only book for their own children"""
        # Create another parent with a child
        other_parent_user = User.objects.create_user(
            email='other.parent@example.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        other_parent  = Parent.objects.get(user=other_parent_user)
        other_child = Child.objects.create(
            parent=other_parent,
            first_name='Other',
            last_name='Child',
            date_of_birth='2016-01-01',
            gender='Female'
        )

        # Try to book appointment for other parent's child
        self.appointment_order_data['child_id'] = str(other_child.id)

        url = reverse('orders-create-appointment-order-with-reservation')
        response = self.client.post(url, self.appointment_order_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('only book appointments for your own children', str(response.data))

    def test_psychologist_service_validation(self):
        """Test that psychologist must offer the requested service type"""
        # Create psychologist who only offers online sessions
        online_only_psychologist_user = User.objects.create_user(
            email='online.only@example.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        online_only_psychologist = Psychologist.objects.create(
            user=online_only_psychologist_user,
            first_name='Dr. Online',
            last_name='Only',
            license_number='PSY999999',
            license_issuing_authority='State Board',
            license_expiry_date='2025-12-31',
            years_of_experience=3,
            offers_online_sessions=True,
            offers_initial_consultation=False,  # Does NOT offer consultations
            verification_status='Approved'
        )

        # Try to book initial consultation with online-only psychologist
        self.appointment_order_data['psychologist_id'] = str(online_only_psychologist_user.id)
        self.appointment_order_data['session_type'] = 'InitialConsultation'

        url = reverse('orders-create-appointment-order-with-reservation')
        response = self.client.post(url, self.appointment_order_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('does not offer initial consultations', str(response.data))

    def test_slot_availability_validation(self):
        """Test that slots must be available for booking"""
        # Book the slot first
        self.slots[0].mark_as_booked()

        # Try to book the same slot
        url = reverse('orders-create-appointment-order-with-reservation')
        response = self.client.post(url, self.appointment_order_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Starting slot is already booked', str(response.data))

    def test_marketplace_visibility_validation(self):
        """Test that only marketplace-visible psychologists can be booked"""
        # Create non-approved psychologist
        pending_psychologist_user = User.objects.create_user(
            email='pending@example.com',
            password='testpass123',
            user_type='Psychologist',
            is_verified=True
        )
        pending_psychologist = Psychologist.objects.create(
            user=pending_psychologist_user,
            first_name='Dr. Pending',
            last_name='Approval',
            license_number='PSY777777',
            license_issuing_authority='State Board',
            license_expiry_date='2025-12-31',
            years_of_experience=2,
            offers_online_sessions=True,
            office_address='123 address',
            verification_status='Pending'  # Not approved yet
        )

        self.appointment_order_data['psychologist_id'] = str(pending_psychologist_user.id)

        url = reverse('orders-create-appointment-order-with-reservation')
        response = self.client.post(url, self.appointment_order_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not available for booking', str(response.data))

    def test_reservation_expiry(self):
        """Test that slot reservations expire after timeout"""
        # Create order with expired reservation
        order = OrderService.create_appointment_booking_order_with_reservation(
            user=self.parent_user,
            child=self.child,
            psychologist=self.psychologist,
            session_type='OnlineMeeting',
            start_slot_id=self.slots[2].slot_id,
            parent_notes='Test expiry',
            currency='USD',
            provider_name='stripe'
        )

        # Manually expire the reservation
        reserved_slot = AppointmentSlot.objects.get(slot_id=self.slots[2].slot_id)
        reserved_slot.reserved_until = timezone.now() - timedelta(minutes=1)
        reserved_slot.save()

        # Try to book the same slot with different user
        other_parent_user = User.objects.create_user(
            email='other.parent2@example.com',
            password='testpass123',
            user_type='Parent',
            is_verified=True
        )
        other_parent  = Parent.objects.get(user=other_parent_user)
        other_child = Child.objects.create(
            parent=other_parent,
            first_name='Other2',
            last_name='Child2',
            date_of_birth='2017-01-01',
            gender='Male'
        )

        other_token = Token.objects.create(user=other_parent_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {other_token.key}')

        other_order_data = {
            'psychologist_id': str(self.psychologist_user.id),
            'child_id': str(other_child.id),
            'session_type': 'OnlineMeeting',
            'start_slot_id': self.slots[2].slot_id,
            'parent_notes': 'Should work after expiry',
            'currency': 'USD',
            'provider': 'stripe'
        }

        with patch('payments.providers.stripe_provider.stripe.PaymentIntent.create'):
            url = reverse('orders-create-appointment-order-with-reservation')
            response = self.client.post(url, other_order_data, format='json')

            # Should succeed because previous reservation expired
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_consecutive_slots_validation_for_consultation(self):
        """Test that initial consultations require 2 consecutive available slots"""
        # Book the second slot (10 AM), breaking consecutive availability
        self.slots[1].mark_as_booked()
        # Try to book initial consultation starting at 9 AM (needs 9-10 and 10-11)
        self.appointment_order_data['session_type'] = 'InitialConsultation'
        url = reverse('orders-create-appointment-order-with-reservation')
        response = self.client.post(url, self.appointment_order_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Updated assertion to match the actual error message format
        self.assertIn('Consecutive slot', str(response.data))

    # def test_payment_failure_releases_reservation(self):
    #     """Test that payment failure releases slot reservations"""
    #     with patch('payments.providers.stripe_provider.stripe.PaymentIntent.retrieve') as mock_retrieve:
    #         # Create order with reservation
    #         order = OrderService.create_appointment_booking_order_with_reservation(
    #             user=self.parent_user,
    #             child=self.child,
    #             psychologist=self.psychologist,
    #             session_type='OnlineMeeting',
    #             start_slot_id=self.slots[3].slot_id,
    #             parent_notes='Test failure',
    #             currency='USD',
    #             provider_name='stripe'
    #         )

    #         payment = Payment.objects.create(
    #             order=order,
    #             provider_payment_id='pi_test_failed_booking',
    #             amount=order.amount,
    #             currency=order.currency,
    #             payment_method='card'
    #         )

    #         # Mock failed payment intent
    #         mock_payment_intent = MagicMock()
    #         mock_payment_intent.id = 'pi_test_failed_booking'
    #         mock_payment_intent.status = 'requires_payment_method'
    #         mock_payment_intent.amount = 15000
    #         mock_payment_intent.currency = 'usd'
    #         mock_payment_intent.charges.data = []
    #         mock_payment_intent.to_dict_recursive.return_value = {'id': 'pi_test_failed_booking'}
    #         mock_retrieve.return_value = mock_payment_intent

    #         # Confirm payment (should fail)
    #         success = PaymentService.confirm_payment(payment)

    #         self.assertFalse(success)

    #         # Verify payment status
    #         payment.refresh_from_db()
    #         self.assertEqual(payment.status, 'failed')

    #         # Verify slot reservation was released
    #         self.slots[3].refresh_from_db()
    #         self.assertFalse(self.slots[3].is_booked)
    #         self.assertEqual(self.slots[3].reservation_status, 'available')
    #         self.assertIsNone(self.slots[3].reserved_by)

    #         # Verify no appointment was created
    #         appointment_exists = Appointment.objects.filter(
    #             child=self.child,
    #             psychologist=self.psychologist,
    #             parent=self.parent
    #         ).exists()
    #         self.assertFalse(appointment_exists)

    def test_appointment_details_in_order(self):
        """Test that appointment details are properly stored in order metadata"""
        with patch('payments.providers.stripe_provider.stripe.PaymentIntent.create'):
            url = reverse('orders-create-appointment-order-with-reservation')
            response = self.client.post(url, self.appointment_order_data, format='json')
            print(response.data)
            order = Order.objects.get(order_id=response.data['order']['order_id'])

            # Verify metadata contains all necessary appointment details
            metadata = order.metadata
            self.assertEqual(metadata['child_id'], str(self.child.id))
            self.assertEqual(metadata['child_name'], self.child.display_name)
            self.assertEqual(metadata['psychologist_id'], str(self.psychologist.user.id))
            self.assertEqual(metadata['psychologist_name'], self.psychologist.full_name)
            self.assertEqual(metadata['session_type'], 'OnlineMeeting')
            self.assertEqual(metadata['parent_notes'], 'Looking forward to the session')
            self.assertIn('reserved_slot_ids', metadata)
            self.assertEqual(len(metadata['reserved_slot_ids']), 1)

    def test_multiple_appointments_same_parent(self):
        """Test that a parent can book multiple appointments"""
        # Book first appointment
        with patch('payments.providers.stripe_provider.stripe.PaymentIntent.create'):
            url = reverse('orders-create-appointment-order-with-reservation')
            response1 = self.client.post(url, self.appointment_order_data, format='json')
            self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

            # Book second appointment with different slot
            self.appointment_order_data['start_slot_id'] = self.slots[4].slot_id
            response2 = self.client.post(url, self.appointment_order_data, format='json')
            self.assertEqual(response2.status_code, status.HTTP_201_CREATED)

            # Verify both orders exist
            orders = Order.objects.filter(
                user=self.parent_user,
                order_type='appointment_booking'
            )
            self.assertEqual(orders.count(), 2)

    def tearDown(self):
        """Clean up test data"""
        # Clear all test data
        Transaction.objects.all().delete()
        Payment.objects.all().delete()
        Order.objects.all().delete()
        Appointment.objects.all().delete()
        AppointmentSlot.objects.all().delete()
        PsychologistAvailability.objects.all().delete()
        Child.objects.all().delete()
        Parent.objects.all().delete()
        Psychologist.objects.all().delete()
        User.objects.all().delete()
