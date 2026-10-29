"""
'AI와 함께 만들기' 여행 정보 검색(RAG) 사용 여부 판단 (추가 호출 없는 규칙).

여행지 안내 문서(guides.search)는 추천·현지 정보 질문에만 도움이 된다. 측정해 보니 삭제·시간 변경·이동·항공/숙소 수정에도
매번 무관한 문서 5개(약 1,200토큰, 검색 0.3~1.4초)가 붙었다. 그래서 '분명한 수정·등록 요청'만 검색을 건너뛴다.

판단 순서 (마지막 사용자 메시지, 개인정보를 가린 뒤)
1. 항공·숙소 확인 선택지(registration.CONFIRM_CHOICES)와 똑같으면 생략: confirm_choice
2. 추천·현지 정보·장소 종류·대체 신호가 있으면 검색: info
3. 추가 신호가 있으면 항공·숙소 등록이면 생략(registration), 아니면 장소 추가라 검색(add_place)
4. 수정 신호만 있으면 생략: edit_only
5. 그 밖(모호한 요청, '그걸로 해줘' 같은 후속 말)은 검색: default
정확성을 우선해 애매하면 검색한다(검색은 지금과 같은 동작이고, 비용·시간만 더 든다).
"""

import re

from .registration import CONFIRM_CHOICES

SEARCH = True
SKIP = False

_CONFIRM_TEXTS = {choice for choices in CONFIRM_CHOICES.values() for choice in choices}


def _any(*patterns):
    return re.compile("|".join(patterns), re.IGNORECASE)


# 안내 문서가 근거가 될 수 있는 요청: 추천·현지 정보·장소 종류·다른 곳으로 바꾸기·계획 (하나라도 있으면 검색)
_INFO = _any(
    r"[?？]",
    r"추천|맛집|근처|주변|옆|가까운|가\s?볼|볼거리|먹을|명소|핫플|유명|관광|쇼핑",
    r"카페|식당|음식|라멘|라면|스시|초밥|이자카야|술집|빵집|디저트|레스토랑",
    r"어디|뭐|무엇|어때|어떤|어떻게|알려|궁금|정보|괜찮",
    r"날씨|기온|옷|비자|입국|교통|지하철|전철|버스|택시|패스|환전|현금|카드|팁|매너|문화|치안|안전|전압|콘센트|유심|와이파이",
    r"축제|영업|문\s?(을\s?)?열|휴무|예약",
    r"다른|대신|대체|새로",
    r"계획|짜\s?줘|짜\s?주|만들어|재구성|동선|다시\s?짜|코스",
)
# 무언가를 더하는 요청
_ADD = _any(r"넣어|추가|더해|하나\s?더")
# 항공·숙소 등록 정보 (이름·날짜·편명을 옮겨 적고 장소 확정은 서버가 한다)
_REGISTRATION = _any(
    r"항공|비행|편명|가는\s?편|오는\s?편|출국|귀국|체크인|체크아웃|숙소|호텔",
    r"(?<![A-Za-z])[A-Za-z]{2}\s?\d{2,4}(?!\d)",  # 편명(KE703). 한글 조사가 바로 붙어도 찾도록 \b를 쓰지 않는다
)
# 기존 일정 수정
_EDIT = _any(
    r"빼|삭제|지워|지우|제거|없애|취소",
    r"옮겨|옮기|이동|바꿔|바꾸|변경|미뤄|당겨|늦춰|수정",
    r"\d{1,2}\s?시|\d{1,2}:\d{2}|오전|오후|아침|저녁|점심|도착|출발",
)


def guide_search_decision(text):
    """(검색할지, 사유 코드). 사유는 confirm_choice·info·registration·add_place·edit_only·default 중 하나다."""
    text = (text or "").strip()
    if text in _CONFIRM_TEXTS:
        return SKIP, "confirm_choice"
    if _INFO.search(text):
        return SEARCH, "info"
    if _ADD.search(text):
        return (SKIP, "registration") if _REGISTRATION.search(text) else (SEARCH, "add_place")
    if _EDIT.search(text) or _REGISTRATION.search(text):
        return SKIP, "edit_only"
    return SEARCH, "default"
