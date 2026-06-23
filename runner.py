#!/usr/bin/env python3
"""
runner.py — runner Stage 2: orkiestracja osądu modelu na wycinku z manifestu (Epik G, G1).

FUNDAMENT ORKIESTRACJI. Bierze gotowy MANIFEST lintera (Stage 1), wybiera segmenty (akapity)
zawierające trafienia klasy "review", woła WYMIENIALNY silnik osądu (engines.JudgeEngine) i agreguje
werdykt według bramki "PASS z uwagami to NIE PASS".

Granica wymienialności: runner zna TYLKO `JudgeEngine.judge`. Podmiana silnika (atrapa → lokalny
model → API) = inny argument `engine`, ZERO zmian w runnerze. Domyślny silnik to atrapa
`StubJudgeEngine` — deterministyczna, bez LLM i bez sieci (rdzeń jest ZERO-DEP, stdlib).

JEDNO ŹRÓDŁO PRAWDY „co idzie do Stage 2": `select_review_segments` opiera się na tej samej funkcji
`metrics.review_paragraphs_for_file`, której E1 używa do liczenia `routed_words`. Dzięki temu zbiór
segmentów osądzanych przez runner jest DOKŁADNIE tym samym zbiorem, który E1 raportuje jako
routowany do modelu. Mapowanie linii i wybór adaptera pochodzą z `ai_linter` (przez metrics), nie są
reimplementowane.

BRAMKA (surowa): gate == "FAIL", gdy jakikolwiek osąd ma verdict == "rewrite". gate == "PASS"
tylko gdy wszystkie osądy to "pass" (lub brak segmentów review). To realizacja zasady „PASS
z uwagami to NIE PASS": jedno trafienie wymagające ruchu zamyka całość. Twarde blokery (klasa
"block") linter zamyka sam na Stage 1 — do Stage 2 nie docierają, więc runner ich nie ocenia.

ROZSZERZALNOŚĆ (E2/E3): API zaprojektowane tak, by dołożyć instrumentację (E3: zapis każdego
osądu do strumienia decyzji) i atrybucję (E2) BEZ przeróbki rdzenia. Parametry-haki `log_path`
i `ts_provider` są przyjmowane już teraz; ich obsługę (zapis JSONL) dokłada E3 w jednym miejscu
(`_emit_stage2_run`), nie ruszając selekcji ani bramki.
"""

import json
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import metrics  # noqa: E402  (review_paragraphs_for_file — jedno źródło prawdy selekcji)
from engines import JudgeEngine, ReviewSegment, StubJudgeEngine  # noqa: E402


def select_review_segments(manifest, file_reader=metrics._default_file_reader):
    """Wybiera z manifestu segmenty (akapity) do osądu Stage 2.

    Zwraca listę `engines.ReviewSegment` — dokładnie te akapity, które E1 liczy jako routed_words
    (wspólna funkcja `metrics.review_paragraphs_for_file`). Akapity z samym trafieniem "block"
    oraz akapity czyste NIE trafiają tu.

    Kolejność: pliki w kolejności z manifestu["summary"], akapity w kolejności dokumentu.

    Wariant awaryjny (plik nieczytelny, a ma trafienia review): tworzony jest jeden ReviewSegment
    zastępczy obejmujący całość trafień pliku (text pusty, seg_index 0) — spójnie z fallbackiem E1,
    który wtedy traktuje cały plik jako routed. Dzięki temu runner nie gubi trafień, których nie da
    się przypiąć do akapitu.
    """
    hits = manifest.get("hits", [])
    summaries = manifest.get("summary", [])

    review_by_file = {}
    for h in hits:
        if h.get("klasa") == "review":
            review_by_file.setdefault(h.get("file"), []).append(h)

    segments = []
    for s in summaries:
        fpath = s.get("file")
        file_reviews = review_by_file.get(fpath, [])
        if not file_reviews:
            continue

        mapped = metrics.review_paragraphs_for_file(fpath, file_reviews, file_reader=file_reader)
        if mapped is None:
            # Fallback: pliku nie da się odczytać — jeden segment zastępczy z całością trafień.
            line = min((h.get("line", 1) for h in file_reviews), default=1)
            segments.append(ReviewSegment(
                file=fpath, seg_index=0, line=line, text="", hits=list(file_reviews),
            ))
            continue

        for idx, (seg, seg_hits) in enumerate(mapped):
            segments.append(ReviewSegment(
                file=fpath, seg_index=idx, line=seg.line, text=seg.text, hits=list(seg_hits),
            ))

    return segments


