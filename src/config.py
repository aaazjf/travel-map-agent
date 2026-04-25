from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
  from dotenv import load_dotenv
except Exception:
  def load_dotenv(*_args, **_kwargs):
    return False


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
AGENT_FILES_DIR = DATA_DIR / "agent_files"
SUMMARY_MD_DIR = AGENT_FILES_DIR / "summaries"
ASSISTANT_ATTACHMENT_DIR = AGENT_FILES_DIR / "attachments"
DB_PATH = DATA_DIR / "travel_map.db"
DEFAULT_USER_ID = "demo_user"

load_dotenv(BASE_DIR / ".env")

AMAP_API_KEY: str = os.getenv("AMAP_API_KEY", "").strip()
AMAP_JS_KEY: str = os.getenv("AMAP_JS_KEY", "").strip()
AMAP_SECURITY_CODE: str = os.getenv("AMAP_SECURITY_CODE", "").strip()


@dataclass
class LLMConfig:
  provider: str
  api_key: str
  model: str
  base_url: str
  temperature: float
  max_tokens: int
  reflection_enabled: bool

  @property
  def enabled(self) -> bool:
    return bool(self.api_key and self.model)


@dataclass
class ContextBudgetConfig:
  total_tokens: int
  history_tokens: int
  memory_tokens: int
  spot_tokens: int
  auto_compress_threshold_tokens: int


def get_llm_config() -> LLMConfig:
  provider = os.getenv("LLM_PROVIDER", "none").strip().lower()
  temperature = _to_float(os.getenv("LLM_TEMPERATURE", "0.3"), 0.3)
  max_tokens = _to_int(os.getenv("LLM_MAX_TOKENS", "900"), 900)
  reflection_enabled = os.getenv("AGENT_ENABLE_REFLECTION", "true").strip().lower() in {"1", "true", "yes"}

  if provider == "openai":
    return LLMConfig(
      provider=provider,
      api_key=os.getenv("OPENAI_API_KEY", "").strip(),
      model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
      base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip(),
      temperature=temperature,
      max_tokens=max_tokens,
      reflection_enabled=reflection_enabled,
    )

  if provider == "deepseek":
    return LLMConfig(
      provider=provider,
      api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
      model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip(),
      base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").strip(),
      temperature=temperature,
      max_tokens=max_tokens,
      reflection_enabled=reflection_enabled,
    )

  if provider in {"kimi", "moonshot"}:
    return LLMConfig(
      provider="kimi",
      api_key=os.getenv("KIMI_API_KEY", "").strip(),
      model=os.getenv("KIMI_MODEL", "moonshot-v1-8k").strip(),
      base_url=os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1").strip(),
      temperature=temperature,
      max_tokens=max_tokens,
      reflection_enabled=reflection_enabled,
    )

  if provider == "custom":
    return LLMConfig(
      provider=provider,
      api_key=os.getenv("CUSTOM_API_KEY", "").strip(),
      model=os.getenv("CUSTOM_MODEL", "").strip(),
      base_url=os.getenv("CUSTOM_BASE_URL", "").strip(),
      temperature=temperature,
      max_tokens=max_tokens,
      reflection_enabled=reflection_enabled,
    )

  return LLMConfig(
    provider="none",
    api_key="",
    model="",
    base_url="",
    temperature=temperature,
    max_tokens=max_tokens,
    reflection_enabled=reflection_enabled,
  )


def get_context_budget_config() -> ContextBudgetConfig:
  total = _to_int(os.getenv("CTX_TOTAL_TOKENS", "3000"), 3000)
  history = _to_int(os.getenv("CTX_HISTORY_TOKENS", "1000"), 1000)
  memory = _to_int(os.getenv("CTX_MEMORY_TOKENS", "600"), 600)
  spot = _to_int(os.getenv("CTX_SPOT_TOKENS", "1000"), 1000)
  auto_compress_threshold = _to_int(os.getenv("AUTO_COMPRESS_THRESHOLD_TOKENS", "6000"), 6000)
  return ContextBudgetConfig(
    total_tokens=max(600, total),
    history_tokens=max(200, history),
    memory_tokens=max(150, memory),
    spot_tokens=max(250, spot),
    auto_compress_threshold_tokens=max(800, auto_compress_threshold),
  )


def _to_float(raw: str, fallback: float) -> float:
  try:
    return float(raw)
  except ValueError:
    return fallback


def _to_int(raw: str, fallback: int) -> int:
  try:
    return int(raw)
  except ValueError:
    return fallback
