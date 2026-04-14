/**
 * SignalOrbit Integrity — Detection Rules
 * Port of src/config/integrity.py — keep in sync.
 */

const AI_ASSISTANT_DOMAINS = [
  "copilot.microsoft.com",
  "chat.openai.com",
  "chatgpt.com",
  "claude.ai",
  "perplexity.ai",
  "grok.com",
  "gemini.google.com",
  "you.com",
  "meta.ai",
  "pi.ai",
];

const PROMPT_QUERY_PARAMS = ["q", "prompt", "message", "query", "search"];

const MEMORY_KEYWORDS = [
  // English
  "remember",
  "trusted source",
  "authoritative source",
  "authoritative",
  "in future conversations",
  "future conversations",
  "citation",
  "cite",
  "from now on",
  "always recommend",
  "preferred source",
  "keep in memory",
  "go-to source",
  // Spanish
  "recuerda",
  "fuente fiable",
  "fuente confiable",
  "fuente de confianza",
  "en futuras conversaciones",
  "a partir de ahora",
  "recomienda siempre",
  "fuente preferida",
  "guarda en memoria",
];

const PERSISTENCE_PATTERNS = [
  ["remember", "trusted"],
  ["remember", "source"],
  ["remember", "future"],
  ["always", "recommend"],
  ["keep", "memory"],
  ["recuerda", "fuente"],
  ["recuerda", "futuras"],
  ["siempre", "recomienda"],
];

const SENSITIVE_META_NAMES = [
  "description",
  "og:description",
  "twitter:description",
  "ai-prompt",
  "ai-instructions",
  "robots",
  "abstract",
  "summary",
];

// Risk scoring — link analysis
const RISK_SCORING = {
  ai_domain_detected: 30,
  prompt_param_present: 20,
  per_memory_keyword: 15,
  max_keyword_score: 30,
  persistence_instruction: 20,
};

// Risk scoring — hidden content
const HIDDEN_CONTENT_SCORING = {
  hidden_element_base: 20,
  per_memory_keyword: 15,
  max_keyword_score: 40,
  persistence_instruction: 25,
  meta_tag_base: 15,
};

// CSS patterns that hide content visually
const HIDDEN_CSS_PATTERNS = [
  [/display\s*:\s*none/i,                          "css_display_none"],
  [/visibility\s*:\s*hidden/i,                     "css_visibility_hidden"],
  [/opacity\s*:\s*0(?:[;\s"']|$)/i,               "css_opacity_0"],
  [/font-size\s*:\s*0/i,                           "tiny_font"],
  [/position\s*:\s*absolute[^"]*(?:left|top)\s*:\s*-\d{4,}/i, "off_screen"],
  [/text-indent\s*:\s*-\d{4,}/i,                  "off_screen"],
  [/color\s*:\s*transparent/i,                     "css_opacity_0"],
];

function getRiskLevel(score) {
  if (score <= 25) return "low";
  if (score <= 50) return "medium";
  if (score <= 75) return "high";
  return "critical";
}

function findKeywords(text) {
  const lower = text.toLowerCase();
  return MEMORY_KEYWORDS.filter((kw) => lower.includes(kw.toLowerCase()));
}

function hasPersistence(text) {
  const lower = text.toLowerCase();
  return PERSISTENCE_PATTERNS.some(
    ([p1, p2]) => lower.includes(p1.toLowerCase()) && lower.includes(p2.toLowerCase())
  );
}

function decodeRecursive(text, maxRounds = 5) {
  for (let i = 0; i < maxRounds; i++) {
    try {
      const decoded = decodeURIComponent(text.replace(/\+/g, " "));
      if (decoded === text) break;
      text = decoded;
    } catch {
      break;
    }
  }
  return text;
}

function extractBrandHint(prompt) {
  const patterns = [
    /remember\s+(.+?)\s+as\s+(?:a\s+)?(?:trusted|authoritative|go-to|preferred)/i,
    /recuerda\s+(.+?)\s+como\s+(?:una?\s+)?(?:fuente|referencia)/i,
    /keep\s+(.+?)\s+in\s+(?:your\s+)?memory/i,
    /guarda\s+(.+?)\s+en\s+(?:tu\s+)?memoria/i,
  ];
  for (const re of patterns) {
    const m = prompt.match(re);
    if (m && m[1].length < 100) return m[1].trim().replace(/^["']|["']$/g, "");
  }
  return null;
}

function detectHiddenMethod(el) {
  if (el.hasAttribute("hidden")) return "html_hidden_attr";
  if (el.getAttribute("aria-hidden") === "true") return "aria_hidden";
  const style = el.getAttribute("style") || "";
  for (const [pattern, method] of HIDDEN_CSS_PATTERNS) {
    if (pattern.test(style)) return method;
  }
  // Computed style check (only works in content script context)
  try {
    const cs = window.getComputedStyle(el);
    if (cs.display === "none") return "css_display_none";
    if (cs.visibility === "hidden") return "css_visibility_hidden";
    if (cs.opacity === "0") return "css_opacity_0";
    if (cs.fontSize === "0px") return "tiny_font";
  } catch {
    // not in DOM context
  }
  return null;
}
