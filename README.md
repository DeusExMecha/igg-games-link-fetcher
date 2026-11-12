# igg-games Link-Fetcher

Liest alle **„Download HERE“-Links** einer [igg-games.com](https://igg-games.com)-Seite aus und löst für jeden Link die **Redirect-Kette** auf – ohne die eigentlichen Dateien herunterzuladen.

## Installation

```powershell
pip install requests beautifulsoup4 playwright
playwright install chromium   # einmalig, ~123 MB (nur für den JS-Fallback nötig)
```

> ⚠️ Immer das **Store-Python** verwenden (nie MSYS2).

## Nutzung

```powershell
python download_links.py <Seiten-URL> [--timeout 20] [--delay 1]
```

| Option | Standard | Bedeutung |
|---|---|---|
| `--timeout` | `20` | Timeout pro Request in Sekunden |
| `--delay` | `1.0` | Pause zwischen den Requests (Sekunden) – schonend zu den Hosts |

Beispiel:

```powershell
python download_links.py "https://igg-games.com/settlers-2-gold-edition/" --timeout 20 --delay 1
```

## Ausgabeformat

Pro gefundener Link:

```text
[1] Download HERE
    von   : https://.../originaler-link
    ->    https://.../zwischenstation (falls vorhanden)
    final : https://.../ziel  (HTTP 200)  [Playwright-Fallback]

    megaup-dl : https://download.megaup.net/?url=...  (Cloudflare-protected – manueller Browser-Besuch nötig)
```

- `von` – der Link, wie er auf der igg-games-Seite steht
- `->` – alle HTTP-Zwischenstationen der Redirect-Kette
- `final` – die endgültige URL inkl. Status; `[Playwright-Fallback]`, wenn JS-Auflösung nötig war
- `megaup-dl` – nur bei MegaUp-Dateiseiten: der eigentliche Download-Link, extrahiert aus dem HTML

## Funktionsweise

1. **Extraktion:** Alle `<a>`-Tags mit „Download … here/hier“ im Text werden geladen und dedupliziert (`requests` + `BeautifulSoup`).
2. **HTTP-Auflösung:** Jede Redirect-Kette wird per `requests` (streaming, ohne Dateiinhalt) nachverfolgt; Zwischenstationen kommen aus der Response-History.
3. **JS-Fallback:** Landet man auf einer HTML-Seite mit JS-Weiterleitung (Countdown, meta-refresh), lädt ein headless Chromium via Playwright die Seite und greift die finale URL ab.
4. **MegaUp-Sonderfall:** MegaUp-Dateiseiten enthalten den echten `download.megaup.net/?url=…`-Link im Klartext – der wird extrahiert und separat ausgegeben, inkl. Cloudflare-Erkennung.

## Bekannte Grenzen (verifiziert)

| Host / Fall | Ergebnis mit diesem Tool |
|---|---|
| **Google Drive** (`docs.google.com/uc`) | ✅ Redirect-Kette auflösbar (303 → `drive.usercontent.google.com`); 404 = Datei wurde entfernt |
| **MegaUp** (`megaup.net/<hash>/<name>`) | ⚠️ Download-Link wird aus dem HTML extrahiert, aber die finale Datei liegt hinter einer Cloudflare-Challenge („Just a moment…“) – auch headless Chromium scheitert → manueller Browser-Besuch nötig |
| **bluemediafiles** (`url-generator`) | ❌ JS-basierte Weiterleitung; nur Ad-/Tracking-JS im HTML, kein sauberes Ziel extrahierbar (Playwright-Fallback greift bei erkennbaren Countdown-Seiten) |
| **go4up.com / upfile.mobi** | ⚠️ Liefert HTTP 200 `text/html` ohne Location-Header – JS-Countdown-/Redirect-Seite; nur mit Playwright-Fallback auflösbar, wenn die Seite nachlädt |
| **openload.co / copiapop.com / ul.to** | ❌ In der Testumgebung nicht erreichbar (ConnectTimeout / ConnectionError / ReadTimeout) – Host tot oder blockiert |

## Projekt-Dateien

| Datei | Zweck |
|---|---|
| `download_links.py` | Hauptskript – Link-Extraktion + Redirect-Auflösung (+ Playwright-Fallback, MegaUp/Cloudflare-Erkennung) |

## Kurzregeln für die Arbeit in diesem Projekt
1. Terminal-Befehl? → Store-Python + `-X utf8` verwenden.
2. Neue Probe-/Test-Skripte mit `_probe_*` / `verify_*` benennen und im Root ablegen (Wegwerf-Code, nach der Analyse löschen).