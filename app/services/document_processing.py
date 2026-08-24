import logging
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.text_chunk import TextChunk
from app.services.chunking import chunk_text
from app.services.extraction import TextExtractionError, extract_text


logger = logging.getLogger(__name__)


class DocumentNotFoundError(Exception):
    """Raised when a document cannot be found for processing."""


class DocumentProcessingError(Exception):
    """Raised with a client-safe message after document processing fails."""


def process_document(document_id: int, db: Session) -> Document:
    """Synchronously extract, chunk, and persist one document's text."""
    document = db.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError(f"Document {document_id} was not found")

    try:
        logger.info("Document processing started document_id=%s", document_id)
        document.status = "PROCESSING"
        db.commit()
        db.refresh(document)

        storage_path = Path(document.storage_path)
        if not storage_path.is_file():
            raise FileNotFoundError(f"Stored file does not exist: {storage_path}")

        text = extract_text(storage_path, document.content_type)
        chunks = chunk_text(text)
        if not chunks:
            raise ValueError("Document contains no text to chunk")

        db.execute(delete(TextChunk).where(TextChunk.document_id == document.id))
        db.add_all(
            TextChunk(
                document_id=document.id,
                chunk_index=chunk_index,
                content=content,
                token_count=None,
            )
            for chunk_index, content in enumerate(chunks)
        )
        document.status = "PROCESSED"
        db.commit()
        db.refresh(document)
        logger.info(
            "Document processing completed document_id=%s chunks=%s",
            document_id,
            len(chunks),
        )
        return document
    except Exception as exc:
        db.rollback()
        logger.exception("Processing failed for document %s: %s", document_id, exc)

        try:
            failed_document = db.get(Document, document_id)
            if failed_document is not None:
                failed_document.status = "FAILED"
                db.commit()
                db.refresh(failed_document)
        except Exception:
            db.rollback()
            logger.exception("Could not mark document %s as FAILED", document_id)

        if isinstance(exc, TextExtractionError):
            public_message = "Document text extraction failed"
        elif isinstance(exc, FileNotFoundError):
            public_message = "Stored document file is unavailable"
        else:
            public_message = "Document processing failed"
        raise DocumentProcessingError(public_message) from exc
