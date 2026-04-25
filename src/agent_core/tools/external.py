"""Agent 外部工具集

天气策略：
  - 国内城市 → 高德天气 API（精确 adcode/城市名）
  - 国际城市 → Open-Meteo（免费全球覆盖）
地理编码策略：
  - 国内 → 高德地理编码（快速）
  - 国际 → Open-Meteo Geocoding API（免费、全球）
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

from src.services import amap_client
from .registry import tool


# ─── web_search ──────────────────────────────────────────────────────────────

@tool(
    name="web_search",
    description=(
        "Search the web for real-time information about places, travel tips, local events, "
        "visa requirements, or any topic. Use this when you need external or up-to-date information."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "search query"},
            "max_results": {
                "type": "integer",
                "description": "number of results to return (default 5, max 10)",
            },
        },
        "required": ["query"],
    },
    risk="low",
    max_calls_per_request=4,
)
def web_search(args: dict[str, Any], **_: Any) -> dict[str, Any]:
    query = str(args.get("query", "")).strip()
    if not query:
        return {"ok": False, "error": "empty_query"}
    max_results = min(int(args.get("max_results") or 5), 10)
    try:
        try:
            from ddgs import DDGS  # type: ignore[import]
        except ImportError:
            from duckduckgo_search import DDGS  # type: ignore[import]

        with DDGS() as ddgs_client:
            raw = list(ddgs_client.text(query, max_results=max_results))
        if not raw:
            return {
                "ok": False,
                "error": "no_results",
                "hint": "搜索无结果。若在中国大陆运行，DuckDuckGo 通过 Bing 路由，可能被屏蔽，请检查代理设置。",
            }
        items = [
            {"title": r.get("title", ""), "snippet": r.get("body", ""), "url": r.get("href", "")}
            for r in raw
        ]
        return {"ok": True, "count": len(items), "items": items}
    except ImportError:
        return {"ok": False, "error": "search_package_not_installed", "hint": "pip install ddgs"}
    except Exception as exc:
        err = str(exc)
        result: dict[str, Any] = {"ok": False, "error": err}
        if any(k in err.lower() for k in ("connection", "timeout", "ssl", "network", "refused")):
            result["hint"] = "网络连接失败。若在中国大陆运行，DuckDuckGo 可能被屏蔽，建议检查代理设置。"
        return result


# ─── get_weather ─────────────────────────────────────────────────────────────

@tool(
    name="get_weather",
    description=(
        "Get current weather conditions and multi-day forecast for any location. "
        "Accepts a city name (Chinese or English) or 'lat,lng' coordinates. "
        "Returns temperature, humidity, wind speed, and daily forecast. "
        "For domestic Chinese cities, uses 高德 API; international cities use Open-Meteo."
    ),
    parameters={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "city name (e.g. '北京', 'Tokyo') or coordinates 'lat,lng'",
            },
            "days": {"type": "integer", "description": "forecast days 1-7 (default 3)"},
        },
        "required": ["location"],
    },
    risk="low",
    max_calls_per_request=4,
)
def get_weather(args: dict[str, Any], **_: Any) -> dict[str, Any]:
    location = str(args.get("location", "")).strip()
    if not location:
        return {"ok": False, "error": "empty_location"}
    days = max(1, min(int(args.get("days") or 3), 7))

    lat, lng, adcode = _resolve_location(location)
    if lat is None or lng is None:
        return {"ok": False, "error": f"could not resolve location: {location}"}

    # 国内城市：高德天气
    if adcode:
        result = amap_client.get_weather(adcode)
        if result:
            return _normalize_amap_weather(result, location, lat, lng, days)

    # 国际城市（或高德失败）：Open-Meteo
    return _open_meteo_weather(lat, lng, location, days)


# ─── geocode_place ────────────────────────────────────────────────────────────

@tool(
    name="geocode_place",
    description=(
        "Look up geographic details for any place name: coordinates (lat/lng), "
        "country, city, state, and full address. "
        "Use this to validate destinations or get coordinates before searching weather."
    ),
    parameters={
        "type": "object",
        "properties": {
            "place": {"type": "string", "description": "place name to look up"},
        },
        "required": ["place"],
    },
    risk="low",
    max_calls_per_request=6,
)
def geocode_place(args: dict[str, Any], **_: Any) -> dict[str, Any]:
    place = str(args.get("place", "")).strip()
    if not place:
        return {"ok": False, "error": "empty_place"}

    # 高德地理编码（国内）
    geo = amap_client.geocode(place)
    if geo:
        return {
            "ok": True,
            "lat": geo["lat"],
            "lng": geo["lng"],
            "country": geo.get("country", "中国"),
            "state": geo.get("province", ""),
            "city": geo.get("city", ""),
            "display_name": geo.get("formatted_address", place),
            "place_type": "domestic",
            "adcode": geo.get("adcode", ""),
        }

    # Open-Meteo Geocoding（国际）
    intl = _open_meteo_geocode(place)
    if intl:
        return {"ok": True, **intl, "place_type": "international"}

    return {"ok": False, "error": f"place not found: {place}"}


# ─── 位置解析（内部） ──────────────────────────────────────────────────────────

def _resolve_location(location: str) -> tuple[float | None, float | None, str]:
    """返回 (lat, lng, adcode)；adcode 为空字符串表示国际城市。"""
    loc = location.strip()

    # 显式经纬度格式 lat,lng
    m = re.match(r"^(-?\d+\.?\d*),\s*(-?\d+\.?\d*)$", loc)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        rev = amap_client.reverse_geocode(lat, lng)
        adcode = rev.get("adcode", "") if rev else ""
        return lat, lng, adcode

    # 高德地理编码（国内）
    geo = amap_client.geocode(loc)
    if geo:
        return geo["lat"], geo["lng"], geo.get("adcode", "")

    # Open-Meteo Geocoding（国际）
    intl = _open_meteo_geocode(loc)
    if intl:
        return intl["lat"], intl["lng"], ""

    return None, None, ""


# ─── Open-Meteo 地理编码（国际兜底） ─────────────────────────────────────────

def _open_meteo_geocode(name: str) -> dict[str, Any] | None:
    """免费全球地理编码，无需 API Key。"""
    try:
        params = urllib.parse.urlencode({
            "name": name, "count": 1, "language": "zh", "format": "json",
        })
        url = f"https://geocoding-api.open-meteo.com/v1/search?{params}"
        with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
            data = json.loads(resp.read())
        results = data.get("results") or []
        if not results:
            return None
        r = results[0]
        return {
            "lat": float(r["latitude"]),
            "lng": float(r["longitude"]),
            "country": r.get("country", ""),
            "state": r.get("admin1", ""),
            "city": r.get("name", name),
            "display_name": r.get("name", name),
        }
    except Exception:
        return None


# ─── Open-Meteo 天气（国际） ──────────────────────────────────────────────────

def _open_meteo_weather(lat: float, lng: float, location: str, days: int) -> dict[str, Any]:
    try:
        params = urllib.parse.urlencode({
            "latitude": lat, "longitude": lng,
            "current": "temperature_2m,weathercode,windspeed_10m,relative_humidity_2m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
            "forecast_days": days,
            "timezone": "auto",
        })
        url = f"https://api.open-meteo.com/v1/forecast?{params}"
        with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
            data = json.loads(resp.read())

        current = data.get("current", {})
        daily = data.get("daily", {})
        forecast = []
        for i, date in enumerate(daily.get("time", [])):
            forecast.append({
                "date": date,
                "max_temp_c": daily.get("temperature_2m_max", [None])[i],
                "min_temp_c": daily.get("temperature_2m_min", [None])[i],
                "precipitation_mm": daily.get("precipitation_sum", [None])[i],
                "condition": _wmo_description(int(daily.get("weathercode", [0])[i] or 0)),
                "night_condition": None,
            })

        return {
            "ok": True,
            "source": "open-meteo",
            "location": location,
            "lat": lat,
            "lng": lng,
            "current": {
                "temperature_c": current.get("temperature_2m"),
                "humidity_pct": current.get("relative_humidity_2m"),
                "windspeed_kmh": current.get("windspeed_10m"),
                "condition": _wmo_description(int(current.get("weathercode") or 0)),
            },
            "forecast": forecast,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ─── 高德天气格式转换 ─────────────────────────────────────────────────────────

def _normalize_amap_weather(
    result: dict[str, Any],
    location: str,
    lat: float,
    lng: float,
    days: int,
) -> dict[str, Any]:
    forecast = result.get("forecast", [])[:days]
    return {
        "ok": True,
        "source": "amap",
        "location": result.get("city", location),
        "lat": lat,
        "lng": lng,
        "current": result.get("current", {}),
        "forecast": forecast,
    }


# ─── WMO 气象代码（Open-Meteo 用） ───────────────────────────────────────────

_WMO_CODES: dict[int, str] = {
    0: "晴", 1: "基本晴朗", 2: "部分多云", 3: "阴天",
    45: "雾", 48: "冻雾",
    51: "小毛毛雨", 53: "中毛毛雨", 55: "大毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "中雪", 75: "大雪",
    80: "阵雨", 81: "中阵雨", 82: "强阵雨",
    95: "雷暴", 99: "雷暴伴冰雹",
}


def _wmo_description(code: int) -> str:
    return _WMO_CODES.get(code, f"天气码{code}")
