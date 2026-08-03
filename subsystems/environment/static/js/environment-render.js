"use strict";

(function () {
  const S = window.appState || (window.appState = {});

  function envEsc(value) {
    return typeof window.esc === "function" ? window.esc(value) : String(value ?? "");
  }

  function envEscAttr(value) {
    return typeof window.escAttr === "function"
      ? window.escAttr(value)
      : envEsc(value).replace(/"/g, "&quot;");
  }

  function envNumber(value) {
    if (value === undefined || value === null || value === "") return null;

    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function envTempTextF(value) {
    const number = envNumber(value);
    return number === null ? "—" : `${Math.round(number)}°F`;
  }

  function envPercentText(value) {
    const number = envNumber(value);
    return number === null ? "—" : `${Math.round(number)}%`;
  }

  function envSnapshot() {
    return S.environmentState && typeof S.environmentState === "object" ? S.environmentState : {};
  }

  function envSetSnapshot(snapshot) {
    S.environmentState = snapshot && typeof snapshot === "object" ? snapshot : {};
    return S.environmentState;
  }

  window.dashboardSetEnvironmentState = envSetSnapshot;

  function envDashboardFetch() {
    return typeof window.dashboardFetch === "function" ? window.dashboardFetch : fetch;
  }

  async function envReadJsonResponse(res, fallbackMessage) {
    const text = await res.text();
    let data = {};

    if (text) {
      try {
        data = JSON.parse(text);
      } catch (_) {
        throw new Error(`${fallbackMessage}: ${res.status} ${text.slice(0, 180)}`);
      }
    }

    if (!res.ok || data.ok === false) {
      throw new Error(data.error || `${fallbackMessage}: ${res.status}`);
    }

    return data;
  }

  window.getDashboardEnvironmentStatus = async function (refresh = false) {
    const fetcher = envDashboardFetch();
    const res = await fetcher(`/api/environment/status${refresh ? "?refresh=1" : ""}`, {
      cache: "no-store",
      credentials: "same-origin"
    });
    const data = await envReadJsonResponse(res, "Environment status failed");

    return envSetSnapshot(data);
  };

  window.saveDashboardEnvironmentSettings = async function (settings = {}) {
    const fetcher = envDashboardFetch();
    const res = await fetcher("/api/environment/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(settings)
    });
    const data = await envReadJsonResponse(res, "Environment settings save failed");

    return envSetSnapshot(data);
  };

  window.refreshDashboardEnvironmentStatus = function () {
    return window.getDashboardEnvironmentStatus(true);
  };

  function envIconName(icon, id) {
    const cleanIcon = String(icon || "").trim().toLowerCase();
    const cleanID = String(id || "").trim().toLowerCase();

    if (["thermometer", "device_thermostat"].includes(cleanIcon) || cleanID === "indoor_temp") return "device_thermostat";
    if (["droplet", "water_drop"].includes(cleanIcon) || cleanID === "humidity") return "water_drop";
    if (["leaf", "eco"].includes(cleanIcon) || cleanID === "air_quality") return "eco";
    if (["sun", "wb_sunny"].includes(cleanIcon)) return "wb_sunny";
    if (cleanID === "outdoor") return cleanIcon || "wb_sunny";

    return cleanIcon || "sensors";
  }

  function environmentWeatherIconName(snapshot = envSnapshot()) {
    const condition = String(snapshot.outdoor?.condition || "").toLowerCase();
    const iconUrl = String(snapshot.outdoor?.icon || "").toLowerCase();
    const iconCondition = iconUrl.split("?")[0].split("/").pop() || "";
    const weatherText = `${condition} ${iconCondition.replace(/_/g, " ")}`;
    const isNight = iconUrl.includes("/night/") || iconUrl.includes("night");

    if (weatherText.includes("thunder") || weatherText.includes("t-storm")) return "thunderstorm";
    if (weatherText.includes("snow") || weatherText.includes("sleet") || weatherText.includes("ice")) return "weather_snowy";
    if (weatherText.includes("heavy rain") || weatherText.includes("rain showers") || weatherText.includes("rain_showers")) return "rainy_heavy";
    if (weatherText.includes("rain") || weatherText.includes("shower") || weatherText.includes("drizzle")) return "rainy";
    if (weatherText.includes("fog") || weatherText.includes("haze") || weatherText.includes("smoke") || weatherText.includes("mist")) return "foggy";
    if (weatherText.includes("wind")) return "air";
    if (weatherText.includes("partly") || weatherText.includes("few clouds") || weatherText.includes("mostly clear")) return isNight ? "partly_cloudy_night" : "partly_cloudy_day";
    if (weatherText.includes("cloud") || weatherText.includes("overcast")) return "cloud";
    if (weatherText.includes("clear") || weatherText.includes("sun") || weatherText.includes("fair")) return isNight ? "dark_mode" : "wb_sunny";

    return isNight ? "dark_mode" : "wb_sunny";
  }

  function environmentOutdoorReady(snapshot = envSnapshot()) {
    const outdoor = snapshot.outdoor;

    if (!outdoor || typeof outdoor !== "object") return false;

    return !!String(outdoor.condition || outdoor.icon || outdoor.temperature_text || outdoor.updated_at || "").trim();
  }

  function environmentAirQualityReady(snapshot = envSnapshot()) {
    const airQuality = snapshot.air_quality;

    if (!airQuality || typeof airQuality !== "object") return false;

    return Object.keys(airQuality).length > 0;
  }

  function environmentAqiValue(snapshot = envSnapshot()) {
    const aqi = envNumber(snapshot.air_quality?.aqi);
    return `AQI ${aqi === null ? "—" : Math.round(aqi)}`;
  }

  function environmentAqiLabel(snapshot = envSnapshot()) {
    const aqi = envNumber(snapshot.air_quality?.aqi);
    const category = String(snapshot.air_quality?.label || "Unavailable").trim() || "Unavailable";

    if (aqi === null) {
      const source = String(snapshot.air_quality?.source || "").trim();
      return source && source !== "Not configured" ? "Unavailable" : "Not Configured";
    }

    return category;
  }

  function environmentMetricIconHtml({
    id = "environment",
    icon = "sensors",
    iconReady = true,
    iconPlaceholder = "cloud_queue"
  } = {}) {
    const iconName = envIconName(icon, id);

    if (id === "outdoor") {
      return environmentValueSlotHtml({
        key: "home-environment:outdoor:icon",
        value: iconName,
        placeholder: iconPlaceholder,
        slotClass: "dashboard-home-environment-icon-slot dashboard-home-environment-outdoor-icon-slot",
        placeholderClass: "dashboard-home-environment-icon",
        contentClass: "dashboard-home-environment-icon",
        placeholderHtml: window.dashboardIconHtml(iconPlaceholder),
        contentHtml: window.dashboardIconHtml(iconName),
        ready: iconReady
      });
    }

    return `${window.dashboardIconHtml(iconName, "dashboard-home-environment-icon")}`;
  }

  function environmentValueSlotHtml(options = {}) {
    if (typeof window.dashboardValueSlotHtml === "function") {
      return window.dashboardValueSlotHtml(options);
    }

    if (options.contentHtml !== null && options.contentHtml !== undefined) {
      return String(options.contentHtml);
    }

    return `<span class="${envEscAttr(options.contentClass || "")}">${envEsc(options.value || options.placeholder || "—")}</span>`;
  }

  function environmentMetricHtml(metric = {}) {
    const id = String(metric.id || "environment").trim().toLowerCase().replace(/[^a-z0-9_-]/g, "-") || "environment";
    const icon = envIconName(metric.icon, id);
    const iconClass = String(icon || "sensors").trim().toLowerCase().replace(/[^a-z0-9_-]/g, "-") || "sensors";
    const valueText = String(metric.value ?? "—").trim() || "—";
    const labelText = String(metric.label ?? "").trim();
    const valuePlaceholder = String(metric.valuePlaceholder || (id === "air_quality" ? "AQI —" : "—"));
    const labelPlaceholder = String(metric.labelPlaceholder || "Loading");
    const valueReady = metric.valueReady ?? window.dashboardValueIsReady?.(valueText, valuePlaceholder) ?? valueText !== valuePlaceholder;
    const labelReady = metric.labelReady ?? window.dashboardValueIsReady?.(labelText, labelPlaceholder) ?? !!labelText;
    const labelFades = metric.labelFades === true;
    const labelHtml = labelFades
      ? environmentValueSlotHtml({
          key: `home-environment:${id}:label`,
          value: labelText || labelPlaceholder,
          placeholder: labelPlaceholder,
          slotClass: `dashboard-home-environment-label-slot dashboard-home-environment-${id}-label-slot`,
          contentClass: "dashboard-home-environment-label",
          ready: labelReady
        })
      : `<span class="dashboard-home-environment-label">${envEsc(labelText)}</span>`;

    return `
      <article class="dashboard-home-environment-metric dashboard-home-environment-metric-${envEscAttr(id)} dashboard-home-environment-icon-${envEscAttr(iconClass)}" data-environment-metric="${envEscAttr(id)}">
        <span class="dashboard-home-environment-icon-wrap">
          ${environmentMetricIconHtml({
            id,
            icon,
            iconReady: metric.iconReady ?? true,
            iconPlaceholder: metric.iconPlaceholder || "cloud_queue"
          })}
        </span>
        ${environmentValueSlotHtml({
          key: `home-environment:${id}:value`,
          value: valueText,
          placeholder: valuePlaceholder,
          slotClass: `dashboard-home-environment-value-slot dashboard-home-environment-${id}-value-slot`,
          contentClass: "dashboard-home-environment-value",
          ready: valueReady
        })}
        ${labelHtml}
      </article>
    `;
  }

  function environmentOverviewHtml(snapshot = envSnapshot(), extraClass = "", showLastUpdate = false) {
    const classes = ["dashboard-home-environment-grid", extraClass].filter(Boolean).join(" ");
    const aqiColor = String(snapshot.air_quality?.color || "").trim();
    const aqiStyle = aqiColor ? ` style="--environment-aqi-color: ${envEscAttr(aqiColor)}"` : "";
    const airQualityReady = environmentAirQualityReady(snapshot);
    const outdoorReady = environmentOutdoorReady(snapshot);

    return `
      <div class="${envEscAttr(classes)}"${aqiStyle}>
        <section class="dashboard-home-environment-group dashboard-home-environment-group-indoor">
          <div class="dashboard-home-environment-group-metrics">
            ${environmentMetricHtml({
              id: "indoor_temp",
              icon: "device_thermostat",
              value: snapshot.indoor?.temperature_text || "—",
              label: "Indoor"
            })}
            ${environmentMetricHtml({
              id: "humidity",
              icon: "water_drop",
              value: snapshot.indoor?.humidity_text || "—",
              label: "Humidity"
            })}
          </div>
        </section>

        <section class="dashboard-home-environment-group dashboard-home-environment-group-outdoor">
          <div class="dashboard-home-environment-group-metrics">
            ${environmentMetricHtml({
              id: "air_quality",
              icon: "eco",
              value: environmentAqiValue(snapshot),
              label: environmentAqiLabel(snapshot),
              valueReady: airQualityReady,
              labelReady: airQualityReady,
              labelFades: true
            })}
            ${environmentMetricHtml({
              id: "outdoor",
              icon: environmentWeatherIconName(snapshot),
              value: snapshot.outdoor?.temperature_text || "—",
              label: "Outdoor",
              iconReady: outdoorReady,
              iconPlaceholder: "cloud_queue"
            })}
          </div>
        </section>

        ${showLastUpdate ? `
          <div class="modal-subtitle environment-updated-text">
            Updated ${envEsc(environmentUpdatedText(snapshot))} ago
          </div>
        ` : ""}
      </div>
    `;
  }

  window.renderDashboardHomeEnvironmentSection = function () {
    const snapshot = envSnapshot();

    return `
      <button class="dashboard-home-card dashboard-home-environment-section" type="button" data-dashboard-action="show-environment-modal" aria-label="Open environment and conditions">
        <div class="dashboard-home-section-head">
          <h2 class="dashboard-home-section-title">Environment</h2>
        </div>

        ${environmentOverviewHtml(snapshot)}
      </button>
    `;
  };

  function ensureMatterEnvironmentModalShell() {
    if (!document.getElementById("matterEnvironmentModal")) {
      document.body.insertAdjacentHTML("beforeend", `
        <div id="matterEnvironmentModal" class="modal" hidden>
          <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="matterEnvironmentModalTitle">
            <div class="modal-head">
              <div class="modal-title-wrap">
                <div id="matterEnvironmentModalTitle" class="modal-title">Environment</div>
              </div>

              <div class="modal-head-actions">
                <button
                  class="modal-close"
                  type="button"
                  data-dashboard-action="show-environment-settings"
                  aria-label="Environment settings"
                  title="Environment settings"
                >
                  ${window.dashboardIconHtml("edit")}
                </button>

                <button
                  class="modal-close"
                  type="button"
                  data-dashboard-action="hide-environment-modal"
                  aria-label="Close environment"
                >
                  ${window.dashboardIconHtml("close")}
                </button>
              </div>
            </div>

            <div id="matterEnvironmentModalBody" class="modal-body"></div>
          </div>
        </div>
      `);
    }

    if (!document.getElementById("matterEnvironmentSettingsModal")) {
      document.body.insertAdjacentHTML("beforeend", `
        <div id="matterEnvironmentSettingsModal" class="modal" hidden>
          <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="matterEnvironmentSettingsModalTitle">
            <div class="modal-head">
              <div class="modal-title-wrap">
                <div id="matterEnvironmentSettingsModalTitle" class="modal-title">Environment Settings</div>
              </div>

              <button
                class="modal-close"
                type="button"
                data-dashboard-action="hide-environment-settings"
                aria-label="Close environment settings"
              >
                ${window.dashboardIconHtml("close")}
              </button>
            </div>

            <div id="matterEnvironmentSettingsModalBody" class="modal-body"></div>
          </div>
        </div>
      `);
    }

    return document.getElementById("matterEnvironmentModal");
  }

  function matterTemperatureUnitValue() {
    if (
      window.dashboardMatterEnvironmentSettingsReady === true &&
      typeof window.matterEnvironmentTemperatureUnit === "function"
    ) {
      return window.matterEnvironmentTemperatureUnit();
    }

    return null;
  }

  function environmentDeviceTemperatureText(device) {
    const tempF = envNumber(device?.temperature_f);
    const unit = matterTemperatureUnitValue();

    if (tempF === null || !unit) return "—";

    if (unit === "f") {
      return envTempTextF(tempF);
    }

    const tempC = (tempF - 32) * 5 / 9;
    return `${tempC.toFixed(1).replace(/\.0$/, "")}°C`;
  }

  function environmentIndoorDevices(snapshot = envSnapshot()) {
    const matterClients = (S.currentClients || [])
      .filter(client => window.dashboardClientIsMatterEnvironment?.(client));

    if (!matterClients.length) {
      return Array.isArray(snapshot.indoor?.devices) ? snapshot.indoor.devices : [];
    }

    const groups = new Map();

    matterClients.forEach(client => {
      const serial = String(client.matter_serial_number || "").trim();
      const deviceID = String(client.deviceID || "").trim();
      const key = serial ? `serial:${serial}` : `device:${deviceID}`;
      const temperatureC = envNumber(client.temperature_c);
      const temperatureF = temperatureC === null ? null : (temperatureC * 9 / 5) + 32;
      const humidity = envNumber(client.humidity_percent);

      if (!groups.has(key)) {
        groups.set(key, {
          deviceID,
          deviceIDs: [],
          serial,
          name: client.matter_node_label || client.matter_product_name || client.clientName || client.model || "Matter sensor",
          zone_name: client.zone_name || client.zoneName || "Unassigned",
          temperature_f: null,
          humidity_percent: null,
          updated_at: 0
        });
      }

      const group = groups.get(key);

      if (deviceID && !group.deviceIDs.includes(deviceID)) {
        group.deviceIDs.push(deviceID);
      }

      if (temperatureF !== null) group.temperature_f = temperatureF;
      if (humidity !== null) group.humidity_percent = humidity;

      group.updated_at = Math.max(
        Number(group.updated_at || 0),
        Number(client.matter_last_sync_at || client.last_seen || 0)
      );
    });

    return [...groups.values()].sort((a, b) => (
      String(a.zone_name).localeCompare(String(b.zone_name)) ||
      String(a.name).localeCompare(String(b.name)) ||
      String(a.serial).localeCompare(String(b.serial))
    ));
  }

  function environmentIndoorDeviceHtml(device = {}, showName = false) {
    return `
      <div class="matter-environment-device">
        ${showName ? `
          <div class="modal-section-title matter-environment-device-title">${envEsc(device.name || "Matter sensor")}</div>
        ` : ""}

        <div class="matter-environment-readout-grid">
          <div class="matter-environment-readout">
            <span class="matter-environment-readout-label">Temperature</span>
            <span class="matter-environment-readout-value">${envEsc(environmentDeviceTemperatureText(device))}</span>
          </div>
          <div class="matter-environment-readout">
            <span class="matter-environment-readout-label">Humidity</span>
            <span class="matter-environment-readout-value">${envEsc(envPercentText(device.humidity_percent))}</span>
          </div>
        </div>
      </div>
    `;
  }

  function environmentIndoorZonesHtml(devices = []) {
    const zones = new Map();

    devices.forEach(device => {
      const zoneName = String(device.zone_name || "Unassigned").trim() || "Unassigned";

      if (!zones.has(zoneName)) zones.set(zoneName, []);
      zones.get(zoneName).push(device);
    });

    return [...zones.entries()].map(([zoneName, zoneDevices]) => `
      <section class="modal-section matter-environment-zone">
        <div class="modal-section-title">${envEsc(zoneName)}</div>
        ${zoneDevices
          .map(device => environmentIndoorDeviceHtml(device, zoneDevices.length > 1))
          .join("")}
      </section>
    `).join("");
  }

  function environmentStationNameHtml(value) {
    const parts = String(value || "")
      .split(/\s*,\s*/)
      .map(part => part.trim())
      .filter(Boolean);

    if (!parts.length) return "—";

    return parts
      .map(part => `<span class="environment-station-name-line">${envEsc(part)}</span>`)
      .join("");
  }

  function environmentLocationDetailsHtml(snapshot = envSnapshot()) {
    const station = snapshot.outdoor?.station || {};
    const location = snapshot.outdoor?.location || {};
    const locationName = [location.city, location.state].filter(Boolean).join(", ") || "—";
    const stationName = station.name || station.id || "—";
    const stationDistance = envNumber(station.distance_miles);

    return `
      <div class="settings-server-card">
        <div class="settings-server-info environment-location-info">
          <div class="settings-server-info-row"><span>Resolved</span><span class="settings-server-info-value">${envEsc(locationName)}</span></div>
          <div class="settings-server-info-row environment-station-row">
            <span>Station</span>
            <span class="settings-server-info-value environment-station-name">
              ${environmentStationNameHtml(stationName)}
            </span>
          </div>
          <div class="settings-server-info-row"><span>Distance</span><span class="settings-server-info-value">${stationDistance === null ? "—" : `${envEsc(stationDistance)} mi`}</span></div>
        </div>
      </div>
    `;
  }

  function environmentSettingsHtml(snapshot = envSnapshot()) {
    const settings = snapshot.settings || {};
    const zipCode = String(settings.zip_code || settings.zipCode || "").replace(/\D/g, "").slice(0, 5);
    const unit = matterTemperatureUnitValue();

    return `
      <section id="matterEnvironmentSettingsSection" class="modal-section environment-settings-section">
        <div class="modal-section-title">Temperature Units</div>

        <div class="client-menu-actions environment-temperature-actions">
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

        <div class="modal-section-title environment-location-title">Location</div>

        <div class="environment-settings-fields">
          <label class="client-menu-inline-field environment-inline-field">
            <span class="client-menu-label">ZIP Code</span>
            <input
              id="matterEnvironmentZipInput"
              class="settings-input"
              type="text"
              inputmode="numeric"
              autocomplete="postal-code"
              maxlength="5"
              value="${envEscAttr(zipCode)}"
            >
          </label>
        </div>

        ${environmentLocationDetailsHtml(snapshot)}

        <div class="client-menu-actions environment-settings-actions">
          <button
            class="client-menu-btn primary"
            type="button"
            data-dashboard-action="save-environment-settings"
          >
            Save
          </button>
        </div>

        <div id="matterEnvironmentStatusText" class="modal-subtitle environment-status-text"></div>
      </section>
    `;
  }

  function environmentUpdatedText(snapshot = envSnapshot()) {
    const updatedAt = Number(snapshot.outdoor?.updated_at || 0);

    if (!updatedAt) return "Unavailable";

    const ageSeconds = Math.max(
      0,
      Math.floor((Date.now() / 1000) - updatedAt)
    );

    if (ageSeconds < 60) {
      return `${ageSeconds} sec`;
    }

    if (ageSeconds < 3600) {
      return `${Math.floor(ageSeconds / 60)} min`;
    }

    const hours = Math.floor(ageSeconds / 3600);
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }

  window.renderMatterEnvironmentSettingsModal = function () {
    ensureMatterEnvironmentModalShell();

    const body = document.getElementById("matterEnvironmentSettingsModalBody");
    if (!body) return;

    body.innerHTML = environmentSettingsHtml(envSnapshot());
  };

  window.renderMatterEnvironmentModal = function () {
    const modal = ensureMatterEnvironmentModalShell();
    const body = document.getElementById("matterEnvironmentModalBody");
    const title = document.getElementById("matterEnvironmentModalTitle");
    const snapshot = envSnapshot();
    const indoorDevices = environmentIndoorDevices(snapshot);
    const errors = [snapshot.outdoor?.error, snapshot.air_quality?.error]
      .map(error => String(error || "").trim())
      .filter(Boolean);

    if (!modal || !body) return;

    if (title) title.textContent = "Environment";

    body.innerHTML = `
      <section class="modal-section environment-current-section">
        <div class="modal-section-title">Current Conditions</div>
        ${environmentOverviewHtml(snapshot, "environment-modal-current-grid", true)}
        ${errors.map(error => `<div class="modal-subtitle environment-error-text">${envEsc(error)}</div>`).join("")}
      </section>

      ${indoorDevices.length
        ? environmentIndoorZonesHtml(indoorDevices)
        : `
          <section class="modal-section">
            <div class="modal-subtitle">No environmental sensors are reporting yet.</div>
          </section>
        `}
    `;

    window.syncDashboardValueSlots?.(body);
    window.renderMatterEnvironmentSettingsModal?.();
  };

  window.showMatterEnvironmentModal = async function () {
    window.closeAllMenus?.();

    const modal = ensureMatterEnvironmentModalShell();
    if (!modal) return;

    modal.hidden = false;
    document.body.classList.add("modal-open");
    window.renderMatterEnvironmentModal?.();

    try {
      await window.getDashboardEnvironmentStatus?.(false);
      window.renderMatterEnvironmentModal?.();
      window.renderDashboardHome?.();
    } catch (err) {
      const status = document.getElementById("matterEnvironmentStatusText");
      if (status) status.textContent = String(err?.message || err || "Environment status failed");
    }
  };

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

  window.showMatterEnvironmentSettings = function () {
    ensureMatterEnvironmentModalShell();
    window.renderMatterEnvironmentSettingsModal?.();

    const parentModal = document.getElementById("matterEnvironmentModal");
    const settingsModal = document.getElementById("matterEnvironmentSettingsModal");

    if (!settingsModal) return;

    if (parentModal && parentModal.hidden === false) {
      parentModal.hidden = true;
      settingsModal.dataset.returnModalId = "matterEnvironmentModal";
    } else {
      settingsModal.dataset.returnModalId = "";
    }

    settingsModal.hidden = false;
    document.body.classList.add("modal-open");

    requestAnimationFrame(() => {
      document.getElementById("matterEnvironmentZipInput")?.focus();
    });
  };

  window.hideMatterEnvironmentSettings = function (restoreParent = true) {
    const settingsModal = document.getElementById("matterEnvironmentSettingsModal");
    if (!settingsModal) return;

    const parentModalID = String(settingsModal.dataset.returnModalId || "").trim();

    settingsModal.hidden = true;
    settingsModal.dataset.returnModalId = "";

    if (restoreParent && parentModalID) {
      const parentModal = document.getElementById(parentModalID);

      if (parentModal) {
        parentModal.hidden = false;
        document.body.classList.add("modal-open");
        return;
      }
    }

    const anyOpen = [...document.querySelectorAll(".modal")]
      .some(modal => modal.hidden === false);

    if (!anyOpen) {
      document.body.classList.remove("modal-open");
    }
  };

  function environmentModalStatus(message = "") {
    const status = document.getElementById("matterEnvironmentStatusText");
    if (status) status.textContent = message;
  }

  function environmentSettingsPayloadFromModal() {
    const zipInput = document.getElementById("matterEnvironmentZipInput");
    const zipCode = String(zipInput?.value || "").replace(/\D/g, "").slice(0, 5);

    if (zipInput) zipInput.value = zipCode;

    return {
      zip_code: zipCode,
      weather_source: "noaa",
      air_quality_source: "airnow"
    };
  }

  window.saveMatterEnvironmentSettingsFromModal = async function () {
    environmentModalStatus("Saving…");

    try {
      await window.saveDashboardEnvironmentSettings?.(environmentSettingsPayloadFromModal());
      window.renderMatterEnvironmentModal?.();
      window.renderMatterEnvironmentSettingsModal?.();
      window.renderDashboardHome?.();
      environmentModalStatus("Saved.");
    } catch (err) {
      environmentModalStatus(String(err?.message || err || "Save failed"));
    }
  };
}());