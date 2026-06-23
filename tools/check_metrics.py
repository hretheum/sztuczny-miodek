#!/usr/bin/env python3
"""
check_metrics.py — gate metryk z manifestu (E1: współczynnik redukcji). ZERO-DEP (stdlib).

Działa na zaszytym mini-manifeście i treści podanej W PAMIĘCI (wstrzyknięty file_reader) — bez I/O,
bez sieci, bez LLM. Weryfikuje fundamenty definicji redukcji:

  1. akapit z trafieniem klasy "review" jest liczony jako routed,
  2. akapit z samym trafieniem "block" NIE jest routed (block linter zamyka sam),
  3. akapit czysty NIE jest routed,
  4. routed_words = suma słów akapitów review (zgodność z definicją i formułą słów),
  5. inwariant: reduction_ratio + routed_ratio == 1.0,
  6. routed_ratio porównywalny z odniesieniem (tu liczony, nie zaszyty na sztywno),
  7. wariant awaryjny: plik nieczytelny z trafieniem review => fallback, cały plik jako routed.

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import metrics  # noqa: E402


# --- Mini-dokument: 3 akapity rozdzielone pustą linią ---
# Akapit 1 (linie 1-1): trafienie review  -> routed
# Akapit 2 (linie 3-3): trafienie block    -> NIE routed
# Akapit 3 (linie 5-5): czysty             -> NIE routed
DOC = (
    "Pierwszy akapit ma trafienie review tutaj.\n"   # linia 1  (8 słów)
    "\n"                                              # linia 2
    "Drugi akapit zawiera twardy bloker block.\n"     # linia 3  (6 słów)
    "\n"                                              # linia 4
    "Trzeci akapit jest zupełnie czysty bez niczego." # linia 5  (7 słów)
)

# Mini-manifest spójny z DOC. Słowa per plik = łączna liczba słów DOC.
WORDS_TOTAL = len(metrics._WORD_RE.findall(DOC))
PARA1_WORDS = len(metrics._WORD_RE.findall("Pierwszy akapit ma trafienie review tutaj."))

MANIFEST = {
    "hits": [
        {"file": "doc.txt", "line": 1, "id": "PL-SIGN", "klasa": "review", "match": "review"},
        {"file": "doc.txt", "line": 3, "id": "EN-DASH", "klasa": "block", "match": "block"},
    ],
    "summary": [
        {"file": "doc.txt", "words": WORDS_TOTAL, "hits": 2, "emdash_max": 0,
         "density": 0.0, "blockers": 1, "verdict": "FAIL"},
    ],
}


def _reader_ok(path):
    if path == "doc.txt":
        return DOC
    raise OSError(f"nieoczekiwana ścieżka: {path}")


def _reader_missing(path):
    raise OSError(f"brak pliku: {path}")


def main():
    fails = []

    # --- Główny przebieg: file_reader w pamięci ---
    r = metrics.reduction_from_manifest(MANIFEST, file_reader=_reader_ok)

    # 1+2+3: routed tylko akapit 1 (review). Block i czysty pominięte.
    if r["routed_segments"] != 1:
        fails.append(f"routed_segments: oczekiwano 1 (tylko akapit review), jest {r['routed_segments']}")
    if r["total_segments"] != 3:
        fails.append(f"total_segments: oczekiwano 3, jest {r['total_segments']}")

    # 4: routed_words = słowa akapitu review.
    if r["routed_words"] != PARA1_WORDS:
        fails.append(f"routed_words: oczekiwano {PARA1_WORDS} (słowa akapitu review), jest {r['routed_words']}")
    if r["total_words"] != WORDS_TOTAL:
        fails.append(f"total_words: oczekiwano {WORDS_TOTAL}, jest {r['total_words']}")

    # 5: inwariant reduction + routed == 1.
    if abs((r["reduction_ratio"] + r["routed_ratio"]) - 1.0) > 1e-9:
        fails.append(f"inwariant: reduction + routed != 1 ({r['reduction_ratio']} + {r['routed_ratio']})")

    # 6: routed_ratio = PARA1_WORDS / WORDS_TOTAL.
    expected_routed = PARA1_WORDS / WORDS_TOTAL
    if abs(r["routed_ratio"] - expected_routed) > 1e-9:
        fails.append(f"routed_ratio: oczekiwano {expected_routed:.4f}, jest {r['routed_ratio']:.4f}")

    # Kontrola: per_file zgodne z agregatem.
    pf = r["per_file"][0]
    if pf["routed_words"] != PARA1_WORDS or pf["fallback"]:
        fails.append(f"per_file: routed_words/fallback rozjazd: {pf}")

    # 7: wariant awaryjny — plik z review, ale nieczytelny => fallback, cały plik routed.
    rf = metrics.reduction_from_manifest(MANIFEST, file_reader=_reader_missing)
    if not rf["per_file"][0]["fallback"]:
        fails.append("fallback: nieczytelny plik z review powinien dać fallback=True")
    if rf["routed_words"] != WORDS_TOTAL:
        fails.append(f"fallback: oczekiwano routed_words={WORDS_TOTAL} (cały plik), jest {rf['routed_words']}")

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)

    print(f"OK   metryki E1: redukcja {r['reduction_ratio']*100:.1f}% / routed {r['routed_ratio']*100:.1f}% "
          f"(akapit review routed, block+czysty pominięte; inwariant red+routed=1; fallback działa).")


if __name__ == "__main__":
    main()
