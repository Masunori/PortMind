"""Reusable DynamoDB resource construction for warm application processes."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from app.repositories.dynamodb.config import DynamoSettings


@lru_cache(maxsize=4)
def _resource(region: str, endpoint_url: str | None) -> Any:
    return boto3.resource(
        "dynamodb",
        region_name=region,
        endpoint_url=endpoint_url,
        config=Config(retries={"mode": "standard", "max_attempts": 4}),
    )


def get_table(settings: DynamoSettings | None = None) -> Any:
    settings = settings or DynamoSettings.from_environment()
    return _resource(settings.region, settings.endpoint_url).Table(settings.table_name)


def reset_clients() -> None:
    """Clear cached SDK resources for tests and explicit configuration reloads."""

    _resource.cache_clear()
