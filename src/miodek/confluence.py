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


class ConfluenceConflict(RuntimeError):
    """Konflikt wersji przy zapisie (ktoś edytował stronę w międzyczasie). Nie nadpisujemy."""


def _default_write_transport(url: str, *, method: str, headers: dict, data: bytes, timeout: float):
    """Domyślny transport zapisu (PUT). Zwraca (status, treść). Nie rzuca na 4xx (zwraca kod)."""
    import urllib.error
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def update_page(page: ConfluencePage, new_storage: str, *, base_url=None, email=None, token=None,
                transport=None, timeout: float = 30.0, comment: str = "miodek: korekta prozy") -> ConfluencePage:
    """Zapisuje zredagowany storage jako NOWĄ wersję (numer N+1). Bezpieczne do wielokrotnego
    uruchomienia: gdy storage bez zmian, pomija PUT (nie pompuje wersji). Konflikt wersji (409)
    przerywa bez nadpisania cudzej zmiany."""
    if new_storage == page.storage:
        return page  # brak zmian — nie tworzymy nowej wersji
    base, email, token = resolve_config(base_url, email, token)
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json",
               "Accept": "application/json", "User-Agent": USER_AGENT}
    body = json.dumps({
        "id": page.id, "type": "page", "title": page.title,
        "version": {"number": page.version + 1, "message": comment},
        "body": {"storage": {"value": new_storage, "representation": "storage"}},
    }).encode("utf-8")
    url = f"{base}/rest/api/content/{page.id}"
    transport = transport or _default_write_transport
    status, resp = transport(url, method="PUT", headers=headers, data=body, timeout=timeout)
    if status == 409:
        raise ConfluenceConflict(
            f"konflikt wersji strony {page.id} (oczekiwano {page.version}+1). Ktoś edytował stronę. "
            "Odśwież (ponowny pull) i spróbuj jeszcze raz."
        )
    if status >= 400:
        raise RuntimeError(f"zapis strony {page.id} nie powiódł się (HTTP {status})")
    return parse_page(resp)


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


