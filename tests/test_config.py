from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_example_environment_loads_as_documented() -> None:
    example_environment = Path(__file__).parents[1] / ".env.example"

    loaded = Settings(_env_file=example_environment)

    assert loaded.SECRET_KEY
    assert loaded.DATABASE_URL.startswith("postgresql+psycopg2://")


def test_secret_key_must_be_at_least_32_characters() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(
            DATABASE_URL="postgresql+psycopg2://user:password@localhost/database",
            SECRET_KEY="too-short",
            _env_file=None,
        )
