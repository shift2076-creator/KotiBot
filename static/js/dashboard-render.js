"use strict";
var S = window.appState;

window.ensureDashboardHomeLightingModalShells = function () {
  if (!document.getElementById("dashboardHomeLightingModal")) {
    document.body.insertAdjacentHTML("beforeend", `
      <div id="dashboardHomeLightingModal" class="modal" hidden data-dashboard-modal="home-lighting">
        <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="dashboardHomeLightingModalTitle">
          <div class="modal-head">
            <div class="modal-title-wrap">
              <h1 id="dashboardHomeLightingModalTitle" class="modal-title">Scenes</h1>
            </div>
            <button class="modal-close" type="button" aria-label="Close lighting mode settings" data-dashboard-action="hide-home-lighting-settings">
              ${window.dashboardIconHtml("close")}
            </button>
          </div>

          <div id="dashboardHomeLightingModalBody" class="modal-body"></div>
        </div>
      </div>
    `);
  }

  if (!document.getElementById("dashboardHomeLightingAutomationModal")) {
    document.body.insertAdjacentHTML("beforeend", `
      <div id="dashboardHomeLightingAutomationModal" class="modal" hidden data-dashboard-modal="home-lighting-automation">
        <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="dashboardHomeLightingAutomationTitle">
          <div class="modal-head">
            <div class="modal-title-wrap">
              <h1 id="dashboardHomeLightingAutomationTitle" class="modal-title">Add to Mode</h1>
              <div id="dashboardHomeLightingAutomationSubtitle" class="modal-subtitle">Choose what this mode controls</div>
            </div>
            <button class="modal-close" type="button" aria-label="Close lighting preset" data-dashboard-action="hide-home-lighting-automation-editor">
              ${window.dashboardIconHtml("close")}
            </button>
          </div>

          <div id="dashboardHomeLightingAutomationBody" class="modal-body"></div>
        </div>
      </div>
    `);
  }
};

window.ensureDashboardHomeArmingModalShells = function () {
  if (!document.getElementById("dashboardHomeArmingModal")) {
    document.body.insertAdjacentHTML("beforeend", `
      <div id="dashboardHomeArmingModal" class="modal" hidden data-dashboard-modal="home-arming">
        <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="dashboardHomeArmingModalTitle">
          <div class="modal-head">
            <div class="modal-title-wrap">
<h1 id="dashboardHomeArmingModalTitle" class="modal-title">Security System Actions</h1>
            </div>
            <button class="modal-close" type="button" aria-label="Close arming state actions" data-dashboard-action="hide-home-arming-settings">
              ${window.dashboardIconHtml("close")}
            </button>
          </div>

          <div id="dashboardHomeArmingModalBody" class="modal-body"></div>
        </div>
      </div>
    `);
  }

  if (!document.getElementById("dashboardHomeArmingActionModal")) {
    document.body.insertAdjacentHTML("beforeend", `
      <div id="dashboardHomeArmingActionModal" class="modal" hidden data-dashboard-modal="home-arming-action">
        <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="dashboardHomeArmingActionTitle">
          <div class="modal-head">
            <div class="modal-title-wrap">
              <h1 id="dashboardHomeArmingActionTitle" class="modal-title">New Security System Action</h1>
              <div id="dashboardHomeArmingActionSubtitle" class="modal-subtitle"></div>
            </div>
            <button class="modal-close" type="button" aria-label="Close arming action picker" data-dashboard-action="hide-home-arming-action-picker">
              ${window.dashboardIconHtml("close")}
            </button>
          </div>

          <div id="dashboardHomeArmingBreadcrumb" class="dashboard-home-arming-breadcrumb" aria-label="Security system action steps"></div>

          <div id="dashboardHomeArmingActionBody" class="modal-body"></div>
        </div>
      </div>
    `);
  }
};

window.ensureDashboardActivityModalShell = function () {
  if (document.getElementById("dashboardActivityModal")) return;

  document.body.insertAdjacentHTML("beforeend", `
    <div id="dashboardActivityModal" class="modal dashboard-activity-modal" hidden data-dashboard-modal="activity">
      <div class="modal-shell dashboard-activity-modal-shell" role="dialog" aria-modal="true" aria-labelledby="dashboardActivityModalTitle">
        <div class="modal-head">
          <div class="modal-title-wrap">
            <h1 id="dashboardActivityModalTitle" class="modal-title">Recent Automation Activity</h1>
          </div>
          <button class="modal-close" type="button" aria-label="Close activity" data-dashboard-action="hide-activity-modal">
            ${window.dashboardIconHtml("close")}
          </button>
        </div>

        <div class="modal-body">
          <div class="modal-section">
            <div class="dashboard-activity-toolbar">
              <div class="dashboard-activity-filters" aria-label="Activity category">
                <button
                  class="dashboard-activity-filter"
                  type="button"
                  title="Automations"
                  aria-label="Automations"
                  data-dashboard-action="set-activity-filter"
                  data-activity-category="automation"
                >
                  ${window.dashboardIconHtml("auto_awesome")}
                </button>

                <button
                  class="dashboard-activity-filter"
                  type="button"
                  title="Security"
                  aria-label="Security"
                  data-dashboard-action="set-activity-filter"
                  data-activity-category="security"
                >
                  ${window.dashboardIconHtml("security")}
                </button>
              </div>

              <div
                class="dashboard-activity-time-filter"
                aria-label="Activity time range"
              >
                <span class="dashboard-activity-time-filter-icon">
                  ${window.dashboardIconHtml("schedule")}
                </span>

                <span class="dashboard-activity-time-filter-body">
                  <span id="dashboardActivityRangeText">
                    Loading range…
                  </span>

                  <span
                    id="dashboardActivityRange"
                    class="dashboard-activity-range"
                  >
                    <span
                      class="dashboard-activity-range-track"
                      aria-hidden="true"
                    ></span>

                    <span
                      class="dashboard-activity-range-selection"
                      aria-hidden="true"
                    ></span>

                    <input
                      id="dashboardActivityFromHours"
                      class="dashboard-activity-range-input dashboard-activity-range-from"
                      type="range"
                      min="0"
                      max="168"
                      value="168"
                      step="1"
                      data-activity-range-bound="from"
                      data-dashboard-input="preview-activity-range"
                      data-dashboard-change="set-activity-range"
                      aria-label="Oldest activity age"
                    >

                    <input
                      id="dashboardActivityToHours"
                      class="dashboard-activity-range-input dashboard-activity-range-to"
                      type="range"
                      min="0"
                      max="168"
                      value="0"
                      step="1"
                      data-activity-range-bound="to"
                      data-dashboard-input="preview-activity-range"
                      data-dashboard-change="set-activity-range"
                      aria-label="Newest activity age"
                    >
                  </span>
                </span>
              </div>
            </div>

            <div id="dashboardActivityList" class="dashboard-activity-list"></div>
            <div
              id="dashboardActivitySentinel"
              class="dashboard-activity-sentinel"
              aria-hidden="true"
              hidden
            ></div>
          </div>
        </div>
      </div>
    </div>
  `);
};

window.ensureDashboardModalShells = function () {
  window.ensureAndroidHomeModalShells?.();
  window.ensureDashboardHomeLightingModalShells?.();
  window.ensureDashboardHomeArmingModalShells?.();
  window.ensureDashboardActivityModalShell?.();

  if (!document.getElementById("clientMetaModal")) {
    document.body.insertAdjacentHTML("beforeend", `
      <div id="clientMetaModal" class="modal" hidden data-dashboard-modal="client-meta">
        <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="clientMetaModalTitle" data-dashboard-stop-click>
          <div class="modal-head">
            <div class="modal-title-wrap">
              <div id="clientMetaModalTitle" class="modal-title">Edit Device</div>
              <div id="clientMetaModalSubtitle" class="modal-subtitle"></div>
            </div>

            <button class="modal-close" type="button" aria-label="Close device details" data-dashboard-action="hide-client-meta">
              ${window.dashboardIconHtml("close")}
            </button>
          </div>

          <div id="clientMetaModalBody" class="modal-body"></div>
        </div>
      </div>
    `);
  }

  if (!document.getElementById("audioModal")) {
    document.body.insertAdjacentHTML("beforeend", `
      <div id="audioModal" class="modal" hidden data-dashboard-modal="audio">
        <div class="modal-shell" data-dashboard-stop-click>
          <div class="modal-head">
            <div class="modal-title">Select Audio</div>
            <button class="modal-close" type="button" aria-label="Close audio selection" data-dashboard-action="hide-audio">${window.dashboardIconHtml("close")}</button>
          </div>
          <div id="audioModalBody" class="modal-body"></div>
        </div>
      </div>
    `);
  }
};

function dashboardClientIsTapoCamera(c) {
  if (!c || !hasClientRole(c, "TAPO")) return false;

  const section = String(c.tapo_dashboard_section || "").trim().toLowerCase();
  const kind = String(c.tapo_kind || c.tapo_device_type || c.device_type || c.type || "").trim().toLowerCase();

  return (
    section === "camera" ||
    kind === "camera" ||
    kind.includes("camera") ||
    c.tapo_is_camera === true ||
    c.tapo_is_camera === 1 ||
    String(c.tapo_is_camera || "").trim().toLowerCase() === "true" ||
    !!c.tapo_hls_url ||
    !!c.tapo_rtsp_url
  );
}

function dashboardClientIsCamera(c) {
  return hasClientRole(c, "CAM") || dashboardClientIsTapoCamera(c);
}

function dashboardOptionalFunction(name) {
  const fn = window[name];
  return typeof fn === "function" ? fn : null;
}

function dashboardRenderCameraCard(c) {
  return dashboardOptionalFunction("renderCameraCard")?.(c) || "";
}

function dashboardRenderDoorCard(c) {
  return dashboardOptionalFunction("renderDoorCard")?.(c) || "";
}

function dashboardRenderMotionSensorCard(c) {
  return dashboardOptionalFunction("renderAndroidMotionSensorCard")?.(c) || "";
}

function dashboardSyncHomeDiscoveryAttention(clients) {
  dashboardOptionalFunction("syncDashboardHomeDiscoveryAttention")?.(clients);
}

function dashboardSyncServerViewControls() {
  dashboardOptionalFunction("syncServerViewControls")?.();
}

function dashboardSyncHomeModeButtons() {
  dashboardOptionalFunction("syncDashboardHomeModeButtons")?.();
}

function dashboardUpdatePreviewViewerState(cameras) {
  dashboardOptionalFunction("updatePreviewViewerState")?.(cameras);
}

function dashboardApplyColumnBuilderLayoutVars() {
  return dashboardOptionalFunction("applyColumnBuilderLayoutVars")?.();
}

function dashboardApplyCardDebugVisibility() {
  dashboardOptionalFunction("applyCardDebugVisibility")?.();
}

function dashboardClientHasAssignedRoom(c) {
  const room = String(
    c?.zone_name ||
    c?.zoneName ||
    c?.room_name ||
    c?.room ||
    c?.zone ||
    c?.area ||
    ""
  ).trim();

  return !!room && room.toLowerCase() !== "unassigned";
}

window.clientVisibleInCurrentMode = function (c) {
  if (!c?.provisioned) return false;

  const actionOnly = window.dashboardClientIsMatterActionOnly?.(c) === true;

  if (actionOnly && !S.renderControls) return false;
  if ((S.renderMonitors || S.renderControls || S.renderSensors) && !dashboardClientHasAssignedRoom(c)) return false;

  const isCamera = dashboardClientIsCamera(c);
  const isDoorSensor = hasClientRole(c, "DSS");
  const isTapoControl = hasClientRole(c, "TAPO") && c.tapo_dashboard_section !== "camera";
  const isMatterDevice = window.dashboardClientIsMatter?.(c) === true;
  const isAndroidMotionSensor = isCamera && !hasClientRole(c, "TAPO") && !isMatterDevice;

  if (S.renderMonitors) {
    return isCamera;
  }

  if (S.renderControls) {
    return actionOnly || (
      isTapoControl &&
      !dashboardTapoExplicitlyHidden(c)
    );
  }

  if (S.renderSensors) {
    return (
      isDoorSensor ||
      isAndroidMotionSensor ||
      isMatterDevice
    );
  }

  return !dashboardTapoExplicitlyHidden(c);
};

let dashboardHomeDiscoveryAcknowledgedSignature = "";
let dashboardHomeDiscoveryAttentionActive = false;

function dashboardHomeDiscoverySignature(clients) {
  const foundClients = typeof window.dashboardHomeFoundClients === "function"
    ? window.dashboardHomeFoundClients(clients || [])
    : [];

  return foundClients
    .map(c => `${String(c?.__homeFoundKind || "device").trim()}:${String(c?.deviceID || "").trim()}`)
    .filter(value => !value.endsWith(":"))
    .sort()
    .join("|");
}

window.dashboardHomeHasDiscoveryAttention = function () {
  return dashboardHomeDiscoveryAttentionActive;
};

window.syncDashboardHomeDiscoveryAttention = function (clients = S.currentClients || []) {
  const signature = dashboardHomeDiscoverySignature(clients);
  const pageMode = cleanDashboardPage?.(S.activeDashboardPage) || "home";
  const renderHomepage = pageMode === "home";

  if (!signature) {
    dashboardHomeDiscoveryAcknowledgedSignature = "";
    dashboardHomeDiscoveryAttentionActive = false;
  } else if (renderHomepage) {
    dashboardHomeDiscoveryAcknowledgedSignature = signature;
    dashboardHomeDiscoveryAttentionActive = false;
  } else {
    dashboardHomeDiscoveryAttentionActive = signature !== dashboardHomeDiscoveryAcknowledgedSignature;
  }

  document.body.dataset.homeDiscoveryAttention = dashboardHomeDiscoveryAttentionActive ? "on" : "off";

  const homeToggle = document.getElementById("asideHomeLogoToggle");
  if (homeToggle) {
    homeToggle.classList.toggle("attention", dashboardHomeDiscoveryAttentionActive);
  }
};

function dashboardActivityClientIcon(
  client,
  item = {}
) {
  const kind = String(
    item?.kind || ""
  ).trim().toLowerCase();

  if (!client?.deviceID) {
    if (kind === "matter_motion") {
      return "motion_sensor_active";
    }

    if (kind === "matter_contact") {
      return "door_front";
    }

    if (kind === "matter_switch_power") {
      return "toggle_on";
    }

    if (kind === "matter_button_press") {
      return "buttons_alt";
    }

    if (kind === "tapo_light_power") {
      return "emoji_objects";
    }

    if (
      kind === "tapo_power" ||
      kind === "tapo_extender_child_power" ||
      kind === "tapo_recharge"
    ) {
      return "power";
    }

    return "history";
  }

  return window.dashboardDeviceIconName(client);
}

function dashboardActivityItemsHtml({
  items = S.recentActivity,
  limit = null
} = {}) {
  let activity = Array.isArray(items) ? items : [];

  if (limit !== null && Number.isFinite(Number(limit))) {
    activity = activity.slice(0, Math.max(0, Number(limit)));
  }

  if (S.recentActivityLoading && !activity.length) return "";

  if (!activity.length) {
    return `<div class="dashboard-activity-empty">No recent activity</div>`;
  }

  const clientsByID = new Map(
    (S.currentClients || []).map(client => [String(client?.deviceID || ""), client])
  );

  return activity.map(item => {
    const deviceID = String(
      item.deviceID || ""
    );
    const parentDeviceID = deviceID
      .split("|", 1)[0];
    const client = (
      clientsByID.get(deviceID) ||
      clientsByID.get(parentDeviceID) ||
      {}
    );
    const zone = esc(item.zone || client.zone_name || client.zoneName || client.room || "—");
    const name = esc(item.name || client.name || "Device");
    const icon = esc(
      dashboardActivityClientIcon(
        client,
        item
      )
    );
    const accent = esc(
      item.accent || "system"
    );
    const statusText = String(
      item.status ||
      item.state ||
      "Activity"
    ).trim();
    const detailText = String(
      item.detail || ""
    ).trim();
    const status = esc(statusText);
    const detail = (
      detailText &&
      detailText !== statusText
    )
      ? esc(detailText)
      : "";
    const time = esc(item.time || "");

    return `
      <article class="dashboard-activity-item">
        ${window.dashboardIconHtml(icon, `icon-glow dashboard-activity-icon dashboard-activity-icon-${accent}`)}
        <span class="dashboard-activity-copy">
          <span class="dashboard-activity-name">${name}</span>
          <span class="dashboard-activity-zone">${zone}</span>
        </span>
        <span class="dashboard-activity-event-copy">
          <span class="dashboard-activity-event">${status}</span>
          ${detail
            ? `<span class="dashboard-activity-detail">${detail}</span>`
            : ""}
        </span>
        <span class="dashboard-activity-time">${time}</span>
      </article>
    `;
  }).join("");
}

function dashboardSettingsActivityItemsHtml(items = S.recentActivity) {
  return dashboardActivityItemsHtml({
    items,
    limit: 3
  });
}

window.syncSettingsRecentActivity = function (items = S.recentActivity) {
  const container = document.getElementById("settingsRecentActivity");
  if (!container) return;

  container.innerHTML = dashboardSettingsActivityItemsHtml(items);
};

function dashboardActivityAgeLabel(hours) {
  const cleanHours = Math.max(
    0,
    Math.round(Number(hours) || 0)
  );

  if (!cleanHours) {
    return "Now";
  }

  if (cleanHours < 24) {
    return `${cleanHours}h ago`;
  }

  const days = Math.floor(cleanHours / 24);
  const remainder = cleanHours % 24;

  return remainder
    ? `${days}d ${remainder}h ago`
    : `${days}d ago`;
}

function dashboardActivityRangeText(
  fromHours,
  toHours
) {
  return (
    `${dashboardActivityAgeLabel(fromHours)} – ` +
    dashboardActivityAgeLabel(toHours)
  );
}

