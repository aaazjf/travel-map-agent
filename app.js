// ─── 常量 ─────────────────────────────────────────────────────────────────────
const DB_NAME = "map-album-db";
const DB_VERSION = 1;
const STORE_NAME = "spots";

// ─── 全局变量 ──────────────────────────────────────────────────────────────────
let db;
let map;
let markersLayer = null;    // AMap.MarkerCluster（国内）
let intlMarkers = [];       // AMap.Marker[]（国外）
let heatLayer = null;       // AMap.HeatMap
let infoWindow = null;      // AMap.InfoWindow（共享单例）
let currentSatLayers = null; // [Satellite, RoadNet] 卫星图层

// 轨迹回放状态
const journey = {
  active: false,
  paused: false,
  spots: [],
  step: 0,
  speed: 1,
  timeoutId: null,
  polylineFull: null,
  polylineDrawn: null,
};

// 灯箱状态
const lb = { spot: null, idx: 0 };

// 应用状态
const state = {
  spots: [],
  markerMap: new Map(),
  search: "",
  heatActive: false,
  expandedSpotIds: new Set(),
  albumCollapsed: false,
  buddyCollapsed: false,
};

const buddyCandidates = [
  {
    id: "u_alina",
    name: "Alina",
    avatarText: "A",
    avatarColor: "#ff7f50",
    tracks: [
      { lat: 39.9042, lng: 116.4074, country: "中国" },
      { lat: 35.6762, lng: 139.6503, country: "日本" },
      { lat: 1.3521, lng: 103.8198, country: "新加坡" },
      { lat: 51.5074, lng: -0.1278, country: "英国" },
    ],
  },
  {
    id: "u_brian",
    name: "Brian",
    avatarText: "B",
    avatarColor: "#5b8def",
    tracks: [
      { lat: 22.3193, lng: 114.1694, country: "中国" },
      { lat: 13.7563, lng: 100.5018, country: "泰国" },
      { lat: 48.8566, lng: 2.3522, country: "法国" },
      { lat: 41.9028, lng: 12.4964, country: "意大利" },
    ],
  },
  {
    id: "u_coco",
    name: "Coco",
    avatarText: "C",
    avatarColor: "#39b980",
    tracks: [
      { lat: 31.2304, lng: 121.4737, country: "中国" },
      { lat: 37.5665, lng: 126.978, country: "韩国" },
      { lat: 25.033, lng: 121.5654, country: "中国" },
      { lat: 34.6937, lng: 135.5023, country: "日本" },
    ],
  },
  {
    id: "u_david",
    name: "David",
    avatarText: "D",
    avatarColor: "#b57bd6",
    tracks: [
      { lat: 40.7128, lng: -74.006, country: "美国" },
      { lat: 34.0522, lng: -118.2437, country: "美国" },
      { lat: 49.2827, lng: -123.1207, country: "加拿大" },
      { lat: -33.8688, lng: 151.2093, country: "澳大利亚" },
    ],
  },
];

// ─── DOM 引用 ──────────────────────────────────────────────────────────────────
const form = document.getElementById("spot-form");
const latInput = document.getElementById("lat");
const lngInput = document.getElementById("lng");
const placeNameInput = document.getElementById("placeName");
const countryInput = document.getElementById("country");
const admin1Input = document.getElementById("admin1");
const cityInput = document.getElementById("city");
const districtInput = document.getElementById("district");
const noteInput = document.getElementById("note");
const travelAtInput = document.getElementById("travelAt");
const photosInput = document.getElementById("photos");
const clearFormBtn = document.getElementById("clear-form-btn");
const fitAllBtn = document.getElementById("fit-all-btn");
const albumList = document.getElementById("album-list");
const albumContent = document.getElementById("album-content");
const albumCollapseBtn = document.getElementById("album-collapse-btn");
const buddyContent = document.getElementById("buddy-content");
const buddyCollapseBtn = document.getElementById("buddy-collapse-btn");
const buddyList = document.getElementById("buddy-list");
const cardTemplate = document.getElementById("photo-card-template");
const searchInput = document.getElementById("search-input");
const statsLocations = document.getElementById("stats-locations");
const statsPhotos = document.getElementById("stats-photos");
const statsCountries = document.getElementById("stats-countries");
const statsDistance = document.getElementById("stats-distance");
const placeSearchInput = document.getElementById("place-search-input");
const placeSearchBtn = document.getElementById("place-search-btn");
const basemapSelect = document.getElementById("basemap-select");
const searchTip = document.getElementById("search-tip");
const heatmapBtn = document.getElementById("heatmap-btn");
const journeyBtn = document.getElementById("journey-btn");
const randomBtn = document.getElementById("random-btn");
const journeyPanel = document.getElementById("journey-panel");
const journeyLabel = document.getElementById("journey-label");
const journeyProgress = document.getElementById("journey-progress");
const journeyPauseBtn = document.getElementById("journey-pause-btn");
const journeyStopBtn = document.getElementById("journey-stop-btn");
const journeySpeedInput = document.getElementById("journey-speed");
const journeySpeedVal = document.getElementById("journey-speed-val");
const exportBtn = document.getElementById("export-btn");
const importInput = document.getElementById("import-input");
const lightboxOverlay = document.getElementById("lightbox-overlay");
const lightboxImg = document.getElementById("lightbox-img");
const lightboxCaption = document.getElementById("lightbox-caption");
const lightboxClose = document.getElementById("lightbox-close");
const lightboxPrev = document.getElementById("lightbox-prev");
const lightboxNext = document.getElementById("lightbox-next");

