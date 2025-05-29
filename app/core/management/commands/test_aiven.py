from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings
import os

class Command(BaseCommand):
    help = 'Test Aiven PostgreSQL connection'

    def handle(self, *args, **options):
        # Debug settings first
        self.stdout.write(self.style.WARNING('=== test_aiven SETTINGS DEBUG ==='))
        self.stdout.write(f"🔧 DJANGO_SETTINGS_MODULE (env): {os.environ.get('DJANGO_SETTINGS_MODULE', 'Not set')}")
        self.stdout.write(f"📋 Django settings module: {settings.SETTINGS_MODULE}")
        self.stdout.write(f"🛠️  DEBUG: {settings.DEBUG}")
        self.stdout.write(f"🗄️  Database host: {settings.DATABASES['default']['HOST']}")
        self.stdout.write(f"🗄️  Database port: {settings.DATABASES['default']['PORT']}")
        self.stdout.write(f"🗄️  Database name: {settings.DATABASES['default']['NAME']}")
        self.stdout.write(f"🗄️  Database user: {settings.DATABASES['default']['USER']}")
        self.stdout.write(f"🗄️  Database options: {settings.DATABASES['default'].get('OPTIONS', {})}")
        self.stdout.write(self.style.WARNING('=== END DEBUG ===\n'))

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT VERSION()")
                version = cursor.fetchone()[0]
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully connected to PostgreSQL: {version}'
                    )
                )

                # Show current database
                cursor.execute("SELECT current_database()")
                db_name = cursor.fetchone()[0]
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Connected to database: {db_name}'
                    )
                )

                # Show connection info
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Host: {settings.DATABASES["default"]["HOST"]}'
                    )
                )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'Database connection failed: {str(e)}'
                )
            )
            # Additional debug info on failure
            import traceback
            self.stdout.write(
                self.style.ERROR(
                    f'Full traceback: {traceback.format_exc()}'
                )
            )