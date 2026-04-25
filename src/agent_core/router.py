from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.llm_service import LLMService

logger = logging.getLogger(__name__)

INTENT_LABELS = frozenset({"geo", "social", "memory", "plan"})

_KEYWORD_FALLBACK: dict[str, tuple[str, ...]] = {
    "social": ("搭子", "邀请", "匹配", "相似度", "buddy", "invite", "rank"),
    "memory": ("记住", "记忆", "偏好", "memory", "长期", "总结会话",
               "分析", "解读", "总结文档", "pdf", "文档", "附件", "analyze", "document", "file"),
    "plan": ("行程", "规划", "计划", "安排", "几天", "itinerary", "schedule", "plan"),
}

_SYSTEM_PROMPT = (
    "You are an intent classifier for a travel AI assistant. "
    "Classify the user's query into exactly ONE agent label:\n"
    "  - geo: travel spot search, place info, weather, POI lookup, trajectory, year review\n"
    "  - social: find travel buddy, invite someone, compatibility ranking\n"
    "  - memory: remember/recall user preferences, profile facts, long-term notes, "
    "analyze or summarize an uploaded document/PDF/file\n"
    "  - plan: create itinerary, multi-day schedule, trip planning\n"
    "Return JSON only: {\"agent\": \"<label>\", \"confidence\": 0.0-1.0}"
)


def route_agent(query: str, llm: "LLMService | None" = None) -> str:
    """Classify query intent via LLM with keyword fallback.

    Falls back to keyword heuristic if LLM is unavailable or errors.
    """
    if llm is not None and llm.is_enabled():
        try:
            label = _llm_route(query, llm)
            logger.debug("llm_route query=%r → %s", query[:60], label)
            return label
        except Exception as exc:
            logger.warning("llm_route failed, using keyword fallback: %s", exc)
    return _keyword_route(query)


def _llm_route(query: str, llm: "LLMService") -> str:
    raw = llm.chat(
        system_prompt=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": query}],
    )
    m = re.search(r"\{[\s\S]*?\}", raw)
    if m:
        try:
            payload = json.loads(m.group(0))
            label = str(payload.get("agent", "geo")).strip().lower()
            if label in INTENT_LABELS:
                return label
        except json.JSONDecodeError:
            pass
    return "geo"


def _keyword_route(query: str) -> str:
    q = query.strip().lower()
    for agent, hints in _KEYWORD_FALLBACK.items():
        if any(h in q for h in hints):
            return agent
    return "geo"
