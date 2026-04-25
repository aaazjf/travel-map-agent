from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.config import DEFAULT_USER_ID
from src.db import init_db
from src.services.report_service import (
  build_travel_report,
  export_report_markdown,
  export_report_pdf,
  list_report_files,
)
from src.services.spot_service import list_spots


st.set_page_config(page_title="旅行报告", page_icon=":page_facing_up:", layout="wide")
init_db()

if "user_id" not in st.session_state:
  st.session_state["user_id"] = DEFAULT_USER_ID

st.title("旅行报告一键生成")
st.caption("按年份/国家生成年度复盘，支持 Markdown 下载，PDF 为可选能力。")

spots = list_spots(st.session_state["user_id"])

# ── 辅助：从 spot 提取年份 / 国家 ──────────────────────────────────────────────
def _spot_year(s: dict) -> str:
  raw = str(s.get("travel_at") or s.get("created_at") or "")[:4]
  return raw if raw.isdigit() else ""

def _spot_country(s: dict) -> str:
  return str(s.get("country") or "").strip()

# ── 初始化联动 session state ───────────────────────────────────────────────────
if "report_year" not in st.session_state:
  st.session_state["report_year"] = "全部"
if "report_country" not in st.session_state:
  st.session_state["report_country"] = "全部"

cur_year = st.session_state["report_year"]
cur_country = st.session_state["report_country"]

# ── 联动计算可用选项 ───────────────────────────────────────────────────────────
# 可用年份：被当前已选国家过滤
year_pool = spots if cur_country == "全部" else [s for s in spots if _spot_country(s) == cur_country]
available_years = sorted({_spot_year(s) for s in year_pool if _spot_year(s)}, reverse=True)

# 可用国家：被当前已选年份过滤
country_pool = spots if cur_year == "全部" else [s for s in spots if _spot_year(s) == cur_year]
available_countries = sorted({_spot_country(s) for s in country_pool if _spot_country(s)})

# 若当前选项因另一维度变化而不再可用，重置为"全部"
if cur_year not in available_years:
  cur_year = "全部"
if cur_country not in available_countries:
  cur_country = "全部"

# ── 渲染联动选择器 ─────────────────────────────────────────────────────────────
year_options = ["全部", *available_years]
country_options = ["全部", *available_countries]

col_y, col_c, col_btn = st.columns([1.2, 1.8, 1], vertical_alignment="bottom")
year_val = col_y.selectbox(
  "年份",
  options=year_options,
  index=year_options.index(cur_year) if cur_year in year_options else 0,
)
country_val = col_c.selectbox(
  "国家/地区",
  options=country_options,
  index=country_options.index(cur_country) if cur_country in country_options else 0,
)

# 选项变化时保存并立即 rerun，让另一个下拉联动更新
if year_val != st.session_state["report_year"] or country_val != st.session_state["report_country"]:
  st.session_state["report_year"] = year_val
  st.session_state["report_country"] = country_val
  st.rerun()

# ── 生成报告 ──────────────────────────────────────────────────────────────────
if col_btn.button("生成报告", use_container_width=True):
  y = int(year_val) if year_val != "全部" and year_val.isdigit() else None
  c = "" if country_val == "全部" else country_val
  report = build_travel_report(st.session_state["user_id"], year=y, country=c)
  st.session_state["last_report_md"] = report.get("markdown", "")
  st.session_state["last_report_scope"] = {"year": y, "country": c}
  st.success("报告已生成。")

md_text = st.session_state.get("last_report_md", "")
if md_text:
  st.markdown(md_text)

  scope = st.session_state.get("last_report_scope", {})
  col_md, col_pdf = st.columns([1, 1])
  if col_md.button("导出 Markdown", use_container_width=True):
    p = export_report_markdown(
      user_id=st.session_state["user_id"],
      markdown_text=md_text,
      year=scope.get("year"),
      country=scope.get("country", ""),
    )
    st.session_state["last_report_path"] = p
    st.success(f"已导出：{p}")

  if col_pdf.button("导出 PDF", use_container_width=True):
    result = export_report_pdf(
      user_id=st.session_state["user_id"],
      markdown_text=md_text,
      year=scope.get("year"),
      country=scope.get("country", ""),
    )
    if result.get("ok"):
      st.session_state["last_report_pdf"] = result.get("file_path")
      st.success(f"已导出：{result.get('file_path')}")
    else:
      st.warning(str(result.get("reason", "导出失败")))

if st.session_state.get("last_report_path"):
  md_path = Path(str(st.session_state["last_report_path"]))
  if md_path.exists():
    st.download_button(
      "下载最新 Markdown",
      data=md_path.read_bytes(),
      file_name=md_path.name,
      mime="text/markdown",
      use_container_width=False,
      key="download_report_md",
    )

if st.session_state.get("last_report_pdf"):
  pdf_path = Path(str(st.session_state["last_report_pdf"]))
  if pdf_path.exists():
    st.download_button(
      "下载最新 PDF",
      data=pdf_path.read_bytes(),
      file_name=pdf_path.name,
      mime="application/pdf",
      use_container_width=False,
      key="download_report_pdf",
    )

st.divider()
st.subheader("已导出文件")
files = list_report_files(limit=15)
if not files:
  st.caption("暂无导出文件。")
else:
  for f in files:
    st.caption(f"- {f['name']} ({f['size']} bytes)")
