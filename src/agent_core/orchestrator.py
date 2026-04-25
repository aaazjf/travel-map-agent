from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from src.db import get_conn
from src.services.llm_service import LLMService

from .agents import GeoAgent, MemoryAgent, PlanAgent, SocialAgent
from .models import AgentContext, SubTask
from .router import route_agent
from .tool_executor import ToolExecutor

logger = logging.getLogger(__name__)

_SUPERVISOR_SYSTEM = (
    "You are a Supervisor Agent for a travel AI system. "
    "Decide if the user query needs ONE agent or multiple agents working together.\n\n"
    "Available agents:\n"
    "  - geo: travel spot search, place info, weather, POI lookup, trajectory review\n"
    "  - social: find travel buddy, invite, compatibility ranking\n"
    "  - memory: remember/recall preferences, profile facts, long-term notes, "
    "analyze or summarize an uploaded document/PDF/file\n"
    "  - plan: create itinerary, multi-day schedule, trip planning\n\n"
    "Rules:\n"
    "  - If the query clearly targets ONE agent: return a single-item array.\n"
    "  - If the query spans 2+ domains (e.g. 'plan a trip to Tokyo and check weather'): decompose.\n"
    "  - If the query mentions a document, file, PDF, or analysis of uploaded content: route to 'memory'.\n"
    "  - Maximum 3 subtasks.\n"
    "  - Each subtask must have a specific, focused query.\n\n"
    "Return JSON array only:\n"
    "[{\"task_id\": \"t1\", \"agent\": \"<label>\", \"query\": \"<specific sub-query>\"}, ...]"
)


class TravelOrchestrator:
    def __init__(self) -> None:
        self._executor = ToolExecutor()
        self._agents: dict[str, Any] = {
            "geo": GeoAgent(self._executor),
            "social": SocialAgent(self._executor),
            "memory": MemoryAgent(self._executor),
            "plan": PlanAgent(self._executor),
        }

    def run(
        self,
        *,
        user_id: str,
        query: str,
        spots: list[dict[str, Any]],
        conversation_id: str | None,
        history: list[dict[str, str]] | None = None,
        extra_context: str = "",
    ) -> str:
        llm = LLMService()
        request_id = str(uuid.uuid4())

        # Hint to supervisor when a document is attached so it routes to the right agent
        supervisor_query = query
        if extra_context and len(extra_context.strip()) > 100:
            supervisor_query = f"[用户上传了文档需要分析] {query}"

        subtasks = _supervisor_decompose(query=supervisor_query, llm=llm, request_id=request_id)

        if len(subtasks) <= 1:
            return self._run_single(
                request_id=request_id,
                user_id=user_id,
                query=query,
                spots=spots,
                conversation_id=conversation_id,
                history=history,
                extra_context=extra_context,
                llm=llm,
            )

        return self._run_multi(
            request_id=request_id,
            user_id=user_id,
            query=query,
            subtasks=subtasks,
            spots=spots,
            conversation_id=conversation_id,
            history=history,
            extra_context=extra_context,
            llm=llm,
        )

    # ── single-agent path ────────────────────────────────────────────────────

    def _run_single(
        self,
        *,
        request_id: str,
        user_id: str,
        query: str,
        spots: list[dict[str, Any]],
        conversation_id: str | None,
        history: list[dict[str, str]] | None,
        extra_context: str,
        llm: LLMService,
    ) -> str:
        routed = route_agent(query, llm)
        ctx = AgentContext(
            request_id=request_id,
            user_id=user_id,
            conversation_id=conversation_id,
            query=query,
            spots=spots,
            history=history or [],
            extra_context=extra_context,
            llm=llm,
            route_agent=routed,
        )
        logger.info("orchestrator single request=%s route=%s query=%r", request_id, routed, query[:60])
        agent = self._agents.get(routed, self._agents["geo"])
        reply, trace = agent.handle(ctx)
        self._log_run(ctx, trace)
        return reply

    # ── multi-agent supervisor path ──────────────────────────────────────────

    def _run_multi(
        self,
        *,
        request_id: str,
        user_id: str,
        query: str,
        subtasks: list[SubTask],
        spots: list[dict[str, Any]],
        conversation_id: str | None,
        history: list[dict[str, str]] | None,
        extra_context: str,
        llm: LLMService,
    ) -> str:
        logger.info(
            "orchestrator multi request=%s subtasks=%d query=%r",
            request_id,
            len(subtasks),
            query[:60],
        )
        for st in subtasks:
            agent = self._agents.get(st.agent, self._agents["geo"])
            sub_ctx = AgentContext(
                request_id=f"{request_id}:{st.task_id}",
                user_id=user_id,
                conversation_id=conversation_id,
                query=st.query,
                spots=spots,
                history=history or [],
                extra_context=extra_context,
                llm=llm,
                route_agent=st.agent,
                parent_agent="supervisor",
            )
            reply, trace = agent.handle(sub_ctx)
            st.result = reply
            st.trace = trace
            self._log_run(sub_ctx, trace)
            logger.debug("subtask %s:%s done len=%d", request_id, st.task_id, len(reply))

        return _synthesize(query=query, subtasks=subtasks, llm=llm)

    # ── logging ──────────────────────────────────────────────────────────────

    def _log_run(self, ctx: AgentContext, trace: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        memory_hits = trace.get("memory_hits", [])
        budget = trace.get("context_budget", {})
        guard_events = trace.get("guard_events", [])
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO agent_run_logs (
                  request_id, user_id, conversation_id, route_agent, query_text,
                  memory_hits_json, context_budget_json, history_used, memory_used, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx.request_id,
                    ctx.user_id,
                    ctx.conversation_id,
                    ctx.route_agent,
                    ctx.query,
                    json.dumps(memory_hits, ensure_ascii=False),
                    json.dumps(budget, ensure_ascii=False),
                    int(budget.get("history_used", 0)),
                    int(budget.get("memory_used", 0)),
                    now,
                ),
            )
            for evt in guard_events:
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
                        str(evt.get("event_type", "unknown")),
                        json.dumps(evt.get("payload", {}), ensure_ascii=False),
                        now,
                    ),
                )


