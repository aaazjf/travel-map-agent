from __future__ import annotations

import streamlit as st

from src.config import DEFAULT_USER_ID
from src.db import init_db
from src.services.collaboration_service import (
  add_spot_comment,
  list_received_shares,
  list_spot_comments,
  list_users,
  resolve_share,
  share_spot_album,
)
from src.services.spot_service import list_spots


st.set_page_config(page_title="协作中心", page_icon=":people_holding_hands:", layout="wide")
init_db()

if "user_id" not in st.session_state:
  st.session_state["user_id"] = DEFAULT_USER_ID

st.title("多用户协作中心")
st.caption("支持共享相册、邀请确认、评论与 @搭子（模拟多用户）。")

users = list_users()
user_map = {u["display_name"]: u["user_id"] for u in users}
default_label = next((k for k, v in user_map.items() if v == st.session_state["user_id"]), list(user_map.keys())[0])
selected_label = st.selectbox("当前身份（用于演示多用户）", options=list(user_map.keys()), index=list(user_map.keys()).index(default_label))
st.session_state["user_id"] = user_map[selected_label]

st.divider()
st.subheader("共享我的相册地点")
spots = list_spots(st.session_state["user_id"])
if not spots:
  st.caption("当前用户暂无地点记录。")
else:
  target_users = [u for u in users if u["user_id"] != st.session_state["user_id"]]
  t_map = {u["display_name"]: u["user_id"] for u in target_users}
  c1, c2, c3 = st.columns([3.6, 2.4, 1.2])
  spot_options = {
    f"{s.get('place_name', '')} | {s.get('country', '')} {s.get('city', '')} | {str(s.get('travel_at') or s.get('created_at') or '')[:16]}": s["id"]
    for s in spots
  }
  pick_spot_label = c1.selectbox("选择地点", options=list(spot_options.keys()), label_visibility="collapsed")
  pick_user_label = c2.selectbox("共享给谁", options=list(t_map.keys()), label_visibility="collapsed") if t_map else ""
  if c3.button("发起共享", use_container_width=True, disabled=not bool(t_map)):
    share_spot_album(
      spot_id=spot_options[pick_spot_label],
      from_user=st.session_state["user_id"],
      to_user=t_map[pick_user_label],
      message="共享这条旅行记录给你，欢迎评论。",
    )
    st.success(f"已共享给 {pick_user_label}。")

st.divider()
st.subheader("收到的共享（邀请确认）")
received = list_received_shares(st.session_state["user_id"])
plan_shares = received.get("plan_shares", [])
album_shares = received.get("album_shares", [])

if not plan_shares and not album_shares:
  st.caption("暂无收到的共享。")

for item in plan_shares:
  with st.container(border=True):
    st.write(f"行程共享：{item.get('plan_title', '')}")
    st.caption(f"来自 {item.get('from_user')} | 状态：{item.get('status')} | {item.get('created_at')}")
    if item.get("message"):
      st.write(item.get("message"))
    if item.get("status") == "pending":
      c1, c2 = st.columns(2)
      if c1.button("接受", key=f"accept_plan_{item['id']}", use_container_width=True):
        resolve_share("plan", str(item["id"]), "accept")
        st.rerun()
      if c2.button("拒绝", key=f"reject_plan_{item['id']}", use_container_width=True):
        resolve_share("plan", str(item["id"]), "reject")
        st.rerun()

for item in album_shares:
  with st.container(border=True):
    title = f"相册共享：{item.get('place_name', '')} | {item.get('country', '')} {item.get('city', '')}"
    st.write(title)
    st.caption(f"来自 {item.get('from_user')} | 状态：{item.get('status')} | {item.get('created_at')}")
    if item.get("message"):
      st.write(item.get("message"))
    if item.get("status") == "pending":
      c1, c2 = st.columns(2)
      if c1.button("接受", key=f"accept_album_{item['id']}", use_container_width=True):
        resolve_share("album", str(item["id"]), "accept")
        st.rerun()
      if c2.button("拒绝", key=f"reject_album_{item['id']}", use_container_width=True):
        resolve_share("album", str(item["id"]), "reject")
        st.rerun()

st.divider()
st.subheader("地点评论与 @搭子")
# 可评论地点 = 自己的地点 + 已接受的共享地点
_own_spot_ids = {s["id"] for s in spots}
_shared_for_comment = [
  {
    "id": item["spot_id"],
    "place_name": item.get("place_name", ""),
    "country": item.get("country", ""),
    "city": item.get("city", ""),
  }
  for item in album_shares
  if item.get("status") == "accepted"
]
comment_spots = spots + [s for s in _shared_for_comment if s["id"] not in _own_spot_ids]

