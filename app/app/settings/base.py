# app/settings/base.py
from pathlib import Path
import os
import sys
from dotenv import load_dotenv
from decimal import Decimal
from celery.schedules import crontab

# Load environment variables
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Security
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    # Only allow empty SECRET_KEY in development/testing
    if 'test' in sys.argv or 'pytest' in sys.modules:
        SECRET_KEY = 'django-insecure-fallback-for-testing'
    elif os.environ.get('DJANGO_SETTINGS_MODULE', '').endswith('development'):
        SECRET_KEY = 'django-insecure-fallback-for-development'
    else:
        raise ValueError("SECRET_KEY environment variable is required")

DEBUG = False  # Always False in base, override in development

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'drf_spectacular',
    'django_extensions',
    'corsheaders',
    # Local apps
    'core',
    'users',
    'parents',
    'children',
    'psychologists',
    'appointments',
    'payments',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'app.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'app' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'app.wsgi.application'

# Database - Base configuration (override in environment-specific files)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': os.environ.get('DB_HOST'),
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20
}

# DRF Spectacular
SPECTACULAR_SETTINGS = {
    'TITLE': 'K&Mdiscova API',
    'DESCRIPTION': 'Personalized Child Development Platform',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# Email Configuration Base
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # Override in production
DEFAULT_FROM_EMAIL = 'K&Mdiscova <noreply@kmdiscova.com>'

# Application-specific settings
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://127.0.0.1:8000')
COMPANY_ADDRESS = os.environ.get('COMPANY_ADDRESS', 'K&Mdiscova - Personalized Child Development Platform')
SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL', 'support@kmdiscova.id.vn')
EMAIL_VERIFICATION_TIMEOUT_DAYS = 3

# MVP Pricing
MVP_PRICING = {
    'ONLINE_SESSION_RATE': 150.00,
    'INITIAL_CONSULTATION_RATE': 280.00
}

# Security defaults (will be overridden in production)
ALLOWED_HOSTS = []
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = []


# Add this after the existing configuration sections

# =============================================================================
# PAYMENT CONFIGURATION
# =============================================================================

# Payment Providers
PAYMENT_PROVIDERS = {
    'STRIPE': {
        'ENABLED': os.environ.get('STRIPE_ENABLED', 'False') == 'True',
        'PUBLISHABLE_KEY': os.environ.get('STRIPE_PUBLISHABLE_KEY', ''),
        'SECRET_KEY': os.environ.get('STRIPE_SECRET_KEY', ''),
        'WEBHOOK_SECRET': os.environ.get('STRIPE_WEBHOOK_SECRET', ''),
        'WEBHOOK_ENDPOINT': '/api/payments/webhooks/stripe/',
    },
    'PAYPAL': {
        'ENABLED': os.environ.get('PAYPAL_ENABLED', 'False') == 'True',
        'CLIENT_ID': os.environ.get('PAYPAL_CLIENT_ID', ''),
        'CLIENT_SECRET': os.environ.get('PAYPAL_CLIENT_SECRET', ''),
        'WEBHOOK_ID': os.environ.get('PAYPAL_WEBHOOK_ID', ''),
        'WEBHOOK_ENDPOINT': '/api/payments/webhooks/paypal/',
        'ENVIRONMENT': os.environ.get('PAYPAL_ENVIRONMENT', 'sandbox'),  # 'sandbox' or 'live'
    }
}

# Payment Configuration
PAYMENT_SETTINGS = {
    'DEFAULT_CURRENCY': 'USD',
    'SUPPORTED_CURRENCIES': ['USD', 'EUR', 'GBP'],
    'ORDER_EXPIRY_MINUTES': int(os.environ.get('PAYMENT_ORDER_EXPIRY_MINUTES', '30')),
    'WEBHOOK_TIMEOUT_SECONDS': int(os.environ.get('PAYMENT_WEBHOOK_TIMEOUT_SECONDS', '30')),
    'MAX_REFUND_DAYS': int(os.environ.get('PAYMENT_MAX_REFUND_DAYS', '30')),
}

# Service Pricing Configuration
PAYMENT_AMOUNTS = {
    'PSYCHOLOGIST_REGISTRATION': {
        'USD': Decimal(os.environ.get('PSYCHOLOGIST_REGISTRATION_FEE_USD', '100.00')),
    },
    'ONLINE_SESSION': {
        'USD': Decimal(os.environ.get('ONLINE_SESSION_FEE_USD', '150.00')),
    },
    'INITIAL_CONSULTATION': {
        'USD': Decimal(os.environ.get('INITIAL_CONSULTATION_FEE_USD', '280.00')),
    },
    'ONLINESESSION': {
        'USD': Decimal(os.environ.get('ONLINE_SESSION_FEE_USD', '150.00')),
    },
    'INITIALCONSULTATION': {
        'USD': Decimal(os.environ.get('INITIAL_CONSULTATION_FEE_USD', '280.00')),
    }

}

# Payment Security
PAYMENT_SECURITY = {
    'REQUIRE_HTTPS_WEBHOOKS': os.environ.get('PAYMENT_REQUIRE_HTTPS_WEBHOOKS', 'True') == 'True',
    'WEBHOOK_IP_WHITELIST': [
        # Stripe webhook IPs will be added in production
        '3.18.12.63', '3.130.192.231', '13.235.14.237', '13.235.122.149',
        '18.211.135.69', '35.154.171.200', '52.15.183.38', '54.187.174.169',
        '54.187.205.235', '54.187.216.72'
    ] if os.environ.get('PAYMENT_REQUIRE_HTTPS_WEBHOOKS', 'True') == 'True' else [],
    'RATE_LIMIT_REQUESTS_PER_MINUTE': int(os.environ.get('PAYMENT_RATE_LIMIT_PER_MINUTE', '60')),
}

# Frontend URLs for payment redirects
PAYMENT_FRONTEND_URLS = {
    'PAYMENT_SUCCESS': f"{FRONTEND_URL}/payment/success",
    'PAYMENT_CANCEL': f"{FRONTEND_URL}/payment/cancel",
    'PAYMENT_ERROR': f"{FRONTEND_URL}/payment/error",
    'PSYCHOLOGIST_DASHBOARD': f"{FRONTEND_URL}/psychologist/dashboard",
    'APPOINTMENT_CONFIRMATION': f"{FRONTEND_URL}/appointments/confirmation",
}

# =============================================================================
# APPOINTMENT SLOT AUTO-GENERATION CONFIGURATION
# =============================================================================

# Enable/disable automatic appointment slot generation
AUTO_GENERATE_APPOINTMENT_SLOTS = os.environ.get('AUTO_GENERATE_APPOINTMENT_SLOTS', 'True') == 'True'

# How many days ahead to generate slots automatically
AUTO_GENERATION_DAYS_AHEAD = int(os.environ.get('AUTO_GENERATION_DAYS_AHEAD', '90'))

# Celery task routing for appointment slots (if using custom routing)
CELERY_TASK_ROUTES = {
    'appointments.tasks.auto_generate_slots_task': {'queue': 'slots'},
    'appointments.tasks.auto_regenerate_slots_task': {'queue': 'slots'},
    # 'appointments.tasks.auto_cleanup_slots_task': {'queue': 'slots'},
}
# Celery scheduler
CELERY_BEAT_SCHEDULE = {
    'cleanup-past-appointment-slots': {
        'task': 'appointments.tasks.auto_cleanup_past_slots_task',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
        'options': {'expires': 3600},  # Task expires in 1 hour if not executed
    },
}


# Google OAuth Configuration
GOOGLE_OAUTH2_CLIENT_ID = os.environ.get('GOOGLE_OAUTH2_CLIENT_ID')
GOOGLE_OAUTH2_CLIENT_SECRET = os.environ.get('GOOGLE_OAUTH2_CLIENT_SECRET')

# Validation for required Google OAuth settings
if not GOOGLE_OAUTH2_CLIENT_ID or not GOOGLE_OAUTH2_CLIENT_SECRET:
    if not ('test' in sys.argv or 'pytest' in sys.modules):
        import warnings
        warnings.warn(
            "Google OAuth credentials not configured. Google authentication will be disabled.",
            UserWarning
        )

# OAuth scopes
GOOGLE_OAUTH2_SCOPES = [
    'openid',
    'email',
    'profile',
]

# Additional OAuth settings
GOOGLE_OAUTH2_USE_DEPRECATED_PYOPENSSL = False


# Facebook OAuth Configuration
FACEBOOK_APP_ID = os.environ.get('FACEBOOK_APP_ID')
FACEBOOK_APP_SECRET = os.environ.get('FACEBOOK_APP_SECRET')

# Validation for required Facebook OAuth settings
if not FACEBOOK_APP_ID or not FACEBOOK_APP_SECRET:
    if not ('test' in sys.argv or 'pytest' in sys.modules):
        import warnings
        warnings.warn(
            "Facebook OAuth credentials not configured. Facebook authentication will be disabled.",
            UserWarning
        )