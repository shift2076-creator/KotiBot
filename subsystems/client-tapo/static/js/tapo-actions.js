const tapoCommandInFlight = new Set();
const tapoPendingPowerState = new Map();
const TAPO_WHITE_SATURATION_DEFAULT = 1;
const TAPO_WHITE_TEMPERATURE_PRESETS = [
  { label: "Soft", kelvin: 2700 },
  { label: "Warm", kelvin: 3200 },
  { label: "Cool", kelvin: 3700 },
  { label: "Bright", kelvin: 4200 }
];

function tapoPendingPowerKey(deviceID, childID = "") {
  return [deviceID || "", childID || ""].filter(Boolean).join(":");
}

function setTapoPendingPowerState(deviceID, isOn, childID = "", ms = 30000) {
  const key = tapoPendingPowerKey(deviceID, childID);
  if (!key) return;

  tapoPendingPowerState.set(key, {
    isOn: !!isOn,
    until: Date.now() + ms
  });
}

function getTapoPendingPowerState(deviceID, childID = "") {
  const key = tapoPendingPowerKey(deviceID, childID);
  if (!key) return null;

  const pending = tapoPendingPowerState.get(key);
  if (!pending) return null;

  if (Date.now() > pending.until) {
    tapoPendingPowerState.delete(key);
    return null;
  }

  return pending;
}

function clearTapoPendingPowerState(deviceID, childID = "") {
  const key = tapoPendingPowerKey(deviceID, childID);
  if (key) tapoPendingPowerState.delete(key);
}

function tapoPendingPowerStillMatches(deviceID, expectedIsOn, childID = "") {
  const pending = getTapoPendingPowerState(deviceID, childID);

  return pending && pending.isOn === !!expectedIsOn;
}

async function loadTapoRechargeData() {
  const res = await dashboardFetch("/api/tapo/recharge");
  const contentType = String(res.headers.get("content-type") || "").toLowerCase();

  if (!res.ok) {
    throw new Error(`Tapo recharge route failed: HTTP ${res.status}`);
  }

  if (!contentType.includes("application/json")) {
    throw new Error("Tapo recharge route returned non-JSON data");
  }

  const data = await res.json();

  if (!data.ok) {
    throw new Error(data.error || "Tapo recharge settings failed to load");
  }

  window.tapoRechargeData = data;
  return data;
}

async function saveTapoRechargeSettings(button) {
  const clientSelect = document.getElementById("tapoRechargeClient");
  const targetInput = document.getElementById("tapoRechargeTarget");

  const deviceID = clientSelect?.value || "";
  const targetID = targetInput?.value || "";

  if (!deviceID || !targetID) return;

  button.disabled = true;

  try {
    const res = await dashboardFetch("/api/tapo/recharge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        deviceID,
        targetID,
        enabled: true
      })
    });

    const data = await res.json();

    if (!data.ok) {
      throw new Error(data.error || "Tapo recharge settings failed to save");
    }

    window.tapoRechargeData = {
      ...(window.tapoRechargeData || {}),
      recharge: data.rules || []
    };

    const modal = document.getElementById("tapoLightModal");
    if (modal) {
      modal.dataset.tapoRechargeMode = "list";
      modal.dataset.tapoRechargeExpanded = "0";
    }

    await refreshTapoRechargeSettingsPanel();
  } catch (error) {
    console.error("[saveTapoRechargeSettings] failed", error);
    alert(error.message || error);
  } finally {
    button.disabled = false;
  }
}

async function refreshTapoRechargeSettingsPanel(data = null) {
  const modal = document.getElementById("tapoLightModal");
  const panel = document.getElementById("tapoRechargePanel");

  if (!modal || !panel) return;

  const deviceID = data?.deviceId || modal.dataset.deviceId || "";
  const tapoKind = data?.tapoKind || modal.dataset.tapoKind || "";
  const isPlug = tapoKind === "plug";
  const isOutletExtender = tapoKind === "outlet_extender";
  const targetID =
    data?.tapoRechargeTargetId
    || modal.dataset.tapoRechargeTargetId
    || (isPlug ? `${deviceID}|` : "");
  const mode = modal.dataset.tapoRechargeMode || "list";
  const expanded = modal.dataset.tapoRechargeExpanded === "1";
  const title = document.getElementById("tapoLightTitle");
  const baseTitle = modal.dataset.tapoBaseTitle || title?.textContent || "Tapo";

  if (title) {
    title.textContent = mode === "add" ? `${baseTitle} - Automations` : baseTitle;
  }

  if (!deviceID || (!isPlug && !isOutletExtender)) {
    panel.innerHTML = "";
    return;
  }

  try {
    const rechargeData = await loadTapoRechargeData();

    panel.innerHTML = renderTapoRechargePanel(rechargeData, {
      targetDeviceID: deviceID,
      targetID,
      mode,
      expanded
    });
  } catch (error) {
    panel.innerHTML = `
      <div class="tapo-recharge-error">${esc(String(error?.message || error))}</div>
    `;
  }
}

let tapoEnergyRequestSerial = 0;

function tapoEnergyDatasetNumber(value) {
  if (value === null || value === undefined || value === "") return null;

  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function tapoEnergyReadingFromDataset(data = {}) {
  return {
    supported: data.tapoSupportsEnergy === "1",
    available: data.tapoEnergyAvailable === "1",
    error: String(data.tapoEnergyError || ""),
    updatedAt: tapoEnergyDatasetNumber(data.tapoEnergyUpdatedAt),
    currentPowerW: tapoEnergyDatasetNumber(data.tapoCurrentPowerW),
    todayEnergyKWh: tapoEnergyDatasetNumber(data.tapoTodayEnergyKwh),
    monthEnergyKWh: tapoEnergyDatasetNumber(data.tapoMonthEnergyKwh),
    todayRuntimeMinutes: tapoEnergyDatasetNumber(data.tapoTodayRuntimeMinutes),
    monthRuntimeMinutes: tapoEnergyDatasetNumber(data.tapoMonthRuntimeMinutes)
  };
}

function tapoEnergyHasValues(reading = {}) {
  return [
    reading.currentPowerW,
    reading.todayEnergyKWh,
    reading.monthEnergyKWh,
    reading.todayRuntimeMinutes,
    reading.monthRuntimeMinutes
  ].some(value => tapoEnergyDatasetNumber(value) !== null);
}

function tapoEnergySum(readings, key) {
  const values = readings
    .map(reading => tapoEnergyDatasetNumber(reading?.[key]))
    .filter(value => value !== null);

  return values.length
    ? values.reduce((total, value) => total + value, 0)
    : null;
}

function tapoAggregateEnergyChildren(device = {}) {
  const children = Array.isArray(device.children)
    ? device.children.filter(child => child?.supported === true)
    : [];

  if (!children.length || tapoEnergyHasValues(device)) {
    return device;
  }

  const updatedValues = children
    .map(child => tapoEnergyDatasetNumber(child?.updatedAt))
    .filter(value => value !== null);
  const errors = children
    .filter(child => child?.error)
    .map(child => `${child.name || "Outlet"}: ${child.error}`);

  return {
    ...device,
    supported: true,
    available: children.some(child => child.available === true),
    error: errors.join("; "),
    updatedAt: updatedValues.length ? Math.max(...updatedValues) : null,
    currentPowerW: tapoEnergySum(children, "currentPowerW"),
    todayEnergyKWh: tapoEnergySum(children, "todayEnergyKWh"),
    monthEnergyKWh: tapoEnergySum(children, "monthEnergyKWh"),
    todayRuntimeMinutes: tapoEnergySum(children, "todayRuntimeMinutes"),
    monthRuntimeMinutes: tapoEnergySum(children, "monthRuntimeMinutes")
  };
}

function tapoEnergyTarget(data, deviceID, childID = "") {
  const devices = Array.isArray(data?.devices) ? data.devices : [];
  const device = devices.find(item => {
    return String(item?.deviceID || "") === String(deviceID || "");
  });

  if (!device) return null;

  if (!childID) {
    return tapoAggregateEnergyChildren(device);
  }

  const children = Array.isArray(device.children) ? device.children : [];

  return children.find(child => {
    const targetID = String(child?.targetID || "");
    const targetChildID = targetID.includes("|")
      ? targetID.slice(targetID.indexOf("|") + 1)
      : "";

    return (
      String(child?.id || "") === String(childID)
      || targetChildID === String(childID)
    );
  }) || null;
}

function writeTapoEnergyDataset(target, reading = {}) {
  if (!target) return;

  const write = (key, value) => {
    target.dataset[key] = value === null || value === undefined
      ? ""
      : String(value);
  };

  write("tapoSupportsEnergy", reading.supported === true ? "1" : "0");
  write("tapoEnergyAvailable", reading.available === true ? "1" : "0");
  write("tapoEnergyError", reading.error || "");
  write("tapoEnergyUpdatedAt", reading.updatedAt);
  write("tapoCurrentPowerW", reading.currentPowerW);
  write("tapoTodayEnergyKwh", reading.todayEnergyKWh);
  write("tapoMonthEnergyKwh", reading.monthEnergyKWh);
  write("tapoTodayRuntimeMinutes", reading.todayRuntimeMinutes);
  write("tapoMonthRuntimeMinutes", reading.monthRuntimeMinutes);
}

async function loadTapoEnergyData(force = false) {
  const res = await dashboardFetch(
    force ? "/api/tapo/energy/refresh" : "/api/tapo/energy",
    force ? { method: "POST" } : undefined
  );
  const contentType = String(res.headers.get("content-type") || "").toLowerCase();

  if (!res.ok) {
    throw new Error(`Tapo energy route failed: HTTP ${res.status}`);
  }

  if (!contentType.includes("application/json")) {
    throw new Error("Tapo energy route returned non-JSON data");
  }

  const data = await res.json();

  if (!data.ok) {
    throw new Error(data.error || "Tapo energy data failed to load");
  }

  window.tapoEnergyData = data;
  return data;
}

async function refreshTapoEnergyPanel(data = null, options = {}) {
  const modal = document.getElementById("tapoLightModal");
  const section = document.getElementById("tapoEnergySection");
  const panel = document.getElementById("tapoEnergyPanel");

  if (!modal || !section || !panel) return;

  const source = data || modal.dataset;
  const deviceID = String(source.deviceId || modal.dataset.deviceId || "");
  const childID = String(source.tapoChildId || modal.dataset.tapoChildId || "");
  const initialReading = tapoEnergyReadingFromDataset(source);
  const cachedReading = tapoEnergyTarget(
    window.tapoEnergyData,
    deviceID,
    childID
  );
  const reading = cachedReading || initialReading;
  const tapoKind = String(source.tapoKind || modal.dataset.tapoKind || "");
  const canQueryEnergy = tapoKind === "plug" || tapoKind === "outlet_extender";
  const force = options.force === true;
  const requestID = String(++tapoEnergyRequestSerial);

  modal.dataset.tapoEnergyRequestId = requestID;

  if (modal.dataset.roomSettings === "1" || !canQueryEnergy) {
    section.hidden = true;
    panel.innerHTML = "";
    return;
  }

  section.hidden = reading.supported !== true;
  panel.innerHTML = section.hidden
    ? ""
    : window.renderTapoEnergyPanel?.({
        reading,
        loading: true
      }) || "";

  try {
    let energyData = await loadTapoEnergyData(force);

    if (modal.dataset.tapoEnergyRequestId !== requestID) return;

    let nextReading = tapoEnergyTarget(energyData, deviceID, childID);

    if (
      !force
      && nextReading?.supported
      && nextReading.available !== true
      && !tapoEnergyHasValues(nextReading)
      && !String(nextReading.error || "").trim()
    ) {
      section.hidden = false;
      panel.innerHTML = window.renderTapoEnergyPanel?.({
        reading: nextReading,
        loading: true
      }) || "";

      energyData = await loadTapoEnergyData(true);

      if (modal.dataset.tapoEnergyRequestId !== requestID) return;

      nextReading = tapoEnergyTarget(energyData, deviceID, childID);
    }

    if (!nextReading?.supported) {
      section.hidden = true;
      panel.innerHTML = "";
      return;
    }

    section.hidden = false;
    writeTapoEnergyDataset(modal, nextReading);
    panel.innerHTML = window.renderTapoEnergyPanel?.({
      reading: nextReading,
      busy: energyData.busy === true
    }) || "";
  } catch (error) {
    if (modal.dataset.tapoEnergyRequestId !== requestID) return;

    panel.innerHTML = window.renderTapoEnergyPanel?.({
      reading,
      error: String(error.message || error)
    }) || "";
  }
}

function tapoDeviceIDList(value) {
  return String(value || "")
    .split(",")
    .map(deviceID => deviceID.trim())
    .filter(Boolean);
}

function tapoClientChildID(client) {
  return String(client?.tapo_child_id || client?.tapoChildId || "").trim();
}

function tapoResolveDashboardDeviceTarget(deviceID, childID = "") {
  const cleanID = String(deviceID || "").trim();
  const cleanChildID = String(childID || "").trim();
  const client = (S.currentClients || []).find(item => String(item?.deviceID || "") === cleanID);

  if (client?.tapo_parent_device_id) {
    return {
      deviceID: String(client.tapo_parent_device_id || "").trim(),
      childID: cleanChildID || tapoClientChildID(client),
      childPosition: client.tapo_child_position ?? "",
      childIndex: client.tapo_child_index ?? ""
    };
  }

  return {
    deviceID: cleanID,
    childID: cleanChildID,
    childPosition: "",
    childIndex: ""
  };
}

function tapoChildCommandValue(target = {}) {
  if (!target.childID) return undefined;

  return {
    child_id: target.childID,
    position: target.childPosition ?? "",
    child_index: target.childIndex ?? ""
  };
}

function tapoDelay(ms) {
  return new Promise(resolve => window.setTimeout(resolve, ms));
}

async function waitForTapoCommandSlot(commandKey, maxWaitMs = 45000) {
  const started = Date.now();

  while (tapoCommandInFlight.has(commandKey)) {
    if (Date.now() - started > maxWaitMs) {
      throw new Error(`Timed out waiting for Tapo command slot: ${commandKey}`);
    }

    await tapoDelay(75);
  }
}

function tapoRefreshClientForDevice(data, deviceID) {
  if (!Array.isArray(data?.clients) || !deviceID) return null;

  return data.clients.find(client => {
    return String(client?.deviceID || client?._client_deviceID || "") === String(deviceID);
  }) || null;
}

function tapoRefreshPowerMatches(client, expectedIsOn, childID = "") {
  if (!client) return false;

  if (!childID) {
    const current = tapoBool(client.is_on ?? client.tapo_is_on ?? client.device_on ?? client.state);
    return current === expectedIsOn;
  }

  const children = Array.isArray(client.children)
    ? client.children
    : Array.isArray(client.tapo_children)
      ? client.tapo_children
      : [];

  return children.some((child, index) => {
    if (!child || typeof child !== "object") return false;

    const currentChildID = String(
      child.id
      ?? child.device_id
      ?? child.deviceId
      ?? child.child_id
      ?? child.childId
      ?? child.index
      ?? index + 1
    ).trim();

    if (currentChildID !== String(childID)) return false;

    const current = tapoBool(child.is_on ?? child.device_on ?? child.on ?? child.state);
    return current === expectedIsOn;
  });
}

function scheduleTapoCommandRefresh(delay = 750) {
  window.clearTimeout(window.__tapoCommandRefreshTimer);
  window.__tapoCommandRefreshTimer = window.setTimeout(() => {
    refreshTapoDashboardView().catch(err => {
      console.warn("[scheduleTapoCommandRefresh] background refresh failed", err);
    });
  }, delay);
}

async function refreshTapoPowerAfterCommand(deviceIDs, expectedIsOn, childID = "") {
  const ids = Array.from(new Set(
    (Array.isArray(deviceIDs) ? deviceIDs : [deviceIDs])
      .map(deviceID => String(deviceID || "").trim())
      .filter(Boolean)
  ));

  if (!ids.length) return false;

  scheduleTapoCommandRefresh(750);

  ids.forEach(deviceID => {
    if (!tapoPendingPowerStillMatches(deviceID, expectedIsOn, childID)) return;

    updateTapoCardState({
      deviceID,
      is_on: childID ? undefined : expectedIsOn,
      tapo_is_on: childID ? undefined : expectedIsOn,
      device_on: childID ? undefined : expectedIsOn,
      state: childID ? undefined : expectedIsOn,
      children: childID
        ? [{
          id: childID,
          is_on: expectedIsOn
        }]
        : undefined
    });
  });

  return true;
}

function applyTapoPendingPowerState(device) {
  if (!device || typeof device !== "object") return device;

  const deviceID = device.deviceID || device._client_deviceID || "";
  if (!deviceID) return device;

  const patch = { ...device };
  const children = Array.isArray(patch.children)
    ? patch.children
    : Array.isArray(patch.tapo_children)
      ? patch.tapo_children
      : [];

  const devicePending = getTapoPendingPowerState(deviceID);

  if (devicePending) {
    patch.is_on = devicePending.isOn;
    patch.tapo_is_on = devicePending.isOn;
    patch.device_on = devicePending.isOn;
    patch.state = devicePending.isOn;
  }

  if (children.length) {
    const patchedChildren = children.map((child, index) => {
      if (!child || typeof child !== "object") return child;

      const childID = String(
        child.id
        ?? child.device_id
        ?? child.deviceId
        ?? child.child_id
        ?? child.childId
        ?? child.index
        ?? index + 1
      ).trim();

      const childPending = getTapoPendingPowerState(deviceID, childID);
      if (!childPending) return child;

      return {
        ...child,
        is_on: childPending.isOn,
        device_on: childPending.isOn,
        on: childPending.isOn,
        state: childPending.isOn
      };
    });

    patch.children = patchedChildren;
    patch.tapo_children = patchedChildren;
  }

  return patch;
}

window.applyTapoPendingPowerStatesToDashboardData = function (data) {
  if (!data || !Array.isArray(data.clients)) return data;

  return {
    ...data,
    clients: data.clients.map(client => applyTapoPendingPowerState(client))
  };
};

function requestTapoDashboardRenderSafe(data) {
  if (typeof window.requestDashboardRender === "function") {
    return window.requestDashboardRender(data);
  }

  if (typeof window.render === "function") {
    return window.render(data);
  }
}

function clientHasTapoPowerDevice(c) {
  const roles = Array.isArray(c.clientRole)
    ? c.clientRole
    : String(c.clientRole || "").split(",");

  const hasTapoRole = roles
    .map(role => String(role).trim().toUpperCase())
    .includes("TAPO");

  if (!hasTapoRole || !c.provisioned) {
    return false;
  }

  if (c.tapo_dashboard_section === "camera") {
    return false;
  }

  return (
    c.tapo_supports_power &&
    ["bulb", "lightstrip", "plug", "outlet_extender"].includes(String(c.tapo_kind || "").toLowerCase())
  );
}

window.refreshTapoDeviceStatesNow = async function () {
  if (window.__tapoDeviceStateRefreshBusy) return;

  const clients = Array.isArray(window.appState?.currentClients)
    ? window.appState.currentClients
    : [];

  if (!clients.some(clientHasTapoPowerDevice)) {
    return;
  }

  window.__tapoDeviceStateRefreshBusy = true;

  try {
    await refreshTapoDeviceStates();

    const data = await refreshStatusData();
    requestTapoDashboardRenderSafe(data);
  } catch (err) {
    console.warn("[tapo-refresh] failed", err);
  } finally {
    window.__tapoDeviceStateRefreshBusy = false;
  }
};

window.refreshTapoDeviceStatesSoon = function (delay = 0) {
  if (window.__tapoDeviceStateRefreshDelay) {
    clearTimeout(window.__tapoDeviceStateRefreshDelay);
  }

  window.__tapoDeviceStateRefreshDelay = setTimeout(() => {
    window.__tapoDeviceStateRefreshDelay = null;
    refreshTapoDeviceStatesNow();
  }, delay);
};

window.startTapoDeviceStateRefreshLoop = function () {
  return;
};

function updateTapoRoomPowerButtonsForDevices(deviceIDs, expectedIsOn) {
  const ids = new Set(tapoDeviceIDList(deviceIDs));
  if (!ids.size) return;

  document.querySelectorAll('[data-tapo-action="room-on"], [data-tapo-action="room-off"]').forEach(button => {
    const buttonIds = tapoDeviceIDList(button.dataset.tapoDeviceIds || "");
    if (!buttonIds.length) return;
    if (!buttonIds.every(deviceID => ids.has(deviceID))) return;

    const isOn = !!expectedIsOn;
    const title = isOn ? "Turn off room power" : "Turn on room power";

    button.dataset.tapoAction = isOn ? "room-off" : "room-on";
    button.dataset.tapoPowerState = isOn ? "on" : "off";
    button.classList.toggle("active", isOn);
    button.classList.remove("unknown");
    button.title = title;
    button.setAttribute("aria-label", title);
  });
}

let tapoLightingStateSaveTimer = null;
let tapoLightingStateLoadPromise = null;

window.TAPO_LIGHTING_STATE = window.TAPO_LIGHTING_STATE || {
  schemes: {},
  activeSchemes: {},
  modeConfig: {},
  loaded: false
};

function renderTapoDashboardFromCurrentState() {
  const state = window.appState || {};
  const data = {
    clients: Array.isArray(state.currentClients) ? state.currentClients : [],
    server: state.serverState || state.server || {},
    used_zones: Array.isArray(state.currentUsedZones) ? state.currentUsedZones : []
  };

  requestTapoDashboardRenderSafe(data);
}

function loadTapoLightingStateAfterInitialPaint() {
  if (getTapoLightingState().loaded) {
    clearLegacyTapoLocalLightingState();
    return;
  }

  const loadLightingState = () => {
    window.dashboardLoadMark?.("deferred Tapo lighting state load start");

    loadTapoLightingState()
      .then(() => {
        window.dashboardLoadMark?.("deferred Tapo lighting state load finished");
        renderTapoDashboardFromCurrentState();
      })
      .catch(err => console.warn("[loadTapoLightingState] failed", err));
  };

  if (window.dashboardInitialPaintDone === true) {
    window.setTimeout(loadLightingState, 0);
    return;
  }

  window.addEventListener("dashboard:initial-paint", loadLightingState, { once: true });
}

loadTapoLightingStateAfterInitialPaint();

function getTapoActionButton(target) {
  if (!(target instanceof Element)) return null;

  const button = target.closest("[data-tapo-action]");
  if (!button) return null;
  if (button.hasAttribute("disabled")) return null;
  if (button.getAttribute("aria-disabled") === "true") return null;

  return button;
}

async function handleTapoActionButton(button) {
  let action = button.dataset.tapoAction;

  if (action === "manager") {
    window.closeAllMenus?.();
    showTapoManagerModal();
    return;
  }

  if (action === "camera-settings") {
    window.closeAllMenus?.();
    showTapoCameraModal(button.dataset);
    return;
  }

  if (action === "camera-record") {
    await setTapoCameraRecording(button);
    return;
  }

  if (action === "settings" || action === "room-settings") {
    window.closeAllMenus?.();
    await loadTapoLightingState();
    showTapoLightModal(button.dataset);
    return;
  }

  if (action === "room-on" || action === "room-off") {
    await sendTapoRoomCommand({
      deviceIDs: button.dataset.tapoDeviceIds || "",
      action: action === "room-on" ? "on" : "off",
      control: button
    });
    return;
  }

  if (action === "scheme") {
    await loadTapoLightingState();

    if (button.classList.contains("active")) {
      const schemeKey = button.dataset.tapoSchemeKey || "";
      const schemeMode = button.dataset.tapoSchemeMode || "";
      const deviceIDs = String(button.dataset.tapoDeviceIds || "")
        .split(",")
        .map(deviceID => deviceID.trim())
        .filter(Boolean);
      const previousActiveSchemes = { ...readTapoActiveLightingSchemes() };

      clearTapoActiveLightingSchemeForKey(schemeKey);
      setTapoSchemeButtonActiveState(button, false);

      try {
        const results = await Promise.allSettled(deviceIDs.map(deviceID => {
          return sendTapoCommand({
            deviceID,
            action: "off",
            verify: false
          });
        }));

        const failures = results.filter(result => result.status === "rejected");

        failures.forEach(result => {
          console.warn("[scheme off] device failed", result.reason);
        });

        if (failures.length >= deviceIDs.length) {
          throw failures[0]?.reason || new Error("Scheme off failed");
        }

        await refreshTapoPowerAfterCommand(deviceIDs, false);
      } catch (err) {
        console.warn("[scheme off] failed", err);

        if (schemeKey && schemeMode) {
          previousActiveSchemes[schemeKey] = schemeMode;
          writeTapoActiveLightingSchemes(previousActiveSchemes);
          setTapoSchemeButtonActiveState(button, true);
        }

        refreshTapoDashboardView();
      }

      return;
    }

    await applyTapoLightingSchemeFromButton(button);
    return;
  }

  const id = button.dataset.tapoId || button.dataset.id;
  const deviceID = button.dataset.deviceId || "";
  const childID = button.dataset.tapoChildId || "";
  const childPosition = button.dataset.tapoChildPosition || "";
  const childIndex = button.dataset.tapoChildIndex || "";

  if (childID && action === "on") {
    action = "child_on";
  } else if (childID && action === "off") {
    action = "child_off";
  }

  const value = childID
    ? { child_id: childID, position: childPosition, child_index: childIndex }
    : button.dataset.value
      ? Number(button.dataset.value)
      : undefined;

  await sendTapoCommand({ id, deviceID, action, value, childID, control: button });
}

async function sendTapoRoomCommand({ deviceIDs, action, value, control }) {
  const targets = tapoDeviceIDList(deviceIDs)
    .map(deviceID => tapoResolveDashboardDeviceTarget(deviceID))
    .filter(target => target.deviceID);

  if (!targets.length) return;

  const isPowerOnAction = action === "on";
  const isPowerOffAction = action === "off";
  const isPowerAction = isPowerOnAction || isPowerOffAction;
  const expectedIsOn = isPowerOnAction;

  window.clearTimeout(window.__tapoCommandRefreshTimer);

  if (isPowerAction) {
    targets.forEach(target => {
      setTapoPendingPowerState(target.deviceID, expectedIsOn, target.childID);

      updateTapoCardState({
        deviceID: target.deviceID,
        is_on: target.childID ? undefined : expectedIsOn,
        tapo_is_on: target.childID ? undefined : expectedIsOn,
        device_on: target.childID ? undefined : expectedIsOn,
        state: target.childID ? undefined : expectedIsOn,
        children: target.childID
          ? [{
            id: target.childID,
            is_on: expectedIsOn
          }]
          : undefined
      });
    });

    updateTapoRoomPowerButtonsForDevices(deviceIDs, expectedIsOn);
  }

  if (control) control.disabled = true;

  try {
    const results = await Promise.allSettled(targets.map(target => {
      return sendTapoCommand({
        deviceID: target.deviceID,
        action: isPowerAction && target.childID
          ? (isPowerOnAction ? "child_on" : "child_off")
          : action,
        childID: isPowerAction ? target.childID : "",
        value: isPowerAction && target.childID ? tapoChildCommandValue(target) : value,
        verify: false
      });
    }));

    const failures = results.filter(result => result.status === "rejected");

    failures.forEach(result => {
      console.warn("[sendTapoRoomCommand] device failed", result.reason);
    });

    if (failures.length >= targets.length) {
      throw failures[0]?.reason || new Error("Tapo room command failed");
    }

    if (isPowerAction) {
      targets.forEach(target => {
        refreshTapoPowerAfterCommand(target.deviceID, expectedIsOn, target.childID);
      });
    } else {
      scheduleTapoCommandRefresh(750);
    }
  } finally {
    if (control) control.disabled = false;
  }
}

function claimTapoClick(event) {
  event.preventDefault();
  event.stopPropagation();
  event.stopImmediatePropagation?.();
}

document.addEventListener("keydown", event => {
  if (event.key !== "Enter" && event.key !== " ") return;

  const target = event.target instanceof Element ? event.target : null;
  const rechargeToggle = target?.closest("[data-tapo-recharge-toggle]");

  if (!rechargeToggle) return;

  event.preventDefault();
  rechargeToggle.click();
});

document.addEventListener("click", async (event) => {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return;

  // Strict CSP forbids inline onclick handlers. Route all dynamically created
  // Tapo modal close buttons through this existing delegated click listener.
  const modalCloseButton = target.closest("[data-tapo-modal-close]");

  if (modalCloseButton) {
    claimTapoClick(event);

    const modalType = modalCloseButton.dataset.tapoModalClose || "";

    if (modalType === "light") {
      window.hideTapoLightModal?.();
    } else if (modalType === "camera") {
      window.hideTapoCameraModal?.();
    } else if (modalType === "manager") {
      window.hideTapoManagerModal?.();
    }

    return;
  }

  const rechargeToggle = target.closest("[data-tapo-recharge-toggle]");

  if (rechargeToggle) {
    claimTapoClick(event);

    const modal = document.getElementById("tapoLightModal");
    if (modal) {
      modal.dataset.tapoRechargeExpanded = modal.dataset.tapoRechargeExpanded === "1" ? "0" : "1";
    }

    await refreshTapoRechargeSettingsPanel();
    return;
  }

  const rechargeViewButton = target.closest("[data-tapo-recharge-view]");

  if (rechargeViewButton) {
    claimTapoClick(event);

    const modal = document.getElementById("tapoLightModal");
    if (modal) {
      modal.dataset.tapoRechargeMode = rechargeViewButton.dataset.tapoRechargeView || "list";
      modal.dataset.tapoRechargeExpanded = "0";
    }

    await refreshTapoRechargeSettingsPanel();
    return;
  }

  const rechargeAddButton = target.closest("[data-tapo-recharge-add]");

  if (rechargeAddButton) {
    claimTapoClick(event);

    const modal = document.getElementById("tapoLightModal");
    if (modal) {
      modal.dataset.tapoRechargeMode = "add";
      modal.dataset.tapoRechargeExpanded = "0";

      if (rechargeAddButton.dataset.tapoRechargeTargetId) {
        modal.dataset.tapoRechargeTargetId = rechargeAddButton.dataset.tapoRechargeTargetId;
      }
    }

    await refreshTapoRechargeSettingsPanel();
    return;
  }

  const rechargeSaveButton = target.closest("[data-tapo-recharge-save]");

  if (rechargeSaveButton) {
    claimTapoClick(event);
    await saveTapoRechargeSettings(rechargeSaveButton);
    return;
  }

  const button = getTapoActionButton(target);
  if (!button) return;

  claimTapoClick(event);
  await handleTapoActionButton(button);
}, true);

async function setTapoCameraRecording(button) {
  const deviceID = button.dataset.deviceId || "";
  const id = button.dataset.tapoId || "";
  const isRecording = button.dataset.recording === "1";
  const active = !isRecording;

  button.disabled = true;

  try {
    const data = await sendTapoCommand({
      id,
      deviceID,
      action: "camera_record",
      value: active,
      control: button
    });

    updateTapoCameraRecordButton(button, !!(data.tapo_recording_enabled || data.recordingEnabled || data.recording));
  } finally {
    button.disabled = false;
  }
}

function updateTapoCameraRecordButton(button, isRecording) {
  if (!button) return;

  button.dataset.recording = isRecording ? "1" : "0";
  button.classList.toggle("active", isRecording);
  button.title = isRecording ? "Stop Recording" : "Start Recording";
  button.setAttribute("aria-label", button.title);
  button.setAttribute("aria-pressed", isRecording ? "true" : "false");
}

window.setTapoPreviewViewer = function (deviceID, active, useBeacon = false) {
  if (!deviceID) return;

  const payload = JSON.stringify({
    deviceID,
    viewerId: window.previewViewerId || "dashboard",
    action: "preview",
    active: !!active
  });

  if (useBeacon && navigator.sendBeacon) {
    navigator.sendBeacon(
      "/api/tapo/client-command",
      new Blob([payload], { type: "application/json" })
    );
    return;
  }

  dashboardFetch("/api/tapo/client-command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
    keepalive: true
  })
    .then(res => res.json())
    .then(data => {
      if (!data?.ok) {
        console.warn("Tapo camera preview request failed", data?.error || "unknown error");
        return;
      }

      const previewUrl = active ? (data.tapo_hls_url || "") : "";

      getTapoCameraVideosForDevice(deviceID).forEach(video => {
        if (!previewUrl) {
          destroyTapoCameraVideoPlayer(video, {
            clearSource: true,
            hide: true
          });
          return;
        }

        const previousSrc = video.dataset.hlsSrc || "";

        video.dataset.hlsSrc = previewUrl;
        video.style.display = "block";

        if (previousSrc !== previewUrl) {
          video.dataset.hlsAttached = "";
          video.dataset.hlsAttaching = "";
        }

        window.initTapoCameraVideo?.(video);
      });

      const escaped = tapoEscapeSelector(deviceID);
      const button = document.querySelector(`.tapo-camera-settings-open[data-device-id="${escaped}"]`);

      if (button && previewUrl) {
        button.dataset.previewUrl = previewUrl;
      }
    })
    .catch(err => {
      console.warn("Tapo camera preview request failed", err);
    });
};

