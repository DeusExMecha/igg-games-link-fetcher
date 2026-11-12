#!/usr/bin/env python3
"""
download_links.py – Liest alle „Download HERE“-Links einer igg-games-Seite aus
und löst jede Redirect-Kette auf (ohne die eigentlichen Dateien herunterzuladen).

Installation:  pip install requests beautifulsoup4 playwright
                playwright install chromium   (einmalig, ~123 MB)
Aufruf:        python download_links.py <Seiten-URL> [--timeout 20] [--delay 1]

Hinweis: Es werden HTTP-Redirects aufgelöst. JS-basierte Weiterleitungen

(z. B. bluemediafiles url-generator, upfile.mobi „Redirecting…") sind für
requests unsichtbar – dafür greift ein Playwright-Fallback (headless Chromium),
der die Seite lädt und die finale URL nach der Navigation abgreift.
"""
import argparse
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Link-Extraktion aus der Quellseite
# ---------------------------------------------------------------------------

def fetch_download_links(page_url: str) -> list[tuple[str, str]]:
    """Lädt die Seite und extrahiert alle 'Download HERE'-Links (dedupliziert)."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    r = s.get(page_url, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    links: list[tuple[str, str]] = []

    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        if "download" in text and ("here" in text or "hier" in text):
            url = requests.compat.urljoin(page_url, a["href"])
            links.append((url, a.get_text(strip=True)))

    # Deduplizieren (Reihenfolge beibehalten)
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for url, text in links:
        if url not in seen:
            seen.add(url)
            unique.append((url, text))

    return unique


# ---------------------------------------------------------------------------
# HTTP-Redirect-Auflösung (requests)
# ---------------------------------------------------------------------------

def resolve_redirects(url: str, timeout: int) -> tuple[str, object, list]:
    """Folgt HTTP-Redirects und gibt (finale URL, Status, Kette) zurück."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    chain: list[str] = [url]

    try:
        r = s.get(url, allow_redirects=True, timeout=timeout, stream=True)
        final_url = str(r.url)
        status = r.status_code

        # Zwischenstationen aus der Redirect-History rekonstruieren
        if r.history:
            for h in r.history:
                chain.append(str(h.url))
        elif final_url != url:
            chain.append(final_url)

        r.close()
        return final_url, status, chain

    except requests.RequestException as e:
        return url, f"FEHLER ({type(e).__name__})", chain


# ---------------------------------------------------------------------------
# JS-Redirect-Erkennung
# ---------------------------------------------------------------------------

def looks_like_js_redirect(html: str) -> bool:
    """Erkennt JS-basierte Weiterleitungsseiten (Countdown, meta-refresh)."""
    h = html.lower()
    indicators = [
        "window.location",
        "location.href",
        'meta http-equiv="refresh"',
        "<script",
        "countdown",
        "redirecting",
        "please wait",
        "loading...",
    ]
    score = sum(1 for ind in indicators if ind in h)
    return score >= 2


# ---------------------------------------------------------------------------
# MegaUp-Download-Link-Extraktion
# ---------------------------------------------------------------------------

def extract_megaup_download_link(html: str) -> str | None:
    """Extrahiert den eigentlichen Download-Link von einer MegaUp-Dateiseite.

    Die Datei-Seite (megaup.net/<hash>/<name>) enthält den Link zu
    download.megaup.net/?url=... im Klartext in einem <a>-Tag – kein JS nötig.
    """
    m = re.search(
        r'href=["\'](https://download\.megaup\.net/\?url=[^"\']+)["\']', html
    )
    return m.group(1) if m else None


def is_cloudflare_challenge(html: str) -> bool:
    """Erkennt Cloudflare-Interstitials ('Just a moment…')."""
    h = html.lower()
    return (
        "just a moment" in h
        or "cf-challenge" in h
        or "verify you are human" in h
    )


# ---------------------------------------------------------------------------
# Playwright-Fallback für JS-Redirects
# ---------------------------------------------------------------------------

