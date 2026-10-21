"""
여행 경비의 다중 통화 계산.

- 환율은 홈 환율 위젯과 같은 서비스(ExchangeRate-API, 6시간 캐시)를 쓴다(trips.travel_info).
- 지출을 등록할 때 그때의 환율(1원당 현지 통화 금액)과 원화 환산 금액을 지출에 저장한다.
  이후에는 저장한 값만 쓰므로 환율이 바뀌거나 환율 서비스가 멈춰도 기존 내역은 그대로 조회된다.
- 금액 계산은 Decimal로만 하고, 원화 환산은 원 단위로 반올림(0.5원 이상 올림)한다.
"""

from decimal import ROUND_HALF_UP, Decimal

from . import reference_data, travel_info

KRW = "KRW"
# 소수점 단위를 쓰지 않는 통화(그 밖의 통화는 소수 둘째 자리까지)
ZERO_DECIMAL = {KRW, "JPY", "VND", "IDR", "LAK", "MMK", "MNT", "KZT", "UZS", "HUF", "ISK"}
RATE_PLACES = Decimal("0.000000000001")  # 저장하는 환율의 소수 12자리


def _info():
    return reference_data.load("currencies.json")["currencies"]


def is_supported(currency):
    return currency == KRW or currency in _info()


def decimal_places(currency):
    return 0 if currency in ZERO_DECIMAL else 2


def rate_per_krw(currency):
    """지금 환율(1원당 현지 통화 금액). 환율 서비스를 쓸 수 없으면 TravelInfoError."""
    value = travel_info.krw_rates()["rates"].get(currency)
    if not value:
        raise travel_info.TravelInfoError("환율 정보를 불러오지 못했어요.")
    return Decimal(str(value)).quantize(RATE_PLACES)


def to_krw(amount, rate):
    """현지 통화 금액을 원화 정수로. amount/rate를 원 단위로 반올림한다."""
    return int((Decimal(amount) / Decimal(rate)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def overview(trip_city_codes):
    """지출 입력에서 고를 수 있는 통화 목록: 환율(1원당)과 표시 정보, 이 여행 도시들의 통화 코드."""
    from . import cities

    krw = travel_info.krw_rates()
    trip_currencies = []
    for code in trip_city_codes:
        currency = cities.city_currency(code)
        if currency and currency != KRW and currency in _info() and currency not in trip_currencies:
            trip_currencies.append(currency)
    currencies = [
        {
            "currency": currency,
            "name": info["name"],
            "flag": info["flag"],
            "decimals": decimal_places(currency),
            "per_krw": str(Decimal(str(krw["rates"][currency]))),
        }
        for currency, info in _info().items()
        if krw["rates"].get(currency)
    ]
    return {"trip_currencies": trip_currencies, "currencies": currencies, "updated_at": krw["updated_at"]}
