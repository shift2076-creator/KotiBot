"use strict";

(() => {
  const INTERACTION_SETTLE_MS = 260;

  let rawRender = null;
  let interactionUntil = 0;
  let pendingRenderData = null;
  let pendingRenderTimer = 0;
  let renderBusy = false;

  function now() {
    return Date.now();
  }

  function dashboardIsInteracting() {
    return now() < interactionUntil || document.body?.classList.contains("dashboard-zone-drag-active");
  }

  function clearPendingRenderTimer() {
    if (!pendingRenderTimer) return;

    clearTimeout(pendingRenderTimer);
    pendingRenderTimer = 0;
  }

  function getRawRender() {
    if (typeof rawRender === "function") return rawRender;
    if (typeof window.render !== "function") return null;

    rawRender = window.render;
    return rawRender;
  }

  function runRender(data) {
    const renderFn = getRawRender();

    clearPendingRenderTimer();
    pendingRenderData = null;

    if (typeof renderFn !== "function") {
      console.error("[dashboard-events] window.render is not available");
      return;
    }

    renderBusy = true;

    try {
      const renderData = typeof window.applyTapoPendingPowerStatesToDashboardData === "function"
        ? window.applyTapoPendingPowerStatesToDashboardData(data)
        : data;

      return renderFn(renderData);
    } finally {
      renderBusy = false;
    }
  }

  function schedulePendingRender() {
    clearPendingRenderTimer();

    const delay = Math.max(30, interactionUntil - now() + 30);

    pendingRenderTimer = setTimeout(() => {
      pendingRenderTimer = 0;

      if (!pendingRenderData) return;

      if (dashboardIsInteracting()) {
        schedulePendingRender();
        return;
      }

      runRender(pendingRenderData);
    }, delay);
  }

  window.dashboardMarkInteraction = function () {
    interactionUntil = Math.max(interactionUntil, now() + INTERACTION_SETTLE_MS);

    if (pendingRenderData) {
      schedulePendingRender();
    }
  };

  window.dashboardRenderNow = function (data) {
    return runRender(data);
  };

  window.dashboardRequestRender = function (data) {
    if (renderBusy || dashboardIsInteracting()) {
      pendingRenderData = data;
      schedulePendingRender();
      return;
    }

    return runRender(data);
  };

  window.requestDashboardRender = function (data) {
    if (typeof window.dashboardRequestRender === "function") {
      return window.dashboardRequestRender(data);
    }

    if (typeof window.render === "function") {
      return window.render(data);
    }
  };

  function getInteractiveTarget(target) {
    if (!(target instanceof Element)) return null;

    return target.closest([
      "button",
      "a",
      "input",
      "select",
      "textarea",
      "label",
      "[role='button']",
      "[data-dashboard-action]",
      "[data-dashboard-change]",
      "[data-tapo-action]",
      ".icon-menu",
      ".settings-item",
      ".modal",
      ".sensor-modal"
    ].join(","));
  }

  function markIfInteractive(event) {
    if (!getInteractiveTarget(event.target)) return;

    window.dashboardMarkInteraction();
  }

  function closeTopModal() {
    const orderedClosers = [
      ["dashboardActivityModal", "hideActivityModal"],
      ["dashboardHomeArmingActionModal", "hideDashboardHomeArmingActionPicker"],
      ["dashboardHomeArmingModal", "hideDashboardHomeArmingSettings"],
      ["dashboardHomeLightingAutomationModal", "hideDashboardHomeLightingAutomationEditor"],
      ["dashboardHomeLightingModal", "hideDashboardHomeLightingSettings"],
      ["audioModal", "hideAudioModal"],
      ["dashboardUsersSettingsModal", "hideDashboardUsersSettingsModal"],
      ["dashboardBluetoothSettingsModal", "hideBluetoothSettingsModal"],
      ["dashboardMatterRecommissionModal", "hideDashboardMatterRecommissionModal"],
      ["dashboardMatterSettingsModal", "hideDashboardMatterSettingsModal"],
      ["dashboardClientsModal", "hideDashboardClientsModal"],
      ["settingsModal", "hideSettingsModal"],
      ["matterEnvironmentSettingsModal", "hideMatterEnvironmentSettings"],
      ["matterEnvironmentModal", "hideMatterEnvironmentModal"],
      ["clientMetaModal", "hideClientMetaModal"],
      ["clientMenuModal", "hideClientMenuModal"]
    ];

    for (const [id, fnName] of orderedClosers) {
      const modal = document.getElementById(id);
      if (!modal || modal.hidden) continue;

      window[fnName]?.();
      return true;
    }

    return false;
  }

  const dashboardActions = {
    "noop": () => true,
    "toggle-menu": (el, event) => {
      window.toggleMenu?.(event, el);
      return true;
    },
    "aside-home": () => {
      window.showDashboardHome?.();
      return true;
    },
    "aside-render-controls": () => {
      window.showRenderControls?.();
      return true;
    },
    "aside-render-monitors": () => {
      window.showRenderMonitors?.();
      return true;
    },
    "aside-render-sensors": () => {
      window.showRenderSensors?.();
      return true;
    },
    "aside-show-activity": () => {
      window.showActivityModal?.();
      return true;
    },
    "hide-activity-modal": () => {
      window.hideActivityModal?.();
      return true;
    },
    "set-activity-filter": async (el) => {
      await window.setActivityFilter?.(el.dataset.activityCategory || "all");
      return true;
    },
    "aside-show-settings": () => {
      window.ensureSettingsModal?.();
      window.showSettingsModal?.();
      return true;
    },
    "set-home-arm-mode": async (el) => {
      await window.setDashboardHomeArmMode?.(el.dataset.mode);
      return true;
    },
    "set-home-light-mode": async (el) => {
      await window.setDashboardHomeLightMode?.(el.dataset.mode);
      return true;
    },
    "show-home-lighting-settings": async (el) => {
      await window.showDashboardHomeLightingSettings?.(el.dataset.mode);
      return true;
    },
    "hide-home-lighting-settings": () => {
      window.hideDashboardHomeLightingSettings?.();
      return true;
    },
    "select-home-lighting-settings-mode": (el) => {
      window.selectDashboardHomeLightingSettingsMode?.(el.dataset.mode || "day");
      return true;
    },
    "set-home-lighting-mode-choice": async (el) => {
      await window.setDashboardHomeLightingModeChoice?.(el);
      return true;
    },
    "show-home-arming-settings": async (el) => {
      await window.showDashboardHomeArmingSettings?.(el.dataset.mode);
      return true;
    },
    "hide-home-arming-settings": () => {
      window.hideDashboardHomeArmingSettings?.();
      return true;
    },
    "select-home-arming-settings-mode": (el) => {
      window.selectDashboardHomeArmingSettingsMode?.(el.dataset.mode || "day");
      return true;
    },
    "show-home-arming-action-picker": (el) => {
      window.showDashboardHomeArmingActionPicker?.(el.dataset.mode || "day", el.dataset.triggerDeviceId || "");
      return true;
    },
    "hide-home-arming-action-picker": () => {
      window.hideDashboardHomeArmingActionPicker?.();
      return true;
    },
    "select-home-arming-action-type": (el) => {
      window.selectDashboardHomeArmingActionType?.(el);
      return true;
    },
    "show-home-arming-breadcrumb-step": (el) => {
      window.showDashboardHomeArmingBreadcrumbStep?.(el);
      return true;
    },
    "toggle-home-arming-trigger": (el) => {
      window.toggleDashboardHomeArmingTrigger?.(el);
      return true;
    },
    "show-home-arming-target-step": (el) => {
      window.showDashboardHomeArmingTargetStep?.(el);
      return true;
    },
    "show-home-arming-post-trigger-step": (el) => {
      window.showDashboardHomeArmingPostTriggerStep?.(el);
      return true;
    },
    "toggle-home-arming-target": (el) => {
      window.toggleDashboardHomeArmingTarget?.(el);
      return true;
    },
    "select-home-arming-sound": (el) => {
      window.selectDashboardHomeArmingSound?.(el);
      return true;
    },
    "test-home-arming-sound": async () => {
      await window.testDashboardHomeArmingSound?.();
      return true;
    },
    "step-home-arming-number": (el) => {
      window.stepDashboardHomeArmingNumber?.(
        el.dataset.inputId,
        el.dataset.direction
      );
      return true;
    },
    "save-home-arming-route": async (el) => {
      await window.saveDashboardHomeArmingRoute?.(el);
      return true;
    },
    "delete-home-arming-route": async (el) => {
      await window.deleteDashboardHomeArmingRoute?.(el);
      return true;
    },
    "show-home-lighting-automation-editor": (el) => {
      window.showDashboardHomeLightingAutomationEditor?.(el.dataset.mode || "day");
      return true;
    },
    "select-home-lighting-action-type": (el) => {
      window.selectDashboardHomeLightingActionType?.(el);
      return true;
    },
    "edit-home-lighting-automation": (el) => {
      window.showDashboardHomeLightingAutomationEditor?.(el.dataset.mode || "day", el.dataset.automationId || "");
      return true;
    },
    "hide-home-lighting-automation-editor": () => {
      window.hideDashboardHomeLightingAutomationEditor?.();
      return true;
    },
    "save-home-lighting-automation": () => {
      window.saveDashboardHomeLightingAutomation?.();
      return true;
    },
    "remove-home-lighting-automation": (el) => {
      window.removeDashboardHomeLightingAutomation?.(el.dataset.mode || "day", el.dataset.automationId || "");
      return true;
    },
    "open-client-menu": (el, event) => {
      const clientCard = el.closest("[data-device-id]");
      const deviceID = el.dataset.deviceId || clientCard?.dataset.deviceId || "";
      const kind = el.dataset.menuKind || clientCard?.dataset.menuKind || "client";

      if (!deviceID) return true;

      window.openClientMenuNow?.(event, deviceID, kind);
      return true;
    },
    "open-dashboard-client-settings": async (el, event) => {
      const clientCard = el.closest("[data-device-id]");
      const deviceID = el.dataset.deviceId || clientCard?.dataset.deviceId || "";

      if (!deviceID) return true;

      await window.openDashboardClientSettings?.(event, deviceID);
      return true;
    },
    "hide-client-menu": () => {
      window.hideClientMenuModal?.();
      return true;
    },
    "toggle-client-menu-edit": (_el, event) => {
      window.toggleClientMenuEditMode?.(event);
      return true;
    },
    "hide-camera-video": () => {
      window.hideCameraVideoModal?.();
      return true;
    },
    "hide-client-meta": () => {
      window.hideClientMetaModal?.();
      return true;
    },
    "save-client-meta": async () => {
      await window.saveClientMenuMeta?.();
      return true;
    },
    "hide-audio": () => {
      window.hideAudioModal?.();
      return true;
    },
    "hide-settings": () => {
      window.hideSettingsModal?.();
      return true;
    },
    "apply-log-filters": () => {
      window.applyLogFilters?.();
      return true;
    },
    "set-recording": (el) => {
      window.setRecordingFromButton?.(el, el.dataset.deviceId);
      return true;
    },
    "toggle-route-link": async (el, event) => {
      await window.toggleRouteLink?.(
        event,
        el.dataset.sourceDeviceId,
        el.dataset.sourceEvent,
        el.dataset.targetType,
        el.dataset.targetDeviceId,
        el.dataset.targetAction,
        el.dataset.routeId
      );
      return true;
    },
    "provision-client": (el) => {
      window.provisionClient?.(el.dataset.deviceId);
      return true;
    },
    "remove-client": async (el) => {
      await window.removeClient?.(el.dataset.deviceId);
      return true;
    },
    "remove-client-meta": async (el) => {
      await window.removeClientMetaDevice?.(el);
      return true;
    },
    "toggle-lens": async (el) => {
      await window.toggleLens?.(el.dataset.deviceId);
      window.renderOpenClientMenu?.();
      return true;
    },
    "recalibrate": async (el) => {
      await window.recalibrate?.(el.dataset.deviceId);
      return true;
    },
    "rename-client": async (el) => {
      await window.renameClient?.(el.dataset.deviceId);
      window.renderOpenClientMenu?.();
      return true;
    },
    "toggle-group-by-room": () => {
      window.setDashboardGroupByRoom?.(true);
      return true;
    },
    "select-dashboard-camera": (el) => {
      if (document.body.dataset.dashboardLayout === "portrait") {
        window.selectDashboardCamera?.(el.dataset.deviceId);
      }

      return true;
    },
    "toggle-dashboard-info": () => {
      window.toggleDashboardInfo?.();
      return true;
    },
    "show-environment-modal": async (el) => {
      await window.loadDashboardEnvironmentSubsystem?.();

      window.showMatterEnvironmentModal?.(el.dataset.room || "");

      void Promise.resolve(window.loadDashboardMatterSubsystem?.())
        .then(() => {
          window.renderMatterEnvironmentModal?.();
        })
        .catch(err => {
          console.warn("[dashboard-load] Environment Matter settings failed", err);
        });

      return true;
    },
    "hide-environment-modal": () => {
      window.hideMatterEnvironmentModal?.();
      return true;
    },
    "show-environment-settings": async () => {
      await window.loadDashboardEnvironmentSubsystem?.();
      window.showMatterEnvironmentSettings?.();
      return true;
    },
    "hide-environment-settings": () => {
      window.hideMatterEnvironmentSettings?.();
      return true;
    },
    "set-environment-temp-unit": (el) => {
      window.setMatterEnvironmentTemperatureUnit?.(el.dataset.unit);
      return true;
    },
    "save-environment-settings": async () => {
      await window.saveMatterEnvironmentSettingsFromModal?.();
      return true;
    },
    "toggle-dashboard-text-size": () => {
      window.toggleDashboardTextSize?.();
      return true;
    },
    "show-dashboard-users-settings": async () => {
      await window.showDashboardUsersSettingsModal?.();
      return true;
    },
    "hide-dashboard-users-settings": () => {
      window.hideDashboardUsersSettingsModal?.();
      return true;
    },
    "show-bluetooth-settings": async () => {
      await window.showBluetoothSettingsModal?.();
      return true;
    },
    "hide-bluetooth-settings": () => {
      window.hideBluetoothSettingsModal?.();
      return true;
    },
    "show-dashboard-matter-settings": async () => {
      await window.showDashboardMatterSettingsModal?.();
      return true;
    },
    "show-dashboard-clients-modal": () => {
      window.showDashboardClientsModal?.();
      return true;
    },
    "hide-dashboard-clients-modal": () => {
      window.hideDashboardClientsModal?.();
      return true;
    },
    "set-dashboard-client-grouping": el => {
      window.setDashboardClientGrouping?.(el.dataset.groupMode);
      return true;
    },
    "hide-dashboard-matter-settings": () => {
      window.hideDashboardMatterSettingsModal?.();
      return true;
    },
    "sync-dashboard-matter": async () => {
      await window.syncDashboardMatterNow?.();
      return true;
    },
    "show-dashboard-matter-recommission": async () => {
      await window.showDashboardMatterRecommissionModal?.();
      return true;
    },
    "hide-dashboard-matter-recommission": () => {
      window.hideDashboardMatterRecommissionModal?.();
      return true;
    },
    "recommission-dashboard-matter": async () => {
      await window.recommissionDashboardMatter?.();
      return true;
    },
    "dashboard-unlock": async () => {
      await window.unlockDashboardSecurity?.();
      return true;
    },
    "dashboard-logout": async () => {
      if (typeof window.logoutDashboardSecurity === "function") {
        await window.logoutDashboardSecurity();
      } else {
        await window.logoutDashboard?.();
      }

      await window.syncDashboardSecurityControls?.();
      return true;
    },
    "toggle-dashboard-user-form": () => {
      window.toggleDashboardUserFormFromSettings?.();
      return true;
    },
    "cancel-dashboard-user-form": () => {
      window.cancelDashboardUserFormFromSettings?.();
      return true;
    },
    "add-dashboard-user": async () => {
      await window.addDashboardUserFromSettings?.();
      return true;
    },
    "remove-dashboard-user": async (el) => {
      await window.removeDashboardUserFromSettings?.(el.dataset.dashboardUserEmail);
      return true;
    },
    "refresh-dashboard-users": async () => {
      await window.renderDashboardUsers?.();
      return true;
    },
    "refresh-dashboard-sessions": async () => {
      await window.refreshDashboardSessionsFromSettings?.();
      return true;
    },
    "revoke-dashboard-session": async (el) => {
      await window.revokeDashboardSessionFromSettings?.(
        el.dataset.dashboardSessionRef
      );
      return true;
    },
    "revoke-other-dashboard-sessions": async () => {
      await window.revokeOtherDashboardSessionsFromSettings?.();
      return true;
    },
    "show-automation-settings": async (el) => {
      await window.showAutomationSettings?.({
        deviceID: el.dataset.deviceId || "",
        triggerGroup: el.dataset.triggerGroup || ""
      });
      return true;
    },
    "edit-device-automation": async (el) => {
      await window.editDashboardDeviceAutomation?.(
        el.dataset.automationId || "",
        el.dataset.deviceId || ""
      );
      return true;
    },
    "delete-device-automation": async () => {
      await window.deleteDashboardDeviceAutomation?.();
      return true;
    },
    "refresh-bluetooth": async () => {
      await window.refreshBluetoothManagerFromSettings?.();
      return true;
    },
    "scan-bluetooth": async () => {
      await window.scanBluetoothFromSettings?.();
      return true;
    },
    "toggle-bluetooth-pairing": async () => {
      await window.toggleBluetoothPairingFromSettings?.();
      return true;
    },
    "cancel-bluetooth-pairing": async () => {
      await window.cancelBluetoothPairingFromSettings?.();
      return true;
    },
    "bluetooth-adapter-action": async (el) => {
      await window.setBluetoothAdapterFromSettings?.(el.dataset.bluetoothAction);
      return true;
    },
    "bluetooth-device-action": async (el) => {
      await window.setBluetoothDeviceFromSettings?.(el.dataset.bluetoothAddress, el.dataset.bluetoothDeviceAction);
      return true;
    },
    "restart-server": () => {
      window.restartServer?.();
      return true;
    },
  };

  const dashboardChanges = {
    "set-activity-range": async (el) => {
      await window.setActivityRange?.(el);
      return true;
    },
    "apply-log-filters": () => {
      window.applyLogFilters?.();
      return true;
    },
    "sync-dashboard-matter-recommission": () => {
      window.syncDashboardMatterRecommissionButton?.();
      return true;
    },
    "set-motion-detection": async (el) => {
      const section = el.closest(".modal-section");
      const content = section?.querySelector(":scope > .client-menu-motion-options");

      if (content) {
        content.hidden = !el.checked;
      }

      await window.setMotionDetection?.(el.dataset.deviceId, el.checked);
      return true;
    },
    "set-camera-motion-sensitivity": async (el) => {
      await window.setCameraMotionSensitivity?.(el.dataset.deviceId, el.value);
      return true;
    },
    "toggle-home-lighting-all-lights": () => {
      window.toggleDashboardHomeLightingAllLights?.();
      return true;
    },
    "update-home-lighting-automation-slider": () => {
      window.updateDashboardHomeLightingAutomationSlider?.();
      return true;
    },
    "update-home-arming-sound-volume": () => {
      window.updateDashboardHomeArmingSoundVolume?.();
      return true;
    },
    "update-home-arming-environment-threshold": () => {
      window.updateDashboardHomeArmingEnvironmentThreshold?.();
      return true;
    }
  };

  const dashboardInputs = {
    "preview-activity-range": el => {
      window.syncDashboardActivityRange?.(el);
      return true;
    },
    "sync-dashboard-matter-recommission": () => {
      window.syncDashboardMatterRecommissionButton?.();
      return true;
    },
    "update-home-lighting-automation-slider": () => {
      window.updateDashboardHomeLightingAutomationSlider?.();
      return true;
    },
    "update-home-arming-sound-volume": () => {
      window.updateDashboardHomeArmingSoundVolume?.();
      return true;
    },
    "update-home-arming-environment-threshold": () => {
      window.updateDashboardHomeArmingEnvironmentThreshold?.();
      return true;
    }
  };

  function getDashboardActionElement(target) {
    if (!(target instanceof Element)) return null;

    return target.closest("[data-dashboard-action], [data-action]");
  }

  function getDashboardActionName(el) {
    return el?.dataset?.dashboardAction || el?.dataset?.action || "";
  }

  function dashboardElementIsDisabled(el) {
    return !el ||
      el.hasAttribute("disabled") ||
      el.getAttribute("aria-disabled") === "true";
  }

  function runDashboardActionHandler(handler, el, event) {
    try {
      const result = handler(el, event);

      if (result && typeof result.catch === "function") {
        result.catch(err => console.warn("[dashboard-events] action failed", err));
      }
    } catch (err) {
      console.warn("[dashboard-events] action failed", err);
    }
  }

  function claimDashboardEvent(event) {
    window.dashboardMarkInteraction();
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
  }

  document.addEventListener("pointerdown", markIfInteractive, { capture: true, passive: true });
  document.addEventListener("pointerdown", event => {
    window.handleControlsZoneDragPointerDown?.(event);
  }, { capture: true, passive: false });
  document.addEventListener("pointerup", markIfInteractive, { capture: true, passive: true });
  document.addEventListener("touchstart", markIfInteractive, { capture: true, passive: true });
  document.addEventListener("touchend", markIfInteractive, { capture: true, passive: true });

  function handleDashboardClick(event) {
    const actionEl = getDashboardActionElement(event.target);

    if (actionEl && !dashboardElementIsDisabled(actionEl)) {
      const action = getDashboardActionName(actionEl);
      const handler = dashboardActions[action];

      if (handler) {
        claimDashboardEvent(event);
        runDashboardActionHandler(handler, actionEl, event);
        return;
      }
    }

    if (
      !(event.target instanceof Element) ||
      !event.target.closest(".menu-container, .menu-content, .icon-menu, [data-tapo-action], [data-dashboard-action], [data-action]")
    ) {
      window.closeAllMenus?.();
    }
  }

  document.addEventListener("click", handleDashboardClick, true);

  document.addEventListener("change", event => {
    const el = event.target instanceof Element
      ? event.target.closest("[data-dashboard-change]")
      : null;

    if (!el || dashboardElementIsDisabled(el)) return;

    const handler = dashboardChanges[el.dataset.dashboardChange || ""];
    if (!handler) return;

    window.dashboardMarkInteraction();
    runDashboardActionHandler(handler, el, event);
  });

  document.addEventListener("input", event => {
    const el = event.target instanceof Element
      ? event.target.closest("[data-dashboard-input]")
      : null;

    if (!el || dashboardElementIsDisabled(el)) return;

    const handler = dashboardInputs[el.dataset.dashboardInput || ""];
    if (!handler) return;

    window.dashboardMarkInteraction();
    runDashboardActionHandler(handler, el, event);
  });

  document.addEventListener("submit", event => {
    const form = event.target instanceof Element
      ? event.target.closest("[data-dashboard-submit]")
      : null;

    if (!form || dashboardElementIsDisabled(form)) return;

    const handler = dashboardActions[form.dataset.dashboardSubmit || ""];
    if (!handler) return;

    claimDashboardEvent(event);
    runDashboardActionHandler(handler, form, event);
  });

  document.addEventListener("dblclick", event => {
    const el = event.target instanceof Element
      ? event.target.closest("[data-dashboard-dblclick]")
      : null;

    if (!el || dashboardElementIsDisabled(el)) return;

    const action = el.dataset.dashboardDblclick || "";

    if (action === "open-zone-list") {
      window.dashboardMarkInteraction();
      event.preventDefault();
      event.stopPropagation();
      window.openZoneList?.(el);
    }
  });

  document.addEventListener("keydown", event => {
    if (
      (event.key === "Enter" || event.key === " ") &&
      event.target instanceof Element &&
      event.target.matches('[role="button"][data-dashboard-action]')
    ) {
      event.preventDefault();
      event.target.click();
      return;
    }

    if (event.key !== "Escape") return;

    window.dashboardMarkInteraction();

    if (closeTopModal()) {
      event.preventDefault();
      event.stopPropagation();
    }
  });
})();

