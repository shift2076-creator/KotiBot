"use strict";

var S = window.appState;

window.requestDashboardRenderSafe = window.requestDashboardRenderSafe || function (data) {
  if (typeof window.requestDashboardRender === "function") {
    return window.requestDashboardRender(data);
  }

  if (typeof window.dashboardRequestRender === "function") {
    return window.dashboardRequestRender(data);
  }

  if (typeof window.render === "function") {
    return window.render(data);
  }
};

/* ================================
   API / SERVER COMMUNICATION
================================ */

(function initDashboardLoadProfiler() {
  if (window.dashboardLoadProfiler) return;

  const pageStartedAt = (window.performance?.timeOrigin || Date.now());
  const now = () => (window.performance?.now ? window.performance.now() : Date.now() - pageStartedAt);
  const cleanNumber = (value) => Math.round(Number(value || 0) * 10) / 10;

  const profiler = {
    entries: [],
    pageStartedAt,
    now,

    mark(label, details = {}) {
      const at = now();
      const entry = {
        kind: "mark",
        label: String(label || "mark"),
        at,
        atMs: cleanNumber(at),
        ...details
      };

      this.entries.push(entry);
      console.debug(`[dashboard-load] ${entry.label}`, { atMs: entry.atMs, ...details });
      return entry;
    },

    measure(label, startedAt, details = {}) {
      const endedAt = now();
      const start = Number(startedAt || endedAt);
      const entry = {
        kind: "measure",
        label: String(label || "measure"),
        startedAt: start,
        endedAt,
        durationMs: cleanNumber(endedAt - start),
        ...details
      };

      this.entries.push(entry);
      console.debug(`[dashboard-load] ${entry.label}: ${entry.durationMs}ms`, details);
      return entry;
    },

    async fetch(url, options = {}, fetcher = window.fetch.bind(window)) {
      const startedAt = now();
      const method = String(options?.method || url?.method || "GET").toUpperCase();
      const requestUrl = String(url?.url || url || "");

      try {
        const res = await fetcher(url, options);
        const serverMsRaw = res?.headers?.get?.("X-KotiBot-Route-Ms");
        const serverMs = serverMsRaw === null || serverMsRaw === undefined || serverMsRaw === ""
          ? null
          : cleanNumber(serverMsRaw);

        const entry = this.measure(`fetch ${method} ${requestUrl}`, startedAt, {
          kind: "request",
          method,
          url: requestUrl,
          status: res?.status ?? "",
          ok: !!res?.ok,
          serverMs
        });

        entry.durationMs = cleanNumber(entry.durationMs);
        return res;
      } catch (err) {
        this.measure(`fetch ${method} ${requestUrl}`, startedAt, {
          kind: "request",
          method,
          url: requestUrl,
          status: "ERR",
          ok: false,
          error: String(err?.message || err || "fetch failed")
        });

        throw err;
      }
    },

    report(label = "dashboard load timing") {
      const requests = this.entries
        .filter(entry => entry.kind === "request")
        .map(entry => ({
          ms: cleanNumber(entry.durationMs),
          serverMs: entry.serverMs ?? "",
          method: entry.method || "",
          status: entry.status ?? "",
          url: entry.url || entry.label || ""
        }))
        .sort((a, b) => Number(b.ms || 0) - Number(a.ms || 0));

      const marks = this.entries
        .filter(entry => entry.kind !== "request")
        .map(entry => ({
          ms: cleanNumber(entry.durationMs ?? entry.atMs ?? 0),
          type: entry.kind,
          label: entry.label || ""
        }));

      console.groupCollapsed(`[dashboard-load] ${label}`);
      console.table(requests);
      console.table(marks);
      console.groupEnd();

      return { requests, marks, entries: this.entries.slice() };
    }
  };

  window.dashboardLoadProfiler = profiler;
  window.dashboardLoadMark = (label, details = {}) => profiler.mark(label, details);
  window.dashboardLoadMeasure = (label, startedAt, details = {}) => profiler.measure(label, startedAt, details);
  window.dashboardTimedFetch = (url, options = {}, fetcher) => profiler.fetch(url, options, fetcher);

  profiler.mark("profiler ready");
})();

