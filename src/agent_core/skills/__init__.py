from .registry import Skill, list_skills, match_skill
from . import travel_skills  # noqa: F401 — registers all @skill decorators

__all__ = ["Skill", "match_skill", "list_skills"]
