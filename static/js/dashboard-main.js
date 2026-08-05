"use strict";

window.dashboardLoadMark?.("dashboard-main loaded");

window.requestDashboardRender = window.requestDashboardRender || function (data) {
  if (typeof window.dashboardRequestRender === "function") {
    return window.dashboardRequestRender(data);
  }

  if (typeof window.render === "function") {
    return window.render(data);
  }
};

window.isDashboardScrollTapSuppressed = function () {
  return false;
};

async function fetchDashboardAuthStatus() {
  try {
    const fetcher = typeof window.dashboardTimedFetch === "function"
      ? window.dashboardTimedFetch
      : window.fetch.bind(window);

    const res = await fetcher("/api/security/status", {
      credentials: "same-origin",
      cache: "no-store"
    });

    if (!res.ok) return { ok: false, dashboard_authenticated: false };

    return await res.json();
  } catch (_) {
    return { ok: false, dashboard_authenticated: false };
  }
}

let dashboardAuthRecheckTimer = 0;

function syncDashboardAuthHeader() {
  const modal = document.getElementById("dashboardAuthModal");
  const form = document.getElementById("dashboardAuthForm");
  const shell = modal?.querySelector(".dashboard-auth-shell");

  if (!modal || !form || !shell) return;

  form.classList.add("dashboard-auth-form");

  const existingHeaders = Array.from(shell.children).filter(el => {
    if (el === form) return false;

    return el.matches?.(".dashboard-auth-brand, .dashboard-auth-hero") ||
      !!el.querySelector?.(".dashboard-auth-logo, .dashboard-home-logo");
  });

  let hero = existingHeaders[0];

  if (!hero) {
    hero = document.createElement("section");
  }

  hero.className = "dashboard-auth-hero dashboard-home-card dashboard-home-hero";
  hero.setAttribute("aria-label", "KotiBot login");

  hero.replaceChildren();

  const logo = document.createElement("img");
  logo.className = "dashboard-home-logo";
  logo.src = "/static/img/KotiBot.svg";
  logo.alt = "";
  hero.appendChild(logo);

  const titleWrap = document.createElement("div");
  titleWrap.className = "dashboard-home-title-wrap";
  hero.appendChild(titleWrap);

  const title = document.createElement("h1");
  title.className = "dashboard-home-title";
  title.textContent = "KotiBot";
  titleWrap.appendChild(title);

  const subtitle = document.createElement("div");
  subtitle.className = "dashboard-home-subtitle";
  subtitle.textContent = "Smart Home Command Center";
  titleWrap.appendChild(subtitle);

  shell.insertBefore(hero, form);

  existingHeaders.forEach(el => {
    if (el !== hero) el.remove();
  });

  form.querySelector(":scope > .dashboard-auth-form-title")?.remove();
  form.querySelector(":scope > .dashboard-auth-separator")?.remove();
  form.querySelectorAll(":scope > .dashboard-auth-brand, :scope > .dashboard-auth-hero, :scope > img").forEach(el => el.remove());
}

async function showDashboardAuthModal(message = "") {
  const modal = document.getElementById("dashboardAuthModal");
  const input = document.getElementById("dashboardAuthEmail");
  const error = document.getElementById("dashboardAuthError");

  if (!modal) return;

  syncDashboardAuthHeader();

  if (error) {
    error.textContent = message;
    error.style.display = message ? "" : "none";
  }

  if (dashboardAuthRecheckTimer) {
    clearTimeout(dashboardAuthRecheckTimer);
  }

  dashboardAuthRecheckTimer = setTimeout(async () => {
    dashboardAuthRecheckTimer = 0;

    const auth = await fetchDashboardAuthStatus();

    if (!auth.dashboard_authenticated) {
      return;
    }

    hideDashboardAuthModal();

    if (!dashboardStarted) {
      await startDashboard();
    }
  }, 250);

  modal.hidden = false;
  document.body.classList.add("dashboard-auth-required");

  setTimeout(() => input?.focus(), 0);
}