(function reportBrowserStartupTiming() {
  try {
    const cleanNumber = (value) => Math.round(Number(value || 0) * 10) / 10;
    const nav = window.performance?.getEntriesByType?.("navigation")?.[0];
    const resources = window.performance?.getEntriesByType?.("resource") || [];

    const navigationRows = nav ? [
      { label: "request start", ms: cleanNumber(nav.requestStart) },
      { label: "response start", ms: cleanNumber(nav.responseStart) },
      { label: "response end", ms: cleanNumber(nav.responseEnd) },
      { label: "dom interactive", ms: cleanNumber(nav.domInteractive) },
      { label: "dom content loaded", ms: cleanNumber(nav.domContentLoadedEventEnd) },
      { label: "load event end", ms: cleanNumber(nav.loadEventEnd) }
    ] : [];

    const assetRows = resources
      .filter(entry => {
        const name = String(entry.name || "");
        const type = String(entry.initiatorType || "");

        return (
          ["script", "link", "css", "font"].includes(type) ||
          name.includes("/static/") ||
          name.includes("/subsystems/")
        );
      })
      .map(entry => {
        const rawName = String(entry.name || "");
        let cleanName = rawName;

        try {
          const url = new URL(rawName);
          cleanName = `${url.pathname}${url.search}`;
        } catch (_) {}

        const serverTiming = Array.isArray(entry.serverTiming)
          ? entry.serverTiming.find(item => item?.name === "kotibot")
          : null;

        return {
          type: entry.initiatorType || "",
          startMs: cleanNumber(entry.startTime),
          ms: cleanNumber(entry.duration),
          serverMs: serverTiming ? cleanNumber(serverTiming.duration) : "",
          transferKb: cleanNumber((entry.transferSize || 0) / 1024),
          decodedKb: cleanNumber((entry.decodedBodySize || 0) / 1024),
          blocking: entry.renderBlockingStatus || "",
          name: cleanName
        };
      })
      .sort((a, b) => a.startMs - b.startMs || b.ms - a.ms);

    console.groupCollapsed("[dashboard-load] browser startup before dashboard-api.js");

    if (navigationRows.length) {
      console.table(navigationRows);
    }

    if (assetRows.length) {
      console.table(assetRows);
    }

    console.groupEnd();
  } catch (err) {
    console.warn("[dashboard-load] browser startup timing failed", err);
  }
})();

window.dashboardHeaders = function (extra = {}) {
  return { ...extra };
};

window.dashboardFetch = function (url, options = {}) {
  return dashboardTimedFetch(url, {
    ...options,
    headers: dashboardHeaders(options.headers || {})
  });
};

