"""
여행지 도시 데이터. 원본은 backend/data/cities.json (프론트 도시 목록도 같은 파일에서 생성한다).

- 도시 키(id)는 서비스 자체 id다(예: "tokyo", "hakone"). IATA 도시 코드가 없는 소도시도 등록할 수 있다.
- 예전에 저장된 IATA 도시 코드(예: "TYO")로 찾아도 같은 도시를 돌려준다.
- 파일은 처음 쓸 때 한 번만 읽어 메모리에 둔다(정적 참조 데이터라 DB 조회가 필요 없다).
  cities.json을 바꾸면 백엔드를 다시 시작해야 반영된다(개발 서버는 .py 변경에만 자동으로 다시 시작한다).
"""

import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings

CITIES_PATH = Path(settings.BASE_DIR) / "data" / "cities.json"

# 나라 -> 현지 통화 (환율 위젯). 캄보디아는 여행 중 달러를 주로 쓰므로 USD로 둔다.
COUNTRY_CURRENCY = {
    "AE": "AED", "AR": "ARS", "AT": "EUR", "AU": "AUD", "BE": "EUR", "BR": "BRL", "CA": "CAD", "CH": "CHF",
    "CN": "CNY", "CZ": "CZK", "DE": "EUR", "DK": "DKK", "EG": "EGP", "ES": "EUR", "FI": "EUR", "FJ": "FJD",
    "FR": "EUR", "GB": "GBP", "GR": "EUR", "GU": "USD", "HK": "HKD", "HR": "EUR", "HU": "HUF", "ID": "IDR",
    "IE": "EUR", "IL": "ILS", "IN": "INR", "IS": "ISK", "IT": "EUR", "JP": "JPY", "KE": "KES", "KH": "USD",
    "KR": "KRW", "KZ": "KZT", "LA": "LAK", "LK": "LKR", "MA": "MAD", "MM": "MMK", "MN": "MNT", "MO": "MOP",
    "MP": "USD", "MV": "MVR", "MX": "MXN", "MY": "MYR", "NL": "EUR", "NO": "NOK", "NP": "NPR", "NZ": "NZD",
    "PE": "PEN", "PH": "PHP", "PL": "PLN", "PT": "EUR", "QA": "QAR", "RU": "RUB", "SE": "SEK", "SG": "SGD",
    "TH": "THB", "TR": "TRY", "TW": "TWD", "US": "USD", "UZ": "UZS", "VN": "VND", "ZA": "ZAR",
}


@lru_cache(maxsize=1)
def _index():
    """{id: 도시}, {IATA 도시 코드: id}"""
    with open(CITIES_PATH, encoding="utf-8") as file:
        cities = json.load(file)
    by_id = {city["id"]: city for city in cities}
    by_iata = {city["iata"]: city["id"] for city in cities if city.get("iata")}
    return by_id, by_iata


def all_cities():
    return list(_index()[0].values())


def get_city(key):
    """도시 id(또는 예전 IATA 도시 코드)로 도시를 찾는다. 없으면 None."""
    key = (key or "").strip()
    if not key:
        return None
    by_id, by_iata = _index()
    return by_id.get(key.lower()) or by_id.get(by_iata.get(key.upper(), ""))


def normalize_key(key):
    """저장할 도시 키: 아는 도시면 id로 맞추고(IATA -> id), 모르는 값은 소문자로만 다듬는다."""
    city = get_city(key)
    return city["id"] if city else (key or "").strip().lower()


def city_center(key):
    """도시 중심 좌표 (lat, lng). 모르는 도시면 None."""
    city = get_city(key)
    return (city["lat"], city["lng"]) if city else None


def city_currency(key):
    city = get_city(key)
    return COUNTRY_CURRENCY.get(city["country"]) if city else None


def trip_center(trip):
    """여행의 첫 여행지 중 좌표를 아는 도시의 중심 (없으면 None)"""
    for dest in trip.destinations or []:
        center = city_center(dest.get("city_code"))
        if center:
            return center
    return None
