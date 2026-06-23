#!/usr/bin/env python3
"""
corrector.py — agent KOREKTOR z pętlą audyt → poprawka → ponowny audyt do PASS (Epik G, G2).

Dotąd narzędzie tylko WYTYKAŁO manieryzm (Stage 1 linter + Stage 2 osąd). G2 zamyka pętlę:
narzędzie samo DOPROWADZA tekst do czysta. Jedna iteracja to:

  1. AUDYT     — Stage 1 (linter → manifest) + Stage 2 (runner.run_stage2: osąd silnika na
                 segmentach review, bramka „PASS z uwagami to NIE PASS").
  2. POPRAWKA  — dla każdego segmentu z werdyktem „rewrite" silnik PRZEPISUJE sporny akapit
                 (engine.rewrite). STRAŻNIK REGRESJI (KAN-223): po przepisaniu tani audyt Stage 1
                 obu wersji segmentu; poprawkę, która POGARSZA (więcej trafień lub nowy bloker),
                 ODRZUCAMY (zostaje oryginał, brak postępu dla segmentu) — chroni zbieżność na
                 żywym modelu, który przy przepisaniu dokłada nowy manieryzm. Tylko nie-pogarszające
                 poprawki stają się edycjami (adapter.Edit).
  3. ZŁOŻENIE  — zapis zwrotny przez adapter (OutputAdapter.write_back / apply_edits_to_text),
                 NIE reimplementujemy składania.
  4. PONOWNY AUDYT — kolejna iteracja na poprawionym tekście.

WARUNKI STOP (trzy, dokładnie):
  - PASS            — gate Stage 2 == "PASS" (brak segmentów rewrite). reason = "pass".
  - brak postępu    — żaden rewrite nie zmienił tekstu w tej iteracji (poprawione == 0). Ochrona
                      przed pętlą nieskończoną. reason = "brak postępu".
  - limit iteracji  — wyczerpany `max_iter` (domyślnie 4). reason = "limit iteracji".

WYMIENNY SILNIK: pętla zna TYLKO `engine.judge` i `engine.rewrite`. Atrapa do testów
(`engines.StubRewriteEngine`, offline), realny model (OpenAICompat/Ollama) wpina się BEZ zmiany
pętli — przez `build_corrector_engine` (reużywa runner.build_engine_from_config; dla configu „stub"
podmienia atrapę osądzającą na atrapę korektora, bo ta umie rewrite).

ZERO-DEP (stdlib). Audyt jest WSTRZYKIWALNY (`audit_fn`): produkcyjny pisze tekst do pliku
tymczasowego i woła linter (offline, bez sieci), test podaje audyt w pamięci. Reużycie:
runner.run_stage2 / run_stage2_managed (auto-offload poda dla silników zdalnych), adapter
(segmentacja + zapis zwrotny), ai_linter (segmentacja, wybór adaptera, progi/słownik).

MAPOWANIE segment → Edit (wierność): `select_review_segments` zwraca ReviewSegment bez offsetów.
Wiążemy go z akapitem `doc.paragraphs()` po (line, text) — oba pochodzą z TEJ SAMEJ segmentacji
adaptera, więc są identyczne. Stąd Edit(para.start, para.end, nowy_tekst). Składa write_back.
"""

import argparse
import os
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import adapter            # noqa: E402  (Edit, NormalizedDoc, write_back, apply_edits_to_text)
import ai_linter          # noqa: E402  (_select_adapter, scan_file, compile_markers, progi/słownik)
import config             # noqa: E402  (CONFIG_PATH — sekcja stage2 / lifecycle)
import engines            # noqa: E402  (StubRewriteEngine — atrapa korektora)
import runner             # noqa: E402  (run_stage2, run_stage2_managed, build_engine_from_config,
                          #              select_review_segments)

# Domyślny limit iteracji pętli korektora. Konfigurowalny: argument correct_document(max_iter=...)
# oraz CLI --max-iter; CLI bez flagi bierze stage2.max_iter z config.json (fallback ta stała).
DEFAULT_MAX_ITER = 4


@dataclass
class CorrectionResult:
    """Wynik pętli korektora.

    - text       : finalny tekst (po wszystkich naniesionych poprawkach; przy zero iteracjach =
                   tekst wejściowy bez zmian).
    - iterations : liczba wykonanych iteracji pętli (0, gdy od razu PASS bez segmentów rewrite).
    - passed     : czy osiągnięto PASS (gate Stage 2 == "PASS").
    - reason     : "pass" | "brak postępu" | "limit iteracji".
    - trace      : ślad per iteracja: [{"iteracja": i, "poprawione": k}].
    """
    text: str
    iterations: int
    passed: bool
    reason: str
    trace: List[dict] = field(default_factory=list)


