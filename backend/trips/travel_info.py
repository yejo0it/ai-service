"""
홈 위젯용 여행지 정보: 날씨(Open-Meteo)와 환율(ExchangeRate-API open access).

둘 다 API 키가 필요 없는 무료 서비스다. 외부 호출을 줄이려고 결과를 캐시한다.
- 날씨: 도시 중심 좌표(cities.city_center)로 현재 날씨와 16일 일별 예보를 받는다. 30분 캐시.
- 환율: 원화(KRW) 기준 환율을 하루 한 번 갱신하는 서비스라 6시간 캐시한다(실시간 시세가 아니다).
  출처 표기 필요: https://www.exchangerate-api.com
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from django.core.cache import cache

from . import cities, reference_data

TIMEOUT_SECONDS = 5
WEATHER_CACHE_SECONDS = 30 * 60
EXCHANGE_CACHE_SECONDS = 6 * 60 * 60
FORECAST_DAYS = 16  # Open-Meteo 무료 예보 최대 일수


class TravelInfoError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def _get_json(url):
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise TravelInfoError("정보를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.") from exc


def weather(city_code):
    """
    현재 날씨와 일별 예보. weather_code는 WMO 날씨 코드(프론트가 아이콘으로 바꾼다).
    city_code는 도시 id(예전 IATA 도시 코드도 된다).
    """
    code = cities.normalize_key(city_code)
    center = cities.city_center(code)
    if not center:
        raise TravelInfoError("날씨를 지원하지 않는 도시예요.", status_code=404)

    cache_key = f"travel-info:weather:{code}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    latitude, longitude = center
    query = urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "forecast_days": FORECAST_DAYS,
        }
    )
    data = _get_json(f"https://api.open-meteo.com/v1/forecast?{query}")
    current = data.get("current", {})
    daily = data.get("daily", {})
    result = {
        "city_code": code,
        "current": {
            "temperature": current.get("temperature_2m"),
            "weather_code": current.get("weather_code"),
        },
        "daily": [
            {"date": date, "weather_code": weather_code, "max": high, "min": low}
            for date, weather_code, high, low in zip(
                daily.get("time", []),
                daily.get("weather_code", []),
                daily.get("temperature_2m_max", []),
                daily.get("temperature_2m_min", []),
            )
        ],
    }
    cache.set(cache_key, result, WEATHER_CACHE_SECONDS)
    return result


def _krw_rates():
    """1원당 각 통화 금액 {통화: 비율}과 기준 시각."""
    cached = cache.get("travel-info:krw-rates")
    if cached:
        return cached
    data = _get_json("https://open.er-api.com/v6/latest/KRW")
    if data.get("result") != "success":
        raise TravelInfoError("환율 정보를 불러오지 못했어요.")
    result = {"rates": data["rates"], "updated_at": data.get("time_last_update_utc", "")}
    cache.set("travel-info:krw-rates", result, EXCHANGE_CACHE_SECONDS)
    return result


def exchange_rates(city_codes):
    """
    여행 도시들의 현지 통화 환율 목록(중복 통화 제외, 도시 순서 유지).
    국내 도시(원화)와 모르는 도시는 제외한다. krw는 표시 단위(unit)당 원화 금액.
    """
    currencies = []
    for code in city_codes:
        currency = cities.city_currency(code)
        if currency and currency != "KRW" and currency not in currencies:
            currencies.append(currency)
    if not currencies:
        return {"rates": [], "updated_at": ""}

    krw = _krw_rates()
    rates = []
    for currency in currencies:
        per_krw = krw["rates"].get(currency)
        # 통화 표시 정보: 한글 이름, 표시 단위(100이면 은행 고시처럼 100단위), 국기 (backend/data/currencies.json)
        info = reference_data.load("currencies.json")["currencies"][currency]
        name, unit, flag = info["name"], info["unit"], info["flag"]
        if not per_krw:
            continue
        rates.append(
            {
                "currency": currency,
                "name": name,
                "flag": flag,
                "unit": unit,
                "krw": round(unit / per_krw, 2),
            }
        )
    return {"rates": rates, "updated_at": krw["updated_at"]}
