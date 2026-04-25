from __future__ import annotations

import json
import re
from typing import Any

from src.memory.service import retrieve_relevant_memories

from .context_manager import build_budgeted_context
from .models import AgentContext
from .tool_executor import ToolExecutor


MAX_TOOL_LOOPS = 8


def run_react(
  *,
  ctx: AgentContext,
  tool_executor: ToolExecutor,
  allowed_tools: list[str],
  system_prompt: str,
) -> tuple[str, dict[str, Any]]:
  llm = ctx.llm
  memories = retrieve_relevant_memories(ctx.user_id, ctx.query, limit=8)
  packed = build_budgeted_context(
    query=ctx.query,
    spots=ctx.spots,
    history=ctx.history,
    memories=memories,
  )

  trace: dict[str, Any] = {
    "route_agent": ctx.route_agent,
    "allowed_tools": allowed_tools,
    "guard_events": [],
    "memory_hits": [
      {
        "id": m.get("id"),
        "type": m.get("memory_type"),
        "confidence": m.get("confidence"),
        "content": str(m.get("content", ""))[:120],
      }
      for m in memories
    ],
    "context_budget": packed["stats"],
  }

  if not llm.is_enabled():
    return _fallback_reply(ctx, tool_executor, allowed_tools), trace

  messages: list[dict[str, Any]] = [
    {
      "role": "user",
      "content": (
        f"User query:\n{ctx.query}\n\n"
        f"Retrieved memories:\n{packed['memory_text'] or 'none'}\n\n"
        f"Conversation window:\n{packed['history_text'] or 'none'}\n\n"
        f"Travel context:\n{packed['spot_text'] or 'none'}\n\n"
        f"Attached docs context:\n{ctx.extra_context or 'none'}"
      ),
    }
  ]
  tools = tool_executor.get_specs(allowed_tools)
  seen_calls: dict[str, int] = {}

  for _ in range(MAX_TOOL_LOOPS):
    result = llm.chat_with_tools(system_prompt=system_prompt, messages=messages, tools=tools)
    assistant_content = result.get("content", "")
    tool_calls = result.get("tool_calls", [])

    if not tool_calls:
      final, reflection_meta = _finalize_with_reflection(
        ctx=ctx,
        draft=assistant_content or "Done.",
        packed_context=packed,
      )
      trace["reflection"] = reflection_meta
      trace["guard_events"].append({"event_type": "reflection", "payload": reflection_meta})
      return final, trace

    tool_entries = []
    for call in tool_calls:
      args = call["arguments"] if isinstance(call["arguments"], dict) else {}
      sig = f"{call['name']}::{json.dumps(args, ensure_ascii=False, sort_keys=True)}"
      seen_calls[sig] = seen_calls.get(sig, 0) + 1
      tool_entries.append(
        {
          "id": call["id"],
          "type": "function",
          "function": {
            "name": call["name"],
            "arguments": call.get("arguments_raw") or json.dumps(args, ensure_ascii=False),
          },
        }
      )

    messages.append({"role": "assistant", "content": assistant_content or "", "tool_calls": tool_entries})
    for call in tool_calls:
      args = call["arguments"] if isinstance(call["arguments"], dict) else {}
      tool_result = tool_executor.execute(ctx, call["name"], args)
      if tool_result.get("pending_approval"):
        pending_id = tool_result.get("pending_id")
        trace["guard_events"].append(
          {
            "event_type": "approval_pending",
            "payload": {"pending_id": pending_id, "tool_name": call["name"]},
          }
        )
        tool_display = _tool_display_name(call["name"])
        return (
          f"**{tool_display}** 需要您的授权才能执行。\n\n"
          f"已加入待审批队列（审批单 ID: {pending_id}），请在下方「待审批工具调用」面板中**批准**或**拒绝**。",
          trace,
        )
      if tool_result.get("blocked_by_policy"):
        trace["guard_events"].append(
          {
            "event_type": "policy_blocked",
            "payload": {"tool_name": call["name"], "reason": tool_result.get("reason", "")},
          }
        )

      messages.append(
        {
          "role": "tool",
          "tool_call_id": call["id"],
          "content": json.dumps(tool_result, ensure_ascii=False),
        }
      )

    if any(count >= 3 for count in seen_calls.values()):
      fallback = _loop_limit_fallback(ctx, tool_executor, allowed_tools)
      final, reflection_meta = _finalize_with_reflection(ctx=ctx, draft=fallback, packed_context=packed)
      trace["reflection"] = reflection_meta
      trace["guard_events"].append({"event_type": "loop_limit_reflection", "payload": reflection_meta})
      return final, trace

  fallback = _loop_limit_fallback(ctx, tool_executor, allowed_tools)
  final, reflection_meta = _finalize_with_reflection(ctx=ctx, draft=fallback, packed_context=packed)
  trace["reflection"] = reflection_meta
  trace["guard_events"].append({"event_type": "loop_limit_reflection", "payload": reflection_meta})
  return final, trace