window.refreshRecentActivities = async function (options = {}) {
  const requestedLimit = Number(
    options.limit ?? S.activityLimit ?? 12
  );
  const limit = Number.isFinite(requestedLimit)
    ? Math.max(
        1,
        Math.min(50, Math.round(requestedLimit))
      )
    : 12;
  const requestedFromHours = Number(
    options.fromHours ??
    S.activityFromHours ??
    0
  );
  const fromHours = Number.isFinite(
    requestedFromHours
  )
    ? Math.max(
        0,
        Math.min(168, requestedFromHours)
      )
    : 0;

  const requestedToHours = Number(
    options.toHours ??
    S.activityToHours ??
    0
  );
  let toHours = Number.isFinite(
    requestedToHours
  )
    ? Math.max(
        0,
        Math.min(167, requestedToHours)
      )
    : 0;

  if (
    fromHours > 0 &&
    toHours >= fromHours
  ) {
    toHours = Math.max(
      0,
      fromHours - 1
    );
  }
  const requestedBefore = Number(
    options.beforeTs || 0
  );
  const beforeTs = (
    Number.isFinite(requestedBefore) &&
    requestedBefore > 0
  )
    ? requestedBefore
    : 0;
  const category = [
    "all",
    "automation",
    "security",
    "system",
    "users"
  ].includes(options.category)
    ? options.category
    : (S.activityFilter || "all");
  const merge = options.merge === true;

  const requestID = (
    Number(S.recentActivityRequestID || 0) + 1
  );
  S.recentActivityRequestID = requestID;
  S.recentActivityLoading = true;
  window.syncDashboardActivityModal?.();

  try {
    const query = new URLSearchParams({
      limit: String(limit),
      from_hours: String(fromHours),
      to_hours: String(toHours),
      category
    });

    if (beforeTs) {
      query.set("before", String(beforeTs));
    }

    const res = await dashboardFetch(
      `/api/activities/recent?${query}`,
      {
        cache: "no-store"
      }
    );
    const data = await res.json();

    if (!res.ok || data.ok === false) {
      throw new Error(
        data.error ||
        `Recent activity failed: ${res.status}`
      );
    }

    if (requestID !== S.recentActivityRequestID) {
      return S.recentActivity || [];
    }

    const items = Array.isArray(data.items)
      ? data.items
      : [];

    if (merge) {
      const nowSeconds = Date.now() / 1000;
      const oldestCutoff = (
        nowSeconds -
        ((fromHours || 168) * 3600)
      );
      const newestCutoff = (
        toHours > 0
          ? nowSeconds - (toHours * 3600)
          : Number.POSITIVE_INFINITY
      );
      const byID = new Map(
        [
          ...(S.recentActivity || []),
          ...items
        ]
          .filter(item => item && item.id)
          .map(item => [item.id, item])
      );

      S.recentActivity = [...byID.values()]
        .sort(
          (a, b) =>
            Number(b.ts || 0) -
            Number(a.ts || 0)
        )
        .filter(item => {
          const timestamp = Number(
            item.ts || 0
          );

          return (
            Number.isFinite(timestamp) &&
            timestamp >= oldestCutoff &&
            timestamp <= newestCutoff
          );
        });
    } else {
      S.recentActivity = items;
    }

    const oldestTs = Number(
      data.oldest_ts || 0
    );
    S.activityOldestTs = Number.isFinite(oldestTs)
      ? oldestTs
      : 0;
    S.activityAvailableHours = S.activityOldestTs
      ? Math.max(
          1,
          Math.min(
            168,
            Math.ceil(
              (
                Date.now() / 1000 -
                S.activityOldestTs
              ) / 3600
            )
          )
        )
      : 1;

    if (
      S.activityFromHours >=
      S.activityAvailableHours
    ) {
      S.activityFromHours = 0;
    }

    const resolvedFromHours = (
      S.activityFromHours > 0
        ? Math.min(
            S.activityFromHours,
            S.activityAvailableHours
          )
        : S.activityAvailableHours
    );

    S.activityToHours = Math.max(
      0,
      Math.min(
        Math.round(
          Number(S.activityToHours || 0)
        ),
        Math.max(0, resolvedFromHours - 1)
      )
    );

    if (options.preserveHasMore !== true) {
      S.activityHasMore =
        data.has_more === true;
    }

    return S.recentActivity;
  } finally {
    if (
      requestID ===
      S.recentActivityRequestID
    ) {
      S.recentActivityLoading = false;
      window.syncDashboardActivityModal?.();
    }
  }
};

window.startRecentActivityPolling = function () {
  if (S.recentActivityInterval) return;

  const pollRecentActivity = async () => {
    try {
      if (S.activityModalOpen && !document.hidden && !S.recentActivityLoading) {
        await refreshRecentActivities({
          limit: S.activityLimit,
          fromHours: S.activityFromHours,
          toHours: S.activityToHours,
          category: S.activityFilter,
          merge: true,
          preserveHasMore: true
        });
      }
    } catch (err) {
      console.warn("[recent-activity] poll error", err);
    }
  };

  S.recentActivityInterval = setInterval(pollRecentActivity, 15000);
};

window.refreshTapoDeviceStates = async function () {
  const res = await dashboardFetch("/api/tapo/refresh", {
    method: "POST"
  });

  const data = await res.json();

  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Tapo refresh failed: ${res.status}`);
  }

  return data;
};

window.getTapoStatus = async function () {
  const res = await dashboardFetch("/api/tapo/status");
  return res.json();
};

window.getBluetoothStatus = async function () {
  const res = await dashboardFetch("/api/bluetooth/status");
  const data = await res.json();

  if (!res.ok) {
    throw new Error(data.error || `Bluetooth status failed: ${res.status}`);
  }

  return data;
};

window.setBluetoothAdapterAction = async function (action) {
  const res = await dashboardFetch("/api/bluetooth/adapter", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action })
  });
  const data = await res.json();

  if (!res.ok || data.ok === false) {
    throw new Error(data.command_error || data.error || `Bluetooth adapter action failed: ${res.status}`);
  }

  return data;
};

window.scanBluetoothDevices = async function (seconds = 8) {
  const res = await dashboardFetch("/api/bluetooth/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ seconds })
  });
  const data = await res.json();

  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Bluetooth scan failed: ${res.status}`);
  }

  return data;
};

