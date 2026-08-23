from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.text_chunk import TextChunk


def test_processed_text_can_be_found_with_document_and_chunk_data(
    client: TestClient,
    auth_headers: dict[str, str],
    upload_text: Callable[..., dict],
    process_document: Callable[..., dict],
) -> None:
    uploaded = upload_text(
        "The quokka observatory tracks unusual celestial signals.",
        "astronomy.txt",
        auth_headers,
    )
    process_document(uploaded["id"], auth_headers)

    response = client.get("/search", params={"q": "quokka"}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["query"] == "quokka"
    assert len(response.json()["results"]) == 1
    result = response.json()["results"][0]
    assert result["document_id"] == uploaded["id"]
    assert result["original_filename"] == "astronomy.txt"
    assert result["chunk_id"] > 0
    assert result["chunk_index"] == 0
    assert "quokka observatory" in result["snippet"]
    assert result["score"] > 0


def test_unrelated_query_returns_no_results(
    client: TestClient,
    auth_headers: dict[str, str],
    upload_text: Callable[..., dict],
    process_document: Callable[..., dict],
) -> None:
    uploaded = upload_text("Orchids grow in the greenhouse.", headers=auth_headers)
    process_document(uploaded["id"], auth_headers)

    response = client.get(
        "/search",
        params={"q": "submarine"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_user_cannot_search_another_users_content(
    client: TestClient,
    create_user: Callable[..., dict],
    auth_headers_for: Callable[[dict], dict[str, str]],
    upload_text: Callable[..., dict],
    process_document: Callable[..., dict],
) -> None:
    owner = create_user()
    other_user = create_user()
    owner_headers = auth_headers_for(owner)
    other_headers = auth_headers_for(other_user)
    uploaded = upload_text("Confidential narwhal migration notes.", headers=owner_headers)
    process_document(uploaded["id"], owner_headers)

    response = client.get(
        "/search",
        params={"q": "narwhal"},
        headers=other_headers,
    )

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_unprocessed_documents_are_excluded(
    client: TestClient,
    auth_headers: dict[str, str],
    upload_text: Callable[..., dict],
    db_session: Session,
) -> None:
    uploaded = upload_text(
        "A pending document mentions capybaras.",
        headers=auth_headers,
    )
    db_session.add(
        TextChunk(
            document_id=uploaded["id"],
            chunk_index=0,
            content="A pending document mentions capybaras.",
        )
    )
    db_session.commit()

    response = client.get(
        "/search",
        params={"q": "capybaras"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["results"] == []
