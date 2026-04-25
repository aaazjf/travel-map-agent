from __future__ import annotations

from typing import Any, Callable

_REGISTRY: dict[str, dict[str, Any]] = {}


def tool(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any],
    risk: str = "low",
    max_calls_per_request: int = 5,
) -> Callable:
    """Decorator to register an agent tool with its OpenAI-compatible spec."""

    def decorator(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        _REGISTRY[name] = {
            "fn": fn,
            "spec": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            },
            "risk": risk,
            "max_calls_per_request": max_calls_per_request,
        }
        return fn

    return decorator


def get_specs(names: list[str]) -> list[dict[str, Any]]:
    return [_REGISTRY[n]["spec"] for n in names if n in _REGISTRY]


def call(name: str, args: dict[str, Any], **ctx_kwargs: Any) -> dict[str, Any]:
    entry = _REGISTRY.get(name)
    if not entry:
        return {"ok": False, "error": f"unknown_tool:{name}"}
    try:
        return entry["fn"](args, **ctx_kwargs)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def is_registered(name: str) -> bool:
    return name in _REGISTRY


def get_risk(name: str) -> str:
    entry = _REGISTRY.get(name)
    return entry["risk"] if entry else "blocked"


def get_max_calls(name: str) -> int:
    entry = _REGISTRY.get(name)
    return entry.get("max_calls_per_request", 0) if entry else 0


def list_tools() -> list[str]:
    return list(_REGISTRY.keys())
