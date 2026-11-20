"use strict";

// The one place that decides where a link to a homelab service points.
// Opened on kotibot.lan, every service link uses its <name>.kotibot.lan address; opened on kotibot.app, its
// <name>.kotibot.app address. Any other host (an IP address, localhost) keeps the old host:port form.
// Subdomains match the Caddy blocks and DNS names in the homelab (see docs); a service with no subdomain of its
// own has none to follow.
(function () {
  const DOMAIN = /(?:^|\.)(kotibot\.(?:lan|app))$/i;

  // The PiVault portal pages have no .lan name; on .lan they are still only served at the Pi's IP address.
  const PIVAULT_LAN_HOST = "192.168.4.90";

  const SERVICES = {
    documents: { subdomain: "paperless", port: 8085 },
    photos: { subdomain: "photos", port: 8446 },
    arcade: { subdomain: "arcade", port: 8000 },
    library: { subdomain: "library", port: 8083 },
    jukebox: { subdomain: "music", path: "/music/" },
    theater: { subdomain: "jellyfin", port: 8096 },
    wiki: { subdomain: "wiki", port: 8084 },
    passwords: { subdomain: "vault", port: 8448 },
    portainer: { subdomain: "portainer", port: 9443 },
    calendar: { subdomain: "calendar", port: 5232 },
    addUser: { path: "/users/add", lanHost: PIVAULT_LAN_HOST }
  };

  function here() {
    return (typeof window !== "undefined" && window.location) || globalThis.location || {};
  }

  function domainOf(hostname) {
    const match = DOMAIN.exec(String(hostname || ""));

    return match ? match[1].toLowerCase() : "";
  }

  window.dashboardServiceOnKotibotDomain = function () {
    return domainOf(here().hostname) !== "";
  };

  window.dashboardServiceUrl = function (key, path) {
    const service = SERVICES[key];

    if (!service) return "";

    const hostname = String(here().hostname || "");
    const domain = domainOf(hostname);
    const tail = path || service.path || "/";

    if (domain && service.subdomain) return `https://${service.subdomain}.${domain}${tail}`;

    const host = domain === "kotibot.lan" && service.lanHost ? service.lanHost : hostname;
    const port = service.port ? `:${service.port}` : "";

    return `https://${host}${port}${tail}`;
  };
})();