window.tapoHlsPlayers = window.tapoHlsPlayers || new WeakMap();
window.tapoHlsPlayerElements = window.tapoHlsPlayerElements || new Set();
window.tapoHlsLoaderPromise = window.tapoHlsLoaderPromise || null;
window.tapoCameraPreviewState = window.tapoCameraPreviewState || new Map();
window.tapoCameraSleepTimers = window.tapoCameraSleepTimers || new Map();
window.tapoCameraLastWake = window.tapoCameraLastWake || new Map();
window.TAPO_CAMERA_SLEEP_DELAY_MS = window.TAPO_CAMERA_SLEEP_DELAY_MS || 90000;
window.TAPO_CAMERA_WAKE_DEDUP_MS = window.TAPO_CAMERA_WAKE_DEDUP_MS || 7500;
window.TAPO_CAMERA_VIEWER_HEARTBEAT_MS = window.TAPO_CAMERA_VIEWER_HEARTBEAT_MS || 15000;
window.TAPO_CAMERA_LAYOUT_SYNC_DELAY_MS = window.TAPO_CAMERA_LAYOUT_SYNC_DELAY_MS || 180;

function tapoEscapeSelector(value) {
  if (window.CSS?.escape) return CSS.escape(value);
  return String(value).replace(/["\\]/g, "\\$&");
}

function getTapoVideoDeviceID(video) {
  return video?.closest?.("[data-device-id]")?.dataset?.deviceId || video?.dataset?.deviceId || "";
}

function getTapoCameraVideosForDevice(deviceID) {
  const escaped = tapoEscapeSelector(deviceID);

  return document.querySelectorAll([
    `.tapo-camera-card[data-device-id="${escaped}"] video.tapo-camera-video`,
    `.tapo-client-card[data-device-id="${escaped}"] video.tapo-camera-video`,
    `[data-device-id="${escaped}"] video.tapo-camera-video`,
    `video.tapo-camera-video[data-device-id="${escaped}"]`
  ].join(","));
}

function destroyTapoCameraVideoPlayer(video, options = {}) {
  if (!video) return;

  const existing = window.tapoHlsPlayers.get(video);

  if (existing) {
    existing.destroy();
    window.tapoHlsPlayers.delete(video);
  }

  window.tapoHlsPlayerElements.delete(video);
  video.dataset.hlsAttached = "";
  video.dataset.hlsAttaching = "";
  video.dataset.hlsNative = "";
  video.dataset.hlsState = "idle";

  if (options.clearSource) {
    video.dataset.hlsSrc = "";
    video.removeAttribute("src");

    if (video.isConnected) {
      video.load();
    }
  }

  if (options.hide) {
    video.style.display = "none";
  }
}

function cleanupDetachedTapoCameraPlayers() {
  Array.from(window.tapoHlsPlayerElements).forEach(video => {
    if (video.isConnected) return;

    window.tapoCameraViewportObserver?.unobserve?.(video);
    destroyTapoCameraVideoPlayer(video, {
      clearSource: true
    });
  });
}

function scheduleTapoCameraVideoSync(force = false, delay = 0) {
  window.__tapoCameraSyncForce = !!window.__tapoCameraSyncForce || !!force;
  window.clearTimeout(window.__tapoCameraSyncTimer);

  window.__tapoCameraSyncTimer = window.setTimeout(() => {
    const shouldForce = !!window.__tapoCameraSyncForce;

    window.__tapoCameraSyncForce = false;
    cleanupDetachedTapoCameraPlayers();
    window.initTapoCameraVideos?.(shouldForce);
  }, Math.max(0, Number(delay) || 0));
}

function setTapoCameraPreviewActive(video, active, useBeacon = false, force = false) {
  const deviceID = getTapoVideoDeviceID(video);
  if (!deviceID) return;

  const existingTimer = window.tapoCameraSleepTimers.get(deviceID);

  if (existingTimer) {
    clearTimeout(existingTimer);
    window.tapoCameraSleepTimers.delete(deviceID);
  }

  if (!active) {
    if (window.tapoCameraPreviewState.get(deviceID) !== true && !force) {
      return;
    }

    const sleepNow = () => {
      window.tapoCameraPreviewState.set(deviceID, false);
      window.tapoCameraLastWake.delete(deviceID);
      window.tapoCameraSleepTimers.delete(deviceID);

      getTapoCameraVideosForDevice(deviceID).forEach(item => {
        destroyTapoCameraVideoPlayer(item, {
          clearSource: true,
          hide: true
        });
      });

      window.setTapoPreviewViewer(deviceID, false, useBeacon);
    };

    if (force) {
      sleepNow();
      return;
    }

    const sleepTimer = window.setTimeout(() => {
      const videos = Array.from(getTapoCameraVideosForDevice(deviceID));
      const stillVisible = videos.some(item => isTapoVideoVisible(item));

      if (stillVisible) {
        window.tapoCameraSleepTimers.delete(deviceID);
        return;
      }

      sleepNow();
    }, window.TAPO_CAMERA_SLEEP_DELAY_MS);

    window.tapoCameraSleepTimers.set(deviceID, sleepTimer);
    return;
  }

  const current = window.tapoCameraPreviewState.get(deviceID);
  const now = Date.now();
  const lastWake = Number(window.tapoCameraLastWake.get(deviceID) || 0);
  const recentWake = (
    current === true &&
    now - lastWake < window.TAPO_CAMERA_WAKE_DEDUP_MS
  );
  const heartbeatDue = (
    current === true &&
    now - lastWake >= window.TAPO_CAMERA_VIEWER_HEARTBEAT_MS
  );
  const needsWake = current !== true || (!recentWake && (force || heartbeatDue));

  if (current === true) {
    window.initTapoCameraVideo?.(video);
  }

  if (!needsWake) {
    return;
  }

  window.tapoCameraPreviewState.set(deviceID, true);
  window.tapoCameraLastWake.set(deviceID, now);
  window.setTapoPreviewViewer(deviceID, true, false);
}

function getTapoCameraVisibilityNode(video) {
  return video?.closest?.(".tapo-camera-card, .tapo-client-card, [data-node-card='camera'], [data-device-id]") || video;
}

function isTapoVideoVisible(video) {
  const node = getTapoCameraVisibilityNode(video);
  const rect = node.getBoundingClientRect();

  return rect.width > 0
    && rect.height > 0
    && rect.bottom >= -120
    && rect.right >= 0
    && rect.top <= window.innerHeight + 120
    && rect.left <= window.innerWidth;
}

function wakeVisibleTapoCameraVideos(force = false) {
  document.querySelectorAll("video.tapo-camera-video").forEach(video => {
    if (isTapoVideoVisible(video)) {
      setTapoCameraPreviewActive(video, true, false, force);
    }
  });
}

window.sleepAllTapoCameraVideos = function (useBeacon = false) {
  document.querySelectorAll("video.tapo-camera-video").forEach(video => {
    setTapoCameraPreviewActive(video, false, useBeacon, true);
  });
};

window.loadTapoHls = function () {
  if (window.Hls) return Promise.resolve(window.Hls);
  if (window.tapoHlsLoaderPromise) return window.tapoHlsLoaderPromise;

  const version = encodeURIComponent(
    window.KOTIBOT_STATIC_VERSION ||
    window.dashboardStaticVersion ||
    ""
  );
  const versionQuery = version ? `?v=${version}` : "";

  const sources = [
    `/subsystems/client-tapo/static/vendor/hls-1.6.17.min.js${versionQuery}`
  ];

  window.tapoHlsLoaderPromise = new Promise((resolve, reject) => {
    const loadNext = () => {
      const src = sources.shift();

      if (!src) {
        window.tapoHlsLoaderPromise = null;
        reject(new Error("HLS.js unavailable"));
        return;
      }

      const script = document.createElement("script");
      script.src = src;
      script.async = true;

      script.onload = () => {
        if (window.Hls) {
          resolve(window.Hls);
          return;
        }

        loadNext();
      };

      script.onerror = () => {
        script.remove();
        loadNext();
      };

      document.head.appendChild(script);
    };

    loadNext();
  });

  return window.tapoHlsLoaderPromise;
};

function playTapoCameraVideo(video) {
  if (!video?.play) return;

  let playback;

  try {
    playback = video.play();
  } catch (err) {
    video.dataset.hlsState = "playback-blocked";
    console.warn("Tapo camera playback failed", err);
    return;
  }

  if (!playback?.then) return;

  playback
    .then(() => {
      video.dataset.hlsState = "playing";
    })
    .catch(err => {
      if (video.dataset.hlsState !== "playback-blocked") {
        console.warn("Tapo camera playback was blocked", err);
      }

      video.dataset.hlsState = "playback-blocked";
    });
}

window.initTapoCameraVideo = async function (video) {
  if (!video) return;

  const src = video.dataset.hlsSrc || "";

  if (!src) {
    destroyTapoCameraVideoPlayer(video, {
      clearSource: true,
      hide: true
    });
    return;
  }

  const existing = window.tapoHlsPlayers.get(video);
  const nativeAttached = (
    video.dataset.hlsNative === "1" &&
    video.getAttribute("src") === src
  );
  const playerAttached = (
    video.dataset.hlsAttached === src &&
    (existing || nativeAttached)
  );

  window.tapoHlsPlayerElements.add(video);
  video.muted = true;
  video.playsInline = true;
  video.autoplay = true;
  video.style.display = "block";

  if (playerAttached) {
    if (video.paused) {
      playTapoCameraVideo(video);
    }

    return;
  }

  if (video.dataset.hlsAttaching === src) {
    return;
  }

  destroyTapoCameraVideoPlayer(video);
  window.tapoHlsPlayerElements.add(video);
  video.dataset.hlsAttaching = src;
  video.dataset.hlsState = "loading";
  video.style.display = "block";

  if (video.canPlayType("application/vnd.apple.mpegurl")) {
    video.dataset.hlsNative = "1";
    video.dataset.hlsAttached = src;
    video.dataset.hlsAttaching = "";
    video.src = src;
    video.load();
    playTapoCameraVideo(video);
    return;
  }

  let Hls;

  try {
    Hls = await window.loadTapoHls();
  } catch (err) {
    console.warn("Tapo camera HLS loader failed", err);
    destroyTapoCameraVideoPlayer(video, {
      hide: true
    });
    return;
  }

  if (!video.isConnected || video.dataset.hlsSrc !== src) {
    destroyTapoCameraVideoPlayer(video);
    return;
  }

  if (!Hls?.isSupported?.()) {
    console.warn("Tapo camera HLS is not supported by this browser");
    destroyTapoCameraVideoPlayer(video, {
      hide: true
    });
    return;
  }

  const hls = new Hls({
    lowLatencyMode: false,
    backBufferLength: 10,
    manifestLoadingMaxRetry: 12,
    levelLoadingMaxRetry: 12,
    fragLoadingMaxRetry: 12,
    manifestLoadingRetryDelay: 500,
    levelLoadingRetryDelay: 500,
    fragLoadingRetryDelay: 500
  });

  window.tapoHlsPlayers.set(video, hls);
  window.tapoHlsPlayerElements.add(video);

  hls.on(Hls.Events.MEDIA_ATTACHED, () => {
    if (window.tapoHlsPlayers.get(video) !== hls) return;
    video.dataset.hlsState = "attached";
  });

  hls.on(Hls.Events.MANIFEST_PARSED, () => {
    if (window.tapoHlsPlayers.get(video) !== hls) return;

    video.dataset.hlsAttached = src;
    video.dataset.hlsAttaching = "";
    video.dataset.hlsState = "ready";
    playTapoCameraVideo(video);
  });

  hls.on(Hls.Events.ERROR, (event, data) => {
    if (!data?.fatal) return;

    if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
      video.dataset.hlsState = "recovering-network";
      hls.startLoad();
      return;
    }

    if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
      video.dataset.hlsState = "recovering-media";
      hls.recoverMediaError();
      return;
    }

    destroyTapoCameraVideoPlayer(video, {
      hide: true
    });
  });

  hls.loadSource(src);
  hls.attachMedia(video);
};