function hideDashboardAuthModal() {
  const modal = document.getElementById("dashboardAuthModal");
  const emailInput = document.getElementById("dashboardAuthEmail");
  const passwordInput = document.getElementById("dashboardAuthPassword");
  const error = document.getElementById("dashboardAuthError");

  if (dashboardAuthRecheckTimer) {
    clearTimeout(dashboardAuthRecheckTimer);
    dashboardAuthRecheckTimer = 0;
  }

  if (emailInput) emailInput.value = "";
  if (passwordInput) passwordInput.value = "";
  if (error) {
    error.textContent = "";
    error.style.display = "none";
  }

  if (modal) modal.hidden = true;
  document.body.classList.remove("dashboard-auth-required");
}

async function submitDashboardAuth(event) {
  event.preventDefault();

  const emailInput = document.getElementById("dashboardAuthEmail");
  const passwordInput = document.getElementById("dashboardAuthPassword");

  const email = String(emailInput?.value || "").trim();
  const password = String(passwordInput?.value || "");

  if (!email || !password) {
    await showDashboardAuthModal("Enter your email and password.");
    return;
  }

  try {
    const fetcher = typeof window.dashboardTimedFetch === "function"
      ? window.dashboardTimedFetch
      : window.fetch.bind(window);

    const res = await fetcher("/api/security/dashboard-login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    });

    const payload = await res.json().catch(() => ({}));

    if (!res.ok || !payload.ok) {
      const auth = await fetchDashboardAuthStatus();

      if (auth.dashboard_authenticated) {
        window.invalidateDashboardBootstrap?.("login confirmed after retry");
        hideDashboardAuthModal();
        await startDashboard();
        return;
      }

      await showDashboardAuthModal("Email or password was not accepted.");
      return;
    }

    window.invalidateDashboardBootstrap?.("login success");
    hideDashboardAuthModal();
    dashboardStarted = false;
    await startDashboard();
  } catch (_) {
    const auth = await fetchDashboardAuthStatus();

    if (auth.dashboard_authenticated) {
      window.invalidateDashboardBootstrap?.("login confirmed after error");
      hideDashboardAuthModal();
      await startDashboard();
      return;
    }

    await showDashboardAuthModal("Login request failed.");
  }
}

async function requireDashboardAuth() {
  window.dashboardLoadMark?.("auth check start");

  const bootstrapAuth = window.dashboardBootstrapAuthStatus?.();

  if (bootstrapAuth) {
    window.dashboardLoadMark?.("auth check finished", {
      authenticated: !!bootstrapAuth.dashboard_authenticated,
      source: "inline-bootstrap"
    });

    if (bootstrapAuth.dashboard_authenticated) {
      hideDashboardAuthModal();
      return true;
    }

    await showDashboardAuthModal();
    return false;
  }

  const auth = await fetchDashboardAuthStatus();
  window.dashboardLoadMark?.("auth check finished", {
    authenticated: !!auth.dashboard_authenticated,
    source: "network"
  });

  if (auth.dashboard_authenticated) {
    hideDashboardAuthModal();
    return true;
  }

  await showDashboardAuthModal();
  return false;
}

let dashboardStarted = false;

const dashboardSubsystemScriptPromises = window.dashboardSubsystemScriptPromises || new Map();
window.dashboardSubsystemScriptPromises = dashboardSubsystemScriptPromises;

function dashboardStaticScriptVersion() {
  return (
    window.KOTIBOT_STATIC_VERSION ||
    window.dashboardStaticVersion ||
    document.documentElement?.dataset?.staticVersion ||
    document.body?.dataset?.staticVersion ||
    String(Date.now())
  );
}

let dashboardModalStylesPromise = null;

function loadDashboardModalStyles() {
  if (dashboardModalStylesPromise) {
    return dashboardModalStylesPromise;
  }

  const existing = document.getElementById("dashboardModalCss");

  if (existing?.sheet) {
    dashboardModalStylesPromise = Promise.resolve();
    return dashboardModalStylesPromise;
  }

  const version = encodeURIComponent(dashboardStaticScriptVersion());

  dashboardModalStylesPromise = new Promise((resolve, reject) => {
    const link = existing || document.createElement("link");

    link.addEventListener("load", resolve, { once: true });
    link.addEventListener("error", () => {
      link.remove();
      dashboardModalStylesPromise = null;
      reject(new Error("Failed to load dashboard stylesheet: modals.css"));
    }, { once: true });

    if (!existing) {
      link.id = "dashboardModalCss";
      link.rel = "stylesheet";
      link.href = `/static/css/modals.css?v=${version}`;
      document.head.appendChild(link);
    }
  });

  return dashboardModalStylesPromise;
}

window.loadDashboardModalStyles = loadDashboardModalStyles;

function loadDashboardScriptUrl(key, src) {
  if (dashboardSubsystemScriptPromises.has(key)) {
    return dashboardSubsystemScriptPromises.get(key);
  }

  const scriptLoadStartedAt = window.dashboardLoadProfiler?.now?.();

  const promise = new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-dashboard-subsystem-script="${CSS.escape(key)}"]`);

    if (existing) {
      window.dashboardLoadMeasure?.(`load script ${key}`, scriptLoadStartedAt, { cached: true });
      resolve();
      return;
    }

    const script = document.createElement("script");

    script.src = src;
    script.dataset.dashboardSubsystemScript = key;
    script.async = false;
    script.onload = () => {
      window.dashboardLoadMeasure?.(`load script ${key}`, scriptLoadStartedAt);
      resolve();
    };
    script.onerror = () => {
      script.remove();
      dashboardSubsystemScriptPromises.delete(key);
      window.dashboardLoadMeasure?.(`load script ${key}`, scriptLoadStartedAt, { failed: true });
      reject(new Error(`Failed to load dashboard script: ${key}`));
    };
    document.head.appendChild(script);
  });

  dashboardSubsystemScriptPromises.set(key, promise);
  return promise;
}

function loadDashboardStaticScript(filename) {
  const version = encodeURIComponent(dashboardStaticScriptVersion());
  return loadDashboardScriptUrl(
    `static/${filename}`,
    `/static/${filename}?v=${version}`
  );
}

function loadDashboardSubsystemScript(subsystemName, filename) {
  const version = encodeURIComponent(dashboardStaticScriptVersion());
  return loadDashboardScriptUrl(
    `${subsystemName}/${filename}`,
    `/subsystems/${encodeURIComponent(subsystemName)}/static/${filename}?v=${version}`
  );
}

async function loadDashboardVoiceSubsystem() {
  if (window.dashboardViewerIsAndroidKeyClientApp?.() !== true) {
    window.dashboardLoadMark?.("deferred voice script load skipped", {
      reason: "not android key client"
    });
    return;
  }

  await loadDashboardSubsystemScript("voice", "js/voice-api.js");
  await loadDashboardSubsystemScript("voice", "js/voice-actions.js");
}

let dashboardMatterSubsystemReadyPromise = null;

function loadDashboardMatterSubsystem() {
  if (dashboardMatterSubsystemReadyPromise) {
    return dashboardMatterSubsystemReadyPromise;
  }

  window.dashboardMatterEnvironmentSettingsReady = false;

  dashboardMatterSubsystemReadyPromise = (async () => {
    await loadDashboardSubsystemScript("matter", "js/matter-render.js");

    if (typeof window.loadMatterEnvironmentSettings === "function") {
      await window.loadMatterEnvironmentSettings();
    }

    window.dashboardMatterEnvironmentSettingsReady = true;
  })().catch(err => {
    dashboardMatterSubsystemReadyPromise = null;
    window.dashboardMatterEnvironmentSettingsReady = false;
    throw err;
  });

  return dashboardMatterSubsystemReadyPromise;
}

async function loadDashboardEnvironmentSubsystem() {
  await loadDashboardSubsystemScript("environment", "js/environment-render.js");
}

window.loadDashboardVoiceSubsystem = loadDashboardVoiceSubsystem;
window.loadDashboardMatterSubsystem = loadDashboardMatterSubsystem;
window.loadDashboardEnvironmentSubsystem = loadDashboardEnvironmentSubsystem;

let dashboardPostPaintHydrationStarted = false;
let dashboardHydrationRenderTimer = 0;
let dashboardHydrationRenderData = null;

function renderDashboardData(data) {
  if (typeof window.requestDashboardRender === "function") {
    window.requestDashboardRender(data);
  } else {
    window.render(data);
  }
}

function queueDashboardHydrationRender(data = currentDashboardRenderData()) {
  dashboardHydrationRenderData = data;

  if (dashboardHydrationRenderTimer) return;

  dashboardHydrationRenderTimer = window.setTimeout(() => {
    dashboardHydrationRenderTimer = 0;
    const queuedData = dashboardHydrationRenderData || currentDashboardRenderData();
    dashboardHydrationRenderData = null;
    renderDashboardData(queuedData);
  }, 90);
}

function currentDashboardRenderData() {
  return {
    clients: S.currentClients || [],
    server: S.serverState || S.server || {},
    used_zones: S.currentUsedZones || []
  };
}

async function loadDashboardInitialTapoLightingState() {
  if (window.TAPO_LIGHTING_STATE?.loaded === true) {
    return window.TAPO_LIGHTING_STATE;
  }

  const fetcher = typeof window.dashboardFetch === "function"
    ? window.dashboardFetch
    : window.fetch.bind(window);
  const res = await fetcher(`/api/tapo/lighting-state?t=${Date.now()}`, {
    cache: "no-store"
  });
  const data = await res.json();

  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Tapo lighting state failed: ${res.status}`);
  }

  return window.applyDashboardTapoLightingState?.(data) || data;
}

