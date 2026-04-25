from __future__ import annotations

from src.agent_core.models import AgentContext
from src.agent_core.react_runner import run_react
from src.agent_core.tool_executor import ToolExecutor


class MemoryAgent:
  name = "MemoryAgent"

  def __init__(self, tool_executor: ToolExecutor) -> None:
    self.tool_executor = tool_executor

  def handle(self, ctx: AgentContext) -> tuple[str, dict]:
    system_prompt = (
      "You are MemoryAgent. You handle two main tasks:\n"
      "1. Long-term memory: when the user wants to save or recall a preference, "
      "fact, or note, call write_memory_note.\n"
      "2. Document analysis: if an 'Attached docs context' section is present in the message, "
      "read it carefully and answer the user's question with a thorough, structured response. "
      "Do NOT call any tool for document analysis — respond directly with your analysis."
    )
    reply, trace = run_react(
      ctx=ctx,
      tool_executor=self.tool_executor,
      allowed_tools=["write_memory_note", "search_spots"],
      system_prompt=system_prompt,
    )
    return f"[MemoryAgent] {reply}", trace
