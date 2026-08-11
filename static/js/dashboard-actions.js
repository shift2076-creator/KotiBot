"use strict";

var S = window.appState;

function requestDashboardRenderSafe(data) {
  if (typeof window.requestDashboardRender === "function") {
    return window.requestDashboardRender(data);
  }

  if (typeof window.render === "function") {
    return window.render(data);
  }
}

function renderDashboardNavigationNow() {
  const data = {
    clients: S.currentClients || [],
    server: S.serverState || S.server || {},
    used_zones: S.currentUsedZones || []
  };

  if (typeof window.dashboardRenderNow === "function") {
    return window.dashboardRenderNow(data);
  }

  return requestDashboardRenderSafe(data);
}

window.showDashboardHome = function () {
  window.setDashboardPageState?.("home");

  showView("dashboard", { render: false, renderAside: false });
  renderDashboardNavigationNow();
};

function dashboardHomeCleanArmMode(mode) {
  return ["day", "night", "away"].includes(String(mode || "").trim().toLowerCase())
    ? String(mode || "").trim().toLowerCase()
    : "day";
}

function dashboardHomeCurrentArmMode() {
  return dashboardHomeCleanArmMode(
    S.serverState?.armState ||
    S.serverState?.arm_state ||
    "day"
  );
}

let dashboardHomeLightingStateSyncPromise = null;

function dashboardHomeActiveLightingModeFromServer() {
  const state = window.TAPO_LIGHTING_STATE || {};
  const activeSchemes = state.activeSchemes && typeof state.activeSchemes === "object"
    ? state.activeSchemes
    : {};
  const mode = String(activeSchemes.home || "").trim().toLowerCase();

  if (mode === "nightlight") return "night";

  return ["day", "evening", "night", "away"].includes(mode) ? mode : "";
}

function dashboardHomeCurrentLightingMode() {
  return dashboardHomeActiveLightingModeFromServer() || "day";
}

function dashboardHomeSetActiveLightingModeLocally(mode) {
  const cleanMode = dashboardHomeCleanLightingMode(mode);
  const state = window.TAPO_LIGHTING_STATE || {};
  const activeSchemes = state.activeSchemes && typeof state.activeSchemes === "object"
    ? state.activeSchemes
    : {};

  state.activeSchemes = { ...activeSchemes, home: cleanMode };
  state.loaded = true;
  window.TAPO_LIGHTING_STATE = state;
  syncDashboardHomeModeButtons?.();
}

function dashboardHomeQueueLightingStateSync() {
  const state = window.TAPO_LIGHTING_STATE || {};

  if (state.loaded === true) return;
  if (dashboardHomeLightingStateSyncPromise) return;
  if (typeof window.loadTapoLightingState !== "function") return;

  dashboardHomeLightingStateSyncPromise = window.loadTapoLightingState()
    .then(() => {
      syncDashboardHomeModeButtons?.();
    })
    .catch(err => {
      console.warn("[dashboardHomeQueueLightingStateSync] failed", err);
    })
    .finally(() => {
      dashboardHomeLightingStateSyncPromise = null;
    });
}

window.syncDashboardHomeModeButtons = function () {
  const armMode = dashboardHomeCurrentArmMode();
  const lightMode = dashboardHomeActiveLightingModeFromServer();

  document.querySelectorAll('[data-dashboard-action="set-home-arm-mode"]').forEach(btn => {
    btn.classList.toggle("active", btn.dataset.mode === armMode);
  });

  document.querySelectorAll('[data-dashboard-action="set-home-light-mode"]').forEach(btn => {
    btn.classList.toggle("active", !!lightMode && btn.dataset.mode === lightMode);
  });

  if (!lightMode) {
    dashboardHomeQueueLightingStateSync();
  }
};

const DASHBOARD_HOME_ARMING_MODES = [
  { mode: "day", label: "At Home", icon: "wb_sunny" },
  { mode: "night", label: "Asleep", icon: "bedtime" },
  { mode: "away", label: "Away", icon: "directions_walk" }
];

window.setDashboardHomeArmMode = async function (mode) {
  const cleanMode = dashboardHomeCleanArmMode(mode);

  syncDashboardHomeModeButtons?.();

  const res = await dashboardFetch("/api/system-arm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ armState: cleanMode })
  });

  const data = await res.json();
  requestDashboardRenderSafe(data);

  if (document.getElementById("dashboardHomeArmingModal")?.hidden === false) {
    await dashboardHomeRefreshRoutes();
    renderDashboardHomeArmingSettings();
  }
};

function dashboardHomeArmingModeMeta(mode) {
  return DASHBOARD_HOME_ARMING_MODES.find(item => item.mode === mode) || DASHBOARD_HOME_ARMING_MODES[0];
}

let dashboardHomeArmingSelectedMode = dashboardHomeCurrentArmMode();

let dashboardHomeArmingRenderedRoutes = [];
let dashboardHomeArmingDraft = null;
let dashboardHomeArmingPendingTriggerIDs = [];
let dashboardHomeArmingPendingSourceIDs = [];
let dashboardHomeArmingPendingTriggerGroup = "";
let dashboardHomeArmingWizardStep = "response";
let dashboardHomeArmingRouteScope = "security";
let dashboardHomeArmingEditingAutomationID = "";
let dashboardHomeArmingEditingDeviceID = "";

function dashboardHomeArmingRouteEndpoint() {
  return dashboardHomeArmingRouteScope === "automation"
    ? "/api/automation-routes"
    : "/api/routes";
}

function dashboardHomeArmingRoutes() {
  return Array.isArray(S.currentRoutes) ? S.currentRoutes : [];
}

async function dashboardHomeRefreshRoutes() {
  try {
    const res = await dashboardFetch("/api/routes");
    const data = await res.json();
    S.currentRoutes = Array.isArray(data.routes) ? data.routes : [];
  } catch (error) {
    console.error("[arming] route refresh failed", error);
    S.currentRoutes = Array.isArray(S.currentRoutes) ? S.currentRoutes : [];
  }

  return S.currentRoutes;
}

function dashboardHomeArmingRouteArmStates(route) {
  const raw = route?.arm_states || route?.armStates || route?.active_arm_states || route?.activeArmStates || [];

  if (Array.isArray(raw)) {
    return raw.map(dashboardHomeCleanArmMode);
  }

  if (typeof raw === "string") {
    return raw.split(",").map(dashboardHomeCleanArmMode);
  }

  const single = route?.arm_state || route?.armState;
  return single ? [dashboardHomeCleanArmMode(single)] : [];
}

function dashboardHomeArmingRouteForMode(route, mode) {
  const states = dashboardHomeArmingRouteArmStates(route);
  return states.includes(dashboardHomeCleanArmMode(mode));
}

function dashboardHomeArmingRouteSource(route) {
  return String(route?.from_deviceID || route?.from_device_id || route?.sourceDeviceID || "").trim();
}

function dashboardHomeArmingRouteTarget(route) {
  return String(route?.to_deviceID || route?.to_device_id || route?.targetDeviceID || "").trim();
}

function dashboardHomeArmingRouteTrigger(route) {
  const trigger = String(route?.trigger || route?.from_trigger || "").trim().toLowerCase();

  if (trigger) return trigger;

  const output = String(route?.from_output || "").trim().toLowerCase();

  if (["open", "opened", "door_open", "door_opened"].includes(output)) return "door_open";
  if (["close", "closed", "door_close", "door_closed"].includes(output)) return "door_close";
  if (["motion", "motion_detected", "camera_motion"].includes(output)) return "motion";

  return output;
}

function dashboardHomeArmingRouteAction(route) {
  return String(route?.action_type || route?.actionType || route?.action || route?.to_kind || "").trim().toLowerCase();
}

function dashboardHomeArmingActionMeta(actionType) {
  const type = String(actionType || "").trim().toLowerCase();

  if (["device", "device_on", "turn_on_device", "turn_on", "power_on"].includes(type)) {
    return {
      actionType: "device_on",
      label: "Power on",
      icon: "toggle_on",
      subtitle: "Power on a switch or an Android Home feedback target"
    };
  }

  if (["sound", "wav", "audio", "play_sound"].includes(type)) {
    return {
      actionType: "sound",
      label: "Play a Sound",
      icon: "music_note",
      subtitle: "Play a sound when a sensor or motion trigger fires"
    };
  }

  if (["notification", "notify", "push", "key_notification"].includes(type)) {
    return {
      actionType: "notification",
      label: "Send a Notification",
      icon: "notifications",
      subtitle: "Send a key-client notification from a sensor or motion trigger"
    };
  }

  if (["android_flashlight", "motion_flashlight", "flashlight"].includes(type)) {
    return {
      actionType: "android_flashlight",
      label: "Use Camera Flashlight",
      icon: "bolt",
      subtitle: "Flash the triggering Android Home camera when motion is detected"
    };
  }

  if (["android_white_screen", "motion_screen", "white_screen"].includes(type)) {
    return {
      actionType: "android_white_screen",
      label: "Show White Screen",
      icon: "mobile_screen",
      subtitle: "Show a white screen on the triggering Android Home client when motion is detected"
    };
  }

  return {
    actionType: "recording",
    label: "Record a Video",
    icon: "videocam",
    subtitle: "Record video when a sensor or motion trigger fires"
  };
}

function dashboardHomeArmingClientIsMatter(client) {
  return (
    window.dashboardClientIsMatter?.(client) === true ||
    String(client?.source || "").trim().toLowerCase() === "matter" ||
    String(client?.deviceID || "").startsWith("matter:")
  );
}

function dashboardHomeArmingActionUsesSourceCamera(actionType) {
  return ["android_flashlight", "android_white_screen"].includes(
    dashboardHomeArmingActionMeta(actionType).actionType
  );
}

function dashboardHomeArmingHasAndroidMotionFeedbackContext() {
  if (dashboardHomeArmingRouteScope !== "automation") return false;
  if (dashboardHomeArmingPendingTriggerGroup !== "motion") return false;

  return dashboardHomeArmingPendingSourceIDs.some(deviceID => {
    const client = dashboardHomeArmingClientForDevice(deviceID);

    return (
      !!client?.provisioned &&
      clientRolesOf(client).includes("CAM") &&
      !dashboardHomeArmingClientIsMatter(client) &&
      !dashboardHomeHasTapoRole(client)
    );
  });
}

function dashboardHomeArmingMatterKinds(client) {
  const rawKinds = Array.isArray(client?.matter_kinds) && client.matter_kinds.length
    ? client.matter_kinds
    : [client?.matter_kind];

  return rawKinds
    .map(kind => String(kind || "").trim().toLowerCase())
    .filter(Boolean);
}

const DASHBOARD_HOME_ARMING_MATTER_ENVIRONMENT_KINDS = new Set([
  "temperature",
  "humidity",
  "environment",
  "battery",
  "power",
  "power_source",
  "powersource"
]);

const DASHBOARD_HOME_ARMING_MATTER_MOTION_WORDS = [
  "motion",
  "occupancy",
  "presence"
];

const DASHBOARD_HOME_ARMING_MATTER_SECURITY_WORDS = [
  "contact",
  "motion",
  "occupancy",
  "presence",
  "tamper",
  "vibration",
  "glass",
  "break",
  "smoke",
  "carbon monoxide",
  "co alarm",
  "water",
  "leak",
  "flood",
  "door",
  "window",
  "security",
  "alarm"
];

function dashboardHomeArmingSecurityText(client) {
  return [
    client?.matter_kind,
    ...(Array.isArray(client?.matter_kinds) ? client.matter_kinds : []),
    client?.matter_device_type,
    client?.matter_cluster,
    client?.tapo_kind,
    client?.tapo_child_kind,
    client?.tapo_device_type,
    client?.tapo_child_type,
    client?.tapo_child_category,
    client?.tapo_child_avatar,
    client?.model,
    client?.manufacturer,
    client?.clientName
  ].map(value => String(value || "").trim().toLowerCase()).filter(Boolean).join(" ");
}

function dashboardHomeArmingSecurityTextIncludes(client, words) {
  const text = dashboardHomeArmingSecurityText(client);

  return words.some(word => text.includes(String(word || "").trim().toLowerCase()));
}

function dashboardHomeArmingClientIsMatterContact(client) {
  if (!dashboardHomeArmingClientIsMatter(client)) return false;

  const kinds = dashboardHomeArmingMatterKinds(client);

  return (
    kinds.includes("contact") ||
    client?.contact_open != null ||
    client?.contact_state_value != null ||
    String(client?.matter_device_type || "").trim().toLowerCase().includes("contact")
  );
}

function dashboardHomeArmingClientIsMatterMotion(client) {
  return dashboardHomeArmingClientIsMatter(client) && dashboardHomeArmingSecurityTextIncludes(client, DASHBOARD_HOME_ARMING_MATTER_MOTION_WORDS);
}

function dashboardHomeArmingClientIsMatterEnvironmentOnly(client) {
  if (!dashboardHomeArmingClientIsMatter(client)) return false;
  if (dashboardHomeArmingClientIsMatterContact(client) || dashboardHomeArmingClientIsMatterMotion(client)) return false;

  const kinds = dashboardHomeArmingMatterKinds(client);

  return kinds.length > 0 && kinds.every(kind => DASHBOARD_HOME_ARMING_MATTER_ENVIRONMENT_KINDS.has(kind));
}

function dashboardHomeArmingClientIsMatterEnvironment(client) {
  if (!dashboardHomeArmingClientIsMatter(client)) return false;

  const kinds = dashboardHomeArmingMatterKinds(client);

  return (
    kinds.includes("temperature") ||
    kinds.includes("humidity") ||
    kinds.includes("environment") ||
    client?.temperature_c != null ||
    client?.humidity_percent != null
  );
}

function dashboardHomeArmingClientIsMatterSecuritySensor(client) {
  if (!dashboardHomeArmingClientIsMatter(client)) return false;
  if (dashboardHomeArmingClientIsMatterEnvironmentOnly(client)) return false;
  if (dashboardHomeArmingClientIsMatterContact(client) || dashboardHomeArmingClientIsMatterMotion(client)) return true;

  return dashboardHomeArmingSecurityTextIncludes(client, DASHBOARD_HOME_ARMING_MATTER_SECURITY_WORDS);
}

function dashboardHomeArmingClientIsTapoMotionSource(client) {
  if (!dashboardHomeHasTapoRole(client)) return false;
  if (dashboardHomeArmingClientIsTapoCamera(client)) return true;

  return dashboardHomeArmingSecurityTextIncludes(client, DASHBOARD_HOME_ARMING_MATTER_MOTION_WORDS);
}

function dashboardHomeArmingClientIsSecurityTriggerSource(client) {
  if (!client?.provisioned) return false;

  const roles = clientRolesOf(client);

  return (
    roles.includes("DSS") ||
    roles.includes("CAM") ||
    dashboardHomeArmingClientIsMatterSecuritySensor(client) ||
    dashboardHomeArmingClientIsMatterEnvironment(client) ||
    dashboardHomeArmingClientIsTapoMotionSource(client)
  );
}

function dashboardHomeArmingDoorTriggerNoun(client) {
  return dashboardHomeArmingClientIsMatterContact(client) ? "contact sensor" : "swing sensor";
}

function dashboardHomeArmingMotionTriggerNoun(client) {
  if (dashboardHomeArmingClientIsMatterSecuritySensor(client) && !dashboardHomeArmingClientIsMatterMotion(client)) return "security sensor";

  return "motion detection";
}

function dashboardHomeArmingTriggerSources() {
  const rows = [];

  (S.currentClients || []).forEach(client => {
    if (!dashboardHomeArmingClientIsSecurityTriggerSource(client)) return;

    const deviceID = String(client.deviceID || "").trim();
    const name = dashboardHomeClientName(client);
    const room = dashboardHomeClientRoom(client);
    const roles = clientRolesOf(client);

    if (!deviceID) return;

    if (roles.includes("DSS") || dashboardHomeArmingClientIsMatterContact(client)) {
      const doorNoun = dashboardHomeArmingDoorTriggerNoun(client);

      rows.push({
        deviceID,
        trigger: "door_open",
        label: `${name} ${doorNoun} opens`,
        icon: "door_open",
        room,
        clientName: name,
        triggerOrder: 1
      });

      rows.push({
        deviceID,
        trigger: "door_close",
        label: `${name} ${doorNoun} closes`,
        icon: "door_front",
        room,
        clientName: name,
        triggerOrder: 2
      });
    }

    if (
      roles.includes("CAM") ||
      dashboardHomeArmingClientIsTapoMotionSource(client) ||
      dashboardHomeArmingClientIsMatterMotion(client) ||
      (dashboardHomeArmingClientIsMatterSecuritySensor(client) && !dashboardHomeArmingClientIsMatterContact(client))
    ) {
      const triggerNoun = dashboardHomeArmingMotionTriggerNoun(client);

      rows.push({
        deviceID,
        trigger: "motion",
        label: `${name} ${triggerNoun} detects motion`,
        icon: "motion_sensor_active",
        room,
        clientName: name,
        triggerOrder: 3
      });
    }

    if (dashboardHomeArmingClientIsMatterEnvironment(client)) {
      const kinds = dashboardHomeArmingMatterKinds(client);
      const hasTemperature = kinds.includes("temperature") || kinds.includes("environment") || client?.temperature_c != null;
      const hasHumidity = kinds.includes("humidity") || kinds.includes("environment") || client?.humidity_percent != null;

      if (hasTemperature) {
        rows.push({
          deviceID,
          trigger: "temperature_above",
          label: `${name} temperature rises above`,
          icon: "device_thermostat",
          room,
          clientName: name,
          currentValue: client?.temperature_c == null ? null : Number(client.temperature_c),
          thresholdKind: "temperature",
          triggerOrder: 4
        });

        rows.push({
          deviceID,
          trigger: "temperature_below",
          label: `${name} temperature falls below`,
          icon: "device_thermostat",
          room,
          clientName: name,
          currentValue: client?.temperature_c == null ? null : Number(client.temperature_c),
          thresholdKind: "temperature",
          triggerOrder: 5
        });
      }

      if (hasHumidity) {
        rows.push({
          deviceID,
          trigger: "humidity_above",
          label: `${name} humidity rises above`,
          icon: "humidity_percentage",
          room,
          clientName: name,
          currentValue: client?.humidity_percent == null ? null : Number(client.humidity_percent),
          thresholdKind: "humidity",
          triggerOrder: 6
        });

        rows.push({
          deviceID,
          trigger: "humidity_below",
          label: `${name} humidity falls below`,
          icon: "humidity_percentage",
          room,
          clientName: name,
          currentValue: client?.humidity_percent == null ? null : Number(client.humidity_percent),
          thresholdKind: "humidity",
          triggerOrder: 7
        });
      }
    }
  });

  return rows;
}

function dashboardHomeArmingClientIsTapoCamera(client) {
  const kind = String(client?.tapo_kind || client?.tapo_device_type || "").trim().toLowerCase();

  return dashboardHomeHasTapoRole(client) && (
    kind === "camera" ||
    dashboardHomeBool(client?.tapo_is_camera ?? client?.is_camera) === true
  );
}

function dashboardHomeArmingCameraTargets() {
  return (S.currentClients || [])
    .filter(client => (
      client?.provisioned &&
      (
        (!dashboardHomeHasTapoRole(client) && clientRolesOf(client).includes("CAM")) ||
        dashboardHomeArmingClientIsTapoCamera(client)
      )
    ))
    .map(client => {
      const isTapoCamera = dashboardHomeArmingClientIsTapoCamera(client);
      const name = dashboardHomeClientName(client);

      return {
        deviceID: String(client.deviceID || "").trim(),
        label: name,
        icon: window.dashboardDeviceIconName(client),
        room: dashboardHomeClientRoom(client),
        clientName: name,
        cameraType: isTapoCamera ? "Tapo Camera" : "Android Camera",
        choiceKind: isTapoCamera ? "tapo-camera" : "camera"
      };
    })
    .filter(client => client.deviceID)
    .sort((a, b) => (
      String(a.room).localeCompare(String(b.room)) ||
      String(a.clientName).localeCompare(String(b.clientName))
    ));
}

function dashboardHomeArmingKeyTargets() {
  return (S.currentClients || [])
    .filter(client => client?.provisioned && clientRolesOf(client).includes("KEY"))
    .map(client => {
      const name = dashboardHomeClientName(client);

      return {
        deviceID: String(client.deviceID || "").trim(),
        label: name,
        icon: window.dashboardDeviceIconName(client),
        room: dashboardHomeClientRoom(client) || "Key Clients",
        clientName: name,
        choiceKind: "key"
      };
    })
    .filter(client => client.deviceID)
    .sort((a, b) => (
      String(a.room).localeCompare(String(b.room)) ||
      String(a.clientName).localeCompare(String(b.clientName))
    ));
}

function dashboardHomeArmingDeviceTargets() {
  const targets = [];
  const seen = new Set();

  (S.currentClients || [])
    .filter(client => client?.provisioned)
    .filter(dashboardHomeHasTapoRole)
    .forEach(client => {
      const deviceID = String(client?.deviceID || "").trim();
      const parentID = String(client?.tapo_parent_device_id || "").trim();
      const childID = String(client?.tapo_child_id || "").trim();
      const targetDeviceID = parentID || deviceID;
      const targetID = childID ? `${targetDeviceID}|${childID}` : `${targetDeviceID}|`;
      const kind = String(client?.tapo_kind || client?.tapo_device_type || "").toLowerCase();
      const supportsPower = dashboardHomeBool(client?.tapo_supports_power ?? client?.supports_power);
      const isCamera = dashboardHomeBool(client?.tapo_is_camera ?? client?.is_camera) === true || kind === "camera";
      const isLight = dashboardHomeBool(client?.tapo_is_bulb ?? client?.is_bulb) === true ||
        kind === "bulb" ||
        kind === "lightstrip";
      const icon = window.dashboardDeviceIconName(client);

      if (!targetDeviceID || seen.has(targetID) || isCamera) return;

      if (
        supportsPower !== true &&
        !client?.tapo_is_bulb &&
        !client?.tapo_is_plug &&
        !childID &&
        !["bulb", "lightstrip", "plug", "outlet"].includes(kind)
      ) {
        return;
      }

      seen.add(targetID);
      targets.push({
        deviceID,
        targetDeviceID,
        targetID,
        label: `${dashboardHomeClientRoom(client)} · ${dashboardHomeClientName(client)}`,
        icon,
        room: dashboardHomeClientRoom(client),
        clientName: dashboardHomeClientName(client),
        choiceKind: isLight ? "tapo-bulb" : "tapo-plug",
        routeActionType: "device_on"
      });
    });

  if (dashboardHomeArmingHasAndroidMotionFeedbackContext()) {
    dashboardHomeArmingPendingSourceIDs.forEach(deviceID => {
      const client = dashboardHomeArmingClientForDevice(deviceID);

      if (
        !client?.provisioned ||
        !clientRolesOf(client).includes("CAM") ||
        dashboardHomeArmingClientIsMatter(client) ||
        dashboardHomeHasTapoRole(client)
      ) {
        return;
      }

      const room = dashboardHomeClientRoom(client);
      const feedbackTargets = [
        {
          routeActionType: "android_flashlight",
          label: "Camera Flashlight",
          icon: "bolt"
        },
        {
          routeActionType: "android_white_screen",
          label: "White Screen",
          icon: "mobile_screen"
        }
      ];

      feedbackTargets.forEach(feedbackTarget => {
        const targetID = `${deviceID}|${feedbackTarget.routeActionType}`;

        if (!deviceID || seen.has(targetID)) return;

        seen.add(targetID);
        targets.push({
          deviceID,
          targetDeviceID: deviceID,
          targetID,
          label: `${room} · ${feedbackTarget.label}`,
          icon: feedbackTarget.icon,
          room,
          clientName: feedbackTarget.label,
          choiceKind: "android-camera",
          routeActionType: feedbackTarget.routeActionType
        });
      });
    });
  }

  return targets.sort((a, b) => a.label.localeCompare(b.label));
}

function dashboardHomeArmingDeviceTargetFromID(targetID) {
  const cleanTargetID = String(targetID || "").trim();

  if (!cleanTargetID) return null;

  return dashboardHomeArmingDeviceTargets()
    .find(target => target.targetID === cleanTargetID) || null;
}

function dashboardHomeArmingPowerTargetActionType(targetID) {
  const target = dashboardHomeArmingDeviceTargetFromID(targetID);
  const targetKind = String(targetID || "").split("|")[1] || "";
  const routeActionType = target?.routeActionType ||
    (dashboardHomeArmingActionUsesSourceCamera(targetKind) ? targetKind : "device_on");

  return dashboardHomeArmingActionMeta(routeActionType).actionType;
}

function dashboardHomeArmingDeviceTargetLabel(route) {
  const targetID = String(route?.targetID || route?.target_id || route?.to_input || "").trim();
  const target = dashboardHomeArmingDeviceTargetFromID(targetID);

  if (target) return target.label;

  return dashboardHomeArmingClientLabel(dashboardHomeArmingRouteTarget(route));
}

function dashboardHomeArmingClientLabel(deviceID) {
  const client = (S.currentClients || []).find(item => String(item?.deviceID || "") === String(deviceID || ""));
  return client ? dashboardHomeClientName(client) : String(deviceID || "Device");
}

function dashboardHomeArmingTriggerLabel(route) {
  const sourceID = dashboardHomeArmingRouteSource(route);
  const sourceName = dashboardHomeArmingClientLabel(sourceID);
  const trigger = dashboardHomeArmingRouteTrigger(route);

  if (trigger === "door_open") return `${sourceName} opens`;
  if (trigger === "door_close") return `${sourceName} closes`;
  if (trigger === "motion") return `${sourceName} detects motion`;
  if (trigger === "temperature_above") return `${sourceName} temperature rises above`;
  if (trigger === "temperature_below") return `${sourceName} temperature falls below`;
  if (trigger === "humidity_above") return `${sourceName} humidity rises above`;
  if (trigger === "humidity_below") return `${sourceName} humidity falls below`;

  return sourceName;
}

function dashboardHomeArmingSavedRoutesForMode(mode) {
  return dashboardHomeArmingRoutes()
    .filter(route => dashboardHomeArmingRouteForMode(route, mode));
}

function dashboardHomeArmingDeviceManufacturer(client) {
  if (dashboardHomeArmingClientIsMatter(client)) return "Matter";
  if (dashboardHomeHasTapoRole(client)) return "Tapo";

  return "Android";
}

function dashboardHomeArmingTriggerDeviceApparatus(client) {
  const roles = clientRolesOf(client);
  const kind = String(client?.tapo_kind || client?.tapo_device_type || client?.matter_kind || client?.matter_device_type || client?.security_apparatus || "").trim().toLowerCase();
  const name = String(dashboardHomeClientName(client) || "").trim().toLowerCase();

  if (dashboardHomeArmingClientIsMatterContact(client)) return "Contact Sensor";
  if (dashboardHomeArmingClientIsMatterMotion(client)) return "Occupancy Sensor";
  if (dashboardHomeArmingClientIsTapoMotionSource(client) || kind.includes("motion") || name.includes("motion")) return "Motion Detection";
  if (dashboardHomeArmingClientIsMatterEnvironment(client)) return "Environmental Sensor";

  if (roles.includes("CAM") && roles.includes("DSS")) {
    return "Motion Detection + Door Swing Sensor";
  }

  if (roles.includes("DSS")) return dashboardHomeArmingClientIsMatter(client) ? "Security Sensor" : "Door Swing Sensor";
  if (roles.includes("CAM")) return "Motion Detection";
  if (kind.includes("contact") || kind.includes("door")) return "Contact Sensor";
  if (dashboardHomeArmingClientIsMatterSecuritySensor(client)) return "Security Sensor";
  if (kind.includes("sensor")) return "Sensor";

  return "Security Device";
}

function dashboardHomeArmingTriggerDeviceSubtitle(client) {
  return `${dashboardHomeArmingDeviceManufacturer(client)} ${dashboardHomeArmingTriggerDeviceApparatus(client)}`;
}

function dashboardHomeArmingTriggerDeviceIconMeta(client) {
  const roles = clientRolesOf(client);
  const apparatus = dashboardHomeArmingTriggerDeviceApparatus(client);
  const icon = window.dashboardDeviceIconName(client);

  if (dashboardHomeArmingClientIsMatterEnvironment(client)) {
    return {
      icon,
      className: "indicator-icon green",
      cardKind: "sensor"
    };
  }

  if (dashboardHomeArmingClientIsMatterMotion(client)) {
    return {
      icon,
      className: "status-key green",
      cardKind: "sensor"
    };
  }

  if (apparatus.toLowerCase().includes("motion")) {
    return {
      icon,
      className: "status-cam green",
      cardKind: "camera"
    };
  }

  if (dashboardHomeArmingClientIsTapoCamera(client)) {
    return {
      icon,
      className: "tapo-device-icon status-tapo-camera",
      cardKind: "tapo"
    };
  }

  if (roles.includes("DSS") && !roles.includes("CAM")) {
    return {
      icon,
      className: "status-door green",
      cardKind: "door"
    };
  }

  if (roles.includes("CAM")) {
    return {
      icon,
      className: "status-cam green",
      cardKind: "camera"
    };
  }

  return {
    icon,
    className: "indicator-icon green",
    cardKind: "sensor"
  };
}

function dashboardHomeArmingTriggerDeviceSortKey(item) {
  return `${String(item.room || "").toLowerCase()}\u0000${String(item.name || "").toLowerCase()}\u0000${String(item.deviceID || "")}`;
}

function dashboardHomeArmingOverviewTriggerDevices(routes) {
  const map = new Map();

  const addClient = (client, fallbackRoom = "Unassigned") => {
    const deviceID = String(client?.deviceID || "").trim();
    if (!deviceID || map.has(deviceID)) return;

    map.set(deviceID, {
      deviceID,
      client,
      name: dashboardHomeClientName(client),
      room: dashboardHomeClientRoom(client) || fallbackRoom || "Unassigned"
    });
  };

  dashboardHomeArmingTriggerSources().forEach(trigger => {
    const client = dashboardHomeArmingClientForDevice(trigger.deviceID);

    if (client && !dashboardHomeArmingClientIsMatterEnvironmentOnly(client)) {
      addClient(client, trigger.room);
    }
  });

  (S.currentClients || [])
    .filter(client => client?.provisioned)
    .filter(client => dashboardHomeArmingClientIsTapoCamera(client))
    .forEach(client => addClient(client));

  (routes || []).forEach(route => {
    const sourceID = dashboardHomeArmingRouteSource(route);
    const client = dashboardHomeArmingClientForDevice(sourceID);

    if (client && !dashboardHomeArmingClientIsMatterEnvironmentOnly(client)) {
      addClient(client);
    }
  });

  return [...map.values()].sort((a, b) => dashboardHomeArmingTriggerDeviceSortKey(a).localeCompare(dashboardHomeArmingTriggerDeviceSortKey(b)));
}

function dashboardHomeArmingDeviceActionTargetLabel(route) {
  const targetID = String(route?.targetID || route?.target_id || route?.to_input || "").trim();
  const target = dashboardHomeArmingDeviceTargetFromID(targetID);

  if (target) return target.clientName || String(target.label || "").split(" · ").pop() || "Device";

  return dashboardHomeArmingClientLabel(dashboardHomeArmingRouteTarget(route));
}