window.startBluetoothPairing = async function () {
  const res = await dashboardFetch("/api/bluetooth/pairing/start", { method: "POST" });
  const data = await res.json();

  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Bluetooth pairing start failed: ${res.status}`);
  }

  return data;
};

window.cancelBluetoothPairing = async function () {
  const res = await dashboardFetch("/api/bluetooth/pairing/cancel", { method: "POST" });
  const data = await res.json();

  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Bluetooth pairing cancel failed: ${res.status}`);
  }

  return data;
};

window.listBluetoothPairingDevices = async function () {
  const res = await dashboardFetch("/api/bluetooth/pairing/devices");
  const data = await res.json();

  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Bluetooth pairing device refresh failed: ${res.status}`);
  }

  return data;
};

window.setBluetoothDeviceAction = async function (address, action) {
  const res = await dashboardFetch("/api/bluetooth/device", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address, action })
  });
  const data = await res.json();

  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Bluetooth device action failed: ${res.status}`);
  }

  return data;
};

window.restartKotiBotServer = async function () {
  await dashboardFetch("/api/restart-server", { method: "POST" });
};

window.refreshSecurityStatus = async function () {
  const res = await dashboardFetch("/api/security/status");
  return res.json();
};

window.loginDashboardSecurity = async function (value, password = "") {
  const cleanValue = String(value || "").trim();
  const cleanPassword = String(password || "");

  let body;

  if (cleanPassword) {
    body = { email: cleanValue, password: cleanPassword };
  } else {
    body = { key: cleanValue };
  }

  if (!cleanValue) {
    return { ok: false, error: "missing_login" };
  }

  const res = await fetch("/api/security/dashboard-login", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });

  return await res.json();
};

window.listDashboardSecurityUsers = async function () {
  const res = await dashboardFetch("/api/security/dashboard-users", {
    method: "GET",
    cache: "no-store"
  });

  const data = await res.json();

  if (!res.ok || data.ok === false) {
    throw new Error(data.error || "Failed to load dashboard users");
  }

  return data;
};

window.addDashboardSecurityUser = async function (email, password) {
  const res = await dashboardFetch("/api/security/dashboard-users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });

  const data = await res.json();

  if (!res.ok || data.ok === false) {
    throw new Error(data.error || "Failed to add dashboard user");
  }

  return data;
};

window.removeDashboardSecurityUser = async function (email) {
  const res = await dashboardFetch("/api/security/dashboard-users", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email })
  });

  const data = await res.json();

  if (!res.ok || data.ok === false) {
    throw new Error(data.error || "Failed to remove dashboard user");
  }

  return data;
};


window.asBool = function (v) {
  if (v === true || v === 1) return true;
  if (v === false || v === 0 || v == null) return false;

  const s = String(v).trim().toLowerCase();
  return ["true", "yes", "y", "1", "provisioned"].includes(s);
};

window.normalizeClient = function (c) {
  const role = c.clientRole || c.client_role || c.role || "UNP";
  const normalized = {
    ...c,
    deviceID: c.deviceID || c.device_id || c.client_id || c.id || "",
    clientName: c.clientName || c.client_name || c.tapo_alias || c.alias || c.name || c.display_name || "",
    clientRole: Array.isArray(role)
      ? role
      : String(role).split(",").map(r => r.trim()).filter(Boolean),
    provisioned: asBool(c.provisioned) && !String(role).toUpperCase().includes("UNP"),
    zone_name: c.zone_name || c.zoneName || "",
    hasDSSHW: c.hasDSSHW
  };

  normalized.server_stale = normalized.server_stale ?? normalized.stale;
  normalized.stale = typeof window.dashboardEffectiveClientStale === "function"
    ? window.dashboardEffectiveClientStale(normalized)
    : !!normalized.stale;

  return normalized;
};

function captureDashboardTapoReportedPowerStates(clients = []) {
  const reportedStates = new Map();

  clients.forEach(client => {
    const deviceID = String(
      client?.deviceID || client?.device_id || client?.client_id || client?.id || ""
    ).trim();

    if (!deviceID) return;
    if (!Object.prototype.hasOwnProperty.call(client, "tapo_is_on")) return;

    reportedStates.set(deviceID, client.tapo_is_on);

    const children = Array.isArray(client?.tapo_children)
      ? client.tapo_children
      : Array.isArray(client?.children)
        ? client.children
        : [];

    children.forEach((child, index) => {
      if (!child || typeof child !== "object") return;

      const childID = String(
        child.id
        ?? child.device_id
        ?? child.deviceId
        ?? child.child_id
        ?? child.childId
        ?? child.position
        ?? child.index
        ?? index + 1
      ).trim();

      if (!childID) return;

      reportedStates.set(
        `${deviceID}::${childID}`,
        child.is_on ?? child.device_on ?? child.on ?? child.state
      );
    });
  });

  S.tapoReportedPowerStates = reportedStates;
}

