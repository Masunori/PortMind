"""Deterministic DynamoDB serialization, tokens, and evidence chunking."""

from __future__ import annotations

import base64
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import hmac
import json
import math
from typing import Any

from app.repositories.errors import ValidationError

MAX_EVIDENCE_BYTES = 256 * 1024
MAX_CHUNK_BYTES = 64 * 1024


def encode_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValidationError("datetimes must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return encode_value(value.value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError("non-finite numbers cannot be stored")
        return Decimal(str(value))
    if isinstance(value, dict):
        return {str(key): encode_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode_value(item) for item in value]
    if isinstance(value, set):
        return [encode_value(item) for item in sorted(value, key=str)]
    return value


TOKEN_VERSION = 1
MAX_TOKEN_BYTES = 16 * 1024


def encode_token(
    last_evaluated_key: dict[str, Any] | None, *, query_identity: str = "default"
) -> str | None:
    if not last_evaluated_key:
        return None
    body = {"v": TOKEN_VERSION, "q": query_identity, "k": _token_value(last_evaluated_key)}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    envelope = {"p": body, "d": hashlib.sha256(canonical.encode()).hexdigest()}
    payload = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    if len(payload.encode()) > MAX_TOKEN_BYTES:
        raise ValidationError("continuation token is too large")
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_token(token: str | None, *, query_identity: str = "default") -> dict[str, Any] | None:
    if token is None:
        return None
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
        if len(raw) > MAX_TOKEN_BYTES:
            raise ValueError("token too large")
        envelope = json.loads(raw)
        if not isinstance(envelope, dict) or set(envelope) != {"p", "d"}:
            raise ValueError("invalid envelope")
        body = envelope["p"]
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        if not isinstance(envelope["d"], str) or not hmac.compare_digest(
            envelope["d"], hashlib.sha256(canonical.encode()).hexdigest()
        ):
            raise ValueError("token digest mismatch")
        if not isinstance(body, dict) or body.get("v") != TOKEN_VERSION:
            raise ValueError("unsupported token version")
        if body.get("q") != query_identity:
            raise ValueError("token belongs to another query")
        value = _untoken_value(body.get("k"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError("invalid continuation token") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValidationError("invalid continuation token")
    return value


def _token_value(value: Any) -> Any:
    """Encode DynamoDB key primitives without relying on boto3's wire format."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, bytes):
        return {"$binary": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _token_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_token_value(item) for item in value]
    raise ValidationError("continuation token contains an unsupported value")


def _untoken_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_untoken_value(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {"$decimal"} and isinstance(value["$decimal"], str):
            try:
                return Decimal(value["$decimal"])
            except ArithmeticError as error:
                raise ValueError("invalid decimal") from error
        if set(value) == {"$binary"} and isinstance(value["$binary"], str):
            return base64.b64decode(value["$binary"], validate=True)
        return {key: _untoken_value(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    raise ValueError("invalid token value")


def decode_value(value: Any) -> Any:
    """Convert SDK values into JSON/Pydantic-friendly Python values recursively."""

    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: decode_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_value(item) for item in value]
    if isinstance(value, set):
        return [decode_value(item) for item in sorted(value, key=str)]
    return value


def chunk_content(content: str) -> tuple[list[bytes], str]:
    raw = content.encode("utf-8")
    if len(raw) > MAX_EVIDENCE_BYTES:
        raise ValidationError("evidence content exceeds 256 KiB")
    chunks: list[bytes] = []
    offset = 0
    while offset < len(raw):
        end = min(offset + MAX_CHUNK_BYTES, len(raw))
        while end > offset:
            try:
                raw[offset:end].decode("utf-8")
                break
            except UnicodeDecodeError:
                end -= 1
        chunks.append(raw[offset:end])
        offset = end
    return chunks, hashlib.sha256(raw).hexdigest()


def reconstruct_content(chunks: list[bytes]) -> str:
    try:
        return b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError("stored evidence content is not valid UTF-8") from error
