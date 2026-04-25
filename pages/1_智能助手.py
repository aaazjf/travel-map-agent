from __future__ import annotations

import streamlit as st

from src.config import DEFAULT_USER_ID
from src.db import init_db
from src.services.agent_service import (
  add_chat_message,
  answer,
  clear_conversation_attachments,
  compress_conversation_history,
  delete_assistant_attachment,
  ensure_active_conversation,
  get_agent_runtime_info,
  get_chat_history,
  get_conversation_compress_hint,
  get_latest_agent_debug,
  get_latest_history_summary,
  get_latest_history_summary_md,
  get_pending_tool_approvals,
  get_request_trace,
  handle_tool_approval,
  list_assistant_attachments,
  list_conversations,
  save_assistant_attachment,
  start_new_conversation,
)
from src.services.spot_service import list_spots


TXT_TITLE = "🤖 智能助手"
TXT_WARNING = "未启用 LLM。请在 `.env` 中配置 LLM_PROVIDER 和对应 API Key。"
TXT_NEW_CHAT = "新建对话"
TXT_HISTORY = "历史会话"
TXT_COMPRESS = "压缩当前会话"
TXT_COMPRESS_MODE = "压缩方式"
TXT_COMPRESS_OK = "压缩完成：已压缩 {count} 条中间消息。"
TXT_COMPRESS_SKIP = "当前无需压缩。"
TXT_CHAT_HINT = "可以问我：总结旅行 / 查找搭子 / 发起邀请 / 写入记忆"
TXT_THINKING = "正在思考中..."
TXT_STEP_1 = "① 读取你的旅行记录与记忆..."
TXT_STEP_2 = "② 调用模型与工具..."
TXT_STEP_3 = "③ 整理最终回复..."
TXT_DONE = "回答完成 ✓"
TXT_TRACE = "本轮 Agent 执行调试信息"
TXT_TOKEN = "Token 上下文液位"
TXT_PENDING = "待审批工具调用"
TXT_TRACE_BY_ID = "按 request_id 回放执行链路"
TXT_COMPRESS_TIP_RECOMMEND = "小tips：当前对话 token 占用较高，建议压缩。"
TXT_COMPRESS_TIP_OK = "小tips：当前对话还不需压缩。"
TXT_SUMMARY_BLOCK = "最近一次 History Summary"
TXT_ATTACH = "附件上传（PDF/Excel/Word）"


