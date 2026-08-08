const tapoEsc = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function tapoRechargeClientRoleText(client) {
  const roles = Array.isArray(client?.clientRole)
    ? client.clientRole
    : String(client?.clientRole || "").split(",");

  return roles
    .map(role => String(role || "").trim())
    .filter(Boolean)
    .join("+");
}

function tapoRechargeClientID(client) {
  return String(
    client?.deviceID
    || client?.device_id
    || client?.clientID
    || client?.client_id
    || client?.id
    || ""
  ).trim();
}

function tapoRechargeClientName(client, deviceID = "") {
  const cleanDeviceID = String(deviceID || tapoRechargeClientID(client)).trim();

  return [
    client?.clientName,
    client?.client_name,
    client?.deviceName,
    client?.device_name,
    client?.name,
    client?.display_name
  ]
    .map(value => String(value || "").trim())
    .find(value => value && value !== cleanDeviceID)
    || "";
}

function tapoRechargeClientOptionLabel(client) {
  const name = tapoRechargeClientName(client);
  const roles = tapoRechargeClientRoleText(client);

  return name && roles ? `${name} · ${roles}` : name;
}

function renderTapoRechargePanel(data = {}, options = {}) {
  const clients = Array.isArray(data.clients) ? data.clients : [];
  const allTargets = Array.isArray(data.targets) ? data.targets : [];
  const rows = Array.isArray(data.recharge) ? data.recharge : [];
  const targetDeviceID = String(options.targetDeviceID || "").trim();
  const preferredTargetID = String(options.targetID || "").trim();
  const mode = String(options.mode || "list");
  const expanded = options.expanded === true;
  const preferredTarget = preferredTargetID
    ? allTargets.find(target => target.targetID === preferredTargetID)
    : null;
  const targets = preferredTarget
    ? [preferredTarget]
    : targetDeviceID
      ? allTargets.filter(target => target.deviceID === targetDeviceID)
      : allTargets;

  const targetRows = preferredTarget
    ? rows.filter(item => item.targetID === preferredTargetID)
    : targetDeviceID
      ? rows.filter(item => item.targetDeviceID === targetDeviceID)
      : rows;

  const existing =
    targetRows.find(item => preferredTargetID && item.targetID === preferredTargetID)
    || targetRows[0]
    || null;

  const selectedDeviceID = existing?.deviceID || clients[0]?.deviceID || "";
  const selectedTargetID =
    existing?.targetID
    || targets.find(target => target.targetID === preferredTargetID)?.targetID
    || targets[0]?.targetID
    || "";

  const showOutletPicker = targets.length > 1;

  const clientLabelForRow = row => {
    const deviceID = String(row.deviceID || "").trim();
    const currentClients = Array.isArray(window.dashboardState?.currentClients)
      ? window.dashboardState.currentClients
      : [];
    const client = [...clients, ...currentClients]
      .find(item => tapoRechargeClientID(item) === deviceID);

    return (
      tapoRechargeClientName(client, deviceID)
      || tapoRechargeClientName(row, deviceID)
    );
  };

  const listHtml = targetRows.length
    ? targetRows.map(row => `
        <button
          class="settings-item settings-automation-item"
          type="button"
          data-tapo-recharge-add="1"
          data-tapo-recharge-target-id="${tapoEsc(row.targetID || "")}"
          title="Edit automation"
        >
          ${window.dashboardIconHtml("battery_charging_full")}
          <span class="settings-automation-copy">
            <span class="settings-automation-title">
              Recharge ${tapoEsc(clientLabelForRow(row))} when its battery reaches ${tapoEsc(row.lowBattery ?? 20)}%
            </span>
          </span>
        </button>
      `).join("")
    : "";

  const addButtonHtml = `
    <button
      class="settings-item"
      type="button"
      data-tapo-recharge-add="1"
      ${clients.length && targets.length ? "" : "disabled"}
    >
      ${window.dashboardIconHtml("add")}
      <span>Add Automation</span>
    </button>
  `;

  if (mode !== "add") {
    return `
      <div class="settings-actions">
        ${listHtml}
        ${addButtonHtml}
      </div>
    `;
  }

  return `
    <div class="tapo-recharge-head" role="button" tabindex="0" aria-expanded="${expanded ? "true" : "false"}" aria-controls="tapoRechargeForm" data-tapo-recharge-toggle="1">
      <div class="tapo-recharge-icon-wrap">
        ${window.dashboardIconHtml("battery_charging_full", "tapo-recharge-icon")}
      </div>

      <div>
        <div class="tapo-recharge-title">Recharge Android Client</div>
        <div class="tapo-recharge-description">
          Turn this Tapo power target on when an Android client drops to 20%, then turn it off when the client reaches full charge.
        </div>
      </div>
    </div>

    <div id="tapoRechargeForm" class="tapo-recharge-form" ${expanded ? "" : "hidden"}>
      <label class="tapo-recharge-field">
        <span class="tapo-recharge-label">Android client</span>
        <select id="tapoRechargeClient" class="tapo-recharge-input">
          ${
            clients.length
              ? clients.map(client => `
                  <option value="${tapoEsc(client.deviceID)}" ${client.deviceID === selectedDeviceID ? "selected" : ""}>
                    ${tapoEsc(tapoRechargeClientOptionLabel(client))}
                  </option>
                `).join("")
              : `<option value="">No Android clients found</option>`
          }
        </select>
      </label>

      ${
        showOutletPicker
          ? `
              <label class="tapo-recharge-field">
                <span class="tapo-recharge-label">Outlet</span>
                <select id="tapoRechargeTarget" class="tapo-recharge-input">
                  ${targets.map(target => `
                    <option value="${tapoEsc(target.targetID)}" ${target.targetID === selectedTargetID ? "selected" : ""}>
                      ${tapoEsc(target.label || target.targetID)}
                    </option>
                  `).join("")}
                </select>
              </label>
            `
          : `
              <input id="tapoRechargeTarget" type="hidden" value="${tapoEsc(selectedTargetID)}">
            `
      }

      <div class="settings-actions">
        <button
          class="settings-item"
          type="button"
          data-tapo-recharge-save="1"
          ${clients.length && targets.length ? "" : "disabled"}
        >
          ${window.dashboardIconHtml("save")}
          <span>Save</span>
        </button>
      </div>
    </div>
  `;
}