function dashboardHomeArmingRouteActionSummary(route) {
  const action = dashboardHomeArmingActionMeta(dashboardHomeArmingRouteAction(route));

  if (action.actionType === "device_on") {
    return {
      icon: "toggle_on",
      label: `Turn on ${dashboardHomeArmingDeviceActionTargetLabel(route)}`,
      className: "dashboard-home-arming-action-summary-device"
    };
  }

  if (action.actionType === "sound") {
    const soundFile = String(route.filename || route.sound || route.to_input || "Sound").trim();
    const soundName = soundFile.split(/[\\/]/).filter(Boolean).pop() || soundFile || "Sound";

    return {
      icon: "music_note",
      label: `Play ${soundName}`,
      className: "dashboard-home-arming-action-summary-sound"
    };
  }

  if (action.actionType === "notification") {
    return {
      icon: "notifications",
      label: `Notify ${dashboardHomeArmingNotificationTargetLabel(route)}`,
      className: "dashboard-home-arming-action-summary-notification"
    };
  }

  return {
    icon: "videocam",
    label: `Start recording on ${dashboardHomeArmingClientLabel(dashboardHomeArmingRouteTarget(route) || dashboardHomeArmingRouteSource(route))}`,
    className: "dashboard-home-arming-action-summary-recording"
  };
}

function dashboardHomeArmingRouteThreshold(route) {
  const values = [
    route?.threshold,
    route?.trigger_threshold,
    route?.threshold_value,
    route?.thresholdValue
  ];

  for (const value of values) {
    if (value == null || value === "") continue;

    const threshold = Number(value);

    if (Number.isFinite(threshold)) return threshold;
  }

  return null;
}

function dashboardHomeArmingRouteConditionLabel(route) {
  const trigger = dashboardHomeArmingRouteTrigger(route);
  const threshold = dashboardHomeArmingRouteThreshold(route);

  if (!dashboardHomeArmingTriggerIsEnvironment(trigger) || threshold === null) return "";

  const direction = trigger.endsWith("_above") ? "above" : "below";

  if (trigger.startsWith("temperature_")) {
    const unit = dashboardHomeArmingTemperatureUnit();
    const display = dashboardHomeArmingTemperatureFromC(threshold, unit);
    const suffix = unit === "f" ? "°F" : "°C";

    return `Temperature ${direction} ${Number(display.toFixed(1))}${suffix}`;
  }

  return `Humidity ${direction} ${Number(threshold.toFixed(1))}%`;
}

function dashboardHomeArmingActionSummaryRowHtml(route, index) {
  const summary = dashboardHomeArmingRouteActionSummary(route);
  const condition = dashboardHomeArmingRouteConditionLabel(route);

  return `
    <div class="dashboard-home-arming-action-summary-row ${escAttr(summary.className)}">
      ${window.dashboardIconHtml(summary.icon)}
      <span class="dashboard-home-arming-action-summary-text">${esc(condition ? `${condition}: ${summary.label}` : summary.label)}</span>
      <button
        class="modal-close dashboard-home-arming-action-summary-delete"
        type="button"
        aria-label="Remove action"
        data-dashboard-action="delete-home-arming-route"
        data-route-index="${index}"
      >
        ${window.dashboardIconHtml("close")}
      </button>
    </div>
  `;
}

function dashboardHomeArmingTriggerDeviceCardHtml(item, routes, mode) {
  const iconMeta = dashboardHomeArmingTriggerDeviceIconMeta(item.client);
  const deviceRoutes = routes
    .map((route, index) => ({ route, index }))
    .filter(entry => dashboardHomeArmingRouteSource(entry.route) === item.deviceID);
  const statusClass = deviceRoutes.length > 0 ? "active" : "inactive";
  const staleClass = dashboardHomeArmingClientIsTapoMotionSource(item.client) ? " stale-client" : "";

  return `
    <article class="modal-device-card dashboard-home-arming-overview-device ${escAttr(statusClass)}${staleClass}" data-node-card="${escAttr(iconMeta.cardKind)}">
      <div class="modal-device-card-head dashboard-home-arming-overview-device-head">
        <span class="modal-device-card-identity">
          ${window.dashboardIconHtml(iconMeta.icon, `dashboard-home-arming-overview-icon ${iconMeta.className}`)}
          <span class="modal-device-card-title card-title">${esc(item.name)}</span>
        </span>

        <button
          class="modal-close dashboard-home-arming-device-add"
          type="button"
          title="Add action"
          aria-label="Add action for ${escAttr(item.name)}"
          data-dashboard-action="show-home-arming-action-picker"
          data-mode="${escAttr(mode)}"
          data-trigger-device-id="${escAttr(item.deviceID)}"
        >
          ${window.dashboardIconHtml("add")}
        </button>
      </div>

      <span class="modal-device-card-label settings-automation-subtitle dashboard-home-arming-overview-subtitle">${esc(dashboardHomeArmingTriggerDeviceSubtitle(item.client))}</span>

      ${deviceRoutes.length ? `
        <div class="modal-device-card-controls dashboard-home-arming-action-summary-list">
          ${deviceRoutes.map(entry => dashboardHomeArmingActionSummaryRowHtml(entry.route, entry.index)).join("")}
        </div>
      ` : ""}
    </article>
  `;
}

function dashboardHomeArmingRoomOverviewHtml(room, devices, routes, mode) {
  return `
    <section class="settings-server-card dashboard-home-arming-room-card">
      <h3 class="modal-section-title">${esc(room)}</h3>

      <div class="modal-device-card-grid dashboard-home-arming-room-device-grid">
        ${devices.map(item => dashboardHomeArmingTriggerDeviceCardHtml(item, routes, mode)).join("")}
      </div>
    </section>
  `;
}

function dashboardHomeArmingSavedActionsHtml(mode) {
  const routes = dashboardHomeArmingSavedRoutesForMode(mode);
  const triggerDevices = dashboardHomeArmingOverviewTriggerDevices(routes);
  const byRoom = new Map();

  dashboardHomeArmingRenderedRoutes = routes;

  triggerDevices.forEach(item => {
    const room = item.room || "Unassigned";
    if (!byRoom.has(room)) byRoom.set(room, []);
    byRoom.get(room).push(item);
  });

  if (!triggerDevices.length) {
    return `
      <div class="dashboard-home-arming-empty">
        No security trigger devices are available yet.
      </div>
    `;
  }

  return `
    <div class="dashboard-home-arming-room-overview-list">
      ${[...byRoom.entries()].map(([room, devices]) => dashboardHomeArmingRoomOverviewHtml(room, devices, routes, mode)).join("")}
    </div>
  `;
}

window.selectDashboardHomeArmingSettingsMode = function (mode) {
  dashboardHomeArmingSelectedMode = dashboardHomeCleanArmMode(mode);
  renderDashboardHomeArmingSettings();
};

function renderDashboardHomeArmingSettings() {
  const body = document.getElementById("dashboardHomeArmingModalBody");
  if (!body) return;

  const selectedMode = dashboardHomeCleanArmMode(dashboardHomeArmingSelectedMode);
  const selectedModeMeta = dashboardHomeArmingModeMeta(selectedMode);

  body.innerHTML = `
    <section class="modal-section dashboard-home-arming-states-section">
      <div class="dashboard-home-arming-state-tabs dashboard-home-arm-row">
        ${DASHBOARD_HOME_ARMING_MODES.map(mode => `
          <button
            class="settings-item dashboard-home-arm-btn dashboard-home-arming-state-btn ${mode.mode === selectedMode ? "active" : ""}"
            type="button"
            data-dashboard-action="select-home-arming-settings-mode"
            data-mode="${escAttr(mode.mode)}"
          >
            <span class="ui-icon-circle dashboard-home-mode-circle">${window.dashboardIconHtml(mode.icon, "dashboard-home-mode-icon")}</span>
            <span>${esc(mode.label)}</span>
          </button>
        `).join("")}
      </div>
    </section>

    <section class="modal-section dashboard-home-arming-selected-section">
      <h2 class="modal-section-title">${esc(selectedModeMeta.label)} Actions</h2>
      ${dashboardHomeArmingSavedActionsHtml(selectedMode)}
    </section>
  `;
}

function renderDashboardHomeArmingActionPicker(mode) {
  const body = document.getElementById("dashboardHomeArmingActionBody");
  const title = document.getElementById("dashboardHomeArmingActionTitle");
  const subtitle = document.getElementById("dashboardHomeArmingActionSubtitle");
  const modeMeta = dashboardHomeArmingModeMeta(dashboardHomeCleanArmMode(mode));

  if (title) {
    title.textContent = dashboardHomeArmingRouteScope === "automation"
      ? "New Automation"
      : "New Security System Action";
  }

  if (subtitle) {
    subtitle.textContent = "";
    subtitle.hidden = true;
  }

  if (!body) return;

  dashboardHomeArmingWizardStep = "response";
  dashboardHomeArmingUpdateBreadcrumb("response", modeMeta.mode, dashboardHomeArmingDraft?.actionType || "");

  body.innerHTML = `
    <section class="modal-section dashboard-home-arming-picker-section">
      <div class="dashboard-home-arming-picker-actions">
        <button class="settings-item dashboard-home-arming-big-action" type="button" data-dashboard-action="select-home-arming-action-type" data-mode="${escAttr(modeMeta.mode)}" data-action-type="device_on">
          ${window.dashboardIconHtml("toggle_on")}
          <span class="settings-automation-title">Power on...</span>
        </button>

        <button class="settings-item dashboard-home-arming-big-action" type="button" data-dashboard-action="select-home-arming-action-type" data-mode="${escAttr(modeMeta.mode)}" data-action-type="sound">
          ${window.dashboardIconHtml("music_note")}
          <span class="settings-automation-title">Play a Sound</span>
        </button>

        <button class="settings-item dashboard-home-arming-big-action" type="button" data-dashboard-action="select-home-arming-action-type" data-mode="${escAttr(modeMeta.mode)}" data-action-type="notification">
          ${window.dashboardIconHtml("notifications")}
          <span class="settings-automation-title">Send a Notification</span>
        </button>

        <button class="settings-item dashboard-home-arming-big-action" type="button" data-dashboard-action="select-home-arming-action-type" data-mode="${escAttr(modeMeta.mode)}" data-action-type="recording">
          ${window.dashboardIconHtml("videocam")}
          <span class="settings-automation-title">Record a Video</span>
        </button>
      </div>
    </section>
  `;
}

function dashboardHomeArmingSetActionHeader(mode) {
  const title = document.getElementById("dashboardHomeArmingActionTitle");
  const subtitle = document.getElementById("dashboardHomeArmingActionSubtitle");

  if (title) {
    title.textContent = dashboardHomeArmingEditingAutomationID
      ? "Edit Automation"
      : dashboardHomeArmingRouteScope === "automation"
        ? "New Automation"
        : "New Security System Action";
  }

  if (subtitle) {
    subtitle.textContent = "";
    subtitle.hidden = true;
  }
}

function dashboardHomeArmingTargetStepComplete(draft = dashboardHomeArmingDraft) {
  if (!draft?.actionType) return false;

  const actionType = dashboardHomeArmingActionMeta(draft.actionType).actionType;

  if (actionType === "sound") {
    return !!String(draft.soundFile || "").trim();
  }

  return Array.isArray(draft.targetIDs) && draft.targetIDs.length > 0;
}

function dashboardHomeArmingUpdateBreadcrumb(step = dashboardHomeArmingWizardStep, mode = null, actionType = null) {
  const nav = document.getElementById("dashboardHomeArmingBreadcrumb");

  if (!nav) return;

  const draft = dashboardHomeArmingDraft;
  const cleanStep = ["response", "trigger", "target", "rules"].includes(step) ? step : "response";
  const cleanMode = dashboardHomeCleanArmMode(mode || draft?.mode || dashboardHomeArmingSelectedMode);
  const cleanActionType = String(actionType || draft?.actionType || "").trim();
  const responseComplete = !!cleanActionType;
  const triggerComplete = responseComplete && Array.isArray(draft?.triggerIDs) && draft.triggerIDs.length > 0;
  const targetComplete = triggerComplete && dashboardHomeArmingTargetStepComplete(draft);
  const steps = [
    { step: "response", label: "1 Response", enabled: true },
    { step: "trigger", label: "2 Trigger", enabled: responseComplete },
    { step: "target", label: "3 Target", enabled: triggerComplete },
    { step: "rules", label: "4 Rules", enabled: targetComplete }
  ];

  dashboardHomeArmingWizardStep = cleanStep;

  nav.innerHTML = `
    <div class="dashboard-home-arming-breadcrumb-track">
      ${steps.map(item => `
        <button
          class="settings-item dashboard-home-arming-breadcrumb-btn ${item.step === cleanStep ? "active" : ""}"
          type="button"
          data-dashboard-action="show-home-arming-breadcrumb-step"
          data-step="${escAttr(item.step)}"
          data-mode="${escAttr(cleanMode)}"
          data-action-type="${escAttr(cleanActionType)}"
          ${item.enabled ? "" : "disabled"}
        >
          <span>${esc(item.label)}</span>
        </button>
      `).join("")}
    </div>
  `;
}

function dashboardHomeArmingCaptureCurrentStepDraft() {
  if (!dashboardHomeArmingDraft) return null;

  const actionType = dashboardHomeArmingDraft.actionType;

  if (dashboardHomeArmingWizardStep === "trigger") {
    dashboardHomeArmingCaptureEnvironmentThresholds();

    const triggerButtons = [...document.querySelectorAll('#dashboardHomeArmingActionBody [data-dashboard-action="toggle-home-arming-trigger"]')];

    if (triggerButtons.length) {
      dashboardHomeArmingDraft.triggerIDs = triggerButtons
        .filter(item => item.classList.contains("active"))
        .map(item => String(item?.dataset?.choiceId || "").trim())
        .filter(Boolean);
    }
  }

  if (dashboardHomeArmingWizardStep === "target") {
    dashboardHomeArmingCaptureTargetStepDraft(actionType);
  }

  if (dashboardHomeArmingWizardStep === "rules") {
    dashboardHomeArmingCapturePostTriggerDraft(actionType);
  }

  return dashboardHomeArmingDraft;
}

function dashboardHomeArmingCurrentStepSelectionComplete(step = dashboardHomeArmingWizardStep) {
  if (!dashboardHomeArmingDraft) return false;

  if (step === "trigger") {
    return (
      Array.isArray(dashboardHomeArmingDraft.triggerIDs) &&
      dashboardHomeArmingDraft.triggerIDs.length > 0 &&
      dashboardHomeArmingEnvironmentThresholdsComplete(dashboardHomeArmingDraft)
    );
  }

  if (step === "target") {
    return dashboardHomeArmingTargetStepComplete(dashboardHomeArmingDraft);
  }

  return true;
}

function dashboardHomeArmingUpdateStepActionButtons(step = dashboardHomeArmingWizardStep) {
  const complete = dashboardHomeArmingCurrentStepSelectionComplete(step);

  document
    .querySelectorAll('#dashboardHomeArmingActionBody [data-dashboard-requires-step-selection="1"]')
    .forEach(button => {
      button.disabled = !complete;
    });
}

function dashboardHomeArmingChoiceID(item, kind) {
  if (kind === "trigger") return `${item.deviceID}|${item.trigger}`;
  if (kind === "device_on") return item.targetID;
  if (kind === "notification") return item.deviceID;
  return item.deviceID;
}

function dashboardHomeArmingClientForDevice(deviceID) {
  return (S.currentClients || [])
    .find(client => String(client?.deviceID || "") === String(deviceID || ""));
}

function dashboardHomeArmingChoiceRoom(item) {
  if (item?.room) return item.room;

  const client = dashboardHomeArmingClientForDevice(item.deviceID);
  const room = dashboardHomeClientRoom(client || {});

  if (room) return room;

  if (String(item?.label || "").includes(" · ")) {
    return String(item.label).split(" · ")[0] || "Other";
  }

  return "Other";
}

function dashboardHomeArmingChoiceLabel(item, kind) {
  if (kind === "device_on") {
    return String(item.label || "").split(" · ").pop() || "Device";
  }

  return item.label || "Device";
}

function dashboardHomeArmingChoiceCardKind(item, kind) {
  const choiceKind = String(item?.choiceKind || "").trim();

  if (choiceKind.startsWith("tapo-")) return "tapo";
  if (choiceKind === "android-camera") return "camera";
  if (kind === "notification") return "key";
  if (kind === "recording") return "camera";
  if (kind === "device_on") return choiceKind || "control";
  if (kind === "trigger") {
    const trigger = String(item?.trigger || "");

    if (trigger === "motion") return "camera";
    if (trigger.startsWith("temperature_") || trigger.startsWith("humidity_")) return "sensor";

    return "door";
  }

  return "control";
}

function dashboardHomeArmingChoiceIconClass(item, kind) {
  const choiceKind = String(item?.choiceKind || "").trim();
  const cardKind = dashboardHomeArmingChoiceCardKind(item, kind);

  if (kind !== "trigger") {
    return choiceKind === "android-camera"
      ? "icon-glow status-cam green"
      : "icon-glow";
  }

  if (cardKind === "camera") return "status-cam green";
  if (cardKind === "door") return "status-door green";
  if (cardKind === "key") return "status-key green";

  return "indicator-icon green";
}

function dashboardHomeArmingSoundVolumePercent(value) {
  const parsed = Number(value);

  if (!Number.isFinite(parsed)) return 100;

  return Math.max(0, Math.min(100, Math.round(parsed)));
}

function dashboardHomeArmingRecordingMinimumSeconds(value) {
  const parsed = Number(value);

  if (!Number.isFinite(parsed)) return 15;

  return Math.max(5, Math.min(3600, Math.round(parsed)));
}

function dashboardHomeArmingNotificationTargetLabel(route) {
  const targetID = String(
    route?.target_key_deviceID ||
    route?.targetKeyDeviceID ||
    route?.notification_target_deviceID ||
    route?.notificationTargetDeviceID ||
    route?.to_deviceID ||
    route?.targetDeviceID ||
    ""
  ).trim();

  if (!targetID || targetID === "__all_key_clients__") {
    return "All Key Clients";
  }

  return dashboardHomeArmingClientLabel(targetID);
}

function dashboardHomeArmingGroupedChoiceHtml(items, kind, selectedIDs, emptyName) {
  const selected = new Set(selectedIDs || []);
  const isTrigger = kind === "trigger";
  const isDeviceTarget = kind === "device_on";
  const isNotificationTarget = kind === "notification";
  const isRecordingTarget = kind === "recording";
  const isClientTarget = isDeviceTarget || isNotificationTarget || isRecordingTarget;
  const isIconChoice = isTrigger || isClientTarget;
  const rows = (items || [])
    .map(item => ({
      ...item,
      choiceID: dashboardHomeArmingChoiceID(item, kind),
      room: dashboardHomeArmingChoiceRoom(item),
      choiceLabel: dashboardHomeArmingChoiceLabel(item, kind)
    }))
    .filter(item => item.choiceID)
    .sort((a, b) => (
      String(a.room).localeCompare(String(b.room)) ||
      String(a.clientName || a.choiceLabel).localeCompare(String(b.clientName || b.choiceLabel)) ||
      Number(a.triggerOrder || 0) - Number(b.triggerOrder || 0) ||
      String(a.choiceLabel).localeCompare(String(b.choiceLabel))
    ));

  if (!rows.length) {
    return `
      <section class="modal-section">
        <div class="dashboard-home-arming-empty">
          No ${esc(emptyName || "choices")} found.
        </div>
      </section>
    `;
  }

  const grouped = rows.reduce((acc, item) => {
    const room = item.room || "Other";
    if (!acc[room]) acc[room] = [];
    acc[room].push(item);
    return acc;
  }, {});

  return Object.entries(grouped).map(([room, group]) => `
    <section class="modal-section">
      <div class="modal-section-title">${esc(room)}</div>
      <div class="${isClientTarget ? "modal-device-card-grid dashboard-home-arming-device-list" : "client-menu-actions"} ${isTrigger ? "dashboard-home-arming-trigger-list" : ""}">
        ${group.map(item => `
          <button
            class="settings-item ${isIconChoice ? "settings-automation-item" : ""} ${isTrigger ? "dashboard-home-arming-trigger-choice" : ""} ${isClientTarget ? "modal-device-card dashboard-home-arming-device-choice dashboard-home-arming-client-choice" : ""} ${selected.has(item.choiceID) ? "active" : ""}"
            type="button"
            data-dashboard-action="${isTrigger ? "toggle-home-arming-trigger" : "toggle-home-arming-target"}"
            data-choice-id="${escAttr(item.choiceID)}"
            data-node-card="${escAttr(dashboardHomeArmingChoiceCardKind(item, kind))}"
          >
            ${isClientTarget ? `
              <span class="modal-device-card-head">
                <span class="modal-device-card-identity">
                  ${window.dashboardIconHtml(item.icon || "toggle_on", dashboardHomeArmingChoiceIconClass(item, kind))}
                  <span class="modal-device-card-copy">
                    <span class="modal-device-card-title">${esc(item.choiceLabel)}</span>
                  </span>
                </span>
              </span>
            ` : isIconChoice ? `
              ${window.dashboardIconHtml(item.icon || "toggle_on", dashboardHomeArmingChoiceIconClass(item, kind))}
              <span class="settings-automation-title">${esc(item.choiceLabel)}</span>
            ` : `
              <span>${esc(item.choiceLabel)}</span>
            `}
          </button>
        `).join("")}
      </div>
    </section>
  `).join("");
}

function dashboardHomeArmingSoundGroups() {
  return (S.soundNodes || [])
    .map(category => {
      const categoryName = String(category?.category || category?.name || category?.directory || "Sounds").trim() || "Sounds";
      const files = (Array.isArray(category?.files) ? category.files : [])
        .map(file => {
          const filename = typeof file === "string" ? file : file?.filename;
          const displayName = typeof file === "string"
            ? String(file).split("/").pop()
            : (file?.display_name || file?.displayName || file?.name || String(filename || "").split("/").pop());

          return {
            filename: String(filename || "").trim(),
            displayName: String(displayName || filename || "Sound").trim()
          };
        })
        .filter(file => file.filename)
        .sort((a, b) => a.displayName.localeCompare(b.displayName));

      return { categoryName, files };
    })
    .filter(category => category.files.length)
    .sort((a, b) => a.categoryName.localeCompare(b.categoryName));
}

function dashboardHomeArmingDefaultSoundFile() {
  const groups = dashboardHomeArmingSoundGroups();
  return groups[0]?.files?.[0]?.filename || "";
}

function dashboardHomeArmingSoundChoiceHtml(selectedFilename, selectedVolumePercent = 100) {
  const groups = dashboardHomeArmingSoundGroups();
  const selected = String(selectedFilename || "").trim();
  const volumePercent = dashboardHomeArmingSoundVolumePercent(selectedVolumePercent);
  const volumeControls = `
    <section class="modal-section dashboard-home-arming-sound-controls-section">
      <div class="dashboard-home-arming-sound-control-row">
        <label class="settings-field-row dashboard-home-arming-sound-volume-field">
          <span class="settings-field-label">Volume <span id="dashboardHomeArmingSoundVolumeValue">${esc(volumePercent)}%</span></span>
          <input
            id="dashboardHomeArmingSoundVolumeInput"
            class="settings-input dashboard-home-arming-sound-volume"
            type="range"
            min="0"
            max="100"
            step="5"
            value="${escAttr(volumePercent)}"
            data-dashboard-input="update-home-arming-sound-volume"
          >
        </label>

        <button class="client-menu-btn dashboard-home-arming-test-sound" type="button" data-dashboard-action="test-home-arming-sound">
          ${window.dashboardIconHtml("play_arrow")}
          <span>Play</span>
        </button>
      </div>
    </section>
  `;

  if (!groups.length) {
    return `
      <section class="modal-section">
        <div class="dashboard-home-arming-empty">
          No WAV files found.
        </div>
      </section>
      ${volumeControls}
    `;
  }

  return `${groups.map(group => `
    <section class="modal-section">
      <div class="modal-section-title">${esc(group.categoryName)}</div>
      <div class="client-menu-actions dashboard-home-arming-trigger-list">
        ${group.files.map(file => `
          <button
            class="settings-item settings-automation-item dashboard-home-arming-trigger-choice ${selected === file.filename ? "active" : ""}"
            type="button"
            data-dashboard-action="select-home-arming-sound"
            data-sound-file="${escAttr(file.filename)}"
          >
            ${window.dashboardIconHtml("music_note")}
            <span class="settings-automation-title">${esc(file.displayName)}</span>
          </button>
        `).join("")}
      </div>
    </section>
  `).join("")}${volumeControls}`;
}

function dashboardHomeArmingCleanTriggerGroup(value) {
  const clean = String(value || "").trim().toLowerCase();

  return ["door", "motion", "environment"].includes(clean) ? clean : "";
}

function dashboardHomeArmingTriggerMatchesGroup(trigger, group) {
  const cleanTrigger = String(trigger || "").trim().toLowerCase();
  const cleanGroup = dashboardHomeArmingCleanTriggerGroup(group);

  if (!cleanGroup) return true;
  if (cleanGroup === "door") return ["door_open", "door_close"].includes(cleanTrigger);
  if (cleanGroup === "motion") return cleanTrigger === "motion";

  return cleanTrigger.startsWith("temperature_") || cleanTrigger.startsWith("humidity_");
}

function dashboardHomeArmingTriggerChoicesForContext() {
  const sourceIDs = new Set(dashboardHomeArmingPendingSourceIDs || []);

  return dashboardHomeArmingTriggerSources().filter(item => (
    (!sourceIDs.size || sourceIDs.has(String(item?.deviceID || "").trim())) &&
    dashboardHomeArmingTriggerMatchesGroup(item?.trigger, dashboardHomeArmingPendingTriggerGroup)
  ));
}

function dashboardHomeArmingTriggerChoiceIDsForDevice(deviceIDs, triggerGroup = "") {
  const ids = new Set(
    (Array.isArray(deviceIDs) ? deviceIDs : [deviceIDs])
      .map(deviceID => String(deviceID || "").trim())
      .filter(Boolean)
  );

  if (!ids.size) return [];

  return dashboardHomeArmingTriggerSources()
    .filter(item => ids.has(String(item?.deviceID || "").trim()))
    .filter(item => dashboardHomeArmingTriggerMatchesGroup(item?.trigger, triggerGroup))
    .map(item => dashboardHomeArmingChoiceID(item, "trigger"))
    .filter(Boolean);
}

function dashboardHomeArmingTemperatureUnit() {
  return window.getMatterEnvironmentTemperatureUnit?.() === "f" ? "f" : "c";
}

function dashboardHomeArmingTemperatureFromC(value, unit = dashboardHomeArmingTemperatureUnit()) {
  const number = Number(value);

  if (!Number.isFinite(number)) return null;

  return unit === "f" ? (number * 9 / 5) + 32 : number;
}

function dashboardHomeArmingTemperatureToC(value, unit = dashboardHomeArmingTemperatureUnit()) {
  const number = Number(value);

  if (!Number.isFinite(number)) return null;

  return unit === "f" ? (number - 32) * 5 / 9 : number;
}

function dashboardHomeArmingTriggerIsEnvironment(trigger) {
  const clean = String(trigger || "").trim().toLowerCase();

  return clean.startsWith("temperature_") || clean.startsWith("humidity_");
}

function dashboardHomeArmingEnvironmentThresholdDefault(choiceID) {
  const item = dashboardHomeArmingTriggerSources()
    .find(trigger => dashboardHomeArmingChoiceID(trigger, "trigger") === choiceID);
  const currentValue = item?.currentValue == null ? Number.NaN : Number(item.currentValue);

  if (Number.isFinite(currentValue)) return currentValue;

  return String(item?.trigger || "").startsWith("humidity_") ? 50 : 21;
}

function dashboardHomeArmingEnsureEnvironmentThresholds(draft = dashboardHomeArmingDraft) {
  if (!draft) return {};

  draft.environmentThresholds = draft.environmentThresholds || {};

  (draft.triggerIDs || []).forEach(choiceID => {
    const [, trigger] = String(choiceID || "|").split("|");

    if (!dashboardHomeArmingTriggerIsEnvironment(trigger)) return;

    if (!Object.prototype.hasOwnProperty.call(draft.environmentThresholds, choiceID)) {
      draft.environmentThresholds[choiceID] = dashboardHomeArmingEnvironmentThresholdDefault(choiceID);
    }
  });

  return draft.environmentThresholds;
}

function dashboardHomeArmingCaptureEnvironmentThresholds() {
  if (!dashboardHomeArmingDraft) return {};

  const thresholds = dashboardHomeArmingEnsureEnvironmentThresholds();

  document
    .querySelectorAll('#dashboardHomeArmingActionBody [data-dashboard-environment-threshold="1"]')
    .forEach(input => {
      const choiceID = String(input?.dataset?.choiceId || "").trim();
      const value = Number(input?.value);

      if (!choiceID) return;

      if (!String(input?.value || "").trim() || !Number.isFinite(value)) {
        thresholds[choiceID] = null;
        return;
      }

      thresholds[choiceID] = input?.dataset?.thresholdKind === "temperature"
        ? dashboardHomeArmingTemperatureToC(value, input?.dataset?.temperatureUnit)
        : value;
    });

  return thresholds;
}

function dashboardHomeArmingEnvironmentThresholdsComplete(draft = dashboardHomeArmingDraft) {
  if (!draft) return false;

  const thresholds = dashboardHomeArmingEnsureEnvironmentThresholds(draft);

  return (draft.triggerIDs || []).every(choiceID => {
    const [, trigger] = String(choiceID || "|").split("|");
    const threshold = thresholds[choiceID];

    if (!dashboardHomeArmingTriggerIsEnvironment(trigger)) return true;
    if (threshold == null || threshold === "" || !Number.isFinite(Number(threshold))) return false;

    if (trigger.startsWith("humidity_")) {
      const humidity = Number(threshold);

      return humidity >= 0 && humidity <= 100;
    }

    return true;
  });
}

function dashboardHomeArmingEnvironmentThresholdsHtml(draft = dashboardHomeArmingDraft) {
  if (!draft) return "";

  const selected = new Set(draft.triggerIDs || []);
  const thresholds = dashboardHomeArmingEnsureEnvironmentThresholds(draft);
  const unit = dashboardHomeArmingTemperatureUnit();
  const fields = dashboardHomeArmingTriggerChoicesForContext()
    .map(item => ({ ...item, choiceID: dashboardHomeArmingChoiceID(item, "trigger") }))
    .filter(item => selected.has(item.choiceID) && dashboardHomeArmingTriggerIsEnvironment(item.trigger))
    .map(item => {
      const isTemperature = String(item.trigger).startsWith("temperature_");
      const rawThreshold = thresholds[item.choiceID];
      const storedValue = rawThreshold == null || rawThreshold === "" ? Number.NaN : Number(rawThreshold);
      const displayValue = isTemperature
        ? dashboardHomeArmingTemperatureFromC(storedValue, unit)
        : storedValue;
      const suffix = isTemperature ? (unit === "f" ? "°F" : "°C") : "%";

      return `
        <label class="settings-field-row">
          <span class="settings-field-label">${esc(item.label)} (${suffix})</span>
          <input
            class="settings-input"
            type="number"
            step="0.1"
            ${isTemperature ? "" : 'min="0" max="100"'}
            value="${escAttr(Number.isFinite(displayValue) ? Number(displayValue.toFixed(1)) : "")}" 
            data-dashboard-input="update-home-arming-environment-threshold"
            data-dashboard-environment-threshold="1"
            data-choice-id="${escAttr(item.choiceID)}"
            data-threshold-kind="${isTemperature ? "temperature" : "humidity"}"
            data-temperature-unit="${unit}"
            required
          >
        </label>
      `;
    });

  if (!fields.length) return "";

  return `
    <section class="modal-section dashboard-home-arming-form-section">
      <div class="modal-section-title">Thresholds</div>
      ${fields.join("")}
    </section>
  `;
}

