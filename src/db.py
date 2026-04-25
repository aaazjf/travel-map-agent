import sqlite3
from contextlib import contextmanager

from src.config import ASSISTANT_ATTACHMENT_DIR, DATA_DIR, DB_PATH, SUMMARY_MD_DIR, UPLOAD_DIR


def init_db() -> None:
  DATA_DIR.mkdir(parents=True, exist_ok=True)
  UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
  SUMMARY_MD_DIR.mkdir(parents=True, exist_ok=True)
  ASSISTANT_ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)

  with sqlite3.connect(DB_PATH) as conn:
    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS spots (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        place_name TEXT NOT NULL,
        country TEXT,
        admin1 TEXT,
        city TEXT,
        district TEXT,
        lat REAL NOT NULL,
        lng REAL NOT NULL,
        travel_at TEXT,
        note TEXT,
        created_at TEXT NOT NULL
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS photos (
        id TEXT PRIMARY KEY,
        spot_id TEXT NOT NULL,
        file_path TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (spot_id) REFERENCES spots(id) ON DELETE CASCADE
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS invites (
        id TEXT PRIMARY KEY,
        from_user TEXT NOT NULL,
        to_user TEXT NOT NULL,
        score REAL NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS agent_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS agent_tool_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        conversation_id TEXT,
        route_agent TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        tool_args TEXT NOT NULL,
        tool_result TEXT NOT NULL,
        created_at TEXT NOT NULL
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS memory_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        memory_type TEXT NOT NULL,
        topic_key TEXT,
        polarity INTEGER,
        content TEXT NOT NULL,
        confidence REAL NOT NULL,
        source TEXT NOT NULL,
        last_used_at TEXT,
        created_at TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS memory_conflicts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        pending_memory_id INTEGER NOT NULL,
        conflicting_memory_ids TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        resolved_at TEXT
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS agent_run_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        conversation_id TEXT,
        route_agent TEXT NOT NULL,
        query_text TEXT NOT NULL,
        memory_hits_json TEXT NOT NULL,
        context_budget_json TEXT NOT NULL,
        history_used INTEGER NOT NULL,
        memory_used INTEGER NOT NULL,
        created_at TEXT NOT NULL
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS agent_pending_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        conversation_id TEXT,
        route_agent TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        tool_args TEXT NOT NULL,
        status TEXT NOT NULL,
        reason TEXT NOT NULL,
        tool_result TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS agent_guard_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        conversation_id TEXT,
        route_agent TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS conversation_summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        file_path TEXT NOT NULL,
        summary_text TEXT NOT NULL,
        created_at TEXT NOT NULL
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS assistant_attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        file_name TEXT NOT NULL,
        mime_type TEXT,
        file_path TEXT NOT NULL,
        extracted_text TEXT,
        created_at TEXT NOT NULL
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS trip_plans (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        query_text TEXT NOT NULL,
        country TEXT,
        days INTEGER,
        theme TEXT,
        budget_level TEXT,
        plan_markdown TEXT NOT NULL,
        created_at TEXT NOT NULL
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS plan_shares (
        id TEXT PRIMARY KEY,
        plan_id TEXT NOT NULL,
        from_user TEXT NOT NULL,
        to_user TEXT NOT NULL,
        status TEXT NOT NULL,
        message TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        FOREIGN KEY (plan_id) REFERENCES trip_plans(id) ON DELETE CASCADE
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS album_shares (
        id TEXT PRIMARY KEY,
        spot_id TEXT NOT NULL,
        from_user TEXT NOT NULL,
        to_user TEXT NOT NULL,
        status TEXT NOT NULL,
        message TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        FOREIGN KEY (spot_id) REFERENCES spots(id) ON DELETE CASCADE
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS spot_comments (
        id TEXT PRIMARY KEY,
        spot_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        content TEXT NOT NULL,
        mentions TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (spot_id) REFERENCES spots(id) ON DELETE CASCADE
      )
      """
    )

    conn.execute(
      """
      CREATE TABLE IF NOT EXISTS photo_tags (
        id TEXT PRIMARY KEY,
        photo_id TEXT NOT NULL,
        spot_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        tags_json TEXT NOT NULL,
        source TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (photo_id) REFERENCES photos(id) ON DELETE CASCADE,
        FOREIGN KEY (spot_id) REFERENCES spots(id) ON DELETE CASCADE
      )
      """
    )

    _ensure_agent_memory_conversation_id(conn)
    _ensure_memory_item_columns(conn)


def _ensure_agent_memory_conversation_id(conn: sqlite3.Connection) -> None:
  cols = conn.execute("PRAGMA table_info(agent_memory)").fetchall()
  names = {row[1] for row in cols}
  if "conversation_id" not in names:
    conn.execute("ALTER TABLE agent_memory ADD COLUMN conversation_id TEXT")


def _ensure_memory_item_columns(conn: sqlite3.Connection) -> None:
  cols = conn.execute("PRAGMA table_info(memory_items)").fetchall()
  names = {row[1] for row in cols}
  if "topic_key" not in names:
    conn.execute("ALTER TABLE memory_items ADD COLUMN topic_key TEXT")
  if "polarity" not in names:
    conn.execute("ALTER TABLE memory_items ADD COLUMN polarity INTEGER")


@contextmanager
def get_conn():
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  conn.execute("PRAGMA foreign_keys = ON")
  try:
    yield conn
    conn.commit()
  finally:
    conn.close()
