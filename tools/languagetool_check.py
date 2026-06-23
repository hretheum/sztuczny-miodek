#!/usr/bin/env python3
"""
languagetool_check.py — CLI pełnej korekty polszczyzny przez LanguageTool, NA ŻĄDANIE (G4).

POZA bramką jakości. Nie jest wpięty do tests/run_tests.sh ani do żadnego hooka — operator
uruchamia go świadomie, gdy chce pełnej korekty polszczyzny (literówki, gramatyka, interpunkcja)
ponad lekkim rdzeniem skilla. Domyślnie NIE odpala się nigdzie automatycznie.

Użycie:
    python3 tools/languagetool_check.py --file dokument.md
    python3 tools/languagetool_check.py --text "Mam pewien błont ortograficzny."
    python3 tools/languagetool_check.py --file x.md --json
    python3 tools/languagetool_check.py --text "..." --endpoint http://localhost:8081/v2/check
    LANGUAGETOOL_ENDPOINT=http://localhost:8081/v2/check python3 tools/languagetool_check.py --file x.md

Realne API LanguageTool jest wołane TYLKO przy faktycznym uruchomieniu (transport nie jest
wystawiony w CLI — produkcyjnie zawsze _default_http_transport). Endpoint rozstrzyga priorytet:
--endpoint > zmienna LANGUAGETOOL_ENDPOINT. Bez wyboru: błąd (KAN-225), nic nie wysyła.
"""

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from miodek import languagetool  # noqa: E402


def _format_suggestion(s) -> str:
    """Czytelny wiersz jednej sugestii: pozycja | reguła | komunikat | → zamienniki."""
    reps = ", ".join(s.replacements) if s.replacements else "—"
    rule = s.rule_id or "?"
    return f"{s.offset}:{s.length} | {rule} | {s.message} | → {reps}"


def _suggestion_to_dict(s) -> dict:
    """Sugestia jako dict (do trybu --json)."""
    return {
        "offset": s.offset, "length": s.length, "message": s.message,
        "replacements": list(s.replacements), "rule_id": s.rule_id,
        "category_id": s.category_id, "issue_type": s.issue_type,
        "context_text": s.context_text,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Pełna korekta polszczyzny przez LanguageTool (NA ŻĄDANIE, poza bramką). G4."
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="Ścieżka pliku do sprawdzenia.")
    src.add_argument("--text", help="Tekst do sprawdzenia (zamiast pliku).")
    ap.add_argument("--language", default="pl-PL", help="Kod języka (domyślnie pl-PL).")
    ap.add_argument("--endpoint", default=None,
                    help="Endpoint LanguageTool (publiczny lub lokalny serwer). Pierwszeństwo: "
                         f"--endpoint > zmienna LANGUAGETOOL_ENDPOINT (bez domyślnego, wymaga wyboru) "
                         f"({languagetool.PUBLIC_ENDPOINT}).")
    ap.add_argument("--json", action="store_true", help="Wypisz surowe sugestie jako JSON.")
    args = ap.parse_args(argv)

    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print(f"[ERROR] nie można odczytać pliku {args.file!r}: {e}", file=sys.stderr)
            return 2
    else:
        text = args.text

    try:
        suggestions = languagetool.check_text(
            text, language=args.language, endpoint=args.endpoint
        )
    except RuntimeError as e:
        print(f"[ERROR] LanguageTool: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps([_suggestion_to_dict(s) for s in suggestions],
                         ensure_ascii=False, indent=2))
        return 0

    if not suggestions:
        print("Brak sugestii korekty (LanguageTool nie znalazł problemów).")
        return 0

    print(f"LanguageTool: {len(suggestions)} sugestii (offset:length | reguła | komunikat | → zamienniki)")
    for s in suggestions:
        print(f"  {_format_suggestion(s)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