window.applyDashboardTapoLightingState = function (serverState = {}) {
  const state = window.TAPO_LIGHTING_STATE && typeof window.TAPO_LIGHTING_STATE === "object"
    ? window.TAPO_LIGHTING_STATE
    : {};

  state.schemes = serverState.schemes && typeof serverState.schemes === "object"
    ? serverState.schemes
    : {};
  state.activeSchemes = serverState.activeSchemes && typeof serverState.activeSchemes === "object"
    ? serverState.activeSchemes
    : {};
  state.modeConfig = serverState.modeConfig && typeof serverState.modeConfig === "object"
    ? serverState.modeConfig
    : {};
  state.loaded = true;

  window.TAPO_LIGHTING_STATE = state;
  return state;
};

const DASHBOARD_BOOTSTRAP_MAX_AGE_MS = 15000;
let dashboardBootstrapStatusConsumed = false;
let dashboardBootstrapInvalidated = false;

function dashboardBootstrapObject() {
  const bootstrap = window.KOTIBOT_BOOTSTRAP;

  if (!bootstrap || typeof bootstrap !== "object" || Array.isArray(bootstrap)) {
    return null;
  }

  if (bootstrap.ok === false || dashboardBootstrapInvalidated) {
    return null;
  }

  const receivedAtMs = Number(window.KOTIBOT_BOOTSTRAP_RECEIVED_AT_MS || 0);
  const generatedAtMs = Number(
    bootstrap.generated_at_ms ||
    (Number(bootstrap.generated_at || 0) * 1000)
  );
  const ageBaseMs = receivedAtMs || generatedAtMs;

  if (ageBaseMs && Date.now() - ageBaseMs > DASHBOARD_BOOTSTRAP_MAX_AGE_MS) {
    window.dashboardLoadMark?.("bootstrap skipped", {
      reason: "stale",
      ageMs: Math.round(Date.now() - ageBaseMs)
    });
    return null;
  }

  return bootstrap;
}

window.invalidateDashboardBootstrap = function (reason = "invalidated") {
  dashboardBootstrapInvalidated = true;
  dashboardBootstrapStatusConsumed = true;
  window.dashboardLoadMark?.("bootstrap invalidated", { reason: String(reason || "invalidated") });
};

window.dashboardBootstrapAuthStatus = function () {
  const bootstrap = dashboardBootstrapObject();

  if (!bootstrap) return null;

  const auth = bootstrap.auth && typeof bootstrap.auth === "object" && !Array.isArray(bootstrap.auth)
    ? { ...bootstrap.auth }
    : { ok: true, dashboard_authenticated: !!bootstrap.dashboard_authenticated };

  auth.dashboard_authenticated = !!(auth.dashboard_authenticated || bootstrap.dashboard_authenticated);
  auth.ok = auth.ok !== false;

  window.dashboardLoadMark?.("bootstrap auth used", {
    authenticated: auth.dashboard_authenticated
  });

  return auth;
};

window.applyDashboardStatusData = function (data, source = "network") {
  data = data && typeof data === "object" ? data : {};

  const rawClients = Array.isArray(data.clients) ? data.clients : [];
  captureDashboardTapoReportedPowerStates(rawClients);

  data.clients = rawClients
    .map(normalizeClient)
    .filter(c => c.deviceID);

  S.currentUsedZones = Array.isArray(data.used_zones) ? data.used_zones : [];

  const serverObject =
    data.server && typeof data.server === "object" && !Array.isArray(data.server)
      ? data.server
      : {};

  const rootServerState = {
    uptime_text: data.uptime_text,
    server_uptime_text: data.server_uptime_text,
    uptime_human: data.uptime_human,
    uptime_label: data.uptime_label,
    server_uptime: data.server_uptime,
    process_uptime: data.process_uptime,
    uptime_seconds: data.uptime_seconds,
    server_uptime_seconds: data.server_uptime_seconds,
    process_uptime_seconds: data.process_uptime_seconds,
    uptime_sec: data.uptime_sec,
    uptime_s: data.uptime_s,
    uptime: data.uptime,
    server_ip: data.server_ip,
    server_ip_address: data.server_ip_address,
    local_ip: data.local_ip,
    lan_ip: data.lan_ip,
    host_ip: data.host_ip,
    ip_address: data.ip_address,
    local_address: data.local_address,
    host_address: data.host_address,
    ip: data.ip,
    host: data.host,
    address: data.address
  };

  const cleanRootServerState = Object.fromEntries(
    Object.entries(rootServerState).filter(([, value]) => (
      value !== undefined &&
      value !== null &&
      String(value).trim() !== ""
    ))
  );

  S.serverState = {
    ...(S.serverState || S.server || {}),
    ...cleanRootServerState,
    ...serverObject
  };

  S.status = data;
  data._dashboardBootstrapSource = source;
  return data;
};

