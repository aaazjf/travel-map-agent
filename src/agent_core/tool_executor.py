from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.db import get_conn
from src.memory.service import add_memory_item
from src.services.llm_service import LLMService
from src.services.match_service import create_invite, rank_buddies
from src.services.spot_service import filter_spots, list_spots

from . import tools as tool_registry
from .models import AgentContext
from .policy import decide_tool_policy

logger = logging.getLogger(__name__)

# OpenAI-compatible tool specs for legacy inline tools
_LEGACY_SPECS: dict[str, dict[str, Any]] = {
    "search_spots": {
        "type": "function",
        "function": {
            "name": "search_spots",
            "description": "Search user travel spots by keyword in place/country/city/district/note.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "search keyword"},
                    "limit": {"type": "integer", "description": "max records to return, default 5"},
                },
                "required": ["keyword"],
            },
        },
    },
    "rank_buddies": {
        "type": "function",
        "function": {
            "name": "rank_buddies",
            "description": "Get buddy candidates ranked by trajectory similarity.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    "create_invite": {
        "type": "function",
        "function": {
            "name": "create_invite",
            "description": "Create an invite to a travel buddy by id or name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "buddy id (u_alina) or name (Alina)"},
                },
                "required": ["target"],
            },
        },
    },
    "write_memory_note": {
        "type": "function",
        "function": {
            "name": "write_memory_note",
            "description": "Write an internal memory note for future context retrieval.",
            "parameters": {
                "type": "object",
                "properties": {"note": {"type": "string", "description": "memory note text"}},
                "required": ["note"],
            },
        },
    },
}


