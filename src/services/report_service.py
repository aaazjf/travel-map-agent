from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import DATA_DIR
from src.db import get_conn
from src.services.spot_service import list_spots


REPORT_DIR = DATA_DIR / "reports"


def _parse_dt(raw: str) -> datetime:
  try:
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
  except Exception:
    return datetime.min


def build_travel_report(user_id: str, year: int | None = None, country: str = "") -> dict[str, Any]:
  spots = list_spots(user_id)
  items = spots
  if year is not None:
    items = [s for s in items if _parse_dt(s.get("travel_at") or s.get("created_at")).year == year]
  if country.strip():
    key = country.strip().lower()
    items = [s for s in items if str(s.get("country", "")).strip().lower() == key]

  if not items:
    return {
      "markdown": "# 旅行报告\n\n当前筛选条件下暂无记录。",
      "stats": {"count": 0, "countries": 0, "cities": 0, "photos": 0},
    }

  ordered = sorted(items, key=lambda x: _parse_dt(x.get("travel_at") or x.get("created_at")))
  countries = sorted({str(s.get("country", "")).strip() for s in items if s.get("country")})
  cities = [str(s.get("city", "")).strip() for s in items if s.get("city")]
  city_counter = Counter([c for c in cities if c])
  top_city = city_counter.most_common(3)
  photo_count = sum(len(s.get("photos", [])) for s in items)

  title_scope = f"{year} 年" if year else "全时段"
  if country.strip():
    title_scope += f" · {country.strip()}"

  lines = [
    f"# 旅行年度复盘（{title_scope}）",
    "",
    "## 总览",
    f"- 地点记录：{len(items)}",
    f"- 覆盖国家/地区：{len(countries)}",
    f"- 覆盖城市：{len(set(cities))}",
    f"- 照片总数：{photo_count}",
    "",
    "## 热门地点/城市",
  ]
  if top_city:
    for city, cnt in top_city:
      lines.append(f"- {city}: {cnt} 次")
  else:
    lines.append("- 暂无城市统计")

  lines.extend(["", "## 时间线（证据点）"])
  for i, s in enumerate(ordered, start=1):
    when = s.get("travel_at") or s.get("created_at")
    note = str(s.get("note", "")).strip() or "无备注"
    lines.append(
      f"{i}. {s.get('place_name', '')} | {s.get('country', '')}/{s.get('city', '')}/{s.get('district', '')} | {when} | 备注：{note}"
    )

  lines.extend(["", "## 结论", "- 推荐按“自然/人文/美食”给未来行程做分主题规划。", "- 可优先复访高频城市并补齐周边目的地。"])

  return {
    "markdown": "\n".join(lines),
    "stats": {
      "count": len(items),
      "countries": len(countries),
      "cities": len(set(cities)),
      "photos": photo_count,
    },
  }


def export_report_markdown(user_id: str, markdown_text: str, year: int | None = None, country: str = "") -> str:
  REPORT_DIR.mkdir(parents=True, exist_ok=True)
  date_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  scope = (country.strip() or "all").replace(" ", "_")
  year_tag = str(year) if year else "all"
  path = REPORT_DIR / f"travel_report_{user_id}_{year_tag}_{scope}_{date_tag}.md"
  path.write_text(markdown_text, encoding="utf-8")
  return str(path)


def export_report_pdf(user_id: str, markdown_text: str, year: int | None = None, country: str = "") -> dict[str, Any]:
  try:
    from reportlab.lib.pagesizes import A4  # type: ignore
    from reportlab.pdfbase import pdfmetrics  # type: ignore
    from reportlab.pdfbase.ttfonts import TTFont  # type: ignore
    from reportlab.pdfgen import canvas  # type: ignore
  except Exception:
    return {"ok": False, "reason": "reportlab 未安装，请先安装 reportlab。"}

  REPORT_DIR.mkdir(parents=True, exist_ok=True)
  date_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  scope = (country.strip() or "all").replace(" ", "_")
  year_tag = str(year) if year else "all"
  path = REPORT_DIR / f"travel_report_{user_id}_{year_tag}_{scope}_{date_tag}.pdf"

  # Try common Windows Chinese font; fallback to Helvetica.
  font_name = "Helvetica"
  try:
    simsun = Path("C:/Windows/Fonts/simsun.ttc")
    if simsun.exists():
      pdfmetrics.registerFont(TTFont("SimSun", str(simsun)))
      font_name = "SimSun"
  except Exception:
    pass

  c = canvas.Canvas(str(path), pagesize=A4)
  width, height = A4
  c.setFont(font_name, 11)
  y = height - 40
  for raw in markdown_text.splitlines():
    line = raw.replace("\t", "    ")
    if not line:
      y -= 14
    else:
      c.drawString(32, y, line[:90])
      y -= 16
    if y < 45:
      c.showPage()
      c.setFont(font_name, 11)
      y = height - 40
  c.save()
  return {"ok": True, "file_path": str(path)}


def list_report_files(limit: int = 30) -> list[dict[str, Any]]:
  REPORT_DIR.mkdir(parents=True, exist_ok=True)
  files = sorted(REPORT_DIR.glob("travel_report_*"), key=lambda p: p.stat().st_mtime, reverse=True)
  result: list[dict[str, Any]] = []
  for p in files[:limit]:
    result.append({"name": p.name, "path": str(p), "size": p.stat().st_size})
  return result
