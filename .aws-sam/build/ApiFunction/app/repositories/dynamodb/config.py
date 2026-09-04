"""Validated DynamoDB runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from urllib.parse import urlparse

from app.repositories.errors import ValidationError

_TABLE_RE = re.compile(r"^[A-Za-z0-9_.-]{3,255}$")
_REGION_RE = re.compile(r"^[a-z]{2}(?:-[a-z0-9]+)+-\d$")
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "dynamodb-local"})


@dataclass(frozen=True, slots=True)
class DynamoSettings:
    table_name: str
    region: str
    endpoint_url: str | None = None

    @classmethod
    def from_environment(cls) -> "DynamoSettings":
        table_name = os.getenv("DYNAMODB_TABLE_NAME", "").strip()
        region = (os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "").strip()
        endpoint_url = os.getenv("DYNAMODB_ENDPOINT_URL") or None
        if not _TABLE_RE.fullmatch(table_name):
            raise ValidationError("DYNAMODB_TABLE_NAME is missing or invalid")
        if not _REGION_RE.fullmatch(region):
            raise ValidationError("AWS_REGION is missing or invalid")
        if endpoint_url and not endpoint_url.startswith(("http://", "https://")):
            raise ValidationError("DYNAMODB_ENDPOINT_URL must use HTTP(S)")
        return cls(table_name=table_name, region=region, endpoint_url=endpoint_url)


def require_local_endpoint(endpoint_url: str) -> str:
    """Reject test endpoints that could send fixture operations to an AWS account."""

    parsed = urlparse(endpoint_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in _LOCAL_HOSTS:
        raise ValidationError("DynamoDB Local endpoint must use a loopback or Compose host")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValidationError("DynamoDB Local endpoint must not contain credentials or options")
    return endpoint_url