# Typ audytu: (text, file_path) -> (manifest_dict, NormalizedDoc).
AuditFn = Callable[[str, str], Tuple[dict, adapter.NormalizedDoc]]


def make_default_audit(lang="both", profile=None, dict_path=None) -> AuditFn:
    """Buduje produkcyjny `audit_fn`: Stage 1 linter na tekście w pamięci → (manifest, doc).

    Tekst zapisujemy do pliku TYMCZASOWEGO z tym samym rozszerzeniem co `file_path` (żeby
    ai_linter wybrał ten sam adapter), wołamy `scan_file`, po czym podmieniamy ścieżkę w hitach
    i summary na ORYGINALNĄ `file_path` (spójny manifest). `doc` liczymy z `_select_adapter(
    file_path).normalize(text)` — wierna segmentacja z offsetami dla mapowania Edit.

    Profil progów i słownik domenowy ustawiamy w ai_linter (jak robi to jego main), żeby audyt
    korektora był spójny z CLI lintera. ZERO sieci — tylko dysk lokalny (plik tymczasowy)."""

    def _audit(text: str, file_path: str) -> Tuple[dict, adapter.NormalizedDoc]:
        # Profil progów (D1) i słownik (D2) — spójnie z ai_linter.main.
        if profile is not None:
            ai_linter.THRESHOLDS = config.load_thresholds(profile)
        if dict_path is not None:
            import dictionary
            ai_linter.DICTIONARY = dictionary.load_dictionary(dict_path)

        compiled = ai_linter.compile_markers(lang)
        ext = os.path.splitext(file_path)[1] or ".txt"
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=ext, delete=False, encoding="utf-8"
        )
        try:
            tmp.write(text)
            tmp.close()
            hits, summary = ai_linter.scan_file(tmp.name, compiled, lang)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

        manifest = {
            "hits": [
                {"file": file_path, "line": h.line, "id": h.mid,
                 "klasa": h.klasa, "match": h.match_fragment}
                for h in hits
            ],
            "summary": [{
                "file": file_path, "words": summary.words, "hits": summary.hits,
                "emdash_max": summary.emdash_max, "density": summary.density,
                "blockers": summary.blockers, "verdict": summary.verdict,
            }],
        }
        doc = ai_linter._select_adapter(file_path).normalize(text)
        return manifest, doc

    return _audit


def _count_hits_blockers(manifest: dict) -> Tuple[int, int]:
    """Z manifestu Stage 1 zwraca (liczba_trafień, liczba_blokerów).

    Strażnik regresji (KAN-223) liczy WSZYSTKIE trafienia (nie tylko review) — nowy manieryzm po
    przepisaniu (np. dołożona półpauza, antyteza serią) bywa blokerem spoza klasy review. Blokery
    z summary[0].blockers (lista). Manifest pusty/bez pól → (0, 0) zachowawczo."""
    hits = manifest.get("hits", []) or []
    summary = manifest.get("summary", []) or []
    blockers = summary[0].get("blockers", []) if summary else []
    return len(hits), len(blockers or [])


def _para_offsets_for_segment(doc: adapter.NormalizedDoc, review_seg) -> Optional[Tuple[int, int]]:
    """Mapuje ReviewSegment (file/seg_index/line/text/hits — bez offsetów) na zakres akapitu w doc.

    Wiążemy po (line, text): akapit `doc.paragraphs()` o tej samej linii początku i tej samej
    treści co segment review. Oba pochodzą z TEJ SAMEJ segmentacji adaptera (review_paragraphs_for_file
    używa `_select_adapter(path).normalize(text).paragraphs()`), więc są identyczne. Zwraca
    (start, end) w doc.text albo None, gdy nie da się przypiąć (np. fallback nieczytelnego pliku:
    text pusty) — wtedy korektor pomija ten segment (brak postępu, świadomy STOP)."""
    paras = doc.paragraphs()
    # 1) dokładne dopasowanie (line + text).
    for p in paras:
        if p.line == review_seg.line and p.text == review_seg.text:
            return (p.start, p.end)
    # 2) zapas: sam text (gdy numer linii się rozjechał, ale treść jednoznaczna).
    matches = [p for p in paras if p.text == review_seg.text and review_seg.text]
    if len(matches) == 1:
        return (matches[0].start, matches[0].end)
    return None


