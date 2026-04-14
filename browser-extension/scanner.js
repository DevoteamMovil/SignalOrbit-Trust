/**
 * SignalOrbit Integrity — DOM Scanner
 * Port of src/integrity/scanner.py — runs entirely in the browser.
 */

/* global AI_ASSISTANT_DOMAINS, PROMPT_QUERY_PARAMS, MEMORY_KEYWORDS,
          RISK_SCORING, HIDDEN_CONTENT_SCORING, SENSITIVE_META_NAMES,
          getRiskLevel, findKeywords, hasPersistence, decodeRecursive,
          extractBrandHint, detectHiddenMethod */

function scanPage() {
  const events = [];
  const url = window.location.href;

  // ── Plane 1: Link analysis ────────────────────────────────────
  document.querySelectorAll("a[href]").forEach((anchor) => {
    const event = analyzeLink(anchor.href, anchor.innerText || "", url);
    if (event) events.push(event);
  });

  // ── Plane 2: Hidden content injection ────────────────────────
  const allElements = document.querySelectorAll("*");
  allElements.forEach((el) => {
    if (["SCRIPT", "STYLE", "NOSCRIPT", "META", "LINK"].includes(el.tagName)) return;
    const method = detectHiddenMethod(el);
    if (!method) return;
    const text = (el.innerText || el.textContent || "").trim();
    if (!text) return;
    const event = analyzeHiddenContent(text, method, el.tagName.toLowerCase(), url);
    if (event) events.push(event);
  });

  // ── Plane 3: Meta tag injection ──────────────────────────────
  document.querySelectorAll("meta").forEach((meta) => {
    const name = (meta.getAttribute("name") || meta.getAttribute("property") || "").toLowerCase();
    const content = meta.getAttribute("content") || "";
    if (!name || !content) return;
    const event = analyzeMetaTag(name, content, url);
    if (event) events.push(event);
  });

  return events;
}

function analyzeLink(href, linkText, sourceUrl) {
  let parsed;
  try {
    parsed = new URL(href);
  } catch {
    return null;
  }

  if (!["http:", "https:"].includes(parsed.protocol)) return null;

  const domain = parsed.hostname.replace(/^www\./, "");
  if (!AI_ASSISTANT_DOMAINS.includes(domain)) return null;

  let promptText = null;
  let paramName = null;
  for (const pname of PROMPT_QUERY_PARAMS) {
    const val = parsed.searchParams.get(pname);
    if (val && val.trim()) {
      promptText = val.trim();
      paramName = pname;
      break;
    }
  }
  if (!promptText) return null;

  const decoded = decodeRecursive(promptText);
  const keywords = findKeywords(decoded);
  const persistence = hasPersistence(decoded);

  if (!keywords.length && !persistence) return null;

  let score = RISK_SCORING.ai_domain_detected + RISK_SCORING.prompt_param_present;
  score += Math.min(keywords.length * RISK_SCORING.per_memory_keyword, RISK_SCORING.max_keyword_score);
  if (persistence) score += RISK_SCORING.persistence_instruction;
  score = Math.min(score, 100);

  const lt = linkText.toLowerCase();
  let evidenceType = "hidden_link";
  if (lt.includes("summarize") || lt.includes("resumen")) evidenceType = "summarize_button";
  else if (lt.includes("share") || lt.includes("compartir")) evidenceType = "share_link";

  return {
    type: "link",
    evidenceType,
    domain,
    paramName,
    decodedPrompt: decoded,
    keywords,
    persistence,
    brand: extractBrandHint(decoded),
    riskScore: score,
    riskLevel: getRiskLevel(score),
    mitre: ["AML.T0051", ...(keywords.length || persistence ? ["AML.T0080"] : [])],
    attackTags: ["T1204.001"],
    linkText,
    detectedUrl: href,
    sourceUrl,
  };
}

function analyzeHiddenContent(text, method, tag, sourceUrl) {
  const keywords = findKeywords(text);
  const persistence = hasPersistence(text);
  if (!keywords.length && !persistence) return null;

  let score = HIDDEN_CONTENT_SCORING.hidden_element_base;
  score += Math.min(keywords.length * HIDDEN_CONTENT_SCORING.per_memory_keyword, HIDDEN_CONTENT_SCORING.max_keyword_score);
  if (persistence) score += HIDDEN_CONTENT_SCORING.persistence_instruction;
  score = Math.min(score, 100);

  return {
    type: "hidden_content",
    evidenceType: `hidden_text_${method}`,
    domain: "page_content",
    decodedPrompt: text.slice(0, 500),
    keywords,
    persistence,
    brand: extractBrandHint(text),
    riskScore: score,
    riskLevel: getRiskLevel(score),
    mitre: ["AML.T0051", ...(keywords.length || persistence ? ["AML.T0080"] : [])],
    attackTags: ["T1027"],
    tag,
    sourceUrl,
  };
}

function analyzeMetaTag(name, content, sourceUrl) {
  if (!SENSITIVE_META_NAMES.includes(name)) return null;
  const keywords = findKeywords(content);
  const persistence = hasPersistence(content);
  if (!keywords.length && !persistence) return null;

  let score = HIDDEN_CONTENT_SCORING.meta_tag_base;
  score += Math.min(keywords.length * HIDDEN_CONTENT_SCORING.per_memory_keyword, HIDDEN_CONTENT_SCORING.max_keyword_score);
  if (persistence) score += HIDDEN_CONTENT_SCORING.persistence_instruction;
  score = Math.min(score, 100);

  return {
    type: "meta_tag",
    evidenceType: `meta_tag_${name}`,
    domain: "meta_tag",
    decodedPrompt: content.slice(0, 500),
    keywords,
    persistence,
    brand: extractBrandHint(content),
    riskScore: score,
    riskLevel: getRiskLevel(score),
    mitre: ["AML.T0051", ...(keywords.length || persistence ? ["AML.T0080"] : [])],
    attackTags: ["T1027"],
    metaName: name,
    sourceUrl,
  };
}