window.closeAllMenus = function () {
  document.querySelectorAll(".menu-content.show").forEach(el => {
    el.classList.remove("show");
  });
};

window.toggleMenu = function (event, menuRef) {
  event.preventDefault();
  event.stopPropagation();
  event.stopImmediatePropagation?.();

  const trigger = menuRef instanceof Element ? menuRef : null;
  const menu = trigger
    ? trigger.parentElement?.querySelector(":scope > .menu-content")
    : document.getElementById(menuRef);

  if (!menu) return;

  const isOpen = menu.classList.contains("show");
  closeAllMenus();

  if (!isOpen) {
    menu.classList.add("show");
  }
};

window.runMenuAction = function (menuId, actionName, ...args) {
  closeAllMenus();

  const fn = window[actionName];
  if (typeof fn !== "function") {
    console.error("[runMenuAction] missing action:", actionName);
    return;
  }

  return fn(...args);
};

window.openClientMenuNow = function (event, deviceID, kind = "client") {
  event?.preventDefault?.();
  event?.stopPropagation?.();
  event?.stopImmediatePropagation?.();

  if (!deviceID) return false;

  if (kind === "matter") {
    if (typeof window.showMatterClientMenu === "function") {
      window.showMatterClientMenu(deviceID);
      window.syncDashboardDeviceAutomationSettings?.(deviceID);
      return false;
    }

    window.loadDashboardMatterSubsystem?.()
      ?.then(() => {
        window.showMatterClientMenu?.(deviceID);
        window.syncDashboardDeviceAutomationSettings?.(deviceID);
      })
      ?.catch(err => console.warn("[dashboard-events] matter menu load failed", err));
    return false;
  }

  window.showDashboardClientMenu?.(deviceID);
  return false;
};

