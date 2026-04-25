from __future__ import annotations

import time
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

from src.config import DEFAULT_USER_ID
from src.db import init_db
from src.services.spot_service import list_spots
from src.ui import build_amap_replay_html


PAGE_TITLE = "\u8f68\u8ff9\u56de\u653e"
TXT_MIN_TWO = "\u81f3\u5c11\u9700\u8981 2 \u4e2a\u5730\u70b9\u624d\u53ef\u4ee5\u56de\u653e\u3002"
TXT_ALL_YEARS = "\u5168\u90e8\u5e74\u4efd"
TXT_SELECT_YEAR = "\u9009\u62e9\u56de\u653e\u5e74\u4efd"
TXT_NOT_ENOUGH = "\u8be5\u5e74\u4efd\u53ef\u56de\u653e\u5730\u70b9\u4e0d\u8db3 2 \u4e2a\uff0c\u8bf7\u5207\u6362\u5e74\u4efd\u3002"
TXT_PLAY = "\u64ad\u653e"
TXT_PAUSE = "\u6682\u505c"
TXT_RESET = "\u91cd\u7f6e"
TXT_CURRENT = "\u5f53\u524d\u7ad9\u70b9\uff1a**{name}**"
TXT_CURRENT_TIME = "\u65f6\u95f4\uff1a{when}"
TXT_STEP = "\u7b2c {step}/{max_step} \u7ad9"
TXT_AUTO = "\u5df2\u6309\u65f6\u95f4\u987a\u5e8f\u81ea\u52a8\u56de\u653e\uff0c\u53ef\u968f\u65f6\u70b9\u51fb\u6682\u505c\u3002"
PIN_TEXT = "\U0001F4CD"
REPLAY_INTERVAL_SEC = 4.0


def get_spot_time(spot: dict) -> datetime:
  raw = spot.get("travel_at") or spot.get("created_at")
  if not raw:
    return datetime.min
  try:
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
  except ValueError:
    return datetime.min



def format_spot_time(spot: dict) -> str:
  raw = spot.get("travel_at") or spot.get("created_at") or ""
  try:
    dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    return dt.strftime("%Y-%m-%d %H:%M")
  except ValueError:
    return str(raw)


st.set_page_config(page_title=PAGE_TITLE, page_icon=":clapper:", layout="wide")
init_db()

if "user_id" not in st.session_state:
  st.session_state["user_id"] = DEFAULT_USER_ID
if "replay_playing" not in st.session_state:
  st.session_state["replay_playing"] = True
if "replay_step" not in st.session_state:
  st.session_state["replay_step"] = 1
if "replay_selected_year" not in st.session_state:
  st.session_state["replay_selected_year"] = TXT_ALL_YEARS

st.title(PAGE_TITLE)

spots = list_spots(st.session_state["user_id"])
if len(spots) < 2:
  st.info(TXT_MIN_TWO)
  st.stop()

years = sorted({get_spot_time(item).year for item in spots if get_spot_time(item) != datetime.min})
year_options = [TXT_ALL_YEARS] + [str(y) for y in years]
default_year = st.session_state["replay_selected_year"]
if default_year not in year_options:
  default_year = TXT_ALL_YEARS
selected_year = st.selectbox(TXT_SELECT_YEAR, options=year_options, index=year_options.index(default_year))

if selected_year != st.session_state["replay_selected_year"]:
  st.session_state["replay_selected_year"] = selected_year
  st.session_state["replay_step"] = 1
  st.session_state["replay_playing"] = True

if selected_year == TXT_ALL_YEARS:
  ordered = sorted(spots, key=get_spot_time)
else:
  ordered = [item for item in spots if str(get_spot_time(item).year) == selected_year]
  ordered.sort(key=get_spot_time)

if len(ordered) < 2:
  st.warning(TXT_NOT_ENOUGH)
  st.stop()

max_step = len(ordered)
if st.session_state["replay_step"] > max_step:
  st.session_state["replay_step"] = 1

col_play, col_pause, col_reset = st.columns([1.1, 1.1, 1.1])
if col_play.button(TXT_PLAY, use_container_width=True):
  st.session_state["replay_playing"] = True
if col_pause.button(TXT_PAUSE, use_container_width=True):
  st.session_state["replay_playing"] = False
if col_reset.button(TXT_RESET, use_container_width=True):
  st.session_state["replay_playing"] = False
  st.session_state["replay_step"] = 1

st.caption(TXT_AUTO)
step = int(st.session_state["replay_step"])

current = ordered[step - 1]
st.write(TXT_CURRENT.format(name=current["place_name"]))
st.caption(TXT_CURRENT_TIME.format(when=format_spot_time(current)))
_loc_parts = [p for p in [
    current.get("country", ""),
    current.get("admin1", ""),
    current.get("city", ""),
    current.get("district", ""),
] if p]
if _loc_parts:
    st.caption(" · ".join(_loc_parts))
if current.get("note"):
    st.caption(f"📝 {current['note']}")

components.html(build_amap_replay_html(current, height=420), height=420)
st.caption(TXT_STEP.format(step=step, max_step=max_step))

if st.session_state["replay_playing"]:
  if step < max_step:
    time.sleep(REPLAY_INTERVAL_SEC)
    st.session_state["replay_step"] = step + 1
    st.rerun()
  else:
    st.session_state["replay_playing"] = False
