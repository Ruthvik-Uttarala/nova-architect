from __future__ import annotations

from backend.app.policy_engine import evaluate_policy
from backend.app.schemas import ExecuteRealRequest


def _req(**overrides) -> ExecuteRealRequest:
    payload = {
        "execution_mode": "aws_api_safe_tag",
        "resource_arn": "arn:aws:ec2:us-east-1:111122223333:instance/i-0123456789abcdef0",
        "resource_type": "ec2",
        "action": "apply_demo_tag",
        "approval_confirmed": True,
    }
    payload.update(overrides)
    return ExecuteRealRequest.model_validate(payload)


def test_policy_blocks_when_approval_missing() -> None:
    decision = evaluate_policy(_req(approval_confirmed=False))
    assert decision.allowed is False
    assert decision.classification == "blocked"
    assert decision.reason == "approval_required"


def test_policy_blocks_unsafe_mode_action_combo() -> None:
    decision = evaluate_policy(_req(execution_mode="aws_console_safe", action="apply_demo_tag"))
    assert decision.allowed is False
    assert decision.classification == "blocked"


def test_policy_allows_reversible_safe_tagging() -> None:
    decision = evaluate_policy(_req(action="remove_demo_tag", execution_mode="aws_api_safe_tag"))
    assert decision.allowed is True
    assert decision.classification == "reversible_safe"


def test_policy_allows_read_only_console_navigation() -> None:
    decision = evaluate_policy(_req(execution_mode="aws_console_safe", action="open_console_view"))
    assert decision.allowed is True
    assert decision.classification == "read_only"
