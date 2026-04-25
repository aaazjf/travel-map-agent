from __future__ import annotations

import json
import urllib.parse
from typing import Any

from src.config import AMAP_JS_KEY, AMAP_SECURITY_CODE


# ─── 高德地图：地图总览（Streamlit 主页）────────────────────────────────────────

def build_amap_html(spots: list[dict[str, Any]], height: int = 500) -> str | None:
    if not spots:
        return None

    spots_data = [
        {
            "lng": float(s["lng"]),
            "lat": float(s["lat"]),
            "placeName": s.get("place_name", ""),
            "country": s.get("country", ""),
            "city": s.get("city", ""),
            "travelAt": s.get("travel_at") or s.get("created_at") or "",
        }
        for s in spots
    ]
    spots_json = json.dumps(spots_data, ensure_ascii=False)
    security_script = (
        f'<script>window._AMapSecurityConfig = {{ securityJsCode: "{AMAP_SECURITY_CODE}" }};</script>'
        if AMAP_SECURITY_CODE else ""
    )

    if not AMAP_JS_KEY:
        return (
            "<div style='padding:1rem;color:#888;font-family:sans-serif'>"
            "AMAP_JS_KEY 未配置，请在 .env 中设置后重启服务。"
            "</div>"
        )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:100%; height:{height}px; overflow:hidden; }}
  #map {{ width:100%; height:{height}px; }}
  .popup-box {{ padding:6px 8px; font-family:"PingFang SC","Microsoft YaHei",sans-serif; font-size:13px; line-height:1.6; }}
  .popup-box b {{ font-size:14px; }}
  .popup-meta {{ color:#666; font-size:12px; }}
</style>
{security_script}
<script src="https://webapi.amap.com/maps?v=2.0&key={AMAP_JS_KEY}&plugin=AMap.MarkerCluster"></script>
</head>
<body>
<div id="map"></div>
<script>
(function () {{
  var spots = {spots_json};
  var map = new AMap.Map('map', {{ zoom: 3, center: [105, 20], resizeEnable: true }});
  var infoWindow = new AMap.InfoWindow({{ closeWhenClickMap: true, offset: new AMap.Pixel(0, -5) }});

  function popupHtml(s) {{
    var meta = [s.country, s.city].filter(Boolean).join(' / ');
    var date = s.travelAt ? s.travelAt.slice(0, 10) : '';
    return '<div class="popup-box"><b>' + (s.placeName || '未命名地点') + '</b>'
      + (meta ? '<div class="popup-meta">' + meta + '</div>' : '')
      + (date ? '<div class="popup-meta">' + date + '</div>' : '')
      + '</div>';
  }}

  function isInChina(s) {{
    return s.lng >= 73 && s.lng <= 136 && s.lat >= 3 && s.lat <= 54;
  }}

  if (spots.length) {{
    var chinaSpots = spots.filter(isInChina);
    var intlSpots = spots.filter(function(s) {{ return !isInChina(s); }});

    // 国内：聚合标记
    if (chinaSpots.length) {{
      new AMap.MarkerCluster(map, chinaSpots.map(function(s) {{ return {{ lnglat: [s.lng, s.lat], spot: s }}; }}), {{
        gridSize: 50,
        renderClusterMarker: function(ctx) {{
          ctx.marker.setContent('<div style="width:36px;height:36px;border-radius:50%;background:#0f8b8d;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.3)">' + ctx.count + '</div>');
          ctx.marker.setOffset(new AMap.Pixel(-18, -18));
        }},
        renderMarker: function(ctx) {{
          var s = ctx.data[0].spot;
          ctx.marker.on('click', function() {{
            infoWindow.setContent(popupHtml(s));
            infoWindow.open(map, ctx.marker.getPosition());
          }});
        }}
      }});
    }}

    // 国外：普通标记
    intlSpots.forEach(function(s) {{
      var m = new AMap.Marker({{ position: [s.lng, s.lat], title: s.placeName || '' }});
      m.on('click', function() {{
        infoWindow.setContent(popupHtml(s));
        infoWindow.open(map, m.getPosition());
      }});
      map.add(m);
    }});

    var lngs = spots.map(function(s) {{ return s.lng; }});
    var lats = spots.map(function(s) {{ return s.lat; }});
    if (spots.length === 1) {{
      map.setCenter([spots[0].lng, spots[0].lat]);
      map.setZoom(10);
    }} else {{
      map.setBounds(new AMap.Bounds(
        [Math.min.apply(null, lngs), Math.min.apply(null, lats)],
        [Math.max.apply(null, lngs), Math.max.apply(null, lats)]
      ), false, [40, 40, 40, 40]);
    }}
  }}
}})();
</script>
</body>
</html>"""


# ─── 高德地图：轨迹回放单站展示 ────────────────────────────────────────────────

def build_amap_replay_html(spot: dict[str, Any], height: int = 420) -> str:
    lng = float(spot["lng"])
    lat = float(spot["lat"])
    is_china = 73 <= lng <= 136 and 3 <= lat <= 54

    spot_data = {
        "lng": lng,
        "lat": lat,
        "placeName": spot.get("place_name", ""),
        "country": spot.get("country", ""),
        "admin1": spot.get("admin1", ""),
        "city": spot.get("city", ""),
        "district": spot.get("district", ""),
        "note": spot.get("note", ""),
    }
    spot_json = json.dumps(spot_data, ensure_ascii=False)

    if is_china:
        return _replay_amap(spot_json, height)
    return _replay_leaflet(spot_json, height)


def _replay_amap(spot_json: str, height: int) -> str:
    security_script = (
        f'<script>window._AMapSecurityConfig = {{ securityJsCode: "{AMAP_SECURITY_CODE}" }};</script>'
        if AMAP_SECURITY_CODE else ""
    )
    if not AMAP_JS_KEY:
        return "<div style='padding:1rem;color:#888'>AMAP_JS_KEY 未配置。</div>"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:100%; height:{height}px; overflow:hidden; }}
  #map {{ width:100%; height:{height}px; }}
  .iw {{ padding:6px 10px; font-family:sans-serif; max-width:260px; }}
  .iw-title {{ font-size:14px; font-weight:700; }}
  .iw-loc {{ color:#666; font-size:12px; margin-top:2px; }}
  .iw-note {{ font-size:12px; margin-top:5px; color:#333; line-height:1.5; }}
</style>
{security_script}
<script src="https://webapi.amap.com/maps?v=2.0&key={AMAP_JS_KEY}"></script>
</head>
<body>
<div id="map"></div>
<script>
(function () {{
  var s = {spot_json};
  var map = new AMap.Map('map', {{ zoom: 13, center: [s.lng, s.lat], resizeEnable: true }});
  var marker = new AMap.Marker({{ position: [s.lng, s.lat], title: s.placeName, animation: 'AMAP_ANIMATION_DROP' }});
  map.add(marker);
  var locParts = [s.country, s.admin1, s.city, s.district].filter(Boolean);
  var iw = document.createElement('div');
  iw.className = 'iw';
  iw.innerHTML = '<div class="iw-title">' + (s.placeName || '未命名') + '</div>'
    + (locParts.length ? '<div class="iw-loc">' + locParts.join(' / ') + '</div>' : '')
    + (s.note ? '<div class="iw-note">' + s.note + '</div>' : '');
  var infoWindow = new AMap.InfoWindow({{ content: iw, offset: new AMap.Pixel(0, -30) }});
  infoWindow.open(map, [s.lng, s.lat]);
}})();
</script>
</body>
</html>"""


def _replay_leaflet(spot_json: str, height: int) -> str:
    """国际地点：Leaflet + ESRI World Street Map（全球有图块，CDN 可访问）"""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.min.css"/>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:100%; height:{height}px; overflow:hidden; }}
  #map {{ width:100%; height:{height}px; }}
  .iw-title {{ font-size:14px; font-weight:700; }}
  .iw-loc {{ color:#666; font-size:12px; margin-top:3px; }}
  .iw-note {{ font-size:12px; margin-top:5px; color:#333; line-height:1.5; max-width:220px; }}
</style>
</head>
<body>
<div id="map"></div>
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.min.js"></script>
<script>
(function () {{
  var s = {spot_json};
  var map = L.map('map', {{ zoomControl: true }}).setView([s.lat, s.lng], 13);
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    attribution: 'Tiles &copy; Esri',
    maxZoom: 18
  }}).addTo(map);
  var locParts = [s.country, s.admin1, s.city, s.district].filter(Boolean);
  var popup = '<div style="font-family:sans-serif;padding:2px 4px">'
    + '<div class="iw-title">' + (s.placeName || '') + '</div>'
    + (locParts.length ? '<div class="iw-loc">' + locParts.join(' / ') + '</div>' : '')
    + (s.note ? '<div class="iw-note">' + s.note + '</div>' : '')
    + '</div>';
  L.marker([s.lat, s.lng]).addTo(map).bindPopup(popup, {{ maxWidth: 260 }}).openPopup();
}})();
</script>
</body>
</html>"""


# ─── 兼容旧接口（供 pydeck SVG 图标使用，如有其他页面引用） ────────────────────

def pin_icon_data(color: str = "#e74c3c") -> dict[str, Any]:
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 64 64'>
  <path d='M32 2C20.7 2 11.5 11.1 11.5 22.4c0 14.8 18.2 35.5 19 36.4a2 2 0 0 0 3 0c0.8-0.9 19-21.6 19-36.4C52.5 11.1 43.3 2 32 2z' fill='{color}'/>
  <circle cx='32' cy='22' r='9.5' fill='white' fill-opacity='0.96'/>
</svg>""".strip()
    return {
        "url": f"data:image/svg+xml;charset=utf-8,{urllib.parse.quote(svg)}",
        "width": 64,
        "height": 64,
        "anchorY": 64,
    }
