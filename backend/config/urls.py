from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from .health import health

urlpatterns = [
    path("admin/", admin.site.urls),
    # 컨테이너 헬스체크(로그인 불필요, config.health)
    path("api/v1/health/", health, name="health"),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/", include("trips.urls")),
]

# 개발 서버에서만 업로드 파일을 서빙한다 (DEBUG가 아니면 static()은 빈 목록).
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