function dashboardHomeArmingDraftFor(mode, actionType) {
  const cleanMode = dashboardHomeCleanArmMode(mode);
  const cleanAction = dashboardHomeArmingActionMeta(actionType).actionType;

  if (
    !dashboardHomeArmingDraft ||
    dashboardHomeArmingDraft.mode !== cleanMode ||
    dashboardHomeArmingDraft.actionType !== cleanAction
  ) {
    dashboardHomeArmingDraft = {
      mode: cleanMode,
      actionType: cleanAction,
      triggerIDs: [...dashboardHomeArmingPendingTriggerIDs],
      targetIDs: [],
      environmentThresholds: {}
    };
  }

  dashboardHomeArmingEnsureEnvironmentThresholds(dashboardHomeArmingDraft);

  return dashboardHomeArmingDraft;
}

function renderDashboardHomeArmingActionForm(mode, actionType) {
  renderDashboardHomeArmingTriggerStep(mode, actionType);
}

function renderDashboardHomeArmingTriggerStep(mode, actionType) {
  const body = document.getElementById("dashboardHomeArmingActionBody");
  const modeMeta = dashboardHomeArmingModeMeta(dashboardHomeCleanArmMode(mode));
  const action = dashboardHomeArmingActionMeta(actionType);
  const draft = dashboardHomeArmingDraftFor(modeMeta.mode, action.actionType);
  const triggers = dashboardHomeArmingTriggerChoicesForContext();

  dashboardHomeArmingSetActionHeader(modeMeta.mode);

  if (!body) return;

  dashboardHomeArmingWizardStep = "trigger";
  dashboardHomeArmingUpdateBreadcrumb("trigger", modeMeta.mode, action.actionType);

  body.innerHTML = `
    <section class="modal-section">
      <div class="modal-subtitle">
        Choose trigger(s) to ${esc(action.label)}
      </div>
    </section>

    ${dashboardHomeArmingGroupedChoiceHtml(triggers, "trigger", draft.triggerIDs, "triggers")}

    ${dashboardHomeArmingEnvironmentThresholdsHtml(draft)}

    <section class="modal-section dashboard-home-arming-save-actions">
      <div class="client-menu-actions">
        <button
          class="client-menu-btn"
          type="button"
          data-dashboard-action="show-home-arming-breadcrumb-step"
          data-step="response"
          data-mode="${escAttr(modeMeta.mode)}"
          data-action-type="${escAttr(action.actionType)}"
        >
          ${window.dashboardIconHtml("arrow_back")}
          <span>Back</span>
        </button>

        <button
          class="client-menu-btn primary"
          type="button"
          data-dashboard-action="show-home-arming-target-step"
          data-dashboard-requires-step-selection="1"
          data-mode="${escAttr(modeMeta.mode)}"
          data-action-type="${escAttr(action.actionType)}"
          ${dashboardHomeArmingCurrentStepSelectionComplete("trigger") ? "" : "disabled"}
        >
          <span>Next</span>
          ${window.dashboardIconHtml("arrow_forward")}
        </button>
      </div>
    </section>
  `;
}

function dashboardHomeArmingCaptureTargetStepDraft(actionType) {
  const action = dashboardHomeArmingActionMeta(actionType);

  if (!dashboardHomeArmingDraft) return null;

  const targetButtons = [...document.querySelectorAll('#dashboardHomeArmingActionBody [data-dashboard-action="toggle-home-arming-target"]')];

  if ((action.actionType === "device_on" || action.actionType === "recording") && targetButtons.length) {
    dashboardHomeArmingDraft.targetIDs = targetButtons
      .filter(item => item.classList.contains("active"))
      .map(item => String(item?.dataset?.choiceId || "").trim())
      .filter(Boolean);
  }

  const soundButton = document.querySelector('#dashboardHomeArmingActionBody [data-dashboard-action="select-home-arming-sound"].active');
  const soundInput = document.getElementById("dashboardHomeArmingSoundInput");

  if (action.actionType === "sound") {
    if (soundButton) {
      dashboardHomeArmingDraft.soundFile = String(soundButton?.dataset?.soundFile || "").trim();
    } else if (soundInput) {
      dashboardHomeArmingDraft.soundFile = String(soundInput.value || "").trim();
    }

    const volumeInput = document.getElementById("dashboardHomeArmingSoundVolumeInput");
    if (volumeInput) {
      dashboardHomeArmingDraft.soundVolumePercent = dashboardHomeArmingSoundVolumePercent(volumeInput.value);
    }
  }

  const titleInput = document.getElementById("dashboardHomeArmingTitleInput");
  const messageInput = document.getElementById("dashboardHomeArmingMessageInput");

  if (action.actionType === "notification") {
    if (targetButtons.length) {
      dashboardHomeArmingDraft.targetIDs = targetButtons
        .filter(item => item.classList.contains("active"))
        .map(item => String(item?.dataset?.choiceId || "").trim())
        .filter(Boolean);
    }

    if (titleInput) dashboardHomeArmingDraft.notificationTitle = String(titleInput.value || "").trim();
    if (messageInput) dashboardHomeArmingDraft.notificationMessage = String(messageInput.value || "").trim();
  }

  return dashboardHomeArmingDraft;
}

function dashboardHomeArmingCapturePostTriggerDraft(actionType) {
  const action = dashboardHomeArmingActionMeta(actionType);

  if (!dashboardHomeArmingDraft) return null;

  const timerInput = document.getElementById("dashboardHomeArmingTimerSecondsInput");
  const minimumVideoInput = document.getElementById("dashboardHomeArmingMinimumVideoSecondsInput");
  const cooldownInput = document.getElementById("dashboardHomeArmingCooldownSecondsInput");
  const autoOffInput = document.getElementById("dashboardHomeArmingAutoOffInput");
  const repeatInput = document.getElementById("dashboardHomeArmingRepeatInput");
  const retriggerInput = document.getElementById("dashboardHomeArmingRetriggerInput");

  dashboardHomeArmingDraft.post = dashboardHomeArmingDraft.post || {};

  if (timerInput) {
    dashboardHomeArmingDraft.post.timerSeconds = String(timerInput.value || "").trim();
  }

  if (minimumVideoInput) {
    dashboardHomeArmingDraft.post.minimumVideoSeconds = String(minimumVideoInput.value || "").trim();
  }

  if (cooldownInput) {
    dashboardHomeArmingDraft.post.cooldownSeconds = String(cooldownInput.value || "").trim();
  }

  if (autoOffInput) {
    dashboardHomeArmingDraft.post.autoOff = !!autoOffInput.checked;
  }

  if (repeatInput) {
    dashboardHomeArmingDraft.post.repeat = !!repeatInput.checked;
  }

  if (retriggerInput) {
    dashboardHomeArmingDraft.post.retrigger = !!retriggerInput.checked;
  }

  dashboardHomeArmingDraft.post.actionType = action.actionType;

  return dashboardHomeArmingDraft;
}

function renderDashboardHomeArmingTargetStep(mode, actionType) {
  const body = document.getElementById("dashboardHomeArmingActionBody");
  const modeMeta = dashboardHomeArmingModeMeta(dashboardHomeCleanArmMode(mode));
  const action = dashboardHomeArmingActionMeta(actionType);
  const draft = dashboardHomeArmingDraftFor(modeMeta.mode, action.actionType);
  const cameras = dashboardHomeArmingCameraTargets();
  const devices = dashboardHomeArmingDeviceTargets();
  const keyTargets = dashboardHomeArmingKeyTargets();

  dashboardHomeArmingSetActionHeader(modeMeta.mode);

  if (!body) return;

  if (action.actionType === "sound") {
    if (!String(draft.soundFile || "").trim()) {
      draft.soundFile = S.selectedSoundFile || dashboardHomeArmingDefaultSoundFile();
    }

    draft.soundVolumePercent = dashboardHomeArmingSoundVolumePercent(draft.soundVolumePercent ?? 100);
  }

  const targetSections = action.actionType === "device_on"
    ? dashboardHomeArmingGroupedChoiceHtml(devices, "device_on", draft.targetIDs, "devices")
    : action.actionType === "recording"
      ? dashboardHomeArmingGroupedChoiceHtml(cameras, "recording", draft.targetIDs, "cameras")
      : action.actionType === "sound"
        ? dashboardHomeArmingSoundChoiceHtml(draft.soundFile, draft.soundVolumePercent)
        : action.actionType === "notification"
          ? dashboardHomeArmingGroupedChoiceHtml(keyTargets, "notification", draft.targetIDs, "key clients")
          : "";

  dashboardHomeArmingWizardStep = "target";
  dashboardHomeArmingUpdateBreadcrumb("target", modeMeta.mode, action.actionType);

  body.innerHTML = `
    <section class="modal-section">
      <div class="modal-subtitle">
        ${action.actionType === "device_on" ? "Choose target(s) to power on" : ""}
        ${action.actionType === "sound" ? "Sound to play..." : ""}
        ${action.actionType === "notification" ? "Choose key client(s) to notify" : ""}
        ${action.actionType === "recording" ? "Choose camera(s) to record" : ""}
      </div>
    </section>

    ${targetSections}

    ${action.actionType === "notification" ? `
      <section class="modal-section dashboard-home-arming-form-section">
        <label class="settings-field-row">
          <span class="settings-field-label">Notification title</span>
          <input id="dashboardHomeArmingTitleInput" class="settings-input" type="text" placeholder="KotiBot Alert" value="${escAttr(draft.notificationTitle || "")}">
        </label>

        <label class="settings-field-row">
          <span class="settings-field-label">Notification message</span>
          <input id="dashboardHomeArmingMessageInput" class="settings-input" type="text" placeholder="A sensor or camera triggered." value="${escAttr(draft.notificationMessage || "")}">
        </label>
      </section>
    ` : ""}

    <section class="modal-section dashboard-home-arming-save-actions">
      <div class="client-menu-actions">
        <button class="client-menu-btn" type="button" data-dashboard-action="select-home-arming-action-type" data-mode="${escAttr(modeMeta.mode)}" data-action-type="${escAttr(action.actionType)}">
          ${window.dashboardIconHtml("arrow_back")}
          <span>Back</span>
        </button>

        <button
          class="client-menu-btn primary"
          type="button"
          data-dashboard-action="show-home-arming-post-trigger-step"
          data-dashboard-requires-step-selection="1"
          data-mode="${escAttr(modeMeta.mode)}"
          data-action-type="${escAttr(action.actionType)}"
          ${dashboardHomeArmingTargetStepComplete(draft) ? "" : "disabled"}
        >
          <span>Next</span>
          ${window.dashboardIconHtml("arrow_forward")}
        </button>
      </div>
    </section>
  `;
}

/*
 * All Page 4 numeric rules use this shared modal control so their layout,
 * icons, spacing, and stepping behavior cannot drift apart.
 */
function dashboardHomeArmingNumberControlHtml({
  inputID,
  label,
  value,
  min,
  max,
  step = 5
} = {}) {
  const safeInputID = escAttr(inputID);
  const safeLabel = escAttr(label);

  return `
    <div class="modal-inline-number-control">
      <label class="settings-field-label modal-inline-number-label" for="${safeInputID}">${safeLabel}</label>
      <input
        id="${safeInputID}"
        class="settings-input modal-inline-number-input"
        type="number"
        inputmode="numeric"
        min="${escAttr(min)}"
        max="${escAttr(max)}"
        step="${escAttr(step)}"
        value="${value}"
      >
      <span class="settings-field-label modal-inline-number-unit">Seconds</span>
      <span class="modal-inline-number-stepper">
        <button
          class="client-menu-btn modal-inline-number-step"
          type="button"
          title="Decrease ${safeLabel}"
          aria-label="Decrease ${safeLabel}"
          data-dashboard-action="step-home-arming-number"
          data-input-id="${safeInputID}"
          data-direction="-1"
        >
          ${window.dashboardIconHtml("chevron_down")}
        </button>
        <button
          class="client-menu-btn modal-inline-number-step"
          type="button"
          title="Increase ${safeLabel}"
          aria-label="Increase ${safeLabel}"
          data-dashboard-action="step-home-arming-number"
          data-input-id="${safeInputID}"
          data-direction="1"
        >
          ${window.dashboardIconHtml("chevron_up")}
        </button>
      </span>
    </div>
  `;
}

function dashboardHomeArmingTimerControlHtml(value, { min, max, step = 5 } = {}) {
  return dashboardHomeArmingNumberControlHtml({
    inputID: "dashboardHomeArmingTimerSecondsInput",
    label: "Timer",
    value,
    min,
    max,
    step
  });
}

/*
 * The clicked button supplies its input ID because a recording rule can contain
 * both the main timer and the minimum-video-duration control at the same time.
 */
window.stepDashboardHomeArmingNumber = function (inputID, direction) {
  const input = document.getElementById(String(inputID || "").trim());

  if (!input) return;

  const amount = Number(input.step) || 1;
  const minimum = Number(input.min);
  const maximum = Number(input.max);
  const current = Number(input.value);
  const next = (Number.isFinite(current) ? current : (Number.isFinite(minimum) ? minimum : 0))
    + (Number(direction) < 0 ? -amount : amount);
  const clamped = Math.min(
    Number.isFinite(maximum) ? maximum : next,
    Math.max(Number.isFinite(minimum) ? minimum : next, next)
  );

  input.value = String(clamped);
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.focus({ preventScroll: true });
};

function renderDashboardHomeArmingPostTriggerStep(mode, actionType) {
  const body = document.getElementById("dashboardHomeArmingActionBody");
  const modeMeta = dashboardHomeArmingModeMeta(dashboardHomeCleanArmMode(mode));
  const action = dashboardHomeArmingActionMeta(actionType);
  const draft = dashboardHomeArmingDraftFor(modeMeta.mode, action.actionType);
  const post = draft.post || {};

  dashboardHomeArmingSetActionHeader(modeMeta.mode);

  if (!body) return;

  dashboardHomeArmingWizardStep = "rules";
  dashboardHomeArmingUpdateBreadcrumb("rules", modeMeta.mode, action.actionType);

  const timerValue = escAttr(post.timerSeconds || (action.actionType === "sound" ? "15" : action.actionType === "recording" ? "30" : "60"));
  const minimumVideoValue = escAttr(post.minimumVideoSeconds || "15");
  const cooldownValue = escAttr(post.cooldownSeconds || "60");
  const autoOffChecked = post.autoOff === true ? " checked" : "";
  const repeatChecked = post.repeat === false ? "" : " checked";
  const retriggerChecked = post.retrigger === false ? "" : " checked";

  body.innerHTML = `
    <section class="modal-section dashboard-home-arming-form-section">
      <h2 class="modal-section-title">Post Trigger</h2>

      ${action.actionType === "device_on" ? `
        <label class="settings-check-row">
          <input id="dashboardHomeArmingAutoOffInput" type="checkbox"${autoOffChecked}>
          <span>Flip switch off when timer ends</span>
        </label>

        ${dashboardHomeArmingTimerControlHtml(timerValue, { min: 1, max: 86400 })}

        <label class="settings-check-row">
          <input id="dashboardHomeArmingRetriggerInput" type="checkbox"${retriggerChecked}>
          <span>Retrigger timer if the trigger fires again</span>
        </label>
      ` : ""}

      ${action.actionType === "sound" ? `
        ${dashboardHomeArmingTimerControlHtml(timerValue, { min: 1, max: 3600 })}

        <label class="settings-check-row">
          <input id="dashboardHomeArmingRepeatInput" type="checkbox"${repeatChecked}>
          <span>Repeat while trigger remains active</span>
        </label>
      ` : ""}

      ${action.actionType === "notification" ? `
        ${dashboardHomeArmingNumberControlHtml({
          inputID: "dashboardHomeArmingCooldownSecondsInput",
          label: "Cool-down",
          value: cooldownValue,
          min: 0,
          max: 86400
        })}
      ` : ""}

      ${action.actionType === "recording" ? `
        ${dashboardHomeArmingTimerControlHtml(timerValue, { min: 5, max: 3600 })}

        ${dashboardHomeArmingNumberControlHtml({
          inputID: "dashboardHomeArmingMinimumVideoSecondsInput",
          label: "Minimum video duration",
          value: minimumVideoValue,
          min: 5,
          max: 3600
        })}

        <label class="settings-check-row">
          <input id="dashboardHomeArmingRetriggerInput" type="checkbox"${retriggerChecked}>
          <span>Retrigger timer if the trigger fires again</span>
        </label>
      ` : ""}
    </section>

    <section class="modal-section dashboard-home-arming-save-actions">
      <div class="client-menu-actions">
        <button class="client-menu-btn" type="button" data-dashboard-action="show-home-arming-target-step" data-mode="${escAttr(modeMeta.mode)}" data-action-type="${escAttr(action.actionType)}">
          ${window.dashboardIconHtml("arrow_back")}
          <span>Back</span>
        </button>

        ${dashboardHomeArmingEditingAutomationID ? `
          <button class="client-menu-btn danger" type="button" data-dashboard-action="delete-device-automation">
            ${window.dashboardIconHtml("delete")}
            <span>Delete Automation</span>
          </button>
        ` : ""}

        <button class="client-menu-btn primary" type="button" data-dashboard-action="save-home-arming-route" data-mode="${escAttr(modeMeta.mode)}" data-action-type="${escAttr(action.actionType)}">
          ${window.dashboardIconHtml("save")}
          <span>${dashboardHomeArmingRouteScope === "automation" ? "Save Automation" : "Save Action"}</span>
        </button>
      </div>
    </section>
  `;
}

function dashboardHideParentModalForSubmodal(childModal, parentModalID) {
  if (!childModal) return;

  const parentModal = document.getElementById(parentModalID);

  if (parentModal && parentModal.hidden === false) {
    parentModal.hidden = true;
    childModal.dataset.returnModalId = parentModalID;
    return;
  }

  childModal.dataset.returnModalId = "";
}

function dashboardRestoreParentModalFromSubmodal(childModal) {
  const parentModalID = String(childModal?.dataset?.returnModalId || "").trim();

  if (childModal) {
    childModal.dataset.returnModalId = "";
  }

  if (!parentModalID) return false;

  const parentModal = document.getElementById(parentModalID);
  if (!parentModal) return false;

  parentModal.hidden = false;
  document.body.classList.add("modal-open");

  return true;
}

window.dashboardRestoreParentModalFromSubmodal =
  dashboardRestoreParentModalFromSubmodal;

window.showDashboardHomeArmingSettings = async function (mode) {
  window.ensureDashboardHomeArmingModalShells?.();
  closeAllMenus?.();

  dashboardHomeArmingSelectedMode = dashboardHomeCleanArmMode(mode || dashboardHomeCurrentArmMode());

  await Promise.all([dashboardHomeRefreshRoutes(), refreshWavData?.()]);
  renderDashboardHomeArmingSettings();

  const modal = document.getElementById("dashboardHomeArmingModal");
  if (!modal) return;

  dashboardHideParentModalForSubmodal(modal, "settingsModal");

  modal.hidden = false;
  document.body.classList.add("modal-open");
};

window.hideDashboardHomeArmingSettings = function () {
  const pickerModal = document.getElementById("dashboardHomeArmingActionModal");
  const modal = document.getElementById("dashboardHomeArmingModal");

  if (pickerModal) {
    pickerModal.hidden = true;
    pickerModal.dataset.returnModalId = "";
  }

  if (modal) modal.hidden = true;

  if (dashboardRestoreParentModalFromSubmodal(modal)) return;

  dashboardCloseModalOpenClassIfNeeded();
};

window.showDashboardHomeArmingActionPicker = function (mode, triggerDeviceIDs = "", triggerGroup = "", routeScope = "security") {
  window.ensureDashboardHomeArmingModalShells?.();
  dashboardHomeArmingDraft = null;
  dashboardHomeArmingEditingAutomationID = "";
  dashboardHomeArmingEditingDeviceID = "";
  dashboardHomeArmingRouteScope = routeScope === "automation" ? "automation" : "security";
  dashboardHomeArmingPendingSourceIDs = (Array.isArray(triggerDeviceIDs) ? triggerDeviceIDs : [triggerDeviceIDs])
    .map(deviceID => String(deviceID || "").trim())
    .filter(Boolean);
  dashboardHomeArmingPendingTriggerGroup = dashboardHomeArmingCleanTriggerGroup(triggerGroup);

  const contextChoices = dashboardHomeArmingTriggerChoiceIDsForDevice(
    dashboardHomeArmingPendingSourceIDs,
    dashboardHomeArmingPendingTriggerGroup
  );

  dashboardHomeArmingPendingTriggerIDs = contextChoices.length === 1 ? contextChoices : [];
  dashboardHomeArmingWizardStep = "response";
  renderDashboardHomeArmingActionPicker(mode);

  const modal = document.getElementById("dashboardHomeArmingActionModal");
  if (!modal) return;

  dashboardHideParentModalForSubmodal(modal, "dashboardHomeArmingModal");

  modal.hidden = false;
  document.body.classList.add("modal-open");
};

window.hideDashboardHomeArmingActionPicker = function () {
  const modal = document.getElementById("dashboardHomeArmingActionModal");
  if (modal) modal.hidden = true;

  if (dashboardRestoreParentModalFromSubmodal(modal)) return;

  dashboardCloseModalOpenClassIfNeeded();
};

window.selectDashboardHomeArmingActionType = function (button) {
  const mode = button?.dataset?.mode || dashboardHomeArmingSelectedMode;
  const actionType = button?.dataset?.actionType || "sound";

  dashboardHomeArmingDraftFor(mode, actionType);
  renderDashboardHomeArmingTriggerStep(mode, actionType);
};

window.toggleDashboardHomeArmingTrigger = function (button) {
  const choiceID = String(button?.dataset?.choiceId || "").trim();

  if (!choiceID || !dashboardHomeArmingDraft) return;

  dashboardHomeArmingCaptureEnvironmentThresholds();

  const set = new Set(dashboardHomeArmingDraft.triggerIDs || []);

  if (set.has(choiceID)) set.delete(choiceID);
  else set.add(choiceID);

  dashboardHomeArmingDraft.triggerIDs = [...set];
  dashboardHomeArmingEnsureEnvironmentThresholds(dashboardHomeArmingDraft);
  renderDashboardHomeArmingTriggerStep(
    dashboardHomeArmingDraft.mode,
    dashboardHomeArmingDraft.actionType
  );
};

window.updateDashboardHomeArmingEnvironmentThreshold = function () {
  dashboardHomeArmingCaptureEnvironmentThresholds();
  dashboardHomeArmingUpdateStepActionButtons("trigger");
};

window.selectDashboardHomeArmingSound = function (button) {
  const soundFile = String(button?.dataset?.soundFile || "").trim();

  if (!soundFile || !dashboardHomeArmingDraft) return;

  dashboardHomeArmingDraft.soundFile = soundFile;

  document
    .querySelectorAll('#dashboardHomeArmingActionBody [data-dashboard-action="select-home-arming-sound"]')
    .forEach(item => {
      const active = item === button;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", active ? "true" : "false");
    });

  dashboardHomeArmingUpdateBreadcrumb("target", dashboardHomeArmingDraft.mode, dashboardHomeArmingDraft.actionType);
  dashboardHomeArmingUpdateStepActionButtons("target");
};

window.toggleDashboardHomeArmingTarget = function (button) {
  const choiceID = String(button?.dataset?.choiceId || "").trim();

  if (!choiceID || !dashboardHomeArmingDraft) return;

  const set = new Set(dashboardHomeArmingDraft.targetIDs || []);

  if (set.has(choiceID)) set.delete(choiceID);
  else set.add(choiceID);

  dashboardHomeArmingDraft.targetIDs = [...set];
  const active = set.has(choiceID);
  button.classList.toggle("active", active);
  button.setAttribute("aria-pressed", active ? "true" : "false");
  dashboardHomeArmingUpdateBreadcrumb("target", dashboardHomeArmingDraft.mode, dashboardHomeArmingDraft.actionType);
  dashboardHomeArmingUpdateStepActionButtons("target");
};

window.updateDashboardHomeArmingSoundVolume = function () {
  const input = document.getElementById("dashboardHomeArmingSoundVolumeInput");
  const label = document.getElementById("dashboardHomeArmingSoundVolumeValue");
  const volumePercent = dashboardHomeArmingSoundVolumePercent(input?.value ?? 100);

  if (label) label.textContent = `${volumePercent}%`;

  if (dashboardHomeArmingDraft) {
    dashboardHomeArmingDraft.soundVolumePercent = volumePercent;
  }
};

window.testDashboardHomeArmingSound = async function () {
  dashboardHomeArmingCaptureTargetStepDraft("sound");

  const filename = String(dashboardHomeArmingDraft?.soundFile || "").trim();
  const volumePercent = dashboardHomeArmingSoundVolumePercent(dashboardHomeArmingDraft?.soundVolumePercent ?? 100);

  if (!filename) return;

  await dashboardFetch("/api/test-sound", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename,
      volume: volumePercent,
      volume_percent: volumePercent
    })
  }).then(r => r.json());
};

window.showDashboardHomeArmingBreadcrumbStep = function (button) {
  if (button?.disabled) return;

  dashboardHomeArmingCaptureCurrentStepDraft();

  const step = String(button?.dataset?.step || "response").trim();
  const mode = dashboardHomeCleanArmMode(button?.dataset?.mode || dashboardHomeArmingDraft?.mode || dashboardHomeArmingSelectedMode);
  const actionType = dashboardHomeArmingActionMeta(button?.dataset?.actionType || dashboardHomeArmingDraft?.actionType).actionType;
  const draft = dashboardHomeArmingDraft;

  if (step === "response") {
    renderDashboardHomeArmingActionPicker(mode);
    return;
  }

  if (!draft?.actionType) return;

  if (step === "trigger") {
    renderDashboardHomeArmingTriggerStep(mode, actionType);
    return;
  }

  if (step === "target") {
    if (!(draft.triggerIDs || []).length) return;

    renderDashboardHomeArmingTargetStep(mode, actionType);
    return;
  }

  if (step === "rules") {
    if (!(draft.triggerIDs || []).length || !dashboardHomeArmingTargetStepComplete(draft)) return;

    renderDashboardHomeArmingPostTriggerStep(mode, actionType);
  }
};

window.showDashboardHomeArmingTargetStep = function (button) {
  const mode = dashboardHomeCleanArmMode(button?.dataset?.mode || dashboardHomeArmingSelectedMode);
  const actionType = dashboardHomeArmingActionMeta(button?.dataset?.actionType).actionType;
  const draft = dashboardHomeArmingDraftFor(mode, actionType);
  dashboardHomeArmingCaptureEnvironmentThresholds();
  const triggerButtons = [...document.querySelectorAll('#dashboardHomeArmingActionBody [data-dashboard-action="toggle-home-arming-trigger"]')];

  if (triggerButtons.length) {
    draft.triggerIDs = triggerButtons
      .filter(item => item.classList.contains("active"))
      .map(item => String(item?.dataset?.choiceId || "").trim())
      .filter(Boolean);
  } else {
    dashboardHomeArmingCapturePostTriggerDraft(actionType);
  }

  if (!draft.triggerIDs.length || !dashboardHomeArmingEnvironmentThresholdsComplete(draft)) return;

  renderDashboardHomeArmingTargetStep(mode, actionType);
};

window.showDashboardHomeArmingPostTriggerStep = function (button) {
  const mode = dashboardHomeCleanArmMode(button?.dataset?.mode || dashboardHomeArmingSelectedMode);
  const actionType = dashboardHomeArmingActionMeta(button?.dataset?.actionType).actionType;
  const draft = dashboardHomeArmingDraftFor(mode, actionType);

  dashboardHomeArmingCaptureTargetStepDraft(actionType);

  if ((actionType === "device_on" || actionType === "recording") && !(draft.targetIDs || []).length) return;
  if (actionType === "notification" && !(draft.targetIDs || []).length) return;
  if (actionType === "sound" && !String(draft.soundFile || "").trim()) return;

  renderDashboardHomeArmingPostTriggerStep(mode, actionType);
};

function dashboardHomeArmingTriggerPayload(mode, actionType, triggerID) {
  const [sourceDeviceID, trigger] = String(triggerID || "|").split("|");
  const fromOutput = trigger === "door_open"
    ? "open"
    : trigger === "door_close"
      ? "closed"
      : trigger;

  if (!sourceDeviceID || !trigger) return null;

  const threshold = dashboardHomeArmingTriggerIsEnvironment(trigger)
    ? Number(dashboardHomeArmingDraft?.environmentThresholds?.[triggerID])
    : null;

  return {
    from_deviceID: sourceDeviceID,
    sourceDeviceID,
    from_output: fromOutput,
    trigger,
    ...(Number.isFinite(threshold) ? {
      threshold,
      trigger_threshold: threshold,
      threshold_unit: trigger.startsWith("temperature_") ? "c" : "percent"
    } : {}),
    ...(dashboardHomeArmingRouteScope === "security" ? { arm_states: [mode] } : {}),
    action_type: actionType,
    to_kind: actionType
  };
}