window.renderTapoRechargePanel = renderTapoRechargePanel;

function tapoEnergyNumber(value) {
  if (value === null || value === undefined || value === "") return null;

  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function tapoEnergyReadableNumber(value) {
  const magnitude = Math.abs(value);
  const digits = magnitude >= 100 ? 0 : magnitude >= 10 ? 1 : 2;
  const fixed = value.toFixed(digits);

  return fixed.includes(".")
    ? fixed.replace(/0+$/, "").replace(/\.$/, "")
    : fixed;
}

function tapoEnergyPowerText(value) {
  const number = tapoEnergyNumber(value);
  if (number === null) return "—";

  const magnitude = Math.abs(number);

  if (magnitude >= 1000) {
    return `${tapoEnergyReadableNumber(number / 1000)} kW`;
  }

  if (magnitude < 1) {
    return `${tapoEnergyReadableNumber(number * 1000)} mW`;
  }

  return `${tapoEnergyReadableNumber(number)} W`;
}

function tapoEnergyUsageText(value, options = {}) {
  const number = tapoEnergyNumber(value);
  if (number === null) return "—";

  const magnitude = Math.abs(number);

  if (options.fixedKWh !== true && magnitude < 1) {
    return `${tapoEnergyReadableNumber(number * 1000)} Wh`;
  }

  const digits = magnitude >= 100 ? 1 : magnitude >= 1 ? 2 : 3;
  const fixed = number.toFixed(digits);
  const readable = fixed.includes(".")
    ? fixed.replace(/0+$/, "").replace(/\.$/, "")
    : fixed;

  return `${readable} kWh`;
}

function tapoEnergyRuntimeText(value) {
  const number = tapoEnergyNumber(value);
  if (number === null) return "—";

  const totalMinutes = Math.max(0, Math.round(number));

  if (totalMinutes < 60) {
    return `${totalMinutes} min`;
  }

  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  return minutes ? `${hours} hr ${minutes} min` : `${hours} hr`;
}

function renderTapoEnergyReading(label, value, className = "") {
  return `
    <div class="tapo-energy-reading ${tapoEsc(className)}">
      <span class="tapo-light-label">${tapoEsc(label)}</span>
      <span class="tapo-light-value">${tapoEsc(value)}</span>
    </div>
  `;
}

window.renderTapoEnergyPanel = function (options = {}) {
  const reading = options.reading && typeof options.reading === "object"
    ? options.reading
    : {};
  const loading = options.loading === true;
  const busy = options.busy === true;
  const error = String(options.error || reading.error || "").trim();
  const hasReading = [
    reading.currentPowerW,
    reading.todayEnergyKWh,
    reading.monthEnergyKWh,
    reading.todayRuntimeMinutes,
    reading.monthRuntimeMinutes
  ].some(value => tapoEnergyNumber(value) !== null);
  const showReadings = reading.available === true || hasReading;
  let statusText = "";
  let statusClass = "tapo-energy-description";

  if (loading && !showReadings) {
    statusText = "Loading energy data…";
  } else if (busy) {
    statusText = "Another Tapo refresh is already running. Showing the latest available reading.";
  } else if (!showReadings) {
    statusText = error
      ? `Energy data is currently unavailable. ${error}`
      : "Energy data is currently unavailable.";
    statusClass = error ? "tapo-energy-error" : statusClass;
  } else if (error) {
    statusText = `Some energy data could not be refreshed. ${error}`;
    statusClass = "tapo-energy-error";
  } else if (loading) {
    statusText = "Refreshing energy data…";
  }

  return `
    ${showReadings ? `
      <div class="tapo-energy-readings">
        ${renderTapoEnergyReading("Current Power", tapoEnergyPowerText(reading.currentPowerW))}
        ${renderTapoEnergyReading("Past 24 Hours Energy", tapoEnergyUsageText(reading.todayEnergyKWh))}
        ${renderTapoEnergyReading(
          "This Month Energy",
          tapoEnergyUsageText(reading.monthEnergyKWh, { fixedKWh: true })
        )}
        ${renderTapoEnergyReading(
          "Past 24 Hours Runtime",
          tapoEnergyRuntimeText(reading.todayRuntimeMinutes),
          "tapo-energy-runtime-today"
        )}
        ${renderTapoEnergyReading(
          "This Month Runtime",
          tapoEnergyRuntimeText(reading.monthRuntimeMinutes),
          "tapo-energy-runtime-month"
        )}
      </div>
    ` : ""}

    ${statusText ? `<div class="${statusClass}">${tapoEsc(statusText)}</div>` : ""}
  `;
};

function readTapoRenderLightingSchemes() {
  const state = window.TAPO_LIGHTING_STATE || {};

  return state.schemes && typeof state.schemes === "object"
    ? state.schemes
    : {};
}

function tapoLightingSchemeKeyFromDeviceIDs(deviceIDs = []) {
  return `room:${deviceIDs
    .map(deviceID => String(deviceID || "").trim())
    .filter(Boolean)
    .sort()
    .join(",")}`;
}

function getTapoRenderSchemeIcon(mode, fallback = "auto_awesome") {
  if (mode === "day") return "wb_sunny";
  if (mode === "evening") return "wb_twilight";
  if (mode === "movie") return "movie";
  if (mode === "nightlight") return "bedtime";

  return fallback;
}

function getTapoRenderSchemeOrder(scheme, index = 0) {
  const mode = String(scheme?.mode || "");

  if (mode === "day") return 10;
  if (mode === "evening") return 20;
  if (mode === "movie") return 30;
  if (mode === "nightlight") return 40;
  if (mode.startsWith("custom:")) return 1000 + index;

  return 900 + index;
}

function getTapoRenderFavoriteSchemesForKey(key) {
  const schemes = readTapoRenderLightingSchemes();
  const targetSchemes = key ? schemes[key] || [] : [];

  return targetSchemes
    .map((scheme, index) => ({ scheme, index }))
    .filter(entry => entry.scheme?.favorite === true)
    .sort((a, b) => {
      const orderA = getTapoRenderSchemeOrder(a.scheme, a.index);
      const orderB = getTapoRenderSchemeOrder(b.scheme, b.index);

      return orderA - orderB || a.index - b.index;
    })
    .map(({ scheme }) => ({
      ...scheme,
      icon: getTapoRenderSchemeIcon(scheme?.mode, scheme?.icon || "auto_awesome")
    }));
}

function getTapoRenderRoomSchemeMatch(deviceIDs = []) {
  const exactKey = tapoLightingSchemeKeyFromDeviceIDs(deviceIDs);
  const schemes = readTapoRenderLightingSchemes();
  const exactStoredSchemes = exactKey ? schemes[exactKey] || [] : [];
  const exactFavoriteSchemes = getTapoRenderFavoriteSchemesForKey(exactKey);

  if (exactStoredSchemes.length || exactFavoriteSchemes.length) {
    return {
      key: exactKey,
      schemes: exactFavoriteSchemes
    };
  }

  const wantedIDs = deviceIDs
    .map(deviceID => String(deviceID || "").trim())
    .filter(Boolean)
    .sort();

  if (!wantedIDs.length) {
    return {
      key: exactKey,
      schemes: []
    };
  }

  const wantedSet = new Set(wantedIDs);

  const candidates = Object.keys(schemes)
    .filter(key => key.startsWith("room:"))
    .map(key => {
      const keyIDs = key
        .replace(/^room:/, "")
        .split(",")
        .map(deviceID => deviceID.trim())
        .filter(Boolean)
        .sort();
      const keyIDSet = new Set(keyIDs);
      const keyContainsWanted = wantedIDs.every(deviceID => keyIDSet.has(deviceID));
      const wantedContainsKey = keyIDs.every(deviceID => wantedSet.has(deviceID));
      const favorites = getTapoRenderFavoriteSchemesForKey(key);

      return {
        key,
        keyIDs,
        favorites,
        match: keyContainsWanted || wantedContainsKey,
        distance: Math.abs(keyIDs.length - wantedIDs.length)
      };
    })
    .filter(candidate => candidate.match && candidate.favorites.length)
    .sort((a, b) => a.distance - b.distance || b.favorites.length - a.favorites.length);

  if (!candidates.length) {
    return {
      key: exactKey,
      schemes: []
    };
  }

  return {
    key: candidates[0].key,
    schemes: candidates[0].favorites
  };
}

function readTapoRenderActiveLightingSchemes() {
  const state = window.TAPO_LIGHTING_STATE || {};

  return state.activeSchemes && typeof state.activeSchemes === "object"
    ? state.activeSchemes
    : {};
}

function getTapoRenderActiveLightingModeEntry(key) {
  const activeSchemes = readTapoRenderActiveLightingSchemes();

  if (!key || !Object.prototype.hasOwnProperty.call(activeSchemes, key)) {
    return { hasValue: false, mode: "" };
  }

  return {
    hasValue: true,
    mode: String(activeSchemes[key] || "")
  };
}

function tapoRenderSchemeForKey(key, mode) {
  const schemes = readTapoRenderLightingSchemes();
  const targetSchemes = key ? schemes[key] || [] : [];

  return targetSchemes.find(scheme => scheme?.mode === mode);
}

function tapoRenderDeviceSchemeKey(deviceID) {
  const cleanID = String(deviceID || "").trim();

  return cleanID ? `device:${cleanID}` : "";
}

function tapoRenderSchemePresetForClient(client, scheme) {
  const mode = String(scheme?.mode || "");
  const deviceScheme = tapoRenderSchemeForKey(tapoRenderDeviceSchemeKey(client?.deviceID), mode);

  return tapoRenderSchemePreset(deviceScheme || scheme);
}

function tapoRenderClientsMatchScheme(clients = [], scheme) {
  const activeClients = clients
    .filter(Boolean)
    .filter(client => tapoRenderClientIsOn(client));

  return activeClients.length > 0
    && activeClients.every(client => (
      tapoRenderDeviceMatchesSchemePreset(client, tapoRenderSchemePresetForClient(client, scheme))
    ));
}

function tapoRenderSchemeIsActive(key, scheme, clients = []) {
  const mode = String(scheme?.mode || "");

  if (!key || !mode) return false;

  const targetClients = clients.filter(Boolean);

  const activeMode = getTapoRenderActiveLightingModeEntry(key);

  if (activeMode.hasValue) {
    return activeMode.mode === mode
      && (!targetClients.length || targetClients.some(client => tapoRenderClientIsOn(client)));
  }

  if (targetClients.length) {
    return tapoRenderClientsMatchScheme(targetClients, scheme);
  }

  return false;
}

function tapoRenderNumberClose(a, b, tolerance = 2) {
  if (a == null || b == null) return false;

  return Math.abs(Number(a) - Number(b)) <= tolerance;
}

function tapoRenderBool(value) {
  if (value === true || value === false) return value;

  const text = String(value ?? "").trim().toLowerCase();

  if (["1", "true", "on", "yes", "enabled"].includes(text)) return true;
  if (["0", "false", "off", "no", "disabled"].includes(text)) return false;

  return null;
}

function tapoRenderClientIsOn(client) {
  return tapoRenderBool(
    client?.tapo_is_on
    ?? client?.is_on
    ?? client?.device_on
    ?? client?.power_on
    ?? client?.on
    ?? client?.state
    ?? client?.powerState
    ?? client?.power_state
  ) === true;
}

function tapoRenderNumberValue(...values) {
  for (const value of values) {
    if (value == null || value === "") continue;

    const number = Number(value);

    if (Number.isFinite(number)) return number;
  }

  return null;
}

const TAPO_RENDER_WHITE_SATURATION_DEFAULT = 1;

function normalizeTapoRenderWhiteSaturation(value = TAPO_RENDER_WHITE_SATURATION_DEFAULT) {
  const parsed = Number(value ?? TAPO_RENDER_WHITE_SATURATION_DEFAULT);

  return Math.max(1, Math.min(10, Math.round(Number.isFinite(parsed) ? parsed : TAPO_RENDER_WHITE_SATURATION_DEFAULT)));
}

function tapoRenderWhiteHueFromKelvin(kelvin) {
  const t = Math.max(2500, Math.min(6500, Number(kelvin || 4200)));
  const ratio = (t - 2500) / 4000;

  return Math.round(42 + ((210 - 42) * ratio));
}

function tapoRenderLightingModePreset(mode) {
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

  return null;
}

function tapoRenderSchemePreset(scheme) {
  return scheme?.preset || tapoRenderLightingModePreset(String(scheme?.mode || ""));
}

function tapoRenderDeviceMatchesSchemePreset(client, preset) {
  if (!client || !preset || !tapoRenderClientIsOn(client)) return false;

  const brightness = tapoRenderNumberValue(
    client.tapo_brightness,
    client.brightness,
    client.brightness_pct,
    client.brightnessPercent
  );
  const colorTemp = tapoRenderNumberValue(
    client.tapo_color_temp,
    client.tapo_color_temperature,
    client.color_temperature,
    client.colorTemperature,
    client.colour_temperature
  );
  const hue = tapoRenderNumberValue(client.tapo_hue, client.hue);
  const saturation = tapoRenderNumberValue(client.tapo_saturation, client.saturation);

  if (!tapoRenderNumberClose(brightness, preset.brightness, 8)) return false;

  if (preset.hue != null) {
    return tapoRenderNumberClose(hue, preset.hue, 8)
      && tapoRenderNumberClose(saturation, preset.saturation, 8);
  }

  if (preset.colorTemperature != null) {
    const colorTempMatches = tapoRenderNumberClose(colorTemp, preset.colorTemperature, 200);
    const hiddenWhiteColorMatches = tapoRenderNumberClose(hue, tapoRenderWhiteHueFromKelvin(preset.colorTemperature), 8)
      && tapoRenderNumberClose(saturation, normalizeTapoRenderWhiteSaturation(preset.whiteSaturation), 3);

    return colorTempMatches || hiddenWhiteColorMatches;
  }

  return false;
}

function renderTapoFavoriteSchemeButton({
  scheme,
  deviceIDs = [],
  targetKey = "",
  className = "",
  active = false,
  showLabel = true
}) {
  const mode = String(scheme?.mode || "");
  const label = String(scheme?.label || "Scheme");
  const icon = String(scheme?.icon || "auto_awesome");
  const preset = tapoRenderSchemePreset(scheme);
  const presetJson = preset ? JSON.stringify(preset) : "";
  const ids = deviceIDs
    .map(deviceID => String(deviceID || "").trim())
    .filter(Boolean)
    .join(",");

  if (!mode || !ids || !targetKey) return "";

  return `
            <button
              class="icon-btn tapo-scheme-toggle power-toggle ${className} ${active ? "active" : ""}"
              type="button"
              title="${tapoEsc(label)}"
              aria-label="${tapoEsc(label)}"
              data-tapo-action="scheme"
              data-tapo-scheme-mode="${tapoEsc(mode)}"
              data-tapo-scheme-key="${tapoEsc(targetKey)}"
              data-tapo-device-ids="${tapoEsc(ids)}"
              data-tapo-scheme-preset="${tapoEsc(presetJson)}"
            >
              ${window.dashboardIconHtml(icon)}
              ${showLabel ? `<span class="tapo-button-label">${tapoEsc(label)}</span>` : ""}
            </button>
  `;
}

window.renderTapoAsideLinks = function () {
  return `
      <button class="aside-link" type="button" data-tapo-action="manager">
        ${window.dashboardIconHtml("power")}
        <span class="aside-label">Tapo</span>
      </button>
  `;
};

window.renderTapoRoomActions = function (room, roomBulbs = [], roomControls = []) {
  const roomPowerEnabled = (c, defaultEnabled = false) => {
    const raw = c?.tapo_room_power;

    if (raw === undefined || raw === null || raw === "") {
      return defaultEnabled;
    }

    return (
      raw === true ||
      raw === 1 ||
      String(raw || "").toLowerCase() === "true" ||
      String(raw || "").toLowerCase() === "1" ||
      String(raw || "").toLowerCase() === "yes" ||
      String(raw || "").toLowerCase() === "on"
    );
  };

  const isRoomBulb = (c) => (
    c?.tapo_is_bulb ||
    c?.tapo_kind === "bulb" ||
    c?.tapo_kind === "lightstrip"
  );

  const byDeviceID = new Map();

  [...roomBulbs, ...roomControls].forEach(c => {
    const deviceID = c?.deviceID || "";

    if (!deviceID) return;
    if (!roomPowerEnabled(c, isRoomBulb(c))) return;

    byDeviceID.set(deviceID, c);
  });

  const roomPowerDevices = Array.from(byDeviceID.values());
  const roomSettingBulbs = roomPowerDevices.filter(isRoomBulb);
  const roomSettingSwitches = roomPowerDevices.filter(c => !isRoomBulb(c));

  if (!roomPowerDevices.length) return "";

  const firstBulb = roomSettingBulbs[0] || roomPowerDevices[0];
  const reportedPowerStates = S.tapoReportedPowerStates instanceof Map
    ? S.tapoReportedPowerStates
    : null;
  const allRoomPowerDevicesOffline = roomPowerDevices.every(c => {
    const deviceID = String(c?.deviceID || "");
    const reportedPower = reportedPowerStates
      ? reportedPowerStates.get(deviceID)
      : c?.tapo_is_on;

    return tapoRenderBool(reportedPower) === null;
  });
  const roomPowerStates = roomPowerDevices.map(c => tapoRenderBool(
    c?.tapo_is_on
    ?? c?.is_on
    ?? c?.device_on
    ?? c?.power_on
    ?? c?.on
    ?? c?.state
  ));
  const knownRoomPowerStates = roomPowerStates.filter(state => state !== null);
  const anyRoomPowerOn = knownRoomPowerStates.some(state => state === true);
  const allKnownRoomPowerOff = knownRoomPowerStates.length > 0 && knownRoomPowerStates.every(state => state === false);
  const roomPowerState = allRoomPowerDevicesOffline
    ? "unknown"
    : anyRoomPowerOn
      ? "on"
      : allKnownRoomPowerOff
        ? "off"
        : "unknown";
  const roomTapoDeviceIds = roomPowerDevices
    .map(c => c.deviceID || "")
    .filter(Boolean)
    .join(",");

  const toggleAction = roomPowerState === "on" ? "room-off" : "room-on";
  const toggleTitle = roomPowerState === "on"
    ? "Turn off room power"
    : roomPowerState === "unknown"
      ? "Room power state unknown — turn on room power"
      : "Turn on room power";
  const roomLightDeviceIDs = roomSettingBulbs
    .map(c => c.deviceID || "")
    .filter(Boolean);
  const roomSchemeMatch = getTapoRenderRoomSchemeMatch(roomLightDeviceIDs);
  const roomSchemeKey = roomSchemeMatch.key;
  const roomFavoriteSchemes = roomSchemeMatch.schemes;
  const useRoomFavoriteSchemes =
    roomFavoriteSchemes.length > 0 &&
    roomPowerState !== "unknown";
  const roomPowerControls = useRoomFavoriteSchemes
    ? `
            <div class="tapo-scheme-button-row room-scheme-button-row">
              ${roomFavoriteSchemes.map(scheme => renderTapoFavoriteSchemeButton({
                scheme,
                deviceIDs: roomLightDeviceIDs,
                targetKey: roomSchemeKey,
                className: "room-light-scheme",
                active: anyRoomPowerOn && tapoRenderSchemeIsActive(roomSchemeKey, scheme, roomSettingBulbs),
                showLabel: false
              })).join("")}
            </div>
      `
    : `
            <button
              class="icon-btn tapo-power-toggle power-toggle room-light-power ${roomPowerState === "on" ? "active" : ""} ${roomPowerState === "unknown" ? "unknown" : ""}"
              type="button"
              title="${tapoEsc(toggleTitle)}"
              aria-label="${tapoEsc(toggleTitle)}"
              data-tapo-action="${toggleAction}"
              data-tapo-power-state="${roomPowerState}"
              data-tapo-device-ids="${tapoEsc(roomTapoDeviceIds)}"
            >
              ${window.dashboardIconHtml("power_settings_new")}
              <span class="tapo-button-label">${roomPowerState === "on" ? "On" : roomPowerState === "unknown" ? "UNK" : "Off"}</span>
            </button>
      `;

  return `
          <div class="room-tapo-actions">
            ${roomPowerControls}

            ${roomSettingBulbs.length ? `
              <button
                class="icon-menu room-light-settings"
                type="button"
                title="Room light settings"
                aria-label="Room light settings"
                data-tapo-action="room-settings"
                data-tapo-device-ids="${tapoEsc(roomSettingBulbs.map(c => c.deviceID || "").filter(Boolean).join(","))}"
                data-tapo-room="${tapoEsc(room)}"
                data-tapo-name="${tapoEsc(room)} Lights"
                data-tapo-model="${tapoEsc(`${roomSettingBulbs.length} light${roomSettingBulbs.length === 1 ? "" : "s"}`)}"
                data-tapo-bulb-count="${roomSettingBulbs.length}"
                data-tapo-switch-count="${roomSettingSwitches.length}"
                data-brightness="${Number(firstBulb.tapo_brightness ?? firstBulb.brightness ?? 100)}"
                data-color-temp="${Number(firstBulb.tapo_color_temp ?? firstBulb.tapo_color_temperature ?? 4200)}"
                data-hue="${Number(firstBulb.tapo_hue ?? 45)}"
                data-saturation="${Number(firstBulb.tapo_saturation ?? 100)}"
                data-tapo-power-state="${roomPowerState}"
                data-supports-brightness="${roomSettingBulbs.some(c => c.tapo_supports_brightness !== false) ? "1" : "0"}"
                data-supports-color-temp="${roomSettingBulbs.some(c => c.tapo_supports_color_temp !== false) ? "1" : "0"}"
                data-supports-color="${roomSettingBulbs.some(c => c.tapo_supports_color !== false) ? "1" : "0"}"
              >
                ${window.dashboardIconHtml("more_vert")}
              </button>
            ` : ""}
          </div>
  `;
};

// Every Tapo title icon uses this one class path so cards rendered on the
// dashboard, in room settings, or elsewhere receive identical shared styling.
function tapoTitleIconClass(roleClass = "") {
  return [
    "icon-glow",
    "tapo-device-icon",
    roleClass
  ].filter(Boolean).join(" ");
}

window.renderTapoDevices = function (devices = []) {
  const root = document.getElementById("tapoCards");
  if (!root) return;

root.innerHTML = devices.map((d) => {
  const tapoKind = String(d.kind || (d.is_plug ? "plug" : "bulb")).toLowerCase();
  const isPlug = tapoKind === "plug" || tapoKind === "outlet_extender" || Boolean(d.is_plug);
  const isCamera = tapoKind === "camera" || Boolean(d.is_camera);

  const tapoIconClass = isCamera
    ? "status-tapo-camera"
    : isPlug
      ? "status-tapo-plug"
      : "status-tapo-bulb";

  const tapoIconName = window.dashboardDeviceIconName(d);

  return `
    <article class="card tapo-card" data-id="${tapoEsc(d.id)}" data-ip="${tapoEsc(d.ip)}" data-node-card="tapo" data-tapo-kind="${tapoEsc(tapoKind)}">
      <div class="card-head lone">
        <div class="status-area">
          ${window.dashboardIconHtml(tapoIconName, tapoTitleIconClass(tapoIconClass))}

          <div class="card-title-group">
            <div class="card-title">${tapoEsc(d.alias || d.model || d.ip)}</div>
            <div class="card-type-label">${tapoEsc(d.model || "Tapo device")}</div>
          </div>
        </div>

        <div class="card-actions">
          <button class="icon-menu" type="button" title="Tapo menu" aria-label="Open Tapo menu" data-dashboard-action="toggle-menu">
            ${window.dashboardIconHtml("more_vert")}
          </button>

          <div class="menu-content">
            <button class="menu-item" type="button" data-tapo-action="on" data-id="${tapoEsc(d.id)}">Turn On</button>
            <button class="menu-item" type="button" data-tapo-action="off" data-id="${tapoEsc(d.id)}">Turn Off</button>
            ${d.is_bulb ? `
              <button class="menu-item" type="button" data-tapo-action="brightness" data-value="25" data-id="${tapoEsc(d.id)}">Brightness 25%</button>
              <button class="menu-item" type="button" data-tapo-action="brightness" data-value="50" data-id="${tapoEsc(d.id)}">Brightness 50%</button>
              <button class="menu-item" type="button" data-tapo-action="brightness" data-value="100" data-id="${tapoEsc(d.id)}">Brightness 100%</button>
            ` : ""}
          </div>
        </div>
      </div>

      <div class="debug-area">
        <div class="debug-grid">
          <div class="debug-label">Status</div>
          <div class="debug-val" data-tapo-status>${d.control_ready ? (d.is_on ? "On" : "Off") : "Unknown"}</div>

          <div class="debug-label">IP</div>
          <div class="debug-val">${tapoEsc(d.ip)}</div>

          ${d.brightness != null ? `
            <div class="debug-label">Brightness</div>
            <div class="debug-val" data-tapo-brightness>${tapoEsc(d.brightness)}%</div>
          ` : ""}
        </div>
      </div>
    </article>
  `;
}).join("");
};

window.renderTapoCameraCard = function (c) {
  const id = tapoEsc(c.deviceID);
  const tapoId = tapoEsc(c.tapo_id || c.deviceID.replace(/^tapo:/, ""));
  const name = tapoEsc(c.clientName || c.tapo_alias || c.tapo_model || "Tapo Camera");
  const model = tapoEsc(c.tapo_model || "Camera");
  const zone = tapoEsc(c.zone_name || "");
  const rotation = Number(c.preview_rotation || 0);
  const previewUrl = c.tapo_hls_url || "";
  const isRec = !!(c.tapo_recording_enabled || c.tapo_recording);

  const statusText = c.stale
    ? "UNKNOWN"
    : (c.frame_live ? "ONLINE" : "NO FEED");

  return `
    <div
      class="card cameracard tapo-camera-card ${c.stale ? "stale-client" : ""}"
      data-device-id="${id}"
      data-node-card="camera"
      data-tapo-kind="camera"
    >
      <div class="camera-preview-container">
        <div class="card-head camera-card-head camera-preview-head">
          <div class="status-area">
            ${window.dashboardIconHtml("videocam", `status-cam ${c.stale ? "stale" : (c.frame_live ? "green" : "no-feed")}`)}
            <div class="card-title-group">
              <div class="card-title">${name}</div>
              <div class="card-type-label">${renderCardSubtitle(c)}</div>
            </div>
          </div>

          <div class="card-actions camera-card-actions">
            <button
              class="camera-record-btn tapo-camera-record-btn ${isRec ? "active" : ""}"
              type="button"
              title="${isRec ? "Stop Recording" : "Start Recording"}"
              aria-label="${isRec ? "Stop Recording" : "Start Recording"}"
              aria-pressed="${isRec ? "true" : "false"}"
              data-tapo-action="camera-record"
              data-device-id="${id}"
              data-tapo-id="${tapoId}"
              data-recording="${isRec ? "1" : "0"}"
            >
              <span class="camera-record-dot" aria-hidden="true"></span>
              <span class="camera-record-label">REC</span>
            </button>
            <button
              class="icon-menu tapo-camera-settings-open"
              type="button"
              title="Tapo camera settings"
              aria-label="Tapo camera settings"
              data-tapo-action="camera-settings"
              data-device-id="${id}"
              data-tapo-id="${tapoId}"
              data-tapo-kind="camera"
              data-tapo-name="${name}"
              data-tapo-brand="Tapo"
              data-tapo-model="${model}"
              data-zone-name="${zone}"
              data-preview-rotation="${rotation}"
              data-preview-url="${tapoEsc(previewUrl)}"
            >
              ${window.dashboardIconHtml("more_vert")}
            </button>
          </div>
        </div>

        <div class="camera-preview-rotator">
          <video
            class="camera-preview tapo-camera-video"
            muted
            playsinline
            autoplay
            data-hls-src="${tapoEsc(previewUrl)}"
            style="display:${previewUrl ? "block" : "none"}; transform: rotate(${rotation}deg);">
          </video>
        </div>
      </div>

      <div class="debug-area">
        <span class="debug-label">STATUS</span><span class="debug-val status-val">${statusText}</span>
        <span class="debug-label">IP</span><span class="debug-val ip-val">${tapoEsc(c.tapo_ip || c.ip || "—")}</span>
        <span class="debug-label">ID</span><span class="debug-val id-val">${id}</span>
        <span class="debug-label">MODEL</span><span class="debug-val">${model}</span>
        <span class="debug-label">ZONE</span><span class="debug-val">${zone || "—"}</span>
        <span class="debug-label">LAST UPDATE</span><span class="debug-val">${tapoEsc(formatLastUpdateText(c.last_update))}</span>
      </div>
    </div>
  `;
};

function renderTapoPowerButton({
  id,
  tapoId,
  powerState,
  childId = "",
  childName = "",
  childPosition = "",
  childIndex = "",
  titlePrefix = "",
  forcedAction = "",
  label = ""
}) {
  const isOn = powerState === "on";
  const isUnknown = powerState === "unknown";
  const toggleAction = forcedAction || (isOn ? "off" : "on");
  const buttonLabel = label || (isOn ? "On" : isUnknown ? "Unk" : "Off");
  const title = toggleAction === "off"
    ? `Turn Off${titlePrefix ? ` ${titlePrefix}` : ""}`
    : isUnknown
      ? `State unknown — Turn On${titlePrefix ? ` ${titlePrefix}` : ""}`
      : `Turn On${titlePrefix ? ` ${titlePrefix}` : ""}`;

  return `
            <button
              class="icon-btn tapo-power-toggle power-toggle${isOn ? " active" : ""}${isUnknown ? " unknown" : ""}"
              type="button"
              title="${tapoEsc(title)}"
              aria-label="${tapoEsc(title)}"
              data-tapo-action="${tapoEsc(toggleAction)}"
              data-tapo-power-state="${powerState}"
              data-device-id="${id}"
              data-tapo-id="${tapoId}"
              ${childId ? `data-tapo-child-id="${tapoEsc(childId)}"` : ""}
              ${childPosition !== "" ? `data-tapo-child-position="${tapoEsc(childPosition)}"` : ""}
              ${childIndex !== "" ? `data-tapo-child-index="${tapoEsc(childIndex)}"` : ""}
              ${childName ? `data-tapo-child-name="${tapoEsc(childName)}"` : ""}
            >
              ${window.dashboardIconHtml("power_settings_new")}
              <span class="tapo-button-label">${tapoEsc(buttonLabel)}</span>
            </button>
  `;
}

function tapoBool(value) {
  if (value === true || value === false) return value;

  const text = String(value ?? "").trim().toLowerCase();

  if (["1", "true", "on", "yes", "enabled"].includes(text)) return true;
  if (["0", "false", "off", "no", "disabled"].includes(text)) return false;

  return null;
}

function tapoControlSortName(c) {
  return String(
    c?.clientName ||
    c?.tapo_alias ||
    c?.tapo_model ||
    c?.deviceID ||
    ""
  ).trim().toLowerCase();
}

function tapoControlAlphaOrder(value) {
  const text = String(value || "").trim().toLowerCase().replace(/^[^a-z0-9]+/, "").padEnd(5, " ");
  let order = 0;

  for (let i = 0; i < 5; i += 1) {
    const code = text.charCodeAt(i);
    let weight = 0;

    if (code >= 48 && code <= 57) {
      weight = code - 47;
    } else if (code >= 97 && code <= 122) {
      weight = code - 86;
    }

    order = (order * 40) + weight;
  }

  return order;
}

window.renderTapoClientCard = function (c) {
  const cardID = tapoEsc(c.deviceID);
  const commandDeviceID = c.tapo_parent_device_id || c.deviceID || "";
  const commandID = tapoEsc(commandDeviceID);
  const tapoId = tapoEsc(c.tapo_id || String(commandDeviceID).replace(/^tapo:/, ""));
  const childIdRaw = String(c.tapo_child_id || "").trim();
  const childId = tapoEsc(childIdRaw);
  const childPosition = c.tapo_child_position ?? "";
  const childIndex = c.tapo_child_index ?? "";
  const childName = String(c.tapo_child_name || c.clientName || c.tapo_alias || "").trim();
  const isOutletChild = c.tapo_is_outlet_child === true;
  const tapoKind = String(c.tapo_kind || (c.tapo_is_plug ? "plug" : "bulb")).toLowerCase();
  const isPlug = tapoKind === "plug" || Boolean(c.tapo_is_plug);
  const isCamera = tapoKind === "camera" || Boolean(c.tapo_is_camera);
  const isBulb = tapoKind === "bulb" || tapoKind === "lightstrip" || Boolean(c.tapo_is_bulb);
  const supportsPower = c.tapo_supports_power === true || isPlug || isBulb;
  const controlReady = c.tapo_control_ready !== false && c.control_ready !== false;
  const rawPower = tapoBool(c.tapo_is_on ?? c.is_on ?? c.device_on ?? c.state);

  // An extender child with a confirmed Boolean power state must not inherit
  // a transient parent refresh failure and incorrectly render as unknown.
  const outletChildHasKnownPower = (
    isOutletChild &&
    (rawPower === true || rawPower === false)
  );

  // Preserve normal offline handling for every other Tapo device and for
  // extender children that genuinely have no confirmed power state.
  const powerState = !supportsPower
    ? "unsupported"
    : !controlReady && !outletChildHasKnownPower
      ? "unknown"
      : rawPower === true
        ? "on"
        : rawPower === false
          ? "off"
          : "unknown";

  const iconClass = isCamera
    ? "status-tapo-camera"
    : isPlug
      ? "status-tapo-plug"
      : "status-tapo-bulb";

  const iconName = window.dashboardDeviceIconName(c);
  const model = tapoEsc(c.tapo_model || c.tapo_child_model || (
    isCamera ? "Camera" :
    isPlug ? "Plug" :
    "Bulb"
  ));
  const brand = tapoEsc("Tapo");
  const zone = tapoEsc(c.zone_name || "");
  const brightness = Number(c.tapo_brightness ?? c.brightness ?? 100);
  const colorTemp = Number(c.tapo_color_temp ?? c.tapo_color_temperature ?? 4200);
  const hue = Number(c.tapo_hue ?? 45);
  const saturation = Number(c.tapo_saturation ?? 100);
  const supportsBrightness = isBulb && c.tapo_supports_brightness !== false;
  const supportsColorTemp = isBulb && c.tapo_supports_color_temp === true;
  const supportsColor = isBulb && c.tapo_supports_color === true;
  const supportsEnergy = tapoBool(c.tapo_supports_energy ?? c.supports_energy) === true;
  const energyAvailable = tapoBool(c.tapo_energy_available ?? c.energy_available) === true;
  const energyError = c.tapo_energy_error ?? c.energy_error ?? "";
  const energyUpdatedAt = c.tapo_energy_updated_at ?? c.energy_updated_at ?? "";
  const currentPowerW = c.tapo_current_power_w ?? c.current_power_w ?? "";
  const todayEnergyKWh = c.tapo_today_energy_kwh ?? c.today_energy_kwh ?? "";
  const monthEnergyKWh = c.tapo_month_energy_kwh ?? c.month_energy_kwh ?? "";
  const todayRuntimeMinutes = c.tapo_today_runtime_minutes ?? c.today_runtime_minutes ?? "";
  const monthRuntimeMinutes = c.tapo_month_runtime_minutes ?? c.month_runtime_minutes ?? "";
  const roomPowerRaw = c.tapo_room_power;
  const roomPower = (
    roomPowerRaw === undefined ||
    roomPowerRaw === null ||
    roomPowerRaw === ""
  )
    ? isBulb
    : (
      roomPowerRaw === true ||
      roomPowerRaw === 1 ||
      String(roomPowerRaw || "").toLowerCase() === "true" ||
      String(roomPowerRaw || "").toLowerCase() === "1" ||
      String(roomPowerRaw || "").toLowerCase() === "yes" ||
      String(roomPowerRaw || "").toLowerCase() === "on"
    );

  const controlSortGroup = (isBulb || tapoKind === "plug")
    ? roomPower ? 1 : 2
    : 9;

  const controlSortName = tapoControlSortName(c);
  const controlSortOrder = (controlSortGroup * 200000000) + tapoControlAlphaOrder(controlSortName);
  const deviceSchemeKey = `device:${c.deviceID || ""}`;
  const deviceFavoriteSchemes = isBulb ? getTapoRenderFavoriteSchemesForKey(deviceSchemeKey) : [];
  const powerButtonsHtml = deviceFavoriteSchemes.length
    ? `
          <div class="tapo-scheme-button-row">
            ${deviceFavoriteSchemes.map(scheme => renderTapoFavoriteSchemeButton({
              scheme,
              deviceIDs: [c.deviceID],
              targetKey: deviceSchemeKey,
              active: tapoRenderSchemeIsActive(deviceSchemeKey, scheme, [c])
            })).join("")}
          </div>
      `
    : supportsPower
      ? renderTapoPowerButton({
          id: commandID,
          tapoId,
          powerState,
          childId,
          childName,
          childPosition,
          childIndex,
          titlePrefix: childName
        })
      : "";
  const batteryValue = c.battery ?? c.tapo_battery ?? c.tapo_battery_percent ?? c.tapo_battery_level;
  const batteryHtml = batteryValue === undefined || batteryValue === null || batteryValue === ""
    ? ""
    : (typeof window.renderBattery === "function" ? window.renderBattery(batteryValue) : "");
  const settingsTitle = isPlug ? "Plug settings" : "Light settings";

  return `
    <div
      class="card tapo-client-card"
      style="order:${controlSortOrder};"
      data-device-id="${cardID}"
      data-node-card="tapo"
      data-tapo-kind="${tapoEsc(tapoKind)}"
      ${isOutletChild ? `data-tapo-parent-device-id="${commandID}" data-tapo-child-id="${childId}"` : ""}
      data-control-sort-group="${controlSortGroup}"
      data-control-sort-name="${tapoEsc(controlSortName)}"
      data-control-sort-order="${controlSortOrder}"
    >
      <div class="card-head lone" data-tapo-power-state="${powerState}">
        <div class="status-area">
          ${window.dashboardIconHtml(iconName, tapoTitleIconClass(iconClass))}

          <div class="card-title-group">
            <div class="card-title">${tapoEsc(c.clientName || c.tapo_alias || model)}</div>
            <div class="card-type-label">${renderCardSubtitle(c)}</div>
          </div>
        </div>

        <div class="card-actions">
          ${batteryHtml}

          <div class="tapo-device-power-controls">
            ${powerButtonsHtml}
          </div>

          <button
            class="icon-menu tapo-settings-open"
            type="button"
            title="${tapoEsc(settingsTitle)}"
            aria-label="${tapoEsc(settingsTitle)}"
            data-tapo-action="settings"
            data-device-id="${commandID}"
            data-tapo-card-id="${cardID}"
            data-tapo-id="${tapoId}"
            data-tapo-kind="${tapoEsc(tapoKind)}"
            ${isOutletChild ? `data-tapo-child-id="${childId}" data-tapo-child-position="${tapoEsc(childPosition)}" data-tapo-child-index="${tapoEsc(childIndex)}" data-tapo-child-name="${tapoEsc(childName)}" data-tapo-recharge-target-id="${tapoEsc(c.tapo_recharge_target_id || `${commandDeviceID}|${childIdRaw}`)}"` : ""}
            data-tapo-room-power="${roomPower ? "1" : "0"}"
            data-tapo-hide-dashboard="${tapoRenderBool(c.tapo_hide_dashboard ?? c.tapoHideDashboard ?? c.tapo_dashboard_hidden ?? c.dashboard_hidden ?? c.hide_dashboard) === true ? "1" : "0"}"
            data-tapo-name="${tapoEsc(c.clientName || c.tapo_alias || model)}"
            data-tapo-brand="${brand}"
            data-tapo-model="${model}"
            data-zone-name="${zone}"
            data-brightness="${brightness}"
            data-color-temp="${colorTemp}"
            data-hue="${hue}"
            data-saturation="${saturation}"
            data-tapo-power-state="${powerState}"
            data-supports-brightness="${supportsBrightness ? "1" : "0"}"
            data-supports-color-temp="${supportsColorTemp ? "1" : "0"}"
            data-supports-color="${supportsColor ? "1" : "0"}"
            data-tapo-supports-energy="${supportsEnergy ? "1" : "0"}"
            data-tapo-energy-available="${energyAvailable ? "1" : "0"}"
            data-tapo-energy-error="${tapoEsc(energyError)}"
            data-tapo-energy-updated-at="${tapoEsc(energyUpdatedAt)}"
            data-tapo-current-power-w="${tapoEsc(currentPowerW)}"
            data-tapo-today-energy-kwh="${tapoEsc(todayEnergyKWh)}"
            data-tapo-month-energy-kwh="${tapoEsc(monthEnergyKWh)}"
            data-tapo-today-runtime-minutes="${tapoEsc(todayRuntimeMinutes)}"
            data-tapo-month-runtime-minutes="${tapoEsc(monthRuntimeMinutes)}"
            data-tapo-control-ready="${controlReady ? "1" : "0"}"
            data-tapo-control-error="${tapoEsc(c.tapo_control_error || c.control_error || "")}"
          >
            ${window.dashboardIconHtml("more_vert")}
          </button>
        </div>
      </div>
    </div>
  `;
};