from __future__ import annotations

import dataclasses
import json
import re
from collections import defaultdict
from datetime import datetime

from src.agent_core.models import AgentContext
from src.agent_core.react_runner import run_react
from src.agent_core.tool_executor import ToolExecutor

_WEATHER_KEYWORDS = (
    "天气", "气温", "温度", "下雨", "下雪", "晴", "阴", "雾", "风力", "空气", "湿度",
    "weather", "temperature", "forecast", "rain", "snow", "wind", "air quality",
)


class GeoAgent:
    name = "GeoAgent"

    def __init__(self, tool_executor: ToolExecutor) -> None:
        self.tool_executor = tool_executor

    def handle(self, ctx: AgentContext) -> tuple[str, dict]:
        if _is_review_query(ctx.query):
            reply = _build_review_report(ctx)
            trace = {
                "route_agent": ctx.route_agent,
                "allowed_tools": [],
                "guard_events": [{"event_type": "geo_review_path", "payload": {"enabled": True}}],
                "memory_hits": [],
                "context_budget": {},
            }
            return f"[GeoAgent] {reply}", trace

        # Weather queries: fetch data directly and format without going through ReAct loop.
        # This guarantees real data regardless of whether the LLM calls the tool.
        if _is_weather_query(ctx.query):
            return self._handle_weather(ctx)

        system_prompt = (
            "You are GeoAgent, a travel intelligence specialist. Your tools:\n"
            "  - search_spots: search the user's personal travel history by keyword\n"
            "  - geocode_place: get coordinates, country, city for any destination\n"
            "  - get_weather: fetch LIVE weather and forecast via Open-Meteo API\n"
            "  - web_search: find real-time travel info, tips, and local events\n\n"
            "Always call a tool first before answering. "
            "Use web_search for travel tips, best seasons, or current events. "
            "Use geocode_place for place/coordinate lookups. "
            "Use search_spots to find the user's own travel history."
        )
        reply, trace = run_react(
            ctx=ctx,
            tool_executor=self.tool_executor,
            allowed_tools=["search_spots", "geocode_place", "get_weather", "web_search"],
            system_prompt=system_prompt,
        )
        return f"[GeoAgent] {reply}", trace

    def _handle_weather(self, ctx: AgentContext) -> tuple[str, dict]:
        location = _extract_location(ctx.query) or ctx.query
        weather = self.tool_executor._execute_raw(ctx, "get_weather", {"location": location, "days": 3})
        trace = {
            "route_agent": ctx.route_agent,
            "allowed_tools": ["get_weather"],
            "guard_events": [{"event_type": "weather_direct_path",
                               "payload": {"location": location, "ok": weather.get("ok")}}],
            "memory_hits": [],
            "context_budget": {},
        }

        if not weather.get("ok"):
            err = weather.get("error", "unknown")
            reply = f"天气查询失败（{err}）。请检查网络连接或稍后重试。"
            return f"[GeoAgent] {reply}", trace

        # Format with LLM if available, otherwise build a plain text response
        if ctx.llm.is_enabled():
            prompt = (
                f"用户询问：{ctx.query}\n\n"
                f"以下是实时天气数据（来自 Open-Meteo API）：\n"
                f"{json.dumps(weather, ensure_ascii=False, indent=2)}\n\n"
                "请用中文、友好简洁的方式回答天气问题，包括当前状况和未来几天预报要点，"
                "并附上适合旅行的穿衣/活动建议。"
            )
            reply = ctx.llm.chat(
                system_prompt="你是专业旅行助手，善于解读天气数据并给出实用旅行建议。",
                messages=[{"role": "user", "content": prompt}],
            )
            return f"[GeoAgent] {reply}", trace

        # LLM disabled: plain text fallback
        cur = weather.get("current", {})
        lines = [
            f"📍 {location} 当前天气",
            f"- 气温：{cur.get('temperature_c', 'N/A')}°C",
            f"- 天气状况：{cur.get('condition', 'N/A')}",
            f"- 湿度：{cur.get('humidity_pct', 'N/A')}%",
            f"- 风速：{cur.get('windspeed_kmh', 'N/A')} km/h",
            "",
            "未来三天预报：",
        ]
        for day in weather.get("forecast", [])[:3]:
            lines.append(
                f"- {day['date']}: {day['condition']}  "
                f"{day['min_temp_c']}~{day['max_temp_c']}°C"
            )
        return f"[GeoAgent] " + "\n".join(lines), trace


