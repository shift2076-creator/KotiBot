"use strict";

window.esc = function (v) {
  return v
    ? String(v)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
    : "";
};

window.fmt = function (v, fallback = "—") {
  return (v === null || v === undefined) ? fallback : v;
};

window.fmtBytes = function (bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
};

window.deviceIdOf = function (client) {
  return client?.deviceID || "";
};

window.roleListOf = function (client) {
  const roles = client?.clientRole;

  const list = Array.isArray(roles)
    ? roles
    : String(roles || "UNP").split(",");

  return list
    .map(v => String(v).trim().toUpperCase())
    .filter(Boolean);
};

function dashboardViewerIsAndroidKeyClientApp() {
  return (
    window.KOTIBOT_ANDROID_KEY_CLIENT === true ||
    String(window.KOTIBOT_ANDROID_KEY_CLIENT || "").trim().toLowerCase() === "true" ||
    String(document.body?.dataset?.androidKeyClient || "").trim().toLowerCase() === "true" ||
    String(document.documentElement?.dataset?.androidKeyClient || "").trim().toLowerCase() === "true"
  );
}

window.dashboardViewerIsAndroidKeyClientApp = dashboardViewerIsAndroidKeyClientApp;

window.routeExists = function (fromDeviceId, toDeviceId, toKind, toInput) {
  const S = window.appState;
  return S.currentRoutes.some(r =>
    r.from_deviceID === fromDeviceId &&
    r.to_deviceID === toDeviceId &&
    r.to_kind === toKind &&
    r.to_input === toInput
  );
};

window.escAttr = window.escAttr || function (value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
};


const DASHBOARD_ICON_CLASSES = Object.freeze({
  add: "koti-fa-plus",
  add_ad: "koti-fa-satellite-dish",
  add_link: "koti-fa-link",
  air: "koti-fa-wind",
  android: "koti-fab-android",
  arrow_back: "koti-fa-arrow-left",
  arrow_forward: "koti-fa-arrow-right",
  auto_awesome: "koti-fa-wand-magic-sparkles",
  bath: "koti-fa-bath",
  bathroom: "koti-fa-bath",
  battery_charging_full: "koti-fa-battery-full",
  battery_full: "koti-fa-battery-full",
  bed: "koti-fa-bed",
  bedtime: "koti-fa-moon",
  block: "koti-fa-ban",
  bluetooth: "koti-fab-bluetooth-b",
  bluetooth_connected: "koti-fab-bluetooth-b",
  bolt: "koti-fa-bolt",
  buttons_alt: "koti-fa-gamepad",
  calibrate: "koti-icon-calibrate",
  chair: "koti-fa-couch",
  change_mode: "koti-fa-sliders",
  check_circle: "koti-fa-circle-check",
  checkroom: "koti-fa-door-closed",
  chevron_left: "koti-fa-chevron-left",
  chevron_right: "koti-fa-chevron-right",
  chevron_up: "koti-fa-chevron-up",
  chevron_down: "koti-fa-chevron-down",
  circle_dot: "koti-fa-circle-dot",
  knob_turn: "koti-icon-knob-turn",
  clock: "koti-fa-clock",
  close: "koti-fa-xmark",
  cloud: "koti-fa-cloud",
  cloud_queue: "koti-fa-cloud",
  overcast: "koti-fa-cloud",
  construction: "koti-fa-gear",
  dark_mode: "koti-fa-moon",
  deck: "koti-fa-leaf",
  delete: "koti-fa-trash",
  desk: "koti-fa-gear",
  device_thermostat: "koti-fa-temperature-half",
  dining: "koti-fa-kitchen-set",
  directions_walk: "koti-fa-person-walking",
  door_close: "koti-fa-door-closed",
  door_closed: "koti-fa-door-closed",
  door_front: "koti-fa-door-closed",
  door_open: "koti-fa-door-open",
  droplet: "koti-fa-droplet",
  eco: "koti-fa-leaf",
  edit: "koti-fa-pencil",
  electrical_services: "koti-fa-plug",
  emoji_objects: "koti-fa-lightbulb",
  fiber_manual_record: "koti-fa-circle",
  foggy: "koti-fa-smog",
  smoke: "koti-fa-smog",
  format_size: "koti-fa-font",
  foundation: "koti-fa-house",
  garage: "koti-fa-house",
  garage_home: "koti-fa-house",
  group: "koti-fa-users",
  hallway: "koti-fa-stairs",
  history: "koti-icon-recent-activity",
  house: "koti-fa-house",
  house_siding: "koti-fa-house",
  humidity_percentage: "koti-fa-droplet",
  info: "koti-fa-circle-info",
  inventory_2: "koti-fa-hard-drive",
  key: "koti-fa-key",
  king_bed: "koti-fa-bed",
  kitchen: "koti-fa-kitchen-set",
  kotibot: "koti-icon-kotibot",
  leaf: "koti-fa-leaf",
  light_mode: "koti-fa-sun",
  link: "koti-fa-link",
  local_laundry_service: "koti-fa-broom",
  lock: "koti-fa-lock",
  lock_open: "koti-fa-lock-open",
  logout: "koti-fa-right-from-bracket",
  manage_accounts: "koti-fa-user-pen",
  matter: "koti-icon-matter",
  meeting_room: "koti-fa-door-open",
  menu: "koti-fa-bars",
  menu_open: "koti-fa-xmark",
  mic: "koti-fa-microphone",
  mobile_screen: "koti-fa-mobile-screen",
  motion_sensor_active: "koti-fa-street-view",
  motion_sensor_idle: "koti-fa-street-view",
  movie: "koti-fa-clapperboard",
  music_note: "koti-fa-music",
  nightlight: "koti-fa-moon",
  notifications: "koti-fa-bell",
  outlet_extender: "koti-fa-plug",
  partly_cloudy_day: "koti-fa-cloud-sun",
  partly_cloudy_night: "koti-fa-cloud-moon",
  person: "koti-fa-user",
  person_add: "koti-fa-user-plus",
  play_arrow: "koti-fa-play",
  playlist_add_check: "koti-fa-list-check",
  pool: "koti-fa-bath",
  power: "koti-fa-plug",
  power_settings_new: "koti-fa-power-off",
  psychiatry: "koti-fa-leaf",
  radio_button_checked: "koti-fa-square",
  rainy: "koti-fa-cloud-rain",
  rain_showers: "koti-fa-cloud-rain",
  rainy_heavy: "koti-fa-cloud-rain",
  restart_alt: "koti-fa-rotate",
  roofing: "koti-fa-house",
  save: "koti-fa-floppy-disk",
  schedule: "koti-fa-clock",
  security: "koti-fa-shield-halved",
  sensor_door: "koti-fa-door-closed",
  sensors: "koti-icon-sensor",
  settings: "koti-fa-gear",
  skillet: "koti-fa-kitchen-set",
  star: "koti-fa-star",
  terminal: "koti-fa-terminal",
  thunderstorm: "koti-fa-cloud-bolt",
  toggle_off: "koti-fa-toggle-off",
  toggle_on: "koti-fa-toggle-on",
  tune: "koti-fa-sliders",
  more_vert: "koti-fa-ellipsis-vertical",
  view_column: "koti-fa-table-columns",
  videocam: "koti-fa-video",
  vpn_key: "koti-fa-key",
  water_drop: "koti-fa-droplet",
  wb_sunny: "koti-icon-lighting-day",
  wb_twilight: "koti-icon-lighting-evening",
  morning: "koti-icon-lighting-morning",
  evening: "koti-icon-lighting-evening",
  sunup: "koti-icon-lighting-sunup",
  sundown: "koti-icon-lighting-sundown",
  weather_snowy: "koti-fa-snowflake",
  weekend: "koti-fa-couch",
  yard: "koti-fa-leaf"
});

