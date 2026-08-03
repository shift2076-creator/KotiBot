"use strict";

var S = window.S = window.dashboardState = {
  status: null,
  activeView: "dashboard",
  previousView: "",
  viewSettingsOpen: false,
  selectedClientId: "",
  selectedRoomName: "",
  groupByRoom: true,
  activeDashboardPage: "home",
  renderHomepage: true,
  renderControls: false,
  renderMonitors: false,
  renderSensors: false,
  cardDebugEnabled: false,
  tapoSettingsOpen: false,
  tapoSelectedRoom: "",
  tapoSelectedDeviceId: "",
  tapoRoomSettingsOpen: false
};

const DASHBOARD_DEFAULTS = {
  cardDebugInfo: "off",
  dashboardGroupByRoom: "1",
  dashboardInfoShown: "0",
  dashboardTextSize: "normal",
  dashboardPage: "home"
};

const DASHBOARD_DEFAULTS_VERSION = "2026-06-14-room-groups-1";

if (localStorage.getItem("dashboardDefaultsVersion") !== DASHBOARD_DEFAULTS_VERSION) {
  Object.entries(DASHBOARD_DEFAULTS).forEach(([key, value]) => {
    if (localStorage.getItem(key) === null) {
      localStorage.setItem(key, value);
    }
  });

  localStorage.removeItem("dashboardSpacing");
  localStorage.setItem("dashboardDefaultsVersion", DASHBOARD_DEFAULTS_VERSION);
}

function dashboardPref(key) {
  const saved = localStorage.getItem(key);
  return saved === null ? DASHBOARD_DEFAULTS[key] : saved;
}

function cleanDashboardPref(value, allowed, fallback) {
  return allowed.includes(value) ? value : fallback;
}

function cleanDashboardPage(value) {
  const clean = String(value || "").trim().toLowerCase();

  if (clean === "monitors") return "monitor";
  if (["home", "controls", "monitor", "sensors"].includes(clean)) return clean;

  return "home";
}

window.cleanDashboardPage = cleanDashboardPage;

function dashboardRenderModeName(page) {
  const cleanPage = cleanDashboardPage(page);

  if (cleanPage === "controls") return "render-controls";
  if (cleanPage === "monitor") return "render-monitors";
  if (cleanPage === "sensors") return "render-sensors";

  return "render-homepage";
}

window.dashboardRenderModeName = dashboardRenderModeName;

function savedDashboardPage() {
  return cleanDashboardPage(localStorage.getItem("dashboardPage") || dashboardPref("dashboardPage"));
}

window.savedDashboardPage = savedDashboardPage;

window.setDashboardPageState = function (page, options = {}) {
  const cleanPage = cleanDashboardPage(page);
  const persist = options.persist !== false;
  const syncDocument = options.syncDocument !== false;

  S.activeDashboardPage = cleanPage;
  S.renderHomepage = cleanPage === "home";
  S.renderControls = cleanPage === "controls";
  S.renderMonitors = cleanPage === "monitor";
  S.renderSensors = cleanPage === "sensors";

  if (syncDocument) {
    document.body.dataset.dashboardPage = cleanPage;
    document.body.dataset.dashboardRender = dashboardRenderModeName(cleanPage);
    document.body.removeAttribute("data-render-controls");
    document.body.removeAttribute("data-render-monitors");
    document.body.removeAttribute("data-render-sensors");
  }

  if (persist) {
    localStorage.setItem("dashboardPage", cleanPage);
  }

  return cleanPage;
};

function dashboardStaticVersionQuery() {
  const version = (
    window.KOTIBOT_STATIC_VERSION ||
    window.dashboardStaticVersion ||
    document.documentElement?.dataset?.staticVersion ||
    document.body?.dataset?.staticVersion ||
    ""
  );

  return version ? `?v=${encodeURIComponent(version)}` : "";
}

function dashboardThemeCssHref(theme) {
  const clean = ["dark", "light"].includes(theme) ? theme : "dark";
  return `/static/css/theme-${clean}.css${dashboardStaticVersionQuery()}`;
}

