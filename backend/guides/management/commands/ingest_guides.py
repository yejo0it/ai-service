"""
`python manage.py ingest_guides` — Wikivoyage 문서를 받아 청크·임베딩해 저장한다 (Issue #49 PoC).

- 문서 판(revision)이 그대로이고 임베딩 모델도 같으면 건너뛴다. `--force`로 모두 다시 만든다.
- 문서 하나씩 트랜잭션으로 바꿔 넣어, 중간에 실패해도 이전 내용이 반쯤 지워진 채 남지 않는다.
"""

import time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from guides import embeddings, wikivoyage
from guides.corpus import EXCLUDED_SECTIONS, PAGES
from guides.models import EMBEDDING_DIMENSIONS, GuideChunk, GuideDocument


def embedding_text(title, section, content):
    """청크만으로는 어느 도시·주제인지 알기 어려워 문서 제목과 섹션 경로를 앞에 붙여 임베딩한다."""
    return f"{title} - {section}\n{content}"


class Command(BaseCommand):
    help = "여행 정보 검색(RAG)용 Wikivoyage 문서를 수집·청크·임베딩해 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="바뀌지 않은 문서도 다시 만듭니다.")

    def handle(self, *args, force=False, **options):
        model = embeddings.current_model()
        if model.dimensions != EMBEDDING_DIMENSIONS:
            raise CommandError(
                f"{model.name}은 {model.dimensions}차원인데 DB 벡터는 {EMBEDDING_DIMENSIONS}차원입니다. "
                "guides.models.EMBEDDING_DIMENSIONS를 맞추고 마이그레이션해 주세요."
            )
        self.stdout.write(f"임베딩 모델: {model.name} ({model.dimensions}차원)")
        total = 0
        for page in PAGES:
            try:
                fetched = wikivoyage.fetch_page(page.title)
            except Exception as exc:  # noqa: BLE001 - 한 문서 실패로 전체를 멈추지 않는다.
                self.stderr.write(f"[건너뜀] {page.title}: {exc}")
                continue

            existing = GuideDocument.objects.filter(source=GuideDocument.Source.WIKIVOYAGE, title=fetched.title).first()
            if (
                existing
                and not force
                and existing.revision_id == fetched.revision_id
                and existing.embedding_model == model.name
            ):
                self.stdout.write(f"[변경 없음] {fetched.title}")
                continue

            chunks = wikivoyage.chunk_page(fetched, EXCLUDED_SECTIONS)
            started = time.time()
            vectors = embeddings.embed_passages(
                [embedding_text(fetched.title, chunk.section, chunk.content) for chunk in chunks], model=model
            )
            with transaction.atomic():
                document, _ = GuideDocument.objects.update_or_create(
                    source=GuideDocument.Source.WIKIVOYAGE,
                    title=fetched.title,
                    defaults={
                        "country": page.country,
                        "city_id": page.city_id,
                        "url": fetched.url,
                        "license": wikivoyage.LICENSE,
                        "revision_id": fetched.revision_id,
                        "embedding_model": model.name,
                        "fetched_at": timezone.now(),
                    },
                )
                document.chunks.all().delete()
                GuideChunk.objects.bulk_create(
                    GuideChunk(document=document, order=index, section=chunk.section, content=chunk.content,
                               embedding=vector)
                    for index, (chunk, vector) in enumerate(zip(chunks, vectors))
                )
            total += len(chunks)
            self.stdout.write(f"[저장] {fetched.title}: 청크 {len(chunks)}개 ({time.time() - started:.1f}초)")

        if not GuideDocument.objects.exists():
            raise CommandError("저장된 문서가 없습니다. 네트워크 연결을 확인해 주세요.")
        self.stdout.write(self.style.SUCCESS(f"완료: 새로 만든 청크 {total}개"))
