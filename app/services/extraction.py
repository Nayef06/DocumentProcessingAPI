from pathlib import Path

from pypdf import PdfReader


class TextExtractionError(Exception):
    """Raised when readable, meaningful text cannot be extracted from a document."""


def _normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return "\n".join(line.rstrip() for line in normalized.split("\n")).strip()


def _extract_txt(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise TextExtractionError(f"Could not read text file: {exc}") from exc


def _extract_pdf(file_path: Path) -> str:
    try:
        reader = PdfReader(file_path)
        page_text = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise TextExtractionError(f"Could not read PDF file: {exc}") from exc
    return "\n\n".join(page_text)


def extract_text(file_path: str | Path, content_type: str | None = None) -> str:
    """Extract and normalize text from a supported local document."""
    path = Path(file_path)
    if not path.is_file():
        raise TextExtractionError(f"Stored file does not exist: {path}")

    extension = path.suffix.lower()
    normalized_content_type = (content_type or "").lower().split(";", maxsplit=1)[0]

    if extension == ".txt" or (
        not extension and normalized_content_type == "text/plain"
    ):
        extracted = _extract_txt(path)
    elif extension == ".pdf" or (
        not extension and normalized_content_type == "application/pdf"
    ):
        extracted = _extract_pdf(path)
    else:
        raise TextExtractionError(
            f"Unsupported document type: {extension or normalized_content_type or 'unknown'}"
        )

    normalized = _normalize_text(extracted)
    if not normalized or not any(character.isalnum() for character in normalized):
        raise TextExtractionError("Document contains no meaningful extractable text")
    return normalized
