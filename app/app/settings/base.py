# app/settings/base.py
from pathlib import Path
import os
import sys
from dotenv import load_dotenv

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