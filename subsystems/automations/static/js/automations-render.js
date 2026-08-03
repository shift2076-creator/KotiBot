window.AUTOMATION_TYPE_TAPO_RECHARGE = "tapo_recharge_android_battery";
window.AUTOMATION_TYPE_TAPO_DAY_RESET = "tapo_day_reset";

function automationEsc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function automationHourLabel(hour) {
  const value = Number(hour || 0);

  if (value === 0) return "12:00 AM";

  return `${value}:00 AM`;
}

window.renderAutomationsCatalog = function (data = {}) {
  const installedTypes = new Set(data.installedTypes || []);

  return `
    <section class="modal-section">
      <button
        class="automation-card automation-card-control"
        type="button"
        data-automation-page="tapo-recharge"
      >
        <div class="automation-card-head">
          <div class="automation-card-title">Tapo plug recharge</div>
          ${
            installedTypes.has(window.AUTOMATION_TYPE_TAPO_RECHARGE)
              ? `${window.dashboardIconHtml("check_circle", "automation-installed-icon")}`
              : ``
          }
        </div>

        <div class="automation-card-body">
          <div class="automation-card-icon-wrap">
            ${window.dashboardIconHtml("battery_charging_full", "automation-card-icon")}
          </div>

          <div class="automation-card-description">
            Turn on a selected Tapo plug or outlet when a KotiBot Android client drops to 20% battery, then turn it off when the client reaches full charge.
          </div>
        </div>
      </button>

      <button
        class="automation-card automation-card-control"
        type="button"
        data-automation-page="tapo-day-reset"
      >
        <div class="automation-card-head">
          <div class="automation-card-title">Tapo daytime reset</div>
          ${
            installedTypes.has(window.AUTOMATION_TYPE_TAPO_DAY_RESET)
              ? `${window.dashboardIconHtml("check_circle", "automation-installed-icon")}`
              : ``
          }
        </div>

        <div class="automation-card-body">
          <div class="automation-card-icon-wrap">
            ${window.dashboardIconHtml("wb_sunny", "automation-card-icon")}
          </div>

          <div class="automation-card-description">
            Reset active evening, nightlight, movie, or custom bulb and room schemes back to Day at a selected AM hour without turning off lights back on.
          </div>
        </div>
      </button>
    </section>
  `;
};

window.renderTapoRechargeAutomationPage = function (data = {}) {
  const clients = Array.isArray(data.clients) ? data.clients : [];
  const targets = Array.isArray(data.targets) ? data.targets : [];
  const existing = Array.isArray(data.automations)
    ? data.automations.find(item => item.type === window.AUTOMATION_TYPE_TAPO_RECHARGE)
    : null;

  const prefillDeviceID = String(data.prefillDeviceID || "").trim();
  const prefillClient = clients.find(client => String(client.deviceID || "") === prefillDeviceID);
  const selectedDeviceID = prefillClient?.deviceID || existing?.deviceID || clients[0]?.deviceID || "";
  const selectedTargetID = existing?.targetID || targets[0]?.targetID || "";

  return `
    <section class="modal-section">
      <button class="automation-back-button" type="button" data-automation-page="catalog">
        ${window.dashboardIconHtml("arrow_back")}
        <span>Automations</span>
      </button>
    </section>

    <section class="modal-section">
      <div class="automation-config-head">
        <div class="automation-config-icon-wrap">
          ${window.dashboardIconHtml("battery_charging_full", "automation-config-icon")}
        </div>

        <div>
          <div class="automation-config-title">Tapo plug recharge</div>
          <div class="automation-config-description">
            Choose the Android client to protect and the Tapo plug or extender outlet that powers its charger.
          </div>
        </div>
      </div>
    </section>

    <section class="modal-section automation-config-form">
      <label class="automation-field">
        <span class="automation-label">KotiBot client</span>
        <select id="automationRechargeClient" class="automation-input">
          ${
            clients.length
              ? clients.map(client => `
                  <option value="${automationEsc(client.deviceID)}" ${client.deviceID === selectedDeviceID ? "selected" : ""}>
                    ${automationEsc(client.clientName || client.deviceID)} · ${automationEsc(client.battery ?? "—")}%
                  </option>
                `).join("")
              : `<option value="">No Android clients found</option>`
          }
        </select>
      </label>

      <label class="automation-field">
        <span class="automation-label">Tapo power</span>
        <select id="automationRechargeTarget" class="automation-input">
          ${
            targets.length
              ? targets.map(target => `
                  <option value="${automationEsc(target.targetID)}" ${target.targetID === selectedTargetID ? "selected" : ""}>
                    ${automationEsc(target.label || target.targetID)}
                  </option>
                `).join("")
              : `<option value="">No Tapo plugs or outlets found</option>`
          }
        </select>
      </label>

      <label class="automation-check-row">
        <input id="automationRechargeEnabled" type="checkbox" ${existing?.enabled === false ? "" : "checked"}>
        <span>Enable this automation</span>
      </label>

      <button
        class="automation-save-button"
        type="button"
        data-automation-save="tapo-recharge"
        ${clients.length && targets.length ? "" : "disabled"}
      >
        Save automation
      </button>
    </section>
  `;
};

window.renderTapoDayResetAutomationPage = function (data = {}) {
  const existing = data.dayReset || {};
  const selectedHour = Number.isFinite(Number(existing.resetHour))
    ? Number(existing.resetHour)
    : 6;

  return `
    <section class="modal-section">
      <button class="automation-back-button" type="button" data-automation-page="catalog">
        ${window.dashboardIconHtml("arrow_back")}
        <span>Automations</span>
      </button>
    </section>

    <section class="modal-section">
      <div class="automation-config-head">
        <div class="automation-config-icon-wrap">
          ${window.dashboardIconHtml("wb_sunny", "automation-config-icon")}
        </div>

        <div>
          <div class="automation-config-title">Tapo daytime reset</div>
          <div class="automation-config-description">
            Reset active Evening, Nightlight, Movie Time, and Custom schemes back to Day. Only lights already on receive the Day preset.
          </div>
        </div>
      </div>
    </section>

    <section class="modal-section automation-config-form">
      <label class="automation-field">
        <span class="automation-label">Reset time</span>
        <select id="automationDayResetHour" class="automation-input">
          ${Array.from({ length: 12 }, (_, hour) => `
            <option value="${hour}" ${hour === selectedHour ? "selected" : ""}>
              ${automationEsc(automationHourLabel(hour))}
            </option>
          `).join("")}
        </select>
      </label>

      <label class="automation-check-row">
        <input id="automationDayResetEnabled" type="checkbox" ${existing.enabled === false ? "" : "checked"}>
        <span>Enable this automation</span>
      </label>

      <button
        class="automation-save-button"
        type="button"
        data-automation-save="tapo-day-reset"
      >
        Save automation
      </button>
    </section>
  `;
};