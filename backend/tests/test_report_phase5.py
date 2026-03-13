from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import backend.app.main as main_module


def test_report_generates_deterministic_artifact_from_cached_data(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_BEDROCK", "0")
    monkeypatch.setenv("ENABLE_NOVA_ACT", "0")
    artifact_dir = Path("backend") / "artifacts_phase5_test"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NOVA_ARTIFACTS_DIR", str(artifact_dir.resolve()))

    client = TestClient(main_module.app)
    analyze_response = client.post("/analyze", json={"goal": "Reduce monthly cost safely"})
    assert analyze_response.status_code == 200

    apply_response = client.post("/apply", json={})
    assert apply_response.status_code == 200

    report_response_1 = client.post("/report", json={})
    assert report_response_1.status_code == 200
    payload_1 = report_response_1.json()

    report_response_2 = client.post("/report", json={})
    assert report_response_2.status_code == 200
    payload_2 = report_response_2.json()

    assert payload_1["source"] == "latest_cached"
    assert payload_1["report_id"] == payload_2["report_id"]
    assert payload_1["executive_summary"]
    assert len(payload_1["highlights"]) >= 4
    assert len(payload_1["artifact_refs"]) >= 2
    for ref in payload_1["artifact_refs"]:
        assert Path(ref["file_path"]).exists()


def test_report_artifact_write_failure_is_swallowed(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LIVE_BEDROCK", "0")

    client = TestClient(main_module.app)
    analyze_response = client.post("/analyze", json={"goal": "Generate report with safe fallback on write failure"})
    assert analyze_response.status_code == 200

    def _raise_write_failure(*, report_id: str, payload: dict, markdown: str):
        del report_id, payload, markdown
        raise OSError("disk_unavailable")

    monkeypatch.setattr(main_module, "_write_report_artifacts", _raise_write_failure)

    report_response = client.post("/report", json={})
    assert report_response.status_code == 200
    payload = report_response.json()
    assert payload["report_id"].startswith("report_")
    assert payload["executive_summary"]
    assert payload["artifact_refs"] == []
