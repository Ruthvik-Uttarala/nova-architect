from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from .agent import DEFAULT_MODEL_ID, DEFAULT_REGION, BedrockNovaAgent, build_fallback_plan
from .schemas import (
    AnalyzeMetadata,
    AnalyzeRequest,
    AnalyzeResponse,
    ApplyRequest,
    ApplyResponse,
    ApplyStep,
    ArtifactReference,
    Plan,
    ReportRequest,
    ReportResponse,
    VoiceRequest,
    VoiceResponse,
)
from .sim import run_simulation

load_dotenv()

app = FastAPI(title="NovaArchitect Phase 1 Backend", version="1.0.0")

DATA_PATH = Path(__file__).resolve().parent / "data" / "infra_sample.json"
DEFAULT_ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts"
EVENT_HISTORY_FILE = "events_history.jsonl"

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

_LAST_ANALYZE_RESPONSE: Optional[dict] = None
_LAST_ANALYZE_GOAL: str = ""
_LAST_APPLY_RESPONSE: Optional[dict] = None


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


def _artifact_dir() -> Path:
    return Path(os.getenv("NOVA_ARTIFACTS_DIR", str(DEFAULT_ARTIFACTS_DIR)))


def _best_effort_log_event(event_type: str, payload: Dict[str, Any]) -> None:
    try:
        directory = _artifact_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / EVENT_HISTORY_FILE
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "payload": payload,
        }
        with path.open("a", encoding="utf-8") as out:
            out.write(json.dumps(record, ensure_ascii=True) + "\n")
    except Exception:
        return


def _maybe_write_analyze_artifact(
    *,
    goal: str,
    metadata: AnalyzeMetadata,
    plan: Plan,
) -> None:
    if os.getenv("ENABLE_ANALYZE_ARTIFACTS", "0").strip() != "1":
        return

    try:
        artifact_dir = _artifact_dir()
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


def _run_nova_sonic(
    *,
    transcript: str,
    latest_goal: Optional[str],
    latest_plan_summary: Optional[str],
) -> Any:
    # Lazy import keeps startup/test paths safe when optional voice path is unused.
    from .nova_sonic_runner import run_voice

    return run_voice(
        transcript=transcript,
        latest_goal=latest_goal,
        latest_plan_summary=latest_plan_summary,
    )


def _voice_fallback_response(request: VoiceRequest, reason: str) -> VoiceResponse:
    transcript = request.transcript or ""
    normalized_goal = _normalize_goal(transcript or (request.latest_goal or ""))
    if not normalized_goal:
        normalized_goal = "Optimize cost, reliability, and security for the current infrastructure."
    plan_context = _normalize_goal(request.latest_plan_summary or "")
    if plan_context:
        spoken_summary = f"Captured goal: {normalized_goal}. Prior plan context: {plan_context}"
    else:
        spoken_summary = f"Captured goal: {normalized_goal}. You can run Analyze now for a full validated plan."

    model_id = os.getenv("NOVA_SONIC_MODEL_ID", "us.amazon.nova-sonic-v1:0")
    region = os.getenv("NOVA_SONIC_REGION", os.getenv("AWS_REGION", DEFAULT_REGION))
    return VoiceResponse.model_validate(
        {
            "transcript": transcript,
            "normalized_goal": normalized_goal,
            "spoken_summary_text": spoken_summary,
            "voice_metadata": {
                "model_id": model_id,
                "aws_region": region,
                "voice_mode": "fallback",
                "used_fallback": True,
            },
        }
    )


def _cache_analyze_response(goal: str, response: AnalyzeResponse) -> dict:
    global _LAST_ANALYZE_RESPONSE, _LAST_ANALYZE_GOAL

    payload = response.model_dump()
    _LAST_ANALYZE_RESPONSE = payload
    _LAST_ANALYZE_GOAL = goal
    metadata = payload.get("analyze_metadata") or {}
    _best_effort_log_event(
        "analyze",
        {
            "goal": goal,
            "model_id": metadata.get("model_id", ""),
            "aws_region": metadata.get("aws_region", ""),
            "analyze_mode": metadata.get("analyze_mode", ""),
            "parse_retries_used": metadata.get("parse_retries_used", 0),
            "used_fallback": payload.get("used_fallback", False),
        },
    )
    return payload


