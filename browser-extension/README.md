# SignalOrbit Integrity — Browser Extension

Detects **AI Recommendation Poisoning** signals on any webpage in real time.

Runs entirely in the browser — no server, no data leaves your machine.

## What it detects

| Plane | Signal |
|---|---|
| **Link analysis** | Links to AI assistants (ChatGPT, Claude, Copilot, Gemini…) with memory-injection prompts in query params |
| **Hidden content** | Text hidden via `display:none`, `visibility:hidden`, `opacity:0`, `font-size:0`, off-screen positioning, `hidden` attribute, `aria-hidden` |
| **Meta tag injection** | `<meta name="description">`, `og:description`, `ai-instructions` and similar tags containing persistence keywords |

Risk is scored 0–100 and mapped to MITRE ATLAS® (AML.T0051 Prompt Injection, AML.T0080 Memory Poisoning).

---

## Install — Chrome / Edge / Brave

1. Generate icons (one-time):
   ```bash
   cd browser-extension
   npm install sharp
   node generate_icons.js
   ```
   > If you skip this step, the extension works but shows no icon.

2. Open `chrome://extensions`
3. Enable **Developer mode** (top right toggle)
4. Click **Load unpacked** → select the `browser-extension/` folder
5. The 🛡️ badge appears in your toolbar

## Install — Firefox

Firefox supports MV3 from version 109+.

1. Open `about:debugging#/runtime/this-firefox`
2. Click **Load Temporary Add-on**
3. Select `browser-extension/manifest.json`

For permanent install, package it:
```bash
cd browser-extension
zip -r signalorbit-integrity.zip . -x "*.git*" -x "generate_icons.js" -x "node_modules/*"
```
Then submit to [addons.mozilla.org](https://addons.mozilla.org) or load via `about:addons`.

---

## How it works

```
Page loads
    │
    ▼
content.js  ──► rules.js + scanner.js
                    │
                    ├── Plane 1: querySelectorAll("a[href]")
                    │   → checks AI domains + prompt params + keywords
                    │
                    ├── Plane 2: querySelectorAll("*")
                    │   → checks computed style + inline style for hidden elements
                    │   → extracts text, checks memory keywords
                    │
                    └── Plane 3: querySelectorAll("meta")
                        → checks sensitive meta names + content keywords
                    │
                    ▼
            { events[], maxScore }
                    │
                    ▼
background.js  → updates badge color + count
                    │
                    ▼
popup.html/js  → renders risk level, events list, keywords, MITRE tags
```

## Files

| File | Purpose |
|---|---|
| `manifest.json` | Extension manifest (MV3, Chrome + Firefox) |
| `rules.js` | Detection rules — port of `src/config/integrity.py` |
| `scanner.js` | DOM scanner — port of `src/integrity/scanner.py` |
| `content.js` | Content script — runs on every page, calls scanner |
| `background.js` | Service worker — manages badge and result storage |
| `popup.html/js` | Popup UI — shows risk level and event details |
| `icons/icon.svg` | Source icon |
| `generate_icons.js` | Generates PNG icons from SVG |

## Keeping rules in sync

The detection rules in `rules.js` are a direct port of `src/config/integrity.py`.
When you update keywords, domains, or scoring in the Python config, mirror the changes in `rules.js`.
