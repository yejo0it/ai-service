"""
Google Places API (New) 숙소 검색.

비용을 줄이기 위해
- 자동완성 요청마다 프론트가 만든 session token을 붙이고, 숙소를 고르면
  같은 token으로 Place Details를 1회 호출해 세션을 종료한다(세션 내 자동완성은 무과금).
- X-Goog-FieldMask로 필요한 필드만 받는다. 숙소명(displayName)은 Pro 등급이므로
  Details에서 받지 않고 자동완성 결과의 이름을 쓴다(Details는 Essentials 등급만 사용).
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from . import cities

PLACES_BASE_URL = "https://places.googleapis.com/v1"
AUTOCOMPLETE_FIELDS = ",".join(
    (
        "suggestions.placePrediction.placeId",
        "suggestions.placePrediction.structuredFormat.mainText.text",
        "suggestions.placePrediction.structuredFormat.secondaryText.text",
    )
)
DETAILS_FIELDS = "formattedAddress,location,nationalPhoneNumber"
# locationRestriction의 circle 반경 상한은 50km다.
SEARCH_RADIUS_M = 50_000
TIMEOUT_SECONDS = 5


class PlacesError(Exception):
    """Google Places 호출 실패. status_code는 클라이언트에 돌려줄 HTTP 상태."""

    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def _request(url, field_mask, body=None):
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    if not api_key:
        raise PlacesError("숙소 검색 API 키가 설정되지 않았습니다.", status_code=503)

    headers = {"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": field_mask}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise PlacesError("숙소 정보를 불러오지 못했습니다.") from exc


# 일정 장소 유형 -> Places 장소 유형(includedPrimaryTypes, 최대 5개)
# 관광지는 전망대·거리·시장처럼 유형이 너무 다양해(예: 도쿄타워가 빠진다) 거르지 않는다.
PLACE_TYPES = {
    "hotel": ["lodging"],
    "airport": ["airport"],
    "restaurant": ["restaurant"],
    "cafe": ["cafe", "coffee_shop", "bakery"],
}

# 장소 상세: 주소·좌표 + 전화번호·영업시간 (전화·영업시간은 Enterprise 등급 필드)
PLACE_DETAIL_FIELDS = "displayName,formattedAddress,location,nationalPhoneNumber,regularOpeningHours"
TEXT_SEARCH_FIELDS = ",".join(
    f"places.{field}" for field in PLACE_DETAIL_FIELDS.split(",") + ["id"]
)


def autocomplete_hotels(query, session_token, city="", city_code=""):
    """숙소 자동완성 후보를 [{place_id, name, description}] 형태로 돌려준다."""
    return autocomplete_places(query, session_token, city=city, city_code=city_code, kind="hotel")


def autocomplete_places(query, session_token, city="", city_code="", kind=""):
    """장소 자동완성 후보 [{place_id, name, description}]. kind를 주면 그 유형만 찾는다."""
    body = {
        "input": query,
        "sessionToken": session_token,
        "languageCode": "ko",
    }
    if kind in PLACE_TYPES:
        body["includedPrimaryTypes"] = PLACE_TYPES[kind]
    center = cities.city_center(city_code)
    if center:
        latitude, longitude = center
        body["locationRestriction"] = {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": SEARCH_RADIUS_M,
            }
        }
    elif city:
        body["input"] = f"{query} {city}"

    result = _request(f"{PLACES_BASE_URL}/places:autocomplete", AUTOCOMPLETE_FIELDS, body)
    hotels = []
    for suggestion in result.get("suggestions", []):
        prediction = suggestion.get("placePrediction")
        if not prediction:
            continue
        fmt = prediction.get("structuredFormat", {})
        hotels.append(
            {
                "place_id": prediction["placeId"],
                "name": fmt.get("mainText", {}).get("text", ""),
                "description": fmt.get("secondaryText", {}).get("text", ""),
            }
        )
    return hotels


def hotel_details(place_id, session_token):
    """선택한 숙소의 주소·좌표·전화번호. 같은 session token으로 호출해 세션을 종료한다."""
    query = urllib.parse.urlencode({"sessionToken": session_token, "languageCode": "ko"})
    place = urllib.parse.quote(place_id, safe="")
    result = _request(f"{PLACES_BASE_URL}/places/{place}?{query}", DETAILS_FIELDS)
    location = result.get("location", {})
    return {
        "place_id": place_id,
        "address": result.get("formattedAddress", ""),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "phone": result.get("nationalPhoneNumber", ""),
    }


def _place_summary(place, place_id):
    location = place.get("location", {})
    return {
        "place_id": place_id,
        "name": place.get("displayName", {}).get("text", ""),
        "address": place.get("formattedAddress", ""),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "phone": place.get("nationalPhoneNumber", ""),
        "opening_hours": place.get("regularOpeningHours", {}).get("weekdayDescriptions", []),
    }


def place_details(place_id, session_token=""):
    """일정 카드용 장소 상세: 이름·주소·좌표·전화번호·영업시간(요일별 문장)."""
    params = {"languageCode": "ko"}
    if session_token:
        params["sessionToken"] = session_token
    query = urllib.parse.urlencode(params)
    place = urllib.parse.quote(place_id, safe="")
    result = _request(f"{PLACES_BASE_URL}/places/{place}?{query}", PLACE_DETAIL_FIELDS)
    return _place_summary(result, place_id)


def search_place(text, latitude=None, longitude=None):
    """
    이름으로 장소 하나를 찾는다(AI가 고른 장소를 실제 장소로 확정할 때).
    여행지 좌표가 있으면 그 주변을 우선한다. 찾지 못하면 None.
    """
    body = {"textQuery": text, "languageCode": "ko", "pageSize": 1}
    if latitude is not None and longitude is not None:
        body["locationBias"] = {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": SEARCH_RADIUS_M,
            }
        }
    result = _request(f"{PLACES_BASE_URL}/places:searchText", TEXT_SEARCH_FIELDS, body)
    places = result.get("places", [])
    if not places:
        return None
    return _place_summary(places[0], places[0].get("id", ""))
