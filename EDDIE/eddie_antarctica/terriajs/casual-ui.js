// Casual mode of the Alzette twin: one simple panel at the bottom of the map with a day to replay
// (date, play / pause, a timeline to drag) and five large on/off buttons. Everything else keeps
// its default. Shown while the mode chosen in twin-mode.js is "casual".
//
// The panel can be moved by its top bar (mouse, touch or pen), always stays fully on screen, and
// keeps its place in localStorage; double-clicking the bar or its reset button puts it back.
//
// It holds no state of its own: every button and the timeline act on window.AlzetteTwin
// (water-level-control.js), the same state the In-depth panels use, and it redraws itself from
// the "alzette-twin-change" and "alzette-twin-clock" events.
(function (root) {
  "use strict";

  // The buttons: shared layer name (AlzetteTwin.LAYER_NAMES), icon, plain-language label.
  var BUTTONS = [
    ["rain", "🌧️", "Show rain"],
    ["river", "🌊", "Show river"],
    ["buildings", "🏠", "Show buildings"],
    ["zones", "⚠️", "Show flood areas"],
    ["names", "🏷️", "Show place names"]
  ];
  // Positions of the timeline slider over a replayed day.
  var STEPS = 1000;
  // Where the panel was moved to ({left, top} in px), kept between sessions.
  var POSITION_KEY = "casual-panel-position";

  // Switch one layer: on if it is off, off if it is on, in the shared state.
  function toggle(api, name) {
    var on = !api.getState().layers[name];
    api.setLayer(name, on);
    return on;
  }

  function sliderToMs(clock, value) {
    return clock.start + (clock.stop - clock.start) * Math.max(0, Math.min(STEPS, value)) / STEPS;
  }

  function msToSlider(clock, ms) {
    if (!(clock.stop > clock.start)) {
      return 0;
    }
    return Math.round(Math.max(0, Math.min(1, (ms - clock.start) / (clock.stop - clock.start))) * STEPS);
  }

  // Replay times are the gauges' local clock times (stored labelled UTC): shown as they are.
  function formatClock(ms) {
    var date = new Date(ms);
    function two(n) { return (n < 10 ? "0" : "") + n; }
    return two(date.getUTCHours()) + ":" + two(date.getUTCMinutes());
  }

  // Top-left corner of a width x height panel moved to (left, top), kept inside a viewWidth x viewHeight
  // window. A panel larger than the window sticks to its top-left corner.
  function clampPosition(left, top, width, height, viewWidth, viewHeight) {
    return {
      left: Math.round(Math.max(0, Math.min(left, viewWidth - width))),
      top: Math.round(Math.max(0, Math.min(top, viewHeight - height)))
    };
  }

  function loadPosition(storage) {
    try {
      var stored = JSON.parse(storage.getItem(POSITION_KEY));
      if (stored && isFinite(stored.left) && isFinite(stored.top)) {
        return { left: Number(stored.left), top: Number(stored.top) };
      }
    } catch (e) { /* storage unavailable or invalid: default place */ }
    return null;
  }

  function savePosition(storage, position) {
    try {
      if (position) {
        storage.setItem(POSITION_KEY, JSON.stringify(position));
      } else {
        storage.removeItem(POSITION_KEY);
      }
    } catch (e) { /* storage unavailable: the position is not kept */ }
  }

  // The sentence at the top of the panel: what the map shows now.
  function statusText(state) {
    if (state.replayDate) {
      return "Showing " + new Date(state.replayDate + "T12:00:00Z").toLocaleDateString("en-GB", {
        weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC"
      }) + ".";
    }
    if (state.scenario) {
      return "Showing a flood scenario (" + state.scenario.toUpperCase() + ").";
    }
    if (state.mode === "MANUAL") {
      return "Showing a water level set by hand.";
    }
    if (state.mode === "HISTORICAL") {
      return "Showing a historical day.";
    }
    return "Showing the river now (latest gauge readings).";
  }

  var STYLE = [
    "#casual-panel{position:fixed;left:50%;bottom:76px;transform:translateX(-50%);z-index:1200;",
    "width:min(760px,calc(100vw - 32px));box-sizing:border-box;padding:14px 16px;border-radius:12px;",
    "background:rgba(32,38,52,0.95);color:#e8ecf2;box-shadow:0 6px 24px rgba(0,0,0,0.4);",
    "font:16px/1.4 Nunito,\"Segoe UI\",sans-serif}",
    "#casual-panel[hidden]{display:none}",
    "#casual-panel.cs-moved{transform:none;bottom:auto}",
    "#casual-panel .cs-handle{display:flex;align-items:center;gap:8px;margin:-8px -6px 6px;padding:2px 6px;cursor:grab;",
    "touch-action:none;user-select:none;-webkit-user-select:none;border-radius:8px;opacity:.6}",
    "#casual-panel .cs-handle:hover{opacity:.95;background:rgba(255,255,255,0.06)}",
    "#casual-panel.cs-dragging .cs-handle{cursor:grabbing;opacity:.95}",
    "#casual-panel .cs-grip{flex:1;text-align:center;font-size:16px;line-height:18px;letter-spacing:1px}",
    "#casual-panel button.cs-reset{font-size:15px;font-weight:400;padding:0 8px;background:none;color:inherit}",
    "#casual-panel button.cs-reset[hidden]{display:none}",
    "#casual-panel .cs-status{font-weight:700;margin:0 0 10px}",
    "#casual-panel .cs-note{font-size:13px;opacity:.75;margin-top:4px;min-height:1em}",
    "#casual-panel .cs-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px}",
    "#casual-panel input[type=date]{font:inherit;padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.2);",
    "background:rgba(255,255,255,0.08);color:inherit;color-scheme:dark;min-width:0}",
    "#casual-panel button{font:inherit;font-weight:700;border:0;border-radius:8px;padding:9px 14px;cursor:pointer;",
    "background:#3f6fb5;color:#fff}",
    "#casual-panel button.cs-secondary{background:rgba(255,255,255,0.14)}",
    "#casual-panel button:hover,#casual-panel button:focus-visible{filter:brightness(1.15)}",
    "#casual-panel button:disabled{opacity:.4;cursor:default;filter:none}",
    "#casual-panel .cs-play{width:52px;height:44px;font-size:20px;padding:0;flex:0 0 auto}",
    "#casual-panel input[type=range]{flex:1;min-width:120px;accent-color:#5b8fd8;height:28px}",
    "#casual-panel .cs-time{font-variant-numeric:tabular-nums;font-weight:700;min-width:48px;text-align:right}",
    "#casual-panel .cs-toggles{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));gap:8px}",
    "#casual-panel .cs-toggle{display:flex;flex-direction:column;align-items:center;gap:4px;padding:10px 6px;",
    "background:rgba(255,255,255,0.06);border:2px solid rgba(255,255,255,0.14);color:#e8ecf2;opacity:.85}",
    "#casual-panel .cs-toggle .cs-icon{font-size:24px;line-height:1;filter:grayscale(1);opacity:.6}",
    "#casual-panel .cs-toggle .cs-state{font-size:12px;font-weight:700;letter-spacing:.06em}",
    "#casual-panel .cs-toggle[aria-pressed=true]{background:rgba(63,111,181,0.35);border-color:#7fb0f0;opacity:1}",
    "#casual-panel .cs-toggle[aria-pressed=true] .cs-icon{filter:none;opacity:1}",
    "@media (max-width:520px){#casual-panel{bottom:8px;padding:12px}#casual-panel.cs-moved{bottom:auto}#casual-panel .cs-toggles{grid-template-columns:repeat(2,1fr)}}"
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

  function start() {
    var doc = root.document;
    var style = doc.createElement("style");
    style.textContent = STYLE;
    doc.head.appendChild(style);

    var panel = element(doc, "section");
    panel.id = "casual-panel";
    panel.hidden = true;
    panel.setAttribute("aria-label", "Alzette twin, simple view");

    // The bar to move the panel by: the only place a drag starts, so buttons and sliders never move it.
    var handle = element(doc, "div", "cs-handle");
    handle.id = "casual-handle";
    handle.title = "Drag to move the panel. Double-click to put it back.";
    handle.appendChild(element(doc, "span", "cs-grip", "\u2022\u2022\u2022\u2022\u2022\u2022"));
    var reset = element(doc, "button", "cs-reset", "\u21ba");
    reset.type = "button";
    reset.id = "casual-reset-position";
    reset.title = "Put the panel back in its place";
    reset.setAttribute("aria-label", "Put the panel back in its place");
    handle.appendChild(reset);
    panel.appendChild(handle);
    var status = element(doc, "p", "cs-status", "Loading the twin...");
    status.id = "casual-status";
    status.setAttribute("aria-live", "polite");
    panel.appendChild(status);

    // Pick a day, or go back to now.
    var dayRow = element(doc, "div", "cs-row");
    var day = doc.createElement("input");
    day.type = "date";
    day.id = "casual-date";
    day.setAttribute("aria-label", "Day to show");
    day.max = new Date().toISOString().slice(0, 10);
    var showDay = element(doc, "button", null, "Show this day");
    showDay.type = "button";
    showDay.id = "casual-show-day";
    var liveNow = element(doc, "button", "cs-secondary", "Back to now");
    liveNow.type = "button";
    liveNow.id = "casual-live";
    dayRow.appendChild(day);
    dayRow.appendChild(showDay);
    dayRow.appendChild(liveNow);
    panel.appendChild(dayRow);

    // Play the day back, or drag through it.
    var timeRow = element(doc, "div", "cs-row");
    var play = element(doc, "button", "cs-play", "▶");
    play.type = "button";
    play.id = "casual-play";
    play.setAttribute("aria-label", "Play");
    var scrub = doc.createElement("input");
    scrub.type = "range";
    scrub.id = "casual-timeline";
    scrub.min = "0";
    scrub.max = String(STEPS);
    scrub.value = "0";
    scrub.setAttribute("aria-label", "Time of day");
    var time = element(doc, "span", "cs-time", "--:--");
    time.id = "casual-time";
    timeRow.appendChild(play);
    timeRow.appendChild(scrub);
    timeRow.appendChild(time);
    panel.appendChild(timeRow);
    var note = element(doc, "div", "cs-note");
    note.id = "casual-note";
    panel.appendChild(note);

    // The five on/off buttons.
    var toggles = element(doc, "div", "cs-toggles");
    var buttons = {};
    BUTTONS.forEach(function (entry) {
      var button = element(doc, "button", "cs-toggle");
      button.type = "button";
      button.id = "casual-toggle-" + entry[0];
      button.setAttribute("aria-pressed", "false");
      button.appendChild(element(doc, "span", "cs-icon", entry[1]));
      button.appendChild(element(doc, "span", null, entry[2]));
      button.appendChild(element(doc, "span", "cs-state", "OFF"));
      button.addEventListener("click", function () {
        if (root.AlzetteTwin) {
          toggle(root.AlzetteTwin, entry[0]);
        }
      });
      toggles.appendChild(button);
      buttons[entry[0]] = button;
    });
    panel.appendChild(toggles);
    doc.body.appendChild(panel);

    // Moving the panel: a stored position is applied clamped to the window, and clamped again
    // whenever the window changes size or the panel is shown again.
    var position = loadPosition(root.localStorage);

    function applyPosition() {
      reset.hidden = !position;
      panel.classList.toggle("cs-moved", !!position);
      if (!position) {
        panel.style.left = "";
        panel.style.top = "";
        return;
      }
      var placed = clampPosition(position.left, position.top, panel.offsetWidth, panel.offsetHeight,
        root.innerWidth, root.innerHeight);
      panel.style.left = placed.left + "px";
      panel.style.top = placed.top + "px";
    }

    function resetPosition() {
      position = null;
      savePosition(root.localStorage, null);
      applyPosition();
    }

    handle.addEventListener("pointerdown", function (event) {
      if (event.target.closest("button") || (event.pointerType === "mouse" && event.button !== 0)) {
        return;
      }
      event.preventDefault();
      var rect = panel.getBoundingClientRect();
      var dx = event.clientX - rect.left;
      var dy = event.clientY - rect.top;
      var pointerId = event.pointerId;
      // Follow this pointer even over the map or outside the window; the map never sees the drag.
      try { handle.setPointerCapture(pointerId); } catch (e) { /* pointer already gone */ }
      panel.classList.add("cs-dragging");
      function move(e) {
        if (e.pointerId !== pointerId) {
          return;
        }
        position = clampPosition(e.clientX - dx, e.clientY - dy, panel.offsetWidth, panel.offsetHeight,
          root.innerWidth, root.innerHeight);
        applyPosition();
      }
      function end(e) {
        if (e.pointerId !== pointerId) {
          return;
        }
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", end);
        handle.removeEventListener("pointercancel", end);
        panel.classList.remove("cs-dragging");
        if (position) {
          savePosition(root.localStorage, position);
        }
      }
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", end);
      handle.addEventListener("pointercancel", end);
    });
    handle.addEventListener("dblclick", function (event) {
      if (!event.target.closest("button")) {
        resetPosition();
      }
    });
    reset.addEventListener("click", resetPosition);
    root.addEventListener("resize", function () {
      if (!panel.hidden) {
        applyPosition();
      }
    });

    var replaying = false;
    var dragging = false;
    var lastClock = null;

    function render(state) {
      if (!state) {
        return;
      }
      status.textContent = statusText(state);
      replaying = !!state.replayDate;
      if (state.replayDate && day.value !== state.replayDate) {
        day.value = state.replayDate;
      }
      BUTTONS.forEach(function (entry) {
        var on = !!state.layers[entry[0]];
        buttons[entry[0]].setAttribute("aria-pressed", on ? "true" : "false");
        buttons[entry[0]].lastChild.textContent = on ? "ON" : "OFF";
      });
      var rainNote = state.layers.rain && state.rainInfo ? state.rainInfo + " " : "";
      note.textContent = replaying ? rainNote : rainNote + "Pick a day and press “Show this day” to play it back.";
      renderClock(lastClock);
    }

    function renderClock(clock) {
      lastClock = clock;
      var usable = replaying && !!clock;
      play.disabled = !usable;
      scrub.disabled = !usable;
      if (!usable) {
        time.textContent = "--:--";
        play.textContent = "▶";
        return;
      }
      play.textContent = clock.playing ? "⏸" : "▶";
      play.setAttribute("aria-label", clock.playing ? "Pause" : "Play");
      time.textContent = formatClock(clock.current);
      if (!dragging) {
        scrub.value = String(msToSlider(clock, clock.current));
      }
    }

    showDay.addEventListener("click", function () {
      if (!day.value || !root.AlzetteTwin) {
        note.textContent = "Choose a day first.";
        return;
      }
      note.textContent = "Loading " + day.value + "...";
      root.AlzetteTwin.replayDay(day.value).then(function (result) {
        if (!result.ok) {
          note.textContent = result.message + " Try another day.";
        } else {
          // Start playing straight away once the day is loaded.
          setTimeout(function () { root.AlzetteTwin.play(true); }, 1500);
        }
      });
    });
    liveNow.addEventListener("click", function () {
      if (root.AlzetteTwin) {
        root.AlzetteTwin.goLive();
      }
    });
    play.addEventListener("click", function () {
      if (root.AlzetteTwin && lastClock) {
        root.AlzetteTwin.play(!lastClock.playing);
      }
    });
    scrub.addEventListener("pointerdown", function () { dragging = true; });
    scrub.addEventListener("input", function () {
      if (root.AlzetteTwin && lastClock) {
        var ms = sliderToMs(lastClock, Number(scrub.value));
        time.textContent = formatClock(ms);
        root.AlzetteTwin.seek(ms);
      }
    });
    scrub.addEventListener("change", function () { dragging = false; });

    root.addEventListener("alzette-twin-change", function (event) { render(event.detail); });
    root.addEventListener("alzette-twin-ready", function (event) { render(event.detail); });
    root.addEventListener("alzette-twin-clock", function (event) { renderClock(event.detail); });
    root.addEventListener("alzette-twin-mode", function (event) {
      panel.hidden = !(event.detail && event.detail.mode === "casual");
      if (!panel.hidden && root.AlzetteTwin) {
        render(root.AlzetteTwin.getState());
      }
      if (!panel.hidden) {
        // Its size is known only once shown (and the window may have changed meanwhile).
        applyPosition();
      }
    });
    if (root.AlzetteTwin) {
      render(root.AlzetteTwin.getState());
    }
    applyPosition();
  }

  root.CasualUI = {
    BUTTONS: BUTTONS,
    STEPS: STEPS,
    toggle: toggle,
    sliderToMs: sliderToMs,
    msToSlider: msToSlider,
    formatClock: formatClock,
    statusText: statusText,
    clampPosition: clampPosition,
    loadPosition: loadPosition,
    savePosition: savePosition,
    POSITION_KEY: POSITION_KEY
  };

  if (root.document) {
    if (root.document.readyState === "loading") {
      root.document.addEventListener("DOMContentLoaded", start);
    } else {
      start();
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
