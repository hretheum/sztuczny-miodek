# Schemat runnera Stage 2 — kontrakt orkiestracji osądu (Epik G, G1)

Runner (`runner.py`) spina Stage 1 (linter, deterministyczny) ze Stage 2 (osąd modelu).
Granicą jest MANIFEST. Runner czyta manifest, wybiera segmenty klasy `review`, woła wymienialny
silnik osądu (`engines.JudgeEngine`) i stosuje bramkę. Rdzeń jest ZERO-DEP (biblioteka standardowa).

## Wejście: manifest lintera

Manifest produkuje `ai_linter --format json`:

```json
{ "hits":    [{ "file": "...", "line": 12, "id": "EN-CLICHE", "klasa": "review", "match": "robust" }],
  "summary": [{ "file": "...", "words": 320, "hits": 3, "emdash_max": 1,
                "density": 0.9, "blockers": 0, "verdict": "PASS" }] }
```

- `klasa == "review"` to pozycja do OSĄDU MODELU (Stage 2). Tylko te trafienia są routowane.
- `klasa == "block"` to twardy bloker — linter zamyka go sam na Stage 1, do runnera nie dociera.

## Selekcja segmentów: `select_review_segments(manifest, file_reader=...)`

Zwraca listę `ReviewSegment` — akapity zawierające co najmniej jedno trafienie `review`. Wybór
akapitów dzieli JEDNĄ funkcję z metrykami E1 (`metrics.review_paragraphs_for_file`), więc zbiór
osądzanych segmentów jest dokładnie tym, co E1 raportuje jako `routed_words`. Mapowanie linii na
akapity i wybór adaptera pochodzą z `ai_linter`, nie są reimplementowane.

Wariant awaryjny: gdy plik jest nieczytelny, a ma trafienia `review`, powstaje jeden segment
zastępczy z całością trafień pliku (spójnie z fallbackiem E1, który traktuje wtedy cały plik jako
routed). Runner nie gubi trafień.

## Interfejs silnika: `engines.JudgeEngine` (wymienialny)

```python
class JudgeEngine(ABC):
    name: str                                    # nazwa silnika (atrybucja E2/E3)
    def judge(self, segment: ReviewSegment) -> Judgement: ...
```

Runner zna TYLKO `name` i `judge`. Podmiana silnika (atrapa → lokalny model przez Ollama → API
przez OpenRouter) to inny argument `engine` do `run_stage2`, bez zmian w runnerze.

### `ReviewSegment` (jednostka routowana)

| Pole | Typ | Opis |
|---|---|---|
| `file` | string | ścieżka pliku źródłowego |
| `seg_index` | int | indeks akapitu w pliku (kolejność dokumentu) |
| `line` | int | 1-based linia początku akapitu (z `adapter.Segment.line`) |
| `text` | string | treść akapitu (`doc.text[seg.start:seg.end]`) |
| `hits` | list[dict] | trafienia `review` przypięte do akapitu (`id, line, klasa, match, file`) |

Metoda `hit_ids()` zwraca listę ID trafień w kolejności z manifestu.

### `Judgement` (werdykt dla jednego segmentu)

| Pole | Typ | Wartości | Opis |
|---|---|---|---|
| `verdict` | string | `pass` lub `rewrite` | werdykt osądu |
| `notes` | string | dowolny | uzasadnienie lub propozycja poprawki |
| `engine` | string | `= JudgeEngine.name` | atrybucja silnika |

### `StubJudgeEngine` (atrapa, domyślny silnik)

Deterministyczna, bez LLM i bez sieci. Reguła: segment z co najmniej jednym trafieniem `review`
daje `rewrite` z notatką wymieniającą ID trafień; segment bez trafień daje `pass`. To nie jest
ocena treści, lecz sygnał, że segment wpadł do Stage 2. Służy do testów potoku, do E3 i jako żywy
kontrakt. Realny silnik nadpisuje regułę faktyczną oceną modelu, zachowując sygnaturę `judge`.

## Bramka: `run_stage2(manifest, engine=..., file_reader=...) -> dict`

Zwraca:

