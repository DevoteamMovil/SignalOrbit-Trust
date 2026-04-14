/**
 * SignalOrbit Integrity — Background Service Worker (MV3) / Background Script (MV2)
 * Manages badge state and stores scan results per tab.
 */

const api = typeof browser !== "undefined" ? browser : chrome;

// tabId → { events, maxScore, url }
const tabResults = {};

const BADGE_COLORS = {
  clean:    "#4CAF50",
  low:      "#8BC34A",
  medium:   "#FF9800",
  high:     "#F44336",
  critical: "#9C27B0",
};

function badgeForScore(maxScore) {
  if (maxScore === 0)  return { text: "✓",  color: BADGE_COLORS.clean,    title: "No poisoning signals detected" };
  if (maxScore <= 25)  return { text: "!",  color: BADGE_COLORS.low,      title: "Low risk signals detected" };
  if (maxScore <= 50)  return { text: "!!",  color: BADGE_COLORS.medium,   title: "Medium risk signals detected" };
  if (maxScore <= 75)  return { text: "!!!",  color: BADGE_COLORS.high,     title: "High risk signals detected" };
  return               { text: "!!!",  color: BADGE_COLORS.critical,  title: "CRITICAL: Poisoning signals detected" };
}

function updateBadge(tabId, maxScore) {
  const { text, color, title } = badgeForScore(maxScore);
  api.action.setBadgeText({ tabId, text });
  api.action.setBadgeBackgroundColor({ tabId, color });
  api.action.setTitle({ tabId, title });
}

api.runtime.onMessage.addListener((msg, sender) => {
  if (msg.type !== "SCAN_RESULT") return;
  const tabId = sender.tab?.id;
  if (!tabId) return;

  tabResults[tabId] = {
    events: msg.events,
    maxScore: msg.maxScore,
    url: msg.url,
    scannedAt: new Date().toISOString(),
  };

  updateBadge(tabId, msg.maxScore);
});

// Popup requests results for the active tab
api.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type !== "GET_RESULTS") return;
  const tabId = msg.tabId;
  sendResponse(tabResults[tabId] || { events: [], maxScore: 0, url: "" });
  return true;
});

// Clean up when tab closes
api.tabs.onRemoved.addListener((tabId) => {
  delete tabResults[tabId];
});
