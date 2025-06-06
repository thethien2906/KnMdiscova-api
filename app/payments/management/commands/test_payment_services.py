from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from decimal import Decimal

from payments.services import PricingService, OrderService, PaymentService
from psychologists.models import Psychologist

User = get_user_model()


class Command(BaseCommand):
    help = 'Test payment services functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-pricing',
            action='store_true',
            help='Test pricing service',
        )
        parser.add_argument(
            '--test-orders',
            action='store_true',
            help='Test order service (requires test psychologist)',
        )
        parser.add_argument(
            '--psychologist-email',
            type=str,
            help='Email of test psychologist for order tests',
        )

    def handle(self, *args, **options):
        self.stdout.write("Testing payment services...")

        if options.get('test_pricing'):
            self._test_pricing_service()

        if options.get('test_orders'):
            psychologist_email = options.get('psychologist_email')
            self._test_order_service(psychologist_email)

    def _test_pricing_service(self):
        """Test pricing service functionality"""
        self.stdout.write(f"\n{'='*50}")
        self.stdout.write("Testing Pricing Service")
        self.stdout.write('='*50)

        try:
            # Test getting individual service prices
            self.stdout.write("Service Prices (USD):")

            services = ['psychologist_registration', 'online_session', 'initial_consultation']
            for service in services:
                try:
                    price = PricingService.get_service_price(service)
                    self.stdout.write(
                        self.style.SUCCESS(f"✅ {service}: ${price}")
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"❌ {service}: Error - {str(e)}")
                    )

            # Test getting all prices
            self.stdout.write("\nAll Service Prices:")
            all_prices = PricingService.get_all_service_prices()
            for service, price in all_prices.items():
                self.stdout.write(f"  {service}: ${price}")

            # Test fee calculation
            self.stdout.write("\nFee Calculation Test:")
            test_amount = Decimal('100.00')
            fees = PricingService.calculate_total_with_fees(test_amount)
            self.stdout.write(f"Base Amount: ${fees['base_amount']}")
            self.stdout.write(f"Provider Fee: ${fees['provider_fee']}")
            self.stdout.write(f"Platform Fee: ${fees['platform_fee']}")
            self.stdout.write(f"Total Amount: ${fees['total_amount']}")

            self.stdout.write(
                self.style.SUCCESS("✅ Pricing service tests completed")
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Pricing service test failed: {str(e)}")
            )

    def _test_order_service(self, psychologist_email=None):
        """Test order service functionality"""
        self.stdout.write(f"\n{'='*50}")
        self.stdout.write("Testing Order Service")
        self.stdout.write('='*50)

        try:
            # Find a test psychologist
            if psychologist_email:
                try:
                    user = User.objects.get(email=psychologist_email)
                    psychologist = Psychologist.objects.get(user=user)
                except (User.DoesNotExist, Psychologist.DoesNotExist):
                    self.stdout.write(
                        self.style.ERROR(f"❌ Psychologist with email {psychologist_email} not found")
                    )
                    return
            else:
                # Try to find any psychologist
                psychologist = Psychologist.objects.first()
                if not psychologist:
                    self.stdout.write(
                        self.style.ERROR("❌ No psychologists found. Create a psychologist first.")
                    )
                    return

            self.stdout.write(f"Using psychologist: {psychologist.full_name} ({psychologist.user.email})")

            # Test creating registration order
            self.stdout.write("\nTesting registration order creation...")
            try:
                registration_order = OrderService.create_psychologist_registration_order(
                    psychologist=psychologist,
                    currency='USD',
                    provider_name='stripe'
                )

                self.stdout.write(
                    self.style.SUCCESS(f"✅ Registration order created: {registration_order.order_id}")
                )
                self.stdout.write(f"   Amount: ${registration_order.amount} {registration_order.currency}")
                self.stdout.write(f"   Status: {registration_order.status}")
                self.stdout.write(f"   Expires: {registration_order.expires_at}")

                # Test retrieving order
                retrieved_order = OrderService.get_order_by_id(str(registration_order.order_id))
                if retrieved_order:
                    self.stdout.write(
                        self.style.SUCCESS("✅ Order retrieval successful")
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR("❌ Order retrieval failed")
                    )

                # Test cancelling order
                if OrderService.cancel_order(registration_order, "Test cancellation"):
                    self.stdout.write(
                        self.style.SUCCESS("✅ Order cancellation successful")
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR("❌ Order cancellation failed")
                    )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Registration order test failed: {str(e)}")
                )

            # Test creating appointment order
            self.stdout.write("\nTesting appointment order creation...")
            try:
                # Create a test parent user if needed
                parent_user, created = User.objects.get_or_create(
                    email='test-parent@example.com',
                    defaults={
                        'user_type': 'Parent',
                        'is_verified': True
                    }
                )

                appointment_order = OrderService.create_appointment_booking_order(
                    user=parent_user,
                    psychologist=psychologist,
                    session_type='online_session',
                    currency='USD',
                    provider_name='stripe'
                )

                self.stdout.write(
                    self.style.SUCCESS(f"✅ Appointment order created: {appointment_order.order_id}")
                )
                self.stdout.write(f"   Amount: ${appointment_order.amount} {appointment_order.currency}")
                self.stdout.write(f"   Status: {appointment_order.status}")
                self.stdout.write(f"   Session Type: online_session")

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Appointment order test failed: {str(e)}")
                )

            self.stdout.write(
                self.style.SUCCESS("✅ Order service tests completed")
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Order service test failed: {str(e)}")
            )

    def _test_payment_initiation(self, order_id=None):
        """Test payment initiation (optional)"""
        if not order_id:
            self.stdout.write("No order ID provided for payment test")
            return

        self.stdout.write(f"\n{'='*50}")
        self.stdout.write("Testing Payment Initiation")
        self.stdout.write('='*50)

        try:
            from payments.models import Order

            order = Order.objects.get(order_id=order_id)

            # Test payment initiation (without actually creating charges)
            self.stdout.write(f"Testing payment initiation for order: {order.order_id}")
            self.stdout.write(f"Amount: ${order.amount} {order.currency}")
            self.stdout.write("Note: This would create a real payment intent with Stripe")

            # Uncomment below to actually test payment initiation
            # WARNING: This will create real payment intents with Stripe
            """
            payment_data = PaymentService.initiate_payment(
                order=order,
                success_url='https://example.com/success',
                cancel_url='https://example.com/cancel'
            )

            self.stdout.write(
                self.style.SUCCESS(f"✅ Payment initiated: {payment_data['payment_id']}")
            )
            self.stdout.write(f"   Payment Intent ID: {payment_data['payment_intent_id']}")
            self.stdout.write(f"   Client Secret: {payment_data['client_secret'][:20]}...")
            """

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Payment initiation test failed: {str(e)}")
            )