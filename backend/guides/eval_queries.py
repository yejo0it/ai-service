"""
검색 품질 평가용 한국어 질의 30개 (Issue #49).

각 질의는 정답이 들어 있어야 할 문서(pages)와, 정답 청크에 들어 있을 영문 낱말(keywords)을 갖는다.
상위 k개 청크 중 하나라도 '정답 문서의 청크이면서 낱말을 하나 이상(단어 단위로) 포함'하면 적중으로 본다.
검색 범위는 실제 서비스처럼 여행지(country·city_ids)로 좁힌다.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class EvalQuery:
    question: str
    country: str
    city_ids: tuple
    pages: tuple
    keywords: tuple


QUERIES = (
    # 일본
    EvalQuery("일본 여행 갈 때 비자가 필요해?", "JP", ("tokyo",), ("Japan",), ("visa",)),
    EvalQuery("일본 콘센트 전압이랑 플러그 모양 알려줘", "JP", ("tokyo",), ("Japan",), ("volt", "plug")),
    EvalQuery("일본 식당에서 팁 줘야 해?", "JP", ("osaka",), ("Japan",), ("tip", "tipping")),
    EvalQuery("일본에서 젓가락 쓸 때 하면 안 되는 행동", "JP", ("tokyo",), ("Japan",), ("chopstick",)),
    EvalQuery("일본 온천 갈 때 지켜야 할 매너", "JP", ("fukuoka",), ("Japan",), ("onsen", "bath")),
    EvalQuery("일본은 아직 현금을 많이 써? 카드 잘 돼?", "JP", ("osaka",), ("Japan",), ("cash", "credit card")),
    EvalQuery("일본 여행 중에 지진 나면 어떻게 해야 해", "JP", ("tokyo",), ("Japan",), ("earthquake",)),
    EvalQuery("일본 장마철은 언제야?", "JP", ("fukuoka",), ("Japan",), ("rainy season", "tsuyu")),
    EvalQuery("일본에서 유심이나 포켓 와이파이 어떻게 구해?", "JP", ("tokyo",), ("Japan", "Tokyo"), ("SIM", "Wi-Fi", "wifi")),
    EvalQuery("JR 패스 사면 이득이야?", "JP", ("osaka",), ("Japan",), ("Japan Rail Pass", "JR Pass", "Rail Pass")),
    EvalQuery("나리타 공항에서 도쿄 시내 가는 방법", "JP", ("tokyo",), ("Tokyo",), ("Narita",)),
    EvalQuery("도쿄에서 교통카드 스이카 써야 해?", "JP", ("tokyo",), ("Tokyo", "Japan"), ("Suica", "Pasmo", "IC card")),
    EvalQuery("도쿄 지하철 출퇴근 시간에 많이 붐벼?", "JP", ("tokyo",), ("Tokyo",), ("rush hour", "crowded")),
    EvalQuery("간사이 공항에서 오사카 시내까지 어떻게 가?", "JP", ("osaka",), ("Osaka",), ("Kansai", "KIX")),
    EvalQuery("오사카 지하철 1일 패스 같은 거 있어?", "JP", ("osaka",), ("Osaka",), ("Amazing Pass", "day pass", "Enjoy Eco", "1-day")),
    EvalQuery("후쿠오카 공항에서 하카타역 가는 법", "JP", ("fukuoka",), ("Fukuoka",), ("airport",)),
    EvalQuery("후쿠오카에서 부산 가는 배 있어?", "JP", ("fukuoka",), ("Fukuoka",), ("Busan", "ferry")),
    EvalQuery("후쿠오카 포장마차 야타이 문화 알려줘", "JP", ("fukuoka",), ("Fukuoka",), ("yatai",)),
    # 태국
    EvalQuery("한국인은 태국 무비자로 며칠 있을 수 있어?", "TH", ("bangkok",), ("Thailand",), ("visa",)),
    EvalQuery("태국에서 왕실 관련해서 조심할 점", "TH", ("bangkok",), ("Thailand",), ("king", "royal", "monarchy", "lèse-majesté")),
    EvalQuery("방콕 사원 들어갈 때 복장 규정 있어?", "TH", ("bangkok",), ("Thailand", "Bangkok"), ("temple", "dress", "shoulder")),
    EvalQuery("방콕 툭툭 사기 조심하라던데 어떤 거야?", "TH", ("bangkok",), ("Bangkok", "Thailand"), ("tuk-tuk", "tuk tuk", "scam")),
    EvalQuery("수완나품 공항에서 방콕 시내 가는 법", "TH", ("bangkok",), ("Bangkok",), ("Suvarnabhumi", "Airport Rail Link")),
    EvalQuery("방콕 지상철 BTS 타는 방법", "TH", ("bangkok",), ("Bangkok",), ("BTS", "Skytrain")),
    EvalQuery("태국 수돗물 마셔도 돼?", "TH", ("bangkok",), ("Thailand", "Bangkok"), ("tap water", "drinking water", "bottled water")),
    # 베트남
    EvalQuery("베트남 전자비자 필요해?", "VN", ("da-nang",), ("Vietnam",), ("visa", "e-visa")),
    EvalQuery("다낭 공항에서 시내까지 얼마나 걸려?", "VN", ("da-nang",), ("Da Nang",), ("airport",)),
    EvalQuery("다낭에서 그랩 쓸 수 있어?", "VN", ("da-nang",), ("Da Nang", "Vietnam"), ("Grab",)),
    EvalQuery("베트남 동 환전은 어디서 하는 게 좋아?", "VN", ("da-nang",), ("Vietnam", "Da Nang"), ("dong", "exchange")),
    EvalQuery("베트남에서 오토바이 많은 길 건너는 요령", "VN", ("da-nang",), ("Vietnam", "Da Nang"), ("cross", "crossing")),
)


def is_relevant(query, page_title, content):
    """정답 문서의 청크이고 정답 낱말이 단어로 들어 있으면 True (대소문자 무시)."""
    if page_title not in query.pages:
        return False
    return any(re.search(rf"\b{re.escape(keyword)}\b", content, re.IGNORECASE) for keyword in query.keywords)