window.saveDashboardHomeArmingRoute = async function (button) {
  const mode = dashboardHomeCleanArmMode(button?.dataset?.mode || dashboardHomeArmingSelectedMode);
  const actionType = dashboardHomeArmingActionMeta(button?.dataset?.actionType).actionType;
  const draft = dashboardHomeArmingDraftFor(mode, actionType);
  const triggerIDs = draft.triggerIDs || [];
  const payloads = [];

  dashboardHomeArmingCaptureTargetStepDraft(actionType);
  dashboardHomeArmingCapturePostTriggerDraft(actionType);

  const post = draft.post || {};

  if (!triggerIDs.length) return;

  if (actionType === "device_on") {
    if (!draft.targetIDs.length) return;

    triggerIDs.forEach(triggerID => {
      const base = dashboardHomeArmingTriggerPayload(mode, actionType, triggerID);
      if (!base) return;

      draft.targetIDs.forEach(targetID => {
        const target = dashboardHomeArmingDeviceTargetFromID(targetID);
        const targetDeviceID = String(target?.targetDeviceID || targetID.split("|")[0] || "").trim();
        const targetActionType = dashboardHomeArmingPowerTargetActionType(targetID);

        if (!targetID || !targetDeviceID) return;
        if (
          dashboardHomeArmingActionUsesSourceCamera(targetActionType) &&
          String(base.from_deviceID || "") !== targetDeviceID
        ) {
          return;
        }

        const payload = {
          ...base,
          action_type: targetActionType,
          to_kind: targetActionType,
          to_deviceID: targetDeviceID,
          targetDeviceID,
          to_input: targetID,
          targetID
        };

        Object.assign(payload, {
          power_action: "on",
          auto_off: !!post.autoOff,
          auto_off_seconds: post.timerSeconds || "",
          timer_seconds: post.timerSeconds || "",
          retrigger: post.retrigger !== false
        });

        payloads.push(payload);
      });
    });
  }

  if (actionType === "sound") {
    const filename = String(draft.soundFile || "").trim();
    const soundVolumePercent = dashboardHomeArmingSoundVolumePercent(draft.soundVolumePercent ?? 100);

    if (!filename) return;

    triggerIDs.forEach(triggerID => {
      const base = dashboardHomeArmingTriggerPayload(mode, actionType, triggerID);
      if (!base) return;

      payloads.push({
        ...base,
        filename,
        sound: filename,
        to_input: filename,
        sound_volume: soundVolumePercent,
        volume_percent: soundVolumePercent,
        repeat: post.repeat !== false,
        repeat_seconds: post.timerSeconds || "",
        timer_seconds: post.timerSeconds || ""
      });
    });
  }

  if (actionType === "notification") {
    const titleValue = String(draft.notificationTitle || "KotiBot Alert").trim();
    const message = String(draft.notificationMessage || "A sensor or camera triggered.").trim();
    const title = titleValue || "KotiBot Alert";
    const notificationTargets = (draft.targetIDs || [])
      .map(targetID => String(targetID || "").trim())
      .filter(Boolean);

    if (!notificationTargets.length) return;

    triggerIDs.forEach(triggerID => {
      const base = dashboardHomeArmingTriggerPayload(mode, actionType, triggerID);
      if (!base) return;

      notificationTargets.forEach(targetKeyDeviceID => {
        payloads.push({
          ...base,
          to_deviceID: targetKeyDeviceID,
          targetDeviceID: targetKeyDeviceID,
          targetID: targetKeyDeviceID,
          target_key_deviceID: targetKeyDeviceID,
          title,
          message,
          body: message,
          to_input: message,
          cooldown_seconds: post.cooldownSeconds || ""
        });
      });
    });
  }

  if (actionType === "recording") {
    if (!draft.targetIDs.length) return;

    triggerIDs.forEach(triggerID => {
      const base = dashboardHomeArmingTriggerPayload(mode, actionType, triggerID);
      if (!base) return;

      draft.targetIDs.forEach(targetID => {
        payloads.push({
          ...base,
          to_deviceID: targetID,
          targetDeviceID: targetID,
          duration_seconds: post.timerSeconds || "30",
          timer_seconds: post.timerSeconds || "30",
          minimum_duration_seconds: dashboardHomeArmingRecordingMinimumSeconds(post.minimumVideoSeconds || "15"),
          min_duration_seconds: dashboardHomeArmingRecordingMinimumSeconds(post.minimumVideoSeconds || "15"),
          retrigger: post.retrigger !== false
        });
      });
    });
  }

  if (!payloads.length) return;

  const routeEndpoint = dashboardHomeArmingRouteEndpoint();

  if (dashboardHomeArmingEditingAutomationID) {
    const res = await dashboardFetch(routeEndpoint, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        automationID: dashboardHomeArmingEditingAutomationID,
        routes: payloads
      })
    });
    const data = await res.json();

    if (!res.ok || data.ok === false) {
      throw new Error(data.error || "Unable to update automation");
    }
  } else {
    const res = await dashboardFetch(routeEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ routes: payloads })
    });
    const data = await res.json();

    if (!res.ok || data.ok === false) {
      throw new Error(data.error || "Unable to save automation");
    }
  }

  if (dashboardHomeArmingRouteScope === "security") {
    await dashboardHomeRefreshRoutes();
    dashboardHomeArmingSelectedMode = mode;
    renderDashboardHomeArmingSettings();
  }

  if (dashboardHomeArmingRouteScope === "automation") {
    const returnDeviceID = dashboardHomeArmingEditingDeviceID || String(payloads[0]?.from_deviceID || "").trim();
    await dashboardReturnToDeviceAutomationSettings(returnDeviceID);
    return;
  }

  dashboardHomeArmingDraft = null;
  hideDashboardHomeArmingActionPicker();
};

window.deleteDashboardDeviceAutomation = async function () {
  const automationID = dashboardHomeArmingEditingAutomationID;
  const deviceID = dashboardHomeArmingEditingDeviceID;

  if (!automationID || !confirm("Delete this automation?")) return;

  const res = await dashboardFetch(dashboardHomeArmingRouteEndpoint(), {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ automationID })
  });
  const data = await res.json();

  if (!res.ok || data.ok === false) {
    throw new Error(data.error || "Unable to delete automation");
  }

  await dashboardReturnToDeviceAutomationSettings(deviceID);
};

window.deleteDashboardHomeArmingRoute = async function (button) {
  const index = Number(button?.dataset?.routeIndex);
  const route = dashboardHomeArmingRenderedRoutes[index];

  if (!route) return;

  await dashboardFetch("/api/routes", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(route)
  }).then(r => r.json());

  await dashboardHomeRefreshRoutes();
  renderDashboardHomeArmingSettings();
};

let dashboardHomeQueuedLightingMode = "";
let dashboardHomeLightingModeRunPromise = null;

async function dashboardHomeDrainLightingModeQueue() {
  let firstError = null;

  while (dashboardHomeQueuedLightingMode) {
    const nextMode = dashboardHomeQueuedLightingMode;
    dashboardHomeQueuedLightingMode = "";

    try {
      await runDashboardHomeLightingMode(nextMode);
    } catch (err) {
      firstError ||= err;
      console.warn(`[home scene] ${nextMode} failed`, err);
    }
  }

  if (firstError) throw firstError;
}

window.setDashboardHomeLightMode = function (mode) {
  const cleanMode = dashboardHomeCleanLightingMode(mode);

  dashboardHomeQueuedLightingMode = cleanMode;
  dashboardHomeSetActiveLightingModeLocally(cleanMode);

  if (!dashboardHomeLightingModeRunPromise) {
    dashboardHomeLightingModeRunPromise = dashboardHomeDrainLightingModeQueue()
      .finally(() => {
        dashboardHomeLightingModeRunPromise = null;
      });
  }

  return dashboardHomeLightingModeRunPromise;
};

const DASHBOARD_HOME_LIGHTING_MODES = [
  {
    mode: "day",
    label: "Day",
    icon: "morning",
    defaultTitle: "Raise Home Lights",
    defaultSubtitle: "Included home lights · No power-on",
    defaultType: "lighting-mode"
  },
  {
    mode: "evening",
    label: "Evening",
    icon: "evening",
    defaultTitle: "Dim Home Lights",
    defaultSubtitle: "Included home lights · No power-on",
    defaultType: "lighting-mode"
  },
  {
    mode: "night",
    label: "Night",
    icon: "bedtime",
    defaultTitle: "Switch Devices Off",
    defaultSubtitle: "Included room-power devices",
    defaultType: "devices-off"
  },
  {
    mode: "away",
    label: "Away",
    icon: "directions_walk",
    defaultTitle: "Switch Devices Off",
    defaultSubtitle: "Included room-power devices",
    defaultType: "devices-off"
  }
];
const DASHBOARD_HOME_LIGHTING_DEFAULTS = DASHBOARD_HOME_LIGHTING_MODES.reduce((map, mode) => {
  map[mode.mode] = [{
    id: `default-${mode.mode}`,
    type: mode.defaultType,
    mode: mode.mode,
    label: mode.defaultTitle,
    subtitle: mode.defaultSubtitle,
    builtin: true
  }];

  return map;
}, {});

let dashboardHomeLightingSelectedMode = dashboardHomeCurrentLightingMode();

function cloneDashboardHomeLightingDefaults(mode) {
  return (DASHBOARD_HOME_LIGHTING_DEFAULTS[mode] || [])
    .map(automation => ({ ...automation }));
}

function readDashboardHomeLightingAutomations() {
  return DASHBOARD_HOME_LIGHTING_MODES.reduce((map, mode) => {
    map[mode.mode] = cloneDashboardHomeLightingDefaults(mode.mode);

    return map;
  }, {});
}

function writeDashboardHomeLightingAutomations() {}

function dashboardHomeLightingModeMeta(mode) {
  return DASHBOARD_HOME_LIGHTING_MODES.find(item => item.mode === mode) || DASHBOARD_HOME_LIGHTING_MODES[0];
}

function dashboardHomeClientRoom(client) {
  return String(client?.zone_name || client?.room || client?.room_name || client?.zone || "Unassigned").trim() || "Unassigned";
}

function dashboardHomeClientName(client) {
  return String(client?.clientName || client?.tapo_alias || client?.name || client?.deviceID || "Light").trim() || "Light";
}

function dashboardHomeLightingModeConfig() {
  const state = window.TAPO_LIGHTING_STATE || {};

  return state.modeConfig && typeof state.modeConfig === "object"
    ? state.modeConfig
    : {};
}

async function writeDashboardHomeLightingModeConfig(config) {
  const state = window.TAPO_LIGHTING_STATE || {};
  const schemes = state.schemes && typeof state.schemes === "object" ? state.schemes : {};
  const activeSchemes = state.activeSchemes && typeof state.activeSchemes === "object" ? state.activeSchemes : {};
  const modeConfig = config && typeof config === "object" ? config : {};

  state.schemes = schemes;
  state.activeSchemes = activeSchemes;
  state.modeConfig = modeConfig;

  const res = await dashboardFetch("/api/tapo/lighting-state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ schemes, activeSchemes, modeConfig })
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

  state.schemes = data.schemes && typeof data.schemes === "object" ? data.schemes : schemes;
  state.activeSchemes = data.activeSchemes && typeof data.activeSchemes === "object" ? data.activeSchemes : activeSchemes;
  state.modeConfig = data.modeConfig && typeof data.modeConfig === "object" ? data.modeConfig : modeConfig;

  return state.modeConfig;
}

function dashboardHomeLightingTargetKey(type, value) {
  const cleanValue = String(value || "").trim();
  return cleanValue ? `${type}:${cleanValue}` : "";
}

function dashboardHomeLightingChoiceIsPreset(choice) {
  return ["day", "evening", "movie", "nightlight"].includes(String(choice || ""));
}

function dashboardHomeLightingPresetMeta(choice) {
  const cleanChoice = String(choice || "").trim();

  if (cleanChoice === "day") {
    return { choice: "day", label: "Day", icon: "wb_sunny" };
  }

  if (cleanChoice === "evening") {
    return { choice: "evening", label: "Evening", icon: "wb_twilight" };
  }

  if (cleanChoice === "movie") {
    return { choice: "movie", label: "Movie", icon: "movie" };
  }

  if (cleanChoice === "nightlight") {
    return { choice: "nightlight", label: "Nightlight", icon: "nightlight" };
  }

  return { choice: "ignore", label: "Ignore", icon: "block" };
}

function dashboardHomeLightingPowerMeta(choice) {
  const cleanChoice = String(choice || "").trim();

  if (cleanChoice === "off") {
    return {
      choice: "off",
      label: "Off",
      icon: "toggle_on",
      iconClass: "dashboard-home-lighting-switch-off"
    };
  }

  if (cleanChoice === "on") {
    return {
      choice: "on",
      label: "On",
      icon: "toggle_on",
      iconClass: "dashboard-home-lighting-switch-on"
    };
  }

  return { choice: "ignore", label: "Ignore", icon: "block", iconClass: "" };
}

function dashboardHomeLightingClientSupportsPreset(client) {
  return dashboardHomeIsLight(client) && client?.tapo_supports_brightness !== false;
}

function dashboardHomeIsPowerLightingClient(client) {
  if (!client?.provisioned || !dashboardHomeHasTapoRole(client)) return false;

  const kind = String(client?.tapo_kind || client?.tapo_device_type || "").toLowerCase();
  const supportsPower = dashboardHomeBool(client?.tapo_supports_power ?? client?.supports_power);

  if (client?.tapo_dashboard_section === "camera" || kind === "camera" || kind === "vacuum") return false;
  if (["bulb", "lightstrip", "plug", "outlet", "outlet_extender"].includes(kind)) return supportsPower !== false;

  return supportsPower === true;
}

function dashboardHomeLightingPowerClients() {
  return (S.currentClients || [])
    .filter(dashboardHomeIsPowerLightingClient)
    .sort((a, b) => (
      dashboardHomeClientRoom(a).localeCompare(dashboardHomeClientRoom(b)) ||
      dashboardHomeClientName(a).localeCompare(dashboardHomeClientName(b))
    ));
}

function dashboardHomeLightingIncludedPowerClients() {
  return dashboardHomeLightingPowerClients()
    .filter(client => dashboardHomeRoomPowerEnabled(client, dashboardHomeIsLight(client)));
}

function dashboardHomeLightingIndividualPowerClients() {
  return dashboardHomeLightingPowerClients()
    .filter(client => !dashboardHomeRoomPowerEnabled(client, dashboardHomeIsLight(client)));
}

function dashboardHomeLightingGroupedPowerClients() {
  return dashboardHomeLightingIncludedPowerClients().reduce((map, client) => {
    const room = dashboardHomeClientRoom(client);

    if (!map.has(room)) map.set(room, []);
    map.get(room).push(client);

    return map;
  }, new Map());
}

function dashboardHomeLightingGroupedIndividualPowerClients() {
  return dashboardHomeLightingIndividualPowerClients().reduce((map, client) => {
    const room = dashboardHomeClientRoom(client);

    if (!map.has(room)) map.set(room, []);
    map.get(room).push(client);

    return map;
  }, new Map());
}

function dashboardHomeLightingModeRooms(roomSwitchGroups, individualGroups) {
  return Array.from(new Set([
    ...Array.from(roomSwitchGroups.keys()),
    ...Array.from(individualGroups.keys())
  ])).sort((a, b) => a.localeCompare(b));
}

function dashboardHomeLightingStoredChoice(mode, key) {
  const config = dashboardHomeLightingModeConfig();
  const modeConfig = config[dashboardHomeCleanLightingMode(mode)] || {};

  if (!Object.prototype.hasOwnProperty.call(modeConfig, key)) return "";

  const value = modeConfig[key];

  if (value && typeof value === "object") return value;

  return String(value || "").trim();
}

function dashboardHomeLightingChoiceProfile(value) {
  if (value && typeof value === "object") {
    const power = ["off", "on"].includes(String(value.power || "").trim())
      ? String(value.power || "").trim()
      : "";
    const preset = dashboardHomeLightingChoiceIsPreset(value.preset)
      ? String(value.preset || "").trim()
      : "";

    if (power === "off") return { power: "off", preset: "" };

    return { power, preset };
  }

  const cleanValue = String(value || "").trim();

  if (cleanValue === "off" || cleanValue === "on") {
    return { power: cleanValue, preset: "" };
  }

  if (dashboardHomeLightingChoiceIsPreset(cleanValue)) {
    return { power: "", preset: cleanValue };
  }

  return { power: "", preset: "" };
}

function dashboardHomeLightingChoiceProfileHas(profile, choice) {
  const cleanChoice = String(choice || "").trim();
  const cleanProfile = dashboardHomeLightingChoiceProfile(profile);

  if (cleanChoice === "off" || cleanChoice === "on") {
    return cleanProfile.power === cleanChoice;
  }

  if (dashboardHomeLightingChoiceIsPreset(cleanChoice)) {
    return cleanProfile.preset === cleanChoice;
  }

  return false;
}

function dashboardHomeLightingChoiceProfileValue(profile) {
  const cleanProfile = dashboardHomeLightingChoiceProfile(profile);

  if (cleanProfile.power === "off") return "off";

  if (cleanProfile.power === "on" && cleanProfile.preset) {
    return { power: "on", preset: cleanProfile.preset };
  }

  if (cleanProfile.power === "on") return "on";
  if (cleanProfile.preset) return cleanProfile.preset;

  return "ignore";
}

function dashboardHomeLightingDefaultRoomChoice(mode, clients = []) {
  const cleanMode = dashboardHomeCleanLightingMode(mode);
  const supportsPreset = clients.some(dashboardHomeLightingClientSupportsPreset);

  if ((cleanMode === "day" || cleanMode === "evening") && supportsPreset) {
    return cleanMode;
  }

  if (cleanMode === "night" || cleanMode === "away") {
    return "off";
  }

  return "ignore";
}

function dashboardHomeLightingDefaultDeviceChoice(mode, client, roomChoice = "") {
  const cleanMode = dashboardHomeCleanLightingMode(mode);
  const roomProfile = dashboardHomeLightingChoiceProfile(roomChoice);

  if (roomProfile.preset) {
    return dashboardHomeLightingClientSupportsPreset(client) ? roomProfile.preset : "ignore";
  }

  if (roomProfile.power === "off") return "off";

  if ((cleanMode === "day" || cleanMode === "evening") && dashboardHomeLightingClientSupportsPreset(client)) {
    return cleanMode;
  }

  if (cleanMode === "night" || cleanMode === "away") {
    return "off";
  }

  return "ignore";
}

function dashboardHomeLightingChoiceForRoom(mode, room, clients = []) {
  const key = dashboardHomeLightingTargetKey("room", room);
  return dashboardHomeLightingStoredChoice(mode, key) || dashboardHomeLightingDefaultRoomChoice(mode, clients);
}

function dashboardHomeLightingChoiceForClient(mode, client, roomChoice = "") {
  const key = dashboardHomeLightingTargetKey("device", client?.deviceID || "");
  return dashboardHomeLightingStoredChoice(mode, key) || dashboardHomeLightingDefaultDeviceChoice(mode, client, roomChoice);
}

function dashboardHomeLightingChoiceButtonsHtml({ mode, targetType, targetKey, activeChoice, supportsPreset }) {
  const activeProfile = dashboardHomeLightingChoiceProfile(activeChoice);
  const choices = [
    dashboardHomeLightingPowerMeta("off"),
    dashboardHomeLightingPowerMeta("on"),
    ...(supportsPreset ? ["day", "evening", "movie", "nightlight"].map(dashboardHomeLightingPresetMeta) : [])
  ];

  return `
    <div class="dashboard-home-lighting-choice-list ${supportsPreset ? "has-presets" : ""}">
      ${choices.map(choice => `
        <button
          class="client-menu-btn dashboard-home-lighting-choice-btn ${dashboardHomeLightingChoiceProfileHas(activeProfile, choice.choice) ? "active" : ""}"
          type="button"
          aria-label="${escAttr(choice.label)}"
          title="${escAttr(choice.label)}"
          data-dashboard-action="set-home-lighting-mode-choice"
          data-mode="${escAttr(dashboardHomeCleanLightingMode(mode))}"
          data-target-type="${escAttr(targetType)}"
          data-target-key="${escAttr(targetKey)}"
          data-choice="${escAttr(choice.choice)}"
        >
          ${window.dashboardIconHtml(choice.icon, `dashboard-home-lighting-choice-icon ${choice.iconClass || ""}`)}
        </button>
      `).join("")}
    </div>
  `;
}

function dashboardHomeResolveTapoCommandPayload(payload = {}) {
  const deviceID = String(payload.deviceID || "").trim();
  const client = (S.currentClients || []).find(item => String(item?.deviceID || "") === deviceID);

  if (!client?.tapo_parent_device_id) return payload;

  const childID = String(client.tapo_child_id || "").trim();
  const action = childID && payload.action === "on"
    ? "child_on"
    : childID && payload.action === "off"
      ? "child_off"
      : payload.action;

  return {
    ...payload,
    deviceID: String(client.tapo_parent_device_id || "").trim(),
    action,
    value: childID
      ? {
        ...(payload.value && typeof payload.value === "object" ? payload.value : {}),
        child_id: childID,
        position: client.tapo_child_position ?? "",
        child_index: client.tapo_child_index ?? ""
      }
      : payload.value
  };
}

function dashboardHomeHasTapoRole(client) {
  const roles = Array.isArray(client?.clientRole)
    ? client.clientRole
    : String(client?.clientRole || "").split(",");

  return roles
    .map(role => String(role || "").trim().toUpperCase())
    .includes("TAPO");
}

function dashboardHomeIsLight(client) {
  const kind = String(client?.tapo_kind || client?.tapo_device_type || "").toLowerCase();

  return dashboardHomeHasTapoRole(client) && (
    client?.tapo_is_bulb ||
    kind === "bulb" ||
    kind === "lightstrip"
  );
}

function dashboardHomeRoomPowerEnabled(client, defaultEnabled = false) {
  const raw = client?.tapo_room_power;

  if (raw === undefined || raw === null || raw === "") return defaultEnabled;

  return (
    raw === true ||
    raw === 1 ||
    String(raw || "").toLowerCase() === "true" ||
    String(raw || "").toLowerCase() === "1" ||
    String(raw || "").toLowerCase() === "yes" ||
    String(raw || "").toLowerCase() === "on"
  );
}

function dashboardHomeAllLightClients() {
  return (S.currentClients || [])
    .filter(client => client?.provisioned)
    .filter(dashboardHomeIsLight)
    .sort((a, b) => (
      dashboardHomeClientRoom(a).localeCompare(dashboardHomeClientRoom(b)) ||
      dashboardHomeClientName(a).localeCompare(dashboardHomeClientName(b))
    ));
}

function dashboardHomeIncludedLightClients() {
  return dashboardHomeAllLightClients()
    .filter(client => dashboardHomeRoomPowerEnabled(client, true));
}

function dashboardHomeRoomPowerTargets() {
  const targets = [];

  (S.currentClients || [])
    .filter(client => client?.provisioned)
    .filter(dashboardHomeHasTapoRole)
    .forEach(client => {
      const deviceID = client.deviceID || "";
      if (!deviceID) return;

      if (dashboardHomeIsLight(client)) {
        if (dashboardHomeRoomPowerEnabled(client, true)) {
          targets.push({ deviceID });
        }
        return;
      }

      const children = Array.isArray(client.tapo_children)
        ? client.tapo_children
        : Array.isArray(client.children)
          ? client.children
          : [];
      const childMap = client.tapo_room_power_children || client.tapoRoomPowerChildren || null;

      if (childMap && typeof childMap === "object") {
        children.forEach((child, index) => {
          const childID = String(child?.id ?? child?.child_id ?? child?.childId ?? "").trim();
          const childEnabled = (
            childMap[childID] === true ||
            childMap[childID] === 1 ||
            String(childMap[childID] || "").toLowerCase() === "true" ||
            String(childMap[childID] || "").toLowerCase() === "1" ||
            String(childMap[childID] || "").toLowerCase() === "yes" ||
            String(childMap[childID] || "").toLowerCase() === "on"
          );

          if (!childID || !childEnabled) return;

          targets.push({
            deviceID,
            action: "child_off",
            value: {
              child_id: childID,
              position: child?.position ?? "",
              child_index: child?.cli_index ?? child?.child_index ?? index
            }
          });
        });
        return;
      }

      if (!dashboardHomeRoomPowerEnabled(client, false)) return;

      targets.push({ deviceID });
    });

  return targets;
}

function dashboardHomeLightingAutomationTargetIDs(automation) {
  if (automation.allLights !== false) {
    return dashboardHomeAllLightClients().map(client => client.deviceID).filter(Boolean);
  }

  const available = new Set(dashboardHomeAllLightClients().map(client => client.deviceID).filter(Boolean));

  return (automation.targetDeviceIDs || [])
    .map(deviceID => String(deviceID || "").trim())
    .filter(deviceID => deviceID && available.has(deviceID));
}

function dashboardHomeBool(value) {
  if (value === true || value === 1) return true;
  if (value === false || value === 0) return false;

  const clean = String(value ?? "").trim().toLowerCase();
  if (["true", "1", "yes", "on"].includes(clean)) return true;
  if (["false", "0", "no", "off"].includes(clean)) return false;

  return null;
}

function dashboardHomeClientIsPoweredOn(client) {
  return dashboardHomeBool(client?.tapo_is_on ?? client?.is_on ?? client?.device_on ?? client?.state) === true;
}

function dashboardHomeDeviceIsPoweredOn(deviceID) {
  const id = String(deviceID || "").trim();
  if (!id) return false;

  const client = (S.currentClients || []).find(item => String(item?.deviceID || "") === id);
  return dashboardHomeClientIsPoweredOn(client);
}

function dashboardHomeLightingAutomationSubtitle(automation) {
  return automation?.subtitle || dashboardHomeLightingModeMeta(automation?.mode).defaultSubtitle || "";
}

function dashboardHomeLightingAutomationTitle(automation) {
  return automation?.label || dashboardHomeLightingModeMeta(automation?.mode).defaultTitle || "Preset";
}

function dashboardHomeLightingAutomationIcon(automation) {
  return dashboardHomeLightingModeMeta(automation.mode).icon;
}

function renderDashboardHomeLightingSettings() {
  const body = document.getElementById("dashboardHomeLightingModalBody");
  if (!body) return;

  const selectedMode = dashboardHomeCleanLightingMode(dashboardHomeLightingSelectedMode);
  const selectedMeta = dashboardHomeLightingModeMeta(selectedMode);
  const grouped = dashboardHomeLightingGroupedPowerClients();
  const groupedDevices = dashboardHomeLightingGroupedIndividualPowerClients();
  const rooms = dashboardHomeLightingModeRooms(grouped, groupedDevices);

  body.innerHTML = `
    <section class="modal-section dashboard-home-lighting-states-section">
      <div class="dashboard-home-arming-state-tabs dashboard-home-light-row dashboard-home-lighting-state-tabs">
        ${DASHBOARD_HOME_LIGHTING_MODES.map(mode => `
          <button
            class="settings-item dashboard-home-light-btn dashboard-home-arming-state-btn ${mode.mode === selectedMode ? "active" : ""}"
            type="button"
            data-dashboard-action="select-home-lighting-settings-mode"
            data-mode="${escAttr(mode.mode)}"
          >
            <span class="ui-icon-circle dashboard-home-mode-circle">${window.dashboardIconHtml(mode.icon, "dashboard-home-mode-icon")}</span>
            <span>${esc(mode.label)}</span>
          </button>
        `).join("")}
      </div>
    </section>

    <section class="modal-section dashboard-home-lighting-selected-section">
      <h2 class="modal-section-title">${esc(selectedMeta.label)} Mode</h2>

      ${rooms.length ? `
        <div class="dashboard-home-lighting-room-list">
          ${rooms.map(room => {
            const roomClients = grouped.get(room) || [];
            const deviceClients = groupedDevices.get(room) || [];
            const roomSupportsPreset = roomClients.some(dashboardHomeLightingClientSupportsPreset);
            const roomChoice = roomClients.length
              ? dashboardHomeLightingChoiceForRoom(selectedMode, room, roomClients)
              : "";

            return `
              <section class="settings-server-card dashboard-home-lighting-room-card">
                <div class="dashboard-home-lighting-room-title-row">
                  <div class="dashboard-home-lighting-room-title">${esc(room)}</div>

                  ${roomClients.length ? dashboardHomeLightingChoiceButtonsHtml({
                    mode: selectedMode,
                    targetType: "room",
                    targetKey: room,
                    activeChoice: roomChoice,
                    supportsPreset: roomSupportsPreset
                  }) : ""}
                </div>

                ${deviceClients.length ? `
                  <div class="dashboard-home-lighting-device-list">
                    ${deviceClients.map(client => {
                      const deviceID = String(client?.deviceID || "").trim();
                      const deviceSupportsPreset = dashboardHomeLightingClientSupportsPreset(client);
                      const deviceChoice = dashboardHomeLightingChoiceForClient(selectedMode, client, "");
                      const deviceKind = deviceSupportsPreset
                        ? "Dimmable light"
                        : dashboardHomeIsLight(client)
                          ? "Light"
                          : "Power device";

                      return `
                        <div class="dashboard-home-lighting-device-row">
                          <div class="dashboard-home-lighting-device-copy">
                            ${window.dashboardIconHtml(
                              dashboardHomeIsLight(client) ? "emoji_objects" : "power",
                              "icon-glow dashboard-home-lighting-device-icon"
                            )}
                            <span class="settings-automation-copy">
                              <span class="settings-automation-title">${esc(dashboardHomeClientName(client))}</span>
                              <span class="settings-automation-subtitle">${esc(deviceKind)}</span>
                            </span>
                          </div>

                          ${dashboardHomeLightingChoiceButtonsHtml({
                            mode: selectedMode,
                            targetType: "device",
                            targetKey: deviceID,
                            activeChoice: deviceChoice,
                            supportsPreset: deviceSupportsPreset
                          })}
                        </div>
                      `;
                    }).join("")}
                  </div>
                ` : ""}
              </section>
            `;
          }).join("")}
        </div>
      ` : `
        <div class="dashboard-home-lighting-empty">
          No lights or power devices are available yet.
        </div>
      `}
    </section>
  `;
}

window.selectDashboardHomeLightingSettingsMode = function (mode) {
  dashboardHomeLightingSelectedMode = dashboardHomeCleanLightingMode(mode);
  renderDashboardHomeLightingSettings();
};

window.setDashboardHomeLightingModeChoice = async function (button) {
  const mode = dashboardHomeCleanLightingMode(button?.dataset?.mode || dashboardHomeLightingSelectedMode);
  const targetType = String(button?.dataset?.targetType || "").trim();
  const targetKey = String(button?.dataset?.targetKey || "").trim();
  const choice = String(button?.dataset?.choice || "").trim();

  if (!mode || !targetType || !targetKey || !choice) return;

  const configKey = dashboardHomeLightingTargetKey(targetType, targetKey);
  if (!configKey) return;

  const grouped = dashboardHomeLightingGroupedPowerClients();
  const currentChoice = targetType === "room"
    ? dashboardHomeLightingChoiceForRoom(mode, targetKey, grouped.get(targetKey) || [])
    : dashboardHomeLightingChoiceForClient(
      mode,
      (S.currentClients || []).find(client => String(client?.deviceID || "") === targetKey),
      ""
    );
  const nextProfile = dashboardHomeLightingChoiceProfile(currentChoice);

  if (choice === "off") {
    if (nextProfile.power === "off" && !nextProfile.preset) {
      nextProfile.power = "";
    } else {
      nextProfile.power = "off";
      nextProfile.preset = "";
    }
  } else if (choice === "on") {
    nextProfile.power = nextProfile.power === "on" ? "" : "on";
  } else if (dashboardHomeLightingChoiceIsPreset(choice)) {
    if (nextProfile.preset === choice) {
      nextProfile.preset = "";
    } else {
      nextProfile.preset = choice;
      if (nextProfile.power === "off") nextProfile.power = "";
    }
  }

  const config = dashboardHomeLightingModeConfig();
  config[mode] = config[mode] && typeof config[mode] === "object" ? config[mode] : {};
  config[mode][configKey] = dashboardHomeLightingChoiceProfileValue(nextProfile);

  await writeDashboardHomeLightingModeConfig(config);
  dashboardHomeLightingSelectedMode = mode;
  renderDashboardHomeLightingSettings();
};

function renderDashboardHomeLightingTargetList(selectedIDs = []) {
  const selected = new Set((selectedIDs || []).map(deviceID => String(deviceID || "").trim()).filter(Boolean));
  const grouped = dashboardHomeAllLightClients().reduce((map, client) => {
    const room = dashboardHomeClientRoom(client);
    if (!map.has(room)) map.set(room, []);
    map.get(room).push(client);
    return map;
  }, new Map());

  if (!grouped.size) {
    return `<div class="dashboard-home-lighting-empty">No Tapo bulbs found.</div>`;
  }

  return Array.from(grouped.entries()).map(([room, clients]) => `
    <div class="dashboard-home-lighting-target-group">
      <div class="dashboard-home-lighting-target-room">${esc(room)}</div>
      ${clients.map(client => `
        <label class="tapo-light-check-row dashboard-home-lighting-target-row">
          <input
            type="checkbox"
            value="${escAttr(client.deviceID || "")}"
            ${selected.has(client.deviceID) ? "checked" : ""}
          >
          <span>${esc(dashboardHomeClientName(client))}</span>
        </label>
      `).join("")}
    </div>
  `).join("");
}

function renderDashboardHomeLightingAutomationEditor(mode) {
  const body = document.getElementById("dashboardHomeLightingAutomationBody");
  const title = document.getElementById("dashboardHomeLightingAutomationTitle");
  const subtitle = document.getElementById("dashboardHomeLightingAutomationSubtitle");
  const modeMeta = dashboardHomeLightingModeMeta(dashboardHomeCleanLightingMode(mode));

  if (title) title.textContent = `Add to ${modeMeta.label} Mode`;

  if (subtitle) {
    subtitle.textContent = "";
    subtitle.hidden = true;
  }

  if (!body) return;

  dashboardHomeArmingWizardStep = "response";
  dashboardHomeArmingUpdateBreadcrumb("response", modeMeta.mode, dashboardHomeArmingDraft?.actionType || "");

  body.innerHTML = `
    <section class="modal-section dashboard-home-arming-picker-section">
      <div class="modal-subtitle">
        THIS MODE SHOULD...
      </div>

      <div class="dashboard-home-arming-picker-actions">
        <button class="settings-item dashboard-home-arming-big-action" type="button" data-dashboard-action="select-home-lighting-action-type" data-mode="${escAttr(modeMeta.mode)}" data-action-type="device_power">
          ${window.dashboardIconHtml("toggle_on")}
          <span class="settings-automation-title">Flip a Switch</span>
        </button>

        <button class="settings-item dashboard-home-arming-big-action" type="button" data-dashboard-action="select-home-lighting-action-type" data-mode="${escAttr(modeMeta.mode)}" data-action-type="lighting_mode">
          ${window.dashboardIconHtml("emoji_objects")}
          <span class="settings-automation-title">Set Lighting</span>
        </button>
      </div>
    </section>
  `;
}

function dashboardHomeLightingEditorSelectedIDs() {
  return [];
}

function dashboardHomeLightingRetryDelay(attempt) {
  return new Promise(resolve => {
    window.setTimeout(resolve, 500 * (attempt + 1));
  });
}

async function sendDashboardHomeTapoCommand(payload) {
  const commandPayload = dashboardHomeResolveTapoCommandPayload(payload);
  const maxAttempts = 3;
  let lastError = null;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      const res = await dashboardFetch("/api/tapo/client-command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(commandPayload)
      });

      let data = {};

      try {
        data = await res.json();
      } catch (err) {
        data = {};
      }

      if (!res.ok || data.ok !== true) {
        const error = new Error(data.error || `Tapo command failed: ${res.status}`);

        error.retryable = (
          res.status === 429 ||
          res.status >= 500 ||
          (res.ok && data.ok !== true)
        );

        throw error;
      }

      return data;
    } catch (err) {
      lastError = err;

      if (attempt >= maxAttempts - 1 || err?.retryable === false) {
        throw err;
      }

      await dashboardHomeLightingRetryDelay(attempt);
    }
  }

  throw lastError || new Error("Tapo command failed.");
}

