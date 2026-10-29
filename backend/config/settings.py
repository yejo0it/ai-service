import os
import sys
from pathlib import Path

from corsheaders.defaults import default_headers
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
# 여행 사진: /media/처럼 공개하지 않고 로그인한 여행 참여자에게만 API로 내려 준다(trips.storage).
PRIVATE_MEDIA_ROOT = Path(os.environ.get("PRIVATE_MEDIA_ROOT", BASE_DIR / "private_media"))

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
    # 토큰은 비활동 7일·로그인 후 30일에 만료된다(accounts.authentication, 아래 AUTH_* 설정).
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "accounts.authentication.ExpiringTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # 인증 API(accounts.views.AuthAPIView)·이메일 변경의 요청 제한(ScopedRateThrottle),
    # AI와 함께 만들기(모델 호출)의 사용자당 요청 제한: 1분 10회, 최근 24시간 100회
    "DEFAULT_THROTTLE_RATES": {"auth": "30/min", "sms": "10/hour", "email": "10/hour", "ai_minute": "10/min", "ai_day": "100/day", "legs": "120/hour", "place_photo": "300/hour", "reservation_hour": "10/hour", "reservation_day": "30/day", "reservation_validate": "300/hour"},
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

# 로그인 만료 정책(서버 시계 기준). 비활동: 마지막 사용자 활동 후 N일, 절대: 로그인 후 N일(활동해도 연장 안 됨).
AUTH_INACTIVITY_DAYS = int(os.environ.get("AUTH_INACTIVITY_DAYS", "7"))
AUTH_ABSOLUTE_DAYS = int(os.environ.get("AUTH_ABSOLUTE_DAYS", "30"))
# 사용자 활동 시각을 DB에 쓰는 최소 간격(초). 활동이 잦아도 이 간격마다 한 번만 쓴다.
AUTH_ACTIVITY_WRITE_SECONDS = int(os.environ.get("AUTH_ACTIVITY_WRITE_SECONDS", "60"))

