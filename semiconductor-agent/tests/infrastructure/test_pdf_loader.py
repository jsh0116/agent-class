"""TDD: 문서 로더 보안 검증 + 텍스트/PDF 분기.

PDF 추출(pypdf)은 monkeypatch로 격리 — pypdf 미설치 환경에서도 로직 검증 가능.
"""
import pytest

from semiconductor.infrastructure.resume import pdf_loader
from semiconductor.infrastructure.resume.pdf_loader import (
    load_document_text,
    validate_document_path,
)


class TestValidateDocumentPath:
    def test_md_파일_통과(self, tmp_path):
        f = tmp_path / "resume.md"
        f.write_text("내용", encoding="utf-8")
        assert validate_document_path(str(f)).name == "resume.md"

    def test_빈_경로_거부(self):
        with pytest.raises(ValueError, match="비어있"):
            validate_document_path("   ")

    def test_허용되지_않은_확장자_거부(self, tmp_path):
        f = tmp_path / "secret.env"
        f.write_text("KEY=1", encoding="utf-8")
        with pytest.raises(ValueError, match="지원하지 않는 형식"):
            validate_document_path(str(f))

    def test_존재하지_않는_파일_거부(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            validate_document_path(str(tmp_path / "nope.pdf"))

    def test_크기_초과_거부(self, tmp_path, monkeypatch):
        f = tmp_path / "big.txt"
        f.write_text("x" * 100, encoding="utf-8")
        monkeypatch.setenv("RESUME_MAX_BYTES", "10")
        with pytest.raises(ValueError, match="상한"):
            validate_document_path(str(f))

    def test_symlink_거부(self, tmp_path):
        target = tmp_path / "real.md"
        target.write_text("x", encoding="utf-8")
        link = tmp_path / "link.md"
        link.symlink_to(target)
        with pytest.raises(PermissionError, match="심볼릭"):
            validate_document_path(str(link))

    def test_allowed_dir_밖_경로_거부(self, tmp_path, monkeypatch):
        outside = tmp_path / "outside.md"
        outside.write_text("x", encoding="utf-8")
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        monkeypatch.setenv("RESUME_ALLOWED_DIR", str(allowed))
        with pytest.raises(PermissionError, match="허용되지 않은 경로"):
            validate_document_path(str(outside))


class TestLoadDocumentText:
    def test_md_직접_읽기(self, tmp_path):
        f = tmp_path / "resume.md"
        f.write_text("수강: 반도체공학", encoding="utf-8")
        assert "반도체공학" in load_document_text(str(f))

    def test_빈_문서_거부(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("   ", encoding="utf-8")
        with pytest.raises(ValueError, match="추출하지 못"):
            load_document_text(str(f))

    def test_pdf는_pypdf로_분기(self, tmp_path, monkeypatch):
        f = tmp_path / "posting.pdf"
        f.write_bytes(b"%PDF-1.4 fake")
        monkeypatch.setattr(pdf_loader, "_pypdf_extract", lambda p: "공고 본문 텍스트")
        assert load_document_text(str(f)) == "공고 본문 텍스트"

    def test_pdf_magic_byte_위장_거부(self, tmp_path, monkeypatch):
        f = tmp_path / "fake.pdf"
        f.write_bytes(b"NOTPDF")
        monkeypatch.setattr(pdf_loader, "_pypdf_extract", lambda p: "x")
        with pytest.raises(ValueError, match="magic byte"):
            load_document_text(str(f))