async function prepareDashboardInitialPageRender() {
  const pageMode = window.cleanDashboardPage?.(S.activeDashboardPage) || S.activeDashboardPage || "home";
  const dependencies = [];

  if (
    ["monitor", "sensors"].includes(pageMode) &&
    typeof window.syncMatterRoomEnvironmentHeader !== "function"
  ) {
    dependencies.push(loadDashboardMatterSubsystem());
  }

  if (
    (pageMode === "monitor" && typeof window.renderCameraCard !== "function") ||
    (pageMode === "sensors" && typeof window.renderAndroidMotionSensorCard !== "function")
  ) {
    dependencies.push(
      loadDashboardSubsystemScript("client-android-home", "js/client-android-home-render.js")
    );
  }

  if (
    ["monitor", "sensors"].includes(pageMode) &&
    window.KOTIBOT_TAPO_ENABLED === true &&
    (
      (pageMode === "monitor" && typeof window.renderTapoCameraCard !== "function") ||
      (pageMode === "sensors" && typeof window.renderTapoClientCard !== "function")
    )
  ) {
    dependencies.push(
      loadDashboardSubsystemScript("client-tapo", "js/tapo-render.js")
    );
  }

  if (pageMode === "controls" && window.KOTIBOT_TAPO_ENABLED === true) {
    dependencies.push(
      loadDashboardSubsystemScript("client-tapo", "js/tapo-render.js"),
      loadDashboardInitialTapoLightingState()
    );
  }

  if (!dependencies.length) return;

  window.dashboardLoadMark?.(`initial ${pageMode} dependencies start`);

  const results = await Promise.allSettled(dependencies);
  const failed = results.filter(result => result.status === "rejected");

  for (const result of failed) {
    console.warn(`[dashboard-load] initial ${pageMode} dependency failed`, result.reason);
  }

  window.dashboardLoadMark?.(`initial ${pageMode} dependencies finished`, {
    failed: failed.length
  });
}

