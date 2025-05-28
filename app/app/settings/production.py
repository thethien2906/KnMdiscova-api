from .base import *

# Database for production (Aiven)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': os.environ.get('DB_HOST'),
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'OPTIONS': {
            'sslmode': os.environ.get('DB_SSL_MODE', 'require'),
        }
    }
}

# Security settings for production
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# CORS settings
CORS_ALLOWED_ORIGINS = [
    "https://kmdiscova.com",
    "https://www.kmdiscova.com",
]

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = '/var/www/static/'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = '/var/www/media/'