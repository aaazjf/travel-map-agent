from __future__ import annotations

from datetime import datetime

import streamlit as st

from src.config import DEFAULT_USER_ID
from src.db import init_db
from src.services.collaboration_service import list_users, share_trip_plan
from src.services.itinerary_service import generate_trip_plan, list_trip_plans, save_trip_plan


st.set_page_config(page_title="行程规划", page_icon=":compass:", layout="wide")
init_db()

if "user_id" not in st.session_state:
  st.session_state["user_id"] = DEFAULT_USER_ID

st.title("行程规划")
st.caption("填写目的地和偏好，AI 自动生成详细每日安排")

with st.form("trip_plan_form", clear_on_submit=False):
  col1, col2, col3 = st.columns([2, 1, 2])
  destination = col1.text_input(
    "目的地",
    placeholder="例如：京都、巴黎、成都",
  )
  days = col2.number_input("天数", min_value=1, max_value=21, value=3, step=1)
  theme = col3.selectbox(
    "旅行风格",
    options=["人文历史", "自然风光", "美食探索", "城市漫步"],
    index=0,
  )
  extra_note = st.text_input(
    "补充需求（可选）",
    placeholder="例如：预算中等、偏爱安静、有小孩同行",
  )
  form_submitted = st.form_submit_button("✨ 生成规划", use_container_width=True)

if form_submitted:
  if not destination.strip():
    st.warning("请先填写目的地。")
  else:
    with st.spinner("正在生成行程规划…"):
      plan = generate_trip_plan(
        query=extra_note.strip(),
        destination=destination.strip(),
        days=int(days),
        theme=theme,
      )
    st.session_state["last_trip_plan"] = plan
    st.session_state["last_trip_destination"] = destination.strip()
    src = plan.get("source", "template")
    if src == "llm":
      st.success("✅ 已由 AI 生成个性化行程。")
    else:
      st.success("✅ 已生成行程建议（模板模式，配置 LLM 后可获得更个性化规划）。")

plan_data = st.session_state.get("last_trip_plan")
if plan_data:
  st.markdown(plan_data.get("markdown", ""))

  dest_label = st.session_state.get("last_trip_destination", "")
  if st.button("💾 保存为我的行程", use_container_width=False):
    title = f"{dest_label}·{int(days)}天·{theme} — {datetime.now().strftime('%Y-%m-%d')}"
    plan_id = save_trip_plan(
      st.session_state["user_id"],
      title,
      f"{dest_label} {int(days)}天 {theme} {extra_note}".strip(),
      plan_data,
    )
    st.session_state["last_plan_id"] = plan_id
    st.success(f"已保存：{title}")

st.divider()
st.subheader("我的行程列表")
plans = list_trip_plans(st.session_state["user_id"], limit=20)
if not plans:
  st.info("暂无已保存行程。")
else:
  users = [u for u in list_users() if u["user_id"] != st.session_state["user_id"]]
  user_options = {u["display_name"]: u["user_id"] for u in users}

  for p in plans:
    label = f"{p['title']} | {p['created_at'][:16].replace('T', ' ')}"
    with st.expander(label, expanded=False):
      st.markdown(p.get("plan_markdown", ""))
      if user_options:
        c1, c2 = st.columns([2, 1])
        target_label = c1.selectbox(
          "共享给",
          options=list(user_options.keys()),
          key=f"share_target_{p['id']}",
          label_visibility="collapsed",
        )
        if c2.button("共享行程", key=f"share_plan_{p['id']}", use_container_width=True):
          share_trip_plan(
            plan_id=str(p["id"]),
            from_user=st.session_state["user_id"],
            to_user=user_options[target_label],
            message="一起看看这个行程，欢迎修改。",
          )
          st.success(f"已共享给 {target_label}。")