function updateDashboardPreviewState() {
  const cameras = (S.currentClients || []).filter(c =>
    c.provisioned && hasClientRole(c, "CAM")
  );

  window.updatePreviewViewerState?.(cameras);
}

async function loadDashboardInteractionScriptsAfterInitialPaint() {
  window.dashboardLoadMark?.("deferred interaction script load start");

  const results = [];

  results.push(await Promise.allSettled([
    loadDashboardSubsystemScript("automations", "js/automations-render.js"),
    loadDashboardSubsystemScript("client-android-home", "js/client-android-home-render.js"),
    loadDashboardStaticScript("js/dashboard-actions.js"),
    loadDashboardSubsystemScript("automations", "js/automations-actions.js"),
    loadDashboardModalStyles()
  ]));

  window.ensureDashboardModalShells?.();

  results.push(await Promise.allSettled([
    loadDashboardStaticScript("js/dashboard-events.js")
  ]));

  const flatResults = results.flat();
  const failed = flatResults.filter(result => result.status === "rejected");

  for (const result of failed) {
    console.warn("[dashboard-load] deferred interaction script load failed", result.reason);
  }

  try {
    await window.refreshRoutes?.();

    const pageMode = window.cleanDashboardPage?.(S.activeDashboardPage)
      || S.activeDashboardPage
      || "home";

    if (["controls", "monitor", "sensors"].includes(pageMode)) {
      queueDashboardHydrationRender(currentDashboardRenderData());
    }
  } catch (err) {
    console.warn("[dashboard-load] route and automation warmup failed", err);
  }

  window.dashboardLoadMark?.("deferred interaction script load finished", {
    failed: failed.length
  });
}