function dashboardHomeEsc(value) {
  if (typeof esc === "function") return esc(value);

  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function dashboardHomeEscAttr(value) {
  if (typeof escAttr === "function") return escAttr(value);

  return dashboardHomeEsc(value);
}

function dashboardHomeCleanLightingMode(mode) {
  if (mode === "nightlight") return "night";

  return ["day", "evening", "night", "away"].includes(mode) ? mode : "day";
}

function dashboardHomeLightingSchemes() {
  const state = window.TAPO_LIGHTING_STATE || {};

  return state.schemes && typeof state.schemes === "object"
    ? state.schemes
    : {};
}

function dashboardHomeLightingSchemeForKey(key, mode) {
  const schemes = dashboardHomeLightingSchemes();
  const targetSchemes = key ? schemes[key] || [] : [];

  return targetSchemes.find(scheme => scheme?.mode === mode);
}

function dashboardHomeLightingDeviceKey(deviceID) {
  const cleanID = String(deviceID || "").trim();

  return cleanID ? `device:${cleanID}` : "";
}

function dashboardHomeLightingRoomKey(clients = []) {
  const ids = clients
    .map(client => String(client?.deviceID || "").trim())
    .filter(Boolean)
    .sort();

  return ids.length ? `room:${ids.join(",")}` : "";
}

function dashboardHomeBuiltinLightingPreset(mode) {
  const presets = {
    day: {
      brightness: 90,
      colorTemperature: 3700,
      whiteSaturation: 1,
      hue: null,
      saturation: null
    },
    evening: {
      brightness: 80,
      colorTemperature: 3200,
      whiteSaturation: 1,
      hue: null,
      saturation: null
    },
    movie: {
      brightness: 5,
      colorTemperature: 2700,
      whiteSaturation: 5,
      hue: null,
      saturation: null
    },
    nightlight: {
      brightness: 1,
      colorTemperature: 2700,
      whiteSaturation: 1,
      hue: null,
      saturation: null
    }
  };

  const preset = presets[String(mode || "").trim().toLowerCase()];

  return preset ? { ...preset } : null;
}

function dashboardHomeLightingPresetForClient(client, mode, roomPreset = null) {
  const deviceScheme = dashboardHomeLightingSchemeForKey(
    dashboardHomeLightingDeviceKey(client?.deviceID),
    mode
  );

  return (
    deviceScheme?.preset ||
    roomPreset ||
    dashboardHomeBuiltinLightingPreset(mode)
  );
}

function dashboardHomeLightingClientsByRoom(clients = []) {
  return clients.reduce((map, client) => {
    const room = dashboardHomeClientRoom(client);

    if (!map.has(room)) map.set(room, []);
    map.get(room).push(client);

    return map;
  }, new Map());
}

function normalizeDashboardHomeWhiteSaturation(value = 1) {
  const parsed = Number(value ?? 1);

  return Math.max(1, Math.min(10, Math.round(Number.isFinite(parsed) ? parsed : 1)));
}

function dashboardHomeWhiteHueFromKelvin(kelvin) {
  const t = Math.max(2500, Math.min(6500, Number(kelvin || 4000)));
  const ratio = (t - 2500) / 4000;

  return Math.round(42 + ((210 - 42) * ratio));
}

function dashboardHomeLightingPresetCommandsForClient(client, preset, mode = "") {
  const deviceID = client?.deviceID || "";
  const lightingMode = String(mode || "").trim().toLowerCase();
  const commands = [];

  if (!deviceID || !preset) return commands;

  if (preset.brightness != null && client?.tapo_supports_brightness !== false) {
    commands.push({
      deviceID,
      action: "brightness_no_power",
      value: preset.brightness,
      lightingMode
    });
  }

  if (preset.hue != null && client?.tapo_supports_color !== false) {
    commands.push({
      deviceID,
      action: "color_no_power",
      value: {
        hue: preset.hue,
        saturation: preset.saturation
      },
      lightingMode
    });
  } else if (preset.colorTemperature != null && client?.tapo_supports_color !== false) {
    commands.push({
      deviceID,
      action: "color_no_power",
      value: {
        hue: dashboardHomeWhiteHueFromKelvin(preset.colorTemperature),
        saturation: normalizeDashboardHomeWhiteSaturation(preset.whiteSaturation),
        colorTemperature: preset.colorTemperature,
        whiteSaturation: normalizeDashboardHomeWhiteSaturation(preset.whiteSaturation)
      },
      lightingMode
    });
  } else if (preset.colorTemperature != null && client?.tapo_supports_color_temp !== false) {
    commands.push({
      deviceID,
      action: "color_temperature_no_power",
      value: preset.colorTemperature,
      lightingMode
    });
  }

  return commands;
}

async function dashboardHomeSendLightingPresetToClient(client, preset, mode = "") {
  const commands = dashboardHomeLightingPresetCommandsForClient(client, preset, mode);

  for (const command of commands) {
    await sendDashboardHomeTapoCommand(command);
  }
}

async function dashboardHomeAwaitLightingTasks(tasks = []) {
  const results = await Promise.allSettled(tasks);
  const failures = results.filter(result => result.status === "rejected");

  if (!failures.length) return results;

  const firstReason = failures[0].reason;
  const firstError = firstReason instanceof Error
    ? firstReason
    : new Error(String(firstReason || "Lighting command failed."));

  if (failures.length === 1) {
    throw firstError;
  }

  throw new Error(
    `${failures.length} lighting targets failed. First error: ${firstError.message}`
  );
}

async function dashboardHomeApplyLightingModeToClients(clients = [], mode = "", opts = {}) {
  const cleanMode = dashboardHomeCleanLightingMode(mode);
  const allRoomClients = dashboardHomeLightingClientsByRoom(dashboardHomeIncludedLightClients());
  let targetClients = clients.filter(client => client?.deviceID);

  if (opts.onlyPoweredOn === true) {
    targetClients = targetClients.filter(dashboardHomeClientIsPoweredOn);
  }

  if (!targetClients.length) return;

  await window.loadTapoLightingState?.({ force: true });

  const tasks = [];

  dashboardHomeLightingClientsByRoom(targetClients).forEach((roomClients, room) => {
    const roomSchemeClients = allRoomClients.get(room) || roomClients;
    const roomScheme = dashboardHomeLightingSchemeForKey(dashboardHomeLightingRoomKey(roomSchemeClients), cleanMode);
    const roomPreset = roomScheme?.preset || null;

    roomClients.forEach(client => {
      tasks.push(dashboardHomeSendLightingPresetToClient(
        client,
        dashboardHomeLightingPresetForClient(client, cleanMode, roomPreset),
        cleanMode
      ));
    });
  });

  await dashboardHomeAwaitLightingTasks(tasks);
}

function dashboardHomeLightingCommandsForChoice(client, choice, roomPreset = null) {
  const deviceID = client?.deviceID || "";
  const profile = dashboardHomeLightingChoiceProfile(choice);
  const commands = [];

  if (!deviceID || (!profile.power && !profile.preset)) return commands;

  if (profile.power === "off") {
    commands.push({ deviceID, action: "off" });
    return commands;
  }

  if (profile.power === "on") {
    commands.push({ deviceID, action: "on" });
  }

  if (profile.preset && dashboardHomeLightingClientSupportsPreset(client)) {
    commands.push(...dashboardHomeLightingPresetCommandsForClient(
      client,
      dashboardHomeLightingPresetForClient(client, profile.preset, roomPreset),
      profile.preset
    ));
  }

  return commands;
}

function dashboardHomeConfiguredLightingModeCommands(mode) {
  const cleanMode = dashboardHomeCleanLightingMode(mode);
  const grouped = dashboardHomeLightingGroupedPowerClients();
  const groupedDevices = dashboardHomeLightingGroupedIndividualPowerClients();
  const commands = [];

  grouped.forEach((clients, room) => {
    const roomChoice = dashboardHomeLightingChoiceForRoom(cleanMode, room, clients);
    const profile = dashboardHomeLightingChoiceProfile(roomChoice);
    const roomScheme = profile.preset
      ? dashboardHomeLightingSchemeForKey(dashboardHomeLightingRoomKey(clients), profile.preset)
      : null;
    const roomPreset = roomScheme?.preset || null;

    clients.forEach(client => {
      commands.push(...dashboardHomeLightingCommandsForChoice(client, roomChoice, roomPreset));
    });
  });

  groupedDevices.forEach(clients => {
    clients.forEach(client => {
      const deviceChoice = dashboardHomeLightingChoiceForClient(cleanMode, client, "");
      commands.push(...dashboardHomeLightingCommandsForChoice(client, deviceChoice));
    });
  });

  return commands.map(dashboardHomeResolveTapoCommandPayload);
}

async function dashboardHomeSendLightingCommandBatch(commands, mode) {
  const cleanMode = dashboardHomeCleanLightingMode(mode);
  const maxAttempts = 3;
  let lastError = null;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      const res = await dashboardFetch("/api/tapo/client-command-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          activeHomeMode: cleanMode,
          commands
        })
      });
      let data = {};

      try {
        data = await res.json();
      } catch (err) {
        data = {};
      }

      if (!res.ok || data.ok !== true) {
        const error = new Error(data.error || `Home scene failed: ${res.status}`);
        error.retryable = res.status === 429 || res.status >= 500 || (res.ok && data.ok !== true);
        throw error;
      }

      if (typeof window.applyDashboardTapoLightingState === "function") {
        window.applyDashboardTapoLightingState(data);
      } else {
        dashboardHomeSetActiveLightingModeLocally(cleanMode);
      }

      const failures = Array.isArray(data.results)
        ? data.results.filter(result => result?.ok !== true)
        : [];

      if (failures.length) {
        console.warn(`[home scene] ${cleanMode} completed with ${failures.length} failed command(s)`, failures);
      }

      return data;
    } catch (err) {
      lastError = err;

      if (attempt >= maxAttempts - 1 || err?.retryable === false) {
        throw err;
      }

      await dashboardHomeLightingRetryDelay(attempt);
    }
  }

  throw lastError || new Error("Home scene failed.");
}

async function dashboardHomeApplyConfiguredLightingMode(mode) {
  const cleanMode = dashboardHomeCleanLightingMode(mode);

  // Use the already-loaded scene configuration. The loader still waits for
  // the initial request when necessary, but does not refetch it on every click.
  await window.loadTapoLightingState?.();
  dashboardHomeSetActiveLightingModeLocally(cleanMode);

  return dashboardHomeSendLightingCommandBatch(
    dashboardHomeConfiguredLightingModeCommands(cleanMode),
    cleanMode
  );
}

async function runDashboardHomeLightingAutomation(automation, opts = {}) {
  if (automation.type !== "lighting-mode") return;

  await dashboardHomeApplyLightingModeToClients(
    dashboardHomeIncludedLightClients(),
    automation.mode,
    opts
  );
}

async function runDashboardHomeLightingMode(mode) {
  const cleanMode = dashboardHomeCleanLightingMode(mode);

  try {
    dashboardHomeSetActiveLightingModeLocally(cleanMode);
    return await dashboardHomeApplyConfiguredLightingMode(cleanMode);
  } finally {
    // The batch response updates server state and broadcasts the completed
    // scene. Do not start a second full-device refresh behind every click.
    syncDashboardHomeModeButtons?.();
  }
}

window.applyDashboardHomeLightingModeToDevices = async function (deviceIDs = [], mode = "") {
  const ids = new Set(
    (Array.isArray(deviceIDs) ? deviceIDs : [deviceIDs])
      .map(deviceID => String(deviceID || "").trim())
      .filter(Boolean)
  );
  const cleanMode = dashboardHomeCleanLightingMode(mode || dashboardHomeCurrentLightingMode());
  const targetClients = dashboardHomeIncludedLightClients()
    .filter(client => ids.has(String(client?.deviceID || "")));

  if (!targetClients.length) return;

  await dashboardHomeApplyLightingModeToClients(targetClients, cleanMode, { onlyPoweredOn: false });
  window.refreshTapoDeviceStatesSoon?.(750);
};

window.showDashboardHomeLightingSettings = async function (mode) {
  window.ensureDashboardHomeLightingModalShells?.();
  closeAllMenus?.();
  await window.loadTapoLightingState?.({ force: true });
  dashboardHomeLightingSelectedMode = dashboardHomeCleanLightingMode(mode || dashboardHomeCurrentLightingMode());
  renderDashboardHomeLightingSettings();

  const modal = document.getElementById("dashboardHomeLightingModal");
  if (!modal) return;

  dashboardHideParentModalForSubmodal(modal, "settingsModal");

  modal.hidden = false;
  document.body.classList.add("modal-open");
};

window.hideDashboardHomeLightingSettings = function () {
  const editorModal = document.getElementById("dashboardHomeLightingAutomationModal");
  const modal = document.getElementById("dashboardHomeLightingModal");

  if (editorModal) {
    editorModal.hidden = true;
    editorModal.dataset.returnModalId = "";
  }

  if (modal) modal.hidden = true;

  if (dashboardRestoreParentModalFromSubmodal(modal)) return;

  dashboardCloseModalOpenClassIfNeeded();
};

window.showDashboardHomeLightingAutomationEditor = function (mode, automationID = "") {
  window.ensureDashboardHomeLightingModalShells?.();
  renderDashboardHomeLightingAutomationEditor(mode, automationID);

  const modal = document.getElementById("dashboardHomeLightingAutomationModal");
  if (!modal) return;

  dashboardHideParentModalForSubmodal(modal, "dashboardHomeLightingModal");

  modal.hidden = false;
  document.body.classList.add("modal-open");
};

window.selectDashboardHomeLightingActionType = function (button) {
  const mode = dashboardHomeCleanLightingMode(button?.dataset?.mode || dashboardHomeLightingSelectedMode);
  const actionType = String(button?.dataset?.actionType || "").trim();

  [...document.querySelectorAll('#dashboardHomeLightingAutomationBody [data-dashboard-action="select-home-lighting-action-type"]')]
    .forEach(item => {
      const active = item === button;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", active ? "true" : "false");
    });

  dashboardHomeLightingSelectedMode = mode;

  return actionType;
};

window.hideDashboardHomeLightingAutomationEditor = function () {
  const modal = document.getElementById("dashboardHomeLightingAutomationModal");
  if (modal) modal.hidden = true;

  if (dashboardRestoreParentModalFromSubmodal(modal)) return;

  dashboardCloseModalOpenClassIfNeeded();
};

window.toggleDashboardHomeLightingAllLights = function () {
  const input = document.getElementById("dashboardHomeLightingAllLightsInput");
  const list = document.getElementById("dashboardHomeLightingTargetList");

  if (list) list.hidden = !!input?.checked;
};

window.updateDashboardHomeLightingAutomationSlider = function () {
};

window.saveDashboardHomeLightingAutomation = function () {
  writeDashboardHomeLightingAutomations();
  hideDashboardHomeLightingAutomationEditor();
  renderDashboardHomeLightingSettings();
};

window.removeDashboardHomeLightingAutomation = function () {
  writeDashboardHomeLightingAutomations();
  renderDashboardHomeLightingSettings();
};

window.showRenderControls = async function () {
  window.setDashboardPageState?.("controls", { syncDocument: false });

  if (typeof window.syncMatterRoomEnvironmentHeader !== "function") {
    try {
      await window.loadDashboardMatterSubsystem?.();
    } catch (err) {
      console.warn("[dashboard-load] Controls Matter dependency failed", err);
    }
  }

  showView("dashboard", { render: false, renderAside: false });
  renderDashboardNavigationNow();
};

window.showRenderMonitors = async function () {
  window.setDashboardPageState?.("monitor", { syncDocument: false });

  if (typeof window.syncMatterRoomEnvironmentHeader !== "function") {
    try {
      await window.loadDashboardMatterSubsystem?.();
    } catch (err) {
      console.warn("[dashboard-load] Monitor Matter dependency failed", err);
    }
  }

  showView("dashboard", { render: false, renderAside: false });
  renderDashboardNavigationNow();
};

window.showRenderSensors = async function () {
  window.setDashboardPageState?.("sensors", { syncDocument: false });

  if (typeof window.syncMatterRoomEnvironmentHeader !== "function") {
    try {
      await window.loadDashboardMatterSubsystem?.();
    } catch (err) {
      console.warn("[dashboard-load] Sensors Matter dependency failed", err);
    }
  }

  showView("dashboard", { render: false, renderAside: false });
  renderDashboardNavigationNow();
};

window.showDashboardClientsModal = async function () {
  window.ensureSettingsModal?.();

  const modal = document.getElementById("dashboardClientsModal");
  if (!modal) return;

  if (typeof window.renderMatterFoundHomeSection !== "function") {
    try {
      await window.loadDashboardMatterSubsystem?.();
    } catch (err) {
      console.warn("[dashboard-load] Devices discovery dependency failed", err);
    }
  }

  dashboardHideParentModalForSubmodal(modal, "settingsModal");
  window.renderDashboardClientsModal?.(S.currentClients || []);

  modal.hidden = false;
  document.body.classList.add("modal-open");
};

window.hideDashboardClientsModal = function () {
  const modal = document.getElementById("dashboardClientsModal");
  if (!modal) return;

  modal.hidden = true;

  if (dashboardRestoreParentModalFromSubmodal(modal)) return;

  dashboardCloseModalOpenClassIfNeeded();
};

async function dashboardOpenTapoSettingsFromClient(
  client,
  returnModalID = ""
) {
  const kind = String(
    client?.tapo_kind || client?.tapo_device_type || ""
  ).trim().toLowerCase();
  const isCamera =
    kind === "camera" ||
    client?.tapo_dashboard_section === "camera" ||
    client?.tapo_is_camera === true;

  for (let attempt = 0; attempt < 20; attempt += 1) {
    const rendererReady = isCamera
      ? (
          typeof window.renderTapoCameraCard === "function" &&
          typeof window.showTapoCameraModal === "function"
        )
      : (
          typeof window.renderTapoClientCard === "function" &&
          typeof window.showTapoLightModal === "function"
        );

    if (rendererReady) break;

    await new Promise(resolve => window.setTimeout(resolve, 100));
  }

  const renderer = isCamera
    ? window.renderTapoCameraCard
    : window.renderTapoClientCard;

  if (typeof renderer !== "function") return false;

  const template = document.createElement("template");
  template.innerHTML = String(renderer(client) || "").trim();

  const sourceButton = template.content.querySelector(
    isCamera
      ? '[data-tapo-action="camera-settings"]'
      : '[data-tapo-action="settings"]'
  );

  if (!sourceButton) return false;

  const host = document.createElement("span");
  const button = sourceButton.cloneNode(true);

  host.hidden = true;
  host.appendChild(button);
  document.body.appendChild(host);
  button.click();

  if (returnModalID) {
    dashboardHideParentModalForSubmodal(
      document.getElementById(
        isCamera ? "tapoCameraModal" : "tapoLightModal"
      ),
      returnModalID
    );
  }

  window.setTimeout(() => host.remove(), 0);
  return true;
}

function dashboardOpenClientMenuFromRegistry(
  event,
  deviceID,
  kind
) {
  window.ensureDashboardModalShells?.();

  dashboardHideParentModalForSubmodal(
    document.getElementById("clientMenuModal"),
    "dashboardClientsModal"
  );

  window.openClientMenuNow?.(event, deviceID, kind);
}

window.openDashboardClientSettings = async function (
  event,
  deviceID
) {
  const client = getClientByDeviceId(deviceID);
  if (!client) return false;

  const isMatter =
    window.dashboardClientIsMatter?.(client) === true ||
    client?.source === "matter";

  if (isMatter) {
    dashboardOpenClientMenuFromRegistry(event, deviceID, "matter");
    return true;
  }

  if (clientHasRole(client, "TAPO")) {
    const opened = await dashboardOpenTapoSettingsFromClient(
      client,
      "dashboardClientsModal"
    );

    if (opened) return true;
  }

  dashboardOpenClientMenuFromRegistry(event, deviceID, "client");
  return true;
};

window.dashboardActivityViewportLimit = function () {
  const viewportHeight = (
    window.visualViewport?.height ||
    window.innerHeight ||
    720
  );
  const rootStyle = getComputedStyle(
    document.documentElement
  );
  const innerSpace = Number.parseFloat(
    rootStyle.getPropertyValue("--inner-space")
  ) || 8;
  const controlSize = Number.parseFloat(
    rootStyle.getPropertyValue("--control-size")
  ) || 44;
  const modal = document.getElementById(
    "dashboardActivityModal"
  );
  const headHeight = (
    modal
      ?.querySelector(".modal-head")
      ?.offsetHeight ||
    controlSize
  );
  const toolbarHeight = (
    modal
      ?.querySelector(
        ".dashboard-activity-toolbar"
      )
      ?.offsetHeight ||
    controlSize
  );
  const rowHeight = (
    controlSize +
    (innerSpace * 2)
  );
  const availableHeight = Math.max(
    rowHeight,
    viewportHeight -
      headHeight -
      toolbarHeight -
      (innerSpace * 10)
  );

  return Math.max(
    4,
    Math.min(
      50,
      Math.ceil(
        availableHeight / rowHeight
      ) + 1
    )
  );
};

window.showActivityModal = function () {
  window.ensureDashboardActivityModalShell?.();
  window.closeAllMenus?.();

  const modal = document.getElementById(
    "dashboardActivityModal"
  );

  if (!modal) return;

  dashboardHideParentModalForSubmodal(
    modal,
    "settingsModal"
  );

  S.activityModalOpen = true;
  S.activityHasMore = false;
  S.recentActivity = [];
  S.recentActivityLoading = true;

  modal.hidden = false;
  document.body.classList.add("modal-open");
  window.renderDashboardAside?.();
  window.syncDashboardActivityModal?.();
  window.startRecentActivityPolling?.();

  requestAnimationFrame(() => {
    S.activityLimit = (
      window.dashboardActivityViewportLimit?.() ||
      12
    );

    refreshRecentActivities?.({
      limit: S.activityLimit,
      fromHours: S.activityFromHours,
      toHours: S.activityToHours,
      category: S.activityFilter
    }).catch(err => {
      console.warn(
        "[recent-activity] activity modal load error",
        err
      );
      S.recentActivity = [];
      window.syncDashboardActivityModal?.();
    });
  });
};

window.hideActivityModal = function () {
  const modal = document.getElementById(
    "dashboardActivityModal"
  );

  if (!modal) return;

  modal.hidden = true;
  S.activityModalOpen = false;
  S.recentActivityLoading = false;
  S.recentActivityRequestID = (
    Number(S.recentActivityRequestID || 0) + 1
  );
  S.activityAutoLoadObserver?.disconnect();
  S.activityAutoLoadObserver = null;

  if (S.recentActivityInterval) {
    clearInterval(S.recentActivityInterval);
    S.recentActivityInterval = null;
  }

  window.renderDashboardAside?.();

  if (
    dashboardRestoreParentModalFromSubmodal(
      modal
    )
  ) return;

  dashboardCloseModalOpenClassIfNeeded();
};

window.setActivityFilter = async function (
  category
) {
  const clean = [
    "automation",
    "security"
  ].includes(category)
    ? category
    : "automation";

  if (clean === S.activityFilter) return;

  S.activityFilter = clean;
  S.activityHasMore = false;
  S.recentActivity = [];
  S.recentActivityLoading = true;
  window.syncDashboardActivityModal?.();

  await refreshRecentActivities?.({
    limit: S.activityLimit,
    fromHours: S.activityFromHours,
    toHours: S.activityToHours,
    category: clean
  });
};

window.setActivityRange = async function (
  changedInput
) {
  const selected =
    window.syncDashboardActivityRange?.(
      changedInput
    );

  if (!selected) return;

  const fromHours = (
    selected.fromHours >=
    selected.availableHours
      ? 0
      : selected.fromHours
  );
  const toHours = selected.toHours;

  if (
    fromHours === S.activityFromHours &&
    toHours === S.activityToHours
  ) return;

  S.activityFromHours = fromHours;
  S.activityToHours = toHours;
  S.activityHasMore = false;
  S.recentActivity = [];
  S.recentActivityLoading = true;
  window.syncDashboardActivityModal?.();

  await refreshRecentActivities?.({
    limit: S.activityLimit,
    fromHours,
    toHours,
    category: S.activityFilter
  });
};

window.loadOlderActivity = async function () {
  if (
    S.recentActivityLoading ||
    !S.activityHasMore
  ) return;

  const timestamps = (S.recentActivity || [])
    .map(item => Number(item?.ts || 0))
    .filter(timestamp => timestamp > 0);
  const beforeTs = timestamps.length
    ? Math.min(...timestamps)
    : 0;

  if (!beforeTs) return;

  await refreshRecentActivities?.({
    limit: S.activityLimit,
    fromHours: S.activityFromHours,
    toHours: S.activityToHours,
    category: S.activityFilter,
    beforeTs,
    merge: true
  });
};

window.openZoneList = function (input) {
  if (!input || input.disabled) return;

  input.focus();

  try {
    if (typeof input.showPicker === "function") {
      input.showPicker();
      return;
    }
  } catch (_) {}

  input.dispatchEvent(new KeyboardEvent("keydown", {
    key: "ArrowDown",
    code: "ArrowDown",
    bubbles: true
  }));
};

window.toggleProvisionFunction = function (deviceID, clientRole) {
  const hidden = document.getElementById(`p_role_${deviceID}`);
  const camBtn = document.getElementById(`p_btn_cam_${deviceID}`);
  const doorBtn = document.getElementById(`p_btn_door_${deviceID}`);

  if (!hidden || !camBtn || !doorBtn) return;

  clientRole = String(clientRole || "").trim().toUpperCase();
  if (!["CAM", "DSS"].includes(clientRole)) return;

  const current = new Set(
    (hidden.value || "")
      .split(",")
      .map(v => v.trim().toUpperCase())
      .filter(Boolean)
  );

  if (current.has(clientRole)) {
    current.delete(clientRole);
  } else {
    current.add(clientRole);
  }

  if (!current.size) current.add("CAM");

  hidden.value = Array.from(current).sort().join(",");

  camBtn.classList.toggle("active", current.has("CAM"));
  doorBtn.classList.toggle("active", current.has("DSS"));
  camBtn.setAttribute("aria-pressed", current.has("CAM") ? "true" : "false");
  doorBtn.setAttribute("aria-pressed", current.has("DSS") ? "true" : "false");

  const createBtn = document.getElementById(`p_create_${deviceID}`);
  if (createBtn) {
    const hasCam = current.has("CAM");
    const hasDss = current.has("DSS");

    createBtn.textContent =
      hasCam && hasDss
        ? "Create multi-function client"
        : hasDss
          ? "Create door sensor client"
          : "Create camera client";
  }
};

function clientRolesOf(c) {
  if (Array.isArray(c?.clientRole)) return c.clientRole.map(v => String(v).toUpperCase());
  return String(c?.clientRole || "")
    .split(",")
    .map(v => v.trim().toUpperCase())
    .filter(Boolean);
}

function clientHasRole(c, clientRole) {
  return clientRolesOf(c).includes(clientRole);
}

function getClientByDeviceId(deviceID) {
  return (S.currentClients || []).find(c => c.deviceID === deviceID) || null;
}

function getClientByDeviceAndRole(deviceID, clientRole) {
  return (S.currentClients || []).find(c =>
    c.deviceID === deviceID &&
    clientHasRole(c, clientRole)
  ) || null;
}

function getActionTarget(deviceID, clientRole) {
  const client = getClientByDeviceAndRole(deviceID, clientRole);

  return {
    deviceID,
    clientRole,
    client
  };
}

function patchClientByDeviceId(deviceID, fields, data = null) {
  const applyPatch = (client) => {
    if (client?.deviceID === deviceID) {
      Object.assign(client, fields);
    }
  };

  (S.currentClients || []).forEach(applyPatch);
  (data?.clients || []).forEach(applyPatch);
}

