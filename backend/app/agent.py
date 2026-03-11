from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import boto3
from botocore.config import Config
from pydantic import ValidationError

from .schemas import Plan
from .sim import calculate_baseline_metrics

DEFAULT_REGION = "us-east-1"
DEFAULT_MODEL_ID = "us.amazon.nova-2-lite-v1:0"
RETRY_SYSTEM_SUFFIX = "RETURN JSON ONLY. NO MARKDOWN. NO EXTRA TEXT."


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    if not text or not text.strip():
        return None

    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        payload = json.loads(text[start : end + 1])
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        return None


def build_fallback_plan(snapshot: Dict[str, Any], reason: str) -> Plan:
    baseline = calculate_baseline_metrics(snapshot)
    fallback = {
        "analysis_summary": f"Fallback response used due to model output validation failure: {reason}",
        "identified_issues": [],
        "optimization_plan": [],
        "tradeoffs": [],
        "metrics": {
            "monthly_cost_before": float(baseline.monthly_cost_before),
            "monthly_cost_after_estimate": float(baseline.monthly_cost_before),
            "uptime_risk_before_0_to_10": float(baseline.uptime_risk_before_0_to_10),
            "uptime_risk_after_0_to_10": float(baseline.uptime_risk_before_0_to_10),
            "security_risk_before_0_to_10": float(baseline.security_risk_before_0_to_10),
            "security_risk_after_0_to_10": float(baseline.security_risk_before_0_to_10),
        },
    }
    return Plan.model_validate(fallback)


@dataclass
class AnalyzeResult:
    plan: Plan
    used_fallback: bool
    parse_retries_used: int
    failure_reason: str


class BedrockNovaAgent:
    def __init__(
        self,
        client: Any = None,
        *,
        region_name: Optional[str] = None,
        model_id: Optional[str] = None,
        connect_timeout: Optional[int] = None,
        read_timeout: Optional[int] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> None:
        self.region_name = region_name or os.getenv("AWS_REGION", DEFAULT_REGION)
        self.model_id = model_id or os.getenv("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)
        self.connect_timeout = connect_timeout if connect_timeout is not None else _env_int("NOVA_CONNECT_TIMEOUT", 30)
        self.read_timeout = read_timeout if read_timeout is not None else _env_int("NOVA_READ_TIMEOUT", 300)
        self.max_tokens = max_tokens if max_tokens is not None else _env_int("NOVA_MAX_TOKENS", 1400)
        self.temperature = temperature if temperature is not None else _env_float("NOVA_TEMPERATURE", 0.1)
        self.top_p = top_p if top_p is not None else _env_float("NOVA_TOP_P", 0.9)

        if client is None:
            config = Config(
                connect_timeout=self.connect_timeout,
                read_timeout=self.read_timeout,
                retries={"max_attempts": 3, "mode": "standard"},
            )
            self.client = boto3.client("bedrock-runtime", region_name=self.region_name, config=config)
        else:
            self.client = client

    def _extract_text(self, response: Dict[str, Any]) -> str:
        content_blocks = response.get("output", {}).get("message", {}).get("content", [])
        texts = []
        for block in content_blocks:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    texts.append(text)
        return "\n".join(texts).strip()

    def _invoke_converse(self, system_text: str, user_text: str) -> str:
        response = self.client.converse(
            modelId=self.model_id,
            system=[{"text": system_text}],
            messages=[{"role": "user", "content": [{"text": user_text}]}],
            inferenceConfig={
                "maxTokens": self.max_tokens,
                "temperature": self.temperature,
                "topP": self.top_p,
            },
        )
        return self._extract_text(response)

    def _build_fallback_plan(self, snapshot: Dict[str, Any], reason: str) -> Plan:
        return build_fallback_plan(snapshot, reason)

    def analyze_detailed(
        self,
        *,
        system_text: str,
        user_text: str,
        snapshot: Dict[str, Any],
    ) -> AnalyzeResult:
        failures = []
        parse_retries_used = 0
        system_attempts = [
            system_text,
            f"{system_text}\n{RETRY_SYSTEM_SUFFIX}",
        ]

        for attempt_idx in range(2):
            if attempt_idx == 1:
                parse_retries_used = 1

            try:
                raw_text = self._invoke_converse(system_attempts[attempt_idx], user_text)
            except Exception as exc:  # pragma: no cover - exception types vary by runtime
                failures.append(f"attempt {attempt_idx + 1} invoke error: {exc.__class__.__name__}")
                continue

            parsed = try_parse_json(raw_text)
            if parsed is None:
                failures.append(f"attempt {attempt_idx + 1} parse-invalid")
                continue

            try:
                plan = Plan.model_validate(parsed)
                return AnalyzeResult(
                    plan=plan,
                    used_fallback=False,
                    parse_retries_used=parse_retries_used,
                    failure_reason="",
                )
            except ValidationError as exc:
                failures.append(f"attempt {attempt_idx + 1} schema-invalid: {exc.errors()[0]['type']}")
                continue

        reason = "; ".join(failures) if failures else "unknown_error"
        return AnalyzeResult(
            plan=self._build_fallback_plan(snapshot, reason),
            used_fallback=True,
            parse_retries_used=parse_retries_used,
            failure_reason=reason,
        )

    def analyze(
        self,
        *,
        system_text: str,
        user_text: str,
        snapshot: Dict[str, Any],
    ) -> Tuple[Plan, bool]:
        result = self.analyze_detailed(system_text=system_text, user_text=user_text, snapshot=snapshot)
        return result.plan, result.used_fallback

