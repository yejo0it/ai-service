"""
정적 참조 데이터(backend/data/*.json) 읽기.

- 코드에 하드코딩하지 않고 데이터 파일로 두어, 데이터만 고칠 때 코드 diff가 섞이지 않게 한다.
- 파일은 처음 쓸 때 한 번만 읽어 메모리에 둔다. 데이터 파일을 바꾸면 백엔드를 다시 시작해야 반영된다
  (개발 서버는 .py 변경에만 자동으로 다시 시작한다).

파일
- cities.json: 여행지 도시 (trips.cities)
- currencies.json: 통화 표시 정보(currencies)와 나라별 현지 통화(country_currency) (환율 위젯)
"""

import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings

DATA_DIR = Path(settings.BASE_DIR) / "data"


@lru_cache(maxsize=None)
def load(name):
    """backend/data/<name> JSON을 읽는다(프로세스당 한 번)."""
    with open(DATA_DIR / name, encoding="utf-8") as file:
        return json.load(file)
