"""
여행 경로 장소 대표 사진(Google Places API New).

비용과 정책
- 사진은 장소마다 두 번 호출한다. ① Place Details(`photos`만): ID 등급이라 무료·무제한 → 그때의 사진 이름.
  ② Place Photos(`/media`): 성공 1건마다 'Place Details Photos' SKU로 과금(월 무료 1,000건, 이후 1,000건당 $7).
- 사진 이름은 만료될 수 있고 캐시할 수 없다고 Google이 정해 두었다. 그래서 사진 이름·주소·이미지는 DB나 서버 캐시에
  저장하지 않고(장소 ID만 저장해 둔다), 요청 때마다 새로 받는다. 브라우저는 응답을 잠깐(1시간) 재사용한다.
- 과금 호출(②)은 월 상한(PLACE_PHOTO_MONTHLY_LIMIT, 기본 무료 한도보다 낮은 900건)을 넘기 전에 막는다.
  상한은 DB에 센다(구글 청구 월과 같은 태평양 시간 기준). 상한이 0이면 사진 기능을 끈다.
- 사진이 없거나 상한을 넘었거나 Google 오류여도 예외를 올리지 않고 '사진 없음'으로 돌려준다(일정 표시에 영향 없음).
- 작성자 표시(authorAttributions)와 Google Maps 원본 링크(googleMapsUri)를 함께 돌려주므로 화면은 사진 옆에 출처를 보여 줘야 한다.
"""

import logging
import re
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from . import places
from .models import PlacePhotoUsage

logger = logging.getLogger(__name__)

BILLING_TIMEZONE = ZoneInfo("America/Los_Angeles")  # Google Maps Platform은 태평양 시간 기준 달력 월로 집계한다.
PHOTO_NAME_PATTERN = re.compile(r"^places/[A-Za-z0-9_-]+/photos/[A-Za-z0-9_-]+$")
PLACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,255}$")

# 결과 상태: ok(사진 있음) / none(사진 없음) / limit(월 상한) / error(Google 오류·키 없음)
OK, NONE, LIMIT, ERROR = "ok", "none", "limit", "error"


def current_month():
    return timezone.now().astimezone(BILLING_TIMEZONE).strftime("%Y-%m")


def monthly_limit():
    return max(0, int(getattr(settings, "PLACE_PHOTO_MONTHLY_LIMIT", 0)))


def used_this_month():
    usage = PlacePhotoUsage.objects.filter(month=current_month()).first()
    return usage.count if usage else 0


def reserve_call():
    """
    과금 호출 한 건을 쓸 수 있으면 이번 달 사용량을 1 올리고 True. 상한이면 False.
    동시에 호출해도 상한을 넘지 않도록 조건부 UPDATE 한 번으로 올린다. 호출이 실패해도 1건으로 센다(보수적으로).
    """
    cap = monthly_limit()
    if cap <= 0:
        return False
    month = current_month()
    PlacePhotoUsage.objects.get_or_create(month=month, defaults={"count": 0})
    return PlacePhotoUsage.objects.filter(month=month, count__lt=cap).update(count=F("count") + 1) == 1


def _safe_https(url):
    return url if urlparse(url or "").scheme == "https" else ""


def _attributions(photo):
    result = []
    for author in photo.get("authorAttributions") or []:
        name = str(author.get("displayName") or "").strip()[:60]
        if name:
            result.append({"name": name, "uri": _safe_https(author.get("uri"))})
    return result[:1]


def result(status, photo_uri=None, attributions=None, maps_uri=""):
    return {"status": status, "photo_uri": photo_uri, "attributions": attributions or [], "maps_uri": maps_uri}


def lookup(place_id):
    """장소 한 곳의 대표 사진 주소와 작성자. 어떤 경우에도 예외를 올리지 않는다."""
    if monthly_limit() <= 0 or used_this_month() >= monthly_limit():
        return result(LIMIT)  # 상한이면 Google을 부르지 않는다(무료인 Details도 부르지 않는다).
    try:
        details = places.place_photo_details(place_id)
        photo = next((p for p in details.get("photos") or [] if PHOTO_NAME_PATTERN.match(str(p.get("name", "")))), None)
        if photo is None:
            return result(NONE)
        if not reserve_call():
            return result(LIMIT)
        photo_uri = _safe_https(places.place_photo_uri(photo["name"]))
        if not photo_uri:
            return result(NONE)
        # 정책: 사진은 Google Maps의 원본(googleMapsUri)으로 연결하고 작성자를 함께 표시한다.
        return result(OK, photo_uri, _attributions(photo), _safe_https(photo.get("googleMapsUri")))
    except places.PlacesError as exc:
        logger.warning("place photo failed for %s: %s", quote(place_id), exc)
        return result(ERROR)
