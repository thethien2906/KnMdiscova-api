from django.core.management.base import BaseCommand
import paypalrestsdk
from django.conf import settings

class Command(BaseCommand):
    help = 'Test PayPal credentials'

    def handle(self, *args, **kwargs):
        paypalrestsdk.configure({
            "mode": "sandbox",
            "client_id": settings.PAYPAL_CLIENT_ID,
            "client_secret": settings.PAYPAL_CLIENT_SECRET,
        })
        token = paypalrestsdk.api.default().get_access_token()
        self.stdout.write(f"PayPal access token: {token}")