/*
 * Canonical device-type icon registry.
 *
 * DASHBOARD_ICON_CLASSES above resolves an icon name to its local SVG class.
 * This registry resolves a physical device/capability to that icon name.
 *
 * Device renderers must call dashboardDeviceIconName(). Do not independently
 * assign bulb, plug, camera, door, Matter, sensor, or client icons elsewhere.
 * Event and action icons are separate because they describe an operation,
 * not the physical device that generated it.
 */
const DASHBOARD_DEVICE_ICON_NAMES = Object.freeze({
  bulb: "emoji_objects",
  button: "buttons_alt",
  camera: "videocam",
  client: "mobile_screen",
  contact: "sensor_door",
  door: "sensor_door",
  environment: "device_thermostat",
  hub: "matter",
  bridge: "matter",
  humidity: "humidity_percentage",
  key: "key",
  lightstrip: "emoji_objects",
  matter: "matter",
  motion: "motion_sensor_active",
  occupancy: "motion_sensor_active",
  onoff: "toggle_on",
  outlet_extender: "outlet_extender",
  plug: "power",
  sensor: "sensors",
  switch: "toggle_on",
  temperature: "device_thermostat",
  vacuum: "local_laundry_service"
});

const DASHBOARD_DEVICE_KIND_ALIASES = Object.freeze({
  android_home: "client",
  android_key: "key",
  cam: "camera",
  contact_sensor: "contact",
  door_sensor: "door",
  dss: "door",
  environmental_sensor: "environment",
  extender: "outlet_extender",
  humid: "humidity",
  humidity_sensor: "humidity",
  light: "bulb",
  light_strip: "lightstrip",
  matter_bridge: "bridge",
  matter_hub: "hub",
  motion_detection: "motion",
  motion_sensor: "motion",
  occupancy_sensor: "motion",
  outlet: "plug",
  outlet_child: "plug",
  outlet_extender_child: "plug",
  power: "plug",
  power_strip: "outlet_extender",
  presence: "motion",
  presence_sensor: "motion",
  push_button: "button",
  smart_plug: "plug",
  smart_power_strip: "outlet_extender",
  socket: "plug",
  strip_light: "lightstrip",
  temp: "temperature",
  temperature_sensor: "temperature",
  thermometer: "temperature"
});

function dashboardDeviceKindKey(value) {
  const key = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_")
    .replace(/_+/g, "_");

  return DASHBOARD_DEVICE_KIND_ALIASES[key] || key;
}

function dashboardDeviceFlag(value) {
  if (value === true || value === 1) return true;

  return ["true", "1", "yes", "on"].includes(
    String(value ?? "").trim().toLowerCase()
  );
}

function dashboardDeviceHasValue(value) {
  return value !== undefined && value !== null && value !== "";
}

