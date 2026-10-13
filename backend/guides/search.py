"""
여행 정보 검색 (하이브리드).

1) 여행지로 범위를 좁힌다: 여행 나라의 나라 문서 + 여행 도시의 도시 문서
2) 벡터 검색: 질문 임베딩과 청크 임베딩의 코사인 거리 (pgvector)
3) 키워드 검색: 질문 속 영문·숫자 낱말(예: JR, BTS, Suica)로 PostgreSQL 전문 검색
   - 질문은 한국어, 문서는 영어라 한국어 낱말은 키워드로 맞지 않는다. 고유명사 보강용이다.
4) 두 순위를 RRF(Reciprocal Rank Fusion)로 합친다.

벡터 유사도가 MIN_SIMILARITY보다 낮은 청크는 버린다. 다만 e5-small은 유사도가 좁은 구간(0.73~0.85)에 몰려
정답·오답·일정 요청("스카이트리 넣어 줘")의 점수가 거의 겹친다(PoC 평가). 그래서 하한은 명백히 관계없는 것만 거르는
낮은 값으로 두고, 실제로 근거로 쓸지는 모델이 정해 source_ids로 돌려준다.
"""

import logging
import re
from dataclasses import dataclass

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Q
from pgvector.django import CosineDistance

from trips import cities

from . import embeddings
from .models import GuideChunk

logger = logging.getLogger(__name__)

TOP_K = 5
CANDIDATES = 20
RRF_K = 60
# 코사인 유사도 하한. PoC 평가에서 정답 청크의 최저 유사도(0.751) 바로 아래로 정했다(eval_guides).
MIN_SIMILARITY = 0.75

_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9\-]{1,}")


@dataclass
class GuideHit:
    id: int
    title: str
    section: str
    content: str
    url: str
    license: str
    similarity: float


def trip_scope(trip):
    """여행의 (나라 코드 목록, 도시 id 목록)"""
    city_ids = [dest.get("city_code") for dest in trip.destinations if dest.get("city_code")]
    countries = sorted({(cities.get_city(city_id) or {}).get("country") for city_id in city_ids} - {None})
    return countries, city_ids


def _scoped(countries, city_ids):
    return GuideChunk.objects.filter(
        Q(document__country__in=countries, document__city_id="") | Q(document__city_id__in=city_ids)
    ).select_related("document")


def search(question, countries, city_ids, k=TOP_K, min_similarity=None):
    """
    여행지 범위 안에서 질문과 관련된 청크 상위 k개 (관련 있는 것이 없으면 빈 목록).
    min_similarity: 이보다 유사도가 낮은 청크는 버린다(기본 MIN_SIMILARITY, 평가 때는 0).
    """
    threshold = MIN_SIMILARITY if min_similarity is None else min_similarity
    scoped = _scoped(countries, city_ids)
    if not scoped.exists():
        return []

    query_vector = embeddings.embed_query(question)
    scored = scoped.annotate(distance=CosineDistance("embedding", query_vector))
    by_vector = list(scored.order_by("distance")[:CANDIDATES])

    words = _LATIN_WORD.findall(question)
    by_keyword = []
    if words:
        query = SearchQuery(words[0], config="english")
        for word in words[1:]:
            query |= SearchQuery(word, config="english")
        by_keyword = list(
            scored.annotate(rank=SearchRank(SearchVector("content", config="english"), query))
            .filter(rank__gt=0)
            .order_by("-rank")[:CANDIDATES]
        )

    fused, chunks = {}, {}
    for ranking in (by_vector, by_keyword):
        for position, chunk in enumerate(ranking, 1):
            fused[chunk.id] = fused.get(chunk.id, 0) + 1 / (RRF_K + position)
            chunks[chunk.id] = chunk

    hits = []
    for chunk_id in sorted(fused, key=fused.get, reverse=True):
        chunk = chunks[chunk_id]
        # 키워드로 걸린 청크도 벡터 유사도가 낮으면 질문과 관계없는 것으로 보고 버린다.
        score = 1 - chunk.distance
        if score < threshold:
            continue
        hits.append(
            GuideHit(
                id=chunk.id,
                title=chunk.document.title,
                section=chunk.section,
                content=chunk.content,
                url=chunk.document.url,
                license=chunk.document.license,
                similarity=round(score, 3),
            )
        )
        if len(hits) == k:
            break
    return hits


def search_for_trip(trip, question, k=TOP_K):
    """
    'AI와 함께 만들기'용: 여행지 범위에서 검색한다. 코퍼스가 없거나 검색이 실패해도 대화는 계속되도록
    빈 목록을 돌려준다(근거 없이 기존 방식으로 답한다).
    """
    countries, city_ids = trip_scope(trip)
    if not countries and not city_ids:
        return []
    try:
        return search(question, countries, city_ids, k)
    except Exception:  # noqa: BLE001 - 검색 실패가 일정 대화 전체를 막지 않게 한다.
        logger.exception("여행 정보 검색 실패")
        return []
