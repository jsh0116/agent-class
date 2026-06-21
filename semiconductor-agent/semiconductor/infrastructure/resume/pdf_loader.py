"""공고/이력서 문서를 텍스트로 로드 — PDF/마크다운/텍스트.

보안 (vision.py와 동일 철학):
  - 크기 상한 RESUME_MAX_BYTES env (기본 10MB) — 대용량 PDF로 인한 OOM/비용 폭주 방지
  - 확장자 화이트리스트 (.pdf / .txt / .md) — 임의 파일 읽기 방지
  - symlink 거부 — 심볼릭 링크를 통한 우회 차단
  - PDF는 magic byte(%PDF-) 검증 — 확장자 위장 방지
  - RESUME_ALLOWED_DIR env가 설정되면 그 하위 경로만 허용 (상용화 멀티유저 대비).
    미설정 시(본인용)에는 임의 경로 허용하되 위 검증은 항상 적용.

pypdf는 PDF일 때만 lazy import — 텍스트/마크다운 경로는 의존성 없이 동작(테스트 친화적).
"""
from __future__ import annotations

import os
from pathlib import Path

_ALLOWED_EXT = {".pdf", ".txt", ".md"}
_PDF_MAGIC = b"%PDF-"


def _max_bytes() -> int:
    return int(os.getenv("RESUME_MAX_BYTES", "10485760"))  # 10 MB


def validate_document_path(path: str) -> Path:
    """문서 경로 보안 검증. 통과 시 resolved Path 반환, 아니면 예외."""
    if not path or not str(path).strip():
        raise ValueError("문서 경로가 비어있습니다.")

    p = Path(path)
    if p.is_symlink():
        raise PermissionError("심볼릭 링크는 허용되지 않습니다.")

    resolved = p.resolve()

    allowed_dir = os.getenv("RESUME_ALLOWED_DIR")
    if allowed_dir:
        base = Path(allowed_dir).resolve()
        try:
            resolved.relative_to(base)
        except ValueError:
            raise PermissionError(f"허용되지 않은 경로입니다. {base} 하위만 가능합니다.")

    if resolved.suffix.lower() not in _ALLOWED_EXT:
        raise ValueError(
            f"지원하지 않는 형식입니다: {resolved.suffix!r}. "
            f"{sorted(_ALLOWED_EXT)}만 허용됩니다."
        )

    if not resolved.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

    size = resolved.stat().st_size
    max_b = _max_bytes()
    if size > max_b:
        raise ValueError(f"파일 크기 {size:,} bytes가 상한 {max_b:,}을 초과합니다.")

    return resolved


def _pypdf_extract(path: Path) -> str:
    """PDF에서 텍스트 추출. pypdf lazy import (PDF 입력 시에만 필요)."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n".join(pages).strip()


def load_document_text(path: str) -> str:
    """문서를 텍스트로 로드. 확장자로 분기 (.pdf → pypdf, .txt/.md → 직접 읽기)."""
    resolved = validate_document_path(path)

    if resolved.suffix.lower() == ".pdf":
        head = resolved.read_bytes()[:8]
        if not head.startswith(_PDF_MAGIC):
            raise ValueError("PDF 형식이 아닙니다 (magic byte 불일치).")
        text = _pypdf_extract(resolved)
    else:
        text = resolved.read_text(encoding="utf-8", errors="replace").strip()

    if not text.strip():
        raise ValueError("문서에서 텍스트를 추출하지 못했습니다 (스캔 이미지 PDF일 수 있음).")
    return text
