from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any

from src.db import get_conn
from src.services.llm_service import LLMService

logger = logging.getLogger(__name__)

NEGATIVE_HINTS = ("not", "no", "never", "don't", "dislike", "不", "不要", "不喜欢", "讨厌")

ANTONYM_TRAIT_PAIRS = [
    ("quiet", "lively"),
    ("安静", "热闹"),
    ("安静", "吵闹"),
    ("人少", "人多"),
    ("清净", "嘈杂"),
]

# In-process embedding cache keyed by content hash.
# Cleared on process restart, which is acceptable for a dev/demo workload.
_EMBED_CACHE: dict[str, list[float]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── public API ───────────────────────────────────────────────────────────────


def classify_memory(note: str) -> str:
    low = note.lower()
    if any(k in low for k in ("prefer", "喜欢", "偏好", "爱", "常去")):
        return "preference"
    if any(k in low for k in ("plan", "打算", "准备", "下次", "要去")):
        return "plan"
    if any(k in low for k in ("i am", "我是", "来自", "职业", "工作")):
        return "profile"
    return "fact"


def add_memory_item(
    user_id: str,
    content: str,
    *,
    source: str = "tool",
    confidence: float = 0.82,
    memory_type: str | None = None,
) -> dict[str, Any]:
    note = content.strip()
    if not note:
        return {"ok": False, "error": "empty_note"}

    mtype = memory_type or classify_memory(note)
    topic = _topic_key(note)
    polarity = -1 if _is_negative(note) else 1
    conflicts = _find_conflicts(
        user_id=user_id,
        memory_type=mtype,
        topic_key=topic,
        polarity=polarity,
        new_content=note,
    )
    now = _now_iso()

    with get_conn() as conn:
        if conflicts:
            conf = max(0.1, min(1.0, confidence - 0.25))
            cur = conn.execute(
                """
                INSERT INTO memory_items (
                  user_id, memory_type, topic_key, polarity, content,
                  confidence, source, last_used_at, created_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (user_id, mtype, topic, polarity, note, conf, "pending_conflict", now, now),
            )
            pending_id = int(cur.lastrowid)
            conflict_ids = [int(item["id"]) for item in conflicts]
            conn.execute(
                """
                INSERT INTO memory_conflicts (
                  user_id, pending_memory_id, conflicting_memory_ids, status, created_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, pending_id, json.dumps(conflict_ids, ensure_ascii=False), "pending", now, None),
            )
            conn.execute(
                "INSERT INTO agent_memory (conversation_id, user_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (None, user_id, "memory", f"[PENDING_CONFLICT] {note}", now),
            )
            return {
                "ok": True,
                "saved": False,
                "pending": True,
                "memory_type": mtype,
                "topic_key": topic,
                "conflict_count": len(conflicts),
                "conflicts": conflicts,
                "resolution": "pending_human_confirmation",
                "pending_memory_id": pending_id,
            }

        conf = max(0.1, min(1.0, confidence))
        conn.execute(
            """
            INSERT INTO memory_items (
              user_id, memory_type, topic_key, polarity, content,
              confidence, source, last_used_at, created_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (user_id, mtype, topic, polarity, note, conf, source, now, now),
        )
        conn.execute(
            "INSERT INTO agent_memory (conversation_id, user_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (None, user_id, "memory", note, now),
        )

    return {
        "ok": True,
        "saved": True,
        "pending": False,
        "memory_type": mtype,
        "topic_key": topic,
        "confidence": round(conf, 3),
        "conflict_count": 0,
        "resolution": "saved_active",
    }


def deactivate_memory(user_id: str, memory_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE memory_items SET is_active = 0 WHERE id = ? AND user_id = ?",
            (memory_id, user_id),
        )
    if cur.rowcount == 0:
        return {"ok": False, "error": "not_found"}
    return {"ok": True, "deactivated_id": memory_id}


def retrieve_relevant_memories(user_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, memory_type, content, confidence, source, last_used_at, created_at
            FROM memory_items
            WHERE user_id = ? AND is_active = 1
            ORDER BY created_at DESC
            LIMIT 300
            """,
            (user_id,),
        ).fetchall()

    items = [dict(row) for row in rows]
    ranked = _rank_memories_semantic(query=query, items=items)[: max(1, min(limit, 12))]

    if ranked:
        now = _now_iso()
        ids = [item["id"] for item in ranked]
        placeholders = ",".join(["?"] * len(ids))
        with get_conn() as conn:
            conn.execute(
                f"UPDATE memory_items SET last_used_at = ? WHERE id IN ({placeholders})",
                [now, *ids],
            )
    return ranked


def list_pending_conflicts(user_id: str, limit: int = 30) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id AS conflict_id, c.pending_memory_id, c.conflicting_memory_ids,
                   c.created_at, m.content, m.memory_type
            FROM memory_conflicts c
            JOIN memory_items m ON m.id = c.pending_memory_id
            WHERE c.user_id = ? AND c.status = 'pending'
            ORDER BY c.id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["conflicting_ids"] = json.loads(item["conflicting_memory_ids"] or "[]")
        result.append(item)
    return result


def resolve_conflict(user_id: str, conflict_id: int, action: str) -> dict[str, Any]:
    if action not in {"approve", "reject"}:
        return {"ok": False, "error": "invalid_action"}

    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM memory_conflicts WHERE id = ? AND user_id = ? AND status = 'pending'",
            (conflict_id, user_id),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "conflict_not_found"}

        data = dict(row)
        pending_id = int(data["pending_memory_id"])
        old_ids = [int(x) for x in json.loads(data["conflicting_memory_ids"] or "[]")]
        now = _now_iso()

        if action == "approve":
            conn.execute(
                "UPDATE memory_items SET is_active = 1, source = 'approved_conflict' WHERE id = ?",
                (pending_id,),
            )
            if old_ids:
                ph = ",".join(["?"] * len(old_ids))
                conn.execute(f"UPDATE memory_items SET is_active = 0 WHERE id IN ({ph})", old_ids)
            status = "approved"
        else:
            conn.execute(
                "UPDATE memory_items SET is_active = 0, source = 'rejected_conflict' WHERE id = ?",
                (pending_id,),
            )
            status = "rejected"

        conn.execute(
            "UPDATE memory_conflicts SET status = ?, resolved_at = ? WHERE id = ?",
            (status, now, conflict_id),
        )
    return {"ok": True, "status": status, "pending_memory_id": pending_id, "old_memory_ids": old_ids}