window.consumeDashboardBootstrapStatus = function () {
  if (dashboardBootstrapStatusConsumed) return null;

  const bootstrap = dashboardBootstrapObject();

  if (!bootstrap) return null;

  if (!bootstrap.dashboard_authenticated || !bootstrap.status || typeof bootstrap.status !== "object") {
    return null;
  }

  dashboardBootstrapStatusConsumed = true;

  if (bootstrap.tapo_lighting_state) {
    window.applyDashboardTapoLightingState(bootstrap.tapo_lighting_state);
  }

  const status = {
    ...bootstrap.status,
    clients: Array.isArray(bootstrap.status.clients) ? bootstrap.status.clients.slice() : []
  };

  window.dashboardLoadMark?.("bootstrap status consumed", {
    clients: status.clients.length
  });

  return window.applyDashboardStatusData(status, "inline-bootstrap");
};

window.refreshRoutes = async function () {
  const [routesResult, automationsResult] = await Promise.allSettled([
    dashboardFetch("/api/routes").then(async res => {
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || `Routes failed: ${res.status}`);
      }

      return data;
    }),
    dashboardFetch("/api/automations").then(async res => {
      const data = await res.json();

      if (!res.ok || data.ok === false) {
        throw new Error(data.error || `Automations failed: ${res.status}`);
      }

      return data;
    })
  ]);

  if (routesResult.status === "rejected") {
    throw routesResult.reason;
  }

  S.currentRoutes = Array.isArray(routesResult.value?.routes)
    ? routesResult.value.routes
    : [];

  if (automationsResult.status === "fulfilled") {
    S.currentAutomations = Array.isArray(automationsResult.value?.automations)
      ? automationsResult.value.automations
      : [];
  } else {
    S.currentAutomations = Array.isArray(S.currentAutomations)
      ? S.currentAutomations
      : [];

    console.warn(
      "[dashboard] automation helper status failed",
      automationsResult.reason
    );
  }

  return S.currentRoutes;
};

window.refreshWavData = async function () {
  const res = await dashboardFetch("/api/wavs");
  const data = await res.json();
  S.soundNodes = data.wavs || data.categories || [];

  const allFiles = [];

  for (const category of S.soundNodes) {
    const files = Array.isArray(category?.files) ? category.files : [];

    for (const file of files) {
      const filename = typeof file === "string" ? file : file?.filename;

      if (filename) allFiles.push(String(filename));
    }
  }

  if (!S.selectedSoundFile || !allFiles.includes(S.selectedSoundFile)) {
    S.selectedSoundFile = allFiles[0] || "";
  }

  return data;
};

window.refreshStatusData = async function (options = {}) {
  if (options.forceNetwork !== true) {
    const bootstrapData = window.consumeDashboardBootstrapStatus?.();

    if (bootstrapData) {
      return bootstrapData;
    }
  }

  const res = await dashboardFetch("/api/status", {
    cache: "no-store"
  });
  const data = await res.json();

  return window.applyDashboardStatusData(data, "network");
};

window.refreshFileServerApks = async function () {
  try {
    const res = await dashboardFetch("/api/file-server/apks", {
      cache: "no-store"
    });
    const data = await res.json();

    if (!res.ok || data.ok === false) {
      S.fileServerApks = [];
      window.syncSettingsApkDownloads?.();
      return data;
    }

    S.fileServerApks = Array.isArray(data.files) ? data.files : [];
    window.syncSettingsApkDownloads?.();
    return data;
  } catch (err) {
    S.fileServerApks = [];
    window.syncSettingsApkDownloads?.();
    return { ok: false, error: String(err?.message || err || "Failed to load APK list") };
  }
};

