"""
일본 역·출구·운영사 이름을 한국어로 바꾼다(NAVITIME 이동 안내 표시용). 정확한 한국어 이름을 확보하지 못하면 원어를 그대로 둔다.

역 이름은 두 단계로 찾는다.
1. node_id 직접 지정(data/station_name_overrides.json): NAVITIME 역 식별자. 사람이 확인한 이름만 넣고, 항상 이 데이터보다 먼저 쓴다.
2. 일본어 역 이름 데이터(data/station_names_ja_ko.json: {"ja", "ko", "lat", "lng"} 목록)에서 이름으로 찾고,
   좌표를 알면 가장 가까운 항목(MAX_DISTANCE_KM 이내)만 쓴다. 좌표를 모르면(행선지 등) 같은 이름의 항목들이
   모두 같은 한국어 이름일 때만 쓴다. 이름이 겹치는 서로 다른 역을 잘못 연결하지 않기 위해서다.
node_id는 NAVITIME 내부 식별자라 외부 철도 데이터에는 없으므로 이름+좌표가 기본 식별 방법이다.
출구 이름은 규칙(동쪽·서쪽·번호 등)으로만 바꾸고, 규칙에 없으면 원어를 그대로 둔다.
"""

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from . import untranslated

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATION_DATA = DATA_DIR / "station_names_ja_ko.json"
OVERRIDES = DATA_DIR / "station_name_overrides.json"
MAX_DISTANCE_KM = 0.8

# 운영사(회사) 이름
COMPANIES = {
    "JR東日本": "JR동일본", "JR東海": "JR도카이", "JR西日本": "JR서일본", "JR北海道": "JR홋카이도", "JR四国": "JR시코쿠",
    "JR九州": "JR규슈", "JR貨物": "JR화물", "東京地下鉄": "도쿄메트로", "東京都交通局": "도쿄도교통국(도에이)",
    "東急電鉄": "도큐전철", "小田急電鉄": "오다큐전철", "京王電鉄": "게이오전철", "京浜急行電鉄": "게이큐전철",
    "西武鉄道": "세이부철도", "東武鉄道": "도부철도", "京成電鉄": "게이세이전철", "相模鉄道": "소테쓰", "東京モノレール": "도쿄모노레일",
    "ゆりかもめ": "유리카모메", "東京臨海高速鉄道": "도쿄린카이고속철도", "首都圏新都市鉄道": "수도권신도시철도(쓰쿠바 익스프레스)",
    "横浜市交通局": "요코하마시교통국", "横浜高速鉄道": "요코하마고속철도", "多摩都市モノレール": "다마도시모노레일",
    "大阪市高速電気軌道": "오사카메트로", "阪急電鉄": "한큐전철", "阪神電気鉄道": "한신전기철도", "南海電気鉄道": "난카이전기철도",
    "京阪電気鉄道": "게이한전기철도", "近畿日本鉄道": "긴테쓰", "京都市交通局": "교토시교통국", "名古屋市交通局": "나고야시교통국",
    "札幌市交通局": "삿포로시교통국", "福岡市交通局": "후쿠오카시교통국", "神戸市交通局": "고베시교통국", "仙台市交通局": "센다이시교통국",
    "西日本鉄道": "니시테쓰",
    "東日本旅客鉄道": "JR동일본", "東海旅客鉄道": "JR도카이", "西日本旅客鉄道": "JR서일본", "北海道旅客鉄道": "JR홋카이도",
    "四国旅客鉄道": "JR시코쿠", "九州旅客鉄道": "JR규슈", "OsakaMetro": "오사카메트로",
    "北総鉄道": "호쿠소철도", "埼玉高速鉄道": "사이타마고속철도", "東葉高速鉄道": "도요고속철도", "芝山鉄道": "시바야마철도",
    "江ノ島電鉄": "에노시마전철", "箱根登山鉄道": "하코네도잔철도", "伊豆箱根鉄道": "이즈하코네철도", "富士急行": "후지급행",
    "秩父鉄道": "지치부철도", "京福電気鉄道": "게이후쿠전철", "叡山電鉄": "에이잔전철", "神戸電鉄": "고베전철",
    "山陽電気鉄道": "산요전기철도", "能勢電鉄": "노세전철", "大阪モノレール": "오사카모노레일", "泉北高速鉄道": "센보쿠고속철도",
    "名古屋鉄道": "메이테쓰", "愛知高速交通": "아이치고속교통", "名古屋臨海高速鉄道": "나고야린카이고속철도",
    "広島電鉄": "히로시마전철", "伊予鉄道": "이요철도", "舞浜リゾートライン": "마이하마 리조트 라인",
}

# 출구 이름 규칙
_DIRECTIONS = [("中央", "중앙"), ("正面", "정면"), ("東", "동쪽"), ("西", "서쪽"), ("南", "남쪽"), ("北", "북쪽")]
_NUMBERED_EXIT = re.compile(r"^([A-Za-z]{0,2}\d{1,3}[A-Za-z]?)(番)?口$")
_DIRECTION_EXIT = re.compile(r"^((?:中央|正面|東|西|南|北)+)口$")


def normalize(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or "")).strip()


def _station_key(name):
    """역 이름 -> 조회 키. 괄호 설명((東京都) 등)과 끝의 '駅'을 떼고 ヶ/ケ를 맞춘다."""
    text = re.sub(r"[(\[〔].*?[)\]〕]", "", normalize(name)).replace("ヶ", "ケ").replace("ヵ", "カ")
    return text[:-1] if text.endswith("駅") else text


_NOTE = re.compile(r"[(\[〔].*?[)\]〕]")


