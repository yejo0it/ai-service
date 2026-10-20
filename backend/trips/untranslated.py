"""
한국어로 바꾸지 못한 역·노선 이름 수집(로그). 쌓인 이름을 보고 사전(JSON)을 보완해 변환율을 높인다.

- 기록하는 것은 변환하지 못한 이름과 식별에 필요한 값뿐이다(여행·사용자·경로 정보는 기록하지 않는다).
  - 역: 이름, NAVITIME node_id, 좌표(같은 이름의 다른 역을 구분하는 데 쓴다). 행선지 이름은 이름만 있다.
  - 노선: 이름, 운영사 이름
- 한 줄에 JSON 하나(JSON Lines)로 UNTRANSLATED_LOG_PATH 파일에 쌓고, 같은 이름은 프로세스당 한 번만 남긴다.
  (여러 번 나온 횟수는 `python manage.py untranslated_names`가 파일에서 센다.)
- 파일을 쓸 수 없으면(읽기 전용 등) 조용히 건너뛴다. 이름 수집이 이동 안내를 막지 않는다.
- 테스트 실행 중에는 쓰지 않는다. UNTRANSLATED_LOG_ENABLED=0으로 끌 수 있다.
"""

import json
import logging
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from django.conf import settings

LOGGER_NAME = "pinroute.untranslated"
_lock = threading.Lock()
_seen = set()
_logger = None


def _enabled():
    return getattr(settings, "UNTRANSLATED_LOG_ENABLED", True) and not settings.TESTING


def _get_logger():
    """파일 핸들러를 처음 쓸 때 한 번 만든다. 만들 수 없으면 None."""
    global _logger
    if _logger is not None:
        return _logger or None
    try:
        path = Path(settings.UNTRANSLATED_LOG_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        _logger = False
        return None
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # 일반 서버 로그에 섞지 않는다
    logger.handlers = [handler]
    _logger = logger
    return logger


def reset():
    """상태 초기화(테스트용): 이미 남긴 이름 목록과 파일 핸들러를 버린다."""
    global _logger
    with _lock:
        _seen.clear()
        if _logger:
            for handler in list(_logger.handlers):
                handler.close()
                _logger.removeHandler(handler)
        _logger = None


def _write(key, record):
    if not _enabled():
        return
    with _lock:
        if key in _seen:
            return
        _seen.add(key)
    logger = _get_logger()
    if logger is None:
        return
    record["t"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":")))


def record_station(name, node_id=None, lat=None, lng=None):
    """한국어로 바꾸지 못한 역 이름(지점은 node_id·좌표와 함께, 행선지는 이름만)."""
    name = (name or "").strip()
    if not name:
        return
    record = {"kind": "station", "name": name}
    if node_id:
        record["node_id"] = node_id
    if lat is not None and lng is not None:
        record["lat"], record["lng"] = round(lat, 5), round(lng, 5)
    _write(("station", node_id or name), record)


def record_line(name, operator=""):
    """한국어로 바꾸지 못한 노선·버스 이름."""
    name = (name or "").strip()
    if not name:
        return
    record = {"kind": "line", "name": name}
    if operator:
        record["operator"] = operator
    _write(("line", name, operator), record)
