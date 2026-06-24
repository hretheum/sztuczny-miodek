# Współtworzenie

Dziękujemy za zainteresowanie projektem. To fork narzędzia Tomasza Jakubowskiego
([upstream](https://github.com/researchanddeploy/sztuczny-miodek)), rozwijany na licencji MIT.

## Zasada nadrzędna: każdy tekst przechodzi własną bramkę

Narzędzie audytuje polszczyznę i manieryzm AI, więc jego dokumentacja sama musi przejść ten audyt.
Każdy plik prozy (`.md`, `.txt`) zmieniony w PR ma uzyskać werdykt PASS:

```bash
PYTHONPATH=src python3 -m miodek.ai_linter --lang both ŚCIEŻKA_DO_PLIKU.md
```

PASS wymaga zera blokerów. Pisz tak, żeby przechodziło: bez serii antytez „nie X, a Y", bez triad
retorycznych, maksymalnie jeden lub dwa myślniki na akapit, pełne polskie znaki diakrytyczne,
bez emoji i strzałek w nagłówkach.

## Testy

Przed zgłoszeniem zmiany uruchom pełny zestaw testów. Musi być zielony:

```bash
bash tests/run_tests.sh
```

Gate obejmuje regresję baseline, kontrole spójności ID reguł, konfiguracji, słownika, CLI oraz
testy offline poszczególnych narzędzi. Nowa funkcja powinna mieć własny `tools/check_*.py`
wpięty do `tests/run_tests.sh`.

## Styl kodu

Rdzeń trzyma się biblioteki standardowej (zero zależności w warstwie podstawowej). Cięższe
elementy wchodzą jako opcjonalne extras. Reguły lintera żyją jako dane w `rules.json`, nie w kodzie.

## Pull requesty

Gałęzie tematyczne trzymaj wąsko (jeden temat na PR). Zmiany przydatne dla wszystkich kieruj
także do upstreamu, małymi wstecznie zgodnymi PR-ami. Commit kończ linią `Co-Authored-By`
zgodnie z historią repozytorium.

[← Powrót do README](README.md)
