from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ..models import AgentContext

_registry: dict[str, "Skill"] = {}


@dataclass
class Skill:
    name: str
    trigger: str        # slash-command label, e.g. "/年度总结"
    description: str    # shown as tooltip in UI
    patterns: list[str] # natural-language keyword patterns
    handler: Callable   # (AgentContext) -> str


def skill(
    name: str,
    trigger: str,
    description: str,
    patterns: list[str],
) -> Callable:
    """Decorator that registers a function as a named Skill."""
    def decorator(fn: Callable) -> Callable:
        _registry[name] = Skill(
            name=name,
            trigger=trigger,
            description=description,
            patterns=patterns,
            handler=fn,
        )
        return fn
    return decorator


def match_skill(query: str) -> Skill | None:
    """Return the first Skill whose trigger or patterns match the query, else None."""
    q = query.strip().lower()
    for s in _registry.values():
        if q.startswith(s.trigger.lower()):
            return s
        if any(p in q for p in s.patterns):
            return s
    return None


def list_skills() -> list[Skill]:
    return list(_registry.values())
