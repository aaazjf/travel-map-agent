import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import UPLOAD_DIR
from src.db import get_conn


TAG_RULES: dict[str, list[str]] = {
  "海边": ["海", "海边", "沙滩", "海岸", "海岛", "beach", "coast"],
  "雪山": ["雪山", "冰川", "雪", "mountain", "alps"],
  "博物馆": ["博物馆", "museum", "美术馆", "展览"],
  "美食": ["美食", "小吃", "餐厅", "火锅", "料理", "food", "restaurant"],
  "人文": ["古城", "历史", "寺庙", "人文", "文化", "architecture"],
  "自然": ["自然", "森林", "湖", "河", "国家公园", "nature", "park"],
  "城市": ["城市", "city", "地标", "广场", "都市"],
}


def add_spot(
  *,
  user_id: str,
  place_name: str,
  country: str,
  admin1: str,
  city: str,
  district: str,
  lat: float,
  lng: float,
  travel_at: str | None,
  note: str,
  photos: list[tuple[str, bytes]],
) -> dict[str, Any]:
  now_iso = datetime.now(timezone.utc).isoformat()
  travel_at_value = travel_at or None
  year_key = _year_key(travel_at_value or now_iso)

  normalized = {
    "place_name": _norm(place_name),
    "country": _norm(country),
    "admin1": _norm(admin1),
    "city": _norm(city),
    "district": _norm(district),
  }

  merged = False
  with get_conn() as conn:
    existing_id = _find_merge_target(
      conn,
      user_id=user_id,
      year_key=year_key,
      normalized=normalized,
      lat=lat,
      lng=lng,
    )
    if existing_id:
      spot_id = existing_id
      merged = True
      # Keep latest note if new note has new information.
      if note.strip():
        row = conn.execute("SELECT note FROM spots WHERE id = ?", (spot_id,)).fetchone()
        old_note = str((row["note"] if row else "") or "").strip()
        new_note = note.strip()
        if new_note and new_note not in old_note:
          merged_note = f"{old_note}\n{new_note}".strip() if old_note else new_note
          conn.execute("UPDATE spots SET note = ? WHERE id = ?", (merged_note, spot_id))
      # Refresh travel time to latest record for timeline sorting.
      if travel_at_value:
        conn.execute("UPDATE spots SET travel_at = ? WHERE id = ?", (travel_at_value, spot_id))
    else:
      spot_id = str(uuid.uuid4())
      conn.execute(
        """
        INSERT INTO spots (
          id, user_id, place_name, country, admin1, city, district,
          lat, lng, travel_at, note, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
          spot_id,
          user_id,
          place_name.strip(),
          country.strip(),
          admin1.strip(),
          city.strip(),
          district.strip(),
          lat,
          lng,
          travel_at_value,
          note.strip(),
          now_iso,
        ),
      )

    added_photo_count = 0
    for filename, content in photos:
      _insert_photo_with_tags(
        conn=conn,
        user_id=user_id,
        spot_id=spot_id,
        filename=filename,
        content=content,
        place_name=place_name,
        country=country,
        city=city,
        district=district,
        note=note,
      )
      added_photo_count += 1

  return {
    "spot_id": spot_id,
    "merged": merged,
    "added_photo_count": added_photo_count,
  }


def delete_spot(spot_id: str, user_id: str) -> None:
  with get_conn() as conn:
    photo_rows = conn.execute(
      "SELECT id, file_path FROM photos WHERE spot_id = ?",
      (spot_id,),
    ).fetchall()
    conn.execute("DELETE FROM spots WHERE id = ? AND user_id = ?", (spot_id, user_id))

  for row in photo_rows:
    path = Path(row["file_path"])
    if path.exists():
      path.unlink()


def list_spots(user_id: str) -> list[dict[str, Any]]:
  with get_conn() as conn:
    rows = conn.execute(
      """
      SELECT *
      FROM spots
      WHERE user_id = ?
      ORDER BY COALESCE(travel_at, created_at) DESC
      """,
      (user_id,),
    ).fetchall()

    spots = [dict(row) for row in rows]
    spot_ids = [s["id"] for s in spots]

    photos_by_spot: dict[str, list[dict[str, Any]]] = {sid: [] for sid in spot_ids}
    if spot_ids:
      placeholders = ",".join(["?"] * len(spot_ids))
      photo_rows = conn.execute(
        f"SELECT id, spot_id, file_path, created_at FROM photos WHERE spot_id IN ({placeholders}) ORDER BY created_at ASC",
        spot_ids,
      ).fetchall()
      for p in photo_rows:
        photos_by_spot[str(p["spot_id"])].append(dict(p))

      tag_rows = conn.execute(
        f"SELECT photo_id, tags_json FROM photo_tags WHERE spot_id IN ({placeholders})",
        spot_ids,
      ).fetchall()
      tag_map: dict[str, list[str]] = {}
      for r in tag_rows:
        try:
          tags = json.loads(str(r["tags_json"]))
          if isinstance(tags, list):
            tag_map[str(r["photo_id"])] = [str(t) for t in tags]
        except Exception:
          tag_map[str(r["photo_id"])] = []

      for sid, plist in photos_by_spot.items():
        for p in plist:
          p["tags"] = tag_map.get(str(p.get("id")), [])

    for spot in spots:
      plist = photos_by_spot.get(str(spot["id"]), [])
      spot["photos"] = plist
      merged_tags: list[str] = []
      for p in plist:
        for t in p.get("tags", []):
          if t not in merged_tags:
            merged_tags.append(t)
      spot["photo_tags"] = merged_tags
  return spots


def filter_spots(spots: list[dict[str, Any]], keyword: str) -> list[dict[str, Any]]:
  key = keyword.strip().lower()
  if not key:
    return spots
  result = []
  for spot in spots:
    joined = " ".join(
      [
        str(spot.get("place_name", "")),
        str(spot.get("country", "")),
        str(spot.get("admin1", "")),
        str(spot.get("city", "")),
        str(spot.get("district", "")),
        str(spot.get("note", "")),
        " ".join([str(t) for t in spot.get("photo_tags", [])]),
      ]
    ).lower()
    if key in joined:
      result.append(spot)
  return result


def semantic_filter_spots(spots: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
  q = query.strip().lower()
  if not q:
    return spots
  wanted_tags = _infer_tags_from_text(q)

  scored: list[tuple[float, dict[str, Any]]] = []
  q_tokens = [t for t in re.split(r"\s+", q) if t]

  for spot in spots:
    base_text = " ".join(
      [
        str(spot.get("place_name", "")),
        str(spot.get("country", "")),
        str(spot.get("admin1", "")),
        str(spot.get("city", "")),
        str(spot.get("district", "")),
        str(spot.get("note", "")),
      ]
    ).lower()
    tags = {str(t).lower() for t in spot.get("photo_tags", [])}

    score = 0.0
    if q in base_text:
      score += 2.0
    for tk in q_tokens:
      if tk and tk in base_text:
        score += 0.35

    for wt in wanted_tags:
      if wt.lower() in tags:
        score += 1.2

    for t in tags:
      if t in q:
        score += 0.9

    if score > 0:
      scored.append((score, spot))

  scored.sort(key=lambda x: (x[0], str(x[1].get("travel_at") or x[1].get("created_at") or "")), reverse=True)
  return [item for _, item in scored]


def get_stats(spots: list[dict[str, Any]]) -> dict[str, Any]:
  countries = {item["country"] for item in spots if item.get("country")}
  photo_count = sum(len(item.get("photos", [])) for item in spots)

  ordered = sorted(spots, key=lambda x: x.get("travel_at") or x.get("created_at"))
  total_km = 0.0
  for idx in range(1, len(ordered)):
    total_km += haversine(
      ordered[idx - 1]["lat"],
      ordered[idx - 1]["lng"],
      ordered[idx]["lat"],
      ordered[idx]["lng"],
    )
  return {
    "locations": len(spots),
    "photos": photo_count,
    "countries": len(countries),
    "distance_km": round(total_km, 1),
  }


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
  r = 6371.0
  d_lat = math.radians(lat2 - lat1)
  d_lng = math.radians(lng2 - lng1)
  a = (
    math.sin(d_lat / 2) ** 2
    + math.cos(math.radians(lat1))
    * math.cos(math.radians(lat2))
    * math.sin(d_lng / 2) ** 2
  )
  return r * 2 * math.asin(math.sqrt(a))


def _insert_photo_with_tags(
  *,
  conn,
  user_id: str,
  spot_id: str,
  filename: str,
  content: bytes,
  place_name: str,
  country: str,
  city: str,
  district: str,
  note: str,
) -> None:
  photo_id = str(uuid.uuid4())
  ext = Path(filename).suffix or ".jpg"
  safe_name = f"{photo_id}{ext}"
  save_path = UPLOAD_DIR / safe_name
  save_path.write_bytes(content)
  now_iso = datetime.now(timezone.utc).isoformat()

  conn.execute(
    """
    INSERT INTO photos (id, spot_id, file_path, created_at)
    VALUES (?, ?, ?, ?)
    """,
    (photo_id, spot_id, str(save_path), now_iso),
  )

  tags = _infer_tags_from_text(" ".join([filename, place_name, country, city, district, note]))
  conn.execute(
    """
    INSERT INTO photo_tags (id, photo_id, spot_id, user_id, tags_json, source, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
    (str(uuid.uuid4()), photo_id, spot_id, user_id, json.dumps(tags, ensure_ascii=False), "rule", now_iso),
  )


def _find_merge_target(
  conn,
  *,
  user_id: str,
  year_key: str,
  normalized: dict[str, str],
  lat: float,
  lng: float,
) -> str | None:
  rows = conn.execute(
    """
    SELECT id, place_name, country, admin1, city, district, travel_at, created_at
           , lat, lng
    FROM spots
    WHERE user_id = ?
      AND substr(COALESCE(travel_at, created_at), 1, 4) = ?
    ORDER BY COALESCE(travel_at, created_at) DESC
    """,
    (user_id, year_key),
  ).fetchall()

  for row in rows:
    if (
      _norm(str(row["place_name"])) == normalized["place_name"]
      and _norm(str(row["country"])) == normalized["country"]
      and _norm(str(row["admin1"])) == normalized["admin1"]
      and _norm(str(row["city"])) == normalized["city"]
      and _norm(str(row["district"])) == normalized["district"]
    ):
      return str(row["id"])
    # Loose fallback: same place + city and within 2km.
    if (
      _norm(str(row["place_name"])) == normalized["place_name"]
      and _norm(str(row["city"])) == normalized["city"]
    ):
      try:
        if haversine(float(row["lat"]), float(row["lng"]), lat, lng) <= 2.0:
          return str(row["id"])
      except Exception:
        pass
  return None


def _infer_tags_from_text(text: str) -> list[str]:
  lower = text.lower()
  tags: list[str] = []
  for tag, keys in TAG_RULES.items():
    if any(k.lower() in lower for k in keys):
      tags.append(tag)
  if not tags:
    tags.append("旅行")
  return tags


def _norm(value: str) -> str:
  return re.sub(r"\s+", "", str(value or "").strip().lower())


def _year_key(raw: str) -> str:
  try:
    return str(datetime.fromisoformat(raw.replace("Z", "+00:00")).year)
  except Exception:
    return str(datetime.now(timezone.utc).year)
