"""
PDF 검사 작업 프로세스(예약 확인서 업로드). `files.py`가 별도 프로세스로 실행한다 - Django와 무관하게 pypdf와 표준 라이브러리만 쓴다.

왜 별도 프로세스인가
- 사용자가 올린 PDF를 파싱하는 일은 시간·메모리를 크게 쓸 수 있다(압축 폭탄, 순환 구조, 거대한 객체 트리 등).
  이 프로세스는 시작하자마자 CPU 시간과 메모리(주소 공간)를 운영체제 수준으로 제한하고, 부모는 제한 시간이 지나면 강제 종료한다.
  제한을 넘으면 이 프로세스만 죽고 웹 서버는 영향이 없다.
- PDF 안의 스크립트·첨부 파일은 실행하지도 열지도 않는다(pypdf는 구조를 읽기만 한다).
- 제한은 실패하면 검사하지 않는다(fail-closed): Linux 등 `resource` 모듈이 있는 환경에서 CPU·메모리·출력 크기 상한을 하나라도
  걸지 못하면 PDF를 읽지 않고 {"ok": false, "error": "limits"}로 끝낸다. `resource`가 없는 환경(Windows 직접 실행)만 제한 없이 진행한다.
- 표준 출력은 OUTPUT_BYTES(1MB)까지만 쓸 수 있다(RLIMIT_FSIZE). 부모가 출력을 파일로 받아 같은 크기까지만 읽으므로
  출력이 폭주해도 Django 프로세스의 메모리는 늘지 않는다. 표준 오류 출력은 부모가 버린다.

검사 내용(PDF 구조 기반, 문자열 검색이 아니다)
1. 문서 구조의 루트(Root)에서 닿을 수 있는 객체를 따라가며 사전(dictionary)의 키와 값을 확인한다.
   이름은 pypdf가 해석한 값이라 `/J#61vaScript`처럼 일부를 16진수로 숨긴 표기도 같은 이름으로 잡힌다.
2. 거절하는 요소: JavaScript(/JS, /JavaScript), 추가 동작(/AA), 열기 동작(/OpenAction)의 실행 동작, 주석·필드의 동작(/A)이
   이동(GoTo)·링크(URI, http·https·mailto·tel만)·이름 있는 동작(Named) 이외인 것(Launch, SubmitForm, ImportData, GoToR 등),
   첨부 파일(/EmbeddedFiles, /EF, /EmbeddedFile, 파일 첨부 주석), XFA 양식, 동영상·소리·화면·3D·RichMedia.
3. 객체 수·깊이 상한을 넘으면 '너무 복잡함'으로 거절한다.
입력(표준 입력): 첫 줄 JSON {"max_pages", "max_objects", "max_text"} + 줄바꿈 + PDF 바이트.
출력(표준 출력): JSON {"ok": true, "pages", "text"} 또는 {"ok": false, "error": "<코드>"}. 코드는 내부용이고 사용자에게는 안내 문구만 보인다.
"""

import json
import sys
from io import BytesIO

CPU_SECONDS = 10
MEMORY_BYTES = 768 * 1024 * 1024
MAX_DEPTH = 60
OUTPUT_BYTES = 1024 * 1024  # 결과 JSON이 쓸 수 있는 최대 크기(부모의 읽기 상한과 같다)

BAD_KEYS = {"/JS", "/JavaScript", "/AA", "/EmbeddedFiles", "/EmbeddedFile", "/EF", "/XFA", "/RichMedia", "/RichMediaContent"}
BAD_SUBTYPES = {"/FileAttachment", "/Movie", "/Sound", "/Screen", "/RichMedia", "/3D"}
SAFE_ACTIONS = {"/GoTo", "/URI", "/Named"}
SAFE_URI_SCHEMES = ("http://", "https://", "mailto:", "tel:")
# 페이지 내용·글꼴 파일 같은 큰 데이터 흐름은 따라가지 않는다(동작·첨부는 여기에 있지 않다).
SKIP_KEYS = {"/Parent", "/P", "/Contents", "/FontFile", "/FontFile2", "/FontFile3", "/Thumb"}


class LimitsUnavailable(Exception):
    """CPU·메모리·출력 크기 제한을 걸지 못했다. 이 경우 PDF를 검사하지 않는다."""


