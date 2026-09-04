from contextlib import contextmanager

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.repositories.dynamodb import client
from app.repositories.dynamodb.config import DynamoSettings
from app.repositories.dynamodb.operations import batch_write, conditional_put, transact_write
from app.repositories.errors import ConflictError, ThrottledError, UnavailableError, ValidationError


def aws_error(code: str, message: str = "secret vendor detail") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message}}, "PutItem")


def test_settings_require_a_valid_table_and_region(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DYNAMODB_TABLE_NAME", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    with pytest.raises(ValidationError, match="TABLE_NAME"):
        DynamoSettings.from_environment()

    monkeypatch.setenv("DYNAMODB_TABLE_NAME", "psa-test")
    monkeypatch.setenv("AWS_REGION", "not a region")
    with pytest.raises(ValidationError, match="AWS_REGION"):
        DynamoSettings.from_environment()

    monkeypatch.setenv("AWS_REGION", "ap-southeast-1")
    monkeypatch.setenv("DYNAMODB_ENDPOINT_URL", "ftp://localhost:8001")
    with pytest.raises(ValidationError, match="HTTP"):
        DynamoSettings.from_environment()


def test_client_is_reused_without_static_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict] = []

    class Resource:
        def Table(self, name: str):
            return (name, self)

    resource = Resource()

    def fake_resource(service: str, **kwargs):
        seen.append({"service": service, **kwargs})
        return resource

    client.reset_clients()
    monkeypatch.setattr(client.boto3, "resource", fake_resource)
    settings = DynamoSettings("psa-test", "ap-southeast-1")
    assert client.get_table(settings)[1] is resource
    assert client.get_table(settings)[1] is resource
    assert len(seen) == 1
    assert "aws_access_key_id" not in seen[0]
    assert "aws_secret_access_key" not in seen[0]
    client.reset_clients()


class FakeTable:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.puts: list[dict] = []

    def put_item(self, **kwargs):
        if self.error:
            raise self.error
        self.puts.append(kwargs)

    @contextmanager
    def batch_writer(self):
        yield self


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("ConditionalCheckFailedException", ConflictError),
        ("ProvisionedThroughputExceededException", ThrottledError),
        ("InternalServerError", UnavailableError),
    ],
)
def test_conditional_write_translates_aws_errors_without_details(code, expected) -> None:
    with pytest.raises(expected) as caught:
        conditional_put(FakeTable(aws_error(code)), {"PK": "one"}, expected_version=None)
    assert "secret" not in str(caught.value)


def test_conditional_write_builds_create_and_version_conditions() -> None:
    table = FakeTable()
    conditional_put(table, {"PK": "one"}, expected_version=None)
    conditional_put(table, {"PK": "one", "version": 3}, expected_version=2)
    assert table.puts[0]["ConditionExpression"] == "attribute_not_exists(PK)"
    assert table.puts[1]["ExpressionAttributeValues"] == {":expected_version": 2}


def test_transaction_cancellation_with_failed_condition_is_a_conflict() -> None:
    error = ClientError(
        {
            "Error": {"Code": "TransactionCanceledException", "Message": "secret"},
            "CancellationReasons": [{"Code": "ConditionalCheckFailed"}],
        },
        "TransactWriteItems",
    )

    class BrokenClient:
        def transact_write_items(self, **kwargs):
            raise error

    with pytest.raises(ConflictError) as caught:
        transact_write(BrokenClient(), [{"ConditionCheck": {}}])
    assert "secret" not in str(caught.value)


def test_transactions_are_bounded_and_translate_transport_failures() -> None:
    with pytest.raises(ValidationError, match="1-100"):
        transact_write(object(), [])

    class BrokenClient:
        def transact_write_items(self, **kwargs):
            raise EndpointConnectionError(endpoint_url="http://unavailable.invalid")

    with pytest.raises(UnavailableError):
        transact_write(BrokenClient(), [{"Put": {"TableName": "test", "Item": {}}}])


def test_batch_writer_never_exceeds_dynamodb_batch_limit() -> None:
    table = FakeTable()
    batch_write(table, ({"PK": str(index)} for index in range(51)))
    assert len(table.puts) == 51
