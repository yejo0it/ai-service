"""
다국어 문장 임베딩 (sentence-transformers, CPU).

한국어 질문으로 영문 문서를 찾아야 하므로 다국어 모델만 쓴다. 모델은 처음 쓸 때 한 번 내려받아
(HuggingFace 캐시) 프로세스 안에 두고 재사용한다. 벡터는 길이 1로 정규화해 코사인 유사도로 비교한다.
"""

from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings


@dataclass(frozen=True)
class EmbeddingModel:
    name: str
    dimensions: int
    # E5 계열은 질의·문서 앞에 정해진 접두어를 붙여야 성능이 나온다.
    query_prefix: str = ""
    passage_prefix: str = ""


MODELS = {
    model.name: model
    for model in (
        EmbeddingModel("intfloat/multilingual-e5-small", 384, "query: ", "passage: "),
        EmbeddingModel("intfloat/multilingual-e5-base", 768, "query: ", "passage: "),
        EmbeddingModel("BAAI/bge-m3", 1024),
        EmbeddingModel("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", 384),
    )
}


def current_model():
    """서비스가 쓰는 모델 (settings.GUIDES_EMBEDDING_MODEL). 저장된 벡터와 같은 모델이어야 한다."""
    return MODELS[settings.GUIDES_EMBEDDING_MODEL]


@lru_cache(maxsize=2)
def _load(name):
    # 무거운 라이브러리라 실제로 쓸 때만 불러온다.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(name, device="cpu")


def embed_passages(texts, model=None, batch_size=32):
    model = model or current_model()
    vectors = _load(model.name).encode(
        [model.passage_prefix + text for text in texts],
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [vector.tolist() for vector in vectors]


def embed_query(text, model=None):
    model = model or current_model()
    vector = _load(model.name).encode(model.query_prefix + text, normalize_embeddings=True, show_progress_bar=False)
    return vector.tolist()
