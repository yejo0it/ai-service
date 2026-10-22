"""
여행 사진 저장소. 프로필 사진(MEDIA_ROOT, `/media/`로 누구나 볼 수 있음)과 달리, 이 폴더의 파일은 어떤 주소로도
공개하지 않고 로그인한 여행 참여자만 `GET /api/v1/trip-photos/{id}/file/`로 받는다.
"""

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateMediaStorage(FileSystemStorage):
    """PRIVATE_MEDIA_ROOT에 저장하고 URL을 만들지 않는다(settings를 읽을 때마다 쓰므로 테스트에서 바꿀 수 있다)."""

    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None  # 공개 주소 없음: .url을 부르면 오류가 나서 실수로 노출되지 않는다.


def private_storage():
    return PrivateMediaStorage()
