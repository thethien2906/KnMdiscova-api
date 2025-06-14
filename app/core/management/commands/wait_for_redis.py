# app/core/management/commands/wait_for_redis.py
import time
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand
from redis.exceptions import ConnectionError
import redis

class Command(BaseCommand):
    """Django command to wait for Redis to be available by parsing CELERY_BROKER_URL"""

    def handle(self, *args, **options):
        self.stdout.write('Waiting for Redis...')

        # Parse the broker URL from settings
        broker_url = settings.CELERY_BROKER_URL
        url_parts = urlparse(broker_url)

        if url_parts.scheme != 'redis':
            self.stdout.write(self.style.ERROR('CELERY_BROKER_URL is not a Redis URL.'))
            exit(1)

        # Extract hostname and port
        redis_host = url_parts.hostname
        redis_port = url_parts.port

        r = redis.Redis(host=redis_host, port=redis_port)
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
        exit(1)