#!/usr/bin/env python3
"""
measure_structural.py — regresja adaptera formatu strukturalnego (C4 / KAN-193, szkielet).

Sprawdza rdzeń StructuralAdapter (HTML/wiki): granice akapitów ze ZNACZNIKÓW blokowych (nie pustych
linii), pomijanie zawartości kodu, wierność source_map (proza→źródło). ZERO-DEP (stdlib).

Exit 1 gdy którykolwiek przypadek się nie zgadza (gate w run_tests.sh).

Użycie:
    python3 tools/measure_structural.py
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
import adapter  # noqa: E402


def _prose_paras(doc):
    return [s.text.strip() for s in doc.paragraphs() if s.text.strip()]


CHECKS = []


def check(desc, fn):
    CHECKS.append((desc, fn))


def c_block_boundaries():
    html = "<p>Pierwszy — raz.</p><p>Drugi — dwa.</p>"
    doc = adapter.StructuralAdapter().normalize(html)
    return _prose_paras(doc) == ["Pierwszy — raz.", "Drugi — dwa."]


def c_emdash_not_merged():
    # 4 akapity po 1 myślniku → BRAK em-dash overuse (gdyby zlane: 4 w 1 akapicie = overuse)
    import ai_linter
    html = "<p>Cel — jasny.</p><p>Zakres — szeroki.</p><p>Budżet — ok.</p><p>Termin — bliski.</p>"
    doc = adapter.StructuralAdapter().normalize(html)
    return len(ai_linter.detect_emdash_overuse(doc.text, "pl")) == 0


def c_code_skipped():
    html = "<p>Tekst <code>x — y — z — w</code> koniec.</p>"
    doc = adapter.StructuralAdapter().normalize(html)
    return doc.text.count("—") == 0  # myślniki z <code> pominięte


def c_source_map():
    html = "<p>Pierwszy akapit.</p><p>Drugi akapit.</p>"
    doc = adapter.StructuralAdapter().normalize(html)
    i = doc.text.index("Drugi")
    src = doc.to_source_offset(i)
    return html[src:src + 5] == "Drugi"


def c_source_preserved():
    html = "<p>Cokolwiek.</p>"
    doc = adapter.StructuralAdapter().normalize(html)
    return doc.source == html


def c_br_soft_break():
    # <br> = miękki podział: linie zostają w JEDNYM akapicie (nie rozbija na dwa)
    html = "<p>Linia jeden<br>linia dwa</p><p>Drugi akapit.</p>"
    doc = adapter.StructuralAdapter().normalize(html)
    paras = [s.text.strip() for s in doc.paragraphs() if s.text.strip()]
    return len(paras) == 2 and "\n" in paras[0]


def c_routing_by_extension():
    # routing wg rozszerzenia: .html → Structural, .md → Markdown, .txt → PlainText
    import ai_linter
    return (
        type(ai_linter._select_adapter("x.html")).__name__ == "StructuralAdapter"
        and type(ai_linter._select_adapter("x.htm")).__name__ == "StructuralAdapter"
        and type(ai_linter._select_adapter("x.md")).__name__ == "MarkdownAdapter"
        and type(ai_linter._select_adapter("x.txt")).__name__ == "PlainTextAdapter"
    )


check("granice akapitów ze znaczników blokowych <p>", c_block_boundaries)
check("myślniki z różnych <p> nie zlewają się (brak FP em-dash)", c_emdash_not_merged)
check("zawartość <code> pomijana w prozie", c_code_skipped)
check("<br> = miękki podział (linie w jednym akapicie)", c_br_soft_break)
check("routing wg rozszerzenia (.html→Structural, .md→Markdown, .txt→PlainText)", c_routing_by_extension)
check("source_map mapuje pozycję prozy na źródło", c_source_map)
check("source zachowane (oryginalny HTML)", c_source_preserved)


def main():
    fails = []
    for desc, fn in CHECKS:
        try:
            ok = bool(fn())
        except Exception as e:  # noqa: BLE001
            ok = False
            desc = f"{desc} (wyjątek: {e})"
        if not ok:
            fails.append(desc)

    ok = len(CHECKS) - len(fails)
    print(f"Adapter strukturalny (C4 szkielet) — {ok}/{len(CHECKS)} przypadków OK")
    for desc in fails:
        print(f"  [FAIL] {desc}", file=sys.stderr)
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