```json
{ "segments": [{ "file": "...", "seg_index": 0, "line": 12, "verdict": "rewrite",
                 "engine": "stub", "notes": "...", "hit_ids": ["EN-CLICHE"] }],
  "judged": 1, "rewrite": 1, "pass": 0, "engine": "stub", "gate": "FAIL" }
```

Reguła bramki (surowa, „PASS z uwagami to NIE PASS"): `gate == "FAIL"`, gdy jakikolwiek osąd ma
`verdict == "rewrite"`. `gate == "PASS"` tylko gdy wszystkie osądy to `pass` lub brak segmentów
review. CLI `runner.py --manifest plik.json` zwraca exit 1 przy `gate == "FAIL"` (gate-owalne w CI).

## Instrumentacja E3 (wspólny strumień JSONL z D4) — ZREALIZOWANE

`run_stage2` przyjmuje haki `log_path` i `ts_provider`. Gdy `log_path` jest podana, dla każdego
trafienia review w osądzonym segmencie runner dopisuje wpis `kind="stage2_run"` przez
`decision_log.append_decision` — TEN SAM append-only JSONL co log decyzji D4 (reużycie warstwy
zapisu, brak duplikacji I/O). Selekcja i bramka pozostają nietknięte (instrumentacja w jednym
punkcie `_emit_stage2_run`). `log_path=None` (domyślnie) = brak zapisu, zachowanie G1 bez zmian.

- `ts_provider` — callable bez argumentów zwracający znacznik czasu (str ISO 8601 UTC). Domyślnie
  bieżąca chwila UTC; test podaje stały znacznik (determinizm).
- Mapowanie osądu na wpis: `verdict` D4 = `pass`→`accept`, `rewrite`→`reject`; `id`/`fragment` =
  `hit.id`/`hit.match`; pola dodatkowe `engine`, `stage2_verdict`, `stage2_notes`, `klasa`, `file`,
  `line`. Pełny schemat wpisu: `decision-log.schema.md` (sekcja „Wpis `stage2_run`").
- Odczyt: `runner.read_stage2_runs(log_path)` → tylko wpisy `kind=="stage2_run"` (filtr rozdziela
  strumień D4 + E3). E2 (atrybucja) czyta `hit_ids` segmentów z wyniku `run_stage2`.

Realny silnik (Bielik przez Ollama, API przez OpenRouter) wpina się przez `engines.JudgeEngine` bez
zmian w instrumentacji — logowanie działa dla każdego silnika (atrybucja po `engine.name`).

## Wybór silnika z configu (KAN-218)

Realne adaptery (`OpenAICompatEngine`, `OllamaEngine`) i ich kontrakt opisuje `engines.schema.md`.
Runner wybiera silnik fabryką `build_engine_from_config(name=None, config_path=...)`: `name=None` →
`stage2.engine` z `config.json` (fallback `stub`); `name` (CLI `--engine`) nadpisuje. CLI:
`runner.py --manifest plik.json [--engine stub|openai|ollama|routing] [--config config.json]`.
Domyślnie atrapa — realne silniki wybierane jawnie i wymagają sieci. `run_stage2` bez zmian (dostaje
gotowy silnik).

## Routing silnika (G3 — lejek kosztowy)

`build_engine_from_config` rozpoznaje też `engine="routing"`: buduje `RoutingJudgeEngine`, którego
`primary` i `appellate` powstają REKURENCYJNIE z `stage2.routing.{primary,appellate}` przez wydzieloną
`_build_single_engine(sub_cfg)` (refaktor: wspólne ciało dla stub/openai/ollama). Routing owija lekki
silnik (na masę) i mocny sędzia apelacyjny (na trudny margines) — kontrakt, polityka eskalacji,
rekurencja i ograniczenie wobec auto-offloadu poda (KAN-220) są w `engines.schema.md` (sekcja „Routing
silnika `RoutingJudgeEngine`"). `_build_single_engine` odrzuca `engine="routing"` (routing jest
jednopoziomowy). `run_stage2` i bramka pozostają nietknięte — routing to po prostu inny `JudgeEngine`.