def correct_document(text, *, file_path, engine, audit_fn=None, max_iter=DEFAULT_MAX_ITER,
                     stage2_fn=None) -> CorrectionResult:
    """Pętla korektora: audyt → poprawka → ponowny audyt, do PASS / braku postępu / limitu.

    Argumenty:
        text       — tekst wejściowy (proza .md/.txt).
        file_path  — ścieżka (decyduje o adapterze i rozszerzeniu audytu; plik NIE musi istnieć).
        engine     — wymienialny silnik (.judge + .rewrite). Atrapa: engines.StubRewriteEngine().
        audit_fn   — (text, file_path) -> (manifest, doc). None → make_default_audit() (offline,
                     przez plik tymczasowy). Test podaje audyt w pamięci.
        max_iter   — limit iteracji (domyślnie 4).
        stage2_fn  — funkcja osądu Stage 2 (manifest, engine, file_reader) -> wynik run_stage2.
                     None → runner.run_stage2 (czysty). CLI podaje wrapper run_stage2_managed
                     (auto-offload poda dla silników zdalnych).

    Zwraca CorrectionResult. NIE dotyka dysku poza audit_fn (który dla produkcji pisze tymczasowy
    plik); ZERO sieci w ścieżce atrapy."""
    if audit_fn is None:
        audit_fn = make_default_audit()
    if stage2_fn is None:
        stage2_fn = runner.run_stage2

    current = text
    trace: List[dict] = []

    for i in range(max_iter):
        manifest, doc = audit_fn(current, file_path)
        # Audyt Stage 2 na BIEŻĄCYM tekście (file_reader zwraca current, nie czyta dysku).
        result = stage2_fn(manifest, engine, file_reader=lambda _p, _t=current: _t)

        if result["gate"] == "PASS":
            return CorrectionResult(text=current, iterations=i, passed=True,
                                    reason="pass", trace=trace)

        # Zbierz segmenty review (z offsetami przez doc) i przepisz te z werdyktem rewrite.
        review_segments = runner.select_review_segments(
            manifest, file_reader=lambda _p, _t=current: _t
        )
        edits: List[adapter.Edit] = []
        poprawione = 0
        # KAN-223 review (drobna): memoizacja audytu ORYGINAŁU segmentu po treści. audit_fn(seg.text)
        # jest niezmienny w obrębie iteracji (a często też między iteracjami dla tych samych akapitów),
        # a make_default_audit pisze/kasuje plik tymczasowy. Cache tnie I/O bez zmiany logiki.
        baseline_audit_cache: dict = {}

        def _audit_baseline(seg_text):
            cached = baseline_audit_cache.get(seg_text)
            if cached is None:
                cached = audit_fn(seg_text, file_path)
                baseline_audit_cache[seg_text] = cached
            return cached

        for seg in review_segments:
            j = engine.judge(seg)
            if j.verdict != "rewrite":
                continue
            new_text = engine.rewrite(seg, j)
            if new_text == seg.text:
                continue  # silnik nic nie zmienił dla tego segmentu
            # STRAŻNIK REGRESJI (KAN-223): tani audyt Stage 1 obu wersji SAMEGO segmentu (offline,
            # bez sieci, bez LLM). Realny model bywa „leczy chorobę, dokłada gorączkę”: przepisując
            # akapit wprowadza NOWY manieryzm (półpauza, druga triada), przez co pętla się rozjeżdża.
            # Akceptujemy tylko poprawki NIE-pogarszające: nie więcej trafień i nie nowy bloker.
            old_m, _old_doc = _audit_baseline(seg.text)
            new_m, _new_doc = audit_fn(new_text, file_path)
            old_hits, old_block = _count_hits_blockers(old_m)
            new_hits, new_block = _count_hits_blockers(new_m)
            if new_hits > old_hits or new_block > old_block:
                continue  # poprawka POGARSZA → odrzuć (zostaw oryginał, brak postępu dla segmentu)
            offsets = _para_offsets_for_segment(doc, seg)
            if offsets is None:
                continue  # nie da się przypiąć do akapitu → pomiń (chroni wierność)
            start, end = offsets
            edits.append(adapter.Edit(start, end, new_text))
            poprawione += 1

        trace.append({"iteracja": i + 1, "poprawione": poprawione})

        if poprawione == 0:
            # Żadna poprawka nie ruszyła tekstu → brak postępu (ochrona przed pętlą nieskończoną).
            return CorrectionResult(text=current, iterations=i + 1, passed=False,
                                    reason="brak postępu", trace=trace)

        out_adapter = ai_linter._select_adapter(file_path)
        if not isinstance(out_adapter, adapter.OutputAdapter):
            # Format strukturalny (HTML) nie ma zapisu zwrotnego (known limitation source_map).
            raise ValueError(
                f"brak zapisu zwrotnego dla formatu strukturalnego ({file_path}); "
                "korektor obsługuje .md i .txt"
            )
        current = out_adapter.write_back(doc, edits)

    # Wyczerpany limit: sprawdź czy mimo to ostatni stan jest PASS.
    manifest, _doc = audit_fn(current, file_path)
    final = stage2_fn(manifest, engine, file_reader=lambda _p, _t=current: _t)
    passed = final["gate"] == "PASS"
    return CorrectionResult(
        text=current, iterations=max_iter, passed=passed,
        reason="pass" if passed else "limit iteracji", trace=trace,
    )


