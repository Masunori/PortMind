"""Single-table DynamoDB schema and lifecycle helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from app.repositories.dynamodb.operations import raise_persistence_error

TTL_ATTRIBUTE = "ttl"

TABLE_SCHEMA: dict[str, Any] = {
    "KeySchema": [
        {"AttributeName": "PK", "KeyType": "HASH"},
        {"AttributeName": "SK", "KeyType": "RANGE"},
    ],
    "AttributeDefinitions": [
        {"AttributeName": "PK", "AttributeType": "S"},
        {"AttributeName": "SK", "AttributeType": "S"},
        {"AttributeName": "GSI1PK", "AttributeType": "S"},
        {"AttributeName": "GSI1SK", "AttributeType": "S"},
        {"AttributeName": "GSI2PK", "AttributeType": "S"},
        {"AttributeName": "GSI2SK", "AttributeType": "S"},
    ],
    "GlobalSecondaryIndexes": [
        {
            "IndexName": "GSI1",
            "KeySchema": [
                {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        },
        {
            "IndexName": "GSI2",
            "KeySchema": [
                {"AttributeName": "GSI2PK", "KeyType": "HASH"},
                {"AttributeName": "GSI2SK", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        },
    ],
    "BillingMode": "PAY_PER_REQUEST",
}


def table_definition(table_name: str) -> dict[str, Any]:
    """Return a fresh create-table request for the canonical schema."""

    return {"TableName": table_name, **deepcopy(TABLE_SCHEMA)}


def create_table(resource: Any, table_name: str) -> Any:
    """Create the canonical table, wait for it, and enable deletion TTL."""

    try:
        table = resource.create_table(**table_definition(table_name))
        table.wait_until_exists()
        resource.meta.client.update_time_to_live(
            TableName=table_name,
            TimeToLiveSpecification={"Enabled": True, "AttributeName": TTL_ATTRIBUTE},
        )
        return table
    except (BotoCoreError, ClientError) as error:
        raise_persistence_error(error)


def delete_table(table: Any) -> None:
    """Delete an isolated table and wait until its name can be reused."""

    try:
        table.delete()
        table.wait_until_not_exists()
    except (BotoCoreError, ClientError) as error:
        raise_persistence_error(error)
