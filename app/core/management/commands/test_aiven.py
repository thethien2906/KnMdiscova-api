from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings

class Command(BaseCommand):
    help = 'Test Aiven PostgreSQL connection'

    def handle(self, *args, **options):
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