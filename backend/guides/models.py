"""
여행 정보 검색(RAG) 코퍼스 (Issue #49 PoC).

GuideDocument: 외부 여행 정보 문서 한 편(출처·라이선스·여행지)
GuideChunk: 문서를 나눈 조각과 임베딩 벡터. 검색은 여행지(country·city_id)로 좁힌 뒤 벡터·키워드로 한다.
"""

from django.db import models
from pgvector.django import HnswIndex, VectorField

# 임베딩 차원은 settings.GUIDES_EMBEDDING_MODEL(guides/embeddings.py)과 같아야 한다.
EMBEDDING_DIMENSIONS = 384


class GuideDocument(models.Model):
    class Source(models.TextChoices):
        WIKIVOYAGE = "wikivoyage", "Wikivoyage"

    source = models.CharField("출처", max_length=20, choices=Source.choices)
    title = models.CharField("문서 제목", max_length=200)
    # 나라 문서는 city_id가 비어 있다.
    country = models.CharField("국가 코드", max_length=2, db_index=True)
    city_id = models.CharField("도시 id", max_length=50, blank=True, default="", db_index=True)
    url = models.URLField("원문 주소", max_length=500)
    license = models.CharField("라이선스", max_length=50)
    revision_id = models.BigIntegerField("원문 판 번호")
    embedding_model = models.CharField("임베딩 모델", max_length=100)
    fetched_at = models.DateTimeField("수집 시각")

    class Meta:
        verbose_name = "여행 정보 문서"
        verbose_name_plural = "여행 정보 문서"
        constraints = [models.UniqueConstraint(fields=("source", "title"), name="guide_document_unique")]

    def __str__(self) -> str:
        return f"{self.get_source_display()}: {self.title}"


class GuideChunk(models.Model):
    document = models.ForeignKey(GuideDocument, related_name="chunks", on_delete=models.CASCADE)
    order = models.PositiveIntegerField("순서")
    # 'Get in > By plane'처럼 상위 섹션까지 이어 붙인 경로
    section = models.CharField("섹션", max_length=300)
    content = models.TextField("내용")
    embedding = VectorField("임베딩", dimensions=EMBEDDING_DIMENSIONS)

    class Meta:
        verbose_name = "여행 정보 청크"
        verbose_name_plural = "여행 정보 청크"
        ordering = ("document", "order")
        indexes = [
            # 코사인 거리 근사 최근접 검색
            HnswIndex(
                name="guide_chunk_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]

    def __str__(self) -> str:
        return f"{self.document.title} · {self.section} #{self.order}"
