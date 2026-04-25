from __future__ import annotations

import streamlit as st

from src.config import DEFAULT_USER_ID
from src.db import init_db
from src.services.match_service import create_invite, get_invites, rank_buddies
from src.services.spot_service import list_spots


st.set_page_config(page_title="找搭子", page_icon=":handshake:", layout="wide")
init_db()

if "user_id" not in st.session_state:
  st.session_state["user_id"] = DEFAULT_USER_ID

st.title("找搭子")
st.caption("按轨迹相似度排序")

with st.expander("📊 匹配分数说明", expanded=False):
  st.markdown(
    """
    **分数计算方式（0–100分）**

    | 维度 | 权重 | 说明 |
    |------|------|------|
    | 地理轨迹相似度 | 75% | 基于哈弗辛距离的地理接近程度 |
    | 国家/地区重叠 | 25% | 去过相同国家的 Jaccard 重叠率 |

    分数 ≥ 70 表示高度相似，推荐优先邀请。
    分数 40–69 表示有一定共同轨迹，可以尝试。
    """
  )

spots = list_spots(st.session_state["user_id"])
ranked = rank_buddies(spots)
sent_to = {row["to_user"] for row in get_invites(st.session_state["user_id"])}

for buddy in ranked:
  with st.container(border=True):
    c1, c2, c3 = st.columns([1, 5, 2])
    c1.markdown(f"### {buddy['avatar']}")
    c2.write(f"**{buddy['name']}**")
    c2.caption(f"综合相似度：{buddy['score']}%")

    already_sent = buddy["id"] in sent_to
    if c3.button(
      "已邀请" if already_sent else "发起邀请",
      key=f"invite_{buddy['id']}",
      disabled=already_sent,
      use_container_width=True,
    ):
      create_invite(st.session_state["user_id"], buddy["id"], buddy["score"])
      st.success(f"已向 {buddy['name']} 发起邀请。")
      st.rerun()

    bd = buddy.get("breakdown", {})
    with st.expander("查看分数明细", expanded=False):
      col_a, col_b, col_c = st.columns(3)
      col_a.metric("地理轨迹得分", f"{bd.get('geo_score', 0)} / 75")
      col_b.metric("国家重叠得分", f"{bd.get('country_score', 0)} / 25")
      col_c.metric("参与比对地点数", bd.get("spots_compared", 0))
      common = bd.get("common_countries", [])
      if common:
        st.caption(f"共同到访地区：{'、'.join(common)}")
      else:
        st.caption("暂无共同到访的国家/地区。")
