# Metryki z manifestu — redukcja (E1) i atrybucja pracy (E2)

Miary ekonomii i obserwowalności liczone z **manifestu** lintera (Stage 1), bez kosztu tokenów i
bez wołania LLM. Moduł: `metrics.py`. ZERO-DEP (stdlib `re`, plus `ai_linter` dla segmentacji i
klasyfikacji warstw). CLI: `tools/measure_reduction.py` (E1), `tools/measure_attribution.py` (E2).
Gate: `tools/check_metrics.py` (obejmuje E1 i E2).

## Po co

Współczynnik redukcji mierzy, ile pracy linter zdjął z modelu: jaki udział treści wejścia trafia do
Stage 2 (osąd modelu), a jaki linter zamknął sam. Punkt odniesienia z praktyki autora po wprowadzeniu
lintera: **routed rzędu 4–5%** treści. To metryka rozdziału etapów (granicą jest manifest), więc liczy
się ją bez uruchamiania silnika osądu.

## Wejście: manifest (Stage 1)

Manifest JSON produkuje `ai_linter --format json`:

```json
{ "hits":    [{"file": "...", "line": 12, "id": "EN-CLICHE", "klasa": "review", "match": "robust"}],
  "summary": [{"file": "...", "words": 320, "hits": 7, "emdash_max": 1, "density": 2.1,
               "blockers": 0, "verdict": "PASS"}] }
```

- `klasa == "review"` — pozycja do OSĄDU MODELU (Stage 2). Liczy się jako routowana.
- `klasa == "block"` — twardy bloker; linter sam FAIL-uje, do Stage 2 NIE idzie, NIE jest routowany.
- `summary[i].words` — słowa pliku (już policzone: `len(re.findall(r"\w+", text))`).

## Definicja współczynnika redukcji (precyzyjna)

> **Treść routowana do modelu** = segmenty (AKAPITY) zawierające co najmniej jedno trafienie klasy
> `review`. Akapity z samym `block` i akapity czyste NIE są routowane.

```
routed_words     = Σ słów akapitów z ≥1 trafieniem klasy "review"   (per plik, sumowane)
total_words      = Σ summary[*].words
reduction_ratio  = 1 - routed_words / total_words      # udział treści, której model NIE tyka
routed_ratio     = routed_words / total_words           # = "hit rate", odniesienie 0.04–0.05
```

Inwariant: `reduction_ratio + routed_ratio == 1.0` (gdy `total_words > 0`; przy 0 słów oba = 0.0).

**Liczbą główną są słowa** (porównywalne z `summary.words` i z odniesieniem 4–5%). Segmenty
raportowane pomocniczo: `routed_segments / total_segments`.

## Mapowanie trafień na akapity (ta sama segmentacja co linter)

Mapowanie nie jest zgadywane — używa adaptera lintera:

1. adapter wybrany jak w linterze: `ai_linter._select_adapter(path)` (`.md` → Markdown, `.html` →
   Structural, reszta → PlainText),
2. `doc.paragraphs()` daje akapity z polem `line` (1-based, w `doc.text`),
3. zakres linii akapitu = `[seg.line, seg.line + seg.text.count("\n")]`,
4. trafienie `review` należy do akapitu, gdy `hit.line` mieści się w tym zakresie,
5. słowa akapitu = `len(re.findall(r"\w+", seg.text))` (ta sama formuła co `summary.words`).

Funkcja `review_paragraphs_for_file` jest **jednym źródłem prawdy „co idzie do Stage 2"** — tej samej
selekcji ma używać runner Stage 2 (G1), żeby metryka i realna selekcja segmentów liczyły to samo.

## Wynik (`reduction_from_manifest`)

```json
{
  "total_words": 206, "routed_words": 107,
  "routed_segments": 4, "total_segments": 8,
  "reduction_ratio": 0.481, "routed_ratio": 0.519,
  "per_file": [
    {"file": "raport.md", "words": 112, "routed_words": 107, "routed_ratio": 0.955,
     "routed_segments": 4, "total_segments": 4, "fallback": false}
  ]
}
```

## Znane ograniczenie: wariant awaryjny (`fallback`)

Gdy plik ma trafienia `review`, ale jest nieczytelny dla `file_reader` (brak na dysku, błąd I/O),
mapowanie na akapity jest niemożliwe. Wtedy zachowawczo cały plik liczy się jako routowany
(`fallback: true`, `routed_words = words`), bo model i tak musiałby go tknąć. W normalnym przebiegu
(plik czytelny) to się nie zdarza. `file_reader` jest wstrzykiwalny — testy podają treść w pamięci.

## API

```python
import metrics
result = metrics.reduction_from_manifest(manifest_dict)            # czyta pliki z dysku
result = metrics.reduction_from_manifest(manifest_dict, file_reader=lambda p: TRESC[p])  # w pamięci
```

## CLI

```bash
python3 ai_linter.py --format json *.md > manifest.json
python3 tools/measure_reduction.py --manifest manifest.json        # tabela per plik + łącznie (%)
python3 ai_linter.py --format json *.md | python3 tools/measure_reduction.py   # przez stdin
python3 tools/measure_reduction.py --manifest manifest.json --json             # surowy JSON
python3 tools/measure_reduction.py --manifest manifest.json --max-routed 0.10  # exit 1 gdy routed > 10%
python3 tools/measure_reduction.py --manifest manifest.json --min-reduction 0.90  # exit 1 gdy redukcja < 90%
```

