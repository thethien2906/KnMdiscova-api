from django.core.management.base import BaseCommand
from django.conf import settings
import os


class Command(BaseCommand):
    help = 'Debug Django settings configuration'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== DJANGO SETTINGS DEBUG ==='))

        # Environment variable
        env_setting = os.environ.get('DJANGO_SETTINGS_MODULE', 'Not set')
        self.stdout.write(f"🔧 DJANGO_SETTINGS_MODULE (env): {env_setting}")

        # Django's detected settings module
        self.stdout.write(f"📋 Django settings module: {settings.SETTINGS_MODULE}")

        # Debug mode
        self.stdout.write(f"🛠️  DEBUG: {settings.DEBUG}")

        # Database info
        db_host = settings.DATABASES['default']['HOST']
        db_name = settings.DATABASES['default']['NAME']
        self.stdout.write(f"🗄️  Database: {db_name} @ {db_host}")

        # Allowed hosts
        self.stdout.write(f"🌐 ALLOWED_HOSTS: {settings.ALLOWED_HOSTS}")

        # Static files
        self.stdout.write(f"📁 STATIC_URL: {settings.STATIC_URL}")

        self.stdout.write(self.style.SUCCESS('=== END DEBUG ==='))