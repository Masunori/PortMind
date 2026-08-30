"""Restricted client disruption schema validation tests."""

import pytest

from app.integrations.contracts import DisruptionCatalog, DisruptionContract
from app.integrations.errors import ClientContractError
from app.integrations.schema_validation import ContractRegistry, admit_schema, schema_hash, validate_payload


def schema():
    return {"type": "object", "additionalProperties": False, "required": ["hours"],
            "properties": {"hours": {"type": "number", "minimum": 0, "maximum": 100}}}


def test_admission_rejects_network_refs_unbounded_arrays_and_open_objects():
    for invalid in ({"$ref": "https://evil/schema"}, {"type": "array", "items": {}},
                    {"type": "object", "properties": {}}):
        with pytest.raises(ClientContractError): admit_schema(invalid)


def test_payload_validation_rejects_missing_extra_type_and_bounds():
    value = schema(); admit_schema(value)
    assert validate_payload({}, value) == ["$.hours: required"]
    assert validate_payload({"hours": "x"}, value) == ["$.hours: expected number"]
    assert validate_payload({"hours": 101}, value) == ["$.hours: above maximum"]
    assert validate_payload({"hours": 1, "extra": 2}, value) == ["$.extra: additional property"]


def test_payload_validation_supports_nullable_union_types():
    value = {"type": "object", "additionalProperties": False,
             "required": ["effective_until"], "properties": {
                 "effective_until": {"type": ["string", "null"], "format": "date-time"}}}
    admit_schema(value)
    assert validate_payload({"effective_until": None}, value) == []
    assert validate_payload({"effective_until": "2026-08-31T00:00:00Z"}, value) == []
    assert validate_payload({"effective_until": 3}, value) == [
        "$.effective_until: expected string or null"]


def test_registry_rejects_hash_conflicts_and_version_reuse():
    value = schema(); contract = DisruptionContract(type="DELAY", target_types=["edge"],
        payload_schema=value, schema_hash=schema_hash(value))
    catalog = DisruptionCatalog(catalog_version="v1", context_version="c1", capability_version="x", contracts=[contract])
    registry = ContractRegistry(); registry.register("client", catalog)
    changed = schema(); changed["properties"]["hours"]["maximum"] = 200
    conflicting = DisruptionCatalog(catalog_version="v1", context_version="c1", capability_version="x", contracts=[
        DisruptionContract(type="DELAY", target_types=["edge"], payload_schema=changed, schema_hash=schema_hash(changed))])
    with pytest.raises(ClientContractError, match="reused"): registry.register("client", conflicting)
