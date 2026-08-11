"use strict";

function matterEsc(value) {
  return typeof window.esc === "function" ? window.esc(value) : String(value ?? "");
}

function matterEscAttr(value) {
  return typeof window.escAttr === "function" ? window.escAttr(value) : matterEsc(value).replace(/"/g, "&quot;");
}

function matterDebugText(value, fallback = "—") {
  if (value === undefined || value === null) return fallback;

  const text = String(value).trim();
  return text || fallback;
}

function matterBool(value) {
  if (typeof window.dashboardBool === "function") return window.dashboardBool(value);

  if (value === true || value === 1) return true;
  if (value === false || value === 0) return false;

  const clean = String(value ?? "").trim().toLowerCase();
  if (["true", "1", "yes", "on", "enabled"].includes(clean)) return true;
  if (["false", "0", "no", "off", "disabled"].includes(clean)) return false;

  return null;
}

function matterPercent(value) {
  if (value === undefined || value === null || value === "") return "—";

  const number = Number(value);

  if (Number.isFinite(number)) {
    return `${number.toFixed(number % 1 === 0 ? 0 : 1)}%`;
  }

  return matterDebugText(value);
}

function matterBatteryLow(c) {
  const lowCandidates = [
    c?.matter_battery_low,
    c?.battery_low,
    c?.matter_battery_replacement_needed
  ];

  for (const value of lowCandidates) {
    const boolValue = matterBool(value);

    if (boolValue !== null) return boolValue;
  }

  const stateText = String(c?.battery_state ?? "").trim().toLowerCase();

  if (["low", "warning", "critical", "replace", "replacement_needed", "replacement-needed"].includes(stateText)) return true;
  if (["ok", "okay", "normal", "good", "nominal", "healthy"].includes(stateText)) return false;

  const chargeLevel = matterNumber(c?.matter_battery_charge_level);

  if (chargeLevel !== null) {
    return chargeLevel > 0;
  }

  const chargeText = String(c?.matter_battery_charge_level ?? "").trim().toLowerCase();

  if (["warning", "critical", "low", "replace", "replacement_needed", "replacement-needed"].includes(chargeText)) return true;
  if (["ok", "okay", "normal", "good", "nominal", "healthy"].includes(chargeText)) return false;

  return null;
}

function matterBatteryIconValue(c) {
  const low = matterBatteryLow(c);

  if (low === true) return 10;
  if (low === false) return 100;

  return null;
}

function matterBatteryText(c) {
  const low = matterBatteryLow(c);

  if (low === true) return "LOW";
  if (low === false) return "OK";

  return "—";
}

function matterBatteryDebugRows(c) {
  const battery = matterBatteryText(c);

  return battery === "—" ? [] : [["BATTERY", battery]];
}

function matterBoolText(value) {
  const boolValue = matterBool(value);

  if (boolValue === true) return "TRUE";
  if (boolValue === false) return "FALSE";

  return "—";
}

function matterLastUpdateText(c) {
  return matterDebugText(typeof window.formatLastUpdateText === "function" ? window.formatLastUpdateText(c?.last_update) : c?.last_update);
}

window.dashboardClientIsMatter = function (c) {
  return String(c?.source || "").trim().toLowerCase() === "matter" || String(c?.deviceID || "").startsWith("matter:");
};

window.dashboardClientIsMatterActionOnly = function (c) {
  if (window.dashboardClientIsMatter?.(c) !== true) return false;

  const kind = String(c?.matter_kind || "").trim().toLowerCase();
  const kinds = Array.isArray(c?.matter_kinds) ? c.matter_kinds : [kind];

  return kinds.some(item => (
    ["button", "switch", "onoff"].includes(String(item || "").trim().toLowerCase())
  ));
};

function matterNumber(value) {
  if (value === undefined || value === null || value === "") return null;

  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function matterRoomName(c) {
  if (typeof window.clientRoomName === "function") {
    return window.clientRoomName(c);
  }

  return String(c?.zone_name || c?.zoneName || "Unassigned").trim() || "Unassigned";
}

function matterRoomKey(value) {
  return String(value || "").trim().toLowerCase();
}

function matterTemperatureValue(c) {
  return matterNumber(c?.temperature_c);
}

function matterHumidityValue(c) {
  return matterNumber(c?.humidity_percent);
}

function matterAverage(values) {
  const cleanValues = (values || []).filter(value => Number.isFinite(value));

  if (!cleanValues.length) return null;

  return cleanValues.reduce((sum, value) => sum + value, 0) / cleanValues.length;
}

const MATTER_ENV_TEMPERATURE_UNIT_KEY = "kotibot_environment_temperature_unit";

function matterDashboardEnvironmentSettings() {
  const statusSettings = window.appState?.status?.matter_settings;

  if (statusSettings && typeof statusSettings === "object" && !Array.isArray(statusSettings)) {
    return statusSettings;
  }

  const bootstrapSettings = window.KOTIBOT_BOOTSTRAP?.status?.matter_settings;

  return bootstrapSettings && typeof bootstrapSettings === "object" && !Array.isArray(bootstrapSettings)
    ? bootstrapSettings
    : null;
}

let matterEnvironmentTemperatureUnitValue = matterNormalizeEnvironmentTemperatureUnit(
  matterDashboardEnvironmentSettings()?.temperature_unit
);

function matterNormalizeEnvironmentTemperatureUnit(unit) {
  return String(unit || "").trim().toLowerCase() === "f" ? "f" : "c";
}

function matterClearLegacyEnvironmentTemperatureUnit() {
  try {
    window.localStorage?.removeItem(MATTER_ENV_TEMPERATURE_UNIT_KEY);
  } catch {}
}

function matterEnvironmentTemperatureUnit() {
  return matterEnvironmentTemperatureUnitValue;
}

window.getMatterEnvironmentTemperatureUnit = matterEnvironmentTemperatureUnit;

function matterSetEnvironmentTemperatureUnitValue(unit) {
  const cleanUnit = matterNormalizeEnvironmentTemperatureUnit(unit);

  matterEnvironmentTemperatureUnitValue = cleanUnit;

  if (window.appState?.status) {
    window.appState.status.matter_settings = {
      ...(window.appState.status.matter_settings || {}),
      temperature_unit: cleanUnit
    };
  }

  matterClearLegacyEnvironmentTemperatureUnit();

  return cleanUnit;
}

window.loadMatterEnvironmentSettings = async function () {
  matterClearLegacyEnvironmentTemperatureUnit();

  const dashboardSettings = matterDashboardEnvironmentSettings();

  if (dashboardSettings) {
    matterSetEnvironmentTemperatureUnitValue(dashboardSettings.temperature_unit);

    return {
      temperature_unit: matterEnvironmentTemperatureUnit()
    };
  }

  try {
    const fetcher = typeof window.dashboardFetch === "function" ? window.dashboardFetch : fetch;
    const res = await fetcher("/api/matter/status", {
      cache: "no-store",
      credentials: "same-origin"
    });
    const data = await res.json();

    if (res.ok && data && data.ok !== false) {
      matterSetEnvironmentTemperatureUnitValue(data.settings?.temperature_unit);
    }
  } catch (err) {
    console.warn("[matter-settings] load failed", err);
  }

  return {
    temperature_unit: matterEnvironmentTemperatureUnit()
  };
};

window.saveMatterEnvironmentTemperatureUnit = async function (unit) {
  const cleanUnit = matterNormalizeEnvironmentTemperatureUnit(unit);
  const fetcher = typeof window.dashboardFetch === "function" ? window.dashboardFetch : fetch;
  const res = await fetcher("/api/matter/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ temperature_unit: cleanUnit })
  });
  const data = await res.json();

  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Matter settings save failed: ${res.status}`);
  }

  return data;
};

function matterTemperatureUnitSuffix() {
  return matterEnvironmentTemperatureUnit() === "f" ? "°F" : "°C";
}

function matterTemperatureDisplayValue(value) {
  const number = matterNumber(value);

  if (number === null) return null;

  if (matterEnvironmentTemperatureUnit() === "f") {
    return (number * 9 / 5) + 32;
  }

  return number;
}

function matterTemperatureText(value) {
  const number = matterTemperatureDisplayValue(value);

  if (number === null) return "—";

  return `${number.toFixed(1).replace(/\.0$/, "")}${matterTemperatureUnitSuffix()}`;
}

function matterHumidityText(value) {
  const number = matterNumber(value);

  if (number === null) return "—";

  return `${number.toFixed(number % 1 === 0 ? 0 : 1)}%`;
}

function matterEnvironmentCapsuleValuesHtml(temperature, humidity) {
  const temperatureText = temperature === null ? "" : matterTemperatureText(temperature);
  const humidityText = humidity === null ? "" : matterHumidityText(humidity);

  if (!temperatureText && !humidityText) return "";

  return [
    temperatureText
      ? `<span class="environment-capsule-temperature" data-card-value="temperature">${matterEsc(temperatureText)}</span>`
      : "",
    temperatureText && humidityText
      ? `<span class="environment-capsule-separator" aria-hidden="true">/</span>`
      : "",
    humidityText
      ? `<span class="environment-capsule-humidity" data-card-value="humidity">${matterEsc(humidityText)}</span>`
      : ""
  ].join("");
}

function matterCardEnvironmentCapsuleHtml(c) {
  const valuesHtml = matterEnvironmentCapsuleValuesHtml(
    matterTemperatureValue(c),
    matterHumidityValue(c)
  );

  return valuesHtml
    ? `<button class="environment-capsule" type="button" data-card-environment data-dashboard-action="show-environment-modal" aria-label="Open environment and conditions">${valuesHtml}</button>`
    : "";
}

function matterEnvironmentKinds(c) {
  return matterKinds(c).filter(kind => ["temperature", "humidity", "environment"].includes(kind));
}

function matterCustomClientName(c) {
  const clientName = String(c?.clientName || "").trim();
  const nodeLabel = String(c?.matter_node_label || "").trim();

  if (!clientName) return "";

  return !nodeLabel || clientName !== nodeLabel ? clientName : "";
}

function matterGroupedDisplayName(clients, representative, fallback) {
  const customName = (clients || [])
    .map(matterCustomClientName)
    .find(Boolean);

  return customName || String(
    representative?.clientName ||
    representative?.matter_node_label ||
    representative?.matter_product_name ||
    representative?.model ||
    fallback
  ).trim();
}

window.dashboardClientIsMatterEnvironment = function (c) {
  if (window.dashboardClientIsMatter?.(c) !== true) return false;

  const kinds = matterKinds(c);
  const hasEnvironment = matterEnvironmentKinds(c).length > 0;
  const hasSecurity = kinds.some(kind => ["contact", "motion"].includes(kind));

  return hasEnvironment && !hasSecurity;
};

function matterEnvironmentClients(clients) {
  return (clients || []).filter(c => window.dashboardClientIsMatterEnvironment?.(c));
}

function matterEnvironmentGroups(clients) {
  const groups = matterPhysicalClientGroups(matterEnvironmentClients(clients)).map((physicalClients, index) => {
    const first = physicalClients[0] || {};
    const displayName = matterGroupedDisplayName(physicalClients, first, "Matter Environment Sensor");
    const group = {
      key: matterMatchedSerialGroupKey(first, physicalClients) || `environment:${index}`,
      clients: [],
      room: matterRoomName(first),
      name: displayName,
      product: first?.matter_product_name || first?.model || "",
      serial: first?.matter_serial_number || "",
      reachable: [],
      temperatures: [],
      humidities: [],
      lastUpdate: first?.last_update || ""
    };

    physicalClients.forEach(c => {
      const temperature = matterTemperatureValue(c);
      const humidity = matterHumidityValue(c);

      group.clients.push(c);
      group.room = group.room || matterRoomName(c);
      group.name = group.name || matterGroupedDisplayName([c], c, "Matter Environment Sensor");
      group.product = group.product || c?.matter_product_name || c?.model || "";
      group.serial = group.serial || c?.matter_serial_number || "";
      group.lastUpdate = c?.last_update || group.lastUpdate;

      if (temperature !== null) group.temperatures.push(temperature);
      if (humidity !== null) group.humidities.push(humidity);

      const reachable = matterBool(c?.matter_reachable);
      if (reachable !== null) group.reachable.push(reachable);
    });

    return group;
  });

  return groups.sort((a, b) => (
    String(a.room || "").localeCompare(String(b.room || "")) ||
    String(a.name || "").localeCompare(String(b.name || "")) ||
    String(a.serial || "").localeCompare(String(b.serial || ""))
  ));
}

function matterEnvironmentReachableText(group) {
  if (!group?.reachable?.length) return "—";
  if (group.reachable.some(value => value === false)) return "FALSE";
  if (group.reachable.some(value => value === true)) return "TRUE";

  return "—";
}

function matterEnvironmentGroupHtml(group) {
  const temperature = matterAverage(group.temperatures);
  const humidity = matterAverage(group.humidities);

  return `
    <section class="modal-section matter-environment-device">
      <div class="matter-environment-device-head">
        <div>
          <div class="modal-section-title matter-environment-device-title">${matterEsc(group.name)}</div>
          <div class="modal-subtitle matter-environment-device-subtitle">${matterEsc(group.room || "Unassigned")}</div>
        </div>
      </div>

      <div class="matter-environment-readout-grid">
        <div class="matter-environment-readout">
          <span class="matter-environment-readout-label">Temperature</span>
          <span class="matter-environment-readout-value">${matterEsc(matterTemperatureText(temperature))}</span>
        </div>
        <div class="matter-environment-readout">
          <span class="matter-environment-readout-label">Humidity</span>
          <span class="matter-environment-readout-value">${matterEsc(matterHumidityText(humidity))}</span>
        </div>
      </div>

      <div class="client-menu-row">
        <span class="client-menu-label">Model</span>
        <span class="client-menu-value">${matterEsc(matterDebugText(group.product))}</span>
      </div>
      <div class="client-menu-row">
        <span class="client-menu-label">Serial</span>
        <span class="client-menu-value">${matterEsc(matterDebugText(group.serial))}</span>
      </div>
      <div class="client-menu-row">
        <span class="client-menu-label">Reachable</span>
        <span class="client-menu-value">${matterEsc(matterEnvironmentReachableText(group))}</span>
      </div>
      <div class="client-menu-row">
        <span class="client-menu-label">Last Update</span>
        <span class="client-menu-value">${matterEsc(matterDebugText(group.lastUpdate))}</span>
      </div>
    </section>
  `;
}

function ensureMatterEnvironmentModal() {
  let modal = document.getElementById("matterEnvironmentModal");

  if (modal) return modal;

  document.body.insertAdjacentHTML("beforeend", `
    <div id="matterEnvironmentModal" class="modal" hidden>
      <div class="modal-shell">
        <div class="modal-head">
          <div class="modal-title-wrap">
            <div id="matterEnvironmentModalTitle" class="modal-title">Environment</div>
            <div id="matterEnvironmentModalSubtitle" class="modal-subtitle">System-wide environmental sensors</div>
          </div>

          <div class="modal-head-actions">
            <button
              id="matterEnvironmentSettingsToggle"
              class="modal-close"
              type="button"
              data-dashboard-action="show-environment-settings"
              aria-label="Environment settings"
              aria-expanded="false"
              title="Environment settings"
            >
              ${window.dashboardIconHtml("settings")}
            </button>

            <button class="modal-close" type="button" data-dashboard-action="hide-environment-modal" aria-label="Close environment">
              ${window.dashboardIconHtml("close")}
            </button>
          </div>
        </div>
        <div id="matterEnvironmentModalBody" class="modal-body"></div>
      </div>
    </div>
  `);

  return document.getElementById("matterEnvironmentModal");
}

window.hideMatterEnvironmentModal = function () {
  const modal = document.getElementById("matterEnvironmentModal");

  if (!modal) return;

  modal.hidden = true;

  const anyOpen = [...document.querySelectorAll(".modal")]
    .some(item => item && item.hidden === false);

  if (!anyOpen) {
    document.body.classList.remove("modal-open");
  }
};

function matterEnvironmentSettingsExpanded() {
  const modal = document.getElementById("matterEnvironmentModal");
  return modal?.dataset?.showSettings === "1";
}

function matterSetEnvironmentSettingsExpanded(expanded) {
  const modal = ensureMatterEnvironmentModal();

  if (modal) {
    modal.dataset.showSettings = expanded ? "1" : "0";
  }

  return modal;
}

function matterEnvironmentSettingsSectionHtml() {
  const unit = matterEnvironmentTemperatureUnit();

  return `
    <section id="matterEnvironmentSettingsSection" class="modal-section" ${matterEnvironmentSettingsExpanded() ? "" : "hidden"}>
      <div class="modal-section-title">Temperature Units</div>
      <div class="client-menu-actions">
        <button
          class="settings-item ${unit === "c" ? "active" : ""}"
          type="button"
          aria-pressed="${unit === "c" ? "true" : "false"}"
          data-dashboard-action="set-environment-temp-unit"
          data-unit="c"
        >
          °C
        </button>
        <button
          class="settings-item ${unit === "f" ? "active" : ""}"
          type="button"
          aria-pressed="${unit === "f" ? "true" : "false"}"
          data-dashboard-action="set-environment-temp-unit"
          data-unit="f"
        >
          °F
        </button>
      </div>
    </section>
  `;
}

window.renderMatterEnvironmentModal = function () {
  const modal = ensureMatterEnvironmentModal();
  const body = document.getElementById("matterEnvironmentModalBody");
  const settingsToggle = document.getElementById("matterEnvironmentSettingsToggle");
  const groups = matterEnvironmentGroups(window.appState?.currentClients || []);
  const settingsOpen = matterEnvironmentSettingsExpanded();

  if (!modal || !body) return;

  body.innerHTML = `
    ${matterEnvironmentSettingsSectionHtml()}
    ${groups.length
      ? groups.map(matterEnvironmentGroupHtml).join("")
      : `
        <section class="modal-section">
          <div class="modal-subtitle">No environmental sensors are reporting yet.</div>
        </section>
      `}
  `;

  if (settingsToggle) {
    settingsToggle.classList.toggle("active", settingsOpen);
    settingsToggle.setAttribute("aria-expanded", settingsOpen ? "true" : "false");
    settingsToggle.title = settingsOpen ? "Hide environment settings" : "Environment settings";
    settingsToggle.setAttribute("aria-label", settingsToggle.title);
  }
};

window.toggleMatterEnvironmentSettings = function () {
  matterSetEnvironmentSettingsExpanded(!matterEnvironmentSettingsExpanded());
  window.renderMatterEnvironmentModal?.();
};

window.setMatterEnvironmentTemperatureUnit = async function (unit) {
  const cleanUnit = matterNormalizeEnvironmentTemperatureUnit(unit);
  const previousUnit = matterEnvironmentTemperatureUnit();

  if (cleanUnit === previousUnit) {
    return;
  }

  matterSetEnvironmentTemperatureUnitValue(cleanUnit);
  window.renderMatterEnvironmentModal?.();
  window.renderDashboard?.();

  try {
    const data = await window.saveMatterEnvironmentTemperatureUnit?.(cleanUnit);
    const savedUnit = matterNormalizeEnvironmentTemperatureUnit(data?.settings?.temperature_unit || cleanUnit);

    if (savedUnit !== cleanUnit) {
      matterSetEnvironmentTemperatureUnitValue(savedUnit);
      window.renderMatterEnvironmentModal?.();
      window.renderDashboard?.();
    }
  } catch (err) {
    console.warn("[matter-settings] temperature unit save failed", err);
    matterSetEnvironmentTemperatureUnitValue(previousUnit);
    window.renderMatterEnvironmentModal?.();
    window.renderDashboard?.();
  }
};

window.showMatterEnvironmentModal = function () {
  window.closeAllMenus?.();

  const modal = ensureMatterEnvironmentModal();

  if (!modal) return;

  modal.hidden = false;
  document.body.classList.add("modal-open");
  window.renderMatterEnvironmentModal?.();
};

window.syncMatterRoomEnvironmentHeader = function (group, room, clients) {
  const slot = group?.querySelector?.("[data-room-environment]");

  if (!slot) return;

  const roomName = String(room || "").trim();
  const roomKey = matterRoomKey(roomName);
  const roomEnvironmentGroups = matterEnvironmentGroups(clients).filter(environmentGroup => (
    matterRoomKey(environmentGroup.room) === roomKey
  ));
  const reportingTemperatures = roomEnvironmentGroups
    .map(environmentGroup => matterAverage(environmentGroup.temperatures))
    .filter(value => Number.isFinite(value));
  const reportingHumidities = roomEnvironmentGroups
    .map(environmentGroup => matterAverage(environmentGroup.humidities))
    .filter(value => Number.isFinite(value));
  const averageTemperature = reportingTemperatures.length > 1
    ? matterAverage(reportingTemperatures)
    : null;
  const averageHumidity = reportingHumidities.length > 1
    ? matterAverage(reportingHumidities)
    : null;
  const valuesHtml = matterEnvironmentCapsuleValuesHtml(
    averageTemperature,
    averageHumidity
  );

  if (!valuesHtml) {
    slot.hidden = true;
    slot.innerHTML = "";
    return;
  }

  slot.hidden = false;
  slot.innerHTML = `
    <button class="environment-capsule" type="button" aria-label="Open ${matterEscAttr(roomName)} environment" data-dashboard-action="show-environment-modal" data-room="${matterEscAttr(roomName)}" title="Show system environment">
      ${valuesHtml}
    </button>
  `;
};

function matterKind(c) {
  const explicitKind = String(c?.matter_kind || "matter").trim().toLowerCase() || "matter";

  if (explicitKind !== "matter") return explicitKind;

  const clusterText = String(c?.matter_cluster || "").trim().toLowerCase();

  if (
    clusterText.includes("occupancysensing") ||
    c?.occupancy_state_value !== undefined ||
    c?.motion_active !== undefined
  ) {
    return "motion";
  }

  return explicitKind;
}

function matterKinds(c) {
  const rawKinds = Array.isArray(c?.matter_kinds) && c.matter_kinds.length
    ? c.matter_kinds
    : [matterKind(c)];
  const cleanKinds = [];

  rawKinds.forEach(kind => {
    const cleanKind = String(kind || "").trim().toLowerCase();

    if (cleanKind && cleanKind !== "matter" && !cleanKinds.includes(cleanKind)) {
      cleanKinds.push(cleanKind);
    }
  });

  return cleanKinds.length ? cleanKinds : [matterKind(c)];
}

function matterKindText(c) {
  return matterKinds(c).join(", ");
}

function matterCapabilityLabel(kind) {
  const cleanKind = String(kind || "").trim().toLowerCase();

  if (cleanKind === "temperature") return "Temperature";
  if (cleanKind === "humidity") return "Humidity";
  if (cleanKind === "contact") return "Contact";
  if (cleanKind === "motion") return "Motion";
  if (cleanKind === "environment") return "Environment";
  if (cleanKind === "switch") return "Switch";
  if (cleanKind === "button") return "Button";
  if (cleanKind === "onoff") return "Switch";

  return cleanKind ? cleanKind.charAt(0).toUpperCase() + cleanKind.slice(1) : "Matter";
}

function matterCapabilityText(c) {
  return matterKinds(c).map(matterCapabilityLabel).join(", ");
}

function matterSensorTypeText(c) {
  return matterCapabilityText(c);
}

function matterConnectedHubName(c) {
  const candidates = [
    c?.tapo_parent_alias,
    c?.tapo_parent_name,
    c?.tapo_hub_name,
    c?.matter_hub_name,
    c?.matter_bridge_name,
    c?.matter_parent_alias,
    c?.matter_parent_name,
    c?.matter_parent_label,
  ];

  return candidates
    .map(value => String(value || "").trim())
    .find(Boolean) || "";
}

function matterConnectedHubSubtitle(c, fallback = "") {
  const hubName = matterConnectedHubName(c);

  return hubName ? `Connected to hub: ${hubName}` : fallback;
}

function matterSubtitle(c) {
  const kinds = matterKinds(c);
  const sensorKinds = kinds.filter(kind => ["temperature", "humidity", "contact", "motion", "environment"].includes(kind));
  const controlKinds = kinds.filter(kind => ["switch", "button", "onoff"].includes(kind));
  const fallback = controlKinds.length && !sensorKinds.length
    ? `Matter Device - ${matterSensorTypeText(c)}`
    : `Matter Sensor - ${matterSensorTypeText(c)}`;

  return matterConnectedHubSubtitle(c, fallback);
}

function matterIcon(c) {
  return window.dashboardDeviceIconName(c);
}

function matterContactOpen(c) {
  const doorStatus = String(c?.door_status || "").trim().toLowerCase();

  if (doorStatus === "open") return true;
  if (doorStatus === "closed" || doorStatus === "close") return false;

  const contactOpen = matterBool(c?.contact_open);
  if (contactOpen !== null) return contactOpen;

  return matterBool(c?.contact_state_value);
}

function matterOnOffValue(c) {
  return matterBool(c?.matter_onoff ?? c?.onoff ?? c?.on_off);
}

function matterMotionActive(c) {
  const active = matterBool(c?.motion_active);

  if (active !== null) return active;

  const occupancy = matterNumber(c?.occupancy_state_value);
  return occupancy === null ? null : Boolean(occupancy & 1);
}

function matterSwitchPositionText(c) {
  const position = matterNumber(c?.matter_switch_position);
  const positions = matterNumber(c?.matter_switch_positions);

  if (position === null) return "—";

  return positions === null ? `POSITION ${position}` : `POSITION ${position} / ${positions}`;
}

function matterButtonEventText(c) {
  const event = String(c?.matter_button_event || "").trim();

  if (!event) return matterSwitchPositionText(c);

  const count = matterNumber(c?.matter_button_press_count);
  const suffix = count === null ? "" : ` x${count}`;

  return `${event.replace(/_/g, " ").toUpperCase()}${suffix}`;
}

function matterStatusText(c) {
  if (c?.stale) return "UNKNOWN";

  const reachable = matterBool(c?.matter_reachable);

  if (reachable === false) return "UNREACHABLE";

  const kinds = matterKinds(c);
  const kind = matterKind(c);

  if (kinds.includes("temperature") && kinds.includes("humidity")) {
    return `${matterTemperatureText(c?.temperature_c)} / ${matterHumidityText(c?.humidity_percent)}`;
  }

  if (kind === "temperature" && c?.temperature_c !== undefined && c?.temperature_c !== null) {
    return matterTemperatureText(c.temperature_c);
  }

  if (kind === "humidity" && c?.humidity_percent !== undefined && c?.humidity_percent !== null) {
    return matterHumidityText(c.humidity_percent);
  }

  if (kind === "contact" || c?.contact_state_value !== undefined || c?.contact_open !== undefined) {
    const isOpen = matterContactOpen(c);

    if (isOpen === true) return "OPEN";
    if (isOpen === false) return "CLOSED";
  }

  if (kind === "motion" || c?.occupancy_state_value !== undefined || c?.motion_active !== undefined) {
    const motionActive = matterMotionActive(c);

    if (motionActive === true) return "MOTION";
    if (motionActive === false) return "CLEAR";
  }

  if (kind === "switch" || kind === "onoff" || c?.matter_onoff !== undefined) {
    const onoff = matterOnOffValue(c);

    if (onoff === true) return "ON";
    if (onoff === false) return "OFF";
  }

  if (kind === "button" || c?.matter_switch_position !== undefined || c?.matter_button_event) {
    return matterButtonEventText(c);
  }

  return reachable === true ? "REACHABLE" : "ONLINE";
}

function matterStatusClass(c) {
  const kinds = matterKinds(c);

  if (c?.stale) return "stale";
  if (matterBool(c?.matter_reachable) === false) return "stale";

  if (
    kinds.includes("contact") &&
    matterContactOpen(c) === true
  ) {
    return "green security-active";
  }

  if (
    kinds.includes("motion") &&
    matterMotionActive(c) === true
  ) {
    return "green security-active";
  }

  if (
    (
      kinds.includes("switch") ||
      kinds.includes("onoff")
    ) &&
    matterOnOffValue(c) === true
  ) {
    return "mint-blue-flash";
  }

  if (
    kinds.includes("button") &&
    String(c?.matter_button_event || "").trim()
  ) {
    return "mint-blue-flash";
  }

  return "green";
}

function matterDebugIdsText(c) {
  if (Array.isArray(c?.matter_device_ids) && c.matter_device_ids.length) {
    return c.matter_device_ids.join(", ");
  }

  return matterDebugText(c?.deviceID);
}

function matterDebugEndpointsText(c) {
  if (Array.isArray(c?.matter_endpoints) && c.matter_endpoints.length) {
    return c.matter_endpoints.join(", ");
  }

  return matterDebugText(c?.matter_endpoint);
}

window.dashboardDebugRowsForMatter = function (c) {
  const grouped = Array.isArray(c?.matter_device_ids) && c.matter_device_ids.length > 1;

  return [
    ["STATUS", matterStatusText(c)],
    [grouped ? "IDS" : "ID", matterDebugIdsText(c)],
    ["NODE", matterDebugText(c?.matter_node_id)],
    [grouped ? "ENDPOINTS" : "ENDPOINT", matterDebugEndpointsText(c)],
    ["KIND", matterDebugText(matterKindText(c))],
    ["LABEL", matterDebugText(c?.matter_node_label)],
    ["SERIAL", matterDebugText(c?.matter_serial_number)],
    ...(["switch", "onoff"].includes(matterKind(c)) ? [
      ["ON/OFF", matterBoolText(c?.matter_onoff)]
    ] : []),
    ...(matterKind(c) === "button" ? [
      ["BUTTON EVENT", matterDebugText(c?.matter_button_event)],
      ["POSITION", matterDebugText(c?.matter_switch_position)],
      ["POSITIONS", matterDebugText(c?.matter_switch_positions)],
      ["MULTI PRESS MAX", matterDebugText(c?.matter_switch_multipress_max)],
      ["PRESS COUNT", matterDebugText(c?.matter_button_press_count)]
    ] : []),
    ...matterBatteryDebugRows(c),
    ["ZONE", matterDebugText(c?.zone_name || c?.zoneName)],
    ["LAST UPDATE", matterLastUpdateText(c)]
  ];
};

window.renderMatterClientCard = function (c) {
  const id = matterEsc(c?.deviceID || "");
  const kind = matterKind(c);
  const kinds = matterKinds(c);
  const hasTemperature = (
    kinds.includes("temperature") ||
    matterNumber(c?.temperature_c) !== null
  );
  const hasHumidity = (
    kinds.includes("humidity") ||
    matterNumber(c?.humidity_percent) !== null
  );
  const isEnvironmentSensor = (
    hasTemperature ||
    hasHumidity
  );
  const isContactSensor = (
    !isEnvironmentSensor &&
    kinds.includes("contact")
  );
  const isMotionSensor = (
    !isEnvironmentSensor &&
    kinds.includes("motion")
  );
  const isSecuritySensor = (
    isContactSensor ||
    isMotionSensor
  );
  const cardKind = isEnvironmentSensor
    ? "environment"
    : kind;
  const title = matterEsc(c?.matter_card_title || c?.clientName || c?.matter_node_label || c?.deviceID || "Matter Sensor");
  const environmentHtml = matterCardEnvironmentCapsuleHtml(c);
  const batteryIconValue = matterBatteryIconValue(c);
  const reserveBatterySlot = isSecuritySensor;
  const batteryHtml = batteryIconValue === null && !reserveBatterySlot
    ? ""
    : (
      typeof window.renderBattery === "function"
        ? window.renderBattery(
            batteryIconValue,
            window.dashboardBatteryHoverText?.(c)
          )
        : ""
    );
  const cardClass = `card matter-card matter-${matterEscAttr(cardKind)}-card ${c?.stale ? "stale-client" : ""}`;
  const nodeCard = isSecuritySensor ? "door" : "matter";
  const iconClass = isSecuritySensor
    ? "status-door"
    : "status-matter";
  const iconText = matterIcon(c);

  return `
    <div class="${cardClass}" data-device-id="${id}" data-node-card="${nodeCard}" data-matter-kind="${matterEscAttr(cardKind)}">
      <div class="card-head lone">
        <div class="status-area">
          ${window.dashboardIconHtml(iconText, `${iconClass} ${matterStatusClass(c)}`)}
          <div class="card-title-group">
            <div class="card-title">${title}</div>
            <div class="card-type-label">${matterEsc(matterSubtitle(c))}</div>
          </div>
          ${environmentHtml}
        </div>

        <div class="card-actions">
          ${batteryHtml}

          <button
            class="icon-menu"
            type="button"
            data-dashboard-action="open-client-menu"
            data-device-id="${id}"
            data-menu-kind="matter"
          >
            ${window.dashboardIconHtml("more_vert")}
          </button>
        </div>
      </div>
    </div>
  `;
};

window.syncMatterCardEnvironment = function (el, c) {
  if (!el || window.dashboardClientIsMatter?.(c) !== true) return;

  const valuesHtml = matterEnvironmentCapsuleValuesHtml(
    matterTemperatureValue(c),
    matterHumidityValue(c)
  );
  let capsule = el.querySelector("[data-card-environment]");

  if (!valuesHtml) {
    capsule?.remove();
    return;
  }

  if (!capsule) {
    const titleGroup = el.querySelector(".status-area > .card-title-group");

    titleGroup?.insertAdjacentHTML(
      "afterend",
      `<button class="environment-capsule" type="button" data-card-environment data-dashboard-action="show-environment-modal" aria-label="Open environment and conditions">${valuesHtml}</button>`
    );
    return;
  }

  capsule.innerHTML = valuesHtml;
};

function matterAssignedRoomValue(c) {
  const candidates = [
    c?.zone_name,
    c?.zoneName,
    c?.room_name,
    c?.room,
    c?.zone,
    c?.area
  ];

  for (const value of candidates) {
    const clean = String(value ?? "").trim();

    if (clean) return clean;
  }

  return "";
}

function matterIsUnassigned(c) {
  const room = matterAssignedRoomValue(c).trim().toLowerCase();

  return !room || ["unassigned", "unknown", "none", "null", "—", "-"].includes(room);
}

function matterEndpointSortValue(c) {
  const number = Number(c?.matter_endpoint);
  return Number.isFinite(number) ? number : 999999;
}

function matterClientSortValue(a, b) {
  return (
    matterEndpointSortValue(a) - matterEndpointSortValue(b) ||
    matterKind(a).localeCompare(matterKind(b)) ||
    String(a?.matter_node_label || a?.clientName || a?.deviceID || "").localeCompare(String(b?.matter_node_label || b?.clientName || b?.deviceID || ""))
  );
}

function matterEnvironmentEndpointKind(c) {
  const kinds = matterKinds(c);

  if (kinds.includes("temperature")) return "temperature";
  if (kinds.includes("humidity")) return "humidity";

  return "";
}

function matterPhysicalIdentity(c) {
  return String(
    c?.matter_node_label ||
    c?.matter_product_name ||
    c?.model ||
    ""
  ).trim().toLowerCase();
}

function matterEnvironmentPair(c, clients) {
  const kind = matterEnvironmentEndpointKind(c);
  const endpoint = matterEndpointSortValue(c);
  const nodeID = String(c?.matter_node_id || "").trim();
  const identity = matterPhysicalIdentity(c);

  if (!kind || endpoint === 999999 || !nodeID) return null;

  return (clients || [])
    .filter(other => other !== c)
    .filter(other => {
      const otherKind = matterEnvironmentEndpointKind(other);
      return otherKind && otherKind !== kind;
    })
    .filter(other => String(other?.matter_node_id || "").trim() === nodeID)
    .filter(other => {
      const otherIdentity = matterPhysicalIdentity(other);
      return !identity || !otherIdentity || otherIdentity === identity;
    })
    .filter(other => {
      const otherEndpoint = matterEndpointSortValue(other);
      return otherEndpoint !== 999999 && Math.abs(otherEndpoint - endpoint) === 1;
    })
    .sort(matterClientSortValue)[0] || null;
}

function matterMatchedSerialGroupKey(c, clients = []) {
  const serial = String(c?.matter_serial_number || "").trim();

  if (serial) return `serial:${serial}`;

  const pair = matterEnvironmentPair(c, clients);
  const pairSerial = String(pair?.matter_serial_number || "").trim();

  if (pairSerial) return `serial:${pairSerial}`;

  if (pair) {
    const nodeID = String(c?.matter_node_id || "").trim();
    const identity = matterPhysicalIdentity(c) || matterPhysicalIdentity(pair);
    const endpoints = [matterEndpointSortValue(c), matterEndpointSortValue(pair)]
      .sort((a, b) => a - b)
      .join("-");

    return `environment:${nodeID}:${identity}:${endpoints}`;
  }

  return `device:${c?.deviceID || ""}`;
}

function matterPhysicalClientGroups(clients) {
  const list = [...(clients || [])];
  const groups = new Map();

  list.forEach(c => {
    const key = matterMatchedSerialGroupKey(c, list);

    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  });

  return [...groups.values()].map(group => group.sort(matterClientSortValue));
}

window.dashboardMatterRelatedDeviceIDs = function (deviceID, clients) {
  const cleanDeviceID = String(deviceID || "").trim();
  const matterClients = (clients || []).filter(c => window.dashboardClientIsMatter?.(c));
  const sourceClient = matterClients.find(c => String(c?.deviceID || "").trim() === cleanDeviceID);

  if (!sourceClient) return cleanDeviceID ? [cleanDeviceID] : [];

  const relatedClients = matterPhysicalClientGroups(matterClients)
    .find(group => group.includes(sourceClient)) || [sourceClient];
  const ids = relatedClients
    .sort(matterClientSortValue)
    .map(c => String(c?.deviceID || "").trim())
    .filter(Boolean);

  return ids.length ? ids : [cleanDeviceID];
};

function matterGroupedClientFromSerial(clients) {
  const sortedClients = [...(clients || [])].sort(matterClientSortValue);

  if (sortedClients.length <= 1) return sortedClients[0] || null;

  const first = sortedClients[0];
  const ids = sortedClients.map(c => String(c?.deviceID || "").trim()).filter(Boolean);
  const endpoints = sortedClients.map(c => String(c?.matter_endpoint || "").trim()).filter(Boolean);
  const kinds = [];

  sortedClients.forEach(c => {
    matterKinds(c).forEach(kind => {
      if (kind && !kinds.includes(kind)) kinds.push(kind);
    });
  });

  const temperatureClient = sortedClients.find(c => matterTemperatureValue(c) !== null);
  const humidityClient = sortedClients.find(c => matterHumidityValue(c) !== null);
  const contactClient = sortedClients.find(c => matterKind(c) === "contact");
  const motionClient = sortedClients.find(c => matterKind(c) === "motion");
  const switchClient = sortedClients.find(c => ["switch", "onoff"].includes(matterKind(c)) || c?.matter_onoff !== undefined);
  const buttonClient = sortedClients.find(c => matterKind(c) === "button" || c?.matter_switch_position !== undefined || c?.matter_button_event);
  const batteryClient = sortedClients.find(c => matterBatteryIconValue(c) !== null);
  const representative = temperatureClient || humidityClient || contactClient || motionClient || switchClient || buttonClient || batteryClient || first;
  const displayName = matterGroupedDisplayName(sortedClients, representative, "Matter Sensor");
    const groupedKind = contactClient
    ? "contact"
    : motionClient
      ? "motion"
      : (kinds.includes("temperature") && kinds.includes("humidity"))
        ? "environment"
        : (kinds.find(kind => kind !== "matter") || matterKind(representative));
  const reachableValues = sortedClients
    .map(c => matterBool(c?.matter_reachable))
    .filter(value => value !== null);
  const anyUnreachable = reachableValues.some(value => value === false);
  const anyReachable = reachableValues.some(value => value === true);

  return {
    ...representative,
    deviceID: ids[0] || representative?.deviceID || first?.deviceID || "",
    clientName: displayName,
    matter_card_title: displayName,
    matter_kind: groupedKind,
    matter_kinds: kinds,
    matter_device_ids: ids,
    matter_endpoints: endpoints,
    matter_endpoint: endpoints.join(", "),
    matter_grouped: true,
    matter_group_size: sortedClients.length,
    matter_group_clients: sortedClients,
    temperature_c: temperatureClient ? matterTemperatureValue(temperatureClient) : representative?.temperature_c,
    humidity_percent: humidityClient ? matterHumidityValue(humidityClient) : representative?.humidity_percent,
    contact_state_value: contactClient?.contact_state_value ?? representative?.contact_state_value,
    contact_open: contactClient?.contact_open ?? representative?.contact_open,
    occupancy_state_value: motionClient?.occupancy_state_value ?? representative?.occupancy_state_value,
    motion_active: motionClient?.motion_active ?? representative?.motion_active,
    last_motion_at: motionClient?.last_motion_at ?? representative?.last_motion_at,
    matter_onoff: switchClient?.matter_onoff ?? representative?.matter_onoff,
    matter_switch_position: buttonClient?.matter_switch_position ?? representative?.matter_switch_position,
    matter_switch_positions: buttonClient?.matter_switch_positions ?? representative?.matter_switch_positions,
    matter_switch_multipress_max: buttonClient?.matter_switch_multipress_max ?? representative?.matter_switch_multipress_max,
    matter_button_event: buttonClient?.matter_button_event ?? representative?.matter_button_event,
    matter_button_event_at: buttonClient?.matter_button_event_at ?? representative?.matter_button_event_at,
    matter_button_position: buttonClient?.matter_button_position ?? representative?.matter_button_position,
    matter_button_press_count: buttonClient?.matter_button_press_count ?? representative?.matter_button_press_count,
    battery: null,
    battery_low: batteryClient?.battery_low ?? representative?.battery_low,
    battery_state: batteryClient?.battery_state ?? representative?.battery_state,
    matter_battery_percent_remaining_raw: null,
    matter_battery_percent: null,
    matter_battery_charge_level: batteryClient?.matter_battery_charge_level ?? representative?.matter_battery_charge_level,
    matter_battery_charge_state: batteryClient?.matter_battery_charge_state ?? representative?.matter_battery_charge_state,
    matter_battery_replacement_needed: batteryClient?.matter_battery_replacement_needed ?? representative?.matter_battery_replacement_needed,
    matter_battery_low: batteryClient?.matter_battery_low ?? representative?.matter_battery_low,
    matter_reachable: anyUnreachable ? false : (anyReachable ? true : representative?.matter_reachable),
    last_update: sortedClients.find(c => c?.last_update)?.last_update || representative?.last_update || first?.last_update
  };
}

function matterGroupClientsBySerial(clients) {
  return matterPhysicalClientGroups(clients)
    .map(matterGroupedClientFromSerial)
    .filter(Boolean);
}

window.dashboardGroupMatterClients = function (clients) {
  const list = [...(clients || [])];
  const matterClients = list.filter(c => window.dashboardClientIsMatter?.(c));
  const groupedMatter = new Map(
    matterPhysicalClientGroups(matterClients).flatMap(group => (
      group.map(c => [c, group])
    ))
  );
  const emittedGroups = new Set();
  const groupedClients = [];

  list.forEach(c => {
    const group = groupedMatter.get(c);

    if (!group) {
      groupedClients.push(c);
      return;
    }

    if (emittedGroups.has(group)) return;

    emittedGroups.add(group);
    groupedClients.push(matterGroupedClientFromSerial(group));
  });

  return groupedClients.filter(Boolean);
};

window.dashboardMatterUnassignedClients = function (clients) {
  const matterClients = (clients || [])
    .filter(c => window.dashboardClientIsMatter?.(c) && matterIsUnassigned(c));

  return matterGroupClientsBySerial(matterClients)
    .sort((a, b) => (
      matterKind(a).localeCompare(matterKind(b)) ||
      String(a?.matter_node_label || a?.clientName || a?.deviceID || "").localeCompare(String(b?.matter_node_label || b?.clientName || b?.deviceID || "")) ||
      String(a?.matter_endpoint || "").localeCompare(String(b?.matter_endpoint || ""))
    ));
};

function matterFoundClientIsAndroidProvisionClient(c) {
  if (!c || c.provisioned || window.dashboardClientIsMatter?.(c)) return false;

  return String(c.detectedRole || "").trim().toUpperCase() !== "TAPO";
}

function matterFoundClientHasRole(c, role) {
  if (typeof window.hasClientRole === "function") return window.hasClientRole(c, role);

  const wanted = String(role || "").trim().toUpperCase();
  const roles = Array.isArray(c?.clientRole)
    ? c.clientRole
    : String(c?.clientRole || "").split(",");

  return roles.some(item => String(item || "").trim().toUpperCase() === wanted);
}

function matterFoundClientIsTapoDevice(c) {
  if (
    !c ||
    c.provisioned ||
    window.dashboardClientIsMatter?.(c) ||
    !matterIsUnassigned(c)
  ) {
    return false;
  }

  const source = String(c?.source || "").trim().toLowerCase();
  const role = String(c?.detectedRole || c?.clientRole || "").trim().toUpperCase();
  const id = String(c?.deviceID || "").trim().toLowerCase();

  if (source === "tapo_child" || c?.tapo_is_hub_child === true) {
    return false;
  }

  return (
    source === "tapo" ||
    role === "TAPO" ||
    matterFoundClientHasRole(c, "TAPO") ||
    id.startsWith("tapo:")
  );
}

function matterFoundTapoKindLabel(c) {
  const kind = String(c?.tapo_kind || "Device").trim().toLowerCase();
  const labels = {
    bulb: "Bulb",
    lightstrip: "Lightstrip",
    plug: "Plug",
    outlet_extender: "Extender",
    hub: "Hub",
    camera: "Camera",
    vacuum: "Vac",
  };

  return labels[kind] || (kind ? kind.replace(/_/g, " ").replace(/\b\w/g, ch => ch.toUpperCase()) : "Device");
}

function matterFoundTapoDefaultName(c) {
  if (typeof window.dashboardDeviceTypeName === "function") {
    return window.dashboardDeviceTypeName(c);
  }

  const model = String(c?.tapo_model || c?.model || "").trim();
  const label = matterFoundTapoKindLabel(c);

  return model ? `Tapo ${model} ${label}` : `Tapo ${label}`;
}

function matterFoundTapoNameIsGenerated(c, value) {
  const text = String(value || "").trim();
  if (!text) return true;

  const id = String(c?.deviceID || "").trim();
  if (id && text === id) return true;
  if (text.startsWith("tapo-child:") || text.startsWith("tapo:")) return true;

  const model = String(c?.tapo_model || c?.model || "").trim();
  const label = matterFoundTapoKindLabel(c);
  const generated = [
    matterFoundTapoDefaultName(c),
    model ? `Tapo ${model}` : "",
    `Tapo ${label}`,
    model ? `Tapo ${model} Outlet` : "",
  ].filter(Boolean);

  return generated.includes(text);
}

function matterFoundTapoTitle(c) {
  const name = String(c?.clientName || "").trim();
  if (!matterFoundTapoNameIsGenerated(c, name)) return name;

  return matterFoundTapoDefaultName(c);
}

function matterFoundTapoSubtitle(c) {
  return matterConnectedHubSubtitle(c, matterFoundTapoKindLabel(c));
}

function matterFoundTapoIcon(c) {
  return window.dashboardDeviceIconName(c);
}

function matterFoundTapoStatusClass(c) {
  if (c?.stale || c?.tapo_control_ready === false) return "stale";
  if (matterBool(c?.tapo_is_on) === true) return "mint-blue-flash";

  return "green";
}

function matterFoundTapoCard(c) {
  const id = matterEscAttr(c?.deviceID || "");
  const title = matterEsc(matterFoundTapoTitle(c) || "Tapo Device");
  const subtitle = matterEsc(matterFoundTapoSubtitle(c));
  const icon = matterEsc(matterFoundTapoIcon(c));
  const statusClass = matterEscAttr(matterFoundTapoStatusClass(c));
  const batteryHtml = c?.battery === undefined || c?.battery === null || c?.battery === ""
    ? ""
    : (typeof window.renderBattery === "function" ? window.renderBattery(c.battery) : "");

  return `
    <div class="card matter-card matter-new-client-card ${c?.stale ? "stale-client" : ""}" data-device-id="${id}" data-node-card="control">
      <div class="card-head matter-card-head">
        <div class="status-area">
          ${window.dashboardIconHtml(icon, `status-matter ${statusClass}`)}
          <div class="card-title-group">
            <div class="card-title">${title}</div>
            <div class="card-type-label">${subtitle}</div>
          </div>
        </div>

        <div class="card-actions matter-card-actions">
          ${batteryHtml}

          <button
            class="icon-menu"
            type="button"
            data-dashboard-action="open-client-menu"
            data-device-id="${id}"
            data-menu-kind="client"
          >
            ${window.dashboardIconHtml("more_vert")}
          </button>
        </div>
      </div>
    </div>
  `;
}

function matterFoundAndroidClientTitle(c) {
  if (typeof window.dashboardDeviceTypeName === "function") {
    return window.dashboardDeviceTypeName(c);
  }

  return "Android Client";
}

function matterFoundAndroidClientSubtitle(c) {
  const manufacturer = String(
    c?.android_manufacturer ||
    c?.device_manufacturer ||
    c?.manufacturer ||
    c?.build_manufacturer ||
    c?.android_brand ||
    c?.brand ||
    ""
  ).trim();

  return manufacturer ? `Android - ${manufacturer}` : "Android";
}

function matterFoundAndroidClientCard(c) {
  const id = matterEscAttr(c?.deviceID || "");
  const title = matterEsc(matterFoundAndroidClientTitle(c));
  const subtitle = matterEsc(matterFoundAndroidClientSubtitle(c));
  const icon = matterEsc(window.dashboardDeviceIconName(c));
  const statusClass = c?.stale ? "stale" : "mint-blue-flash";
  const batteryHtml = c?.battery === undefined || c?.battery === null || c?.battery === ""
    ? ""
    : (typeof window.renderBattery === "function" ? window.renderBattery(c.battery) : "");

  return `
    <div class="card matter-card matter-new-client-card ${c?.stale ? "stale-client" : ""}" data-device-id="${id}" data-node-card="control">
      <div class="card-head matter-card-head">
        <div class="status-area">
          ${window.dashboardIconHtml(icon, `status-matter matter-new-client-icon ${statusClass}`)}
          <div class="card-title-group">
            <div class="card-title">${title}</div>
            <div class="card-type-label">${subtitle}</div>
          </div>
        </div>

        <div class="card-actions matter-card-actions">
          ${batteryHtml}

          <button
            class="icon-menu"
            type="button"
            data-dashboard-action="open-client-menu"
            data-device-id="${id}"
            data-menu-kind="client"
          >
            ${window.dashboardIconHtml("more_vert")}
          </button>
        </div>
      </div>
    </div>
  `;
}

window.dashboardHomeFoundClients = function (clients) {
  const matterClients = window.dashboardMatterUnassignedClients?.(clients) || [];
  const matterIDs = new Set(
    matterClients
      .flatMap(c => Array.isArray(c?.matter_device_ids) ? c.matter_device_ids : [c?.deviceID])
      .map(id => String(id || "").trim())
      .filter(Boolean)
  );
  const tapoClients = (clients || [])
    .filter(matterFoundClientIsTapoDevice)
    .filter(c => !matterIDs.has(String(c?.deviceID || "").trim()))
    .sort((a, b) => (
      matterFoundTapoTitle(a).localeCompare(matterFoundTapoTitle(b), undefined, { sensitivity: "base" }) ||
      String(a?.deviceID || "").localeCompare(String(b?.deviceID || ""))
    ));
  const foundIDs = new Set([
    ...matterIDs,
    ...tapoClients.map(c => String(c?.deviceID || "").trim()).filter(Boolean)
  ]);
  const androidProvisionClients = (clients || [])
    .filter(matterFoundClientIsAndroidProvisionClient)
    .filter(c => !foundIDs.has(String(c?.deviceID || "").trim()))
    .sort((a, b) => (
      matterFoundAndroidClientTitle(a).localeCompare(matterFoundAndroidClientTitle(b), undefined, { sensitivity: "base" }) ||
      String(a?.deviceID || "").localeCompare(String(b?.deviceID || ""))
    ));

  return [
    ...matterClients.map(c => ({ ...c, __homeFoundKind: "matter" })),
    ...tapoClients.map(c => ({ ...c, __homeFoundKind: "tapo" })),
    ...androidProvisionClients.map(c => ({ ...c, __homeFoundKind: "client" }))
  ];
};

window.renderHomeFoundClientCard = function (c) {
  if (c?.__homeFoundKind === "client" || matterFoundClientIsAndroidProvisionClient(c)) {
    return matterFoundAndroidClientCard(c);
  }

  if (c?.__homeFoundKind === "tapo" || matterFoundClientIsTapoDevice(c)) {
    return matterFoundTapoCard(c);
  }

  return window.renderMatterClientCard?.(c) || "";
};

window.renderMatterFoundHomeSection = function (clients) {
  const foundClients = window.dashboardHomeFoundClients?.(clients) || [];

  if (!foundClients.length || typeof window.renderHomeFoundClientCard !== "function") {
    return "";
  }

  return `
    <section class="dashboard-home-card dashboard-home-matter-found-section" data-home-client-section="matter">
      <div class="dashboard-home-section-head">
        ${window.dashboardIconHtml("koti-fa-triangle-exclamation", "dashboard-home-section-icon dashboard-home-matter-found-icon")}
        <h2 class="dashboard-home-section-title">New Device Found</h2>
      </div>

      <div class="dashboard-home-matter-device-list">
        ${foundClients.map(c => window.renderHomeFoundClientCard(c)).join("")}
      </div>
    </section>
  `;
};

window.syncMatterFoundHomeSection = function (root, clients) {
  const slot = root?.matches?.("[data-home-matter-found-slot]")
    ? root
    : root?.querySelector?.("[data-home-matter-found-slot]");

  if (!slot) return;

  const foundClients = window.dashboardHomeFoundClients?.(clients) || [];

  if (!foundClients.length) {
    slot.hidden = true;
    slot.innerHTML = "";
    return;
  }

  slot.hidden = false;
  slot.innerHTML = window.renderMatterFoundHomeSection?.(clients) || "";

  const section = slot.querySelector('[data-home-client-section="matter"]');

  if (!section) return;

  foundClients.forEach(c => {
    const deviceID = String(c?.deviceID || "");
    const card = deviceID
      ? [...section.querySelectorAll("[data-device-id]")].find(el => String(el.dataset.deviceId || "") === deviceID)
      : null;

    if (card) {
      window.syncClientDebugArea?.(card, c);
    }
  });
};

function matterMenuRows(c) {
  const rows = [
    ["Label", matterDebugText(c?.matter_node_label)],
    ["Serial", matterDebugText(c?.matter_serial_number)]
  ];
  const kinds = matterKinds(c);

  if (kinds.includes("temperature")) rows.push(["Temperature", matterTemperatureText(c?.temperature_c)]);
  if (kinds.includes("humidity")) rows.push(["Humidity", c?.humidity_percent == null ? "—" : matterPercent(c.humidity_percent)]);
  if (matterKind(c) === "contact") rows.push(["Contact", matterStatusText(c)]);
  if (matterKind(c) === "motion") rows.push(["Motion", matterStatusText(c)]);
  if (matterKind(c) === "switch" || matterKind(c) === "onoff") rows.push(["Switch", matterStatusText(c)]);
  if (matterKind(c) === "button") rows.push(["Button", matterButtonEventText(c)]);

  return rows;
}

function renderMatterMenuRows(c) {
  return matterMenuRows(c)
    .map(([label, value]) => `
      <div class="client-menu-row">
        <span class="client-menu-label">${matterEsc(label)}</span>
        <span class="client-menu-value">${matterEsc(value)}</span>
      </div>
    `)
    .join("");
}

function matterSetClientMenuEditMode() {
  const modal = document.getElementById("clientMenuModal");
  const editToggle = document.getElementById("clientMenuEditToggle");

  if (!modal || !editToggle) return;

  delete modal.dataset.editMode;

  editToggle.hidden = false;
  editToggle.classList.remove("active");
  editToggle.title = "Edit device details";
  editToggle.setAttribute("aria-label", editToggle.title);
  editToggle.removeAttribute("aria-expanded");
}

window.showMatterClientMenu = function (deviceID) {
  window.closeAllMenus?.();

  const modal = document.getElementById("clientMenuModal");
  if (!modal) return;

  modal.dataset.deviceId = deviceID;
  modal.dataset.menuKind = "matter";
  modal.hidden = false;
  document.body.classList.add("modal-open");

  window.renderMatterClientMenu?.(deviceID);
};

window.renderMatterClientMenu = function (deviceID) {
  const modal = document.getElementById("clientMenuModal");
  const title = document.getElementById("clientMenuTitle");
  const subtitle = document.getElementById("clientMenuSubtitle");
  const body = document.getElementById("clientMenuBody");

  if (!modal || !body) return;

  const currentClients = window.appState?.currentClients || [];
  const sourceClient = currentClients.find(item => item?.deviceID === deviceID) || null;
  const matterClients = currentClients.filter(item => window.dashboardClientIsMatter?.(item) === true);
  const relatedClients = sourceClient
    ? (matterPhysicalClientGroups(matterClients).find(group => group.includes(sourceClient)) || [sourceClient])
    : [];
  const client = matterGroupedClientFromSerial(relatedClients);

  if (!client) {
    window.hideClientMenuModal?.();
    return;
  }

  const automationKinds = new Set(matterKinds(client));
  const automationTriggerGroups = [];

  if (
    automationKinds.has("contact") ||
    matterKind(client) === "contact" ||
    client.contact_open != null ||
    client.contact_state_value != null
  ) {
    automationTriggerGroups.push("door");
  }

  if (
    automationKinds.has("motion") ||
    matterKind(client) === "motion" ||
    client.motion_active != null ||
    client.occupancy_state_value != null
  ) {
    automationTriggerGroups.push("motion");
  }

  if (
    [...automationKinds].some(kind => ["temperature", "humidity", "environment"].includes(kind)) ||
    client.temperature_c != null ||
    client.humidity_percent != null
  ) {
    automationTriggerGroups.push("environment");
  }

  modal.dataset.deviceId = deviceID;
  modal.dataset.menuKind = "matter";

  if (title) title.textContent = client.clientName || client.matter_node_label || "Matter Sensor";
  if (subtitle) subtitle.textContent = matterSubtitle(client);

  body.innerHTML = `
    <div class="modal-section">
      <div class="modal-section-title">Matter Sensor</div>
      ${renderMatterMenuRows(client)}
    </div>

    ${automationTriggerGroups.length ? `
      <div class="modal-section">
        <div class="modal-section-title">Automations</div>
        <div class="client-menu-actions">
          ${automationTriggerGroups.map(triggerGroup => {
            const triggerLabel = {
              door: "Door",
              motion: "Motion",
              environment: "Environmental"
            }[triggerGroup];
            const buttonLabel = automationTriggerGroups.length > 1
              ? `Add ${triggerLabel} Automation`
              : "Add Automation";

            return `
              <button
                class="client-menu-btn"
                type="button"
                data-dashboard-action="show-automation-settings"
                data-device-id="${matterEscAttr(deviceID)}"
                data-trigger-group="${matterEscAttr(triggerGroup)}">
                ${window.dashboardIconHtml("add")}
                <span>${matterEsc(buttonLabel)}</span>
              </button>
            `;
          }).join("")}
        </div>
      </div>
    ` : ""}

  `;

  matterSetClientMenuEditMode();
};
