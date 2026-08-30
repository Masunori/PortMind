"""Restricted Draft 2020-12 disruption-schema admission and local validation."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from app.integrations.contracts import DisruptionCatalog, DisruptionContract
from app.integrations.errors import ClientContractError

ALLOWED = {"$schema", "$id", "$defs", "$ref", "type", "properties", "required", "additionalProperties",
           "items", "minItems", "maxItems", "minLength", "maxLength", "minimum", "maximum",
           "exclusiveMinimum", "exclusiveMaximum", "enum", "const", "description", "title", "format",
           "uniqueItems", "anyOf", "oneOf", "allOf"}
ALLOWED_FORMATS = {"date", "date-time", "duration", "uuid"}


def schema_hash(schema: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def admit_schema(schema: dict[str, Any], *, max_bytes: int = 64_000, max_depth: int = 12) -> None:
    """Reject network refs, executable/unknown vocabulary, and unbounded collections."""

    if len(json.dumps(schema).encode()) > max_bytes: raise ClientContractError("Client schema exceeds size limit")
    def visit(value: Any, depth: int) -> None:
        if depth > max_depth: raise ClientContractError("Client schema exceeds depth limit")
        if isinstance(value, dict):
            unknown = set(value) - ALLOWED
            if unknown: raise ClientContractError(f"Unsupported JSON Schema keywords: {sorted(unknown)}")
            ref = value.get("$ref")
            if ref is not None and not str(ref).startswith("#/"): raise ClientContractError("Only local JSON Schema references are allowed")
            declared = value.get("type")
            declared_types = ({declared} if isinstance(declared, str)
                              else set(declared) if isinstance(declared, list) else set())
            if not declared_types.issubset({"object", "array", "string", "number",
                                            "integer", "boolean", "null"}):
                raise ClientContractError("Unsupported JSON Schema type")
            if "object" in declared_types and value.get("additionalProperties") is not False:
                raise ClientContractError("Object schemas must set additionalProperties to false")
            if "array" in declared_types and "maxItems" not in value:
                raise ClientContractError("Array schemas require maxItems")
            if "format" in value and value["format"] not in ALLOWED_FORMATS:
                raise ClientContractError("Unsupported JSON Schema format")
            for key, child in value.items():
                if key in {"properties", "$defs"} and isinstance(child, dict):
                    for subschema in child.values(): visit(subschema, depth + 1)
                elif key not in {"required", "enum"}:
                    visit(child, depth + 1)
        elif isinstance(value, list):
            for child in value: visit(child, depth + 1)
    visit(schema, 0)


def validate_payload(payload: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Validate the intentionally restricted vocabulary without network resolution."""

    errors: list[str] = []; expected = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "number": (int, float), "integer": int,
             "boolean": bool, "null": type(None)}
    expected_types = [expected] if isinstance(expected, str) else expected if isinstance(expected, list) else []
    def matches(kind: str) -> bool:
        if kind not in types: return False
        if kind in {"number", "integer"} and isinstance(payload, bool): return False
        return isinstance(payload, types[kind])
    if expected_types and not any(matches(kind) for kind in expected_types):
        return [f"{path}: expected {' or '.join(expected_types)}"]
    if isinstance(payload, dict):
        properties = schema.get("properties", {}); required = schema.get("required", [])
        errors += [f"{path}.{key}: required" for key in required if key not in payload]
        if schema.get("additionalProperties") is False:
            errors += [f"{path}.{key}: additional property" for key in payload if key not in properties]
        for key, value in payload.items():
            if key in properties: errors += validate_payload(value, properties[key], f"{path}.{key}")
    if isinstance(payload, list):
        if len(payload) < schema.get("minItems", 0): errors.append(f"{path}: too few items")
        if len(payload) > schema.get("maxItems", len(payload)): errors.append(f"{path}: too many items")
        for index, value in enumerate(payload): errors += validate_payload(value, schema.get("items", {}), f"{path}[{index}]")
    if isinstance(payload, str) and "maxLength" in schema and len(payload) > schema["maxLength"]: errors.append(f"{path}: too long")
    if isinstance(payload, (int, float)) and not isinstance(payload, bool):
        if "minimum" in schema and payload < schema["minimum"]: errors.append(f"{path}: below minimum")
        if "maximum" in schema and payload > schema["maximum"]: errors.append(f"{path}: above maximum")
        if "exclusiveMinimum" in schema and payload <= schema["exclusiveMinimum"]: errors.append(f"{path}: below exclusive minimum")
        if "exclusiveMaximum" in schema and payload >= schema["exclusiveMaximum"]: errors.append(f"{path}: above exclusive maximum")
    if "enum" in schema and payload not in schema["enum"]: errors.append(f"{path}: outside enum")
    return errors


@dataclass
class ContractRegistry:
    """Cache admitted catalogs while detecting version/hash reuse."""

    catalogs: dict[tuple[str, str], DisruptionCatalog] = field(default_factory=dict)

    def register(self, client_id: str, catalog: DisruptionCatalog) -> None:
        for contract in catalog.contracts:
            admit_schema(contract.payload_schema)
            if schema_hash(contract.payload_schema) != contract.schema_hash:
                raise ClientContractError("Declared disruption schema hash is invalid")
        key = (client_id, catalog.catalog_version); existing = self.catalogs.get(key)
        if existing:
            previous = [(item.type, item.schema_hash) for item in existing.contracts]
            current = [(item.type, item.schema_hash) for item in catalog.contracts]
            if previous != current or existing.capability_version != catalog.capability_version:
                raise ClientContractError("Catalog version was reused with changed content")
        self.catalogs[key] = catalog