function dashboardDeviceMatterKinds(client) {
  const values = [
    ...(Array.isArray(client?.matter_kinds) ? client.matter_kinds : []),
    client?.matter_kind
  ];
  const kinds = new Set(
    values
      .map(dashboardDeviceKindKey)
      .filter(kind => kind && kind !== "matter")
  );
  const cluster = String(client?.matter_cluster || "").trim().toLowerCase();
  const identity = [
    client?.matter_device_type,
    client?.matter_product_name,
    client?.matter_node_label
  ]
    .map(value => String(value || "").trim().toLowerCase())
    .filter(Boolean)
    .join(" ");

  if (
    cluster.includes("occupancysensing") ||
    dashboardDeviceHasValue(client?.occupancy_state_value) ||
    dashboardDeviceHasValue(client?.motion_active)
  ) {
    kinds.add("motion");
  }

  if (dashboardDeviceHasValue(client?.temperature_c)) {
    kinds.add("temperature");
  }

  if (dashboardDeviceHasValue(client?.humidity_percent)) {
    kinds.add("humidity");
  }

  if (
    dashboardDeviceHasValue(client?.contact_open) ||
    dashboardDeviceHasValue(client?.contact_state_value) ||
    dashboardDeviceHasValue(client?.door_status)
  ) {
    kinds.add("contact");
  }

  if (dashboardDeviceHasValue(client?.matter_onoff)) {
    kinds.add("onoff");
  }

  if (
    dashboardDeviceHasValue(client?.matter_button_event) ||
    dashboardDeviceHasValue(client?.matter_switch_position)
  ) {
    kinds.add("button");
  }

  if (/(^|\s)(hub|bridge)(\s|$)/.test(identity)) {
    kinds.add("hub");
  }

  return kinds;
}

window.dashboardDeviceKind = function (client = {}, requestedKind = "") {
  const requested = dashboardDeviceKindKey(requestedKind);

  if (DASHBOARD_DEVICE_ICON_NAMES[requested]) {
    return requested;
  }

  const roles = new Set(window.roleListOf(client));
  const source = String(client?.source || "").trim().toLowerCase();
  const deviceID = String(client?.deviceID || "").trim().toLowerCase();
  const rawKind = dashboardDeviceKindKey(
    client?.kind ||
    client?.device_kind ||
    client?.device_type ||
    client?.type
  );
  const tapoKind = dashboardDeviceKindKey(
    client?.tapo_child_kind ||
    client?.tapo_kind ||
    client?.tapo_device_type ||
    rawKind
  );
  const tapoEvidence = (
    roles.has("TAPO") ||
    dashboardDeviceHasValue(client?.tapo_kind) ||
    dashboardDeviceHasValue(client?.tapo_device_type) ||
    dashboardDeviceHasValue(client?.tapo_model) ||
    dashboardDeviceFlag(client?.tapo_is_bulb ?? client?.is_bulb) ||
    dashboardDeviceFlag(client?.tapo_is_plug ?? client?.is_plug) ||
    dashboardDeviceFlag(client?.tapo_is_camera ?? client?.is_camera) ||
    dashboardDeviceFlag(
      client?.tapo_is_outlet_extender ??
      client?.is_outlet_extender
    )
  );

  if (tapoEvidence) {
    if (
      dashboardDeviceFlag(
        client?.tapo_is_outlet_extender ??
        client?.is_outlet_extender
      ) ||
      tapoKind === "outlet_extender"
    ) {
      return "outlet_extender";
    }

    if (
      dashboardDeviceFlag(client?.tapo_is_camera ?? client?.is_camera) ||
      tapoKind === "camera"
    ) {
      return "camera";
    }

    if (
      dashboardDeviceFlag(client?.tapo_is_bulb ?? client?.is_bulb) ||
      tapoKind === "bulb" ||
      tapoKind === "lightstrip"
    ) {
      return tapoKind === "lightstrip" ? "lightstrip" : "bulb";
    }

    if (
      dashboardDeviceFlag(client?.tapo_is_plug ?? client?.is_plug) ||
      tapoKind === "plug"
    ) {
      return "plug";
    }

    if (
      tapoKind !== "sensor" &&
      DASHBOARD_DEVICE_ICON_NAMES[tapoKind]
    ) {
      return tapoKind;
    }
  }

  const isMatter = (
    source === "matter" ||
    deviceID.startsWith("matter:") ||
    roles.has("MATTER")
  );

  if (isMatter) {
    const kinds = dashboardDeviceMatterKinds(client);

    if (
      kinds.has("environment") ||
      (kinds.has("temperature") && kinds.has("humidity"))
    ) {
      return "environment";
    }

    for (const kind of [
      "temperature",
      "humidity",
      "contact",
      "motion",
      "occupancy",
      "switch",
      "onoff",
      "button",
      "hub",
      "bridge"
    ]) {
      if (kinds.has(kind)) return kind;
    }

    return "matter";
  }

  if (roles.has("CAM")) return "camera";
  if (roles.has("DSS")) return "door";
  if (roles.has("KEY")) return "key";

  if (DASHBOARD_DEVICE_ICON_NAMES[rawKind]) {
    return rawKind;
  }

  if (tapoEvidence) return "sensor";

  return "client";
};

/*
 * Canonical device-type display-name registry.
 *
 * Keep model/type wording here beside the canonical icon registry. Renderers
 * must call dashboardDeviceTypeName(); they must never rebuild labels from raw
 * roles, Matter endpoints, or "model + kind" fragments.
 *
 * Matter temperature and humidity endpoints are telemetry records, not
 * separate physical devices. dashboardPhysicalClients() groups them before
 * display, and this formatter deliberately names a T310 as one combined
 * Temperature & Humidity Sensor.
 */
