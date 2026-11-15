// Mode selection for the Alzette twin: an entry screen asks what type of user is visiting
// (Casual or In-depth, Casual by default), and a small switch at the top of the map changes the
// mode later without reloading. The last choice is kept in localStorage and preselected next time;
// the entry screen is still shown on every visit.
//
// The mode is announced with the window event "alzette-twin-mode" ({ mode }); water-level-control.js
// shows or hides its in-depth panels, casual-ui.js its Casual panel. Both act on the same twin
// state (window.AlzetteTwin), so the date and the layers shown stay when the mode changes.
(function (root) {
  "use strict";

  var STORAGE_KEY = "twin-ui-mode";
  var MODES = [
    ["casual", "Casual", "A simple view: pick a day, play it back, and switch rain, river and buildings on or off."],
    ["indepth", "In-depth", "Every system of the twin and all its settings: gauges, flood scenarios, terrain, models and data."]
  ];
  var DEFAULT_MODE = "casual";

  function isMode(value) {
    return MODES.some(function (mode) { return mode[0] === value; });
  }

  // The mode preselected on the entry screen: the last one chosen, or Casual.
  function initialMode(storage) {
    try {
      var stored = storage && storage.getItem(STORAGE_KEY);
      return isMode(stored) ? stored : DEFAULT_MODE;
    } catch (e) {
      return DEFAULT_MODE;
    }
  }

  function saveMode(storage, mode) {
    try {
      if (storage && isMode(mode)) {
        storage.setItem(STORAGE_KEY, mode);
      }
    } catch (e) { /* storage unavailable: the choice holds for this visit only */ }
  }

  var current = null;

  function setMode(mode) {
    if (!isMode(mode)) {
      return;
    }
    current = mode;
    saveMode(root.localStorage, mode);
    var doc = root.document;
    if (doc) {
      Array.prototype.forEach.call(doc.querySelectorAll("#twin-mode-switch button"), function (button) {
        button.setAttribute("aria-pressed", button.getAttribute("data-mode") === mode ? "true" : "false");
      });
      var switcher = doc.getElementById("twin-mode-switch");
      if (switcher) {
        switcher.hidden = false;
      }
    }
    root.dispatchEvent(new root.CustomEvent("alzette-twin-mode", { detail: { mode: mode } }));
  }

  var STYLE = [
    "#twin-mode-entry{position:fixed;inset:0;z-index:100000;display:flex;align-items:center;justify-content:center;",
    "background:rgba(14,20,30,0.82);backdrop-filter:blur(3px);font:16px/1.45 Nunito,\"Segoe UI\",sans-serif;color:#e8ecf2;",
    "padding:16px;box-sizing:border-box}",
    "#twin-mode-entry .tm-card{width:100%;max-width:440px;background:rgb(32,38,52);border-radius:12px;padding:24px;",
    "box-shadow:0 8px 32px rgba(0,0,0,0.45);box-sizing:border-box}",
    "#twin-mode-entry h1{margin:0 0 4px;font-size:22px}",
    "#twin-mode-entry p.tm-lead{margin:0 0 16px;opacity:.75;font-size:14px}",
    "#twin-mode-entry fieldset{border:0;margin:0 0 18px;padding:0;display:flex;flex-direction:column;gap:10px}",
    "#twin-mode-entry legend{font-weight:700;margin-bottom:10px;font-size:17px}",
    "#twin-mode-entry label{display:flex;gap:12px;align-items:flex-start;padding:12px 14px;border-radius:8px;cursor:pointer;",
    "border:2px solid rgba(255,255,255,0.12);background:rgba(255,255,255,0.04)}",
    "#twin-mode-entry label:has(input:checked){border-color:#5b8fd8;background:rgba(63,111,181,0.22)}",
    "#twin-mode-entry input{accent-color:#3f6fb5;width:18px;height:18px;margin:3px 0 0}",
    "#twin-mode-entry .tm-name{font-weight:700;display:block}",
    "#twin-mode-entry .tm-desc{font-size:13px;opacity:.75}",
    "#twin-mode-entry button{width:100%;border:0;border-radius:8px;padding:12px;font:inherit;font-weight:700;",
    "background:#3f6fb5;color:#fff;cursor:pointer}",
    "#twin-mode-entry button:hover,#twin-mode-entry button:focus-visible{filter:brightness(1.12)}",
    "#twin-mode-switch{position:fixed;top:8px;left:50%;transform:translateX(-50%);z-index:1500;display:flex;",
    "background:rgba(32,38,52,0.92);border-radius:16px;padding:3px;box-shadow:0 2px 8px rgba(0,0,0,0.3);",
    "font:12px/1 Nunito,\"Segoe UI\",sans-serif}",
    "#twin-mode-switch[hidden]{display:none}",
    "#twin-mode-switch button{border:0;background:none;color:#e8ecf2;padding:6px 12px;border-radius:13px;cursor:pointer;",
    "font:inherit;font-weight:700;opacity:.7}",
    "#twin-mode-switch button[aria-pressed=true]{background:#3f6fb5;opacity:1}"
  ].join("");

  function element(doc, tag, className, text) {
    var node = doc.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text) {
      node.textContent = text;
    }
    return node;
  }

  function buildEntry(doc) {
    var overlay = element(doc, "div");
    overlay.id = "twin-mode-entry";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-labelledby", "twin-mode-title");
    var card = element(doc, "form", "tm-card");
    var title = element(doc, "h1", null, "Alzette river twin");
    title.id = "twin-mode-title";
    card.appendChild(title);
    card.appendChild(element(doc, "p", "tm-lead", "A digital twin of the Alzette in Luxembourg: its water, rain, floods and the town around it."));
    var fieldset = element(doc, "fieldset");
    fieldset.appendChild(element(doc, "legend", null, "What type of user are you?"));
    var preselected = initialMode(root.localStorage);
    MODES.forEach(function (mode) {
      var label = element(doc, "label");
      var input = doc.createElement("input");
      input.type = "radio";
      input.name = "twin-mode";
      input.value = mode[0];
      input.id = "twin-mode-option-" + mode[0];
      input.checked = mode[0] === preselected;
      label.appendChild(input);
      var text = element(doc, "span");
      text.appendChild(element(doc, "span", "tm-name", mode[1]));
      text.appendChild(element(doc, "span", "tm-desc", mode[2]));
      label.appendChild(text);
      fieldset.appendChild(label);
    });
    card.appendChild(fieldset);
    var go = element(doc, "button", null, "Continue");
    go.type = "submit";
    go.id = "twin-mode-continue";
    card.appendChild(go);
    card.addEventListener("submit", function (event) {
      event.preventDefault();
      var chosen = card.querySelector("input[name=twin-mode]:checked");
      overlay.remove();
      setMode(chosen ? chosen.value : DEFAULT_MODE);
    });
    overlay.appendChild(card);
    doc.body.appendChild(overlay);
    var checked = card.querySelector("input:checked");
    if (checked) {
      checked.focus();
    }
  }

  // The switch at the top of the map, shown once a mode is chosen.
  function buildSwitch(doc) {
    var switcher = element(doc, "div");
    switcher.id = "twin-mode-switch";
    switcher.hidden = true;
    switcher.setAttribute("role", "group");
    switcher.setAttribute("aria-label", "View mode");
    MODES.forEach(function (mode) {
      var button = element(doc, "button", null, mode[1]);
      button.type = "button";
      button.setAttribute("data-mode", mode[0]);
      button.setAttribute("aria-pressed", "false");
      button.title = mode[2];
      button.addEventListener("click", function () { setMode(mode[0]); });
      switcher.appendChild(button);
    });
    doc.body.appendChild(switcher);
  }

  function start() {
    var doc = root.document;
    var style = doc.createElement("style");
    style.textContent = STYLE;
    doc.head.appendChild(style);
    buildSwitch(doc);
    buildEntry(doc);
  }

  root.TwinMode = {
    STORAGE_KEY: STORAGE_KEY,
    DEFAULT_MODE: DEFAULT_MODE,
    initialMode: initialMode,
    saveMode: saveMode,
    current: function () { return current; },
    set: setMode
  };

  if (root.document) {
    if (root.document.readyState === "loading") {
      root.document.addEventListener("DOMContentLoaded", start);
    } else {
      start();
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
