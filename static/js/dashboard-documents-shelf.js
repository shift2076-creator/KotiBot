// Home-page Documents card. Reads KotiBot's own /api/shelves/paperless route
// only; the browser never talks to Paperless and never holds a Paperless token.
// KotiBot asks Paperless as the signed-in person, so each person sees only their
// own documents. Document text is untrusted, so every node is built with
// textContent and links are built here from numeric ids.
//
// The first page comes in the HTML (window.KOTIBOT_DOCS_BOOTSTRAP), so the card
// is drawn on the first frame. Without it the card is blocked out at its final
// size and the rows fade in.
(function () {
  const REFRESH_MS = 60 * 1000;
  const BATCH = 10;
  const MORE_PX = 160;
  const SEARCH_MS = 250;
  const PAPERLESS_PORT = "8085";
  const TABS = [
    { id: "added", label: "Added" },
    { id: "edited", label: "Edited" },
    { id: "favs", label: "Favs" }
  ];

  let items = null;
  let loaded = false;
  let available = true;
  let animateRows = true;
  let tab = "added";
  let query = "";
  let inbox = 0;
  let hasMore = false;
  let linkBase = "";
  let loadingMore = false;
  let loadedAt = 0;
  let inFlight = null;
  let token = 0;
  let ui = null;
  let listSignature = "";
  let rowCache = new Map();
  let scrollTop = 0;
  let searchTimer = 0;
  let searchFocused = false;

  function el(tag, className, text) {
    const node = document.createElement(tag);

    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;

    return node;
  }

  function icon(name) {
    return el("span", `koti-icon koti-fa-${name}`);
  }

  function fadeIn(node) {
    if (typeof window.dashboardFadeIn === "function") window.dashboardFadeIn(node);
  }

  function age(value) {
    const then = Date.parse(value);

    if (!Number.isFinite(then)) return "";

    const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));

    if (minutes < 2) return "just now";
    if (minutes < 60) return `${minutes} min ago`;
    if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;

    return `${Math.round(minutes / 1440)} d ago`;
  }

  function subtitle(item) {
    const when = tab === "edited" ? `edited ${age(item.modified)}` : age(item.added);

    return [item.correspondent, item.type, when.trim()].filter(Boolean).join(" · ");
  }

  function paperlessUrl(path) {
    // The address the server was told people use (KOTIBOT_PAPERLESS_PUBLIC_URL); else the old host:port guess.
    return `${linkBase || `https://${window.location.hostname}:${PAPERLESS_PORT}`}${path}`;
  }

  // --- data ------------------------------------------------------------------

  function apply(data) {
    loaded = true;

    if (!data || data.available !== true || !Array.isArray(data.items)) {
      // Keep what is showing when a refresh fails; hide the card only when there is nothing.
      if (!items) available = Boolean(data && data.available === true);

      return;
    }

    available = true;
    items = data.items;
    hasMore = Boolean(data.has_more);
    inbox = Number(data.inbox_count) || 0;
    linkBase = /^https?:\/\/[^\s]+$/.test(String(data.link_base || "")) ? String(data.link_base).replace(/\/+$/, "") : "";
  }

  function takeBootstrap() {
    const boot = window.KOTIBOT_DOCS_BOOTSTRAP;

    window.KOTIBOT_DOCS_BOOTSTRAP = null;

    if (!boot || boot.ready !== true) return;

    if (boot.available !== true) {
      loaded = true;
      available = false;
      loadedAt = Date.now();
      return;
    }

    apply(boot);
    loadedAt = Date.now();
    animateRows = false;
  }

  function url(limit, offset) {
    const text = query.trim();

    return `/api/shelves/paperless/documents?tab=${tab}&limit=${limit}&offset=${offset}${text ? `&q=${encodeURIComponent(text)}` : ""}`;
  }

  function fetchPage(limit, offset) {
    return fetch(url(limit, offset), { cache: "no-store", credentials: "same-origin" })
      .then(res => (res.ok ? res.json() : null))
      .catch(() => null);
  }

  // Loads the first batch, or reloads as many rows as already show.
  function load(force) {
    if (inFlight) return inFlight;

    if (!force && loadedAt && Date.now() - loadedAt < REFRESH_MS) return Promise.resolve();

    const mine = ++token;

    inFlight = fetchPage(Math.max(BATCH, items ? items.length : 0), 0)
      .then(data => {
        if (mine === token) apply(data);
      })
      .finally(() => {
        loaded = true;
        loadedAt = Date.now();
        inFlight = null;
      });

    return inFlight;
  }

  function loadMore() {
    if (!hasMore || loadingMore || !items) return;

    const mine = token;

    loadingMore = true;
    renderList();

    fetchPage(BATCH, items.length).then(data => {
      loadingMore = false;

      if (mine === token && data && data.available === true && Array.isArray(data.items)) {
        const known = new Set(items.map(row => row.id));

        items = items.concat(data.items.filter(row => !known.has(row.id)));
        hasMore = Boolean(data.has_more) && data.items.length > 0;
      } else {
        hasMore = false;
      }

      renderList();
    });
  }

  function reload() {
    items = null;
    hasMore = false;
    loadedAt = 0;
    scrollTop = 0;
    listSignature = "";
    token += 1;
    inFlight = null;
    renderList();

    load(true).then(() => {
      renderList();
      renderBar();
    });
  }

  // --- view ------------------------------------------------------------------

  function row(item, previous) {
    const wrap = el("div", "dashboard-home-news-row");
    const body = el("div");
    const headline = el("a", "dashboard-home-media-link dashboard-home-news-title", item.title);
    const line = el("div", "dashboard-home-section-head");
    const tile = previous && previous.children && previous.children[0];

    wrap.setAttribute("role", "listitem");
    headline.href = paperlessUrl(`/documents/${Number(item.id)}/details`);
    headline.target = "_blank";
    headline.rel = "noopener noreferrer";
    line.appendChild(el("span", "dashboard-home-subtitle", subtitle(item)));

    if (item.favorite) {
      const star = el("span", "koti-icon dashboard-home-news-kind koti-fa-star");

      star.title = "Favorite";
      star.setAttribute("role", "img");
      star.setAttribute("aria-label", "Favorite");
      line.appendChild(star);
    }

    body.appendChild(headline);
    body.appendChild(line);

    const fresh = el("span", "dashboard-home-news-favicon is-fallback");

    fresh.appendChild(icon("file-lines"));
    wrap.appendChild(tile || fresh);
    wrap.appendChild(body);

    return wrap;
  }

  function rowFor(item, cache) {
    const signature = JSON.stringify([tab, item, subtitle(item)]);
    const known = rowCache.get(item.id);
    const node = known && known.signature === signature ? known.node : row(item, known && known.node);

    if (!known && animateRows) fadeIn(node);

    cache.set(item.id, { signature, node });

    return node;
  }

  function syncChildren(parent, nodes) {
    if (!parent.insertBefore) {
      parent.replaceChildren(...nodes);
      return;
    }

    const wanted = new Set(nodes);

    Array.from(parent.children).forEach(child => {
      if (!wanted.has(child)) parent.removeChild(child);
    });
    nodes.forEach((node, index) => {
      if (parent.children[index] !== node) parent.insertBefore(node, parent.children[index] || null);
    });
  }

  function emptyText() {
    if (query.trim()) return "No matches";
    if (tab === "favs") return "No favorites yet";

    return "No documents yet";
  }

  function renderList() {
    if (!ui) return;

    const shown = items || [];
    const signature = JSON.stringify([tab, query, loadingMore, shown]);

    if (signature === listSignature) return;

    listSignature = signature;

    const more = loadingMore ? [el("p", "dashboard-home-news-empty", "Loading more…")] : [];
    const cache = new Map();
    const nodes = shown.length
      ? shown.map(item => rowFor(item, cache)).concat(more)
      : [el("p", "dashboard-home-news-empty", items ? emptyText() : "")];

    rowCache = cache;
    syncChildren(ui.list, nodes);
    ui.list.scrollTop = scrollTop;

    if (loaded) animateRows = true;
  }

  function renderBar() {
    if (!ui) return;

    ui.inboxCount.textContent = String(inbox);
    ui.inboxLink.hidden = inbox < 1;
    ui.tabs.forEach(entry => entry.button.setAttribute("aria-pressed", String(entry.id === tab)));
  }

  function nearEnd() {
    return ui.list.scrollHeight - ui.list.scrollTop - ui.list.clientHeight < MORE_PX;
  }

  function build(section) {
    const tabs = el("div", "dashboard-home-docs-tabs");
    const list = el("div", "dashboard-home-news-list");
    const bar = el("div", loaded ? "dashboard-home-news-bar" : "dashboard-home-news-bar is-pending");
    const label = el("label", "dashboard-home-news-search");
    const input = el("input", "dashboard-home-news-search-input");
    const inboxLink = el("a", "dashboard-home-news-toggle");
    const inboxCount = el("span", "", "0");
    const buttons = TABS.map(entry => {
      const button = el("button", "dashboard-home-docs-tab", entry.label);

      button.type = "button";
      button.setAttribute("aria-pressed", String(entry.id === tab));
      button.addEventListener("click", () => {
        if (tab === entry.id) return;

        tab = entry.id;
        reload();
        renderBar();
      });
      tabs.appendChild(button);

      return { id: entry.id, button };
    });

    list.setAttribute("role", "list");
    list.addEventListener("scroll", () => {
      scrollTop = list.scrollTop;

      if (nearEnd()) loadMore();
    });

    input.type = "search";
    input.placeholder = "Search documents";
    input.value = query;
    input.setAttribute("aria-label", "Search documents");
    input.addEventListener("input", () => {
      query = input.value;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(reload, SEARCH_MS);
    });
    input.addEventListener("focus", () => {
      searchFocused = true;
    });
    input.addEventListener("blur", () => {
      if (input.isConnected !== false) searchFocused = false;
    });

    inboxLink.href = paperlessUrl("/documents");
    inboxLink.target = "_blank";
    inboxLink.rel = "noopener noreferrer";
    inboxLink.title = "Documents waiting in the Paperless inbox";
    inboxLink.setAttribute("aria-label", "Documents waiting in the Paperless inbox");
    inboxLink.appendChild(icon("folder-plus"));
    inboxLink.appendChild(inboxCount);

    label.appendChild(icon("magnifying-glass"));
    label.appendChild(input);
    bar.appendChild(label);
    bar.appendChild(inboxLink);

    section.replaceChildren(tabs, list, bar);
    ui = { section, list, bar, input, inboxLink, inboxCount, tabs: buttons };
    listSignature = "";
    rowCache = new Map();
    section.dataset.docsBuilt = "1";

    if (searchFocused && input.focus) {
      setTimeout(() => {
        input.focus();
        if (input.setSelectionRange) input.setSelectionRange(input.value.length, input.value.length);
      }, 0);
    }
  }

  function render(section) {
    if (loaded && !available && !items) {
      section.hidden = true;
      section.replaceChildren();
      delete section.dataset.docsBuilt;
      ui = null;
      return;
    }

    section.hidden = false;

    if (!ui || ui.section !== section || !section.dataset.docsBuilt) build(section);

    if (!loaded) return;

    if (ui.bar.className.includes("is-pending")) {
      ui.bar.className = ui.bar.className.replace(/\s*is-pending/, "");
      fadeIn(ui.bar);
    }

    renderList();
    renderBar();
  }

  takeBootstrap();

  window.syncDashboardHomeDocumentsShelf = function (home) {
    const section = home && home.querySelector("[data-home-docs-shelf]");

    if (!section) return;

    render(section);

    load().then(() => {
      const live = document.querySelector("[data-home-docs-shelf]");

      if (live) render(live);
    });
  };
})();
