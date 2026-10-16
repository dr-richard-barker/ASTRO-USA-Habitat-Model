/* ASTRO-USA Habitat Model page: light/dark toggle (same key as the shared theme), the viewer scene tabs and the
   click-to-load viewer. Theme toggle and tab keyboard handling ported from Hardware_OSDR_review site/site.js @ 291f806. */
(function () {
  "use strict";
  var LS_THEME = "barker.theme";
  var SUN = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  var MOON = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';

  /* ---------- theme ---------- */
  var btn = document.querySelector(".theme-btn");
  function current() {
    return document.documentElement.getAttribute("data-theme") ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  }
  function paint() { if (btn) btn.innerHTML = current() === "dark" ? SUN : MOON; }
  if (btn) {
    btn.addEventListener("click", function () {
      var t = current() === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", t);
      try { localStorage.setItem(LS_THEME, t); } catch (e) {}
      paint();
    });
    paint();
  }

  /* ---------- viewer: scenes as tabs, nothing loads until asked ---------- */
  var box = document.querySelector(".viewer");
  var full = document.getElementById("viewer-full");
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".tabs [role=tab]"));
  var scene = tabs.length ? tabs[0].getAttribute("data-src") : "viewer/";
  function load() {
    if (!box) return;
    var f = box.querySelector("iframe");
    if (!f) {
      f = document.createElement("iframe");
      f.title = "Interactive 3-D model of the Food Production Module";
      f.setAttribute("allow", "xr-spatial-tracking; fullscreen");
      f.setAttribute("allowfullscreen", "");
      box.appendChild(f);
      var p = box.querySelector(".poster"), b = box.querySelector(".load-viewer");
      if (p) p.remove();
      if (b) b.remove();
    }
    if (f.getAttribute("src") !== scene) f.setAttribute("src", scene);
  }
  function select(tab, andLoad) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
    });
    scene = tab.getAttribute("data-src");
    if (full) full.setAttribute("href", scene);
    if (andLoad || (box && box.querySelector("iframe"))) load();
  }
  tabs.forEach(function (t, i) {
    t.addEventListener("click", function () { select(t, true); });
    t.addEventListener("keydown", function (e) {
      var j = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
      if (j === null) return;
      e.preventDefault();
      var n = tabs[(j + tabs.length) % tabs.length];
      select(n, false); n.focus();
    });
  });
  var go = document.querySelector(".load-viewer");
  if (go) go.addEventListener("click", load);
})();
