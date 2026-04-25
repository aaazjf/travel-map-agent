from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PolicyDecision:
    allowed: bool
    needs_approval: bool
    risk: str
    reason: str


@dataclass
class ToolPolicy:
    risk: str
    require_approval: bool
    max_calls_per_request: int


# Legacy tool policies (inline-implemented tools)
_STATIC_POLICIES: dict[str, ToolPolicy] = {
    "search_spots": ToolPolicy(risk="low", require_approval=False, max_calls_per_request=6),
    "rank_buddies": ToolPolicy(risk="low", require_approval=False, max_calls_per_request=4),
    "write_memory_note": ToolPolicy(risk="medium", require_approval=False, max_calls_per_request=3),
    "create_invite": ToolPolicy(risk="high", require_approval=True, max_calls_per_request=2),
}


def decide_tool_policy(
    tool_name: str,
    args: dict[str, Any],
    call_count: int,
) -> PolicyDecision:
    # Check static policy table first
    cfg = _STATIC_POLICIES.get(tool_name)
    if cfg:
        return _evaluate(tool_name=tool_name, args=args, call_count=call_count, cfg=cfg)

    # Fall back to registry-based policy for dynamically registered tools
    try:
        from src.agent_core import tools as tool_registry

        if tool_registry.is_registered(tool_name):
            risk = tool_registry.get_risk(tool_name)
            max_calls = tool_registry.get_max_calls(tool_name)
            dyn_cfg = ToolPolicy(
                risk=risk,
                require_approval=False,
                max_calls_per_request=max_calls,
            )
            return _evaluate(tool_name=tool_name, args=args, call_count=call_count, cfg=dyn_cfg)
    except Exception as exc:
        logger.debug("registry policy lookup failed for %s: %s", tool_name, exc)

    return PolicyDecision(
        allowed=False,
        needs_approval=False,
        risk="blocked",
        reason=f"tool_not_registered:{tool_name}",
    )


def _evaluate(
    tool_name: str,
    args: dict[str, Any],
    call_count: int,
    cfg: ToolPolicy,
) -> PolicyDecision:
    if call_count > cfg.max_calls_per_request:
        return PolicyDecision(
            allowed=False,
            needs_approval=False,
            risk=cfg.risk,
            reason="rate_limit_exceeded",
        )

    if tool_name == "create_invite":
        if not str(args.get("target", "")).strip():
            return PolicyDecision(
                allowed=False,
                needs_approval=False,
                risk=cfg.risk,
                reason="missing_target",
            )

    if cfg.require_approval:
        return PolicyDecision(
            allowed=False,
            needs_approval=True,
            risk=cfg.risk,
            reason="human_approval_required",
        )

    return PolicyDecision(
        allowed=True,
        needs_approval=False,
        risk=cfg.risk,
        reason="allowed",
    )
