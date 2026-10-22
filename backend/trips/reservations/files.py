"""
예약 확인서 파일 검증과 전처리.

- 확장자·Content-Type을 믿지 않고 파일 내용으로 형식을 확인한다(PDF는 `%PDF`, 이미지는 Pillow로 열어 본다).
- 크기(10MB)·PDF 쪽수(5쪽)·이미지 크기를 제한하고, 손상·암호가 걸린 PDF를 거절한다.
- PDF는 별도 프로세스(pdf_worker)에서 구조를 검사한다: 시간·메모리·출력 크기를 제한하고(제한을 걸지 못하면 검사하지 않는다),
  표준 출력은 메모리 위 익명 파일로 받아 1MB까지만 읽고 표준 오류는 버린다. JavaScript·자동 실행 동작·첨부 파일 등
  위험 요소가 있으면 거절한다. 스크립트·첨부 파일은 실행하거나 열지 않는다. 사용자에게는 이유를 알기 쉬운 안내만 보이고
  내부 오류 내용은 보이지 않는다.
- 텍스트가 있는 PDF는 텍스트만 뽑아 보내(이미지 분석 비용 절약), 텍스트가 거의 없는 스캔 PDF는 PDF 그대로 보낸다.
- 이미지는 긴 변 1568px 이하 JPEG로 다시 저장해 크기를 줄이고 EXIF(촬영 위치 등)를 지운다.
- 파일 이름은 쓰지 않고, 아무 곳에도 기록하지 않는다.
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 5
MAX_PDF_OBJECTS = 20_000  # 문서 구조에서 따라갈 객체 수 상한(넘으면 너무 복잡한 PDF로 본다)
PDF_WORKER_TIMEOUT = 15  # 초. 이 시간 안에 검사가 끝나지 않으면 프로세스를 강제 종료한다.
MAX_PDF_OUTPUT_BYTES = 1024 * 1024  # 검사 프로세스 출력을 읽는 상한(pdf_worker.OUTPUT_BYTES와 같다)
MAX_IMAGE_PIXELS = 40_000_000  # 압축 폭탄 같은 거대한 이미지를 열기 전에 거절한다.
MAX_IMAGE_SIDE = 1568  # 모델이 더 큰 이미지는 어차피 줄여서 읽는다.
MIN_IMAGE_SIDE = 200
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
# 텍스트 PDF로 볼 최소 글자 수(공백 제외). 이보다 적으면 스캔본으로 보고 PDF를 그대로(이미지 인식) 보낸다.
MIN_TEXT_CHARS = 120
MAX_TEXT_CHARS = 30_000

PDF_TEXT, PDF_VISUAL, IMAGE = "pdf_text", "pdf_visual", "image"


class ReservationFileError(Exception):
    """사용자에게 그대로 보여줄 수 있는 파일 오류 메시지."""


@dataclass
class PreparedDocument:
    method: str  # pdf_text / pdf_visual / image
    pages: int
    text: str = ""  # pdf_text
    data: bytes = b""  # pdf_visual: PDF 원본, image: 다시 저장한 JPEG
    media_type: str = ""


def prepare(upload):
    """업로드 파일(Django UploadedFile) -> PreparedDocument. 쓸 수 없는 파일이면 ReservationFileError."""
    if upload.size > MAX_BYTES:
        raise ReservationFileError("파일은 10MB 이하로 올려 주세요.")
    if upload.size == 0:
        raise ReservationFileError("빈 파일이에요. 다른 파일을 골라 주세요.")
    data = upload.read()
    if data[:5] == b"%PDF-":
        return _prepare_pdf(data)
    return _prepare_image(data)


PDF_WORKER = Path(__file__).with_name("pdf_worker.py")
logger = logging.getLogger(__name__)

# 검사 프로세스가 돌려주는 내부 코드 -> 사용자 안내(내부 오류 내용은 보여 주지 않는다)
PDF_MESSAGES = {
    "encrypted": "암호가 걸린 PDF는 분석할 수 없어요. 암호를 해제한 파일을 올려 주세요.",
    "empty": "PDF에 페이지가 없어요. 다른 파일을 골라 주세요.",
    "pages": f"PDF는 {MAX_PDF_PAGES}쪽 이하만 분석할 수 있어요.",
    "unsafe": "보안상 안전하지 않은 요소(스크립트·첨부 파일 등)가 들어 있는 PDF라서 분석할 수 없어요. "
    "예약 사이트에서 다시 내려받거나 화면을 캡처해 이미지로 올려 주세요.",
    "complex": "PDF가 너무 복잡해서 분석할 수 없어요. 이미지로 저장해 올려 주세요.",
    "corrupt": "PDF 파일을 읽을 수 없어요. 파일이 손상되었는지 확인해 주세요.",
    # 서버가 검사 제한을 걸지 못한 경우(서버 환경 문제). 제한 없이는 검사하지 않는다.
    "limits": "PDF를 읽을 수 없는 상태예요. 이미지로 올리거나 직접 입력해 주세요.",
}


def _output_file():
    """검사 프로세스의 표준 출력을 받을 익명 파일. Linux에서는 디스크 없이 메모리에만 두고, 그 밖에는 임시 파일을 쓴다."""
    if hasattr(os, "memfd_create"):
        return os.fdopen(os.memfd_create("pdf-check"), "w+b")
    return tempfile.TemporaryFile()


def _inspect_pdf(data):
    """
    별도 프로세스에서 PDF를 검사한다(시간·메모리·출력 크기 제한). 결과 사전을 돌려주고, 프로세스 이상은 'complex'로 본다.
    표준 출력은 상한이 걸린 익명 파일로 받아 MAX_PDF_OUTPUT_BYTES까지만 읽고(폭주해도 이 프로세스의 메모리는 늘지 않는다),
    표준 오류는 버린다.
    """
    limits = json.dumps({"max_pages": MAX_PDF_PAGES, "max_objects": MAX_PDF_OBJECTS, "max_text": MAX_TEXT_CHARS})
    try:
        with _output_file() as output:
            completed = subprocess.run(
                [sys.executable, "-I", str(PDF_WORKER)],
                input=limits.encode("ascii") + b"\n" + data,
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=PDF_WORKER_TIMEOUT,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
                check=False,
            )
            output.seek(0)
            raw = output.read(MAX_PDF_OUTPUT_BYTES + 1)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "complex"}
    except OSError as exc:  # 검사 프로세스나 출력 파일을 만들지 못함(서버 환경 문제)
        raise ReservationFileError(PDF_MESSAGES["limits"]) from exc
    if completed.returncode != 0 or len(raw) > MAX_PDF_OUTPUT_BYTES:
        return {"ok": False, "error": "complex"}  # 메모리·CPU·출력 제한으로 종료되었거나 비정상 종료
    try:
        result = json.loads(raw)
    except ValueError:
        return {"ok": False, "error": "complex"}
    return result if isinstance(result, dict) else {"ok": False, "error": "corrupt"}


def _prepare_pdf(data):
    result = _inspect_pdf(data)
    if not result.get("ok"):
        if result.get("error") == "limits":
            logger.warning("pdf check refused: resource limits could not be applied")  # 문서 내용·파일명은 기록하지 않는다.
        raise ReservationFileError(PDF_MESSAGES.get(result.get("error"), PDF_MESSAGES["corrupt"]))
    text = re.sub(r"[ \t]+", " ", str(result.get("text", ""))).strip()
    pages = int(result.get("pages", 0))
    if len(re.sub(r"\s", "", text)) >= MIN_TEXT_CHARS:
        return PreparedDocument(method=PDF_TEXT, pages=pages, text=text[:MAX_TEXT_CHARS])
    return PreparedDocument(method=PDF_VISUAL, pages=pages, data=data, media_type="application/pdf")


def _prepare_image(data):
    try:
        with Image.open(BytesIO(data)) as probe:
            if probe.format not in ALLOWED_IMAGE_FORMATS:
                raise ReservationFileError("PDF, JPG, PNG, WEBP 파일만 올릴 수 있어요.")
            if probe.width * probe.height > MAX_IMAGE_PIXELS:
                raise ReservationFileError("이미지가 너무 커요. 크기를 줄여서 다시 올려 주세요.")
            probe.verify()  # 손상된 이미지를 걸러낸다.
        with Image.open(BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
    except ReservationFileError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, SyntaxError) as exc:
        raise ReservationFileError("지원하지 않거나 손상된 파일이에요. PDF, JPG, PNG, WEBP 파일을 올려 주세요.") from exc

    if min(image.size) < MIN_IMAGE_SIDE:
        raise ReservationFileError("이미지가 너무 작아서 글자를 읽을 수 없어요. 더 큰 이미지를 올려 주세요.")
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return PreparedDocument(method=IMAGE, pages=1, data=buffer.getvalue(), media_type="image/jpeg")
