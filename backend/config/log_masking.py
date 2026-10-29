"""
서버 로그에 비밀 값·개인정보가 남지 않게 가리는 Formatter(config.settings의 LOGGING).

- Formatter가 완성한 출력 문자열(메시지 + traceback + stack_info)을 가린다. 그래서 예외 메시지·DB 오류 DETAIL처럼
  로그를 남기는 코드가 직접 만들지 않은 문자열도 가려진다.
- 원본 예외 객체와 로그 레코드의 msg·args는 바꾸지 않는다. 예외 종류·파일·줄 번호·코드 줄은 그대로 남는다.
- 가리는 것(값만 ***로 바꾸고 키·컬럼 이름은 남긴다)
  1. 초대 링크 토큰 경로(/invitations/{token}/)
  2. URL 쿼리의 인증 값(token·key·code·password 등)
  3. Authorization 값(Token·Bearer·Basic 뒤)
  4. API 키 모양 문자열(sk-ant-…, AIza…)
  5. 민감한 키-값(password=…, "secret": "…", API_KEY: … 등). 파이썬 코드 줄(password = …)은 디버깅에 필요해 두려고
     '='는 앞뒤 공백 없이 붙은 경우만 본다.
  6. PostgreSQL 제약 위반 DETAIL의 값(Key (email)=(***), Failing row contains (***))
  7. 이메일 주소
- AI 사용량(pinroute.ai_usage)·번역 못 한 이름(pinroute.untranslated) 로그는 숫자·코드·역 이름만 남기므로 이 Formatter를 쓰지
  않고 기존 형식 그대로 둔다.
"""

import logging
import re

from django.utils.log import ServerFormatter

MASK = "***"

_SENSITIVE_KEYS = (
    "password|passwd|pwd|secret|client_secret|secret_key|api_key|apikey|api-key|private_key|"
    "access_token|refresh_token|id_token|auth_token|token|authorization|cookie|sessionid|session_id|csrftoken"
)
_QUERY_KEYS = (
    "token|key|code|api_key|apikey|access_token|refresh_token|id_token|secret|client_secret|password|signature|sig|auth"
)

_RULES = (
    # 6. DB 제약 위반: 컬럼 이름은 두고 값만 가린다. 값에 괄호가 있어도 끝 문구까지 가린다.
    (re.compile(r"(Key \([^)\n]*\)=\().*?(\) (?:already exists|is not present in table|is still referenced from table))"),
     rf"\g<1>{MASK}\g<2>"),
    (re.compile(r"(Failing row contains \().*(\))"), rf"\g<1>{MASK}\g<2>"),
    # 1. 초대 링크 토큰
    (re.compile(r"(/invitations/)[^/\s?#\"']+"), rf"\g<1>{MASK}"),
    # 2. URL 쿼리의 인증 값
    (re.compile(rf"([?&](?:{_QUERY_KEYS})=)[^&\s#\"']*", re.IGNORECASE), rf"\g<1>{MASK}"),
    # 3. Authorization 값
    (re.compile(r"\b(Token|Bearer|Basic) [A-Za-z0-9._~+/=-]{8,}"), rf"\g<1> {MASK}"),
    # 4. API 키 모양 문자열
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]+|\bAIza[0-9A-Za-z_-]{20,}"), MASK),
    # 5. 민감한 키-값: password=…, password: …, "password": "…", 'api_key': '…', GOOGLE_PLACES_API_KEY=…
    (re.compile(rf"((?<![\w-])(?:[A-Za-z0-9]+[_-])*(?:{_SENSITIVE_KEYS})[\"']?(?:=|\s*:\s*))"
                r"(?:\"[^\"\n]*\"|'[^'\n]*'|[^\s,;&)}\]\"']+)", re.IGNORECASE),
     None),
    # 7. 이메일 주소
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"), MASK),
)


def _mask_value(match):
    prefix, value = match.group(1), match.group(0)[len(match.group(1)):]
    quote = value[0] if value[:1] in ("'", '"') else ""
    return f"{prefix}{quote}{MASK}{quote}"


def mask_secrets(text):
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement or _mask_value, text)
    return text


class MaskingFormatter(logging.Formatter):
    """일반 로그: 시각 수준 로거: 메시지 (+ traceback·stack_info), 출력 전체를 가린다."""

    def format(self, record):
        return mask_secrets(super().format(record))


class MaskingServerFormatter(ServerFormatter):
    """개발 서버 요청 줄(django.server): Django 기본 형식 그대로, 출력 전체를 가린다."""

    def format(self, record):
        return mask_secrets(super().format(record))