// ─── 启动 ──────────────────────────────────────────────────────────────────────
boot().catch((err) => {
  console.error("Init failed:", err);
  alert("初始化失败，请刷新页面重试。");
});

async function boot() {
  await loadAmapSdk();
  db = await openDb();
  initMap();
  bindEvents();
  await loadSpots();
  renderAll();
}

async function loadAmapSdk() {
  const res = await fetch("/api/amap-config");
  if (!res.ok) throw new Error("无法获取地图配置，请确认服务已启动。");
  const { amapKey, securityCode } = await res.json();
  if (!amapKey) throw new Error("AMAP_JS_KEY 未配置，请检查 .env 文件。");

  if (securityCode) {
    window._AMapSecurityConfig = { securityJsCode: securityCode };
  }

  await new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${amapKey}&plugin=AMap.MarkerCluster,AMap.HeatMap,AMap.Geocoder,AMap.PlaceSearch,AMap.TileLayer`;
    script.onload = resolve;
    script.onerror = () => reject(new Error("高德地图 SDK 加载失败，请检查网络或 Key 配置。"));
    document.head.appendChild(script);
  });
}

// ─── IndexedDB ─────────────────────────────────────────────────────────────────
function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onerror = () => reject(req.error);
    req.onsuccess = () => resolve(req.result);
    req.onupgradeneeded = () => {
      const d = req.result;
      if (!d.objectStoreNames.contains(STORE_NAME)) {
        d.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
    };
  });
}

function txStore(mode = "readonly") {
  return db.transaction(STORE_NAME, mode).objectStore(STORE_NAME);
}

function listAllSpots() {
  return new Promise((resolve, reject) => {
    const req = txStore().getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

function putSpot(spot) {
  return new Promise((resolve, reject) => {
    const req = txStore("readwrite").put(spot);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

function deleteSpot(id) {
  return new Promise((resolve, reject) => {
    const req = txStore("readwrite").delete(id);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

// ─── 地图初始化 ────────────────────────────────────────────────────────────────
function initMap() {
  map = new AMap.Map("map", {
    zoom: 3,
    center: [105, 20],
    resizeEnable: true,
  });

  infoWindow = new AMap.InfoWindow({
    offset: new AMap.Pixel(0, -5),
    closeWhenClickMap: true,
  });

  map.on("click", async (e) => {
    const lng = e.lnglat.getLng();
    const lat = e.lnglat.getLat();
    await locateAndFill(lat, lng, false);
  });
}

function switchBaseLayer(mode) {
  if (currentSatLayers) {
    map.remove(currentSatLayers);
    currentSatLayers = null;
  }
  if (mode === "satellite") {
    currentSatLayers = [
      new AMap.TileLayer.Satellite(),
      new AMap.TileLayer.RoadNet(),
    ];
    map.add(currentSatLayers);
  }
  // "normal" 使用高德默认底图，无需额外图层
}

// ─── 事件绑定 ──────────────────────────────────────────────────────────────────
function bindEvents() {
  form.addEventListener("submit", onSubmitSpot);
  clearFormBtn.addEventListener("click", clearForm);
  fitAllBtn.addEventListener("click", fitAllSpots);
  searchInput.addEventListener("input", () => {
    state.search = searchInput.value.trim().toLowerCase();
    renderAlbumCards();
  });
  albumCollapseBtn.addEventListener("click", toggleAlbumCollapse);
  buddyCollapseBtn.addEventListener("click", toggleBuddyCollapse);
  buddyList.addEventListener("click", onBuddyInviteClick);

  placeSearchBtn.addEventListener("click", onSearchPlace);
  placeSearchInput.addEventListener("keydown", async (e) => {
    if (e.key === "Enter") { e.preventDefault(); await onSearchPlace(); }
  });
  basemapSelect.addEventListener("change", () => {
    switchBaseLayer(basemapSelect.value);
  });

  heatmapBtn.addEventListener("click", toggleHeatmap);
  journeyBtn.addEventListener("click", () => journey.active ? stopJourneyReplay() : startJourneyReplay());
  randomBtn.addEventListener("click", showRandomSpot);
  journeyPauseBtn.addEventListener("click", toggleJourneyPause);
  journeyStopBtn.addEventListener("click", stopJourneyReplay);
  journeySpeedInput.addEventListener("input", () => {
    journey.speed = Number(journeySpeedInput.value);
    journeySpeedVal.textContent = `${journey.speed}×`;
  });

  exportBtn.addEventListener("click", exportData);
  importInput.addEventListener("change", async (e) => {
    if (!e.target.files.length) return;
    try { await importData(e.target.files[0]); }
    catch (err) { alert(`导入失败：${err.message}`); }
    importInput.value = "";
  });

  document.addEventListener("keydown", (e) => {
    if (!lightboxOverlay.classList.contains("active")) return;
    if (e.key === "ArrowLeft") navigateLightbox(-1);
    else if (e.key === "ArrowRight") navigateLightbox(1);
    else if (e.key === "Escape") closeLightbox();
  });
  lightboxClose.addEventListener("click", closeLightbox);
  lightboxPrev.addEventListener("click", () => navigateLightbox(-1));
  lightboxNext.addEventListener("click", () => navigateLightbox(1));
  lightboxOverlay.addEventListener("click", (e) => {
    if (e.target === lightboxOverlay) closeLightbox();
  });
}

// ─── 数据加载 ──────────────────────────────────────────────────────────────────
async function loadSpots() {
  const spots = await listAllSpots();
  state.spots = spots.sort((a, b) => new Date(getSpotTime(a)) - new Date(getSpotTime(b))).reverse();
}

// ─── 地点搜索 ──────────────────────────────────────────────────────────────────
async function onSearchPlace() {
  const query = placeSearchInput.value.trim();
  if (!query) { setSearchTip("请输入要搜索的地名。", true); return; }
  placeSearchBtn.disabled = true;
  setSearchTip("正在搜索地点...");
  try {
    const result = await geocodeByName(query);
    if (!result) { setSearchTip("未找到该地点，请换个关键词试试。", true); return; }
    const lat = result.lat;
    const lng = result.lon;
    const fittedByBounds = fitMapToSearchBounds(result);
    await locateAndFill(lat, lng, !fittedByBounds, result);
    setSearchTip(`已定位到：${result.display_name || query}`);
  } catch (err) {
    console.error("Search place failed:", err);
    setSearchTip("搜索失败，请稍后重试。", true);
  } finally {
    placeSearchBtn.disabled = false;
  }
}

async function locateAndFill(lat, lng, flyToMap = false, forwardGeoResult = null) {
  latInput.value = lat.toFixed(6);
  lngInput.value = lng.toFixed(6);
  if (flyToMap) {
    const currentZoom = map.getZoom();
    map.setZoomAndCenter(Math.max(currentZoom, 11), [lng, lat]);
  }
  try {
    const reverse = await reverseGeocode(lat, lng);
    autofillAddress(reverse);
  } catch (err) {
    console.warn("reverseGeocode failed:", err);
    if (forwardGeoResult) autofillFromForward(forwardGeoResult);
  }
}

// ─── 保存地点 ──────────────────────────────────────────────────────────────────
async function onSubmitSpot(event) {
  event.preventDefault();
  if (!photosInput.files.length) { alert("请至少上传一张照片。"); return; }
  const lat = parseFloat(latInput.value);
  const lng = parseFloat(lngInput.value);
  if (isNaN(lat) || isNaN(lng)) { alert("请先点击地图或搜索一个有效地点。"); return; }

  const photos = await Promise.all(Array.from(photosInput.files).map(fileToDataUrl));
  const spot = {
    id: crypto.randomUUID(),
    lat,
    lng,
    placeName: placeNameInput.value.trim(),
    country: countryInput.value.trim(),
    admin1: admin1Input.value.trim(),
    city: cityInput.value.trim(),
    district: districtInput.value.trim(),
    note: noteInput.value.trim(),
    travelAt: travelAtInput.value ? new Date(travelAtInput.value).toISOString() : "",
    photos,
    createdAt: new Date().toISOString(),
  };

  await putSpot(spot);
  state.spots.unshift(spot);
  clearForm();
  renderAll();
}

// ─── 渲染 ──────────────────────────────────────────────────────────────────────
function renderAll() {
  renderMarkers();
  renderAlbumCards();
  renderBuddyList();
  renderStats();
  if (state.heatActive) refreshHeatmap();
}

function renderStats() {
  statsLocations.textContent = String(state.spots.length);
  statsPhotos.textContent = String(state.spots.reduce((s, sp) => s + sp.photos.length, 0));

  const countries = new Set(state.spots.map((s) => s.country).filter(Boolean));
  statsCountries.textContent = String(countries.size);

  const sorted = [...state.spots].sort((a, b) => new Date(getSpotTime(a)) - new Date(getSpotTime(b)));
  let totalKm = 0;
  for (let i = 1; i < sorted.length; i++) {
    totalKm += haversine(sorted[i - 1].lat, sorted[i - 1].lng, sorted[i].lat, sorted[i].lng);
  }
  if (totalKm >= 10000) {
    statsDistance.textContent = `${(totalKm / 1000).toFixed(0)}k`;
  } else if (totalKm >= 1000) {
    statsDistance.textContent = `${(totalKm / 1000).toFixed(1)}k`;
  } else {
    statsDistance.textContent = String(Math.round(totalKm));
  }
}

// AMap.MarkerCluster 只支持国内坐标，国外用普通 Marker
function isInChina(spot) {
  return spot.lng >= 73 && spot.lng <= 136 && spot.lat >= 3 && spot.lat <= 54;
}

function renderMarkers() {
  if (markersLayer) { markersLayer.setMap(null); markersLayer = null; }
  for (const m of intlMarkers) m.setMap(null);
  intlMarkers = [];
  state.markerMap.clear();

  if (!state.spots.length) return;

  const chinaSpots = state.spots.filter(isInChina);
  const intlSpots = state.spots.filter((s) => !isInChina(s));

  // 国内：聚合标记
  if (chinaSpots.length) {
    markersLayer = new AMap.MarkerCluster(
      map,
      chinaSpots.map((spot) => ({ lnglat: [spot.lng, spot.lat], spot })),
      {
        gridSize: 60,
        renderClusterMarker(context) {
          context.marker.setContent(`<div class="cluster-icon">${context.count}</div>`);
          context.marker.setOffset(new AMap.Pixel(-20, -20));
        },
        renderMarker(context) {
          const spot = context.data[0].spot;
          state.markerMap.set(spot.id, context.marker);
          context.marker.on("click", () => {
            infoWindow.setContent(buildPopupHtml(spot));
            infoWindow.open(map, context.marker.getPosition());
          });
        },
      }
    );
  }

  // 国外：普通标记（逐一 setMap，避免 map.add 数组方式的时序问题）
  for (const spot of intlSpots) {
    const marker = new AMap.Marker({ position: [spot.lng, spot.lat], title: spot.placeName || "" });
    marker.setMap(map);
    marker.on("click", () => {
      infoWindow.setContent(buildPopupHtml(spot));
      infoWindow.open(map, marker.getPosition());
    });
    state.markerMap.set(spot.id, marker);
    intlMarkers.push(marker);
  }
}

function buildPopupHtml(spot) {
  const pics = spot.photos
    .slice(0, 3)
    .map((src) => `<img src="${src}" alt="${escapeHtml(spot.placeName || "旅行照片")}" />`)
    .join("");
  const meta = [spot.country, spot.admin1, spot.city, spot.district].filter(Boolean).join(" / ");
  return `
    <div class="popup-title">${escapeHtml(spot.placeName || "未命名地点")}</div>
    <div class="popup-meta">${escapeHtml(meta || `${spot.lat.toFixed(4)}, ${spot.lng.toFixed(4)}`)}</div>
    <div class="popup-strip">${pics}</div>
  `;
}

function renderAlbumCards() {
  albumList.innerHTML = "";
  const filtered = getFilteredSpots();
  if (!filtered.length) {
    const empty = document.createElement("p");
    empty.className = "empty-tip";
    empty.textContent = state.spots.length
      ? "没有匹配结果，试试其他关键字。"
      : "还没有旅行记录，点击地图或搜索地名创建第一条吧。";
    albumList.appendChild(empty);
    return;
  }

  for (const spot of filtered) {
    const node = cardTemplate.content.cloneNode(true);
    const card = node.querySelector(".photo-card");
    const content = node.querySelector(".photo-content");
    node.querySelector(".photo-title").textContent = spot.placeName || "未命名地点";
    const meta = [spot.country, spot.admin1, spot.city, spot.district].filter(Boolean).join(" / ");
    const when = formatTime(getSpotTime(spot));
    node.querySelector(".photo-meta").textContent =
      `${meta || `${spot.lat.toFixed(4)}, ${spot.lng.toFixed(4)}`} · ${when}`;
    node.querySelector(".photo-note").textContent = spot.note || "暂无备注";

    const isExpanded = state.expandedSpotIds.has(spot.id);
    card.classList.toggle("collapsed", !isExpanded);
    content.addEventListener("click", (event) => {
      if (event.target.closest("button")) return;
      const currentlyExpanded = state.expandedSpotIds.has(spot.id);
      if (currentlyExpanded) {
        state.expandedSpotIds.delete(spot.id);
      } else {
        state.expandedSpotIds.add(spot.id);
      }
      renderAlbumCards();
    });

    const strip = node.querySelector(".photo-strip");
    spot.photos.slice(0, 5).forEach((src, i) => {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = src;
      img.alt = spot.placeName || "旅行照片";
      img.title = "点击查看大图";
      img.style.cursor = "pointer";
      img.addEventListener("click", () => openLightbox(spot, i));
      strip.appendChild(img);
    });

    node.querySelector(".focus-btn").addEventListener("click", () => focusSpot(spot.id));
    node.querySelector(".delete-btn").addEventListener("click", async () => {
      if (!confirm("确认删除这个地点和照片吗？")) return;
      await deleteSpot(spot.id);
      state.spots = state.spots.filter((item) => item.id !== spot.id);
      state.expandedSpotIds.delete(spot.id);
      renderAll();
    });

    albumList.appendChild(node);
  }
}

function focusSpot(id) {
  const spot = state.spots.find((s) => s.id === id);
  if (!spot) return;
  map.setZoomAndCenter(14, [spot.lng, spot.lat]);
  setTimeout(() => {
    infoWindow.setContent(buildPopupHtml(spot));
    infoWindow.open(map, [spot.lng, spot.lat]);
  }, 800);
}

function fitAllSpots() {
  if (!state.spots.length) {
    map.setZoomAndCenter(3, [105, 20]);
    return;
  }
  const lngs = state.spots.map((s) => s.lng);
  const lats = state.spots.map((s) => s.lat);
  const bounds = new AMap.Bounds(
    [Math.min(...lngs), Math.min(...lats)],
    [Math.max(...lngs), Math.max(...lats)]
  );
  map.setBounds(bounds, false, [40, 40, 40, 40]);
}

function getFilteredSpots() {
  if (!state.search) return state.spots;
  return state.spots.filter((spot) => {
    const text = [spot.placeName, spot.country, spot.admin1, spot.city, spot.district, spot.note]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return text.includes(state.search);
  });
}

function renderBuddyList() {
  buddyList.innerHTML = "";
  const ranked = rankBuddyCandidates(state.spots);
  if (!ranked.length) {
    const empty = document.createElement("p");
    empty.className = "empty-tip";
    empty.textContent = "暂无搭子候选。";
    buddyList.appendChild(empty);
    return;
  }

  for (const item of ranked) {
    const row = document.createElement("article");
    row.className = "buddy-row";

    const left = document.createElement("div");
    left.className = "buddy-left";

    const avatar = document.createElement("div");
    avatar.className = "buddy-avatar";
    avatar.style.background = item.avatarColor;
    avatar.textContent = item.avatarText;

    const meta = document.createElement("div");
    meta.className = "buddy-meta";

    const name = document.createElement("div");
    name.className = "buddy-name";
    name.textContent = item.name;

    const score = document.createElement("div");
    score.className = "buddy-score";
    score.textContent = state.spots.length
      ? `轨迹相似度 ${item.score}%`
      : "先添加地点后可计算相似度";

    meta.appendChild(name);
    meta.appendChild(score);
    left.appendChild(avatar);
    left.appendChild(meta);

    const inviteBtn = document.createElement("button");
    inviteBtn.type = "button";
    inviteBtn.className = "small";
    inviteBtn.textContent = "发起邀请";
    inviteBtn.dataset.userId = item.id;
    inviteBtn.dataset.userName = item.name;

    row.appendChild(left);
    row.appendChild(inviteBtn);
    buddyList.appendChild(row);
  }
}

function rankBuddyCandidates(userSpots) {
  return buddyCandidates
    .map((candidate) => ({
      ...candidate,
      score: calculateTrajectorySimilarity(userSpots, candidate.tracks),
    }))
    .sort((a, b) => b.score - a.score);
}

function calculateTrajectorySimilarity(userSpots, candidateTracks) {
  if (!userSpots.length || !candidateTracks.length) return 0;

  const userPoints = userSpots.map((s) => ({ lat: s.lat, lng: s.lng, country: s.country || "" }));
  const geoRaw = userPoints.reduce((sum, point) => {
    let nearest = Number.POSITIVE_INFINITY;
    for (const target of candidateTracks) {
      const km = haversine(point.lat, point.lng, target.lat, target.lng);
      if (km < nearest) nearest = km;
    }
    const normalized = Math.exp(-nearest / 2400);
    return sum + normalized;
  }, 0) / userPoints.length;

  const userCountrySet = new Set(userPoints.map((p) => normalizeCountry(p.country)).filter(Boolean));
  const candidateCountrySet = new Set(candidateTracks.map((p) => normalizeCountry(p.country)).filter(Boolean));
  const overlapCount = [...userCountrySet].filter((name) => candidateCountrySet.has(name)).length;
  const unionCount = new Set([...userCountrySet, ...candidateCountrySet]).size || 1;
  const countryRaw = overlapCount / unionCount;

  const sizeRaw = 1 - Math.min(Math.abs(userPoints.length - candidateTracks.length), 10) / 10;
  const scorePercent = geoRaw * 70 + countryRaw * 20 + sizeRaw * 10;
  const bounded = Math.max(0, Math.min(100, scorePercent));
  return Math.round(bounded);
}

function onBuddyInviteClick(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (!target.dataset.userId) return;

  const userName = target.dataset.userName || "该用户";
  target.textContent = "已邀请";
  target.setAttribute("disabled", "true");
  setSearchTip(`已向 ${userName} 发起邀请，等待对方响应。`);
}

function toggleAlbumCollapse() {
  state.albumCollapsed = !state.albumCollapsed;
  albumContent.classList.toggle("is-collapsed", state.albumCollapsed);
  albumCollapseBtn.textContent = state.albumCollapsed ? "展开" : "收起";
}

function toggleBuddyCollapse() {
  state.buddyCollapsed = !state.buddyCollapsed;
  buddyContent.classList.toggle("is-collapsed", state.buddyCollapsed);
  buddyCollapseBtn.textContent = state.buddyCollapsed ? "展开" : "收起";
}

// ─── 热力图 ────────────────────────────────────────────────────────────────────
function toggleHeatmap() {
  state.heatActive = !state.heatActive;
  heatmapBtn.classList.toggle("active", state.heatActive);
  heatmapBtn.textContent = state.heatActive ? "关闭热力图" : "热力图";

  if (state.heatActive) {
    if (markersLayer) markersLayer.setMap(null);
    for (const m of intlMarkers) m.setMap(null);
    refreshHeatmap();
  } else {
    if (heatLayer) heatLayer.hide();
    if (markersLayer) markersLayer.setMap(map);
    for (const m of intlMarkers) m.setMap(map);
  }
}

function refreshHeatmap() {
  if (!heatLayer) {
    heatLayer = new AMap.HeatMap(map, {
      radius: 40,
      opacity: [0, 0.8],
      gradient: { 0.2: "#89e5c8", 0.5: "#0f8b8d", 0.75: "#f5a623", 1.0: "#e23f3f" },
    });
  }
  heatLayer.setDataSet({
    data: state.spots.map((s) => ({
      lng: s.lng,
      lat: s.lat,
      count: Math.min(1 + s.photos.length, 5),
    })),
    max: 5,
  });
  heatLayer.show();
}

// ─── 轨迹回放 ──────────────────────────────────────────────────────────────────
function startJourneyReplay() {
  const sorted = [...state.spots].sort((a, b) => new Date(getSpotTime(a)) - new Date(getSpotTime(b)));
  if (sorted.length < 2) { alert("至少需要 2 个地点才能回放轨迹。"); return; }

  if (journey.polylineFull) { map.remove(journey.polylineFull); journey.polylineFull = null; }
  if (journey.polylineDrawn) { map.remove(journey.polylineDrawn); journey.polylineDrawn = null; }
  if (journey.timeoutId) { clearTimeout(journey.timeoutId); journey.timeoutId = null; }

  journey.active = true;
  journey.paused = false;
  journey.spots = sorted;
  journey.step = 0;
  journey.speed = Number(journeySpeedInput.value);

  const coords = sorted.map((s) => [s.lng, s.lat]);
  journey.polylineFull = new AMap.Polyline({
    path: coords,
    strokeColor: "#0f8b8d",
    strokeWeight: 2,
    strokeOpacity: 0.2,
    strokeStyle: "dashed",
    strokeDasharray: [6, 8],
    lineJoin: "round",
  });
  map.add(journey.polylineFull);

  journeyBtn.textContent = "■ 停止回放";
  journeyBtn.classList.remove("ghost");
  journeyBtn.classList.add("active");
  journeyPanel.classList.remove("hidden");
  journeyPauseBtn.textContent = "⏸ 暂停";

  const lngs = sorted.map((s) => s.lng);
  const lats = sorted.map((s) => s.lat);
  const bounds = new AMap.Bounds(
    [Math.min(...lngs), Math.min(...lats)],
    [Math.max(...lngs), Math.max(...lats)]
  );
  map.setBounds(bounds, false, [50, 50, 50, 50]);
  journey.timeoutId = setTimeout(runJourneyStep, 1000);
}

function runJourneyStep() {
  if (!journey.active || journey.paused) return;

  if (journey.step >= journey.spots.length) {
    finishJourneyReplay();
    return;
  }

  const spot = journey.spots[journey.step];
  const drawnCoords = journey.spots.slice(0, journey.step + 1).map((s) => [s.lng, s.lat]);

  if (journey.polylineDrawn) {
    journey.polylineDrawn.setPath(drawnCoords);
  } else {
    journey.polylineDrawn = new AMap.Polyline({
      path: drawnCoords,
      strokeColor: "#0f8b8d",
      strokeWeight: 3.5,
      strokeOpacity: 0.9,
      lineJoin: "round",
    });
    map.add(journey.polylineDrawn);
  }

  journeyLabel.textContent = spot.placeName || "未命名地点";
  journeyProgress.textContent = `第 ${journey.step + 1} / ${journey.spots.length} 站 · ${formatTime(getSpotTime(spot)).slice(0, 10)}`;

  const flyDur = Math.max(0.6, 1.5 / journey.speed);
  map.setZoomAndCenter(10, [spot.lng, spot.lat]);

  setTimeout(() => {
    if (!journey.active) return;
    infoWindow.setContent(buildPopupHtml(spot));
    infoWindow.open(map, [spot.lng, spot.lat]);
  }, flyDur * 1000 + 200);

  journey.step++;
  const stepDelay = flyDur * 1000 + 2200 / journey.speed;
  journey.timeoutId = setTimeout(runJourneyStep, stepDelay);
}

function toggleJourneyPause() {
  if (!journey.active) return;
  journey.paused = !journey.paused;
  journeyPauseBtn.textContent = journey.paused ? "▶ 继续" : "⏸ 暂停";
  if (!journey.paused) {
    journey.timeoutId = setTimeout(runJourneyStep, 300);
  }
}

function stopJourneyReplay() {
  journey.active = false;
  journey.paused = false;
  if (journey.timeoutId) { clearTimeout(journey.timeoutId); journey.timeoutId = null; }
  if (journey.polylineFull) { map.remove(journey.polylineFull); journey.polylineFull = null; }
  if (journey.polylineDrawn) { map.remove(journey.polylineDrawn); journey.polylineDrawn = null; }
  journeyBtn.textContent = "▶ 轨迹回放";
  journeyBtn.classList.add("ghost");
  journeyBtn.classList.remove("active");
  journeyPanel.classList.add("hidden");
  if (infoWindow) infoWindow.close();
}

function finishJourneyReplay() {
  journey.active = false;
  journeyLabel.textContent = "✓ 回放完成！";
  journeyProgress.textContent = `共 ${journey.spots.length} 站`;
  journeyBtn.textContent = "▶ 轨迹回放";
  journeyBtn.classList.add("ghost");
  journeyBtn.classList.remove("active");
  setTimeout(() => {
    if (!journey.active) {
      journeyPanel.classList.add("hidden");
      if (journey.polylineFull) { map.remove(journey.polylineFull); journey.polylineFull = null; }
    }
  }, 3000);
}

// ─── 随机记忆 ──────────────────────────────────────────────────────────────────
function showRandomSpot() {
  if (!state.spots.length) { setSearchTip("还没有旅行记录！", true); return; }
  const spot = state.spots[Math.floor(Math.random() * state.spots.length)];
  focusSpot(spot.id);
  setSearchTip(`随机记忆：${spot.placeName || "未命名地点"} · ${formatTime(getSpotTime(spot)).slice(0, 10)}`);
}

// ─── 照片灯箱 ──────────────────────────────────────────────────────────────────
function openLightbox(spot, idx) {
  lb.spot = spot;
  lb.idx = idx;
  renderLightbox();
  lightboxOverlay.classList.add("active");
  document.body.style.overflow = "hidden";
}

function renderLightbox() {
  lightboxImg.style.opacity = "0";
  lightboxImg.src = lb.spot.photos[lb.idx];
  lightboxImg.onload = () => { lightboxImg.style.opacity = "1"; };
  lightboxCaption.textContent =
    `${lb.spot.placeName || "未命名地点"}  ·  第 ${lb.idx + 1} / ${lb.spot.photos.length} 张`;
  lightboxPrev.style.visibility = lb.idx > 0 ? "visible" : "hidden";
  lightboxNext.style.visibility = lb.idx < lb.spot.photos.length - 1 ? "visible" : "hidden";
}

function navigateLightbox(dir) {
  const next = lb.idx + dir;
  if (next < 0 || next >= lb.spot.photos.length) return;
  lb.idx = next;
  renderLightbox();
}

function closeLightbox() {
  lightboxOverlay.classList.remove("active");
  document.body.style.overflow = "";
  lb.spot = null;
}

// ─── 导入 / 导出 ───────────────────────────────────────────────────────────────
function exportData() {
  if (!state.spots.length) { alert("暂无数据可导出。"); return; }
  const payload = {
    version: 1,
    exportedAt: new Date().toISOString(),
    spots: state.spots,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `旅行相册备份_${new Date().toLocaleDateString("zh-CN").replaceAll("/", "-")}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

async function importData(file) {
  const text = await file.text();
  let data;
  try { data = JSON.parse(text); } catch {
    throw new Error("文件解析失败，请确认是有效的 JSON 备份文件。");
  }
  const spots = Array.isArray(data) ? data : (data.spots || []);
  if (!spots.length) throw new Error("备份文件中没有找到旅行数据。");

  const existingIds = new Set(state.spots.map((s) => s.id));
  let imported = 0;
  for (const spot of spots) {
    if (!spot.id || existingIds.has(spot.id)) continue;
    if (typeof spot.lat !== "number" || typeof spot.lng !== "number") continue;
    await putSpot(spot);
    state.spots.push(spot);
    imported++;
  }
  state.spots.sort((a, b) => new Date(getSpotTime(a)) - new Date(getSpotTime(b)));
  state.spots.reverse();
  renderAll();
  alert(imported > 0 ? `成功导入 ${imported} 个地点！` : "没有新地点可导入（已全部存在）。");
}

// ─── 地理编码（高德优先，Nominatim 兜底国际）──────────────────────────────────
async function geocodeByName(query) {
  try {
    const amapResult = await _amapPlaceSearch(query);
    if (amapResult) return amapResult;
  } catch (e) {
    console.warn("AMap PlaceSearch failed:", e);
  }
  return _nominatimSearch(query);
}

function _amapPlaceSearch(query) {
  return new Promise((resolve) => {
    const ps = new AMap.PlaceSearch({ pageSize: 1 });
    ps.search(query, (status, result) => {
      if (status === "complete" && result.poiList && result.poiList.pois.length) {
        const poi = result.poiList.pois[0];
        resolve({
          lat: poi.location.lat,
          lon: poi.location.lng,
          display_name: poi.name + (poi.address ? `，${poi.address}` : ""),
          address: {
            country: "中国",
            state: poi.pname || "",
            city: poi.cityname || poi.pname || "",
            county: poi.adname || "",
          },
          boundingbox: null,
        });
      } else {
        resolve(null);
      }
    });
  });
}

async function _nominatimSearch(query) {
  const url = new URL("https://nominatim.openstreetmap.org/search");
  url.searchParams.set("q", query);
  url.searchParams.set("format", "jsonv2");
  url.searchParams.set("limit", "1");
  url.searchParams.set("accept-language", "zh-CN");
  const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  if (!Array.isArray(data) || !data.length) return null;
  const item = data[0];
  const addr = item.address || {};
  return {
    lat: parseFloat(item.lat),
    lon: parseFloat(item.lon),
    display_name: item.display_name,
    address: {
      country: addr.country || "",
      state: addr.state || addr.province || "",
      city: addr.city || addr.town || addr.village || "",
      county: addr.county || addr.city_district || "",
    },
    boundingbox: item.boundingbox,
  };
}

async function reverseGeocode(lat, lng) {
  // AMap.Geocoder 仅支持国内坐标；国外坐标传入后回调永远不触发，直接走 Nominatim
  if (!isInChina({ lat, lng })) {
    return _nominatimReverse(lat, lng);
  }
  return new Promise((resolve, reject) => {
    const geocoder = new AMap.Geocoder({ radius: 500 });
    geocoder.getAddress([lng, lat], (status, result) => {
      if (status === "complete" && result.regeocode) {
        const addr = result.regeocode.addressComponent;
        // city 在县级行政区可能是数组（空），取 province 兜底
        const city = Array.isArray(addr.city) ? (addr.province || "") : (addr.city || "");
        resolve({
          display_name: result.regeocode.formattedAddress || "",
          address: {
            country: "中国",
            state: addr.province || "",
            city,
            county: addr.district || "",
          },
        });
      } else {
        _nominatimReverse(lat, lng).then(resolve).catch(reject);
      }
    });
  });
}

async function _nominatimReverse(lat, lng) {
  const url = new URL("https://nominatim.openstreetmap.org/reverse");
  url.searchParams.set("format", "jsonv2");
  url.searchParams.set("lat", String(lat));
  url.searchParams.set("lon", String(lng));
  url.searchParams.set("accept-language", "zh-CN");
  const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  const addr = data.address || {};
  return {
    display_name: data.display_name || "",
    address: {
      country: addr.country || "",
      state: addr.state || addr.province || "",
      city: addr.city || addr.town || addr.village || "",
      county: addr.county || addr.suburb || addr.city_district || "",
    },
  };
}

function autofillAddress(geo) {
  const address = geo?.address || {};
  countryInput.value = address.country || "";
  admin1Input.value = address.state || "";
  cityInput.value = address.city || "";
  districtInput.value = address.county || "";
  if (geo.display_name) {
    placeNameInput.value = geo.display_name.split(",")[0].trim();
  }
}

function autofillFromForward(geo) {
  if (geo.display_name) {
    placeNameInput.value = geo.display_name.split(",")[0].trim() || placeNameInput.value;
  }
  if (geo.address) {
    const addr = geo.address;
    if (addr.country && !countryInput.value) countryInput.value = addr.country;
    if (addr.state && !admin1Input.value) admin1Input.value = addr.state;
    if (addr.city && !cityInput.value) cityInput.value = addr.city;
    if (addr.county && !districtInput.value) districtInput.value = addr.county;
  }
}

function fitMapToSearchBounds(geoResult) {
  const bbox = geoResult?.boundingbox;
  if (!Array.isArray(bbox) || bbox.length !== 4) return false;

  const south = Number.parseFloat(bbox[0]);
  const north = Number.parseFloat(bbox[1]);
  const west = Number.parseFloat(bbox[2]);
  const east = Number.parseFloat(bbox[3]);
  if ([south, north, west, east].some((v) => Number.isNaN(v))) return false;
  if (south === north || west === east) return false;

  const bounds = new AMap.Bounds([west, south], [east, north]);
  map.setBounds(bounds, false, [28, 28, 28, 28]);
  return true;
}

// ─── 工具函数 ──────────────────────────────────────────────────────────────────
function clearForm() {
  form.reset();
  latInput.value = "";
  lngInput.value = "";
  setSearchTip("");
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function formatTime(iso) {
  return new Date(iso).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function setSearchTip(text, isError = false) {
  searchTip.textContent = text;
  searchTip.classList.toggle("error", Boolean(isError));
}

function getSpotTime(spot) {
  return spot.travelAt || spot.createdAt;
}

function normalizeCountry(name) {
  return String(name || "").trim().toLowerCase();
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function haversine(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.asin(Math.sqrt(a));
}
