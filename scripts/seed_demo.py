"""
Demo data seed script.

Usage:
    python scripts/seed_demo.py          # insert demo data (idempotent)
    python scripts/seed_demo.py --reset  # wipe demo_user data first, then seed

Only touches user_id = 'demo_user'. Safe to run multiple times.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import UPLOAD_DIR
from src.db import get_conn, init_db


# ─── travel spots ─────────────────────────────────────────────────────────────

SPOTS = [
    # China
    {"place_name": "故宫博物院",       "country": "中国", "city": "北京",  "lat": 39.9169, "lng": 116.3907, "travel_at": "2023-10-03", "note": "金秋十月，人很多但很震撼，建议早上开门就进"},
    {"place_name": "外滩",             "country": "中国", "city": "上海",  "lat": 31.2304, "lng": 121.4737, "travel_at": "2023-07-15", "note": "夜景绝美，黄浦江对岸陆家嘴灯火辉煌"},
    {"place_name": "西湖",             "country": "中国", "city": "杭州",  "lat": 30.2590, "lng": 120.1494, "travel_at": "2024-04-05", "note": "春天樱花季，苏堤漫步非常舒服"},
    {"place_name": "宽窄巷子",         "country": "中国", "city": "成都",  "lat": 30.6698, "lng": 104.0626, "travel_at": "2023-05-20", "note": "吃了正宗的火锅和担担面，当地人很热情"},
    {"place_name": "秦始皇兵马俑博物馆","country": "中国", "city": "西安",  "lat": 34.3843, "lng": 109.2785, "travel_at": "2022-09-10", "note": "震撼程度超出预期，建议请导游讲解历史"},
    {"place_name": "漓江",             "country": "中国", "city": "桂林",  "lat": 25.2736, "lng": 110.2908, "travel_at": "2022-04-18", "note": "乘竹筏顺流而下，山水如画"},
    {"place_name": "张家界国家森林公园","country": "中国", "city": "张家界","lat": 29.1178, "lng": 110.4792, "travel_at": "2021-08-02", "note": "《阿凡达》取景地，云雾中的山峰太梦幻"},
    {"place_name": "丽江古城",         "country": "中国", "city": "丽江",  "lat": 26.8721, "lng": 100.2299, "travel_at": "2021-03-14", "note": "古城保存完好，纳西文化很有特色"},
    # Japan
    {"place_name": "浅草寺",           "country": "日本", "city": "东京",  "lat": 35.7148, "lng": 139.7967, "travel_at": "2024-01-08", "note": "新年参拜，人山人海但气氛极好"},
    {"place_name": "金阁寺",           "country": "日本", "city": "京都",  "lat": 35.0394, "lng": 135.7292, "travel_at": "2024-01-10", "note": "镀金外墙倒映在镜湖中，美得不真实"},
    {"place_name": "岚山竹林",         "country": "日本", "city": "京都",  "lat": 35.0171, "lng": 135.6719, "travel_at": "2024-01-11", "note": "清晨6点到几乎没有游客，竹林沙沙声非常治愈"},
    # Southeast Asia
    {"place_name": "滨海湾花园",       "country": "新加坡","city": "新加坡","lat": 1.2834,  "lng": 103.8607, "travel_at": "2023-12-28", "note": "超级树灯光秀每晚8点，免费观看非常壮观"},
    # Europe
    {"place_name": "埃菲尔铁塔",       "country": "法国", "city": "巴黎",  "lat": 48.8584, "lng": 2.2945,   "travel_at": "2019-06-20", "note": "登顶俯瞰巴黎全景，日落时分最美"},
    {"place_name": "圣家族大教堂",     "country": "西班牙","city": "巴塞罗那","lat": 41.4036,"lng": 2.1744,  "travel_at": "2019-06-25", "note": "高迪建筑奇迹，内部彩窗在阳光下令人窒息"},
    {"place_name": "斗兽场",           "country": "意大利","city": "罗马",  "lat": 41.8902, "lng": 12.4922,  "travel_at": "2019-06-28", "note": "两千年历史扑面而来，买了跳过排队的票很值"},
]

# ─── Photo sources per spot ───────────────────────────────────────────────────
# Priority 1: Unsplash direct CDN URLs (images.unsplash.com uses Cloudflare,
#             globally accessible; ID resolves to a specific scenic photo)
# Priority 2: Wikipedia REST API (may be blocked in mainland China)
# Priority 3: picsum.photos with seed (Fastly CDN, landscape placeholders)

SPOT_WIKI: dict[str, str] = {
    "故宫博物院":         "Forbidden_City",
    "外滩":               "The_Bund",
    "西湖":               "West_Lake_(Hangzhou)",
    "宽窄巷子":           "Kuanzhai_Alley",
    "秦始皇兵马俑博物馆": "Terracotta_Army",
    "漓江":               "Li_River_(Guangxi)",
    "张家界国家森林公园": "Zhangjiajie_National_Forest_Park",
    "丽江古城":           "Lijiang_Old_Town",
    "浅草寺":             "Senso-ji",
    "金阁寺":             "Kinkaku-ji",
    "岚山竹林":           "Arashiyama",
    "滨海湾花园":         "Gardens_by_the_Bay",
    "埃菲尔铁塔":         "Eiffel_Tower",
    "圣家族大教堂":       "Sagrada_Familia",
    "斗兽场":             "Colosseum",
}

# Hardcoded Unsplash scenic photo IDs (images.unsplash.com CDN)
SPOT_UNSPLASH: dict[str, str] = {
    "故宫博物院":         "photo-1508804185872-d7badad00f7d",   # Forbidden City red walls
    "外滩":               "photo-1548919973-5b8da2e6b3e4",   # Shanghai Bund skyline night
    "西湖":               "photo-1523906834658-6e24ef2386f9",   # Hangzhou West Lake misty
    "宽窄巷子":           "photo-1583417319070-4a69db38a482",   # Chengdu old alley
    "秦始皇兵马俑博物馆": "photo-1591608971362-f08b2a75731a",   # Terracotta warriors pit
    "漓江":               "photo-1510832842230-87253f48d74b",   # Guilin karst mountains river
    "张家界国家森林公园": "photo-1558618666-fcd25c85cd64",   # Zhangjiajie pillar mountains
    "丽江古城":           "photo-1603283906909-3e47b5e7a5a4",   # Lijiang old town cobblestone
    "浅草寺":             "photo-1540959733332-eab4deabeeaf",   # Senso-ji temple Tokyo dusk
    "金阁寺":             "photo-1528360983277-13d401cdc186",   # Kinkaku-ji golden pavilion
    "岚山竹林":           "photo-1545569341-9eb8b30979d9",   # Arashiyama bamboo grove
    "滨海湾花园":         "photo-1508109742236-f8b3b06d9c36",   # Gardens by the Bay supertrees
    "埃菲尔铁塔":         "photo-1502602898657-3e91760cbb34",   # Eiffel Tower Paris
    "圣家族大教堂":       "photo-1583265627959-fb7042f5d9d0",   # Sagrada Familia Barcelona
    "斗兽场":             "photo-1552832230-c0197dd5d68a",   # Colosseum Rome
}


# ─── long-term memories ───────────────────────────────────────────────────────

MEMORIES = [
    {"memory_type": "preference", "content": "喜欢安静、人少的景点，不喜欢过度商业化的旅游区",        "confidence": 0.92},
    {"memory_type": "preference", "content": "偏好历史文化类景点，对自然风景和建筑艺术特别感兴趣",    "confidence": 0.90},
    {"memory_type": "preference", "content": "旅行时喜欢拍照，尤其是建筑细节和自然光影",              "confidence": 0.88},
    {"memory_type": "preference", "content": "喜欢在当地早市或菜市场感受真实的市井生活",              "confidence": 0.85},
    {"memory_type": "plan",       "content": "打算2025年秋天去日本京都看红叶，最好是11月上旬",        "confidence": 0.80},
    {"memory_type": "plan",       "content": "计划未来去秘鲁马丘比丘，需要提前预约并做好高原反应准备", "confidence": 0.75},
    {"memory_type": "profile",    "content": "经常独自旅行，偏好自由行而非跟团",                      "confidence": 0.95},
    {"memory_type": "fact",       "content": "已去过中国、日本、法国、西班牙、意大利、新加坡等地",    "confidence": 0.98},
]


# ─── main ─────────────────────────────────────────────────────────────────────

USER_ID = "demo_user"


def seed(reset: bool = False) -> None:
    init_db()

    with get_conn() as conn:
        if reset:
            conn.execute("DELETE FROM spots WHERE user_id = ?", (USER_ID,))
            conn.execute("DELETE FROM memory_items WHERE user_id = ?", (USER_ID,))
            print(f"[seed] reset: cleared existing demo_user data")

        existing_spots = conn.execute(
            "SELECT place_name FROM spots WHERE user_id = ?", (USER_ID,)
        ).fetchall()
        existing_names = {row["place_name"] for row in existing_spots}

        existing_mems = conn.execute(
            "SELECT content FROM memory_items WHERE user_id = ?", (USER_ID,)
        ).fetchall()
        existing_contents = {row["content"] for row in existing_mems}

    spots_added = _seed_spots(existing_names)
    mems_added = _seed_memories(existing_contents)
    photos_added = _seed_photos()

    print(f"\n[seed] done — spots: +{spots_added}, memories: +{mems_added}, photos: +{photos_added}")
    print(f"[seed] total spots: {_count('spots')}, total memories: {_count('memory_items')}")


def _seed_spots(existing_names: set[str]) -> int:
    added = 0
    base_date = datetime(2024, 1, 1)
    with get_conn() as conn:
        for i, s in enumerate(SPOTS):
            if s["place_name"] in existing_names:
                continue
            created_at = (base_date - timedelta(days=i * 7)).isoformat()
            conn.execute(
                """
                INSERT INTO spots (id, user_id, place_name, country, city, lat, lng, travel_at, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    USER_ID,
                    s["place_name"],
                    s.get("country", ""),
                    s.get("city", ""),
                    s["lat"],
                    s["lng"],
                    s.get("travel_at", ""),
                    s.get("note", ""),
                    created_at,
                ),
            )
            print(f"  + spot: {s['place_name']} ({s.get('country', '')})")
            added += 1
    return added


