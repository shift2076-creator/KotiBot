"use strict";

window.androidCameraTalkSessions = window.androidCameraTalkSessions || new Map();

function cameraTalkErrorMessage(err) {
  const name = err?.name || "";

  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return "Microphone permission was denied. Allow microphone access for this app, then try again.";
  }

  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "No microphone was found.";
  }

  if (name === "NotReadableError" || name === "TrackStartError") {
    const detail = [err?.name, err?.message].filter(Boolean).join(": ");

    return detail
      ? `The key client WebView could not open the microphone. Android reported: ${detail}`
      : "The key client WebView could not open the microphone.";
  }

  if (!window.isSecureContext) {
    return "Microphone access requires HTTPS or localhost.";
  }

  return err?.message || "Camera talk failed.";
}

async function getDashboardCameraTalkStream() {
  try {
    return await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: { ideal: true },
        noiseSuppression: { ideal: true },
        autoGainControl: { ideal: true }
      },
      video: false
    });
  } catch (err) {
    const name = err?.name || "";
    const shouldRetryBareAudio = [
      "NotReadableError",
      "TrackStartError",
      "OverconstrainedError",
      "ConstraintNotSatisfiedError"
    ].includes(name);

    if (!shouldRetryBareAudio) {
      throw err;
    }

    console.warn("Camera talk preferred mic constraints failed; retrying bare audio.", err);

    await new Promise(resolve => setTimeout(resolve, 150));

    try {
      return await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: false
      });
    } catch (fallbackErr) {
      fallbackErr.cameraTalkFirstError = {
        name: err?.name || "",
        message: err?.message || ""
      };

      throw fallbackErr;
    }
  }
}

function dashboardCameraTalkClientHasRole(client, role) {
  if (!client || !role) return false;

  try {
    if (typeof window.clientHasRole === "function") {
      return !!window.clientHasRole(client, role);
    }
  } catch (_) {}

  try {
    if (typeof window.hasClientRole === "function") {
      return !!window.hasClientRole(client, role);
    }
  } catch (_) {}

  const wanted = String(role || "").trim().toUpperCase();
  const roles = Array.isArray(client.roles)
    ? client.roles
    : String(client.role || client.clientRole || "").split(/[\s,|]+/);

  return roles.some(item => String(item || "").trim().toUpperCase() === wanted);
}

function dashboardCameraTalkViewerIsAndroidKeyClientApp() {
  try {
    if (typeof window.dashboardViewerIsAndroidKeyClientApp === "function") {
      return !!window.dashboardViewerIsAndroidKeyClientApp();
    }
  } catch (_) {}

  return false;
}

function dashboardCameraTalkSourceDeviceID() {
  return "";
}

window.shouldRenderAndroidCameraTalkButton = function (c) {
  if (!dashboardCameraTalkViewerIsAndroidKeyClientApp()) return false;
  if (!c?.provisioned || c?.stale) return false;
  if (!dashboardCameraTalkClientHasRole(c, "CAM")) return false;
  if (dashboardCameraTalkClientHasRole(c, "TAPO") || c.tapo_kind === "camera") return false;

  if (c.cameraTalkAvailable === false || c.camera_talk_available === false) {
    return false;
  }

  return true;
};

function setCameraTalkButtonState(button, state) {
  if (!button) return;

  const active = state === "active" || state === "connected";
  const pending = state === "pending" || state === "starting";

  button.classList.toggle("active", active);
  button.classList.toggle("pending", pending);
  button.dataset.cameraTalkActive = active ? "1" : "0";
  button.dataset.cameraTalkPending = pending ? "1" : "0";
  button.setAttribute("aria-pressed", active ? "true" : "false");

  if (active) {
    button.title = "Mic on";
    button.setAttribute("aria-label", "Mic on. Tap to turn off");
  } else if (pending) {
    button.title = "Starting mic";
    button.setAttribute("aria-label", "Starting mic");
  } else {
    button.title = "Mic off";
    button.setAttribute("aria-label", "Mic off. Tap to turn on");
  }
}

function cameraTalkCandidatePayload(candidate) {
  if (!candidate) return null;

  if (typeof candidate.toJSON === "function") {
    return candidate.toJSON();
  }

  return candidate;
}

function cameraTalkSessionDescriptionPayload(description, expectedType) {
  const sdp = String(description?.sdp || "").trim();

  if (!sdp || sdp === "null" || !sdp.startsWith("v=0")) {
    throw new Error(`Camera talk ${expectedType} SDP was not created.`);
  }

  return {
    type: expectedType,
    sdp: `${sdp.replace(/\r?\n/g, "\r\n")}\r\n`
  };
}

