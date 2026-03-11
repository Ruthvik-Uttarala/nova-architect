from __future__ import annotations

import json

import boto3
from botocore.stub import ANY, Stubber
from fastapi.testclient import TestClient
import pytest

import backend.app.agent as agent_module
import backend.app.main as main_module
from backend.app.agent import AnalyzeResult
from backend.app.schemas import Plan


def _valid_plan_payload() -> dict:
    return {
        "analysis_summary": "Validated live analyze plan",
        "identified_issues": [],
        "optimization_plan": [],
        "tradeoffs": [],
        "metrics": {
            "monthly_cost_before": 100.0,
            "monthly_cost_after_estimate": 90.0,
            "uptime_risk_before_0_to_10": 5.0,
            "uptime_risk_after_0_to_10": 3.0,
            "security_risk_before_0_to_10": 3.0,
            "security_risk_after_0_to_10": 2.0,
        },
    }


def _converse_response(text: str) -> dict:
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 10, "outputTokens": 10, "totalTokens": 20},
        "metrics": {"latencyMs": 100},
    }


def _build_stubbed_bedrock_client():
    session = boto3.session.Session(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_session_token="test",
        region_name="us-east-1",
    )
    client = session.client("bedrock-runtime", region_name="us-east-1")
    return client, Stubber(client)


@pytest.mark.parametrize("disabled_value", ["0", "false", "off", "no", "FALSE"])
def test_analyze_with_live_flag_off_returns_valid_without_bedrock_call(monkeypatch, disabled_value: str) -> None:
    monkeypatch.setenv("ENABLE_LIVE_BEDROCK", disabled_value)

    class FailIfCalledAgent:
        def __init__(self):
            raise AssertionError("BedrockNovaAgent should not be constructed when ENABLE_LIVE_BEDROCK=0")

    monkeypatch.setattr(main_module, "BedrockNovaAgent", FailIfCalledAgent)

    client = TestClient(main_module.app)
    response = client.post("/analyze", json={"goal": "Reduce costs safely"})
    assert response.status_code == 200
    payload = response.json()
    assert "plan" in payload
    assert "simulation" in payload
    assert payload["used_fallback"] is True
    assert payload["analyze_metadata"]["analyze_mode"] == "fallback"
    assert payload["analyze_metadata"]["used_fallback"] is True
    assert payload["simulation"]["cost"]["delta_usd_per_month"] == pytest.approx(
        payload["simulation"]["cost"]["monthly_cost_after_estimate"]
        - payload["simulation"]["cost"]["monthly_cost_before"]
    )


def test_analyze_live_path_returns_valid_schema_with_metadata(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_BEDROCK", "1")

    class FakeLiveAgent:
        def __init__(self):
            self.model_id = "env.model.id"
            self.region_name = "us-east-1"

        def analyze_detailed(self, *, system_text: str, user_text: str, snapshot: dict) -> AnalyzeResult:
            return AnalyzeResult(
                plan=Plan.model_validate(_valid_plan_payload()),
                used_fallback=False,
                parse_retries_used=0,
                failure_reason="",
            )

    monkeypatch.setattr(main_module, "BedrockNovaAgent", FakeLiveAgent)

    client = TestClient(main_module.app)
    response = client.post("/analyze", json={"goal": "Improve uptime"})
    assert response.status_code == 200
    payload = response.json()
    assert "plan" in payload and "simulation" in payload
    assert payload["analyze_metadata"]["analyze_mode"] == "live_bedrock"
    assert payload["analyze_metadata"]["model_id"] == "env.model.id"
    assert payload["analyze_metadata"]["used_fallback"] is False
    assert payload["simulation"]["cost"]["delta_usd_per_month"] == pytest.approx(
        payload["simulation"]["cost"]["monthly_cost_after_estimate"]
        - payload["simulation"]["cost"]["monthly_cost_before"]
    )


def test_analyze_retry_behavior_reports_retry_count(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_BEDROCK", "1")
    model_id = "us.amazon.nova-2-lite-v1:0"

    client, stubber = _build_stubbed_bedrock_client()
    expected_request = {
        "modelId": model_id,
        "system": ANY,
        "messages": ANY,
        "inferenceConfig": {"maxTokens": 1400, "temperature": 0.1, "topP": 0.9},
    }
    stubber.add_response("converse", _converse_response("not-json"), expected_request)
    stubber.add_response("converse", _converse_response(json.dumps(_valid_plan_payload())), expected_request)
    stubber.activate()

    real_cls = agent_module.BedrockNovaAgent

    def fake_agent_factory():
        return real_cls(client=client, region_name="us-east-1", model_id=model_id)

    monkeypatch.setattr(main_module, "BedrockNovaAgent", fake_agent_factory)

    api = TestClient(main_module.app)
    response = api.post("/analyze", json={"goal": "Retry parse test"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["used_fallback"] is False
    assert payload["analyze_metadata"]["parse_retries_used"] == 1
    assert payload["analyze_metadata"]["analyze_mode"] == "live_bedrock"
    assert payload["simulation"]["cost"]["delta_usd_per_month"] == pytest.approx(
        payload["simulation"]["cost"]["monthly_cost_after_estimate"]
        - payload["simulation"]["cost"]["monthly_cost_before"]
    )

    stubber.assert_no_pending_responses()
    stubber.deactivate()


def test_analyze_live_failure_returns_safe_fallback(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_BEDROCK", "1")

    class FailAgent:
        def __init__(self):
            self.model_id = "failing.model.id"
            self.region_name = "us-east-1"

        def analyze_detailed(self, *, system_text: str, user_text: str, snapshot: dict) -> AnalyzeResult:
            raise RuntimeError("simulated_bedrock_error")

    monkeypatch.setattr(main_module, "BedrockNovaAgent", FailAgent)

    client = TestClient(main_module.app)
    response = client.post("/analyze", json={"goal": "Handle failure"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["used_fallback"] is True
    assert payload["analyze_metadata"]["analyze_mode"] == "fallback"
    assert payload["analyze_metadata"]["used_fallback"] is True
    assert "analysis_summary" in payload["plan"]
    assert "metrics" in payload["plan"]
    assert payload["simulation"]["cost"]["delta_usd_per_month"] == pytest.approx(
        payload["simulation"]["cost"]["monthly_cost_after_estimate"]
        - payload["simulation"]["cost"]["monthly_cost_before"]
    )
