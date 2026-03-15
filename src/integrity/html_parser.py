"""Extractor de enlaces de HTML usando stdlib."""

from html.parser import HTMLParser
from dataclasses import dataclass


@dataclass
class ExtractedLink:
    href: str
    text: str       # Texto visible del enlace (innerText)
    context: str     # Texto circundante para evidencia


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


def extract_links_from_html(html: str) -> list[ExtractedLink]:
    """Extrae todos los enlaces de un string HTML."""
    parser = LinkExtractor()
    parser.feed(html)
    return parser.get_links()