async function loadDashboardTapoScriptsAfterInitialPaint() {
  if (window.KOTIBOT_TAPO_ENABLED !== true) return;

  window.dashboardLoadMark?.("deferred Tapo script load start");

  const renderWasReady = typeof window.renderTapoClientCard === "function";
  const results = [];

  results.push(await Promise.allSettled([
    loadDashboardSubsystemScript("client-tapo", "js/tapo-render.js")
  ]));

  results.push(await Promise.allSettled([
    loadDashboardSubsystemScript("client-tapo", "js/tapo-actions.js")
  ]));

  const flatResults = results.flat();
  const failed = flatResults.filter(result => result.status === "rejected");

  for (const result of failed) {
    console.warn("[dashboard-load] deferred Tapo script load failed", result.reason);
  }

  window.dashboardLoadMark?.("deferred Tapo script load finished", {
    failed: failed.length
  });

  if (!renderWasReady) {
    queueDashboardHydrationRender(currentDashboardRenderData());
  }

  const pageMode = window.cleanDashboardPage?.(S.activeDashboardPage) || S.activeDashboardPage || "home";

  if (pageMode === "monitor") {
    window.initTapoCameraVideos?.();
  }
}

async function loadDashboardSubsystemsAfterInitialPaint() {
  window.dashboardLoadMark?.("deferred subsystem script load start");

  const pageMode = window.cleanDashboardPage?.(S.activeDashboardPage) || S.activeDashboardPage || "home";
  const loadMatterAfterPaint = pageMode === "home" || pageMode === "controls";
  const loaders = [
    loadDashboardVoiceSubsystem()
  ];

  if (loadMatterAfterPaint) {
    loaders.push(loadDashboardMatterSubsystem());
  } else {
    window.dashboardLoadMark?.("deferred matter script load skipped", {
      reason: "already loaded by the active page or lazy-loaded on Matter UI open"
    });
  }

  window.dashboardLoadMark?.("deferred environment script load skipped", {
    reason: "lazy-loaded on Environment UI open"
  });

  const results = await Promise.allSettled(loaders);
  const failed = results.filter(result => result.status === "rejected");

  for (const result of failed) {
    console.warn("[dashboard-load] deferred subsystem load failed", result.reason);
  }

  const matterRenderReady = pageMode === "home"
    ? typeof window.syncMatterFoundHomeSection === "function"
    : typeof window.syncMatterRoomEnvironmentHeader === "function";

  if (loadMatterAfterPaint && matterRenderReady) {
    queueDashboardHydrationRender(currentDashboardRenderData());
  }

  window.dashboardLoadMark?.("deferred subsystem script load finished", {
    failed: failed.length
  });
}