# ─── supervisor helpers ───────────────────────────────────────────────────────


def _supervisor_decompose(query: str, llm: LLMService, request_id: str) -> list[SubTask]:
    """Ask the LLM supervisor to decompose the query into agent subtasks."""
    if not llm.is_enabled():
        return []
    try:
        raw = llm.chat(
            system_prompt=_SUPERVISOR_SYSTEM,
            messages=[{"role": "user", "content": query}],
        )
        m = re.search(r"\[[\s\S]*\]", raw)
        if not m:
            return []
        tasks_data = json.loads(m.group(0))
        result: list[SubTask] = []
        for t in tasks_data[:3]:
            if not isinstance(t, dict):
                continue
            agent = str(t.get("agent", "geo")).strip().lower()
            sub_query = str(t.get("query", "")).strip()
            if not sub_query:
                continue
            if agent not in {"geo", "social", "memory", "plan"}:
                agent = "geo"
            result.append(
                SubTask(
                    task_id=str(t.get("task_id", uuid.uuid4().hex[:6])),
                    agent=agent,
                    query=sub_query,
                )
            )
        logger.debug("supervisor decomposed %d subtasks for request=%s", len(result), request_id)
        return result
    except Exception as exc:
        logger.warning("supervisor_decompose failed: %s", exc)
        return []


def _synthesize(query: str, subtasks: list[SubTask], llm: LLMService) -> str:
    """Merge multi-agent results into a single coherent reply."""
    if not subtasks:
        return "No results available."
    if len(subtasks) == 1:
        return subtasks[0].result

    parts = "\n\n".join(
        f"[{st.agent.upper()} — {st.query}]\n{st.result}" for st in subtasks
    )

    if not llm.is_enabled():
        return parts

    try:
        merged = llm.chat(
            system_prompt=(
                "You are a synthesis assistant. Merge the following multi-agent results "
                "into one coherent, well-structured response for the user. "
                "Eliminate redundancy. Preserve all key facts. Be concise."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"User's original query: {query}\n\nAgent results:\n{parts}",
                }
            ],
        )
        return merged or parts
    except Exception:
        return parts
