from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from src.db import get_conn


MOCK_USERS = [
  {"user_id": "demo_user", "display_name": "我（demo_user）"},
  {"user_id": "u_alina", "display_name": "Alina"},
  {"user_id": "u_brian", "display_name": "Brian"},
  {"user_id": "u_coco", "display_name": "Coco"},
]


def _now_iso() -> str:
  return datetime.now(timezone.utc).isoformat()


def list_users() -> list[dict[str, str]]:
  return MOCK_USERS


def share_trip_plan(plan_id: str, from_user: str, to_user: str, message: str = "") -> str:
  share_id = str(uuid.uuid4())
  with get_conn() as conn:
    conn.execute(
      """
      INSERT INTO plan_shares (id, plan_id, from_user, to_user, status, message, created_at)
      VALUES (?, ?, ?, ?, 'pending', ?, ?)
      """,
      (share_id, plan_id, from_user, to_user, message.strip(), _now_iso()),
    )
  return share_id


def share_spot_album(spot_id: str, from_user: str, to_user: str, message: str = "") -> str:
  share_id = str(uuid.uuid4())
  with get_conn() as conn:
    conn.execute(
      """
      INSERT INTO album_shares (id, spot_id, from_user, to_user, status, message, created_at)
      VALUES (?, ?, ?, ?, 'pending', ?, ?)
      """,
      (share_id, spot_id, from_user, to_user, message.strip(), _now_iso()),
    )
  return share_id


def list_received_shares(user_id: str) -> dict[str, list[dict[str, Any]]]:
  with get_conn() as conn:
    plan_rows = conn.execute(
      """
      SELECT ps.*, tp.title AS plan_title
      FROM plan_shares ps
      JOIN trip_plans tp ON ps.plan_id = tp.id
      WHERE ps.to_user = ?
      ORDER BY ps.created_at DESC
      """,
      (user_id,),
    ).fetchall()
    album_rows = conn.execute(
      """
      SELECT a.*, s.place_name, s.country, s.city
      FROM album_shares a
      JOIN spots s ON a.spot_id = s.id
      WHERE a.to_user = ?
      ORDER BY a.created_at DESC
      """,
      (user_id,),
    ).fetchall()
  return {
    "plan_shares": [dict(r) for r in plan_rows],
    "album_shares": [dict(r) for r in album_rows],
  }


def resolve_share(share_type: str, share_id: str, action: str) -> dict[str, Any]:
  if action not in {"accept", "reject"}:
    return {"ok": False, "error": "invalid_action"}
  if share_type not in {"plan", "album"}:
    return {"ok": False, "error": "invalid_share_type"}

  table = "plan_shares" if share_type == "plan" else "album_shares"
  status = "accepted" if action == "accept" else "rejected"

  with get_conn() as conn:
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (share_id,)).fetchone()
    if not row:
      return {"ok": False, "error": "not_found"}
    conn.execute(
      f"UPDATE {table} SET status = ?, resolved_at = ? WHERE id = ?",
      (status, _now_iso(), share_id),
    )
  return {"ok": True, "status": status}


def add_spot_comment(spot_id: str, user_id: str, content: str) -> dict[str, Any]:
  text = content.strip()
  if not text:
    return {"ok": False, "error": "empty"}

  mentions = re.findall(r"@([A-Za-z0-9_\-]+)", text)
  comment_id = str(uuid.uuid4())
  with get_conn() as conn:
    conn.execute(
      """
      INSERT INTO spot_comments (id, spot_id, user_id, content, mentions, created_at)
      VALUES (?, ?, ?, ?, ?, ?)
      """,
      (comment_id, spot_id, user_id, text, json.dumps(mentions, ensure_ascii=False), _now_iso()),
    )
  return {"ok": True, "id": comment_id, "mentions": mentions}


def list_spot_comments(spot_id: str, limit: int = 50) -> list[dict[str, Any]]:
  with get_conn() as conn:
    rows = conn.execute(
      """
      SELECT *
      FROM spot_comments
      WHERE spot_id = ?
      ORDER BY created_at DESC
      LIMIT ?
      """,
      (spot_id, limit),
    ).fetchall()
  items = []
  for r in rows:
    d = dict(r)
    try:
      d["mentions"] = json.loads(d.get("mentions") or "[]")
    except Exception:
      d["mentions"] = []
    items.append(d)
  return items