window.tapoCameraViewportObserver = window.tapoCameraViewportObserver || (
  "IntersectionObserver" in window
    ? new IntersectionObserver(entries => {
      entries.forEach(entry => {
        const video = entry.target;

        if (entry.isIntersecting) {
          setTapoCameraPreviewActive(video, true, false);
          return;
        }

        setTapoCameraPreviewActive(video, false, false);
      });
    }, {
      root: null,
      rootMargin: "240px 0px",
      threshold: 0.01
    })
    : null
);

window.initTapoCameraVideos = function (force = false) {
  document.querySelectorAll("video.tapo-camera-video").forEach(video => {
    if (window.tapoCameraViewportObserver && !video.dataset.tapoViewportObserved) {
      video.dataset.tapoViewportObserved = "1";
      window.tapoCameraViewportObserver.observe(video);
    }
  });

  wakeVisibleTapoCameraVideos(force);
};

window.tapoCameraVideoObserver = window.tapoCameraVideoObserver || new MutationObserver(() => {
  scheduleTapoCameraVideoSync(false, 80);
});

window.tapoCameraVideoObserver.observe(document.body, {
  childList: true,
  subtree: true
});

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    return;
  }

  scheduleTapoCameraVideoSync(true);
});

window.addEventListener("pageshow", () => {
  scheduleTapoCameraVideoSync(true);
});

window.addEventListener("focus", () => {
  scheduleTapoCameraVideoSync(true);
});

window.addEventListener("scroll", () => {
  scheduleTapoCameraVideoSync(false, 150);
}, { passive: true });

window.addEventListener("resize", () => {
  scheduleTapoCameraVideoSync(
    true,
    window.TAPO_CAMERA_LAYOUT_SYNC_DELAY_MS
  );
});

window.tapoCameraWakeInterval = window.tapoCameraWakeInterval || window.setInterval(() => {
  if (document.hidden) return;
  scheduleTapoCameraVideoSync(false);
}, 5000);

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    scheduleTapoCameraVideoSync(true);
  }, { once: true });
} else {
  scheduleTapoCameraVideoSync(true);
}

async function sendTapoCommand({ id, deviceID, action, value, childID = "", control, verify = true, skipHomeLightingMode = false, lightingMode = "" }) {
  const targetID = deviceID || id;
  const commandKey = [targetID, childID].filter(Boolean).join(":");
  if (!commandKey) return;

  if (action === "color_temp") action = "color_temperature";

  const isPowerOnAction = action === "on" || action === "child_on";
  const isPowerOffAction = action === "off" || action === "child_off";
  const isPowerAction = isPowerOnAction || isPowerOffAction;

  if (isPowerAction) {
    setTapoPendingPowerState(targetID, isPowerOnAction, childID);

    updateTapoCardState({
      id,
      deviceID: targetID,
      is_on: childID ? undefined : isPowerOnAction,
      children: childID
        ? [{
          id: childID,
          is_on: isPowerOnAction
        }]
        : undefined
    });
  }

  if (!isPowerAction) {
    await waitForTapoCommandSlot(commandKey);

    tapoCommandInFlight.add(commandKey);
    if (control) control.disabled = true;
  }

  try {
    const res = await dashboardFetch("/api/tapo/client-command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ deviceID, id, action, value, lightingMode })
    });

    const data = await res.json();

    if (!data.ok) {
      console.warn("Tapo command failed", data);
      throw new Error(data.error || "Tapo command failed");
    }

    updateTapoCardState(applyTapoPendingPowerState(data.client || data.device || {
      id,
      deviceID: targetID,
      is_on: isPowerAction && !childID ? isPowerOnAction : undefined,
      children: isPowerAction && childID
        ? [{
          id: childID,
          is_on: isPowerOnAction
        }]
        : undefined,
      brightness: ["brightness", "brightness_no_power"].includes(action) ? value : undefined,
      color_temperature: ["color_temperature", "color_temperature_no_power"].includes(action) ? value : undefined,
      hue: ["color", "color_no_power"].includes(action) ? value?.hue : undefined,
      saturation: ["color", "color_no_power"].includes(action) ? value?.saturation : undefined
    }));

    if (isPowerAction) {
      refreshTapoPowerAfterCommand(targetID, isPowerOnAction, childID);

      if (
        isPowerOnAction &&
        !childID &&
        !skipHomeLightingMode &&
        data.lightingRecovered !== true &&
        typeof window.applyDashboardHomeLightingModeToDevices === "function"
      ) {
        window.applyDashboardHomeLightingModeToDevices([targetID]).catch(err => {
          console.warn("[applyDashboardHomeLightingModeToDevices] failed", err);
        });
      }
    } else {
      scheduleTapoCommandRefresh(750);
    }

    return data;
  } catch (err) {
    if (isPowerAction) {
      clearTapoPendingPowerState(targetID, childID);

      updateTapoCardState({
        id,
        deviceID: targetID,
        is_on: childID ? undefined : null,
        tapo_is_on: childID ? undefined : null,
        device_on: childID ? undefined : null,
        state: childID ? undefined : null,
        children: childID
          ? [{
            id: childID,
            is_on: null,
            device_on: null,
            on: null,
            state: null
          }]
          : undefined,
        tapo_control_ready: false,
        tapo_control_error: err?.message || "Tapo command failed"
      });

      scheduleTapoCommandRefresh(750);
    } else {
      scheduleTapoCommandRefresh(750);
    }

    throw err;
  } finally {
    if (!isPowerAction) {
      tapoCommandInFlight.delete(commandKey);
      if (control) control.disabled = false;
    }
  }
}

function getTapoLightingModePreset(mode) {
  if (mode === "day") {
    return {
      brightness: 90,
      colorTemperature: 3700,
      whiteSaturation: 1,
      hue: null,
      saturation: null
    };
  }

  if (mode === "evening") {
    return {
      brightness: 80,
      colorTemperature: 3200,
      whiteSaturation: 1,
      hue: null,
      saturation: null
    };
  }

  if (mode === "movie") {
    return {
      brightness: 5,
      colorTemperature: 2700,
      whiteSaturation: 5,
      hue: null,
      saturation: null
    };
  }

  if (mode === "nightlight") {
    return {
      brightness: 1,
      colorTemperature: 2700,
      whiteSaturation: 1,
      hue: null,
      saturation: null
    };
  }

  return {
    brightness: 90,
    colorTemperature: 3700,
    whiteSaturation: 1,
    hue: null,
    saturation: null
  };
}

function getTapoLightingModeClients() {
  return (S.currentClients || []).filter(c => {
    if (!c?.provisioned) return false;

    const roles = Array.isArray(c.clientRole)
      ? c.clientRole
      : String(c.clientRole || "").split(",");

    const hasTapoRole = roles
      .map(role => String(role).trim().toUpperCase())
      .includes("TAPO");

    if (!hasTapoRole) return false;

    return ["bulb", "lightstrip"].includes(String(c.tapo_kind || "").toLowerCase());
  });
}

function getTapoLightingModeTargets() {
  const target = activeTapoLight();

  if (target.deviceIDs) {
    return target.deviceIDs
      .split(",")
      .map(deviceID => deviceID.trim())
      .filter(Boolean);
  }

  if (target.deviceID) {
    return [target.deviceID];
  }

  return getTapoLightingModeClients()
    .map(c => c.deviceID)
    .filter(Boolean);
}

function getTapoLightingSchemeTargetKey() {
  const target = activeTapoLight();

  if (target.deviceIDs) {
    return `room:${target.deviceIDs
      .split(",")
      .map(deviceID => deviceID.trim())
      .filter(Boolean)
      .sort()
      .join(",")}`;
  }

  if (target.deviceID) {
    return `device:${target.deviceID}`;
  }

  if (target.id) {
    return `tapo:${target.id}`;
  }

  return "";
}

function getTapoLightingSchemeStorageKeys() {
  const primaryKey = getTapoLightingSchemeTargetKey();

  return primaryKey ? [primaryKey] : [];
}

function tapoLightingKeyDeviceIDs(key = "") {
  return String(key || "")
    .replace(/^room:/, "")
    .split(",")
    .map(deviceID => deviceID.trim())
    .filter(Boolean)
    .sort();
}

function tapoLightingRoomKeysOverlap(a = "", b = "") {
  if (!String(a || "").startsWith("room:") || !String(b || "").startsWith("room:")) return false;

  const aIDs = tapoLightingKeyDeviceIDs(a);
  const bIDs = tapoLightingKeyDeviceIDs(b);

  if (!aIDs.length || !bIDs.length) return false;

  const aSet = new Set(aIDs);
  const bSet = new Set(bIDs);

  return aIDs.every(deviceID => bSet.has(deviceID))
    || bIDs.every(deviceID => aSet.has(deviceID));
}

function getTapoLightingSchemeFavoriteKeys(key = "", schemes = readTapoLightingSchemes()) {
  const cleanKey = String(key || "").trim();

  if (!cleanKey) return [];

  const keys = [cleanKey];

  if (cleanKey.startsWith("room:") && schemes && typeof schemes === "object") {
    Object.keys(schemes).forEach(existingKey => {
      if (existingKey !== cleanKey && tapoLightingRoomKeysOverlap(cleanKey, existingKey)) {
        keys.push(existingKey);
      }
    });
  }

  return keys;
}

function isTapoLightingSchemeFavoriteForKey(key, mode) {
  if (!key || !mode) return false;

  const schemes = readTapoLightingSchemes();

  return getTapoLightingSchemeFavoriteKeys(key, schemes).some(candidateKey => (
    Array.isArray(schemes[candidateKey]) ? schemes[candidateKey] : []
  ).some(scheme => scheme?.mode === mode && scheme?.favorite === true));
}

function setTapoLightingSchemeFavoriteForTargetKey(key, mode, isFavorite) {
  if (!key || !mode) return;

  if (isFavorite) {
    setTapoLightingSchemeFavoriteForKey(key, mode, true);
    return;
  }

  const schemes = readTapoLightingSchemes();
  const keys = getTapoLightingSchemeFavoriteKeys(key, schemes);
  let changed = false;

  keys.forEach(candidateKey => {
    const targetSchemes = Array.isArray(schemes[candidateKey]) ? schemes[candidateKey] : [];
    const targetIndex = targetSchemes.findIndex(scheme => scheme.mode === mode);

    if (targetIndex < 0 || targetSchemes[targetIndex]?.favorite !== true) return;

    targetSchemes[targetIndex] = {
      ...targetSchemes[targetIndex],
      favorite: false
    };
    schemes[candidateKey] = targetSchemes;
    changed = true;
  });

  if (changed) {
    writeTapoLightingSchemes(schemes);
  } else {
    setTapoLightingSchemeFavoriteForKey(key, mode, false);
  }
}

function tapoLightingSchemeWasFavorite(schemes, keys = [], mode = "") {
  if (!schemes || !mode) return false;

  const candidates = new Set(
    keys
      .map(key => String(key || "").trim())
      .filter(Boolean)
  );

  keys.forEach(key => {
    const cleanKey = String(key || "").trim();

    if (!cleanKey.startsWith("room:")) return;

    Object.keys(schemes).forEach(existingKey => {
      if (tapoLightingRoomKeysOverlap(cleanKey, existingKey)) {
        candidates.add(existingKey);
      }
    });
  });

  return Array.from(candidates).some(key => (Array.isArray(schemes[key]) ? schemes[key] : [])
    .some(scheme => scheme?.mode === mode && scheme?.favorite === true));
}

const TAPO_BUILTIN_LIGHTING_SCHEMES = [
  {
    mode: "day",
    label: "Day",
    icon: "wb_sunny"
  },
  {
    mode: "evening",
    label: "Evening",
    icon: "wb_twilight"
  },
  {
    mode: "movie",
    label: "Movie Time",
    icon: "movie"
  },
  {
    mode: "nightlight",
    label: "Nightlight",
    icon: "bedtime"
  }
];

function getTapoBuiltinLightingScheme(mode) {
  return TAPO_BUILTIN_LIGHTING_SCHEMES
    .find(scheme => scheme.mode === mode);
}

function getTapoLightingSchemeLabel(mode) {
  const builtinScheme = getTapoBuiltinLightingScheme(mode);

  if (builtinScheme) return builtinScheme.label;
  if (String(mode || "").startsWith("custom:")) return "Custom";

  return "Scheme";
}

function getTapoLightingSchemeIcon(mode) {
  const builtinScheme = getTapoBuiltinLightingScheme(mode);

  if (builtinScheme) return builtinScheme.icon;
  if (String(mode || "").startsWith("custom:")) return "tune";

  return "emoji_objects";
}

function getTapoLightingScopeLabel() {
  const modal = document.getElementById("tapoLightModal");
  const target = activeTapoLight();
  const fallback = modal?.dataset.roomSettings === "1" ? "Room" : "Bulb";

  return String(
    modal?.dataset.tapoBaseTitle ||
    modal?.dataset.tapoRoom ||
    target.tapoName ||
    target.clientName ||
    fallback
  ).trim() || fallback;
}

function tapoCapabilityFlag(value, fallback = false) {
  if (value === true || value === 1) return true;
  if (value === false || value === 0) return false;

  const clean = String(value ?? "").trim().toLowerCase();
  if (["1", "true", "yes", "on", "enabled"].includes(clean)) return true;
  if (["0", "false", "no", "off", "disabled"].includes(clean)) return false;

  return fallback;
}

function getTapoLightCapabilities() {
  const modal = document.getElementById("tapoLightModal");

  return {
    brightness: tapoCapabilityFlag(modal?.dataset.supportsBrightness, false),
    white: tapoCapabilityFlag(modal?.dataset.supportsColorTemp, false),
    color: tapoCapabilityFlag(modal?.dataset.supportsColor, false)
  };
}

function getTapoLightHasAdjustments() {
  const capabilities = getTapoLightCapabilities();

  return capabilities.brightness || capabilities.white || capabilities.color;
}

function getCurrentTapoLightingPreset() {
  const capabilities = getTapoLightCapabilities();
  const colorMode = capabilities.color && document.getElementById("tapoColorModeBtn")?.classList.contains("active");
  const brightness = capabilities.brightness
    ? Number(document.getElementById(colorMode ? "tapoColorBrightnessSlider" : "tapoWhiteBrightnessSlider")?.value || 100)
    : null;

  if (colorMode) {
    return {
      brightness,
      colorTemperature: null,
      hue: Number(document.getElementById("tapoHueSlider")?.value || 45),
      saturation: Number(document.getElementById("tapoSaturationSlider")?.value || 100)
    };
  }

  return {
    brightness,
    colorTemperature: capabilities.white
      ? getTapoWhiteTemperatureValue()
      : null,
    whiteSaturation: capabilities.color ? getTapoWhiteSaturationValue() : null,
    hue: null,
    saturation: null
  };
}

function normalizeTapoWhiteSaturation(value = TAPO_WHITE_SATURATION_DEFAULT) {
  const parsed = Number(value ?? TAPO_WHITE_SATURATION_DEFAULT);

  return Math.max(1, Math.min(10, Math.round(Number.isFinite(parsed) ? parsed : TAPO_WHITE_SATURATION_DEFAULT)));
}

function getTapoWhiteSaturationValue() {
  return TAPO_WHITE_SATURATION_DEFAULT;
}

function normalizeTapoWhiteTemperature(value = 4200) {
  const parsed = Number(value ?? 4200);

  return Math.max(2500, Math.min(6500, Math.round(Number.isFinite(parsed) ? parsed : 4200)));
}

function getTapoWhiteTemperatureValue() {
  return normalizeTapoWhiteTemperature(document.getElementById("tapoWhiteBalanceSlider")?.value || 4200);
}

function getTapoWhiteTemperaturePreset(kelvin) {
  const targetKelvin = normalizeTapoWhiteTemperature(kelvin);

  return TAPO_WHITE_TEMPERATURE_PRESETS.find(preset => preset.kelvin === targetKelvin) || null;
}

