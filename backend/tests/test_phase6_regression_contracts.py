from __future__ import annotations

from fastapi.testclient import TestClient

import backend.app.main as main_module


def test_analyze_contract_unchanged_required_fields(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_BEDROCK", "0")
    client = TestClient(main_module.app)
    response = client.post("/analyze", json={"goal": "regression check"})
    assert response.status_code == 200
    payload = response.json()
    assert "plan" in payload
    assert "simulation" in payload
    assert "used_fallback" in payload


def test_apply_contract_unchanged_required_fields(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_NOVA_ACT", "0")
    client = TestClient(main_module.app)
    response = client.post("/apply", json={})
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"run_id", "status", "steps", "notes"}


def test_voice_and_report_contracts_still_available(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_BEDROCK", "0")
    client = TestClient(main_module.app)

    analyze = client.post("/analyze", json={"goal": "report contract"})
    assert analyze.status_code == 200

    voice = client.post("/voice", json={"transcript": "help me optimize"})
    assert voice.status_code == 200
    voice_payload = voice.json()
    assert "normalized_goal" in voice_payload
    assert "voice_metadata" in voice_payload

    report = client.post("/report", json={})
    assert report.status_code == 200
    report_payload = report.json()
    assert "executive_summary" in report_payload
    assert "artifact_refs" in report_payload
