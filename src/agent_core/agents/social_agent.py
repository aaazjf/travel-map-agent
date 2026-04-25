from __future__ import annotations

from src.agent_core.models import AgentContext
from src.agent_core.react_runner import run_react
from src.agent_core.tool_executor import ToolExecutor


class SocialAgent:
  name = "SocialAgent"

  def __init__(self, tool_executor: ToolExecutor) -> None:
    self.tool_executor = tool_executor

  def handle(self, ctx: AgentContext) -> tuple[str, dict]:
    system_prompt = (
      "You are SocialAgent. Handle buddy ranking, matching explanation, and invite actions. "
      "Use rank_buddies and create_invite responsibly."
    )
    reply, trace = run_react(
      ctx=ctx,
      tool_executor=self.tool_executor,
      allowed_tools=["rank_buddies", "create_invite"],
      system_prompt=system_prompt,
    )
    return f"[SocialAgent] {reply}", trace
