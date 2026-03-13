from __future__ import annotations

from fastapi.testclient import TestClient

import backend.app.main as main_module


def _base_payload() -> dict:
    return {
        "execution_mode": "aws_api_safe_tag",
        "resource_arn": "arn:aws:ec2:us-east-1:111122223333:instance/i-0123456789abcdef0",
        "resource_type": "ec2",
        "action": "apply_demo_tag",
        "approval_confirmed": True,
    }


def test_execute_real_blocked_without_approval() -> None:
    client = TestClient(main_module.app)
    payload = _base_payload()
    payload["approval_confirmed"] = False
    response = client.post("/execute-real", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert body["policy_decision"]["reason"] == "approval_required"


def test_execute_real_blocks_unsafe_combo() -> None:
    client = TestClient(main_module.app)
    payload = _base_payload()
    payload["execution_mode"] = "aws_api_safe_tag"
    payload["action"] = "open_console_view"
    response = client.post("/execute-real", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert body["policy_decision"]["allowed"] is False


def test_execute_real_safe_tag_returns_normalized_response(monkeypatch) -> None:
    def _fake_execute_aws_api_safe_tag(*, request, run_id, region_name, artifact_dir):
        del request, region_name, artifact_dir
        return {
            "status": "success",
            "steps": [{"step": 1, "action": "rgta_tag_resources", "result": "ok"}],
            "notes": "ok",
            "evidence_refs": [
                {"label": "evidence", "file_path": f"C:/tmp/{run_id}.txt", "format": "txt"},
            ],
        }

    monkeypatch.setattr(main_module, "execute_aws_api_safe_tag", _fake_execute_aws_api_safe_tag)
    client = TestClient(main_module.app)
    response = client.post("/execute-real", json=_base_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["execution_mode"] == "aws_api_safe_tag"
    assert body["steps"][0]["action"] == "rgta_tag_resources"


def test_execute_real_rollback_remove_tag_returns_normalized_response(monkeypatch) -> None:
    def _fake_execute_aws_api_safe_tag(*, request, run_id, region_name, artifact_dir):
        del run_id, region_name, artifact_dir
        return {
            "status": "success",
            "steps": [{"step": 1, "action": request.action, "result": "ok"}],
            "notes": "rollback_ok",
            "evidence_refs": [],
        }

    monkeypatch.setattr(main_module, "execute_aws_api_safe_tag", _fake_execute_aws_api_safe_tag)
    client = TestClient(main_module.app)
    payload = _base_payload()
    payload["action"] = "remove_demo_tag"
    response = client.post("/execute-real", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["steps"][0]["action"] == "remove_demo_tag"


def test_execute_real_console_mode_blocked_unless_enabled(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_REAL_AWS_CONSOLE", "0")
    client = TestClient(main_module.app)
    payload = _base_payload()
    payload["execution_mode"] = "aws_console_safe"
    payload["action"] = "open_console_view"
    response = client.post("/execute-real", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert "ENABLE_REAL_AWS_CONSOLE_not_enabled" in body["steps"][0]["result"]
