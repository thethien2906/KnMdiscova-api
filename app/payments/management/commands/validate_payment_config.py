from django.core.management.base import BaseCommand
from django.conf import settings
import os


class Command(BaseCommand):
    help = 'Validate payment provider configuration'

    def handle(self, *args, **options):
        self.stdout.write("Validating payment configuration...")

        # Check if payments app is installed
        if 'payments' not in settings.INSTALLED_APPS:
            self.stdout.write(
                self.style.ERROR("❌ Payments app not in INSTALLED_APPS")
            )
            return

        self.stdout.write(
            self.style.SUCCESS("✅ Payments app properly installed")
        )

        # Check payment providers configuration
        if hasattr(settings, 'PAYMENT_PROVIDERS'):
            stripe_config = settings.PAYMENT_PROVIDERS.get('STRIPE', {})
            if stripe_config.get('ENABLED'):
                if stripe_config.get('PUBLISHABLE_KEY') and stripe_config.get('SECRET_KEY'):
                    self.stdout.write(
                        self.style.SUCCESS("✅ Stripe configuration looks good")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING("⚠️  Stripe enabled but missing keys")
                    )
            else:
                self.stdout.write(
                    self.style.WARNING("⚠️  Stripe is disabled")
                )
        else:
            self.stdout.write(
                self.style.ERROR("❌ PAYMENT_PROVIDERS not configured")
            )

        # Check payment amounts
        if hasattr(settings, 'PAYMENT_AMOUNTS'):
            self.stdout.write(
                self.style.SUCCESS("✅ Payment amounts configured")
            )
            for service, amounts in settings.PAYMENT_AMOUNTS.items():
                self.stdout.write(f"   {service}: {amounts}")
        else:
            self.stdout.write(
                self.style.ERROR("❌ PAYMENT_AMOUNTS not configured")
            )

        self.stdout.write(
            self.style.SUCCESS("Payment configuration validation complete!")
        )