// Home-page media shelves. Reads KotiBot's own /api/shelves/* routes only;
// the browser never talks to Jellyfin and never holds one of its tokens.
(function () {
  const REFRESH_MS = 30000;

  let items = null;
  let loadedAt = 0;
  let inFlight = null;

  function load() {
    if (inFlight) return inFlight;

    if (loadedAt && Date.now() - loadedAt < REFRESH_MS) {
      return Promise.resolve();
    }

    inFlight = fetch("/api/shelves/jellyfin/continue", {
      cache: "no-store",
      credentials: "same-origin"
    })
      .then(res => (res.ok ? res.json() : null))
      .then(data => {
        items = data && data.available && Array.isArray(data.items)
          ? data.items
          : null;
      })
      .catch(() => {
        items = null;
      })
      .finally(() => {
        loadedAt = Date.now();
        inFlight = null;
      });

    return inFlight;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);

    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;

    return node;
  }

  function timeLeft(minutes) {
    if (!Number.isFinite(minutes) || minutes < 1) return "";

    return minutes >= 60
      ? `${Math.floor(minutes / 60)}h ${minutes % 60}m left`
      : `${minutes}m left`;
  }

  // Jellyfin is served by Caddy on the same host, port 8096. The id was
  // validated as hex by the server; it is checked again before use.
  function detailsUrl(id) {
    if (!/^[0-9a-f]{32}$/.test(String(id || ""))) return "";

    return `${location.protocol}//${location.hostname}:8096/web/#/details?id=${id}`;
  }

  function card(item) {
    const li = el("li", "dashboard-home-media-card");
    const href = detailsUrl(item.id);
    const link = el(href ? "a" : "div", "dashboard-home-media-link");

    if (href) {
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }

    li.appendChild(link);
    const poster = el("div", "dashboard-home-media-poster");
    const initial = el(
      "span",
      "dashboard-home-media-initial",
      String(item.title || "?").charAt(0).toUpperCase()
    );

    initial.setAttribute("aria-hidden", "true");
    poster.appendChild(initial);

    if (item.image) {
      const img = el("img", "dashboard-home-media-image");

      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      img.addEventListener("error", () => img.remove());
      img.src = item.image;
      poster.appendChild(img);
    }

    const percent = Math.max(0, Math.min(100, Number(item.percent) || 0));
    const bar = el("div", "dashboard-home-media-progress");
    const fill = el("span");

    fill.style.width = `${percent}%`;
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", "100");
    bar.setAttribute("aria-valuenow", String(percent));
    bar.setAttribute("aria-label", `${item.title} progress`);
    bar.appendChild(fill);
    poster.appendChild(bar);

    link.appendChild(poster);
    link.appendChild(el("div", "dashboard-home-media-title", item.title));

    const meta = [item.subtitle, timeLeft(item.minutes_left) || `${percent}%`]
      .filter(Boolean)
      .join(" · ");

    link.appendChild(el("div", "dashboard-home-media-meta", meta));

    return li;
  }

  function render(section) {
    if (!items || !items.length) {
      section.hidden = true;
      section.replaceChildren();
      delete section.dataset.shelfSignature;
      return;
    }

    const signature = JSON.stringify(items);

    section.hidden = false;

    if (section.dataset.shelfSignature === signature) return;

    const watermark = el("span", "koti-icon koti-fa-film dashboard-home-watermark");
    const list = el("ul", "dashboard-home-media-row");

    watermark.setAttribute("aria-hidden", "true");
    items.forEach(item => list.appendChild(card(item)));

    section.replaceChildren(watermark, list);
    section.dataset.shelfSignature = signature;
  }

  window.syncDashboardHomeMediaShelf = function (home) {
    const section = home && home.querySelector("[data-home-media-shelf]");

    if (!section) return;

    render(section);

    load().then(() => {
      const live = document.querySelector("[data-home-media-shelf]");

      if (live) render(live);
    });
  };
})();