window.refreshVideoData = async function () {
  const res = await dashboardFetch("/api/videos");
  const data = await res.json();
  S.currentVideoStorage = data.storage || null;
  S.currentVideosByDeviceId = {};
  for (const group of (data.videos || [])) {
    S.currentVideosByDeviceId[group.deviceID] = group.files || [];
  }
  return data;
};

window.isElementInViewport = function (element) {
  if (!element) return false;
  const rect = element.getBoundingClientRect();
  return (
    rect.top < window.innerHeight &&
    rect.bottom > 0 &&
    rect.left < window.innerWidth &&
    rect.right > 0
  );
};

window.previewViewerPostState = window.previewViewerPostState || Object.create(null);
window.previewViewerPostInflight = window.previewViewerPostInflight || Object.create(null);
window.previewViewerDebug = window.previewViewerDebug || {
  sent: 0,
  beacon: 0,
  skippedInflight: 0,
  skippedRecent: 0,
  failed: 0,
  byDevice: Object.create(null),
  events: []
};

function recordPreviewViewerDebugEvent(type, detail = {}) {
  const debug = window.previewViewerDebug || (window.previewViewerDebug = {});
  debug.byDevice = debug.byDevice || Object.create(null);
  debug.events = Array.isArray(debug.events) ? debug.events : [];

  const deviceID = String(detail.deviceID || "").trim();
  const event = {
    at: Math.round(performance.now()),
    type,
    deviceID,
    active: !!detail.active,
    useBeacon: !!detail.useBeacon,
    reason: detail.reason || ""
  };

  debug.events.push(event);

  while (debug.events.length > 80) {
    debug.events.shift();
  }

  if (deviceID) {
    const row = debug.byDevice[deviceID] || {
      sent: 0,
      beacon: 0,
      skippedInflight: 0,
      skippedRecent: 0,
      failed: 0
    };

    if (type === "sent") row.sent += 1;
    if (type === "beacon") row.beacon += 1;
    if (type === "skipped-inflight") row.skippedInflight += 1;
    if (type === "skipped-recent") row.skippedRecent += 1;
    if (type === "failed") row.failed += 1;

    row.lastAt = event.at;
    row.lastActive = event.active;
    debug.byDevice[deviceID] = row;
  }
}

window.setPreviewViewer = function (deviceID, active, useBeacon = false) {
  if (!deviceID) return;

  const cleanDeviceID = String(deviceID || "").trim();
  const nextActive = !!active;
  const now = Date.now();
  const stateKey = `${cleanDeviceID}:${nextActive ? "1" : "0"}`;
  const repeatMs = Number(window.previewViewerMinRepeatMs || 1200);
  const previous = window.previewViewerPostState[cleanDeviceID];

  window.previewViewerDebug.byDevice = window.previewViewerDebug.byDevice || Object.create(null);
  window.previewViewerDebug.events = Array.isArray(window.previewViewerDebug.events)
    ? window.previewViewerDebug.events
    : [];

  if (!useBeacon) {
    if (window.previewViewerPostInflight[stateKey]) {
      window.previewViewerDebug.skippedInflight += 1;
      recordPreviewViewerDebugEvent("skipped-inflight", {
        deviceID: cleanDeviceID,
        active: nextActive,
        useBeacon,
        reason: "same device/active request already in flight"
      });
      return;
    }

    if (
      previous &&
      previous.active === nextActive &&
      now - Number(previous.sentAt || 0) < repeatMs
    ) {
      window.previewViewerDebug.skippedRecent += 1;
      recordPreviewViewerDebugEvent("skipped-recent", {
        deviceID: cleanDeviceID,
        active: nextActive,
        useBeacon,
        reason: `same state sent ${now - Number(previous.sentAt || 0)}ms ago`
      });
      return;
    }
  }

  const payload = JSON.stringify({
    deviceID: cleanDeviceID,
    viewerId: window.previewViewerId,
    active: nextActive
  });

  window.previewViewerPostState[cleanDeviceID] = {
    active: nextActive,
    sentAt: now
  };

  if (useBeacon && navigator.sendBeacon) {
    window.previewViewerDebug.beacon += 1;
    recordPreviewViewerDebugEvent("beacon", {
      deviceID: cleanDeviceID,
      active: nextActive,
      useBeacon
    });

    navigator.sendBeacon(
      "/api/preview-viewer",
      new Blob([payload], { type: "application/json" })
    );
    return;
  }

  const fetcher = typeof window.dashboardTimedFetch === "function"
    ? window.dashboardTimedFetch
    : window.fetch.bind(window);

  window.previewViewerDebug.sent += 1;
  window.previewViewerPostInflight[stateKey] = true;

  recordPreviewViewerDebugEvent("sent", {
    deviceID: cleanDeviceID,
    active: nextActive,
    useBeacon
  });

  fetcher("/api/preview-viewer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: payload,
    keepalive: true
  })
    .catch(() => {
      window.previewViewerDebug.failed += 1;

      recordPreviewViewerDebugEvent("failed", {
        deviceID: cleanDeviceID,
        active: nextActive,
        useBeacon
      });
    })
    .finally(() => {
      delete window.previewViewerPostInflight[stateKey];
    });
};