class ToolExecutor:
    def __init__(self) -> None:
        self._request_call_counter: dict[str, int] = {}

    def get_specs(self, allowed: list[str]) -> list[dict[str, Any]]:
        """Return OpenAI tool specs for the given allowed tool names."""
        specs: list[dict[str, Any]] = []
        for name in allowed:
            if name in _LEGACY_SPECS:
                specs.append(_LEGACY_SPECS[name])
            else:
                registry_specs = tool_registry.get_specs([name])
                specs.extend(registry_specs)
        return specs

    def execute(self, ctx: AgentContext, name: str, args: dict[str, Any]) -> dict[str, Any]:
        call_count = self._inc_call_count(ctx.request_id, name)
        decision = decide_tool_policy(name, args, call_count)
        self._log_guard(
            ctx=ctx,
            event_type="policy_decision",
            payload={
                "tool": name,
                "risk": decision.risk,
                "call_count": call_count,
                "allowed": decision.allowed,
                "needs_approval": decision.needs_approval,
                "reason": decision.reason,
            },
        )

        if decision.needs_approval:
            pending_id = self._enqueue_pending(ctx=ctx, tool_name=name, args=args, reason=decision.reason)
            result: dict[str, Any] = {
                "ok": False,
                "error_code": "APPROVAL_REQUIRED",
                "pending_approval": True,
                "pending_id": pending_id,
                "tool_name": name,
                "reason": decision.reason,
            }
            self._log_tool_call(ctx, name, args, result)
            return result

        if not decision.allowed:
            result = {
                "ok": False,
                "error_code": "POLICY_BLOCKED",
                "blocked_by_policy": True,
                "tool_name": name,
                "reason": decision.reason,
            }
            self._log_tool_call(ctx, name, args, result)
            return result

        result = self._execute_raw(ctx, name, args)
        self._log_tool_call(ctx, name, args, result)
        return result

    def _execute_raw(self, ctx: AgentContext, name: str, args: dict[str, Any]) -> dict[str, Any]:
        user_spots = list_spots(ctx.user_id)

        if name == "search_spots":
            keyword = str(args.get("keyword", "")).strip()
            limit = max(1, min(int(args.get("limit") or 5), 20))
            items = filter_spots(user_spots, keyword)[:limit]
            return {
                "ok": True,
                "count": len(items),
                "items": [
                    {
                        "id": s["id"],
                        "place_name": s.get("place_name", ""),
                        "country": s.get("country", ""),
                        "city": s.get("city", ""),
                        "district": s.get("district", ""),
                        "travel_at": s.get("travel_at") or s.get("created_at"),
                    }
                    for s in items
                ],
            }

        if name == "rank_buddies":
            ranked = rank_buddies(user_spots)
            return {
                "ok": True,
                "count": len(ranked),
                "items": [{"id": r["id"], "name": r["name"], "score": r["score"]} for r in ranked],
            }

        if name == "create_invite":
            ranked = rank_buddies(user_spots)
            target = str(args.get("target", "")).strip().lower()
            picked = next(
                (it for it in ranked if target in {it["id"].lower(), it["name"].lower()}), None
            )
            if not picked:
                return {"ok": False, "error_code": "TARGET_NOT_FOUND", "error": "target_not_found"}
            create_invite(ctx.user_id, picked["id"], int(picked["score"]))
            return {
                "ok": True,
                "invite_sent": True,
                "to_user": picked["id"],
                "to_name": picked["name"],
                "score": picked["score"],
            }

        if name == "write_memory_note":
            note = str(args.get("note", "")).strip()
            if not note:
                return {"ok": False, "error_code": "EMPTY_NOTE", "error": "empty_note"}
            mem_result = add_memory_item(ctx.user_id, note, source="tool")
            return {"ok": True, "saved": True, "note_preview": note[:80], "memory_meta": mem_result}

        # Delegate to tool registry for dynamically registered tools
        if tool_registry.is_registered(name):
            return tool_registry.call(name, args, user_id=ctx.user_id)

        return {"ok": False, "error_code": "UNKNOWN_TOOL", "error": f"unknown_tool:{name}"}

    # ── internal helpers ──────────────────────────────────────────────────────

    def _inc_call_count(self, request_id: str, tool_name: str) -> int:
        key = f"{request_id}:{tool_name}"
        self._request_call_counter[key] = self._request_call_counter.get(key, 0) + 1
        return self._request_call_counter[key]

    def _enqueue_pending(
        self, ctx: AgentContext, tool_name: str, args: dict[str, Any], reason: str
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO agent_pending_actions (
                  request_id, user_id, conversation_id, route_agent,
                  tool_name, tool_args, status, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    ctx.request_id,
                    ctx.user_id,
                    ctx.conversation_id,
                    ctx.route_agent,
                    tool_name,
                    json.dumps(args, ensure_ascii=False),
                    reason,
                    now,
                ),
            )
        pending_id = int(cur.lastrowid)
        self._log_guard(
            ctx=ctx,
            event_type="approval_enqueued",
            payload={"pending_id": pending_id, "tool": tool_name, "reason": reason},
        )
        return pending_id

    def _log_guard(self, ctx: AgentContext, event_type: str, payload: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO agent_guard_logs (
                  request_id, user_id, conversation_id, route_agent,
                  event_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx.request_id,
                    ctx.user_id,
                    ctx.conversation_id,
                    ctx.route_agent,
                    event_type,
                    json.dumps(payload, ensure_ascii=False),
                    now,
                ),
            )

    def _log_tool_call(
        self, ctx: AgentContext, tool_name: str, args: dict[str, Any], result: dict[str, Any]
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        args_text = json.dumps(args, ensure_ascii=False)
        result_text = json.dumps(result, ensure_ascii=False)
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO agent_tool_logs (
                  request_id, user_id, conversation_id, route_agent,
                  tool_name, tool_args, tool_result, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx.request_id,
                    ctx.user_id,
                    ctx.conversation_id,
                    ctx.route_agent,
                    tool_name,
                    args_text,
                    result_text,
                    now,
                ),
            )
        logger.debug(
            "tool_call request=%s route=%s tool=%s args=%s",
            ctx.request_id,
            ctx.route_agent,
            tool_name,
            args_text,
        )


# ─── approval resolution (called from agent_service) ─────────────────────────


def list_pending_tool_approvals(user_id: str, limit: int = 30) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, request_id, conversation_id, route_agent,
                   tool_name, tool_args, reason, created_at
            FROM agent_pending_actions
            WHERE user_id = ? AND status = 'pending'
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        try:
            item["tool_args_obj"] = json.loads(item.get("tool_args") or "{}")
        except Exception:
            item["tool_args_obj"] = {}
        items.append(item)
    return items


