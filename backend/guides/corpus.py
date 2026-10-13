"""
PoC 코퍼스 범위 (Issue #49).

여행 준비 Q&A에 쓸 Wikivoyage(영문) 문서. 도시 문서는 서비스 도시 id(data/cities.json)에,
나라 문서는 ISO 국가 코드에 연결해 여행지로 검색 범위를 좁힌다.
한국어 Wikivoyage는 아직 인큐베이터 단계라 문서가 없어 영문판을 쓰고, 다국어 임베딩으로 한국어 질문을 검색한다.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GuidePage:
    title: str
    country: str
    # 나라 문서면 빈 문자열
    city_id: str = ""


PAGES = (
    GuidePage("Japan", "JP"),
    GuidePage("Tokyo", "JP", "tokyo"),
    GuidePage("Osaka", "JP", "osaka"),
    GuidePage("Fukuoka", "JP", "fukuoka"),
    GuidePage("Thailand", "TH"),
    GuidePage("Bangkok", "TH", "bangkok"),
    GuidePage("Vietnam", "VN"),
    GuidePage("Da Nang", "VN", "da-nang"),
)

# 여행 준비 Q&A와 관계가 적고 분량이 큰 장소 목록 섹션은 넣지 않는다(장소 추천은 후속 단계).
EXCLUDED_SECTIONS = {"See", "Do", "Sleep", "Districts", "Regions", "Cities", "Other destinations", "Go next"}