def resolve_with_playwright(url: str, timeout_ms: int = 30_000) -> tuple[str, object, list]:
    """Lädt die Seite mit headless Chromium und greift die finale URL ab.

    Nutzt Playwright für JS-basierte Weiterleitungen (Countdown-Seiten etc.).
    Gibt (finale URL, Status/Info, Kette) zurück.
    """
    from playwright.sync_api import sync_playwright

    chain: list[str] = [url]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=UA,
                locale="en-US",
                viewport={"width": 1280, "height": 800},
            )
            page = ctx.new_page()

            try:
                resp = page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                status = resp.status if resp else "n/a"

                # Warten auf JS-Redirects – Countdown-Seiten brauchen länger
                content = page.content()
                if looks_like_js_redirect(content):
                    page.wait_for_timeout(20_000)  # ~15 s Countdown + Puffer
                else:
                    page.wait_for_timeout(3_000)

                final_url = page.url
            except Exception as e:
                browser.close()
                return url, f"FEHLER ({type(e).__name__})", chain

            browser.close()

        if final_url != url:
            chain.append(final_url)

        status_str = f"HTTP {status}" if isinstance(status, int) else str(status)
        return final_url, status_str, chain

    except ImportError:
        return url, "FEHLER (Playwright nicht installiert)", chain


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Download-Links auslesen & Redirects auflösen"
    )
    ap.add_argument("page_url", help="URL der Seite mit den Download-Links")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--delay", type=float, default=1.0,
                    help="Pause zwischen Requests (Sek.)")
    args = ap.parse_args()

    print(f"Seite: {args.page_url}\n")
    links = fetch_download_links(args.page_url)
    if not links:
        sys.exit("Keine 'Download HERE'-Links gefunden.")

    for i, (url, text) in enumerate(links, 1):
        final, status, chain = resolve_redirects(url, args.timeout)
        used_playwright = False

        # Fallback: Wenn requests auf einer HTML-Seite landet, die nach JS-Redirect
        # aussieht → Playwright nachziehen (nur bei text/html, nicht bei Dateien).
        if isinstance(status, int) and status == 200:
            try:
                s = requests.Session()
                s.headers.update({"User-Agent": UA})
                r = s.get(final, allow_redirects=True, timeout=args.timeout, stream=True)
                content_type = r.headers.get("Content-Type", "")

                if "text/html" in content_type:
                    html_snippet = next(
                        r.iter_content(20_000), b""
                    ).decode("utf-8", errors="ignore")
                    r.close()

                    if looks_like_js_redirect(html_snippet):
                        used_playwright = True
                        final, status, chain = resolve_with_playwright(url)
                else:
                    r.close()
            except requests.RequestException:
                pass

        # MegaUp-Dateiseiten enthalten den eigentlichen Download-Link im HTML – extrahieren.
        megaup_dl_link = None
        if "megaup.net" in final and "download.megaup.net" not in final:
            try:
                s2 = requests.Session()
                s2.headers.update({"User-Agent": UA})
                r2 = s2.get(final, timeout=args.timeout)
                megaup_dl_link = extract_megaup_download_link(r2.text)
            except requests.RequestException:
                pass

        print(f"[{i}] {text}")
        print(f"    von   : {url}")
        for step in chain[1:-1]:  # Zwischenstationen (falls vorhanden)
            print(f"    ->    {step}")

        status_str = f"(HTTP {status})" if isinstance(status, int) else f"({status})"
        pw_note = "  [Playwright-Fallback]" if used_playwright else ""
        print(f"    final : {final}  {status_str}{pw_note}\n")

        if megaup_dl_link:
            cf_hint = ""
            # Prüfen, ob der Ziel-Link hinter einer Cloudflare-Challenge liegt
            try:
                s3 = requests.Session()
                s3.headers.update({"User-Agent": UA})
                r3 = s3.get(megaup_dl_link, timeout=args.timeout, stream=True)
                snippet = next(r3.iter_content(20_000), b"").decode("utf-8", errors="ignore")
                r3.close()
                if is_cloudflare_challenge(snippet):
                    cf_hint = "  (Cloudflare-protected – manueller Browser-Besuch nötig)"
            except requests.RequestException:
                pass

            print(f"    megaup-dl : {megaup_dl_link}{cf_hint}\n")

        time.sleep(args.delay)


if __name__ == "__main__":
    main()