function roleSetOfClient(c) {
  return new Set(clientRolesOf(c));
}

function detectedRoleSetOfClient(c) {
  const raw = c?.detectedRole || c?.detected_role || "";

  return new Set(
    String(raw)
      .split(",")
      .map(role => role.trim().toUpperCase())
      .filter(role => ["CAM", "DSS", "KEY", "TAPO"].includes(role))
  );
}

window.setClientEnabledRoles = async function (deviceID, roles) {
  const cleanRoles = Array.from(new Set((roles || [])
    .map(v => String(v || "").trim().toUpperCase())
    .filter(v => ["CAM", "DSS", "KEY"].includes(v))
  ));

  if (!cleanRoles.length) {
    alert("At least one service must remain enabled.");
    renderOpenClientMenu();
    return;
  }

  const client = getClientByDeviceId(deviceID);
  const previewUrl = client?.latest_frame_url || "";
  const selectedCamera = String(client?.selected_camera || client?.selectedCamera || "back").toLowerCase();

  const fields = {
    clientRole: cleanRoles,
    provisioned: true
  };

  if (cleanRoles.includes("CAM")) {
    fields.selected_camera = selectedCamera;
    fields.selectedCamera = selectedCamera;

    if (previewUrl) {
      fields.latest_frame_url = previewUrl;
    }
  }

  patchClientByDeviceId(deviceID, fields);

  await postJson("/api/client-command", {
    deviceID,
    enabledRoles: cleanRoles
  });

  const data = await refreshStatusData();
  patchClientByDeviceId(deviceID, fields, data);
  requestDashboardRenderSafe(data);
  renderOpenClientMenu();
};

window.toggleClientServiceRole = async function (deviceID, role, enabled) {
  const client = getClientByDeviceId(deviceID);
  if (!client) return;

  role = String(role || "").toUpperCase();

  const roles = roleSetOfClient(client);

  if (role === "KEY") {
    await setClientEnabledRoles(deviceID, enabled ? ["KEY"] : ["CAM"]);
    return;
  }

  roles.delete("KEY");

  if (enabled) {
    roles.add(role);
  } else {
    roles.delete(role);
  }

  await setClientEnabledRoles(deviceID, Array.from(roles));
};

function motionSensitivityFromThreshold(threshold) {
  const value = Number(threshold || 18);
  return Math.max(1, Math.min(10, Math.round((30 - value) / 2.4)));
}

function motionThresholdFromSensitivity(sensitivity) {
  const value = Math.max(1, Math.min(10, Number(sensitivity || 5)));
  return Math.round((30 - (value * 2.4)) * 10) / 10;
}

window.setCameraMotionSensitivity = async function (deviceID, sensitivity) {
  const target = getActionTarget(deviceID, "CAM");
  const cleanSensitivity = Math.max(1, Math.min(10, Number(sensitivity || 5)));
  const threshold = motionThresholdFromSensitivity(cleanSensitivity);
  const fields = {
    motionDetectionThreshold: threshold,
    motion_detection_threshold: threshold
  };

  patchClientByDeviceId(target.deviceID, fields);
  renderOpenClientMenu();

  await postJson("/api/client-command", {
    deviceID: target.deviceID,
    clientRole: target.clientRole,
    motionDetectionThreshold: threshold,
    motion_detection_threshold: threshold
  });

  const data = await refreshStatusData();
  patchClientByDeviceId(target.deviceID, fields, data);
  requestDashboardRenderSafe(data);
  renderOpenClientMenu();
};

window.clientMenuPreviewUrl = function (client) {
  const url = client?.latest_frame_url || "";
  if (!url) return "";
  return `${url}${url.includes("?") ? "&" : "?"}menu=${Date.now()}`;
};

function clientMenuManufacturer(client) {
  return String(
    client?.android_manufacturer ||
    client?.device_manufacturer ||
    client?.manufacturer ||
    client?.build_manufacturer ||
    client?.android_brand ||
    client?.brand ||
    ""
  ).trim();
}

function renderClientMenuZoneOptions() {
  return getProvisionZoneOptions()
    .map(zone => `<option value="${escAttr(zone)}"></option>`)
    .join("");
}

let clientMetaContext = null;

window.showClientMetaModal = function (initial) {
  window.ensureDashboardModalShells?.();

  const options = initial && typeof initial === "object"
    ? initial
    : { deviceID: initial };
  const deviceID = String(options.deviceID || "").trim();
  const client = getClientByDeviceId(deviceID);
  const modal = document.getElementById("clientMetaModal");
  const title = document.getElementById("clientMetaModalTitle");
  const subtitle = document.getElementById("clientMetaModalSubtitle");
  const body = document.getElementById("clientMetaModalBody");

  if (!deviceID || !modal || !body || (!client && !options.clientName)) return;

  const clientName = String(options.clientName ?? client?.clientName ?? "").trim();
  const zoneName = String(options.zoneName ?? clientRoomName(client) ?? "").trim();
  const parentModalID = String(options.parentModalID || "clientMenuModal").trim();
  const removable = options.removable !== false;
  const additionalFieldsHtml = String(options.additionalFieldsHtml || "");

  clientMetaContext = {
    save: typeof options.save === "function" ? options.save : null,
    remove: typeof options.remove === "function" ? options.remove : null
  };

  modal.dataset.deviceId = deviceID;

  if (title) title.textContent = "Edit Device";
  if (subtitle) subtitle.textContent = String(options.subtitle || clientName || "Device");

  body.innerHTML = `
    <div class="modal-section">
      <label class="client-menu-inline-field" for="clientMenuNameInput">
        <span class="client-menu-label">Rename</span>
        <input id="clientMenuNameInput" class="form-input client-menu-input" maxlength="40" value="${escAttr(clientName)}">
      </label>

      <label class="client-menu-inline-field" for="clientMenuZoneInput">
        <span class="client-menu-label">Zone</span>
        <input id="clientMenuZoneInput" class="form-input client-menu-input" list="clientMenuZoneList" maxlength="40" value="${escAttr(zoneName)}" data-dashboard-dblclick="open-zone-list">
      </label>

      <datalist id="clientMenuZoneList">
        ${renderClientMenuZoneOptions()}
      </datalist>

      ${additionalFieldsHtml}

      <div class="client-menu-actions client-menu-meta-actions">
        <button class="client-menu-btn" type="button" data-dashboard-action="save-client-meta">Save</button>
      </div>
    </div>

    ${removable ? `<div class="modal-section client-menu-delete-section">
      <div class="client-menu-actions">
        <button class="client-menu-btn danger client-menu-remove-btn" type="button" data-dashboard-action="remove-client-meta">
          ${window.dashboardIconHtml("delete")}
          <span>Remove Device</span>
        </button>
      </div>
    </div>` : ""}
  `;

  dashboardHideParentModalForSubmodal(modal, parentModalID);
  modal.hidden = false;
  document.body.classList.add("modal-open");

  requestAnimationFrame(() => document.getElementById("clientMenuNameInput")?.focus());
};

window.hideClientMetaModal = function (restoreParent = true) {
  const modal = document.getElementById("clientMetaModal");
  if (!modal) return;

  const wasOpen = modal.hidden === false;

  modal.hidden = true;
  modal.dataset.deviceId = "";

  const restoredParent = wasOpen && restoreParent
    ? dashboardRestoreParentModalFromSubmodal(modal)
    : false;

  if (!restoredParent) {
    modal.dataset.returnModalId = "";
    dashboardCloseModalOpenClassIfNeeded();
  }

  clientMetaContext = null;
};

window.removeClientMetaDevice = async function (button) {
  const modal = document.getElementById("clientMetaModal");
  const deviceID = modal?.dataset.deviceId || "";

  if (typeof clientMetaContext?.remove === "function") {
    return clientMetaContext.remove(button);
  }

  if (deviceID) {
    return window.removeClient?.(deviceID);
  }
};

function toggleClientMenuEditMode(event) {
  event?.preventDefault();
  event?.stopPropagation();

  const deviceID = document.getElementById("clientMenuModal")?.dataset.deviceId || "";
  if (!deviceID) return;

  window.showClientMetaModal(deviceID);
}

window.toggleClientMenuEditMode = toggleClientMenuEditMode;

window.clientMenuPreviewDeviceId = window.clientMenuPreviewDeviceId || "";
window.clientMenuPreviewRefreshTimer = window.clientMenuPreviewRefreshTimer || null;

window.setClientMenuPreviewViewerState = function (deviceID, active, useBeacon = false) {
  const cleanDeviceID = String(deviceID || "").trim();
  if (!cleanDeviceID) return;

  const payload = JSON.stringify({
    deviceID: cleanDeviceID,
    viewerId: `${window.previewViewerId || "dash"}_client_menu`,
    active: !!active
  });

  if (useBeacon && navigator.sendBeacon) {
    navigator.sendBeacon(
      "/api/preview-viewer",
      new Blob([payload], { type: "application/json" })
    );
    return;
  }

  fetch("/api/preview-viewer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
    keepalive: true
  }).catch(() => {});
};

window.refreshClientMenuPreviewImage = function () {
  const modal = document.getElementById("clientMenuModal");
  const deviceID = modal?.dataset.deviceId || "";
  if (!modal || modal.hidden || !deviceID) return;

  const client = getClientByDeviceId(deviceID);
  const previewUrl = clientMenuPreviewUrl(client);
  if (!previewUrl) return;

  const preview = document.querySelector("#clientMenuBody .camera-menu-preview");
  if (!preview) return;

  const img = preview.querySelector("img");
  if (img) {
    img.src = previewUrl;
    return;
  }

  const nextImage = document.createElement("img");
  nextImage.src = previewUrl;
  nextImage.alt = "Camera preview";
  preview.replaceChildren(nextImage);
};

window.syncClientMenuCameraPreviewViewer = function () {
  const modal = document.getElementById("clientMenuModal");
  const deviceID = modal?.dataset.deviceId || "";
  const client = getClientByDeviceId(deviceID);
  const shouldPreview = !!(
    modal &&
    !modal.hidden &&
    deviceID &&
    client &&
    roleSetOfClient(client).has("CAM")
  );

  if (!shouldPreview) {
    if (window.clientMenuPreviewRefreshTimer) {
      clearInterval(window.clientMenuPreviewRefreshTimer);
      window.clientMenuPreviewRefreshTimer = null;
    }

    if (window.clientMenuPreviewDeviceId) {
      window.setClientMenuPreviewViewerState(window.clientMenuPreviewDeviceId, false, true);
      window.clientMenuPreviewDeviceId = "";
    }

    return;
  }

  if (window.clientMenuPreviewDeviceId && window.clientMenuPreviewDeviceId !== deviceID) {
    window.setClientMenuPreviewViewerState(window.clientMenuPreviewDeviceId, false);
  }

  window.clientMenuPreviewDeviceId = deviceID;
  window.setClientMenuPreviewViewerState(deviceID, true);
  window.refreshClientMenuPreviewImage?.();

  if (!window.clientMenuPreviewRefreshTimer) {
    window.clientMenuPreviewRefreshTimer = setInterval(() => {
      if (!window.clientMenuPreviewDeviceId) return;
      window.setClientMenuPreviewViewerState(window.clientMenuPreviewDeviceId, true);
      window.refreshClientMenuPreviewImage?.();
    }, window.clientMenuPreviewRefreshMs || 4000);
  }
};

window.setRecording = async function (deviceID, val) {
  const target = getActionTarget(deviceID, "CAM");

  await postJson("/api/client-command", {
    deviceID: target.deviceID,
    clientRole: target.clientRole,
    recordingEnabled: val ? 1 : 0
  });

  const data = await refreshStatusData();
  requestDashboardRenderSafe(data);
};

window.setRecordingFromButton = async function (btnOrEvent, deviceID) {
  btnOrEvent?.preventDefault?.();
  btnOrEvent?.stopPropagation?.();

  const btn =
    btnOrEvent?.classList?.contains?.("camera-record-btn")
      ? btnOrEvent
      : btnOrEvent?.currentTarget?.classList?.contains?.("camera-record-btn")
        ? btnOrEvent.currentTarget
        : btnOrEvent?.target?.closest?.(".camera-record-btn");

  const nextVal = Number(btn?.dataset?.nextVal || 0) ? 1 : 0;

  if (btn) {
    btn.disabled = true;
    btn.classList.add("pending");
    btn.classList.toggle("active", !!nextVal);
    btn.title = nextVal ? "Stop Recording" : "Start Recording";
    btn.setAttribute("aria-label", btn.title);
    btn.setAttribute("aria-pressed", nextVal ? "true" : "false");
  }

  try {
    await setRecording(deviceID, nextVal);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove("pending");
    }
  }
};

window.setMotionDetection = async function (deviceID, val) {
  const target = getActionTarget(deviceID, "CAM");
  const isEnabled = !!val;
  const fields = {
    motionDetectionEnabled: isEnabled,
    motion_detection_enabled: isEnabled
  };

  patchClientByDeviceId(target.deviceID, fields);

  await postJson("/api/client-command", {
    deviceID: target.deviceID,
    clientRole: target.clientRole,
    motionDetectionEnabled: isEnabled ? 1 : 0,
    motion_detection_enabled: isEnabled ? 1 : 0
  });

  const data = await refreshStatusData();
  patchClientByDeviceId(target.deviceID, fields, data);
  requestDashboardRenderSafe(data);
};

window.toggleLens = async function (deviceID) {
  const target = getActionTarget(deviceID, "CAM");
  const client = target.client;

  const current =
    client?.selectedCamera ||
    client?.selected_camera ||
    "back";

  const nextCamera = current === "back" ? "front" : "back";

  await postJson("/api/client-command", {
    deviceID: target.deviceID,
    clientRole: "CAM",
    selected_camera: nextCamera,
    selectedCamera: nextCamera
  });

  const data = await refreshStatusData();
  requestDashboardRenderSafe(data);
};

window.recalibrate = async function (deviceID) {
  const target = getActionTarget(deviceID, "DSS");

  await postJson("/api/recalibrate", {
    deviceID: target.deviceID,
    clientRole: target.clientRole,
    triggerRecalibrate: 1
  });
};

window.provisionClient = async function (deviceID) {
  const clientName = document.getElementById(`p_name_${deviceID}`).value.trim();
  const zoneName = document.getElementById(`p_zone_${deviceID}`)?.value.trim() || "";
  const functionValue = document.getElementById(`p_role_${deviceID}`).value.trim();

  const clientRole = functionValue
    .split(",")
    .map(v => v.trim().toLowerCase())
    .filter(Boolean)
    .map(v => {
      if (v === "camera" || v === "cam" || v === "c") return "CAM";
      if (v === "door" || v === "dss" || v === "doorbell" || v === "sensor") return "DSS";
      if (v === "key" || v === "presence" || v === "user" || v === "controller") return "KEY";
      if (v === "tapo" || v === "light" || v === "bulb" || v === "plug") return "TAPO";
      return "";
    })
    .filter(Boolean);

  if (!clientName) {
    alert("Enter a client name first.");
    return;
  }

  if (!clientRole.length) {
    alert("Select at least one function first.");
    return;
  }

  if (!clientRole.includes("KEY") && !zoneName) {
    alert("Choose a room / zone / area first.");
    return;
  }

  const payload = { deviceID: deviceID, clientName, clientRole };

  if (!clientRole.includes("KEY")) {
    payload.zoneName = zoneName;
    payload.zone_name = zoneName;
  }
  if (clientRole.includes("CAM")) {
    payload.selectedCamera = "back";
  }

  let response;

  try {
    response = await postJson("/api/provision-client", payload);
  } catch (err) {
    console.error("[provisionClient] request failed", err);
    alert("Provisioning request failed. Check console for details.");
    return;
  }

  if (!response || response.error || response.ok === false) {
    console.error("[provisionClient] failed", response);
    alert(response?.error || "Provisioning failed. Check server logs.");
    return;
  }

  window.hideClientMenuModal?.();

  try {
    const data = await refreshStatusData();
    requestDashboardRenderSafe(data);
  } catch (err) {
    console.warn("[provisionClient] post-provision refresh failed", err);
  }
};

window.unlockDashboardSecurity = async function () {
  const input = document.getElementById("dashboardSecurityKey");
  const key = String(input?.value || "").trim();

  const data = await loginDashboardSecurity(key);

  if (!data.ok) {
    setDashboardSecurityStatus?.("Dashboard key was not accepted.");
    window.syncServerViewControls?.();
    return;
  }

  if (input) input.value = "";

  if (window.statusEventSource) {
    window.statusEventSource.close();
    window.statusEventSource = null;
  }

  startStatusStream?.();
  window.syncServerViewControls?.();
  syncDashboardSecurityControls?.();

  setDashboardSecurityStatus?.("");
};

window.restartServer = async function () {
  if (!confirm("Restart KotiBot Server?")) return;

  if (typeof hideSettingsModal === "function") {
    hideSettingsModal();
  }

  await restartKotiBotServer();
  alert("Server restarting...");
};

function dashboardDeviceAutomationTriggerGroup(trigger) {
  const value = String(trigger || "").trim().toLowerCase();

  if (["door_open", "door_close"].includes(value)) return "door";
  if (value === "motion") return "motion";
  if (value.startsWith("temperature_") || value.startsWith("humidity_")) return "environment";

  return "";
}

function dashboardDeviceAutomationTriggerLabel(trigger) {
  const value = String(trigger || "").trim().toLowerCase();
  const labels = {
    door_open: "Door opens",
    door_close: "Door closes",
    motion: "Motion",
    temperature_above: "Temperature rises above",
    temperature_below: "Temperature falls below",
    humidity_above: "Humidity rises above",
    humidity_below: "Humidity falls below"
  };

  return labels[value] || value.replace(/_/g, " ").replace(/^./, letter => letter.toUpperCase()) || "Trigger";
}

function dashboardDeviceAutomationTimerLabel(value) {
  const seconds = Number(value);

  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  if (seconds % 60 === 0) return `${seconds / 60} min`;

  return `${seconds} sec`;
}

function dashboardDeviceAutomationCardHtml(automation, menuDeviceID = "") {
  const actionType = String(automation?.actionType || "").trim().toLowerCase();
  const trigger = dashboardDeviceAutomationTriggerLabel(automation?.trigger);
  const timer = dashboardDeviceAutomationTimerLabel(automation?.autoOffSeconds);
  const targetName = String(automation?.targetName || automation?.targetDeviceID || "Device").trim();
  let icon = "toggle_on";
  let title = targetName;
  let action = "ON";

  if (["sound", "wav", "audio", "play_sound"].includes(actionType)) {
    icon = "music_note";
    title = String(automation?.filename || "Play Sound").split(/[\\/]/).pop();
    action = "Play";
  } else if (["notification", "notify", "push", "key_notification"].includes(actionType)) {
    icon = "notifications";
    title = String(automation?.title || "Notification").trim();
    action = "Send";
  } else if (["recording", "record", "video", "camera", "cam"].includes(actionType)) {
    icon = "videocam";
    action = "Record";
  } else if (["android_flashlight", "motion_flashlight", "flashlight"].includes(actionType)) {
    icon = "bolt";
    title = "Camera Flashlight";
    action = "Flash";
  } else if (["android_white_screen", "motion_screen", "white_screen"].includes(actionType)) {
    icon = "mobile_screen";
    title = "White Screen";
    action = "Show";
  }

  const autoOff = automation?.autoOff === true && timer ? ` · Off after ${timer}` : "";

  return `
    <button
      class="settings-item settings-automation-item dashboard-device-automation-item"
      type="button"
      data-dashboard-action="edit-device-automation"
      data-automation-id="${escAttr(automation?.automationID || "")}"
      data-device-id="${escAttr(menuDeviceID || automation?.deviceID || "")}"
    >
      ${window.dashboardIconHtml(icon)}
      <span class="settings-automation-copy">
        <span class="settings-automation-title">${esc(title)}</span>
        <span class="settings-automation-subtitle">${esc(`${trigger} → ${action}${autoOff}`)}</span>
      </span>
    </button>
  `;
}

window.renderDashboardDeviceAutomationSettings = function (deviceID) {
  const modal = document.getElementById("clientMenuModal");
  const body = document.getElementById("clientMenuBody");

  if (!modal || !body || String(modal.dataset.deviceId || "") !== String(deviceID || "")) return;

  const sourceIDs = new Set(
    (window.dashboardMatterRelatedDeviceIDs?.(deviceID, S.currentClients || []) || [deviceID])
      .map(value => String(value || "").trim())
      .filter(Boolean)
  );
  const automations = (S.currentAutomations || []).filter(item => (
    item?.type === "device_automation" &&
    sourceIDs.has(String(item?.deviceID || "").trim())
  ));

  body.querySelectorAll(".modal-section-title").forEach(title => {
    if (String(title.textContent || "").trim() === "Automations") {
      title.textContent = "Automation";
    }
  });

  body.querySelectorAll('[data-dashboard-action="show-automation-settings"], [data-action="show-automation-settings"]').forEach(button => {
    const triggerGroup = String(button.dataset.triggerGroup || "").trim().toLowerCase();
    const container = button.closest(".client-menu-actions");

    if (!container) return;

    container.classList.add("dashboard-device-automation-menu");
    container.querySelectorAll(".dashboard-device-automation-item").forEach(item => item.remove());

    const matches = automations.filter(item => (
      !triggerGroup || dashboardDeviceAutomationTriggerGroup(item.trigger) === triggerGroup
    ));

    matches.forEach(item => button.insertAdjacentHTML("beforebegin", dashboardDeviceAutomationCardHtml(item, deviceID)));
    button.hidden = matches.length > 0;
  });
};

window.syncDashboardDeviceAutomationSettings = async function (deviceID) {
  try {
    const res = await dashboardFetch("/api/automations");
    const data = await res.json();

    if (res.ok && data.ok !== false) {
      S.currentAutomations = Array.isArray(data.automations) ? data.automations : [];
    }
  } catch (error) {
    console.warn("[automations] device settings refresh failed", error);
  }

  window.renderDashboardDeviceAutomationSettings?.(deviceID);
};

window.editDashboardDeviceAutomation = async function (automationID, deviceID = "") {
  const automation = (S.currentAutomations || []).find(item => (
    item?.type === "device_automation" &&
    String(item?.automationID || "") === String(automationID || "")
  ));

  if (!automation) return;

  const sourceDeviceID = String(automation.deviceID || deviceID || "").trim();
  const menuDeviceID = String(deviceID || sourceDeviceID).trim();
  const trigger = String(automation.trigger || "").trim().toLowerCase();
  const savedActionType = dashboardHomeArmingActionMeta(automation.actionType).actionType;
  const actionType = dashboardHomeArmingActionUsesSourceCamera(savedActionType)
    ? "device_on"
    : savedActionType;
  const savedTargetID = String(automation.targetID || automation.targetDeviceID || "").trim();
  const targetID = dashboardHomeArmingActionUsesSourceCamera(savedActionType)
    ? `${sourceDeviceID}|${savedActionType}`
    : savedTargetID;
  const threshold = automation.threshold === "" || automation.threshold == null
    ? null
    : Number(automation.threshold);
  const mode = dashboardHomeCurrentArmMode();

  window.ensureDashboardHomeArmingModalShells?.();
  await refreshWavData?.();

  dashboardHomeArmingRouteScope = "automation";
  dashboardHomeArmingEditingAutomationID = String(automation.automationID || "");
  dashboardHomeArmingEditingDeviceID = menuDeviceID;
  dashboardHomeArmingPendingSourceIDs = [sourceDeviceID];
  dashboardHomeArmingPendingTriggerGroup = dashboardDeviceAutomationTriggerGroup(trigger);
  dashboardHomeArmingPendingTriggerIDs = [`${sourceDeviceID}|${trigger}`];
  dashboardHomeArmingDraft = {
    mode,
    actionType,
    triggerIDs: [...dashboardHomeArmingPendingTriggerIDs],
    targetIDs: actionType === "sound"
      ? []
      : [actionType === "notification"
        ? String(automation.targetKeyDeviceID || automation.targetDeviceID || "").trim()
        : targetID].filter(Boolean),
    environmentThresholds: Number.isFinite(threshold)
      ? { [`${sourceDeviceID}|${trigger}`]: threshold }
      : {},
    soundFile: String(automation.filename || "").trim(),
    soundVolumePercent: dashboardHomeArmingSoundVolumePercent(automation.soundVolume ?? 100),
    notificationTitle: String(automation.title || "").trim(),
    notificationMessage: String(automation.message || "").trim(),
    post: {
      timerSeconds: String(automation.autoOffSeconds || automation.durationSeconds || automation.repeatSeconds || "").trim(),
      minimumVideoSeconds: String(automation.minimumDurationSeconds || "").trim(),
      cooldownSeconds: String(automation.cooldownSeconds || "").trim(),
      autoOff: automation.autoOff === true,
      repeat: automation.repeat !== false,
      retrigger: automation.retrigger !== false,
      actionType
    }
  };

  window.hideClientMenuModal?.();
  renderDashboardHomeArmingPostTriggerStep(mode, actionType);

  const modal = document.getElementById("dashboardHomeArmingActionModal");
  if (!modal) return;

  modal.dataset.returnModalId = "";
  modal.hidden = false;
  document.body.classList.add("modal-open");
};

async function dashboardReturnToDeviceAutomationSettings(deviceID) {
  dashboardHomeArmingDraft = null;
  dashboardHomeArmingEditingAutomationID = "";
  dashboardHomeArmingEditingDeviceID = "";
  window.hideDashboardHomeArmingActionPicker?.();

  if (!deviceID) return;

  await window.showDashboardClientMenu?.(deviceID);
}

window.showAutomationSettings = async function (initial = {}) {
  const options = typeof initial === "string"
    ? { deviceID: initial }
    : (initial && typeof initial === "object" ? initial : {});
  const deviceID = String(options.deviceID || "").trim();

  if (!deviceID) {
    hideSettingsModal?.();
    await window.showAutomationsModal?.();
    return;
  }

  const sourceIDs = window.dashboardMatterRelatedDeviceIDs?.(
    deviceID,
    S.currentClients || []
  ) || [deviceID];

  await refreshWavData?.();

  window.hideClientMenuModal?.();
  window.showDashboardHomeArmingActionPicker?.(
    dashboardHomeCurrentArmMode(),
    sourceIDs,
    options.triggerGroup || "",
    "automation"
  );
};

window.shutdownServer = async function () {
  if (confirm("Shutdown KotiBot Server?")) {
    await fetch("/api/shutdown", { method: "POST" });
    alert("Server shutting down...");
  }
};

window.removeClient = async function (deviceID) {
  if (!confirm("Remove this client?")) return;

  const reqBody = { deviceID: deviceID };
  let res;
  let rawText;

  try {
    res = await dashboardFetch("/api/remove-client", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reqBody)
    });

    rawText = await res.text();

  } catch (err) {
    console.error("[removeClient] request failed:", err);
    alert("Remove client request failed. Check console.");
    return;
  }

  let payload = {};

  try {
    payload = rawText ? JSON.parse(rawText) : {};
  } catch (err) {
    console.error("[removeClient] JSON parse failed:", err);
    alert("Remove client returned non-JSON response. Check console.");
    return;
  }

  if (!res.ok || !payload.ok) {
    console.error("[removeClient] remove failed =", payload);
    alert(payload.error || "Failed to remove client");
    return;
  }

  window.hideClientMetaModal?.(false);
  window.hideClientMenuModal?.();

  const [routesResult, statusResult] = await Promise.allSettled([
    refreshRoutes(),
    refreshStatusData({ forceNetwork: true })
  ]);

  if (routesResult.status === "rejected") {
    console.warn("[removeClient] post-remove route refresh failed:", routesResult.reason);
  }

  if (statusResult.status === "fulfilled") {
    requestDashboardRenderSafe(statusResult.value);
  } else {
    console.warn("[removeClient] post-remove status refresh failed:", statusResult.reason);
  }
};

window.toggleRouteLink = async function (event, fromDeviceId, fromOutput, toKind, toDeviceId, toInput) {
  event.stopPropagation();

  const fromClient = getClientByDeviceId(fromDeviceId);
  const toClient = getClientByDeviceId(toDeviceId);

  const fromRole = clientHasRole(fromClient, "DSS") ? "DSS" : clientRolesOf(fromClient)[0] || "";
  const toRole = toKind === "client"
    ? (
        toInput === "record" && clientHasRole(toClient, "CAM")
          ? "CAM"
          : clientRolesOf(toClient)[0] || ""
      )
    : "";

  const linked = routeExists(fromDeviceId, toDeviceId, toKind, toInput);

  const payload = {
    from_device_id: fromDeviceId,
    from_clientRole: fromRole,
    from_output: fromOutput,
    to_kind: toKind,
    to_device_id: toDeviceId,
    to_clientRole: toRole,
    to_input: toInput
  };

  if (linked) {
    await dashboardFetch("/api/routes", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(r => r.json());
  } else {
    await postJson("/api/routes", payload);
  }

  await refreshRoutes();
  await refreshStatusData();
};

window.setSystemArmed = async function (armed) {
  const next = !!armed;
  const armBtn = document.getElementById("asideArmLogoToggle");

  if (armBtn) {
    armBtn.classList.remove("arming");
    void armBtn.offsetWidth;
    armBtn.classList.add("arming");
    armBtn.dataset.armed = next ? "true" : "false";
    armBtn.title = next ? "Disarm System" : "Arm System";
    armBtn.setAttribute("aria-label", armBtn.title);
  }

  const res = await dashboardFetch("/api/system-arm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ armed: next ? 1 : 0 })
  });

  const data = await res.json();
  requestDashboardRenderSafe(data);

  const renderedArmBtn = document.getElementById("asideArmLogoToggle");
  if (renderedArmBtn) {
    renderedArmBtn.classList.remove("arming");
    void renderedArmBtn.offsetWidth;
    renderedArmBtn.classList.add("arming");
    window.setTimeout(() => {
      document.getElementById("asideArmLogoToggle")?.classList.remove("arming");
    }, 780);
  }
};

window.toggleSystemArmed = async function () {
  await setSystemArmed(!S.serverState?.armed);
};

window.toggleDebug = function () {
  setDashboardInfoShown(!S.debugMode);
};

function refreshRestoredClientReturnModal(modalID) {
  const restoredModal = document.getElementById(modalID);

  if (!restoredModal) return;

  if (modalID === "matterActionModal") {
    const deviceID = String(restoredModal.dataset.deviceId || "").trim();

    if (deviceID) {
      window.showMatterActionSettings?.(deviceID);
    }

    return;
  }

  if (modalID === "tapoLightModal") {
    window.renderMatterRoomActionsSection?.(restoredModal.dataset.tapoRoom || "");
  }
}

window.hideClientMenuModal = function () {
  const modal = document.getElementById("clientMenuModal");
  if (!modal) return;

  if (window.clientMenuPreviewRefreshTimer) {
    clearInterval(window.clientMenuPreviewRefreshTimer);
    window.clientMenuPreviewRefreshTimer = null;
  }

  if (modal.dataset.deviceId) {
    window.setClientMenuPreviewViewerState?.(modal.dataset.deviceId, false, true);
  }

  const returnModalIDs = String(modal.dataset.returnModalIds || "")
    .split(",")
    .map(item => item.trim())
    .filter(Boolean);

  window.clientMenuPreviewDeviceId = "";
  modal.hidden = true;
  modal.dataset.deviceId = "";
  modal.dataset.menuKind = "";
  modal.dataset.returnModalIds = "";

  let restoredModal = dashboardRestoreParentModalFromSubmodal(modal);

  returnModalIDs.forEach(modalID => {
    const returnModal = document.getElementById(modalID);
    if (!returnModal) return;

    returnModal.hidden = false;
    restoredModal = true;
    refreshRestoredClientReturnModal(modalID);
  });

  if (restoredModal) {
    document.body.classList.add("modal-open");
  } else {
    document.body.classList.remove("modal-open");
  }
};

