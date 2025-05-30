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

# Override database settings if running tests
if 'test' in sys.argv:
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'testdb',       # Matches POSTGRES_DB in docker-compose.test.yml
        'USER': 'testuser',     # Matches POSTGRES_USER in docker-compose.test.yml
        'PASSWORD': 'testpass', # Matches POSTGRES_PASSWORD in docker-compose.test.yml
        'HOST': 'db',           # This is the service name from docker-compose.test.yml
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