from __future__ import annotations

import streamlit as st

from src.config import DEFAULT_USER_ID
from src.db import init_db
from src.memory import deactivate_memory, list_pending_conflicts, resolve_conflict
from src.services.agent_service import get_memory_notes


TITLE = "🧠 旅行记忆"
SUB = "这里展示长期记忆，冲突记忆需要人工确认。"

st.set_page_config(page_title=TITLE, page_icon="🧠", layout="wide")
init_db()

if "user_id" not in st.session_state:
  st.session_state["user_id"] = DEFAULT_USER_ID

st.title(TITLE)
st.caption(SUB)

if st.button("刷新", use_container_width=False):
  st.rerun()

pending = list_pending_conflicts(st.session_state["user_id"], limit=50)
st.subheader("待确认冲突")
if not pending:
  st.info("暂无待处理的冲突记忆。")
else:
  for item in pending:
    with st.container(border=True):
      st.write(f"**候选新记忆**: {item['content']}")
      st.caption(f"type={item['memory_type']} | conflict_id={item['conflict_id']} | 冲突旧记忆 ID：{item['conflicting_ids']}")
      c1, c2 = st.columns(2)
      if c1.button("批准替换旧记忆", key=f"approve_{item['conflict_id']}", use_container_width=True):
        result = resolve_conflict(st.session_state["user_id"], int(item["conflict_id"]), "approve")
        if result.get("ok"):
          st.success("已批准。新记忆已生效，旧冲突记忆已失活。")
        else:
          st.error(str(result))
        st.rerun()
      if c2.button("拒绝新记忆", key=f"reject_{item['conflict_id']}", use_container_width=True):
        result = resolve_conflict(st.session_state["user_id"], int(item["conflict_id"]), "reject")
        if result.get("ok"):
          st.success("已拒绝。继续使用旧记忆。")
        else:
          st.error(str(result))
        st.rerun()

st.subheader("已生效记忆")
notes = get_memory_notes(st.session_state["user_id"], limit=200)
if not notes:
  st.info("暂无记忆内容。")
else:
  st.caption(f"共 {len(notes)} 条（点击「删除」将该条记忆失活，不再参与检索）")

  TYPE_LABELS = {
    "preference": "🎯 偏好",
    "plan": "📅 计划",
    "profile": "👤 画像",
    "fact": "📌 事实",
  }

  for idx, note in enumerate(notes):
    with st.container(border=True):
      mem_id = note.get("id")  # None for legacy agent_memory rows
      col_text, col_del = st.columns([9, 1])
      mtype = str(note.get("memory_type") or "fact")
      label = TYPE_LABELS.get(mtype, mtype)
      conf = note.get("confidence")
      conf_text = f"  置信度 {int(float(conf) * 100)}%" if conf else ""
      col_text.write(note["content"])
      col_text.caption(f"{label}{conf_text} | {note.get('created_at', '')[:16].replace('T', ' ')}")
      if mem_id is not None:
        if col_del.button("🗑️", key=f"del_mem_{mem_id}", help="删除该条记忆"):
          res = deactivate_memory(st.session_state["user_id"], int(mem_id))
          if res.get("ok"):
            st.success("已删除。")
          else:
            st.error("删除失败。")
          st.rerun()
      else:
        col_del.caption("—")
