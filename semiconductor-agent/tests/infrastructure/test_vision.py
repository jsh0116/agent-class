"""TDD: Gemini vision analyzer + 경로/크기/magic byte 보안 검증."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from semiconductor.infrastructure.tools.vision import GeminiVisionAnalyzer, _encode_image


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch):
    """tmp_path를 VISION_UPLOAD_DIR로 설정 — 보안 검증을 격리 환경에서."""
    d = tmp_path / "uploads"
    d.mkdir()
    monkeypatch.setenv("VISION_UPLOAD_DIR", str(d))
    return d


# ── _encode_image ────────────────────────────────────────────────


class TestEncodeImage:
    def test_png_파일_정상_인코딩(self, upload_dir: Path):
        f = upload_dir / "test.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        b64, mime = _encode_image(str(f))
        assert mime == "image/png"
        assert isinstance(b64, str) and len(b64) > 0

    def test_jpg_jpeg_둘다_인식(self, upload_dir: Path):
        for ext in ("jpg", "jpeg"):
            f = upload_dir / f"test.{ext}"
            f.write_bytes(b"\xff\xd8\xff\xe0fake")
            _, mime = _encode_image(str(f))
            assert mime == "image/jpeg"

    def test_webp_인식(self, upload_dir: Path):
        f = upload_dir / "test.webp"
        f.write_bytes(b"RIFFfake")
        _, mime = _encode_image(str(f))
        assert mime == "image/webp"

    def test_pdf_인식(self, upload_dir: Path):
        f = upload_dir / "doc.pdf"
        f.write_bytes(b"%PDF-1.4 fake")
        _, mime = _encode_image(str(f))
        assert mime == "application/pdf"

    def test_파일_없으면_FileNotFoundError(self, upload_dir: Path):
        # 경로는 upload_dir 안이지만 파일 없음
        with pytest.raises(FileNotFoundError):
            _encode_image(str(upload_dir / "nonexistent.png"))


class TestPathTraversal:
    """P1 보안: upload_dir 밖 경로 차단."""

    def test_절대경로_etc_passwd_접근_차단(self, upload_dir: Path):
        with pytest.raises(PermissionError, match="허용되지 않은 경로"):
            _encode_image("/etc/passwd")

    def test_상대경로_dotdot_탈출_차단(self, upload_dir: Path):
        # ../../etc/passwd 같은 시도
        outside = upload_dir.parent / "secret.png"
        outside.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        with pytest.raises(PermissionError, match="허용되지 않은 경로"):
            _encode_image(str(outside))

    def test_심볼릭_링크로_탈출_차단(self, upload_dir: Path, tmp_path: Path):
        # symlink → upload_dir 밖. resolve()가 따라가서 차단
        target = tmp_path / "outside.png"
        target.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        link = upload_dir / "link.png"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("심볼릭 링크 권한 없음")
        with pytest.raises(PermissionError):
            _encode_image(str(link))


class TestFileSizeLimit:
    """P1 보안: 대용량 파일로 인한 OOM/비용 폭주 방지."""

    def test_상한_초과시_ValueError(self, upload_dir: Path, monkeypatch):
        monkeypatch.setenv("VISION_MAX_BYTES", "100")  # 100 bytes 상한
        f = upload_dir / "big.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"A" * 1000)  # 1KB > 100B
        with pytest.raises(ValueError, match="파일 크기"):
            _encode_image(str(f))

    def test_상한_이하는_정상(self, upload_dir: Path, monkeypatch):
        monkeypatch.setenv("VISION_MAX_BYTES", "10000")
        f = upload_dir / "ok.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\nfake")  # 작음
        b64, _ = _encode_image(str(f))
        assert b64


class TestMagicBytes:
    """P1 보안: 확장자 위장 차단 — 실제 바이트로 형식 판별."""

    def test_확장자_png인데_내용_ELF면_거부(self, upload_dir: Path):
        # 악의: .png로 위장한 ELF 바이너리
        f = upload_dir / "fake.png"
        f.write_bytes(b"\x7fELF\x02\x01\x01")  # ELF magic
        with pytest.raises(ValueError, match="지원하지 않거나 위장된"):
            _encode_image(str(f))

    def test_확장자_jpg인데_PDF_헤더면_PDF로_인식(self, upload_dir: Path):
        # 위장 아니라 단순 잘못된 확장자 → magic byte 우선 → 정상 처리
        f = upload_dir / "mislabeled.jpg"
        f.write_bytes(b"%PDF-1.4 fake")
        _, mime = _encode_image(str(f))
        assert mime == "application/pdf"  # magic byte 기반

    def test_빈_파일_거부(self, upload_dir: Path):
        f = upload_dir / "empty.png"
        f.write_bytes(b"")
        with pytest.raises(ValueError, match="지원하지 않거나 위장된"):
            _encode_image(str(f))

    def test_랜덤_바이너리_거부(self, upload_dir: Path):
        f = upload_dir / "random.png"
        f.write_bytes(b"\x00\x01\x02random_garbage_data")
        with pytest.raises(ValueError, match="지원하지 않거나 위장된"):
            _encode_image(str(f))


# ── GeminiVisionAnalyzer ─────────────────────────────────────────


class TestGeminiVisionAnalyzer:
    @patch("semiconductor.infrastructure.tools.vision.init_chat_model")
    def test_생성시_init_chat_model_호출_default_gemini(self, mock_init):
        mock_init.return_value = MagicMock()
        GeminiVisionAnalyzer()
        spec = mock_init.call_args.args[0]
        assert spec == "google_genai:gemini-2.5-flash"

    @patch("semiconductor.infrastructure.tools.vision.init_chat_model")
    def test_명시_model_spec으로_재정의_가능(self, mock_init):
        mock_init.return_value = MagicMock()
        GeminiVisionAnalyzer(model_spec="google_genai:gemini-2.5-pro")
        spec = mock_init.call_args.args[0]
        assert spec == "google_genai:gemini-2.5-pro"

    @patch("semiconductor.infrastructure.tools.vision.init_chat_model")
    def test_analyze_이미지를_base64로_변환해_invoke에_전달(
        self, mock_init, upload_dir: Path
    ):
        llm = MagicMock()
        response = MagicMock()
        response.content = "회로 분석 결과"
        llm.invoke.return_value = response
        mock_init.return_value = llm

        f = upload_dir / "circuit.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\nfake")

        analyzer = GeminiVisionAnalyzer()
        result = analyzer.analyze(str(f), "이 회로를 분석해줘")

        assert result == "회로 분석 결과"
        msgs = llm.invoke.call_args.args[0]
        content = msgs[0].content
        assert any(
            block.get("type") == "image_url" for block in content if isinstance(block, dict)
        )

    @patch("semiconductor.infrastructure.tools.vision.init_chat_model")
    def test_path_traversal_시도시_안내_메시지(self, mock_init, upload_dir: Path):
        mock_init.return_value = MagicMock()
        analyzer = GeminiVisionAnalyzer()
        result = analyzer.analyze("/etc/passwd", "분석")
        assert "❌" in result
        assert "허용되지 않은 경로" in result

    @patch("semiconductor.infrastructure.tools.vision.init_chat_model")
    def test_LLM_실패시_graceful_degradation(self, mock_init, upload_dir: Path):
        llm = MagicMock()
        llm.invoke.side_effect = Exception("API timeout")
        mock_init.return_value = llm

        f = upload_dir / "x.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\nfake")

        analyzer = GeminiVisionAnalyzer()
        result = analyzer.analyze(str(f), "분석")
        assert "⚠️" in result
        assert "Gemini" in result
