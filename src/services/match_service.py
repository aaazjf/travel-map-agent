import uuid
from datetime import datetime, timezone
from typing import Any

from src.db import get_conn
from src.services.spot_service import haversine


MOCK_BUDDIES = [
  {
    "id": "u_alina",
    "name": "Alina",
    "avatar": "A",
    "tracks": [
      (39.9042, 116.4074, "china"),
      (35.6762, 139.6503, "japan"),
      (51.5074, -0.1278, "uk"),
    ],
  },
  {
    "id": "u_brian",
    "name": "Brian",
    "avatar": "B",
    "tracks": [
      (31.2304, 121.4737, "china"),
      (48.8566, 2.3522, "france"),
      (41.9028, 12.4964, "italy"),
    ],
  },
  {
    "id": "u_coco",
    "name": "Coco",
    "avatar": "C",
    "tracks": [
      (22.3193, 114.1694, "china"),
      (25.0330, 121.5654, "china"),
      (37.5665, 126.9780, "korea"),
    ],
  },
]


def rank_buddies(spots: list[dict[str, Any]]) -> list[dict[str, Any]]:
  ranked = []
  for buddy in MOCK_BUDDIES:
    score, breakdown = calc_similarity(spots, buddy["tracks"])
    ranked.append({**buddy, "score": score, "breakdown": breakdown})
  ranked.sort(key=lambda item: item["score"], reverse=True)
  return ranked


def calc_similarity(spots: list[dict[str, Any]], tracks: list[tuple[float, float, str]]) -> tuple[int, dict[str, Any]]:
  if not spots:
    return 0, {"geo_score": 0, "country_score": 0, "common_countries": [], "spots_compared": 0}

  geo_scores = []
  for spot in spots:
    nearest = min(haversine(spot["lat"], spot["lng"], lat, lng) for lat, lng, _ in tracks)
    geo_scores.append(pow(2.71828, -nearest / 2200))
  geo = sum(geo_scores) / len(geo_scores)

  spot_countries = {str(item.get("country", "")).strip().lower() for item in spots if item.get("country")}
  track_countries = {name.strip().lower() for _, _, name in tracks if name}
  union = len(spot_countries | track_countries) or 1
  common = spot_countries & track_countries
  overlap = len(common)
  country = overlap / union

  raw = geo * 0.75 + country * 0.25
  score = max(0, min(100, round(raw * 100)))
  breakdown = {
    "geo_score": round(geo * 75),
    "country_score": round(country * 25),
    "common_countries": sorted(common),
    "spots_compared": len(spots),
  }
  return score, breakdown


def create_invite(from_user: str, to_user: str, score: int) -> None:
  with get_conn() as conn:
    conn.execute(
      """
      INSERT INTO invites (id, from_user, to_user, score, status, created_at)
      VALUES (?, ?, ?, ?, ?, ?)
      """,
      (str(uuid.uuid4()), from_user, to_user, score, "pending", datetime.now(timezone.utc).isoformat()),
    )


def get_invites(from_user: str) -> list[dict[str, Any]]:
  with get_conn() as conn:
    rows = conn.execute(
      """
      SELECT * FROM invites
      WHERE from_user = ?
      ORDER BY created_at DESC
      """,
      (from_user,),
    ).fetchall()
  return [dict(row) for row in rows]
