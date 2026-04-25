from src.agent_core.tools import external as _ext  # noqa: F401 — side-effect: registers all @tool entries

from src.agent_core.tools.registry import (
    call,
    get_max_calls,
    get_risk,
    get_specs,
    is_registered,
    list_tools,
)

__all__ = ["call", "get_specs", "is_registered", "get_risk", "get_max_calls", "list_tools"]
