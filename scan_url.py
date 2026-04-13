#!/usr/bin/env python3
"""SignalOrbit — Integrity Scanner CLI.

Detecta señales de AI Recommendation Poisoning en URLs y páginas web.

Uso:
    python scan_url.py --url "https://example-blog.com/best-crm"
    python scan_url.py --analyze-link "https://chatgpt.com/?q=Summarize+and+remember..."
    python scan_url.py --url-list urls_to_scan.txt
    python scan_url.py --url "https://..." --output data/integrity/integrity_events.jsonl
"""

import argparse
import json
from pathlib import Path

from src.integrity.scanner import IntegrityScanner, IntegrityEvent
from src.io.write_jsonl import append_record
from src.logger import get_logger

log = get_logger(__name__)


def _print_event(event: IntegrityEvent) -> None:
    """Imprime un evento de integridad en formato legible."""
    label = event.risk_level.upper()
    print(f"  [!] {label} ({event.risk_score}) {event.ai_target_domain} · "
          f"\"{event.decoded_prompt[:80]}{'...' if len(event.decoded_prompt) > 80 else ''}\"")
    if event.memory_keywords_found:
        print(f"      Keywords: {', '.join(event.memory_keywords_found)}")
    print(f"      MITRE: {', '.join(event.mitre_atlas_tags)}")
    if event.brand_mentioned_in_prompt:
        print(f"      Brand: {event.brand_mentioned_in_prompt}")


def main():
    parser = argparse.ArgumentParser(description="SignalOrbit Integrity Scanner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="URL of a page to scan (downloads and analyzes links)")
    group.add_argument("--analyze-link", help="Direct URL to analyze without downloading a page")
    group.add_argument("--url-list", help="File with URLs to scan (one per line)")
    parser.add_argument("--output", default="data/integrity/integrity_events.jsonl",
                        help="Path to output JSONL (default: data/integrity/integrity_events.jsonl)")
    args = parser.parse_args()

    scanner = IntegrityScanner()
    all_events: list[IntegrityEvent] = []

    print("═" * 55)
    print("  SignalOrbit Integrity Scan")
    print("═" * 55)

    if args.analyze_link:
        print(f"  Analyzing: {args.analyze_link}")
        print("─" * 55)
        event = scanner.analyze_single_url(args.analyze_link)
        if event:
            all_events.append(event)
            _print_event(event)
        else:
            print("  No suspicious signals detected.")

    elif args.url:
        print(f"  Scanning: {args.url}")
        print("─" * 55)
        events = scanner.scan_page(args.url)
        all_events.extend(events)
        for event in events:
            _print_event(event)
        if not events:
            print("  No suspicious signals detected.")

    elif args.url_list:
        url_file = Path(args.url_list)
        if not url_file.exists():
            log.error("URL list file not found", extra={"path": args.url_list})
            return
        urls = [line.strip() for line in url_file.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")]
        print(f"  URLs to scan: {len(urls)}")
        print("─" * 55)
        for url in urls:
            print(f"\n  Scanning: {url}")
            events = scanner.scan_page(url)
            all_events.extend(events)
            for event in events:
                _print_event(event)
            if not events:
                print("  No suspicious signals detected.")

    # Write events to JSONL
    if all_events:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        for event in all_events:
            append_record(args.output, event.to_dict())

    # Summary
    print()
    print("─" * 55)
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for e in all_events:
        counts[e.risk_level] += 1
    print(f"  Total: {len(all_events)} events · "
          f"{counts['critical']} critical · {counts['high']} high · "
          f"{counts['medium']} medium · {counts['low']} low")
    if all_events:
        print(f"  Output: {args.output}")
    print("═" * 55)


if __name__ == "__main__":
    main()