window.syncDashboardActivityRange = function (
  changedInput = null
) {
  const fromRange = document.getElementById(
    "dashboardActivityFromHours"
  );
  const toRange = document.getElementById(
    "dashboardActivityToHours"
  );
  const range = document.getElementById(
    "dashboardActivityRange"
  );
  const rangeText = document.getElementById(
    "dashboardActivityRangeText"
  );
  const selection = range?.querySelector(
    ".dashboard-activity-range-selection"
  );

  if (!fromRange || !toRange) {
    return null;
  }

  const availableHours = Math.max(
    1,
    Math.round(
      Number(S.activityAvailableHours || 1)
    )
  );
  const rangeStyles = range
    ? window.getComputedStyle(range)
    : null;
  const thumbSize = Math.max(
    1,
    Number.parseFloat(
      rangeStyles?.getPropertyValue(
        "--activity-range-thumb-size"
      ) || ""
    ) || 12
  );
  const rangeWidth = Math.max(
    thumbSize + 1,
    range?.getBoundingClientRect().width ||
    thumbSize + 1
  );
  const travelWidth = Math.max(
    1,
    rangeWidth - thumbSize
  );
  const minimumGapHours = Math.min(
    availableHours,
    Math.max(
      1,
      Math.ceil(
        (
          thumbSize /
          travelWidth
        ) *
        availableHours
      )
    )
  );

  let fromHours = Math.max(
    minimumGapHours,
    Math.min(
      availableHours,
      Math.round(
        Number(fromRange.value) ||
        availableHours
      )
    )
  );

  let toHours = Math.max(
    0,
    Math.min(
      availableHours - minimumGapHours,
      Math.round(Number(toRange.value) || 0)
    )
  );

  if (
    fromHours - toHours <
    minimumGapHours
  ) {
    if (changedInput === fromRange) {
      fromHours = Math.min(
        availableHours,
        toHours + minimumGapHours
      );
    } else {
      toHours = Math.max(
        0,
        fromHours - minimumGapHours
      );
    }
  }

  fromRange.value = String(fromHours);
  toRange.value = String(toHours);

  fromRange.setAttribute(
    "aria-valuetext",
    dashboardActivityAgeLabel(fromHours)
  );
  toRange.setAttribute(
    "aria-valuetext",
    dashboardActivityAgeLabel(toHours)
  );

  if (range && selection) {
    const startRatio = (
      availableHours - fromHours
    ) / availableHours;
    const endRatio = (
      availableHours - toHours
    ) / availableHours;
    const startPosition = (
      thumbSize / 2
    ) + (
      startRatio * travelWidth
    );
    const endPosition = (
      thumbSize / 2
    ) + (
      endRatio * travelWidth
    );

    selection.style.insetInlineStart = (
      `${startPosition}px`
    );
    selection.style.inlineSize = (
      `${Math.max(
        0,
        endPosition - startPosition
      )}px`
    );
  }

  if (rangeText) {
    rangeText.textContent = S.activityOldestTs
      ? dashboardActivityRangeText(
          fromHours,
          toHours
        )
      : (
          S.recentActivityLoading
            ? "Loading range…"
            : "No activity yet"
        );
  }

  return {
    availableHours,
    fromHours,
    toHours
  };
};

window.syncDashboardActivityAutoLoad = function () {
  S.activityAutoLoadObserver?.disconnect();
  S.activityAutoLoadObserver = null;

  const modal = document.getElementById("dashboardActivityModal");
  const body = modal?.querySelector(".modal-body");
  const sentinel = document.getElementById("dashboardActivitySentinel");

  if (
    !modal ||
    modal.hidden ||
    !body ||
    !sentinel ||
    !S.activityHasMore ||
    S.recentActivityLoading
  ) {
    return;
  }

  S.activityAutoLoadObserver = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) {
      window.loadOlderActivity?.();
    }
  }, {
    root: body,
    rootMargin: "0px 0px 160px",
    threshold: 0
  });

  S.activityAutoLoadObserver.observe(sentinel);
};

window.syncDashboardActivityModal = function () {
  const modal = document.getElementById(
    "dashboardActivityModal"
  );
  const list = document.getElementById(
    "dashboardActivityList"
  );
  const title = document.getElementById(
    "dashboardActivityModalTitle"
  );

  if (!modal || !list) return;

  if (title) {
    const mode = (
      S.activityFilter === "security"
        ? "Security"
        : "Automation"
    );

    title.textContent = (
      `Recent ${mode} Activity`
    );
  }

  list.innerHTML = dashboardActivityItemsHtml();

  modal.querySelectorAll("[data-activity-category]").forEach(button => {
    const active = button.dataset.activityCategory === S.activityFilter;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });

  const fromRange = document.getElementById(
    "dashboardActivityFromHours"
  );
  const toRange = document.getElementById(
    "dashboardActivityToHours"
  );
  const availableHours = Math.max(
    1,
    Math.round(
      Number(S.activityAvailableHours || 1)
    )
  );
  const selectedFromHours = (
    S.activityFromHours > 0
      ? Math.min(
          availableHours,
          Math.round(S.activityFromHours)
        )
      : availableHours
  );
  const selectedToHours = Math.min(
    Math.max(
      0,
      Math.round(
        Number(S.activityToHours || 0)
      )
    ),
    Math.max(0, selectedFromHours - 1)
  );

  if (fromRange && toRange) {
    fromRange.min = "0";
    fromRange.max = String(availableHours);
    fromRange.value = String(
      selectedFromHours
    );

    toRange.min = "0";
    toRange.max = String(availableHours);
    toRange.value = String(
      selectedToHours
    );

    fromRange.disabled = !S.activityOldestTs;
    toRange.disabled = !S.activityOldestTs;
  }

  window.syncDashboardActivityRange?.();

  const sentinel = document.getElementById("dashboardActivitySentinel");
  if (sentinel) {
    sentinel.hidden = !S.activityHasMore;
  }

  window.syncDashboardActivityAutoLoad?.();
};

function syncDashboardAsideFit(
  el = document.getElementById("dashboardAside")
) {
  if (!el) return;

  const nav = el.querySelector(".aside-nav");
  const footerMode =
    window.matchMedia?.("(max-aspect-ratio: 2/3)")?.matches === true;

  el.classList.remove("aside-truncated");
  document.body.removeAttribute("data-dashboard-aside-truncated");

  if (!nav || footerMode) return;

  const styles = window.getComputedStyle(el);
  const paddingBlockStart =
    Number.parseFloat(styles.paddingBlockStart || styles.paddingTop) || 0;
  const paddingBlockEnd =
    Number.parseFloat(styles.paddingBlockEnd || styles.paddingBottom) || 0;
  const availableBlockSize = Math.max(
    0,
    el.clientHeight - paddingBlockStart - paddingBlockEnd
  );
  const needsTruncation =
    nav.scrollHeight > Math.ceil(availableBlockSize) + 1;

  if (!needsTruncation) return;

  el.classList.add("aside-truncated");
  document.body.dataset.dashboardAsideTruncated = "1";
}

window.syncDashboardAsideFit = syncDashboardAsideFit;

function revealDashboardNavigation(el) {
  if (!el || el.dataset.dashboardNavigationRevealStarted === "1") return;

  el.dataset.dashboardNavigationRevealStarted = "1";
  el.classList.add("dashboard-navigation-measuring");

  syncDashboardAsideFit(el);

  const bounds = el.getBoundingClientRect();

  el.classList.remove("dashboard-navigation-measuring");
  el.style.setProperty(
    "--dashboard-navigation-expanded-inline-size",
    `${bounds.width}px`
  );
  el.style.setProperty(
    "--dashboard-navigation-expanded-block-size",
    `${bounds.height}px`
  );

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      document.body.dataset.dashboardNavigationRevealed = "1";

      window.setTimeout(() => {
        document.body.dataset.dashboardNavigationSettled = "1";
        el.style.removeProperty("--dashboard-navigation-expanded-inline-size");
        el.style.removeProperty("--dashboard-navigation-expanded-block-size");

        syncDashboardAsideFit(el);
      }, 800);
    });
  });
}

window.renderDashboardAside = function () {
  const el = document.getElementById("dashboardAside");
  if (!el) return;

  const pageMode = cleanDashboardPage?.(S.activeDashboardPage) || "home";
  const renderHomepage = pageMode === "home";
  const renderControls = pageMode === "controls";
  const renderMonitors = pageMode === "monitor";
  const renderSensors = pageMode === "sensors";
  const renderActivity = S.activityModalOpen === true;
  const homeDiscoveryAttention = window.dashboardHomeHasDiscoveryAttention?.() === true;

  const asideSignature = JSON.stringify({
    pageMode,
    renderActivity,
    homeDiscoveryAttention
  });

  if (el.dataset.asideSignature === asideSignature) {
    return;
  }

  el.dataset.asideSignature = asideSignature;

  el.innerHTML = `
    <nav class="aside-nav">
      <button
        id="asideHomeLogoToggle"
        class="aside-link ${renderHomepage ? "active" : ""} ${homeDiscoveryAttention ? "attention" : ""}"
        type="button"
        title="KotiBot Home"
        aria-label="KotiBot Home"
        data-dashboard-action="aside-home"
      >
        ${window.dashboardIconHtml("kotibot", "aside-home-icon")}
        <span class="aside-label">Home</span>
      </button>

      <button
        id="asideRenderControlsToggle"
        class="aside-link ${renderControls ? "active" : ""}"
        type="button"
        title="System Controls"
        aria-label="System Controls"
        data-dashboard-action="aside-render-controls"
      >
        ${window.dashboardIconHtml("toggle_on", "aside-controls-icon")}
        <span class="aside-label">Controls</span>
      </button>

      <button
        id="asideRenderMonitorsToggle"
        class="aside-link ${renderMonitors ? "active" : ""}"
        type="button"
        title="Monitor Camera Feeds"
        aria-label="Monitor Camera Feeds"
        data-dashboard-action="aside-render-monitors"
      >
        ${window.dashboardIconHtml("videocam")}
        <span class="aside-label">Monitor</span>
      </button>

      <button
        id="asideRenderSensorsToggle"
        class="aside-link ${renderSensors ? "active" : ""}"
        type="button"
        title="System Sensors"
        aria-label="System Sensors"
        data-dashboard-action="aside-render-sensors"
      >
        ${window.dashboardIconHtml("sensors")}
        <span class="aside-label">Sensors</span>
      </button>

      <div class="aside-double-space"></div>

      <button
        id="asideSettingsToggle"
        class="aside-link"
        type="button"
        title="KotiBot System"
        aria-label="KotiBot System"
        data-dashboard-action="aside-show-settings"
      >
        ${window.dashboardIconHtml("settings")}
        <span class="aside-label">System</span>
      </button>

      <button
        id="asideScenesToggle"
        class="aside-link aside-wide-only"
        type="button"
        title="Edit Scenes"
        aria-label="Edit Scenes"
        data-dashboard-action="show-home-lighting-settings"
      >
        ${window.dashboardIconHtml("auto_awesome")}
        <span class="aside-label">Scenes</span>
      </button>

      <button
        id="asideSecurityToggle"
        class="aside-link aside-wide-only"
        type="button"
        title="Edit Security Settings"
        aria-label="Edit Security Settings"
        data-dashboard-action="show-home-arming-settings"
      >
        ${window.dashboardIconHtml("security")}
        <span class="aside-label">Security</span>
      </button>

      <button
        id="asideActivityToggle"
        class="aside-link aside-wide-only ${renderActivity ? "active" : ""}"
        type="button"
        title="Recent Activity"
        aria-label="Recent Activity"
        data-dashboard-action="aside-show-activity"
      >
        ${window.dashboardIconHtml("history")}
        <span class="aside-label">Activity</span>
      </button>
    </nav>
  `;

  revealDashboardNavigation(el);
};

window.applyCardDebugVisibility = function () {
  const showDebug = document.body.dataset.cardDebug !== "off";

  document.querySelectorAll(".debug-area").forEach(el => {
    el.hidden = !showDebug;
  });
};

window.renderCardSubtitle = function (c) {
  return esc(clientRoomName(c));
};

function dashboardDebugText(value, fallback = "—") {
  if (value === undefined || value === null) return fallback;

  const text = String(value).trim();
  return text || fallback;
}

function dashboardDebugPercent(value) {
  if (value === undefined || value === null || value === "") return "—";

  const number = Number(value);

  if (Number.isFinite(number)) {
    return `${number.toFixed(number % 1 === 0 ? 0 : 1)}%`;
  }

  return dashboardDebugText(value);
}

function dashboardBatteryIsMatter(c) {
  return String(c?.source || "").trim().toLowerCase() === "matter" || String(c?.deviceID || "").startsWith("matter:");
}

function dashboardBatteryPercentValue(c) {
  if (dashboardBatteryIsMatter(c)) return null;

  const candidates = [
    c?.battery,
    c?.tapo_battery_percent,
    c?.tapo_battery_level,
    c?.tapo_battery
  ];

  for (const value of candidates) {
    if (value === undefined || value === null || value === "") continue;

    const number = Number(value);
    if (Number.isFinite(number)) return number;
  }

  return null;
}

function dashboardBatteryLowValue(c) {
  const lowCandidates = [
    c?.matter_battery_low,
    c?.battery_low,
    c?.matter_battery_replacement_needed,
    c?.tapo_battery_low
  ];

  for (const value of lowCandidates) {
    const boolValue = dashboardBool(value);

    if (boolValue !== null) return boolValue;
  }

  const stateText = String(c?.battery_state ?? "").trim().toLowerCase();

  if (["low", "warning", "critical", "replace", "replacement_needed", "replacement-needed"].includes(stateText)) return true;
  if (["ok", "okay", "normal", "good", "nominal", "healthy"].includes(stateText)) return false;

  const chargeLevel = Number(c?.matter_battery_charge_level);

  if (Number.isFinite(chargeLevel)) {
    return chargeLevel > 0;
  }

  const chargeText = String(c?.matter_battery_charge_level ?? "").trim().toLowerCase();

  if (["warning", "critical", "low", "replace", "replacement_needed", "replacement-needed"].includes(chargeText)) return true;
  if (["ok", "okay", "normal", "good", "nominal", "healthy"].includes(chargeText)) return false;

  return null;
}

function dashboardBatteryIconValue(c) {
  const low = dashboardBatteryLowValue(c);

  if (dashboardBatteryIsMatter(c)) {
    if (low === true) return 10;
    if (low === false) return 100;
    return null;
  }

  const percent = dashboardBatteryPercentValue(c);

  if (percent !== null) return percent;
  if (low === true) return 10;
  if (low === false) return 100;

  return null;
}

function dashboardBatteryHoverText(c) {
  const percent = dashboardBatteryPercentValue(c);

  if (percent !== null) return dashboardDebugPercent(percent);

  const low = dashboardBatteryLowValue(c);

  if (low === true) return "Low Battery";
  if (low === false) return "Battery OK";

  return "";
}

window.dashboardBatteryHoverText = dashboardBatteryHoverText;

function dashboardDebugBatteryText(c) {
  const low = dashboardBatteryLowValue(c);

  if (dashboardBatteryIsMatter(c)) {
    if (low === true) return "LOW";
    if (low === false) return "OK";
    return "—";
  }

  const percent = dashboardBatteryPercentValue(c);

  if (percent !== null) return dashboardDebugPercent(percent);
  if (low === true) return "LOW";
  if (low === false) return "OK";

  return "—";
}

function dashboardTapoKind(c) {
  const kind = String(c?.tapo_kind || c?.tapo_device_type || "").trim().toLowerCase();

  if (c?.tapo_is_camera === true || c?.tapo_dashboard_section === "camera" || kind === "camera") return "camera";
  if (c?.tapo_is_bulb === true || kind === "bulb" || kind === "lightstrip") return kind || "bulb";
  if (c?.tapo_is_outlet_extender === true || kind === "outlet_extender") return "outlet_extender";
  if (c?.tapo_is_plug === true || kind === "plug" || kind === "outlet" || kind === "socket") return "plug";

  return kind || "unknown";
}

function dashboardTapoPowerText(c) {
  const power = dashboardBool(c?.tapo_is_on ?? c?.is_on ?? c?.device_on ?? c?.state);

  if (power === true) return "ON";
  if (power === false) return "OFF";

  return "—";
}

function dashboardTapoControlText(c) {
  const controlReady = dashboardBool(c?.tapo_control_ready ?? c?.control_ready);
  const controlError = dashboardDebugText(c?.tapo_control_error ?? c?.control_error, "");

  if (controlError) return `ERROR: ${controlError}`;
  if (controlReady === true) return "READY";
  if (controlReady === false) return "ERROR";

  return "—";
}

function dashboardTapoStreamText(c) {
  if (c?.tapo_hls_url) return "HLS";
  if (c?.tapo_rtsp_url) return "RTSP";

  const rtsp = dashboardBool(c?.tapo_supports_rtsp);
  const onvif = dashboardBool(c?.tapo_supports_onvif);

  if (rtsp === true && onvif === true) return "RTSP/ONVIF";
  if (rtsp === true) return "RTSP";
  if (onvif === true) return "ONVIF";

  return "—";
}

function dashboardTapoDebugBaseRows(c) {
  return [
    ["STATUS", dashboardTapoStatusText(c)],
    ["IP", dashboardDebugText(c?.tapo_ip || c?.ip)],
    ["ID", dashboardDebugText(c?.tapo_id || c?.deviceID)],
    ["MAC", dashboardDebugText(c?.tapo_mac)],
    ["MODEL", dashboardDebugText(c?.tapo_model || c?.tapo_device_type || c?.model)],
    ["KIND", dashboardDebugText(dashboardTapoKind(c))]
  ];
}

function dashboardTapoDebugTailRows(c) {
  return [
    ["ZONE", dashboardDebugText(c?.zone_name || c?.zoneName)],
    ["LAST UPDATE", dashboardDebugText(formatLastUpdateText(c?.last_update))]
  ];
}

function dashboardTapoStatusText(c) {
  if (c?.stale) return "UNKNOWN";

  const kind = dashboardTapoKind(c);
  const controlText = dashboardTapoControlText(c);

  if (kind === "camera") {
    if (c?.tapo_recording || c?.tapo_recording_enabled) return "RECORDING";
    if (dashboardTapoStreamText(c) !== "—") return "ONLINE";

    return controlText === "READY" ? "READY" : "IDLE";
  }

  if (controlText.startsWith("ERROR")) {
    return controlText;
  }

  const powerText = dashboardTapoPowerText(c);

  if (powerText !== "—") return powerText;

  return controlText === "READY" ? "READY" : "ONLINE";
}

