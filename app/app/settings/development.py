# app/settings/development.py
from .base import *

# Database for development
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': os.environ.get('DB_HOST', 'db'),
        'NAME': os.environ.get('DB_NAME', 'devdb'),
        'USER': os.environ.get('DB_USER', 'devuser'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'changeme'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# Development-specific settings
CORS_ALLOW_ALL_ORIGINS = True  # Be careful with this in production

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'