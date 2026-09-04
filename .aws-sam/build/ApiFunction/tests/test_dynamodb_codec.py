from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.repositories.dynamodb.codec import (
    MAX_CHUNK_BYTES, chunk_content, decode_token, decode_value, encode_token, encode_value,
    reconstruct_content,
)
from app.repositories.errors import ValidationError


def test_codec_normalizes_dates_floats_and_nested_values() -> None:
    assert encode_value({"at": datetime(2026, 1, 2, tzinfo=timezone.utc), "n": 0.1}) == {
        "at": "2026-01-02T00:00:00Z", "n": Decimal("0.1")
    }


def test_token_round_trip_and_validation() -> None:
    key = {"PK": "SOURCE#one", "SK": "META", "sequence": Decimal("1"), "raw": b"x"}
    assert decode_token(encode_token(key)) == key
    with pytest.raises(ValidationError):
        decode_token("not-json")


def test_tokens_are_query_bound_and_tamper_evident() -> None:
    token = encode_token({"PK": "one", "SK": "META"}, query_identity="sources")
    with pytest.raises(ValidationError, match="continuation token"):
        decode_token(token, query_identity="evidence")
    replacement = "A" if token[-1] != "A" else "B"
    with pytest.raises(ValidationError, match="continuation token"):
        decode_token(token[:-1] + replacement, query_identity="sources")


def test_decode_value_restores_nested_decimal_numbers() -> None:
    assert decode_value({"whole": Decimal("2"), "fraction": [Decimal("0.25")]}) == {
        "whole": 2, "fraction": [0.25]
    }


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_codec_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValidationError, match="non-finite"):
        encode_value(value)


def test_token_rejects_unsupported_values() -> None:
    with pytest.raises(ValidationError, match="unsupported"):
        encode_token({"PK": object()})


def test_content_chunks_on_utf8_boundaries_and_reconstructs() -> None:
    content = "é" * 100_000
    chunks, digest = chunk_content(content)
    assert all(len(chunk) <= MAX_CHUNK_BYTES for chunk in chunks)
    assert reconstruct_content(chunks) == content
    assert len(digest) == 64


def test_oversized_evidence_is_rejected_before_storage() -> None:
    with pytest.raises(ValidationError, match="256 KiB"):
        chunk_content("x" * (256 * 1024 + 1))
