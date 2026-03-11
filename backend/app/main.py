from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from .agent import DEFAULT_MODEL_ID, DEFAULT_REGION, BedrockNovaAgent, build_fallback_plan
from .schemas import AnalyzeMetadata, AnalyzeRequest, AnalyzeResponse, ApplyRequest, ApplyResponse, ApplyStep, Plan
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


def _is_live_bedrock_enabled() -> bool:
    raw = os.getenv("ENABLE_LIVE_BEDROCK")
    if raw is None:
        return True
    value = raw.strip().lower()
    if not value:
        return True
    if value in {"0", "false", "off", "no"}:
        return False
    if value in {"1", "true", "on", "yes"}:
        return True
    return True


def _maybe_write_analyze_artifact(
    *,
    goal: str,
    metadata: AnalyzeMetadata,
    plan: Plan,
) -> None:
    if os.getenv("ENABLE_ANALYZE_ARTIFACTS", "0").strip() != "1":
        return

    try:
        default_dir = Path(__file__).resolve().parents[1] / "artifacts"
        artifact_dir = Path(os.getenv("ANALYZE_ARTIFACTS_DIR", str(default_dir)))
        artifact_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        digest = hashlib.sha1(goal.encode("utf-8")).hexdigest()[:8]
        artifact_path = artifact_dir / f"analyze_{stamp}_{digest}.json"

        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "goal": goal,
            "model_id": metadata.model_id,
            "aws_region": metadata.aws_region,
            "analyze_mode": metadata.analyze_mode,
            "used_fallback": metadata.used_fallback,
            "parse_retries_used": metadata.parse_retries_used,
            "analysis_summary": plan.analysis_summary[:300],
        }
        artifact_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        # Best-effort artifact writing only; never fail the analyze request.
        return


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


def _run_nova_act_apply(actions: List[str]) -> dict:
    # Lazy import keeps startup/test paths safe when nova-act is absent.
    from .nova_act_runner import run_apply

    return run_apply(actions)


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
    live_enabled = _is_live_bedrock_enabled()

    model_id = os.getenv("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)
    aws_region = os.getenv("AWS_REGION", DEFAULT_REGION)
    parse_retries_used = 0
    used_fallback = False
    plan: Plan

    if not live_enabled:
        used_fallback = True
        plan = build_fallback_plan(snapshot, "live_bedrock_disabled")
    else:
        try:
            agent = BedrockNovaAgent()
            model_id = agent.model_id
            aws_region = agent.region_name

            if hasattr(agent, "analyze_detailed"):
                detailed = agent.analyze_detailed(system_text=SYSTEM_PROMPT, user_text=user_prompt, snapshot=snapshot)
                plan = detailed.plan
                used_fallback = detailed.used_fallback
                parse_retries_used = detailed.parse_retries_used
            else:
                # Backward-compatible fallback for mocked agents that only expose analyze().
                plan, used_fallback = agent.analyze(system_text=SYSTEM_PROMPT, user_text=user_prompt, snapshot=snapshot)
                parse_retries_used = 1 if used_fallback else 0
        except Exception as exc:
            used_fallback = True
            plan = build_fallback_plan(snapshot, f"live_bedrock_exception:{exc.__class__.__name__}")
            parse_retries_used = 0

    try:
        validated_plan = Plan.model_validate(plan.model_dump())
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail={"error": "plan validation failed", "details": exc.errors()}) from exc

    simulation = run_simulation(snapshot, validated_plan)
    analyze_mode = "fallback" if (used_fallback or not live_enabled) else "live_bedrock"
    metadata = AnalyzeMetadata(
        model_id=model_id,
        aws_region=aws_region,
        analyze_mode=analyze_mode,
        parse_retries_used=parse_retries_used,
        used_fallback=used_fallback,
    )
    _maybe_write_analyze_artifact(goal=goal, metadata=metadata, plan=validated_plan)

    response = AnalyzeResponse(
        plan=validated_plan,
        simulation=simulation,
        used_fallback=used_fallback,
        analyze_metadata=metadata,
    )
    return response.model_dump()


@app.post("/apply", response_model=ApplyResponse)
def apply_changes(request: ApplyRequest) -> dict:
    requested_actions = _normalize_actions(request.actions)
    effective_actions = requested_actions if requested_actions else DEFAULT_APPLY_ACTIONS.copy()

    if os.getenv("ENABLE_NOVA_ACT", "0") != "1":
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

    if not os.getenv("NOVA_ACT_API_KEY", "").strip():
        response = ApplyResponse(
            run_id=_deterministic_run_id(effective_actions),
            status="failed",
            steps=[],
            notes="NOVA_ACT_API_KEY is required when ENABLE_NOVA_ACT=1.",
        )
        return response.model_dump()

    try:
        raw_result = _run_nova_act_apply(effective_actions)
    except Exception as exc:  # pragma: no cover - protects API from runtime SDK errors.
        response = ApplyResponse(
            run_id=_deterministic_run_id(effective_actions),
            status="failed",
            steps=[],
            notes=f"Nova Act execution failed before completion: {exc.__class__.__name__}",
        )
        return response.model_dump()

    try:
        validated = ApplyResponse.model_validate(raw_result)
    except ValidationError:
        validated = ApplyResponse(
            run_id=_deterministic_run_id(effective_actions),
            status="failed",
            steps=[],
            notes="Nova Act runner returned invalid response schema.",
        )
    return validated.model_dump()
