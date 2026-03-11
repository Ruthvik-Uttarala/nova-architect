from __future__ import annotations

import pytest

from backend.app.schemas import Plan
from backend.app.sim import calculate_baseline_metrics, run_simulation


def _snapshot_fixture() -> dict:
    return {
        "single_az_deployment": True,
        "no_autoscaling": True,
        "peak_multiplier": 3.0,
        "s3": {"default_encryption": False},
        "services": [
            {"name": "svc_a", "monthly_cost_usd": 100.0},
            {"name": "svc_b", "monthly_cost_usd": 50.0},
        ],
    }


def _plan_fixture() -> Plan:
    return Plan.model_validate(
        {
            "analysis_summary": "Plan generated",
            "identified_issues": [],
            "optimization_plan": [],
            "tradeoffs": [],
            "metrics": {
                "monthly_cost_before": 150.0,
                "monthly_cost_after_estimate": 120.0,
                "uptime_risk_before_0_to_10": 5.0,
                "uptime_risk_after_0_to_10": 2.0,
                "security_risk_before_0_to_10": 3.0,
                "security_risk_after_0_to_10": 1.0,
            },
        }
    )


def test_calculate_baseline_metrics_cost_and_risk_rules() -> None:
    baseline = calculate_baseline_metrics(_snapshot_fixture())
    assert baseline.monthly_cost_before == pytest.approx(150.0)
    assert baseline.uptime_risk_before_0_to_10 == pytest.approx(5.0)  # 3 + 2
    assert baseline.security_risk_before_0_to_10 == pytest.approx(3.0)  # +3


def test_run_simulation_outputs_deterministic_cost_and_scenarios() -> None:
    simulation = run_simulation(_snapshot_fixture(), _plan_fixture())
    assert simulation.cost.monthly_cost_before == pytest.approx(150.0)
    assert simulation.cost.monthly_cost_after_estimate == pytest.approx(120.0)
    assert simulation.cost.delta_usd_per_month == pytest.approx(-30.0)

    scenario_names = [scenario.name for scenario in simulation.scenarios]
    assert scenario_names == ["traffic_spike_3x", "single_instance_failure"]
    assert simulation.scenarios[0].baseline["error_rate_percent"] == pytest.approx(4.2)
    assert simulation.scenarios[1].after["outage_minutes"] == pytest.approx(2.0)
    assert simulation.risk.uptime_risk_before_0_to_10 == pytest.approx(5.0)
    assert simulation.risk.uptime_risk_after_0_to_10 == pytest.approx(2.0)