# ─── semantic ranking ─────────────────────────────────────────────────────────


def _rank_memories_semantic(query: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank memories by semantic similarity using n-gram cosine + optional embeddings.

    Algorithm:
      1. Compute character n-gram TF-IDF cosine similarity (always, no external calls).
      2. Blend with confidence score.
      3. If OpenAI embeddings are available (provider=openai), re-rank using dense vectors.
    """
    if not items:
        return []

    q_vec = _ngram_tfidf(query)
    scored: list[tuple[float, dict[str, Any]]] = []

    for item in items:
        text = str(item.get("content", ""))
        conf = float(item.get("confidence") or 0.6)
        sim = _sparse_cosine(q_vec, _ngram_tfidf(text))
        score = sim * 0.75 + conf * 0.25
        if score > 0.05:
            scored.append((score, item))

    # Optionally re-rank with dense embeddings (only if OpenAI provider configured)
    try:
        llm = LLMService()
        if llm.is_enabled() and llm.cfg.provider in ("openai", "custom"):
            scored = _rerank_with_embeddings(query=query, scored=scored, llm=llm)
    except Exception as exc:
        logger.debug("embedding rerank skipped: %s", exc)

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


def _rerank_with_embeddings(
    query: str,
    scored: list[tuple[float, dict[str, Any]]],
    llm: "LLMService",
) -> list[tuple[float, dict[str, Any]]]:
    """Replace n-gram scores with dense cosine similarity from embedding API."""
    q_emb = _get_embedding(query, llm)
    if q_emb is None:
        return scored

    reranked: list[tuple[float, dict[str, Any]]] = []
    for _old_score, item in scored:
        text = str(item.get("content", ""))
        conf = float(item.get("confidence") or 0.6)
        t_emb = _get_embedding(text, llm)
        if t_emb is None:
            reranked.append((_old_score, item))
            continue
        sim = _dense_cosine(q_emb, t_emb)
        score = sim * 0.75 + conf * 0.25
        reranked.append((score, item))
    return reranked


def _get_embedding(text: str, llm: "LLMService") -> list[float] | None:
    cache_key = hashlib.md5(text.encode("utf-8")).hexdigest()
    if cache_key in _EMBED_CACHE:
        return _EMBED_CACHE[cache_key]
    try:
        from openai import OpenAI  # type: ignore[import]

        client = OpenAI(api_key=llm.cfg.api_key, base_url=llm.cfg.base_url or None)
        resp = client.embeddings.create(model="text-embedding-3-small", input=text[:512])
        vec = resp.data[0].embedding
        _EMBED_CACHE[cache_key] = vec
        return vec
    except Exception as exc:
        logger.debug("embedding call failed: %s", exc)
        return None


def _dense_cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _ngram_tfidf(text: str) -> dict[str, float]:
    """Character bigram + word unigram term-frequency vector (no IDF for simplicity)."""
    low = text.lower()
    tf: dict[str, int] = {}

    # word unigrams
    for word in re.findall(r"[a-z0-9]+|[一-鿿]+", low):
        tf[word] = tf.get(word, 0) + 1

    # character bigrams (captures partial Chinese word overlap)
    for i in range(len(low) - 1):
        bg = low[i : i + 2]
        if re.search(r"[a-z0-9一-鿿]", bg):
            tf[bg] = tf.get(bg, 0) + 1

    total = sum(tf.values()) or 1
    return {k: v / total for k, v in tf.items()}


def _sparse_cosine(a: dict[str, float], b: dict[str, float]) -> float:
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ─── conflict detection ───────────────────────────────────────────────────────


def _find_conflicts(
    user_id: str,
    memory_type: str,
    topic_key: str,
    polarity: int,
    new_content: str,
) -> list[dict[str, Any]]:
    new_traits = _extract_traits(new_content)
    llm = LLMService()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, content, topic_key, polarity
            FROM memory_items
            WHERE user_id = ? AND memory_type = ? AND is_active = 1
            ORDER BY created_at DESC
            LIMIT 80
            """,
            (user_id, memory_type),
        ).fetchall()
    conflicts: list[dict[str, Any]] = []
    for row in rows:
        old_id = int(row["id"])
        old_content = str(row["content"])
        old_topic = str(row["topic_key"] or _topic_key(old_content))
        old_polarity = int(row["polarity"] or 1)
        old_traits = _extract_traits(old_content)

        if old_topic == topic_key and old_polarity != polarity:
            conflicts.append({"id": old_id, "content": old_content, "reason": "same_topic_opposite_polarity"})
            continue

        if _llm_semantic_conflict(new_text=new_content, old_text=old_content, llm=llm):
            conflicts.append({"id": old_id, "content": old_content, "reason": "llm_semantic_conflict"})
            continue

        if _has_trait_conflict(new_traits, old_traits):
            conflicts.append({"id": old_id, "content": old_content, "reason": "opposite_preference_trait"})

    return conflicts