def _is_review_query(query: str) -> bool:
    q = query.lower()
    hints = ("复盘", "年度", "总结", "严谨", "证据点", "evidence", "yearly review", "summary")
    return any(h in q for h in hints)


def _build_review_report(ctx: AgentContext) -> str:
    spots = ctx.spots or []
    if not spots:
        return "你还没有旅行记录，暂时无法生成年度复盘。"

    by_year: dict[str, list[dict]] = defaultdict(list)
    unknown_year: list[dict] = []
    for s in spots:
        y = _extract_year(str(s.get("travel_at") or s.get("created_at") or ""))
        if y:
            by_year[y].append(s)
        else:
            unknown_year.append(s)

    country_count = len(
        {str(s.get("country", "")).strip() for s in spots if str(s.get("country", "")).strip()}
    )
    city_count = len(
        {str(s.get("city", "")).strip() for s in spots if str(s.get("city", "")).strip()}
    )

    lines = [
        "年度旅行复盘（基于本地记录）",
        f"- 总记录数：{len(spots)}",
        f"- 覆盖国家/地区：{country_count}",
        f"- 覆盖城市：{city_count}",
    ]

    for year in sorted(by_year.keys(), reverse=True):
        items = sorted(by_year[year], key=lambda x: str(x.get("travel_at") or x.get("created_at") or ""))
        places = [str(i.get("place_name", "")).strip() for i in items if str(i.get("place_name", "")).strip()]
        lines.append(f"- {year} 年：{len(items)} 条，代表地点：{', '.join(places[:5])}")

    if unknown_year:
        lines.append(f"- 未标注年份记录：{len(unknown_year)} 条")

    lines.append("")
    lines.append("证据点（样例）")
    evidence = sorted(spots, key=lambda x: str(x.get("travel_at") or x.get("created_at") or ""), reverse=True)[:8]
    for idx, s in enumerate(evidence, start=1):
        when = str(s.get("travel_at") or s.get("created_at") or "未知时间")
        place = str(s.get("place_name", "")).strip() or "未知地点"
        geo = "/".join(x for x in [str(s.get("country", "")), str(s.get("city", ""))] if x.strip()) or "未知区域"
        note = str(s.get("note", "")).strip() or "无备注"
        lines.append(f"{idx}. {place} | {geo} | {when} | 备注：{note}")

    llm = ctx.llm
    if llm and llm.is_enabled():
        try:
            enhanced = llm.chat(
                system_prompt=(
                    "你是严谨的旅行分析助手。请基于给定事实生成年度复盘，"
                    "必须：1)结论可验证；2)显式引用证据点编号；3)不要编造事实。"
                ),
                messages=[{"role": "user", "content": "\n".join(lines)}],
            )
            if enhanced:
                return enhanced
        except Exception:
            pass

    return "\n".join(lines)


def _is_weather_query(query: str) -> bool:
    return any(k in query.lower() for k in _WEATHER_KEYWORDS)


def _extract_location(query: str) -> str:
    """Extract a city/location name from a weather query."""
    noise = (
        # Weather terms
        "天气", "气温", "温度", "下雨", "下雪", "晴朗", "空气", "湿度", "风力", "预报",
        "天气预报", "气象", "气候",
        # Query verbs / adverbs
        "查询", "查看", "查一下", "帮我查", "告诉我", "请问", "询问",
        "现在", "当前", "今天", "明天", "最近", "实时", "目前",
        # Trailing question words
        "情况", "状况", "怎么样", "如何", "怎样", "好不好",
        # English
        "weather", "temperature", "forecast", "air quality", "current", "today",
        "how", "what", "is", "the", "in", "at", "of", "like", "check",
    )
    cleaned = query.strip()
    # Sort by length desc so longer phrases are stripped before substrings
    for word in sorted(noise, key=len, reverse=True):
        cleaned = re.sub(re.escape(word), " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip("？?。，,")
    return cleaned if len(cleaned) >= 2 else ""


def _extract_year(text: str) -> str:
    raw = text.strip()
    if not raw:
        return ""
    formats = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M", "%Y/%m/%d")
    for candidate in (raw, raw[:19], raw[:10]):
        for fmt in formats:
            try:
                return str(datetime.strptime(candidate, fmt).year)
            except Exception:
                continue
    if len(raw) >= 4 and raw[:4].isdigit():
        return raw[:4]
    return ""
