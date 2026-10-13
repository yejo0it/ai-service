"""
Wikivoyage(영문) 문서 수집과 청크 분할.

- MediaWiki API(TextExtracts)로 본문을 일반 텍스트로 받는다. 섹션 제목은 '== 제목 ==' 형식으로 온다.
- 라이선스: CC BY-SA 4.0. 화면에 출처(문서 링크)와 라이선스를 함께 표시한다.
"""

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

API_URL = "https://en.wikivoyage.org/w/api.php"
PAGE_URL = "https://en.wikivoyage.org/wiki/"
LICENSE = "CC BY-SA 4.0"
USER_AGENT = "PinRoute-RAG-PoC/0.1 (https://github.com/yejo0it/ai-service)"
TIMEOUT_SECONDS = 20

# 청크 길이(문자). 다국어 임베딩 모델의 입력 한도(512토큰) 안에 들어가도록 잡는다.
CHUNK_CHARS = 900
CHUNK_OVERLAP = 150

_HEADING = re.compile(r"^(={2,4})\s*(.+?)\s*\1\s*$")


@dataclass
class FetchedPage:
    title: str
    url: str
    revision_id: int
    text: str


@dataclass
class Chunk:
    section: str
    content: str


def fetch_page(title):
    params = {
        "action": "query",
        "prop": "extracts|revisions",
        "explaintext": 1,
        "exsectionformat": "wiki",
        "rvprop": "ids",
        "titles": title,
        "redirects": 1,
        "format": "json",
        "formatversion": 2,
    }
    request = urllib.request.Request(f"{API_URL}?{urllib.parse.urlencode(params)}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        page = json.loads(response.read().decode("utf-8"))["query"]["pages"][0]
    if page.get("missing"):
        raise ValueError(f"Wikivoyage 문서를 찾지 못했어요: {title}")
    return FetchedPage(
        title=page["title"],
        url=PAGE_URL + urllib.parse.quote(page["title"].replace(" ", "_")),
        revision_id=page["revisions"][0]["revid"],
        text=page.get("extract", ""),
    )


def _sections(text):
    """(섹션 경로, 본문) 목록. 경로는 'Get in > By plane'처럼 상위 제목을 이어 붙인다."""
    path, buffer, result = [], [], []

    def flush():
        body = "\n".join(buffer).strip()
        if body:
            result.append((" > ".join(path) or "Overview", body))
        buffer.clear()

    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            flush()
            level = len(match.group(1)) - 2  # == → 0, === → 1, ==== → 2
            path = path[:level] + [match.group(2)]
        else:
            buffer.append(line)
    flush()
    return result


def _windows(text):
    """CHUNK_CHARS보다 긴 문단은 조금씩 겹치게 잘라 문맥이 끊기지 않게 한다."""
    step = CHUNK_CHARS - CHUNK_OVERLAP
    return [text[start:start + CHUNK_CHARS] for start in range(0, len(text) - CHUNK_OVERLAP, step)]


def _split(body):
    """문단을 이어 붙여 CHUNK_CHARS 안팎의 청크로 만든다."""
    pieces = []
    for paragraph in (line.strip() for line in body.splitlines()):
        if paragraph:
            pieces.extend(_windows(paragraph) if len(paragraph) > CHUNK_CHARS else [paragraph])
    chunks, current = [], ""
    for piece in pieces:
        if current and len(current) + 1 + len(piece) > CHUNK_CHARS:
            chunks.append(current)
            current = ""
        current = f"{current}\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks


def chunk_page(page, excluded_sections=()):
    """섹션별로 나눈 뒤 청크로 자른다. 최상위 섹션이 excluded_sections에 있으면 뺀다."""
    chunks = []
    for section, body in _sections(page.text):
        if section.split(" > ")[0] in excluded_sections:
            continue
        for piece in _split(body):
            chunks.append(Chunk(section=section, content=piece))
    return chunks