function dashboardAndroidStatusText(c, el) {
  if (c?.stale) return "UNKNOWN";

  const cardKind = el?.dataset?.nodeCard || "";
  const isCameraCard = cardKind === "camera" || !!el?.querySelector?.(".camera-preview");

  if (cardKind === "motion") {
    const motionEnabled = dashboardBool(c?.motion_detection_enabled ?? c?.motionDetectionEnabled) === true;
    const motionActive = dashboardBool(c?.visual_motion_active ?? c?.motion_active ?? c?.motionActive) === true;

    if (!motionEnabled) return "DISABLED";
    return motionActive ? "MOTION" : "CLEAR";
  }

  if (isCameraCard || hasClientRole(c || {}, "CAM")) {
    return c?.frame_live ? "ONLINE" : "NO FEED";
  }

  if (hasClientRole(c || {}, "DSS")) {
    const openScore = Number(c?.openness_score || 0).toFixed(2);
    return `${String(c?.door_status || "unknown").toUpperCase()} (${openScore})`;
  }

  return c?.provisioned ? "ONLINE" : "NEW";
}

function dashboardDebugRowsForTapo(c) {
  const kind = dashboardTapoKind(c);
  const rows = dashboardTapoDebugBaseRows(c);

  if (kind === "camera") {
    rows.push(["RTSP", dashboardBool(c?.tapo_supports_rtsp) === true ? "TRUE" : "—"]);
    rows.push(["ONVIF", dashboardBool(c?.tapo_supports_onvif) === true ? "TRUE" : "—"]);
    rows.push(["STREAM", dashboardTapoStreamText(c)]);
    rows.push(["CONTROL", dashboardTapoControlText(c)]);
    rows.push(...dashboardTapoDebugTailRows(c));
    return rows;
  }

  if (kind === "plug") {
    rows.push(["POWER", dashboardTapoPowerText(c)]);
    rows.push(["CONTROL", dashboardTapoControlText(c)]);

    if (c?.tapo_parent_name || c?.tapo_child_name || c?.tapo_child_id) {
      rows.push(["PARENT", dashboardDebugText(c?.tapo_parent_name)]);
      rows.push(["CHILD", dashboardDebugText(c?.tapo_child_name || c?.tapo_child_id)]);
    }

    rows.push(...dashboardTapoDebugTailRows(c));
    return rows;
  }

  if (kind === "outlet_extender") {
    const childCount = Array.isArray(c?.tapo_children) ? c.tapo_children.length : 0;

    rows.push(["POWER", dashboardTapoPowerText(c)]);
    rows.push(["CONTROL", dashboardTapoControlText(c)]);
    rows.push(["CHILDREN", childCount ? String(childCount) : "—"]);
    rows.push(...dashboardTapoDebugTailRows(c));
    return rows;
  }

  if (kind === "bulb" || kind === "lightstrip") {
    rows.push(["POWER", dashboardTapoPowerText(c)]);

    if (c?.tapo_supports_brightness || c?.tapo_brightness !== undefined) {
      rows.push(["BRIGHTNESS", dashboardDebugPercent(c?.tapo_brightness)]);
    }

    if (c?.tapo_supports_color_temp || c?.tapo_color_temperature !== undefined) {
      rows.push(["COLOR TEMP", c?.tapo_color_temperature ? `${dashboardDebugText(c.tapo_color_temperature)}K` : "—"]);
    }

    if (c?.tapo_supports_color) {
      rows.push(["COLOR", `${dashboardDebugText(c?.tapo_hue)} / ${dashboardDebugText(c?.tapo_saturation)}%`]);
    }

    rows.push(["CONTROL", dashboardTapoControlText(c)]);
    rows.push(...dashboardTapoDebugTailRows(c));
    return rows;
  }

  rows.push(["POWER", dashboardTapoPowerText(c)]);
  rows.push(["CONTROL", dashboardTapoControlText(c)]);
  rows.push(...dashboardTapoDebugTailRows(c));
  return rows;
}

function dashboardDebugRowsForAndroid(c, el) {
  const rows = [
    ["STATUS", dashboardAndroidStatusText(c, el)],
    ["IP", dashboardDebugText(c?.ip)],
    ["ID", dashboardDebugText(c?.deviceID)],
    ["CLIENT VER", dashboardDebugText(c?.version)],
    ["BATTERY", dashboardDebugBatteryText(c)],
    ["ZONE", dashboardDebugText(c?.zone_name || c?.zoneName)],
    ["LAST UPDATE", dashboardDebugText(formatLastUpdateText(c?.last_update))]
  ];

  if (c?.brand || c?.androidVersion) {
    rows.splice(3, 0, ["BRAND", dashboardDebugText(c?.brand)]);
    rows.splice(4, 0, ["ANDROID VER", dashboardDebugText(c?.androidVersion)]);
  }

  return rows;
}

function dashboardClientDebugRows(c, el) {
  if (window.dashboardClientIsMatter?.(c)) {
    return ["matter", typeof window.dashboardDebugRowsForMatter === "function" ? window.dashboardDebugRowsForMatter(c) : dashboardDebugRowsForAndroid(c, el)];
  }

  if (hasClientRole(c || {}, "TAPO")) {
    return ["tapo", dashboardDebugRowsForTapo(c)];
  }

  return ["android", dashboardDebugRowsForAndroid(c, el)];
}

function dashboardDebugRowsHtml(rows) {
  return rows
    .map(([label, value]) => `
      <span class="debug-label">${esc(String(label || ""))}</span><span class="debug-val">${esc(String(dashboardDebugText(value)))}</span>
    `)
    .join("");
}

window.syncClientDebugArea = function (el, c) {
  if (!el || !c) return;

  if (el.dataset?.dashboardCameraPicker === "1") {
    el.querySelector(".debug-area")?.remove();
    return;
  }

  const [debugKind, rows] = dashboardClientDebugRows(c, el);
  let debugArea = el.querySelector(":scope > .debug-area") || el.querySelector(".debug-area");

  if (!debugArea) {
    debugArea = document.createElement("div");
    debugArea.className = "debug-area";

    const head = el.querySelector(":scope > .card-head") || el.querySelector(".card-head");

    if (head?.parentElement === el) {
      head.insertAdjacentElement("afterend", debugArea);
    } else {
      el.appendChild(debugArea);
    }
  }

  debugArea.className = "debug-area";
  debugArea.dataset.debugKind = debugKind;
  debugArea.innerHTML = dashboardDebugRowsHtml(rows);
  debugArea.hidden = document.body.dataset.cardDebug === "off";
};

function dashboardCardListItemID(c) {
  return String(c?.__dashboardCardID || c?.deviceID || "");
}

function findCardListItem(container, cardID) {
  const id = String(cardID || "");

  return Array.from(container.children).find(el =>
    String(el?.dataset?.dashboardCardId || el?.dataset?.deviceId || "") === id
  ) || null;
}

window.normalizeDashboardDeviceCard = function (el) {
  if (!el) return null;

  el.classList.add("dashboard-device-card");
  el.dataset.dashboardDeviceCard = "1";

  const head = el.querySelector(".card-head");
  const status = head?.querySelector(":scope > .status-area");
  const titleIcon = status?.querySelector(":scope > .koti-icon:first-child");
  const titleGroup = status?.querySelector(":scope > .card-title-group");
  const actions = head?.querySelector(":scope > .card-actions");

  head?.classList.add("dashboard-device-card-head");
  status?.classList.add("dashboard-device-card-status");
  titleIcon?.classList.add("icon-glow");
  titleGroup?.classList.add("dashboard-device-card-title-group");
  actions?.classList.add("dashboard-device-card-actions");

  return el;
};

window.renderCardList = function (container, clients, renderFunc) {
  if (!container) return;

  const activeEl = document.activeElement;
  if (container.contains(activeEl) && activeEl.tagName === "INPUT") return;

  const list = (clients || []).filter(c => c?.deviceID);
  const newIds = new Set(list.map(dashboardCardListItemID));

  Array.from(container.children).forEach(el => {
    const id = String(el?.dataset?.dashboardCardId || el?.dataset?.deviceId || "");

    if (!id || !newIds.has(id)) {
      el.remove();
    }
  });

  list.forEach(c => {
    const cardID = dashboardCardListItemID(c);
    let el = findCardListItem(container, cardID);

    if (!el) {
      const html = String(renderFunc(c) || "").trim();
      if (!html) return;

      const temp = document.createElement("div");
      temp.innerHTML = html;
      el = temp.firstElementChild;

      if (!el) return;

      el.dataset.dashboardCardId = cardID;
      el.dataset.deviceId = String(c.deviceID || "");
      container.appendChild(el);
    }

    window.normalizeDashboardDeviceCard(el);
    updateCard(el, c);
  });
};

window.ensureRoomGroup = function (container, room) {
  let group = container.querySelector(`.room-group[data-room="${CSS.escape(room)}"]`);
  const roomTitle = room;

  if (!group) {
    container.insertAdjacentHTML("beforeend", `
      <section class="room-group" data-room="${esc(room)}" data-room-label="${esc(roomTitle)}">
        <div class="room-head">
          <div class="room-title-wrap">
            <button
              class="icon-btn dashboard-zone-drag-handle"
              type="button"
              title="Drag to reorder ${esc(roomTitle)} zone"
              aria-label="Reorder ${esc(roomTitle)} zone"
              data-dashboard-zone-drag-handle
            >
              ${window.dashboardIconHtml("koti-fa-grip")}
            </button>
            <h3 class="modal-section-title room-title">${esc(roomTitle)}</h3>
            <span class="room-environment" data-room-environment hidden></span>
          </div>
          <div class="room-actions" data-room-actions></div>
        </div>
        <div class="room-card-row room-control-row" data-room-row="controls" data-room-label="${esc(roomTitle)}"></div>
        <div class="room-card-row room-camera-row" data-room-row="cameras" data-room-label="${esc(roomTitle)}"></div>
        <div class="room-card-row room-sensor-row" data-room-row="sensors" data-room-label="${esc(roomTitle)}"></div>
      </section>
    `);

    group = container.querySelector(`.room-group[data-room="${CSS.escape(room)}"]`);
  }

  return group;
};

window.ensureRoomLanes = function (container, laneCount) {
  container.querySelectorAll(":scope > .room-lane").forEach((lane, index) => {
    if (index >= laneCount) lane.remove();
  });

  for (let i = 0; i < laneCount; i += 1) {
    if (!container.querySelector(`:scope > .room-lane[data-room-lane="${i}"]`)) {
      const lane = document.createElement("div");
      lane.className = "room-lane";
      lane.dataset.roomLane = String(i);
      container.appendChild(lane);
    }
  }

  return Array.from(container.querySelectorAll(":scope > .room-lane"));
};

function setDashboardRoomRowVisible(row, visible) {
  if (!row) return;

  row.hidden = !visible;
  row.setAttribute("aria-hidden", visible ? "false" : "true");

  if (visible) {
    row.style.removeProperty("display");
  } else {
    row.style.setProperty("display", "none", "important");
  }
}

function dashboardCameraLabel(c) {
  return c?.clientName || c?.tapo_alias || c?.name || c?.deviceID || "Camera";
}

function setDashboardButtonHint(button, hint) {
  const cleanHint = String(hint || "").trim();

  if (!button || !cleanHint) return;

  button.title = cleanHint;
  button.setAttribute("aria-label", cleanHint);
}

function getDashboardSelectedCamera(cameras) {
  const cameraList = Array.isArray(cameras) ? cameras : [];

  if (!cameraList.length) {
    S.selectedDashboardCameraId = "";
    return null;
  }

  const savedId = String(S.selectedDashboardCameraId || localStorage.getItem("dashboardSelectedCameraId") || "");
  const selected = cameraList.find(c => String(c?.deviceID || "") === savedId) || cameraList[0];
  const selectedId = String(selected?.deviceID || "");

  S.selectedDashboardCameraId = selectedId;

  if (selectedId) {
    localStorage.setItem("dashboardSelectedCameraId", selectedId);
  }

  return selected || null;
}

window.selectDashboardCamera = function (deviceID) {
  const selectedId = String(deviceID || "").trim();
  if (!selectedId) return;
  if (document.body.dataset.dashboardLayout !== "portrait") return;

  S.selectedDashboardCameraId = selectedId;
  localStorage.setItem("dashboardSelectedCameraId", selectedId);

  window.requestDashboardRender?.({
    clients: S.currentClients || [],
    server: S.serverState || S.server || {},
    used_zones: S.currentUsedZones || []
  });
};

function ensureDashboardFeaturedCamera(container) {
  let featured = container.querySelector(":scope > .dashboard-featured-camera");

  if (!featured) {
    featured = document.createElement("section");
    featured.className = "dashboard-featured-camera";
    featured.setAttribute("aria-label", "Selected camera");
    featured.innerHTML = '<div class="dashboard-featured-camera-row" data-dashboard-featured-camera-row></div>';
  }

  const hero = container.querySelector(":scope > .dashboard-grouped-hero");
  const expectedNext = hero?.nextElementSibling || container.firstElementChild || null;

  if (featured.parentElement !== container || featured !== expectedNext) {
    container.insertBefore(featured, expectedNext);
  }

  return featured;
}

function renderDashboardFeaturedCamera(container, cameras) {
  container.querySelectorAll(":scope > .dashboard-featured-camera").forEach((el, index) => {
    if (index > 0) el.remove();
  });

  const portraitRenderMonitors = !!S.renderMonitors && document.body.dataset.dashboardLayout === "portrait";

  if (!portraitRenderMonitors) {
    container.querySelector(":scope > .dashboard-featured-camera")?.remove();
    return null;
  }

  const selected = getDashboardSelectedCamera(cameras);
  const featured = ensureDashboardFeaturedCamera(container);
  const row = featured.querySelector("[data-dashboard-featured-camera-row]");

  featured.hidden = !selected;
  renderCardList(row, selected ? [selected] : [], dashboardRenderCameraCard);

  return selected;
}

function renderDashboardCameraPickerCard(c, selectedId) {
  const temp = document.createElement("div");
  temp.innerHTML = dashboardRenderCameraCard(c);

  const card = temp.firstElementChild;
  if (!card) return "";

  const id = String(c?.deviceID || "");
  const isSelected = id === String(selectedId || "");
  const previewContainer = card.querySelector(".camera-preview-container");
  const previewHead = card.querySelector(".camera-preview-head");

  card.classList.add("dashboard-camera-picker-card");
  card.dataset.dashboardCameraPicker = "1";
  card.dataset.selected = isSelected ? "1" : "0";
  card.setAttribute("aria-current", isSelected ? "true" : "false");

  card.querySelector(".camera-preview-rotator")?.remove();
  card.querySelector(".debug-area")?.remove();

  if (previewContainer) {
    previewContainer.removeAttribute("data-camera-video-open");
    previewContainer.dataset.dashboardAction = "select-dashboard-camera";
    previewContainer.dataset.deviceId = id;
    previewContainer.setAttribute("role", "button");
    previewContainer.setAttribute("tabindex", "0");
    previewContainer.setAttribute("aria-label", `Show ${dashboardCameraLabel(c)} camera`);
  }

  if (previewHead) {
    previewHead.dataset.dashboardAction = "select-dashboard-camera";
    previewHead.dataset.deviceId = id;
  }

  return card.outerHTML;
}

function syncDashboardCameraPickerCards(container, selectedId) {
  container.querySelectorAll(".dashboard-camera-picker-card").forEach(card => {
    const id = String(card.dataset.deviceId || "");
    const isSelected = id === String(selectedId || "");

    card.dataset.selected = isSelected ? "1" : "0";
    card.setAttribute("aria-current", isSelected ? "true" : "false");

    card.querySelectorAll(".camera-preview-head").forEach(el => {
      el.removeAttribute("data-camera-video-open");
      el.dataset.dashboardAction = "select-dashboard-camera";
      el.dataset.deviceId = id;
      el.setAttribute("role", "button");
      el.setAttribute("tabindex", "0");
      el.setAttribute("aria-label", `Show ${card.querySelector(".card-title")?.textContent || "selected"} camera`);
    });

    card.querySelector(".camera-preview-rotator")?.remove();
    card.querySelector(".debug-area")?.remove();
  });
};

function syncNonPortraitCameraHeaders(root = document) {
  const nonPortrait = document.body.dataset.dashboardLayout !== "portrait";

  root.querySelectorAll(".cameracard").forEach(card => {
    const preview = card.querySelector(":scope > .camera-preview-container");
    const nestedHead = preview?.querySelector(":scope > .camera-preview-head");
    const detachedHead = card.querySelector(":scope > .camera-preview-head");

    if (nonPortrait && preview && nestedHead) {
      card.insertBefore(nestedHead, preview);
    } else if (!nonPortrait && preview && detachedHead) {
      preview.insertBefore(detachedHead, preview.firstElementChild);
    }

    const head = card.querySelector(":scope > .camera-preview-head")
      || preview?.querySelector(":scope > .camera-preview-head");

    if (nonPortrait && head) {
      delete head.dataset.dashboardAction;
      delete head.dataset.deviceId;
      head.removeAttribute("role");
      head.removeAttribute("tabindex");
      head.removeAttribute("aria-current");
      head.removeAttribute("aria-label");
      head.removeAttribute("data-camera-video-open");
    }

    card.classList.toggle("camera-head-detached", nonPortrait);
  });
}