def _cache_apply_response(response: ApplyResponse) -> dict:
    global _LAST_APPLY_RESPONSE

    payload = response.model_dump()
    _LAST_APPLY_RESPONSE = payload
    _best_effort_log_event(
        "apply",
        {
            "run_id": payload["run_id"],
            "status": payload["status"],
            "steps_count": len(payload["steps"]),
        },
    )
    return payload


def _first_items(items: List[str], limit: int) -> str:
    if not items:
        return "none"
    return ", ".join(items[:limit])


def _build_executive_summary(goal: str, analyze_data: AnalyzeResponse, apply_data: Optional[ApplyResponse]) -> str:
    cost = analyze_data.simulation.cost
    risk = analyze_data.simulation.risk
    issue_count = len(analyze_data.plan.identified_issues)
    action_count = len(analyze_data.plan.optimization_plan)
    base = (
        f"For goal '{goal}', NovaArchitect identified {issue_count} issue(s) and proposed {action_count} action(s). "
        f"Estimated monthly cost changes from {cost.monthly_cost_before:.1f} to {cost.monthly_cost_after_estimate:.1f} "
        f"(delta {cost.delta_usd_per_month:.1f}). Uptime risk shifts from {risk.uptime_risk_before_0_to_10:.1f} "
        f"to {risk.uptime_risk_after_0_to_10:.1f}, and security risk shifts from "
        f"{risk.security_risk_before_0_to_10:.1f} to {risk.security_risk_after_0_to_10:.1f}."
    )
    if apply_data is not None:
        base += f" Latest apply run status: {apply_data.status} (run_id {apply_data.run_id})."
    return base


def _build_report_markdown(
    *,
    report_id: str,
    generated_at_utc: str,
    goal: str,
    executive_summary: str,
    highlights: List[str],
) -> str:
    lines = [
        f"# NovaArchitect Executive Summary ({report_id})",
        "",
        f"- Generated at (UTC): {generated_at_utc}",
        f"- Goal: {goal}",
        "",
        "## Executive Summary",
        executive_summary,
        "",
        "## Highlights",
    ]
    lines.extend([f"- {line}" for line in highlights])
    lines.append("")
    return "\n".join(lines)


def _write_report_artifacts(
    *,
    report_id: str,
    payload: Dict[str, Any],
    markdown: str,
) -> List[ArtifactReference]:
    artifact_dir = _artifact_dir()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    json_path = artifact_dir / f"{report_id}.json"
    md_path = artifact_dir / f"{report_id}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return [
        ArtifactReference(label="Executive Summary (JSON)", file_path=str(json_path.resolve()), format="json"),
        ArtifactReference(label="Executive Summary (Markdown)", file_path=str(md_path.resolve()), format="md"),
    ]


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
    return _cache_analyze_response(goal, response)


@app.post("/voice", response_model=VoiceResponse)
def voice(request: VoiceRequest) -> dict:
    try:
        raw = _run_nova_sonic(
            transcript=request.transcript,
            latest_goal=request.latest_goal,
            latest_plan_summary=request.latest_plan_summary,
        )
        payload = raw.model_dump() if hasattr(raw, "model_dump") else raw
        response = VoiceResponse.model_validate(payload)
    except Exception as exc:
        response = _voice_fallback_response(request, f"voice_exception:{exc.__class__.__name__}")

    voice_payload = response.model_dump()
    _best_effort_log_event(
        "voice",
        {
            "transcript": voice_payload["transcript"][:300],
            "normalized_goal": voice_payload["normalized_goal"][:300],
            "voice_mode": voice_payload["voice_metadata"]["voice_mode"],
            "used_fallback": voice_payload["voice_metadata"]["used_fallback"],
        },
    )
    return voice_payload


