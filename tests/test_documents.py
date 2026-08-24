from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.processing_job import ProcessingJob
from app.core.config import settings


def test_unauthenticated_upload_fails(client: TestClient) -> None:
    response = client.post(
        "/documents/upload",
        files={"file": ("private.txt", b"private text", "text/plain")},
    )

    assert response.status_code == 401


def test_upload_rejects_unsupported_empty_and_oversized_files(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    unsupported = client.post(
        "/documents/upload",
        headers=auth_headers,
        files={"file": ("image.png", b"content", "image/png")},
    )
    empty = client.post(
        "/documents/upload",
        headers=auth_headers,
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    oversized = client.post(
        "/documents/upload",
        headers=auth_headers,
        files={"file": ("large.txt", b"x" * (1024 * 1024 + 1), "text/plain")},
    )

    assert unsupported.status_code == 415
    assert empty.status_code == 422
    assert oversized.status_code == 413


def test_authenticated_text_upload_creates_pending_owned_document(
    user: dict,
    auth_headers: dict[str, str],
    upload_text: Callable[..., dict],
    db_session: Session,
) -> None:
    uploaded = upload_text("uploaded content", "notes.txt", auth_headers)
    document = db_session.get(Document, uploaded["id"])

    assert uploaded["original_filename"] == "notes.txt"
    assert uploaded["status"] == "PENDING"
    assert document is not None
    assert document.user_id == user["id"]
    assert document.status == "PENDING"
    assert document.metadata_json == {"extension": ".txt"}
    assert Path(document.storage_path).read_text() == "uploaded content"


def test_list_documents_only_returns_current_users_documents(
    client: TestClient,
    create_user: Callable[..., dict],
    auth_headers_for: Callable[[dict], dict[str, str]],
    upload_text: Callable[..., dict],
) -> None:
    first_user = create_user()
    second_user = create_user()
    first_headers = auth_headers_for(first_user)
    second_headers = auth_headers_for(second_user)
    first_document = upload_text("first user's text", "first.txt", first_headers)
    upload_text("second user's text", "second.txt", second_headers)

    response = client.get("/documents", headers=first_headers)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [first_document["id"]]


def test_user_cannot_access_another_users_document(
    client: TestClient,
    create_user: Callable[..., dict],
    auth_headers_for: Callable[[dict], dict[str, str]],
    upload_text: Callable[..., dict],
) -> None:
    owner = create_user()
    other_user = create_user()
    document = upload_text("owner only", headers=auth_headers_for(owner))

    response = client.get(
        f"/documents/{document['id']}",
        headers=auth_headers_for(other_user),
    )

    assert response.status_code == 404


def test_document_ids_must_be_positive_and_missing_documents_return_404(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    invalid = client.get("/documents/0", headers=auth_headers)
    missing = client.get("/documents/999999", headers=auth_headers)

    assert invalid.status_code == 422
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Document not found"}


def test_active_processing_conflicts_with_processing_and_deletion(
    client: TestClient,
    auth_headers: dict[str, str],
    upload_text: Callable[..., dict],
    db_session: Session,
) -> None:
    uploaded = upload_text("still processing", headers=auth_headers)
    db_session.add(ProcessingJob(document_id=uploaded["id"], status="QUEUED"))
    db_session.commit()

    process_response = client.post(
        f"/documents/{uploaded['id']}/process",
        headers=auth_headers,
    )
    delete_response = client.delete(
        f"/documents/{uploaded['id']}",
        headers=auth_headers,
    )

    assert process_response.status_code == 409
    assert delete_response.status_code == 409


def test_delete_works_for_owner(
    client: TestClient,
    auth_headers: dict[str, str],
    upload_text: Callable[..., dict],
    db_session: Session,
) -> None:
    uploaded = upload_text("delete me", headers=auth_headers)
    document = db_session.get(Document, uploaded["id"])
    assert document is not None
    storage_path = Path(document.storage_path)

    response = client.delete(
        f"/documents/{uploaded['id']}",
        headers=auth_headers,
    )
    db_session.expire_all()

    assert response.status_code == 204
    assert db_session.get(Document, uploaded["id"]) is None
    assert not storage_path.exists()


def test_another_user_cannot_delete_document(
    client: TestClient,
    create_user: Callable[..., dict],
    auth_headers_for: Callable[[dict], dict[str, str]],
    upload_text: Callable[..., dict],
    db_session: Session,
) -> None:
    owner = create_user()
    other_user = create_user()
    uploaded = upload_text("keep me", headers=auth_headers_for(owner))

    response = client.delete(
        f"/documents/{uploaded['id']}",
        headers=auth_headers_for(other_user),
    )

    assert response.status_code == 404
    assert db_session.get(Document, uploaded["id"]) is not None
