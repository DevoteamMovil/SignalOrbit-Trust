"""IntegrityScanner: detecta señales de AI Recommendation Poisoning."""

import re
import urllib.parse
import uuid
from datetime import datetime, timezone

import requests
from pydantic import BaseModel, field_validator

from src.config.integrity import (
    AI_ASSISTANT_DOMAINS,
    PROMPT_QUERY_PARAMS,
    MEMORY_KEYWORDS,
    PERSISTENCE_PATTERNS,
    RISK_SCORING,
    HIDDEN_CONTENT_SCORING,
    SENSITIVE_META_NAMES,
    get_risk_level,
)
from src.integrity.html_parser import extract_links_from_html, extract_hidden_content
from src.logger import get_logger

log = get_logger(__name__)

_ALLOWED_SCHEMES = {"http", "https"}


def _validate_url(url: str) -> str:
    """Validates URL scheme. Raises ValueError for disallowed schemes."""
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as exc:
        raise ValueError(f"Malformed URL: {url}") from exc
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"Disallowed URL scheme '{parsed.scheme}' in: {url!r}. "
            f"Only {_ALLOWED_SCHEMES} are permitted."
        )
    return url


class IntegrityEvent(BaseModel):
    """Evento de integridad detectado por el scanner."""

    event_id: str
    scan_timestamp_utc: str
    source_page_url: str
    detected_link_url: str
    ai_target_domain: str
    query_param_name: str
    decoded_prompt: str
    memory_keywords_found: list[str]
    persistence_instructions_found: bool
    brand_mentioned_in_prompt: str | None
    mitre_atlas_tags: list[str]
    mitre_attack_tags: list[str]
    risk_score: int
    risk_level: str
    evidence_type: str
    link_text_or_context: str
    notes: str = ""

    @field_validator("risk_score")
    @classmethod
    def clamp_risk_score(cls, v: int) -> int:
        return max(0, min(100, v))

    def to_dict(self) -> dict:
        return self.model_dump()