def _finalize_with_reflection(ctx: AgentContext, draft: str, packed_context: dict[str, Any]) -> tuple[str, dict[str, Any]]:
  llm = ctx.llm
  if not llm.is_enabled():
    return draft, {"checked": False, "passed": True, "retried": False, "reason": "llm_disabled"}

  # When a document is attached, use it as context so the quality checker
  # evaluates the answer against the document rather than the travel spot list.
  extra = (ctx.extra_context or "").strip()
  context_text = extra if len(extra) > 80 else packed_context.get("spot_text", "")

  improved = llm.reflect(
    draft=draft,
    user_query=ctx.query,
    context_text=context_text,
  )
  check = _reflection_check(
    llm=llm,
    query=ctx.query,
    answer=improved,
    context_text=context_text,
  )
  if check.get("passed", True):
    return improved, {"checked": True, "passed": True, "retried": False, "reason": check.get("reason", "ok")}

  reason = check.get("reason", "quality_guard_failed")
  retry = _retry_answer(
    llm=llm,
    query=ctx.query,
    answer=improved,
    context_text=context_text,
    reason=reason,
  )
  return retry, {"checked": True, "passed": False, "retried": True, "reason": reason}


def _reflection_check(*, llm, query: str, answer: str, context_text: str) -> dict[str, Any]:
  try:
    raw = llm.chat(
      system_prompt=(
        "You are a strict answer quality checker. "
        "Return JSON only: {\"passed\": true|false, \"reason\": \"...\"}. "
        "Fail if answer does not address question, is too vague, or appears inconsistent with context."
      ),
      messages=[
        {
          "role": "user",
          "content": f"question:\n{query}\n\ncontext:\n{context_text}\n\nanswer:\n{answer}",
        }
      ],
    )
    payload = _extract_json(raw)
    return {
      "passed": bool(payload.get("passed", True)),
      "reason": str(payload.get("reason", "ok")),
    }
  except Exception:
    return {"passed": True, "reason": "check_failed_fallback_pass"}


def _retry_answer(*, llm, query: str, answer: str, context_text: str, reason: str) -> str:
  try:
    retried = llm.chat(
      system_prompt=(
        "You are an assistant revising an answer after quality check. "
        "Fix only the issues and keep it concise and factual."
      ),
      messages=[
        {
          "role": "user",
          "content": (
            f"question:\n{query}\n\ncontext:\n{context_text}\n\n"
            f"current_answer:\n{answer}\n\nissue:\n{reason}\n\n"
            "Please return an improved final answer."
          ),
        }
      ],
    )
    return retried or answer
  except Exception:
    return answer


def _extract_json(text: str) -> dict[str, Any]:
  try:
    return json.loads(text)
  except Exception:
    pass
  start = text.find("{")
  end = text.rfind("}")
  if start >= 0 and end > start:
    try:
      return json.loads(text[start : end + 1])
    except Exception:
      return {}
  return {}


