from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
  sys.path.insert(0, str(ROOT_DIR))

from src.agent_core import TravelOrchestrator
from src.agent_core.tool_executor import list_pending_tool_approvals, resolve_tool_approval
from src.db import get_conn, init_db
from src.services.agent_service import get_latest_agent_debug


TEST_USER = "week4_eval_user"


@dataclass
class CaseResult:
  name: str
  passed: bool
  detail: str


def _set_local_mode() -> None:
  os.environ["LLM_PROVIDER"] = "none"


def _reset_user_data() -> None:
  with get_conn() as conn:
    conn.execute("DELETE FROM spots WHERE user_id = ?", (TEST_USER,))
    conn.execute("DELETE FROM agent_memory WHERE user_id = ?", (TEST_USER,))
    conn.execute("DELETE FROM conversations WHERE user_id = ?", (TEST_USER,))
    conn.execute("DELETE FROM agent_run_logs WHERE user_id = ?", (TEST_USER,))
    conn.execute("DELETE FROM agent_tool_logs WHERE user_id = ?", (TEST_USER,))
    conn.execute("DELETE FROM agent_guard_logs WHERE user_id = ?", (TEST_USER,))
    conn.execute("DELETE FROM agent_pending_actions WHERE user_id = ?", (TEST_USER,))
    conn.execute("DELETE FROM invites WHERE from_user = ?", (TEST_USER,))


def _seed_spots() -> list[dict]:
  spots = [
    {
      "id": "s1",
      "user_id": TEST_USER,
      "place_name": "Badaling Great Wall",
      "country": "China",
      "admin1": "Beijing",
      "city": "Beijing",
      "district": "Yanqing",
      "lat": 40.3652,
      "lng": 116.0204,
      "travel_at": "2026-01-10T10:00:00",
      "note": "winter trip",
      "created_at": "2026-01-10T10:00:00",
    },
    {
      "id": "s2",
      "user_id": TEST_USER,
      "place_name": "Paris",
      "country": "France",
      "admin1": "Ile-de-France",
      "city": "Paris",
      "district": "7th Arr.",
      "lat": 48.8566,
      "lng": 2.3522,
      "travel_at": "2026-03-15T14:30:00",
      "note": "museum day",
      "created_at": "2026-03-15T14:30:00",
    },
  ]
  with get_conn() as conn:
    for s in spots:
      conn.execute(
        """
        INSERT INTO spots (id, user_id, place_name, country, admin1, city, district, lat, lng, travel_at, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
          s["id"],
          s["user_id"],
          s["place_name"],
          s["country"],
          s["admin1"],
          s["city"],
          s["district"],
          s["lat"],
          s["lng"],
          s["travel_at"],
          s["note"],
          s["created_at"],
        ),
      )
  return spots


def case_geo_review_with_evidence() -> CaseResult:
  orch = TravelOrchestrator()
  spots = _seed_spots()
  reply = orch.run(
    user_id=TEST_USER,
    query="Please write a yearly review with evidence points.",
    spots=spots,
    conversation_id=None,
    history=[],
  )
  passed = ("evidence" in reply.lower()) or ("\u8bc1\u636e\u70b9" in reply)
  return CaseResult("geo review path", passed, reply[:220])


def case_high_risk_pending_approval() -> CaseResult:
  orch = TravelOrchestrator()
  with get_conn() as conn:
    rows = conn.execute("SELECT * FROM spots WHERE user_id = ? ORDER BY created_at DESC", (TEST_USER,)).fetchall()
  spots = [dict(r) for r in rows]
  reply = orch.run(
    user_id=TEST_USER,
    query="Please invite Alina to travel together.",
    spots=spots,
    conversation_id=None,
    history=[],
  )
  pending = list_pending_tool_approvals(TEST_USER, limit=10)
  passed = bool(pending) and "requires human approval" in reply.lower()
  return CaseResult("pending approval", passed, f"pending={len(pending)} | reply={reply[:140]}")


def case_approval_execute() -> CaseResult:
  pending = list_pending_tool_approvals(TEST_USER, limit=10)
  if not pending:
    return CaseResult("approval execute", False, "no pending action")
  top = pending[0]
  result = resolve_tool_approval(TEST_USER, int(top["id"]), "approve")
  passed = bool(result.get("ok")) and result.get("status") == "executed"
  return CaseResult("approval execute", passed, str(result))


def case_trace_visibility() -> CaseResult:
  debug = get_latest_agent_debug(TEST_USER, conversation_id=None)
  has_tools = isinstance(debug.get("tools", []), list)
  has_guards = isinstance(debug.get("guards", []), list)
  passed = bool(debug) and has_tools and has_guards
  return CaseResult("trace visibility", passed, f"request_id={debug.get('request_id','')} tools={len(debug.get('tools', []))}")


def run_all() -> list[CaseResult]:
  _set_local_mode()
  init_db()
  _reset_user_data()
  cases: list[Callable[[], CaseResult]] = [
    case_geo_review_with_evidence,
    case_high_risk_pending_approval,
    case_approval_execute,
    case_trace_visibility,
  ]
  return [c() for c in cases]


if __name__ == "__main__":
  results = run_all()
  passed = 0
  for r in results:
    status = "PASS" if r.passed else "FAIL"
    print(f"[{status}] {r.name}: {r.detail}")
    if r.passed:
      passed += 1
  print(f"\nSummary: {passed}/{len(results)} passed")
