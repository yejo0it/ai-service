"""
한국어로 바꾸지 못한 역·노선 이름 목록(trips/untranslated.py가 쌓은 로그)을 센다.

    python manage.py untranslated_names                # 많이 나온 순서로 표
    python manage.py untranslated_names --kind station # 역만 (line: 노선만)
    python manage.py untranslated_names --limit 20
    python manage.py untranslated_names --json         # 한 줄에 JSON 하나

보완 방법:
- 역: 이름이 한자인데 한국어 데이터에 없으면 data/station_name_overrides.json에 node_id로 직접 확인한 이름을 넣는다.
  (히라가나·가타카나 표기는 한자 이름 데이터와 맞지 않아 여기에 넣어야 한다.)
- 노선·운영사: trips/line_names.py의 LINES·OPERATORS, trips/station_names.py의 COMPANIES에 추가한다.
확인한 이름만 넣고, 모르면 원어로 둔다. 수집 로그를 지우려면 파일을 삭제하면 된다.
"""

import json
from collections import OrderedDict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


def read_records(path):
    """로그 파일(과 회전된 이전 파일)의 모든 기록. 깨진 줄은 건너뛴다."""
    records = []
    base = Path(path)
    for file in [*(base.with_name(f"{base.name}.{i}") for i in (3, 2, 1)), base]:
        try:
            lines = file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
    return records


def aggregate(records, kind=None):
    """같은 이름(역은 node_id, 노선은 운영사까지)을 합쳐 횟수·처음/마지막 시각을 센다."""
    groups = OrderedDict()
    for record in records:
        if kind and record.get("kind") != kind:
            continue
        key = (record.get("kind"), record.get("node_id") or record.get("name"), record.get("operator", ""))
        group = groups.setdefault(key, {**record, "count": 0, "first": record.get("t"), "last": record.get("t")})
        group["count"] += 1
        group["last"] = record.get("t", group["last"])
    return sorted(groups.values(), key=lambda g: (-g["count"], g.get("kind", ""), g.get("name", "")))


class Command(BaseCommand):
    help = "한국어로 바꾸지 못한 역·노선 이름 목록을 보여줍니다."

    def add_arguments(self, parser):
        parser.add_argument("--kind", choices=["station", "line"])
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, kind=None, limit=0, as_json=False, **options):
        path = settings.UNTRANSLATED_LOG_PATH
        rows = aggregate(read_records(path), kind)
        if limit:
            rows = rows[:limit]
        if as_json:
            for row in rows:
                self.stdout.write(json.dumps(row, ensure_ascii=False))
            return
        if not rows:
            self.stdout.write(f"수집된 미변환 이름이 없습니다. ({path})")
            return
        self.stdout.write(f"미변환 이름 {len(rows)}건 ({path})")
        for row in rows:
            extra = (
                f"node_id={row['node_id']}" + (f" 좌표={row['lat']},{row['lng']}" if "lat" in row else "")
                if row.get("kind") == "station" and row.get("node_id")
                else (f"운영사={row['operator']}" if row.get("operator") else "")
            )
            label = "역" if row.get("kind") == "station" else "노선"
            self.stdout.write(f"{row['count']:>4}회  [{label}] {row['name']}  {extra}  (마지막 {row.get('last', '')})")
