from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/", include("trips.urls")),
]

# 개발 서버에서만 업로드 파일을 서빙한다 (DEBUG가 아니면 static()은 빈 목록).
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
