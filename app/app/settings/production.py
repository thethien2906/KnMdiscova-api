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

# Security settings - but relaxed for HTTP during development
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'False') == 'True'

# CSRF settings for HTTP access
CSRF_COOKIE_SECURE = False  # Set to True only when you have HTTPS
SESSION_COOKIE_SECURE = False  # Set to True only when you have HTTPS

# Allow CSRF from your domain
CSRF_TRUSTED_ORIGINS = [
    'http://kmdiscova.id.vn',
    'https://kmdiscova.id.vn',
    'http://www.kmdiscova.id.vn',
    'https://www.kmdiscova.id.vn',
    'http://localhost',
    'http://127.0.0.1',
    'http://localhost:8081',
    f'http://{os.environ.get("ALLOWED_HOSTS", "").split(",")[0]}' if os.environ.get("ALLOWED_HOSTS") else '',
]

# Remove empty strings
CSRF_TRUSTED_ORIGINS = [origin for origin in CSRF_TRUSTED_ORIGINS if origin]

# CORS settings for API access
CORS_ALLOW_ALL_ORIGINS = False  # More secure
CORS_ALLOWED_ORIGINS = [
    'http://kmdiscova.id.vn',
    'https://kmdiscova.id.vn',
    'http://www.kmdiscova.id.vn',
    'https://www.kmdiscova.id.vn',
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8081',

]

CORS_ALLOW_CREDENTIALS = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = '/app/staticfiles/'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = '/app/media/'

# Additional security headers for production (but not too strict for HTTP)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'  # Changed from DENY to allow admin