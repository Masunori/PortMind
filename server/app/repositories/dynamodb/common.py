"""Shared query, item and validation mechanics for DynamoDB repositories."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel

from app.repositories.contracts import Page
from app.repositories.dynamodb.client import get_table
from app.repositories.dynamodb.codec import decode_token, decode_value, encode_token, encode_value
from app.repositories.dynamodb.operations import raise_persistence_error
from app.repositories.errors import ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


def validate_limit(limit: int) -> None:
    if not 1 <= limit <= 1000:
        raise ValidationError("limit must be between 1 and 1000")


def model_payload(model: BaseModel) -> dict[str, Any]:
    return encode_value(model.model_dump(mode="python"))


def parse_model(model_type: type[ModelT], payload: Mapping[str, Any]) -> ModelT:
    return model_type.model_validate(decode_value(dict(payload)))


class DynamoRepository:
    def __init__(self, table: Any | None = None):
        self.table = table or get_table()

    def _get(self, pk: str, sk: str = "META", *, consistent: bool = True) -> dict[str, Any] | None:
        try:
            return self.table.get_item(
                Key={"PK": pk, "SK": sk}, ConsistentRead=consistent
            ).get("Item")
        except (BotoCoreError, ClientError) as error:
            raise_persistence_error(error)

    def _query_page(
        self, *, index: str, partition: str, limit: int, token: str | None,
        identity: str, ascending: bool = True, filter_expression: Any | None = None,
        names: Mapping[str, str] | None = None, values: Mapping[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        validate_limit(limit)
        start_key = decode_token(token, query_identity=identity)
        kwargs: dict[str, Any] = {
            "IndexName": index,
            "KeyConditionExpression": Key(f"{index}PK").eq(partition),
            "Limit": limit,
            "ScanIndexForward": ascending,
        }
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        if filter_expression is not None:
            kwargs["FilterExpression"] = filter_expression
        if names:
            kwargs["ExpressionAttributeNames"] = dict(names)
        if values:
            kwargs["ExpressionAttributeValues"] = dict(values)
        try:
            response = self.table.query(**kwargs)
        except (BotoCoreError, ClientError) as error:
            raise_persistence_error(error)
        return response.get("Items", []), encode_token(
            response.get("LastEvaluatedKey"), query_identity=identity
        )

    def _model_page(
        self, model_type: type[ModelT], *, index: str, partition: str, limit: int,
        token: str | None, identity: str, ascending: bool = True,
    ) -> Page[ModelT]:
        items, next_token = self._query_page(
            index=index, partition=partition, limit=limit, token=token,
            identity=identity, ascending=ascending,
        )
        return Page(
            tuple(parse_model(model_type, item["payload"]) for item in items), next_token
        )
