"use strict";

var S = window.appState;

/* ==========================================================================
  DEBUG LOG 
  ========================================================================== */

window.getDebugDisplayName = function (client) {
  const id = String(client?.clientName || "server").trim();

  if (id.toLowerCase() === "server") return "KotiBot Server";
  const roles = Array.isArray(client?.clientRole)
    ? client.clientRole
    : String(client?.clientRole || "UNP").split(",");

  const roleSet = roles.map(v => String(v).trim().toUpperCase());

  if (roleSet.includes("CAM") && roleSet.includes("DSS")) return `${id} Cam/Sensor`;
  if (roleSet.includes("CAM")) return `${id} Cam`;
  if (roleSet.includes("DSS")) return `${id} Sensor`;

  return id;
};

window.parseDebugClientName = function (line) {
  const parts = String(line || "").split("|").map(v => v.trim());
  return parts[2] || "server";
};

window.getDebugFilterNameByDeviceId = function (deviceId) {
  if (!deviceId) return "";
  if (deviceId === "server") return "KotiBot Server";

  const match = (S.currentClients || []).find(c => c.deviceID === deviceId);
  return match ? getDebugDisplayName(match) : "";
};

window.refreshDebugClientOptions = function () {
  const sel = document.getElementById("logClientFilter");
  if (!sel) return;

  const currentValue = sel.value;
  const options = new Map();

  options.set("server", "KotiBot Server");

  for (const c of (S.currentClients || [])) {
    if (!c.deviceID) continue;
    options.set(c.deviceID, getDebugDisplayName(c));
  }

  sel.innerHTML = `<option value="">All Clients / Server</option>` +
    Array.from(options.entries())
      .sort((a, b) => a[1].localeCompare(b[1]))
      .map(([value, label]) => `<option value="${esc(value)}">${esc(label)}</option>`)
      .join("");

  sel.value = Array.from(sel.options).some(o => o.value === currentValue) ? currentValue : "";
};

window.parseDebugLevel = function (line) {
  if (/\|\s⚪\s\|/.test(line)) return "DEBUG";
  if (/\|\s🟢\s\|/.test(line)) return "INFO";
  if (/\|\s🟡\s\|/.test(line)) return "WARNING";
  if (/\|\s🔴\s\|/.test(line)) return "ERROR";
  if (/\|\s🟣\s\|/.test(line)) return "CRITICAL";
  return "INFO";
};

window.applyLogFilters = function () {
  const box = document.getElementById("logBox");
  if (!box) return;

  const clientFilter = document.getElementById("logClientFilter")?.value || "";
  const showDebug = document.getElementById("debugLevelDebug")?.checked ?? true;
  const showInfo = document.getElementById("debugLevelInfo")?.checked ?? true;
  const showWarning = document.getElementById("debugLevelWarning")?.checked ?? true;
  const showError = document.getElementById("debugLevelError")?.checked ?? true;
  const showCritical = document.getElementById("debugLevelCritical")?.checked ?? true;

  const filtered = S.logLines.filter(line => {
    const level = parseDebugLevel(line);
    const lineClientName = parseDebugClientName(line);
    const selectedClientName = getDebugFilterNameByDeviceId(clientFilter);

    if (clientFilter && lineClientName !== selectedClientName) return false;
    if (level === "DEBUG" && !showDebug) return false;
    if (level === "INFO" && !showInfo) return false;
    if (level === "WARNING" && !showWarning) return false;
    if (level === "ERROR" && !showError) return false;
    if (level === "CRITICAL" && !showCritical) return false;

    return true;
  });

  box.value = filtered.join("\n");
  box.scrollTop = box.scrollHeight;
};

window.pushLogLine = function (line) {
  if (!line) return;

  S.logLines.push(line);

  if (S.logLines.length > S.DEBUG_LOG_MAX_LINES) {
    S.logLines = S.logLines.slice(-S.DEBUG_LOG_MAX_LINES);
  }

  refreshDebugClientOptions();
  applyLogFilters();
};

window.clearLogView = function () {
  S.logLines = [];
  refreshDebugClientOptions();
  applyLogFilters();
};

window.initLogView = async function () {
  if (!S.logLines.length) {
    try {
      const res = await dashboardFetch("/api/debug-log");
      const data = await res.json();
      S.logLines = Array.isArray(data.lines) ? data.lines : [];
    } catch (err) {
      S.logLines = [];
    }

    refreshDebugClientOptions();
    applyLogFilters();
  }

  if (S.logInterval) return;

  const pollLog = async () => {
    try {
      const res = await dashboardFetch("/api/debug-log");
      const data = await res.json();
      const newLines = Array.isArray(data.lines) ? data.lines : [];
      if (newLines.length !== S.logLines.length || newLines.some((line, i) => line !== S.logLines[i])) {
        S.logLines = newLines;
        refreshDebugClientOptions();
        applyLogFilters();
      }
    } catch (err) {
      console.warn("[log] poll error", err);
    }
  };

  // Poll every 5 seconds
  S.logInterval = setInterval(pollLog, 5000);
};