function syncTapoWhiteTemperatureButtons(kelvin = getTapoWhiteTemperatureValue()) {
  const targetKelvin = normalizeTapoWhiteTemperature(kelvin);

  document.querySelectorAll("[data-tapo-white-kelvin]").forEach(button => {
    const active = Number(button.dataset.tapoWhiteKelvin || 0) === targetKelvin;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function setTapoWhiteTemperature(kelvin) {
  const targetKelvin = normalizeTapoWhiteTemperature(kelvin);
  const hiddenInput = document.getElementById("tapoWhiteBalanceSlider");

  if (hiddenInput) hiddenInput.value = String(targetKelvin);
  syncTapoWhiteTemperatureButtons(targetKelvin);
}

function renderTapoWhiteTemperatureButtons() {
  return TAPO_WHITE_TEMPERATURE_PRESETS.map(preset => `
              <button class="client-menu-btn" type="button" data-tapo-white-kelvin="${preset.kelvin}">
                ${window.dashboardIconHtml("emoji_objects", "tapo-white-temperature-icon")}
                <span class="tapo-white-temperature-copy">
                  <span class="tapo-white-temperature-title">${esc(preset.label)}</span>
                  <span class="tapo-white-temperature-subtitle">${preset.kelvin}K</span>
                </span>
              </button>
            `).join("");
}

function tapoWhiteHueFromKelvin(kelvin) {
  const t = Math.max(2500, Math.min(6500, Number(kelvin || 4200)));
  const ratio = (t - 2500) / 4000;

  return Math.round(42 + ((210 - 42) * ratio));
}

function getTapoWhiteColorValue() {
  return {
    hue: tapoWhiteHueFromKelvin(getTapoWhiteTemperatureValue()),
    saturation: getTapoWhiteSaturationValue()
  };
}

function tapoWhitePreviewHex(kelvin, saturation) {
  return hslToHex(tapoWhiteHueFromKelvin(kelvin), normalizeTapoWhiteSaturation(saturation), 82);
}

function sendTapoWhiteCommand(target, control = null) {
  const supports = getTapoLightCapabilities();

  if (supports.color) {
    const value = getTapoWhiteColorValue();

    if (target.deviceIDs) {
      sendTapoRoomCommand({ deviceIDs: target.deviceIDs, action: "color", value, control });
      return;
    }

    sendTapoCommand({ ...target, action: "color", value, control });
    return;
  }

  if (!supports.white) return;

  const value = getTapoWhiteTemperatureValue();

  if (target.deviceIDs) {
    sendTapoRoomCommand({ deviceIDs: target.deviceIDs, action: "color_temperature", value, control });
    return;
  }

  sendTapoCommand({ ...target, action: "color_temperature", value, control });
}

function tapoLightingNumberClose(a, b, tolerance = 2) {
  if (a == null || b == null) return a == null && b == null;

  return Math.abs(Number(a) - Number(b)) <= tolerance;
}

function tapoLightingPresetsMatch(a, b) {
  if (!a || !b) return false;

  if (!tapoLightingNumberClose(a.brightness, b.brightness, 1)) return false;

  const aColor = a.hue != null;
  const bColor = b.hue != null;

  if (aColor || bColor) {
    return aColor === bColor
      && tapoLightingNumberClose(a.hue, b.hue, 1)
      && tapoLightingNumberClose(a.saturation, b.saturation, 1);
  }

  return tapoLightingNumberClose(a.colorTemperature, b.colorTemperature, 50)
    && tapoLightingNumberClose(
      a.whiteSaturation ?? TAPO_WHITE_SATURATION_DEFAULT,
      b.whiteSaturation ?? TAPO_WHITE_SATURATION_DEFAULT,
      1
    );
}

function getTapoLightingState() {
  window.TAPO_LIGHTING_STATE = window.TAPO_LIGHTING_STATE || {
    schemes: {},
    activeSchemes: {},
    modeConfig: {},
    loaded: false
  };

  if (!window.TAPO_LIGHTING_STATE.schemes || typeof window.TAPO_LIGHTING_STATE.schemes !== "object") {
    window.TAPO_LIGHTING_STATE.schemes = {};
  }

  if (!window.TAPO_LIGHTING_STATE.activeSchemes || typeof window.TAPO_LIGHTING_STATE.activeSchemes !== "object") {
    window.TAPO_LIGHTING_STATE.activeSchemes = {};
  }

  if (!window.TAPO_LIGHTING_STATE.modeConfig || typeof window.TAPO_LIGHTING_STATE.modeConfig !== "object") {
    window.TAPO_LIGHTING_STATE.modeConfig = {};
  }

  return window.TAPO_LIGHTING_STATE;
}

function mergeTapoLightingState(serverState = {}) {
  return window.applyDashboardTapoLightingState(serverState);
}

function clearLegacyTapoLocalLightingState() {
  try {
    localStorage.removeItem("kotibot.tapo.lightSchemes");
    localStorage.removeItem("kotibot.tapo.activeLightSchemes");
  } catch (err) {
    console.warn("[clearLegacyTapoLocalLightingState] failed", err);
  }
}

async function loadTapoLightingState({ force = false } = {}) {
  const state = getTapoLightingState();

  if (state.loaded && !force) {
    return state;
  }

  if (tapoLightingStateLoadPromise && !force) {
    return tapoLightingStateLoadPromise;
  }

  const fetcher = typeof window.dashboardFetch === "function"
    ? window.dashboardFetch
    : window.fetch.bind(window);

  tapoLightingStateLoadPromise = fetcher(`/api/tapo/lighting-state?t=${Date.now()}`, {
    cache: "no-store"
  })
    .then(async res => {
      let data = {};

      try {
        data = await res.json();
      } catch (err) {
        data = {};
      }

      if (!res.ok || data.ok === false) {
        throw new Error(data.error || `Tapo lighting state failed: ${res.status}`);
      }

      const nextState = mergeTapoLightingState(data);
      clearLegacyTapoLocalLightingState();

      return nextState;
    })
    .catch(err => {
      console.warn("[loadTapoLightingState] failed", err);
      return getTapoLightingState();
    })
    .finally(() => {
      tapoLightingStateLoadPromise = null;
    });

  return tapoLightingStateLoadPromise;
}

window.loadTapoLightingState = loadTapoLightingState;

async function saveTapoLightingStateNow() {
  const state = getTapoLightingState();

  const res = await fetch("/api/tapo/lighting-state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      schemes: state.schemes,
      activeSchemes: state.activeSchemes,
      modeConfig: state.modeConfig
    })
  });

  let data = {};

  try {
    data = await res.json();
  } catch (err) {
    data = {};
  }

  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Tapo lighting save failed: ${res.status}`);
  }

  mergeTapoLightingState(data);

  return data;
}

function queueTapoLightingStateSave() {
  window.clearTimeout(tapoLightingStateSaveTimer);

  tapoLightingStateSaveTimer = window.setTimeout(() => {
    saveTapoLightingStateNow()
      .catch(err => console.warn("[saveTapoLightingStateNow] failed", err));
  }, 150);
}

function readTapoLightingSchemes() {
  return getTapoLightingState().schemes;
}

function writeTapoLightingSchemes(schemes) {
  getTapoLightingState().schemes = schemes && typeof schemes === "object"
    ? schemes
    : {};

  queueTapoLightingStateSave();
}

function readTapoActiveLightingSchemes() {
  return getTapoLightingState().activeSchemes;
}

function writeTapoActiveLightingSchemes(activeSchemes) {
  getTapoLightingState().activeSchemes = activeSchemes && typeof activeSchemes === "object"
    ? activeSchemes
    : {};

  queueTapoLightingStateSave();
}

function setTapoActiveLightingSchemeForKey(key, mode) {
  if (!key || !mode) return;

  const activeSchemes = readTapoActiveLightingSchemes();

  activeSchemes[key] = mode;
  writeTapoActiveLightingSchemes(activeSchemes);
}

function clearTapoActiveLightingSchemeForKey(key) {
  if (!key) return;

  const activeSchemes = readTapoActiveLightingSchemes();

  activeSchemes[key] = "";
  writeTapoActiveLightingSchemes(activeSchemes);
}

function setTapoSchemeButtonActiveState(button, isActive) {
  if (!button) return;

  const row = button.closest(".tapo-scheme-button-row");

  if (row && isActive) {
    row.querySelectorAll(".tapo-scheme-toggle.active").forEach(activeButton => {
      if (activeButton !== button) {
        activeButton.classList.remove("active");
        activeButton.setAttribute("aria-pressed", "false");
      }
    });
  }

  button.classList.toggle("active", isActive);
  button.setAttribute("aria-pressed", isActive ? "true" : "false");
}

function getTapoLightingSchemesForKey(key) {
  const schemes = readTapoLightingSchemes();

  return key ? schemes[key] || [] : [];
}

function getTapoLightingSchemeForKey(key, mode) {
  return getTapoLightingSchemesForKey(key)
    .find(scheme => scheme.mode === mode);
}

function setTapoLightingSchemeFavoriteForKey(key, mode, isFavorite) {
  if (!key || !mode) return;

  const schemes = readTapoLightingSchemes();
  const targetSchemes = schemes[key] || [];
  const targetIndex = targetSchemes.findIndex(scheme => scheme.mode === mode);
  const existingScheme = targetIndex >= 0 ? targetSchemes[targetIndex] : null;
  const builtinScheme = getTapoBuiltinLightingScheme(mode);

  if (!existingScheme && !builtinScheme) return;

  const targetScheme = {
    mode,
    label: existingScheme?.label || getTapoLightingSchemeLabel(mode),
    icon: existingScheme?.icon || getTapoLightingSchemeIcon(mode),
    preset: existingScheme?.preset || getTapoLightingModePreset(mode),
    savedAt: existingScheme?.savedAt || Date.now(),
    favorite: isFavorite
  };

  if (targetIndex >= 0) {
    targetSchemes[targetIndex] = {
      ...existingScheme,
      favorite: isFavorite
    };
  } else {
    targetSchemes.push(targetScheme);
  }

  schemes[key] = targetSchemes;
  writeTapoLightingSchemes(schemes);
}

function getTapoSavedLightingSchemes() {
  const key = getTapoLightingSchemeTargetKey();
  const schemes = readTapoLightingSchemes();

  return key ? schemes[key] || [] : [];
}

function getTapoSavedLightingScheme(mode) {
  return getTapoSavedLightingSchemes()
    .find(scheme => scheme.mode === mode);
}

function getTapoLightingModeStoredPreset(mode) {
  const savedPreset = getTapoSavedLightingScheme(mode)?.preset;
  if (savedPreset) return savedPreset;

  const target = activeTapoLight();
  if (target.deviceID && !target.deviceIDs) {
    return getTapoRoomDefaultPresetForDevice(target.deviceID, mode) || getTapoLightingModePreset(mode);
  }

  return getTapoLightingModePreset(mode);
}

function getTapoLightingDeviceKey(deviceID) {
  const cleanID = String(deviceID || "").trim();

  return cleanID ? `device:${cleanID}` : "";
}

function getTapoLightingRoomKeyFromDeviceIDs(deviceIDs = []) {
  const ids = deviceIDs
    .map(deviceID => String(deviceID || "").trim())
    .filter(Boolean)
    .sort();

  return ids.length ? `room:${ids.join(",")}` : "";
}

function getTapoLightingRoomSchemeMatchForDevice(deviceID = "") {
  const cleanDeviceID = String(deviceID || "").trim();
  const client = tapoAllCurrentClients().find(c => String(c?.deviceID || "").trim() === cleanDeviceID);
  const roomName = tapoClientRoomName(client) || document.getElementById("tapoLightModal")?.dataset.tapoRoom || "";
  const roomKey = String(roomName || "").trim().toLowerCase();

  if (!cleanDeviceID || !roomKey) {
    return { key: "", ids: [] };
  }

  const roomLightIDs = tapoAllCurrentClients()
    .filter(candidate => candidate?.provisioned)
    .filter(tapoClientIsRoomLight)
    .filter(candidate => tapoRoomPowerEnabledForClient(candidate))
    .filter(candidate => tapoClientRoomName(candidate).toLowerCase() === roomKey)
    .map(candidate => String(candidate?.deviceID || "").trim())
    .filter(Boolean)
    .sort();

  const exactKey = getTapoLightingRoomKeyFromDeviceIDs(roomLightIDs.length ? roomLightIDs : [cleanDeviceID]);
  const schemes = readTapoLightingSchemes();

  if (schemes[exactKey]) {
    return { key: exactKey, ids: roomLightIDs };
  }

  const wantedSet = new Set(roomLightIDs.length ? roomLightIDs : [cleanDeviceID]);
  const candidates = Object.keys(schemes)
    .filter(key => key.startsWith("room:"))
    .map(key => {
      const keyIDs = key
        .replace(/^room:/, "")
        .split(",")
        .map(id => id.trim())
        .filter(Boolean)
        .sort();
      const keyIDSet = new Set(keyIDs);
      const keyContainsWanted = Array.from(wantedSet).every(id => keyIDSet.has(id));
      const wantedContainsKey = keyIDs.every(id => wantedSet.has(id));
      const hasTargetDevice = keyIDSet.has(cleanDeviceID);

      return {
        key,
        match: hasTargetDevice && (keyContainsWanted || wantedContainsKey),
        distance: Math.abs(keyIDs.length - wantedSet.size)
      };
    })
    .filter(candidate => candidate.match)
    .sort((a, b) => a.distance - b.distance);

  return candidates[0] || { key: exactKey, ids: roomLightIDs };
}

function getTapoRoomDefaultPresetForDevice(deviceID, mode) {
  const roomMatch = getTapoLightingRoomSchemeMatchForDevice(deviceID);
  const roomScheme = getTapoLightingSchemeForKey(roomMatch.key, mode);

  return roomScheme?.preset || null;
}

function getTapoLightingPresetForDeviceID(deviceID, mode, fallbackPreset = null) {
  const deviceScheme = getTapoLightingSchemeForKey(getTapoLightingDeviceKey(deviceID), mode);

  return deviceScheme?.preset || fallbackPreset || getTapoLightingModePreset(mode);
}

async function sendTapoLightingPresetToDevice(deviceID, preset, mode = "") {
  if (!deviceID || !preset) return;

  const client = (S.currentClients || []).find(c => c.deviceID === deviceID);
  const target = tapoResolveDashboardDeviceTarget(deviceID);
  const commandDeviceID = target.deviceID || deviceID;

  if (preset.brightness != null && (!client || client.tapo_supports_brightness !== false)) {
    await sendTapoCommand({ deviceID: commandDeviceID, action: "brightness_no_power", value: preset.brightness, verify: false, lightingMode: mode });
  }

  if (preset.hue != null && (!client || client.tapo_supports_color !== false)) {
    await sendTapoCommand({
      deviceID: commandDeviceID,
      action: "color_no_power",
      value: {
        hue: preset.hue,
        saturation: preset.saturation
      },
      verify: false,
      lightingMode: mode
    });
  } else if (preset.colorTemperature != null && (!client || client.tapo_supports_color !== false)) {
    await sendTapoCommand({
      deviceID: commandDeviceID,
      action: "color_no_power",
      value: {
        hue: tapoWhiteHueFromKelvin(preset.colorTemperature),
        saturation: normalizeTapoWhiteSaturation(preset.whiteSaturation),
        colorTemperature: preset.colorTemperature,
        whiteSaturation: normalizeTapoWhiteSaturation(preset.whiteSaturation)
      },
      verify: false,
      lightingMode: mode
    });
  } else if (preset.colorTemperature != null && (!client || client.tapo_supports_color_temp !== false)) {
    await sendTapoCommand({
      deviceID: commandDeviceID,
      action: "color_temperature_no_power",
      value: preset.colorTemperature,
      verify: false,
      lightingMode: mode
    });
  }
}

function handleTapoLightingPresetResults(ids, results, logLabel) {
  const failedIDs = new Set();

  results.forEach((result, index) => {
    if (result.status !== "rejected") return;

    const deviceID = ids[index];
    failedIDs.add(deviceID);
    clearTapoPendingPowerState(deviceID);

    console.warn(logLabel, result.reason);

    updateTapoCardState({
      deviceID,
      is_on: null,
      tapo_is_on: null,
      device_on: null,
      state: null,
      tapo_control_ready: false,
      tapo_control_error: result.reason?.message || String(result.reason || "Tapo command failed")
    });
  });

  return failedIDs;
}

async function applyTapoLightingModePresetToDeviceIDs(deviceIDs = [], mode = "", opts = {}) {
  const ids = deviceIDs
    .map(deviceID => String(deviceID || "").trim())
    .filter(Boolean);

  if (!ids.length || !mode) return;

  const fallbackPreset = opts.fallbackPreset || getTapoLightingModePreset(mode);

  if (opts.updateUi !== false) {
    setTapoLightingModeUi(
      getTapoLightingPresetForDeviceID(ids[0], mode, fallbackPreset)
    );
  }

  const results = await Promise.allSettled(ids.map(deviceID => (
    sendTapoLightingPresetToDevice(
      deviceID,
      getTapoLightingPresetForDeviceID(deviceID, mode, fallbackPreset),
      mode
    )
  )));
  const failedIDs = handleTapoLightingPresetResults(
    ids,
    results,
    "[applyTapoLightingModePresetToDeviceIDs] device failed"
  );
  const preparedIDs = ids.filter(deviceID => !failedIDs.has(deviceID));

  if (failedIDs.size >= results.length) {
    throw results.find(
      result => result.status === "rejected"
    )?.reason || new Error("Lighting scheme failed");
  }

  const targetIDs = opts.powerOn === true
    ? await powerOnTapoLightingPresetDeviceIDs(preparedIDs)
    : preparedIDs;

  if (targetIDs.some(deviceID => !failedIDs.has(deviceID))) {
    scheduleTapoCommandRefresh(750);
  }
}

window.applyTapoLightingModePresetToDeviceIDs = applyTapoLightingModePresetToDeviceIDs;

function getTapoCustomLightingSchemes() {
  return getTapoSavedLightingSchemes()
    .filter(scheme => String(scheme.mode || "").startsWith("custom:"));
}

function removeTapoDeviceLightingSchemeOverrides(schemes, deviceIDs = [], mode = "") {
  if (!schemes || !mode) return;

  deviceIDs
    .map(deviceID => String(deviceID || "").trim())
    .filter(Boolean)
    .forEach(deviceID => {
      const key = getTapoLightingDeviceKey(deviceID);
      const targetSchemes = Array.isArray(schemes[key]) ? schemes[key] : [];
      const remainingSchemes = targetSchemes.filter(scheme => scheme?.mode !== mode);

      if (remainingSchemes.length) {
        schemes[key] = remainingSchemes;
      } else {
        delete schemes[key];
      }
    });
}

function clearTapoActiveDeviceLightingSchemes(deviceIDs = [], mode = "") {
  const activeSchemes = readTapoActiveLightingSchemes();
  let changed = false;

  deviceIDs
    .map(deviceID => String(deviceID || "").trim())
    .filter(Boolean)
    .forEach(deviceID => {
      const key = getTapoLightingDeviceKey(deviceID);

      if (!key || !Object.prototype.hasOwnProperty.call(activeSchemes, key)) return;
      if (mode && activeSchemes[key] && activeSchemes[key] !== mode) return;

      delete activeSchemes[key];
      changed = true;
    });

  if (changed) writeTapoActiveLightingSchemes(activeSchemes);
}

function saveTapoLightingScheme(mode, opts = {}) {
  const keys = getTapoLightingSchemeStorageKeys();

  if (!keys.length) {
    alert("No Tapo light target found.");
    return;
  }

  const target = activeTapoLight();
  const roomDeviceIDs = target.deviceIDs ? tapoDeviceIDList(target.deviceIDs) : [];
  const preset = opts.preset || getCurrentTapoLightingPreset();
  const nextScheme = {
    mode,
    label: opts.label || getTapoLightingSchemeLabel(mode),
    icon: opts.icon || getTapoLightingSchemeIcon(mode),
    preset,
    savedAt: Date.now()
  };

  const schemes = readTapoLightingSchemes();
  const keepFavorite = tapoLightingSchemeWasFavorite(schemes, keys, mode);

  keys.forEach(key => {
    const targetSchemes = Array.isArray(schemes[key]) ? schemes[key] : [];
    const existingIndex = targetSchemes.findIndex(scheme => scheme.mode === mode);
    const targetScheme = {
      ...nextScheme,
      favorite: keepFavorite
    };

    if (existingIndex >= 0) {
      targetSchemes[existingIndex] = targetScheme;
    } else {
      targetSchemes.push(targetScheme);
    }

    schemes[key] = targetSchemes;
  });

  if (roomDeviceIDs.length) {
    removeTapoDeviceLightingSchemeOverrides(schemes, roomDeviceIDs, mode);
    clearTapoActiveDeviceLightingSchemes(roomDeviceIDs, mode);
  }

  writeTapoLightingSchemes(schemes);
  hideTapoLightSchemePicker();
  setTapoSliderDirty(false);
  renderTapoLightingSchemeLists();
  setTapoActiveLightingScheme(mode);
  syncTapoSetSchemeButtonLabel();
  syncTapoRoomDefaultResetButton();
  refreshTapoDashboardView();
}

function createTapoCustomLightingScheme() {
  const label = prompt("Scheme name?", "Custom");

  if (!label) return;

  saveTapoLightingScheme(`custom:${Date.now()}`, {
    label: label.trim(),
    icon: "tune",
    preset: getCurrentTapoLightingPreset()
  });
}

function renderTapoBuiltinLightingSchemeRows({ actionAttr }) {
  return TAPO_BUILTIN_LIGHTING_SCHEMES.map(scheme => `
      <div class="client-menu-btn tapo-light-scheme-row">
        <button class="tapo-light-scheme-main power-toggle" type="button" ${actionAttr}="${esc(scheme.mode)}">
          ${window.dashboardIconHtml(scheme.icon)}
          <span>${esc(scheme.label)}</span>
        </button>
        <button
          class="tapo-light-scheme-favorite power-toggle"
          type="button"
          title="Favorite scheme"
          aria-label="Favorite scheme"
          data-tapo-favorite-scheme-mode="${esc(scheme.mode)}"
        >${window.dashboardIconHtml("star")}</button>
        <button
          class="tapo-light-scheme-settings"
          type="button"
          title="Show ${esc(scheme.label)} settings"
          aria-label="Show ${esc(scheme.label)} settings"
          data-tapo-lighting-settings-mode="${esc(scheme.mode)}"
        >${window.dashboardIconHtml("settings")}</button>
      </div>
    `).join("");
}

function renderTapoLightingSchemeLists() {
  const builtinWrap = document.getElementById("tapoBuiltinSchemes");
  const savedWrap = document.getElementById("tapoSavedSchemes");
  const setBuiltinWrap = document.getElementById("tapoSchemeSetBuiltinActions");
  const setCustomWrap = document.getElementById("tapoSchemeSetCustomActions");
  const customSchemes = getTapoCustomLightingSchemes();
  const targetKey = getTapoLightingSchemeTargetKey();

  if (builtinWrap) {
    builtinWrap.innerHTML = renderTapoBuiltinLightingSchemeRows({
      actionAttr: "data-tapo-lighting-mode"
    });
  }

  if (savedWrap) {
    savedWrap.hidden = !customSchemes.length;
    savedWrap.innerHTML = customSchemes.map((scheme, index) => `
      <div class="tapo-light-scheme-row">
        <button class="client-menu-btn tapo-light-scheme-main power-toggle" type="button" aria-pressed="false" data-tapo-custom-scheme-index="${index}" data-tapo-custom-scheme-mode="${esc(scheme.mode || "")}">
          ${window.dashboardIconHtml(scheme.icon || "tune")}
          <span>${esc(scheme.label || "Custom")}</span>
        </button>
        <button
          class="tapo-light-scheme-favorite power-toggle ${scheme.favorite ? "active" : ""}"
          type="button"
          title="${scheme.favorite ? "Remove favorite" : "Favorite scheme"}"
          aria-label="${scheme.favorite ? "Remove favorite" : "Favorite scheme"}"
          aria-pressed="${scheme.favorite ? "true" : "false"}"
          data-tapo-favorite-scheme-mode="${esc(scheme.mode || "")}"
        >${window.dashboardIconHtml("star")}</button>
      </div>
    `).join("");
  }

  if (setBuiltinWrap) {
    setBuiltinWrap.innerHTML = TAPO_BUILTIN_LIGHTING_SCHEMES.map(scheme => `
      <button class="client-menu-btn power-toggle" type="button" data-tapo-set-scheme-mode="${esc(scheme.mode)}">
        ${window.dashboardIconHtml(scheme.icon)}
        <span>${esc(scheme.label)}</span>
      </button>
    `).join("");
  }

  if (setCustomWrap) {
    setCustomWrap.hidden = !customSchemes.length;
    setCustomWrap.innerHTML = customSchemes.map((scheme, index) => `
      <button class="client-menu-btn power-toggle" type="button" data-tapo-set-custom-scheme-index="${index}" data-tapo-set-custom-scheme-mode="${esc(scheme.mode || "")}">
        ${window.dashboardIconHtml(scheme.icon || "tune")}
        <span>${esc(scheme.label || "Custom")}</span>
      </button>
    `).join("");
  }

  document.querySelectorAll("[data-tapo-favorite-scheme-mode]").forEach(button => {
    const mode = button.dataset.tapoFavoriteSchemeMode || "";
    const isFavorite = isTapoLightingSchemeFavoriteForKey(targetKey, mode);

    window.setDashboardIcon(button.querySelector(".koti-icon"), "star");
    button.classList.toggle("active", isFavorite);
    button.title = isFavorite ? "Remove favorite" : "Favorite scheme";
    button.setAttribute("aria-label", isFavorite ? "Remove favorite" : "Favorite scheme");

    button.onclick = event => {
      event.preventDefault();
      event.stopPropagation();

      const nextKey = getTapoLightingSchemeTargetKey();
      const nextFavorite = !button.classList.contains("active");

      setTapoLightingSchemeFavoriteForTargetKey(nextKey, mode, nextFavorite);
      renderTapoLightingSchemeLists();
      refreshTapoDashboardView();
    };
  });

  syncTapoLightSchemeSettingsButtons();
  setTapoActiveLightingScheme(document.getElementById("tapoLightModal")?.dataset.activeSchemeMode || "");
}

function syncTapoLightSchemeSettingsButtons() {
  const modal = document.getElementById("tapoLightModal");
  const settingsMode = modal?.dataset.lightControlsMode || "";

  document.querySelectorAll("[data-tapo-lighting-settings-mode]").forEach(button => {
    const isActive = Boolean(settingsMode) && button.dataset.tapoLightingSettingsMode === settingsMode;

    button.classList.toggle("active", isActive);
    button.title = isActive ? "Hide light settings" : `Show ${getTapoLightingSchemeLabel(button.dataset.tapoLightingSettingsMode || "")} settings`;
    button.setAttribute("aria-label", button.title);
  });
}

function syncTapoSetSchemeButtonLabel() {
  const modal = document.getElementById("tapoLightModal");
  const label = document.getElementById("tapoSetSchemeBtnLabel");
  const subtitle = document.getElementById("tapoSetSchemeBtnSubtitle");
  const mode = modal?.dataset.lightControlsMode || "";
  const targetLabel = getTapoLightingScopeLabel();
  const roomLabel = String(modal?.dataset.tapoRoom || "").trim();
  const isRoom = modal?.dataset.roomSettings === "1";
  const subtitleTarget = !isRoom && roomLabel && targetLabel && roomLabel !== targetLabel
    ? `${roomLabel} ${targetLabel}`
    : targetLabel;

  if (label) label.textContent = "Save Preset";

  if (subtitle) {
    const subtitleText = mode ? `${subtitleTarget} - ${getTapoLightingSchemeLabel(mode)}` : "";

    subtitle.textContent = subtitleText;
    subtitle.hidden = !subtitleText;
  }
}

function getTapoLightingResetDefaultPreset(mode) {
  const modal = document.getElementById("tapoLightModal");
  const isRoom = modal?.dataset.roomSettings === "1";
  const deviceID = modal?.dataset.deviceId || "";

  if (!mode) return null;
  if (isRoom) return getTapoLightingModePreset(mode);

  return getTapoRoomDefaultPresetForDevice(deviceID, mode) || getTapoLightingModePreset(mode);
}

function getTapoLightingResetDefaultLabel() {
  const modal = document.getElementById("tapoLightModal");

  return modal?.dataset.roomSettings === "1" ? "Reset to App Default" : "Reset to Room Default";
}

function syncTapoRoomDefaultResetButton() {
  const modal = document.getElementById("tapoLightModal");
  const button = document.getElementById("tapoResetRoomDefaultBtn");
  const label = document.getElementById("tapoResetDefaultBtnLabel");
  if (!modal || !button) return;

  const mode = modal.dataset.lightControlsMode || "";
  const hasControls = Boolean(mode);
  const defaultPreset = hasControls ? getTapoLightingResetDefaultPreset(mode) : null;
  const targetKey = getTapoLightingSchemeTargetKey();
  const storedScheme = getTapoLightingSchemeForKey(targetKey, mode);
  const currentPreset = hasControls ? getCurrentTapoLightingPreset() : null;
  const comparePreset = storedScheme?.preset || currentPreset;
  const show = Boolean(defaultPreset && comparePreset && !tapoLightingPresetsMatch(comparePreset, defaultPreset));

  if (label) label.textContent = getTapoLightingResetDefaultLabel();
  button.hidden = !show;
  button.disabled = !show;
}

function toggleTapoLightingSchemeSettings(mode) {
  const modal = document.getElementById("tapoLightModal");
  if (!modal || !mode) return;

  const nextMode = modal.dataset.lightControlsMode === mode ? "" : mode;

  modal.dataset.schemePicker = "0";
  modal.dataset.lightControlsMode = nextMode;

  if (nextMode) {
    setTapoLightingModeUi(getTapoLightingModeStoredPreset(nextMode));
  }

  setTapoSliderDirty(false);
  syncTapoLightVisibility();
  syncTapoLightSchemeSettingsButtons();
}

function handleTapoSetSchemeButton() {
  const mode = document.getElementById("tapoLightModal")?.dataset.lightControlsMode || "";

  if (mode) {
    saveTapoLightingScheme(mode, {
      preset: getCurrentTapoLightingPreset()
    });
    syncTapoRoomDefaultResetButton();
    return;
  }

  showTapoLightSchemePicker();
}

async function handleTapoResetRoomDefaultButton() {
  const modal = document.getElementById("tapoLightModal");
  const mode = modal?.dataset.lightControlsMode || "";
  const targetKey = getTapoLightingSchemeTargetKey();
  const deviceIDs = getTapoLightingModeTargets();
  const defaultPreset = getTapoLightingResetDefaultPreset(mode);
  const resetLabel = getTapoLightingResetDefaultLabel().toLowerCase();

  if (!modal || !mode || !targetKey || !deviceIDs.length || !defaultPreset) return;

  const schemes = readTapoLightingSchemes();
  const targetSchemes = (schemes[targetKey] || []).filter(scheme => scheme?.mode !== mode);

  if (targetSchemes.length) {
    schemes[targetKey] = targetSchemes;
  } else {
    delete schemes[targetKey];
  }

  writeTapoLightingSchemes(schemes);
  setTapoLightingModeUi(defaultPreset);
  setTapoSliderDirty(false);
  setTapoActiveLightingScheme(mode);

  try {
    await applyTapoLightingPresetToDeviceIDs(deviceIDs, defaultPreset, { mode });
  } catch (err) {
    console.warn("[reset lighting default] failed", err);
    alert(`${resetLabel} failed. Check console/server logs.`);
  } finally {
    syncTapoRoomDefaultResetButton();
    renderTapoLightingSchemeLists();
  }
}

function setTapoActiveLightingScheme(mode) {
  const modal = document.getElementById("tapoLightModal");
  if (!modal) return;

  modal.dataset.activeSchemeMode = mode || "";

  modal
    .querySelectorAll("[data-tapo-lighting-mode], [data-tapo-custom-scheme-mode], [data-tapo-set-scheme-mode], [data-tapo-set-custom-scheme-mode]")
    .forEach(button => {
      const buttonMode =
        button.dataset.tapoLightingMode ||
        button.dataset.tapoCustomSchemeMode ||
        button.dataset.tapoSetSchemeMode ||
        button.dataset.tapoSetCustomSchemeMode ||
        "";

      const isActive = Boolean(mode) && buttonMode === mode;

      button.classList.toggle("active", isActive);
      button.closest(".tapo-light-scheme-row")?.classList.toggle("active", isActive);
    });
}

function setTapoSliderDirty(isDirty) {
  const modal = document.getElementById("tapoLightModal");

  if (modal) {
    modal.dataset.sliderDirty = isDirty ? "1" : "0";

    if (isDirty) {
      setTapoActiveLightingScheme("");
    }
  }

  syncTapoRoomDefaultResetButton();
}

function setTapoLightingModeUi(preset) {
  const brightness = Number(preset.brightness || 100);

  document.getElementById("tapoWhiteBrightnessSlider").value = brightness;
  document.getElementById("tapoColorBrightnessSlider").value = brightness;
  document.getElementById("tapoWhiteBrightnessValue").textContent = `${brightness}%`;
  document.getElementById("tapoColorBrightnessValue").textContent = `${brightness}%`;

  if (preset.hue != null) {
    document.getElementById("tapoHueSlider").value = preset.hue;
    document.getElementById("tapoSaturationSlider").value = preset.saturation;
    document.getElementById("tapoColorValue").textContent = `${preset.hue}°`;
    document.getElementById("tapoSaturationValue").textContent = `${preset.saturation}%`;
    setTapoLightMode("color", { send: false });
    return;
  }

  setTapoWhiteTemperature(preset.colorTemperature);
  setTapoLightMode("white", { send: false });
}

async function applyTapoLightingPreset(preset, mode = "") {
  const deviceIDs = getTapoLightingModeTargets();

  if (!deviceIDs.length) {
    alert("No Tapo lights found.");
    return;
  }

  setTapoLightingModeUi(preset);

  const results = await Promise.allSettled(deviceIDs.map(deviceID => (
    sendTapoLightingPresetToDevice(deviceID, preset, mode)
  )));
  const failedIDs = handleTapoLightingPresetResults(deviceIDs, results, "[applyTapoLightingPreset] device failed");

  if (deviceIDs.some(deviceID => !failedIDs.has(deviceID))) {
    scheduleTapoCommandRefresh(750);
  }

  if (failedIDs.size >= results.length) {
    alert("Lighting scheme failed. Check console/server logs.");
  }
}

async function powerOnTapoLightingPresetDeviceIDs(deviceIDs = []) {
  const ids = Array.from(new Set(
    deviceIDs
      .map(deviceID => String(deviceID || "").trim())
      .filter(Boolean)
  ));

  if (!ids.length) return [];

  const idsToPowerOn = ids.filter(deviceID => {
    const client = (S.currentClients || []).find(candidate => (
      String(candidate?.deviceID || "").trim() === deviceID
    ));
    const isOn = tapoBool(
      client?.tapo_is_on ??
      client?.is_on ??
      client?.device_on ??
      client?.state
    );

    return isOn !== true;
  });

  if (!idsToPowerOn.length) return ids;

  const results = await Promise.allSettled(idsToPowerOn.map(deviceID => (
    sendTapoCommand({
      deviceID,
      action: "on",
      verify: false,
      skipHomeLightingMode: true
    })
  )));
  const failedIDs = handleTapoLightingPresetResults(
    idsToPowerOn,
    results,
    "[powerOnTapoLightingPresetDeviceIDs] device failed"
  );
  const successfulPowerOnIDs = idsToPowerOn.filter(
    deviceID => !failedIDs.has(deviceID)
  );

  await refreshTapoPowerAfterCommand(successfulPowerOnIDs, true);

  if (
    failedIDs.size >= results.length &&
    idsToPowerOn.length === ids.length
  ) {
    throw results.find(
      result => result.status === "rejected"
    )?.reason || new Error("Lighting scheme power on failed");
  }

  return ids.filter(deviceID => !failedIDs.has(deviceID));
}

async function applyTapoLightingPresetToDeviceIDs(deviceIDs = [], preset, opts = {}) {
  const ids = deviceIDs
    .map(deviceID => String(deviceID || "").trim())
    .filter(Boolean);

  if (!ids.length || !preset) return;

  const results = await Promise.allSettled(ids.map(deviceID => (
    sendTapoLightingPresetToDevice(
      deviceID,
      preset,
      opts.mode || ""
    )
  )));
  const failedIDs = handleTapoLightingPresetResults(
    ids,
    results,
    "[applyTapoLightingPresetToDeviceIDs] device failed"
  );
  const preparedIDs = ids.filter(deviceID => !failedIDs.has(deviceID));

  if (failedIDs.size >= results.length) {
    throw results.find(
      result => result.status === "rejected"
    )?.reason || new Error("Lighting scheme failed");
  }

  const targetIDs = opts.powerOn === true
    ? await powerOnTapoLightingPresetDeviceIDs(preparedIDs)
    : preparedIDs;

  if (targetIDs.some(deviceID => !failedIDs.has(deviceID))) {
    scheduleTapoCommandRefresh(750);
  }
}

function readTapoLightingPresetFromButton(button) {
  const raw = button?.dataset?.tapoSchemePreset || "";
  if (!raw) return null;

  try {
    const preset = JSON.parse(raw);

    return preset && typeof preset === "object" ? preset : null;
  } catch (err) {
    console.warn("[readTapoLightingPresetFromButton] failed", err);
    return null;
  }
}

async function applyTapoLightingSchemeFromButton(button) {
  const key = button.dataset.tapoSchemeKey || "";
  const mode = button.dataset.tapoSchemeMode || "";
  const deviceIDs = String(button.dataset.tapoDeviceIds || "")
    .split(",")
    .map(deviceID => deviceID.trim())
    .filter(Boolean);
  const scheme = getTapoLightingSchemeForKey(key, mode);
  const preset = readTapoLightingPresetFromButton(button) || scheme?.preset || getTapoLightingModePreset(mode);

  if (!preset || !deviceIDs.length) return;

  const previousActiveSchemes = { ...readTapoActiveLightingSchemes() };

  setTapoActiveLightingSchemeForKey(key, mode);
  setTapoSchemeButtonActiveState(button, true);

  try {
    await applyTapoLightingModePresetToDeviceIDs(deviceIDs, mode, {
      fallbackPreset: preset,
      updateUi: false,
      powerOn: true
    });
  } catch (err) {
    console.warn("[scheme apply] failed", err);

    writeTapoActiveLightingSchemes(previousActiveSchemes);
    setTapoSchemeButtonActiveState(button, false);
    refreshTapoDashboardView();
  }
}

window.applyTapoLightingMode = async function (mode) {
  const targetKey = getTapoLightingSchemeTargetKey() || "home";
  const targetPreset = getTapoLightingModeStoredPreset(mode);

  setTapoSliderDirty(false);
  setTapoActiveLightingScheme(mode);

  if (targetKey === "home") {
    writeTapoActiveLightingSchemes({ home: mode });
  } else {
    setTapoActiveLightingSchemeForKey(targetKey, mode);
  }

  await saveTapoLightingStateNow();
  await applyTapoLightingModePresetToDeviceIDs(getTapoLightingModeTargets(), mode, {
    fallbackPreset: targetPreset
  });
};

function tapoBool(value) {
  if (value === true || value === false) return value;

  const text = String(value ?? "").trim().toLowerCase();

  if (["1", "true", "on", "yes", "enabled"].includes(text)) return true;
  if (["0", "false", "off", "no", "disabled"].includes(text)) return false;

  return null;
}

function mergeTapoClientState(device) {
  if (!device || typeof device !== "object") return device;

  const deviceID = device.deviceID || device._client_deviceID || "";
  const patch = { ...device };

  if (patch.tapo_brightness == null && patch.brightness != null) {
    patch.tapo_brightness = patch.brightness;
  }

  if (patch.tapo_color_temperature == null && patch.color_temperature != null) {
    patch.tapo_color_temperature = patch.color_temperature;
  }

  if (patch.tapo_hue == null && patch.hue != null) {
    patch.tapo_hue = patch.hue;
  }

  if (patch.tapo_saturation == null && patch.saturation != null) {
    patch.tapo_saturation = patch.saturation;
  }

  if (patch.tapo_is_on == null && patch.is_on != null) {
    patch.tapo_is_on = patch.is_on;
  }

  if (!Array.isArray(patch.tapo_children) && Array.isArray(patch.children)) {
    patch.tapo_children = patch.children;
  }

  if (!deviceID || !Array.isArray(S.currentClients)) {
    return patch;
  }

  const index = S.currentClients.findIndex(c => c.deviceID === deviceID);

  if (index >= 0) {
    S.currentClients[index] = {
      ...S.currentClients[index],
      ...patch
    };

    return S.currentClients[index];
  }

  return patch;
}

function tapoExtenderChildDisplayName(device, child, index = 0) {
  const position = String(child?.position ?? child?.index ?? index + 1).trim() || String(index + 1);

  return String(
    child?.clientName
    || child?.alias
    || child?.nickname
    || child?.name
    || `Outlet ${position}`
  ).trim();
}

function updateTapoCardState(device) {
  device = applyTapoPendingPowerState(mergeTapoClientState(device));

  const children = Array.isArray(device.children)
    ? device.children
    : Array.isArray(device.tapo_children)
      ? device.tapo_children
      : [];
  const selector = device.deviceID
    ? `.tapo-client-card[data-device-id="${CSS.escape(device.deviceID)}"]`
    : `.tapo-card[data-id="${CSS.escape(device.id)}"]`;
  const childCardSelector = device.deviceID && children.length
    ? children.map((child, index) => {
        const childID = String(
          child?.id
          ?? child?.device_id
          ?? child?.deviceId
          ?? child?.child_id
          ?? child?.childId
          ?? child?.index
          ?? index + 1
        ).trim();

        return childID
          ? `.tapo-client-card[data-tapo-parent-device-id="${CSS.escape(device.deviceID)}"][data-tapo-child-id="${CSS.escape(childID)}"]`
          : "";
      }).filter(Boolean).join(",")
    : "";

  const card = document.querySelector(selector);
  const hasChildCards = childCardSelector ? Boolean(document.querySelector(childCardSelector)) : false;
  if (!card && !hasChildCards) return;

  const rawPower = tapoBool(device.is_on ?? device.tapo_is_on ?? device.device_on ?? device.state);

  if (children.length) {
    children.forEach((child, index) => {
      if (!child || typeof child !== "object") return;

      const childID = String(
        child.id
        ?? child.device_id
        ?? child.deviceId
        ?? child.child_id
        ?? child.childId
        ?? child.index
        ?? index + 1
      ).trim();

      if (!childID) return;

      const childCard = device.deviceID
        ? document.querySelector(`.tapo-client-card[data-tapo-parent-device-id="${CSS.escape(device.deviceID)}"][data-tapo-child-id="${CSS.escape(childID)}"]`)
        : null;
      const scope = childCard || card;
      const toggle = scope?.querySelector(`.tapo-power-toggle[data-tapo-child-id="${CSS.escape(childID)}"], .tapo-power-toggle`);
      if (!toggle) return;

      const childPower = tapoBool(child.is_on ?? child.device_on ?? child.on ?? child.state);
      const isOn = childPower === true;
      const isUnknown = childPower !== true && childPower !== false;
      const childName = tapoExtenderChildDisplayName(device, child, index);
      const nextPowerState = isOn ? "on" : isUnknown ? "unknown" : "off";

      toggle.dataset.tapoAction = isOn ? "off" : "on";
      toggle.dataset.tapoPowerState = nextPowerState;
      toggle.classList.toggle("active", isOn);
      toggle.classList.toggle("unknown", isUnknown);
      scope?.querySelector(".card-head")?.setAttribute("data-tapo-power-state", nextPowerState);

      const title = isOn
        ? `Turn Off ${childName}`
        : isUnknown
          ? `State unknown — Turn On ${childName}`
          : `Turn On ${childName}`;

      toggle.title = title;
      toggle.setAttribute("aria-label", title);
    });
  } else if (card) {
    const toggle = card.querySelector(".tapo-power-toggle");

    if (toggle) {
      const isOn = rawPower === true;
      const isUnknown = rawPower !== true && rawPower !== false;

      toggle.dataset.tapoAction = isOn ? "off" : "on";
      toggle.dataset.tapoPowerState = isOn ? "on" : isUnknown ? "unknown" : "off";
      toggle.classList.toggle("active", isOn);
      toggle.classList.toggle("unknown", isUnknown);

      const title = isOn ? "Turn Off" : isUnknown ? "State unknown — Turn On" : "Turn On";
      toggle.title = title;
      toggle.setAttribute("aria-label", title);
    }
  }

  const status = card?.querySelector("[data-tapo-status]");
  const brightness = card?.querySelector("[data-tapo-brightness]");

  if (status) {
    if (rawPower === true) {
      status.textContent = "On";
    } else if (rawPower === false) {
      status.textContent = "Off";
    } else {
      status.textContent = "Unknown";
    }
  }

  const nextBrightness = device.tapo_brightness ?? device.brightness;
  const nextColorTemp = device.tapo_color_temperature ?? device.color_temperature;
  const nextHue = device.tapo_hue ?? device.hue;
  const nextSaturation = device.tapo_saturation ?? device.saturation;

  if (brightness && nextBrightness != null) {
    brightness.textContent = `${nextBrightness}%`;
  }

  const settingsButton = card?.querySelector('[data-tapo-action="settings"]');

  if (settingsButton) {
    if (nextBrightness != null) settingsButton.dataset.brightness = String(nextBrightness);
    if (nextColorTemp != null) settingsButton.dataset.colorTemp = String(nextColorTemp);
    if (nextHue != null) settingsButton.dataset.hue = String(nextHue);
    if (nextSaturation != null) settingsButton.dataset.saturation = String(nextSaturation);
  }
}

function bindTapoLightEditToggle() {
  const editToggle = document.getElementById("tapoLightEditToggle");
  if (!editToggle) return;

  editToggle.onclick = event => {
    event.preventDefault();
    event.stopPropagation();

    toggleTapoLightEditMode();
  };
}

function ensureTapoLightModal() {
  if (document.getElementById("tapoLightModal")) {
    bindTapoLightEditToggle();
    return;
  }

  document.body.insertAdjacentHTML("beforeend", `
    <div id="tapoLightModal" class="modal" hidden>
      <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="tapoLightTitle">
        <div class="modal-head">
          <div class="modal-title-wrap">
            <div id="tapoLightTitle" class="modal-title">Light Settings</div>
            <div id="tapoLightSubtitle" class="modal-subtitle">Zone</div>
          </div>

          <div class="modal-head-actions">
            <button id="tapoLightEditToggle" class="modal-close" type="button" aria-label="Edit device settings" title="Edit device settings">
              ${window.dashboardIconHtml("edit")}
            </button>

            <button
  class="modal-close"
  type="button"
  aria-label="Close light settings"
  data-tapo-modal-close="light"
>
  ${window.dashboardIconHtml("close")}
</button>
          </div>
        </div>

        <div class="modal-body">
          <section id="tapoEnergySection" class="modal-section tapo-energy-section" hidden>
            <div class="modal-section-title">Energy Monitoring</div>
            <div id="tapoEnergyPanel" class="tapo-energy-panel"></div>
          </section>

          <section id="tapoRechargeSection" class="modal-section" hidden>
            <div class="modal-section-title">Automations</div>
            <div id="tapoRechargePanel" class="tapo-recharge-panel"></div>
          </section>

          <section id="tapoLightSchemesSection" class="modal-section">
            <div id="tapoLightSchemesHeader" class="modal-section-title">Set Light</div>
            <div id="tapoBuiltinSchemes" class="tapo-light-scheme-actions"></div>

            <div id="tapoSavedSchemes" class="tapo-light-saved-schemes" hidden></div>
          </section>

          <section id="tapoControlledRoomDevicesSection" class="modal-section room-settings-device-section" hidden>
            <div class="modal-section-title">Zone Controlled Devices</div>
            <div id="tapoControlledRoomDevicesList" class="sensor-group-tapo-plugs room-settings-device-list"></div>
          </section>

          <section id="tapoHiddenRoomDevicesSection" class="modal-section room-settings-device-section" hidden>
            <div class="modal-section-title">Hidden Devices</div>
            <div id="tapoHiddenRoomDevicesList" class="sensor-group-tapo-plugs room-settings-device-list"></div>
          </section>

          <section id="tapoLightSchemePickerSection" class="modal-section" hidden>
            <div id="tapoSchemeSetBuiltinActions" class="tapo-light-scheme-actions"></div>

            <div id="tapoSchemeSetCustomActions" class="tapo-light-saved-schemes" hidden></div>

            <div class="tapo-light-single-action">
              <button id="tapoCreateCustomSchemeBtn" class="client-menu-btn" type="button">
                ${window.dashboardIconHtml("add")}
                <span>Add Scheme</span>
              </button>
            </div>
          </section>

          <section id="tapoLightPickerSection" class="modal-section tapo-light-picker">
            <div class="tapo-light-mode-toggle" role="group" aria-label="Light mode">
              <button id="tapoWhiteModeBtn" class="client-menu-btn active" type="button">White Light</button>
              <button id="tapoColorModeBtn" class="client-menu-btn" type="button">Color Light</button>
            </div>
          </section>

          <section id="tapoLightPowerSection" class="modal-section tapo-light-power-section" hidden>
            <div class="tapo-light-single-action">
              <button id="tapoLightPowerToggle" class="client-menu-btn tapo-light-power-toggle power-toggle" type="button">
                ${window.dashboardIconHtml("power_settings_new")}
                <span id="tapoLightPowerToggleLabel">Toggle Light</span>
              </button>
            </div>
          </section>

          <section id="tapoWhiteSection" class="modal-section">
            <div id="tapoWhiteBrightnessRow" class="tapo-light-row">
              <label class="tapo-light-label" for="tapoWhiteBrightnessSlider">Brightness</label>
              <output id="tapoWhiteBrightnessValue" class="tapo-light-value">100%</output>
            </div>
            <input id="tapoWhiteBrightnessSlider" class="tapo-light-slider tapo-system-fill-slider" type="range" min="1" max="100" step="1">

            <div id="tapoWhiteBalanceRow" class="tapo-light-row">
              <span class="tapo-light-label">White Tone</span>
            </div>
            <input id="tapoWhiteBalanceSlider" type="hidden" value="4200">
            <div id="tapoWhiteTemperatureButtons" class="tapo-white-temperature-buttons">
${renderTapoWhiteTemperatureButtons()}
            </div>
          </section>

          <section id="tapoColorSection" class="modal-section" hidden>
            <div id="tapoColorBrightnessRow" class="tapo-light-row">
              <label class="tapo-light-label" for="tapoColorBrightnessSlider">Brightness</label>
              <output id="tapoColorBrightnessValue" class="tapo-light-value">100%</output>
            </div>
            <input id="tapoColorBrightnessSlider" class="tapo-light-slider tapo-system-fill-slider" type="range" min="1" max="100" step="1">

            <div id="tapoHueRow" class="tapo-light-row">
              <label class="tapo-light-label" for="tapoHueSlider">Tone / Hue</label>
              <output id="tapoColorValue" class="tapo-light-value">45°</output>
            </div>
            <input id="tapoHueSlider" class="tapo-light-slider tapo-hue-slider" type="range" min="0" max="360" step="1">

            <div id="tapoSaturationRow" class="tapo-light-row">
              <label class="tapo-light-label" for="tapoSaturationSlider">Saturation</label>
              <output id="tapoSaturationValue" class="tapo-light-value">100%</output>
            </div>
            <input id="tapoSaturationSlider" class="tapo-light-slider tapo-saturation-slider" type="range" min="0" max="100" step="1">
          </section>
          
          <section id="tapoLightSetSection" class="modal-section" hidden>
            <div class="tapo-light-single-action tapo-light-set-actions">
              <button id="tapoSetSchemeBtn" class="client-menu-btn" type="button">
                ${window.dashboardIconHtml("save")}
                <span class="tapo-preset-save-copy">
                  <span id="tapoSetSchemeBtnLabel" class="tapo-preset-save-title">Save Preset</span>
                  <span id="tapoSetSchemeBtnSubtitle" class="tapo-preset-save-subtitle" hidden></span>
                </span>
              </button>
              <button id="tapoResetRoomDefaultBtn" class="client-menu-btn tapo-reset-room-default-btn" type="button" hidden>
                ${window.dashboardIconHtml("restart_alt")}
                <span id="tapoResetDefaultBtnLabel">Reset to Room Default</span>
              </button>
            </div>
          </section>

        </div>
      </div>
    </div>
  `);

  bindTapoLightEditToggle();

  document.getElementById("tapoWhiteModeBtn").addEventListener("click", () => setTapoLightMode("white", { send: true }));
  document.getElementById("tapoColorModeBtn").addEventListener("click", () => setTapoLightMode("color", { send: true }));
  document.getElementById("tapoLightPowerToggle").addEventListener("click", toggleTapoLightModalPower);

  document.getElementById("tapoSetSchemeBtn").addEventListener("click", handleTapoSetSchemeButton);
  document.getElementById("tapoResetRoomDefaultBtn").addEventListener("click", handleTapoResetRoomDefaultButton);
  document.getElementById("tapoCreateCustomSchemeBtn").addEventListener("click", createTapoCustomLightingScheme);

  document.getElementById("tapoSavedSchemes").addEventListener("click", event => {
    const button = event.target.closest("[data-tapo-custom-scheme-index]");
    if (!button) return;

    const customSchemes = getTapoCustomLightingSchemes();
    const scheme = customSchemes[Number(button.dataset.tapoCustomSchemeIndex)];

    if (!scheme?.preset) return;

    setTapoSliderDirty(false);
    setTapoActiveLightingScheme(scheme.mode || "");
    setTapoActiveLightingSchemeForKey(getTapoLightingSchemeTargetKey(), scheme.mode || "");
    applyTapoLightingPreset(scheme.preset, scheme.mode || "");
  });

  document.getElementById("tapoSchemeSetCustomActions").addEventListener("click", event => {
    const button = event.target.closest("[data-tapo-set-custom-scheme-index]");
    if (!button) return;

    const customSchemes = getTapoCustomLightingSchemes();
    const scheme = customSchemes[Number(button.dataset.tapoSetCustomSchemeIndex)];

    if (!scheme?.mode) return;

    saveTapoLightingScheme(scheme.mode, {
      label: scheme.label || "Custom",
      icon: scheme.icon || "tune",
      preset: getCurrentTapoLightingPreset()
    });
  });

  document.getElementById("tapoBuiltinSchemes").addEventListener("click", event => {
    const settingsButton = event.target.closest("[data-tapo-lighting-settings-mode]");

    if (settingsButton) {
      toggleTapoLightingSchemeSettings(settingsButton.dataset.tapoLightingSettingsMode || "");
      return;
    }

    const button = event.target.closest("[data-tapo-lighting-mode]");
    if (!button) return;

    applyTapoLightingMode(button.dataset.tapoLightingMode || "day");
  });

  document.getElementById("tapoSchemeSetBuiltinActions").addEventListener("click", event => {
    const button = event.target.closest("[data-tapo-set-scheme-mode]");
    if (!button) return;

    saveTapoLightingScheme(button.dataset.tapoSetSchemeMode || "day", {
      preset: getCurrentTapoLightingPreset()
    });
  });

  document.getElementById("tapoWhiteBrightnessSlider").addEventListener("pointerdown", handleTapoSliderPointerDown);
  document.getElementById("tapoWhiteBrightnessSlider").addEventListener("input", handleTapoBrightnessPreview);
  document.getElementById("tapoWhiteBrightnessSlider").addEventListener("pointerup", handleTapoBrightnessChange);
  document.getElementById("tapoWhiteBrightnessSlider").addEventListener("change", handleTapoBrightnessChange);

  document.getElementById("tapoColorBrightnessSlider").addEventListener("pointerdown", handleTapoSliderPointerDown);
  document.getElementById("tapoColorBrightnessSlider").addEventListener("input", handleTapoBrightnessPreview);
  document.getElementById("tapoColorBrightnessSlider").addEventListener("pointerup", handleTapoBrightnessChange);
  document.getElementById("tapoColorBrightnessSlider").addEventListener("change", handleTapoBrightnessChange);

  document.querySelectorAll("[data-tapo-white-kelvin]").forEach(button => {
    button.addEventListener("click", handleTapoWhiteTemperatureButton);
  });

  document.getElementById("tapoHueSlider").addEventListener("pointerdown", handleTapoSliderPointerDown);
  document.getElementById("tapoHueSlider").addEventListener("input", handleTapoColorPreview);
  document.getElementById("tapoHueSlider").addEventListener("pointerup", handleTapoColorChange);
  document.getElementById("tapoHueSlider").addEventListener("change", handleTapoColorChange);

  document.getElementById("tapoSaturationSlider").addEventListener("pointerdown", handleTapoSliderPointerDown);
  document.getElementById("tapoSaturationSlider").addEventListener("input", handleTapoColorPreview);
  document.getElementById("tapoSaturationSlider").addEventListener("pointerup", handleTapoColorChange);
  document.getElementById("tapoSaturationSlider").addEventListener("change", handleTapoColorChange);
}

function setTapoLightEditMode() {
  const modal = document.getElementById("tapoLightModal");
  const editToggle = document.getElementById("tapoLightEditToggle");
  const roomPowerSection = document.getElementById("tapoRoomPowerSection");
  const roomPowerRow = document.getElementById("tapoRoomPowerRow");
  const dashboardHideRow = document.getElementById("tapoDashboardHideRow");

  if (!modal) return;

  const isRoom = modal.dataset.roomSettings === "1";
  const isOutletExtender = modal.dataset.tapoKind === "outlet_extender";
  const controlsOpen = Boolean(modal.dataset.lightControlsMode || "");
  const roomPowerAvailable = modal.dataset.roomPowerAvailable === "1";

  if (editToggle) {
    editToggle.hidden = isRoom;
    editToggle.classList.remove("active");
    editToggle.title = "Edit device details";
    editToggle.setAttribute("aria-label", editToggle.title);
    editToggle.removeAttribute("aria-expanded");
  }

  if (roomPowerSection) roomPowerSection.hidden = controlsOpen || isRoom || !roomPowerAvailable;
  if (roomPowerRow) roomPowerRow.hidden = controlsOpen || isRoom || !roomPowerAvailable || isOutletExtender;
  if (dashboardHideRow) dashboardHideRow.hidden = controlsOpen || isRoom || !roomPowerAvailable || isOutletExtender;

  delete modal.dataset.editMode;
}

function toggleTapoLightEditMode(event) {
  event?.preventDefault?.();
  event?.stopPropagation?.();

  const modal = document.getElementById("tapoLightModal");
  if (!modal || modal.dataset.roomSettings === "1") return;

  const target = activeTapoLight();
  const title = String(modal.dataset.clientName || modal.dataset.tapoBaseTitle || "Tapo Device");
  const subtitle = document.getElementById("tapoLightSubtitle")?.textContent?.trim() || title;
  const showDeviceOptions = (
    modal.dataset.roomPowerAvailable === "1"
    && modal.dataset.tapoKind !== "outlet_extender"
  );
  const additionalFieldsHtml = showDeviceOptions
    ? `
        <div class="tapo-device-meta-options">
          <label id="tapoRoomPowerRow" class="tapo-light-check-row">
            <input id="tapoRoomPowerInput" type="checkbox" ${modal.dataset.tapoRoomPower === "1" ? "checked" : ""}>
            <span>Include in room power switch</span>
          </label>

          <label id="tapoDashboardHideRow" class="tapo-light-check-row">
            <input id="tapoDashboardHideInput" type="checkbox" ${modal.dataset.tapoHideDashboard === "1" ? "checked" : ""}>
            <span>Hide individual device</span>
          </label>
        </div>
      `
    : "";

  window.showClientMetaModal?.({
    deviceID: target.deviceID,
    parentModalID: "tapoLightModal",
    clientName: title,
    zoneName: modal.dataset.zoneName || "",
    subtitle,
    removable: modal.dataset.childOutletSettings !== "1",
    additionalFieldsHtml,
    save: values => saveTapoLightMeta(values),
    remove: button => removeTapoDeviceFromSettings(button, modal)
  });
}

function findTapoClientForSettings(deviceID) {
  const sources = [
    window.appState?.currentClients,
    window.clients,
    S.currentClients
  ];

  for (const source of sources) {
    if (!Array.isArray(source)) continue;

    const client = source.find(item => item?.deviceID === deviceID);
    if (client) return client;
  }

  return null;
}

function tapoCurrentClientTargetKey(client) {
  const directDeviceID = String(client?.deviceID || "").trim();
  const separatorIndex = directDeviceID.indexOf("::");

  // Extender children can arrive as parent::child or as separate parent and
  // child fields. Normalize both representations to one physical target key.
  const parentDeviceID = String(
    client?.tapo_parent_device_id
    || (separatorIndex >= 0 ? directDeviceID.slice(0, separatorIndex) : "")
  ).trim();
  const childID = String(
    client?.tapo_child_id
    || (separatorIndex >= 0 ? directDeviceID.slice(separatorIndex + 2) : "")
  ).trim();

  if (parentDeviceID && childID) {
    return `tapo-child:${parentDeviceID}::${childID}`;
  }

  return directDeviceID ? `device:${directDeviceID}` : "";
}

function tapoAllCurrentClients() {
  const map = new Map();

  // Process the current rendered collection last and key extender children by
  // physical target, allowing the current visible/hidden value to replace any
  // stale copy that used a different synthetic deviceID.
  [
    window.appState?.currentClients,
    window.clients,
    S.currentClients
  ].forEach(source => {
    if (!Array.isArray(source)) return;

    source.forEach(client => {
      const targetKey = tapoCurrentClientTargetKey(client);

      if (targetKey) {
        map.set(targetKey, client);
      }
    });
  });

  return Array.from(map.values());
}

function tapoClientRoomName(client) {
  return String(client?.zone_name || client?.room || client?.room_name || client?.zone || "").trim();
}

function tapoClientIsRoomLight(client) {
  const kind = String(client?.tapo_kind || "").toLowerCase();
  const childKind = String(client?.tapo_child_kind || "").toLowerCase();

  return client?.tapo_is_bulb === true || kind === "bulb" || kind === "lightstrip" || kind === "nightlight" || childKind === "nightlight";
}

function tapoClientIsRoomPlug(client) {
  const kind = String(client?.tapo_kind || "").toLowerCase();
  const childKind = String(client?.tapo_child_kind || "").toLowerCase();

  return client?.tapo_is_plug === true || kind === "plug" || (client?.tapo_is_outlet_child === true && kind !== "nightlight" && childKind !== "nightlight");
}

function tapoRoomPowerEnabledForClient(client) {
  const raw = client?.tapo_room_power ?? client?.tapoRoomPower ?? client?.room_power ?? client?.include_in_room_power;

  if (raw === undefined || raw === null || raw === "") {
    return tapoClientIsRoomLight(client);
  }

  return tapoBool(raw) === true;
}

function tapoClientExplicitlyHiddenOnDashboard(client) {
  // Reuse the dashboard’s canonical decision so Controls and Hidden Devices
  // cannot interpret the same hide value differently.
  if (typeof window.dashboardTapoExplicitlyHidden === "function") {
    return window.dashboardTapoExplicitlyHidden(client);
  }

  // // Keep startup safe if subsystem scripts load before dashboard-render.js;
  // this fallback intentionally mirrors the canonical dashboard fields.
  const raw = client?.tapo_hide_dashboard
    ?? client?.tapoHideDashboard
    ?? client?.tapo_dashboard_hidden
    ?? client?.dashboard_hidden
    ?? client?.hide_dashboard;

  return tapoBool(raw) === true;
}

function tapoRoomDeviceClients(roomName = "") {
  const roomKey = String(roomName || "").trim().toLowerCase();

  if (!roomKey) return [];

  // Use the exact expanded client collection currently rendered by Controls.
  // Legacy client arrays can contain stale extender children with old hide flags.
  const currentClients = Array.isArray(S.currentClients)
    ? S.currentClients
    : [];

  return currentClients
    .filter(client => client?.provisioned)
    .filter(client => tapoClientIsRoomLight(client) || tapoClientIsRoomPlug(client))
    .filter(client => tapoClientRoomName(client).toLowerCase() === roomKey)
    .sort((a, b) => String(a.clientName || a.tapo_alias || "").localeCompare(String(b.clientName || b.tapo_alias || "")));
}

function tapoControlledRoomClients(roomName = "") {
  return tapoRoomDeviceClients(roomName)
    .filter(tapoRoomPowerEnabledForClient);
}

function tapoHiddenRoomClients(roomName = "") {
  return tapoRoomDeviceClients(roomName)
    .filter(client => !tapoRoomPowerEnabledForClient(client))
    .filter(tapoClientExplicitlyHiddenOnDashboard);
}

function renderTapoRoomDeviceRow(client) {
  if (typeof window.renderTapoClientCard === "function") {
    return window.renderTapoClientCard(client);
  }

  return "";
}

function renderTapoRoomDeviceSection(sectionID, listID, devices) {
  const section = document.getElementById(sectionID);
  const list = document.getElementById(listID);

  if (!section || !list) return;

  section.hidden = !devices.length;
  list.innerHTML = section.hidden ? "" : devices.map(renderTapoRoomDeviceRow).join("");

  if (section.hidden) return;

  devices.forEach(client => {
    const deviceID = String(client?.deviceID || "");
    const card = Array.from(list.children).find(item => {
      return String(item?.dataset?.deviceId || "") === deviceID;
    });

    // Room-settings cards must use the same shared card normalization as the
    // dashboard so title-icon size, alignment, and glow cannot diverge.
    window.normalizeDashboardDeviceCard?.(card);
    window.syncClientDebugArea?.(card, client);
  });
}

function renderTapoRoomDeviceSections() {
  const modal = document.getElementById("tapoLightModal");
  if (!modal) return;

  const isRoom = modal.dataset.roomSettings === "1";
  const controlsOpen = Boolean(modal.dataset.lightControlsMode || "");
  const roomName = modal.dataset.tapoRoom || "";
  const controlledDevices = isRoom && !controlsOpen ? tapoControlledRoomClients(roomName) : [];
  const hiddenDevices = isRoom && !controlsOpen ? tapoHiddenRoomClients(roomName) : [];

  renderTapoRoomDeviceSection(
    "tapoControlledRoomDevicesSection",
    "tapoControlledRoomDevicesList",
    controlledDevices
  );
  renderTapoRoomDeviceSection(
    "tapoHiddenRoomDevicesSection",
    "tapoHiddenRoomDevicesList",
    hiddenDevices
  );
}

function tapoPatchChildByTarget(client, target, fields) {
  const childID = String(target?.childID || "").trim();
  if (!client || !childID) return false;

  const children = Array.isArray(client.tapo_children)
    ? client.tapo_children
    : Array.isArray(client.children)
      ? client.children
      : [];

  let changed = false;

  children.forEach((child, index) => {
    if (!child || typeof child !== "object") return;

    const currentChildID = String(
      child.id
      ?? child.child_id
      ?? child.childId
      ?? child.position
      ?? child.index
      ?? index + 1
    ).trim();

    const isTargetChild = currentChildID === childID;

    if (fields.zone_name) {
      child.zone_name = fields.zone_name;
      child.room = fields.zone_name;
      child.room_name = fields.zone_name;
      child.zone = fields.zone_name;
      changed = true;
    }

    if (!isTargetChild) return;

    if (fields.clientName) {
      child.alias = fields.clientName;
      child.name = fields.clientName;
      child.clientName = fields.clientName;
      changed = true;
    }

    if (fields.tapo_room_power !== undefined) {
      child.tapo_room_power = fields.tapo_room_power;
      changed = true;
    }

    if (fields.tapo_hide_dashboard !== undefined) {
      child.tapo_hide_dashboard = fields.tapo_hide_dashboard;
      changed = true;
    }
  });

  if (changed && fields.zone_name) {
    client.zone_name = fields.zone_name;
    client.room = fields.zone_name;
    client.room_name = fields.zone_name;
    client.zone = fields.zone_name;
  }

  return changed;
}

function tapoPatchExpandedClientByTarget(client, target, fields) {
  if (!client || !target) return false;

  const targetDeviceID = String(target.deviceID || "").trim();
  const childID = String(target.childID || "").trim();
  const expandedChildID = String(client.tapo_child_id || "").trim();
  const parentDeviceID = String(client.tapo_parent_device_id || "").trim();
  const directDeviceID = String(client.deviceID || "").trim();
  const isTarget = childID
    ? (
      (parentDeviceID === targetDeviceID && expandedChildID === childID) ||
      directDeviceID === `${targetDeviceID}::${childID}`
    )
    : directDeviceID === targetDeviceID;

  if (!isTarget) return false;

  if (fields.clientName) {
    client.clientName = fields.clientName;
    client.tapo_alias = fields.clientName;
    client.name = fields.clientName;
    client.tapo_child_name = fields.clientName;
  }

  if (fields.zone_name) {
    client.zone_name = fields.zone_name;
    client.room = fields.zone_name;
    client.room_name = fields.zone_name;
    client.zone = fields.zone_name;
  }

  if (fields.tapo_room_power !== undefined) {
    client.tapo_room_power = fields.tapo_room_power;
  }

  if (fields.tapo_hide_dashboard !== undefined) {
    client.tapo_hide_dashboard = fields.tapo_hide_dashboard;
  }

  return true;
}

function patchTapoLightMetaInSource(source, target, fields) {
  if (!Array.isArray(source)) return;

  source.forEach(client => {
    const targetDeviceID = String(target?.deviceID || "").trim();

    if (target?.childID && String(client?.deviceID || "").trim() === targetDeviceID) {
      tapoPatchChildByTarget(client, target, fields);
      return;
    }

    tapoPatchExpandedClientByTarget(client, target, fields);
  });
}

function patchTapoLightMetaInCurrentData(target, fields, data = null) {
  [
    window.appState?.currentClients,
    window.clients,
    S.currentClients,
    data?.clients
  ].forEach(source => patchTapoLightMetaInSource(source, target, fields));
}

function updateTapoLightModalMetaAfterSave(fields) {
  const modal = document.getElementById("tapoLightModal");
  if (!modal || modal.dataset.roomSettings === "1") return;

  if (fields.clientName) {
    modal.dataset.clientName = fields.clientName;
    modal.dataset.tapoBaseTitle = fields.clientName;
    document.getElementById("tapoLightTitle").textContent = fields.clientName;
  }

  if (fields.zone_name !== undefined) {
    modal.dataset.zoneName = fields.zone_name || "";
  }

  if (fields.tapo_room_power !== undefined) {
    modal.dataset.tapoRoomPower = fields.tapo_room_power ? "1" : "0";
  }

  if (fields.tapo_hide_dashboard !== undefined) {
    modal.dataset.tapoHideDashboard = fields.tapo_hide_dashboard ? "1" : "0";
  }
}

function removeTapoDashboardCardForTarget(target = {}) {
  const targetDeviceID = String(target.deviceID || "").trim();
  const childID = String(target.childID || "").trim();
  const targetCardID = childID ? `${targetDeviceID}::${childID}` : targetDeviceID;

  if (!targetCardID) return;

  document.querySelectorAll('[data-node-card="tapo"]').forEach(card => {
    const cardID = String(card.dataset.deviceId || "").trim();
    const commandID = String(card.dataset.tapoParentDeviceId || card.dataset.deviceId || "").trim();
    const cardChildID = String(card.dataset.tapoChildId || "").trim();

    if (cardID === targetCardID || (!childID && commandID === targetDeviceID) || (childID && commandID === targetDeviceID && cardChildID === childID)) {
      card.remove();
    }
  });
}

function renderDashboardAfterTapoMetaSave(data = null) {
  const renderData = data || {
    clients: S.currentClients || [],
    server: S.serverState || {},
    used_zones: S.currentUsedZones || []
  };

  // Tapo metadata saves run inside the dashboard interaction-settle window.
  // A queued render can be superseded before the Controls card consumes the
  // accepted name/zone, leaving the old card text until a manual refresh. Both
  // the rendered collection and any fetched status payload are patched before
  // reaching this boundary, so publish that state immediately. Do not route
  // this metadata handoff through requestDashboardRenderSafe().
  if (typeof window.dashboardRenderNow === "function") {
    window.dashboardRenderNow(renderData);
  } else if (typeof requestDashboardRenderSafe === "function") {
    requestDashboardRenderSafe(renderData);
  }

  // Rebuild the open room sections immediately so a device removed from the
  // hidden set cannot remain as a stale Hidden Devices card.
  renderTapoRoomDeviceSections();
}

window.setTapoLightEditMode = setTapoLightEditMode;
window.toggleTapoLightEditMode = toggleTapoLightEditMode;

function ensureTapoCameraModal() {
  if (document.getElementById("tapoCameraModal")) return;

  document.body.insertAdjacentHTML("beforeend", `
    <div id="tapoCameraModal" class="modal" hidden>
      <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="tapoCameraTitle">
        <div class="modal-head">
          <div class="modal-title-wrap">
            <div id="tapoCameraTitle" class="modal-title">Camera Settings</div>
            <div id="tapoCameraSubtitle" class="modal-subtitle">TAPO CAMERA</div>
          </div>

          <div class="modal-head-actions">
            <button id="tapoCameraEditToggle" class="modal-close" type="button" aria-label="Edit camera settings" title="Edit camera settings">
              ${window.dashboardIconHtml("edit")}
            </button>

            <button
              class="modal-close"
              type="button"
              aria-label="Close camera settings"
              data-tapo-modal-close="camera"
            >
              ${window.dashboardIconHtml("close")}
            </button>
          </div>
        </div>

        <div class="modal-body">
          <section class="modal-section tapo-camera-preview-section">
            <div class="camera-preview-container tapo-camera-modal-preview">
              <div class="camera-preview-rotator">
                <video
                  id="tapoCameraSettingsPreview"
                  class="camera-preview tapo-camera-video"
                  muted
                  playsinline
                  autoplay
                  data-hls-src=""
                  style="display:none;">
                </video>
              </div>
            </div>
          </section>

          <section class="modal-section tapo-camera-rotation-section">
            <div class="tapo-light-row">
              <span class="tapo-light-label">Rotation</span>
              <output id="tapoCameraRotationValue" class="tapo-light-value">0°</output>
            </div>

            <div class="tapo-light-mode-toggle" role="group" aria-label="Camera rotation">
              <button class="client-menu-btn" type="button" data-tapo-camera-rotation="0">0°</button>
              <button class="client-menu-btn" type="button" data-tapo-camera-rotation="90">90°</button>
              <button class="client-menu-btn" type="button" data-tapo-camera-rotation="180">180°</button>
              <button class="client-menu-btn" type="button" data-tapo-camera-rotation="270">270°</button>
            </div>
          </section>

        </div>
      </div>
    </div>
  `);

  document.getElementById("tapoCameraEditToggle").addEventListener("click", toggleTapoCameraEditMode);

  document.querySelectorAll("[data-tapo-camera-rotation]").forEach(button => {
    button.addEventListener("click", () => {
      saveTapoCameraRotation(Number(button.dataset.tapoCameraRotation || 0));
    });
  });
}

function setTapoCameraEditMode() {
  const modal = document.getElementById("tapoCameraModal");
  const editToggle = document.getElementById("tapoCameraEditToggle");

  if (!modal) return;

  delete modal.dataset.editMode;

  if (editToggle) {
    editToggle.classList.remove("active");
    editToggle.title = "Edit device details";
    editToggle.setAttribute("aria-label", editToggle.title);
    editToggle.removeAttribute("aria-expanded");
  }
}

function toggleTapoCameraEditMode(event) {
  event?.preventDefault();
  event?.stopPropagation();

  const modal = document.getElementById("tapoCameraModal");
  const target = activeTapoCamera();

  if (!modal || !target.deviceID) return;

  window.showClientMetaModal?.({
    deviceID: target.deviceID,
    parentModalID: "tapoCameraModal",
    clientName: modal.dataset.clientName || "Tapo Camera",
    zoneName: modal.dataset.zoneName || "",
    subtitle: document.getElementById("tapoCameraSubtitle")?.textContent?.trim() || "Tapo Camera",
    save: values => saveTapoCameraMeta(values),
    remove: button => removeTapoDeviceFromSettings(button, modal)
  });
}

window.showTapoLightModal = function (data) {
  ensureTapoLightModal();

  const modal = document.getElementById("tapoLightModal");
  const brightness = Number(data.brightness || 100);
  const colorTemp = Number(data.colorTemp || 4200);
  const hue = Number(data.hue || 45);
  const saturation = Number(data.saturation || 100);
  const tapoKind = data.tapoKind || "bulb";
  const isPlug = tapoKind === "plug" || tapoKind === "outlet_extender";
  const isCamera = tapoKind === "camera";
  const isLight = tapoKind === "bulb" || tapoKind === "lightstrip";
  const nonLight = isPlug || isCamera;
  const isRoom = Boolean(data.tapoDeviceIds);
  const isOutletChild = Boolean(data.tapoChildId);
  const roomName = data.tapoRoom || String(data.tapoName || "").replace(/\s+Lights$/i, "");

  modal.dataset.tapoId = data.tapoId || "";
  modal.dataset.tapoDeviceIds = data.tapoDeviceIds || "";
  modal.dataset.deviceId = data.deviceId || "";
  modal.dataset.clientName = data.tapoName || "";
  modal.dataset.zoneName = data.zoneName || "";
  modal.dataset.tapoKind = tapoKind;
  modal.dataset.tapoChildId = data.tapoChildId || "";
  modal.dataset.tapoChildPosition = data.tapoChildPosition || "";
  modal.dataset.tapoChildIndex = data.tapoChildIndex || "";
  modal.dataset.tapoRechargeTargetId = data.tapoRechargeTargetId || "";
  modal.dataset.tapoRechargeMode = "list";
  modal.dataset.tapoRechargeExpanded = "0";
  modal.dataset.childOutletSettings = isOutletChild ? "1" : "0";
  modal.dataset.roomSettings = isRoom ? "1" : "0";
  modal.dataset.tapoRoom = roomName || "";
  modal.dataset.supportsBrightness = data.supportsBrightness === "1" ? "1" : "0";
  modal.dataset.supportsColorTemp = data.supportsColorTemp === "1" ? "1" : "0";
  modal.dataset.supportsColor = data.supportsColor === "1" ? "1" : "0";
  writeTapoEnergyDataset(modal, tapoEnergyReadingFromDataset(data));
  modal.dataset.tapoPowerState = data.tapoPowerState || "unknown";
  modal.dataset.schemePicker = "0";
  modal.dataset.lightControlsMode = "";
  modal.dataset.sliderDirty = "0";
  modal.dataset.activeSchemeMode = "";

  renderTapoLightingSchemeLists();
  setTapoSliderDirty(false);

  const tapoTypeText =
    isCamera ? "Camera" :
    isPlug ? "Plug" :
    isLight ? "Light" :
    "Device";

  const tapoDeviceText = [
    data.tapoBrand || "Tapo",
    data.tapoModel || "",
    isOutletChild ? "Outlet" : tapoTypeText
  ]
    .map(part => String(part || "").trim())
    .filter(Boolean)
    .join(" ");

  const tapoTitle = isRoom
    ? roomName || data.tapoName || "Room settings"
    : data.tapoName || "Tapo Device";

  const subtitle = document.getElementById("tapoLightSubtitle");

  modal.dataset.tapoBaseTitle = tapoTitle;
  document.getElementById("tapoLightTitle").textContent = tapoTitle;

  if (subtitle) {
    const subtitleText = isRoom ? "" : tapoDeviceText;

    subtitle.textContent = subtitleText;
    subtitle.hidden = !subtitleText;
  }

  const schemesHeader = document.getElementById("tapoLightSchemesHeader");

  if (schemesHeader) {
    schemesHeader.textContent = isRoom ? "Set Zone Lighting" : "Set Light";
  }

  const roomPowerAvailable = !isRoom && (tapoKind === "plug" || isLight);
  const roomPowerEnabled = data.tapoRoomPower === "1" || (isLight && data.tapoRoomPower !== "0");

  modal.dataset.roomPowerAvailable = roomPowerAvailable ? "1" : "0";
  modal.dataset.tapoRoomPower = roomPowerEnabled ? "1" : "0";
  modal.dataset.tapoHideDashboard = data.tapoHideDashboard === "1" ? "1" : "0";

  setTapoLightEditMode(false);

  document.getElementById("tapoWhiteBrightnessSlider").value = brightness;
  document.getElementById("tapoColorBrightnessSlider").value = brightness;
  document.getElementById("tapoWhiteBrightnessValue").textContent = `${brightness}%`;
  document.getElementById("tapoColorBrightnessValue").textContent = `${brightness}%`;

  setTapoWhiteTemperature(colorTemp);

  document.getElementById("tapoHueSlider").value = hue;
  document.getElementById("tapoSaturationSlider").value = saturation;
  document.getElementById("tapoColorValue").textContent = `${hue}°`;
  document.getElementById("tapoSaturationValue").textContent = `${saturation}%`;

  const rechargeSection = document.getElementById("tapoRechargeSection");
  const energySection = document.getElementById("tapoEnergySection");
  const schemesSection = document.getElementById("tapoLightSchemesSection");
  const schemePickerSection = document.getElementById("tapoLightSchemePickerSection");
  const pickerSection = document.getElementById("tapoLightPickerSection");
  const powerSection = document.getElementById("tapoLightPowerSection");
  const whiteSection = document.getElementById("tapoWhiteSection");
  const colorSection = document.getElementById("tapoColorSection");
  const setSection = document.getElementById("tapoLightSetSection");

  if (rechargeSection) rechargeSection.hidden = isRoom || tapoKind !== "plug";
  if (energySection) energySection.hidden = true;
  renderTapoRoomDeviceSections();
  if (schemesSection) schemesSection.hidden = nonLight;
  if (schemePickerSection) schemePickerSection.hidden = true;
  if (pickerSection) pickerSection.hidden = true;
  if (powerSection) powerSection.hidden = true;
  if (whiteSection) whiteSection.hidden = true;
  if (colorSection) colorSection.hidden = true;
  if (setSection) setSection.hidden = true;

  if (!isRoom && tapoKind === "plug") {
    refreshTapoRechargeSettingsPanel(data);
  }

  if (!isRoom && isPlug) {
    refreshTapoEnergyPanel(data);
  }

  const supports = getTapoLightCapabilities();
  const preferredMode = supports.white || !supports.color ? "white" : "color";

  syncTapoLightCapabilityControls();

  if (nonLight) {
    syncTapoLightVisibility();
  } else {
    setTapoLightMode(preferredMode, { send: false });
    renderTapoLightingSchemeLists();
    setTapoSliderDirty(false);
  }

  modal.hidden = false;
  document.body.classList.add("modal-open");
};

window.hideTapoLightModal = function () {
  const modal = document.getElementById("tapoLightModal");
  if (!modal) return;

  modal.dataset.schemePicker = "0";
  modal.dataset.sliderDirty = "0";
  modal.dataset.activeSchemeMode = "";
  modal.dataset.tapoEnergyRequestId = String(++tapoEnergyRequestSerial);
  modal.hidden = true;

  if (window.dashboardRestoreParentModalFromSubmodal?.(modal)) return;

  document.body.classList.remove("modal-open");
};

window.showTapoCameraModal = function (data) {
  ensureTapoCameraModal();

  const modal = document.getElementById("tapoCameraModal");
  const rotation = Number(data.previewRotation || 0);
  const previewUrl = data.previewUrl || "";

  modal.dataset.deviceId = data.deviceId || "";
  modal.dataset.tapoId = data.tapoId || "";
  modal.dataset.clientName = data.tapoName || "";
  modal.dataset.zoneName = data.zoneName || "";
  modal.dataset.previewRotation = String(rotation);
  modal.dataset.previewUrl = previewUrl;

  const cameraSubtitle = [
    data.tapoBrand || "Tapo",
    data.tapoModel || "Camera",
    "Camera"
  ]
    .map(part => String(part || "").trim())
    .filter(Boolean)
    .join(" ");

  document.getElementById("tapoCameraTitle").textContent = data.tapoName || "Tapo Camera";
  document.getElementById("tapoCameraSubtitle").textContent = cameraSubtitle;
  setTapoCameraEditMode(false);

  setTapoCameraRotationUi(rotation);
  setTapoCameraPreviewUi(previewUrl, rotation);

  modal.hidden = false;
  document.body.classList.add("modal-open");
};

window.hideTapoCameraModal = function () {
  const modal = document.getElementById("tapoCameraModal");
  if (!modal) return;

  modal.hidden = true;

  if (window.dashboardRestoreParentModalFromSubmodal?.(modal)) return;

  document.body.classList.remove("modal-open");
};

function activeTapoCamera() {
  const modal = document.getElementById("tapoCameraModal");

  return {
    id: modal?.dataset.tapoId || "",
    deviceID: modal?.dataset.deviceId || ""
  };
}

function setTapoCameraPreviewUi(previewUrl, rotation) {
  const video = document.getElementById("tapoCameraSettingsPreview");

  if (!video) {
    return;
  }

  if (!previewUrl) {
    video.dataset.hlsSrc = "";
    video.removeAttribute("src");
    video.style.display = "none";
    return;
  }

  video.dataset.hlsSrc = previewUrl;
  video.style.display = "block";
  video.style.transform = `rotate(${Number(rotation || 0) % 360}deg)`;

  window.initTapoCameraVideo?.(video);
}

function setTapoCameraRotationUi(rotation) {
  const value = Number(rotation || 0) % 360;
  const modal = document.getElementById("tapoCameraModal");

  if (modal) {
    modal.dataset.previewRotation = String(value);
  }

  const label = document.getElementById("tapoCameraRotationValue");
  if (label) {
    label.textContent = `${value}°`;
  }

  const preview = document.getElementById("tapoCameraSettingsPreview");

  if (preview) {
    preview.style.transform = `rotate(${value}deg)`;
  }

  document.querySelectorAll("[data-tapo-camera-rotation]").forEach(button => {
    const active = Number(button.dataset.tapoCameraRotation || 0) === value;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

async function saveTapoCameraMeta(values = {}) {
  const target = activeTapoCamera();
  const modal = document.getElementById("tapoCameraModal");

  if (!target.deviceID || !modal) return false;

  const clientName = String(values.clientName ?? modal.dataset.clientName ?? "").trim();
  const zoneName = String(values.zoneName ?? modal.dataset.zoneName ?? "").trim();

  if (!clientName) return false;

  try {
    const res = await dashboardFetch("/api/tapo/client-command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        deviceID: target.deviceID,
        clientName,
        zone_name: zoneName
      })
    });

    const data = await res.json();

    if (!data.ok) {
      console.warn("Tapo camera save failed", data);
      return false;
    }

    modal.dataset.clientName = clientName;
    modal.dataset.zoneName = zoneName;
    document.getElementById("tapoCameraTitle").textContent = clientName;

    await refreshTapoDashboardView();
    return true;
  } catch (err) {
    console.warn("Tapo camera save failed", err);
    return false;
  }
}

async function saveTapoCameraRotation(rotation) {
  const target = activeTapoCamera();
  const value = Number(rotation || 0) % 360;

  if (!target.deviceID) {
    return;
  }

  setTapoCameraRotationUi(value);

  try {
    const res = await dashboardFetch("/api/tapo/client-command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        deviceID: target.deviceID,
        action: "rotation",
        value
      })
    });

    const data = await res.json();

    if (!data.ok) {
      console.warn("Tapo camera rotation failed", data);
      return;
    }

    const preview = document.querySelector(`.tapo-camera-card[data-device-id="${CSS.escape(target.deviceID)}"] .camera-preview`);

    if (preview) {
      preview.style.transform = `rotate(${value}deg)`;
    }

    const button = document.querySelector(`.tapo-camera-settings-open[data-device-id="${CSS.escape(target.deviceID)}"]`);
    if (button) {
      button.dataset.previewRotation = String(value);
    }
  } catch (err) {
    console.warn("Tapo camera rotation failed", err);
  }
}

function activeTapoLight() {
  const modal = document.getElementById("tapoLightModal");

  if (!modal) {
    return {
      id: "",
      deviceIDs: "",
      deviceID: "",
      childID: "",
      childPosition: "",
      childIndex: ""
    };
  }

  return {
    id: modal.dataset.tapoId || "",
    deviceIDs: modal.dataset.tapoDeviceIds || "",
    deviceID: modal.dataset.deviceId || "",
    childID: modal.dataset.tapoChildId || "",
    childPosition: modal.dataset.tapoChildPosition || "",
    childIndex: modal.dataset.tapoChildIndex || ""
  };
}

function showTapoLightSchemePicker() {
  const modal = document.getElementById("tapoLightModal");
  if (!modal) return;

  modal.dataset.schemePicker = "1";
  syncTapoLightVisibility();
}

function hideTapoLightSchemePicker() {
  const modal = document.getElementById("tapoLightModal");
  if (!modal) return;

  modal.dataset.schemePicker = "0";
  syncTapoLightVisibility();
}

function syncTapoLightCapabilityControls() {
  const supports = getTapoLightCapabilities();

  const whiteModeBtn = document.getElementById("tapoWhiteModeBtn");
  const colorModeBtn = document.getElementById("tapoColorModeBtn");
  const showModeToggle = supports.color && supports.white;

  if (whiteModeBtn) whiteModeBtn.hidden = !showModeToggle;
  if (colorModeBtn) colorModeBtn.hidden = !showModeToggle;

  document.getElementById("tapoWhiteBrightnessRow")?.toggleAttribute("hidden", !supports.brightness);
  document.getElementById("tapoWhiteBrightnessSlider")?.toggleAttribute("hidden", !supports.brightness);
  document.getElementById("tapoColorBrightnessRow")?.toggleAttribute("hidden", !supports.brightness);
  document.getElementById("tapoColorBrightnessSlider")?.toggleAttribute("hidden", !supports.brightness);

  document.getElementById("tapoWhiteBalanceRow")?.toggleAttribute("hidden", !supports.white);
  document.getElementById("tapoWhiteTemperatureButtons")?.toggleAttribute("hidden", !supports.white);

  document.getElementById("tapoHueRow")?.toggleAttribute("hidden", !supports.color);
  document.getElementById("tapoHueSlider")?.toggleAttribute("hidden", !supports.color);
  document.getElementById("tapoSaturationRow")?.toggleAttribute("hidden", !supports.color);
  document.getElementById("tapoSaturationSlider")?.toggleAttribute("hidden", !supports.color);
}

function syncTapoLightPowerToggle() {
  const modal = document.getElementById("tapoLightModal");
  const button = document.getElementById("tapoLightPowerToggle");
  const label = document.getElementById("tapoLightPowerToggleLabel");
  if (!modal || !button) return;

  const powerState = modal.dataset.tapoPowerState || "unknown";
  const isOn = powerState === "on";
  const isUnknown = powerState !== "on" && powerState !== "off";
  const nextLabel = isOn ? "Turn Off" : "Turn On";

  button.classList.toggle("active", isOn);
  button.classList.toggle("unknown", isUnknown);
  button.dataset.tapoPowerState = powerState;
  button.title = isUnknown ? "Power state unknown — turn on" : nextLabel;
  button.setAttribute("aria-label", button.title);

  if (label) label.textContent = isUnknown ? "Power Unknown" : nextLabel;
}

function syncTapoLightVisibility() {
  const modal = document.getElementById("tapoLightModal");
  const tapoKind = modal?.dataset.tapoKind || "";
  const isPlug = tapoKind === "plug" || tapoKind === "outlet_extender";
  const isCamera = tapoKind === "camera";
  const nonLight = isPlug || isCamera;
  const supports = getTapoLightCapabilities();
  const hasAdjustments = getTapoLightHasAdjustments();
  const whiteMode = !document.getElementById("tapoColorModeBtn")?.classList.contains("active") || !supports.color;
  const hasWhiteControls = supports.brightness || supports.white;
  const isRoom = modal?.dataset.roomSettings === "1";
  const isOutletExtender = modal?.dataset.tapoKind === "outlet_extender";
  const roomPowerAvailable = modal?.dataset.roomPowerAvailable === "1";
  const isSchemePicker = modal?.dataset.schemePicker === "1";
  const controlsOpen = Boolean(modal?.dataset.lightControlsMode || "");
  const controlsPanelOpen = controlsOpen && !isSchemePicker && !nonLight && hasAdjustments;

  const schemesSection = document.getElementById("tapoLightSchemesSection");
  const schemePickerSection = document.getElementById("tapoLightSchemePickerSection");
  const pickerSection = document.getElementById("tapoLightPickerSection");
  const powerSection = document.getElementById("tapoLightPowerSection");
  const whiteSection = document.getElementById("tapoWhiteSection");
  const colorSection = document.getElementById("tapoColorSection");
  const setSection = document.getElementById("tapoLightSetSection");
  const roomPowerSection = document.getElementById("tapoRoomPowerSection");
  const roomPowerRow = document.getElementById("tapoRoomPowerRow");
  const dashboardHideRow = document.getElementById("tapoDashboardHideRow");

  syncTapoLightCapabilityControls();

  renderTapoRoomDeviceSections();
  if (schemesSection) schemesSection.hidden = nonLight || isSchemePicker || !hasAdjustments || controlsOpen;
  if (schemePickerSection) schemePickerSection.hidden = nonLight || !isSchemePicker || !hasAdjustments;
  if (pickerSection) pickerSection.hidden = nonLight || isSchemePicker || !controlsOpen || !(supports.white && supports.color);
  if (powerSection) powerSection.hidden = nonLight || isSchemePicker || hasAdjustments;
  if (whiteSection) whiteSection.hidden = nonLight || !whiteMode || isSchemePicker || !controlsOpen || !hasWhiteControls;
  if (colorSection) colorSection.hidden = nonLight || whiteMode || isSchemePicker || !controlsOpen || !supports.color;
  if (setSection) setSection.hidden = nonLight || isSchemePicker || !controlsOpen || !hasAdjustments;
  if (roomPowerSection) roomPowerSection.hidden = controlsPanelOpen || isRoom || !roomPowerAvailable;
  if (roomPowerRow) roomPowerRow.hidden = controlsPanelOpen || isRoom || !roomPowerAvailable || isOutletExtender;
  if (dashboardHideRow) dashboardHideRow.hidden = controlsPanelOpen || isRoom || !roomPowerAvailable || isOutletExtender;

  syncTapoLightPowerToggle();
  syncTapoLightSchemeSettingsButtons();
  syncTapoSetSchemeButtonLabel();
  syncTapoRoomDefaultResetButton();
}

function setTapoLightMode(mode, opts = {}) {
  const supports = getTapoLightCapabilities();
  const nextMode = mode === "color" && supports.color ? "color" : "white";
  const whiteMode = nextMode !== "color";
  const modal = document.getElementById("tapoLightModal");

  if (modal && opts.send) {
    modal.dataset.schemePicker = "0";
  }

  const whiteButton = document.getElementById("tapoWhiteModeBtn");
  const colorButton = document.getElementById("tapoColorModeBtn");

  whiteButton.classList.toggle("active", whiteMode);
  whiteButton.setAttribute("aria-pressed", whiteMode ? "true" : "false");
  colorButton.classList.toggle("active", !whiteMode);
  colorButton.setAttribute("aria-pressed", whiteMode ? "false" : "true");

  syncTapoLightVisibility();

  if (opts.send) {
    sendTapoLightModeCommand(nextMode);
  }
}

function currentTapoLightMode() {
  return getTapoLightCapabilities().color && document.getElementById("tapoColorModeBtn")?.classList.contains("active")
    ? "color"
    : "white";
}

function sendTapoLightModeCommand(mode) {
  const target = activeTapoLight();
  const supports = getTapoLightCapabilities();

  if (mode === "color" && supports.color) {
    const value = {
      hue: Number(document.getElementById("tapoHueSlider").value),
      saturation: Number(document.getElementById("tapoSaturationSlider").value)
    };

    if (target.deviceIDs) {
      sendTapoRoomCommand({ deviceIDs: target.deviceIDs, action: "color", value });
      return;
    }

    sendTapoCommand({ ...target, action: "color", value });
    return;
  }

  if (!supports.white) return;

  sendTapoWhiteCommand(target);
}

async function toggleTapoLightModalPower(event) {
  const modal = document.getElementById("tapoLightModal");
  const target = activeTapoLight();
  const currentState = modal?.dataset.tapoPowerState || "unknown";
  const nextOn = currentState !== "on";
  const action = nextOn ? "on" : "off";

  if (target.deviceIDs) {
    await sendTapoRoomCommand({
      deviceIDs: target.deviceIDs,
      action,
      control: event.currentTarget
    });
  } else {
    const resolved = tapoResolveDashboardDeviceTarget(target.deviceID, target.childID);

    await sendTapoCommand({
      deviceID: resolved.deviceID,
      childID: resolved.childID,
      action: resolved.childID ? (nextOn ? "child_on" : "child_off") : action,
      value: tapoChildCommandValue(resolved),
      control: event.currentTarget
    });
  }

  if (modal) {
    modal.dataset.tapoPowerState = nextOn ? "on" : "off";
  }

  syncTapoLightPowerToggle();
}

async function saveTapoLightMeta(values = {}) {
  const target = activeTapoLight();
  const modal = document.getElementById("tapoLightModal");

  if (!target.deviceID || !modal) return false;

  const clientName = String(values.clientName ?? modal.dataset.clientName ?? modal.dataset.tapoBaseTitle ?? "").trim();
  const zoneName = String(values.zoneName ?? modal.dataset.zoneName ?? "").trim();
  const roomPowerRow = document.getElementById("tapoRoomPowerRow");
  const roomPowerInput = document.getElementById("tapoRoomPowerInput");
  const dashboardHideRow = document.getElementById("tapoDashboardHideRow");
  const dashboardHideInput = document.getElementById("tapoDashboardHideInput");
  const canSaveRoomPower = (
    modal.dataset.roomPowerAvailable === "1"
    && modal.dataset.tapoKind !== "outlet_extender"
  );

  if (!clientName) return false;

  const tapoRoomPower = canSaveRoomPower && roomPowerRow && roomPowerInput
    ? Boolean(roomPowerInput?.checked)
    : undefined;
  const tapoHideDashboard = canSaveRoomPower && dashboardHideRow && dashboardHideInput
    ? Boolean(dashboardHideInput?.checked)
    : undefined;

  try {
    const res = await dashboardFetch("/api/tapo/client-command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        deviceID: target.deviceID,
        child_id: target.childID,
        child_position: target.childPosition,
        child_index: target.childIndex,
        clientName,
        zone_name: zoneName,
        ...(tapoRoomPower !== undefined ? { tapo_room_power: tapoRoomPower } : {}),
        ...(tapoHideDashboard !== undefined ? { tapo_hide_dashboard: tapoHideDashboard } : {})
      })
    });


    const data = await res.json();

    if (!data.ok) {
      console.warn("Tapo save failed", data);
      return false;
    }

    const fields = {
      clientName,
      zone_name: zoneName,
      ...(tapoRoomPower !== undefined ? { tapo_room_power: tapoRoomPower } : {}),
      ...(tapoHideDashboard !== undefined ? { tapo_hide_dashboard: tapoHideDashboard } : {})
    };

    patchTapoLightMetaInCurrentData(target, fields);
    updateTapoLightModalMetaAfterSave(fields);

    if (tapoHideDashboard === true) {
      removeTapoDashboardCardForTarget(target);
    }

    renderDashboardAfterTapoMetaSave();

    const refreshedData = await refreshStatusData();
    patchTapoLightMetaInCurrentData(target, fields, refreshedData);

    if (tapoHideDashboard === true) {
      removeTapoDashboardCardForTarget(target);
    }

    renderDashboardAfterTapoMetaSave(refreshedData);
    return true;
  } catch (err) {
    console.warn("Tapo save failed", err);
    return false;
  }
}
function handleTapoBrightnessPreview(event) {
  const value = Number(event.target.value);

  document.getElementById("tapoWhiteBrightnessSlider").value = value;
  document.getElementById("tapoColorBrightnessSlider").value = value;
  document.getElementById("tapoWhiteBrightnessValue").textContent = `${value}%`;
  document.getElementById("tapoColorBrightnessValue").textContent = `${value}%`;

  setTapoSliderDirty(true);
}

function handleTapoSliderPointerDown(event) {
  const slider = event.currentTarget || event.target;
  if (!slider) return;

  slider.dataset.tapoPointerSlider = "1";
  slider.dataset.tapoPointerCommitted = "0";
}

function tapoShouldCommitSlider(slider, commitKey, event = null) {
  const eventType = event?.type || "";

  if (eventType === "change" && slider?.dataset.tapoPointerCommitted === "1") {
    slider.dataset.tapoPointerSlider = "0";
    slider.dataset.tapoPointerCommitted = "0";
    return false;
  }

  if (eventType === "pointerup") {
    slider.dataset.tapoPointerSlider = "0";
    slider.dataset.tapoPointerCommitted = "1";
  } else if (eventType === "change") {
    slider.dataset.tapoPointerSlider = "0";
    slider.dataset.tapoPointerCommitted = "0";
  }

  const now = Date.now();
  const lastKey = slider?.dataset.tapoLastCommitKey || "";
  const lastAt = Number(slider?.dataset.tapoLastCommitAt || 0);

  if (lastKey === commitKey && now - lastAt < 350) return false;

  if (slider) {
    slider.dataset.tapoLastCommitKey = commitKey;
    slider.dataset.tapoLastCommitAt = String(now);
  }

  return true;
}

function handleTapoBrightnessChange(event) {
  const slider = event.currentTarget || event.target;
  const target = activeTapoLight();
  const value = Number(slider.value);
  const commitKey = `brightness:${value}`;

  if (!tapoShouldCommitSlider(slider, commitKey, event)) return;

  if (target.deviceIDs) {
    sendTapoRoomCommand({ deviceIDs: target.deviceIDs, action: "brightness", value, control: slider });
    return;
  }

  sendTapoCommand({ ...target, action: "brightness", value, control: slider });
}

function handleTapoWhitePreview() {
  syncTapoWhiteTemperatureButtons();
  setTapoSliderDirty(true);
}

function handleTapoWhiteTemperatureButton(event) {
  const button = event.currentTarget || event.target;
  const kelvin = Number(button?.dataset?.tapoWhiteKelvin || 4200);

  setTapoWhiteTemperature(kelvin);
  setTapoSliderDirty(true);
  handleTapoWhiteChange(event);
}

function handleTapoWhiteChange(event) {
  const control = event.currentTarget || event.target;
  const target = activeTapoLight();
  const colorTemperature = getTapoWhiteTemperatureValue();
  const whiteSaturation = getTapoWhiteSaturationValue();
  const commitKey = `white:${colorTemperature}:${whiteSaturation}`;

  if (!tapoShouldCommitSlider(control, commitKey, event)) return;

  sendTapoWhiteCommand(target, control);
}

function handleTapoColorPreview() {
  const hue = Number(document.getElementById("tapoHueSlider").value);
  const saturation = Number(document.getElementById("tapoSaturationSlider").value);

  document.getElementById("tapoColorValue").textContent = `${hue}°`;
  document.getElementById("tapoSaturationValue").textContent = `${saturation}%`;

  setTapoSliderDirty(true);
}

function handleTapoColorChange(event) {
  const slider = event.currentTarget || event.target;
  const target = activeTapoLight();
  const value = {
    hue: Number(document.getElementById("tapoHueSlider").value),
    saturation: Number(document.getElementById("tapoSaturationSlider").value)
  };
  const commitKey = `color:${value.hue}:${value.saturation}`;

  if (!tapoShouldCommitSlider(slider, commitKey, event)) return;

  if (target.deviceIDs) {
    sendTapoRoomCommand({ deviceIDs: target.deviceIDs, action: "color", value, control: slider });
    return;
  }

  sendTapoCommand({ ...target, action: "color", value, control: slider });
}

function kelvinToPreviewHex(kelvin) {
  const t = Math.max(2500, Math.min(6500, Number(kelvin || 4200)));
  const ratio = (t - 2500) / 4000;

  const warm = { r: 255, g: 190, b: 92 };
  const cool = { r: 210, g: 238, b: 255 };

  const r = Math.round(warm.r + ((cool.r - warm.r) * ratio));
  const g = Math.round(warm.g + ((cool.g - warm.g) * ratio));
  const b = Math.round(warm.b + ((cool.b - warm.b) * ratio));

  return `#${[r, g, b].map(v => v.toString(16).padStart(2, "0")).join("")}`;
}