if not comment_spots:
  st.caption("当前用户暂无可评论地点（共享接受后可对共享地点评论）。")
else:
  spot_map = {
    f"{s.get('place_name', '')} | {s.get('country', '')} {s.get('city', '')}": s["id"]
    for s in comment_spots
  }
  selected_spot_label = st.selectbox("选择评论地点", options=list(spot_map.keys()))
  selected_spot_id = spot_map[selected_spot_label]

  other_users = [u for u in users if u["user_id"] != st.session_state["user_id"]]

  # ── 在任何 comment_input widget 渲染之前，把上一轮挂起的值写入 session state ──
  # Streamlit 规则：key 绑定的 widget 渲染后不能再修改其 session state，
  # 所以 chip 点击 / 发送清空都只记录 _pending_comment，
  # 下一次 rerun 最开头在这里统一落地。
  if "_pending_comment" in st.session_state:
    st.session_state["comment_input"] = st.session_state.pop("_pending_comment")

  # ── @用户前缀搜索 ─────────────────────────────────────────────────────────────
  if other_users:
    mention_filter = st.text_input(
      "🔍 搜索要 @ 的用户",
      placeholder="输入开头字符，如 a → 匹配 alina…",
      key="mention_filter_input",
      label_visibility="visible",
    )
    filter_text = mention_filter.strip().lower()
    if filter_text:
      matched = [
        u for u in other_users
        if u["user_id"].lower().startswith(filter_text)
        or u["display_name"].lower().startswith(filter_text)
      ]
      if matched:
        chip_cols = st.columns(min(len(matched), 6))
        for i, u in enumerate(matched[:6]):
          uid = u["user_id"]
          if chip_cols[i].button(f"@{uid}", key=f"chip_{uid}", help=u["display_name"]):
            current = st.session_state.get("comment_draft", "")
            tag = f"@{uid}"
            if tag not in current:
              new_text = (current.rstrip() + f" {tag} ").lstrip()
              st.session_state["comment_draft"] = new_text
              # 不直接写 comment_input（widget 可能已渲染），挂起到下一轮
              st.session_state["_pending_comment"] = new_text
            st.rerun()
      else:
        st.caption("无匹配用户。")

  # ── 评论输入框 ────────────────────────────────────────────────────────────────
  comment_text = st.text_input(
    "输入评论",
    value=st.session_state.get("comment_draft", ""),
    placeholder="例如：@u_alina 这条路线你会喜欢吗？",
    key="comment_input",
  )
  # 实时同步用户的手动输入到 draft
  st.session_state["comment_draft"] = comment_text

  # ── 发送 ──────────────────────────────────────────────────────────────────────
  if st.button("发送评论", use_container_width=False):
    result = add_spot_comment(selected_spot_id, st.session_state["user_id"], comment_text)
    if result.get("ok"):
      st.session_state["comment_draft"] = ""
      # 发送后清空输入框：挂起到下一轮，不在 widget 渲染后直接写
      st.session_state["_pending_comment"] = ""
      st.success("评论已发送。")
      st.rerun()
    else:
      st.warning("评论不能为空。")

  # ── 评论列表 ──────────────────────────────────────────────────────────────────
  # 可见规则：公开评论（无艾特）+ 艾特了当前用户的评论 + 自己发的评论
  _cur = st.session_state["user_id"]
  comments = list_spot_comments(selected_spot_id, limit=50)
  visible = [
    c for c in comments
    if not (c.get("mentions") or [])          # 公开（无艾特）
    or _cur in (c.get("mentions") or [])       # 艾特了我
    or c.get("user_id") == _cur                # 自己发的
  ]
  if not visible:
    st.caption("暂无可见评论（公开评论或艾特你的评论会显示在此）。")
  else:
    for c in visible:
      with st.container(border=True):
        mentions = c.get("mentions") or []
        is_mine = c.get("user_id") == _cur
        col_txt, col_btn = st.columns([6, 1])
        col_txt.write(c.get("content", ""))
        tag_str = "、".join(mentions) if mentions else "公开"
        col_txt.caption(
          f"{'🟢 ' if is_mine else ''}{c.get('user_id')} "
          f"| 可见：{tag_str} "
          f"| {str(c.get('created_at', ''))[:16]}"
        )
        if not is_mine:
          reply_uid = c.get("user_id", "")
          if col_btn.button("回复", key=f"reply_{c.get('id', '')}_{selected_spot_id}", use_container_width=True):
            tag = f"@{reply_uid}"
            draft = st.session_state.get("comment_draft", "")
            new_draft = (draft.rstrip() + " " + tag + " ").lstrip() if tag not in draft else draft
            st.session_state["comment_draft"] = new_draft
            st.session_state["_pending_comment"] = new_draft
            st.rerun()