Progi `--max-routed` / `--min-reduction` czynią E1 gate-owalnym (exit 1 przy przekroczeniu).

# Atrybucja pracy (E2)

Atrybucja odpowiada na pytanie „która **reguła** (i która **warstwa**) robi modelowi najwięcej
roboty", czyli generuje najwięcej trafień. Liczona czysto z manifestu (`attribution_from_manifest`),
bez LLM. Główną miarą jest tu **liczba trafień** (nie słowa) — robotę dla modelu generuje pojedyncze
trafienie review. Dla każdej pozycji rozdzielamy klasę `review` (realnie routowane do Stage 2) od
`block` (zamknięte przez linter), żeby pokazać też, co linter odsiewa twardo.

## Warstwa i reguła rozstrzygania nakładki

**Warstwa** = źródło trafienia:

- **deklaratywna** — regex z `rules.json`: `id ∈ {id z ai_linter.MARKER_DEFS}`,
- **proceduralna** — detektor kodu: `id ∈ ai_linter.PROCEDURAL_MARKER_IDS` (`PL-TYPO`, `EN-DASH`, `PL-RHYTHM`).

`PL-TYPO` jest w obu zbiorach. Reguła rozstrzygania: **obecność w `MARKER_DEFS` wygrywa**. Czyli
`PL-TYPO` (jest w `MARKER_DEFS`) i `PL-SIGN` => **deklaratywna**; `PL-RHYTHM` i `EN-DASH` (brak ich w
`MARKER_DEFS`, są tylko proceduralne) => **proceduralna**. ID nieznane żadnemu zbiorowi => `nieznana`
(sygnał rozjazdu reguł). Funkcja `classify_layer(rule_id)`.

## Wynik (`attribution_from_manifest`)

```json
{
  "total_hits": 6,
  "per_class": {"review": 5, "block": 1},
  "per_rule": [
    {"id": "PL-SIGN",   "layer": "deklaratywna", "hits": 3, "review": 3, "block": 0, "share": 0.5},
    {"id": "PL-RHYTHM", "layer": "proceduralna", "hits": 2, "review": 2, "block": 0, "share": 0.333},
    {"id": "EN-DASH",   "layer": "proceduralna", "hits": 1, "review": 0, "block": 1, "share": 0.167}
  ],
  "per_layer": {
    "deklaratywna": {"hits": 3, "review": 3, "block": 0, "share": 0.5},
    "proceduralna": {"hits": 3, "review": 2, "block": 1, "share": 0.5}
  }
}
```

`per_rule` jest posortowane malejąco wg liczby trafień (remis: alfabet ID). Inwariant:
`Σ per_rule[*].hits == total_hits == len(hits)`, a `share` sumuje się do 1.0 (gdy `total_hits > 0`).

## Atrybucja per silnik (`attribution_from_runner`) — ograniczenie

Manifest sam w sobie **nie zawiera werdyktów silnika**, więc atrybucji per silnik nie da się policzyć
z samego manifestu (jawne ograniczenie). Wymaga wyniku `runner.run_stage2(...)` (G1). Gdy danych z
runnera brak, ogranicz się do atrybucji per reguła/warstwa z manifestu. `attribution_from_runner`
przyjmuje wynik runnera i zwraca rozbicie osądzonych segmentów per silnik (z `rewrite`/`pass`):

```json
{ "judged": 3,
  "per_engine": [ {"engine": "stub", "judged": 2, "rewrite": 2, "pass": 0, "share": 0.667},
                  {"engine": "inny", "judged": 1, "rewrite": 0, "pass": 1, "share": 0.333} ] }
```

## CLI E2 (`tools/measure_attribution.py`)

```bash
python3 ai_linter.py --format json *.md > manifest.json
python3 tools/measure_attribution.py --manifest manifest.json      # tabele per warstwa + per reguła
python3 ai_linter.py --format json *.md | python3 tools/measure_attribution.py   # przez stdin
python3 tools/measure_attribution.py --manifest manifest.json --json             # surowy JSON
```

To raport diagnostyczny — bez progu, zawsze exit 0.

## Gate (`tools/check_metrics.py`)

Na zaszytym mini-manifeście i treści w pamięci sprawdza:

- **E1**: akapit `review` jest routed, akapit `block` i akapit czysty NIE, `routed_words` = słowa
  akapitu review, inwariant `reduction + routed == 1`, wariant awaryjny (`fallback`),
- **E2**: `per_rule` sumuje się do `total_hits == len(hits)`, `PL-RHYTHM`/`EN-DASH` => proceduralna,
  `PL-SIGN` => deklaratywna, ranking malejący, udziały sumują się do 1.0, oraz atrybucja per silnik z
  wyniku runnera rozdziela `rewrite`/`pass`.

Wpięty do `tests/run_tests.sh` jako warstwa „Metryki: redukcja/atrybucja z manifestu (E1/E2)".