function hslToHex(h, s, l) {
  s /= 100;
  l /= 100;

  const k = n => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = n => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  const toHex = x => Math.round(255 * x).toString(16).padStart(2, "0");

  return `#${toHex(f(0))}${toHex(f(8))}${toHex(f(4))}`;
}

function hexToHsv(hex) {
  const clean = String(hex || "").replace("#", "");
  const r = parseInt(clean.slice(0, 2), 16) / 255;
  const g = parseInt(clean.slice(2, 4), 16) / 255;
  const b = parseInt(clean.slice(4, 6), 16) / 255;

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;

  let hue = 0;

  if (delta) {
    if (max === r) hue = 60 * (((g - b) / delta) % 6);
    else if (max === g) hue = 60 * (((b - r) / delta) + 2);
    else hue = 60 * (((r - g) / delta) + 4);
  }

  hue = Math.round((hue + 360) % 360);

  return {
    hue,
    saturation: Math.round((max ? delta / max : 0) * 100)
  };
}

function ensureTapoManagerModal() {
  if (document.getElementById("tapoManagerModal")) return;

  document.body.insertAdjacentHTML("beforeend", `
    <div id="tapoManagerModal" class="modal" hidden>
      <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="tapoManagerTitle">
        <div class="modal-head">
          <div>
            <h1 id="tapoManagerTitle" class="modal-title">Tapo Devices</h1>
            <div id="tapoManagerStatus" class="modal-subtitle">Current server clients</div>
          </div>

          <button class="modal-close" type="button" aria-label="Close Tapo manager" data-tapo-modal-close="manager">
            ${window.dashboardIconHtml("close")}
          </button>
        </div>

        <div class="modal-body">
          <section class="modal-section">
            <div id="tapoManagerCards" class="tapo-manager-cards"></div>
          </section>

          <section class="modal-section">
            <button id="tapoManagerScanBtn" class="client-menu-btn tapo-manager-action" type="button">
              Scan for Tapo devices
            </button>
          </section>

          <section class="modal-section">
            <button id="tapoManagerRemoveBtn" class="client-menu-btn tapo-manager-action tapo-manager-danger" type="button">
              Remove Tapo add-on from server
            </button>
          </section>
        </div>
      </div>
    </div>
  `);

  document.getElementById("tapoManagerScanBtn").addEventListener("click", scanForTapoDevices);
  document.getElementById("tapoManagerRemoveBtn").addEventListener("click", removeTapoAddonFromServer);
  document.getElementById("tapoManagerCards").addEventListener("click", removeTapoDeviceFromManager);
}

