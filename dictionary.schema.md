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

- **D3 (build-dict)**: zbuduje zalążek słownika z korpusu (częste terminy domenowe → kandydaci do `allow`).
- **D4 (log decyzji)**: akceptacje/odrzucenia operatora zasilą `allow`/`review` + `provenance`.

## Użycie

```bash
python3 ai_linter.py --lang en --dict dictionary.example.json plik.txt
```