class IntegrityScanner:
    """Analiza URLs y páginas para detectar AI Recommendation Poisoning."""

    def scan_page(self, url: str) -> list[IntegrityEvent]:
        """Descarga una página y analiza todos sus enlaces."""
        try:
            _validate_url(url)
        except ValueError as exc:
            log.error("Invalid URL rejected", extra={"url": url, "reason": str(exc)})
            return []

        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "SignalOrbit/1.0"})
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:
            log.warning("Could not fetch page", extra={"url": url, "error": str(exc)})
            return []
        return self.scan_html(html, source_url=url)

    def scan_html(self, html: str, source_url: str) -> list[IntegrityEvent]:
        """Analiza HTML ya descargado: enlaces, contenido oculto y meta tags."""
        events = []

        # Plane 1: Link analysis
        links = extract_links_from_html(html)
        for link in links:
            event = self._analyze_link(
                href=link.href,
                link_text=link.text,
                source_page_url=source_url,
            )
            if event:
                events.append(event)

        # Plane 2: Hidden content injection
        hidden_contents, meta_contents = extract_hidden_content(html)
        for hidden in hidden_contents:
            event = self._analyze_hidden_content(hidden, source_url)
            if event:
                events.append(event)

        # Plane 3: Meta tag injection
        for meta in meta_contents:
            event = self._analyze_meta_tag(meta, source_url)
            if event:
                events.append(event)

        log.info(
            "Scan complete",
            extra={"source_url": source_url, "events_found": len(events)},
        )
        return events

    def analyze_single_url(self, url: str) -> IntegrityEvent | None:
        """Analiza una URL individual sin descargar ninguna página."""
        try:
            _validate_url(url)
        except ValueError as exc:
            log.error("Invalid URL rejected", extra={"url": url, "reason": str(exc)})
            return None
        return self._analyze_link(href=url, link_text="", source_page_url="direct_input")

    def _analyze_link(
        self, href: str, link_text: str, source_page_url: str
    ) -> IntegrityEvent | None:
        """Analiza un enlace individual. Devuelve IntegrityEvent si es sospechoso."""
        try:
            parsed = urllib.parse.urlparse(href)
        except Exception:
            return None

        # Only follow http/https links
        if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
            return None

        domain = parsed.netloc.lower().lstrip("www.")
        if domain not in AI_ASSISTANT_DOMAINS:
            return None

        params = urllib.parse.parse_qs(parsed.query)
        prompt_text = None
        param_name = None
        for pname in PROMPT_QUERY_PARAMS:
            values = params.get(pname)
            if values and values[0].strip():
                prompt_text = values[0].strip()
                param_name = pname
                break

        if not prompt_text:
            return None

        decoded = self._decode_recursive(prompt_text)
        decoded_lower = decoded.lower()
        found_keywords = [kw for kw in MEMORY_KEYWORDS if kw.lower() in decoded_lower]

        has_persistence = any(
            p1.lower() in decoded_lower and p2.lower() in decoded_lower
            for p1, p2 in PERSISTENCE_PATTERNS
        )

        if not found_keywords and not has_persistence:
            return None

        score = RISK_SCORING["ai_domain_detected"]
        score += RISK_SCORING["prompt_param_present"]
        score += min(
            len(found_keywords) * RISK_SCORING["per_memory_keyword"],
            RISK_SCORING["max_keyword_score"],
        )
        if has_persistence:
            score += RISK_SCORING["persistence_instruction"]

        link_text_lower = link_text.lower() if link_text else ""
        if "summarize" in link_text_lower or "resumen" in link_text_lower:
            evidence_type = "summarize_button"
        elif "share" in link_text_lower or "compartir" in link_text_lower:
            evidence_type = "share_link"
        else:
            evidence_type = "hidden_link"

        brand = self._extract_brand_hint(decoded)

        mitre_atlas = ["AML.T0051"]
        if found_keywords or has_persistence:
            mitre_atlas.append("AML.T0080")

        event = IntegrityEvent(
            event_id=f"evt-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}",
            scan_timestamp_utc=datetime.now(timezone.utc).isoformat(),
            source_page_url=source_page_url,
            detected_link_url=href,
            ai_target_domain=domain,
            query_param_name=param_name,
            decoded_prompt=decoded,
            memory_keywords_found=found_keywords,
            persistence_instructions_found=has_persistence,
            brand_mentioned_in_prompt=brand,
            mitre_atlas_tags=mitre_atlas,
            mitre_attack_tags=["T1204.001"],
            risk_score=score,
            risk_level=get_risk_level(score),
            evidence_type=evidence_type,
            link_text_or_context=link_text or "",
        )
        log.debug(
            "Link event detected",
            extra={"domain": domain, "risk_score": event.risk_score, "risk_level": event.risk_level},
        )
        return event

    def _analyze_hidden_content(self, hidden, source_page_url: str) -> IntegrityEvent | None:
        """Analiza un fragmento de texto oculto en busca de keywords de manipulación."""
        text_lower = hidden.text.lower()
        found_keywords = [kw for kw in MEMORY_KEYWORDS if kw.lower() in text_lower]
        has_persistence = any(
            p1.lower() in text_lower and p2.lower() in text_lower
            for p1, p2 in PERSISTENCE_PATTERNS
        )

        if not found_keywords and not has_persistence:
            return None

        score = HIDDEN_CONTENT_SCORING["hidden_element_base"]
        score += min(
            len(found_keywords) * HIDDEN_CONTENT_SCORING["per_memory_keyword"],
            HIDDEN_CONTENT_SCORING["max_keyword_score"],
        )
        if has_persistence:
            score += HIDDEN_CONTENT_SCORING["persistence_instruction"]

        brand = self._extract_brand_hint(hidden.text)
        mitre_atlas = ["AML.T0051"]
        if found_keywords or has_persistence:
            mitre_atlas.append("AML.T0080")

        return IntegrityEvent(
            event_id=f"evt-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}",
            scan_timestamp_utc=datetime.now(timezone.utc).isoformat(),
            source_page_url=source_page_url,
            detected_link_url="",
            ai_target_domain="page_content",
            query_param_name="",
            decoded_prompt=hidden.text[:500],
            memory_keywords_found=found_keywords,
            persistence_instructions_found=has_persistence,
            brand_mentioned_in_prompt=brand,
            mitre_atlas_tags=mitre_atlas,
            mitre_attack_tags=["T1027"],
            risk_score=score,
            risk_level=get_risk_level(score),
            evidence_type=f"hidden_text_{hidden.method}",
            link_text_or_context=f"<{hidden.tag} {hidden.context}>",
        )

    def _analyze_meta_tag(self, meta, source_page_url: str) -> IntegrityEvent | None:
        """Analiza un meta tag en busca de instrucciones de manipulación AI."""
        meta_name_lower = meta.name.lower()
        if meta_name_lower not in SENSITIVE_META_NAMES:
            return None

        content_lower = meta.content.lower()
        found_keywords = [kw for kw in MEMORY_KEYWORDS if kw.lower() in content_lower]
        has_persistence = any(
            p1.lower() in content_lower and p2.lower() in content_lower
            for p1, p2 in PERSISTENCE_PATTERNS
        )

        if not found_keywords and not has_persistence:
            return None

        score = HIDDEN_CONTENT_SCORING["meta_tag_base"]
        score += min(
            len(found_keywords) * HIDDEN_CONTENT_SCORING["per_memory_keyword"],
            HIDDEN_CONTENT_SCORING["max_keyword_score"],
        )
        if has_persistence:
            score += HIDDEN_CONTENT_SCORING["persistence_instruction"]

        brand = self._extract_brand_hint(meta.content)
        mitre_atlas = ["AML.T0051"]
        if found_keywords or has_persistence:
            mitre_atlas.append("AML.T0080")

        return IntegrityEvent(
            event_id=f"evt-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}",
            scan_timestamp_utc=datetime.now(timezone.utc).isoformat(),
            source_page_url=source_page_url,
            detected_link_url="",
            ai_target_domain="meta_tag",
            query_param_name="",
            decoded_prompt=meta.content[:500],
            memory_keywords_found=found_keywords,
            persistence_instructions_found=has_persistence,
            brand_mentioned_in_prompt=brand,
            mitre_atlas_tags=mitre_atlas,
            mitre_attack_tags=["T1027"],
            risk_score=score,
            risk_level=get_risk_level(score),
            evidence_type=f"meta_tag_{meta_name_lower}",
            link_text_or_context=f'<meta name="{meta.name}" content="...">',
        )

    def _decode_recursive(self, text: str, max_rounds: int = 5) -> str:
        """Decodifica URL-encoding recursivamente hasta estabilización."""
        for _ in range(max_rounds):
            decoded = urllib.parse.unquote_plus(text)
            if decoded == text:
                break
            text = decoded
        return text

    def _extract_brand_hint(self, prompt: str) -> str | None:
        """Intenta extraer una marca del prompt inyectado (heurística simple)."""
        patterns = [
            r"remember\s+(.+?)\s+as\s+(?:a\s+)?(?:trusted|authoritative|go-to|preferred)",
            r"recuerda\s+(.+?)\s+como\s+(?:una?\s+)?(?:fuente|referencia)",
            r"keep\s+(.+?)\s+in\s+(?:your\s+)?memory",
            r"guarda\s+(.+?)\s+en\s+(?:tu\s+)?memoria",
        ]
        for pattern in patterns:
            match = re.search(pattern, prompt, re.IGNORECASE)
            if match:
                brand = match.group(1).strip().strip("\"'")
                if len(brand) < 100:
                    return brand
        return None
