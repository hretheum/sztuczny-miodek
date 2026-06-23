#!/usr/bin/env python3
"""
check_runner.py — gate runnera Stage 2 (G1). ZERO-DEP (stdlib), bez LLM, bez sieci.

Działa na zaszytym mini-manifeście i treści podanej W PAMIĘCI (wstrzyknięty file_reader). Weryfikuje:

  1. select_review_segments zwraca DOKŁADNIE akapity z trafieniem "review"
     (akapit "block" oraz akapit czysty są pominięte) — ten sam zbiór co routed E1,
  2. ReviewSegment niesie poprawne pola (file/line/hit_ids) z manifestu,
  3. run_stage2 z atrapą StubJudgeEngine na manifeście z review daje gate == "FAIL"
     (bramka surowa: jeden "rewrite" zamyka całość),
  4. run_stage2 na manifeście bez review (sam block) daje gate == "PASS" i judged == 0,
  5. werdykt atrapy dla segmentu review to "rewrite", a atrybucja silnika to "stub",
  6. spójność z E1: zbiór segmentów runnera == akapity routed liczone przez metrics
     (jedno źródło prawdy „co idzie do Stage 2").

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import metrics      # noqa: E402
import runner       # noqa: E402
from engines import StubJudgeEngine, ReviewSegment, Judgement  # noqa: E402


# --- Mini-dokument: 3 akapity rozdzielone pustą linią (jak w check_metrics) ---
# Akapit 1 (linia 1): trafienie review  -> osądzany (rewrite)
# Akapit 2 (linia 3): trafienie block    -> NIE osądzany (block zamyka linter)
# Akapit 3 (linia 5): czysty             -> NIE osądzany
DOC = (
    "Pierwszy akapit ma trafienie review tutaj.\n"   # linia 1
    "\n"                                              # linia 2
    "Drugi akapit zawiera twardy bloker block.\n"     # linia 3
    "\n"                                              # linia 4
    "Trzeci akapit jest zupełnie czysty bez niczego." # linia 5
)

WORDS_TOTAL = len(metrics._WORD_RE.findall(DOC))

MANIFEST_REVIEW = {
    "hits": [
        {"file": "doc.txt", "line": 1, "id": "PL-SIGN", "klasa": "review", "match": "review"},
        {"file": "doc.txt", "line": 3, "id": "EN-DASH", "klasa": "block", "match": "block"},
    ],
    "summary": [
        {"file": "doc.txt", "words": WORDS_TOTAL, "hits": 2, "emdash_max": 0,
         "density": 0.0, "blockers": 1, "verdict": "FAIL"},
    ],
}

# Manifest bez trafień review (sam block) — nic nie idzie do Stage 2.
MANIFEST_CLEAN = {
    "hits": [
        {"file": "doc.txt", "line": 3, "id": "EN-DASH", "klasa": "block", "match": "block"},
    ],
    "summary": [
        {"file": "doc.txt", "words": WORDS_TOTAL, "hits": 1, "emdash_max": 0,
         "density": 0.0, "blockers": 1, "verdict": "FAIL"},
    ],
}


def _reader_ok(path):
    if path == "doc.txt":
        return DOC
    raise OSError(f"nieoczekiwana ścieżka: {path}")


def main():
    fails = []

    # --- 1+2: selekcja — tylko akapit review ---
    segs = runner.select_review_segments(MANIFEST_REVIEW, file_reader=_reader_ok)
    if len(segs) != 1:
        fails.append(f"select_review_segments: oczekiwano 1 segmentu (akapit review), jest {len(segs)}")
    else:
        seg = segs[0]
        if not isinstance(seg, ReviewSegment):
            fails.append(f"segment nie jest ReviewSegment, jest {type(seg).__name__}")
        if seg.file != "doc.txt" or seg.line != 1:
            fails.append(f"segment: file/line rozjazd: file={seg.file!r} line={seg.line}")
        if seg.hit_ids() != ["PL-SIGN"]:
            fails.append(f"segment.hit_ids: oczekiwano ['PL-SIGN'], jest {seg.hit_ids()}")
        if "review" not in seg.text:
            fails.append(f"segment.text nie zawiera akapitu review: {seg.text!r}")

    # --- 6: spójność z E1 (to samo „co idzie do Stage 2") ---
    e1 = metrics.reduction_from_manifest(MANIFEST_REVIEW, file_reader=_reader_ok)
    if e1["routed_segments"] != len(segs):
        fails.append(f"spójność E1: routed_segments={e1['routed_segments']} != len(segs)={len(segs)}")

    # --- 3+5: run_stage2 z atrapą na review => gate FAIL, verdict rewrite, engine stub ---
    res = runner.run_stage2(MANIFEST_REVIEW, engine=StubJudgeEngine(), file_reader=_reader_ok)
    if res["gate"] != "FAIL":
        fails.append(f"gate (review): oczekiwano FAIL, jest {res['gate']!r}")
    if res["judged"] != 1 or res["rewrite"] != 1 or res["pass"] != 0:
        fails.append(f"agregacja (review): judged/rewrite/pass rozjazd: {res['judged']}/{res['rewrite']}/{res['pass']}")
    if res["engine"] != "stub":
        fails.append(f"atrybucja silnika: oczekiwano 'stub', jest {res['engine']!r}")
    if res["segments"] and res["segments"][0]["verdict"] != "rewrite":
        fails.append(f"verdict atrapy (review): oczekiwano 'rewrite', jest {res['segments'][0]['verdict']!r}")

    # --- 4: run_stage2 na czystym (sam block) => gate PASS, judged 0 ---
    res_clean = runner.run_stage2(MANIFEST_CLEAN, engine=StubJudgeEngine(), file_reader=_reader_ok)
    if res_clean["gate"] != "PASS":
        fails.append(f"gate (clean): oczekiwano PASS, jest {res_clean['gate']!r}")
    if res_clean["judged"] != 0:
        fails.append(f"judged (clean): oczekiwano 0, jest {res_clean['judged']}")

    # --- kontrola interfejsu: Judgement waliduje verdict ---
    try:
        Judgement(verdict="maybe", notes="x", engine="stub")
        fails.append("Judgement: zaakceptował niedozwolony verdict 'maybe'")
    except ValueError:
        pass

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)

    print("OK   runner Stage 2 (G1): selekcja=tylko review (block+czysty pominięte), "
          "bramka FAIL na rewrite / PASS na czystym, atrapa deterministyczna, spójność z E1.")


if __name__ == "__main__":
    main()