def _correct(args) -> int:
    """Tryb correct (KAN-234): pobierz stronę, popraw prozę korektorem (Stage 2), zapisz zredagowaną
    wersję z powrotem. DRY-RUN DOMYŚLNY (pokazuje diff, nie zapisuje); zapis tylko z --apply plus
    potwierdzeniem. Makra, kod i struktura nietknięte; twarda weryfikacja wierności przed PUT."""
    import sys
    import difflib
    from miodek import corrector
    from miodek import adapter as adp

    try:
        engine = corrector.build_corrector_engine(name=args.engine, config_path=args.config)
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] nie zbudowano silnika korektora: {e}", file=sys.stderr)
        return 2

    conf_adapter = adp.ConfluenceStorageAdapter()

    changed_any = False
    errors = 0
    for pid in args.page:
        try:
            page = fetch_page(pid)
        except ConfluenceNotConfigured as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 2
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] nie pobrano strony {pid}: {e}", file=sys.stderr)
            errors += 1
            continue

        # Korekta prowadzona na PROZIE (sprawdzony korektor na .txt). Poprawki wracają na storage
        # przez alignment akapitów (korektor zachowuje liczbę akapitów) + write_back adaptera.
        doc = conf_adapter.normalize(page.storage)
        result = corrector.correct_document(
            doc.text, file_path="_confluence_audit.txt", engine=engine,
            stage2_fn=corrector._make_managed_stage2(args.config),  # auto-offload poda RunPod po użyciu
        )
        new_storage = page.storage
        if result.text != doc.text:
            orig_paras = doc.paragraphs()
            new_paras = adp.split_paragraphs_faithful(result.text)
            if len(orig_paras) != len(new_paras):
                print(f"[ABORT] „{page.title}” (id {pid}): korekta zmieniła liczbę akapitów "
                      "(nieoczekiwane); nie składam z powrotem.", file=sys.stderr)
                errors += 1
                continue
            edits = [adp.Edit(o.start, o.end, n.text)
                     for o, n in zip(orig_paras, new_paras) if o.text != n.text]
            new_storage = conf_adapter.write_back(doc, edits)
        if new_storage == page.storage:
            print(f"[confluence] „{page.title}” (id {pid}): brak zmian "
                  f"(werdykt korektora: {result.reason}).", file=sys.stderr)
            continue

        # TWARDA BRAMKA: nowy storage może różnić się od oryginału WYŁĄCZNIE prozą.
        if not adp.verify_prose_only_change(page.storage, new_storage):
            print(f"[ABORT] „{page.title}” (id {pid}): weryfikacja wierności nie przeszła "
                  "(zmiana dotknęłaby makr/struktury). NIE zapisuję.", file=sys.stderr)
            errors += 1
            continue

        # Diff prozy (czytelny dla człowieka) — przed/po na wyłuskanym tekście.
        old_prose = conf_adapter.normalize(page.storage).text.splitlines()
        new_prose = conf_adapter.normalize(new_storage).text.splitlines()
        diff = list(difflib.unified_diff(old_prose, new_prose,
                                         fromfile=f"{pid} (przed)", tofile=f"{pid} (po)", lineterm=""))
        print(f"\n=== „{page.title}” (id {pid}, wersja {page.version}) — proponowana korekta prozy ===")
        print("\n".join(diff) if diff else "(zmiana tylko w obrębie linii)")
        changed_any = True

        if not args.apply:
            print(f"[dry-run] NIE zapisano. Dodaj --apply, aby zapisać jako wersję {page.version + 1}.",
                  file=sys.stderr)
            continue

        if not args.yes:
            try:
                ans = input(f"Zapisać stronę {pid} „{page.title}” jako wersję {page.version + 1}? [t/N] ")
            except EOFError:
                ans = ""
            if ans.strip().lower() not in ("t", "tak", "y", "yes"):
                print(f"[pominięto] {pid}: bez zapisu (brak potwierdzenia).", file=sys.stderr)
                continue
        try:
            updated = update_page(page, new_storage)
            print(f"[zapisano] {pid}: wersja {updated.version}.", file=sys.stderr)
        except ConfluenceConflict as e:
            print(f"[ABORT] {e}", file=sys.stderr)
            errors += 1
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] zapis {pid} nie powiódł się: {e}", file=sys.stderr)
            errors += 1

    return 1 if errors else 0


def main(argv=None) -> int:
    """Podkomenda `miodek confluence` (KAN-233/234). Tryby: pull (read-only audyt), correct (write-back)."""
    import argparse
    from miodek import config as _config
    ap = argparse.ArgumentParser(
        prog="miodek confluence",
        description="Audyt i korekta prozy stron Confluence przez adapter.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    pull = sub.add_parser("pull", help="Pobierz i zaudytuj prozę strony/stron (read-only).")
    pull.add_argument("--page", nargs="+", required=True, metavar="ID",
                      help="ID strony Confluence (można podać wiele).")
    pull.add_argument("--out", default="conflu",
                      help="Katalog na wyłuskaną prozę (.txt). Domyślnie ./conflu.")
    pull.add_argument("--lang", choices=["pl", "en", "both"], default="both")
    pull.add_argument("--report", action="store_true",
                      help="Dołóż zbiorczy agregat batch (== BATCH ==).")

    corr = sub.add_parser("correct",
                          help="Popraw prozę korektorem i zapisz z powrotem (dry-run domyślny).")
    corr.add_argument("--page", nargs="+", required=True, metavar="ID",
                      help="ID strony Confluence (można podać wiele).")
    corr.add_argument("--engine", default=None, choices=("stub", "openai", "ollama"),
                      help="Silnik korekty (nadpisuje config). Domyślnie z config.json.")
    corr.add_argument("--config", default=_config.CONFIG_PATH, help="Ścieżka config.json.")
    corr.add_argument("--lang", choices=["pl", "en", "both"], default="both")
    corr.add_argument("--apply", action="store_true",
                      help="Zapisz zmiany do Confluence. Bez tej flagi: dry-run (tylko diff).")
    corr.add_argument("--yes", action="store_true",
                      help="Pomiń interaktywne potwierdzenie (tylko w parze z --apply, np. CI).")

    args = ap.parse_args(argv)
    if args.cmd == "pull":
        return _pull(args)
    if args.cmd == "correct":
        return _correct(args)
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(main())
