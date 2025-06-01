"""
Settings package for K&Mdiscova project.

This module automatically loads the appropriate settings based on the
DJANGO_SETTINGS_MODULE environment variable.
"""

import os
from django.core.exceptions import ImproperlyConfigured

# Determine which settings module to use
settings_module = os.environ.get('DJANGO_SETTINGS_MODULE')

if not settings_module:
    # Default to development if not specified
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings.development')

# Optionally, you can import from base to make some settings available at package level
# from .base import *