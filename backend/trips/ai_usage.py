"""
'AI와 함께 만들기' 토큰 사용량·응답 시간 기록. 컨텍스트 최적화(프롬프트 캐싱 등) 전후의 비용·속도를 비교하는 데 쓴다.

- 한 줄에 JSON 하나로 LOGGER_NAME 로거에 남긴다(출력 위치는 config.settings의 LOGGING, 기본은 표준 출력).
- 숫자와 모델명·결과 종류만 남긴다. 사용자·여행 id, 대화, 여행 정보, 프롬프트, 응답 내용, 키, 오류 메시지는 기록하지 않는다
  (오류는 예외 클래스 이름만).
- 기록이 실패해도 AI 기능에는 영향이 없다(예외를 밖으로 내보내지 않는다).

이벤트
- claude_call: Claude API 호출 한 번. api_ms는 API 호출 전후 시간이다.
- ai_request: 제안 요청 처리 전체(검증·문서 검색·모델 호출·장소 확정·이동 시간 계산). total_ms는 뷰 처리 시간이다.
  모델을 부른 요청만 남긴다(미리 거절·요청 제한에 걸린 요청은 모델을 부르지 않아 남기지 않는다).
- source: 호출 목적. 호출하는 쪽이 직접 넘긴다(추측하지 않는다).
  SOURCE_USER(실제 'AI와 함께 만들기' 채팅 요청) / SOURCE_EVALUATION(eval_guides 평가 명령)
- request_id: HTTP 요청마다 새로 만드는 무작위 값(UUID4)으로, 같은 요청의 claude_call과 ai_request에 똑같이 붙는다.
  사용자·여행·시각에서 만들지 않으므로 이 값으로 사람이나 여행을 알아낼 수 없고, 서버 어디에도 따로 저장하지 않는다.

대화 길이 (ai_request, 실제 대화 길이를 보고 대화 요약 필요 여부를 판단하는 데 쓴다)
- messages_received: 요청에 들어온 메시지 수(현재 질문 포함, 서버가 최근 메시지만 남기기 전)
- messages_sent: 모델에 실제로 보낸 메시지 수(현재 질문 포함)
- history_truncated: 메시지 상한 때문에 앞의 대화가 잘렸는지
- history_chars: 모델에 보낸 이전 대화(현재 질문 제외)의 글자 수. 개인정보를 가린 뒤 실제로 보낸 내용 기준이다.
  글자 수만 남기고 내용은 남기지 않는다. 토큰 수는 여기서 계산하지 않는다(분석할 때 추정치로만 환산한다).

usage 필드 (Anthropic Messages API)
- input_tokens: 새로 처리한 입력 토큰. 캐시에 쓰거나 캐시에서 읽은 토큰은 들어 있지 않다.
- cache_creation_input_tokens / cache_read_input_tokens: 캐시에 쓴 / 캐시에서 읽은 입력 토큰
- total_input_tokens = 위 세 값의 합, total_tokens = total_input_tokens + output_tokens
- 응답에 usage가 없으면(호출 실패) 토큰 값은 모두 null, usage에 일부 필드가 없으면 그 값은 0으로 센다.
- thinking_tokens: output_tokens 가운데 모델 내부 추론(thinking)에 쓴 토큰(usage.output_tokens_details.thinking_tokens).
  output_tokens에 이미 들어 있으므로 합계에 더하지 않는다. API가 알려 주지 않으면 추정하지 않고 null로 둔다.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

LOGGER_NAME = "pinroute.ai_usage"
logger = logging.getLogger(LOGGER_NAME)

SOURCE_USER = "user"
SOURCE_EVALUATION = "evaluation"

USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def new_request_id():
    """요청 하나를 가리키는 무작위 id (개인정보와 관계없는 UUID4, 32자리 16진수)"""
    return uuid.uuid4().hex


def _count(usage, field):
    value = getattr(usage, field, None)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _thinking_tokens(usage):
    """API가 알려 준 추론 토큰 수. 없거나 숫자가 아니면 None(추정하지 않는다)."""
    value = getattr(getattr(usage, "output_tokens_details", None), "thinking_tokens", None)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def usage_fields(usage):
    """응답의 usage -> 기록할 토큰 수 (usage가 없으면 모두 None)"""
    if usage is None:
        return {field: None for field in (*USAGE_FIELDS, "thinking_tokens", "total_input_tokens", "total_tokens")}
    counts = {field: _count(usage, field) for field in USAGE_FIELDS}
    total_input = counts["input_tokens"] + counts["cache_creation_input_tokens"] + counts["cache_read_input_tokens"]
    return {**counts, "thinking_tokens": _thinking_tokens(usage), "total_input_tokens": total_input,
            "total_tokens": total_input + counts["output_tokens"]}


def _write(record):
    if not logger.isEnabledFor(logging.INFO):
        return
    record = {"t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **record}
    logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":")))


def record_call(feature, source, request_id, model, response, api_ms, error=None):
    """
    Claude API 호출 한 번: 모델·토큰 수·API 응답 시간(ms)·성공 여부.
    source: 호출 목적(SOURCE_USER·SOURCE_EVALUATION), request_id: 이 호출을 한 요청의 id(new_request_id),
    response: 받은 응답(실패하면 None), error: 실패한 예외 클래스 이름(성공이면 None)
    """
    try:
        stop_reason = getattr(response, "stop_reason", None)
        _write(
            {
                "event": "claude_call",
                "request_id": request_id,
                "feature": feature,
                "source": source,
                "model": model,
                "success": error is None,
                "error": error,
                "stop_reason": stop_reason if isinstance(stop_reason, str) else None,
                **usage_fields(getattr(response, "usage", None)),
                "api_ms": round(api_ms),
            }
        )
    except Exception:  # noqa: BLE001 - 기록 실패가 AI 응답을 막지 않게 한다.
        pass


CONVERSATION_FIELDS = ("messages_received", "messages_sent", "history_truncated", "history_chars")


def record_request(feature, source, request_id, outcome, status_code, total_ms, conversation=None):
    """
    제안 요청 처리 전체 시간(ms)과 결과. source·request_id는 같은 요청의 claude_call과 같은 값이다.
    outcome: ok(제안) / off_topic(범위 밖이라 거절) / planner_error(모델 호출 실패)
    conversation: 대화 길이 수치(CONVERSATION_FIELDS). 없으면 null로 남긴다.
    """
    try:
        conversation = conversation or {}
        _write(
            {
                "event": "ai_request",
                "request_id": request_id,
                "feature": feature,
                "source": source,
                "outcome": outcome,
                "status": status_code,
                "total_ms": round(total_ms),
                **{field: conversation.get(field) for field in CONVERSATION_FIELDS},
            }
        )
    except Exception:  # noqa: BLE001 - 기록 실패가 AI 응답을 막지 않게 한다.
        pass
