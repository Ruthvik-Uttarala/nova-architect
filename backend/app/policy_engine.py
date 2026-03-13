from __future__ import annotations

from .schemas import ExecuteRealRequest, PolicyDecision

DEV_ACCOUNT_WARNING = (
    "Use a dedicated dev/staging AWS account with least privilege. "
    "Real production mutation is blocked in Phase 6."
)


def evaluate_policy(request: ExecuteRealRequest) -> PolicyDecision:
    warnings = [DEV_ACCOUNT_WARNING]

    if not request.approval_confirmed:
        return PolicyDecision(
            classification="blocked",
            allowed=False,
            requires_approval=True,
            reason="approval_required",
            warnings=warnings,
        )

    if request.action == "open_console_view":
        if request.execution_mode != "aws_console_safe":
            return PolicyDecision(
                classification="blocked",
                allowed=False,
                requires_approval=True,
                reason="open_console_view_requires_aws_console_safe_mode",
                warnings=warnings,
            )
        return PolicyDecision(
            classification="read_only",
            allowed=True,
            requires_approval=True,
            reason="read_only_navigation_allowed",
            warnings=warnings,
        )

    if request.action in {"apply_demo_tag", "remove_demo_tag"}:
        if request.execution_mode != "aws_api_safe_tag":
            return PolicyDecision(
                classification="blocked",
                allowed=False,
                requires_approval=True,
                reason="tag_actions_limited_to_aws_api_safe_tag_mode",
                warnings=warnings,
            )
        return PolicyDecision(
            classification="reversible_safe",
            allowed=True,
            requires_approval=True,
            reason="reversible_demo_tag_action_allowed",
            warnings=warnings,
        )

    return PolicyDecision(
        classification="blocked",
        allowed=False,
        requires_approval=True,
        reason="action_blocked_by_phase6_policy",
        warnings=warnings,
    )
