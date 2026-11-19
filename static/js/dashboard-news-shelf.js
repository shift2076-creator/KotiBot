// Home-page News card. Reads KotiBot's own /api/rss/items route only; the
// browser never contacts a feed host. Feed text is untrusted, so every node is
// built with textContent and links are limited to http(s).
//
// One newest-first stream from every feed. Each row starts with the favicon of
// the site the item links to (served by KotiBot, never fetched by the browser)
// and ends with a small icon for what the item is (article, video or audio);
// the kind comes from the feed's own data or from the Type set for the feed in
// Settings.
(function () {
  const REFRESH_MS = 5 * 60 * 1000;
  const ROW_LIMIT = 12;
  const KINDS = {
    article: { label: "Article", icon: "koti-fa-file-lines" },
    video: { label: "Video", icon: "koti-fa-circle-play" },
    audio: { label: "Audio", icon: "koti-fa-music" }
  };

  let items = null;
  let loadedAt = 0;
  let inFlight = null;

  function load() {
    if (inFlight) return inFlight;

    if (loadedAt && Date.now() - loadedAt < REFRESH_MS) {
      return Promise.resolve();
    }

    inFlight = fetch("/api/rss/items", {
      cache: "no-store",
      credentials: "same-origin"
    })
      .then(res => (res.ok ? res.json() : null))
      .then(data => {
        items = data && Array.isArray(data.items) ? data.items : null;
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

  function age(iso) {
    const then = Date.parse(iso);

    if (!Number.isFinite(then)) return "";

    const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));

    if (minutes < 60) return `${Math.max(1, minutes)}m`;
    if (minutes < 1440) return `${Math.floor(minutes / 60)}h`;

    return `${Math.floor(minutes / 1440)}d`;
  }

  function safeLink(value) {
    try {
      const url = new URL(String(value || ""));

      return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
    } catch (err) {
      return "";
    }
  }

  function subtitle(item) {
    const minutes = Number(item.minutes);

    return [
      item.feed,
      item.kind !== "article" && Number.isFinite(minutes) && minutes > 0 ? `${minutes} min` : "",
      age(item.published)
    ].filter(Boolean).join(" · ");
  }

  // Only KotiBot's own icon route is ever used as an image source.
  function safeIcon(value) {
    return typeof value === "string" && /^\/api\/rss\/icon\/[a-z0-9.-]+$/.test(value) ? value : "";
  }

  function globe() {
    const tile = el("span", "dashboard-home-news-favicon is-fallback");

    tile.appendChild(el("span", "koti-icon koti-fa-globe"));

    return tile;
  }

  function favicon(item) {
    const src = safeIcon(item.icon);

    if (!src) return globe();

    const img = el("img", "dashboard-home-news-favicon");

    img.src = src;
    img.alt = "";
    img.loading = "lazy";
    img.decoding = "async";
    img.addEventListener("error", () => img.replaceWith(globe()));

    return img;
  }

  function row(item) {
    const href = safeLink(item.link);
    const wrap = el("div", "dashboard-home-news-row");
    const body = el("div");
    const headline = el(href ? "a" : "span", href ? "dashboard-home-media-link" : "", item.title);
    // The section-head row centres the icon against the text; the subtitle class keeps the text green.
    const line = el("div", "dashboard-home-section-head");
    const kind = KINDS[item.kind] || KINDS.article;
    const icon = el("span", `koti-icon dashboard-home-news-kind ${kind.icon}`);

    if (href) {
      headline.href = href;
      headline.target = "_blank";
      headline.rel = "noopener noreferrer";
    }

    icon.title = kind.label;
    icon.setAttribute("role", "img");
    icon.setAttribute("aria-label", kind.label);
    line.appendChild(el("span", "dashboard-home-subtitle", subtitle(item)));
    line.appendChild(icon);
    body.appendChild(headline);
    body.appendChild(line);
    wrap.appendChild(favicon(item));
    wrap.appendChild(body);

    return wrap;
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

    const watermark = el("span", "koti-icon koti-fa-rss dashboard-home-watermark");

    watermark.setAttribute("aria-hidden", "true");
    section.replaceChildren(watermark, ...items.slice(0, ROW_LIMIT).map(row));
    section.dataset.shelfSignature = signature;
  }

  window.syncDashboardHomeNewsShelf = function (home) {
    const section = home && home.querySelector("[data-home-news-shelf]");

    if (!section) return;

    render(section);

    load().then(() => {
      const live = document.querySelector("[data-home-news-shelf]");

      if (live) render(live);
    });
  };

  // Called after the feed list changes so the card does not wait for the timer.
  window.refreshDashboardHomeNewsShelf = function () {
    loadedAt = 0;

    const live = document.querySelector("[data-home-news-shelf]");

    if (live) window.syncDashboardHomeNewsShelf(live.closest(".dashboard-home"));
  };
})();
