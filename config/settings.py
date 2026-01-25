import os
from pathlib import Path
from decouple import config

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)  # Default to False for safety
ALLOWED_HOSTS = [h.strip() for h in config('ALLOWED_HOSTS', default='localhost').split(',')]
ENVIRONMENT = config('ENVIRONMENT', default='production')  # Default to production

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'django_filters',
    'storages',  # ← ADD FOR S3
    'apps.accounts',
    'apps.streaming',
    'apps.payments',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Production optimization middleware
    'django.middleware.gzip.GZipMiddleware',  # Compress responses
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'config.wsgi.application'

# ============ DATABASE CONFIGURATION (OPTIMIZED) ============
if ENVIRONMENT == 'production':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='youtubestreamer'),
            'USER': config('DB_USER', default='postgres'),
            'PASSWORD': config('DB_PASSWORD', default='postgres'),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
            'OPTIONS': {
                'sslmode': 'require',
                # Connection pooling reduces overhead
                'connect_timeout': 10,
                'options': '-c default_transaction_isolation=read_committed'
            },
            # Persistent connections for cost-effectiveness
            'CONN_MAX_AGE': 300,  # Keep connections alive for 5 minutes
            'ATOMIC_REQUESTS': False,  # Use selective transactions for performance
        }
    }
else:
    # Development: SQLite
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Database query optimization - auto-explain slow queries
if not DEBUG:
    DATABASE_QUERY_TIMEOUT = 5000  # 5 seconds in milliseconds

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============ AWS S3 STORAGE CONFIGURATION (OPTIMIZED) ============
if ENVIRONMENT == 'production':
    # Production: Use AWS S3 with cost optimization
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='us-east-1')
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com'
    AWS_LOCATION = 'media'
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False
    
    # Optimized S3 settings for cost-effectiveness
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=31536000',  # 1 year caching to reduce transfers
        'ServerSideEncryption': 'AES256',  # Free encryption
    }
    
    # Use S3 Transfer Acceleration (optional, depends on setup)
    AWS_S3_USE_SSL = True
    AWS_S3_VERIFY = True
    
    # Static Files (served from S3)
    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/static/'
    STATIC_ROOT = 'static'
    
    # Media Files (served from S3)
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'
    MEDIA_ROOT = 'media'
    
    # Storage configuration with optimization
    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
            'OPTIONS': {
                'bucket_name': AWS_STORAGE_BUCKET_NAME,
                'region_name': AWS_S3_REGION_NAME,
                'max_memory_size': 5242880,  # 5MB before using disk (default is larger)
            }
        },
        'staticfiles': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
            'OPTIONS': {
                'bucket_name': AWS_STORAGE_BUCKET_NAME,
                'region_name': AWS_S3_REGION_NAME,
            }
        }
    }
else:
    # Development: Local filesystem
    STATIC_URL = '/static/'
    STATICFILES_DIRS = [BASE_DIR / 'static']
    STATIC_ROOT = BASE_DIR / 'staticfiles'
    
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

# ============ CACHE CONFIGURATION (OPTIMIZED FOR PRODUCTION) ============
if ENVIRONMENT == 'production':
    # Production: Redis with aggressive caching
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': config('REDIS_URL', default='redis://localhost:6379/1'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'CONNECTION_POOL_CLASS': 'redis.connection.BlockingConnectionPool',
                'CONNECTION_POOL_CLASS_KWARGS': {
                    'max_connections': 10,
                    'timeout': 20,
                },
                'IGNORE_EXCEPTIONS': True,  # Fail gracefully
                'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
                'PARSER': 'redis.connection.HiredisParser',
            }
        }
    }
else:
    # Development: In-memory cache
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        }
    }

SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
# Cache sessions for 2 weeks
SESSION_COOKIE_AGE = 1209600  # 2 weeks in seconds

# ============ GOOGLE OAUTH SETTINGS ============
GOOGLE_CLIENT_ID = config('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = config('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = config('GOOGLE_REDIRECT_URI')
GOOGLE_SCOPES = [
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/youtube.force-ssl',
]

# ============ RAZORPAY SETTINGS ============
RAZORPAY_KEY_ID = config('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = config('RAZORPAY_KEY_SECRET')

# ============ SUBSCRIPTION PLANS ============
SUBSCRIPTION_PLANS = {
    'oneday': {
        'name': 'One Day Plan',
        'price': 4900.00,
        'duration_days': 1,
        'max_streams': 1,
        'description': '1 concurrent stream, 1 day access'
    },
    'monthly': {
        'name': 'Monthly Plan',
        'price': 49900.00,
        'duration_days': 30,
        'max_streams': 1,
        'description': '1 concurrent stream, 30 days access'
    },
    'annual': {
        'name': 'Annual Plan',
        'price': 399900.00,
        'duration_days': 365,
        'max_streams': 3,
        'description': 'Up to 3 concurrent streams, 365 days access'
    }
}

# ============ CELERY SETTINGS ============
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# ============ FFMPEG SETTINGS ============
FFMPEG_PATH = config('FFMPEG_PATH', default='ffmpeg')

# ============ REST FRAMEWORK SETTINGS ============
REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# ============ AUTH URLS ============
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'