class Rejected(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def limit_resources():
    """
    CPU 시간·메모리·출력 크기를 이 프로세스에 제한한다. `resource` 모듈이 없는 환경(Windows)에서는 건너뛰고,
    있는 환경에서는 하나라도 실패하면 LimitsUnavailable을 올려 검사를 막는다(fail-closed).
    """
    try:
        import resource
    except ImportError:
        return
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS + 1))
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
        resource.setrlimit(resource.RLIMIT_FSIZE, (OUTPUT_BYTES, OUTPUT_BYTES))
    except (ValueError, OSError) as exc:
        raise LimitsUnavailable from exc


def check_action(action, objects):
    """동작 사전을 확인한다: 허용 목록(이동·링크·이름 있는 동작) 밖이거나 위험한 링크면 거절. /Next로 이어진 동작도 본다."""
    from pypdf.generic import ArrayObject, DictionaryObject

    action = action.get_object() if hasattr(action, "get_object") else action
    if isinstance(action, ArrayObject):  # 열기 동작이 이동 위치(배열)인 경우
        return
    if not isinstance(action, DictionaryObject):
        return
    if "/S" not in action and action.get("/Type") != "/Action":
        return  # 동작이 아닌 /A(예: 태그된 PDF의 구조 속성)는 건너뛴다.
    kind = action.get("/S")
    if kind not in SAFE_ACTIONS:
        raise Rejected("unsafe")
    if kind == "/URI":
        uri = str(action.get("/URI", "")).strip().lower()
        if not uri.startswith(SAFE_URI_SCHEMES):
            raise Rejected("unsafe")
    following = action.get("/Next")
    if following is not None:
        following = following.get_object() if hasattr(following, "get_object") else following
        for item in following if isinstance(following, ArrayObject) else [following]:
            objects[0] += 1
            if objects[0] > objects[1]:
                raise Rejected("complex")
            check_action(item, objects)


def check_dictionary(node, objects):
    for key in list(dict.keys(node)):
        if key in BAD_KEYS:
            raise Rejected("unsafe")
    if node.get("/Subtype") in BAD_SUBTYPES or node.get("/Type") == "/EmbeddedFile":
        raise Rejected("unsafe")
    if "/A" in node:
        check_action(dict.__getitem__(node, "/A"), objects)
    if "/OpenAction" in node:
        check_action(dict.__getitem__(node, "/OpenAction"), objects)


def scan(reader, max_objects):
    """Root에서 닿는 객체를 따라가며 위험 요소를 찾는다. 위험하면 Rejected('unsafe'), 너무 크면 Rejected('complex')."""
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

    seen = set()
    objects = [0, max_objects]  # [지금까지 본 객체 수, 상한]
    stack = [(reader.trailer["/Root"], 0)]
    while stack:
        node, depth = stack.pop()
        if depth > MAX_DEPTH:
            raise Rejected("complex")
        if isinstance(node, IndirectObject):
            key = (node.idnum, node.generation)
            if key in seen:
                continue
            seen.add(key)
            objects[0] += 1
            if objects[0] > max_objects:
                raise Rejected("complex")
            node = node.get_object()
        if isinstance(node, DictionaryObject):
            check_dictionary(node, objects)
            for key, value in dict.items(node):
                if key not in SKIP_KEYS:
                    stack.append((value, depth + 1))
        elif isinstance(node, ArrayObject):
            for value in node:
                stack.append((value, depth + 1))


def inspect(data, limits):
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data), strict=False)
    if reader.is_encrypted:
        raise Rejected("encrypted")
    pages = len(reader.pages)
    if pages == 0:
        raise Rejected("empty")
    if pages > limits["max_pages"]:
        raise Rejected("pages")
    scan(reader, limits["max_objects"])
    text = "\n".join((reader.pages[index].extract_text() or "") for index in range(pages))
    return {"ok": True, "pages": pages, "text": text[: limits["max_text"]]}


def main():
    try:
        limit_resources()
    except LimitsUnavailable:
        sys.stdout.write(json.dumps({"ok": False, "error": "limits"}))
        return  # 제한 없이는 PDF를 읽지 않는다.
    raw = sys.stdin.buffer.read()
    header, _, data = raw.partition(b"\n")
    try:
        limits = json.loads(header)
        result = inspect(data, limits)
    except Rejected as rejected:
        result = {"ok": False, "error": rejected.code}
    except MemoryError:
        result = {"ok": False, "error": "complex"}
    except RecursionError:
        result = {"ok": False, "error": "complex"}
    except Exception:  # noqa: BLE001 - 손상된 PDF가 일으키는 모든 파싱 오류. 내용은 출력하지 않는다.
        result = {"ok": False, "error": "corrupt"}
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
