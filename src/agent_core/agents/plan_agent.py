from __future__ import annotations

from src.agent_core.models import AgentContext
from src.agent_core.react_runner import run_react
from src.agent_core.tool_executor import ToolExecutor


class PlanAgent:
    name = "PlanAgent"

    def __init__(self, tool_executor: ToolExecutor) -> None:
        self.tool_executor = tool_executor

    def handle(self, ctx: AgentContext) -> tuple[str, dict]:
        system_prompt = (
            "You are PlanAgent, a specialist in creating detailed travel itineraries. "
            "Your capabilities:\n"
            "  - search_spots: check where the user has traveled before for inspiration\n"
            "  - geocode_place: get coordinates and details for destinations\n"
            "  - get_weather: provide weather context for travel dates\n"
            "  - web_search: find current travel tips, visa info, local events\n\n"
            "Structure every itinerary day-by-day with morning/afternoon/evening blocks. "
            "Include practical details: transport, estimated costs, must-see spots. "
            "Always verify destination coordinates with geocode_place first."
        )
        reply, trace = run_react(
            ctx=ctx,
            tool_executor=self.tool_executor,
            allowed_tools=["search_spots", "geocode_place", "get_weather", "web_search"],
            system_prompt=system_prompt,
        )
        return f"[PlanAgent] {reply}", trace