def _seed_memories(existing_contents: set[str]) -> int:
    added = 0
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        for m in MEMORIES:
            if m["content"] in existing_contents:
                continue
            conn.execute(
                """
                INSERT INTO memory_items
                  (user_id, memory_type, topic_key, polarity, content, confidence, source, last_used_at, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    USER_ID,
                    m["memory_type"],
                    m["content"][:18],
                    1,
                    m["content"],
                    m["confidence"],
                    "seed",
                    now,
                    now,
                ),
            )
            print(f"  + memory [{m['memory_type']}]: {m['content'][:40]}...")
            added += 1
    return added


def _http_get(url: str, timeout: int = 10) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TravelMapSeed/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        return data if len(data) > 5000 else None  # skip tiny error payloads
    except Exception as exc:
        print(f"    [http] {url[:60]}… → {exc}")
        return None


def _fetch_photo_bytes(spot_name: str) -> bytes | None:
    # 1. Unsplash direct CDN (images.unsplash.com uses Cloudflare, globally accessible)
    uid = SPOT_UNSPLASH.get(spot_name)
    if uid:
        data = _http_get(f"https://images.unsplash.com/{uid}?w=800&q=80", timeout=12)
        if data:
            print(f"    [photo] Unsplash ✓ ({len(data)//1024}KB)")
            return data

    # 2. Wikipedia REST API thumbnail (may be blocked in mainland China)
    wiki_title = SPOT_WIKI.get(spot_name)
    if wiki_title:
        meta = _http_get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/"
            + urllib.parse.quote(wiki_title, safe=""),
            timeout=8,
        )
        if meta:
            try:
                img_url = (json.loads(meta).get("thumbnail") or {}).get("source", "")
                if img_url:
                    data = _http_get(img_url, timeout=12)
                    if data:
                        print(f"    [photo] Wikipedia ✓ ({len(data)//1024}KB)")
                        return data
            except Exception:
                pass

    # 3. picsum.photos with seed (Fastly CDN — landscape placeholder, consistent per spot)
    seed_str = urllib.parse.quote(spot_name, safe="")
    data = _http_get(f"https://picsum.photos/seed/{seed_str}/800/600", timeout=10)
    if data:
        print(f"    [photo] picsum ✓ ({len(data)//1024}KB)")
        return data

    return None


def _seed_photos() -> int:
    added = 0
    now = datetime.now(timezone.utc).isoformat()

    with get_conn() as conn:
        spots = conn.execute(
            "SELECT id, place_name FROM spots WHERE user_id = ?", (USER_ID,)
        ).fetchall()

        for spot_row in spots:
            spot_id = spot_row["id"]
            place_name = spot_row["place_name"]

            existing = conn.execute(
                "SELECT COUNT(*) FROM photos WHERE spot_id = ?", (spot_id,)
            ).fetchone()[0]
            if existing > 0:
                print(f"  [photo] skip {place_name} (already has photo)")
                continue

            print(f"  [photo] fetching {place_name} …")
            img_bytes = _fetch_photo_bytes(place_name)
            if not img_bytes:
                print(f"  [photo] ✗ all sources failed for {place_name}, skipped")
                continue

            safe_name = "".join(c if (c.isalnum() or c in "-_") else "_" for c in place_name)
            file_name = f"seed_{safe_name}.jpg"
            file_path = UPLOAD_DIR / file_name
            file_path.write_bytes(img_bytes)

            photo_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO photos (id, spot_id, file_path, created_at) VALUES (?, ?, ?, ?)",
                (photo_id, spot_id, str(file_path), now),
            )
            print(f"  [photo] ✓ {place_name} → {file_name} ({len(img_bytes)//1024}KB)")
            added += 1

    return added


def _count(table: str) -> int:
    with get_conn() as conn:
        return conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (USER_ID,)
        ).fetchone()[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo data for travel map assistant")
    parser.add_argument("--reset", action="store_true", help="clear existing demo_user data before seeding")
    args = parser.parse_args()
    seed(reset=args.reset)
