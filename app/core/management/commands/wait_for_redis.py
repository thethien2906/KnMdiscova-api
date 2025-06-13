# app/core/management/commands/wait_for_redis.py
import time
from django.conf import settings
from django.core.management.base import BaseCommand
from redis.exceptions import ConnectionError
import redis

class Command(BaseCommand):
    """Django command to wait for Redis to be available"""

    def handle(self, *args, **options):
        self.stdout.write('Waiting for Redis...')
        r = redis.Redis(
            host=6379,
            port=6379
        )
        retries = 30
        while retries > 0:
            try:
                r.ping()
                self.stdout.write(self.style.SUCCESS('Redis is available!'))
                return
            except ConnectionError:
                self.stdout.write(f'Redis unavailable, waiting 2 seconds... ({31 - retries}/30)')
                retries -= 1
                time.sleep(2)

        self.stdout.write(self.style.ERROR('Could not connect to Redis!'))
        exit(1) # Exit with a non-zero status code to fail the CI job