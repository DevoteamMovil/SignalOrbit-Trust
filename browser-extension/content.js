/**
 * SignalOrbit Integrity — Content Script
 * Runs in the context of every page, sends results to the background worker.
 */

/* global scanPage */

(function () {
  // Avoid double-injection on SPA navigations
  if (window.__signalOrbitInjected) return;
  window.__signalOrbitInjected = true;

  function run() {
    const events = scanPage();
    const maxScore = events.reduce((m, e) => Math.max(m, e.riskScore), 0);

    // Send to background so it can update the badge
    const api = typeof browser !== "undefined" ? browser : chrome;
    api.runtime.sendMessage({
      type: "SCAN_RESULT",
      url: window.location.href,
      events,
      maxScore,
    });
  }

  // Run on initial load
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }

  // Re-scan on SPA navigation (history pushState / replaceState)
  const _push = history.pushState.bind(history);
  const _replace = history.replaceState.bind(history);
  history.pushState = function (...args) { _push(...args); setTimeout(run, 800); };
  history.replaceState = function (...args) { _replace(...args); setTimeout(run, 800); };
  window.addEventListener("popstate", () => setTimeout(run, 800));
})();
