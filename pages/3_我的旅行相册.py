from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from src.config import DEFAULT_USER_ID
from src.db import init_db
from src.services.spot_service import delete_spot, filter_spots, list_spots, semantic_filter_spots


def _spot_time_raw(spot: dict[str, Any]) -> str:
  return str(spot.get("travel_at") or spot.get("created_at") or "")


def _spot_year(spot: dict[str, Any]) -> str:
  raw = _spot_time_raw(spot)
  try:
    return str(datetime.fromisoformat(raw.replace("Z", "+00:00")).year)
  except ValueError:
    return "未知年份"


def _location_key(spot: dict[str, Any]) -> str:
  place_name = str(spot.get("place_name", "")).strip().lower()
  country = str(spot.get("country", "")).strip().lower()
  admin1 = str(spot.get("admin1", "")).strip().lower()
  city = str(spot.get("city", "")).strip().lower()
  district = str(spot.get("district", "")).strip().lower()
  return "|".join([place_name, country, admin1, city, district])


def _group_spots_by_location_and_year(spots: list[dict[str, Any]]) -> list[dict[str, Any]]:
  bucket: dict[str, dict[str, Any]] = {}

  for spot in spots:
    year = _spot_year(spot)
    location = _location_key(spot)
    group_key = f"{location}|{year}"
    when = _spot_time_raw(spot)

    if group_key not in bucket:
      bucket[group_key] = {
        "group_key": group_key,
        "year": year,
        "place_name": spot.get("place_name", "未命名地点"),
        "country": spot.get("country", ""),
        "admin1": spot.get("admin1", ""),
        "city": spot.get("city", ""),
        "district": spot.get("district", ""),
        "latest_time": when,
        "spot_ids": [],
        "photos": [],
        "notes": [],
        "tags": [],
      }

    current = bucket[group_key]
    current["spot_ids"].append(spot["id"])
    current["photos"].extend(spot.get("photos", []))
    if when > current["latest_time"]:
      current["latest_time"] = when

    note = str(spot.get("note", "")).strip()
    if note and note not in current["notes"]:
      current["notes"].append(note)

    for tag in spot.get("photo_tags", []):
      if tag not in current["tags"]:
        current["tags"].append(tag)

  grouped = list(bucket.values())
  grouped.sort(key=lambda item: item["latest_time"], reverse=True)
  return grouped


st.set_page_config(page_title="我的旅行相册", page_icon="📸", layout="wide")
init_db()

if "user_id" not in st.session_state:
  st.session_state["user_id"] = DEFAULT_USER_ID
if "album_expand_all" not in st.session_state:
  st.session_state["album_expand_all"] = False

st.title("📸 我的旅行相册")

all_spots = list_spots(st.session_state["user_id"])
all_years = sorted({_spot_year(item) for item in all_spots if _spot_year(item) != "未知年份"}, reverse=True)

col_search, col_sem, col_year, col_expand, col_refresh = st.columns([3.4, 2.8, 1.6, 1.6, 1.1])
keyword = col_search.text_input(
  "关键词检索",
  placeholder="按城市 / 区县 / 地点搜索",
  label_visibility="collapsed",
)
semantic_q = col_sem.text_input(
  "语义检索",
  placeholder="例如：海边、美食、博物馆、雪山",
  label_visibility="collapsed",
)
year_option = col_year.selectbox(
  "年份筛选",
  options=["全部年份", *all_years],
  index=0,
  label_visibility="collapsed",
)
if col_expand.button("全部展开/收起", use_container_width=True):
  st.session_state["album_expand_all"] = not st.session_state["album_expand_all"]
if col_refresh.button("刷新", use_container_width=True):
  st.rerun()

filtered = filter_spots(all_spots, keyword)
if semantic_q.strip():
  filtered = semantic_filter_spots(filtered, semantic_q)
if year_option != "全部年份":
  filtered = [item for item in filtered if _spot_year(item) == year_option]

grouped = _group_spots_by_location_and_year(filtered)
st.caption(f"匹配分组：{len(grouped)} 组（原始记录 {len(filtered)} 条）")

if not grouped:
  st.info("没有匹配记录。")

for group in grouped:
  location_parts = [str(group.get(k) or "") for k in ("country", "admin1", "city", "district")]
  location_text = " ".join(p for p in location_parts if p).strip()
  title = (
    f"{group['place_name']}（{group['year']}）"
    f" | {location_text}"
    f" | {group['latest_time']}"
    f" | {len(group['photos'])} 张照片"
  )
  with st.expander(title, expanded=st.session_state["album_expand_all"]):
    note_text = "；".join(group["notes"]) if group["notes"] else "暂无备注"
    st.write(note_text)

    if group["tags"]:
      st.caption("标签：" + "、".join(group["tags"]))

    if group["photos"]:
      cols = st.columns(4)
      for idx, photo in enumerate(group["photos"]):
        path = Path(photo["file_path"])
        if path.exists():
          cols[idx % 4].image(str(path), use_container_width=True)
          if photo.get("tags"):
            cols[idx % 4].caption("#" + " #".join([str(t) for t in photo.get("tags", [])]))

    if st.button("删除该分组全部记录", key=f"del_group_{group['group_key']}"):
      for spot_id in group["spot_ids"]:
        delete_spot(spot_id, st.session_state["user_id"])
      st.success("已删除该分组记录。")
      st.rerun()
