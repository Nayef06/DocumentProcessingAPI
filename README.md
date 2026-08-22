# Async Document Processing Search API

Backend API for authenticated document uploads, asynchronous document processing, metadata storage, and searchable processed content.

## Tech Stack

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Redis
- Celery
- Docker Compose
- Pytest

## Features

- User registration and JWT login
- Authenticated document upload
- File metadata storage
- Background document processing with Celery and Redis
- Text extraction from uploaded documents
- Text chunk storage for search
- Search endpoint for processed document content
- Relational models for users, documents, processing jobs, and text chunks
- Alembic database migrations
- Docker Compose setup for API, worker, PostgreSQL, and Redis
- Pytest integration tests
- Auto-generated OpenAPI documentation at `/docs`

## Running the Project

Start the complete API, worker, PostgreSQL, and Redis stack:

```bash
docker compose up --build
```

Migrations run before the API starts and can also be run explicitly:

```bash
docker compose exec api alembic upgrade head
```

Stop the stack with `docker compose down`. Named volumes retain PostgreSQL data
and uploaded files; use `docker compose down -v` only when you intentionally want
to delete that data.

For local development outside Docker, copy `.env.example` to `.env`, install the
dependencies, and start the API:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```
