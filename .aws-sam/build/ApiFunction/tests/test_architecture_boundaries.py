"""Regression guards for removed platform-owned operational behavior."""

import ast
from pathlib import Path

from app.main import app
from app.database import Base


REMOVED_IMPORTS = {
    "app.simulation", "app.services.network_service", "app.services.schema_service",
    "app.services.rule_service", "app.services.context_version_service",
    "app.services.entity_resolution", "app.services.alias_service",
}


def test_active_application_code_cannot_import_removed_operational_modules() -> None:
    root = Path(__file__).parents[1] / "app"
    active = [root / "main.py", *sorted((root / "api").glob("*.py")),
              *sorted((root / "services").glob("*.py"))]
    violations: list[str] = []
    for path in active:
        tree = ast.parse(path.read_text(), filename=str(path))
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                    for alias in node.names]
        for name in imports:
            if name and any(name == removed or name.startswith(f"{removed}.")
                            for removed in REMOVED_IMPORTS):
                violations.append(f"{path.relative_to(root)} imports {name}")
    assert violations == []


def test_model_adapters_share_neutral_behavior_without_cross_vendor_imports() -> None:
    """Keep transport adapters independent while sharing prompts and output contracts."""

    root = Path(__file__).parents[1] / "app" / "integrations"
    imports_by_adapter: dict[str, set[str]] = {}
    for adapter in ("bedrock", "gemini"):
        tree = ast.parse((root / f"{adapter}.py").read_text())
        imports_by_adapter[adapter] = {
            node.module for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }

    assert "app.integrations.model_provider" in imports_by_adapter["bedrock"]
    assert "app.integrations.model_provider" in imports_by_adapter["gemini"]
    assert "app.integrations.gemini" not in imports_by_adapter["bedrock"]
    assert "app.integrations.bedrock" not in imports_by_adapter["gemini"]


def test_removed_operational_and_legacy_routes_are_absent() -> None:
    paths = set(app.openapi()["paths"])
    removed = {"/api/network", "/api/shipments", "/api/schemas",
               "/api/network/context-version", "/api/simulation-rules",
               "/api/simulations", "/api/documents", "/api/disruption-candidates",
               "/api/runs"}
    assert paths.isdisjoint(removed)
    assert "/api/experiments/{experiment_id}/submit" in paths


def test_orm_metadata_contains_only_platform_owned_tables() -> None:
    assert set(Base.metadata.tables) == {
        "scenarios", "plans", "data_sources", "collection_batches", "collection_runs",
        "evidence", "evidence_assessments", "signals", "signal_versions",
        "signal_evidence", "signal_entities", "signal_effects", "signal_relationships",
        "experiment_packages", "simulation_result_copies", "planning_cycles",
        "agent_prompts",
        "source_collection_leases",
    }


def test_repository_contracts_are_storage_vendor_neutral() -> None:
    root = Path(__file__).parents[1] / "app" / "repositories"
    tree = ast.parse((root / "contracts.py").read_text())
    imports = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imports |= {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(name.startswith(("sqlalchemy", "boto3", "botocore")) for name in imports)


def test_dynamodb_foundation_never_scans_or_configures_static_credentials() -> None:
    project = Path(__file__).parents[2]
    dynamodb = project / "server" / "app" / "repositories" / "dynamodb"
    for path in dynamodb.glob("*.py"):
        source = path.read_text()
        assert ".scan(" not in source.casefold()

    deployment_files = [
        project / "compose.dev.yml", project / "compose.prod.yml",
        project / "server" / "Dockerfile.dev", project / "server" / "Dockerfile.prod",
    ]
    credential_names = ("aws_access_key_id", "aws_secret_access_key", "aws_session_token")
    for path in deployment_files:
        source = path.read_text().casefold()
        assert not any(name in source for name in credential_names)


def test_extracted_services_have_no_persistence_vendor_imports() -> None:
    services = Path(__file__).parents[1] / "app" / "services"
    for path in services.glob("*.py"):
        tree = ast.parse(path.read_text())
        imports = {node.module for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom) and node.module}
        imports |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                    for alias in node.names}
        assert not any(item.startswith(("sqlalchemy", "app.database", "app.models",
                                        "app.repositories.postgres")) for item in imports)