const DASHBOARD_DEVICE_TYPE_NAMES = Object.freeze({
  bulb: "Bulb",
  button: "Button",
  camera: "Security Camera",
  client: "Client",
  contact: "Contact Sensor",
  door: "Door Sensor",
  environment: "Temperature & Humidity Sensor",
  hub: "Hub",
  bridge: "Bridge",
  humidity: "Humidity Sensor",
  key: "Key Client",
  lightstrip: "Light Strip",
  matter: "Matter Device",
  motion: "Motion Sensor",
  occupancy: "Occupancy Sensor",
  onoff: "Switch",
  outlet_extender: "Outlet Extender",
  plug: "Smart Plug",
  sensor: "Sensor",
  switch: "Switch",
  temperature: "Temperature Sensor",
  vacuum: "Robot Vacuum"
});

const DASHBOARD_DEVICE_MODEL_TYPE_NAMES = Object.freeze({
  L510: "Dimmable Bulb",
  L520: "Daylight Dimmable Bulb",
  L530: "Full-Color Bulb",
  L535: "Full-Color Bulb",
  L610: "Dimmable Spotlight",
  L630: "Full-Color Spotlight",
  L900: "Full-Color Light Strip",
  L920: "Full-Color Light Strip",
  L930: "Full-Color Light Strip",
  P100: "Smart Plug",
  P105: "Smart Plug",
  P110: "Energy-Monitoring Plug",
  P115: "Energy-Monitoring Plug",
  P125: "Smart Plug",
  P300: "Outlet Extender",
  P304M: "Energy-Monitoring Outlet Extender",
  P304: "Outlet Extender",
  P306: "Outlet Extender",
  P316M: "Power Strip",
  P316: "Power Strip",
  EP10: "Smart Plug",
  EP25: "Smart Plug",
  EP300: "Outlet Extender",
  EP304: "Outlet Extender",
  EP306: "Outlet Extender",
  EP316: "Power Strip",
  H100: "IoT Hub",
  H110: "IR & IoT Hub",
  H200: "Smart Hub",
  T100: "Motion Sensor",
  T110: "Contact Sensor",
  T310: "Temperature & Humidity Sensor",
  S200D: "Remote Dimmer Switch"
});

function dashboardDeviceIsMatter(client, roles) {
  const source = String(client?.source || "").trim().toLowerCase();
  const deviceID = String(client?.deviceID || "").trim().toLowerCase();

  return (
    source === "matter" ||
    deviceID.startsWith("matter:") ||
    roles.has("MATTER")
  );
}

function dashboardDeviceIsTapo(client, roles) {
  const source = String(client?.source || "").trim().toLowerCase();

  return (
    roles.has("TAPO") ||
    source === "tapo" ||
    source === "tapo_child" ||
    source.startsWith("tapo-") ||
    dashboardDeviceHasValue(client?.tapo_model) ||
    dashboardDeviceHasValue(client?.tapo_kind) ||
    dashboardDeviceHasValue(client?.tapo_device_type)
  );
}

function dashboardDeviceModel(client, isMatter) {
  const candidates = [
    client?.tapo_model,
    client?.matter_product_name,
    client?.product_model,
    isMatter ? "" : client?.model
  ];

  for (const value of candidates) {
    const text = String(value || "")
      .trim()
      .toUpperCase()
      .replace(/^(?:TAPO|KASA|TP-LINK)\s+/, "");

    const match = text.match(
      /\b(?:L\d{3}[A-Z]?|P\d{3}[A-Z]?|EP\d{2,3}[A-Z]?|H\d{3}[A-Z]?|T\d{3}[A-Z]?|S\d{3}[A-Z]?|TC\d{2,4}[A-Z]?|C\d{2,4}[A-Z]?|RV[A-Z0-9-]+)\b/
    );

    if (match) return match[0];
  }

  return "";
}

function dashboardDeviceModelTypeName(model) {
  const cleanModel = String(model || "").trim().toUpperCase();

  for (const [prefix, name] of Object.entries(
    DASHBOARD_DEVICE_MODEL_TYPE_NAMES
  )) {
    if (cleanModel.startsWith(prefix)) return name;
  }

  if (/^(?:C|TC)\d/.test(cleanModel)) return "Security Camera";
  if (/^RV/.test(cleanModel)) return "Robot Vacuum";

  return "";
}

function dashboardDeviceKnownTapoModel(model) {
  const cleanModel = String(model || "").trim().toUpperCase();

  if (!cleanModel || cleanModel.startsWith("EP")) return false;
  if (dashboardDeviceModelTypeName(cleanModel)) return true;

  return /^(?:L|P|H|T|S)\d/.test(cleanModel);
}

function dashboardDeviceBrandName(value) {
  const text = String(value || "").trim();

  if (!text) return "";
  if (/kasa/i.test(text)) return "Kasa";
  if (/tapo/i.test(text)) return "Tapo";
  if (/tp[\s-]*link/i.test(text)) return "TP-Link";

  return text;
}

function dashboardDeviceBrand(client, model, isTapo) {
  const cleanModel = String(model || "").toUpperCase();

  if (/^EP(?:10|25)/.test(cleanModel)) return "Kasa";
  if (cleanModel.startsWith("EP")) return "TP-Link";

  if (isTapo || dashboardDeviceKnownTapoModel(cleanModel)) {
    return "Tapo";
  }

  return dashboardDeviceBrandName(
    client?.matter_vendor_name ||
    client?.manufacturer ||
    client?.brand
  );
}

