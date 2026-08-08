"use strict";

window.ensureAndroidHomeModalShells = function () {
  if (!document.getElementById("clientMenuModal")) {
    document.body.insertAdjacentHTML("beforeend", `
      <div id="clientMenuModal" class="modal" hidden data-dashboard-modal="client-menu">
        <div class="modal-shell" data-dashboard-stop-click>
          <div class="modal-head">
            <div class="modal-title-wrap">
              <div id="clientMenuTitle" class="modal-title">Client Menu</div>
              <div id="clientMenuSubtitle" class="modal-subtitle">Android Client</div>
            </div>

            <div class="modal-head-actions">
              <button id="clientMenuEditToggle" class="modal-close" type="button" aria-label="Edit client settings" title="Edit client settings" data-dashboard-action="toggle-client-menu-edit">
                ${window.dashboardIconHtml("edit")}
              </button>

              <button class="modal-close" type="button" aria-label="Close client menu" data-dashboard-action="hide-client-menu">${window.dashboardIconHtml("close")}</button>
            </div>
          </div>
          <div id="clientMenuBody" class="modal-body"></div>
        </div>
      </div>
    `);
  }

  if (!document.getElementById("cameraVideoModal")) {
    document.body.insertAdjacentHTML("beforeend", `
      <div id="cameraVideoModal" class="modal" hidden data-dashboard-modal="camera-video">
        <div class="modal-shell" data-dashboard-stop-click>
          <div class="modal-head">
            <div id="cameraVideoModalTitle" class="modal-title">Camera Video</div>
            <button class="modal-close" type="button" aria-label="Close camera video" data-dashboard-action="hide-camera-video">${window.dashboardIconHtml("close")}</button>
          </div>
          <div id="cameraVideoModalBody" class="modal-body">
            <img id="cameraVideoPlayer" class="camera-video-player" alt="Android camera live view">
          </div>
        </div>
      </div>
    `);
  }
};

window.renderDoorCard = function (c) {
  const id = escAttr(c.deviceID);
  const isStale = typeof window.dashboardEffectiveClientStale === "function"
    ? window.dashboardEffectiveClientStale(c)
    : !!c.stale;
  const statusClass = isStale
    ? "stale"
    : (c.calibrating
        ? "mint-blue-flash"
        : (c.door_status === "open" ? "orange-blink" : "green")
      );

  const statusText = isStale
    ? "UNKNOWN"
    : (c.calibrating ? "CALIBRATING..." : (c.door_status || "unknown").toUpperCase());

  const openScore = Number(c.openness_score || 0).toFixed(2);
  const doorStatusText = `${statusText} (${openScore})`;

  return `
    <div class="card ${isStale ? 'stale-client' : ''}" data-device-id="${id}" data-node-card="door">
      <div class="card-head lone">
        <div class="status-area">
          ${window.dashboardIconHtml(
            window.dashboardDeviceIconName(c, "door"),
            `status-door ${statusClass}`
          )}
          <div class="card-title-group">
            <div class="card-title">${esc(c.clientName)}</div>
            <div class="card-type-label">${renderCardSubtitle(c)}</div>
          </div>
        </div>

        <div class="card-actions">
          ${renderBattery(c.battery)}

          <button
            class="icon-btn${c.calibrating ? " active" : ""}"
            type="button"
            title="${c.calibrating ? "Door sensor is calibrating" : "Recalibrate door sensor"}"
            aria-label="${c.calibrating ? "Door sensor is calibrating" : "Recalibrate door sensor"}"
            data-dashboard-action="recalibrate"
            data-device-id="${id}"
            ${c.calibrating ? "disabled" : ""}
          >
            ${window.dashboardIconHtml("calibrate")}
          </button>

          <button
            class="icon-menu"
            type="button"
            aria-label="Open ${escAttr(c.clientName || "door sensor")} settings"
            data-dashboard-action="open-client-menu"
            data-device-id="${id}"
            data-menu-kind="client"
          >
            ${window.dashboardIconHtml("more_vert")}
          </button>
        </div>
      </div>

      <div class="debug-area">
        <span class="debug-label">STATUS</span><span class="debug-val status-val">${esc(doorStatusText)}</span>
        <span class="debug-label">IP</span><span class="debug-val ip-val">${esc(c.ip || "—")}</span>
        <span class="debug-label">ID</span><span class="debug-val id-val">${esc(c.deviceID || "—")}</span>
        <span class="debug-label">CLIENT VER</span><span class="debug-val ver-val">${esc(c.version || "—")}</span>
        <span class="debug-label">BATTERY</span><span class="debug-val battery-val">${c.battery !== undefined ? esc(fmt(c.battery)) + "%" : '—'}</span>
        <span class="debug-label">ZONE</span><span class="debug-val zone-val">${esc(c.zone_name || "—")}</span>
        <span class="debug-label">LAST UPDATE</span><span class="debug-val last-update-val">${esc(formatLastUpdateText(c.last_update))}</span>
      </div>
    </div>
  `;
};