window.renderGroupedDashboard = function ({
  controlClients,
  sensorClients,
  cameras,
  tapoPlugs,
  tapoBulbs
}) {
  const container = document.getElementById("clientCards");
  if (!container) return;

  container.classList.add("room-dashboard");

  const home = container.querySelector(":scope > .dashboard-home");
  if (home) {
    home.hidden = true;
    home.setAttribute("aria-hidden", "true");
  }

  syncDashboardPageHeader(container);

  Array.from(container.children).forEach(child => {
    if (
      !child.classList.contains("dashboard-home") &&
      !child.classList.contains("dashboard-grouped-hero") &&
      !child.classList.contains("dashboard-featured-camera") &&
      !child.classList.contains("room-group") &&
      !child.classList.contains("room-lane")
    ) {
      child.remove();
    }
  });

  const portraitRenderMonitors = !!S.renderMonitors && document.body.dataset.dashboardLayout === "portrait";
  const selectedCamera = renderDashboardFeaturedCamera(container, cameras || []);
  const selectedCameraId = portraitRenderMonitors ? String(selectedCamera?.deviceID || "") : "";

  const rooms = new Map();

  const ensureRoom = (c) => {
    const room = clientRoomName(c);
    if (!rooms.has(room)) {
      rooms.set(room, {
        controls: [],
        cameras: [],
        sensors: [],
        bulbs: []
      });
    }
    return rooms.get(room);
  };

  (tapoPlugs || []).forEach(c => {
    const room = ensureRoom(c);
    const roomPowerEnabled = dashboardTapoRoomPowerEnabled(c, false);

    if (!dashboardTapoHideIndividualCard(c)) {
      room.controls.push(c);
    }

    if (roomPowerEnabled) {
      room.bulbs.push(c);
    }
  });

  (tapoBulbs || []).forEach(c => {
    const room = ensureRoom(c);

    if (!dashboardTapoHideIndividualCard(c)) {
      room.controls.push(c);
    }

    room.bulbs.push(c);
  });

  const groupedControlClients = typeof window.dashboardGroupMatterClients === "function"
    ? window.dashboardGroupMatterClients(controlClients || [])
    : (controlClients || []);

  groupedControlClients.forEach(c => {
    ensureRoom(c).controls.push(c);
  });

  (cameras || []).forEach(c => ensureRoom(c).cameras.push(c));

  const groupedSensorClients = typeof window.dashboardGroupMatterClients === "function"
    ? window.dashboardGroupMatterClients(sensorClients || [])
    : (sensorClients || []);

  groupedSensorClients.forEach(c => ensureRoom(c).sensors.push({
    c,
    kind: c.__dashboardSensorKind || (
      window.dashboardClientIsMatter?.(c)
        ? "matter"
        : (
            hasClientRole(c, "TAPO") &&
            String(
              c.tapo_dashboard_section || ""
            ).trim().toLowerCase() === "sensor"
          )
          ? "tapo"
          : "door"
    )
  }));

  (S.currentClients || [])
    .filter(
      c =>
        window.dashboardClientIsMatterEnvironment?.(c) === true
    )
    .forEach(c => ensureRoom(c));

  const roomEntries = sortDashboardRoomEntries(
    Array.from(rooms.entries())
      .map(([room, data]) => ({
        room,
        data,
        weight: estimateRoomLayoutWeight(room, data)
      }))
      .filter(entry => {
        if (String(entry.room || "").trim().toLowerCase() === "unassigned") {
          return false;
        }

        if (S.renderMonitors) {
          return entry.data.cameras.length;
        }

        if (S.renderControls) {
          return entry.data.controls.length || entry.data.bulbs.length;
        }

        if (S.renderSensors) {
          return entry.data.sensors.length;
        }

        return (
          entry.data.controls.length ||
          entry.data.cameras.length ||
          entry.data.sensors.length ||
          entry.data.bulbs.length
        );
      })
  );

  const activeRooms = roomEntries.map(entry => entry.room);
  const zoneOrderIndex = new Map(roomEntries.map((entry, index) => [entry.room, index]));

  container.querySelectorAll(".room-group").forEach(group => {
    if (!activeRooms.includes(group.dataset.room || "")) group.remove();
  });

  const gridColumns = getRoomGridColumnCount(roomEntries);

  container.style.setProperty("--room-grid-columns", String(gridColumns));

  const laneEntries = [];

  roomEntries.forEach(entry => {
    const roomSpan = Math.max(
      1,
      Math.min(gridColumns, getRoomColumnSpan(entry.data, gridColumns))
    );
    let lane = laneEntries[laneEntries.length - 1];

    if (!lane || lane.roomSpan + roomSpan > gridColumns) {
      lane = {
        roomSpan: 0,
        entries: []
      };
      laneEntries.push(lane);
    }

    lane.roomSpan += roomSpan;
    lane.entries.push({
      ...entry,
      roomSpan
    });
  });

  const lanes = ensureRoomLanes(container, laneEntries.length);

  dashboardApplyColumnBuilderLayoutVars();

  laneEntries.forEach((laneData, laneIndex) => {
    const lane = lanes[laneIndex];

    laneData.entries.forEach(({ room, data: roomData, roomSpan: packedRoomSpan }, roomIndex) => {
      const group = ensureRoomGroup(container, room);
      const zoneOrder = zoneOrderIndex.get(room) ?? roomIndex;

      group.dataset.dashboardZoneOrder = String(zoneOrder);
      group.dataset.renderControlsZoneOrder = S.renderControls ? String(zoneOrder) : "";
      group.dataset.renderMonitorsZoneOrder = S.renderMonitors ? String(zoneOrder) : "";
      group.dataset.renderSensorsZoneOrder = S.renderSensors ? String(zoneOrder) : "";
      const roomSpan = Math.max(
        1,
        Math.min(gridColumns, Number(packedRoomSpan) || getRoomColumnSpan(roomData, gridColumns))
      );
      const roomItemCount = S.renderControls
        ? roomData.controls.length
        : S.renderSensors
          ? roomData.sensors.length
          : roomData.cameras.length;
      const roomDashboardColumns = getRoomDashboardColumns(roomItemCount, roomSpan);

      group.style.setProperty("--room-column-span", String(roomSpan));
      group.style.setProperty("--room-dashboard-columns", String(roomDashboardColumns));

      const expectedIndex = laneData.entries.findIndex(entry => entry.room === room);
      const roomGroups = Array.from(lane.querySelectorAll(":scope > .room-group"));
      const expectedNext = roomGroups[expectedIndex] || null;
      const zoneDragActive = document.body?.classList.contains("dashboard-zone-drag-active");

      if (!zoneDragActive && (group.parentElement !== lane || group !== expectedNext)) {
        lane.insertBefore(group, expectedNext);
      }

      const controlRow = group.querySelector('[data-room-row="controls"]');
      const cameraRow = group.querySelector('[data-room-row="cameras"]');
      const sensorRow = group.querySelector('[data-room-row="sensors"]');
      const roomActions = group.querySelector("[data-room-actions]");
      const roomBulbs = roomData.bulbs || [];
      const roomControls = (roomData.controls || []).filter(c => hasClientRole(c, "TAPO"));

      const roomEnvironment = group.querySelector("[data-room-environment]");

      if (S.renderSensors) {
        window.syncMatterRoomEnvironmentHeader?.(
          group,
          room,
          S.currentClients || []
        );
      } else if (roomEnvironment) {
        roomEnvironment.hidden = true;
        roomEnvironment.replaceChildren();
      }

      if (roomActions) {
        const renderedRoomActions = S.renderMonitors || S.renderSensors
          ? ""
          : (
              window.renderTapoRoomActions?.(
                room,
                roomBulbs,
                roomControls
              ) || ""
            );

        roomActions.innerHTML = renderedRoomActions;
      }

      setDashboardRoomRowVisible(controlRow, roomData.controls.length > 0);
      setDashboardRoomRowVisible(cameraRow, roomData.cameras.length > 0);
      setDashboardRoomRowVisible(sensorRow, roomData.sensors.length > 0);

      renderCardList(
        controlRow,
        roomData.controls,
        c => window.dashboardClientIsMatter?.(c)
          ? window.renderMatterClientCard?.(c) || ""
          : window.renderTapoClientCard?.(c) || ""
      );

      if (portraitRenderMonitors) {
        cameraRow.querySelectorAll(":scope > :not(.dashboard-camera-picker-card)").forEach(el => el.remove());
      } else {
        cameraRow.querySelectorAll(".dashboard-camera-picker-card").forEach(el => el.remove());
      }

      renderCardList(
        cameraRow,
        roomData.cameras,
        c => portraitRenderMonitors
          ? renderDashboardCameraPickerCard(c, selectedCameraId)
          : dashboardRenderCameraCard(c)
      );

      if (portraitRenderMonitors) {
        syncDashboardCameraPickerCards(cameraRow, selectedCameraId);
      } else {
        syncNonPortraitCameraHeaders(cameraRow);
      }

      renderCardList(
        sensorRow,
        roomData.sensors.map(item => ({
          ...item.c,
          __roomSensorKind: item.kind
        })),
        c => (c.__roomSensorKind === "matter" && typeof window.renderMatterClientCard === "function")
          ? window.renderMatterClientCard(c)
          : (c.__roomSensorKind === "tapo" && typeof window.renderTapoClientCard === "function")
            ? window.renderTapoClientCard(c)
            : c.__roomSensorKind === "android-motion"
              ? dashboardRenderMotionSensorCard(c)
              : dashboardRenderDoorCard(c)
      );
    });
  });
};

function dashboardPageHeaderMode() {
  return cleanDashboardPage?.(S.activeDashboardPage) || (
    S.renderControls
      ? "controls"
      : S.renderMonitors
        ? "monitor"
        : S.renderSensors
          ? "sensors"
          : "home"
  );
}

function dashboardPageHeaderLabel(mode) {
  if (mode === "activity") return "KotiBot activity";
  if (mode === "monitor") return "KotiBot monitor";
  if (mode === "sensors") return "KotiBot sensors";
  if (mode === "controls") return "KotiBot controls";
  return "KotiBot home";
}

function dashboardHeaderMarkup() {
  return `
    <img class="dashboard-home-logo" src="/static/img/KotiBot.svg" alt="">
    <div class="dashboard-home-title-wrap">
      <h1 class="dashboard-home-title">KotiBot</h1>
      <div class="dashboard-home-subtitle">Smart Home Command Center</div>
    </div>
  `;
}

function dashboardHomeEnvironmentSnapshot() {
  return S.environmentState && typeof S.environmentState === "object" ? S.environmentState : {};
}

