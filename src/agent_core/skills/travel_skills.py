from __future__ import annotations

from ..agents.geo_agent import GeoAgent
from ..agents.plan_agent import PlanAgent
from ..agents.social_agent import SocialAgent
from ..models import AgentContext
from ..tool_executor import ToolExecutor
from .registry import skill

# Shared executor & agents — Skills reuse the same agent instances as tools,
# so no extra cost; this is the whole point of the Skills layer.
_executor = ToolExecutor()
_geo = GeoAgent(_executor)
_plan = PlanAgent(_executor)
_social = SocialAgent(_executor)


@skill(
    name="年度总结",
    trigger="/年度总结",
    description="基于旅行记录生成年度统计 + AI 点评，绕过 Supervisor 直接调用 GeoAgent",
    patterns=["年度总结", "年终总结", "全年总结", "年度复盘", "旅行总结", "今年去了哪"],
)
def annual_summary(ctx: AgentContext) -> str:
    sub = _fork(ctx, "帮我生成旅行年度复盘，包含统计数据和证据点", route="skill:年度总结")
    reply, _ = _geo.handle(sub)
    return reply


@skill(
    name="找搭子",
    trigger="/找搭子",
    description="按轨迹相似度排列最佳旅行伙伴候选人，绕过 Supervisor 直接调用 SocialAgent",
    patterns=["找搭子", "旅行伙伴", "推荐搭子", "谁适合和我旅行", "find buddy", "travel buddy"],
)
def find_buddy(ctx: AgentContext) -> str:
    sub = _fork(ctx, "帮我查找最匹配的旅行搭子，列出前几名并给出匹配理由", route="skill:找搭子")
    reply, _ = _social.handle(sub)
    return reply


@skill(
    name="快速行程",
    trigger="/行程",
    description="输入目的地直接生成多日行程规划，绕过 Supervisor 直接调用 PlanAgent",
    patterns=["帮我规划", "规划行程", "制定行程", "几日游", "几天行程", "trip plan", "itinerary"],
)
def quick_itinerary(ctx: AgentContext) -> str:
    sub = _fork(ctx, ctx.query, route="skill:快速行程")
    reply, _ = _plan.handle(sub)
    return reply


# ── helper ────────────────────────────────────────────────────────────────────

def _fork(ctx: AgentContext, query: str, route: str) -> AgentContext:
    """Return a copy of ctx with a new query and route_agent label."""
    return AgentContext(
        request_id=f"{ctx.request_id}:skill",
        user_id=ctx.user_id,
        conversation_id=ctx.conversation_id,
        query=query,
        spots=ctx.spots,
        history=ctx.history,
        extra_context=ctx.extra_context,
        llm=ctx.llm,
        route_agent=route,
    )
