from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def test_register_succeeds(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "New.User@example.com", "password": "strong-password"},
    )

    assert response.status_code == 201
    assert response.json()["email"] == "new.user@example.com"
    assert "password" not in response.json()
    assert db_session.scalar(select(User).where(User.email == "new.user@example.com"))


def test_duplicate_registration_fails(
    client: TestClient,
    create_user: Callable[..., dict],
) -> None:
    create_user(email="duplicate@example.com")

    response = client.post(
        "/auth/register",
        json={"email": "duplicate@example.com", "password": "another-password"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Email is already registered"}


def test_registration_validates_email_and_password_without_echoing_password(
    client: TestClient,
) -> None:
    password = "short"

    response = client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": password},
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert password not in response.text


def test_login_succeeds(client: TestClient, user: dict) -> None:
    response = client.post(
        "/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_login_with_wrong_password_fails(client: TestClient, user: dict) -> None:
    response = client.post(
        "/auth/login",
        json={"email": user["email"], "password": "incorrect-password"},
    )

    assert response.status_code == 401


def test_auth_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_auth_me_rejects_invalid_jwt(client: TestClient) -> None:
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_auth_me_succeeds_with_valid_jwt(
    client: TestClient,
    user: dict,
    auth_headers: dict[str, str],
) -> None:
    response = client.get("/auth/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == user["id"]
    assert response.json()["email"] == user["email"]