function dashboardDeviceGenericTypeName(client, kind) {
  if (
    kind === "bulb" &&
    dashboardDeviceFlag(
      client?.tapo_supports_color ??
      client?.supports_color
    )
  ) {
    return "Full-Color Bulb";
  }

  if (
    kind === "lightstrip" &&
    dashboardDeviceFlag(
      client?.tapo_supports_color ??
      client?.supports_color
    )
  ) {
    return "Full-Color Light Strip";
  }

  if (
    kind === "plug" &&
    dashboardDeviceFlag(
      client?.tapo_supports_energy ??
      client?.supports_energy
    )
  ) {
    return "Energy-Monitoring Plug";
  }

  return DASHBOARD_DEVICE_TYPE_NAMES[kind] || "Device";
}

function dashboardDeviceIdentityTypeName(brand, model, typeName) {
  const identity = [brand, model]
    .map(value => String(value || "").trim())
    .filter(Boolean)
    .filter((value, index, values) => (
      index === 0 ||
      value.toLowerCase() !== values[0].toLowerCase()
    ))
    .join(" ");

  return identity ? identity + " — " + typeName : typeName;
}

window.dashboardDeviceTypeName = function (client = {}) {
  const roles = new Set(window.roleListOf(client));
  const isMatter = dashboardDeviceIsMatter(client, roles);
  const isTapo = dashboardDeviceIsTapo(client, roles);
  const model = dashboardDeviceModel(client, isMatter);
  const kind = window.dashboardDeviceKind(client);
  const outletChild = dashboardDeviceFlag(client?.tapo_is_outlet_child);

  if (isTapo && outletChild) {
    const childText = [
      client?.tapo_child_kind,
      client?.tapo_child_name,
      client?.clientName,
      client?.tapo_alias,
      client?.tapo_kind
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    const childType = (
      kind === "bulb" ||
      kind === "lightstrip" ||
      /night\s*light|nightlight/.test(childText)
    )
      ? "Nightlight"
      : "Outlet";

    return dashboardDeviceIdentityTypeName(
      dashboardDeviceBrand(client, model, true),
      model,
      childType
    );
  }

  const typeName = (
    dashboardDeviceModelTypeName(model) ||
    dashboardDeviceGenericTypeName(client, kind)
  );

  if (isMatter) {
    if (model) {
      return dashboardDeviceIdentityTypeName(
        dashboardDeviceBrand(client, model, false),
        model,
        typeName
      );
    }

    return typeName === "Matter Device"
      ? typeName
      : "Matter " + typeName;
  }

  if (isTapo) {
    return dashboardDeviceIdentityTypeName(
      dashboardDeviceBrand(client, model, true),
      model,
      typeName
    );
  }

  if (roles.has("KEY")) return "Android Key Client";
  if (roles.has("CAM") && roles.has("DSS")) {
    return "Android Camera & Door Sensor Client";
  }
  if (roles.has("CAM")) return "Android Camera Client";
  if (roles.has("DSS")) return "Android Door Sensor Client";

  const source = String(client?.source || "").trim().toLowerCase();
  const isAndroid = (
    source.includes("android") ||
    dashboardDeviceHasValue(client?.androidVersion) ||
    dashboardDeviceHasValue(client?.android_version) ||
    roles.has("PRIMARY") ||
    roles.has("RESIDENT")
  );

  if (!client?.provisioned && (isAndroid || !source)) {
    return "Unprovisioned Android Client";
  }

  if (isAndroid) return "Android Home Client";

  return client?.provisioned
    ? typeName
    : "Unprovisioned Client";
};

window.DASHBOARD_DEVICE_TYPE_NAMES = DASHBOARD_DEVICE_TYPE_NAMES;
window.DASHBOARD_DEVICE_MODEL_TYPE_NAMES =
  DASHBOARD_DEVICE_MODEL_TYPE_NAMES;

window.dashboardDeviceIconName = function (
  client = {},
  requestedKind = ""
) {
  const kind = window.dashboardDeviceKind(client, requestedKind);

  return (
    DASHBOARD_DEVICE_ICON_NAMES[kind] ||
    DASHBOARD_DEVICE_ICON_NAMES.sensor
  );
};

window.DASHBOARD_DEVICE_ICON_NAMES = DASHBOARD_DEVICE_ICON_NAMES;

function dashboardIconKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
}

window.dashboardIconClass = function (value) {
  const raw = String(value || "").trim();

  if (/^koti-(?:fa|fab|icon)-[a-z0-9-]+$/i.test(raw)) return raw;

  return DASHBOARD_ICON_CLASSES[dashboardIconKey(raw)] || "koti-fa-circle-dot";
};

window.dashboardIconHtml = function (value, className = "") {
  const iconClass = window.dashboardIconClass(value);
  const extraClasses = String(className || "")
    .split(/\s+/)
    .filter(name => /^[a-zA-Z0-9_-]+$/.test(name));
  const classes = ["koti-icon", iconClass, ...extraClasses].join(" ");

  return `<span class="${window.escAttr(classes)}" data-dashboard-icon="${window.escAttr(dashboardIconKey(value))}" data-dashboard-icon-class="${window.escAttr(iconClass)}" aria-hidden="true"></span>`;
};

window.setDashboardIcon = function (element, value) {
  if (!element) return;

  const previousClass = String(element.dataset.dashboardIconClass || "").trim();
  const iconClass = window.dashboardIconClass(value);

  if (previousClass && previousClass !== iconClass) {
    element.classList.remove(previousClass);
  }

  element.classList.add("koti-icon", iconClass);
  element.dataset.dashboardIcon = dashboardIconKey(value);
  element.dataset.dashboardIconClass = iconClass;
  element.textContent = "";
};