@app.post("/report", response_model=ReportResponse)
def report(request: ReportRequest) -> dict:
    request_analyze = request.analyze_response
    request_apply = request.apply_run
    analyze_payload = request_analyze.model_dump() if request_analyze is not None else _LAST_ANALYZE_RESPONSE
    apply_payload = request_apply.model_dump() if request_apply is not None else _LAST_APPLY_RESPONSE

    if analyze_payload is None:
        raise HTTPException(status_code=400, detail="No analyze data available. Run /analyze first or supply analyze_response.")

    analyze_data = AnalyzeResponse.model_validate(analyze_payload)
    apply_data = ApplyResponse.model_validate(apply_payload) if apply_payload is not None else None

    goal = _normalize_goal(request.goal or _LAST_ANALYZE_GOAL)
    if not goal:
        goal = "Infrastructure optimization"

    executive_summary = _build_executive_summary(goal, analyze_data, apply_data)
    highlights = [
        f"Analysis summary: {analyze_data.plan.analysis_summary}",
        f"Top issues: {_first_items([x.issue for x in analyze_data.plan.identified_issues], 3)}",
        f"Recommended actions: {_first_items([x.action for x in analyze_data.plan.optimization_plan], 3)}",
        (
            "Cost view: "
            f"{analyze_data.simulation.cost.monthly_cost_before:.1f} -> "
            f"{analyze_data.simulation.cost.monthly_cost_after_estimate:.1f} "
            f"(delta {analyze_data.simulation.cost.delta_usd_per_month:.1f})"
        ),
    ]
    if apply_data is not None:
        highlights.append(f"Latest apply run: {apply_data.status} ({apply_data.run_id})")

    source = "latest_cached"
    if request.goal is not None or request_analyze is not None or request_apply is not None:
        source = "request_payload" if request_analyze is not None else "mixed"

    digest_source = (
        f"{goal}|{analyze_data.plan.analysis_summary}|"
        f"{analyze_data.simulation.cost.monthly_cost_before:.2f}|"
        f"{apply_data.status if apply_data is not None else 'none'}"
    )
    report_id = f"report_{hashlib.sha1(digest_source.encode('utf-8')).hexdigest()[:10]}"
    generated_at_utc = datetime.now(timezone.utc).isoformat()

    report_payload = {
        "report_id": report_id,
        "generated_at_utc": generated_at_utc,
        "goal": goal,
        "executive_summary": executive_summary,
        "highlights": highlights,
        "analysis": analyze_data.model_dump(),
        "apply": apply_data.model_dump() if apply_data is not None else None,
    }
    markdown_text = _build_report_markdown(
        report_id=report_id,
        generated_at_utc=generated_at_utc,
        goal=goal,
        executive_summary=executive_summary,
        highlights=highlights,
    )

    artifact_refs: List[ArtifactReference] = []
    try:
        artifact_refs = _write_report_artifacts(report_id=report_id, payload=report_payload, markdown=markdown_text)
    except Exception:
        artifact_refs = []

    response = ReportResponse(
        report_id=report_id,
        generated_at_utc=generated_at_utc,
        goal=goal,
        executive_summary=executive_summary,
        highlights=highlights,
        artifact_refs=artifact_refs,
        source=source,
    )
    response_payload = response.model_dump()
    _best_effort_log_event(
        "report",
        {
            "report_id": report_id,
            "goal": goal,
            "source": source,
            "artifact_count": len(artifact_refs),
        },
    )
    return response_payload


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
        return _cache_apply_response(response)

    if not os.getenv("NOVA_ACT_API_KEY", "").strip():
        response = ApplyResponse(
            run_id=_deterministic_run_id(effective_actions),
            status="failed",
            steps=[],
            notes="NOVA_ACT_API_KEY is required when ENABLE_NOVA_ACT=1.",
        )
        return _cache_apply_response(response)

    try:
        raw_result = _run_nova_act_apply(effective_actions)
    except Exception as exc:  # pragma: no cover - protects API from runtime SDK errors.
        response = ApplyResponse(
            run_id=_deterministic_run_id(effective_actions),
            status="failed",
            steps=[],
            notes=f"Nova Act execution failed before completion: {exc.__class__.__name__}",
        )
        return _cache_apply_response(response)

    try:
        validated = ApplyResponse.model_validate(raw_result)
    except ValidationError:
        validated = ApplyResponse(
            run_id=_deterministic_run_id(effective_actions),
            status="failed",
            steps=[],
            notes="Nova Act runner returned invalid response schema.",
        )
    return _cache_apply_response(validated)
