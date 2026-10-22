"""
여행 사진 처리.

프로필 사진(accounts.avatar)과 같은 규칙으로 업로드 파일을 그대로 저장하지 않고 Pillow로 다시 그려 저장한다.
- 이미지가 아닌 파일·너무 큰 파일을 거절한다(형식·용량 한도는 프로필 사진과 같다).
- EXIF 방향을 반영한 뒤 JPEG로 다시 저장해 EXIF(촬영 위치 등)를 남기지 않는다.
- 프로필 사진과 달리 자르지 않고, 긴 변이 MAX_SIDE를 넘으면 비율을 유지한 채 줄인다.
"""

from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

from accounts.avatar import ALLOWED_FORMATS, MAX_UPLOAD_BYTES

MAX_SIDE = 1600


class PhotoError(Exception):
    pass


def make_trip_photo(upload):
    """업로드 파일을 여행 사진(JPEG)으로 만든다. (파일, 너비, 높이)를 돌려주고, 쓸 수 없는 파일이면 PhotoError."""
    if upload.size > MAX_UPLOAD_BYTES:
        raise PhotoError("사진은 5MB 이하로 올려 주세요.")
    try:
        image = Image.open(upload)
        if image.format not in ALLOWED_FORMATS:
            raise PhotoError("JPG, PNG, WEBP, GIF 사진만 올릴 수 있어요.")
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)  # 작은 사진은 키우지 않는다.
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise PhotoError("사진 파일을 읽을 수 없어요. 다른 사진을 골라 주세요.") from exc

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85, optimize=True)
    return ContentFile(buffer.getvalue(), name="photo.jpg"), image.width, image.height