window.resolveDashboardSystemTheme = function () {
  try {
    const androidTheme = String(window.KOTIBOT_ANDROID_SYSTEM_THEME || "").toLowerCase();
    if (["dark", "light"].includes(androidTheme)) return androidTheme;
  } catch (_) {}

  try {
    const nativeTheme = String(window.KotiBotAndroidStorage?.getSystemThemeMode?.() || "").toLowerCase();
    if (["dark", "light"].includes(nativeTheme)) return nativeTheme;
  } catch (_) {}

  try {
    const darkQuery = window.matchMedia?.("(prefers-color-scheme: dark)");
    const lightQuery = window.matchMedia?.("(prefers-color-scheme: light)");

    if (darkQuery?.matches) return "dark";
    if (lightQuery?.matches) return "light";
  } catch (_) {}

  return "dark";
};

window.loadDashboardThemeCss = function (theme) {
  const clean = ["dark", "light"].includes(theme) ? theme : "dark";
  let link = document.getElementById("dashboardThemeCss");

  if (!link) {
    link = document.createElement("link");
    link.id = "dashboardThemeCss";
    link.rel = "stylesheet";
    document.head.appendChild(link);
  }

  const href = dashboardThemeCssHref(clean);
  const currentHref = link.getAttribute("href") || "";

  if (currentHref !== href) {
    link.href = href;
  }

  const root = document.documentElement;
  const body = document.body;

  root.dataset.theme = clean;
  root.style.colorScheme = clean;

  if (body) {
    body.dataset.theme = clean;
    body.style.colorScheme = clean;
  }

  window.kotibotApplyAndroidSystemBars?.();
};

window.applyDashboardSystemTheme = function () {
  const theme = resolveDashboardSystemTheme?.() || "dark";
  loadDashboardThemeCss?.(theme);
  return theme;
};

window.bindDashboardSystemTheme = function () {
  if (window.__dashboardSystemThemeBound) {
    return applyDashboardSystemTheme?.();
  }

  window.__dashboardSystemThemeBound = true;
  applyDashboardSystemTheme?.();

  try {
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!media) return;

    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", () => applyDashboardSystemTheme?.());
    } else if (typeof media.addListener === "function") {
      media.addListener(() => applyDashboardSystemTheme?.());
    }
  } catch (_) {}
};

const initialGroupByRoom = true;
const initialCardDebug = dashboardPref("cardDebugInfo") === "on" ? "on" : "off";
const initialInfoShown = initialCardDebug === "on";
const initialDashboardTextSize = cleanDashboardPref(dashboardPref("dashboardTextSize"), ["normal", "accessible"], "normal");
const initialDashboardPage = savedDashboardPage();
const initialRenderHomepage = initialDashboardPage === "home";
const initialRenderControls = initialDashboardPage === "controls";
const initialRenderMonitors = initialDashboardPage === "monitor";
const initialRenderSensors = initialDashboardPage === "sensors";

localStorage.removeItem("dashboardSpacing");
localStorage.removeItem("dashboardActiveRoomFilter");
localStorage.removeItem("dashboardMaxColumns");

document.body.dataset.cardDebug = initialCardDebug;
document.body.dataset.dashboardTextSize = initialDashboardTextSize;
document.body.dataset.groupByRoom = initialGroupByRoom ? "1" : "0";
document.body.dataset.dashboardPage = initialDashboardPage;
document.body.dataset.dashboardRender = dashboardRenderModeName(initialDashboardPage);
applyDashboardSystemTheme?.();
document.body.classList.toggle("debug-off", !initialInfoShown);

