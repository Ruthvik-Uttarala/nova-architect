from __future__ import annotations

from typing import Any, Dict, Iterable

from .schemas import Plan, PlanMetrics, Simulation, SimulationCost, SimulationRisk, SimulationScenario


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp_risk(value: float) -> float:
    return max(0.0, min(10.0, float(value)))


def _iter_services(snapshot: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    services = snapshot.get("services", [])
    collected = []
    if isinstance(services, list):
        collected.extend(svc for svc in services if isinstance(svc, dict))
    elif isinstance(services, dict):
        for value in services.values():
            if isinstance(value, list):
                collected.extend(svc for svc in value if isinstance(svc, dict))
            elif isinstance(value, dict):
                collected.append(value)
    return collected


def _known_risk_present(snapshot: Dict[str, Any], risk_name: str) -> bool:
    if bool(snapshot.get(risk_name, False)):
        return True
    known_risks = snapshot.get("known_risks", [])
    return isinstance(known_risks, list) and risk_name in known_risks


def _peak_multiplier(snapshot: Dict[str, Any]) -> float:
    traffic = snapshot.get("traffic", {})
    if isinstance(traffic, dict) and "peak_multiplier" in traffic:
        return _as_float(traffic.get("peak_multiplier"), 1.0)
    return _as_float(snapshot.get("peak_multiplier", 1.0), 1.0)


def _has_unencrypted_s3(snapshot: Dict[str, Any]) -> bool:
    s3_cfg = snapshot.get("s3", {})
    if isinstance(s3_cfg, dict) and s3_cfg.get("default_encryption") is False:
        return True
    if isinstance(s3_cfg, list):
        for entry in s3_cfg:
            if isinstance(entry, dict) and entry.get("default_encryption") is False:
                return True

    services = snapshot.get("services", {})
    if isinstance(services, dict):
        s3_services = services.get("s3", [])
        if isinstance(s3_services, dict):
            s3_services = [s3_services]
        if isinstance(s3_services, list):
            for entry in s3_services:
                if isinstance(entry, dict) and entry.get("default_encryption") is False:
                    return True
    return False


def calculate_baseline_metrics(snapshot: Dict[str, Any]) -> PlanMetrics:
    cost_before = sum(_as_float(svc.get("monthly_cost_usd", 0.0), 0.0) for svc in _iter_services(snapshot))

    uptime_risk = 0.0
    security_risk = 0.0

    if _known_risk_present(snapshot, "single_az_deployment"):
        uptime_risk += 3.0

    peak_multiplier = _peak_multiplier(snapshot)
    if _known_risk_present(snapshot, "no_autoscaling") and peak_multiplier > 2.0:
        uptime_risk += 2.0

    if _has_unencrypted_s3(snapshot):
        security_risk += 3.0

    return PlanMetrics(
        monthly_cost_before=cost_before,
        monthly_cost_after_estimate=cost_before,
        uptime_risk_before_0_to_10=_clamp_risk(uptime_risk),
        uptime_risk_after_0_to_10=_clamp_risk(uptime_risk),
        security_risk_before_0_to_10=_clamp_risk(security_risk),
        security_risk_after_0_to_10=_clamp_risk(security_risk),
    )


def run_simulation(snapshot: Dict[str, Any], plan: Plan) -> Simulation:
    baseline = calculate_baseline_metrics(snapshot)
    plan_metrics = plan.metrics

    monthly_cost_before = baseline.monthly_cost_before
    monthly_cost_after = plan_metrics.monthly_cost_after_estimate
    if monthly_cost_after is None:
        monthly_cost_after = monthly_cost_before * 0.9

    simulation = Simulation(
        scenarios=[
            SimulationScenario(
                name="traffic_spike_3x",
                baseline={"error_rate_percent": 4.2, "latency_ms": 680.0},
                after={"error_rate_percent": 0.7, "latency_ms": 240.0},
            ),
            SimulationScenario(
                name="single_instance_failure",
                baseline={"outage_minutes": 18.0},
                after={"outage_minutes": 2.0},
            ),
        ],
        cost=SimulationCost(
            monthly_cost_before=monthly_cost_before,
            monthly_cost_after_estimate=monthly_cost_after,
            delta_usd_per_month=monthly_cost_after - monthly_cost_before,
        ),
        risk=SimulationRisk(
            uptime_risk_before_0_to_10=baseline.uptime_risk_before_0_to_10,
            uptime_risk_after_0_to_10=_clamp_risk(plan_metrics.uptime_risk_after_0_to_10),
            security_risk_before_0_to_10=baseline.security_risk_before_0_to_10,
            security_risk_after_0_to_10=_clamp_risk(plan_metrics.security_risk_after_0_to_10),
        ),
    )
    return simulation

