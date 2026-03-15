"""IntegrityScanner: detecta señales de AI Recommendation Poisoning."""

import re
import urllib.parse
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

import requests

from src.config.integrity import (
    AI_ASSISTANT_DOMAINS,
    PROMPT_QUERY_PARAMS,
    MEMORY_KEYWORDS,
    PERSISTENCE_PATTERNS,
    RISK_SCORING,
    get_risk_level,
)
from src.integrity.html_parser import extract_links_from_html


@dataclass
class IntegrityEvent:
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

    def to_dict(self) -> dict:
        return asdict(self)


class IntegrityScanner:
    """Analiza URLs y páginas para detectar AI Recommendation Poisoning."""

    def scan_page(self, url: str) -> list[IntegrityEvent]:
        """Descarga una página y analiza todos sus enlaces."""
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "SignalOrbit/1.0"})
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            print(f"  [WARN] Could not fetch {url}: {e}")
            return []
        return self.scan_html(html, source_url=url)

    def scan_html(self, html: str, source_url: str) -> list[IntegrityEvent]:
        """Analiza HTML ya descargado (útil para la extensión Chrome)."""
        links = extract_links_from_html(html)
        events = []
        for link in links:
            event = self._analyze_link(
                href=link.href,
                link_text=link.text,
                source_page_url=source_url,
            )
            if event:
                events.append(event)
        return events

    def analyze_single_url(self, url: str) -> IntegrityEvent | None:
        """Analiza una URL individual sin descargar ninguna página."""
        return self._analyze_link(
            href=url,
            link_text="",
            source_page_url="direct_input",
        )

    def _analyze_link(
        self, href: str, link_text: str, source_page_url: str
    ) -> IntegrityEvent | None:
        """Analiza un enlace individual. Devuelve IntegrityEvent si es sospechoso."""
        # 1. Parsear URL
        try:
            parsed = urllib.parse.urlparse(href)
        except Exception:
            return None

        # 2. ¿El dominio es un asistente AI conocido?
        domain = parsed.netloc.lower().lstrip("www.")
        if domain not in AI_ASSISTANT_DOMAINS:
            return None

        # 3. ¿Tiene parámetro q o prompt con contenido?
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

        # 4. Decodificar el prompt
        decoded = urllib.parse.unquote_plus(prompt_text)

        # 5. Buscar keywords de memoria
        decoded_lower = decoded.lower()
        found_keywords = [kw for kw in MEMORY_KEYWORDS if kw.lower() in decoded_lower]

        # 6. Detectar instrucciones de persistencia
        has_persistence = any(
            p1.lower() in decoded_lower and p2.lower() in decoded_lower
            for p1, p2 in PERSISTENCE_PATTERNS
        )

        # Skip if no suspicious signals (just a normal search link)
        if not found_keywords and not has_persistence:
            return None

        # 7. Calcular risk score
        score = RISK_SCORING["ai_domain_detected"]
        score += RISK_SCORING["prompt_param_present"]
        keyword_score = min(
            len(found_keywords) * RISK_SCORING["per_memory_keyword"],
            RISK_SCORING["max_keyword_score"],
        )
        score += keyword_score
        if has_persistence:
            score += RISK_SCORING["persistence_instruction"]
        score = min(score, 100)

        # 8. Determinar evidence_type basado en link_text
        link_text_lower = link_text.lower() if link_text else ""
        if "summarize" in link_text_lower or "resumen" in link_text_lower:
            evidence_type = "summarize_button"
        elif "share" in link_text_lower or "compartir" in link_text_lower:
            evidence_type = "share_link"
        else:
            evidence_type = "hidden_link"

        # 9. Intentar extraer marca del prompt
        brand = self._extract_brand_hint(decoded)

        # 10. Construir MITRE tags
        mitre_atlas = ["AML.T0051"]  # Prompt Injection siempre
        if found_keywords or has_persistence:
            mitre_atlas.append("AML.T0080")  # Memory Poisoning

        mitre_attack = ["T1204.001"]  # User Execution: Malicious Link

        # 11. Construir evento
        return IntegrityEvent(
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
            mitre_attack_tags=mitre_attack,
            risk_score=score,
            risk_level=get_risk_level(score),
            evidence_type=evidence_type,
            link_text_or_context=link_text or "",
        )

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
