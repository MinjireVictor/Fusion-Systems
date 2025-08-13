"""
Django settings for app project.

Updated for new Ubuntu server deployment with HTTP configuration
Server: zoho.fusionsystems.co.ke:8000
"""

from pathlib import Path
from datetime import timedelta

import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-kutm#q4$thg3q&**fn0^9%&8o(^l+ewxrtuho)qoyh8mjpz#yl'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Updated allowed hosts for new server
ALLOWED_HOSTS = [
    'zoho.fusionsystems.co.ke',
    'localhost',
    '127.0.0.1',
    '*'  # Remove this in production
]

# Review Analysis Settings (keeping existing)
REVIEW_ANALYSIS_SETTINGS = {
    'CRON_INTERVAL_MINUTES': int(os.environ.get('REVIEW_CRON_INTERVAL', 5)),
    'MAX_AGE_HOURS': int(os.environ.get('REVIEW_MAX_AGE_HOURS', 24)),
    'BATCH_SIZE': int(os.environ.get('REVIEW_BATCH_SIZE', 50)),
    'MODAL_APP_NAME': os.environ.get('MODAL_APP_NAME', 'hotel-review-analyzer'),
    'MODAL_FUNCTION_NAME': os.environ.get('MODAL_FUNCTION_NAME', 'analyze_reviews_batch'),
    'MODAL_TIMEOUT_SECONDS': int(os.environ.get('MODAL_TIMEOUT', 1800)),
    'MAX_RETRIES': int(os.environ.get('REVIEW_MAX_RETRIES', 3)),
    'RETRY_DELAY_SECONDS': int(os.environ.get('REVIEW_RETRY_DELAY', 60)),
    'ADMIN_EMAIL': os.environ.get('ADMIN_EMAIL', ''),
    'SEND_ERROR_NOTIFICATIONS': os.environ.get('SEND_ERROR_NOTIFICATIONS', 'False').lower() == 'true',
}

# PhoneBridge Settings - UPDATED for new server and Zoho credentials
PHONEBRIDGE_SETTINGS = {
    # NEW Zoho OAuth Configuration (Updated credentials from paste.txt)
    'ZOHO_CLIENT_ID': os.environ.get('ZOHO_CLIENT_ID', '1000.MJGOZDZMF9NJL38KY8XT0TVECIPGOK'),
    'ZOHO_CLIENT_SECRET': os.environ.get('ZOHO_CLIENT_SECRET', '7b18171a976a2529e44e340b9b5149cc39da8261b3'),
    
    # UPDATED redirect URI for HTTP development server
    'ZOHO_REDIRECT_URI': os.environ.get(
        'ZOHO_REDIRECT_URI', 
        'http://zoho.fusionsystems.co.ke:8000/phonebridge/zoho/callback/'
    ),
    
    # OAuth URLs (will be dynamically resolved based on location)
    'ZOHO_AUTH_URL': 'https://accounts.zoho.com/oauth/v2/auth',
    'ZOHO_TOKEN_URL': 'https://accounts.zoho.com/oauth/v2/token',
    'ZOHO_API_BASE': 'https://www.zohoapis.com',
    
    # UPDATED: PhoneBridge specific scopes as per your .env
    'ZOHO_SCOPES': os.environ.get('ZOHO_SCOPES', 'PhoneBridge.call.log,PhoneBridge.zohoone.search'),

    # VitalPBX Configuration (keeping existing but with environment fallbacks)
    'VITALPBX_API_BASE': os.environ.get('VITALPBX_API_BASE', 'https://cc.fusionsystems.co.ke/api'),
    'VITALPBX_API_KEY': os.environ.get('VITALPBX_API_KEY', '36e6b22faea32d0069b1a7bd1da9de82'),
    'VITALPBX_TENANT': os.environ.get('VITALPBX_TENANT', ''),
    
    # VitalPBX Basic Auth (Fallback)
    'VITALPBX_USERNAME': os.environ.get('VITALPBX_USERNAME', 'T5_'),
    'VITALPBX_PASSWORD': os.environ.get('VITALPBX_PASSWORD', 'YwFV4YBaQbnZJq'),
    
    # General Settings
    'CALL_TIMEOUT_SECONDS': int(os.environ.get('CALL_TIMEOUT', 30)),
    'MAX_RETRIES': int(os.environ.get('PHONEBRIDGE_MAX_RETRIES', 3)),

    # Popup Configuration Settings
    'POPUP_ENABLED': os.environ.get('POPUP_ENABLED', 'true').lower() == 'true',
    'POPUP_TIMEOUT_SECONDS': int(os.environ.get('POPUP_TIMEOUT_SECONDS', 10)),
    'CONTACT_LOOKUP_CACHE_TTL': int(os.environ.get('CONTACT_LOOKUP_CACHE_TTL', 300)),
    'MAX_POPUP_RETRIES': int(os.environ.get('MAX_POPUP_RETRIES', 3)),
    'INCLUDE_CALL_HISTORY': os.environ.get('INCLUDE_CALL_HISTORY', 'true').lower() == 'true',
    'INCLUDE_RECENT_NOTES': os.environ.get('INCLUDE_RECENT_NOTES', 'true').lower() == 'true',

    # PhoneBridge API Configuration
    'PHONEBRIDGE_API_URL': os.environ.get('PHONEBRIDGE_API_URL', 'https://www.zohoapis.com/phonebridge/v3'),
    'PHONEBRIDGE_POPUP_ENDPOINT': os.environ.get('PHONEBRIDGE_POPUP_ENDPOINT', '/calls/popup'),
    'PHONEBRIDGE_CONTROL_ENDPOINT': os.environ.get('PHONEBRIDGE_CONTROL_ENDPOINT', '/calls/control'),

    # Performance Settings
    'MAX_CONCURRENT_POPUPS': int(os.environ.get('MAX_CONCURRENT_POPUPS', 50)),
    'POPUP_RETRY_DELAY_SECONDS': int(os.environ.get('POPUP_RETRY_DELAY', 60)),
    'CALL_LOG_RETENTION_DAYS': int(os.environ.get('CALL_LOG_RETENTION_DAYS', 90)),

    # Phone Number Normalization
    'DEFAULT_COUNTRY_CODE': os.environ.get('DEFAULT_COUNTRY_CODE', 'kenya'),
    
    
    # NEW: Development/HTTP specific settings
    'HTTP_DEVELOPMENT_MODE': os.environ.get('DEBUG', 'true').lower() == 'true',
    'SKIP_SSL_VERIFICATION': os.environ.get('SKIP_SSL_VERIFICATION', 'true').lower() == 'true',
    
    # OAuth Migration Settings (from your .env)
    'OAUTH_MIGRATION_ENABLED': os.environ.get('OAUTH_MIGRATION_ENABLED', 'true').lower() == 'true',
    'OAUTH_AUTO_REFRESH': os.environ.get('OAUTH_AUTO_REFRESH', 'true').lower() == 'true',
    'OAUTH_FALLBACK_TO_US': os.environ.get('OAUTH_FALLBACK_TO_US', 'true').lower() == 'true',
    'OAUTH_SERVER_INFO_TIMEOUT': int(os.environ.get('OAUTH_SERVER_INFO_TIMEOUT', 10)),
    'OAUTH_TOKEN_REFRESH_MARGIN_MINUTES': int(os.environ.get('OAUTH_TOKEN_REFRESH_MARGIN_MINUTES', 5)),
}

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'drf_spectacular',
    'core',
    'user',
    'rest_framework.authtoken',
    'recipe',
    'reviews',
    'corsheaders',
    'phonebridge',
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

