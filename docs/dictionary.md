# Słownik domenowy

Słownik domenowy oznacza terminy branżowe, które wyglądają jak manieryzm AI, choć w danej dziedzinie są poprawne, żeby linter ich nie flagował.

## Po co warstwa terminologii

Niektóre terminy branżowe wyglądają jak manieryzm AI, choć w danej dziedzinie są poprawne (na przykład „robust” jako nazwa produktu albo „leverage” w finansach). To warstwa nadrzędna nad regułami: gdy słownik mówi `allow`, trafienie markera na ten termin jest pomijane.

## Format słownika (JSON)

Format to JSON (biblioteka standardowa, zero zależności, spójnie z `rules.json` i `config.json`):

```json
{
  "provenance": { "projekt": "...", "wersja": "...", "data": "...", "autor": "...", "zrodlo": "..." },
  "allow":  ["robust", "leverage"],
  "review": ["termin do przejrzenia"]
}
```

- `allow` — terminy nie flagowane (marker wygaszony, nawet gdy wygląda jak AI-tell).
- `review` — terminy spychane do klasy `review` (informacyjne, nie blokują werdyktu).
- `provenance` — metadane pochodzenia (kto, kiedy, skąd).

Dopasowanie idzie po całym słowie, bez względu na wielkość liter.

## Użycie: flaga `--dict`

Wskazujesz słownik flagą `--dict`:

```bash
miodek lint --dict slownik.json --lang both ŚCIEŻKA_DO_PLIKU.md
```

Bez słownika skill działa w trybie ogólnym: pełny audyt polszczyzny i manieryzmu AI. Słownik użytkownika jest zwykle zewnętrzny, dopasowany do jego dziedziny.

## Budowa szkicu: `miodek build-dict`

Szkic słownika budujesz z własnego korpusu podkomendą `miodek build-dict`. Zasada: częstość proponuje kandydatów, kanon wetuje terminy będące manieryzmem, a człowiek zatwierdza (szkic ma `allow` puste, kandydaci lądują w `review` do przeniesienia):

```bash
miodek build-dict ./korpus --out szkic.json --projekt mój-projekt
```

Flagi: `--out` (plik wyjściowy, domyślnie stdout), `--min-count` i `--min-files` (progi częstości i rozrzutu), `--wordlist` (lista słów ogólnych do odsiania), `--projekt` (nazwa do provenance). Po przeglądzie przenosisz zaakceptowane terminy z `review` do `allow` i wskazujesz słownik flagą `--dict` w `miodek lint`.

## Słownik projektu `dictionary.project.json`

Repo zawiera własny słownik projektu `dictionary.project.json` (dogfooding). Oznacza terminy, które linter łapie jako manieryzm, choć w tej dokumentacji są poprawne, na przykład `robust` i `leverage` użyte jako przykłady terminów branżowych. Audyt z tym słownikiem wygasza te trafienia:

```bash
miodek lint --dict dictionary.project.json --lang both README.md
```

[← Powrót do README](../README.md)
