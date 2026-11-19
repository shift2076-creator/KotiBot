// Home-page media shelves. Reads KotiBot's own /api/shelves/* routes only;
// the browser never talks to Jellyfin and never holds one of its tokens.
(function () {
  const REFRESH_MS = 30000;

  let items = null;
  let index = 0;
  let shownId = "";
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

  function lengthText(minutes) {
    if (!Number.isFinite(minutes) || minutes < 1) return "";

    return minutes >= 60
      ? `${Math.floor(minutes / 60)}h ${minutes % 60}m`
      : `${minutes}m`;
  }

  function icon(name, extra) {
    const node = el("span", `koti-icon koti-fa-${name}${extra ? ` ${extra}` : ""}`);

    node.setAttribute("aria-hidden", "true");

    return node;
  }

  // Same component as the Scenes and Security buttons: a circle with an icon
  // and a label under it.
  function control(tag, iconName, label, className) {
    const node = el(tag, `settings-item dashboard-home-light-btn power-toggle ${className || ""}`.trim());
    const circle = el("span", "ui-icon-circle dashboard-home-mode-circle");

    circle.appendChild(icon(iconName, "dashboard-home-mode-icon"));
    node.appendChild(circle);
    node.appendChild(el("span", "", label));

    if (tag === "button") node.type = "button";

    return node;
  }

  function poster(item) {
    const box = el("div", "dashboard-home-nowplaying-poster");
    const initial = el(
      "span",
      "dashboard-home-media-initial",
      String(item.title || "?").charAt(0).toUpperCase()
    );

    initial.setAttribute("aria-hidden", "true");
    box.appendChild(initial);

    if (item.image) {
      const img = el("img", "dashboard-home-media-image");

      img.alt = "";
      img.decoding = "async";
      img.addEventListener("error", () => img.remove());
      img.src = item.image;
      box.appendChild(img);
    }

    return box;
  }

  function percentOf(item) {
    return Math.max(0, Math.min(100, Number(item.percent) || 0));
  }

  function postReset(id) {
    const send = typeof window.dashboardFetch === "function"
      ? window.dashboardFetch
      : (url, options) => fetch(url, { credentials: "same-origin", ...options });

    return send(`/api/shelves/jellyfin/progress/${id}/reset`, { method: "POST" })
      .then(res => !!(res && res.ok))
      .catch(() => false);
  }

  function refreshNow(section) {
    loadedAt = 0;

    return load().then(() => {
      const live = document.querySelector("[data-home-media-shelf]");

      if (live) render(live);
    });
  }

  function tile(section, item) {
    const href = detailsUrl(item.id);
    const main = el("div", "dashboard-home-nowplaying-main");
    const head = el("div", "dashboard-home-nowplaying-head");
    const brand = el("span", "ui-icon-circle dashboard-home-mode-circle dashboard-home-nowplaying-brand");
    const title = el("h2", "dashboard-home-nowplaying-title", item.title);
    const afterTitle = item.year ? String(item.year) : item.subtitle;

    brand.appendChild(icon("circle-play", "dashboard-home-mode-icon"));
    head.appendChild(brand);
    head.appendChild(title);

    if (afterTitle) head.appendChild(el("span", "dashboard-home-nowplaying-year", afterTitle));

    main.appendChild(head);

    if (item.overview) {
      main.appendChild(el("p", "dashboard-home-nowplaying-overview", item.overview));
    }

    const length = lengthText(item.runtime_minutes);
    const left = timeLeft(item.minutes_left) || `${percentOf(item)}%`;

    main.appendChild(el("div", "dashboard-home-nowplaying-meta", [length, left].filter(Boolean).join(" · ")));

    const controls = el("div", "dashboard-home-nowplaying-controls");
    const resume = control(href ? "a" : "button", "play", "Resume", "is-primary");

    if (href) {
      resume.href = href;
      resume.target = "_blank";
      resume.rel = "noopener noreferrer";
    } else {
      resume.disabled = true;
    }

    const restart = control("button", "rotate", "Restart");
    const remove = control("button", "xmark", "Remove");

    restart.addEventListener("click", () => {
      restart.disabled = true;
      postReset(item.id).then(ok => {
        if (ok && href) window.open(href, "_blank", "noopener,noreferrer");
        return refreshNow(section);
      });
    });

    remove.addEventListener("click", () => {
      remove.disabled = true;
      postReset(item.id).then(() => refreshNow(section));
    });

    controls.append(resume, restart, remove);
    main.appendChild(controls);

    const wrap = el("div", "dashboard-home-nowplaying");
    const art = poster(item);
    const bar = el("div", "dashboard-home-media-progress");
    const fill = el("span");

    fill.style.width = `${percentOf(item)}%`;
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", "100");
    bar.setAttribute("aria-valuenow", String(percentOf(item)));
    bar.setAttribute("aria-label", `${item.title} progress`);
    bar.appendChild(fill);
    art.appendChild(bar);
    wrap.append(main, art);

    return wrap;
  }

  function nav(section, count) {
    const bar = el("nav", "dashboard-home-nowplaying-nav");
    const show = position => {
      index = position;
      shownId = items[position].id;
      render(section);
    };
    const step = delta => () => show((index + delta + count) % count);
    const prev = el("button", "dashboard-home-nowplaying-step");
    const next = el("button", "dashboard-home-nowplaying-step");
    const segments = el("div", "dashboard-home-nowplaying-segments");

    bar.setAttribute("aria-label", "Now playing");

    [[prev, "chevron-left", "Previous title", -1], [next, "chevron-right", "Next title", 1]]
      .forEach(([button, name, label, delta]) => {
        button.type = "button";
        button.setAttribute("aria-label", label);
        button.appendChild(icon(name));
        button.addEventListener("click", step(delta));
      });

    items.forEach((entry, position) => {
      const segment = el("button", "dashboard-home-nowplaying-segment");
      const track = el("span", "dashboard-home-nowplaying-track");
      const fill = el("span");

      segment.type = "button";
      segment.setAttribute("aria-label", entry.title);
      if (position === index) {
        segment.classList.add("is-current");
        segment.setAttribute("aria-current", "true");
      }
      fill.style.width = `${percentOf(entry)}%`;
      track.appendChild(fill);
      segment.appendChild(track);
      segment.addEventListener("click", () => show(position));
      segments.appendChild(segment);
    });

    bar.append(prev, segments, next);

    return bar;
  }

  function render(section) {
    if (!items || !items.length) {
      section.hidden = true;
      section.replaceChildren();
      delete section.dataset.shelfSignature;
      index = 0;
      shownId = "";
      return;
    }

    const kept = items.findIndex(entry => entry.id === shownId);

    if (kept >= 0) index = kept;
    if (index >= items.length || index < 0) index = 0;

    shownId = items[index].id;

    const signature = JSON.stringify([items, index]);

    section.hidden = false;

    if (section.dataset.shelfSignature === signature) return;

    const parts = [tile(section, items[index])];

    if (items.length > 1) parts.push(nav(section, items.length));

    section.replaceChildren(...parts);
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
