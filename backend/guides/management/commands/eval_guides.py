"""
`python manage.py eval_guides` — 여행 정보 검색 품질 평가 (Issue #49 PoC).

1) 검색: 평가 질의 30개(guides/eval_queries.py)로 hit@1·3·5, MRR@10, 질의당 검색 시간을 잰다.
   유사도 하한(MIN_SIMILARITY)을 정할 수 있도록 정답·오답 청크의 유사도 분포도 함께 보여준다.
2) 답변(--answers N): 30개 중 고르게 뽑은 N개 질의를 'AI와 함께 만들기'에 RAG 없이 / RAG로 물어 답변·출처·토큰을 JSON으로 남긴다.
   Claude API를 실제로 호출하므로 비용이 든다. 평가용 여행·회원은 트랜잭션을 되돌려 남기지 않는다.
"""

import json
import statistics
import time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from guides import search
from guides.eval_queries import QUERIES, is_relevant
from trips import ai_planner
from trips.itinerary_views import days_map
from trips.models import Trip


class Command(BaseCommand):
    help = "여행 정보 검색(RAG) 품질을 평가합니다."

    def add_arguments(self, parser):
        parser.add_argument("--answers", type=int, default=0, help="RAG 전·후 답변을 비교할 질의 수 (Claude 호출)")
        parser.add_argument("--output", default="/tmp/guides_eval.json", help="결과 JSON 경로")

    def handle(self, *args, answers=0, output="/tmp/guides_eval.json", **options):
        result = {"retrieval": self.evaluate_retrieval()}
        if answers:
            # 나라·주제가 고르게 섞이도록 일정한 간격으로 뽑는다.
            step = max(1, len(QUERIES) // answers)
            result["answers"] = self.compare_answers(QUERIES[::step][:answers])
        with open(output, "w", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=1)
        self.stdout.write(self.style.SUCCESS(f"결과 저장: {output}"))

    def evaluate_retrieval(self):
        hits = {1: 0, 3: 0, 5: 0}
        reciprocal_ranks, seconds, relevant_scores, other_scores, rows = [], [], [], [], []
        with_threshold = 0
        for query in QUERIES:
            started = time.time()
            # 순위 평가는 하한 없이 상위 10개로 본다.
            ranked = search.search(query.question, [query.country], list(query.city_ids), k=10, min_similarity=0)
            seconds.append(time.time() - started)
            relevant = [is_relevant(query, hit.title, hit.content) for hit in ranked]
            rank = relevant.index(True) + 1 if True in relevant else None
            for k in hits:
                hits[k] += int(rank is not None and rank <= k)
            reciprocal_ranks.append(1 / rank if rank else 0)
            for hit, ok in zip(ranked, relevant):
                (relevant_scores if ok else other_scores).append(hit.similarity)
            # 서비스 기본 하한을 적용했을 때 상위 5개 안에 정답이 남는지
            kept = [ok for hit, ok in zip(ranked[:5], relevant[:5]) if hit.similarity >= search.MIN_SIMILARITY]
            with_threshold += int(any(kept))
            rows.append({"question": query.question, "rank": rank, "top": f"{ranked[0].title} · {ranked[0].section}"
                         if ranked else None, "top_similarity": ranked[0].similarity if ranked else None})
            self.stdout.write(f"{'O' if rank and rank <= 5 else 'X'} rank={rank} | {query.question}")

        n = len(QUERIES)
        summary = {
            "queries": n,
            "hit@1": round(hits[1] / n, 3),
            "hit@3": round(hits[3] / n, 3),
            "hit@5": round(hits[5] / n, 3),
            "mrr@10": round(sum(reciprocal_ranks) / n, 3),
            f"hit@5 (similarity>={search.MIN_SIMILARITY})": round(with_threshold / n, 3),
            "avg_search_ms": round(statistics.mean(seconds[1:] or seconds) * 1000),  # 첫 질의는 모델 로딩 포함
            "relevant_similarity": _distribution(relevant_scores),
            "other_similarity": _distribution(other_scores),
        }
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=1))
        return {"summary": summary, "rows": rows}

    def compare_answers(self, queries):
        rows = []
        with transaction.atomic():
            owner = get_user_model().objects.create_user(username="guides-eval@pinroute.local")
            for query in queries:
                trip = Trip.objects.create(
                    owner=owner, destinations=[{"city": city, "city_code": city} for city in query.city_ids],
                    start_date="2026-11-10", end_date="2026-11-12", itinerary_initialized=True,
                )
                trip.refresh_from_db()
                conversation = [{"role": "user", "content": query.question}]
                days = days_map(trip)
                references = search.search_for_trip(trip, query.question)
                row = {"question": query.question}
                for label, refs in (("without_rag", ()), ("with_rag", references)):
                    started = time.time()
                    plan = ai_planner.propose(trip, sorted(days), days, conversation, None, refs)
                    row[label] = {
                        "reply": plan.reply,
                        "sources": [f"{ref.title} · {ref.section}" for ref in refs if ref.id in set(plan.source_ids)],
                        "seconds": round(time.time() - started, 1),
                    }
                row["retrieved"] = [f"{ref.title} · {ref.section} ({ref.similarity})" for ref in references]
                rows.append(row)
                self.stdout.write(f"답변 비교 완료: {query.question}")
            transaction.set_rollback(True)
        return rows


def _distribution(scores):
    if not scores:
        return None
    ordered = sorted(scores)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "p25": ordered[len(ordered) // 4],
        "median": ordered[len(ordered) // 2],
        "max": ordered[-1],
    }
