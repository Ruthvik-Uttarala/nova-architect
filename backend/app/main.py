from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from .agent import BedrockNovaAgent
from .schemas import AnalyzeRequest, AnalyzeResponse, ApplyRequest, ApplyResponse, ApplyStep, Plan
from .sim import run_simulation

load_dotenv()

app = FastAPI(title="NovaArchitect Phase 1 Backend", version="1.0.0")

DATA_PATH = Path(__file__).resolve().parent / "data" / "infra_sample.json"

SYSTEM_PROMPT = (
    "You are NovaArchitect Analyze Agent. "
    "Return exactly one JSON object that matches the output contract with no markdown."
)

OUTPUT_CONTRACT = {
    "analysis_summary": "string",
    "identified_issues": [
        {
            "issue": "string",
            "evidence": "string",
            "severity": "low|med|high",
        }
    ],
    "optimization_plan": [
        {
            "action": "string",
            "why": "string",
            "expected_impact": "string",
            "risk": "low|med|high",
        }
    ],
    "tradeoffs": [
        {
            "action": "string",
            "cost_change_usd_per_month": "number",
            "uptime_impact": "string",
            "security_impact": "string",
            "risk_score_0_to_10": "number(0..10)",
        }
    ],
    "metrics": {
        "monthly_cost_before": "number",
        "monthly_cost_after_estimate": "number",
        "uptime_risk_before_0_to_10": "number(0..10)",
        "uptime_risk_after_0_to_10": "number(0..10)",
        "security_risk_before_0_to_10": "number(0..10)",
        "security_risk_after_0_to_10": "number(0..10)",
    },
}

KNOWN_APPLY_ACTIONS = {"resize_instance", "enable_autoscaling", "enable_s3_encryption"}
DEFAULT_APPLY_ACTIONS = ["resize_instance", "enable_autoscaling", "enable_s3_encryption"]


def _normalize_goal(goal: str) -> str:
    return " ".join(goal.strip().split())


def _load_snapshot() -> dict:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Snapshot not found: {DATA_PATH}")
    with DATA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _build_user_prompt(goal: str, snapshot: dict) -> str:
    prompt_parts = [
        "GOAL:",
        goal,
        "INFRA_SNAPSHOT_JSON:",
        json.dumps(snapshot, separators=(",", ":"), ensure_ascii=True),
        "OUTPUT_CONTRACT_JSON:",
        json.dumps(OUTPUT_CONTRACT, separators=(",", ":"), ensure_ascii=True),
    ]
    return "\n".join(prompt_parts)


def _normalize_actions(actions: Iterable[str]) -> List[str]:
    normalized = []
    for action in actions:
        if isinstance(action, str):
            clean = action.strip()
            if clean:
                normalized.append(clean)
    return normalized


def _deterministic_run_id(actions: List[str]) -> str:
    digest = hashlib.sha1(",".join(actions).encode("utf-8")).hexdigest()[:10]
    return f"run_{digest}"


@app.get("/")
def health() -> dict:
    return {"ok": True}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> dict:
    goal = _normalize_goal(request.goal)
    if not goal:
        raise HTTPException(status_code=400, detail="goal must not be empty")

    try:
        snapshot = _load_snapshot()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to load infra snapshot: {exc}") from exc

    user_prompt = _build_user_prompt(goal, snapshot)
    agent = BedrockNovaAgent()

    plan, used_fallback = agent.analyze(system_text=SYSTEM_PROMPT, user_text=user_prompt, snapshot=snapshot)

    try:
        validated_plan = Plan.model_validate(plan.model_dump())
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail={"error": "plan validation failed", "details": exc.errors()}) from exc

    simulation = run_simulation(snapshot, validated_plan)
    response = AnalyzeResponse(plan=validated_plan, simulation=simulation, used_fallback=used_fallback)
    return response.model_dump()


@app.post("/apply", response_model=ApplyResponse)
def apply_changes(request: ApplyRequest) -> dict:
    requested_actions = _normalize_actions(request.actions)
    effective_actions = requested_actions if requested_actions else DEFAULT_APPLY_ACTIONS.copy()

    run_id = _deterministic_run_id(effective_actions)
    steps: List[ApplyStep] = [ApplyStep(step=1, action="open_console", result="ok")]

    has_known = False
    has_unknown = False

    for idx, action in enumerate(effective_actions, start=2):
        if action in KNOWN_APPLY_ACTIONS:
            has_known = True
            result = "ok"
        else:
            has_unknown = True
            result = "skipped_unknown_action"
        steps.append(ApplyStep(step=idx, action=action, result=result))

    if has_known and not has_unknown:
        status = "success"
        notes = "Simulated execution completed for all requested actions."
    elif has_known and has_unknown:
        status = "partial"
        notes = "Simulated execution completed for known actions; unknown actions were skipped."
    else:
        status = "failed"
        notes = "No executable known actions were provided."

    response = ApplyResponse(run_id=run_id, status=status, steps=steps, notes=notes)
    return response.model_dump()
