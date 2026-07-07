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

Start all services:

```bash
docker compose up --build