window.showTapoManagerModal = function () {
  ensureTapoManagerModal();
  renderTapoManagerCards();

  document.getElementById("tapoManagerModal").hidden = false;
  document.body.classList.add("modal-open");
};

window.hideTapoManagerModal = function () {
  const modal = document.getElementById("tapoManagerModal");
  if (!modal) return;

  modal.hidden = true;
  document.body.classList.remove("modal-open");
};

function renderTapoManagerCards() {
  const target = document.getElementById("tapoManagerCards");
  const status = document.getElementById("tapoManagerStatus");
  if (!target) return;

  const cards = [...document.querySelectorAll(".tapo-client-card, .tapo-camera-card")];

  if (!cards.length) {
    target.innerHTML = `<div class="tapo-manager-empty">No Tapo clients are currently saved on this server.</div>`;
    if (status) status.textContent = "No current server clients";
    return;
  }

  target.innerHTML = "";
  cards.forEach(card => {
    const clone = card.cloneNode(true);
    const deviceID = clone.dataset.deviceId || "";
    const title = clone.querySelector(".card-title")?.textContent?.trim() || "this Tapo device";

    clone.classList.add("tapo-manager-card");

    clone.querySelectorAll(
      ".tapo-power-toggle, .tapo-scheme-button-row, .icon-menu, .tapo-camera-record-btn"
    ).forEach(control => control.remove());

    const actions = clone.querySelector(".card-actions");
    if (actions && deviceID) {
      actions.insertAdjacentHTML("beforeend", `
        <button
          class="icon-btn tapo-manager-device-remove tapo-manager-danger"
          type="button"
          title="Remove ${esc(title)}"
          aria-label="Remove ${esc(title)}"
          data-tapo-remove-device-id="${esc(deviceID)}"
          data-tapo-remove-device-name="${esc(title)}"
        >
          ${window.dashboardIconHtml("delete")}
        </button>
      `);
    }

    target.appendChild(clone);
  });

  if (status) {
    status.textContent = `${cards.length} current server client${cards.length === 1 ? "" : "s"}`;
  }
}

