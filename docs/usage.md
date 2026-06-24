# Użycie z linii poleceń: batch i flagi

Typowe przepływy lintera poza podstawowym wywołaniem. Pełną listę flag pokazuje `miodek lint --help`.

## Batch: katalog, wzorzec, raport zbiorczy

Linter przyjmuje wiele ścieżek, wzorce glob i całe katalogi (rekursywnie po `*.md` i `*.txt`), więc audyt dużego wolumenu to jedno polecenie:

```bash
miodek lint ./content            # cały katalog rekurencyjnie
miodek lint "**/*.md"            # wzorzec glob
```

Kod wyjścia jest zbiorczy: `1`, gdy którykolwiek plik kończy się werdyktem `FAIL`/`FAIL-HARD`, więc nadaje się wprost jako bramka jakości na całym drzewie. Flaga `--report` dokłada po blokach per-plik zbiorczy agregat `== BATCH ==`: rozkład werdyktów, sumy słów i trafień, najbardziej problematyczne pliki oraz najczęstsze reguły. W trybie `--format json` ten agregat trafia do klucza `batch`. Bez `--report` wyjście jest niezmienione.

```bash
miodek lint --report ./content
```

## Pozostałe flagi

- `--profile NAZWA` — profil progów z `config.json` (np. `default`, `luzny`, `ostry`). Domyślnie `active_profile` z konfiguracji.
- `--dict slownik.json` — słownik domenowy jako warstwa nadrzędna terminów (patrz [Słownik domenowy](dictionary.md)). Domyślnie brak słownika oznacza obecne zachowanie.
- `--format manifest|json` — format wyjścia (domyślnie `manifest`).

[← Powrót do README](../README.md)
