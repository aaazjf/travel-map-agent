from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
  sys.path.insert(0, str(ROOT_DIR))

from src.db import init_db
from src.memory.service import add_memory_item, retrieve_relevant_memories


EVAL_USER = "eval_memory_user"


def load_cases() -> list[dict]:
  path = Path(__file__).with_name("memory_cases.json")
  return json.loads(path.read_text(encoding="utf-8"))


def seed_memories(cases: list[dict]) -> None:
  for case in cases:
    add_memory_item(EVAL_USER, case["query"], source="eval", confidence=0.9)


def run_eval() -> tuple[int, int, list[dict]]:
  cases = load_cases()
  seed_memories(cases)

  passed = 0
  details = []
  for case in cases:
    query = case["query"]
    expected = case["expect"]
    memories = retrieve_relevant_memories(EVAL_USER, query, limit=3)
    joined = " | ".join([str(m.get("content", "")) for m in memories])
    ok = expected in joined
    if ok:
      passed += 1
    details.append(
      {
        "query": query,
        "expected": expected,
        "top_memories": [m.get("content", "") for m in memories],
        "pass": ok,
      }
    )
  return passed, len(cases), details


if __name__ == "__main__":
  init_db()
  p, total, details = run_eval()
  print(f"[memory-eval] pass={p}/{total}")
  for item in details:
    mark = "PASS" if item["pass"] else "FAIL"
    print(f"- {mark} | {item['query']} | expect={item['expected']} | hits={item['top_memories']}")
