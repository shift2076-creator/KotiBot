// Home-page News card. Reads KotiBot's own /api/rss/items route only; the
// browser never contacts a feed host. Feed text is untrusted, so every node is
// built with textContent and links are limited to http(s).
(function () {
  const REFRESH_MS = 5 * 60 * 1000;

  let groups = null;
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
        groups = data && Array.isArray(data.groups) ? data.groups : null;
      })
      .catch(() => {
        groups = null;
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

  function host(link) {
    try {
      return new URL(link).hostname.replace(/^www\./, "");
    } catch (err) {
      return "";
    }
  }

  // Same row layout as the Recent Automation Activity list: icon, source,
  // headline, age. Only the headline is a link, so no link styling leaks.
  function row(item, feedTitle) {
    const href = safeLink(item.link);
    const article = el("div", "dashboard-activity-item");
    const copy = el("span", "dashboard-activity-copy");
    const event = el("span", "dashboard-activity-event-copy");
    const headline = el(href ? "a" : "span", href ? "dashboard-activity-event dashboard-home-media-link" : "dashboard-activity-event", item.title);

    if (href) {
      headline.href = href;
      headline.target = "_blank";
      headline.rel = "noopener noreferrer";
    }

    article.appendChild(el("span", "koti-icon koti-fa-globe dashboard-activity-icon dashboard-activity-icon-system"));
    copy.appendChild(el("span", "dashboard-activity-name", host(href) || feedTitle));
    article.appendChild(copy);
    event.appendChild(headline);
    article.appendChild(event);
    article.appendChild(el("span", "dashboard-activity-time", age(item.published)));

    return article;
  }

  function render(section) {
    if (!groups || !groups.length) {
      section.hidden = true;
      section.replaceChildren();
      delete section.dataset.shelfSignature;
      return;
    }

    const signature = JSON.stringify(groups);

    section.hidden = false;

    if (section.dataset.shelfSignature === signature) return;

    const head = el("div", "dashboard-home-section-head");

    head.appendChild(el("h2", "dashboard-home-section-title", "News"));

    const parts = [head];

    groups.forEach(group => {
      const block = el("div");

      block.appendChild(el("h3", "modal-section-title", group.title));
      group.items.forEach(item => block.appendChild(row(item, group.title)));
      parts.push(block);
    });

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

  // Called after the feed list changes so the card does not wait for the timer.
  window.refreshDashboardHomeNewsShelf = function () {
    loadedAt = 0;

    const live = document.querySelector("[data-home-news-shelf]");

    if (live) window.syncDashboardHomeNewsShelf(live.closest(".dashboard-home"));
  };
})();