def _emit_stage2_run(judgement, segment, hit, log_path, ts_provider):
    """Hak instrumentacji E3 (zapis pojedynczego osądu do strumienia decyzji).

    W G1 to NO-OP, dopóki `log_path` jest None. E3 podmienia implementację, by dopisywać wpis
    `kind="stage2_run"` przez `decision_log.append_decision`. Sygnatura jest stała, więc E3 nie
    rusza pętli `run_stage2`. Pozostawione tu świadomie jako pojedynczy punkt rozszerzenia.
    """
    return None


def run_stage2(manifest, engine: JudgeEngine = None, file_reader=metrics._default_file_reader,
               log_path=None, ts_provider=None):
    """Uruchamia Stage 2 na manifeście: selekcja review → osąd silnikiem → agregacja + bramka.

    Argumenty:
        manifest    — dict {"hits":[...], "summary":[...]} (kontrakt między etapami).
        engine      — wymienialny JudgeEngine; domyślnie atrapa StubJudgeEngine().
        file_reader — wstrzykiwalny czytnik treści (testy podają treść w pamięci, bez I/O).
        log_path    — (E3) ścieżka strumienia decyzji; w G1 nieużywana (hak rozszerzenia).
        ts_provider — (E3) dostawca znacznika czasu; w G1 nieużywany (hak rozszerzenia).

    Zwraca:
        {
          "segments": [{file, seg_index, line, verdict, engine, notes, hit_ids}],
          "judged": N,           # liczba osądzonych segmentów
          "rewrite": M,          # liczba werdyktów "rewrite"
          "pass": K,             # liczba werdyktów "pass"
          "engine": nazwa_silnika,
          "gate": "PASS" | "FAIL"  # FAIL, gdy jakikolwiek verdict == "rewrite" (bramka surowa)
        }
    """
    if engine is None:
        engine = StubJudgeEngine()

    segments = select_review_segments(manifest, file_reader=file_reader)

    out_segments = []
    n_rewrite = 0
    n_pass = 0
    for seg in segments:
        j = engine.judge(seg)
        if j.verdict == "rewrite":
            n_rewrite += 1
        else:
            n_pass += 1

        out_segments.append({
            "file": seg.file,
            "seg_index": seg.seg_index,
            "line": seg.line,
            "verdict": j.verdict,
            "engine": j.engine,
            "notes": j.notes,
            "hit_ids": seg.hit_ids(),
        })

        # Hak instrumentacji E3 (NO-OP w G1, dopóki log_path is None).
        if log_path is not None:
            for hit in seg.hits:
                _emit_stage2_run(j, seg, hit, log_path, ts_provider)

    gate = "FAIL" if n_rewrite > 0 else "PASS"

    return {
        "segments": out_segments,
        "judged": len(out_segments),
        "rewrite": n_rewrite,
        "pass": n_pass,
        "engine": engine.name,
        "gate": gate,
    }


def _load_manifest(path):
    """Wczytuje manifest z pliku JSON; '-' = stdin."""
    if path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _main(argv=None):
    """CLI: runner.py --manifest plik.json [--engine stub].

    Wypisuje raport + JSON; exit 1, gdy gate == "FAIL" (gate-owalne w CI/pre-publish)."""
    import argparse
    ap = argparse.ArgumentParser(
        description="Runner Stage 2: osąd modelu na segmentach review z manifestu (G1)."
    )
    ap.add_argument("--manifest", required=True, help="Ścieżka do manifestu JSON ('-' = stdin).")
    ap.add_argument("--engine", default="stub", choices=("stub",),
                    help="Silnik osądu (domyślnie atrapa 'stub'; realne silniki wpinają się w kodzie).")
    args = ap.parse_args(argv)

    manifest = _load_manifest(args.manifest)
    engine = StubJudgeEngine()  # jedyny zero-dep silnik dostępny z CLI
    result = run_stage2(manifest, engine=engine)

    print(f"Stage 2 (silnik: {result['engine']}): osądzono {result['judged']} segmentów review "
          f"→ rewrite {result['rewrite']}, pass {result['pass']} → BRAMKA: {result['gate']}")
    for seg in result["segments"]:
        ids = ", ".join(str(i) for i in seg["hit_ids"])
        print(f"  [{seg['verdict']:>7}] {seg['file']}:{seg['line']} ({ids}) — {seg['notes']}")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))

    sys.exit(1 if result["gate"] == "FAIL" else 0)


if __name__ == "__main__":
    _main()
