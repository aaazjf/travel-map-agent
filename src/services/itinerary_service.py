from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from src.db import get_conn


# City → country/region hint
_CITY_COUNTRY: dict[str, str] = {
    "京都": "日本", "东京": "日本", "大阪": "日本", "奈良": "日本", "横滨": "日本",
    "富士山": "日本", "镰仓": "日本", "福冈": "日本", "北海道": "日本", "冲绳": "日本",
    "巴黎": "法国", "里昂": "法国", "尼斯": "法国", "波尔多": "法国",
    "罗马": "意大利", "威尼斯": "意大利", "佛罗伦萨": "意大利", "米兰": "意大利",
    "巴塞罗那": "西班牙", "马德里": "西班牙",
    "伦敦": "英国", "爱丁堡": "英国",
    "纽约": "美国", "洛杉矶": "美国", "旧金山": "美国",
    "首尔": "韩国", "釜山": "韩国", "济州": "韩国",
    "曼谷": "泰国", "清迈": "泰国", "普吉": "泰国",
    "新加坡": "新加坡",
    "悉尼": "澳大利亚", "墨尔本": "澳大利亚",
}

COUNTRY_CITY_TEMPLATE: dict[str, list[str]] = {
    "日本": ["东京", "富士山河口湖", "上高地", "京都", "奈良", "大阪", "冲绳"],
    "中国": ["北京", "西安", "成都", "杭州", "三亚", "喀纳斯", "桂林"],
    "法国": ["巴黎", "尼斯", "里昂", "波尔多"],
    "意大利": ["罗马", "佛罗伦萨", "威尼斯", "米兰"],
    "韩国": ["首尔", "釜山", "济州"],
    "泰国": ["曼谷", "清迈", "普吉"],
}

