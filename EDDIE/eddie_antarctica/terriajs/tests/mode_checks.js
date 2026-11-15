/* Dependency-free checks of the mode selection (twin-mode.js), the Casual mode (casual-ui.js) and the
 * state they share with the In-depth panels (water-level-control.js).
 * Usage: node mode_checks.js <terriajs directory>
 * The modules run in a minimal fake browser: no DOM is built, only their exported functions are used.
 */
"use strict";
var fs = require("fs");
var path = require("path");
var vm = require("vm");

var dir = process.argv[2] || path.join(__dirname, "..");
var count = 0;

function assert(value, message) {
  if (!value) {
    throw new Error(message || "Assertion failed");
  }
  count++;
}

function equal(a, b, message) {
  assert(JSON.stringify(a) === JSON.stringify(b), (message || "") + ": " + JSON.stringify(a) + " != " + JSON.stringify(b));
}

function memoryStorage(initial) {
  var values = Object.assign({}, initial);
  return {
    getItem: function (key) { return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : null; },
    setItem: function (key, value) { values[key] = String(value); },
    values: values
  };
}

// A browser-like global: events, storage, a location hash, and a document that never becomes ready
// (so the modules do not build their panels).
function fakeWindow(storage) {
  var listeners = {};
  var win = {
    localStorage: storage,
    location: { hash: "" },
    events: [],
    document: {
      readyState: "loading",
      addEventListener: function () {},
      querySelectorAll: function () { return []; },
      getElementById: function () { return null; },
      body: { classList: { toggle: function () {} } }
    },
    addEventListener: function (type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    dispatchEvent: function (event) {
      win.events.push(event);
      (listeners[event.type] || []).forEach(function (fn) { fn(event); });
    },
    CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    setTimeout: setTimeout, setInterval: function () { return 0; }, clearInterval: function () {},
    fetch: function () { return new Promise(function () {}); },
    Promise: Promise, JSON: JSON, Math: Math, Date: Date, Object: Object, Array: Array, String: String, Number: Number
  };
  win.window = win;
  win.globalThis = win;
  return win;
}

// Just enough of a DOM for water-level-control.js to build its panels (elements are plain objects).
function fakeDocument() {
  var all = [];
  function make(tag) {
    var node = {
      tagName: tag.toUpperCase(), children: [], style: {}, attributes: {}, listeners: {}, className: "", textContent: "",
      value: "", checked: false, offsetLeft: 0, offsetTop: 0, offsetWidth: 200, offsetHeight: 100, parentNode: null,
      classList: { toggle: function () {}, add: function () {}, remove: function () {} },
      appendChild: function (child) { child.parentNode = node; node.children.push(child); return child; },
      insertBefore: function (child) { child.parentNode = node; node.children.unshift(child); return child; },
      setAttribute: function (name, value) { node.attributes[name] = String(value); },
      getAttribute: function (name) { return node.attributes[name]; },
      addEventListener: function (type, fn) { (node.listeners[type] = node.listeners[type] || []).push(fn); },
      dispatchEvent: function (event) { (node.listeners[event.type] || []).forEach(function (fn) { fn(event); }); },
      closest: function () { return null; },
      getClientRects: function () { return [{}]; },
      querySelector: function () { return null; },
      remove: function () {}
    };
    Object.defineProperty(node, "firstChild", { get: function () { return node.children[0] || null; } });
    Object.defineProperty(node, "lastChild", { get: function () { return node.children[node.children.length - 1] || null; } });
    all.push(node);
    return node;
  }
  var doc = {
    readyState: "complete",
    head: make("head"),
    body: make("body"),
    createElement: make,
    createTextNode: function (text) { return { textContent: text }; },
    addEventListener: function () {},
    querySelectorAll: function () { return []; },
    getElementById: function (id) { return doc.byId(id); },
    byId: function (id) { return all.find(function (node) { return node.id === id; }) || null; }
  };
  return doc;
}

function load(win, file) {
  var context = vm.createContext(win);
  vm.runInContext(fs.readFileSync(path.join(dir, file), "utf8"), context, { filename: file });
  return win;
}

function microtasks() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

(async function () {
  // --- Mode selection: Casual by default, the last choice preselected -------------------------
  var win = load(fakeWindow(memoryStorage()), "twin-mode.js");
  var mode = win.TwinMode;
  equal(mode.initialMode(memoryStorage()), "casual", "Casual is the default");
  equal(mode.initialMode(memoryStorage({ "twin-ui-mode": "indepth" })), "indepth", "last choice preselected");
  equal(mode.initialMode(memoryStorage({ "twin-ui-mode": "expert" })), "casual", "unknown stored value ignored");
  equal(mode.initialMode({ getItem: function () { throw new Error("blocked"); } }), "casual", "blocked storage");
  equal(mode.initialMode(null), "casual", "no storage");
  var stored = memoryStorage();
  mode.saveMode(stored, "nonsense");
  equal(stored.getItem("twin-ui-mode"), null, "invalid mode not saved");
  equal(mode.current(), null, "no mode before the entry screen is confirmed");
  mode.set("indepth");
  equal(win.localStorage.getItem("twin-ui-mode"), "indepth", "choice remembered");
  equal(mode.current(), "indepth", "current mode");
  var last = win.events[win.events.length - 1];
  equal([last.type, last.detail.mode], ["alzette-twin-mode", "indepth"], "mode announced");

  // --- Casual mode helpers ------------------------------------------------------------------------
  win = load(fakeWindow(memoryStorage()), "casual-ui.js");
  var casual = win.CasualUI;
  assert(casual.BUTTONS.length <= 5, "at most five Casual buttons");
  var names = casual.BUTTONS.map(function (b) { return b[0]; });
  ["rain", "river", "buildings"].forEach(function (name) { assert(names.indexOf(name) >= 0, name + " button present"); });
  equal(casual.BUTTONS.slice(0, 3).map(function (b) { return b[2]; }), ["Show rain", "Show river", "Show buildings"], "labels");
  var clock = { start: Date.UTC(2026, 9, 5), stop: Date.UTC(2026, 9, 5, 23, 59, 59) };
  equal(casual.msToSlider(clock, clock.start), 0, "slider start");
  equal(casual.msToSlider(clock, clock.stop), casual.STEPS, "slider end");
  equal(casual.msToSlider(clock, clock.stop + 1e6), casual.STEPS, "slider clamped");
  equal(casual.sliderToMs(clock, casual.STEPS / 2), clock.start + (clock.stop - clock.start) / 2, "slider middle");
  equal(casual.formatClock(Date.UTC(2026, 9, 5, 14, 5)), "14:05", "clock time");
  assert(/Monday.*2026/.test(casual.statusText({ replayDate: "2026-10-05", layers: {} })), "replay status");
  assert(/now/.test(casual.statusText({ mode: "LIVE", layers: {} })), "live status");

  // --- Shared state: Casual buttons act on the twin's own state (water-level-control.js) ----------
  win = load(fakeWindow(memoryStorage()), "water-level-control.js");
  load(win, "casual-ui.js");
  var twin = win.AlzetteTwin;
  equal(names.slice().sort(), twin.LAYER_NAMES.slice().sort(), "every Casual button is a shared layer");
  equal(twin.getState().layers, { rain: true, river: true, buildings: false, zones: false, names: false }, "defaults");
  var changes = [];
  win.addEventListener("alzette-twin-change", function (event) { changes.push(event.detail); });

  win.CasualUI.toggle(twin, "river");
  await microtasks();
  equal(twin.getState().layers.river, false, "river hidden");
  equal(changes[changes.length - 1].layers.river, false, "In-depth panels told of the change");

  win.CasualUI.toggle(twin, "buildings");
  await microtasks();
  equal(twin.getState().layers.buildings, true, "buildings shown");
  assert(win.location.hash.indexOf("/terria-water-init/layers/rain/") >= 0, "rain kept in the init file: " + win.location.hash);
  assert(/buildings\.json$/.test(win.location.hash), "buildings in the init file: " + win.location.hash);

  win.CasualUI.toggle(twin, "rain");
  win.CasualUI.toggle(twin, "zones");
  win.CasualUI.toggle(twin, "names");
  await microtasks();
  equal(twin.getState().layers, { rain: false, river: false, buildings: true, zones: true, names: true }, "all switched");
  assert(win.location.hash.indexOf("layers/zones-hq100/") >= 0, "flood zones in the init file: " + win.location.hash);
  assert(win.location.hash.indexOf("names/streets,other/") >= 0, "place names in the init file: " + win.location.hash);
  assert(win.location.hash.indexOf("rain") < 0, "rain left out: " + win.location.hash);

  // Switching mode changes only what is shown, never the state.
  var before = JSON.stringify(twin.getState().layers);
  twin.setUiMode("casual");
  await microtasks();
  equal(twin.getState().uiMode, "casual", "Casual mode applied");
  twin.setUiMode("indepth");
  await microtasks();
  equal(JSON.stringify(twin.getState().layers), before, "layers kept across mode switches");

  // --- The In-depth panels build without errors, with every new control ----------------------------
  win = fakeWindow(memoryStorage());
  var doc = fakeDocument();
  win.document = doc;
  win.innerWidth = 1500;
  win.innerHeight = 800;
  win.requestAnimationFrame = function () {};
  win.Event = function (type) { this.type = type; };
  load(win, "water-level-control.js");
  [
    "water-level-control-category-layers", "water-level-control-layer-rain", "water-level-control-layer-zones-hq10",
    "water-level-control-layer-zones-hq100", "water-level-control-layer-zones-hqextreme", "water-level-control-layer-fees",
    "water-level-control-water-surface", "water-level-control-water-rippleSize", "water-level-control-water-period",
    "water-level-control-water-amplitude", "water-level-control-water-fps", "water-level-control-poll",
    "water-level-control-replay-speed", "water-level-control-rain-start", "water-level-control-rain-end",
    "water-level-control-sun-twilight", "water-level-control-sun-day", "water-level-control-sun-night",
    "water-level-control-fees-volume", "water-level-control-fees-percentage", "water-level-control-fees-price",
    "water-level-control-damage", "water-level-control-replay-date"
  ].forEach(function (id) { assert(doc.byId(id), "In-depth control built: " + id); });
  var readyEvents = win.events.filter(function (event) { return event.type === "alzette-twin-ready"; });
  equal(readyEvents.length, 1, "the panels finished building");
  // A Casual change ticks the In-depth box.
  win.AlzetteTwin.setLayer("zones", true);
  await microtasks();
  equal(doc.byId("water-level-control-layer-zones-hq100").checked, true, "In-depth box follows the shared state");

  console.log(count + " mode checks passed");
  // The panels keep retrying to find Terria; nothing else is left to check.
  process.exit(0);
})().catch(function (error) {
  console.error(error.stack || error);
  process.exit(1);
});
