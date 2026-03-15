"""Extractor de enlaces y contenido oculto de HTML usando stdlib."""

import re
from html.parser import HTMLParser
from dataclasses import dataclass, field


@dataclass
class ExtractedLink:
    href: str
    text: str       # Texto visible del enlace (innerText)
    context: str     # Texto circundante para evidencia


@dataclass
class HiddenContent:
    """Fragmento de texto oculto detectado en la página."""
    text: str
    method: str        # "css_display_none", "css_visibility_hidden", "css_opacity_0",
                       # "html_hidden_attr", "aria_hidden", "tiny_font", "off_screen"
    tag: str           # Tag HTML donde se encontró
    context: str = ""  # Atributos relevantes para evidencia


@dataclass
class MetaContent:
    """Contenido extraído de meta tags."""
    name: str          # name o property del meta tag
    content: str       # Valor del atributo content


# Patrones CSS que ocultan contenido visualmente
_HIDDEN_CSS_PATTERNS = [
    (r"display\s*:\s*none", "css_display_none"),
    (r"visibility\s*:\s*hidden", "css_visibility_hidden"),
    (r"opacity\s*:\s*0(?:[;\s\"]|$)", "css_opacity_0"),
    (r"font-size\s*:\s*0", "tiny_font"),
    (r"position\s*:\s*absolute[^\"]*(?:left|top)\s*:\s*-\d{4,}", "off_screen"),
    (r"text-indent\s*:\s*-\d{4,}", "off_screen"),
    (r"overflow\s*:\s*hidden[^\"]*(?:width|height)\s*:\s*0", "css_display_none"),
    (r"color\s*:\s*transparent", "css_opacity_0"),
]


class LinkExtractor(HTMLParser):
    """Extrae todos los <a href="..."> de un documento HTML."""

    def __init__(self):
        super().__init__()
        self.links: list[ExtractedLink] = []
        self._current_href: str | None = None
        self._current_text_parts: list[str] = []
        self._in_link: bool = False

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._current_href = href
                self._current_text_parts = []
                self._in_link = True

    def handle_data(self, data):
        if self._in_link:
            self._current_text_parts.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "a" and self._in_link:
            text = " ".join(self._current_text_parts).strip()
            if self._current_href:
                self.links.append(ExtractedLink(
                    href=self._current_href,
                    text=text,
                    context="",
                ))
            self._in_link = False
            self._current_href = None

    def get_links(self) -> list[ExtractedLink]:
        return self.links


class HiddenContentExtractor(HTMLParser):
    """Extrae texto de elementos HTML ocultos y meta tags."""

    def __init__(self):
        super().__init__()
        self.hidden_contents: list[HiddenContent] = []
        self.meta_contents: list[MetaContent] = []
        self._stack: list[dict] = []  # Stack de {tag, hidden_method, text_parts}

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        # Extraer meta tags
        if tag == "meta":
            name = attrs_dict.get("name", "") or attrs_dict.get("property", "")
            content = attrs_dict.get("content", "")
            if name and content:
                self.meta_contents.append(MetaContent(name=name, content=content))
            return

        # Detectar si el elemento está oculto
        hidden_method = self._detect_hidden(tag, attrs_dict)

        self._stack.append({
            "tag": tag,
            "hidden_method": hidden_method,
            "text_parts": [],
            "attrs_str": " ".join(f'{k}="{v}"' for k, v in attrs_dict.items()
                                  if k in ("style", "class", "id", "hidden", "aria-hidden")),
        })

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return
        # Añadir texto a todos los ancestros en el stack
        for frame in self._stack:
            frame["text_parts"].append(text)

    def handle_endtag(self, tag):
        if not self._stack:
            return
        # Buscar el frame correspondiente (puede haber tags sin cerrar)
        idx = None
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i]["tag"] == tag:
                idx = i
                break
        if idx is None:
            return

        frame = self._stack.pop(idx)
        if frame["hidden_method"]:
            text = " ".join(frame["text_parts"]).strip()
            if text:
                self.hidden_contents.append(HiddenContent(
                    text=text,
                    method=frame["hidden_method"],
                    tag=frame["tag"],
                    context=frame["attrs_str"],
                ))

    def _detect_hidden(self, tag: str, attrs: dict) -> str | None:
        """Detecta si un elemento está oculto. Devuelve el método o None."""
        # HTML hidden attribute
        if "hidden" in attrs:
            return "html_hidden_attr"

        # aria-hidden="true"
        if attrs.get("aria-hidden", "").lower() == "true":
            return "aria_hidden"

        # CSS inline styles
        style = attrs.get("style", "")
        if style:
            for pattern, method in _HIDDEN_CSS_PATTERNS:
                if re.search(pattern, style, re.IGNORECASE):
                    return method

        return None


def extract_links_from_html(html: str) -> list[ExtractedLink]:
    """Extrae todos los enlaces de un string HTML."""
    parser = LinkExtractor()
    parser.feed(html)
    return parser.get_links()


def extract_hidden_content(html: str) -> tuple[list[HiddenContent], list[MetaContent]]:
    """Extrae contenido oculto y meta tags de un string HTML."""
    parser = HiddenContentExtractor()
    parser.feed(html)
    return parser.hidden_contents, parser.meta_contents