THEME_KEYWORDS: dict[str, list[str]] = {
    "人文历史": ["人文", "历史", "建筑", "博物馆", "文化", "古迹", "寺庙", "遗址"],
    "美食探索": ["美食", "吃", "餐", "料理", "街食", "小吃"],
    "自然风光": ["自然", "风景", "山", "海", "湖", "森林", "国家公园"],
    "城市漫步": ["城市", "购物", "街区", "夜生活", "咖啡"],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_trip_request(query: str, destination: str = "", days: int = 0, theme: str = "") -> dict[str, Any]:
    text = (destination + " " + query).strip()

    # Days
    if not days:
        m_day = re.search(r"(\d+)\s*[天日]", text) or re.search(r"(\d+)\s*day", text, re.I)
        days = max(1, min(21, int(m_day.group(1)))) if m_day else 5

    # Country — check city hints first, then explicit country names
    country = "中国"
    for city, ctry in _CITY_COUNTRY.items():
        if city in text:
            country = ctry
            break
    else:
        for c in ["日本", "法国", "英国", "意大利", "韩国", "泰国", "美国", "澳大利亚", "新加坡"]:
            if c in text:
                country = c
                break

    # Theme
    if not theme:
        for t_name, keywords in THEME_KEYWORDS.items():
            if any(k in text for k in keywords):
                theme = t_name
                break
        else:
            theme = "自然风光"

    # Budget
    budget_level = "中等"
    if any(k in text for k in ["穷游", "省钱", "低预算", "经济"]):
        budget_level = "经济"
    elif any(k in text for k in ["豪华", "高端", "奢华", "luxury"]):
        budget_level = "高端"

    # Destination city
    dest_city = destination.strip() or next(
        (city for city in _CITY_COUNTRY if city in text), ""
    )

    return {
        "query": query,
        "destination": dest_city,
        "days": days,
        "country": country,
        "theme": theme,
        "budget_level": budget_level,
    }


def generate_trip_plan(
    query: str,
    destination: str = "",
    days: int = 0,
    theme: str = "",
) -> dict[str, Any]:
    parsed = parse_trip_request(query, destination=destination, days=days, theme=theme)
    n_days = int(parsed["days"])
    country = str(parsed["country"])
    dest = str(parsed["destination"])
    t = str(parsed["theme"])
    budget = str(parsed["budget_level"])

    # Try LLM generation first
    try:
        from src.services.llm_service import LLMService
        llm = LLMService()
        if llm.is_enabled():
            prompt = (
                f"请为用户生成一份详细的旅行行程规划。\n"
                f"目的地：{dest or country}\n"
                f"天数：{n_days} 天\n"
                f"风格/主题：{t}\n"
                f"预算：{budget}\n"
                f"用户需求：{query}\n\n"
                "请生成包含以下内容的 Markdown 格式行程：\n"
                "1. 每天的具体安排（上午/下午/晚上）\n"
                "2. 推荐景点与特色活动\n"
                "3. 交通建议\n"
                "4. 预算估算\n"
                "5. 实用小贴士"
            )
            md = llm.chat(
                system_prompt="你是专业旅行规划师，熟悉全球各地文化、景点和旅行实践。请生成详细、实用、有当地特色的行程规划。",
                messages=[{"role": "user", "content": prompt}],
            )
            if md and len(md) > 100:
                return {
                    "parsed": parsed,
                    "daily": [],
                    "transport": [],
                    "budget_hint": "",
                    "markdown": md,
                    "source": "llm",
                }
    except Exception:
        pass

    # Fallback: template-based generation
    city_pool = COUNTRY_CITY_TEMPLATE.get(country) or [dest or "核心城市", "自然区域", "文化古城"]
    if dest and dest not in city_pool:
        city_pool = [dest] + city_pool

    picks = city_pool[: min(len(city_pool), max(2, n_days // 2 + 1))]

    daily: list[dict[str, Any]] = []
    for i in range(n_days):
        city = picks[min(len(picks) - 1, i * len(picks) // n_days)]
        activity = {
            "人文历史": f"上午参观历史遗址或博物馆，下午漫步古街，晚上体验当地民俗（{city}）",
            "美食探索": f"上午逛早市，午餐尝试本地特色，下午街食探索，晚餐精品餐厅（{city}）",
            "自然风光": f"上午自然/山地徒步，下午核心景点，晚上本地餐食（{city}）",
            "城市漫步": f"上午特色街区漫步，下午购物体验，晚上夜生活（{city}）",
        }.get(t, f"上午自然/城市漫步，下午核心景点，晚上本地餐食（{city}）")
        daily.append({"day": i + 1, "city": city, "focus": t, "plan": activity})

    per_day_budget = {
        "经济": "400-700 RMB/天",
        "中等": "800-1500 RMB/天",
        "高端": "1800-3500 RMB/天",
    }.get(budget, "800-1500 RMB/天")

    transport = [
        "城市间优先高铁/航班，提前 7-14 天预订。",
        "市内优先地铁+步行，景区段可打车。",
        "自然景区建议预留机动半天，应对天气变化。",
    ]

    md_lines = [
        "# 行程规划建议",
        "",
        f"- 目的地：{dest or country}",
        f"- 天数：{n_days} 天",
        f"- 风格：{t}",
        f"- 预算：{budget}（{per_day_budget}）",
        "",
        "## 城市与天数拆分",
    ]
    for row in daily:
        md_lines.append(f"- Day {row['day']}: {row['city']} | {row['focus']}")
        md_lines.append(f"  - {row['plan']}")
    md_lines.extend(["", "## 交通建议"])
    for t_tip in transport:
        md_lines.append(f"- {t_tip}")
    md_lines.extend(["", "## 预算提示", f"- 建议人均：{per_day_budget}"])

    return {
        "parsed": parsed,
        "daily": daily,
        "transport": transport,
        "budget_hint": per_day_budget,
        "markdown": "\n".join(md_lines),
        "source": "template",
    }


def save_trip_plan(user_id: str, title: str, query: str, plan: dict[str, Any]) -> str:
    plan_id = str(uuid.uuid4())
    parsed = plan.get("parsed", {}) if isinstance(plan, dict) else {}
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO trip_plans (
              id, user_id, title, query_text, country, days, theme, budget_level, plan_markdown, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                user_id,
                title.strip() or "未命名行程",
                query,
                str(parsed.get("country", "")),
                int(parsed.get("days", 0) or 0),
                str(parsed.get("theme", "")),
                str(parsed.get("budget_level", "")),
                str(plan.get("markdown", "")),
                _now_iso(),
            ),
        )
    return plan_id


def list_trip_plans(user_id: str, limit: int = 30) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM trip_plans
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_trip_plan(plan_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    with get_conn() as conn:
        if user_id:
            row = conn.execute("SELECT * FROM trip_plans WHERE id = ? AND user_id = ?", (plan_id, user_id)).fetchone()
        else:
            row = conn.execute("SELECT * FROM trip_plans WHERE id = ?", (plan_id,)).fetchone()
    return dict(row) if row else None
