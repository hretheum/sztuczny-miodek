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

Instrumentacja E3 (wspólny strumień JSONL z D4):
  7. run_stage2 z log_path dopisuje wpisy kind="stage2_run" do logu (per trafienie review),
     read_stage2_runs zwraca tylko te wpisy, z poprawnym mapowaniem (verdict rewrite→reject,
     id/fragment/engine/stage2_verdict/ts) i stałym ts ze wstrzykniętego ts_provider,
  8. wpisy E3 współistnieją z ręcznym wpisem D4 w jednym logu: read_decisions widzi oba,
     a filtr po kind rozdziela strumienie bez kolizji (D4 bez kind, E3 z kind="stage2_run"),
  9. bez log_path (None) run_stage2 NIC nie dopisuje (zachowanie G1 nietknięte).

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from miodek import metrics      # noqa: E402
from miodek import runner       # noqa: E402
from miodek import decision_log  # noqa: E402
from miodek.engines import StubJudgeEngine, ReviewSegment, Judgement  # noqa: E402


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

    # --- 7+8+9: instrumentacja E3 — wspólny strumień JSONL z D4 ---
    FIXED_TS = "2026-06-23T12:00:00Z"
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "decisions.jsonl")

        # 8: najpierw ręczny wpis D4 (bez pola kind) — symuluje istniejący log operatora.
        decision_log.append_decision(
            {"ts": "2026-06-23T09:00:00Z", "verdict": "reject", "id": "EN-CLICHE",
             "fragment": "robust", "klasa": "review"},
            path=log,
        )

        # 7: run_stage2 z log_path + stały ts_provider → dopisanie wpisów stage2_run.
        res_log = runner.run_stage2(
            MANIFEST_REVIEW, engine=StubJudgeEngine(), file_reader=_reader_ok,
            log_path=log, ts_provider=lambda: FIXED_TS,
        )
        if res_log["gate"] != "FAIL":
            fails.append(f"E3 run_stage2 z log: gate oczekiwano FAIL, jest {res_log['gate']!r}")

        runs = runner.read_stage2_runs(log)
        # MANIFEST_REVIEW ma 1 segment review z 1 trafieniem (PL-SIGN) → dokładnie 1 wpis E3.
        if len(runs) != 1:
            fails.append(f"E3 read_stage2_runs: oczekiwano 1 wpisu stage2_run, jest {len(runs)}")
        else:
            r = runs[0]
            if r.get("kind") != "stage2_run":
                fails.append(f"E3 wpis: kind oczekiwano 'stage2_run', jest {r.get('kind')!r}")
            if r.get("verdict") != "reject":
                fails.append(f"E3 mapowanie verdict: rewrite→reject, jest {r.get('verdict')!r}")
            if r.get("stage2_verdict") != "rewrite":
                fails.append(f"E3 stage2_verdict: oczekiwano 'rewrite', jest {r.get('stage2_verdict')!r}")
            if r.get("id") != "PL-SIGN":
                fails.append(f"E3 id: oczekiwano 'PL-SIGN', jest {r.get('id')!r}")
            if r.get("fragment") != "review":
                fails.append(f"E3 fragment (=match): oczekiwano 'review', jest {r.get('fragment')!r}")
            if r.get("engine") != "stub":
                fails.append(f"E3 engine: oczekiwano 'stub', jest {r.get('engine')!r}")
            if r.get("ts") != FIXED_TS:
                fails.append(f"E3 ts (ze wstrzykniętego ts_provider): oczekiwano {FIXED_TS!r}, jest {r.get('ts')!r}")

        # 8: oba strumienie w jednym logu — read_decisions widzi D4 + E3, filtr po kind rozdziela.
        all_entries = decision_log.read_decisions(log)
        if len(all_entries) != 2:
            fails.append(f"E3 wspólny strumień: oczekiwano 2 wpisów łącznie (D4+E3), jest {len(all_entries)}")
        d4_only = [w for w in all_entries if w.get("kind") is None]
        if len(d4_only) != 1 or d4_only[0].get("id") != "EN-CLICHE":
            fails.append(f"E3 filtr: wpis D4 (bez kind) zgubiony lub zniekształcony: {d4_only}")

        # 9: bez log_path nic nie dopisuje do logu (zachowanie G1 nietknięte).
        before = len(decision_log.read_decisions(log))
        runner.run_stage2(MANIFEST_REVIEW, engine=StubJudgeEngine(), file_reader=_reader_ok)
        after = len(decision_log.read_decisions(log))
        if before != after:
            fails.append(f"E3 bez log_path: log nie powinien rosnąć ({before} → {after})")

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)

    print("OK   runner Stage 2 (G1/E3): selekcja=tylko review (block+czysty pominięte), "
          "bramka FAIL na rewrite / PASS na czystym, atrapa deterministyczna, spójność z E1; "
          "instrumentacja E3: wpisy stage2_run we wspólnym strumieniu JSONL z D4 (filtr po kind).")


if __name__ == "__main__":
    main()
