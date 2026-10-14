import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent

# 환경변수가 없으면 끈다(운영에서 에러 화면에 설정·요청 정보가 보이지 않게). 개발 환경은 docker-compose가 1로 켠다.
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

# 비밀번호 재설정·휴대폰 인증 토큰과 세션 서명에 쓴다. 코드·저장소에 고정 값을 두지 않는다.
# - 운영(DEBUG=0): 반드시 환경변수로 넣는다. 없으면 시작하지 않는다.
# - 개발(DEBUG=1): 비어 있으면 실행할 때마다 무작위로 만든다(다시 시작하면 세션·인증 토큰이 무효).
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY 환경변수를 설정해 주세요 (운영 환경에서는 필수).")
    SECRET_KEY = get_random_secret_key()

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,backend").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "accounts",
    "trips",
    "guides",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "pinroute"),
        "USER": os.environ.get("POSTGRES_USER", "pinroute"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "pinroute"),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# 업로드 파일(프로필 사진). 개발 서버(DEBUG)는 Django가 직접 서빙하고, 운영은 웹 서버·스토리지에서 서빙한다.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# 이메일 변경 인증 메일(SMTP). EMAIL_HOST가 비어 있으면 개발(DEBUG)은 콘솔(백엔드 로그)로 보내고,
# 운영은 발송하지 않는다(503).
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "PinRoute <no-reply@pinroute.local>")
if not EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# 여행 정보 검색(RAG, Issue #49)의 다국어 임베딩 모델. 바꾸면 벡터 차원이 달라지므로
# 마이그레이션과 `python manage.py ingest_guides`를 다시 해야 한다(guides/embeddings.py).
GUIDES_EMBEDDING_MODEL = os.environ.get("GUIDES_EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
# 메일 속 링크가 가리키는 프론트 주소
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:8002")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # 프론트는 로그인·가입 응답의 토큰을 `Authorization: Token <key>`로 보낸다.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # 인증 API(accounts.views.AuthAPIView)·이메일 변경의 요청 제한(ScopedRateThrottle),
    # AI와 함께 만들기(모델 호출)의 사용자당 요청 제한: 1분 10회, 최근 24시간 100회
    "DEFAULT_THROTTLE_RATES": {"auth": "30/min", "sms": "10/hour", "email": "10/hour", "ai_minute": "10/min", "ai_day": "100/day"},
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

# 브라우저 Origin 기준. Docker compose에서는 http://localhost:8002 가 주입된다.
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:8002,http://127.0.0.1:8002",
).split(",")
