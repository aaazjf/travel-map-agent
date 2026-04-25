from __future__ import annotations

import json
from typing import Any

from src.config import LLMConfig, get_llm_config


class LLMService:
  def __init__(self) -> None:
    self.cfg: LLMConfig = get_llm_config()
    self._client = None

  def is_enabled(self) -> bool:
    return self.cfg.enabled and self.cfg.provider != "none"

  def provider_label(self) -> str:
    if self.cfg.provider == "none":
      return "not_enabled"
    return f"{self.cfg.provider} / {self.cfg.model}"

  def chat(self, *, system_prompt: str, messages: list[dict[str, str]]) -> str:
    if not self.is_enabled():
      raise RuntimeError("LLM is not configured. Please set LLM_PROVIDER and provider API key in .env.")

    client = self._get_client()
    payload = [{"role": "system", "content": system_prompt}, *messages]
    response = client.chat.completions.create(
      model=self.cfg.model,
      messages=payload,
      temperature=self.cfg.temperature,
      max_tokens=self.cfg.max_tokens,
    )
    content = response.choices[0].message.content or ""
    return str(content).strip()

  def chat_with_tools(
    self,
    *,
    system_prompt: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
  ) -> dict[str, Any]:
    if not self.is_enabled():
      raise RuntimeError("LLM is not configured. Please set LLM_PROVIDER and provider API key in .env.")

    client = self._get_client()
    payload = [{"role": "system", "content": system_prompt}, *messages]
    response = client.chat.completions.create(
      model=self.cfg.model,
      messages=payload,
      tools=tools,
      tool_choice="auto",
      temperature=self.cfg.temperature,
      max_tokens=self.cfg.max_tokens,
    )
    msg = response.choices[0].message
    content = str(msg.content or "").strip()

    tool_calls = []
    for tc in (msg.tool_calls or []):
      args = tc.function.arguments or "{}"
      parsed = _safe_load_json(args)
      tool_calls.append(
        {
          "id": tc.id,
          "name": tc.function.name,
          "arguments": parsed,
          "arguments_raw": args,
        }
      )

    return {
      "content": content,
      "tool_calls": tool_calls,
    }

  def reflect(self, *, draft: str, user_query: str, context_text: str) -> str:
    if not self.is_enabled() or not self.cfg.reflection_enabled:
      return draft
    review_prompt = (
      "You are a quality checker for an agent response. Verify factual consistency with provided user context. "
      "If there are issues, return a corrected response. If no issue, return the draft as-is."
    )
    review_messages = [
      {
        "role": "user",
        "content": f"Question:\n{user_query}\n\nContext:\n{context_text}\n\nDraft:\n{draft}",
      }
    ]
    try:
      improved = self.chat(system_prompt=review_prompt, messages=review_messages)
      return improved or draft
    except Exception:
      return draft

  def _get_client(self):
    if self._client is not None:
      return self._client
    try:
      from openai import OpenAI
    except ImportError as exc:
      raise RuntimeError("Missing dependency openai. Run: pip install -r requirements.txt") from exc

    self._client = OpenAI(
      api_key=self.cfg.api_key,
      base_url=self.cfg.base_url or None,
    )
    return self._client


def compact_spot_context(spots: list[dict[str, Any]], limit: int = 15) -> str:
  if not spots:
    return "No travel spots available."
  lines = []
  for idx, spot in enumerate(spots[:limit], start=1):
    when = spot.get("travel_at") or spot.get("created_at")
    lines.append(
      f"{idx}. {spot.get('place_name', '')} | {spot.get('country', '')}/{spot.get('city', '')}/{spot.get('district', '')} "
      f"| ({spot.get('lat')}, {spot.get('lng')}) | {when} | note:{spot.get('note', '') or 'none'}"
    )
  if len(spots) > limit:
    lines.append(f"... and {len(spots) - limit} more records")
  return "\n".join(lines)


def _safe_load_json(text: str) -> dict[str, Any]:
  try:
    obj = json.loads(text)
    if isinstance(obj, dict):
      return obj
  except Exception:
    pass
  return {}