window.renderAndroidMotionSensorCard = function (c) {
  const id = escAttr(c.deviceID);
  const isStale = typeof window.dashboardEffectiveClientStale === "function"
    ? window.dashboardEffectiveClientStale(c)
    : !!c.stale;
  const motionEnabled = window.dashboardBool?.(
    c.motion_detection_enabled ?? c.motionDetectionEnabled
  ) === true;
  const motionActive = motionEnabled && window.dashboardBool?.(
    c.visual_motion_active ?? c.motion_active ?? c.motionActive
  ) === true;
  const visibleMotionActive = !isStale && motionActive;

  return `
    <div class="card android-motion-card ${isStale ? "stale-client" : ""}" data-device-id="${id}" data-node-card="motion">
      <div class="card-head lone">
        <div class="status-area">
          ${window.dashboardIconHtml(
            window.dashboardDeviceIconName(c, "camera"),
            `status-cam status-motion ${isStale ? "stale" : "green"}${visibleMotionActive ? " security-active" : ""}`
          )}
          <div class="card-title-group">
            <div class="card-title">${esc(c.clientName)} Motion</div>
            <div class="card-type-label">${renderCardSubtitle(c)}</div>
          </div>
        </div>

        <div class="card-actions">
          ${renderBattery(c.battery)}

          <button
            class="icon-menu"
            type="button"
            title="Motion detection settings"
            aria-label="Motion detection settings"
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
};

window.renderCameraCard = function (c) {
  if (
    hasClientRole(c, "TAPO") &&
    (
      String(c.tapo_dashboard_section || "").toLowerCase() === "camera" ||
      String(c.tapo_kind || "").toLowerCase() === "camera" ||
      c.tapo_is_camera
    ) &&
    typeof window.renderTapoCameraCard === "function"
  ) {
    const tapoHtml = String(window.renderTapoCameraCard(c) || "").trim();

    if (tapoHtml) {
      return tapoHtml;
    }
  }

  const id = escAttr(c.deviceID);
  const isRec = !!c.recording_enabled;
  const isStale = typeof window.dashboardEffectiveClientStale === "function"
    ? window.dashboardEffectiveClientStale(c)
    : !!c.stale;
  const previewUrl = typeof window.dashboardCameraPreviewUrl === "function"
    ? window.dashboardCameraPreviewUrl(c)
    : String(c.latest_frame_url || "").trim();
  const statusText = isStale
    ? "UNKNOWN"
    : (c.frame_live ? "ONLINE" : "NO FEED");
  const lastCameraUpdate = c.frame_live
    ? `${Number(c.frame_age || 0) < 2 ? "now" : `${Math.round(Number(c.frame_age || 0))}s ago`}`
    : formatLastUpdateText(c.last_update);
  const isTalkActive = !!(c.camera_talk_active || c.cameraTalkActive);
  let shouldShowTalkButton = false;

  try {
    shouldShowTalkButton = (
      typeof window.shouldRenderAndroidCameraTalkButton === "function" &&
      window.shouldRenderAndroidCameraTalkButton(c)
    );
  } catch (err) {
    console.warn("[camera-card] talk button render failed", err);
    shouldShowTalkButton = false;
  }

  const talkButtonHtml = shouldShowTalkButton
    ? `
          <button
            class="icon-btn camera-talk-btn${isTalkActive ? ' active' : ''}"
            type="button"
            title="${isTalkActive ? 'Talking' : 'Hold to talk'}"
            aria-label="${isTalkActive ? 'Talking' : 'Hold to talk'}"
            aria-pressed="${isTalkActive ? 'true' : 'false'}"
            data-dashboard-action="noop"
            data-camera-talk-button="1"
            data-device-id="${id}"
            data-camera-talk-active="${isTalkActive ? '1' : '0'}"
          >
            ${window.dashboardIconHtml("mic")}
          </button>`
    : "";

  return `
  <div class="card cameracard ${isStale ? 'stale-client' : ''}" data-device-id="${id}" data-node-card="camera">

    <div class="camera-preview-container">
      <div class="card-head camera-card-head camera-preview-head">
        <div class="status-area">
          ${window.dashboardIconHtml(
            window.dashboardDeviceIconName(c, "camera"),
            `status-cam ${isStale ? "stale" : (c.frame_live ? "green" : "no-feed")}`
          )}
          <div class="card-title-group">
            <div class="card-title">${esc(c.clientName)}</div>
            <div class="card-type-label">${renderCardSubtitle(c)}</div>
          </div>
        </div>
        <div class="card-actions camera-card-actions">
          ${renderBattery(c.battery)}
          ${talkButtonHtml}
          <button
            class="camera-record-btn ${isRec ? 'active' : ''}"
            type="button"
            data-next-val="${isRec ? '0' : '1'}"
            data-dashboard-action="set-recording"
            data-device-id="${id}"
            title="${isRec ? 'Stop Recording' : 'Start Recording'}"
            aria-label="${isRec ? 'Stop Recording' : 'Start Recording'}"
            aria-pressed="${isRec ? 'true' : 'false'}"
          >
            <span class="camera-record-dot" aria-hidden="true"></span>
            <span class="camera-record-label">REC</span>
          </button>
          <button
            class="icon-menu"
            type="button"
            aria-label="Open ${escAttr(c.clientName || "camera")} settings"
            data-dashboard-action="open-client-menu"
            data-device-id="${id}"
            data-menu-kind="client"
          >
            ${window.dashboardIconHtml("more_vert")}
          </button>
        </div>
      </div>

      <div class="camera-preview-rotator" role="button" tabindex="0" aria-label="Open ${escAttr(c.clientName || "camera")} video" data-camera-video-open="1" data-device-id="${id}">
        <img
          class="camera-preview"
          ${previewUrl ? `src="${escAttr(previewUrl)}"` : ""}
          alt="${escAttr(c.clientName || "Camera preview")}"
          loading="eager"
          decoding="async"
          fetchpriority="high"
          style="display:${previewUrl ? 'block' : 'none'};">
      </div>

      </div>
      <div class="debug-area">
        <span class="debug-label">STATUS</span><span class="debug-val status-val">${statusText}</span>
        <span class="debug-label">IP</span><span class="debug-val ip-val">${esc(c.ip || "—")}</span>
        <span class="debug-label">ID</span><span class="debug-val id-val">${esc(c.deviceID || "—")}</span>
        <span class="debug-label">CLIENT VER</span><span class="debug-val ver-val">${esc(c.version || "—")}</span>
        <span class="debug-label">BATTERY</span><span class="debug-val battery-val">${c.battery !== undefined ? esc(fmt(c.battery)) + "%" : '—'}</span>
        <span class="debug-label">ZONE</span><span class="debug-val zone-val">${esc(c.zone_name || "—")}</span>
        <span class="debug-label">LAST UPDATE</span><span class="debug-val last-update-val">${esc(lastCameraUpdate)}</span>
      </div>
    </div>
  `;
};

window.renderCameraLinkItems = function (cameraClient, doors) {
  return doors.map(door => {
    const linked = routeExists(door.deviceID, cameraClient.deviceID, "camera", "record");
    const sourceDeviceID = escAttr(door.deviceID);
    const targetDeviceID = escAttr(cameraClient.deviceID);
    const routeID = escAttr(`m_${cameraClient.deviceID}`);

    return `<button class="menu-item ${linked ? "linked" : ""}" type="button" aria-pressed="${linked ? "true" : "false"}" data-dashboard-action="toggle-route-link"
      data-source-device-id="${sourceDeviceID}"
      data-source-event="open"
      data-target-type="camera"
      data-target-device-id="${targetDeviceID}"
      data-target-action="record"
      data-route-id="${routeID}">${linked ? "✓ " : "+ "}Link ${esc(door.clientName)}</button>`;
  }).join("");
};