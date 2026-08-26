# Async Document Processing Search API

A backend API where users can upload documents, process them in the background, and search extracted text. I built it to practice using FastAPI, PostgreSQL, Celery, Redis, and Docker together.

## Tech Stack

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Redis
- Celery
- Docker / Docker Compose
- Pytest

## What It Does

1. A user registers and logs in.
2. The user uploads a `.txt` or `.pdf` file.
3. The API saves the file and stores its metadata in PostgreSQL.
4. When processing is requested, the API creates a `ProcessingJob`.
5. Celery queues the job through Redis.
6. A worker extracts the text and splits it into overlapping chunks.
7. The chunks and job status are stored in PostgreSQL.
8. The user can search text from their processed documents.

Documents and search results are limited to the user who owns them.

## Architecture

```text
Client
  |
  v
FastAPI --------------------> PostgreSQL
  |                         users, documents,
  |                         jobs, and text chunks
  v
Redis
  |
  v
Celery Worker
  |       |
  |       +-----------------> PostgreSQL
  v
Shared uploaded-file volume
```

FastAPI handles HTTP requests and Redis acts as the Celery message broker. The Celery worker does the document processing. PostgreSQL stores users, document metadata, processing jobs, and text chunks. The API and worker use the same Docker volume so both can access uploaded files.

## Database Models

- `User` stores an account and its password hash. A user can own many documents.
- `Document` stores ownership, file metadata, storage location, and processing status.
- `ProcessingJob` tracks one attempt to process a document, including its Celery task ID, status, timestamps, and any safe error message.
- `TextChunk` stores an ordered piece of extracted document text for full-text search.

The main relationships are:

```text
User
`-- Documents
    |-- ProcessingJobs
    `-- TextChunks
```

## API Endpoints

### Authentication

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/auth/register` | Create an account. |
| `POST` | `/auth/login` | Log in and get a JWT access token. |
| `GET` | `/auth/me` | Get the current user. |

### Documents

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/documents/upload` | Upload a `.txt` or `.pdf` document. |
| `GET` | `/documents` | List your documents. |
| `GET` | `/documents/{document_id}` | Get one document. |
| `GET` | `/documents/{document_id}/status` | Check a document's processing status. |
| `POST` | `/documents/{document_id}/process` | Queue background processing. |
| `DELETE` | `/documents/{document_id}` | Delete a document that is not being processed. |

### Processing Jobs

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/jobs/{job_id}` | Check a processing job. |

### Search

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/search?q={query}&limit={limit}` | Search your processed document chunks. |

### Health

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check whether the API is running. |

Most routes require a Bearer token. Full interactive API documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

## Running Locally

Docker and Docker Compose are the easiest way to run the project. Copy the example environment file first:

```bash
cp .env.example .env
```

On PowerShell, use `Copy-Item .env.example .env` instead. Replace `SECRET_KEY` with a random value of at least 32 characters before starting the app. One way to generate one is:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Build and start the API, worker, PostgreSQL, and Redis:

```bash
docker compose up --build
```

The API container runs `alembic upgrade head` before starting. To run the migration command yourself from another terminal:

```bash
docker compose exec api alembic upgrade head
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) after the API starts. Stop the services with `docker compose down`. PostgreSQL data and uploads stay in named volumes unless the volumes are removed.

## Example Flow

The Swagger UI at `/docs` is enough to try the main workflow:

1. Register with `POST /auth/register`.
2. Log in with `POST /auth/login` and copy the returned `access_token`.
3. Click **Authorize** in Swagger UI and enter the token.
4. Upload a file with `POST /documents/upload`.
5. Use the returned document ID with `POST /documents/{document_id}/process`.
6. Check `/jobs/{job_id}` or `/documents/{document_id}/status` until processing finishes.
7. Search the extracted text with `GET /search`.

## Testing

With the Compose stack running, run:

```bash
docker compose exec api pytest
```

The integration tests cover authentication, upload validation, document ownership, processing, search, error responses, and OpenAPI output. They use a separate PostgreSQL test database and run Celery tasks eagerly, so a worker is not needed for the test itself.

For local test runs outside Docker, PostgreSQL must be available and `TEST_DATABASE_URL` must point to a database separate from `DATABASE_URL`:

```bash
pytest
```

## Project Structure

```text
.
|-- alembic/                 # Migration setup and migration files
|-- app/
|   |-- api/                 # Route handlers and API dependencies
|   |-- core/                # Settings and JWT/password helpers
|   |-- db/                  # SQLAlchemy engine and base model
|   |-- models/              # Database models
|   |-- schemas/             # Request and response schemas
|   |-- services/            # Storage, extraction, chunking, and search
|   |-- worker/              # Celery app and processing task
|   `-- main.py              # FastAPI application
|-- tests/                   # Pytest integration tests
|-- .env.example             # Example local settings
|-- docker-compose.yml       # API, worker, PostgreSQL, and Redis
|-- Dockerfile
`-- requirements.txt
```

## Notes / Limitations

- Only `.txt` files and text-based PDFs are supported.
- Scanned PDFs need OCR, which this project does not include.
- Uploaded files use local storage or a shared Docker volume, not cloud storage.
- Search uses PostgreSQL full-text search, not embeddings or vector search.
- There is no frontend; the API can be used through Swagger UI or another HTTP client.
