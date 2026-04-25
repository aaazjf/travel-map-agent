from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.services.llm_service import LLMService


@dataclass
class SubTask:
    """A decomposed sub-task delegated to a specific agent by the Supervisor."""

    task_id: str
    agent: str
    query: str
    result: str = ""
    trace: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentContext:
    request_id: str
    user_id: str
    conversation_id: str | None
    query: str
    spots: list[dict[str, Any]]
    history: list[dict[str, str]]
    extra_context: str
    llm: LLMService
    route_agent: str
    subtasks: list[SubTask] = field(default_factory=list)
    parent_agent: str | None = None
