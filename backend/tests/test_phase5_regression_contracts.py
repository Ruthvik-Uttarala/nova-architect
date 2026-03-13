from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

import backend.app.main as main_module


def _run_id(actions: list[str]) -> str:
    digest = hashlib.sha1(",".join(actions).encode("utf-8")).hexdigest()[:10]
    return f"run_{digest}"


def test_analyze_contract_required_fields_unchanged(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_BEDROCK", "0")
    client = TestClient(main_module.app)
    response = client.post("/analyze", json={"goal": "Regression contract check"})
    assert response.status_code == 200
    payload = response.json()

    assert "plan" in payload
    assert "simulation" in payload
    assert "used_fallback" in payload
    assert isinstance(payload["plan"], dict)
    assert isinstance(payload["simulation"], dict)
    assert isinstance(payload["used_fallback"], bool)


def test_apply_contract_required_fields_and_determinism_unchanged(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_NOVA_ACT", "0")
    client = TestClient(main_module.app)
    actions = ["resize_instance", "enable_autoscaling"]
    response = client.post("/apply", json={"actions": actions})
    assert response.status_code == 200
    payload = response.json()

    assert set(payload.keys()) == {"run_id", "status", "steps", "notes"}
    assert payload["run_id"] == _run_id(actions)
    assert isinstance(payload["steps"], list)
