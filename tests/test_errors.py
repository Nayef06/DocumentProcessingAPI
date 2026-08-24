from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user


def test_unexpected_errors_return_sanitized_response(app: FastAPI) -> None:
    def fail_authentication_dependency() -> None:
        raise RuntimeError("database driver exploded")

    app.dependency_overrides[get_current_user] = fail_authentication_dependency

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/auth/me")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "database driver exploded" not in response.text
