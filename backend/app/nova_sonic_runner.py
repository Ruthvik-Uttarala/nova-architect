from __future__ import annotations

import os
from typing import Dict, Optional

import boto3
from botocore.config import Config

from .agent import _env_float, _env_int
from .schemas import VoiceResponse

DEFAULT_SONIC_MODEL_ID = "us.amazon.nova-sonic-v1:0"


def _normalize_goal(*, transcript: str, latest_goal: Optional[str]) -> str:
    preferred = transcript if transcript and transcript.strip() else (latest_goal or "")
    normalized = " ".join(preferred.strip().split())
    return normalized or "Optimize cost, reliability, and security for the current infrastructure."


def _fallback_spoken_summary(normalized_goal: str, latest_plan_summary: Optional[str]) -> str:
    summary = " ".join((latest_plan_summary or "").strip().split())
    if summary:
        return f"Captured goal: {normalized_goal}. Prior plan context: {summary}"
    return f"Captured goal: {normalized_goal}. You can run Analyze now for a full validated plan."


def _extract_text(response: Dict[str, object]) -> str:
    content_blocks = response.get("output", {}).get("message", {}).get("content", [])
    texts = []
    if isinstance(content_blocks, list):
        for block in content_blocks:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    texts.append(text.strip())
    return " ".join(part for part in texts if part).strip()


def run_voice(
    *,
    transcript: str,
    latest_goal: Optional[str],
    latest_plan_summary: Optional[str],
    region_name: Optional[str] = None,
    model_id: Optional[str] = None,
) -> VoiceResponse:
    aws_region = (region_name or os.getenv("NOVA_SONIC_REGION") or os.getenv("AWS_REGION") or "us-east-1").strip()
    resolved_model_id = (model_id or os.getenv("NOVA_SONIC_MODEL_ID") or DEFAULT_SONIC_MODEL_ID).strip()
    normalized_goal = _normalize_goal(transcript=transcript, latest_goal=latest_goal)

    if os.getenv("ENABLE_NOVA_SONIC", "0").strip() != "1":
        return VoiceResponse.model_validate(
            {
                "transcript": transcript,
                "normalized_goal": normalized_goal,
                "spoken_summary_text": _fallback_spoken_summary(normalized_goal, latest_plan_summary),
                "voice_metadata": {
                    "model_id": resolved_model_id,
                    "aws_region": aws_region,
                    "voice_mode": "fallback",
                    "used_fallback": True,
                },
            }
        )

    try:
        config = Config(
            connect_timeout=_env_int("NOVA_CONNECT_TIMEOUT", 30),
            read_timeout=_env_int("NOVA_READ_TIMEOUT", 300),
            retries={"max_attempts": 3, "mode": "standard"},
        )
        client = boto3.client("bedrock-runtime", region_name=aws_region, config=config)
        max_tokens = _env_int("NOVA_SONIC_MAX_TOKENS", 200)
        temperature = _env_float("NOVA_SONIC_TEMPERATURE", 0.2)
        top_p = _env_float("NOVA_SONIC_TOP_P", 0.9)

        system_text = (
            "You are NovaArchitect voice assistant. "
            "Return one short spoken-style summary sentence only, no markdown."
        )
        user_text = (
            f"Transcript goal: {transcript}\n"
            f"Normalized goal: {normalized_goal}\n"
            f"Latest plan summary: {latest_plan_summary or 'none'}\n"
            "Produce a concise sentence the host can read aloud before pressing Analyze."
        )
        response = client.converse(
            modelId=resolved_model_id,
            system=[{"text": system_text}],
            messages=[{"role": "user", "content": [{"text": user_text}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature, "topP": top_p},
        )
        spoken_summary_text = _extract_text(response)
        if not spoken_summary_text:
            raise RuntimeError("empty_sonic_response")

        return VoiceResponse.model_validate(
            {
                "transcript": transcript,
                "normalized_goal": normalized_goal,
                "spoken_summary_text": spoken_summary_text,
                "voice_metadata": {
                    "model_id": resolved_model_id,
                    "aws_region": aws_region,
                    "voice_mode": "live_sonic",
                    "used_fallback": False,
                },
            }
        )
    except Exception:
        return VoiceResponse.model_validate(
            {
                "transcript": transcript,
                "normalized_goal": normalized_goal,
                "spoken_summary_text": _fallback_spoken_summary(normalized_goal, latest_plan_summary),
                "voice_metadata": {
                    "model_id": resolved_model_id,
                    "aws_region": aws_region,
                    "voice_mode": "fallback",
                    "used_fallback": True,
                },
            }
        )