def ja_station_label(name, keep_note=True):
    """
    원어 역 표기. 끝에 '駅'이 없으면 붙인다(渋谷 -> 渋谷駅). 괄호 설명은 '駅' 뒤에 두거나(keep_note) 뗀다:
    恵比寿(東京都) -> 恵比寿駅(東京都) / 恵比寿駅
    """
    text = normalize(name)
    note = "".join(_NOTE.findall(text))
    base = _NOTE.sub("", text).strip()
    if base and not base.endswith("駅"):
        base += "駅"
    return base + (note if keep_note else "")


def _clean_ko(label):
    return re.sub(r"\s+역$", "역", label.strip())


@lru_cache(maxsize=1)
def _load_index():
    """
    {조회 키: [(lat, lng, 한국어 이름), ...]} (파일이 없거나 STATION_NAMES_ENABLED가 꺼져 있으면 비어 있다).
    파일은 {"_meta": {...}, "stations": [...]} 또는 목록이다(trips/../scripts/fetch_station_names.py가 만든다).
    """
    from django.conf import settings

    if not getattr(settings, "STATION_NAMES_ENABLED", False):
        return {}
    index = {}
    try:
        rows = json.loads(STATION_DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if isinstance(rows, dict):
        rows = rows.get("stations", [])
    for row in rows:
        if row.get("flag"):  # 읽기가 의심스러운 항목은 쓰지 않는다(원어를 보여준다)
            continue
        index.setdefault(_station_key(row["ja"]), []).append((row.get("lat"), row.get("lng"), row["ko"]))
    return index


@lru_cache(maxsize=1)
def _load_overrides():
    try:
        data = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    overrides = {}
    for key, value in data.items():
        if key.startswith("_"):
            continue
        ko = value.get("ko") if isinstance(value, dict) else value
        if isinstance(ko, str) and ko.strip():
            overrides[key] = ko.strip()
    return overrides


def _km(a, b):
    from .itinerary_planner import distance_km

    return distance_km(a, b)


def korean_station(name, lat=None, lng=None, node_id=None):
    """역 이름의 한국어 표기(끝에 '역' 포함). 확실하지 않으면 None."""
    if node_id and node_id in _load_overrides():
        return _clean_ko(_load_overrides()[node_id])
    candidates = _load_index().get(_station_key(name))
    if not candidates:
        return None
    if lat is not None and lng is not None:
        located = [(_km((lat, lng), (c[0], c[1])), _clean_ko(c[2])) for c in candidates if c[0] is not None and c[1] is not None]
        located = [item for item in located if item[0] <= MAX_DISTANCE_KM]
        return min(located)[1] if located else None
    names = {_clean_ko(c[2]) for c in candidates}
    return next(iter(names)) if len(names) == 1 else None


def station_labels(name, lat=None, lng=None, node_id=None):
    """(한국어 표기, 원어 표기). 한국어를 확보하지 못하면 둘 다 원어다."""
    ko = korean_station(name, lat, lng, node_id)
    if ko:
        return ko, ja_station_label(name, keep_note=False)
    original = ja_station_label(name)  # 한국어를 확보하지 못하면 원어 그대로(괄호 설명 포함)
    untranslated.record_station(name, node_id, lat, lng)  # 사전 보완용으로 이름만 남긴다
    return original, original


def display_station(name, lat=None, lng=None, node_id=None):
    """문장용 표기: '시부야역(渋谷駅)'. 한국어를 확보하지 못하면 원어만."""
    ko, ja = station_labels(name, lat, lng, node_id)
    return ko if ko == ja else f"{ko}({ja})"


def korean_gateway(gateway):
    """
    출구 이름의 한국어 표기. 번호·방향 규칙에 맞는 것만 바꾸고(東口 -> 동쪽 출구, A1口 -> A1 출구, 1番口 -> 1번 출구),
    '赤羽橋口'처럼 역 이름이 들어간 출구는 그 역 이름을 한국어로 확보했을 때만 바꾼다. 그 밖에는 원어 그대로다.
    """
    text = normalize(gateway)
    if not text:
        return ""
    numbered = _NUMBERED_EXIT.match(text)
    if numbered:
        number, ban = numbered.group(1), numbered.group(2)
        return f"{number}번 출구" if ban and number.isdigit() else f"{number} 출구"
    direction = _DIRECTION_EXIT.match(text)
    if direction:
        tokens, rest = [], direction.group(1)
        while rest:
            for japanese, korean in _DIRECTIONS:
                if rest.startswith(japanese):
                    tokens.append(korean)
                    rest = rest[len(japanese):]
                    break
        return " ".join(tokens) + " 출구"
    if text.endswith("口") and len(text) > 1:
        ko = korean_station(text[:-1])
        if ko:
            return f"{ko[:-1] if ko.endswith('역') else ko} 출구"
    return text


def korean_company(name):
    """
    운영사 이름의 한국어 표기. 전각/반각을 맞추고 끝의 괄호 설명((メトロ)·(成田空港線))을 떼며, 'A/B'처럼 운영사가 여럿이면
    각각 바꿔 '/'로 잇는다. 하나라도 확보하지 못하면 일부만 한국어로 섞지 않고 원어 전체를 그대로 둔다.
    """
    text = normalize(name)
    if not text:
        return ""
    translated = []
    for part in text.split("/"):
        base = re.sub(r"\s*\(.*?\)\s*$", "", part.strip()).replace(" ", "")
        ko = COMPANIES.get(base)
        if ko is None:
            return text
        translated.append(ko)
    return "/".join(translated)