async function scanForTapoDevices(event) {
  const button = event.currentTarget;
  const status = document.getElementById("tapoManagerStatus");

  button.disabled = true;
  if (status) status.textContent = "Scanning for Tapo devices...";

  try {
    const res = await dashboardFetch("/api/tapo/detect", {
      method: "POST"
    });

    const data = await res.json();

    if (!data.ok) {
      if (status) status.textContent = data.error || "Tapo scan failed";
      console.warn("Tapo scan failed", data);
      return;
    }

    const count = Number(data.clients?.length || 0);

    if (status) {
      status.textContent = `Scan complete: ${count} device${count === 1 ? "" : "s"} found`;
    }

    hideTapoManagerModal();
    await refreshTapoDashboardView();
  } finally {
    button.disabled = false;
  }
}

async function readTapoJsonResponse(res) {
  const text = await res.text();

  try {
    return JSON.parse(text);
  } catch (e) {
    return {
      ok: false,
      error: text.slice(0, 500) || `HTTP ${res.status} ${res.statusText}`
    };
  }
}

async function removeTapoDeviceFromSettings(button, settingsModal = null) {
  const lightModal = document.getElementById("tapoLightModal");
  const cameraModal = document.getElementById("tapoCameraModal");
  const activeModal =
    settingsModal ||
    (lightModal && !lightModal.hidden ? lightModal : null) ||
    (cameraModal && !cameraModal.hidden ? cameraModal : null) ||
    null;

  if (!button || !activeModal) return false;

  const deviceID = activeModal.dataset.deviceId || "";
  const name =
    activeModal.querySelector(".modal-title")?.textContent?.trim() ||
    "this Tapo device";

  if (!deviceID) return false;
  if (!confirm(`Remove ${name} from this server?`)) return false;

  button.disabled = true;

  try {
    const res = await dashboardFetch("/api/tapo/remove-client", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ deviceID })
    });

    const data = await readTapoJsonResponse(res);

    if (!res.ok || !data.ok) {
      console.warn("Tapo device remove failed", data);
      return false;
    }

    window.hideClientMetaModal?.(false);
    window.hideTapoLightModal?.();
    window.hideTapoCameraModal?.();

    await refreshTapoDashboardView();
    return true;
  } catch (err) {
    console.warn("Tapo device remove failed", err);
    return false;
  } finally {
    button.disabled = false;
  }
}