async function startTapoRefreshAfterInitialPaint() {
  if (typeof window.startTapoDeviceStateRefreshLoop !== "function") return;

  window.startTapoDeviceStateRefreshLoop();
}

function startDashboardPostPaintHydration() {
  if (dashboardPostPaintHydrationStarted) return;
  dashboardPostPaintHydrationStarted = true;

  const interactionScriptsTask = loadDashboardInteractionScriptsAfterInitialPaint().catch(err => {
    console.warn("[dashboard-load] deferred interaction script load error", err);
  });

  const tapoScriptsTask = loadDashboardTapoScriptsAfterInitialPaint()
    .then(() => startTapoRefreshAfterInitialPaint())
    .catch(err => {
      console.warn("[dashboard-load] deferred Tapo load error", err);
    });

  const subsystemTask = loadDashboardSubsystemsAfterInitialPaint().catch(err => {
    console.warn("[dashboard-load] deferred subsystem load error", err);
  });

  Promise.allSettled([
    interactionScriptsTask,
    tapoScriptsTask,
    subsystemTask
  ]).then(() => {
    window.dashboardLoadProfiler?.report?.("post-paint hydration");
  });

  window.startStatusStream();
}

async function startDashboard() {
  if (dashboardStarted) return;

  window.dashboardLoadMark?.("dashboard start requested");

  const authed = await requireDashboardAuth();
  if (!authed) return;

  dashboardStarted = true;
  hideDashboardAuthModal();

  window.dashboardLoadMark?.("initial dashboard data start");
  const data = await refreshStatusData();
  window.dashboardLoadMark?.("initial dashboard data finished", {
    clients: Array.isArray(data?.clients) ? data.clients.length : 0,
    source: data?._dashboardBootstrapSource || "network"
  });

  await prepareDashboardInitialPageRender();

  window.dashboardLoadMark?.("initial dashboard render start");
  renderDashboardData(data);
  window.dashboardLoadMark?.("initial dashboard render finished");

  updateDashboardPreviewState();

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      window.dashboardLoadMark?.("initial dashboard paint finished");
      window.dashboardInitialPaintDone = true;
      window.dispatchEvent(new CustomEvent("dashboard:initial-paint"));
      window.dashboardLoadProfiler?.report?.("initial page load");

      if (typeof drawConnections === "function") drawConnections();

      startDashboardPostPaintHydration();
    });
  });
}

window.logoutDashboardSecurity = function () {
  return window.logoutDashboard?.();
};

window.logoutDashboard = async function () {
  const fetcher = typeof window.dashboardTimedFetch === "function"
    ? window.dashboardTimedFetch
    : window.fetch.bind(window);

  await fetcher("/api/security/dashboard-logout", {
    method: "POST",
    credentials: "same-origin"
  }).catch(() => {});

  location.reload();
};


window.applyLogFilters = function () {
  const logBox = document.getElementById("logBox");
  if (!logBox) return;

  // Placeholder hook for the debug log UI. If logs are populated elsewhere, that
  // code can replace this without changing event routing.
};

/* ==========================================================================
  GLOBAL LISTENERS
  ========================================================================== */

function runPowerTogglePressAnimation(target) {
  if (!target || target.disabled || target.classList.contains("disabled")) return;

  target.classList.remove("power-toggle-press");
  void target.offsetWidth;
  target.classList.add("power-toggle-press");
}

