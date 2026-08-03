"use strict";

window.createCameraTalkSession = async function ({ targetDeviceID, sourceDeviceID = "" }) {
  return await postJson("/api/voice/session", {
    targetDeviceID,
    sourceDeviceID
  });
};

window.postCameraTalkOffer = async function (sessionID, offer) {
  return await postJson(`/api/voice/session/${encodeURIComponent(sessionID)}/offer`, {
    offer
  });
};

window.postCameraTalkDashboardCandidate = async function (sessionID, candidate) {
  return await postJson(`/api/voice/session/${encodeURIComponent(sessionID)}/candidate`, {
    candidate
  });
};

window.getCameraTalkSession = async function (sessionID) {
  const res = await dashboardFetch(`/api/voice/session/${encodeURIComponent(sessionID)}`, {
    method: "GET",
    cache: "no-store"
  });

  const text = await res.text();
  const data = text ? JSON.parse(text) : {};

  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `Voice session failed: ${res.status}`);
  }

  return data;
};

window.endCameraTalkSession = async function (sessionID, reason = "", useBeacon = false) {
  if (!sessionID) return { ok: true };

  const payload = JSON.stringify({ reason });

  if (useBeacon && navigator.sendBeacon) {
    navigator.sendBeacon(
      `/api/voice/session/${encodeURIComponent(sessionID)}/end`,
      new Blob([payload], { type: "application/json" })
    );

    return { ok: true };
  }

  return await postJson(`/api/voice/session/${encodeURIComponent(sessionID)}/end`, {
    reason
  });
};