window.appState = {
  debugMode: initialCardDebug === "on",
  currentClients: [],
  currentRoutes: [],
  currentAutomations: [],
  currentUsedZones: [],
  currentVideosByDeviceId: {},
  currentVideoStorage: null,
  fileServerApks: [],
  logLines: [],
  logInterval: null,
  recentActivity: [],
  recentActivityLoading: false,
  recentActivityInterval: null,
  recentActivityRequestID: 0,
  activityModalOpen: false,
  activityFilter: "automation",
  activityFromHours: 0,
  activityToHours: 0,
  activityAvailableHours: 1,
  activityOldestTs: 0,
  activityLimit: 12,
  activityHasMore: false,
  activityAutoLoadObserver: null,
  statusInterval: null,
  DEBUG_LOG_MAX_LINES: 800,

  clients: [],
  soundNodes: [],
  selectedSoundFile: "",
  nodes: {},
  connections: [],
  routes: [],

  selectedOutput: null,
  selectedInput: null,

  activeView: "dashboard",
  activeDashboardPage: initialDashboardPage,
  renderHomepage: initialRenderHomepage,
  renderControls: initialRenderControls,
  renderMonitors: initialRenderMonitors,
  renderSensors: initialRenderSensors,
  groupByRoom: initialGroupByRoom,

  previewViewerId: localStorage.getItem("previewViewerId") || ("viewer_" + Math.random().toString(36).slice(2)),
  activePreviewDeviceIds: []
};

S = window.S = window.dashboardState = window.appState;

{
  const versionQuery = dashboardStaticVersionQuery();
  const initialRendererPaths = [];

  if (initialRenderControls && window.KOTIBOT_TAPO_ENABLED === true) {
    initialRendererPaths.push("client-tapo/static/js/tapo-render.js");
  }

  if (initialRenderMonitors || initialRenderSensors) {
    initialRendererPaths.push(
      "matter/static/js/matter-render.js",
      "client-android-home/static/js/client-android-home-render.js"
    );

    if (window.KOTIBOT_TAPO_ENABLED === true) {
      initialRendererPaths.push("client-tapo/static/js/tapo-render.js");
    }
  }

  initialRendererPaths.forEach(path => {
    const href = `/subsystems/${path}${versionQuery}`;

    if (versionQuery && !document.querySelector(`link[rel="preload"][href="${CSS.escape(href)}"]`)) {
      const preload = document.createElement("link");
      preload.rel = "preload";
      preload.as = "script";
      preload.href = href;
      document.head.appendChild(preload);
    }
  });
}

localStorage.setItem("previewViewerId", window.appState.previewViewerId);

function dashboardRoomOrderStorageKey(mode) {
  if (mode === "controls" || (mode !== "dashboard" && S.renderControls)) {
    return DASHBOARD_CONTROLS_ROOM_ORDER_STORAGE_KEY;
  }

  if (mode === "monitors" || mode === "monitor" || (mode !== "dashboard" && S.renderMonitors)) {
    return DASHBOARD_MONITORS_ROOM_ORDER_STORAGE_KEY;
  }

  if (mode === "sensors" || (mode !== "dashboard" && S.renderSensors)) {
    return DASHBOARD_SENSORS_ROOM_ORDER_STORAGE_KEY;
  }

  return DASHBOARD_ROOM_ORDER_STORAGE_KEY;
}

window.getDashboardRoomOrder = function (mode) {
  try {
    const parsed = JSON.parse(localStorage.getItem(dashboardRoomOrderStorageKey(mode)) || "[]");

    return Array.isArray(parsed)
      ? parsed.map(room => String(room || "").trim()).filter(Boolean)
      : [];
  } catch (_) {
    return [];
  }
};

window.setDashboardRoomOrder = function (rooms, mode) {
  const cleanRooms = Array.from(new Set(
    (rooms || [])
      .map(room => String(room || "").trim())
      .filter(room => room && room !== "Unassigned")
  ));

  localStorage.setItem(dashboardRoomOrderStorageKey(mode), JSON.stringify(cleanRooms));
};

window.getDashboardControlsRoomOrder = function () {
  return getDashboardRoomOrder("controls");
};

window.setDashboardControlsRoomOrder = function (rooms) {
  setDashboardRoomOrder(rooms, "controls");
};

