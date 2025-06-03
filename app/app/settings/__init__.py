# app/settings/__init__.py

"""
Django settings module selector

This file determines which settings configuration to use based on
the DJANGO_SETTINGS_MODULE environment variable.
"""

import os

# Default to development if not specified
settings_module = os.environ.get('DJANGO_SETTINGS_MODULE', 'app.settings.development')

if settings_module.endswith('production'):
    from .production import *
elif settings_module.endswith('development'):
    from .development import *
else:
    from .base import *