window.showDashboardClientMenu = function (deviceID) {
  closeAllMenus();

  const modal = document.getElementById("clientMenuModal");
  if (!modal) return;

  modal.dataset.deviceId = deviceID;
  modal.dataset.menuKind = "client";
  modal.hidden = false;
  document.body.classList.add("modal-open");

  if (window.dashboardClientIsMatter?.(getClientByDeviceId(deviceID)) && typeof window.showMatterClientMenu === "function") {
    window.showMatterClientMenu(deviceID);
    return window.syncDashboardDeviceAutomationSettings?.(deviceID);
  }

  renderDashboardClientMenu(deviceID);
  window.syncClientMenuCameraPreviewViewer?.();
  return window.syncDashboardDeviceAutomationSettings?.(deviceID);
};

window.renderOpenClientMenu = function () {
  const clientModal = document.getElementById("clientMenuModal");
  if (clientModal && !clientModal.hidden && clientModal.dataset.deviceId) {
    if (clientModal.dataset.menuKind === "matter" && typeof window.renderMatterClientMenu === "function") {
      window.renderMatterClientMenu(clientModal.dataset.deviceId);
      window.renderDashboardDeviceAutomationSettings?.(clientModal.dataset.deviceId);
    } else {
      renderDashboardClientMenu(clientModal.dataset.deviceId);
      window.syncClientMenuCameraPreviewViewer?.();
    }
  }
};

window.renderDashboardClientMenu = function (deviceID) {
  const modal = document.getElementById("clientMenuModal");
  const title = document.getElementById("clientMenuTitle");
  const body = document.getElementById("clientMenuBody");
  if (!modal || !body) return;

  const client = getClientByDeviceId(deviceID);
  if (!client) {
    hideClientMenuModal();
    return;
  }

  if (window.dashboardClientIsMatter?.(client) && typeof window.renderMatterClientMenu === "function") {
    window.renderMatterClientMenu(deviceID);
    window.renderDashboardDeviceAutomationSettings?.(deviceID);
    return;
  }

  modal.dataset.menuKind = "client";

  const roles = roleSetOfClient(client);
  const isProvisioned = !!client.provisioned;
  const detectedRoles = isProvisioned ? new Set() : detectedRoleSetOfClient(client);
  const provisionRoles = isProvisioned ? roles : detectedRoles;
  const hasCam = provisionRoles.has("CAM");
  const hasDss = provisionRoles.has("DSS");
  const canDss = isProvisioned || hasDssHardware(client) || hasDss;
  const selectedCamera = String(client.selected_camera || client.selectedCamera || "back").toLowerCase();
  const switchLensLabel = selectedCamera === "front" ? "Switch to Back Lens" : "Switch to Front Lens";
  const motionSensitivity = motionSensitivityFromThreshold(client.motion_detection_threshold || client.motionDetectionThreshold || 18);
  const previewUrl = clientMenuPreviewUrl(client);
  const manufacturer = clientMenuManufacturer(client);
  const tapoKind = String(client.tapo_child_kind || client.tapo_kind || "").trim().toLowerCase();
  const tapoSource = String(client.source || "").trim().toLowerCase();
  const tapoDetectedRole = String(client.detectedRole || "").trim().toUpperCase();
  const isTapoProvisionClient = (
    !isProvisioned &&
    (
      tapoSource === "tapo" ||
      tapoDetectedRole === "TAPO" ||
      String(deviceID).startsWith("tapo:")
    )
  );
  const isControlProvisionClient = (
    !isProvisioned &&
    !isTapoProvisionClient &&
    provisionRoles.has("KEY")
  );
  const isMonitorProvisionClient = (
    !isProvisioned &&
    !isTapoProvisionClient &&
    (provisionRoles.has("CAM") || provisionRoles.has("DSS"))
  );
  const provisionRoleValue = isTapoProvisionClient
    ? "TAPO"
    : ["KEY", "CAM", "DSS"]
      .filter(role => provisionRoles.has(role))
      .join(",");
  const tapoKindLabels = {
    bulb: "Bulb",
    lightstrip: "Lightstrip",
    plug: "Plug",
    outlet_extender: "Extender",
    hub: "Hub",
    camera: "Camera",
    vacuum: "Vac"
  };
  const tapoSetupLabel = `Tapo ${tapoKindLabels[tapoKind] || "Device"}`;
  const subtitle = isTapoProvisionClient
    ? tapoSetupLabel
    : manufacturer ? `Android - ${manufacturer}` : "Android";
  const provisionTitle = isTapoProvisionClient
    ? "New Tapo Device"
    : isControlProvisionClient
      ? "New KotiBot Control Client"
      : isMonitorProvisionClient
        ? "New KotiBot Monitor Client"
        : "New Android Client";
  const subtitleEl = document.getElementById("clientMenuSubtitle");

  if (title) {
    title.textContent = isProvisioned
      ? client.clientName || "Client Menu"
      : provisionTitle;
  }

  if (subtitleEl) subtitleEl.textContent = subtitle;

  const editToggle = document.getElementById("clientMenuEditToggle");
  if (editToggle) {
    editToggle.hidden = !isProvisioned;
    editToggle.classList.remove("active");
    editToggle.title = "Edit device details";
    editToggle.setAttribute("aria-label", editToggle.title);
    editToggle.removeAttribute("aria-expanded");
  }

  body.innerHTML = `
    ${!isProvisioned ? `
      <div class="modal-section">
        <label class="client-menu-inline-field" for="p_name_${escAttr(deviceID)}">
          <span class="client-menu-label">Name</span>
          <input
            class="form-input client-menu-input"
            id="p_name_${escAttr(deviceID)}"
            value="${escAttr(client.clientName || client.client_name || "")}"
            placeholder="Enter a client name"
            maxlength="12"
          >
        </label>

        ${isControlProvisionClient ? "" : `
          <label class="client-menu-inline-field" for="p_zone_${escAttr(deviceID)}">
            <span class="client-menu-label">Zone</span>
            <input
              class="form-input client-menu-input"
              id="p_zone_${escAttr(deviceID)}"
              list="p_zone_list_${escAttr(deviceID)}"
              value="${escAttr(client.zone_name || "")}"
              placeholder="Room / zone / area"
              maxlength="40"
              required
              data-dashboard-dblclick="open-zone-list"
            >
          </label>

          <datalist id="p_zone_list_${escAttr(deviceID)}">
            ${renderClientMenuZoneOptions()}
          </datalist>
        `}

        <input
          type="hidden"
          id="p_role_${escAttr(deviceID)}"
          value="${provisionRoleValue}"
        >

        ${isMonitorProvisionClient ? `
          <div class="prov-role-buttons client-menu-provision-role-buttons" data-device-id="${escAttr(deviceID)}">
            <button
              type="button"
              class="prov-role-btn ${provisionRoles.has("CAM") ? "active" : ""}"
              id="p_btn_cam_${escAttr(deviceID)}"
              data-action="toggle-provision"
              data-device-id="${escAttr(deviceID)}"
              data-role="CAM"
              aria-pressed="${provisionRoles.has("CAM") ? "true" : "false"}">
              Security Camera
            </button>

            <button
              type="button"
              class="prov-role-btn ${provisionRoles.has("DSS") ? "active" : ""}"
              id="p_btn_door_${escAttr(deviceID)}"
              data-action="toggle-provision"
              data-device-id="${escAttr(deviceID)}"
              data-role="DSS"
              aria-pressed="${provisionRoles.has("DSS") ? "true" : "false"}"
              ${!canDss ? 'disabled aria-disabled="true" title="No DSS hardware detected"' : ""}>
              Door Swing Sensor
            </button>
          </div>
        ` : ""}

        <div class="client-menu-actions client-menu-meta-actions">
          <button
            class="client-menu-btn"
            type="button"
            id="p_create_${escAttr(deviceID)}"
            data-action="provision-client"
            data-device-id="${escAttr(deviceID)}">
            ${window.dashboardIconHtml("add")}
            <span>${isTapoProvisionClient ? "Add Tapo Device" : "Create Client"}</span>
          </button>

          <button class="client-menu-btn danger" type="button" data-action="remove-client" data-device-id="${escAttr(deviceID)}">
            ${isTapoProvisionClient ? "Remove Device" : "Remove Client"}
          </button>
        </div>
      </div>
    ` : ""}

    ${isProvisioned ? `
      <div class="modal-section">
        <div class="modal-section-head">
          <label class="modal-section-title">
            <input
              type="checkbox"
              ${hasCam ? "checked" : ""}
              data-dashboard-change="toggle-client-role" data-device-id="${escAttr(deviceID)}" data-role="CAM">
            <span>Camera</span>
          </label>

          <div class="modal-head-actions" ${hasCam ? "" : "hidden"}>
            <span class="client-menu-label">
              ${selectedCamera === "front" ? "Front Lens" : "Back Lens"}
            </span>

            <button
              class="modal-close"
              type="button"
              title="${escAttr(switchLensLabel)}"
              aria-label="${escAttr(switchLensLabel)}"
              data-dashboard-action="toggle-lens"
              data-device-id="${escAttr(deviceID)}">
              ${window.dashboardIconHtml("rotate")}
            </button>
          </div>
        </div>

        <div class="client-menu-camera-options" ${hasCam ? "" : "hidden"}>
          <div class="camera-menu-preview">
            ${previewUrl
              ? `<img src="${escAttr(previewUrl)}" alt="Camera preview">`
              : `<div class="client-menu-row"><span class="client-menu-subtle">No live preview available.</span></div>`
            }
          </div>

          <div class="client-menu-motion-options">
            <div class="client-menu-motion-subsection">
              <div class="client-menu-range-head">
                <div class="modal-section-title">Motion Sensitivity</div>
                <div class="client-menu-range-value">${motionSensitivity}</div>
              </div>

              <label class="client-menu-range-row">
                <input
                  class="client-menu-range"
                  type="range"
                  min="1"
                  max="10"
                  step="1"
                  value="${motionSensitivity}"
                  data-dashboard-change="set-camera-motion-sensitivity"
                  data-device-id="${escAttr(deviceID)}">

                <span class="client-menu-range-scale">
                  <span>Low</span>
                  <span>High</span>
                </span>
              </label>
            </div>
          </div>

          <div class="client-menu-motion-subsection">
            <div class="modal-section-title">Automation</div>
            <div class="client-menu-actions">
              <button
                class="client-menu-btn"
                type="button"
                data-dashboard-action="show-automation-settings"
                data-device-id="${escAttr(deviceID)}"
                data-trigger-group="motion">
                ${window.dashboardIconHtml("add")}
                <span>Add Automation</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="modal-section">
        <label class="modal-section-title">
          <input
            type="checkbox"
            ${hasDss ? "checked" : ""}
            ${canDss ? "" : "disabled"}
            data-dashboard-change="toggle-client-role" data-device-id="${escAttr(deviceID)}" data-role="DSS">
          <span>Door Swing Sensor</span>
        </label>

        <div class="client-menu-content" ${hasDss ? "" : "hidden"}>
          ${canDss ? "" : `<div class="client-menu-subtle">Door Swing Sensor unavailable: no DSS hardware detected.</div>`}

          <div class="client-menu-actions">
            <button
              class="client-menu-btn"
              type="button"
              data-dashboard-action="show-automation-settings"
              data-device-id="${escAttr(deviceID)}"
              data-trigger-group="door">
              ${window.dashboardIconHtml("add")}
              <span>Add Automation</span>
            </button>
          </div>
        </div>
      </div>

    ` : ""}
  `;
};

window.hideAudioModal = function () {
  const modal = document.getElementById("audioModal");
  if (!modal) return;

  modal.hidden = true;
  document.body.classList.remove("modal-open");

  const body = document.getElementById("audioModalBody");
  if (body) body.innerHTML = "";
};

window.renameClient = async function (deviceId) {
  const client = getClientByDeviceId(deviceId);
  const currentName = client?.clientName || "";

  const nextName = prompt("New client name:", currentName);
  if (nextName === null) return;

  const trimmed = nextName.trim();
  if (!trimmed) return;

  const clientRole = clientRolesOf(client)[0] || "UNP";

  await postJson("/api/client-command", {
    deviceID: deviceId,
    clientRole,
    newName: trimmed,
    clientName: trimmed
  });

  const data = await refreshStatusData();
  requestDashboardRenderSafe(data);

  if (document.getElementById("clientMenuModal")?.hidden === false) {
    renderOpenClientMenu?.();
  }
};

let clientSaveSuccessHoldTimer = 0;
let clientSaveSuccessFadeTimer = 0;

function clientSaveSuccessDeviceLabel(client) {
  const manufacturer = String(
    client?.manufacturer ||
    client?.matter_vendor_name ||
    client?.device_manufacturer ||
    client?.android_manufacturer ||
    client?.brand ||
    ""
  ).trim();
  const device = String(
    client?.matter_product_name ||
    client?.model ||
    client?.device_model ||
    client?.android_model ||
    client?.matter_node_label ||
    "Device"
  ).trim();

  return manufacturer && device && manufacturer.toLowerCase() !== device.toLowerCase()
    ? `${manufacturer} - ${device}`
    : manufacturer || device;
}

window.showClientSaveSuccessModal = function (client, name, zoneName) {
  let successModal = document.getElementById("clientSaveSuccessModal");

  if (!successModal) {
    document.body.insertAdjacentHTML("beforeend", `
      <div id="clientSaveSuccessModal" class="modal client-save-success-modal" hidden>
        <div class="modal-shell client-save-success-shell" role="status" aria-live="polite">
          <div id="clientSaveSuccessDevice" class="client-save-success-device"></div>
          <div class="client-save-success-copy">Successfully saved as</div>
          <div id="clientSaveSuccessName" class="client-save-success-name"></div>
          <div id="clientSaveSuccessZone" class="client-save-success-zone"></div>
        </div>
      </div>
    `);

    successModal = document.getElementById("clientSaveSuccessModal");
  }

  clearTimeout(clientSaveSuccessHoldTimer);
  clearTimeout(clientSaveSuccessFadeTimer);

  const settingsModal = document.getElementById("clientMenuModal");
  if (settingsModal) settingsModal.hidden = true;

  const metaModal = document.getElementById("clientMetaModal");
  if (metaModal) {
    metaModal.hidden = true;
    metaModal.dataset.deviceId = "";
    metaModal.dataset.returnModalId = "";
  }

  clientMetaContext = null;

  document.getElementById("clientSaveSuccessDevice").textContent = clientSaveSuccessDeviceLabel(client);
  document.getElementById("clientSaveSuccessName").textContent = name;
  document.getElementById("clientSaveSuccessZone").textContent = zoneName;

  successModal.classList.remove("is-fading");
  successModal.hidden = false;
  document.body.classList.add("modal-open");

  clientSaveSuccessHoldTimer = window.setTimeout(() => {
    successModal.classList.add("is-fading");

    clientSaveSuccessFadeTimer = window.setTimeout(() => {
      successModal.hidden = true;
      successModal.classList.remove("is-fading");

      if (!document.querySelector(".modal:not([hidden])")) {
        document.body.classList.remove("modal-open");
      }
    }, 300);
  }, 1500);
};

window.saveClientMenuMeta = async function () {
  const metaModal = document.getElementById("clientMetaModal");
  const settingsModal = document.getElementById("clientMenuModal");
  const deviceID = metaModal?.dataset.deviceId || settingsModal?.dataset.deviceId || "";

  const name = document.getElementById("clientMenuNameInput")?.value.trim() || "";
  const zoneName = document.getElementById("clientMenuZoneInput")?.value.trim() || "";

  if (!deviceID || !name) return;

  if (typeof clientMetaContext?.save === "function") {
    const saved = await clientMetaContext.save({ clientName: name, zoneName });

    if (saved !== false) {
      window.hideClientMetaModal?.();
    }

    return;
  }

  const client = getClientByDeviceId(deviceID);
  if (!client) return;

  const clientRole = clientRolesOf(client)[0] || "CAM";

  const relatedMatterDeviceIDs = window.dashboardMatterRelatedDeviceIDs?.(deviceID, S.currentClients || []) || [deviceID];
  const targetDeviceIDs = window.dashboardClientIsMatter?.(client) ? relatedMatterDeviceIDs : [deviceID];

  await Promise.all(targetDeviceIDs.map(targetDeviceID => postJson("/api/client-command", {
    deviceID: targetDeviceID,
    clientRole,
    newName: name,
    clientName: name,
    zoneName,
    zone_name: zoneName
  })));

  const data = await refreshStatusData();
  targetDeviceIDs.forEach(targetDeviceID => {
    patchClientByDeviceId(
      targetDeviceID,
      { clientName: name, zone_name: zoneName },
      data
    );
  });
  requestDashboardRenderSafe(data);
  window.showClientSaveSuccessModal(client, name, zoneName);
};

window.cameraVideoModalRefreshTimer = window.cameraVideoModalRefreshTimer || null;
window.cameraVideoModalViewerHeartbeatTimer = window.cameraVideoModalViewerHeartbeatTimer || null;
window.cameraVideoModalDeviceId = window.cameraVideoModalDeviceId || "";

window.setCameraModalViewerState = function (deviceID, active, useBeacon = false) {
  const cleanDeviceID = String(deviceID || "").trim();
  if (!cleanDeviceID) return;

  const payload = JSON.stringify({
    deviceID: cleanDeviceID,
    viewerId: `${window.previewViewerId || "dash"}_modal`,
    active: !!active
  });

  if (useBeacon && navigator.sendBeacon) {
    navigator.sendBeacon(
      "/api/preview-viewer",
      new Blob([payload], { type: "application/json" })
    );
    return;
  }

  fetch("/api/preview-viewer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
    keepalive: true
  }).catch(() => {});
};

window.hideCameraVideoModal = function () {
  const modal = document.getElementById("cameraVideoModal");
  const player = document.getElementById("cameraVideoPlayer");
  const deviceID = window.cameraVideoModalDeviceId || "";

  if (window.cameraVideoModalRefreshTimer) {
    clearInterval(window.cameraVideoModalRefreshTimer);
    window.cameraVideoModalRefreshTimer = null;
  }

  if (window.cameraVideoModalViewerHeartbeatTimer) {
    clearInterval(window.cameraVideoModalViewerHeartbeatTimer);
    window.cameraVideoModalViewerHeartbeatTimer = null;
  }

  if (deviceID) {
    window.setCameraModalViewerState(deviceID, false, true);
  }

  window.cameraVideoModalDeviceId = "";

  if (player) {
    player.removeAttribute("src");
  }

  if (modal) modal.hidden = true;
  document.body.classList.remove("modal-open");
};

window.openCameraVideo = function (deviceId) {
  const deviceID = String(deviceId || "").trim();
  if (!deviceID) return;

  const modal = document.getElementById("cameraVideoModal");
  const player = document.getElementById("cameraVideoPlayer");
  const title = document.getElementById("cameraVideoModalTitle");

  if (!modal || !player) return;

  const client = (S.currentClients || []).find(c => c.deviceID === deviceID);
  const label = client?.clientName || "Android Camera";
  const videoUrl = `/video_feed/${encodeURIComponent(deviceID)}`;

  if (window.cameraVideoModalRefreshTimer) {
    clearInterval(window.cameraVideoModalRefreshTimer);
    window.cameraVideoModalRefreshTimer = null;
  }

  if (window.cameraVideoModalViewerHeartbeatTimer) {
    clearInterval(window.cameraVideoModalViewerHeartbeatTimer);
    window.cameraVideoModalViewerHeartbeatTimer = null;
  }

  if (window.cameraVideoModalDeviceId && window.cameraVideoModalDeviceId !== deviceID) {
    window.setCameraModalViewerState(window.cameraVideoModalDeviceId, false);
  }

  window.cameraVideoModalDeviceId = deviceID;
  window.setCameraModalViewerState(deviceID, true);

  if (title) {
    title.textContent = `${label} Live View`;
  }

  const refreshFrame = () => {
    player.src = `${videoUrl}?modal=${Date.now()}`;
  };

  refreshFrame();

  window.cameraVideoModalRefreshTimer = setInterval(() => {
    refreshFrame();
  }, window.cameraVideoModalRefreshMs || 1500);

  window.cameraVideoModalViewerHeartbeatTimer = setInterval(() => {
    window.setCameraModalViewerState(deviceID, true);
  }, window.cameraVideoModalViewerHeartbeatMs || 4000);

  modal.hidden = false;
  document.body.classList.add("modal-open");
};

window.showStoredVideos = async function (deviceId) {
  const files = S.currentVideosByDeviceId?.[deviceId] || [];
  if (!files.length) {
    alert("No stored videos for this client yet.");
    return;
  }

  if (files.length === 1) {
    window.open(files[0].url, "_blank", "noopener");
    return;
  }

  const options = files.map((f, i) => `${i + 1}. ${f.name}`).join("\n");
  const pick = prompt(`Stored videos:\n\n${options}\n\nOpen which number?`, "1");

  if (pick === null) return;

  const index = Number(pick) - 1;
  if (!Number.isInteger(index) || index < 0 || index >= files.length) {
    alert("Invalid selection.");
    return;
  }

  window.open(files[index].url, "_blank", "noopener");
};

window.setDashboardGroupByRoom = function () {
  S.groupByRoom = true;
  document.body.dataset.groupByRoom = "1";
  localStorage.setItem("dashboardGroupByRoom", "1");

  if (S.currentClients) {
    window.requestDashboardRenderSafe?.({ clients: S.currentClients, server: S.serverState || {} });
  }

  window.syncServerViewControls?.();
};

window.toggleDashboardGroupByRoom = function () {
  setDashboardGroupByRoom(true);
};

window.setDashboardInfoShown = function (shown) {
  const isShown = !!shown;

  S.debugMode = isShown;
  document.body.dataset.cardDebug = isShown ? "on" : "off";
  document.body.classList.toggle("debug-off", !isShown);

  localStorage.setItem("cardDebugInfo", isShown ? "on" : "off");
  localStorage.setItem("dashboardInfoShown", isShown ? "1" : "0");
  localStorage.setItem("debugMode", isShown ? "1" : "0");

  applyCardDebugVisibility?.();
  window.syncServerViewControls?.();

  if (S.groupByRoom && S.currentClients) {
    window.requestDashboardRenderSafe?.({ clients: S.currentClients, server: S.serverState || {} });
  }
};

window.toggleDashboardInfo = function () {
  setDashboardInfoShown(document.body.classList.contains("debug-off"));
};

function dashboardCleanTextSizeMode(mode) {
  return String(mode || "").toLowerCase() === "accessible" ? "accessible" : "normal";
}

window.setDashboardTextSize = function (mode) {
  const clean = dashboardCleanTextSizeMode(mode);

  document.body.dataset.dashboardTextSize = clean;
  localStorage.setItem("dashboardTextSize", clean);
  syncDashboardTextSizeControls?.();
};

window.toggleDashboardTextSize = function () {
  const current = dashboardCleanTextSizeMode(document.body.dataset.dashboardTextSize || localStorage.getItem("dashboardTextSize"));
  setDashboardTextSize(current === "accessible" ? "normal" : "accessible");
};

window.syncDashboardTextSizeControls = function () {
  const clean = dashboardCleanTextSizeMode(document.body.dataset.dashboardTextSize || localStorage.getItem("dashboardTextSize"));
  const btn = document.getElementById("dashboardTextSizeToggle");
  const label = document.getElementById("dashboardTextSizeToggleLabel");
  const title = clean === "accessible" ? "Text Size: Accessible" : "Text Size: Normal";

  document.body.dataset.dashboardTextSize = clean;

  if (btn) {
    btn.classList.remove("active");
    btn.title = title;
    btn.setAttribute("aria-label", title);
  }

  if (label) {
    label.textContent = clean === "accessible" ? "Accessible" : "Normal Text";
  }
};

function dashboardFirstServerValue(server, keys) {
  for (const key of keys) {
    const value = server?.[key];

    if (Array.isArray(value) && value.length) return value.join(", ");
    if (value !== undefined && value !== null && String(value).trim() !== "") return value;
  }

  return "";
}

