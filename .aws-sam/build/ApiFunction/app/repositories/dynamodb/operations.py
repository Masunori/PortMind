"""Bounded DynamoDB writes and stable application-error translation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, NoReturn

from botocore.exceptions import BotoCoreError, ClientError

from app.repositories.errors import (
    ConflictError, PersistenceError, ThrottledError, UnavailableError, ValidationError,
)

MAX_TRANSACTION_ITEMS = 100
MAX_BATCH_ITEMS = 25

_CONFLICT_CODES = {
    "ConditionalCheckFailed", "ConditionalCheckFailedException",
    "TransactionConflict", "TransactionConflictException",
}
_THROTTLED_CODES = {
    "ProvisionedThroughputExceededException", "RequestLimitExceeded",
    "ThrottlingException", "TransactionInProgressException",
}
_VALIDATION_CODES = {"ValidationException", "IdempotentParameterMismatchException"}
_AUTH_CODES = {
    "AccessDeniedException", "ExpiredTokenException", "InvalidSignatureException",
    "MissingAuthenticationTokenException", "UnrecognizedClientException",
}


def raise_persistence_error(error: BaseException) -> NoReturn:
    """Translate SDK failures without leaking AWS response details."""

    if isinstance(error, ClientError):
        code = str(error.response.get("Error", {}).get("Code", ""))
        cancellation_codes = {
            str(reason.get("Code", ""))
            for reason in error.response.get("CancellationReasons", [])
            if isinstance(reason, dict)
        }
        if code == "TransactionCanceledException" and cancellation_codes & _CONFLICT_CODES:
            raise ConflictError("conditional persistence operation failed") from error
        if code in _CONFLICT_CODES:
            raise ConflictError("conditional persistence operation failed") from error
        if code in _THROTTLED_CODES:
            raise ThrottledError("persistence request was throttled") from error
        if code in _VALIDATION_CODES:
            raise ValidationError("invalid persistence operation") from error
        if code in _AUTH_CODES:
            raise UnavailableError("persistence authentication failed") from error
    if isinstance(error, (BotoCoreError, ClientError)):
        raise UnavailableError("persistence service unavailable") from error
    if isinstance(error, PersistenceError):
        raise error
    raise UnavailableError("persistence operation failed") from error


def conditional_put(table: Any, item: Mapping[str, Any], *, expected_version: int | None) -> None:
    kwargs: dict[str, Any] = {"Item": dict(item)}
    if expected_version is None:
        kwargs["ConditionExpression"] = "attribute_not_exists(PK)"
    else:
        kwargs.update(
            ConditionExpression="#version = :expected_version",
            ExpressionAttributeNames={"#version": "version"},
            ExpressionAttributeValues={":expected_version": expected_version},
        )
    try:
        table.put_item(**kwargs)
    except (BotoCoreError, ClientError) as error:
        raise_persistence_error(error)


def conditional_delete(
    table: Any, key: Mapping[str, Any], *, expected_version: int | None = None
) -> None:
    kwargs: dict[str, Any] = {"Key": dict(key), "ConditionExpression": "attribute_exists(PK)"}
    if expected_version is not None:
        kwargs.update(
            ConditionExpression="attribute_exists(PK) AND #version = :expected_version",
            ExpressionAttributeNames={"#version": "version"},
            ExpressionAttributeValues={":expected_version": expected_version},
        )
    try:
        table.delete_item(**kwargs)
    except (BotoCoreError, ClientError) as error:
        raise_persistence_error(error)


def conditional_update(
    table: Any, key: Mapping[str, Any], *, expected_version: int,
    update_expression: str, expression_names: Mapping[str, str] | None = None,
    expression_values: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    names = {"#version": "version", **dict(expression_names or {})}
    values = {":expected_version": expected_version, ":next_version": expected_version + 1,
              **dict(expression_values or {})}
    expression = update_expression.strip()
    if expression.startswith("SET "):
        expression += ", #version = :next_version"
    else:
        expression = f"SET #version = :next_version {expression}"
    try:
        response = table.update_item(
            Key=dict(key), ConditionExpression="#version = :expected_version",
            UpdateExpression=expression, ExpressionAttributeNames=names,
            ExpressionAttributeValues=values, ReturnValues="ALL_NEW",
        )
        return response.get("Attributes", {})
    except (BotoCoreError, ClientError) as error:
        raise_persistence_error(error)


def transact_write(client: Any, items: Sequence[Mapping[str, Any]], *, token: str | None = None) -> None:
    if not 1 <= len(items) <= MAX_TRANSACTION_ITEMS:
        raise ValidationError(f"transactions require 1-{MAX_TRANSACTION_ITEMS} items")
    kwargs: dict[str, Any] = {"TransactItems": [dict(item) for item in items]}
    if token:
        kwargs["ClientRequestToken"] = token
    try:
        client.transact_write_items(**kwargs)
    except (BotoCoreError, ClientError) as error:
        raise_persistence_error(error)


def batch_write(table: Any, items: Iterable[Mapping[str, Any]]) -> None:
    """Write arbitrary iterables in SDK-managed batches of at most 25 requests."""

    batch: list[Mapping[str, Any]] = []
    try:
        for item in items:
            batch.append(item)
            if len(batch) == MAX_BATCH_ITEMS:
                _write_batch(table, batch)
                batch = []
        if batch:
            _write_batch(table, batch)
    except (BotoCoreError, ClientError) as error:
        raise_persistence_error(error)


def _write_batch(table: Any, items: Sequence[Mapping[str, Any]]) -> None:
    with table.batch_writer() as writer:
        for item in items:
            writer.put_item(Item=dict(item))


def wire_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """Copy an item for the document-aware client owned by a boto3 resource."""
    return dict(item)