# UPDATED CORS settings for new server
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001", 
    "http://127.0.0.1:3001",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "zoho.fusionsystems.co.ke",
    "http://zoho.fusionsystems.co.ke:8000",  # NEW: Add your server
    "https://zoho.fusionsystems.co.ke",      # For future HTTPS
]

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding', 
    'accept-language',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-requested-with',
    'cache-control',
    'pragma',
    'x-csrftoken',
    'baggage',
    'sentry-trace',
    'traceparent',
    'tracestate',
    'x-trace-id',
    'x-span-id',
    'x-idt',
    'x-correlation-id',
    'x-request-id',
    'x-session-id',
    'x-tenant-id',
    'x-api-key',
    'x-client-version',
    'xat',
    'x-forwarded-for',
    'x-forwarded-proto',
    'x-real-ip',
    'x-content-type-options',
    'x-frame-options',
]

CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH', 
    'POST',
    'PUT',
]

CORS_EXPOSE_HEADERS = [
    'content-type',
    'x-csrftoken',
    'x-total-count',
    'x-page-count',
]

CORS_PREFLIGHT_MAX_AGE = 86400

ROOT_URLCONF = 'app.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': os.environ.get('DB_HOST'),
        'NAME': os.environ.get('DB_NAME'), 
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASS'),
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

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'core.User'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'reviews.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler', 
            'formatter': 'simple',
        },
    },
    'loggers': {
        'reviews': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
        'phonebridge': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG' if DEBUG else 'INFO',  # More verbose in development
            'propagate': True,
        },
        'phonebridge.oauth': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
}

# Cache settings (using Redis from your .env)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('REDIS_URL', 'redis://redis:6379/1'),
    }
}

# Analytics settings (keeping existing)
ANALYTICS_SETTINGS = {
    'CACHE_TIMEOUT': 300,
    'MAX_DAILY_SNAPSHOTS': 90,
    'MAX_WEEKLY_SNAPSHOTS': 104,
    'MAX_MONTHLY_SNAPSHOTS': 36,
}

# Environment-specific settings
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

if DEBUG:
    # Development settings for HTTP server
    REVIEW_ANALYSIS_SETTINGS['CRON_INTERVAL_MINUTES'] = 5
    ALLOWED_HOSTS = ['*']  # Be more restrictive in production
else:
    # Production settings
    REVIEW_ANALYSIS_SETTINGS['CRON_INTERVAL_MINUTES'] = 1440
    ALLOWED_HOSTS = ['zoho.fusionsystems.co.ke', 'fusionsystems.co.ke']