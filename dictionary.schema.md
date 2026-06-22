# Schemat słownika domenowego (D2 / KAN-196)

Słownik domenowy per projekt to warstwa NADRZĘDNA terminów: pozwala oznaczyć terminy branżowe,
które wyglądają jak AI-tell, ale w danej dziedzinie są poprawne (np. „robust" jako cecha
techniczna, „framework"). Z analizy 03 / sekcji „terminologia domenowa" w `SKILL.md`.

Format JSON (stdlib, ZERO-DEP; spójny z `config.json` z D1). Domyślnie BRAK słownika = obecne
zachowanie lintera (zero zmiany). Wczytywany flagą `--dict <ścieżka>`.

## Struktura

```json
{
  "provenance": { "projekt": "...", "wersja": "...", "data": "...", "autor": "...", "zrodlo": "..." },
  "allow":  ["termin", "wyrażenie wielowyrazowe", ...],
  "review": ["termin", ...]
}
```

| Sekcja | Typ | Rola |
|---|---|---|
| `provenance` | obiekt | Metadane pochodzenia (skąd, kiedy, kto, wersja). Wszystkie pola opcjonalne; służy audytowi i przyszłej budowie z korpusu (D3) + logu decyzji (D4). |
| `allow` | lista stringów | Terminy NIE flagowane — warstwa nadrzędna: trafienie markera na taki termin jest POMIJANE. |
| `review` | lista stringów | Terminy obniżane do klasy `review` — jeśli marker był `block`, staje się `review` (nie blokuje werdyktu; pozostaje jako hint). |

## Dopasowanie terminu

- Case-insensitive, jako CAŁE SŁOWO (granica na znakach nie-słownych, z polskimi literami w klasie
  „słowo"). Np. `allow: ["robust"]` łapie „robust", ale NIE „robustness".
- Wyrażenia wielowyrazowe dozwolone (np. „design system").
- Termin dopasowywany wewnątrz `match_fragment` trafienia markera DEKLARATYWNEGO (regex z rules.json).
  Detektory PROCEDURALNE (em-dash, bold, SVO, connector, emoji) operują na strukturze, nie na
  terminach — słownik ich nie dotyczy (świadomie: to warstwa TERMINÓW, nie progów).

## Priorytety i zachowanie

- `allow` ma priorytet nad `review` (jawne dopuszczenie wygrywa).
- Brak pliku / `--dict` nie podany → słownik = None → obecne zachowanie (zero zmiany).
- Niepoprawna struktura (allow/review nie-lista, provenance nie-obiekt, zły JSON) → czytelny błąd
  (exit 2 z CLI).

## Styk z resztą Epiku D

- **D3 (build-dict)** — ZREALIZOWANE: `tools/build_dict.py` buduje SZKIC słownika z korpusu.
  Zasada „częstość proponuje, kanon wetuje, człowiek zatwierdza": terminy częste i o szerokim
  rozrzucie → `review`; AI-telle/kalki (łapane przez markery lintera) wetowane (do `_vetoed_by_canon`,
  informacyjnie); `allow` PUSTE — operator ręcznie przenosi zaakceptowane z `review` do `allow`.
  Opcjonalny `--wordlist` odsiewa słowa ogólne. Szkic jest poprawnym plikiem D2 (wczytywalnym przez
  `load_dictionary`); pole `_vetoed_by_canon` jest ignorowane przez loader.
- **D4 (log decyzji)**: akceptacje/odrzucenia operatora zasilą `allow`/`review` + `provenance`.

## Użycie

```bash
# D2 — linter ze słownikiem:
python3 ai_linter.py --lang en --dict dictionary.example.json plik.txt

# D3 — zbuduj szkic słownika z korpusu (do akceptacji człowieka):
python3 tools/build_dict.py KORPUS/ --wordlist slowa_ogolne.txt --out szkic.json --projekt moj-projekt
```
