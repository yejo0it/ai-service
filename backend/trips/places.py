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

# 여행지 도시코드(IATA 도시 코드) -> 도시 중심 좌표. 숙소 검색 범위를 제한하는 데 쓴다.
# 목록에 없는 도시는 검색어에 도시명을 붙여 찾는다.
CITY_CENTERS = {
    # 한국
    "SEL": (37.5665, 126.9780), "PUS": (35.1796, 129.0756), "CJU": (33.4996, 126.5312),
    # 일본
    "TYO": (35.6812, 139.7671), "OSA": (34.6937, 135.5023), "NGO": (35.1815, 136.9066),
    "FUK": (33.5902, 130.4017), "SPK": (43.0618, 141.3545), "OKA": (26.2124, 127.6809),
    "SDJ": (38.2682, 140.8694), "HIJ": (34.3853, 132.4553), "KOJ": (31.5966, 130.5571),
    "TAK": (34.3428, 134.0466),
    # 중화권
    "BJS": (39.9042, 116.4074), "SHA": (31.2304, 121.4737), "CAN": (23.1291, 113.2644),
    "TAO": (36.0671, 120.3826), "SIA": (34.3416, 108.9398), "HKG": (22.3193, 114.1694),
    "MFM": (22.1987, 113.5439), "TPE": (25.0330, 121.5654), "KHH": (22.6273, 120.3014),
    # 동남아시아
    "BKK": (13.7563, 100.5018), "CNX": (18.7883, 98.9853), "HKT": (7.8804, 98.3923),
    "SIN": (1.3521, 103.8198), "KUL": (3.1390, 101.6869), "BKI": (5.9804, 116.0735),
    "HAN": (21.0278, 105.8342), "SGN": (10.8231, 106.6297), "DAD": (16.0544, 108.2022),
    "CXR": (12.2388, 109.1967), "PQC": (10.2899, 103.9840), "MNL": (14.5995, 120.9842),
    "CEB": (10.3157, 123.8854), "MPH": (11.9674, 121.9248), "DPS": (-8.6500, 115.2167),
    "JKT": (-6.2088, 106.8456), "PNH": (11.5564, 104.9282), "REP": (13.3671, 103.8448),
    "VTE": (17.9757, 102.6331), "RGN": (16.8409, 96.1735),
    # 남아시아 · 중앙아시아
    "DEL": (28.6139, 77.2090), "BOM": (19.0760, 72.8777), "KTM": (27.7172, 85.3240),
    "CMB": (6.9271, 79.8612), "MLE": (4.1755, 73.5093), "ULN": (47.8864, 106.9057),
    "ALA": (43.2220, 76.8512), "TAS": (41.2995, 69.2401),
    # 중동
    "DXB": (25.2048, 55.2708), "AUH": (24.4539, 54.3773), "DOH": (25.2854, 51.5310),
    "IST": (41.0082, 28.9784), "TLV": (32.0853, 34.7818),
    # 유럽
    "PAR": (48.8566, 2.3522), "LON": (51.5074, -0.1278), "ROM": (41.9028, 12.4964),
    "MIL": (45.4642, 9.1900), "VCE": (45.4408, 12.3155), "FLR": (43.7696, 11.2558),
    "NAP": (40.8518, 14.2681), "BCN": (41.3874, 2.1686), "MAD": (40.4168, -3.7038),
    "LIS": (38.7223, -9.1393), "OPO": (41.1579, -8.6291), "AMS": (52.3676, 4.9041),
    "BRU": (50.8503, 4.3517), "BER": (52.5200, 13.4050), "MUC": (48.1351, 11.5820),
    "FRA": (50.1109, 8.6821), "PRG": (50.0755, 14.4378), "VIE": (48.2082, 16.3738),
    "BUD": (47.4979, 19.0402), "ZRH": (47.3769, 8.5417), "GVA": (46.2044, 6.1432),
    "CPH": (55.6761, 12.5683), "STO": (59.3293, 18.0686), "OSL": (59.9139, 10.7522),
    "HEL": (60.1699, 24.9384), "REK": (64.1466, -21.9426), "DUB": (53.3498, -6.2603),
    "EDI": (55.9533, -3.1883), "ATH": (37.9838, 23.7275), "WAW": (52.2297, 21.0122),
    "ZAG": (45.8150, 15.9819), "DBV": (42.6507, 18.0944), "MOW": (55.7558, 37.6173),
    # 북미
    "NYC": (40.7128, -74.0060), "LAX": (34.0522, -118.2437), "SFO": (37.7749, -122.4194),
    "LAS": (36.1699, -115.1398), "SEA": (47.6062, -122.3321), "CHI": (41.8781, -87.6298),
    "WAS": (38.9072, -77.0369), "BOS": (42.3601, -71.0589), "MIA": (25.7617, -80.1918),
    "ORL": (28.5383, -81.3792), "HNL": (21.3069, -157.8583), "YVR": (49.2827, -123.1207),
    "YTO": (43.6532, -79.3832),
    # 중남미
    "MEX": (19.4326, -99.1332), "CUN": (21.1619, -86.8515), "SAO": (-23.5505, -46.6333),
    "RIO": (-22.9068, -43.1729), "BUE": (-34.6037, -58.3816), "LIM": (-12.0464, -77.0428),
    # 오세아니아 · 태평양
    "SYD": (-33.8688, 151.2093), "MEL": (-37.8136, 144.9631), "BNE": (-27.4698, 153.0251),
    "OOL": (-28.0167, 153.4000), "CNS": (-16.9186, 145.7781), "AKL": (-36.8485, 174.7633),
    "ZQN": (-45.0312, 168.6626), "GUM": (13.4443, 144.7937), "SPN": (15.1850, 145.7467),
    "NAN": (-17.7765, 177.4356),
    # 아프리카
    "CAI": (30.0444, 31.2357), "CPT": (-33.9249, 18.4241), "JNB": (-26.2041, 28.0473),
    "NBO": (-1.2921, 36.8219), "RAK": (31.6295, -7.9811),
}


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
    center = CITY_CENTERS.get(city_code.upper())
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
