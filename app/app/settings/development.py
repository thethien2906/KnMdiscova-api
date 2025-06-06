# app/settings/development.py
from .base import *

# Database for development
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': os.environ.get('DB_HOST', 'db'),
        'NAME': os.environ.get('DB_NAME', 'testdb'),
        'USER': os.environ.get('DB_USER', 'testuser'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'testpass'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# Override database settings if running tests
if 'test' in sys.argv:
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'testdb',
        'USER': 'testuser',
        'PASSWORD': 'testpass',
        'HOST': 'db',
        'PORT': '5432',
    }


# Development-specific settings
CORS_ALLOW_ALL_ORIGINS = True  # Be careful with this in production

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEBUG = os.getenv("DEBUG", "False") == "True"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