# AI 일정 제안의 실제 이동 시간 계산(Google Routes API, trips.routes). 키는 환경변수 GOOGLE_ROUTES_API_KEY.
# 비용은 요소(출발지×도착지 쌍) 수로 제한한다: 제안 한 번 / 사용자별 하루 / 전체 하루.
# 테스트 실행 중에는 실제 Google·NAVITIME 호출을 막는다(키가 환경에 있어도 요금이 나가지 않도록). 테스트는 호출 함수를 모킹한다.
TESTING = "test" in sys.argv
ROUTES_ENABLED = os.environ.get("ROUTES_ENABLED", "1") == "1"
# 지원 지역: 나라 코드(ISO) 목록 + 따로 더할 도시 id 목록. 기본은 동아시아(일본·한국·대만·홍콩·마카오·몽골)이고 점차 넓힌다.
# 일본은 NAVITIME, 그 밖의 나라는 Google 대중교통 결과를 쓴다(중국 본토는 Google이 대중교통 경로를 주지 않아 기본에서 뺐다).
ROUTES_COUNTRIES = [c.strip().upper() for c in os.environ.get("ROUTES_COUNTRIES", "JP,KR,TW,HK,MO,MN").split(",") if c.strip()]
ROUTES_CITIES = [c.strip() for c in os.environ.get("ROUTES_CITIES", "").split(",") if c.strip()]
ROUTES_CITY_RADIUS_KM = int(os.environ.get("ROUTES_CITY_RADIUS_KM", "80"))
ROUTES_TIMEZONE = os.environ.get("ROUTES_TIMEZONE", "Asia/Tokyo")
ROUTES_MAX_FUTURE_DAYS = int(os.environ.get("ROUTES_MAX_FUTURE_DAYS", "14"))
ROUTES_MAX_ELEMENTS_PER_PROPOSAL = int(os.environ.get("ROUTES_MAX_ELEMENTS_PER_PROPOSAL", "300"))
ROUTES_USER_DAILY_ELEMENTS = int(os.environ.get("ROUTES_USER_DAILY_ELEMENTS", "600"))
ROUTES_DAILY_ELEMENTS = int(os.environ.get("ROUTES_DAILY_ELEMENTS", "3000"))
# 일본 대중교통 이동 시간(NAVITIME Route, RapidAPI, trips.transit). 키는 환경변수 NAVITIME_RAPIDAPI_KEY.
# 무료 요금제는 월 500건 하드 리밋이라, 제안 한 번의 호출 수와 월 호출 수를 제한하고 남은 횟수가 적으면 호출을 멈춘다.
NAVITIME_ENABLED = os.environ.get("NAVITIME_ENABLED", "1") == "1"
NAVITIME_MAX_REQUESTS_PER_PROPOSAL = int(os.environ.get("NAVITIME_MAX_REQUESTS_PER_PROPOSAL", "30"))
NAVITIME_MONTHLY_REQUESTS = int(os.environ.get("NAVITIME_MONTHLY_REQUESTS", "450"))
NAVITIME_RESERVE = int(os.environ.get("NAVITIME_RESERVE", "20"))
NAVITIME_TIMEOUT_SECONDS = int(os.environ.get("NAVITIME_TIMEOUT_SECONDS", "8"))
# 한국어 역 이름 데이터(data/station_names_ja_ko.json, Wikidata) 사용 여부. 기본은 켬(0으로 끌 수 있다).
STATION_NAMES_ENABLED = os.environ.get("STATION_NAMES_ENABLED", "1") == "1"
# 한국어로 바꾸지 못한 역·노선 이름 수집(trips.untranslated). 사전을 보완할 때 `python manage.py untranslated_names`로 본다.
UNTRANSLATED_LOG_ENABLED = os.environ.get("UNTRANSLATED_LOG_ENABLED", "1") == "1"
UNTRANSLATED_LOG_PATH = os.environ.get("UNTRANSLATED_LOG_PATH", str(BASE_DIR / "logs" / "untranslated_names.jsonl"))
# 'AI와 함께 만들기' 토큰 사용량·응답 시간 기록(trips.ai_usage). 한 줄에 JSON 하나로 표준 출력(docker compose logs backend)에 남긴다.
# 숫자·모델명·결과 종류만 남기고 대화·여행 정보·id는 남기지 않는다. 0으로 끌 수 있고, 테스트 실행 중에는 출력하지 않는다.
AI_USAGE_LOG_ENABLED = os.environ.get("AI_USAGE_LOG_ENABLED", "1") == "1"
# 서버 로그. 모두 컨테이너 표준 출력·오류로 내보내고 `docker compose logs backend`로 본다(파일로 쌓지 않는다).
# - 앱 로거(accounts·trips·guides): DJANGO_LOG_LEVEL 이상(기본 INFO). 형식은 "시각 수준 로거: 메시지"
# - Django(django.request의 4xx 경고·5xx 오류와 traceback 등): 개발·운영 모두 남긴다(기본 설정은 운영에서 출력하지 않았다).
# - 그 밖의 라이브러리(httpx·anthropic 등): WARNING 이상만 남겨 호출마다 찍히는 INFO 로그를 막는다.
# - 정상 헬스체크(/api/v1/health/) 요청 줄은 15초마다 쌓이지 않게 뺀다(config.health).
# - 요청 줄(django.server)은 기존 형식 그대로 두고, AI 사용량(JSON 한 줄)·번역 못 한 이름(파일)은 각자 출력해
#   일반 로그에 중복으로 찍히지 않는다(propagate=False).
# - 일반 로그·요청 줄은 출력 전체(메시지·traceback·stack_info)에서 비밀 값·개인정보를 가린다(config.log_masking).
#   각 모듈도 개인정보·대화·키를 직접 기록하지 않는다.
# - 테스트 실행 중에는 일반 로그를 출력하지 않는다(assertLogs로 확인하는 테스트는 그대로 동작한다).
LOG_LEVEL = os.environ.get("DJANGO_LOG_LEVEL", "INFO").strip().upper()
if LOG_LEVEL not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
    raise ImproperlyConfigured("DJANGO_LOG_LEVEL은 DEBUG·INFO·WARNING·ERROR·CRITICAL 중 하나로 설정해 주세요.")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"quiet_health_check": {"()": "config.health.QuietHealthCheckFilter"}},
    "formatters": {
        "standard": {
            "()": "config.log_masking.MaskingFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
        },
        "message": {"format": "%(message)s"},
        "django.server": {"()": "config.log_masking.MaskingServerFormatter", "format": "[{server_time}] {message}", "style": "{"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": "CRITICAL" if TESTING else "DEBUG",
        },
        "django.server": {"class": "logging.StreamHandler", "formatter": "django.server", "filters": ["quiet_health_check"]},
        "ai_usage": {"class": "logging.StreamHandler", "stream": "ext://sys.stdout", "formatter": "message"},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "accounts": {"level": LOG_LEVEL},
        "trips": {"level": LOG_LEVEL},
        "guides": {"level": LOG_LEVEL},
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.server": {"handlers": ["django.server"], "level": "INFO", "propagate": False},
        "pinroute.ai_usage": {
            "handlers": ["ai_usage"],
            "level": "INFO" if AI_USAGE_LOG_ENABLED and not TESTING else "WARNING",
            "propagate": False,
        },
    },
}
# Google 데이터는 DB에 저장하지 않고 이 시간 동안만 서버 메모리 캐시에 둔다(초).
ROUTES_CACHE_TTL_SECONDS = int(os.environ.get("ROUTES_CACHE_TTL_SECONDS", str(6 * 60 * 60)))
ROUTES_TIMEOUT_SECONDS = int(os.environ.get("ROUTES_TIMEOUT_SECONDS", "8"))

# 브라우저 Origin 기준. Docker compose에서는 http://localhost:8002 가 주입된다.
# 프런트가 사용자 조작 직후의 요청에 붙이는 헤더(accounts.authentication.ACTIVITY_HEADER)를 허용한다.
CORS_ALLOW_HEADERS = (*default_headers, "x-user-activity")
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:8002,http://127.0.0.1:8002",
).split(",")

# 여행 경로 장소 사진(Google Place Photos, trips.place_photos). 사진 파일 요청은 월 1,000건까지 무료이고 이후 과금되므로,
# 무료 한도보다 낮은 상한에 닿으면 사진을 더 받지 않고 아이콘으로 대신한다. 0이면 사진 기능을 끈다.
PLACE_PHOTO_MONTHLY_LIMIT = int(os.environ.get("PLACE_PHOTO_MONTHLY_LIMIT", "900"))

# 예약 확인서(항공권·숙소) 분석(trips.reservations). 운영에서는 기본 꺼짐(2단계 여행 자동 생성과 함께 열 때 1로 켠다).
RESERVATION_ANALYSIS_ENABLED = os.environ.get("RESERVATION_ANALYSIS_ENABLED", "0") == "1"
# 예약 확인서(최대 10MB)가 임시 파일 없이 메모리에서만 처리되도록 업로드 파일을 이 크기까지 메모리에 둔다.
FILE_UPLOAD_MAX_MEMORY_SIZE = 11 * 1024 * 1024