window.dashboardValueIsReady = window.dashboardValueIsReady || function (value, placeholder = "—") {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  const fallback = String(placeholder ?? "—").replace(/\s+/g, " ").trim();

  return !!text && text !== fallback;
};

window.dashboardValueSlotHtml = window.dashboardValueSlotHtml || function ({
  key = "",
  value = "",
  placeholder = "—",
  slotClass = "",
  placeholderClass = "",
  contentClass = "",
  placeholderHtml = null,
  contentHtml = null,
  ready = null
} = {}) {
  const S = window.appState || (window.appState = {});
  S.dashboardValueSlotState = S.dashboardValueSlotState || Object.create(null);

  const valueText = String(value ?? "").trim() || String(placeholder ?? "—");
  const placeholderText = String(placeholder ?? "—");
  const isReady = ready === null ? window.dashboardValueIsReady(valueText, placeholderText) : !!ready;
  const baseClasses = ["dashboard-value-slot", slotClass].filter(Boolean);
  const stableKey = String(key || "").trim() || `${baseClasses.join(" ")}:${placeholderText}`;
  const previous = S.dashboardValueSlotState[stableKey];
  const sameReadyValue = !!(
    isReady &&
    previous &&
    previous.ready === true &&
    previous.value === valueText
  );

  if (sameReadyValue) baseClasses.push("has-value");
  if (sameReadyValue && Number(previous.settledAt || 0) > 0) baseClasses.push("dashboard-value-settled");

  const placeholderMarkup = placeholderHtml === null
    ? window.esc(placeholderText)
    : String(placeholderHtml);
  const contentMarkup = contentHtml === null
    ? window.esc(valueText)
    : String(contentHtml);

  return `
    <span class="${window.escAttr(baseClasses.join(" "))}" data-dashboard-value-key="${window.escAttr(stableKey)}" data-dashboard-value-text="${window.escAttr(valueText)}" data-dashboard-value-ready="${isReady ? "1" : "0"}" aria-live="polite">
      <span class="dashboard-value-placeholder ${window.escAttr(placeholderClass)}" aria-hidden="true">${placeholderMarkup}</span>
      <span class="dashboard-value-content ${window.escAttr(contentClass)}">${contentMarkup}</span>
    </span>
  `;
};

window.syncDashboardValueSlots = window.syncDashboardValueSlots || function (root = document) {
  const S = window.appState || (window.appState = {});
  S.dashboardValueSlotState = S.dashboardValueSlotState || Object.create(null);

  root.querySelectorAll?.(".dashboard-value-slot").forEach(slot => {
    const ready = slot.dataset.dashboardValueReady === "1";
    const key = String(slot.dataset.dashboardValueKey || "").trim();
    const valueText = String(slot.dataset.dashboardValueText || slot.textContent || "").trim();
    const now = Date.now();
    const previous = key ? S.dashboardValueSlotState[key] : null;

    if (!ready) {
      slot.classList.remove("has-value", "dashboard-value-settled", "dashboard-value-animating");

      if (key && (!previous || previous.ready !== false || previous.value !== valueText)) {
        S.dashboardValueSlotState[key] = {
          value: valueText,
          ready: false,
          token: 0,
          startedAt: 0,
          settledAt: 0
        };
      }

      return;
    }

    const sameReadyValue =
      previous &&
      previous.ready === true &&
      previous.value === valueText;

    if (sameReadyValue) {
      slot.classList.add("has-value");
      slot.classList.toggle("dashboard-value-settled", Number(previous.settledAt || 0) > 0);
      slot.classList.remove("dashboard-value-animating");
      return;
    }

    const token = now + Math.random();

    if (key) {
      S.dashboardValueSlotState[key] = {
        value: valueText,
        ready: true,
        token,
        startedAt: now,
        settledAt: 0
      };
    }

    slot.classList.remove("has-value", "dashboard-value-settled");
    slot.classList.add("dashboard-value-animating");

    window.setTimeout(() => {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (!slot.isConnected) return;
          if (key && S.dashboardValueSlotState[key]?.token !== token) return;

          slot.classList.add("has-value");

          window.setTimeout(() => {
            if (!slot.isConnected) return;
            if (key && S.dashboardValueSlotState[key]?.token !== token) return;

            slot.classList.remove("dashboard-value-animating");
            slot.classList.add("dashboard-value-settled");

            if (key && S.dashboardValueSlotState[key]?.value === valueText) {
              S.dashboardValueSlotState[key].settledAt = Date.now();
            }
          }, 1050);
        });
      });
    }, 180);
  });
};

window.hasClientRole = function (c, role) {
  const target = String(role || "").trim().toUpperCase();
  const roles = Array.isArray(c.clientRole)
    ? c.clientRole
    : String(c.clientRole || "").split(",");

  return roles
    .map(r => String(r).trim().toUpperCase())
    .includes(target);
};

function dashboardTruthValue(value) {
  if (value === true || value === 1) return true;
  if (value === false || value === 0 || value == null) return false;

  return ["true", "yes", "y", "1", "on", "active", "online"].includes(
    String(value).trim().toLowerCase()
  );
}

function dashboardSecondsAgo(value) {
  const text = String(value || "").trim().toLowerCase();

  if (!text || text === "—") return null;
  if (text === "now") return 0;

  const match = text.match(/^(\d+(?:\.\d+)?)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes)\s*ago$/);
  if (!match) return null;

  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) return null;

  return match[2].startsWith("m") ? amount * 60 : amount;
}

