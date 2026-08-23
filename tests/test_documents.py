from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.document import Document


def test_unauthenticated_upload_fails(client: TestClient) -> None:
    response = client.post(
        "/documents/upload",
        files={"file": ("private.txt", b"private text", "text/plain")},
    )

    assert response.status_code == 401


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
