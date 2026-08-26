import os
import re
from collections.abc import Callable, Generator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_DATABASE_URL = (
    "postgresql+psycopg2://postgres:postgres@localhost:5432/"
    "async_document_processing"
)
TEST_PASSWORD = "integration-password"


def _test_database_url() -> tuple[URL, URL]:
    development_url = make_url(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
    configured_test_url = os.getenv("TEST_DATABASE_URL")
    test_url = (
        make_url(configured_test_url)
        if configured_test_url
        else development_url.set(database=f"{development_url.database}_test")
    )

    if test_url.database == development_url.database:
        raise RuntimeError("TEST_DATABASE_URL must not point to the development database")
    if not test_url.database or not re.fullmatch(r"[A-Za-z0-9_-]+", test_url.database):
        raise RuntimeError("The test database name contains unsupported characters")
    if "test" not in test_url.database.lower():
        raise RuntimeError("The test database name must contain 'test'")
    if not test_url.drivername.startswith("postgresql"):
        raise RuntimeError("Integration tests require PostgreSQL")

    return development_url, test_url


DEVELOPMENT_DATABASE_URL, TEST_DATABASE_URL = _test_database_url()

# Application modules read settings at import time, so point every application
# session (including Celery task sessions) at PostgreSQL's isolated test database.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL.render_as_string(hide_password=False)
os.environ.setdefault(
    "SECRET_KEY",
    "integration-test-secret-key-at-least-32-characters",
)

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models import Document, ProcessingJob, TextChunk, User  # noqa: E402, F401
from app.worker.celery_app import celery_app  # noqa: E402


@pytest.fixture(scope="session")
def test_engine() -> Generator[Engine, None, None]:
    admin_url = TEST_DATABASE_URL.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    database_name = TEST_DATABASE_URL.database

    with admin_engine.connect() as connection:
        exists = connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
            {"database_name": database_name},
        )
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    admin_engine.dispose()

    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(test_engine: Engine) -> Generator[None, None, None]:
    table_names = "text_chunks, processing_jobs, documents, users"
    with test_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
    yield
    with test_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session", autouse=True)
def eager_celery() -> Generator[None, None, None]:
    previous_always_eager = celery_app.conf.task_always_eager
    previous_eager_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )
    yield
    celery_app.conf.update(
        task_always_eager=previous_always_eager,
        task_eager_propagates=previous_eager_propagates,
    )


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path / "uploads")
    fastapi_app.dependency_overrides.clear()
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session(test_engine: Engine) -> Generator[Session, None, None]:
    session_factory = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def create_user(client: TestClient) -> Callable[..., dict]:
    def _create_user(
        email: str | None = None,
        password: str = TEST_PASSWORD,
    ) -> dict:
        email = email or f"user-{uuid4().hex}@example.com"
        response = client.post(
            "/auth/register",
            json={"email": email, "password": password},
        )
        assert response.status_code == 201, response.text
        return {**response.json(), "password": password}

    return _create_user


@pytest.fixture
def user(create_user: Callable[..., dict]) -> dict:
    return create_user()


@pytest.fixture
def auth_headers_for(client: TestClient) -> Callable[[dict], dict[str, str]]:
    def _auth_headers_for(user_data: dict) -> dict[str, str]:
        response = client.post(
            "/auth/login",
            json={
                "email": user_data["email"],
                "password": user_data["password"],
            },
        )
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _auth_headers_for


@pytest.fixture
def auth_headers(
    user: dict,
    auth_headers_for: Callable[[dict], dict[str, str]],
) -> dict[str, str]:
    return auth_headers_for(user)


@pytest.fixture
def upload_text(
    client: TestClient,
    auth_headers: dict[str, str],
) -> Callable[..., dict]:
    def _upload_text(
        content: str = "A searchable integration test document.",
        filename: str = "document.txt",
        headers: dict[str, str] | None = None,
    ) -> dict:
        response = client.post(
            "/documents/upload",
            headers=headers or auth_headers,
            files={"file": (filename, content.encode(), "text/plain")},
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _upload_text


@pytest.fixture
def process_document(client: TestClient) -> Callable[..., dict]:
    def _process_document(document_id: int, headers: dict[str, str]) -> dict:
        response = client.post(
            f"/documents/{document_id}/process",
            headers=headers,
        )
        assert response.status_code == 202, response.text
        return response.json()

    return _process_document
