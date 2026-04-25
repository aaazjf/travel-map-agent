"""高德地图 REST API 客户端（v3）

覆盖能力：
  - geocode        地名/地址 → 经纬度 + adcode（仅国内）
  - reverse_geocode 经纬度 → 行政区划
  - search_poi     POI 关键词搜索
  - get_weather    实况 + 预报天气（仅国内，adcode 或 城市名）

国际城市地理编码请通过 Open-Meteo geocoding API 兜底（见 external.py）。
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

_BASE = "https://restapi.amap.com/v3"


# ─── 内部工具 ────────────────────────────────────────────────────────────────

def _key() -> str:
    k = os.getenv("AMAP_API_KEY", "").strip()
    if not k:
        raise RuntimeError("AMAP_API_KEY 未配置，请在 .env 中设置。")
    return k


def _get(path: str, params: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
    params = {**params, "key": _key(), "output": "JSON"}
    url = f"{_BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "TravelMapApp/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _float(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _str(val: Any) -> str:
    if val is None or isinstance(val, list):
        return ""
    return str(val)


# ─── 地理编码 ─────────────────────────────────────────────────────────────────

def geocode(address: str) -> dict[str, Any] | None:
    """地名/地址 → 经纬度（仅支持国内地址）

    返回 None 表示未找到或非国内地址。
    """
    try:
        data = _get("/geocode/geo", {"address": address})
        if data.get("status") != "1":
            return None
        geocodes = data.get("geocodes") or []
        if not geocodes:
            return None
        item = geocodes[0]
        location = item.get("location", "")
        if not location or "," not in location:
            return None
        lng_s, lat_s = location.split(",", 1)
        return {
            "lat": float(lat_s),
            "lng": float(lng_s),
            "adcode": _str(item.get("adcode")),
            "province": _str(item.get("province")),
            "city": _str(item.get("city") or item.get("province")),
            "district": _str(item.get("district")),
            "formatted_address": _str(item.get("formatted_address")) or address,
            "country": "中国",
        }
    except Exception:
        return None


# ─── 逆地理编码 ──────────────────────────────────────────────────────────────

def reverse_geocode(lat: float, lng: float) -> dict[str, Any] | None:
    """经纬度 → 行政区划（优先国内，海外返回 None）"""
    try:
        data = _get("/geocode/regeo", {
            "location": f"{lng},{lat}",
            "extensions": "base",
        })
        if data.get("status") != "1":
            return None
        info = data.get("regeocode") or {}
        if not info:
            return None
        addr = info.get("addressComponent") or {}
        city = addr.get("city") or addr.get("province") or ""
        return {
            "formatted_address": _str(info.get("formatted_address")),
            "country": _str(addr.get("country")) or "中国",
            "province": _str(addr.get("province")),
            "city": _str(city),
            "district": _str(addr.get("district")),
            "adcode": _str(addr.get("adcode")),
        }
    except Exception:
        return None


# ─── POI 搜索 ────────────────────────────────────────────────────────────────

def search_poi(query: str, city: str = "", limit: int = 6) -> list[dict[str, Any]]:
    """POI 关键词搜索，返回最多 limit 条结果（仅国内）"""
    try:
        params: dict[str, Any] = {
            "keywords": query,
            "offset": min(limit, 10),
            "page": 1,
            "extensions": "base",
        }
        if city:
            params["city"] = city
        data = _get("/place/text", params)
        if data.get("status") != "1":
            return []
        pois = data.get("pois") or []
        results: list[dict[str, Any]] = []
        for p in pois:
            loc = p.get("location", "")
            if not loc or "," not in loc:
                continue
            lng_s, lat_s = loc.split(",", 1)
            results.append({
                "name": _str(p.get("name")),
                "lat": float(lat_s),
                "lng": float(lng_s),
                "address": _str(p.get("address")),
                "type": _str(p.get("type")),
                "city": _str(p.get("cityname")),
                "district": _str(p.get("adname")),
                "province": _str(p.get("pname")),
                "adcode": _str(p.get("adcode")),
                "country": "中国",
            })
        return results
    except Exception:
        return []


# ─── 天气查询 ────────────────────────────────────────────────────────────────

def get_weather(city_or_adcode: str) -> dict[str, Any] | None:
    """高德天气（仅支持国内城市）

    返回统一格式：
    {
        ok: True,
        source: "amap",
        city: str,
        current: {temperature_c, humidity_pct, condition, wind_direction, wind_power, reporttime},
        forecast: [{date, condition, night_condition, max_temp_c, min_temp_c, wind_direction, wind_power}]
    }
    """
    try:
        # 实况天气
        live_resp = _get("/weather/weatherInfo", {
            "city": city_or_adcode,
            "extensions": "base",
        })
        # 预报天气
        fc_resp = _get("/weather/weatherInfo", {
            "city": city_or_adcode,
            "extensions": "all",
        })

        current: dict[str, Any] = {}
        if live_resp.get("status") == "1":
            lives = live_resp.get("lives") or []
            if lives:
                live = lives[0]
                current = {
                    "temperature_c": _float(live.get("temperature")),
                    "humidity_pct": _float(live.get("humidity")),
                    "windspeed_kmh": None,
                    "condition": _str(live.get("weather")),
                    "wind_direction": _str(live.get("winddirection")),
                    "wind_power": _str(live.get("windpower")),
                    "reporttime": _str(live.get("reporttime")),
                }

        forecast: list[dict[str, Any]] = []
        city_name = city_or_adcode
        if fc_resp.get("status") == "1":
            forecasts = fc_resp.get("forecasts") or []
            if forecasts:
                fc = forecasts[0]
                city_name = _str(fc.get("city")) or city_or_adcode
                for cast in fc.get("casts") or []:
                    forecast.append({
                        "date": _str(cast.get("date")),
                        "condition": _str(cast.get("dayweather")),
                        "night_condition": _str(cast.get("nightweather")),
                        "max_temp_c": _float(cast.get("daytemp")),
                        "min_temp_c": _float(cast.get("nighttemp")),
                        "wind_direction": _str(cast.get("daywind")),
                        "wind_power": _str(cast.get("daypower")),
                        "precipitation_mm": None,
                    })

        if not current and not forecast:
            return None

        return {
            "ok": True,
            "source": "amap",
            "city": city_name,
            "current": current,
            "forecast": forecast,
        }
    except Exception:
        return None
