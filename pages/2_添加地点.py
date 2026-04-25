from __future__ import annotations

from datetime import datetime

import streamlit as st

from src.config import DEFAULT_USER_ID
from src.db import init_db
from src.services.geo_service import search_places
from src.services.spot_service import add_spot


# ─── 辅助函数（必须在调用之前定义） ──────────────────────────────────────────────

def _fill_form(state: dict, poi: dict) -> None:
    state["place_name"] = poi.get("place_name", "") or str(poi.get("display_name", "")).split("，")[0].strip()
    state["lat"] = float(poi.get("lat", state["lat"]))
    state["lng"] = float(poi.get("lng", poi.get("lon", state["lng"])))
    state["country"] = poi.get("country", "")
    state["admin1"] = poi.get("province", "")
    state["city"] = poi.get("city", "")
    state["district"] = poi.get("district", "")
    # 国际城市兜底：从 address 子 dict 补全
    if not state["country"]:
        addr = poi.get("address", {})
        state["country"] = addr.get("country", "")
        state["admin1"] = addr.get("state", "") or addr.get("province", "")
        state["city"] = addr.get("city", "") or addr.get("town", "") or addr.get("village", "")
        state["district"] = addr.get("county", "") or addr.get("city_district", "")


def _poi_label(poi: dict, idx: int) -> str:
    name = poi.get("place_name", "") or str(poi.get("display_name", "")).split("，")[0]
    city = poi.get("city", "")
    district = poi.get("district", "")
    addr = poi.get("address", "") if isinstance(poi.get("address"), str) else ""
    parts = [p for p in [city, district, addr] if p]
    detail = " · ".join(parts[:2]) if parts else poi.get("display_name", "")
    return f"{'①②③④⑤'[idx]}  {name}   {detail}"


def _parse_default_datetime(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return datetime.now()


# ─── 页面初始化 ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="添加地点", page_icon=":pushpin:", layout="wide")
init_db()

if "user_id" not in st.session_state:
    st.session_state["user_id"] = DEFAULT_USER_ID

if "add_form" not in st.session_state:
    st.session_state["add_form"] = {
        "place_name": "",
        "country": "",
        "admin1": "",
        "city": "",
        "district": "",
        "lat": 39.9042,
        "lng": 116.4074,
        "travel_at": datetime.now().isoformat(timespec="minutes"),
        "note": "",
    }

if "poi_results" not in st.session_state:
    st.session_state["poi_results"] = []

form_state = st.session_state["add_form"]
st.title("添加旅行地点")

# ─── 地点搜索 ─────────────────────────────────────────────────────────────────
with st.container(border=True):
    st.subheader("地点搜索")
    with st.form("search_place_form", clear_on_submit=False):
        col_q, col_btn = st.columns([5, 1.4])
        search_query = col_q.text_input(
            "关键词",
            placeholder="例如：抚州、八达岭长城、Paris（回车或点搜索）",
            label_visibility="collapsed",
        )
        search_submitted = col_btn.form_submit_button("搜索", use_container_width=True)

    if search_submitted and search_query.strip():
        with st.spinner("正在搜索…"):
            try:
                results = search_places(search_query.strip(), limit=5)
                if not results:
                    st.warning("未找到匹配地点，可尝试英文名或补充省份。")
                    st.session_state["poi_results"] = []
                else:
                    st.session_state["poi_results"] = results
                    _fill_form(form_state, results[0])
                    st.success(f"找到 {len(results)} 条结果，已自动填入第一条，可在下方选择其他。")
            except Exception as exc:
                err_msg = str(exc)
                if "timed out" in err_msg.lower():
                    st.error("搜索超时，请稍后重试，或直接手动填写坐标。")
                elif "AMAP_API_KEY" in err_msg:
                    st.error(
                        "高德 REST API Key 未配置。\n\n"
                        "请在高德控制台创建一个**Web服务**类型的应用，"
                        "将 Key 填入 .env 的 `AMAP_API_KEY`（与 JS API 的 `AMAP_JS_KEY` 是两个不同 Key）。"
                    )
                else:
                    st.error(f"搜索失败：{exc}")

    # POI 结果列表（多条时显示）
    poi_results = st.session_state.get("poi_results", [])
    if len(poi_results) > 1:
        st.markdown("**选择正确地点：**")
        for i, poi in enumerate(poi_results):
            label = _poi_label(poi, i)
            if st.button(label, key=f"poi_pick_{i}", use_container_width=True):
                _fill_form(form_state, poi)
                st.success(f"已选择：{poi.get('place_name', poi.get('display_name', ''))}")
                st.rerun()


# ─── 地点表单 ─────────────────────────────────────────────────────────────────
default_dt = _parse_default_datetime(form_state["travel_at"])

with st.form("add_spot_form"):
    col1, col2 = st.columns(2)
    place_name = col1.text_input("地点名称", value=form_state["place_name"])

    col_date, col_time = col2.columns([1, 1])
    travel_date = col_date.date_input("旅行日期", value=default_dt.date())
    travel_time = col_time.time_input("旅行时间", value=default_dt.time().replace(second=0, microsecond=0))

    col3, col4 = st.columns(2)
    lat = col3.number_input("纬度", value=float(form_state["lat"]), format="%.6f")
    lng = col4.number_input("经度", value=float(form_state["lng"]), format="%.6f")

    col5, col6 = st.columns(2)
    country = col5.text_input("国家/地区", value=form_state["country"])
    admin1 = col6.text_input("省/州", value=form_state["admin1"])

    col7, col8 = st.columns(2)
    city = col7.text_input("城市", value=form_state["city"])
    district = col8.text_input("区/县", value=form_state["district"])

    note = st.text_area("旅行备注", value=form_state["note"], height=90)
    uploaded_files = st.file_uploader(
        "上传照片（可多选）",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
    )

    submitted = st.form_submit_button("保存地点")

if submitted:
    if not place_name.strip():
        st.error("地点名称不能为空。")
    elif not uploaded_files:
        st.error("请至少上传一张照片。")
    else:
        travel_dt = datetime.combine(travel_date, travel_time).replace(second=0, microsecond=0)
        photos = [(file.name, file.getvalue()) for file in uploaded_files]
        result = add_spot(
            user_id=st.session_state["user_id"],
            place_name=place_name,
            country=country,
            admin1=admin1,
            city=city,
            district=district,
            lat=float(lat),
            lng=float(lng),
            travel_at=travel_dt.isoformat(),
            note=note,
            photos=photos,
        )
        if result.get("merged"):
            st.success(f"已合并到同地点同年份记录，并新增 {result.get('added_photo_count', 0)} 张照片。")
        else:
            st.success('保存成功，可到"我的旅行相册"查看。')
        st.session_state["poi_results"] = []
