#!/usr/bin/env python3
"""
measure_markdown.py — regresja adaptera Markdown (C3 / KAN-192).

Sprawdza, że `adapter.strip_code_spans` poprawnie zeruje zawartość kodu (bloki ```/~~~ i inline
`…`), zachowując długość i nowe linie, oraz że proza pozostaje nietknięta. To gwarantuje, że
detektory (em-dash, bold) nie liczą znaków w kodzie jako manieryzmu prozy. ZERO-DEP (stdlib).

Exit 1 gdy którykolwiek przypadek się nie zgadza (gate w run_tests.sh).

Użycie:
    python3 tools/measure_markdown.py
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
import adapter  # noqa: E402


# Każdy przypadek: (opis, źródło, predykat(stripped, source) -> bool).
def _len_and_newlines_preserved(stripped, source):
    return len(stripped) == len(source) and stripped.count("\n") == source.count("\n")


def _code_blanked(stripped, source, needle):
    """needle (fragment kodu) nie występuje w stripped, ale jest w source."""
    return needle in source and needle not in stripped


def _prose_kept(stripped, prose):
    return prose in stripped


CASES = []


def case(desc, source, check):
    CASES.append((desc, source, check))


FENCE = "```"
case(
    "blok kodu ``` zerowany, proza zachowana",
    f"Proza przed.\n\n{FENCE}python\nx = a — b — c — d\n{FENCE}\n\nProza po — z myślnikiem.",
    lambda s, src: _len_and_newlines_preserved(s, src)
    and _code_blanked(s, src, "x = a — b — c — d")
    and _prose_kept(s, "Proza przed.")
    and _prose_kept(s, "Proza po — z myślnikiem."),
)
case(
    "blok kodu ~~~ zerowany",
    "Tekst.\n\n~~~\nkod — z — myślnikami\n~~~\n\nKoniec.",
    lambda s, src: _len_and_newlines_preserved(s, src)
    and _code_blanked(s, src, "kod — z — myślnikami"),
)
case(
    "inline code `…` zerowany, długość zachowana",
    "Gałąź `fix/db — pool — x` wymaga przeglądu.",
    lambda s, src: _len_and_newlines_preserved(s, src)
    and _code_blanked(s, src, "fix/db — pool — x")
    and _prose_kept(s, "wymaga przeglądu."),
)
case(
    "czysta proza bez kodu — bez zmian",
    "Zwykły akapit bez kodu. Drugie zdanie.",
    lambda s, src: s == src,
)


def main():
    fails = []
    for desc, source, check in CASES:
        stripped = adapter.strip_code_spans(source)
        try:
            ok = bool(check(stripped, source))
        except Exception as e:  # noqa: BLE001
            ok = False
            desc = f"{desc} (wyjątek: {e})"
        if not ok:
            fails.append(desc)

    ok = len(CASES) - len(fails)
    print(f"Adapter Markdown — {ok}/{len(CASES)} przypadków OK")
    for desc in fails:
        print(f"  [FAIL] {desc}", file=sys.stderr)
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
