from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.processing_job import ProcessingJob
from app.models.text_chunk import TextChunk
from app.worker.celery_app import celery_app


def test_database_prevents_two_active_jobs_for_one_document(
    auth_headers: dict[str, str],
    upload_text: Callable[..., dict],
    db_session: Session,
) -> None:
    uploaded = upload_text("concurrent processing", headers=auth_headers)
    db_session.add_all(
        [
            ProcessingJob(document_id=uploaded["id"], status="QUEUED"),
            ProcessingJob(document_id=uploaded["id"], status="STARTED"),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_processing_text_document_runs_eagerly_and_persists_results(
    auth_headers: dict[str, str],
    upload_text: Callable[..., dict],
    process_document: Callable[..., dict],
    db_session: Session,
) -> None:
    content = "first searchable section " * 70
    uploaded = upload_text(content, "processable.txt", auth_headers)

    queued = process_document(uploaded["id"], auth_headers)
    db_session.expire_all()
    job = db_session.get(ProcessingJob, queued["job_id"])
    document = db_session.get(Document, uploaded["id"])
    chunks = list(
        db_session.scalars(
            select(TextChunk)
            .where(TextChunk.document_id == uploaded["id"])
            .order_by(TextChunk.chunk_index)
        )
    )

    assert celery_app.conf.task_always_eager is True
    assert celery_app.conf.task_eager_propagates is True
    assert queued["status"] == "QUEUED"
    assert job is not None and job.status == "SUCCESS"
    assert job.started_at is not None
    assert job.finished_at is not None
    assert job.celery_task_id
    assert document is not None and document.status == "PROCESSED"
    assert len(chunks) >= 2
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_reprocessing_does_not_duplicate_chunks(
    auth_headers: dict[str, str],
    upload_text: Callable[..., dict],
    process_document: Callable[..., dict],
    db_session: Session,
) -> None:
    uploaded = upload_text("repeatable content " * 100, headers=auth_headers)
    process_document(uploaded["id"], auth_headers)
    first_count = db_session.scalar(
        select(func.count(TextChunk.id)).where(
            TextChunk.document_id == uploaded["id"]
        )
    )

    process_document(uploaded["id"], auth_headers)
    db_session.expire_all()
    second_count = db_session.scalar(
        select(func.count(TextChunk.id)).where(
            TextChunk.document_id == uploaded["id"]
        )
    )
    chunk_indexes = list(
        db_session.scalars(
            select(TextChunk.chunk_index)
            .where(TextChunk.document_id == uploaded["id"])
            .order_by(TextChunk.chunk_index)
        )
    )

    assert second_count == first_count
    assert chunk_indexes == list(range(second_count or 0))


def test_failed_processing_marks_document_and_job_failed(
    client: TestClient,
    auth_headers: dict[str, str],
    upload_text: Callable[..., dict],
    db_session: Session,
) -> None:
    uploaded = upload_text("!!!", "invalid.txt", auth_headers)

    response = client.post(
        f"/documents/{uploaded['id']}/process",
        headers=auth_headers,
    )
    db_session.expire_all()
    document = db_session.get(Document, uploaded["id"])
    job = db_session.scalar(
        select(ProcessingJob).where(
            ProcessingJob.document_id == uploaded["id"]
        )
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Document text extraction failed"}
    assert document is not None and document.status == "FAILED"
    assert job is not None and job.status == "FAILED"
    assert job.started_at is not None
    assert job.finished_at is not None
    assert job.error_message == "Document text extraction failed"
