"""DynamoDB Local schema contract and opt-in lifecycle test."""

from __future__ import annotations

import os
from uuid import uuid4

import boto3
import pytest

from app.repositories.dynamodb.config import require_local_endpoint
from app.repositories.dynamodb.schema import (
    TABLE_SCHEMA, TTL_ATTRIBUTE, create_table, delete_table, table_definition,
)
from app.repositories.errors import ValidationError


class _WaiterTable:
    def __init__(self) -> None:
        self.waited_for_create = False
        self.waited_for_delete = False
        self.deleted = False

    def wait_until_exists(self) -> None:
        self.waited_for_create = True

    def delete(self) -> None:
        self.deleted = True

    def wait_until_not_exists(self) -> None:
        self.waited_for_delete = True


class _FakeClient:
    def __init__(self) -> None:
        self.ttl_request = None

    def update_time_to_live(self, **kwargs) -> None:
        self.ttl_request = kwargs


class _FakeResource:
    def __init__(self) -> None:
        self.table = _WaiterTable()
        self.request = None
        self.meta = type("Meta", (), {"client": _FakeClient()})()

    def create_table(self, **kwargs):
        self.request = kwargs
        return self.table


def test_schema_has_primary_keys_indexes_and_on_demand_billing() -> None:
    definition = table_definition("psa-test-one")
    assert definition["TableName"] == "psa-test-one"
    assert definition["BillingMode"] == "PAY_PER_REQUEST"
    assert definition["KeySchema"] == [
        {"AttributeName": "PK", "KeyType": "HASH"},
        {"AttributeName": "SK", "KeyType": "RANGE"},
    ]
    assert {index["IndexName"] for index in definition["GlobalSecondaryIndexes"]} == {
        "GSI1", "GSI2"
    }
    assert all(
        index["Projection"] == {"ProjectionType": "ALL"}
        for index in definition["GlobalSecondaryIndexes"]
    )
    assert definition is not TABLE_SCHEMA


def test_table_lifecycle_waits_and_enables_ttl() -> None:
    resource = _FakeResource()
    table = create_table(resource, "psa-test-lifecycle")
    assert table.waited_for_create
    assert resource.meta.client.ttl_request == {
        "TableName": "psa-test-lifecycle",
        "TimeToLiveSpecification": {"Enabled": True, "AttributeName": TTL_ATTRIBUTE},
    }
    delete_table(table)
    assert table.deleted and table.waited_for_delete


@pytest.mark.parametrize(
    "endpoint",
    ["https://dynamodb.ap-southeast-1.amazonaws.com", "http://example.test:8000"],
)
def test_local_fixture_rejects_non_local_endpoints(endpoint: str) -> None:
    with pytest.raises(ValidationError, match="Local endpoint"):
        require_local_endpoint(endpoint)


def test_local_fixture_accepts_host_and_compose_endpoints() -> None:
    assert require_local_endpoint("http://127.0.0.1:8001")
    assert require_local_endpoint("http://dynamodb-local:8000")


@pytest.fixture
def local_dynamodb_table():
    configured_endpoint = os.getenv("DYNAMODB_LOCAL_ENDPOINT")
    if not configured_endpoint:
        pytest.skip("set DYNAMODB_LOCAL_ENDPOINT to run against DynamoDB Local")
    endpoint = require_local_endpoint(configured_endpoint)
    region = os.getenv("DYNAMODB_LOCAL_REGION", "ap-southeast-1")
    table_name = f"psa-test-{uuid4().hex}"
    resource = boto3.resource(
        "dynamodb",
        region_name=region,
        endpoint_url=endpoint,
        aws_access_key_id="localTestKey",
        aws_secret_access_key="localTestSecret",
    )
    table = create_table(resource, table_name)
    try:
        yield resource, table_name
    finally:
        delete_table(table)
    assert table_name not in resource.meta.client.list_tables()["TableNames"]


def test_dynamodb_local_creates_describes_and_deletes_isolated_table(
    local_dynamodb_table,
) -> None:
    resource, table_name = local_dynamodb_table
    description = resource.meta.client.describe_table(TableName=table_name)["Table"]
    assert description["KeySchema"] == TABLE_SCHEMA["KeySchema"]
    assert description["BillingModeSummary"]["BillingMode"] == "PAY_PER_REQUEST"
    assert {
        index["IndexName"]: index["KeySchema"]
        for index in description["GlobalSecondaryIndexes"]
    } == {
        index["IndexName"]: index["KeySchema"]
        for index in TABLE_SCHEMA["GlobalSecondaryIndexes"]
    }
    ttl = resource.meta.client.describe_time_to_live(TableName=table_name)
    assert ttl["TimeToLiveDescription"]["AttributeName"] == TTL_ATTRIBUTE