window.dashboardEffectiveClientStale = function (client) {
  const serverStale = dashboardTruthValue(client?.server_stale ?? client?.stale);

  if (hasClientRole(client || {}, "TAPO") || hasClientRole(client || {}, "KEY")) {
    return serverStale;
  }

  const isAndroidCamera = hasClientRole(client || {}, "CAM");
  const isAndroidDoor = hasClientRole(client || {}, "DSS");

  if (isAndroidCamera) return serverStale;

  if (!serverStale) return false;
  if (!isAndroidDoor) return true;

  if (dashboardTruthValue(client?.calibrating)) return false;

  const lastUpdateAge = dashboardSecondsAgo(client?.last_update ?? client?.lastUpdate);
  if (lastUpdateAge !== null && lastUpdateAge <= 30) return false;

  return true;
};

window.dashboardCameraPreviewUrl = function (client) {
  const baseUrl = String(client?.latest_frame_url || client?.latestFrameUrl || "").trim();

  if (!baseUrl) return "";

  const revision = String(
    client?.latest_frame_revision ??
    client?.frame_revision ??
    client?.latest_frame_at ??
    client?.last_frame_at ??
    client?.frame_timestamp ??
    client?.frame_ts ??
    Math.floor(Date.now() / 1000)
  ).trim();

  const separator = baseUrl.includes("?") ? "&" : "?";
  return `${baseUrl}${separator}dash=${encodeURIComponent(revision)}`;
};

window.formatLastUpdateText = function (value) {
  const text = String(value || "—").trim();
  return text.toLowerCase() === "now" ? "now" : text;
};

window.hasDssHardware = function (c) {
  const v = c.hasDSSHW;

  if (v === false || v === 0 || v == null) return false;

  const s = String(v).trim().toLowerCase();
  return !["no", "nope", "false", "0", "none", "missing"].includes(s);
};

window.COMMON_HOME_AREAS = [
  { name: "Attic", icon: "roofing" },
  { name: "Basement", icon: "foundation" },
  { name: "Master Bathroom", icon: "bathroom" },
  { name: "Bathroom", icon: "bathroom" },
  { name: "Master Bedroom", icon: "king_bed" },
  { name: "Bedroom", icon: "bed" },
  { name: "Bedroom 1", icon: "bed" },
  { name: "Bedroom 2", icon: "bed" },
  { name: "Closet", icon: "checkroom" },
  { name: "Deck", icon: "deck" },
  { name: "Dining Room", icon: "dining" },
  { name: "Driveway", icon: "garage" },
  { name: "Entryway", icon: "door_front" },
  { name: "Family Room", icon: "weekend" },
  { name: "Foyer", icon: "door_front" },
  { name: "Garage", icon: "garage_home" },
  { name: "Garden", icon: "psychiatry" },
  { name: "Greenhouse", icon: "eco" },
  { name: "Hallway", icon: "hallway" },
  { name: "Kitchen", icon: "skillet" },
  { name: "Laundry Room", icon: "local_laundry_service" },
  { name: "Living Room", icon: "chair" },
  { name: "Mudroom", icon: "door_front" },
  { name: "Office", icon: "desk" },
  { name: "Pantry", icon: "kitchen" },
  { name: "Patio", icon: "deck" },
  { name: "Pool", icon: "pool" },
  { name: "Porch", icon: "deck" },
  { name: "Shed", icon: "house_siding" },
  { name: "Storage", icon: "inventory_2" },
  { name: "Utility Room", icon: "electrical_services" },
  { name: "Workshop", icon: "construction" },
  { name: "Yard", icon: "yard" }
];

window.commonHomeAreaName = function (area) {
  return typeof area === "string"
    ? area
    : String(area?.name || "").trim();
};

window.commonHomeAreaIcon = function (area) {
  return typeof area === "string"
    ? ""
    : String(area?.icon || "").trim();
};

window.getRoomIcon = function (room) {
  const clean = String(room || "").trim();
  const key = clean.toLowerCase();

  const commonArea = window.COMMON_HOME_AREAS.find(area =>
    commonHomeAreaName(area).toLowerCase() === key
  );

  return commonHomeAreaIcon(commonArea) || "meeting_room";
};

window.getProvisionZoneOptions = function () {
  const used = Array.isArray(S.currentUsedZones) ? S.currentUsedZones : [];
  const seen = new Set();
  const out = [];

  [...used, ...window.COMMON_HOME_AREAS].forEach(area => {
    const clean = commonHomeAreaName(area);
    const key = clean.toLowerCase();

    if (!clean || seen.has(key)) return;

    seen.add(key);
    out.push(clean);
  });
  return out;
};

window.guessProvisionZone = function (clientName = "") {
  const zones = getProvisionZoneOptions();
  const name = String(clientName || "").toLowerCase();

  const exact = zones.find(z => name === String(z).toLowerCase());
  if (exact) return exact;

  const contained = zones.find(z => {
    const zone = String(z).toLowerCase();
    return zone && name.includes(zone);
  });

  return contained || "";
};

window.clientRoomName = function (c) {
  return String(
    c?.zone_name ||
    c?.zoneName ||
    c?.room_name ||
    c?.room ||
    c?.zone ||
    c?.area ||
    "Unassigned"
  ).trim() || "Unassigned";
};

