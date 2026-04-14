/**
 * SignalOrbit Integrity — Popup Script
 */

const api = typeof browser !== "undefined" ? browser : chrome;

const LEVEL_ICONS = {
  clean:    "✅",
  low:      "🟡",
  medium:   "🟠",
  high:     "🔴",
  critical: "🟣",
};

const LEVEL_LABELS = {
  clean:    "Clean",
  low:      "Low Risk",
  medium:   "Medium Risk",
  high:     "High Risk",
  critical: "Critical",
};

const TYPE_LABELS = {
  link:           "Poisoned Link",
  hidden_content: "Hidden Content",
  meta_tag:       "Meta Tag Injection",
};

function scoreColor(score) {
  if (score === 0)  return "#4caf50";
  if (score <= 25)  return "#8bc34a";
  if (score <= 50)  return "#ff9800";
  if (score <= 75)  return "#f44336";
  return "#ce93d8";
}

function renderStatus(maxScore, eventCount) {
  const level = maxScore === 0 ? "clean"
    : maxScore <= 25 ? "low"
    : maxScore <= 50 ? "medium"
    : maxScore <= 75 ? "high"
    : "critical";

  const sub = maxScore === 0
    ? "No poisoning signals found on this page."
    : `${eventCount} signal${eventCount !== 1 ? "s" : ""} detected — review below.`;

  return `
    <div class="status-banner status-${level}">
      <div class="status-icon">${LEVEL_ICONS[level]}</div>
      <div>
        <div class="status-label label-${level}">${LEVEL_LABELS[level]}</div>
        <div class="status-sub">${sub}</div>
      </div>
    </div>
    <div class="score-row">
      <div class="score-label">Risk Score</div>
      <div class="score-bar-wrap">
        <div class="score-bar" style="width:${maxScore}%; background:${scoreColor(maxScore)}"></div>
      </div>
      <div class="score-value" style="color:${scoreColor(maxScore)}">${maxScore}</div>
    </div>
  `;
}

function renderEvent(ev) {
  const keywords = (ev.keywords || []).slice(0, 5).map(
    (kw) => `<span class="kw-chip">${escHtml(kw)}</span>`
  ).join("");

  const domain = ev.domain !== "page_content" && ev.domain !== "meta_tag"
    ? `<div class="event-domain">${escHtml(ev.domain)}</div>`
    : `<div class="event-domain">${escHtml(ev.evidenceType)}</div>`;

  const prompt = ev.decodedPrompt
    ? `<div class="event-prompt" title="${escHtml(ev.decodedPrompt)}">${escHtml(ev.decodedPrompt.slice(0, 90))}${ev.decodedPrompt.length > 90 ? "…" : ""}</div>`
    : "";

  const mitre = (ev.mitre || []).join(" · ");

  return `
    <div class="event-item">
      <div class="event-top">
        <span class="event-badge badge-${ev.riskLevel}">${ev.riskLevel}</span>
        <span class="event-type">${TYPE_LABELS[ev.type] || ev.type}</span>
        <span class="event-score" style="color:${scoreColor(ev.riskScore)}">${ev.riskScore}/100</span>
      </div>
      ${domain}
      ${prompt}
      ${keywords ? `<div class="event-keywords">${keywords}</div>` : ""}
      ${mitre ? `<div class="event-mitre">MITRE: ${escHtml(mitre)}</div>` : ""}
    </div>
  `;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function render(data) {
  const root = document.getElementById("root");
  const { events = [], maxScore = 0, url = "", scannedAt } = data;

  // Sort by risk score descending
  const sorted = [...events].sort((a, b) => b.riskScore - a.riskScore);

  let html = renderStatus(maxScore, events.length);

  if (sorted.length > 0) {
    html += `<div class="events-header">Detected Signals (${sorted.length})</div>`;
    html += `<div class="events-list">${sorted.map(renderEvent).join("")}</div>`;
  } else {
    html += `
      <div class="empty">
        <div class="empty-icon">🛡️</div>
        <div class="empty-text">This page has no AI recommendation poisoning signals.</div>
      </div>
    `;
  }

  root.innerHTML = html;

  // Footer
  if (url) {
    try {
      document.getElementById("footer-url").textContent = new URL(url).hostname;
    } catch {
      document.getElementById("footer-url").textContent = url.slice(0, 40);
    }
  }
  if (scannedAt) {
    document.getElementById("footer-time").textContent =
      new Date(scannedAt).toLocaleTimeString();
  }
}

// ── Init ──────────────────────────────────────────────────────────
api.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  const tabId = tabs[0]?.id;
  if (!tabId) return;

  api.runtime.sendMessage({ type: "GET_RESULTS", tabId }, (data) => {
    if (data && (data.events?.length > 0 || data.url)) {
      render(data);
    } else {
      // Results not ready yet — inject content script and wait briefly
      api.scripting
        ? api.scripting.executeScript(
            { target: { tabId }, files: ["rules.js", "scanner.js", "content.js"] },
            () => setTimeout(() => api.runtime.sendMessage({ type: "GET_RESULTS", tabId }, render), 600)
          )
        : setTimeout(() => api.runtime.sendMessage({ type: "GET_RESULTS", tabId }, render), 800);
    }
  });
});