async function removeTapoDeviceFromManager(event) {
  const button = event.target.closest?.("[data-tapo-remove-device-id]");
  if (!button) return;

  event.preventDefault();
  event.stopPropagation();

  const deviceID = button.dataset.tapoRemoveDeviceId || "";
  const name = button.dataset.tapoRemoveDeviceName || "this Tapo device";
  const status = document.getElementById("tapoManagerStatus");

  if (!deviceID) return;
  if (!confirm(`Remove ${name} from this server?`)) return;

  button.disabled = true;
  if (status) status.textContent = `Removing ${name}...`;

  try {
    const res = await dashboardFetch("/api/remove-client", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ deviceID })
    });

    const data = await readTapoJsonResponse(res);

    if (!res.ok || !data.ok) {
      if (status) status.textContent = data.error || "Remove failed";
      console.warn("Tapo device remove failed", data);
      return;
    }

    await refreshTapoDashboardView();
    renderTapoManagerCards();

    if (status) status.textContent = `Removed ${name}`;
  } finally {
    button.disabled = false;
  }
}

async function removeTapoAddonFromServer(event) {
  if (!confirm("Remove all Tapo clients from this server?")) return;

  const button = event.currentTarget;
  const status = document.getElementById("tapoManagerStatus");

  button.disabled = true;
  if (status) status.textContent = "Removing Tapo clients...";

  try {
    const res = await dashboardFetch("/api/tapo/remove-addon", {
      method: "POST"
    });

    const data = await res.json();

    if (!data.ok) {
      if (status) status.textContent = data.error || "Remove failed";
      console.warn("Tapo remove failed", data);
      return;
    }

    await refreshTapoDashboardView();
    renderTapoManagerCards();

    if (status) {
      status.textContent = `Removed ${Number(data.removed || 0)} Tapo client${Number(data.removed || 0) === 1 ? "" : "s"}`;
    }
  } finally {
    button.disabled = false;
  }
}

async function refreshTapoDeviceStates() {
  const res = await dashboardFetch("/api/tapo/refresh", {
    method: "POST"
  });

  const text = await res.text();
  let data;

  try {
    data = JSON.parse(text || "{}");
  } catch (err) {
    data = {
      ok: false,
      error: text || `Tapo refresh failed with HTTP ${res.status}`
    };
  }

  if (!res.ok || !data.ok) {
    console.warn("Tapo refresh failed", data);
    return data;
  }

  if (Array.isArray(data.clients)) {
    data.clients.forEach(client => {
      updateTapoCardState(client);
    });
  }

  return data;
}

async function refreshTapoDashboardView() {
  await refreshTapoDeviceStates();

  if (typeof refreshStatusData === "function") {
    const data = await refreshStatusData();

    if (Array.isArray(data?.clients)) {
      data.clients = data.clients.map(client => applyTapoPendingPowerState(client));
    }

    render(data);
  }
}

window.addTapoDevices = async function () {
  setAddDeviceModalNote?.("Checking Tapo subsystem...");

  let status;

  try {
    status = await dashboardFetch("/api/tapo/status").then(r => r.json());
  } catch (err) {
    console.error("[addTapoDevices] status failed", err);
    setAddDeviceModalNote?.("Tapo status check failed.");
    return;
  }

  if (!status.enabled) {
    setAddDeviceModalNote?.("Enabling Tapo and restarting server...");

    try {
      const enabled = await dashboardFetch("/api/tapo/enable", { method: "POST" }).then(r => r.json());

      if (!enabled.ok) {
        setAddDeviceModalNote?.(enabled.error || "Unable to enable Tapo.");
        return;
      }

      setTimeout(() => {
        window.location.reload();
      }, 4500);

    } catch (err) {
      console.error("[addTapoDevices] enable failed", err);
      setAddDeviceModalNote?.("Unable to enable Tapo.");
    }

    return;
  }

  if (!status.loaded) {
    setAddDeviceModalNote?.(status.error || "Tapo is enabled but failed to load. Check server logs.");
    return;
  }

  setAddDeviceModalNote?.("Searching for Tapo devices...");

  try {
    const result = await dashboardFetch("/api/tapo/detect", { method: "POST" }).then(r => r.json());

    if (!result.ok) {
      setAddDeviceModalNote?.(result.error || "Tapo detection failed.");
      return;
    }

    const count = Array.isArray(result.clients) ? result.clients.length : 0;
    setAddDeviceModalNote?.(`Found ${count} Tapo device${count === 1 ? "" : "s"}.`);

    const data = await refreshStatusData();
    requestTapoDashboardRenderSafe(data);
    renderSettingsAutomations?.();
    renderSettingsDevices?.();

    setTimeout(() => {
      hideAddDeviceModal?.();
    }, 900);
  } catch (err) {
    console.error("[addTapoDevices] detect failed", err);
    setAddDeviceModalNote?.("Tapo detection failed. Check server logs.");
  }
};

window.removeTapoFromSystem = async function () {
  if (!confirm("Remove Tapo from this system?")) return;

  try {
    await dashboardFetch("/api/tapo/disable", { method: "POST" }).then(r => r.json());

    setTimeout(() => {
      window.location.reload();
    }, 4500);
  } catch (err) {
    console.error("[removeTapoFromSystem] failed", err);
    alert("Unable to remove Tapo.");
  }
};