from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str


class ValidationIssue(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ValidationErrorResponse(BaseModel):
    detail: list[ValidationIssue]


def sanitized_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return useful validation details without echoing submitted values."""
    return [
        {
            "loc": list(error["loc"]),
            "msg": error["msg"],
            "type": error["type"],
        }
        for error in errors
    ]
