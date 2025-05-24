from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings

class Command(BaseCommand):
    help = 'Test email configuration'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='Email address to send test to')

    def handle(self, *args, **options):
        try:
            send_mail(
                'Test Email from K&Mdiscova',
                'This is a test email to verify your email configuration is working correctly.',
                settings.DEFAULT_FROM_EMAIL,
                [options['email']],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS(f'Test email sent to {options["email"]}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error sending email: {str(e)}'))