def render_floating_token_tank(used_tokens: int, total_tokens: int) -> None:
  total = max(1, int(total_tokens))
  used = max(0, min(int(used_tokens), total))
  remain = total - used
  fill_percent = int(round((remain / total) * 100))
  color = "#39b980" if fill_percent > 60 else "#f0a400" if fill_percent > 30 else "#df4d4d"
  st.markdown(
    f"""
    <div style="
      position: fixed;
      right: 18px;
      bottom: 140px;
      z-index: 9999;
      background: rgba(255, 255, 255, 0.96);
      border: 1px solid #d7dce1;
      border-radius: 12px;
      padding: 8px 10px;
      box-shadow: 0 4px 14px rgba(0,0,0,0.08);
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 170px;
    ">
      <div style="width:18px;height:56px;border:2px solid #bfc7cf;border-radius:9px;position:relative;overflow:hidden;background:#f4f6f8;">
        <div style="position:absolute;left:0;bottom:0;width:100%;height:{fill_percent}%;background:{color};transition:height .3s ease;"></div>
      </div>
      <div style="line-height:1.3;font-size:12px;color:#1f2937;">
        <div style="font-weight:700;">{TXT_TOKEN}</div>
        <div>已用 <b>{used}</b> / {total}</div>
        <div>剩余 <b>{fill_percent}%</b></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
  )


st.set_page_config(page_title=TXT_TITLE, page_icon="🤖", layout="wide")
init_db()

if "user_id" not in st.session_state:
  st.session_state["user_id"] = DEFAULT_USER_ID

if "active_conversation_id" not in st.session_state:
  st.session_state["active_conversation_id"] = ensure_active_conversation(st.session_state["user_id"])

st.title(TXT_TITLE)
runtime = get_agent_runtime_info()
st.caption(f"运行模式：{runtime['mode']} | 模型通道：{runtime['provider']}")
st.caption(f"架构：{runtime.get('architecture', 'single-agent')}")
if runtime["mode"] != "LLM_TOOL_AGENT":
  st.warning(TXT_WARNING)

with st.expander(TXT_TRACE_BY_ID, expanded=False):
  rid = st.text_input("request_id", value="", placeholder="粘贴 request_id 后查看完整链路")
  if st.button("查询链路", key="trace_by_id_btn"):
    if not rid.strip():
      st.warning("请先输入 request_id。")
    else:
      trace = get_request_trace(st.session_state["user_id"], rid.strip())
      if not trace:
        st.info("未找到该 request_id 的运行记录。")
      else:
        st.json(trace)

conversations = list_conversations(st.session_state["user_id"])
if not conversations:
  first = start_new_conversation(st.session_state["user_id"])
  st.session_state["active_conversation_id"] = first["id"]
  conversations = list_conversations(st.session_state["user_id"])

conv_map = {f"{item['title']} | {item['updated_at'][:16].replace('T', ' ')}": item["id"] for item in conversations}
labels = list(conv_map.keys())
active_id = st.session_state["active_conversation_id"]
default_index = 0
for i, label in enumerate(labels):
  if conv_map[label] == active_id:
    default_index = i
    break

latest_debug = get_latest_agent_debug(
  st.session_state["user_id"],
  conversation_id=st.session_state["active_conversation_id"],
)
budget = latest_debug.get("context_budget", {}) if latest_debug else {}
budgets = budget.get("budgets", {}) if isinstance(budget, dict) else {}

col_new, col_center, col_zip = st.columns([1.15, 4.8, 1.25])
if col_new.button(TXT_NEW_CHAT, use_container_width=True):
  created = start_new_conversation(st.session_state["user_id"])
  st.session_state["active_conversation_id"] = created["id"]
  st.rerun()

selected_label = col_center.selectbox(
  TXT_HISTORY,
  options=labels,
  index=default_index,
  label_visibility="collapsed",
)
selected_conversation_id = conv_map[selected_label]
if selected_conversation_id != st.session_state["active_conversation_id"]:
  # Clean up attachment tracking for the old conversation to avoid stale state
  old_att_key = f"_saved_att_names_{st.session_state['active_conversation_id']}"
  st.session_state.pop(old_att_key, None)
  st.session_state["active_conversation_id"] = selected_conversation_id
  st.rerun()

compress_mode = col_zip.selectbox(
  TXT_COMPRESS_MODE,
  options=["普通压缩", "压缩并导出MD"],
  index=0,
  label_visibility="collapsed",
)
export_md = compress_mode == "压缩并导出MD"

if col_zip.button(TXT_COMPRESS, use_container_width=True):
  result = compress_conversation_history(
    user_id=st.session_state["user_id"],
    conversation_id=st.session_state["active_conversation_id"],
    force=True,
    export_md=export_md,
  )
  if result.get("compressed"):
    st.success(TXT_COMPRESS_OK.format(count=result.get("removed_messages", 0)))
    if result.get("summary_md_path"):
      st.caption(f"History Summary 已导出 Markdown: `{result.get('summary_md_path')}`")
      st.session_state["latest_summary_md_path"] = result.get("summary_md_path")
    else:
      st.session_state["latest_summary_md_path"] = ""
  else:
    st.info(result.get("message", TXT_COMPRESS_SKIP))

if st.session_state.get("latest_summary_md_path"):
  try:
    _md_path = st.session_state.get("latest_summary_md_path")
    with open(_md_path, "rb") as f:
      _md_bytes = f.read()
    col_zip.download_button(
      label="下载 History Summary.md",
      data=_md_bytes,
      file_name="history_summary.md",
      mime="text/markdown",
      use_container_width=True,
      key="download_history_summary_md",
    )
  except Exception:
    pass

compress_hint = get_conversation_compress_hint(
  user_id=st.session_state["user_id"],
  conversation_id=st.session_state["active_conversation_id"],
)
if compress_hint.get("recommended"):
  st.caption(
    f"{TXT_COMPRESS_TIP_RECOMMEND} "
    f"({int(compress_hint.get('conversation_tokens', 0))}/{int(compress_hint.get('threshold_tokens', 0))})"
  )
else:
  st.caption(
    f"{TXT_COMPRESS_TIP_OK} "
    f"({int(compress_hint.get('conversation_tokens', 0))}/{int(compress_hint.get('threshold_tokens', 0))})"
  )

latest_summary = get_latest_history_summary(
  user_id=st.session_state["user_id"],
  conversation_id=st.session_state["active_conversation_id"],
)
latest_summary_md = get_latest_history_summary_md(
  user_id=st.session_state["user_id"],
  conversation_id=st.session_state["active_conversation_id"],
)
with st.expander(TXT_SUMMARY_BLOCK, expanded=False):
  if latest_summary:
    st.code(latest_summary, language="markdown")
    if latest_summary_md.get("file_path"):
      st.caption(f"Markdown 文件: `{latest_summary_md.get('file_path')}`")
  else:
    st.caption("当前会话还没有 History Summary。")

# ── token tank (floating, above chat_input bar) ───────────────────────────────
render_floating_token_tank(
  used_tokens=int(budget.get("total_tokens_used", 0) or 0),
  total_tokens=int(budgets.get("total_tokens", 3000) or 3000),
)

# ── chat history ──────────────────────────────────────────────────────────────
history = get_chat_history(
  user_id=st.session_state["user_id"],
  conversation_id=st.session_state["active_conversation_id"],
)
for message in history:
  with st.chat_message("assistant" if message["role"] == "assistant" else "user"):
    st.write(message["content"])

# ── panels below history ─────────────────────────────────────────────────────
pending_actions = get_pending_tool_approvals(st.session_state["user_id"], limit=20)
with st.expander(TXT_PENDING, expanded=bool(pending_actions)):
  if not pending_actions:
    st.caption("当前无待审批操作。")
  else:
    for p in pending_actions:
      with st.container(border=True):
        st.write(f"**ID {p['id']} | {p['tool_name']}**")
        st.caption(f"原因: {p['reason']} | agent={p['route_agent']} | {p['created_at']}")
        st.json(p.get("tool_args_obj", {}))
        c1, c2 = st.columns(2)
        if c1.button("批准执行", key=f"approve_tool_{p['id']}", use_container_width=True):
          res = handle_tool_approval(st.session_state["user_id"], int(p["id"]), "approve")
          if res.get("ok"):
            st.success(f"已执行审批 ID={p['id']}")
          else:
            st.error(str(res))
          st.rerun()
        if c2.button("拒绝", key=f"reject_tool_{p['id']}", use_container_width=True):
          res = handle_tool_approval(st.session_state["user_id"], int(p["id"]), "reject")
          if res.get("ok"):
            st.info(f"已拒绝 ID={p['id']}")
          else:
            st.error(str(res))
          st.rerun()

with st.expander(TXT_TRACE, expanded=False):
  if latest_debug:
    st.json(latest_debug)
  else:
    st.caption("本会话暂无可展示的执行调试信息。")

# ── attachment panel ──────────────────────────────────────────────────────────
# Per-conversation set that tracks which filenames were already saved this session.
# This prevents the file uploader (which retains state across reruns) from
# re-uploading the same files every time any other widget triggers a rerun.
_att_saved_key = f"_saved_att_names_{st.session_state['active_conversation_id']}"
if _att_saved_key not in st.session_state:
  st.session_state[_att_saved_key] = set()

attached = list_assistant_attachments(
  user_id=st.session_state["user_id"],
  conversation_id=st.session_state["active_conversation_id"],
  limit=20,
)

with st.expander(
  f"📎 {TXT_ATTACH}（{len(attached)} 个）" if attached else f"📎 {TXT_ATTACH}",
  expanded=False,
):
  _uploaded = st.file_uploader(
    "上传文件",
    type=["pdf", "doc", "docx", "xls", "xlsx", "txt", "md", "csv"],
    accept_multiple_files=True,
    key="quick_attach_uploader",
    label_visibility="collapsed",
  )
  if _uploaded:
    # Only process files that haven't been saved yet this session
    _new_files = [
      f for f in _uploaded
      if f.name not in st.session_state[_att_saved_key]
    ]
    if _new_files:
      _saved_count = 0
      for _f in _new_files:
        try:
          _res = save_assistant_attachment(
            user_id=st.session_state["user_id"],
            conversation_id=st.session_state["active_conversation_id"],
            file_name=_f.name,
            mime_type=str(getattr(_f, "type", "") or ""),
            data=_f.getvalue(),
          )
          if _res.get("ok"):
            _saved_count += 1
            st.session_state[_att_saved_key].add(_f.name)
        except Exception as _exc:
          st.error(f"附件保存失败: {_f.name} | {_exc}")
      if _saved_count:
        st.success(f"已保存 {_saved_count} 个附件。")
        st.rerun()

  if attached:
    if st.button("🗑️ 清除全部附件", key="clear_all_attachments"):
      clear_conversation_attachments(
        user_id=st.session_state["user_id"],
        conversation_id=st.session_state["active_conversation_id"],
      )
      st.session_state[_att_saved_key] = set()
      st.rerun()

    for _att in attached:
      _col_name, _col_del = st.columns([8, 1])
      _col_name.caption(
        f"📄 {_att.get('file_name', '')}  "
        f"| {str(_att.get('created_at', ''))[:16].replace('T', ' ')}"
      )
      if _col_del.button("✕", key=f"del_att_{_att['id']}", help="删除此附件"):
        delete_assistant_attachment(
          user_id=st.session_state["user_id"],
          attachment_id=int(_att["id"]),
        )
        # Remove from tracking so the file can be re-uploaded later if needed
        st.session_state[_att_saved_key].discard(_att.get("file_name", ""))
        st.rerun()
  else:
    st.caption("当前对话暂无附件，上传后助手可直接分析内容。")

# ── chat input (Enter to send, auto-clears) ───────────────────────────────────
if prompt := st.chat_input(TXT_CHAT_HINT):
  conversation_id = st.session_state["active_conversation_id"]
  user_id = st.session_state["user_id"]
  query = prompt.strip()

  # Render user bubble immediately
  with st.chat_message("user"):
    st.write(query)

  # Save user message
  add_chat_message(user_id, "user", query, conversation_id=conversation_id)

  # Render assistant bubble with thinking steps
  with st.chat_message("assistant"):
    with st.status(TXT_THINKING, expanded=True) as status:
      st.write(TXT_STEP_1)
      spots = list_spots(user_id)
      st.write(TXT_STEP_2)
      reply = answer(user_id, query, spots, conversation_id=conversation_id)
      st.write(TXT_STEP_3)
      status.update(label=TXT_DONE, state="complete", expanded=False)
    st.write(reply)

  # Save assistant reply then refresh to persist history
  add_chat_message(user_id, "assistant", reply, conversation_id=conversation_id)
  st.rerun()
