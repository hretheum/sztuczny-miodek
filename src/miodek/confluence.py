#!/usr/bin/env python3
"""
confluence.py — connector REST do Confluence (KAN-233, Krok 1: read-only). ZERO-DEP (stdlib).

Pobiera stronę w formacie storage (XHTML), żeby adapter mógł wyłuskać czystą prozę do audytu.
Warstwa transportu i sekretów; NIC o językoznawstwie (to robi ConfluenceStorageAdapter).

GRANICA: connector zna sieć i wersje, nie zna prozy. Oddaje surowy storage jako string.

SEKRETY WYŁĄCZNIE ZE ZMIENNYCH ŚRODOWISKOWYCH (jak RUNPOD_API_KEY, jak endpoint LanguageTool):
  CONFLUENCE_BASE_URL   baza instancji, np. https://twoja-domena.atlassian.net/wiki
  CONFLUENCE_EMAIL      e-mail konta (Basic auth)
  CONFLUENCE_TOKEN      token API (Basic auth)
Brak base URL albo poświadczeń => błąd z prośbą o konfigurację. Nie ma domyślnej instancji,
więc nic nie łączy się nigdzie bez świadomego wskazania (spójnie z KAN-225 dla LanguageTool).
"""

import base64
import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

BASE_URL_ENV = "CONFLUENCE_BASE_URL"
EMAIL_ENV = "CONFLUENCE_EMAIL"
TOKEN_ENV = "CONFLUENCE_TOKEN"
USER_AGENT = "sztuczny-miodek/confluence (+https://github.com/researchanddeploy/sztuczny-miodek)"


class ConfluenceNotConfigured(RuntimeError):
    """Brak konfiguracji connectora (base URL albo poświadczeń w ENV)."""


@dataclass(frozen=True)
class ConfluencePage:
    """Strona Confluence w formacie storage. `storage` to surowy XHTML do normalizacji adapterem."""
    id: str
    title: str
    storage: str
    version: int
    space_key: Optional[str] = None


def resolve_config(base_url: Optional[str] = None, email: Optional[str] = None,
                   token: Optional[str] = None):
    """Ustala (base_url, email, token) z argumentów lub ENV. Brak któregokolwiek => błąd.

    Pierwszeństwo ma argument jawny, potem ENV. Wartości sekretów nigdy nie trafiają do komunikatu
    błędu (echo'wane są tylko NAZWY zmiennych, jak w languagetool/runpod)."""
    base_url = base_url or os.environ.get(BASE_URL_ENV, "")
    email = email or os.environ.get(EMAIL_ENV, "")
    token = token or os.environ.get(TOKEN_ENV, "")
    missing = [name for name, val in
               ((BASE_URL_ENV, base_url), (EMAIL_ENV, email), (TOKEN_ENV, token)) if not val]
    if missing:
        raise ConfluenceNotConfigured(
            "Connector Confluence nie jest skonfigurowany. Ustaw zmienne środowiskowe: "
            + ", ".join(missing) + ". Wzór w .env.example."
        )
    return base_url.rstrip("/"), email, token