function dashboardHomeEnvironmentNumber(value) {
  if (value === undefined || value === null || value === "") return null;

  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function dashboardHomeEnvironmentEsc(value) {
  return typeof window.esc === "function" ? window.esc(value) : String(value ?? "");
}

function dashboardHomeEnvironmentEscAttr(value) {
  return typeof window.escAttr === "function"
    ? window.escAttr(value)
    : dashboardHomeEnvironmentEsc(value).replace(/"/g, "&quot;");
}

function dashboardHomeEnvironmentIconName(icon, id) {
  const cleanIcon = String(icon || "").trim().toLowerCase();
  const cleanID = String(id || "").trim().toLowerCase();

  if (["thermometer", "device_thermostat"].includes(cleanIcon) || cleanID === "indoor_temp") return "device_thermostat";
  if (["droplet", "water_drop"].includes(cleanIcon) || cleanID === "humidity") return "water_drop";
  if (["leaf", "eco"].includes(cleanIcon) || cleanID === "air_quality") return "eco";
  if (["sun", "wb_sunny"].includes(cleanIcon)) return "wb_sunny";
  if (cleanID !== "outdoor") return cleanIcon || "sensors";

  const snapshot = dashboardHomeEnvironmentSnapshot();
  const condition = String(snapshot.outdoor?.condition || "").toLowerCase();
  const iconUrl = String(snapshot.outdoor?.icon || "").toLowerCase();
  const iconCondition = iconUrl.split("?")[0].split("/").pop() || "";
  const weatherText = `${condition} ${iconCondition.replace(/_/g, " ")}`;
  const isNight = iconUrl.includes("/night/") || iconUrl.includes("night");

  if (weatherText.includes("thunder") || weatherText.includes("t-storm")) return "thunderstorm";
  if (weatherText.includes("snow") || weatherText.includes("sleet") || weatherText.includes("ice")) return "weather_snowy";

  if (weatherText.includes("heavy rain")) return "rainy_heavy";

  if (
    weatherText.includes("rain showers") ||
    weatherText.includes("rain_showers")
  ) {
    return "rain_showers";
  }

  if (
    weatherText.includes("rain") ||
    weatherText.includes("shower") ||
    weatherText.includes("drizzle")
  ) {
    return "rainy";
  }

  if (weatherText.includes("smoke")) return "smoke";

  if (
    weatherText.includes("fog") ||
    weatherText.includes("haze") ||
    weatherText.includes("mist")
  ) {
    return "foggy";
  }

  if (weatherText.includes("wind")) return "air";

  if (
    weatherText.includes("partly") ||
    weatherText.includes("few clouds") ||
    weatherText.includes("mostly clear")
  ) {
    return isNight ? "partly_cloudy_night" : "partly_cloudy_day";
  }

  if (weatherText.includes("overcast")) return "overcast";
  if (weatherText.includes("cloud")) return "cloud";

  if (
    weatherText.includes("clear") ||
    weatherText.includes("sun") ||
    weatherText.includes("fair")
  ) {
    return isNight ? "dark_mode" : "wb_sunny";
  }

  return isNight ? "dark_mode" : "wb_sunny";
}

function dashboardHomeEnvironmentValueSlotHtml(options = {}) {
  if (typeof window.dashboardValueSlotHtml === "function") {
    return window.dashboardValueSlotHtml(options);
  }

  const value = String(options.value ?? "").trim() || String(options.placeholder ?? "");

  return `<span class="${dashboardHomeEnvironmentEscAttr(options.contentClass || "")}">${dashboardHomeEnvironmentEsc(value)}</span>`;
}

function dashboardHomeEnvironmentAqiValue(snapshot = dashboardHomeEnvironmentSnapshot()) {
  const aqi = dashboardHomeEnvironmentNumber(snapshot.air_quality?.aqi);
  return aqi === null ? "" : `AQI ${Math.round(aqi)}`;
}

function dashboardHomeEnvironmentAqiLabel(snapshot = dashboardHomeEnvironmentSnapshot()) {
  const aqi = dashboardHomeEnvironmentNumber(snapshot.air_quality?.aqi);
  const category = String(snapshot.air_quality?.label || "Unavailable").trim() || "Unavailable";

  if (aqi === null) {
    const source = String(snapshot.air_quality?.source || "").trim();
    return source && source !== "Not configured" ? "Unavailable" : "Not Configured";
  }

  return category;
}

function dashboardHomeEnvironmentMetricHtml(metric = {}) {
  const id = String(metric.id || "environment").trim().toLowerCase().replace(/[^a-z0-9_-]/g, "-") || "environment";
  const icon = dashboardHomeEnvironmentIconName(metric.icon, id);
  const iconClass = String(icon || "sensors").trim().toLowerCase().replace(/[^a-z0-9_-]/g, "-") || "sensors";
  const valueText = String(metric.value ?? "").trim();
  const labelText = String(metric.label ?? "").trim();
  const valuePlaceholder = String(metric.valuePlaceholder ?? "");
  const labelPlaceholder = String(metric.labelPlaceholder || "Loading");
  const valueReady = metric.valueReady ?? window.dashboardValueIsReady?.(valueText, valuePlaceholder) ?? valueText !== valuePlaceholder;
  const labelReady = metric.labelReady ?? window.dashboardValueIsReady?.(labelText, labelPlaceholder) ?? !!labelText;
  const labelHtml = metric.labelFades === true
    ? dashboardHomeEnvironmentValueSlotHtml({
        key: `home-environment:${id}:label`,
        value: labelText || labelPlaceholder,
        placeholder: labelPlaceholder,
        slotClass: `dashboard-home-environment-label-slot dashboard-home-environment-${id}-label-slot`,
        contentClass: "dashboard-home-environment-label",
        ready: labelReady
      })
    : `<span class="dashboard-home-environment-label">${dashboardHomeEnvironmentEsc(labelText)}</span>`;

  return `
    <article class="dashboard-home-environment-metric dashboard-home-environment-metric-${dashboardHomeEnvironmentEscAttr(id)} dashboard-home-environment-icon-${dashboardHomeEnvironmentEscAttr(iconClass)}" data-environment-metric="${dashboardHomeEnvironmentEscAttr(id)}">
      <span class="dashboard-home-environment-icon-wrap">
        ${window.dashboardIconHtml(icon, "dashboard-home-environment-icon")}
      </span>
      ${dashboardHomeEnvironmentValueSlotHtml({
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

function dashboardHomeEnvironmentLoadingSection() {
  const snapshot = dashboardHomeEnvironmentSnapshot();
  const aqiColor = String(snapshot.air_quality?.color || "").trim();
  const aqiStyle = aqiColor ? ` style="--environment-aqi-color: ${dashboardHomeEnvironmentEscAttr(aqiColor)}"` : "";
  const airQualityReady = !!(snapshot.air_quality && typeof snapshot.air_quality === "object" && Object.keys(snapshot.air_quality).length);
  const outdoorReady = !!String(snapshot.outdoor?.condition || snapshot.outdoor?.icon || snapshot.outdoor?.temperature_text || snapshot.outdoor?.updated_at || "").trim();

  return `
    <button class="dashboard-home-card dashboard-home-environment-section" type="button" data-dashboard-action="show-environment-modal" aria-label="Open environment and conditions"${aqiStyle}>
      <div class="dashboard-home-section-head">
        <h2 class="dashboard-home-section-title">Environment</h2>
      </div>

      <div class="dashboard-home-environment-grid">
        <section class="dashboard-home-environment-group dashboard-home-environment-group-indoor">
          <div class="dashboard-home-environment-group-metrics">
            ${dashboardHomeEnvironmentMetricHtml({
              id: "indoor_temp",
              icon: "device_thermostat",
              value: snapshot.indoor?.temperature_text || "",
              label: "Indoor"
            })}
            ${dashboardHomeEnvironmentMetricHtml({
              id: "humidity",
              icon: "water_drop",
              value: snapshot.indoor?.humidity_text || "",
              label: "Humidity"
            })}
          </div>
        </section>

        <section class="dashboard-home-environment-group dashboard-home-environment-group-outdoor">
          <div class="dashboard-home-environment-group-metrics">
            ${dashboardHomeEnvironmentMetricHtml({
              id: "air_quality",
              icon: "eco",
              value: dashboardHomeEnvironmentAqiValue(snapshot),
              label: dashboardHomeEnvironmentAqiLabel(snapshot),
              valueReady: airQualityReady,
              labelReady: airQualityReady,
              labelFades: true
            })}
            ${dashboardHomeEnvironmentMetricHtml({
              id: "outdoor",
              icon: dashboardHomeEnvironmentIconName("", "outdoor"),
              value: snapshot.outdoor?.temperature_text || "",
              label: "Outdoor",
              valueReady: outdoorReady
            })}
          </div>
        </section>
      </div>
    </button>
  `;
}

function syncDashboardPageHeader(container) {
  if (!container) return null;

  document.getElementById("sectionClients")
    ?.querySelectorAll(":scope > .dashboard-page-hero")
    .forEach(hero => hero.remove());

  const mode = dashboardPageHeaderMode();

  if (mode === "home") {
    container.querySelectorAll(":scope > .dashboard-grouped-hero").forEach(hero => hero.remove());
    return null;
  }

  const label = dashboardPageHeaderLabel(mode);
  let hero = container.querySelector(
    ":scope > .dashboard-grouped-hero, " +
    ":scope > .dashboard-page-hero, " +
    ":scope > .dashboard-controls-hero"
  );

  if (!hero) {
    hero = document.createElement("section");
    container.insertBefore(hero, container.firstElementChild || null);
  } else if (hero !== container.firstElementChild) {
    container.insertBefore(hero, container.firstElementChild || null);
  }

  hero.className = [
    "dashboard-grouped-hero",
    "dashboard-home-card",
    "dashboard-home-hero",
    `dashboard-${mode}-hero`
  ].join(" ");
  hero.dataset.dashboardHero = mode;
  hero.setAttribute("aria-label", label);

  if (!hero.querySelector(".dashboard-home-logo") || !hero.querySelector(".dashboard-home-title")) {
    hero.innerHTML = dashboardHeaderMarkup();
  }

  const logo = hero.querySelector("img");
  if (logo) {
    logo.className = "dashboard-home-logo";
    logo.setAttribute("src", "/static/img/KotiBot.svg");
    logo.setAttribute("alt", "");
  }

  const titleWrap = hero.querySelector("div");
  if (titleWrap) {
    titleWrap.className = "dashboard-home-title-wrap";
  }

  const title = hero.querySelector("h1");
  if (title) {
    title.className = "dashboard-home-title";
    title.textContent = "KotiBot";
  }

  const subtitle = hero.querySelector(".dashboard-home-subtitle, .dashboard-controls-subtitle");
  if (subtitle) {
    subtitle.className = "dashboard-home-subtitle";
    subtitle.textContent = "Smart Home Command Center";
  }

  return hero;
}

let dashboardHomeFoundSectionShown = false;

function clearDashboardHomeFoundReveal(slot) {
  slot.classList.remove(
    "dashboard-home-matter-found-entering",
    "dashboard-home-matter-found-visible"
  );
  slot.style.removeProperty("--dashboard-home-found-height");
}

function revealDashboardHomeFoundSection(slot) {
  const section = slot.querySelector('[data-home-client-section="matter"]');

  if (!section) {
    dashboardHomeFoundSectionShown = false;
    clearDashboardHomeFoundReveal(slot);
    return;
  }

  if (dashboardHomeFoundSectionShown) return;

  dashboardHomeFoundSectionShown = true;

  slot.style.setProperty(
    "--dashboard-home-found-height",
    `${Math.ceil(section.getBoundingClientRect().height)}px`
  );
  slot.classList.add("dashboard-home-matter-found-entering");
  slot.classList.remove("dashboard-home-matter-found-visible");

  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => {
      slot.classList.add("dashboard-home-matter-found-visible");
    });
  });

  window.setTimeout(() => {
    clearDashboardHomeFoundReveal(slot);
  }, 700);
}

function syncDashboardHomeFoundSection(homeControls, clients) {
  const syncFoundSection = window.syncMatterFoundHomeSection;

  if (typeof syncFoundSection !== "function") return false;

  syncFoundSection(homeControls, clients);

  const slot = homeControls.querySelector("[data-home-matter-found-slot]");

  if (!slot || slot.hidden) {
    dashboardHomeFoundSectionShown = false;

    if (slot) clearDashboardHomeFoundReveal(slot);

    return true;
  }

  revealDashboardHomeFoundSection(slot);
  return true;
}

window.renderDashboardHome = function () {
  const clientContainer = document.getElementById("clientCards");

  if (!clientContainer) return;

  const clientModal = document.getElementById("clientMenuModal");

  if (clientModal && !clientModal.hidden) {
    return;
  }

  clientContainer.classList.remove("room-dashboard");

  let home = clientContainer.querySelector(":scope > .dashboard-home");

  if (!home) {
    home = document.createElement("div");
    home.className = "dashboard-home";
    clientContainer.appendChild(home);
  }

  home.hidden = false;
  home.removeAttribute("aria-hidden");

  let homeHeader = home.querySelector(":scope > .dashboard-home-hero");

  if (!homeHeader) {
    home.insertAdjacentHTML("afterbegin", `
      <section class="dashboard-home-card dashboard-home-hero" aria-label="KotiBot home">
        ${dashboardHeaderMarkup()}
      </section>
    `);
    homeHeader = home.querySelector(":scope > .dashboard-home-hero");
  }

  if (homeHeader && homeHeader !== home.firstElementChild) {
    home.insertBefore(homeHeader, home.firstElementChild || null);
  }

  let homeControls = home.querySelector(":scope > .dashboard-home-control-wrap");

  if (!homeControls) {
    homeControls = document.createElement("div");
    homeControls.className = "dashboard-home-control-wrap";
    home.appendChild(homeControls);
  }

  const homeControlsMarkup = `
    <div class="dashboard-home-spacer"></div>

    <div class="dashboard-home-matter-found-slot" data-home-matter-found-slot hidden></div>

    ${typeof window.renderDashboardHomeEnvironmentSection === "function" ? window.renderDashboardHomeEnvironmentSection() : dashboardHomeEnvironmentLoadingSection()}

    <section class="dashboard-home-card dashboard-home-light-section">
      <div class="dashboard-home-section-head dashboard-home-section-head-with-action">
        <h2 class="dashboard-home-section-title">Scenes</h2>
      </div>

      <div class="dashboard-home-light-row">
        <button class="settings-item dashboard-home-light-btn power-toggle" type="button" data-dashboard-action="set-home-light-mode" data-mode="day">
          <span class="ui-icon-circle dashboard-home-mode-circle">${window.dashboardIconHtml("wb_sunny", "dashboard-home-mode-icon")}</span>
          <span>Day</span>
        </button>
        <button class="settings-item dashboard-home-light-btn power-toggle" type="button" data-dashboard-action="set-home-light-mode" data-mode="evening">
          <span class="ui-icon-circle dashboard-home-mode-circle">${window.dashboardIconHtml("wb_twilight", "dashboard-home-mode-icon")}</span>
          <span>Evening</span>
        </button>
        <button class="settings-item dashboard-home-light-btn power-toggle" type="button" data-dashboard-action="set-home-light-mode" data-mode="night">
          <span class="ui-icon-circle dashboard-home-mode-circle">${window.dashboardIconHtml("bedtime", "dashboard-home-mode-icon")}</span>
          <span>Night</span>
        </button>
        <button class="settings-item dashboard-home-light-btn power-toggle" type="button" data-dashboard-action="set-home-light-mode" data-mode="away">
          <span class="ui-icon-circle dashboard-home-mode-circle">${window.dashboardIconHtml("directions_walk", "dashboard-home-mode-icon")}</span>
          <span>Away</span>
        </button>
      </div>
    </section>

    <section class="dashboard-home-card dashboard-home-arm-section">
      <div class="dashboard-home-section-head dashboard-home-section-head-with-action">
        <h2 class="dashboard-home-section-title">Security</h2>
      </div>

      <div class="dashboard-home-arm-row">
        <button class="settings-item dashboard-home-arm-btn power-toggle" type="button" data-dashboard-action="set-home-arm-mode" data-mode="day">
          <span class="ui-icon-circle dashboard-home-mode-circle">${window.dashboardIconHtml("wb_sunny", "dashboard-home-mode-icon")}</span>
          <span>At Home</span>
        </button>
        <button class="settings-item dashboard-home-arm-btn power-toggle" type="button" data-dashboard-action="set-home-arm-mode" data-mode="night">
          <span class="ui-icon-circle dashboard-home-mode-circle">${window.dashboardIconHtml("bedtime", "dashboard-home-mode-icon")}</span>
          <span>Asleep</span>
        </button>
        <button class="settings-item dashboard-home-arm-btn power-toggle" type="button" data-dashboard-action="set-home-arm-mode" data-mode="away">
          <span class="ui-icon-circle dashboard-home-mode-circle">${window.dashboardIconHtml("directions_walk", "dashboard-home-mode-icon")}</span>
          <span>Away</span>
        </button>
      </div>
    </section>
  `;

  if (homeControls.__dashboardHomeControlsMarkup !== homeControlsMarkup) {
    homeControls.innerHTML = homeControlsMarkup;
    homeControls.__dashboardHomeControlsMarkup = homeControlsMarkup;
  }

  if (!syncDashboardHomeFoundSection(homeControls, S.currentClients || [])) {
    setTimeout(() => {
      syncDashboardHomeFoundSection(homeControls, S.currentClients || []);
    }, 0);
  }

  syncDashboardPageHeader(clientContainer);

  Array.from(clientContainer.children).forEach(child => {
    if (child !== home) child.remove();
  });

  window.syncDashboardValueSlots?.(homeControls.querySelector(":scope > .dashboard-home-environment-section") || homeControls);
  dashboardSyncHomeModeButtons();
};

window.renderSensorRow = function (label, value) {
  return `
    <div class="sensor-modal-label">${esc(label)}</div>
    <div class="sensor-modal-value">${esc(value || "—")}</div>
  `;
};

window.renderBattery = function (pct, hoverText = "") {
  const numericLevel = Number(pct);
  const hasLevel = (
    pct !== undefined &&
    pct !== null &&
    pct !== "" &&
    Number.isFinite(numericLevel)
  );
  const level = hasLevel ? Math.max(0, Math.min(100, numericLevel)) : 0;
  const colorClass = hasLevel ? (level < 20 ? "danger" : (level < 50 ? "warning" : "")) : "";
  const placeholderClass = hasLevel ? "" : " battery-placeholder";
  const ariaHidden = hasLevel ? "false" : "true";
  const cleanHoverText = String(hoverText || "").trim() || (
    hasLevel ? dashboardDebugPercent(level) : ""
  );
  const hoverAttributes = cleanHoverText
    ? ` title="${escAttr(cleanHoverText)}" aria-label="${escAttr(cleanHoverText)}"`
    : "";

  return `
    <div class="battery-container${placeholderClass}" aria-hidden="${ariaHidden}"${hoverAttributes}>
      <div class="battery-icon-wrapper battery-vertical">
        <div class="battery-level ${colorClass}" style="height: ${level}%"></div>
      </div>
    </div>
  `;
};

window.updateContainer = function (containerId, clients, renderFunc) {
  const container = document.getElementById(containerId);
  const activeEl = document.activeElement;

  if (container.contains(activeEl) && activeEl.tagName === "INPUT") return;

  const existingIds = Array.from(container.children).map(c => c.dataset.deviceId);
  const newIds = clients.map(c => c.deviceID);

  existingIds.forEach(id => {
    if (!newIds.includes(id)) {
      const selectorID = CSS.escape(String(id || ""));
      const el = container.querySelector(`[data-device-id="${selectorID}"]`);

      if (el) el.remove();
    }
  });

  clients.forEach(c => {
    const selectorID = CSS.escape(String(c.deviceID || ""));
    let el = container.querySelector(`[data-device-id="${selectorID}"]`);
    if (!el) {
      let html = "";

      try {
        html = String(renderFunc(c) || "").trim();
      } catch (err) {
        console.warn("[dashboard-render] card render failed", c?.deviceID, err);
        return;
      }

      if (!html) return;

      const temp = document.createElement("div");
      temp.innerHTML = html;
      el = temp.firstElementChild;

      if (!el) return;

      el.dataset.deviceId = c.deviceID;
      window.syncClientDebugArea?.(el, c);
      container.appendChild(el);
    } else {
      updateCard(el, c);
    }
  });
};

window.updateCard = function (el, c) {
  const activeEl = document.activeElement;

  if (
    activeEl &&
    el.contains(activeEl) &&
    (
      activeEl.tagName === "INPUT" ||
      activeEl.tagName === "TEXTAREA" ||
      activeEl.tagName === "SELECT" ||
      activeEl.isContentEditable
    )
  ) {
    return;
  }

  const effectiveStale = typeof window.dashboardEffectiveClientStale === "function"
    ? window.dashboardEffectiveClientStale(c)
    : !!c.stale;

  c = { ...c, stale: effectiveStale };
  el.classList.toggle("stale-client", effectiveStale);

  const tapoVideo = el.querySelector("video.tapo-camera-video");

  if (!tapoVideo) {
    const img = el.querySelector("img.camera-preview");

    if (img) {
      const previewUrl = typeof window.dashboardCameraPreviewUrl === "function"
        ? window.dashboardCameraPreviewUrl(c)
        : String(c.latest_frame_url || "").trim();
      const previewBaseUrl = String(c.latest_frame_url || "").trim();

      if (previewUrl) {
        if (img.dataset.previewBaseUrl !== previewBaseUrl || img.dataset.src !== previewUrl) {
          img.dataset.previewBaseUrl = previewBaseUrl;
          img.dataset.src = previewUrl;
          img.src = previewUrl;
        }

        img.loading = "eager";
        img.decoding = "async";
        img.fetchPriority = "high";
        img.style.display = "block";
      } else {
        img.dataset.previewBaseUrl = "";
        img.dataset.src = "";
        img.removeAttribute("src");
        img.style.display = "none";
      }

      img.style.width = "100%";
      img.style.height = "auto";
      img.style.maxWidth = "100%";
      img.style.maxHeight = "none";
    }
  }

  const statusText = c.stale
    ? "UNKNOWN"
    : (c.calibrating ? "CALIBRATING..." : (c.door_status || "unknown").toUpperCase());

  const doorOpenScore = Number(c.openness_score || 0).toFixed(2);
  const doorStatusText = `${statusText} (${doorOpenScore})`;

  const cardKind = el.dataset.nodeCard || "";
  const isTapoCameraCard = !!tapoVideo;
  const isCameraCard = isTapoCameraCard || cardKind === "camera" || !!el.querySelector(".camera-preview");
  const isDoorCard = cardKind === "door";
  const isMotionCard = cardKind === "motion";

  const files = S.currentVideosByDeviceId[c.deviceID] || [];
  const latestVideo = files[0] || null;

  const cameraStatusText = isTapoCameraCard
    ? (c.stale ? "UNKNOWN" : (c.preview_requested ? "ONLINE" : "IDLE"))
    : (c.stale ? "UNKNOWN" : (c.frame_live ? "ONLINE" : "NO FEED"));
  const motionEnabled = dashboardBool(c.motion_detection_enabled ?? c.motionDetectionEnabled) === true;
  const motionActive = dashboardBool(c.visual_motion_active ?? c.motion_active ?? c.motionActive) === true;
  const cameraMotionActive = motionEnabled && motionActive;
  const motionStatusText = c.stale
    ? "UNKNOWN"
    : !motionEnabled
      ? "DISABLED"
      : cameraMotionActive
        ? "MOTION"
        : "CLEAR";

  const cameraLastUpdateText = isCameraCard && !isTapoCameraCard
    ? (c.frame_live
        ? (Number(c.frame_age || 0) < 2 ? "now" : `${Math.round(Number(c.frame_age || 0))}s ago`)
        : formatLastUpdateText(c.last_update)
      )
    : formatLastUpdateText(c.last_update);

  const heartbeatMs = Number(c.heartbeat_interval_ms || 30000);
  const heartbeatSec = `${Math.round(heartbeatMs / 1000)}s`;
  const zoneName = c.zone_name || c.zoneName || "—";

  const sets = {
    ".battery-val": c.stale ? "" : (c.battery == null ? "—" : fmt(c.battery) + "%"),
    ".status-val": isCameraCard
      ? cameraStatusText
      : isDoorCard
        ? doorStatusText
        : isMotionCard
          ? motionStatusText
          : "",
    ".ip-val": c.ip || "—",
    ".id-val": c.deviceID || "—",
    ".brand-val": c.brand || "—",
    ".android-ver-val": c.androidVersion || "—",
    ".ver-val": c.version || "unknown",
    ".zone-val": zoneName,
    ".heartbeat-val": heartbeatSec,
    ".last-update-val": cameraLastUpdateText,
    ".video-count-val": String(files.length),
    ".latest-video-val": latestVideo ? latestVideo.name : "—",
    ".storage-used-val": fmtBytes(S.currentVideoStorage?.used ?? 0),
    ".storage-free-val": fmtBytes(S.currentVideoStorage?.free ?? 0)
  };

  for (const [sel, val] of Object.entries(sets)) {
    const target = el.querySelector(sel);
    if (target && target.textContent !== val) target.textContent = val;
  }

  let batteryLevel = el.querySelector(".battery-level");
  const batteryPct = dashboardBatteryIconValue(c);
  const batteryHoverText = dashboardBatteryHoverText(c);
  const shouldReserveBatterySlot = dashboardBatteryIsMatter(c) && isDoorCard;

  if (!batteryLevel && (Number.isFinite(batteryPct) || shouldReserveBatterySlot) && typeof window.renderBattery === "function") {
    const actions = el.querySelector(".card-actions");

    if (actions) {
      actions.insertAdjacentHTML(
        "afterbegin",
        window.renderBattery(batteryPct, batteryHoverText)
      );
      batteryLevel = el.querySelector(".battery-level");
    }
  }

  const batteryContainer = batteryLevel?.closest(".battery-container");

  if (batteryContainer) {
    if (batteryHoverText) {
      batteryContainer.title = batteryHoverText;
      batteryContainer.setAttribute("aria-label", batteryHoverText);
    } else {
      batteryContainer.removeAttribute("title");
      batteryContainer.removeAttribute("aria-label");
    }
  }

  if (batteryLevel && Number.isFinite(batteryPct)) {
    const clampedBatteryPct = Math.max(0, Math.min(100, batteryPct));

    batteryContainer?.classList.remove("battery-placeholder");
    batteryContainer?.setAttribute("aria-hidden", "false");
    batteryLevel.style.height = `${clampedBatteryPct}%`;
    batteryLevel.classList.toggle("danger", clampedBatteryPct < 20);
    batteryLevel.classList.toggle("warning", clampedBatteryPct >= 20 && clampedBatteryPct < 50);
  } else if (batteryLevel && !Number.isFinite(batteryPct)) {
    if (shouldReserveBatterySlot) {
      batteryContainer?.classList.add("battery-placeholder");
      batteryContainer?.setAttribute("aria-hidden", "true");
      batteryLevel.style.height = "0%";
      batteryLevel.classList.remove("danger", "warning");
    } else {
      batteryContainer?.remove();
    }
  }

  const camIcon = el.querySelector(".status-cam");

  if (camIcon && isCameraCard) {
    camIcon.classList.remove("stale", "green", "orange-blink", "no-feed", "security-active");
    camIcon.classList.add(
      c.stale ? "stale" : (isTapoCameraCard ? (c.preview_requested ? "green" : "no-feed") : (c.frame_live ? "green" : "no-feed"))
    );
    camIcon.classList.toggle("security-active", !c.stale && cameraMotionActive);
  }

  const motionIcon = el.querySelector(".status-motion");

  if (motionIcon && isMotionCard) {
    const visibleMotionActive = !c.stale && cameraMotionActive;

    motionIcon.classList.remove("stale", "green", "security-active");
    motionIcon.classList.add(c.stale ? "stale" : "green");
    motionIcon.classList.toggle("security-active", visibleMotionActive);
  }

  const doorIcon = el.querySelector(".status-door");

  if (doorIcon && isDoorCard) {
    const matterKinds = Array.isArray(c.matter_kinds) ? c.matter_kinds : [c.matter_kind];
    const isMatterMotionCard = window.dashboardClientIsMatter?.(c) === true && matterKinds.some(kind => String(kind || "").trim().toLowerCase() === "motion");

    if (doorIcon.parentElement) {
      doorIcon.parentElement.style.overflow = isMatterMotionCard ? "visible" : "";
    }

    const isMatterContactCard = window.dashboardClientIsMatter?.(c) === true && matterKinds.some(kind => String(kind || "").trim().toLowerCase() === "contact");
    const occupancy = Number(c.occupancy_state_value);
    const matterMotionActive = dashboardBool(c.motion_active) ?? (Number.isFinite(occupancy) ? Boolean(occupancy & 1) : false);
    const matterContactOpen = dashboardBool(c.contact_open) ?? dashboardBool(c.contact_state_value);
    const doorOpen = String(c.door_status || "").trim().toLowerCase() === "open" || (isMatterContactCard && matterContactOpen === true);
    const securityActive = isMatterMotionCard ? matterMotionActive : doorOpen;

    doorIcon.classList.remove("stale", "green", "orange-blink", "mint-blue-flash", "security-active");

    const doorStatusClass = c.stale
      ? "stale"
      : (c.calibrating
          ? "mint-blue-flash"
          : "green"
        );

    doorIcon.classList.add(doorStatusClass);
    doorIcon.classList.toggle("security-active", !c.stale && !c.calibrating && securityActive);

    window.setDashboardIcon(
      doorIcon,
      isMatterMotionCard
        ? "motion_sensor_active"
        : isMatterContactCard
          ? "door_front"
          : doorOpen
            ? "door_open"
            : "door_front"
    );
  }

  const switchCameraBtn = el.querySelector(".switch-camera-btn");
  if (switchCameraBtn && isCameraCard) {
    const selectedCamera = String(c.selected_camera || c.selectedCamera || "back").toLowerCase();
    const switchCameraHint = selectedCamera === "front"
      ? "Switch to Back Camera"
      : "Switch to Front Camera";

    switchCameraBtn.textContent = switchCameraHint;
    setDashboardButtonHint(switchCameraBtn, switchCameraHint);
  }

  const recordBtn = el.querySelector(".camera-record-btn, .tapo-camera-record-btn");
  const isRecording = isTapoCameraCard
    ? !!(c.tapo_recording_enabled || c.tapo_recording)
    : !!c.recording_enabled;

  const motionBtn = el.querySelector(".camera-motion-btn");

  if (motionBtn && isCameraCard && !isTapoCameraCard) {
    motionBtn.dataset.nextVal = motionEnabled ? "0" : "1";
    setDashboardButtonHint(
      motionBtn,
      motionEnabled ? "Disable Motion Detection" : "Enable Motion Detection"
    );
    motionBtn.classList.toggle("active", motionEnabled);
    motionBtn.setAttribute("aria-pressed", motionEnabled ? "true" : "false");
    motionBtn.classList.toggle("motion-active", cameraMotionActive);
  }

  window.setDashboardIcon(
    motionBtn?.querySelector(".koti-icon"),
    cameraMotionActive ? "motion_sensor_active" : "motion_sensor_idle"
  );

  if (recordBtn && isCameraCard) {
    if (isTapoCameraCard) {
      recordBtn.dataset.recording = isRecording ? "1" : "0";
    } else {
      recordBtn.dataset.nextVal = isRecording ? "0" : "1";
    }

    setDashboardButtonHint(recordBtn, isRecording ? "Stop Recording" : "Start Recording");
    recordBtn.classList.toggle("active", isRecording);
    recordBtn.setAttribute("aria-pressed", isRecording ? "true" : "false");
  }

  const talkBtn = el.querySelector(".camera-talk-btn");
  if (talkBtn) {
    setDashboardButtonHint(
      talkBtn,
      talkBtn.classList.contains("active") ? "Stop Talking" : "Start Talking"
    );
  }

  el.querySelectorAll('button.icon-menu, button[data-dashboard-action="open-client-menu"]').forEach(button => {
    if (button.matches(".camera-record-btn, .tapo-camera-record-btn, .camera-motion-btn, .camera-talk-btn")) return;

    setDashboardButtonHint(button, "Open Settings");
  });

  el.querySelectorAll("button").forEach(button => {
    const hint =
      button.getAttribute("aria-label") ||
      button.title ||
      button.textContent;

    if (String(hint || "").trim()) {
      setDashboardButtonHint(button, hint);
    }
  });

  window.syncMatterCardEnvironment?.(el, c);
  window.syncClientDebugArea?.(el, c);
};

function dashboardBool(value) {
  if (value === true || value === 1) return true;
  if (value === false || value === 0) return false;

  const clean = String(value ?? "").trim().toLowerCase();
  if (["true", "1", "yes", "on", "enabled"].includes(clean)) return true;
  if (["false", "0", "no", "off", "disabled"].includes(clean)) return false;

  return null;
}

function dashboardTapoChildID(child, index = 0) {
  return String(
    child?.id
    ?? child?.device_id
    ?? child?.deviceId
    ?? child?.child_id
    ?? child?.childId
    ?? child?.position
    ?? child?.index
    ?? index + 1
  ).trim();
}

function dashboardTapoChildName(child, index = 0, parent = null) {
  const position = String(child?.position ?? child?.index ?? index + 1).trim() || String(index + 1);
  const rawName = String(
    child?.alias
    ?? child?.nickname
    ?? child?.name
    ?? `Outlet ${position}`
  ).trim();
  const parentName = String(
    parent?.clientName
    ?? parent?.tapo_alias
    ?? parent?.name
    ?? parent?.tapo_model
    ?? "Tapo Extender"
  ).trim() || "Tapo Extender";

  if (/^(tapo\s*)?p306[_\s-]*\d+$/i.test(rawName) || /^outlet\s+\d+$/i.test(rawName)) {
    return `Extender ${parentName} ${position}`;
  }

  return rawName || `Extender ${parentName} ${position}`;
}

function dashboardTapoChildLooksLikeLight(child) {
  const text = String([
    child?.kind,
    child?.type,
    child?.category,
    child?.component,
    child?.alias,
    child?.nickname,
    child?.name
  ].filter(Boolean).join(" ")).toLowerCase();

  return /night\s*light|nightlight|\blight\b|\bled\b/.test(text);
}

function dashboardTapoRoomPowerEnabled(client, defaultEnabled = false) {
  const raw = client?.tapo_room_power ?? client?.tapoRoomPower ?? client?.room_power ?? client?.include_in_room_power;

  if (raw === undefined || raw === null || raw === "") {
    return defaultEnabled;
  }

  return dashboardBool(raw) === true;
}

function dashboardTapoIsLightControl(client) {
  return (
    client?.tapo_is_bulb ||
    client?.tapo_kind === "bulb" ||
    client?.tapo_kind === "lightstrip"
  );
}

function dashboardTapoExplicitlyHidden(client) {
  const raw = client?.tapo_hide_dashboard
    ?? client?.tapoHideDashboard
    ?? client?.tapo_dashboard_hidden
    ?? client?.dashboard_hidden
    ?? client?.hide_dashboard;

  return dashboardBool(raw) === true;
}

// Controls and room settings must use this exact shared hide decision so one
// physical device cannot be classified as both dashboard-visible and hidden.
window.dashboardTapoExplicitlyHidden = dashboardTapoExplicitlyHidden;

function dashboardTapoHideIndividualCard(client) {
  if (dashboardTapoExplicitlyHidden(client)) return true;

  return dashboardTapoRoomPowerEnabled(client, dashboardTapoIsLightControl(client));
}

function dashboardRemoveHiddenTapoCards(clients = []) {
  const hiddenIDs = new Set(
    (clients || [])
      .filter(client => client?.provisioned && hasClientRole(client, "TAPO"))
      .filter(dashboardTapoExplicitlyHidden)
      .map(client => String(client.deviceID || "").trim())
      .filter(Boolean)
  );

  if (!hiddenIDs.size) return;

  document.querySelectorAll('#clientCards [data-node-card="tapo"]').forEach(card => {
    const cardID = String(card.dataset.deviceId || "").trim();

    if (hiddenIDs.has(cardID)) {
      card.remove();
    }
  });
}

function dashboardExpandTapoExtenderClients(clients = []) {
  const expanded = [];

  (clients || []).forEach(client => {
    const tapoKind = String(client?.tapo_kind || "").toLowerCase();
    const isExtender = tapoKind === "outlet_extender" || client?.tapo_is_outlet_extender === true;
    const children = Array.isArray(client?.tapo_children)
      ? client.tapo_children
      : Array.isArray(client?.children)
        ? client.children
        : [];

    if (!client?.provisioned || !isExtender || !children.length) {
      expanded.push(client);
      return;
    }

    children.forEach((child, index) => {
      if (!child || typeof child !== "object") return;

      const childID = dashboardTapoChildID(child, index);
      if (!childID) return;

      const childName = dashboardTapoChildName(child, index, client);
      const isLight = dashboardTapoChildLooksLikeLight(child);
      const childPower = dashboardBool(child.is_on ?? child.device_on ?? child.on ?? child.state);
      const roomPowerRaw = child.tapo_room_power ?? child.room_power ?? child.include_in_room_power;
      const roomPower = roomPowerRaw === undefined || roomPowerRaw === null || roomPowerRaw === ""
        ? isLight
        : dashboardBool(roomPowerRaw) === true;
      const hideRaw = child.tapo_hide_dashboard
        ?? child.tapoHideDashboard
        ?? child.tapo_dashboard_hidden
        ?? child.dashboard_hidden
        ?? child.hide_dashboard;
      const childZone = String(
        client.zone_name
        ?? client.room
        ?? client.room_name
        ?? client.zone
        ?? child.zone_name
        ?? child.room
        ?? child.room_name
        ?? child.zone
        ?? ""
      ).trim();

      expanded.push({
        ...client,
        deviceID: `${client.deviceID}::${childID}`,
        clientName: childName,
        tapo_alias: childName,
        zone_name: childZone,
        room: childZone,
        room_name: childZone,
        tapo_kind: isLight ? "bulb" : "plug",
        tapo_is_bulb: isLight,
        tapo_is_plug: !isLight,
        tapo_is_outlet_extender: false,
        tapo_is_outlet_child: true,
        tapo_parent_device_id: client.deviceID || "",
        tapo_parent_name: client.clientName || client.tapo_alias || client.tapo_model || "Tapo Extender",
        tapo_child_id: childID,
        tapo_child_index: child.cli_index ?? child.index ?? index,
        tapo_child_position: child.position ?? "",
        tapo_child_name: childName,
        tapo_children: [],
        children: [],
        tapo_is_on: childPower,
        is_on: childPower,
        device_on: childPower,
        state: childPower,
        tapo_room_power: roomPower,
        tapo_hide_dashboard: dashboardBool(hideRaw) === true,
        tapo_supports_power: true,
        tapo_supports_brightness: false,
        tapo_supports_color_temp: false,
        tapo_supports_color: false,
        tapo_recharge_target_id: `${client.deviceID}|${childID}`
      });
    });
  });

  return expanded;
}

function dashboardPhysicalClients(clients = []) {
  const list = [...(clients || [])];

  // Matter intentionally keeps one client record per endpoint for telemetry.
  // Every device-facing UI must pass through this function so endpoints from
  // one physical device are never rendered or counted separately. A T310's
  // temperature and humidity endpoints are one device, not two sensors.
  return typeof window.dashboardGroupMatterClients === "function"
    ? window.dashboardGroupMatterClients(list)
    : list;
}

function dashboardClientCollections(clients = []) {
  const controlClients = [];
  const sensorClients = [];

  clients.forEach(c => {
    if (!c.provisioned) return;

    const deviceID = String(c.deviceID || "");
    const isMatterDevice =
      window.dashboardClientIsMatter?.(c) === true ||
      c?.source === "matter";
    const isMatterControl =
      window.dashboardClientIsMatterActionOnly?.(c) === true;
    const isTapoDevice = hasClientRole(c, "TAPO");

    if (isMatterDevice) {
      if (isMatterControl) {
        controlClients.push({
          ...c,
          __dashboardCardID: `control:matter:${deviceID}`,
          __dashboardControlKind: "matter"
        });
      } else {
        sensorClients.push({
          ...c,
          __dashboardCardID: `sensor:matter:${deviceID}`,
          __dashboardSensorKind: "matter"
        });
      }

      return;
    }

    if (isTapoDevice) return;

    if (hasClientRole(c, "DSS")) {
      sensorClients.push({
        ...c,
        __dashboardCardID: `sensor:door:${deviceID}`,
        __dashboardSensorKind: "door"
      });
    }

    if (hasClientRole(c, "CAM")) {
      sensorClients.push({
        ...c,
        __dashboardCardID: `sensor:motion:${deviceID}`,
        __dashboardSensorKind: "android-motion"
      });
    }
  });

  const cameras = clients.filter(c =>
    c.provisioned && dashboardClientIsCamera(c)
  );

  const keyClients = clients.filter(c =>
    c.provisioned && hasClientRole(c, "KEY")
  );

  const tapoControlDevices = clients.filter(c => {
    if (
      !c.provisioned ||
      !hasClientRole(c, "TAPO") ||
      c.tapo_dashboard_section === "camera" ||
      dashboardTapoExplicitlyHidden(c)
    ) {
      return false;
    }

    const kind = String(
      c.tapo_kind || c.tapo_device_type || ""
    ).trim().toLowerCase();

    return (
      kind === "bulb" ||
      kind === "lightstrip" ||
      kind === "plug" ||
      kind === "outlet_extender" ||
      c.tapo_is_bulb === true ||
      c.tapo_is_plug === true ||
      c.tapo_is_outlet_extender === true
    );
  });

  return {
    controlClients,
    sensorClients,
    cameras,
    keyClients,
    tapoControlDevices
  };
}

function dashboardSensorDeviceCount(sensorClients = []) {
  return sensorClients.filter(
    client => client?.__dashboardSensorKind !== "android-motion"
  ).length;
}

window.dashboardClientCounts = function (clients = S.currentClients || []) {
  const physicalClients = dashboardPhysicalClients(clients);
  const {
    sensorClients,
    cameras,
    keyClients,
    tapoControlDevices
  } = dashboardClientCollections(physicalClients);

  return {
    clients: physicalClients.length,
    sensors: dashboardSensorDeviceCount(sensorClients),
    cameras: cameras.length,
    tapoControls: tapoControlDevices.length,
    keys: keyClients.length
  };
};

function dashboardRegistryClientName(c) {
  return String(
    c?.clientName ||
    c?.tapo_alias ||
    c?.matter_node_label ||
    c?.matter_product_name ||
    c?.deviceID ||
    "Unknown Client"
  ).trim();
}

function dashboardRegistryClientType(c) {
  return window.dashboardDeviceTypeName(c);
}

function dashboardRegistryClientIcon(c) {
  return window.dashboardDeviceIconName(c);
}

function dashboardRenderRegistryClientCard(c, groupByRoom) {
  const deviceID = String(c?.deviceID || "");
  const name = dashboardRegistryClientName(c);
  const type = dashboardRegistryClientType(c);
  const room = clientRoomName(c);
  const subtitle = groupByRoom ? type : room;
  const icon = dashboardRegistryClientIcon(c);
  const [debugKind, debugRows] = dashboardClientDebugRows(c, null);
  const debugHidden = document.body.dataset.cardDebug === "off";

  return `
    <article
      class="modal-device-card card ${c?.stale ? "stale-client" : ""}"
      data-device-id="${escAttr(deviceID)}"
      data-dashboard-client-card
    >
      <div class="modal-device-card-head card-head">
        <div class="modal-device-card-identity status-area">
          ${window.dashboardIconHtml(icon, "icon-glow")}

          <div class="modal-device-card-copy card-title-group">
            <div class="modal-device-card-title card-title">${esc(name)}</div>
            <div class="modal-device-card-label card-type-label">${esc(subtitle)}</div>
          </div>
        </div>

        <div class="modal-device-card-actions card-actions">
          <button
            class="icon-menu"
            type="button"
            title="Open settings for ${escAttr(name)}"
            aria-label="Open settings for ${escAttr(name)}"
            data-dashboard-action="open-dashboard-client-settings"
            data-device-id="${escAttr(deviceID)}"
          >
            ${window.dashboardIconHtml("more_vert")}
          </button>
        </div>
      </div>

      <div
        class="debug-area"
        data-debug-kind="${escAttr(debugKind)}"
        ${debugHidden ? "hidden" : ""}
      >
        ${dashboardDebugRowsHtml(debugRows)}
      </div>
    </article>
  `;
}

function dashboardRegistryGroupHtml(label, clients, groupByRoom) {
  const listClass = groupByRoom
    ? "room-settings-device-list"
    : "modal-device-card-grid";

  return `
    <section
      class="settings-server-card"
      data-dashboard-client-group
      data-group-label="${escAttr(label)}"
    >
      <h2 class="modal-section-title">${esc(label)}</h2>

      <div class="${listClass}">
        ${clients
          .map(client =>
            dashboardRenderRegistryClientCard(client, groupByRoom)
          )
          .join("")}
      </div>
    </section>
  `;
}

window.setDashboardClientGrouping = function (mode) {
  S.clientRegistryGroupByRoom = String(mode || "").trim() !== "device";
  window.renderDashboardClientsModal?.(S.currentClients || []);
};

window.renderDashboardClientsModal = function (
  clients = S.currentClients || []
) {
  const container = document.getElementById("dashboardClientsModalBody");
  if (!container) return;

  const groupByRoom = S.clientRegistryGroupByRoom !== false;
  const physicalClients = dashboardPhysicalClients(clients);
  const foundClients = typeof window.dashboardHomeFoundClients === "function"
    ? window.dashboardHomeFoundClients(clients)
    : [];
  const foundClientIDs = new Set(
    foundClients
      .flatMap(client => [
        client?.deviceID,
        ...(Array.isArray(client?.matter_device_ids)
          ? client.matter_device_ids
          : [])
      ])
      .map(deviceID => String(deviceID || "").trim())
      .filter(Boolean)
  );
  const registryClients = physicalClients.filter(client => {
    const clientIDs = [
      client?.deviceID,
      ...(Array.isArray(client?.matter_device_ids)
        ? client.matter_device_ids
        : [])
    ]
      .map(deviceID => String(deviceID || "").trim())
      .filter(Boolean);

    return !clientIDs.some(deviceID => foundClientIDs.has(deviceID));
  });
  const sortedClients = [...registryClients].sort((a, b) =>
    dashboardRegistryClientName(a).localeCompare(
      dashboardRegistryClientName(b),
      undefined,
      { sensitivity: "base" }
    )
  );
  const clientsByGroup = new Map();

  sortedClients.forEach(client => {
    let label = groupByRoom
      ? clientRoomName(client)
      : dashboardRegistryClientType(client);

    if (groupByRoom && label.toLowerCase() === "unassigned") {
      label = "Key Clients";
    }

    if (!clientsByGroup.has(label)) {
      clientsByGroup.set(label, []);
    }

    clientsByGroup.get(label).push(client);
  });

  const groups = [...clientsByGroup.entries()].sort(
    ([labelA], [labelB]) => {
      if (groupByRoom) {
        const aKeyClients = labelA.toLowerCase() === "key clients";
        const bKeyClients = labelB.toLowerCase() === "key clients";

        if (aKeyClients !== bKeyClients) {
          return aKeyClients ? -1 : 1;
        }
      }

      return labelA.localeCompare(labelB, undefined, {
        sensitivity: "base"
      });
    }
  );
  const count = document.querySelector(
    "#dashboardClientsModal [data-dashboard-client-count]"
  );

  if (count) {
    count.textContent = `${physicalClients.length} total`;
  }

  const foundSectionHtml = typeof window.renderMatterFoundHomeSection === "function"
    ? window.renderMatterFoundHomeSection(clients)
    : "";

  container.innerHTML = `
    ${foundSectionHtml}

    <section class="modal-section">
      <div class="settings-actions" aria-label="Group devices">
        <button
          class="settings-item ${groupByRoom ? "active" : ""}"
          type="button"
          aria-pressed="${groupByRoom ? "true" : "false"}"
          data-dashboard-action="set-dashboard-client-grouping"
          data-group-mode="room"
        >
          ${window.dashboardIconHtml("view_column")}
          <span>Group by Room</span>
        </button>

        <button
          class="settings-item ${groupByRoom ? "" : "active"}"
          type="button"
          aria-pressed="${groupByRoom ? "false" : "true"}"
          data-dashboard-action="set-dashboard-client-grouping"
          data-group-mode="device"
        >
          ${window.dashboardIconHtml("koti-fa-network-wired")}
          <span>Group by Device</span>
        </button>
      </div>
    </section>

    ${groups
      .map(([label, groupClients]) =>
        dashboardRegistryGroupHtml(
          label,
          groupClients,
          groupByRoom
        )
      )
      .join("")}

    <div
      class="modal-subtitle"
      data-dashboard-client-empty
      ${physicalClients.length ? "hidden" : ""}
    >
      No devices found.
    </div>
  `;
};

window.render = function (data) {
  const dashboardRenderStartedAt = window.dashboardLoadProfiler?.now?.();

  data = data || {};
  const rawClients = (data.clients || []).map(c => (
    typeof window.normalizeClient === "function" ? window.normalizeClient(c) : c
  ));
  const clients = dashboardExpandTapoExtenderClients(rawClients);

  if (!S.activeView) S.activeView = "dashboard";

  S.currentClients = clients;
  dashboardRemoveHiddenTapoCards(clients);

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

  if (data.environment && typeof data.environment === "object") {
    if (typeof window.dashboardSetEnvironmentState === "function") {
      window.dashboardSetEnvironmentState(data.environment);
    } else {
      S.environmentState = data.environment;
    }
  }

  S.currentUsedZones = data.used_zones || S.currentUsedZones || [];

  dashboardSyncHomeDiscoveryAttention(clients);
  renderDashboardAside();

  window.syncSettingsSystemSummaries?.();

  if (document.getElementById("dashboardClientsModal")?.hidden === false) {
    window.renderDashboardClientsModal?.(clients);
  }

  if (typeof updateOpenSensorModal === "function") {
    updateOpenSensorModal();
  }

  const {
    controlClients,
    sensorClients,
    cameras,
    keyClients,
    tapoControlDevices
  } = dashboardClientCollections(clients);

  const tapoBulbs = tapoControlDevices.filter(c => (
    c.tapo_kind === "bulb" ||
    c.tapo_kind === "lightstrip" ||
    c.tapo_is_bulb
  ));

  const tapoPlugs = tapoControlDevices.filter(c =>
    !tapoBulbs.includes(c)
  );

  const pageMode = cleanDashboardPage?.(S.activeDashboardPage) || "home";
  const renderControls = pageMode === "controls";
  const renderMonitors = pageMode === "monitor";
  const renderSensors = pageMode === "sensors";
  const renderHomepage = pageMode === "home";

  S.renderHomepage = renderHomepage;
  S.renderControls = renderControls;
  S.renderMonitors = renderMonitors;
  S.renderSensors = renderSensors;

  const visibleControlClients = renderControls
    ? controlClients.filter(dashboardClientHasAssignedRoom)
    : [];

  const visibleSensorClients = renderSensors
    ? sensorClients.filter(dashboardClientHasAssignedRoom)
    : [];

  const visibleCameras = renderMonitors
    ? cameras.filter(dashboardClientHasAssignedRoom)
    : [];

  const visibleTapoPlugs = renderControls
    ? tapoPlugs.filter(dashboardClientHasAssignedRoom)
    : [];

  const visibleTapoBulbs = renderControls
    ? tapoBulbs.filter(dashboardClientHasAssignedRoom)
    : [];

  document.body.dataset.dashboardPage = pageMode;
  document.body.dataset.dashboardRender = window.dashboardRenderModeName?.(pageMode) || pageMode;
  document.body.removeAttribute("data-render-controls");
  document.body.removeAttribute("data-render-monitors");
  document.body.removeAttribute("data-render-sensors");

  if (S.activeView === "debug") {
    document.getElementById("sectionClients").style.display = "none";
    document.getElementById("sectionEmpty").style.display = "none";
    document.getElementById("sectionLog").style.display = "";
    dashboardUpdatePreviewViewerState([]);
    dashboardApplyCardDebugVisibility();
    window.dashboardLoadMeasure?.("render dashboard debug view", dashboardRenderStartedAt, {
      clients: clients.length
    });
    return;
  }

  const hasVisibleDashboardContent = (
    renderHomepage ||
    visibleControlClients.length ||
    visibleSensorClients.length ||
    visibleCameras.length ||
    visibleTapoPlugs.length ||
    visibleTapoBulbs.length
  );
  const emptySection = document.getElementById("sectionEmpty");

  document.getElementById("sectionClients").style.display = hasVisibleDashboardContent ? "" : "none";

  if (emptySection) {
    emptySection.textContent = renderControls
      ? "No controls assigned."
      : renderMonitors
        ? "No monitors assigned."
        : "No sensors assigned.";
    emptySection.style.display = hasVisibleDashboardContent ? "none" : "";
  }

  document.getElementById("sectionLog").style.display = "none";

  const cameraClientsEl = document.getElementById("cameraClients");
  if (cameraClientsEl) {
    cameraClientsEl.innerHTML = "";
  }

  if (renderHomepage) {
    renderDashboardHome();
  } else {
    renderGroupedDashboard({
      controlClients: visibleControlClients,
      sensorClients: visibleSensorClients,
      cameras: visibleCameras,
      tapoPlugs: visibleTapoPlugs,
      tapoBulbs: visibleTapoBulbs
    });
  }

  if (!renderHomepage) {
    dashboardApplyColumnBuilderLayoutVars();
    syncNonPortraitCameraHeaders(document);
    dashboardUpdatePreviewViewerState(visibleCameras);
    window.initTapoCameraVideos?.();
  }

  dashboardApplyCardDebugVisibility();
  window.dashboardLoadMeasure?.("render dashboard page", dashboardRenderStartedAt, {
    page: pageMode,
    registryClients: rawClients.length,
    renderedDevices: clients.length,
    sensors: dashboardSensorDeviceCount(sensorClients),
    cameras: cameras.length,
    tapoControls: tapoControlDevices.length,
    keys: keyClients.length
  });
};

function dashboardApkVersionParts(apk) {
  return String(apk?.version || "")
    .split(".")
    .map(part => Number.parseInt(part, 10))
    .filter(part => Number.isFinite(part));
}

function dashboardCompareApkVersions(a, b) {
  const av = dashboardApkVersionParts(a);
  const bv = dashboardApkVersionParts(b);
  const len = Math.max(av.length, bv.length);

  for (let i = 0; i < len; i += 1) {
    const ai = av[i] || 0;
    const bi = bv[i] || 0;

    if (ai !== bi) return ai - bi;
  }

  return Number(a?.modified || 0) - Number(b?.modified || 0);
}

function dashboardLatestApk(kind) {
  const cleanKind = String(kind || "").trim().toLowerCase();
  const apks = (S.fileServerApks || [])
    .filter(apk => String(apk?.kind || "").trim().toLowerCase() === cleanKind)
    .filter(apk => String(apk?.url || apk?.download_url || "").trim());

  if (!apks.length) return null;

  return apks.sort((a, b) => dashboardCompareApkVersions(b, a))[0];
}

function dashboardApkDownloadItem(kind, icon, label) {
  const apk = dashboardLatestApk(kind);
  const href = String(apk?.url || apk?.download_url || "").trim();
  const version = String(apk?.version || "").trim();
  const versionLabel = version ? `v${version}` : "—";

  if (!href) {
    return `
      <span class="settings-item settings-row" aria-disabled="true">
        ${window.dashboardIconHtml(icon)}
        <span>${esc(label)}</span>
        <span class="settings-row-value">${esc(versionLabel)}</span>
      </span>
    `;
  }

  return `
    <a class="settings-item settings-row" href="${escAttr(href)}">
      ${window.dashboardIconHtml(icon)}
      <span>${esc(label)}</span>
      <span class="settings-row-value">${esc(versionLabel)}</span>
    </a>
  `;
}

function dashboardApkDownloadItemsHtml() {
  return [
    dashboardApkDownloadItem("home", "mobile_screen", "Home Client"),
    dashboardApkDownloadItem("key", "key", "Key Client")
  ].join("");
}

window.syncSettingsApkDownloads = function () {
  const container = document.getElementById("settingsApkDownloads");
  if (!container) return;

  container.innerHTML = dashboardApkDownloadItemsHtml();
};

window.ensureSettingsModal = function () {
  if (document.getElementById("settingsModal")) return;

  document.body.insertAdjacentHTML("beforeend", `
    <div id="settingsModal" class="modal" hidden data-dashboard-modal="settings">
      <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="settingsModalTitle">
        <div class="modal-head">
          <h1 id="settingsModalTitle" class="modal-title">KotiBot System</h1>
          <button class="modal-close" type="button" aria-label="Close settings" data-dashboard-action="hide-settings">
            ${window.dashboardIconHtml("close")}
          </button>
        </div>

        <div class="modal-body">
          <section class="modal-section">
            <h2 class="modal-section-title">Dashboard View</h2>

            <div class="settings-list settings-control-grid">
              <button
                id="dashboardTextSizeToggle"
                class="settings-item settings-row"
                type="button"
                data-dashboard-action="toggle-dashboard-text-size"
              >
                ${window.dashboardIconHtml("format_size")}
                <span>Text Size</span>
                <span id="dashboardTextSizeToggleLabel" class="settings-row-value">Normal Text</span>
              </button>

              <button
                id="dashboardInfoToggle"
                class="settings-item settings-row"
                type="button"
                title="Show Info"
                aria-label="Show Info"
                data-dashboard-action="toggle-dashboard-info"
              >
                ${window.dashboardIconHtml("info")}
                <span>Client Info</span>
                <span id="dashboardInfoToggleLabel" class="settings-row-value">Show Info</span>
              </button>
            </div>
          </section>

          <section class="modal-section settings-narrow-section">
            <h2 class="modal-section-title">Automations</h2>

            <div class="settings-list settings-control-grid">
              <button
                class="settings-item settings-row"
                type="button"
                data-dashboard-action="show-home-lighting-settings"
              >
                ${window.dashboardIconHtml("auto_awesome")}
                <span>Scenes</span>
              </button>

              <button
                class="settings-item settings-row"
                type="button"
                data-dashboard-action="show-home-arming-settings"
              >
                ${window.dashboardIconHtml("security")}
                <span>Security</span>
              </button>
            </div>
          </section>

          <section class="modal-section settings-narrow-section settings-activity-section">
            <div class="settings-activity-head">
              <h2 class="modal-section-title">Recent Activity</h2>

              <button
                class="icon-menu"
                type="button"
                title="View all activity"
                aria-label="View all activity"
                data-dashboard-action="aside-show-activity"
              >
                ${window.dashboardIconHtml("more_vert")}
              </button>
            </div>

            <div id="settingsRecentActivity" class="dashboard-activity-list">
              ${dashboardSettingsActivityItemsHtml()}
            </div>
          </section>

          <section class="modal-section">
            <h2 class="modal-section-title">System</h2>

            <div class="settings-list settings-control-grid">
              <button
                class="settings-item settings-row"
                type="button"
                data-dashboard-action="show-dashboard-users-settings"
              >
                ${window.dashboardIconHtml("manage_accounts")}
                <span>Accounts</span>
              </button>

              <button
                class="settings-item settings-row"
                type="button"
                data-dashboard-action="show-bluetooth-settings"
              >
                ${window.dashboardIconHtml("bluetooth")}
                <span>Bluetooth</span>
                <span id="settingsBluetoothSummary" class="settings-row-value">Unknown</span>
              </button>

              <button
                class="settings-item settings-row settings-system-wide settings-clients-row"
                type="button"
                aria-label="Devices. Sensors: 0; Cameras: 0; Tapo Controls: 0; Keys: 0"
                data-dashboard-action="show-dashboard-clients-modal"
              >
                ${window.dashboardIconHtml("koti-fa-network-wired")}
                <span>Devices</span>
                <span id="settingsClientsSummary" class="settings-row-value">
                  <span title="Sensors">
                    ${window.dashboardIconHtml("sensors")}
                    <span>0</span>
                  </span>
                  <span title="Cameras">
                    ${window.dashboardIconHtml("videocam")}
                    <span>0</span>
                  </span>
                  <span title="Tapo Controls">
                    ${window.dashboardIconHtml("toggle_on")}
                    <span>0</span>
                  </span>
                  <span title="Keys">
                    ${window.dashboardIconHtml("key")}
                    <span>0</span>
                  </span>
                </span>
              </button>

              <button
                class="settings-item settings-row settings-system-wide"
                type="button"
                data-dashboard-action="show-dashboard-matter-settings"
              >
                ${window.dashboardIconHtml("matter")}
                <span>Matter</span>
                <span id="settingsMatterSummary" class="settings-row-value">No connection</span>
              </button>
            </div>
          </section>

          <section class="modal-section">
            <h2 class="modal-section-title">Downloads</h2>

            <div id="settingsApkDownloads" class="settings-list settings-control-grid">
              ${dashboardApkDownloadItemsHtml()}
            </div>
          </section>

          <section class="modal-section">
            <h2 class="modal-section-title">Server</h2>

            <div class="settings-server-grid">
              <div class="settings-server-summary">
                <span class="settings-server-summary-row">
                  <span class="settings-server-summary-label">Uptime</span>
                  <span id="settingsServerUptime">—</span>
                </span>

                <span class="settings-server-summary-row">
                  <span class="settings-server-summary-label">IP</span>
                  <span id="settingsServerIp">—</span>
                </span>
              </div>

              <button
                class="settings-item settings-server-restart danger"
                type="button"
                data-dashboard-action="restart-server"
              >
                ${window.dashboardIconHtml("restart_alt")}
                <span>Restart Server</span>
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>

    <div id="dashboardClientsModal" class="modal" hidden data-dashboard-modal="settings-clients">
      <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="dashboardClientsModalTitle">
        <div class="modal-head">
          <div class="modal-title-wrap">
            <h1 id="dashboardClientsModalTitle" class="modal-title">
              Devices
            </h1>
            <div class="modal-subtitle" data-dashboard-client-count>
              0 total
            </div>
          </div>

          <button
            class="modal-close"
            type="button"
            aria-label="Close Devices"
            data-dashboard-action="hide-dashboard-clients-modal"
          >
            ${window.dashboardIconHtml("close")}
          </button>
        </div>

        <div id="dashboardClientsModalBody" class="modal-body"></div>
      </div>
    </div>

    <div id="dashboardMatterSettingsModal" class="modal" hidden data-dashboard-modal="settings-matter">
      <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="dashboardMatterSettingsModalTitle">
        <div class="modal-head">
          <h1 id="dashboardMatterSettingsModalTitle" class="modal-title">Matter</h1>

          <button
            class="modal-close"
            type="button"
            aria-label="Close Matter settings"
            data-dashboard-action="hide-dashboard-matter-settings"
          >
            ${window.dashboardIconHtml("close")}
          </button>
        </div>

        <div class="modal-body">
          <div class="modal-section settings-server-section">
            <div class="settings-server-card-grid">
              <div class="settings-server-card settings-server-matter-card">
                <div class="settings-server-info settings-matter-info">
                  <div class="settings-server-info-row">
                    <span>Connection</span>
                    <span id="settingsMatterConnection" class="settings-server-info-value">—</span>
                  </div>

                  <div class="settings-server-info-row">
                    <span>Last Sync</span>
                    <span id="settingsMatterLastSync" class="settings-server-info-value">—</span>
                  </div>

                  <div class="settings-server-info-row">
                    <span>Node</span>
                    <span id="settingsMatterNode" class="settings-server-info-value">—</span>
                  </div>

                  <div class="settings-server-info-row">
                    <span>Endpoints</span>
                    <span id="settingsMatterEndpoints" class="settings-server-info-value">—</span>
                  </div>
                </div>

                <div id="settingsMatterStatus" class="settings-note" hidden></div>

                <div class="settings-actions settings-matter-actions">
                  <button
                    id="settingsMatterSyncButton"
                    class="settings-item"
                    type="button"
                    data-dashboard-action="sync-dashboard-matter"
                  >
                    ${window.dashboardIconHtml("restart_alt")}
                    <span>Sync Now</span>
                  </button>

                  <button
                    id="settingsMatterRecommissionButton"
                    class="settings-item danger"
                    type="button"
                    data-dashboard-action="show-dashboard-matter-recommission"
                  >
                    ${window.dashboardIconHtml("add_link")}
                    <span>Recommission H110</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div id="dashboardMatterRecommissionModal" class="modal" hidden data-dashboard-modal="settings-matter-recommission">
      <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="dashboardMatterRecommissionModalTitle">
        <div class="modal-head">
          <h1 id="dashboardMatterRecommissionModalTitle" class="modal-title settings-icon-modal-title">
            ${window.dashboardIconHtml("sensors")}
            <span>Recommission H110</span>
          </h1>

          <button
            class="modal-close"
            type="button"
            aria-label="Close Matter settings"
            data-dashboard-action="hide-dashboard-matter-recommission"
          >
            ${window.dashboardIconHtml("close")}
          </button>
        </div>

        <div class="modal-body">
          <div class="modal-section settings-server-section">
            <div class="settings-server-card settings-matter-recommission-card">
              <p class="settings-matter-recommission-copy">
                Generate a new Matter setup code for the H110 in the Tapo app. KotiBot will back up its current Matter controller storage before pairing again.
              </p>

              <label class="settings-field-row">
                <span class="settings-field-label">Matter setup code</span>

                <input
                  id="dashboardMatterSetupCode"
                  class="settings-input"
                  type="password"
                  inputmode="numeric"
                  autocomplete="off"
                  spellcheck="false"
                  data-dashboard-input="sync-dashboard-matter-recommission"
                />
              </label>

              <label class="settings-check-row settings-matter-confirm-row">
                <input
                  id="dashboardMatterRecommissionConfirm"
                  type="checkbox"
                  data-dashboard-change="sync-dashboard-matter-recommission"
                />

                <span>I have generated a new H110 Matter setup code and want to replace KotiBot’s current Matter connection.</span>
              </label>

              <div id="dashboardMatterRecommissionStatus" class="settings-note" hidden></div>

              <div class="settings-actions settings-server-actions">
                <button
                  class="settings-item"
                  type="button"
                  data-dashboard-action="hide-dashboard-matter-recommission"
                >
                  ${window.dashboardIconHtml("close")}
                  <span>Cancel</span>
                </button>

                <button
                  id="dashboardMatterRecommissionSubmit"
                  class="settings-item danger"
                  type="button"
                  data-dashboard-action="recommission-dashboard-matter"
                  disabled
                >
                  ${window.dashboardIconHtml("add_link")}
                  <span>Recommission H110</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div id="dashboardUsersSettingsModal" class="modal" hidden data-dashboard-modal="settings-users">
      <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="dashboardUsersSettingsModalTitle">
        <div class="modal-head">
          <h1 id="dashboardUsersSettingsModalTitle" class="modal-title settings-icon-modal-title">
            ${window.dashboardIconHtml("manage_accounts")}
            <span>User Accounts</span>
          </h1>
          <button class="modal-close" type="button" aria-label="Close dashboard users" data-dashboard-action="hide-dashboard-users-settings">
            ${window.dashboardIconHtml("close")}
          </button>
        </div>

        <div class="modal-body">
          <div class="modal-section settings-server-section">
            <div id="dashboardSecurityStatus" class="settings-note" hidden></div>

            <div id="dashboardKeyUnlockSection" class="settings-server-card settings-security-section">
              <div class="settings-server-card-head">
                ${window.dashboardIconHtml("key")}
                <span>Dashboard Key</span>
              </div>

              <input
                id="dashboardSecurityKey"
                class="form-input settings-input"
                type="password"
                autocomplete="current-password"
                spellcheck="false"
                placeholder="Dashboard key"
              />

              <div class="settings-actions settings-server-actions">
                <button class="settings-item" data-action="dashboard-unlock" type="button" data-dashboard-action="dashboard-unlock">
                  ${window.dashboardIconHtml("lock_open")}
                  <span>Unlock</span>
                </button>
              </div>
            </div>

            <div id="dashboardLoggedInSection" class="settings-server-card settings-dashboard-users-section" hidden>
              <div class="settings-server-card-head">
                ${window.dashboardIconHtml("person")}
                <span>Logged in as</span>
              </div>

              <div class="settings-dashboard-user-session-row">
                <span class="settings-dashboard-user-avatar ui-icon-circle">${window.dashboardIconHtml("person")}</span>
                <span class="settings-dashboard-user-copy">
                  <span id="dashboardLoggedInEmail" class="settings-dashboard-user-email">Authenticated dashboard session</span>
                  <span class="settings-dashboard-user-meta">Current dashboard login</span>
                </span>

                <button class="settings-item settings-dashboard-user-logout" data-action="dashboard-logout" type="button" data-dashboard-action="dashboard-logout">
                  ${window.dashboardIconHtml("logout")}
                  <span>Logout</span>
                </button>
              </div>
            </div>

            <div class="settings-server-card settings-dashboard-users-section">
              <div class="settings-server-card-head">
                ${window.dashboardIconHtml("group")}
                <span>Other User Accounts</span>
              </div>
            </div>

            <div id="dashboardAddUserSection" class="settings-server-card settings-dashboard-users-section settings-dashboard-add-user-section" hidden>
              <div class="settings-server-card-head">
                ${window.dashboardIconHtml("person_add")}
                <span>Add User Account</span>
              </div>

              <div id="dashboardUserFormCollapsed" class="settings-actions settings-server-actions">
                <button class="settings-item" type="button" aria-expanded="false" aria-controls="dashboardUserFormFields" data-dashboard-action="toggle-dashboard-user-form">
                  ${window.dashboardIconHtml("person_add")}
                  <span>Add User Account</span>
                </button>
              </div>

              <div id="dashboardUserFormFields" class="settings-dashboard-user-form" hidden>
                <input
                  id="dashboardUserEmail"
                  class="form-input settings-input"
                  type="email"
                  autocomplete="username"
                  spellcheck="false"
                  placeholder="Email"
                />

                <input
                  id="dashboardUserPassword"
                  class="form-input settings-input"
                  type="password"
                  autocomplete="new-password"
                  spellcheck="false"
                  minlength="10"
                  title="10+ characters with uppercase, lowercase, number, and special character"
                  placeholder="10+ chars, upper/lower, number, special"
                />

                <input
                  id="dashboardUserPasswordConfirm"
                  class="form-input settings-input"
                  type="password"
                  autocomplete="new-password"
                  spellcheck="false"
                  minlength="10"
                  title="Repeat the new dashboard user password"
                  placeholder="Confirm password"
                />

                <div class="settings-actions settings-server-actions settings-dashboard-user-form-actions">
                  <button class="settings-item" type="button" data-dashboard-action="cancel-dashboard-user-form">
                    ${window.dashboardIconHtml("close")}
                    <span>Cancel</span>
                  </button>

                  <button class="settings-item active" type="button" data-dashboard-action="add-dashboard-user">
                    ${window.dashboardIconHtml("save")}
                    <span>Save User</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div id="dashboardBluetoothSettingsModal" class="modal" hidden data-dashboard-modal="settings-bluetooth">
      <div class="modal-shell" role="dialog" aria-modal="true" aria-labelledby="dashboardBluetoothSettingsModalTitle">
        <div class="modal-head">
          <h1 id="dashboardBluetoothSettingsModalTitle" class="modal-title settings-bluetooth-modal-title">
            ${window.dashboardIconHtml("bluetooth")}
            <span>KotiBot Bluetooth Manager</span>
          </h1>
          <button class="modal-close" type="button" aria-label="Close Bluetooth manager" data-dashboard-action="hide-bluetooth-settings">
            ${window.dashboardIconHtml("close")}
          </button>
        </div>

        <div class="modal-body">
          <div class="modal-section settings-server-section">
            <div class="settings-server-card settings-bluetooth-section">
              <div class="settings-server-card-head settings-bluetooth-card-head">
                <h2 class="modal-section-title settings-bluetooth-paired-title">Paired Devices</h2>
                <button id="dashboardBluetoothPowerBtn" class="settings-item settings-bluetooth-power-btn" type="button" aria-pressed="false" data-dashboard-action="bluetooth-adapter-action" data-bluetooth-action="power_on">
                  ${window.dashboardIconHtml("power_settings_new")}
                  <span data-bluetooth-power-label>Bluetooth Power: Off</span>
                </button>
              </div>

              <div class="settings-actions settings-server-actions settings-bluetooth-pair-actions">
                <button id="dashboardBluetoothPairBtn" class="settings-item" type="button" aria-expanded="false" data-dashboard-action="toggle-bluetooth-pairing">
                  ${window.dashboardIconHtml("add_link")}
                  <span data-bluetooth-pair-label>Pair with a Bluetooth Device</span>
                </button>
              </div>

              <div id="dashboardBluetoothPairingMessage" class="settings-note" hidden>
                Make sure your Bluetooth device is turned on and set to pair.
              </div>

              <div id="dashboardBluetoothPairingDeviceList" class="settings-bluetooth-device-list" hidden></div>

              <div class="settings-actions settings-server-actions settings-bluetooth-pair-cancel" hidden>
                <button id="dashboardBluetoothPairCancelBtn" class="settings-item" type="button" data-dashboard-action="cancel-bluetooth-pairing">
                  ${window.dashboardIconHtml("close")}
                  <span>Cancel</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `);

  dashboardSyncServerViewControls();
};

function dashboardBluetoothDeviceKey(device) {
  return String(device?.address || "").trim().toUpperCase();
}

function dashboardBluetoothDeviceName(device) {
  return String(device?.alias || device?.name || device?.address || "Bluetooth Device").trim() || "Bluetooth Device";
}

function dashboardBluetoothDeviceMeta(device) {
  const parts = [];
  const address = dashboardBluetoothDeviceKey(device);

  if (address) parts.push(address);
  if (Number.isFinite(Number(device?.rssi))) parts.push(`${Number(device.rssi)} dBm`);

  return parts.join(" · ");
}

function dashboardBluetoothDeviceRow(device) {
  const address = dashboardBluetoothDeviceKey(device);
  const connected = !!device?.connected;
  const paired = !!device?.paired;

  return `
    <div class="settings-bluetooth-device-row">
      <span class="settings-bluetooth-device-copy">
        <span class="settings-bluetooth-device-name">${esc(dashboardBluetoothDeviceName(device))}</span>
        <span class="settings-bluetooth-device-meta">${esc(dashboardBluetoothDeviceMeta(device))}</span>
      </span>
      <span class="settings-bluetooth-device-actions">
        ${!paired ? `
          <button
            class="settings-room-order-btn"
            type="button"
            title="Pair ${escAttr(dashboardBluetoothDeviceName(device))}"
            aria-label="Pair ${escAttr(dashboardBluetoothDeviceName(device))}"
            data-dashboard-action="bluetooth-device-action"
            data-bluetooth-address="${escAttr(address)}"
            data-bluetooth-device-action="pair"
          >
            ${window.dashboardIconHtml("add_link")}
          </button>
        ` : `
          <button
            class="settings-room-order-btn settings-bluetooth-connect-btn ${connected ? "active" : ""}"
            type="button"
            title="${connected ? "Disconnect" : "Connect"} ${escAttr(dashboardBluetoothDeviceName(device))}"
            aria-label="${connected ? "Disconnect" : "Connect"} ${escAttr(dashboardBluetoothDeviceName(device))}"
            aria-pressed="${connected ? "true" : "false"}"
            data-dashboard-action="bluetooth-device-action"
            data-bluetooth-address="${escAttr(address)}"
            data-bluetooth-device-action="${connected ? "disconnect" : "connect"}"
          >
            ${window.dashboardIconHtml("bluetooth_connected")}
          </button>
          <button
            class="settings-room-order-btn"
            type="button"
            title="Remove ${escAttr(dashboardBluetoothDeviceName(device))}"
            aria-label="Remove ${escAttr(dashboardBluetoothDeviceName(device))}"
            data-dashboard-action="bluetooth-device-action"
            data-bluetooth-address="${escAttr(address)}"
            data-bluetooth-device-action="remove"
          >
            ${window.dashboardIconHtml("delete")}
          </button>
        `}
      </span>
    </div>
  `;
}

function dashboardBluetoothRender(data = {}) {
  const list = document.getElementById("dashboardBluetoothDeviceList");
  const powerBtn = document.getElementById("dashboardBluetoothPowerBtn");
  const pairBtn = document.getElementById("dashboardBluetoothPairBtn");
  const pairLabel = pairBtn?.querySelector("[data-bluetooth-pair-label]");
  const pairingMessage = document.getElementById("dashboardBluetoothPairingMessage");
  const pairingList = document.getElementById("dashboardBluetoothPairingDeviceList");
  const pairingCancel = document.querySelector(".settings-bluetooth-pair-cancel");
  const adapter = data.adapter || {};
  const paired = Array.isArray(data.paired) ? data.paired : [];
  const pairingDevices = Array.isArray(window.dashboardBluetoothPairingDevices)
    ? window.dashboardBluetoothPairingDevices
    : [];
  const pairingActive = window.dashboardBluetoothPairingActive === true;

  if (powerBtn) {
    const label = powerBtn.querySelector("[data-bluetooth-power-label]");

    powerBtn.classList.toggle("active", !!adapter.powered);
    powerBtn.setAttribute("aria-pressed", adapter.powered ? "true" : "false");
    powerBtn.dataset.bluetoothAction = adapter.powered ? "power_off" : "power_on";

    if (label) label.textContent = `Bluetooth Power: ${adapter.powered ? "On" : "Off"}`;
  }

  if (pairBtn) {
    pairBtn.classList.toggle("active", pairingActive);
    pairBtn.setAttribute("aria-expanded", pairingActive ? "true" : "false");
    pairBtn.dataset.dashboardAction = pairingActive ? "cancel-bluetooth-pairing" : "toggle-bluetooth-pairing";

    if (pairLabel) pairLabel.textContent = "Pair with a Bluetooth Device";
  }

  if (pairingMessage) pairingMessage.hidden = !pairingActive;
  if (pairingList) pairingList.hidden = !pairingActive;
  if (pairingCancel) pairingCancel.hidden = !pairingActive;

  if (list) {
    list.innerHTML = paired.length
      ? paired.map(dashboardBluetoothDeviceRow).join("")
      : "";
  }

  if (!pairingList) return;

  if (!pairingActive) {
    pairingList.innerHTML = "";
    return;
  }

  pairingList.innerHTML = pairingDevices.length
    ? pairingDevices.map(dashboardBluetoothDeviceRow).join("")
    : `<div class="settings-note">Scanning for Bluetooth devices in pairing mode...</div>`;
}

window.renderDashboardBluetoothManager = async function () {
  const list = document.getElementById("dashboardBluetoothDeviceList");

  if (!list) return;

  try {
    const data = await getBluetoothStatus();

    window.dashboardBluetoothStatus = data;
    window.syncSettingsSystemSummaries?.();
    dashboardBluetoothRender(data);
  } catch (err) {
    list.innerHTML = `<div class="settings-note">${esc(err?.message || "Bluetooth manager is unavailable.")}</div>`;
  }
};

function dashboardUserDateText(value) {
  const timestamp = Number(value || 0);

  if (!timestamp) return "Unknown";

  try {
    return new Date(timestamp * 1000).toLocaleDateString();
  } catch {
    return "Unknown";
  }
}

function renderDashboardUserRows(users = [], currentEmail = "") {
  const normalizedCurrentEmail = String(currentEmail || "").trim().toLowerCase();
  const visibleUsers = normalizedCurrentEmail
    ? users.filter(user => String(user?.email || "").trim().toLowerCase() !== normalizedCurrentEmail)
    : users;

  if (!visibleUsers.length) {
    return `<div class="settings-note">No other dashboard users found.</div>`;
  }

  const activeCount = users.filter(user => String(user?.status || "active").toLowerCase() === "active").length;

  return visibleUsers.map(user => {
    const email = String(user?.email || "").trim();
    const status = String(user?.status || "active").trim() || "active";
    const removeDisabled = activeCount <= 1 && status.toLowerCase() === "active";

    return `
      <div class="settings-dashboard-user-row">
        <span class="settings-dashboard-user-avatar ui-icon-circle">${window.dashboardIconHtml("person")}</span>

        <span class="settings-dashboard-user-copy">
          <span class="settings-dashboard-user-email">${esc(email)}</span>
          <span class="settings-dashboard-user-meta"><span class="settings-dashboard-user-status">${esc(status)}</span><span> · Updated ${esc(dashboardUserDateText(user?.updated_at || user?.created_at))}</span></span>
        </span>

        <button
          class="settings-room-order-btn"
          type="button"
          title="${removeDisabled ? "At least one dashboard user is required" : `Remove ${escAttr(email)}`}"
          aria-label="${removeDisabled ? "At least one dashboard user is required" : `Remove ${escAttr(email)}`}"
          data-dashboard-action="remove-dashboard-user"
          data-dashboard-user-email="${escAttr(email)}"
          ${removeDisabled ? "disabled" : ""}
        >
          ${window.dashboardIconHtml("delete")}
        </button>
      </div>
    `;
  }).join("");
}

window.renderDashboardUsers = async function () {
  const list = document.getElementById("dashboardUserList");
  if (!list) return;

  try {
    const data = await listDashboardSecurityUsers();
    const currentEmail = String(
      window.dashboardCurrentUserEmail ||
      window.dashboardCurrentUserEmailFromStatus?.(window.dashboardSecurityStatus || {}) ||
      ""
    ).trim();

    list.innerHTML = renderDashboardUserRows(data.dashboard_users || [], currentEmail);
  } catch (err) {
    list.innerHTML = `<div class="settings-note">${esc(err?.message || "Failed to load dashboard users")}</div>`;
  }
};