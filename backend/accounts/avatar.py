"""
프로필 사진 처리.

업로드한 이미지를 그대로 저장하지 않고 Pillow로 다시 그려 저장한다.
- 이미지가 아닌 파일·너무 큰 파일을 거절한다.
- EXIF 방향을 반영한 뒤 가운데를 정사각형으로 잘라 AVATAR_SIZE로 줄인다.
- JPEG로 다시 저장해 EXIF(촬영 위치 등) 메타데이터를 남기지 않는다.
"""

from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
AVATAR_SIZE = 512


class AvatarError(Exception):
    pass


def make_avatar(upload):
    """업로드 파일을 프로필 사진(JPEG)으로 만든다. 쓸 수 없는 파일이면 AvatarError."""
    if upload.size > MAX_UPLOAD_BYTES:
        raise AvatarError("사진은 5MB 이하로 올려 주세요.")
    try:
        image = Image.open(upload)
        if image.format not in ALLOWED_FORMATS:
            raise AvatarError("JPG, PNG, WEBP, GIF 사진만 올릴 수 있어요.")
        image = ImageOps.exif_transpose(image)
        image = ImageOps.fit(image.convert("RGB"), (AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise AvatarError("사진 파일을 읽을 수 없어요. 다른 사진을 골라 주세요.") from exc

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85, optimize=True)
    return ContentFile(buffer.getvalue(), name="avatar.jpg")