(function bootstrapDashboardTransport() {
  if (typeof window.dashboardFetch !== "function") {
    window.dashboardFetch = function (url, options = {}) {
      return fetch(url, {
        credentials: "same-origin",
        ...options
      });
    };
  }

  if (typeof window.postJson !== "function") {
    window.postJson = async function (url, payload = {}) {
      const res = await dashboardFetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const text = await res.text();
      let data = {};

      if (text) {
        try {
          data = JSON.parse(text);
        } catch (_) {
          throw new Error(
            res.ok
              ? "Server returned an invalid response."
              : `Request failed: ${res.status}`
          );
        }
      }

      if (!res.ok || data.ok === false) {
        throw new Error(data.error || `Request failed: ${res.status}`);
      }

      return data;
    };
  }

  if (typeof window.refreshStatusData !== "function") {
    window.refreshStatusData = async function () {
      const res = await dashboardFetch("/api/status");
      const text = await res.text();
      const data = text ? JSON.parse(text) : {};

      if (!res.ok) {
        throw new Error(data.error || `Status failed: ${res.status}`);
      }

      return data;
    };
  }

  if (typeof window.startStatusStream !== "function") {
    window.startStatusStream = function () {
      if (
        window.statusEventSource &&
        window.statusEventSource.readyState !== EventSource.CLOSED
      ) {
        return;
      }

      if (window.statusEventSource) {
        window.statusEventSource.close();
        window.statusEventSource = null;
      }

      if (window.statusPollTimer) {
        clearInterval(window.statusPollTimer);
        window.statusPollTimer = null;
      }

      if (window.statusStreamWatchdogTimer) {
        clearInterval(window.statusStreamWatchdogTimer);
        window.statusStreamWatchdogTimer = null;
      }

      window.statusStreamLastMessageAt = Date.now();

      const pollStatusOnce = () => {
        refreshStatusData({ forceNetwork: true })
          .then(data => window.requestDashboardRenderSafe(data))
          .catch(err => console.error("[status-poll] failed", err));
      };

      const startStatusPolling = () => {
        if (!window.statusPollTimer) {
          pollStatusOnce();
          window.statusPollTimer = setInterval(pollStatusOnce, 10000);
        }
      };

      const stopStatusPolling = () => {
        if (!window.statusPollTimer) return;

        clearInterval(window.statusPollTimer);
        window.statusPollTimer = null;
      };

      const stopStatusStream = () => {
        if (window.statusEventSource) {
          window.statusEventSource.close();
          window.statusEventSource = null;
        }
      };

      const source = new EventSource("/api/status/stream", {
        withCredentials: true
      });

      window.statusEventSource = source;

      source.onopen = function () {
        window.statusStreamLastMessageAt = Date.now();
        stopStatusPolling();
      };

      source.addEventListener("heartbeat", function () {
        window.statusStreamLastMessageAt = Date.now();
      });

      source.onmessage = function (event) {
        window.statusStreamLastMessageAt = Date.now();

        try {
          const statusData = JSON.parse(event.data);
          const renderData = typeof window.applyDashboardStatusData === "function"
            ? window.applyDashboardStatusData(statusData, "status-stream")
            : statusData;

          window.requestDashboardRenderSafe(renderData);
        } catch (err) {
          console.error("[status-stream] render failed", err);
        }
      };

      source.onerror = function () {
        console.warn("[status-stream] disconnected; falling back to polling");
        startStatusPolling();
      };

      window.statusStreamWatchdogTimer = setInterval(() => {
        if (!window.statusEventSource) return;

        const age = Date.now() - Number(window.statusStreamLastMessageAt || 0);

        if (age <= 25000) return;

        console.warn("[status-stream] stale; falling back to polling");

        stopStatusStream();
        window.startStatusStream();
      }, 5000);
    };
  }
})();
