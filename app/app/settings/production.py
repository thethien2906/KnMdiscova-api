# app/settings/production.py
from .base import *

DEBUG = False

# Parse ALLOWED_HOSTS from environment variable
ALLOWED_HOSTS_ENV = os.environ.get('ALLOWED_HOSTS', '')
if ALLOWED_HOSTS_ENV:
    ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_ENV.split(',') if host.strip()]
else:
    ALLOWED_HOSTS = ['kmdiscova.id.vn', 'www.kmdiscova.id.vn']

# Production database with SSL
DATABASES['default'].update({
    'OPTIONS': {
        'sslmode': os.environ.get('DB_SSL_MODE', 'require'),
    }
})

# Email Configuration for Production
USE_MAILERSEND = os.environ.get('USE_MAILERSEND', 'False') == 'True'

if USE_MAILERSEND:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.environ.get('MAILERSEND_SMTP_HOST', 'smtp.mailersend.net')
    EMAIL_PORT = int(os.environ.get('MAILERSEND_SMTP_PORT', 587))
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = os.environ.get('MAILERSEND_SMTP_USERNAME', '')
    EMAIL_HOST_PASSWORD = os.environ.get('MAILERSEND_API_KEY', '')
    DEFAULT_FROM_EMAIL = os.environ.get('MAILERSEND_SMTP_USERNAME', 'noreply@kmdiscova.id.vn')
else:
    EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
    EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
    EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
    EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
    DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'K&Mdiscova <noreply@kmdiscova.id.vn>')

# Security settings
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'False') == 'True'
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'

# CSRF settings (adjust based on your HTTPS setup)
CSRF_COOKIE_SECURE = os.environ.get('HTTPS_ENABLED', 'False') == 'True'
SESSION_COOKIE_SECURE = os.environ.get('HTTPS_ENABLED', 'False') == 'True'

# CSRF trusted origins
CSRF_TRUSTED_ORIGINS = [
    'http://kmdiscova.id.vn',
    'https://kmdiscova.id.vn',
    'http://www.kmdiscova.id.vn',
    'https://www.kmdiscova.id.vn',
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8081',
    'http://127.0.0.1:8081',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# Add custom trusted origins from environment
CSRF_TRUSTED_ORIGINS_ENV = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
if CSRF_TRUSTED_ORIGINS_ENV:
    CSRF_TRUSTED_ORIGINS.extend([
        origin.strip() for origin in CSRF_TRUSTED_ORIGINS_ENV.split(',') if origin.strip()
    ])

# CORS settings
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    'http://kmdiscova.id.vn',
    'https://kmdiscova.id.vn',
    'http://www.kmdiscova.id.vn',
    'https://www.kmdiscova.id.vn',
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8081',
    'http://127.0.0.1:8081',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# Add custom CORS origins from environment
CORS_ALLOWED_ORIGINS_ENV = os.environ.get('CORS_ALLOWED_ORIGINS', '')
if CORS_ALLOWED_ORIGINS_ENV:
    CORS_ALLOWED_ORIGINS.extend([
        origin.strip() for origin in CORS_ALLOWED_ORIGINS_ENV.split(',') if origin.strip()
    ])

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# Static files
STATIC_ROOT = '/app/staticfiles/'
MEDIA_ROOT = '/app/media/'

# Logging for production
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'users': {
            'handlers': ['console'],
            'level': 'WARNING',  # Less verbose in production
            'propagate': False,
        },
        'parents': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}