document.addEventListener("pointerdown", (event) => {
  const target = event.target?.closest?.(".power-toggle");
  if (!target) return;

  runPowerTogglePressAnimation(target);
}, { passive: true });

document.addEventListener("click", (event) => {
  if (event.detail !== 0) return;

  const target = event.target?.closest?.(".power-toggle");
  if (!target) return;

  runPowerTogglePressAnimation(target);
}, true);

document.addEventListener("animationend", (event) => {
  const target = event.target;

  if (!target?.classList?.contains("power-toggle")) return;
  if (!target.classList.contains("power-toggle-press")) return;

  target.classList.remove("power-toggle-press");
}, true);

document.addEventListener("keydown", (e) => {
  if (e.ctrlKey && e.key.toLowerCase() === "d") {
    e.preventDefault();
    toggleDebug();
  }

  if (e.key === "Escape" && document.getElementById("cameraVideoModal")?.hidden === false) {
    e.preventDefault();
    window.hideCameraVideoModal?.();
  }
});

document.addEventListener("click", (event) => {

  const closeVideoButton = event.target?.closest?.('[data-dashboard-action="hide-camera-video"]');
  if (closeVideoButton) {
    event.preventDefault();
    event.stopPropagation();
    window.hideCameraVideoModal?.();
    return;
  }

  const cameraOpenTarget = event.target?.closest?.("[data-camera-video-open]");
  if (!cameraOpenTarget) return;

  if (
    event.target.closest(
      "button, a, input, select, textarea, label, .card-actions, .menu-content, [data-dashboard-stop-click]"
    )
  ) {
    return;
  }

  const deviceID = cameraOpenTarget.dataset.deviceId || cameraOpenTarget.closest(".cameracard")?.dataset.deviceId || "";
  if (!deviceID) return;

  event.preventDefault();
  window.openCameraVideo?.(deviceID);
});

document.getElementById("dashboardAuthForm")?.addEventListener("submit", submitDashboardAuth);

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", syncDashboardAuthHeader, { once: true });
} else {
  syncDashboardAuthHeader();
}

/* ==========================================================================
  INITIALIZATION & STARTUP
  ========================================================================== */

const savedInfoShown = localStorage.getItem("dashboardInfoShown");

if (savedInfoShown === "0") {
  document.body.classList.add("debug-off");
} else if (savedInfoShown === "1") {
  document.body.classList.remove("debug-off");
} else {
  document.body.classList.toggle("debug-off", !S.debugMode);
}

document.getElementById("sectionClients").style.display = "none";
document.getElementById("sectionEmpty").style.display = "none";
document.getElementById("sectionLog").style.display = "none";

// Automatic heartbeats removed. Now waiting for server pulse via SSE.

document.addEventListener("visibilitychange", () => {
  const cameras = (S.currentClients || []).filter(c =>
    c.provisioned && hasClientRole(c, "CAM")
  );

  window.updatePreviewViewerState?.(cameras);
});

localStorage.removeItem("dashboardSpacing");
document.body.removeAttribute("data-spacing");
document.body.dataset.groupByRoom = S.groupByRoom ? "1" : "0";
window.bindDashboardSystemTheme?.();

function syncDashboardLayoutMode() {
  const aspectQuery = window.matchMedia?.("(max-aspect-ratio: 2/3)");
  let portraitLayout = !!aspectQuery?.matches;

  if (!aspectQuery) {
    const width = Math.max(1, window.innerWidth || document.documentElement.clientWidth || 1);
    const height = Math.max(1, window.innerHeight || document.documentElement.clientHeight || 1);

    portraitLayout = (width / height) <= (2 / 3);
  }

  const nextLayout = portraitLayout ? "portrait" : "landscape";
  const previousLayout = document.body.dataset.dashboardLayout || "";

  document.body.dataset.dashboardLayout = nextLayout;

  return nextLayout !== previousLayout;
}

