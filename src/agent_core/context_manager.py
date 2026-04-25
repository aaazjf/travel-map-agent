from __future__ import annotations

from typing import Any

from src.config import get_context_budget_config
from src.services.llm_service import compact_spot_context


def estimate_tokens(text: str) -> int:
  if not text:
    return 0
  # Lightweight approximation without external tokenizer dependency.
  # Works reasonably for mixed Chinese/English product logs.
  return max(1, (len(text) + 3) // 4)


def build_budgeted_context(
  *,
  query: str,
  spots: list[dict[str, Any]],
  history: list[dict[str, str]],
  memories: list[dict[str, Any]],
) -> dict[str, Any]:
  cfg = get_context_budget_config()

  history_lines = [f"{m.get('role', 'user')}: {m.get('content', '')}" for m in history]
  history_text, history_used, history_tokens = _fit_from_end(history_lines, cfg.history_tokens)

  memory_lines = [
    f"{m.get('memory_type', 'fact')} | conf={m.get('confidence', 0)} | {m.get('content', '')}"
    for m in memories
  ]
  memory_text, memory_used, memory_tokens = _fit_from_start(memory_lines, cfg.memory_tokens)

  spot_text = compact_spot_context(spots, limit=18)
  spot_text = _fit_single_text(spot_text, cfg.spot_tokens)
  spot_tokens = estimate_tokens(spot_text)

  total_tokens = estimate_tokens(query) + history_tokens + memory_tokens + spot_tokens
  if total_tokens > cfg.total_tokens:
    overflow = total_tokens - cfg.total_tokens
    # Trim history first, then memory.
    if history_tokens > 0:
      history_text = _trim_by_tokens(history_text, max(0, history_tokens - overflow))
      history_tokens = estimate_tokens(history_text)
      overflow = estimate_tokens(query) + history_tokens + memory_tokens + spot_tokens - cfg.total_tokens
    if overflow > 0 and memory_tokens > 0:
      memory_text = _trim_by_tokens(memory_text, max(0, memory_tokens - overflow))
      memory_tokens = estimate_tokens(memory_text)

  return {
    "history_text": history_text,
    "memory_text": memory_text,
    "spot_text": spot_text,
    "stats": {
      "budgets": {
        "total_tokens": cfg.total_tokens,
        "history_tokens": cfg.history_tokens,
        "memory_tokens": cfg.memory_tokens,
        "spot_tokens": cfg.spot_tokens,
      },
      "history_used": history_used,
      "memory_used": memory_used,
      "history_tokens_used": history_tokens,
      "memory_tokens_used": memory_tokens,
      "spot_tokens_used": spot_tokens,
      "total_tokens_used": estimate_tokens(query) + history_tokens + memory_tokens + spot_tokens,
    },
  }


def _fit_from_end(lines: list[str], budget_tokens: int) -> tuple[str, int, int]:
  taken: list[str] = []
  used_tokens = 0
  count = 0
  for line in reversed(lines):
    add = estimate_tokens(line + "\n")
    if used_tokens + add > budget_tokens:
      break
    taken.append(line)
    used_tokens += add
    count += 1
  taken.reverse()
  text = "\n".join(taken)
  return text, count, estimate_tokens(text)


def _fit_from_start(lines: list[str], budget_tokens: int) -> tuple[str, int, int]:
  taken: list[str] = []
  used_tokens = 0
  count = 0
  for line in lines:
    add = estimate_tokens(line + "\n")
    if used_tokens + add > budget_tokens:
      break
    taken.append(line)
    used_tokens += add
    count += 1
  text = "\n".join(taken)
  return text, count, estimate_tokens(text)


def _fit_single_text(text: str, budget_tokens: int) -> str:
  if estimate_tokens(text) <= budget_tokens:
    return text
  return _trim_by_tokens(text, budget_tokens)


def _trim_by_tokens(text: str, target_tokens: int) -> str:
  if target_tokens <= 0:
    return ""
  if estimate_tokens(text) <= target_tokens:
    return text
  # coarse trim by chars, then fine tune
  rough_chars = target_tokens * 4
  trimmed = text[:rough_chars]
  while estimate_tokens(trimmed) > target_tokens and trimmed:
    trimmed = trimmed[:-8]
  return trimmed
