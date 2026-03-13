from __future__ import annotations

from fastapi.testclient import TestClient

import backend.app.main as main_module
import backend.app.nova_sonic_runner as sonic_runner


def test_voice_flag_off_returns_fallback_and_skips_live_client(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_NOVA_SONIC", "0")
    called = {"value": False}

    def _fail_if_called(*_args, **_kwargs):
        called["value"] = True
        raise AssertionError("boto3 client should not be called when ENABLE_NOVA_SONIC=0")

    monkeypatch.setattr(sonic_runner.boto3, "client", _fail_if_called)

    client = TestClient(main_module.app)
    response = client.post(
        "/voice",
        json={
            "transcript": "Lower cost while keeping uptime high",
            "latest_goal": "Optimize infra",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["normalized_goal"] == "Lower cost while keeping uptime high"
    assert payload["voice_metadata"]["voice_mode"] == "fallback"
    assert payload["voice_metadata"]["used_fallback"] is True
    assert called["value"] is False


def test_voice_live_success_returns_live_metadata(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_NOVA_SONIC", "1")

    def _fake_run_nova_sonic(*, transcript: str, latest_goal: str | None, latest_plan_summary: str | None) -> dict:
        del latest_goal, latest_plan_summary
        return {
            "transcript": transcript,
            "normalized_goal": "Lower monthly cost with reliability guardrails",
            "spoken_summary_text": "Captured your goal and prepared it for Analyze.",
            "voice_metadata": {
                "model_id": "us.amazon.nova-sonic-v1:0",
                "aws_region": "us-east-1",
                "voice_mode": "live_sonic",
                "used_fallback": False,
            },
        }

    monkeypatch.setattr(main_module, "_run_nova_sonic", _fake_run_nova_sonic)

    client = TestClient(main_module.app)
    response = client.post("/voice", json={"transcript": "optimize costs safely"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["voice_metadata"]["voice_mode"] == "live_sonic"
    assert payload["voice_metadata"]["used_fallback"] is False
    assert "spoken_summary_text" in payload


def test_voice_live_failure_returns_fallback_schema(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_NOVA_SONIC", "1")

    def _raise_failure(*, transcript: str, latest_goal: str | None, latest_plan_summary: str | None) -> dict:
        del transcript, latest_goal, latest_plan_summary
        raise RuntimeError("sonic_failure")

    monkeypatch.setattr(main_module, "_run_nova_sonic", _raise_failure)

    client = TestClient(main_module.app)
    response = client.post("/voice", json={"transcript": "optimize uptime and security"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["voice_metadata"]["voice_mode"] == "fallback"
    assert payload["voice_metadata"]["used_fallback"] is True
    assert payload["normalized_goal"]
