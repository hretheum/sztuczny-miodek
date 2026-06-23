# Schemat korektora: pętla audyt, poprawka, ponowny audyt do PASS (G2)

Agent korektor zamyka pętlę nad Stage 1 (linter) i Stage 2 (osąd modelu): zamiast tylko WYTYKAĆ
manieryzm, sam DOPROWADZA tekst do czysta. Moduł `corrector.py`. ZERO-DEP (stdlib), audyt
wstrzykiwalny (offline na atrapie, bez sieci).

Komplement do `engines.schema.md` (silnik + zdolność rewrite) i `runner.schema.md` (audyt Stage 2).

## Jedna iteracja pętli

1. AUDYT — `audit_fn(text, file_path) -> (manifest, doc)` (Stage 1 linter na bieżącym tekście) plus
   `run_stage2(manifest, engine, file_reader)` (Stage 2 osąd; bramka „PASS z uwagami to NIE PASS").
2. POPRAWKA — dla każdego segmentu z werdyktem `rewrite`: `engine.rewrite(segment, judgement) -> str`
   przepisuje sporny akapit. STRAŻNIK REGRESJI (KAN-223): po przepisaniu tani audyt Stage 1 obu
   wersji SAMEGO segmentu (`audit_fn(seg.text)` i `audit_fn(new_text)`, offline, bez sieci); poprawka
   POGARSZAJĄCA (więcej trafień LUB nowy bloker, ostre nierówności `new_hits > old_hits or new_block
   > old_block`) jest ODRZUCana — segment zostaje oryginałem, traktowany jak brak postępu. Tylko
   nie-pogarszająca zmiana ≠ oryginał staje się `adapter.Edit`. Liczone są WSZYSTKIE trafienia (nie
   tylko review), bo nowy manieryzm (np. dołożona półpauza) bywa blokerem spoza klasy review.
3. ZŁOŻENIE — `OutputAdapter.write_back(doc, edits) -> str` (PlainText/Markdown przez
   `apply_edits_to_text`). NIE reimplementujemy składania.
4. PONOWNY AUDYT — następna iteracja na poprawionym tekście.

## Warunki STOP (trzy)

| reason | warunek | passed |
|---|---|---|
| `pass` | gate Stage 2 == `PASS` (brak segmentów rewrite) | `True` |
| `brak postępu` | w iteracji żaden rewrite nie zmienił tekstu (`poprawione == 0`) — ochrona przed pętlą nieskończoną | `False` |
| `limit iteracji` | wyczerpany `max_iter` (domyślnie 4) bez PASS | `False` |

Po wyczerpaniu limitu pętla robi jeszcze jeden audyt: jeśli ostatni stan to PASS, `reason == "pass"`,
`passed == True` (zbieżność dokładnie w ostatniej iteracji nie jest karana).

Strażnik regresji a zbieżność: gdy żywy model dokłada manieryzm przy każdym przepisaniu, strażnik
odrzuca wszystkie pogarszające poprawki, więc `poprawione == 0` i pętla kończy „brak postępu” —
zamiast rozjeżdżać tekst do limitu. Granica jest ostra: zmiana NEUTRALNA (bez nowych trafień)
przechodzi, więc realny postęp bez zbieżności nadal trafia na „limit iteracji”.

## Kontrakt zwrotu — `CorrectionResult`

```
CorrectionResult(
    text: str,            # finalny tekst (zero iteracji => wejście bez zmian)
    iterations: int,      # liczba wykonanych iteracji (0 gdy od razu PASS)
    passed: bool,         # czy osiągnięto PASS
    reason: str,          # "pass" | "brak postępu" | "limit iteracji"
    trace: list[dict],    # [{"iteracja": i, "poprawione": k}, ...]
)
```

## Mapowanie segmentu na Edit (wierność)

`runner.select_review_segments(manifest)` zwraca `ReviewSegment(file, seg_index, line, text, hits)` —
BEZ offsetów. Mostek `_para_offsets_for_segment(doc, review_seg)` wiąże segment z akapitem
`doc.paragraphs()` po `(line, text)`: oba pochodzą z TEJ SAMEJ segmentacji adaptera
(`metrics.review_paragraphs_for_file` i `corrector.audit_fn` używają `ai_linter._select_adapter(
path).normalize(text).paragraphs()`), więc są identyczne. Stąd `Edit(para.start, para.end,
nowy_tekst)`. Nie da się przypiąć (np. fallback nieczytelnego pliku, `text` pusty) → segment
pominięty (chroni wierność; w skrajnym wypadku „brak postępu" zatrzymuje pętlę). Jeden Edit na
akapit (cały akapit zastępowany) — brak nakładania, `apply_edits_to_text` i tak waliduje.

## Wymienny silnik

Pętla zna TYLKO `engine.judge` i `engine.rewrite`. `corrector.build_corrector_engine(name,
config_path)` reużywa `runner.build_engine_from_config`; dla configu `stub` (atrapa osądzająca, bez
rewrite) podmienia ją na `engines.StubRewriteEngine` (atrapa korektora, deterministyczna, offline).
Realne silniki (`openai`/`ollama`) mają własny `rewrite` — przechodzą bez zmian. G1 (runner,
StubJudgeEngine) nietknięty.

## Audyt: produkcyjny vs testowy

- Produkcyjny: `make_default_audit(lang, profile, dict_path)` — pisze bieżący tekst do pliku
  TYMCZASOWEGO z rozszerzeniem `file_path` (ten sam adapter co linter), woła `ai_linter.scan_file`,
  podmienia ścieżkę w hitach/summary na oryginalną, liczy `doc` z `_select_adapter(path).normalize`.
  ZERO sieci — tylko dysk lokalny.
- Testowy: ten sam `make_default_audit` (offline) wstrzykiwany do `correct_document(audit_fn=...)`.
  Audyt Stage 2 dostaje `file_reader` zwracający bieżący tekst w pamięci (nie czyta dysku).

CLI używa `run_stage2_managed` (przez `stage2_fn`) → auto-offload poda RunPod dla silników zdalnych
(KAN-220). Atrapa/silnik lokalny: ścieżka identyczna jak `run_stage2` (NO-OP managed).

## Format strukturalny (HTML)

`StructuralAdapter` jest tylko `InputAdapter` (brak zapisu zwrotnego — known limitation `source_map`
po encjach, opisana w `adapter.py`). Korektor obsługuje `.md`/`.txt`; dla formatu bez `OutputAdapter`
podnosi jasny `ValueError` „brak zapisu zwrotnego dla formatu strukturalnego", nie psuje źródła.

## CLI

```
python3 corrector.py --file PLIK [--lang both] [--profile P] [--dict D]
        [--max-iter N] [--engine stub|openai|ollama] [--config ...] [--in-place]
```

- finalny tekst na stdout, raport (silnik, iteracje, PASS, reason, ślad) na stderr,
- `--max-iter` domyślnie `stage2.max_iter` z config.json (fallback 4),
- `--in-place` zapisuje wynik z powrotem do pliku (domyślnie tylko wypisuje),
- exit 0 gdy `passed`, 1 gdy nie osiągnięto PASS (gate-owalne),
- domyślny silnik z configu (stub = offline; openai/ollama wymagają sieci — świadomy wybór).

## Test offline

`tools/check_corrector.py` (wpięty do `tests/run_tests.sh`) weryfikuje na atrapie: zbieżność do PASS
(finalny tekst bez trafień review), czysty tekst → zero iteracji bez zmian, brak postępu (rewrite =
no-op → STOP), limit iteracji (postęp bez zbieżności → STOP po max_iter), zapis zwrotny wierny (tylko
sporny akapit zmieniony), kontrakt rewrite (domyślny no-op vs StubRewriteEngine vs StubJudgeEngine).

```bash
python3 tools/check_corrector.py
```
