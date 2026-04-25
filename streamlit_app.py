from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from src.config import DEFAULT_USER_ID
from src.db import init_db
from src.services.spot_service import get_stats, list_spots
from src.ui import build_amap_html


st.set_page_config(page_title="旅行地图智能助手", page_icon=":world_map:", layout="wide")
init_db()

if "user_id" not in st.session_state:
    st.session_state["user_id"] = DEFAULT_USER_ID

st.title("旅行地图智能助手")
st.caption("MVP：地图相册 + 轨迹回放 + 找搭子 + 智能助手")

spots = list_spots(st.session_state["user_id"])
stats = get_stats(spots)

col1, col2, col3, col4 = st.columns(4)
col1.metric("地点", stats["locations"])
col2.metric("照片", stats["photos"])
col3.metric("国家/地区", stats["countries"])
col4.metric("总里程（km）", stats["distance_km"])

if not spots:
    st.info(
        "👋 **欢迎使用旅行地图智能助手！**\n\n"
        "当前还没有任何旅行记录。你可以：\n"
        "- 前往左侧「**添加地点**」手动创建第一条记录\n"
        "- 或者运行以下命令一键导入 **15 个演示地点**（含中国、日本、欧洲等地的实景照片和旅行记忆）：\n\n"
        "```bash\n"
        "python scripts/seed_demo.py\n"
        "```\n\n"
        "导入完成后刷新页面即可看到地图和数据。"
    )

st.subheader("地图总览")
amap_html = build_amap_html(spots, height=500)
if amap_html and spots:
    components.html(amap_html, height=500)
elif spots:
    st.info("地图加载中，请确认 .env 中已配置 AMAP_JS_KEY。")

st.subheader("最近记录")
if not spots:
    st.write("暂无数据。")
else:
    for item in spots[:5]:
        when = item.get("travel_at") or item.get("created_at")
        st.write(f"- **{item['place_name']}** | {item.get('country', '')} {item.get('city', '')} | {when}")
