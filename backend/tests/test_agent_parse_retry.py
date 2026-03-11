from __future__ import annotations

import json

import boto3
from botocore.stub import Stubber

from backend.app.agent import BedrockNovaAgent, RETRY_SYSTEM_SUFFIX, try_parse_json


def _snapshot_fixture() -> dict:
    return {
        "single_az_deployment": True,
        "no_autoscaling": True,
        "peak_multiplier": 3.0,
        "s3": {"default_encryption": False},
        "services": [{"name": "svc_a", "monthly_cost_usd": 100.0}],
    }


def _valid_plan_payload() -> dict:
    return {
        "analysis_summary": "Validated plan",
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


def _build_stubbed_client():
    session = boto3.session.Session(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_session_token="test",
        region_name="us-east-1",
    )
    client = session.client("bedrock-runtime", region_name="us-east-1")
    return client, Stubber(client)


def test_retry_when_parse_invalid_then_success() -> None:
    client, stubber = _build_stubbed_client()
    model_id = "us.amazon.nova-2-lite-v1:0"
    system_prompt = "System contract prompt"
    user_prompt = "User content"

    expected_first = {
        "modelId": model_id,
        "system": [{"text": system_prompt}],
        "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
        "inferenceConfig": {"maxTokens": 1400, "temperature": 0.1, "topP": 0.9},
    }
    expected_second = {
        "modelId": model_id,
        "system": [{"text": f"{system_prompt}\n{RETRY_SYSTEM_SUFFIX}"}],
        "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
        "inferenceConfig": {"maxTokens": 1400, "temperature": 0.1, "topP": 0.9},
    }

    stubber.add_response("converse", _converse_response("not json"), expected_first)
    stubber.add_response("converse", _converse_response(json.dumps(_valid_plan_payload())), expected_second)
    stubber.activate()

    agent = BedrockNovaAgent(client=client, model_id=model_id, region_name="us-east-1")
    plan, used_fallback = agent.analyze(
        system_text=system_prompt,
        user_text=user_prompt,
        snapshot=_snapshot_fixture(),
    )

    assert used_fallback is False
    assert plan.analysis_summary == "Validated plan"
    stubber.assert_no_pending_responses()
    stubber.deactivate()


def test_retry_when_schema_invalid_then_success() -> None:
    client, stubber = _build_stubbed_client()
    model_id = "us.amazon.nova-2-lite-v1:0"
    system_prompt = "System contract prompt"
    user_prompt = "User content"

    invalid_but_parseable = {"analysis_summary": "missing fields"}
    expected_first = {
        "modelId": model_id,
        "system": [{"text": system_prompt}],
        "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
        "inferenceConfig": {"maxTokens": 1400, "temperature": 0.1, "topP": 0.9},
    }
    expected_second = {
        "modelId": model_id,
        "system": [{"text": f"{system_prompt}\n{RETRY_SYSTEM_SUFFIX}"}],
        "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
        "inferenceConfig": {"maxTokens": 1400, "temperature": 0.1, "topP": 0.9},
    }

    stubber.add_response("converse", _converse_response(json.dumps(invalid_but_parseable)), expected_first)
    stubber.add_response("converse", _converse_response(json.dumps(_valid_plan_payload())), expected_second)
    stubber.activate()

    agent = BedrockNovaAgent(client=client, model_id=model_id, region_name="us-east-1")
    plan, used_fallback = agent.analyze(
        system_text=system_prompt,
        user_text=user_prompt,
        snapshot=_snapshot_fixture(),
    )

    assert used_fallback is False
    assert plan.metrics.monthly_cost_after_estimate == 90.0
    stubber.assert_no_pending_responses()
    stubber.deactivate()


def test_try_parse_json_salvages_wrapped_json() -> None:
    text = 'prefix text {"analysis_summary":"ok","identified_issues":[],"optimization_plan":[],"tradeoffs":[],"metrics":{"monthly_cost_before":1,"monthly_cost_after_estimate":1,"uptime_risk_before_0_to_10":1,"uptime_risk_after_0_to_10":1,"security_risk_before_0_to_10":1,"security_risk_after_0_to_10":1}} trailing'
    parsed = try_parse_json(text)
    assert parsed is not None
    assert parsed["analysis_summary"] == "ok"