function dashboardFormatDurationSeconds(value) {
  const seconds = Math.floor(Number(value || 0));

  if (!Number.isFinite(seconds) || seconds <= 0) return "";

  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${Math.max(1, minutes)}m`;
}

function dashboardServerUptimeText(server) {
  const raw = dashboardFirstServerValue(server, [
    "uptime_text",
    "server_uptime_text",
    "uptime_human",
    "uptime_label",
    "server_uptime",
    "process_uptime",
    "uptime"
  ]);

  if (typeof raw === "string" && raw.trim() && !/^\d+(\.\d+)?$/.test(raw.trim())) {
    return raw.trim();
  }

  const seconds = dashboardFirstServerValue(server, [
    "uptime_seconds",
    "server_uptime_seconds",
    "process_uptime_seconds",
    "uptime_sec",
    "uptime_s",
    "server_uptime",
    "process_uptime",
    "uptime"
  ]);

  return dashboardFormatDurationSeconds(seconds) || "—";
}

function dashboardServerIpText(server) {
  const ip = dashboardFirstServerValue(server, [
    "server_ip",
    "server_ip_address",
    "local_ip",
    "lan_ip",
    "host_ip",
    "ip_address",
    "local_address",
    "host_address",
    "ip",
    "host",
    "address"
  ]);

  return String(ip || "—").trim() || "—";
}

window.syncSettingsServerInfo = function () {
  const server = S.serverState || S.server || {};
  const uptime = document.getElementById("settingsServerUptime");
  const ip = document.getElementById("settingsServerIp");

  if (uptime) uptime.textContent = dashboardServerUptimeText(server);
  if (ip) ip.textContent = dashboardServerIpText(server);
};

function dashboardBluetoothSummaryText(status) {
  if (!status || status.ok !== true) {
    return "Unknown";
  }

  if (status.adapter?.powered !== true) {
    return "Off";
  }

  const deviceCount = Array.isArray(status.paired)
    ? status.paired.length
    : 0;

  if (!deviceCount) {
    return "On";
  }

  return `On - ${deviceCount} device${deviceCount === 1 ? "" : "s"}`;
}

function dashboardCountLabel(count, singular, plural = `${singular}s`) {
  const value = Number(count) || 0;
  return `${value} ${value === 1 ? singular : plural}`;
}

function dashboardMatterSummaryText() {
  const matterClients = (S.currentClients || []).filter(
    client => client?.source === "matter"
  );

  if (
    !matterClients.length ||
    !matterClients.some(client => client?.stale !== true)
  ) {
    return "No connection";
  }

  const hubCount = new Set(
    matterClients
      .map(client => String(client?.matter_node_id || "").trim())
      .filter(Boolean)
  ).size;

  const deviceCount = new Set(
    matterClients
      .map(client => {
        const nodeID = String(client?.matter_node_id || "").trim();
        const endpoint = String(client?.matter_endpoint || "").trim();

        return nodeID && endpoint
          ? `${nodeID}:${endpoint}`
          : String(client?.deviceID || "").trim();
      })
      .filter(Boolean)
  ).size;

  return [
    dashboardCountLabel(hubCount, "hub"),
    dashboardCountLabel(deviceCount, "device")
  ].join(" - ");
}

function dashboardClientSummary() {
  const counts = window.dashboardClientCounts?.(
    S.currentClients || []
  ) || {
    clients: 0,
    sensors: 0,
    cameras: 0,
    tapoControls: 0,
    keys: 0
  };

  return {
    ariaLabel: [
      `Devices. Sensors: ${counts.sensors}`,
      `Cameras: ${counts.cameras}`,
      `Tapo Controls: ${counts.tapoControls}`,
      `Keys: ${counts.keys}`
    ].join("; "),
    html: [
      `<span title="Sensors">${window.dashboardIconHtml("sensors")}<span>${counts.sensors}</span></span>`,
      `<span title="Cameras">${window.dashboardIconHtml("videocam")}<span>${counts.cameras}</span></span>`,
      `<span title="Tapo Controls">${window.dashboardIconHtml("toggle_on")}<span>${counts.tapoControls}</span></span>`,
      `<span title="Keys">${window.dashboardIconHtml("key")}<span>${counts.keys}</span></span>`
    ].join("")
  };
}

window.syncSettingsSystemSummaries = function () {
  const bluetooth = document.getElementById("settingsBluetoothSummary");
  const matter = document.getElementById("settingsMatterSummary");
  const clients = document.getElementById("settingsClientsSummary");

  if (bluetooth) {
    bluetooth.textContent = dashboardBluetoothSummaryText(
      window.dashboardBluetoothStatus
    );
  }

  if (matter) {
    matter.textContent = dashboardMatterSummaryText();
  }

  if (clients) {
    const summary = dashboardClientSummary();

    clients.innerHTML = summary.html;
    clients.closest("button")?.setAttribute(
      "aria-label",
      summary.ariaLabel
    );
  }
};

window.syncServerViewControls = function () {
  localStorage.removeItem("dashboardSpacing");
  localStorage.removeItem("dashboardMaxColumns");
  document.body.removeAttribute("data-spacing");
  document.body.removeAttribute("data-dashboard-max-cols");
  applyDashboardSystemTheme?.();
  window.applyColumnBuilderLayoutVars?.();

  S.groupByRoom = true;
  document.body.dataset.groupByRoom = "1";
  localStorage.setItem("dashboardGroupByRoom", "1");

  const infoShown = !document.body.classList.contains("debug-off");

  ["dashboardInfoToggle", "asideCardDebugToggle"].forEach(id => {
    const infoToggle = document.getElementById(id);
    if (!infoToggle) return;

    const title = id === "dashboardInfoToggle"
      ? `${infoShown ? "Hide" : "Show"} Client Info`
      : (infoShown ? "Hide info" : "Show info");

    infoToggle.classList.toggle("active", infoShown);
    infoToggle.title = title;
    infoToggle.setAttribute("aria-label", title);
  });

  const dashboardInfoToggleLabel = document.getElementById("dashboardInfoToggleLabel");
  if (dashboardInfoToggleLabel) {
    dashboardInfoToggleLabel.textContent = infoShown ? "Hide Info" : "Show Info";
  }

  syncSettingsServerInfo?.();
  syncSettingsSystemSummaries?.();
  syncDashboardTextSizeControls?.();
  setDashboardSecurityStatus?.("");
};

function dashboardCurrentUserEmailFromStatus(status = {}) {
  const candidates = [
    status?.dashboard_user_email,
    status?.dashboard_email,
    status?.current_user_email,
    status?.user_email,
    status?.email,
    status?.dashboard_user?.email,
    status?.current_user?.email,
    status?.user?.email
  ];

  for (const candidate of candidates) {
    const email = String(candidate || "").trim();
    if (email) return email;
  }

  return "";
}

window.dashboardCurrentUserEmailFromStatus = dashboardCurrentUserEmailFromStatus;

window.syncDashboardSecurityControls = async function () {
  const input = document.getElementById("dashboardSecurityKey");
  const unlockBtn = document.querySelector("[data-action='dashboard-unlock']");
  const logoutBtn = document.querySelector("[data-action='dashboard-logout']");

  let status = null;

  try {
    status = await refreshSecurityStatus?.();
  } catch (_) {}

  const authenticated = !!status?.dashboard_authenticated;
  const unlockSection = document.getElementById("dashboardKeyUnlockSection");
  const loggedInSection = document.getElementById("dashboardLoggedInSection");
  const loggedInEmail = document.getElementById("dashboardLoggedInEmail");
  const addUserSection = document.getElementById("dashboardAddUserSection");

  window.dashboardSecurityStatus = status || {};
  window.dashboardCurrentUserEmail = authenticated ? dashboardCurrentUserEmailFromStatus(status || {}) : "";

  if (unlockSection) unlockSection.hidden = authenticated;
  if (input) input.hidden = authenticated;
  if (unlockBtn) unlockBtn.hidden = authenticated;
  if (logoutBtn) logoutBtn.hidden = !authenticated;
  if (loggedInSection) loggedInSection.hidden = !authenticated;
  if (loggedInEmail) loggedInEmail.textContent = window.dashboardCurrentUserEmail || "Authenticated dashboard session";
  if (addUserSection) addUserSection.hidden = !authenticated;

  if (authenticated) {
    renderDashboardUsers?.();
  } else {
    setDashboardUserFormVisible?.(false);

    const list = document.getElementById("dashboardUserList");
    if (list) {
      list.innerHTML = `<div class="settings-note">Unlock the dashboard to manage users.</div>`;
    }
  }

  setDashboardSecurityStatus?.("");
};

function dashboardPasswordRequirementError(password) {
  password = String(password || "");

  if (password.length < 10) {
    return "Password must be at least 10 characters.";
  }

  if (!/[A-Z]/.test(password)) {
    return "Password must include an uppercase letter.";
  }

  if (!/[a-z]/.test(password)) {
    return "Password must include a lowercase letter.";
  }

  if (!/[0-9]/.test(password)) {
    return "Password must include a number.";
  }

  if (!/[^A-Za-z0-9]/.test(password)) {
    return "Password must include a special character.";
  }

  return "";
}

window.setDashboardUserFormVisible = function (visible) {
  const fields = document.getElementById("dashboardUserFormFields");
  const collapsed = document.getElementById("dashboardUserFormCollapsed");
  const emailInput = document.getElementById("dashboardUserEmail");
  const passwordInput = document.getElementById("dashboardUserPassword");
  const confirmInput = document.getElementById("dashboardUserPasswordConfirm");

  if (fields) fields.hidden = !visible;
  if (collapsed) collapsed.hidden = visible;

  collapsed
    ?.querySelector('[data-dashboard-action="toggle-dashboard-user-form"]')
    ?.setAttribute("aria-expanded", visible ? "true" : "false");

  if (!visible) {
    if (emailInput) emailInput.value = "";
    if (passwordInput) passwordInput.value = "";
    if (confirmInput) confirmInput.value = "";
    return;
  }

  setTimeout(() => emailInput?.focus(), 0);
};

window.toggleDashboardUserFormFromSettings = function () {
  const fields = document.getElementById("dashboardUserFormFields");
  setDashboardSecurityStatus?.("");
  setDashboardUserFormVisible?.(!!fields?.hidden);
};

window.cancelDashboardUserFormFromSettings = function () {
  setDashboardSecurityStatus?.("");
  setDashboardUserFormVisible?.(false);
};

window.addDashboardUserFromSettings = async function () {
  const emailInput = document.getElementById("dashboardUserEmail");
  const passwordInput = document.getElementById("dashboardUserPassword");
  const confirmInput = document.getElementById("dashboardUserPasswordConfirm");
  const email = String(emailInput?.value || "").trim();
  const password = String(passwordInput?.value || "");
  const confirmation = String(confirmInput?.value || "");

  if (!email) {
    setDashboardSecurityStatus?.("Enter an email address.");
    emailInput?.focus();
    return;
  }

  const passwordError = dashboardPasswordRequirementError(password);

  if (passwordError) {
    setDashboardSecurityStatus?.(passwordError);
    passwordInput?.focus();
    return;
  }

  if (password !== confirmation) {
    setDashboardSecurityStatus?.("Passwords do not match.");
    confirmInput?.focus();
    return;
  }

  try {
    await addDashboardSecurityUser(email, password);

    setDashboardUserFormVisible?.(false);
    setDashboardSecurityStatus?.(`Dashboard user added: ${email}`);
    renderDashboardUsers?.();
  } catch (err) {
    setDashboardSecurityStatus?.(err?.message || "Failed to add dashboard user.");
  }
};

window.removeDashboardUserFromSettings = async function (email) {
  const cleanEmail = String(email || "").trim().toLowerCase();

  if (!cleanEmail) return;
  if (!confirm(`Remove dashboard user ${cleanEmail}?`)) return;

  try {
    await removeDashboardSecurityUser(cleanEmail);
    setDashboardSecurityStatus?.(`Dashboard user removed: ${cleanEmail}`);
    renderDashboardUsers?.();
  } catch (err) {
    setDashboardSecurityStatus?.(err?.message || "Failed to remove dashboard user.");
  }
};

window.toggleCardDebugInfo = function () {
  const next = document.body.dataset.cardDebug === "off" ? "on" : "off";
  document.body.dataset.cardDebug = next;
  localStorage.setItem("cardDebugInfo", next);

  applyCardDebugVisibility();
  syncServerViewControls();
};

function dashboardZoneDragMode() {
  if (S.renderControls) return "controls";
  if (S.renderMonitors) return "monitors";
  if (S.renderSensors) return "sensors";

  return "";
}

function dashboardZoneDragGroupOrder(group) {
  const order = Number(group?.dataset?.dashboardZoneOrder);

  return Number.isFinite(order) ? order : Number.MAX_SAFE_INTEGER;
}

function dashboardZoneDragGroups() {
  if (!dashboardZoneDragMode()) return [];

  return Array.from(document.querySelectorAll(
    "#clientCards.room-dashboard > .room-lane > .room-group"
  ))
    .filter(group => group instanceof HTMLElement && group.dataset.room)
    .sort((a, b) => {
      const orderDelta = dashboardZoneDragGroupOrder(a) - dashboardZoneDragGroupOrder(b);

      if (orderDelta) return orderDelta;

      return String(a.dataset.room || "").localeCompare(String(b.dataset.room || ""), undefined, { sensitivity: "base" });
    });
}

function dashboardZoneDragRooms() {
  return dashboardZoneDragGroups()
    .map(group => String(group.dataset.room || "").trim())
    .filter(Boolean);
}

function dashboardZoneClearDragUi() {
  document.body.classList.remove("dashboard-zone-drag-active");
  document.querySelectorAll(".dashboard-zone-drop-slot").forEach(slot => slot.remove());
  document.querySelectorAll(".room-group.dashboard-zone-source").forEach(group => {
    group.classList.remove("dashboard-zone-source");
  });
  document.getElementById("dashboardZoneDragGhost")?.remove();
}

function dashboardZoneCreateDragGhost(room, x, y) {
  document.getElementById("dashboardZoneDragGhost")?.remove();

  const ghost = document.createElement("div");
  ghost.id = "dashboardZoneDragGhost";
  ghost.className = "dashboard-zone-drag-ghost";
  ghost.innerHTML = `
    ${window.dashboardIconHtml(getRoomIcon(room))}
    <span>${esc(room)}</span>
  `;
  document.body.appendChild(ghost);
  dashboardZoneMoveDragGhost(x, y);
}

function dashboardZoneMoveDragGhost(x, y) {
  const ghost = document.getElementById("dashboardZoneDragGhost");
  if (!ghost) return;

  ghost.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
}

function dashboardZoneBuildDropSlots(dragRoom) {
  const groups = dashboardZoneDragGroups();
  const dragIndex = groups.findIndex(group => group.dataset.room === dragRoom);
  const skippedDropIndexes = dragIndex >= 0
    ? new Set([dragIndex, dragIndex + 1])
    : new Set();

  const createDropSlot = (dropIndex) => {
    const slot = document.createElement("div");
    slot.className = "dashboard-zone-drop-slot";
    slot.dataset.dropIndex = String(dropIndex);
    slot.textContent = "DRAG TO REORDER";
    slot.setAttribute("aria-hidden", "true");
    return slot;
  };

  document.querySelectorAll(".dashboard-zone-drop-slot").forEach(slot => slot.remove());

  groups.forEach(group => group.classList.toggle("dashboard-zone-source", group.dataset.room === dragRoom));

  groups.forEach((group, index) => {
    if (skippedDropIndexes.has(index)) return;

    group.parentElement?.insertBefore(createDropSlot(index), group);
  });

  const lastGroup = groups[groups.length - 1];
  const afterDropIndex = groups.length;
  if (lastGroup?.parentElement && !skippedDropIndexes.has(afterDropIndex)) {
    lastGroup.parentElement.insertBefore(createDropSlot(afterDropIndex), lastGroup.nextSibling);
  }
}

function dashboardZoneDropSlotAtPoint(x, y) {
  const direct = document.elementFromPoint(x, y)?.closest?.(".dashboard-zone-drop-slot");
  if (direct) return direct;

  const slots = Array.from(document.querySelectorAll(".dashboard-zone-drop-slot"));
  let best = null;
  let bestDistance = Number.POSITIVE_INFINITY;

  slots.forEach(slot => {
    const rect = slot.getBoundingClientRect();
    const clampedY = Math.max(rect.top, Math.min(y, rect.bottom));
    const clampedX = Math.max(rect.left, Math.min(x, rect.right));
    const distance = Math.hypot(x - clampedX, y - clampedY);

    if (distance < bestDistance) {
      bestDistance = distance;
      best = slot;
    }
  });

  return best;
}

function dashboardZoneSetActiveDropSlot(slot) {
  document.querySelectorAll(".dashboard-zone-drop-slot.active").forEach(activeSlot => {
    if (activeSlot !== slot) activeSlot.classList.remove("active");
  });

  slot?.classList.add("active");
}

function dashboardZoneSaveRoomOrder(rooms, mode) {
  if (mode === "monitors" || mode === "monitor") {
    setDashboardMonitorsRoomOrder(rooms);
    return;
  }

  if (mode === "sensors") {
    setDashboardSensorsRoomOrder(rooms);
    return;
  }

  setDashboardControlsRoomOrder(rooms);
}

window.handleControlsZoneDragPointerDown = function (event) {
  const dragMode = dashboardZoneDragMode();
  if (!dragMode) return;
  if (!(event.target instanceof Element)) return;
  if (event.pointerType === "mouse" && event.button !== 0) return;

  const header = event.target.closest("#clientCards.room-dashboard .room-head");
  if (!header) return;
  if (event.target.closest("button, a, input, select, textarea, label, [role='button'], [data-room-actions], [data-dashboard-action], [data-tapo-action], .icon-menu")) return;

  const group = header.closest(".room-group");
  const room = String(group?.dataset?.room || "").trim();
  if (!group || !room) return;

  const startX = Number(event.clientX || 0);
  const startY = Number(event.clientY || 0);
  let dragging = false;

  const cleanup = () => {
    document.removeEventListener("pointermove", onMove, true);
    document.removeEventListener("pointerup", onUp, true);
    document.removeEventListener("pointercancel", onCancel, true);
    header.releasePointerCapture?.(event.pointerId);
  };

  const beginDrag = (moveEvent) => {
    if (dragging) return;

    dragging = true;
    window.dashboardMarkInteraction?.();
    document.body.classList.add("dashboard-zone-drag-active");
    dashboardZoneBuildDropSlots(room);
    dashboardZoneCreateDragGhost(room, moveEvent.clientX, moveEvent.clientY);
  };

  const onMove = (moveEvent) => {
    const x = Number(moveEvent.clientX || 0);
    const y = Number(moveEvent.clientY || 0);
    const distance = Math.hypot(x - startX, y - startY);

    if (!dragging && distance < 6) return;

    beginDrag(moveEvent);
    moveEvent.preventDefault();
    moveEvent.stopPropagation();
    window.dashboardMarkInteraction?.();
    dashboardZoneMoveDragGhost(x, y);
    dashboardZoneSetActiveDropSlot(dashboardZoneDropSlotAtPoint(x, y));
  };

  const onUp = (upEvent) => {
    cleanup();

    if (!dragging) return;

    upEvent.preventDefault();
    upEvent.stopPropagation();

    const rooms = dashboardZoneDragRooms();
    const currentIndex = rooms.indexOf(room);
    const slot = dashboardZoneDropSlotAtPoint(upEvent.clientX, upEvent.clientY);
    let dropIndex = Number(slot?.dataset?.dropIndex);

    dashboardZoneClearDragUi();

    if (currentIndex < 0 || !Number.isFinite(dropIndex)) return;

    if (currentIndex < dropIndex) dropIndex -= 1;
    dropIndex = Math.max(0, Math.min(dropIndex, rooms.length - 1));

    if (dropIndex === currentIndex) return;

    const nextRooms = rooms.slice();
    const moved = nextRooms.splice(currentIndex, 1)[0];
    nextRooms.splice(dropIndex, 0, moved);

    dashboardZoneSaveRoomOrder(nextRooms, dragMode);
    renderDashboard();
    renderDashboardAside();
  };

  const onCancel = () => {
    cleanup();
    dashboardZoneClearDragUi();
  };

  header.setPointerCapture?.(event.pointerId);
  document.addEventListener("pointermove", onMove, true);
  document.addEventListener("pointerup", onUp, true);
  document.addEventListener("pointercancel", onCancel, true);
};

const DASHBOARD_BLUETOOTH_PAIRING_REFRESH_MS = 4000;
let dashboardBluetoothPairingTimer = null;
let dashboardBluetoothPairingRefreshBusy = false;

function dashboardBluetoothStopPairingTimer() {
  if (dashboardBluetoothPairingTimer) {
    clearInterval(dashboardBluetoothPairingTimer);
    dashboardBluetoothPairingTimer = null;
  }
}

function dashboardBluetoothPairingError(message) {
  const list = document.getElementById("dashboardBluetoothPairingDeviceList");

  if (list) {
    list.innerHTML = `<div class="settings-note">${esc(message || "Bluetooth pairing failed.")}</div>`;
  }
}

async function dashboardBluetoothRefreshPairingDevices() {
  if (window.dashboardBluetoothPairingActive !== true || dashboardBluetoothPairingRefreshBusy) return;

  dashboardBluetoothPairingRefreshBusy = true;

  try {
    const data = await listBluetoothPairingDevices();
    window.dashboardBluetoothPairingDevices = Array.isArray(data.devices) ? data.devices : [];

    if (data.status && typeof data.status === "object") {
      window.dashboardBluetoothStatus = data.status;
      window.syncSettingsSystemSummaries?.();
    }

    dashboardBluetoothRender?.(window.dashboardBluetoothStatus || {});
  } catch (err) {
    dashboardBluetoothPairingError(err?.message || "Bluetooth pairing device refresh failed.");
  } finally {
    dashboardBluetoothPairingRefreshBusy = false;
  }
}

function dashboardBluetoothStartPairingTimer() {
  dashboardBluetoothStopPairingTimer();
  dashboardBluetoothPairingTimer = setInterval(() => {
    dashboardBluetoothRefreshPairingDevices();
  }, DASHBOARD_BLUETOOTH_PAIRING_REFRESH_MS);
}

window.refreshBluetoothManagerFromSettings = async function () {
  await renderDashboardBluetoothManager?.();
};

window.scanBluetoothFromSettings = async function () {
  try {
    const data = await scanBluetoothDevices(8);
    window.dashboardBluetoothPairingDevices = Array.isArray(data.devices) ? data.devices : [];
    await renderDashboardBluetoothManager?.();
  } catch (err) {
    dashboardBluetoothPairingError(err?.message || "Bluetooth scan failed.");
  }
};

window.startBluetoothPairingFromSettings = async function () {
  window.dashboardBluetoothPairingActive = true;
  window.dashboardBluetoothPairingDevices = [];
  dashboardBluetoothRender?.(window.dashboardBluetoothStatus || {});

  try {
    const data = await startBluetoothPairing();

    window.dashboardBluetoothStatus =
      data.status && typeof data.status === "object"
        ? data.status
        : data;

    window.syncSettingsSystemSummaries?.();
    dashboardBluetoothRender?.(window.dashboardBluetoothStatus || {});
    await dashboardBluetoothRefreshPairingDevices();
    dashboardBluetoothStartPairingTimer();
  } catch (err) {
    dashboardBluetoothStopPairingTimer();
    window.dashboardBluetoothPairingActive = false;
    dashboardBluetoothPairingError(err?.message || "Bluetooth pairing failed to start.");
    dashboardBluetoothRender?.(window.dashboardBluetoothStatus || {});
  }
};

window.cancelBluetoothPairingFromSettings = async function () {
  dashboardBluetoothStopPairingTimer();
  window.dashboardBluetoothPairingActive = false;
  window.dashboardBluetoothPairingDevices = [];

  try {
    const data = await cancelBluetoothPairing();

    window.dashboardBluetoothStatus =
      data.status && typeof data.status === "object"
        ? data.status
        : data;

    window.syncSettingsSystemSummaries?.();
  } catch (err) {
    dashboardBluetoothPairingError(err?.message || "Bluetooth pairing cancel failed.");
  }

  dashboardBluetoothRender?.(window.dashboardBluetoothStatus || {});
};

window.toggleBluetoothPairingFromSettings = async function () {
  if (window.dashboardBluetoothPairingActive === true) {
    await window.cancelBluetoothPairingFromSettings?.();
    return;
  }

  await window.startBluetoothPairingFromSettings?.();
};

window.setBluetoothAdapterFromSettings = async function (action) {
  if (!action) return;

  try {
    const data = await setBluetoothAdapterAction(action);

    window.dashboardBluetoothStatus =
      data.status && typeof data.status === "object"
        ? data.status
        : data;

    window.syncSettingsSystemSummaries?.();
    await renderDashboardBluetoothManager?.();
  } catch (err) {
    dashboardBluetoothPairingError(err?.message || "Bluetooth adapter update failed.");
  }
};

window.setBluetoothDeviceFromSettings = async function (address, action) {
  if (!address || !action) return;

  if (action === "remove" && !confirm("Remove this Bluetooth device from the server?")) return;

  try {
    await setBluetoothDeviceAction(address, action);

    if (action === "pair") {
      await window.cancelBluetoothPairingFromSettings?.();
    }

    await renderDashboardBluetoothManager?.();
    window.syncSettingsSystemSummaries?.();
  } catch (err) {
    dashboardBluetoothPairingError(err?.message || "Bluetooth device update failed.");
  }
};

let dashboardMatterSettingsBusy = false;
let dashboardMatterNodeID = "";

function dashboardMatterStatusLabel(status) {
  return {
    connected: "Connected",
    unconfigured: "Not configured",
    unreachable: "Unreachable",
  }[String(status || "").trim().toLowerCase()] || "Unknown";
}

function dashboardMatterDateTime(value) {
  const timestamp = Number(value || 0);

  if (!Number.isFinite(timestamp) || timestamp <= 0) {
    return "Never";
  }

  return new Date(timestamp * 1000).toLocaleString([], {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function dashboardSetMatterMessage(elementID, message = "", state = "") {
  const element = document.getElementById(elementID);
  if (!element) return;

  element.textContent = String(message || "");
  element.hidden = !message;
  element.dataset.status = state || "";
}

function dashboardSetMatterBusy(busy) {
  dashboardMatterSettingsBusy = Boolean(busy);

  for (const elementID of [
    "settingsMatterSyncButton",
    "settingsMatterRecommissionButton",
  ]) {
    const button = document.getElementById(elementID);

    if (button) {
      button.disabled = dashboardMatterSettingsBusy;
    }
  }

  window.syncDashboardMatterRecommissionButton?.();
}

window.renderDashboardMatterSettings = function () {
  const connection = document.getElementById("settingsMatterConnection");
  const lastSync = document.getElementById("settingsMatterLastSync");
  const node = document.getElementById("settingsMatterNode");
  const endpoints = document.getElementById("settingsMatterEndpoints");

  if (!connection || !lastSync || !node || !endpoints) {
    return null;
  }

  const matterClients = (S.currentClients || []).filter(
    client => client?.source === "matter"
  );
  const nodeID = String(matterClients[0]?.matter_node_id || "").trim();
  const endpointCount = new Set(
    matterClients
      .map(client => String(client?.matter_endpoint || "").trim())
      .filter(Boolean)
  ).size;
  const lastSyncAt = matterClients.reduce(
    (latest, client) => Math.max(
      latest,
      Number(client?.matter_last_sync_at || 0)
    ),
    0
  );
  const status = !matterClients.length
    ? "unconfigured"
    : (
      matterClients.some(client => !client?.stale)
        ? "connected"
        : "unreachable"
    );

  dashboardMatterNodeID = nodeID;
  connection.textContent = dashboardMatterStatusLabel(status);
  connection.dataset.status = status;
  lastSync.textContent = dashboardMatterDateTime(lastSyncAt);
  node.textContent = nodeID || "—";
  endpoints.textContent = String(endpointCount);

  const recommissionModal = document.getElementById(
    "dashboardMatterRecommissionModal"
  );

  if (recommissionModal) {
    recommissionModal.dataset.nodeId = nodeID;
  }

  return nodeID;
};

async function dashboardRefreshAfterMatterUpdate() {
  const data = await refreshStatusData?.();

  if (data) {
    requestDashboardRenderSafe?.(data);
  }
}

window.syncDashboardMatterNow = async function () {
  if (dashboardMatterSettingsBusy) return;

  dashboardSetMatterBusy(true);

  dashboardSetMatterMessage(
    "settingsMatterStatus",
    "Syncing Matter devices…",
    "maintenance"
  );

  try {
    const result = await postJson("/api/matter/sync", {
      force_discovery: true,
    });

    await dashboardRefreshAfterMatterUpdate();
    window.renderDashboardMatterSettings?.();

    const count = Number(result?.devices?.length || 0);

    dashboardSetMatterMessage(
      "settingsMatterStatus",
      `Matter sync complete. ${count} device${count === 1 ? "" : "s"} updated.`,
      "success"
    );
  } catch (error) {
    window.renderDashboardMatterSettings?.();

    dashboardSetMatterMessage(
      "settingsMatterStatus",
      error?.message || "Matter sync failed.",
      "error"
    );
  } finally {
    dashboardSetMatterBusy(false);
  }
};

window.syncDashboardMatterRecommissionButton = function () {
  const setupCode = document.getElementById(
    "dashboardMatterSetupCode"
  );
  const confirm = document.getElementById(
    "dashboardMatterRecommissionConfirm"
  );
  const submit = document.getElementById(
    "dashboardMatterRecommissionSubmit"
  );

  if (!submit) return;

  submit.disabled =
    dashboardMatterSettingsBusy
    || !String(setupCode?.value || "").trim()
    || confirm?.checked !== true;
};

window.showDashboardMatterSettingsModal = function () {
  ensureSettingsModal?.();

  const modal = document.getElementById(
    "dashboardMatterSettingsModal"
  );

  if (!modal) return;

  dashboardHideParentModalForSubmodal(
    modal,
    "settingsModal"
  );

  dashboardSetMatterMessage("settingsMatterStatus");
  window.renderDashboardMatterSettings?.();
  modal.hidden = false;
  document.body.classList.add("modal-open");
};

window.hideDashboardMatterSettingsModal = function () {
  const modal = document.getElementById(
    "dashboardMatterSettingsModal"
  );

  if (!modal) return;

  modal.hidden = true;

  if (dashboardRestoreParentModalFromSubmodal(modal)) return;

  dashboardCloseModalOpenClassIfNeeded();
};

window.showDashboardMatterRecommissionModal = function () {
  ensureSettingsModal?.();

  const modal = document.getElementById(
    "dashboardMatterRecommissionModal"
  );

  if (!modal) return;

  const nodeID =
    dashboardMatterNodeID
    || window.renderDashboardMatterSettings?.();

  const setupCode = document.getElementById(
    "dashboardMatterSetupCode"
  );
  const confirm = document.getElementById(
    "dashboardMatterRecommissionConfirm"
  );

  modal.dataset.nodeId = String(
    nodeID || modal.dataset.nodeId || ""
  );

  if (setupCode) setupCode.value = "";
  if (confirm) confirm.checked = false;

  dashboardSetMatterMessage(
    "dashboardMatterRecommissionStatus"
  );

  dashboardHideParentModalForSubmodal(
    modal,
    "dashboardMatterSettingsModal"
  );

  modal.hidden = false;
  document.body.classList.add("modal-open");

  window.syncDashboardMatterRecommissionButton?.();
  setupCode?.focus();
};

window.hideDashboardMatterRecommissionModal = function () {
  const modal = document.getElementById(
    "dashboardMatterRecommissionModal"
  );

  if (!modal) return;

  modal.hidden = true;

  if (dashboardRestoreParentModalFromSubmodal(modal)) {
    window.renderDashboardMatterSettings?.();
    return;
  }

  dashboardCloseModalOpenClassIfNeeded();
};

window.recommissionDashboardMatter = async function () {
  if (dashboardMatterSettingsBusy) return;

  const modal = document.getElementById(
    "dashboardMatterRecommissionModal"
  );

  const setupCode = String(
    document.getElementById("dashboardMatterSetupCode")?.value
    || ""
  ).trim();

  const confirmed =
    document.getElementById(
      "dashboardMatterRecommissionConfirm"
    )?.checked === true;

  const nodeID = String(
    modal?.dataset?.nodeId
    || dashboardMatterNodeID
    || ""
  ).trim();

  if (!nodeID || !setupCode || !confirmed) {
    dashboardSetMatterMessage(
      "dashboardMatterRecommissionStatus",
      "Enter the new setup code and confirm the replacement.",
      "error"
    );

    return;
  }

  dashboardSetMatterBusy(true);

  dashboardSetMatterMessage(
    "dashboardMatterRecommissionStatus",
    "Backing up the old connection and recommissioning the H110…",
    "maintenance"
  );

  try {
    const result = await postJson(
      "/api/matter/recommission",
      {
        node_id: nodeID,
        setup_code: setupCode,
      }
    );

    const setupCodeInput = document.getElementById(
      "dashboardMatterSetupCode"
    );
    const confirmInput = document.getElementById(
      "dashboardMatterRecommissionConfirm"
    );

    if (setupCodeInput) setupCodeInput.value = "";
    if (confirmInput) confirmInput.checked = false;

    await dashboardRefreshAfterMatterUpdate();
    window.renderDashboardMatterSettings?.();

    const count = Number(result?.device_count || 0);

    dashboardSetMatterMessage(
      "dashboardMatterRecommissionStatus",
      result.sync_ok === false
        ? "H110 recommissioned. The first device sync failed; use Sync Now after closing this window."
        : `H110 recommissioned. ${count} device${count === 1 ? "" : "s"} updated.`,
      result.sync_ok === false ? "warning" : "success"
    );
  } catch (error) {
    dashboardSetMatterMessage(
      "dashboardMatterRecommissionStatus",
      error?.message || "H110 recommissioning failed.",
      "error"
    );
  } finally {
    dashboardSetMatterBusy(false);
  }
};

function dashboardAnySettingsModalOpen() {
  return [...document.querySelectorAll(
    ".modal"
  )].some(modal => modal && modal.hidden === false);
}

function dashboardCloseModalOpenClassIfNeeded() {
  if (!dashboardAnySettingsModalOpen()) {
    document.body.classList.remove("modal-open");
  }
}

window.showSettingsModal = function () {
  const modal = document.getElementById("settingsModal");
  if (!modal) return;

  modal.hidden = false;
  document.body.classList.add("modal-open");

  window.syncServerViewControls?.();
  syncSettingsServerInfo?.();

  const showSupplementalSettings =
    window.matchMedia?.("(max-aspect-ratio: 2/3)")?.matches === true ||
    document.body.dataset.dashboardAsideTruncated === "1";

  if (showSupplementalSettings) {
    syncSettingsRecentActivity?.();
  }

  Promise.allSettled([
    refreshStatusData?.(),
    refreshFileServerApks?.(),
    getBluetoothStatus?.(),
    showSupplementalSettings
      ? refreshRecentActivities?.({
          limit: 3,
          fromHours: 0,
          toHours: 0,
          category: "all"
        })
      : null
  ])
    .then(results => {
      const statusResult = results[0];
      const bluetoothResult = results[2];
      const activityResult = results[3];
      const data = statusResult?.status === "fulfilled" ? statusResult.value : null;

      if (data) {
        requestDashboardRenderSafe?.(data);
      }

      window.dashboardBluetoothStatus = bluetoothResult?.status === "fulfilled"
        ? bluetoothResult.value
        : null;

      syncSettingsServerInfo?.();
      syncSettingsSystemSummaries?.();
      if (showSupplementalSettings) {
        syncSettingsRecentActivity?.(
          activityResult?.status === "fulfilled" ? activityResult.value : []
        );
      }
    })
    .catch(() => {
      window.dashboardBluetoothStatus = null;
      syncSettingsServerInfo?.();
      syncSettingsSystemSummaries?.();

      if (showSupplementalSettings) {
        syncSettingsRecentActivity?.([]);
      }
    });
};

window.hideSettingsModal = function () {
  const modal = document.getElementById("settingsModal");
  if (!modal) return;

  modal.hidden = true;
  dashboardCloseModalOpenClassIfNeeded();
};

window.showDashboardUsersSettingsModal = async function () {
  ensureSettingsModal?.();

  const modal = document.getElementById("dashboardUsersSettingsModal");
  if (!modal) return;

  setDashboardUserFormVisible?.(false);
  dashboardHideParentModalForSubmodal(modal, "settingsModal");
  modal.hidden = false;
  document.body.classList.add("modal-open");
  await syncDashboardSecurityControls?.();
};

window.hideDashboardUsersSettingsModal = function () {
  const modal = document.getElementById("dashboardUsersSettingsModal");
  if (!modal) return;

  setDashboardUserFormVisible?.(false);
  modal.hidden = true;

  if (dashboardRestoreParentModalFromSubmodal(modal)) return;

  dashboardCloseModalOpenClassIfNeeded();
};

window.showBluetoothSettingsModal = async function () {
  ensureSettingsModal?.();

  const modal = document.getElementById("dashboardBluetoothSettingsModal");
  if (!modal) return;

  dashboardHideParentModalForSubmodal(modal, "settingsModal");
  modal.hidden = false;
  document.body.classList.add("modal-open");
  await renderDashboardBluetoothManager?.();
};

window.hideBluetoothSettingsModal = function () {
  const modal = document.getElementById("dashboardBluetoothSettingsModal");
  if (!modal) return;

  if (window.dashboardBluetoothPairingActive === true) {
    window.cancelBluetoothPairingFromSettings?.();
  }

  modal.hidden = true;

  if (dashboardRestoreParentModalFromSubmodal(modal)) return;

  dashboardCloseModalOpenClassIfNeeded();
};

window.setDashboardSecurityStatus = function (message = "") {
  const el = document.getElementById("dashboardSecurityStatus");
  if (!el) return;

  el.textContent = message;
  el.hidden = !message;
};