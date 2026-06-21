"""Gemini 멀티모달 비전 분석 — 회로도·밴드 다이어그램·도식 입력.

Gemini의 멀티모달 추론을 활용해 텍스트 LLM이 못 보는
시각적 정보(회로도, 밴드 다이어그램, 레이아웃)를 텍스트로 변환.

사용처:
  - 사용자가 회로도 사진 업로드 → 분석 텍스트 → mock_evaluate에 전달
  - 강의 슬라이드 PDF → 핵심 개념 추출
  - 밴드 다이어그램 → MOSFET 동작 설명

보안 (P1 fix):
  - 경로는 VISION_UPLOAD_DIR env (기본 ./uploads/) 안으로 제한 (path traversal 방지)
  - 파일 크기 상한 VISION_MAX_BYTES env (기본 10MB) — 대용량 PDF로 인한 OOM/비용 폭주 방지
  - magic byte 검증 — 확장자 위장 공격(.png 인데 실제 ELF) 방지
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage


_DEFAULT_VISION_MODEL = os.getenv("LLM_MODEL_VISION", "google_genai:gemini-2.5-flash")


def _upload_dir() -> Path:
    """env 변수 lazy-read — monkeypatch friendly."""
    return Path(os.getenv("VISION_UPLOAD_DIR", "./uploads")).resolve()


def _max_bytes() -> int:
    return int(os.getenv("VISION_MAX_BYTES", "10485760"))  # 10 MB

# Magic byte signatures — 확장자만 검사하면 위장 가능. 실제 바이트로 검증.
_MAGIC_BYTES: dict[str, list[bytes]] = {
    "image/png":       [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg":      [b"\xff\xd8\xff"],
    "image/webp":      [b"RIFF"],  # RIFF....WEBP, 4~8바이트 추가 검증 가능하지만 prefix만 검사
    "application/pdf": [b"%PDF-"],
}


def _validate_path_within_upload_dir(image_path: str) -> Path:
    """upload 디렉토리 밖 경로 접근 차단 (path traversal 방지).

    상대 경로·절대 경로 모두 resolve해서 upload_dir 하위인지 확인.
    """
    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    resolved = Path(image_path).resolve()
    try:
        resolved.relative_to(upload_dir)
    except ValueError:
        raise PermissionError(
            f"허용되지 않은 경로입니다. {upload_dir} 하위 파일만 업로드 가능합니다."
        )
    return resolved


def _detect_mime_by_magic(data: bytes) -> str | None:
    for mime, signatures in _MAGIC_BYTES.items():
        for sig in signatures:
            if data.startswith(sig):
                return mime
    return None


def _encode_image(image_path: str) -> tuple[str, str]:
    """이미지 파일 읽어 base64 + mime_type 반환.

    Validates: (1) upload dir scope, (2) file size, (3) magic bytes.
    """
    p = _validate_path_within_upload_dir(image_path)
    if not p.exists():
        raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

    size = p.stat().st_size
    max_b = _max_bytes()
    if size > max_b:
        raise ValueError(
            f"파일 크기 {size:,} bytes가 상한 {max_b:,}을 초과합니다."
        )

    data = p.read_bytes()
    detected_mime = _detect_mime_by_magic(data[:16])
    if detected_mime is None:
        raise ValueError(
            "지원하지 않거나 위장된 파일 형식입니다. PNG/JPEG/WEBP/PDF만 허용됩니다."
        )

    return base64.standard_b64encode(data).decode("utf-8"), detected_mime


class GeminiVisionAnalyzer:
    """반도체 도식 분석 전용 Gemini 래퍼."""

    def __init__(self, model_spec: str | None = None) -> None:
        self._model_spec = model_spec or _DEFAULT_VISION_MODEL
        self._llm = init_chat_model(self._model_spec, temperature=0.2)

    def analyze(self, image_path: str, prompt: str) -> str:
        """이미지를 전문가 관점으로 분석.

        Args:
            image_path: 로컬 이미지 또는 PDF 파일 경로
            prompt: 분석 요청 텍스트 (예: "이 회로도를 설명하세요")

        Returns:
            Gemini 분석 결과 텍스트.
            실패 시 사용자 안내 메시지 (graceful degradation).
        """
        try:
            b64, mime = _encode_image(image_path)
        except (FileNotFoundError, ValueError, PermissionError) as e:
            return f"❌ 이미지 처리 실패: {e}"

        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                },
            ]
        )
        try:
            response = self._llm.invoke([message])
            return response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            return f"⚠️ Gemini 분석 일시 실패 ({type(exc).__name__})."
