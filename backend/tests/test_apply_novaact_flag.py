from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

import backend.app.main as main_module


def _run_id_for(actions: list[str]) -> str:
    digest = hashlib.sha1(",".join(actions).encode("utf-8")).hexdigest()[:10]
    return f"run_{digest}"


def test_apply_with_flag_off_keeps_simulated_behavior(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_NOVA_ACT", "0")
    monkeypatch.delenv("NOVA_ACT_API_KEY", raising=False)

    called = {"value": False}

    def _fake_runner(_actions: list[str]) -> dict:
        called["value"] = True
        return {}

    monkeypatch.setattr(main_module, "_run_nova_act_apply", _fake_runner)

    client = TestClient(main_module.app)
    response = client.post("/apply", json={})
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "success"
    assert payload["run_id"] == _run_id_for(["resize_instance", "enable_autoscaling", "enable_s3_encryption"])
    assert payload["steps"][0]["action"] == "open_console"
    assert called["value"] is False


def test_apply_with_flag_on_and_missing_key_returns_failed(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_NOVA_ACT", "1")
    monkeypatch.delenv("NOVA_ACT_API_KEY", raising=False)

    client = TestClient(main_module.app)
    response = client.post("/apply", json={"actions": ["resize_instance"]})
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "failed"
    assert "NOVA_ACT_API_KEY" in payload["notes"]
    assert payload["run_id"] == _run_id_for(["resize_instance"])


def test_apply_unknown_action_returns_skipped_result_and_valid_schema(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_NOVA_ACT", "1")
    monkeypatch.setenv("NOVA_ACT_API_KEY", "dummy_key_for_test")

    client = TestClient(main_module.app)
    response = client.post("/apply", json={"actions": ["unknown_action"]})
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "failed"
    assert isinstance(payload["steps"], list)
    assert any(str(step["result"]).startswith("skipped:") for step in payload["steps"])
    assert payload["run_id"] == _run_id_for(["unknown_action"])
