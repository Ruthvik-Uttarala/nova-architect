from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.schemas import Plan


def _valid_plan_payload() -> dict:
    return {
        "analysis_summary": "Cost and resiliency opportunities identified.",
        "identified_issues": [
            {
                "issue": "Single AZ deployment",
                "evidence": "Compute tier runs in one AZ.",
                "severity": "high",
            }
        ],
        "optimization_plan": [
            {
                "action": "Enable autoscaling",
                "why": "Scale during peak demand",
                "expected_impact": "Lower errors during traffic spikes",
                "risk": "med",
            }
        ],
        "tradeoffs": [
            {
                "action": "Move to multi-AZ",
                "cost_change_usd_per_month": 120.0,
                "uptime_impact": "Improves availability",
                "security_impact": "Neutral",
                "risk_score_0_to_10": 4.0,
            }
        ],
        "metrics": {
            "monthly_cost_before": 775.7,
            "monthly_cost_after_estimate": 712.0,
            "uptime_risk_before_0_to_10": 6.0,
            "uptime_risk_after_0_to_10": 3.0,
            "security_risk_before_0_to_10": 4.0,
            "security_risk_after_0_to_10": 2.0,
        },
    }


def test_plan_schema_valid_payload_passes() -> None:
    payload = _valid_plan_payload()
    plan = Plan.model_validate(payload)
    assert plan.metrics.monthly_cost_before == pytest.approx(775.7)


def test_plan_schema_rejects_invalid_severity() -> None:
    payload = _valid_plan_payload()
    payload["identified_issues"][0]["severity"] = "critical"
    with pytest.raises(ValidationError):
        Plan.model_validate(payload)


def test_plan_schema_rejects_invalid_risk_score_range() -> None:
    payload = _valid_plan_payload()
    payload["tradeoffs"][0]["risk_score_0_to_10"] = 11.0
    with pytest.raises(ValidationError):
        Plan.model_validate(payload)

