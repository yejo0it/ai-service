"""
'AI와 함께 만들기' 대화의 응답 범위 제한.

- 여행 계획과 관계없는 요청은 모델이 off_topic으로 표시하고, 서버가 정해진 거절 문구로 답한다.
- 시스템 지시를 무시·변경·공개하라는 뻔한 입력(프롬프트 인젝션)은 모델을 부르기 전에 서버가 바로 거절한다.
  정상적인 여행 질문을 막지 않도록 '지시·프롬프트·규칙' 같은 단어와 '무시·공개' 같은 동작이 함께 있을 때만 잡는다.
- 사용자 메시지에 서비스가 붙이는 여행 정보 태그(<current_trip>)를 흉내 낸 부분은 지운다.
- 사용자가 적은 개인정보·인증 정보(비밀번호, 카드번호 등)는 외부 LLM으로 보내기 전에 가린다(redact_sensitive).
"""

import re

REFUSAL = (
    "PinRoute 여행 계획과 관련된 질문에만 답변할 수 있어요.\n"
    "가고 싶은 곳, 바꾸고 싶은 일정, 항공·숙소 등록, 여행 준비에 관해 물어봐 주세요."
)

_INSTRUCTION = r"(지시|명령|규칙|프롬프트|지침|instructions?|prompts?|rules)"
INJECTION_PATTERNS = [
    # "이전 지시는 모두 무시해", "너의 규칙을 잊어"
    re.compile(
        r"(이전|위|앞|기존|모든|원래|너의|네|당신의|니)\s*(의\s*)?" + _INSTRUCTION
        + r"\S*\s*(전부|모두|다)?\s*(무시|잊|따르지\s*마|따르지\s*말|어기|어겨|해제)",
        re.IGNORECASE,
    ),
    # 시스템 프롬프트·시스템 메시지를 묻거나 바꾸려는 요청
    re.compile(r"(시스템|system)\s*(프롬프트|prompt|메시지|message|지시|instruction)", re.IGNORECASE),
    # "ignore all previous instructions", "disregard the above rules"
    re.compile(
        r"(ignore|disregard|forget|override)\s+(all\s+|any\s+|the\s+|your\s+|of\s+)*"
        r"(previous|prior|above|earlier|system|initial)?\s*(instructions?|prompts?|rules|guidelines)",
        re.IGNORECASE,
    ),
    # "프롬프트를 보여줘", "지시사항을 출력해"
    # 사이에 '그대로', '전부' 같은 말이 두 단어까지 끼어도 잡는다.
    re.compile(r"(프롬프트|지시\s*사항|지시문|지침)\s*(을|를|좀)?\s*(\S+\s+){0,2}(알려|보여|출력|공개|말해|복사)", re.IGNORECASE),
    # 탈옥 모드 요청
    re.compile(r"(developer|dev|개발자)\s*(mode|모드)|jailbreak|탈옥|\bDAN\b", re.IGNORECASE),
]

_TRIP_TAG = re.compile(r"</?\s*current_trip\s*>", re.IGNORECASE)


def looks_like_injection(text):
    """시스템 지시를 무시·변경·공개하라는 입력인지"""
    return any(pattern.search(text or "") for pattern in INJECTION_PATTERNS)


def strip_trip_tags(text):
    """사용자 메시지에서 서비스용 여행 정보 태그를 흉내 낸 부분을 지운다."""
    return _TRIP_TAG.sub("", text or "")


# ------------------------------------------------------------------ #
# 민감정보 가리기 (외부 LLM으로 보내기 전에)
# ------------------------------------------------------------------ #
# 여행 계획에는 필요 없는 개인정보·인증 정보를 사용자가 채팅에 적어도 모델에 보내지 않는다.
# 날짜(2026-11-10)·편명(KE703)·숙소 전화(03-1234-5678)·금액 같은 여행 정보는 건드리지 않는다.

def _luhn_ok(digits):
    total, double = 0, False
    for char in reversed(digits):
        number = int(char)
        if double:
            number = number * 2 - 9 if number * 2 > 9 else number * 2
        total += number
        double = not double
    return total % 10 == 0


def _card(match):
    digits = re.sub(r"\D", "", match.group(0))
    return "[카드번호]" if 13 <= len(digits) <= 16 and _luhn_ok(digits) else match.group(0)


# 한글도 단어 문자(\w)라 '1111로'처럼 조사가 붙으면 가 경계를 못 잡는다. 숫자·영문 기준 경계를 쓴다.
SENSITIVE_PATTERNS = [
    # (가릴 대상 이름, 패턴, 바꿀 값 또는 함수)
    ("인증 정보", re.compile(r"(?<![A-Za-z0-9])(sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{20,}"
                         r"|xox[baprs]-[A-Za-z0-9-]{10,})"), "[인증 정보]"),
    ("인증 정보", re.compile(r"(?<![A-Za-z0-9])(Bearer|Token)\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE),
     "[인증 정보]"),
    ("비밀번호", re.compile(r"(비밀\s*번호|비번|패스워드|password|passwd|pw)(\s*(은|는|이|가|:|=)?\s*)(\S+)",
                        re.IGNORECASE), r"\1\2[가림]"),
    ("주민등록번호", re.compile(r"(?<!\d)\d{6}\s*-\s*[1-8]\d{6}(?!\d)"), "[주민등록번호]"),
    ("카드번호", re.compile(r"(?<!\d)\d(?:[ -]?\d){12,15}(?!\d)"), _card),
    ("여권번호", re.compile(r"(?<![A-Za-z0-9])[MSRODG](\d{8}|\d{3}[A-Z]\d{4})(?!\d)"), "[여권번호]"),
    ("이메일", re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+"), "[이메일]"),
    ("전화번호", re.compile(r"(?<!\d)01[016789][-. ]?\d{3,4}[-. ]?\d{4}(?!\d)"), "[전화번호]"),
]


def redact_sensitive(text):
    """(가린 글, 가린 대상 이름 목록). 여행 계획에 필요 없는 민감정보를 자리표시로 바꾼다."""
    found = []
    for label, pattern, replacement in SENSITIVE_PATTERNS:
        new = pattern.sub(replacement, text or "")
        if new != text:
            found.append(label)
        text = new
    return text, found