def resolve_tool_approval(user_id: str, pending_id: int, action: str) -> dict[str, Any]:
    if action not in {"approve", "reject"}:
        return {"ok": False, "error_code": "INVALID_ACTION", "error": "invalid_action"}

    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM agent_pending_actions WHERE id = ? AND user_id = ? AND status = 'pending'",
            (pending_id, user_id),
        ).fetchone()
        if not row:
            return {"ok": False, "error_code": "PENDING_NOT_FOUND", "error": "pending_not_found"}
        data = dict(row)

    now = datetime.now(timezone.utc).isoformat()

    if action == "reject":
        with get_conn() as conn:
            conn.execute(
                "UPDATE agent_pending_actions SET status='rejected', resolved_at=? WHERE id=?",
                (now, pending_id),
            )
            if data.get("conversation_id"):
                tool_name = str(data["tool_name"])
                reject_msg = _format_approval_message(tool_name, None, approved=False)
                conn.execute(
                    "INSERT INTO agent_memory (conversation_id, user_id, role, content, created_at) VALUES (?,?,'assistant',?,?)",
                    (data["conversation_id"], str(data["user_id"]), reject_msg, now),
                )
        _insert_guard_log(
            request_id=str(data["request_id"]),
            user_id=str(data["user_id"]),
            conversation_id=data.get("conversation_id"),
            route_agent=str(data["route_agent"]),
            event_type="approval_rejected",
            payload={"pending_id": pending_id},
        )
        return {"ok": True, "status": "rejected", "pending_id": pending_id}

    ctx = AgentContext(
        request_id=str(data["request_id"]),
        user_id=str(data["user_id"]),
        conversation_id=data.get("conversation_id"),
        query="[approval_resume]",
        spots=list_spots(str(data["user_id"])),
        history=[],
        extra_context="",
        llm=LLMService(),
        route_agent=str(data["route_agent"]),
    )
    try:
        args = json.loads(str(data.get("tool_args") or "{}"))
    except Exception:
        args = {}

    executor = ToolExecutor()
    tool_name = str(data["tool_name"])
    result = executor._execute_raw(ctx, tool_name, args)
    executor._log_tool_call(ctx, f"{tool_name}[approved]", args, result)

    with get_conn() as conn:
        conn.execute(
            "UPDATE agent_pending_actions SET status='executed', resolved_at=?, tool_result=? WHERE id=?",
            (now, json.dumps(result, ensure_ascii=False), pending_id),
        )
        if data.get("conversation_id"):
            exec_msg = _format_approval_message(tool_name, result, approved=True)
            conn.execute(
                "INSERT INTO agent_memory (conversation_id, user_id, role, content, created_at) VALUES (?,?,'assistant',?,?)",
                (data["conversation_id"], str(data["user_id"]), exec_msg, now),
            )
    _insert_guard_log(
        request_id=str(data["request_id"]),
        user_id=str(data["user_id"]),
        conversation_id=data.get("conversation_id"),
        route_agent=str(data["route_agent"]),
        event_type="approval_executed",
        payload={"pending_id": pending_id, "tool": tool_name, "result_ok": bool(result.get("ok"))},
    )
    return {"ok": True, "status": "executed", "pending_id": pending_id, "tool_result": result}


def _format_approval_message(tool_name: str, result: dict[str, Any] | None, *, approved: bool) -> str:
    """Return a user-friendly Chinese message after a tool approval/rejection."""
    if not approved:
        return f"您已拒绝执行「{tool_name}」操作，本次请求已取消。"

    if result is None or not result.get("ok"):
        err = result.get("error_code") or result.get("error") or "未知错误" if result else "执行失败"
        return f"「{tool_name}」执行失败：{err}。"

    if tool_name == "create_invite":
        if result.get("ok"):
            name = result.get("to_name", result.get("to_user", "对方"))
            score = result.get("score", "")
            score_text = f"（匹配度 {score}%）" if score else ""
            return f"✅ 旅行邀请已成功发送给 **{name}**{score_text}！邀请记录已保存，等待对方回应。"
        error_code = result.get("error_code") or result.get("error") or ""
        if error_code == "TARGET_NOT_FOUND":
            return "邀请失败，不存在该角色，请检查用户名后重试。"
        return f"邀请发送失败：{error_code or '未知错误'}。"

    return f"「{tool_name}」已成功执行。"


def _insert_guard_log(
    *,
    request_id: str,
    user_id: str,
    conversation_id: str | None,
    route_agent: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO agent_guard_logs (
              request_id, user_id, conversation_id, route_agent,
              event_type, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                user_id,
                conversation_id,
                route_agent,
                event_type,
                json.dumps(payload, ensure_ascii=False),
                now,
            ),
        )