window.getDashboardMonitorsRoomOrder = function () {
  return getDashboardRoomOrder("monitors");
};

window.setDashboardMonitorsRoomOrder = function (rooms) {
  setDashboardRoomOrder(rooms, "monitors");
};

window.getDashboardSensorsRoomOrder = function () {
  return getDashboardRoomOrder("sensors");
};

window.setDashboardSensorsRoomOrder = function (rooms) {
  setDashboardRoomOrder(rooms, "sensors");
};

window.sortDashboardRoomNames = function (rooms) {
  const order = getDashboardRoomOrder();
  const orderIndex = new Map(order.map((room, index) => [room.toLowerCase(), index]));
  const maxIndex = Number.MAX_SAFE_INTEGER;

  return Array.from(new Set(
    (rooms || [])
      .map(room => String(room || "").trim())
      .filter(Boolean)
  )).sort((a, b) => {
    const ai = orderIndex.has(a.toLowerCase()) ? orderIndex.get(a.toLowerCase()) : maxIndex;
    const bi = orderIndex.has(b.toLowerCase()) ? orderIndex.get(b.toLowerCase()) : maxIndex;

    if (ai !== bi) return ai - bi;

    return a.localeCompare(b, undefined, { sensitivity: "base" });
  });
};

window.compareDefaultRoomEntries = function (a, b) {
  if (b.weight !== a.weight) return b.weight - a.weight;

  return a.room.localeCompare(b.room, undefined, { sensitivity: "base" });
};

window.sortDashboardRoomEntries = function (entries) {
  const order = getDashboardRoomOrder();

  if (!order.length) {
    return (entries || []).sort(compareDefaultRoomEntries);
  }

  const orderIndex = new Map(order.map((room, index) => [room.toLowerCase(), index]));
  const maxIndex = Number.MAX_SAFE_INTEGER;

  return (entries || []).sort((a, b) => {
    const ai = orderIndex.has(a.room.toLowerCase()) ? orderIndex.get(a.room.toLowerCase()) : maxIndex;
    const bi = orderIndex.has(b.room.toLowerCase()) ? orderIndex.get(b.room.toLowerCase()) : maxIndex;

    if (ai !== bi) return ai - bi;

    return compareDefaultRoomEntries(a, b);
  });
};

window.getDashboardAllRoomNames = function () {
  const seen = new Set();
  const rooms = [];

  const addRoom = (roomValue) => {
    const room = String(roomValue || "").trim();
    const key = room.toLowerCase();

    if (!room || room === "Unassigned" || seen.has(key)) return;

    seen.add(key);
    rooms.push(room);
  };

  (S.currentClients || []).forEach(c => {
    if (!c?.provisioned) return;
    addRoom(clientRoomName(c));
  });

  (S.currentUsedZones || []).forEach(addRoom);

  return sortDashboardRoomNames(rooms);
};

const DASHBOARD_ROOM_ORDER_STORAGE_KEY = "dashboardRoomOrder";
const DASHBOARD_CONTROLS_ROOM_ORDER_STORAGE_KEY = "dashboardControlsRoomOrder";
const DASHBOARD_MONITORS_ROOM_ORDER_STORAGE_KEY = "dashboardMonitorsRoomOrder";
const DASHBOARD_SENSORS_ROOM_ORDER_STORAGE_KEY = "dashboardSensorsRoomOrder";

window.previewViewerId = window.previewViewerId || `dash_${Date.now()}_${Math.random().toString(16).slice(2)}`;
window.previewActiveDeviceIds = window.previewActiveDeviceIds || new Set();
window.previewViewerHeartbeatMs = Number(window.previewViewerHeartbeatMs || 15000);
window.previewViewerMinRepeatMs = Number(window.previewViewerMinRepeatMs || 3000);
window.clientMenuPreviewRefreshMs = 4000;
window.cameraVideoModalRefreshMs = 1500;
window.cameraVideoModalViewerHeartbeatMs = 4000;