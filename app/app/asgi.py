"""
ASGI config for app project.
"""
# app/asgi.py
import os
from django.core.asgi import get_asgi_application

# Check if DJANGO_SETTINGS_MODULE is already set in environment
# If not, default to production for web server
if 'DJANGO_SETTINGS_MODULE' not in os.environ:
    os.environ['DJANGO_SETTINGS_MODULE'] = 'app.settings.production'

application = get_asgi_application()