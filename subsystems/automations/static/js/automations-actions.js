document.addEventListener("click", event => {
  const pageButton = event.target.closest("[data-automation-page]");

  if (pageButton) {
    setAutomationsPage(pageButton.dataset.automationPage || "catalog");
    return;
  }

  const saveButton = event.target.closest("[data-automation-save]");

  if (saveButton) {
    if (saveButton.dataset.automationSave === "tapo-recharge") {
      saveTapoRechargeAutomation(saveButton);
      return;
    }

    if (saveButton.dataset.automationSave === "tapo-day-reset") {
      saveTapoDayResetAutomation(saveButton);
      return;
    }
  }
});

window.automationModalData = window.automationModalData || {};

function ensureAutomationsModal() {
  if (document.getElementById("automationsModal")) return;

  document.body.insertAdjacentHTML("beforeend", `
    <div id="automationsModal" class="modal" hidden>
      <div class="modal-shell">
        <div class="modal-head">
          <div>
            <h1 id="automationsModalTitle" class="modal-title">Automations</h1>
            <div id="automationsModalSubtitle" class="modal-subtitle">Rules and device helpers</div>
          </div>

          <button class="modal-close" type="button" aria-label="Close automations" data-automations-close>
            ${window.dashboardIconHtml("close")}
          </button>
        </div>

        <div id="automationsModalBody" class="modal-body"></div>
      </div>
    </div>
  `);

  const modal = document.getElementById("automationsModal");

  modal?.addEventListener("click", event => {
    const closeButton = event.target instanceof Element
      ? event.target.closest("[data-automations-close]")
      : null;

    if (event.target === modal || closeButton) {
      window.hideAutomationsModal?.();
    }
  });
}

async function loadAutomationsData() {
  const res = await dashboardFetch("/api/automations");
  const data = await res.json();

  if (!data.ok) {
    throw new Error(data.error || "Automations failed to load");
  }

  window.automationModalData = data;
  return data;
}

function setAutomationsPage(page) {
  const body = document.getElementById("automationsModalBody");
  const title = document.getElementById("automationsModalTitle");
  const subtitle = document.getElementById("automationsModalSubtitle");
  const data = window.automationModalData || {};

  if (!body || !title || !subtitle) return;

  if (page === "tapo-recharge") {
    title.textContent = "Configure Automation";
    subtitle.textContent = "KotiBot client battery recharge";
    body.innerHTML = renderTapoRechargeAutomationPage(data);
    return;
  }

  if (page === "tapo-day-reset") {
    title.textContent = "Configure Automation";
    subtitle.textContent = "Tapo daytime reset";
    body.innerHTML = renderTapoDayResetAutomationPage(data);
    return;
  }

  title.textContent = "Automations";
  subtitle.textContent = "Rules and device helpers";
  body.innerHTML = renderAutomationsCatalog(data);
}

async function saveTapoRechargeAutomation(button) {
  const client = document.getElementById("automationRechargeClient");
  const target = document.getElementById("automationRechargeTarget");
  const enabled = document.getElementById("automationRechargeEnabled");

  if (!client?.value || !target?.value) return;

  button.disabled = true;

  try {
    const res = await dashboardFetch("/api/automations/tapo-recharge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        deviceID: client.value,
        targetID: target.value,
        enabled: enabled?.checked !== false,
      }),
    });

    const data = await res.json();

    if (!res.ok || !data.ok) {
      throw new Error(data.error || "Unable to save automation");
    }

    await loadAutomationsData();
    setAutomationsPage("catalog");
  } catch (error) {
    document.getElementById("automationsModalBody").insertAdjacentHTML("beforeend", `
      <section class="modal-section">
        <div class="automation-error">${String(error.message || error)}</div>
      </section>
    `);
  } finally {
    button.disabled = false;
  }
}

async function saveTapoDayResetAutomation(button) {
  const hour = document.getElementById("automationDayResetHour");
  const enabled = document.getElementById("automationDayResetEnabled");

  button.disabled = true;

  try {
    const res = await dashboardFetch("/api/automations/tapo-day-reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        resetHour: Number(hour?.value || 6),
        enabled: enabled?.checked !== false,
      }),
    });

    const data = await res.json();

    if (!res.ok || !data.ok) {
      throw new Error(data.error || "Unable to save automation");
    }

    await loadAutomationsData();
    setAutomationsPage("catalog");
  } catch (error) {
    document.getElementById("automationsModalBody").insertAdjacentHTML("beforeend", `
      <section class="modal-section">
        <div class="automation-error">${String(error.message || error)}</div>
      </section>
    `);
  } finally {
    button.disabled = false;
  }
}

window.showAutomationsModal = async function (initial = {}) {
  ensureAutomationsModal();

  const options = typeof initial === "string"
    ? { deviceID: initial }
    : (initial && typeof initial === "object" ? initial : {});

  document.getElementById("automationsModal").hidden = false;
  document.body.classList.add("modal-open");

  try {
    const data = await loadAutomationsData();

    window.automationModalData = {
      ...data,
      prefillDeviceID: String(options.deviceID || "").trim()
    };

    setAutomationsPage(options.page || "catalog");
  } catch (error) {
    document.getElementById("automationsModalBody").innerHTML = `
      <section class="modal-section">
        <div class="automation-error">${String(error.message || error)}</div>
      </section>
    `;
  }
};

window.hideAutomationsModal = function (event) {
  if (event && event.target?.id !== "automationsModal") return;

  const modal = document.getElementById("automationsModal");
  if (!modal) return;

  modal.hidden = true;
  document.body.classList.remove("modal-open");
};