syncDashboardLayoutMode();

startDashboard();

let dashboardResizeRenderTimer = 0;

window.addEventListener("resize", () => {
  const layoutChanged = syncDashboardLayoutMode();
  window.syncServerViewControls?.();

  window.requestAnimationFrame(() => {
    window.syncDashboardAsideFit?.();
  });

  if ((layoutChanged || S.groupByRoom) && S.currentClients) {
    clearTimeout(dashboardResizeRenderTimer);
    dashboardResizeRenderTimer = setTimeout(() => {
      const data = {
        clients: S.currentClients,
        server: S.serverState || S.server || {},
        used_zones: S.currentUsedZones || []
      };

      if (typeof window.requestDashboardRender === "function") {
        window.requestDashboardRender(data);
      } else {
        window.render(data);
      }
    }, 80);
  }

  const cameras = (S.currentClients || []).filter(c =>
    c.provisioned && hasClientRole(c, "CAM")
  );

  window.updatePreviewViewerState?.(cameras);

  if (typeof drawConnections === "function") drawConnections();
});

let previewViewportSyncTimer = 0;

window.addEventListener("scroll", () => {
  if (previewViewportSyncTimer) return;

  previewViewportSyncTimer = setTimeout(() => {
    previewViewportSyncTimer = 0;

    const cameras = (S.currentClients || []).filter(c =>
      c.provisioned && hasClientRole(c, "CAM")
    );

    window.updatePreviewViewerState?.(cameras);
  }, 250);
}, { passive: true });

window.renderDashboard = function () {
  window.requestDashboardRender({
    clients: S.currentClients || [],
    server: S.serverState || S.server || {},
    used_zones: S.currentUsedZones || []
  });

  window.applyCardDebugVisibility?.();
};

window.showView = function (view, options = {}) {
  const renderView = options.render !== false;
  const renderAside = options.renderAside !== false;

  S.activeView = view;
  document.title = view === "debug" ? "KotiBot Logs" : "KotiBot Dashboard";
  document.body.classList.toggle("debug-view", view === "debug");

  document.getElementById("sectionClients").style.display = "none";
  document.getElementById("sectionEmpty").style.display = "none";
  document.getElementById("sectionLog").style.display = "none";

  if (typeof clearRouteSelection === "function") {
    clearRouteSelection();
  }

  if (renderAside) {
    renderDashboardAside();
  }

  if (view === "debug") {
    window.updatePreviewViewerState?.([]);
    document.getElementById("sectionLog").style.display = "";
    initLogView();
    return;
  }

  if (renderView) {
    window.requestDashboardRender({
      clients: S.currentClients || [],
      server: S.serverState || S.server || {},
      used_zones: S.currentUsedZones || []
    });
  }
};

window.updatePreviewViewerState = function (cameras) {
  const shouldPreview =
    S.activeView !== "debug" &&
    !document.hidden;

  const androidCameras = (cameras || []).filter(c => {
    return !(hasClientRole(c || {}, "TAPO") && c?.tapo_kind === "camera");
  });

  const nextIds = new Set();

  if (shouldPreview) {
    for (const c of androidCameras) {
      const deviceID = c.deviceID;
      if (!deviceID) continue;

      const card = document.querySelector(`.cameracard[data-device-id="${CSS.escape(deviceID)}"]`);
      if (!card) continue;

      if (typeof isElementInViewport === "function" && !isElementInViewport(card)) {
        continue;
      }

      nextIds.add(deviceID);
    }
  }

  for (const deviceID of window.previewActiveDeviceIds) {
    if (!nextIds.has(deviceID)) {
      setPreviewViewer(deviceID, false);
    }
  }

  for (const deviceID of nextIds) {
    if (!window.previewActiveDeviceIds.has(deviceID)) {
      setPreviewViewer(deviceID, true);
    }
  }

  window.previewActiveDeviceIds = nextIds;
};