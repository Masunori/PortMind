"""Shared PostgreSQL adapter helpers."""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.repositories.errors import ConflictError, UnavailableError, ValidationError


def encode_offset(offset: int, limit: int) -> str:
    return base64.urlsafe_b64encode(f"v1:{offset + limit}".encode()).decode().rstrip("=")


def decode_offset(token: str | None) -> int:
    if token is None:
        return 0
    try:
        padded = token + "=" * (-len(token) % 4)
        version, value = base64.b64decode(padded, altchars=b"-_", validate=True).decode().split(":", 1)
        offset = int(value)
        if version != "v1" or offset < 0:
            raise ValueError
        return offset
    except (ValueError, UnicodeDecodeError) as error:
        raise ValidationError("invalid continuation token") from error


def validate_limit(limit: int) -> None:
    if not 1 <= limit <= 1000:
        raise ValidationError("limit must be between 1 and 1000")


def translate(error: SQLAlchemyError) -> None:
    if isinstance(error, IntegrityError):
        raise ConflictError("persistence constraint conflict") from error
    raise UnavailableError("persistence service unavailable") from error
