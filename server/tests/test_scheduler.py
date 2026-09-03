"""Tests for explicit global scheduling configuration."""

from app import scheduler


def test_global_scheduling_defaults_off(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_SOURCE_SCHEDULER", raising=False)
    assert scheduler.scheduling_enabled() is False


def test_global_scheduling_requires_explicit_true(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_SOURCE_SCHEDULER", "true")
    assert scheduler.scheduling_enabled() is True
    monkeypatch.setenv("ENABLE_SOURCE_SCHEDULER", "1")
    assert scheduler.scheduling_enabled() is False