def build_corrector_engine(name=None, config_path=config.CONFIG_PATH):
    """Buduje silnik korektora: reużywa runner.build_engine_from_config, ale dla atrapy osądzającej
    (config „stub") podmienia ją na atrapę KOREKTORA (StubRewriteEngine), która umie rewrite.

    Realne silniki (openai/ollama) mają własny rewrite — przechodzą bez zmian. Dzięki temu domyślny
    config (stub) daje OFFLINE korektor, który zbiega, bez ruszania fabryki silnika w runnerze
    (G1 nietknięty)."""
    eng = runner.build_engine_from_config(name=name, config_path=config_path)
    # Czysta atrapa osądzająca (StubJudgeEngine, NIE jej podklasa) nie umie rewrite → podmień.
    if type(eng) is engines.StubJudgeEngine:
        return engines.StubRewriteEngine()
    return eng


def _make_managed_stage2(config_path):
    """Wrapper Stage 2 dla CLI: run_stage2_managed (auto-offload poda RunPod dla silników zdalnych).

    Podpina config_path; sygnatura zgodna ze stage2_fn (manifest, engine, file_reader)."""
    def _fn(manifest, engine, file_reader):
        return runner.run_stage2_managed(
            manifest, engine=engine, config_path=config_path, file_reader=file_reader
        )
    return _fn


def _main(argv=None):
    """CLI: corrector.py --file PLIK [--lang both] [--profile P] [--dict D] [--max-iter N]
    [--engine stub|openai|ollama] [--config ...] [--in-place].

    Audytuje i poprawia plik. Na stdout: finalny tekst, potem raport (iteracje, passed, reason,
    ślad). --in-place zapisuje wynik z powrotem do pliku (domyślnie tylko wypisuje). Exit 0 gdy
    passed, 1 gdy nie osiągnięto PASS."""
    ap = argparse.ArgumentParser(
        description="Korektor (G2): pętla audyt → poprawka → ponowny audyt do PASS. Domyślnie "
                    "silnik z config.json (stub = offline)."
    )
    ap.add_argument("--file", required=True, help="Ścieżka pliku prozy (.md/.txt) do poprawy.")
    ap.add_argument("--lang", default="both", choices=["pl", "en", "both"],
                    help="Język markerów (domyślnie both).")
    ap.add_argument("--profile", default=None, help="Profil progów z config.json (opcjonalnie).")
    ap.add_argument("--dict", default=None, dest="dict_path",
                    help="Słownik domenowy (opcjonalnie).")
    ap.add_argument("--max-iter", type=int, default=None,
                    help=f"Limit iteracji pętli. Domyślnie stage2.max_iter z config.json "
                         f"(fallback {DEFAULT_MAX_ITER}).")
    ap.add_argument("--engine", default=None, choices=("stub", "openai", "ollama"),
                    help="Silnik. Domyślnie z config.json (stub = offline). openai/ollama wymagają "
                         "sieci — świadomy wybór operatora.")
    ap.add_argument("--config", default=config.CONFIG_PATH,
                    help="Ścieżka do config.json. Domyślnie config repo.")
    ap.add_argument("--in-place", action="store_true",
                    help="Zapisz poprawiony tekst z powrotem do pliku (domyślnie tylko wypisz).")
    args = ap.parse_args(argv)

    with open(args.file, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    max_iter = args.max_iter
    if max_iter is None:
        cfg = config.load_stage2(args.config)
        max_iter = int(cfg.get("max_iter", DEFAULT_MAX_ITER))

    engine = build_corrector_engine(name=args.engine, config_path=args.config)
    audit_fn = make_default_audit(lang=args.lang, profile=args.profile, dict_path=args.dict_path)
    stage2_fn = _make_managed_stage2(args.config)

    res = correct_document(
        text, file_path=args.file, engine=engine,
        audit_fn=audit_fn, max_iter=max_iter, stage2_fn=stage2_fn,
    )

    if args.in_place:
        with open(args.file, "w", encoding="utf-8") as f:
            f.write(res.text)

    sys.stdout.write(res.text)
    if not res.text.endswith("\n"):
        sys.stdout.write("\n")
    print("\n== RAPORT KOREKTORA ==", file=sys.stderr)
    print(f"silnik: {getattr(engine, 'name', '?')} | iteracje: {res.iterations} | "
          f"PASS: {res.passed} | powód: {res.reason}", file=sys.stderr)
    for t in res.trace:
        print(f"  iteracja {t['iteracja']}: poprawiono {t['poprawione']} segment(ów)",
              file=sys.stderr)
    if args.in_place:
        print(f"  zapisano do {args.file}", file=sys.stderr)

    sys.exit(0 if res.passed else 1)


if __name__ == "__main__":
    _main()
