// Home-page News card. Reads KotiBot's own /api/rss/items route only; the
// browser never contacts a feed host. Feed text is untrusted, so every node is
// built with textContent and links are limited to http(s).
//
// One newest-first stream from every feed. Filter buttons (the same ones the
// Activity window uses) narrow it to articles, videos or audio; they appear
// only when the stream holds more than one kind.
(function () {
  const REFRESH_MS = 5 * 60 * 1000;
  const ROW_LIMIT = 12;
  const KINDS = [
    { key: "all", label: "All", icon: "koti-fa-bars-staggered" },
    { key: "article", label: "Articles", icon: "koti-fa-file-lines" },
    { key: "video", label: "Videos", icon: "koti-fa-video" },
    { key: "audio", label: "Audio", icon: "koti-fa-music" }
  ];

  let items = null;
  let kind = "all";
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
    const label = KINDS.find(entry => entry.key === item.kind);
    const minutes = Number(item.minutes);

    return [
      item.feed,
      item.kind === "video" || item.kind === "audio" ? label.label.replace(/s$/, "") : "",
      Number.isFinite(minutes) && minutes > 0 ? `${minutes} min` : "",
      age(item.published)
    ].filter(Boolean).join(" · ");
  }

  function row(item) {
    const href = safeLink(item.link);
    const wrap = el("div");
    const headline = el(href ? "a" : "span", href ? "dashboard-home-media-link" : "", item.title);

    if (href) {
      headline.href = href;
      headline.target = "_blank";
      headline.rel = "noopener noreferrer";
    }

    wrap.appendChild(headline);
    wrap.appendChild(el("div", "dashboard-home-subtitle", subtitle(item)));

    return wrap;
  }

  function filters(present) {
    const group = el("div", "dashboard-activity-filters");

    group.setAttribute("aria-label", "News type");

    KINDS.filter(entry => entry.key === "all" || present.has(entry.key)).forEach(entry => {
      const button = el("button", `dashboard-activity-filter${entry.key === kind ? " active" : ""}`);

      button.type = "button";
      button.title = entry.label;
      button.setAttribute("aria-label", entry.label);
      button.setAttribute("aria-pressed", entry.key === kind ? "true" : "false");
      button.dataset.dashboardAction = "news-filter";
      button.dataset.newsKind = entry.key;
      button.appendChild(el("span", `koti-icon ${entry.icon}`));
      group.appendChild(button);
    });

    return group;
  }

  function render(section) {
    if (!items || !items.length) {
      section.hidden = true;
      section.replaceChildren();
      delete section.dataset.shelfSignature;
      return;
    }

    const present = new Set(items.map(item => item.kind));

    if (kind !== "all" && !present.has(kind)) kind = "all";

    const signature = JSON.stringify([kind, items]);

    section.hidden = false;

    if (section.dataset.shelfSignature === signature) return;

    const head = el("div", "dashboard-home-section-head");
    const parts = [head];

    head.appendChild(el("h2", "dashboard-home-section-title", "News"));

    if (present.size > 1) parts.push(filters(present));

    items
      .filter(item => kind === "all" || item.kind === kind)
      .slice(0, ROW_LIMIT)
      .forEach(item => parts.push(row(item)));

    section.replaceChildren(...parts);
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

  window.setDashboardNewsKind = function (value) {
    kind = KINDS.some(entry => entry.key === value) ? value : "all";

    const live = document.querySelector("[data-home-news-shelf]");

    if (live) render(live);
  };

  // Called after the feed list changes so the card does not wait for the timer.
  window.refreshDashboardHomeNewsShelf = function () {
    loadedAt = 0;

    const live = document.querySelector("[data-home-news-shelf]");

    if (live) window.syncDashboardHomeNewsShelf(live.closest(".dashboard-home"));
  };
})();