def _default_http_transport(url: str, *, headers: dict, timeout: float) -> str:
    """Domyślny transport GET (urllib). Zwraca treść odpowiedzi jako tekst."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def parse_page(raw: str) -> ConfluencePage:
    """Parsuje odpowiedź JSON API (content/{id}?expand=body.storage,version,space) na ConfluencePage."""
    d = json.loads(raw)
    body = (d.get("body") or {}).get("storage") or {}
    version = (d.get("version") or {}).get("number")
    space = (d.get("space") or {}).get("key")
    return ConfluencePage(
        id=str(d.get("id", "")),
        title=d.get("title", ""),
        storage=body.get("value", ""),
        version=int(version) if version is not None else 0,
        space_key=space,
    )


def fetch_page(page_id: str, *, base_url: Optional[str] = None, email: Optional[str] = None,
               token: Optional[str] = None, transport: Optional[Callable] = None,
               timeout: float = 30.0) -> ConfluencePage:
    """Pobiera stronę po ID w formacie storage. Sekrety z ENV (lub argumentów). Transport
    wstrzykiwalny (atrapa w testach => zero realnej sieci, jak w languagetool/engines)."""
    base, email, token = resolve_config(base_url, email, token)
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Accept": "application/json",
               "User-Agent": USER_AGENT}
    url = f"{base}/rest/api/content/{page_id}?expand=body.storage,version,space"
    transport = transport or _default_http_transport
    raw = transport(url, headers=headers, timeout=timeout)
    return parse_page(raw)


def _slug(title: str, fallback: str) -> str:
    """Bezpieczna nazwa pliku z tytułu strony."""
    import re
    s = re.sub(r"[^\w-]+", "-", title.lower()).strip("-")[:60]
    return s or fallback


def _pull(args) -> int:
    """Tryb pull: pobierz stronę/strony, wyłuskaj czystą prozę adapterem Confluence, zapisz jako
    .txt i zaudytuj linterem (read-only, bez zapisu zwrotnego)."""
    import os
    import sys
    from miodek import ai_linter
    from miodek import adapter as adp

    os.makedirs(args.out, exist_ok=True)
    paths = []
    fetch_errors = 0
    for pid in args.page:
        try:
            page = fetch_page(pid)
        except ConfluenceNotConfigured as e:
            # Brak konfiguracji dotyczy wszystkich stron — nie ma sensu próbować dalej.
            print(f"[ERROR] {e}", file=sys.stderr)
            return 2
        except Exception as e:  # noqa: BLE001 — błąd sieci/HTTP raportujemy zwięźle, bez tokenu
            # Błąd pojedynczej strony nie przerywa pozostałych; raportujemy i lecimy dalej.
            print(f"[ERROR] nie pobrano strony {pid}: {e}", file=sys.stderr)
            fetch_errors += 1
            continue
        doc = adp.ConfluenceStorageAdapter().normalize(page.storage)
        path = os.path.join(args.out, f"{pid}-{_slug(page.title, pid)}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(doc.text)
        paths.append(path)
        print(f"[confluence] pobrano „{page.title}” (id {pid}, wersja {page.version}) -> {path}",
              file=sys.stderr)

    # Audyt wyłuskanej prozy istniejącym pipeline lintera (reużycie, zero duplikacji logiki).
    compiled = ai_linter.compile_markers(args.lang)
    all_hits, summaries = [], []
    for p in paths:
        hits, summary = ai_linter.scan_file(p, compiled, args.lang)
        all_hits.extend(hits)
        summaries.append(summary)
    out = ai_linter.format_manifest(all_hits, summaries)
    if args.report:
        out += "\n" + ai_linter.format_batch_report(ai_linter.compute_batch(all_hits, summaries))
    print(out)
    verdict_fail = any(s.verdict in ("FAIL", "FAIL-HARD") for s in summaries)
    # Exit niezerowy, gdy którakolwiek strona padła w pobieraniu LUB ma negatywny werdykt.
    return 1 if (fetch_errors or verdict_fail) else 0


def main(argv=None) -> int:
    """Podkomenda `miodek confluence` (KAN-233, Krok 1). Tryb: pull (read-only audyt prozy)."""
    import argparse
    ap = argparse.ArgumentParser(
        prog="miodek confluence",
        description="Audyt prozy stron Confluence przez adapter (read-only; bez zapisu zwrotnego).",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    pull = sub.add_parser("pull", help="Pobierz i zaudytuj prozę strony/stron (bez zapisu).")
    pull.add_argument("--page", nargs="+", required=True, metavar="ID",
                      help="ID strony Confluence (można podać wiele).")
    pull.add_argument("--out", default="conflu",
                      help="Katalog na wyłuskaną prozę (.txt). Domyślnie ./conflu.")
    pull.add_argument("--lang", choices=["pl", "en", "both"], default="both")
    pull.add_argument("--report", action="store_true",
                      help="Dołóż zbiorczy agregat batch (== BATCH ==).")
    args = ap.parse_args(argv)
    if args.cmd == "pull":
        return _pull(args)
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(main())