async function pollDashboardCameraTalkSession(session) {
  if (!session || session.stopping || !session.sessionID) return;

  try {
    const data = await getCameraTalkSession(session.sessionID);
    const serverSession = data.session || {};

    if (["ended", "failed", "expired"].includes(serverSession.state)) {
      stopDashboardCameraTalk(
        session.deviceID,
        serverSession.error || serverSession.state || "server_ended",
        false,
        false
      );
      return;
    }

    if (serverSession.answer && !session.remoteAnswerSet) {
      await session.pc.setRemoteDescription(new RTCSessionDescription(serverSession.answer));
      session.remoteAnswerSet = true;
    }

    const candidates = Array.isArray(serverSession.clientCandidates)
      ? serverSession.clientCandidates
      : [];

    for (const candidate of candidates) {
      if (!candidate) continue;

      const key = JSON.stringify(candidate);

      if (session.clientCandidateKeys.has(key)) continue;

      session.clientCandidateKeys.add(key);

      try {
        await session.pc.addIceCandidate(new RTCIceCandidate(candidate));
      } catch (err) {
        console.warn("Camera talk client ICE candidate failed", err);
      }
    }
  } catch (err) {
    console.warn("Camera talk session poll failed", err);
  }
}

async function startDashboardCameraTalk(button) {
  const deviceID = String(button?.dataset?.deviceId || "").trim();

  if (!deviceID || window.androidCameraTalkSessions.has(deviceID)) return;
  if (button.dataset.cameraTalkStarting === "1") return;

  if (!dashboardCameraTalkViewerIsAndroidKeyClientApp()) return;

  if (!window.isSecureContext) {
    alert("Microphone access requires HTTPS or localhost.");
    return;
  }

  if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) {
    alert("This app view does not support WebRTC microphone talk.");
    return;
  }

  button.dataset.cameraTalkRequested = "1";
  button.dataset.cameraTalkStarting = "1";
  setCameraTalkButtonState(button, "starting");

  let stream = null;

  try {
    stream = await getDashboardCameraTalkStream();

    if (button.dataset.cameraTalkRequested !== "1") {
      stream.getTracks().forEach(track => track.stop());
      setCameraTalkButtonState(button, "idle");
      return;
    }

    const createData = await createCameraTalkSession({
      targetDeviceID: deviceID,
      sourceDeviceID: dashboardCameraTalkSourceDeviceID()
    });

    const sessionID = createData.sessionID || "";
    if (!sessionID) throw new Error("Camera talk session was not created.");

    const pc = new RTCPeerConnection({
      iceServers: Array.isArray(createData.iceServers) ? createData.iceServers : []
    });

    const session = {
      deviceID,
      sessionID,
      stream,
      pc,
      button,
      remoteAnswerSet: false,
      clientCandidateKeys: new Set(),
      pollTimer: 0,
      connectTimer: 0,
      stopping: false
    };

    window.androidCameraTalkSessions.set(deviceID, session);

    pc.onicecandidate = async (event) => {
      if (!event.candidate || session.stopping) return;

      try {
        await postCameraTalkDashboardCandidate(
          sessionID,
          cameraTalkCandidatePayload(event.candidate)
        );
      } catch (err) {
        console.warn("Camera talk dashboard ICE candidate failed", err);
      }
    };

    pc.onconnectionstatechange = () => {
      if (session.stopping) return;

      if (pc.connectionState === "connected") {
        if (session.connectTimer) {
          clearTimeout(session.connectTimer);
          session.connectTimer = 0;
        }

        setCameraTalkButtonState(button, "connected");
        return;
      }

      if (["failed", "closed"].includes(pc.connectionState)) {
        stopDashboardCameraTalk(deviceID, pc.connectionState);
      }
    };

    pc.oniceconnectionstatechange = () => {
      if (session.stopping) return;

      if (["connected", "completed"].includes(pc.iceConnectionState)) {
        if (session.connectTimer) {
          clearTimeout(session.connectTimer);
          session.connectTimer = 0;
        }

        setCameraTalkButtonState(button, "connected");
        return;
      }

      if (["failed", "closed", "disconnected"].includes(pc.iceConnectionState)) {
        stopDashboardCameraTalk(deviceID, `ice_${pc.iceConnectionState}`);
      }
    };

    stream.getAudioTracks().forEach(track => {
      const sender = pc.addTrack(track, stream);
      const transceiver = pc.getTransceivers().find(item => item.sender === sender);

      if (transceiver) {
        transceiver.direction = "sendonly";
      }
    });

    const offer = await pc.createOffer({
      offerToReceiveAudio: false,
      offerToReceiveVideo: false
    });

    await pc.setLocalDescription(offer);

    const localOffer = pc.localDescription || offer;
    await postCameraTalkOffer(
      sessionID,
      cameraTalkSessionDescriptionPayload(localOffer, "offer")
    );

    setCameraTalkButtonState(button, "active");

    session.connectTimer = setTimeout(() => {
      if (session.stopping) return;

      if (!session.remoteAnswerSet || !["connected", "completed"].includes(pc.iceConnectionState)) {
        stopDashboardCameraTalk(deviceID, "ice_connect_timeout");
        alert("Camera talk could not connect across this network. Check the camera talk relay/STUN/TURN settings.");
      }
    }, 20000);

    session.pollTimer = setInterval(() => {
      pollDashboardCameraTalkSession(session);
    }, 250);

    pollDashboardCameraTalkSession(session);
  } catch (err) {
    console.warn("Camera talk start failed", err);

    if (stream) {
      stream.getTracks().forEach(track => track.stop());
    }

    alert(cameraTalkErrorMessage(err));
    stopDashboardCameraTalk(deviceID, "start_failed");
  } finally {
    button.dataset.cameraTalkStarting = "0";
  }
}