def _fallback_reply(ctx: AgentContext, tool_executor: ToolExecutor, allowed_tools: list[str]) -> str:
  if "create_invite" in allowed_tools and _looks_like_invite_query(ctx.query):
    target = _extract_invite_target(ctx.query)
    if not target:
      return "我可以帮您发起邀请，请告诉我要邀请谁（例如：邀请 Alina）。"
    invite_result = tool_executor.execute(ctx, "create_invite", {"target": target})
    if invite_result.get("pending_approval"):
      pending_id = invite_result.get("pending_id")
      return (
        f"**发起旅行邀请** 需要您的授权才能执行。\n\n"
        f"已加入待审批队列（审批单 ID: {pending_id}），请在下方「待审批工具调用」面板中**批准**或**拒绝**。"
      )
    if invite_result.get("ok"):
      name = invite_result.get("to_name", target)
      score = invite_result.get("score", "")
      return f"邀请已发送给 **{name}**（匹配度 {score}%）。"
    error_code = invite_result.get("error_code") or invite_result.get("error") or ""
    if error_code == "TARGET_NOT_FOUND":
      return f"邀请失败，不存在「{target}」这个角色，请检查用户名后重试。"
    return f"邀请发送失败：{error_code or '未知错误'}。"

  if "rank_buddies" in allowed_tools:
    ranked = tool_executor.execute(ctx, "rank_buddies", {}).get("items", [])
    if not ranked:
      return "No buddy candidates available right now."
    top = ranked[0]
    return f"Routed to SocialAgent. Top match: {top['name']} (score {top['score']}%)."

  if "write_memory_note" in allowed_tools:
    return "Routed to MemoryAgent. LLM is not enabled. You can say: remember: <note>."

  return "Routed to GeoAgent. LLM is not enabled. You can ask to search spots by keyword."


def _loop_limit_fallback(ctx: AgentContext, tool_executor: ToolExecutor, allowed_tools: list[str]) -> str:
  if "rank_buddies" in allowed_tools:
    ranked = tool_executor.execute(ctx, "rank_buddies", {}).get("items", [])
    if not ranked:
      return "Tool loop was interrupted. No buddy candidates found."
    top = ranked[:3]
    text = ", ".join([f"{x['name']}({x['score']}%)" for x in top])
    return f"Tool loop was interrupted. Current top buddies: {text}."

  if "search_spots" in allowed_tools:
    spots = ctx.spots
    if not spots:
      return "Tool loop was interrupted. No travel records found yet."
    countries = {str(s.get("country", "")).strip() for s in spots if s.get("country")}
    top_places = ", ".join([str(s.get("place_name", "")) for s in spots[:5]])
    return (
      "Tool loop was interrupted, returning deterministic summary: "
      f"{len(spots)} spots, {len(countries)} countries/regions, recent places: {top_places}."
    )

  return "Tool loop was interrupted. Please retry with a narrower request."


_TOOL_DISPLAY: dict[str, str] = {
    "create_invite": "发起旅行邀请",
    "search_spots": "搜索旅行记录",
    "rank_buddies": "搭子匹配",
    "write_memory_note": "写入记忆",
    "get_weather": "查询天气",
    "web_search": "网络搜索",
    "geocode_place": "地点解析",
}


def _tool_display_name(name: str) -> str:
    return _TOOL_DISPLAY.get(name, name)


def _looks_like_invite_query(query: str) -> bool:
  q = query.lower()
  keywords = ["invite", "invitation", "send invite", "travel together", "buddy",
              "邀请", "一起旅行", "发起邀请", "搭子邀请"]
  return any(k in q for k in keywords)


def _extract_invite_target(query: str) -> str:
  # English style: invite Alina / invite Brian to ...
  m = re.search(r"\binvite\s+([A-Za-z][A-Za-z0-9_-]*)", query, flags=re.IGNORECASE)
  if m:
    return str(m.group(1)).strip()

  # Alternate English style: send invite to Alina
  m = re.search(r"\binvite\s+to\s+([A-Za-z][A-Za-z0-9_-]*)", query, flags=re.IGNORECASE)
  if m:
    return str(m.group(1)).strip()

  # Fallback: explicit user id style
  m = re.search(r"\b(u_[A-Za-z0-9_-]+)\b", query, flags=re.IGNORECASE)
  if m:
    return str(m.group(1)).strip()

  return ""
