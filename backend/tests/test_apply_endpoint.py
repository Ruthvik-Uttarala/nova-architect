from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from backend.app.main import app


def _run_id_for(actions: list[str]) -> str:
    digest = hashlib.sha1(",".join(actions).encode("utf-8")).hexdigest()[:10]
    return f"run_{digest}"


def test_apply_default_request_returns_success() -> None:
    client = TestClient(app)
    response = client.post("/apply", json={})
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "success"
    assert len(payload["steps"]) == 4
    assert payload["steps"][0]["action"] == "open_console"
    assert payload["run_id"] == _run_id_for(["resize_instance", "enable_autoscaling", "enable_s3_encryption"])


def test_apply_unknown_action_mixed_with_known_returns_partial() -> None:
    client = TestClient(app)
    actions = ["resize_instance", "unknown_action"]
    response = client.post("/apply", json={"actions": actions})
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "partial"
    assert any(step["result"] == "skipped_unknown_action" for step in payload["steps"])
    assert payload["run_id"] == _run_id_for(actions)


def test_apply_only_unknown_actions_returns_failed() -> None:
    client = TestClient(app)
    actions = ["unknown_one", "unknown_two"]
    response = client.post("/apply", json={"actions": actions})
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "failed"
    assert "No executable known actions were provided." in payload["notes"]
    assert payload["run_id"] == _run_id_for(actions)