window.addEventListener("beforeunload", () => {
  for (const deviceID of window.previewActiveDeviceIds) {
    setPreviewViewer(deviceID, false, true);
  }

  window.sleepAllTapoCameraVideos?.(true);
});

window.previewViewerHeartbeatTimer = window.previewViewerHeartbeatTimer || setInterval(() => {
  const debug = window.previewViewerDebug || (window.previewViewerDebug = {});
  const activeIds = window.previewActiveDeviceIds instanceof Set
    ? window.previewActiveDeviceIds
    : new Set();
  const page = window.cleanDashboardPage?.(S.activeDashboardPage) || S.activeDashboardPage || "home";

  debug.heartbeatTicks = Number(debug.heartbeatTicks || 0) + 1;
  debug.heartbeatLastAt = Math.round(performance.now());
  debug.heartbeatActiveCount = activeIds.size;

  if (!activeIds.size) {
    debug.heartbeatSkippedEmpty = Number(debug.heartbeatSkippedEmpty || 0) + 1;
    return;
  }

  if (document.hidden || S.activeView === "debug" || page !== "monitor") {
    debug.heartbeatSkippedInactive = Number(debug.heartbeatSkippedInactive || 0) + 1;
    return;
  }

  debug.heartbeatSent = Number(debug.heartbeatSent || 0) + 1;

  for (const deviceID of activeIds) {
    setPreviewViewer(deviceID, true);
  }
}, window.previewViewerHeartbeatMs || 15000);