def _is_negative(text: str) -> bool:
    return any(k in text.lower() for k in NEGATIVE_HINTS)


def _topic_key(text: str) -> str:
    normalized = re.sub(r"\s+", "", text.lower())
    for k in NEGATIVE_HINTS:
        normalized = normalized.replace(k, "")
    return normalized[:18]


def _extract_traits(text: str) -> set[str]:
    low = str(text).lower()
    traits: set[str] = set()
    for left, right in ANTONYM_TRAIT_PAIRS:
        if left in low:
            traits.add(left)
        if right in low:
            traits.add(right)
    return traits


def _has_trait_conflict(new_traits: set[str], old_traits: set[str]) -> bool:
    if not new_traits or not old_traits:
        return False
    for left, right in ANTONYM_TRAIT_PAIRS:
        if (left in new_traits and right in old_traits) or (right in new_traits and left in old_traits):
            return True
    return False


def _llm_semantic_conflict(new_text: str, old_text: str, llm: LLMService) -> bool:
    if not llm.is_enabled():
        return False
    try:
        result = llm.chat(
            system_prompt=(
                "You are a strict contradiction detector for user memory statements. "
                "Only mark conflict=true when both statements are semantically incompatible "
                "and cannot both hold simultaneously. "
                "Topic difference or detail granularity is NOT a conflict. "
                "Return JSON only: {\"conflict\": true|false}."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"new_statement: {new_text}\nold_statement: {old_text}\nTask: contradictory?",
                }
            ],
        )
        m = re.search(r"\{[\s\S]*?\}", result)
        payload = json.loads(m.group(0) if m else result)
        return bool(payload.get("conflict", False))
    except Exception:
        return False
