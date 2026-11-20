// Home-page News card. Reads KotiBot's own /api/rss routes only; the browser
// never contacts a feed host. Feed text is untrusted, so every node is built
// with textContent and links are limited to http(s).
//
// One newest-first stream from every feed in a scrolling list sized for five
// two-line entries. It loads a few rows at a time as the list is scrolled, and
// the search box at the bottom searches the whole stream, not just what has
// loaded. Each row starts with the
// favicon of the site the item links to (served by KotiBot, never fetched by the
// browser) and ends with a small icon for what the item is (article, video or
// audio). Each signed-in user can hide an entry from their own feed and save it
// to one of their own folders; both are kept by KotiBot per user.
(function () {
  const REFRESH_MS = 5 * 60 * 1000;
  const BATCH = 10;
  const MORE_PX = 160;
  const SEARCH_MS = 250;
  // A site icon the server had not fetched yet is asked for again, twice.
  const ICON_RETRY_MS = [4000, 20000];
  const TOAST_MS = 5000;
  const DEFAULT_FOLDER = "Read later";
  const FOLDER_NAME_LIMIT = 40;
  const KINDS = {
    article: { label: "Article", icon: "koti-fa-file-lines" },
    video: { label: "Video", icon: "koti-fa-circle-play" },
    audio: { label: "Audio", icon: "koti-fa-music" }
  };

  let items = null;
  let loadedAt = 0;
  let inFlight = null;
  // Counts and folder names that come with the feed.
  let meta = { hidden: 0, saved: 0, folders: [DEFAULT_FOLDER] };
  // "feed", "hidden" or "saved"; the last two show their own list.
  let mode = "feed";
  let sideItems = [];
  let query = "";
  let picking = "";
  let naming = false;
  let undo = null;
  let toastTimer = 0;
  let ui = null;
  let scrollTop = 0;
  let searchFocused = false;
  let listSignature = "";
  let rowCache = new Map();
  let hasMore = false;
  let loadingMore = false;
  let feedToken = 0;
  let searchTimer = 0;

  function applyFeed(data) {
    items = data && Array.isArray(data.items) ? data.items : null;
    hasMore = Boolean(data && data.has_more);

    if (!data) return;

    meta = {
      hidden: Number(data.hidden_count) || 0,
      saved: Number(data.saved_count) || 0,
      folders: Array.isArray(data.folders) && data.folders.length ? data.folders.map(String) : [DEFAULT_FOLDER]
    };
  }

  function feedUrl(limit, offset) {
    const text = query.trim();

    return `/api/rss/items?limit=${limit}&offset=${offset}${text ? `&q=${encodeURIComponent(text)}` : ""}`;
  }

  // Loads the first batch, or reloads as many rows as are already showing so a
  // refresh does not throw away how far the person has scrolled.
  function load() {
    if (inFlight) return inFlight;

    if (loadedAt && Date.now() - loadedAt < REFRESH_MS) {
      return Promise.resolve();
    }

    const token = ++feedToken;

    inFlight = fetch(feedUrl(Math.max(BATCH, items ? items.length : 0), 0), {
      cache: "no-store",
      credentials: "same-origin"
    })
      .then(res => (res.ok ? res.json() : null))
      .then(data => {
        if (token === feedToken) applyFeed(data);
      })
      .catch(() => {
        if (token === feedToken) items = null;
      })
      .finally(() => {
        loadedAt = Date.now();
        inFlight = null;
      });

    return inFlight;
  }

  // The next batch, appended when the list is scrolled near its end.
  function loadMore() {
    if (mode !== "feed" || !hasMore || loadingMore || !items) return;

    const token = feedToken;

    loadingMore = true;
    renderList();

    send(feedUrl(BATCH, items.length)).then(result => {
      loadingMore = false;

      if (token !== feedToken || mode !== "feed") {
        renderList();
        return;
      }

      if (result.ok && Array.isArray(result.data.items)) {
        const known = new Set(items.map(row => row.id));

        items = items.concat(result.data.items.filter(row => !known.has(row.id)));
        hasMore = Boolean(result.data.has_more) && result.data.items.length > 0;
      } else {
        hasMore = false;
      }

      renderList();
      fillIfShort();
    });
  }

  // A search starts the stream again from the top, on the server.
  function searchFeed() {
    const token = ++feedToken;

    scrollTop = 0;
    loadingMore = false;

    send(feedUrl(BATCH, 0)).then(result => {
      if (token !== feedToken) return;

      if (result.ok) applyFeed(result.data);

      loadedAt = Date.now();
      renderList();
      renderBar();
      fillIfShort();
    });
  }

  function nearEnd() {
    return ui && ui.list.scrollHeight - ui.list.scrollTop - ui.list.clientHeight < MORE_PX;
  }

  // If the rows loaded so far do not fill the list, there is nothing to scroll.
  function fillIfShort() {
    if (ui && hasMore && mode === "feed" && ui.list.clientHeight > 0 && ui.list.scrollHeight <= ui.list.clientHeight) {
      loadMore();
    }
  }

  function send(url, body) {
    const options = body === undefined
      ? { cache: "no-store", credentials: "same-origin" }
      : {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      };
    const call = typeof window.dashboardFetch === "function" ? window.dashboardFetch : fetch;

    return call(url, options)
      .then(res => res.json().catch(() => ({})).then(data => ({ ok: res.ok && data.ok !== false, data })))
      .catch(() => ({ ok: false, data: {} }));
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);

    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;

    return node;
  }

  function icon(name, className) {
    const node = el("span", `koti-icon koti-fa-${name}${className ? ` ${className}` : ""}`);

    node.setAttribute("aria-hidden", "true");

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

  function retryIcon(tile, src, attempt) {
    if (attempt >= ICON_RETRY_MS.length) return;

    setTimeout(() => {
      if (tile.isConnected === false) return;

      const img = el("img", "dashboard-home-news-favicon");

      img.alt = "";
      img.decoding = "async";
      img.dataset.iconSrc = src;
      // The picture is swapped in only once it has loaded, so nothing flashes.
      img.addEventListener("load", () => tile.replaceWith(img));
      img.addEventListener("error", () => retryIcon(tile, src, attempt + 1));
      img.src = src;
    }, ICON_RETRY_MS[attempt]);
  }

  function favicon(item) {
    const src = safeIcon(item.icon);

    if (!src) return globe();

    const img = el("img", "dashboard-home-news-favicon");

    img.dataset.iconSrc = src;
    img.src = src;
    img.alt = "";
    img.loading = "lazy";
    img.decoding = "async";
    img.addEventListener("error", () => {
      const tile = globe();

      tile.dataset.iconSrc = src;
      img.replaceWith(tile);
      retryIcon(tile, src, 0);
    });

    return img;
  }

  // --- changes -------------------------------------------------------------

  function showToast(message, onUndo) {
    clearTimeout(toastTimer);
    undo = onUndo || null;

    if (!ui) return;

    ui.toastText.textContent = message;
    ui.undoButton.hidden = !onUndo;
    ui.toast.hidden = false;
    toastTimer = setTimeout(hideToast, TOAST_MS);
  }

  function hideToast() {
    clearTimeout(toastTimer);
    undo = null;

    if (ui) ui.toast.hidden = true;
  }

  function currentList() {
    return mode === "feed" ? (items || []) : sideItems;
  }

  function hideItem(item) {
    const index = (items || []).findIndex(row => row.id === item.id);

    if (index < 0) return;

    items.splice(index, 1);
    meta.hidden += 1;
    picking = "";
    renderList();
    showToast("Hidden from feed", () => restore(item, index));

    send(`/api/rss/items/${encodeURIComponent(item.id)}/hide`, {}).then(result => {
      if (result.ok) return;

      items.splice(Math.min(index, items.length), 0, item);
      meta.hidden = Math.max(0, meta.hidden - 1);
      renderList();
      showToast(result.data.error || "Could not hide that article.");
    });
  }

  function restore(item, index) {
    hideToast();

    return send(`/api/rss/items/${encodeURIComponent(item.id)}/unhide`, {}).then(result => {
      if (!result.ok) {
        showToast(result.data.error || "Could not undo that.");
        return;
      }

      items.splice(Math.min(index, items.length), 0, item);
      meta.hidden = Math.max(0, meta.hidden - 1);
      renderList();
      renderBar();
    });
  }

  function unhideItem(item) {
    send(`/api/rss/items/${encodeURIComponent(item.id)}/unhide`, {}).then(result => {
      if (!result.ok) {
        showToast(result.data.error || "Could not unhide that article.");
        return;
      }

      sideItems = sideItems.filter(row => row.id !== item.id);
      meta.hidden = Math.max(0, meta.hidden - 1);
      // The feed list is rebuilt from the server the next time it is shown.
      loadedAt = 0;
      renderList();
      renderBar();
    });
  }

  function saveItem(item, folder) {
    const name = String(folder || "").trim().slice(0, FOLDER_NAME_LIMIT);

    if (!name) return;

    send(`/api/rss/saved/${encodeURIComponent(item.id)}`, { folder: name }).then(result => {
      if (!result.ok) {
        showToast(result.data.error || "Could not save that article.");
        return;
      }

      if (!item.folder) meta.saved += 1;

      item.folder = name;

      if (!meta.folders.includes(name)) meta.folders = [...meta.folders, name];

      picking = "";
      naming = false;
      renderList();
      renderBar();
      showToast(`Saved to ${name}`);
    });
  }

  function unsaveItem(item) {
    send(`/api/rss/saved/${encodeURIComponent(item.id)}/remove`, {}).then(result => {
      if (!result.ok) {
        showToast(result.data.error || "Could not remove that article.");
        return;
      }

      sideItems = sideItems.filter(row => row.id !== item.id);
      meta.saved = Math.max(0, meta.saved - 1);
      loadedAt = 0;
      renderList();
      renderBar();
    });
  }

  function setMode(next) {
    mode = mode === next ? "feed" : next;
    picking = "";
    naming = false;
    scrollTop = 0;
    hideToast();
    sideItems = [];

    if (mode === "feed") {
      renderList();
      renderBar();
      return;
    }

    renderList();
    renderBar();

    const url = mode === "hidden" ? "/api/rss/items?view=hidden" : "/api/rss/saved";
    const wanted = mode;

    send(url).then(result => {
      if (mode !== wanted) return;

      sideItems = result.ok && Array.isArray(result.data.items) ? result.data.items : [];
      renderList();
    });
  }

  // --- rows ----------------------------------------------------------------

  function actionButton(name, label, onClick) {
    const button = el("button", "dashboard-home-news-act");

    button.type = "button";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.appendChild(icon(name));
    button.addEventListener("click", onClick);

    return button;
  }

  function folderPicker(item) {
    const line = el("div", "dashboard-home-news-picker");

    line.setAttribute("role", "group");
    line.setAttribute("aria-label", "Save to folder");

    meta.folders.forEach(name => {
      const chip = el("button", "dashboard-home-news-chip", name);

      chip.type = "button";
      chip.addEventListener("click", () => saveItem(item, name));
      line.appendChild(chip);
    });

    if (!naming) {
      const add = el("button", "dashboard-home-news-chip", "New folder");

      add.type = "button";
      add.addEventListener("click", () => {
        naming = true;
        renderList();
      });
      line.appendChild(add);

      return line;
    }

    const field = el("input", "dashboard-home-news-folder-input");

    field.type = "text";
    field.maxLength = FOLDER_NAME_LIMIT;
    field.placeholder = "Folder name";
    field.setAttribute("aria-label", "New folder name");
    field.addEventListener("keydown", event => {
      if (event.key === "Enter") saveItem(item, field.value);
      if (event.key === "Escape") {
        naming = false;
        renderList();
      }
    });
    line.appendChild(field);
    setTimeout(() => field.focus && field.focus(), 0);

    return line;
  }

  function row(item, previous) {
    const href = safeLink(item.link);
    const wrap = el("div", "dashboard-home-news-row");
    const body = el("div");
    const headline = el(href ? "a" : "span", href ? "dashboard-home-media-link dashboard-home-news-title" : "dashboard-home-news-title", item.title);
    // The section-head row centres the icon against the text; the subtitle class keeps the text green.
    const line = el("div", "dashboard-home-section-head");
    const kind = KINDS[item.kind] || KINDS.article;
    const kindIcon = el("span", `koti-icon dashboard-home-news-kind ${kind.icon}`);
    const actions = el("div", "dashboard-home-news-actions");

    wrap.setAttribute("role", "listitem");

    if (href) {
      headline.href = href;
      headline.target = "_blank";
      headline.rel = "noopener noreferrer";
    }

    kindIcon.title = kind.label;
    kindIcon.setAttribute("role", "img");
    kindIcon.setAttribute("aria-label", kind.label);
    line.appendChild(el("span", "dashboard-home-subtitle", mode === "saved" ? `${item.feed} · ${item.folder}` : subtitle(item)));
    line.appendChild(kindIcon);

    if (mode === "feed" && item.folder) {
      const tag = el("span", "dashboard-home-news-folder-tag");

      tag.appendChild(icon("folder"));
      tag.appendChild(el("span", "", item.folder));
      line.appendChild(tag);
    }

    body.appendChild(headline);

    if (picking === item.id && mode === "feed") {
      body.appendChild(folderPicker(item));
    } else {
      body.appendChild(line);
    }

    if (mode === "feed" && picking === item.id) {
      actions.appendChild(actionButton("xmark", "Cancel", () => {
        picking = "";
        naming = false;
        renderList();
      }));
    } else if (mode === "feed") {
      actions.appendChild(actionButton("folder-plus", item.folder ? `Move to another folder (now in ${item.folder})` : "Save to folder", () => {
        picking = item.id;
        naming = false;
        renderList();
      }));
      actions.appendChild(actionButton("eye-slash", "Hide from feed", () => hideItem(item)));
    } else if (mode === "hidden") {
      actions.appendChild(actionButton("eye", "Show in feed again", () => unhideItem(item)));
    } else {
      actions.appendChild(actionButton("folder-minus", "Remove from folder", () => unsaveItem(item)));
    }

    // An unchanged icon stays the same element, so a refresh never reloads or blinks it.
    const kept = previous && previous.children && previous.children[0];

    wrap.appendChild(kept && (kept.dataset.iconSrc || "") === safeIcon(item.icon) ? kept : favicon(item));
    wrap.appendChild(body);
    wrap.appendChild(actions);

    return wrap;
  }

  function matches(item) {
    const needle = query.trim().toLowerCase();

    if (!needle) return true;

    return [item.title, item.feed, item.folder].some(value => String(value || "").toLowerCase().includes(needle));
  }

  function emptyText() {
    if (query.trim()) return "No matches";
    if (mode === "hidden") return "Nothing hidden";
    if (mode === "saved") return "No saved articles yet";

    return "Nothing left in the feed";
  }

  // Rows are kept per item: a refresh rebuilds only the rows whose content changed.
  function rowFor(item, cache) {
    const picked = picking === item.id && mode === "feed";
    const signature = JSON.stringify([mode, item, picked, picked && naming, picked && meta.folders, mode === "saved" ? "" : subtitle(item)]);
    const known = rowCache.get(item.id);
    const node = known && known.signature === signature ? known.node : row(item, known && known.node);

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

  function renderList() {
    if (!ui) return;

    // The feed is searched by the server; the Hidden and Saved lists are short and filtered here.
    const shown = mode === "feed" ? (items || []) : sideItems.filter(matches);
    const signature = JSON.stringify([mode, query, picking, naming, loadingMore, shown]);

    if (signature === listSignature) return;

    listSignature = signature;
    const more = loadingMore ? [el("p", "dashboard-home-news-empty", "Loading more…")] : [];
    const cache = new Map();
    const nodes = shown.length ? shown.map(item => rowFor(item, cache)).concat(more) : [el("p", "dashboard-home-news-empty", emptyText())];

    rowCache = cache;
    syncChildren(ui.list, nodes);
    ui.list.scrollTop = scrollTop;
  }

  function renderBar() {
    if (!ui) return;

    ui.savedCount.textContent = String(meta.saved);
    ui.hiddenCount.textContent = String(meta.hidden);
    ui.savedButton.setAttribute("aria-pressed", String(mode === "saved"));
    ui.hiddenButton.setAttribute("aria-pressed", String(mode === "hidden"));
  }

  function toggle(name, label, onClick) {
    const button = el("button", "dashboard-home-news-toggle");
    const count = el("span", "", "0");

    button.type = "button";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.setAttribute("aria-pressed", "false");
    button.appendChild(icon(name));
    button.appendChild(count);
    button.addEventListener("click", onClick);

    return { button, count };
  }

  // The card is built once per section element: the list, a short message line,
  // and the search box with the Saved and Hidden buttons at the bottom.
  function build(section) {
    const list = el("div", "dashboard-home-news-list");
    const toast = el("div", "dashboard-home-news-toast");
    const toastText = el("span");
    const undoButton = el("button", "dashboard-home-news-chip", "Undo");
    const bar = el("div", "dashboard-home-news-bar");
    const label = el("label", "dashboard-home-news-search");
    const input = el("input", "dashboard-home-news-search-input");
    const saved = toggle("folder", "Saved articles", () => setMode("saved"));
    const hidden = toggle("eye-slash", "Hidden articles", () => setMode("hidden"));

    list.setAttribute("role", "list");
    toast.hidden = true;
    toast.setAttribute("role", "status");
    undoButton.type = "button";
    undoButton.addEventListener("click", () => {
      if (undo) undo();
    });
    toast.appendChild(toastText);
    toast.appendChild(undoButton);

    input.type = "search";
    input.placeholder = "Search feed";
    input.value = query;
    input.setAttribute("aria-label", "Search feed");
    input.addEventListener("input", () => {
      query = input.value;
      scrollTop = 0;
      clearTimeout(searchTimer);

      if (mode === "feed") {
        searchTimer = setTimeout(searchFeed, SEARCH_MS);
      } else {
        renderList();
      }
    });
    input.addEventListener("focus", () => {
      searchFocused = true;
    });
    input.addEventListener("blur", () => {
      // A removed input also blurs; only a real blur clears the flag.
      if (input.isConnected !== false) searchFocused = false;
    });
    list.addEventListener("scroll", () => {
      scrollTop = list.scrollTop;

      if (nearEnd()) loadMore();
    });

    label.appendChild(icon("magnifying-glass"));
    label.appendChild(input);
    bar.appendChild(label);
    bar.appendChild(saved.button);
    bar.appendChild(hidden.button);

    section.replaceChildren(list, toast, bar);
    ui = {
      section, list, toast, toastText, undoButton, input,
      savedButton: saved.button, savedCount: saved.count,
      hiddenButton: hidden.button, hiddenCount: hidden.count
    };
    listSignature = "";
    rowCache = new Map();
    section.dataset.newsBuilt = "1";

    if (searchFocused && input.focus) {
      // The Home page rebuilt this card while the search box had focus.
      setTimeout(() => {
        input.focus();
        if (input.setSelectionRange) input.setSelectionRange(input.value.length, input.value.length);
      }, 0);
    }
  }

  function render(section) {
    if (!items || !items.length) {
      // Nothing to read: show the card only when there is something to un-hide or open.
      if (mode === "feed" && !query.trim() && !(meta.saved || meta.hidden)) {
        section.hidden = true;
        section.replaceChildren();
        delete section.dataset.newsBuilt;
        ui = null;
        return;
      }
    }

    section.hidden = false;

    if (!ui || ui.section !== section || !section.dataset.newsBuilt) build(section);

    renderList();
    renderBar();
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
