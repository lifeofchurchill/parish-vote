/*
  Live turnout: the motion and live updates on the Electoral Commissioner's dashboard.

  1. When the page opens, everything counts up together from zero: the rose window
     lights clockwise from 12 o'clock, each pane flaring as it fills, while the
     numbers and bars rise with it. One movement, about two seconds.
  2. Every 15 seconds (only while the page is on screen) it quietly fetches the
     same page in the background, compares the numbers, and animates only what
     changed: numbers roll on, the window lights further, new ticks slide in.
     No full-page reload, so nothing flickers and the intro doesn't replay.
  3. Tapping a centre card (or a filter button) shows only that centre's latest ticks.

  Without this file the page still shows the correct numbers; it just doesn't move
  or update itself. Anything unexpected (sessions added, signed out) => full reload.
*/
(() => {
  "use strict";

  const REFRESH_EVERY = 15000;   // milliseconds between background updates
  const INTRO_TIME = 2000;       // the opening count-up
  const UPDATE_TIME = 1200;      // rolling to new numbers after an update
  const PANES = 24;              // panes of glass in the rose window

  const dash = document.querySelector("[data-dashboard]");
  if (!dash) return;             // "No election is open" page: nothing to animate

  // How many ticks to show in "Latest ticks" (RECENT_TICKS in commissioner_views.py)
  const RECENT_MAX = Number(dash.dataset.recentMax) || 15;

  // People who turn off animations on their phone or laptop get instant changes
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- Reading and drawing the numbers ----------

  // Every number on a page, as plain data: { values: {voted: 142, ...}, bars: {...}, turnout: 27.79 }
  function readState(root) {
    const state = { values: {}, bars: {}, turnout: 0 };
    root.querySelectorAll("[data-live]").forEach((el) => {
      state.values[el.dataset.live] = Number(el.dataset.value) || 0;
    });
    root.querySelectorAll("[data-bar]").forEach((el) => {
      state.bars[el.dataset.bar] = parseFloat(el.getAttribute("width")) || 0;
    });
    const sweep = root.querySelector("[data-rose-sweep]");
    if (sweep) state.turnout = parseFloat(sweep.getAttribute("stroke-dasharray")) || 0;
    return state;
  }

  // Same numbers and bars on both pages? If not (a session was added), we reload instead
  function sameShape(a, b) {
    const keys = (s) => Object.keys(s.values).concat(Object.keys(s.bars)).sort().join("|");
    return keys(a) === keys(b);
  }

  // A state part-way between two states: k = 0 is "from", k = 1 is "to"
  function between(from, to, k) {
    const mix = (a, b) => a + (b - a) * k;
    const state = { values: {}, bars: {}, turnout: mix(from.turnout, to.turnout) };
    for (const key in to.values) state.values[key] = mix(from.values[key] ?? 0, to.values[key]);
    for (const key in to.bars) state.bars[key] = mix(from.bars[key] ?? 0, to.bars[key]);
    return state;
  }

  // Put a state on the screen
  function draw(state) {
    for (const key in state.values) {
      const el = dash.querySelector(`[data-live="${key}"]`);
      if (el) el.textContent = Math.round(state.values[key]);
    }
    for (const key in state.bars) {
      const el = dash.querySelector(`[data-bar="${key}"]`);
      if (el) el.setAttribute("width", `${state.bars[key].toFixed(1)}%`);
    }
    const sweep = dash.querySelector("[data-rose-sweep]");
    if (sweep) sweep.setAttribute("stroke-dasharray", `${state.turnout.toFixed(2)} 100`);
  }

  // How many panes are completely lit at a given turnout
  const panesLit = (turnout) => Math.min(PANES, Math.floor((turnout * PANES) / 100 + 1e-6));

  // A pane that has just filled flares white-gold for a moment (CSS animation "pane-flare")
  function flare(index) {
    const pane = dash.querySelector(`[data-pane="${index}"]`);
    if (!pane) return;
    pane.classList.remove("is-new");
    pane.getBoundingClientRect();          // makes the browser notice, so the animation restarts
    pane.classList.add("is-new");
  }

  // A number that changed during a live update glows briefly
  function glow(el) {
    el.classList.remove("is-bumped");
    el.getBoundingClientRect();
    el.classList.add("is-bumped");
  }

  // ---------- The animation: one moving "k" drives everything, so it all stays in step ----------

  let running = null;   // the animation in progress, so a new one can replace it

  function animate(from, to, duration) {
    if (running) cancelAnimationFrame(running);
    if (reduceMotion || duration === 0) {
      draw(to);
      return;
    }
    const start = performance.now();
    let lit = panesLit(from.turnout);
    const easeOut = (t) => 1 - Math.pow(1 - t, 3);   // quick start, gentle landing

    function frame(now) {
      const t = Math.min((now - start) / duration, 1);
      const state = between(from, to, easeOut(t));
      draw(state);
      // Flare every pane the sweep has just filled
      const nowLit = panesLit(state.turnout);
      for (; lit < nowLit; lit++) flare(lit);
      running = t < 1 ? requestAnimationFrame(frame) : null;
    }
    running = requestAnimationFrame(frame);
  }

  // ---------- 1. The opening count-up ----------

  let current = readState(dash);
  const zero = between(current, current, 0);
  for (const key in zero.values) zero.values[key] = 0;
  for (const key in zero.bars) zero.bars[key] = 0;
  zero.turnout = 0;
  // Fixed figures stay put; "Still to vote" counts down from everyone as "Voted" counts up
  zero.values.eligible = current.values.eligible;
  zero.values.remaining = current.values.eligible;
  if (!reduceMotion) {
    draw(zero);
    animate(zero, current, INTRO_TIME);
  }

  // ---------- 2. Live updates in the background ----------

  const statusBox = dash.querySelector("[data-status]");
  const statusText = dash.querySelector("[data-status-text]");
  let busy = false;

  function setOnline(online) {
    statusBox.classList.toggle("is-offline", !online);
    statusText.textContent = online ? "Live" : "Can't reach the server. Retrying…";
  }

  // Swap the contents of a data-slot for the new page's version
  function replaceSlot(next, name) {
    const here = dash.querySelector(`[data-slot="${name}"]`);
    const there = next.querySelector(`[data-slot="${name}"]`);
    if (here && there) here.replaceChildren(...[...there.childNodes].map((n) => document.importNode(n, true)));
  }

  // Latest ticks: take the new list, and mark the ticks we haven't seen before,
  // so they slide in with a green wash
  function updateRecent(next) {
    const seen = new Set([...dash.querySelectorAll("[data-slot='recent'] li")].map((li) => li.dataset.id));
    replaceSlot(next, "recent");
    dash.querySelectorAll("[data-slot='recent'] li").forEach((li) => {
      if (!seen.has(li.dataset.id)) li.classList.add("is-new");
    });
  }

  async function refresh() {
    if (busy) return;
    busy = true;
    try {
      const response = await fetch(window.location.href, { cache: "no-store", credentials: "same-origin" });
      // Signed out (sent to the sign-in page)? Reload so the Commissioner sees it.
      if (response.redirected) return window.location.reload();
      if (!response.ok) throw new Error(`Server answered ${response.status}`);

      const next = new DOMParser().parseFromString(await response.text(), "text/html");
      const nextDash = next.querySelector("[data-dashboard]");
      const target = nextDash && readState(nextDash);
      // The election was closed, or sessions were added or removed: just reload the page
      if (!target || !sameShape(current, target)) return window.location.reload();

      setOnline(true);
      // Glow the numbers that changed, then roll everything to the new values
      for (const key in target.values) {
        if (target.values[key] !== current.values[key]) {
          const el = dash.querySelector(`[data-live="${key}"]`);
          if (el) { el.dataset.value = target.values[key]; glow(el); }
        }
      }
      animate(current, target, UPDATE_TIME);
      current = target;

      dash.querySelector("[data-rose]")?.setAttribute("aria-label", `${target.values.percent}% turnout`);
      updateRecent(next);
      // Everything else marked data-slot: warning, updated time, officials, centre summaries
      next.querySelectorAll("[data-slot]").forEach((slot) => {
        if (slot.dataset.slot !== "recent") replaceSlot(next, slot.dataset.slot);
      });
      applyFilter();
    } catch (error) {
      // No signal or the server is down: say so, keep the last numbers, try again next time
      setOnline(false);
    } finally {
      busy = false;
    }
  }

  // Every 15 seconds while the page is on screen, and straight away when you come back to it
  setInterval(() => {
    if (document.visibilityState === "visible") refresh();
  }, REFRESH_EVERY);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refresh();
  });

  // ---------- 3. Filtering "Latest ticks" by centre ----------

  let filter = "all";   // "all", or a centre's id
  const filterBar = dash.querySelector("[data-tick-filter]");
  const filterEmpty = dash.querySelector("[data-filter-empty]");
  const recentSection = dash.querySelector("#latest-ticks");

  // Show the newest ticks that match the filter (up to RECENT_MAX), hide the rest,
  // and light up the matching button and centre card
  function applyFilter() {
    const items = dash.querySelectorAll("[data-slot='recent'] li");
    let shown = 0;
    items.forEach((li) => {
      const show = (filter === "all" || li.dataset.centre === filter) && shown < RECENT_MAX;
      li.hidden = !show;
      if (show) shown++;
    });
    filterEmpty.hidden = shown > 0 || items.length === 0;
    dash.querySelectorAll("[data-filter]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.filter === filter));
    });
  }

  function chooseFilter(value, fromCard) {
    // Tapping the chosen centre again goes back to all centres
    filter = fromCard && value === filter ? "all" : value;
    applyFilter();
    // On a phone "Latest ticks" is further down the page: take the Commissioner there
    if (fromCard && filter !== "all" && window.matchMedia("(max-width: 959px)").matches) {
      recentSection.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    }
  }

  dash.addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter]");
    if (!button) return;
    chooseFilter(button.dataset.filter, button.classList.contains("centre-pick"));
  });

  if (filterBar) filterBar.hidden = false;   // the buttons only appear when they can work
  applyFilter();
})();