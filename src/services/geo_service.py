"""地理服务层

优先使用高德地图 API（国内，速度快、精度高），
国际城市自动回退到 Nominatim（OpenStreetMap）。
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

from src.services import amap_client

_NOMINATIM_UA = "TravelMapApp/1.0"


# ─── 公开接口 ────────────────────────────────────────────────────────────────

def search_places(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """搜索地点，返回最多 limit 条结果（统一格式）。

    每条结果包含:
        lat, lng, place_name, display_name,
        country, province, city, district, adcode,
        address (Nominatim 兼容子 dict)
    """
    if not query.strip():
        return []

    # AMAP_API_KEY 未配置时直接报错，避免静默空结果误导用户
    if not os.getenv("AMAP_API_KEY", "").strip():
        raise RuntimeError("AMAP_API_KEY 未配置，请在 .env 中设置。")

    # 1. 高德 POI 搜索（国内）
    pois = amap_client.search_poi(query.strip(), limit=limit)
    if pois:
        return [_normalize_amap_poi(p) for p in pois]

    # 2. 高德地理编码（国内地址）
    geo = amap_client.geocode(query.strip())
    if geo:
        return [_normalize_amap_geo(query.strip(), geo)]

    # 3. Nominatim 兜底（国际城市）
    results = _nominatim_search(query.strip(), limit=limit)
    return [_normalize_nominatim(r) for r in results]


def search_place(query: str) -> dict[str, Any] | None:
    """搜索单个地点（向后兼容接口）"""
    results = search_places(query, limit=1)
    return results[0] if results else None


def reverse_geocode(lat: float, lng: float) -> dict[str, Any] | None:
    """坐标 → 地址（统一格式）

    返回包含 display_name / address / province / city / district / adcode 的 dict。
    """
    # 高德逆地理编码（国内）
    result = amap_client.reverse_geocode(lat, lng)
    if result and result.get("city"):
        return {
            "display_name": result["formatted_address"],
            "province": result.get("province", ""),
            "city": result.get("city", ""),
            "district": result.get("district", ""),
            "adcode": result.get("adcode", ""),
            "country": result.get("country", "中国"),
            # Nominatim-style address sub-dict（向后兼容）
            "address": {
                "country": result.get("country", "中国"),
                "state": result.get("province", ""),
                "city": result.get("city", ""),
                "county": result.get("district", ""),
            },
        }

    # Nominatim 兜底（海外坐标）
    return _nominatim_reverse(lat, lng)


# ─── 格式化帮助 ──────────────────────────────────────────────────────────────

def _normalize_amap_poi(p: dict[str, Any]) -> dict[str, Any]:
    name = p.get("name", "")
    addr = p.get("address", "")
    display = f"{name}，{addr}".strip("，") if addr else name
    return {
        "lat": p["lat"],
        "lng": p["lng"],
        "lon": p["lng"],           # 向后兼容
        "place_name": name,
        "display_name": display,
        "country": "中国",
        "province": p.get("province", ""),
        "city": p.get("city", ""),
        "district": p.get("district", ""),
        "adcode": p.get("adcode", ""),
        "address": {
            "country": "中国",
            "state": p.get("province", ""),
            "city": p.get("city", ""),
            "county": p.get("district", ""),
        },
    }


def _normalize_amap_geo(query: str, geo: dict[str, Any]) -> dict[str, Any]:
    return {
        "lat": geo["lat"],
        "lng": geo["lng"],
        "lon": geo["lng"],
        "place_name": query,
        "display_name": geo.get("formatted_address", query),
        "country": "中国",
        "province": geo.get("province", ""),
        "city": geo.get("city", ""),
        "district": geo.get("district", ""),
        "adcode": geo.get("adcode", ""),
        "address": {
            "country": "中国",
            "state": geo.get("province", ""),
            "city": geo.get("city", ""),
            "county": geo.get("district", ""),
        },
    }


def _normalize_nominatim(item: dict[str, Any]) -> dict[str, Any]:
    addr = item.get("address", {})
    name = str(item.get("display_name", "")).split(",")[0].strip()
    return {
        "lat": float(item.get("lat", 0)),
        "lng": float(item.get("lon", 0)),
        "lon": float(item.get("lon", 0)),
        "place_name": name,
        "display_name": item.get("display_name", ""),
        "country": addr.get("country", ""),
        "province": addr.get("state", "") or addr.get("province", ""),
        "city": addr.get("city", "") or addr.get("town", "") or addr.get("village", ""),
        "district": addr.get("county", "") or addr.get("city_district", ""),
        "adcode": "",
        "address": addr,
    }


# ─── Nominatim 兜底（国际城市） ───────────────────────────────────────────────

def _nominatim_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    try:
        params = urllib.parse.urlencode({
            "q": query,
            "format": "jsonv2",
            "limit": limit,
            "addressdetails": 1,
            "accept-language": "zh-CN",
        })
        url = f"https://nominatim.openstreetmap.org/search?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": _NOMINATIM_UA})
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read())
    except Exception:
        return []


def _nominatim_reverse(lat: float, lng: float) -> dict[str, Any] | None:
    try:
        params = urllib.parse.urlencode({
            "lat": lat, "lon": lng,
            "format": "jsonv2",
            "addressdetails": 1,
            "accept-language": "zh-CN",
        })
        url = f"https://nominatim.openstreetmap.org/reverse?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": _NOMINATIM_UA})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        if not data:
            return None
        addr = data.get("address", {})
        return {
            "display_name": data.get("display_name", ""),
            "province": addr.get("state", ""),
            "city": addr.get("city", "") or addr.get("town", "") or addr.get("village", ""),
            "district": addr.get("county", "") or addr.get("city_district", ""),
            "adcode": "",
            "country": addr.get("country", ""),
            "address": addr,
        }
    except Exception:
        return None
