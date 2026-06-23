# Metryki z manifestu — współczynnik redukcji (E1 / KAN-199)

Miary ekonomii i obserwowalności liczone z **manifestu** lintera (Stage 1), bez kosztu tokenów i
bez wołania LLM. Moduł: `metrics.py`. ZERO-DEP (stdlib `re`, plus `ai_linter` dla segmentacji).
CLI: `tools/measure_reduction.py`. Gate: `tools/check_metrics.py`.

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

## Gate (`tools/check_metrics.py`)

Na zaszytym mini-manifeście i treści w pamięci sprawdza: akapit `review` jest routed, akapit `block`
i akapit czysty NIE, `routed_words` = słowa akapitu review, inwariant `reduction + routed == 1`, oraz
wariant awaryjny (`fallback`). Wpięty do `tests/run_tests.sh` jako warstwa „Metryki: współczynnik
redukcji z manifestu (E1)".