window.groupClientsByRoom = function (clients) {
  const groups = new Map();

  (clients || []).forEach(c => {
    const room = clientRoomName(c);
    if (!groups.has(room)) groups.set(room, []);
    groups.get(room).push(c);
  });

  return Array.from(groups.entries())
    .sort(([a], [b]) => a.localeCompare(b, undefined, { sensitivity: "base" }));
};

window.getColumnBuilderViewportWidth = window.getColumnBuilderViewportWidth || function () {
  const wrap = document.querySelector("#sectionClients > div");
  const main = document.querySelector(".app-main");
  const width =
    wrap?.getBoundingClientRect?.().width ||
    main?.getBoundingClientRect?.().width ||
    window.innerWidth ||
    0;

  return Math.max(0, width);
};

window.getColumnBuilderCapacity = window.getColumnBuilderCapacity || function () {
  const width = window.getColumnBuilderViewportWidth?.() || window.innerWidth || 0;

  if (
    window.matchMedia?.("(orientation: portrait)")?.matches ||
    window.matchMedia?.("(pointer: coarse) and (max-width: 950px)")?.matches ||
    width < 700
  ) {
    return 1;
  }

  const rootStyle = getComputedStyle(document.documentElement);
  const bodyStyle = getComputedStyle(document.body);
  const gap =
    parseFloat(bodyStyle.getPropertyValue("--outer-space")) ||
    parseFloat(rootStyle.getPropertyValue("--outer-space")) ||
    16;
  const baseColumnCardMinWidth = 300;
  const columnCardMinWidth = baseColumnCardMinWidth * 1.25;
  const columnsFit = (cols) => width >= ((cols * columnCardMinWidth) + ((cols - 1) * gap));

  if (columnsFit(4)) return 4;
  if (columnsFit(3)) return 3;

  return 2;
};

window.getResolvedColumnBuilderColumns = window.getResolvedColumnBuilderColumns || function () {
  return Math.max(
    1,
    Math.min(4, window.getColumnBuilderCapacity?.() || 1)
  );
};

window.getColumnBuilderLayoutWidth = window.getColumnBuilderLayoutWidth || function () {
  const grouped = document.getElementById("clientCards")?.classList.contains("room-dashboard");

  if (grouped) {
    const clientCards = document.getElementById("clientCards");
    if (clientCards?.clientWidth) return clientCards.clientWidth;
  }

  const cameraClients = document.getElementById("cameraClients");
  if (cameraClients?.clientWidth) return cameraClients.clientWidth;

  const sectionClients = document.getElementById("sectionClients");
  if (sectionClients?.clientWidth) return sectionClients.clientWidth;

  return window.getColumnBuilderViewportWidth?.() || window.innerWidth || 0;
};

window.applyColumnBuilderLayoutVars = window.applyColumnBuilderLayoutVars || function () {
  const root = document.documentElement;
  const bodyStyle = getComputedStyle(document.body);
  const gap = parseFloat(bodyStyle.getPropertyValue("--outer-space")) || 16;
  const width = window.getColumnBuilderLayoutWidth?.() || window.innerWidth || 0;
  const capacity = window.getColumnBuilderCapacity?.() || 1;
  const cols = window.getResolvedColumnBuilderColumns?.() || 1;
  const cardWidth = Math.max(1, Math.floor((width - ((cols - 1) * gap)) / cols));

  root.style.setProperty("--dashboard-columns", String(cols));
  root.style.setProperty("--dashboard-layout-width", `${width}px`);
  root.style.setProperty("--dashboard-card-width", `${cardWidth}px`);

  document.body.dataset.dashboardColumnCapacity = String(capacity);
  document.body.dataset.dashboardColumnsResolved = String(cols);

  return { width, gap, capacity, cols, cardWidth };
};

window.estimateRoomLayoutWeight = function (_roomName, roomData) {
  const cameraWeight = 4.5;

  return (
    1 +
    ((roomData.controls || []).length * 1.2) +
    ((roomData.sensors || []).length * 1.35) +
    ((roomData.cameras || []).length * cameraWeight)
  );
};

window.getRoomGridColumnCount = function () {
  const width = window.getColumnBuilderLayoutWidth?.() || window.getColumnBuilderViewportWidth?.() || window.innerWidth;
  const cols = window.getResolvedColumnBuilderColumns?.() || 4;

  if (width < 650 || window.matchMedia?.("(orientation: portrait)")?.matches) return 1;

  return Math.max(1, Math.min(cols, 4));
};

window.getRoomColumnSpan = function (roomData, gridColumns) {
  const controls = (roomData.controls || []).length;
  const sensors = (roomData.sensors || []).length;
  const cameras = (roomData.cameras || []).length;

  if (S.renderMonitors) {
    return Math.max(1, Math.min(cameras || 1, gridColumns));
  }

  if (S.renderControls || S.renderSensors) {
    const visibleDevices = S.renderControls ? controls : sensors;
    const visibleDeviceSpan = 1 + Math.floor(visibleDevices / 4);

    return Math.max(1, Math.min(visibleDeviceSpan, gridColumns));
  }

  const controlSpan = controls ? Math.min(controls, gridColumns) : 1;
  const sensorSpan = Math.max(1, 1 + Math.floor(Number(sensors || 0) / 4));
  const cameraSpan = cameras ? Math.min(cameras, gridColumns) : 1;

  return Math.max(
    1,
    Math.min(gridColumns, Math.max(controlSpan, sensorSpan, cameraSpan))
  );
};

window.getRoomDashboardColumns = function (itemCount, roomSpan) {
  return Math.max(1, Math.min(Number(itemCount || 0) || 1, roomSpan));
};