function stopDashboardCameraTalk(
  buttonOrDeviceID,
  reason = "ended",
  useBeacon = false,
  notifyServer = true
) {
  const deviceID = typeof buttonOrDeviceID === "string"
    ? buttonOrDeviceID
    : String(buttonOrDeviceID?.dataset?.deviceId || "").trim();

  if (!deviceID) return;

  const session = window.androidCameraTalkSessions.get(deviceID);
  const button = session?.button || (
    buttonOrDeviceID instanceof Element
      ? buttonOrDeviceID
      : document.querySelector(`[data-camera-talk-button][data-device-id="${CSS.escape(deviceID)}"]`)
  );

  if (session) {
    if (session.stopping) return;

    session.stopping = true;

    if (session.pollTimer) {
      clearInterval(session.pollTimer);
      session.pollTimer = 0;
    }

    if (session.connectTimer) {
      clearTimeout(session.connectTimer);
      session.connectTimer = 0;
    }

    try {
      session.pc?.getSenders?.().forEach(sender => sender.track?.stop?.());
    } catch (_) {}

    try {
      session.stream?.getTracks?.().forEach(track => track.stop());
    } catch (_) {}

    try {
      session.pc?.close?.();
    } catch (_) {}

    window.androidCameraTalkSessions.delete(deviceID);

    if (notifyServer) {
      endCameraTalkSession(session.sessionID, reason, useBeacon).catch(err => {
        console.warn("Camera talk end failed", err);
      });
    }
  }

  if (button) {
    button.dataset.cameraTalkRequested = "0";
    button.dataset.cameraTalkStarting = "0";
    setCameraTalkButtonState(button, "idle");
  }
}

window.stopDashboardCameraTalk = stopDashboardCameraTalk;

function stopAllDashboardCameraTalk(
  reason = "ended",
  useBeacon = false,
  notifyServer = true
) {
  Array.from(window.androidCameraTalkSessions.keys()).forEach(deviceID => {
    stopDashboardCameraTalk(deviceID, reason, useBeacon, notifyServer);
  });

  document.querySelectorAll("[data-camera-talk-button]").forEach(button => {
    button.dataset.cameraTalkRequested = "0";
    button.dataset.cameraTalkStarting = "0";
    setCameraTalkButtonState(button, "idle");
  });
}

function toggleDashboardCameraTalkFromEvent(event) {
  const button = event.target.closest?.("[data-camera-talk-button]");

  if (!button || button.hasAttribute("disabled")) return;

  const eventType = String(event.type || "");
  const now = Date.now();

  if (eventType === "click") {
    const lastPointerToggleAt = Number(button.dataset.cameraTalkLastPointerToggleAt || 0);

    if (window.PointerEvent && now - lastPointerToggleAt < 650) {
      return;
    }
  } else if (eventType === "pointerdown") {
    button.dataset.cameraTalkLastPointerToggleAt = String(now);
  }

  event.preventDefault();
  event.stopPropagation();

  window.dashboardMarkInteraction?.();

  const deviceID = String(button.dataset.deviceId || "").trim();
  if (!deviceID) return;

  const isOnOrPending =
    window.androidCameraTalkSessions.has(deviceID) ||
    button.dataset.cameraTalkRequested === "1" ||
    button.dataset.cameraTalkActive === "1" ||
    button.dataset.cameraTalkPending === "1" ||
    button.dataset.cameraTalkStarting === "1";

  if (isOnOrPending) {
    stopDashboardCameraTalk(button, "toggled_off");
    return;
  }

  stopAllDashboardCameraTalk("switch_target");

  button.dataset.cameraTalkRequested = "1";

  try {
    if (event.pointerId !== undefined) {
      button.setPointerCapture?.(event.pointerId);
    }
  } catch (_) {}

  startDashboardCameraTalk(button);
}

if (!window.dashboardVoiceActionsBound) {
  window.dashboardVoiceActionsBound = true;

  document.addEventListener("pointerdown", toggleDashboardCameraTalkFromEvent, true);

  document.addEventListener("click", (event) => {
    if (event.detail !== 0 && window.PointerEvent) return;

    toggleDashboardCameraTalkFromEvent(event);
  }, true);

  window.addEventListener("pagehide", () => {
    stopAllDashboardCameraTalk("pagehide", true);
  });
}
