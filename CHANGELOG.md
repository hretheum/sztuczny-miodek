# Changelog

Rejestr istotnych zmian w projekcie. Format wzorowany na [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/),
wersjonowanie zgodne z [SemVer](https://semver.org/lang/pl/).

## [Nieopublikowane]

## [1.2.1] - 2026-06-25

### Dodane
- `miodek confluence correct --runpod` — korekta stron Confluence realnym Bielikiem na efemerycznym podzie RunPod (jak `miodek correct --runpod`).

## [1.2.0] - 2026-06-25

### Dodane
- Podkomenda `miodek confluence pull` — audyt prozy stron Confluence przez adapter (read-only). Connector na bibliotece standardowej, poświadczenia z env; adapter pomija makra `ac:`/`ri:` i kod jako wyspy nie-prozy.
- Podkomenda `miodek confluence correct` — korekta prozy i zapis zwrotny do Confluence. Dry-run domyślny, zapis tylko z `--apply` plus potwierdzeniem; twarda weryfikacja wierności przed zapisem (makra i struktura nietknięte), nowa wersja strony, przerwanie na konflikt wersji.
- Nazwane instancje Confluence: flaga `--instance <nazwa>` wybiera slot `CONFLUENCE_<NAZWA>_*` w env; bez flagi domyślny zestaw `CONFLUENCE_*`.

## [1.1.0] - 2026-06-24

### Dodane
- Dystrybucja jako pakiet uruchamiany przez `uvx` (PyPI i źródło git). Polecenie `uvx miodek lint ...` działa ulotnie, bez ręcznej instalacji.
- Ujednolicone CLI `miodek` z podkomendami `lint`, `correct`, `gate`, `lt` oraz `build-dict`.
- Podkomenda `build-dict` buduje szkic słownika domenowego z korpusu (wcześniej narzędzie dostępne tylko z klonu repozytorium).
- Tryb batch lintera: katalogi i wzorce glob z jednym zbiorczym kodem wyjścia oraz flagą `--report` (blok `== BATCH ==`, agregat w JSON pod kluczem `batch`).
- Osobne polecenie `miodek-exporter` (eksporter metryk Prometheus).
- Słownik projektu `dictionary.project.json` jako przykład warstwy terminologii domenowej.

### Zmienione
- Pakiet w układzie `src/miodek/`, dostęp do danych przez `importlib.resources`.
- Dokumentacja przeniesiona na składnię `miodek` (zamiast bezpośrednich wywołań skryptów).

## [1.0.0]

### Dodane
- Deterministyczny linter manieryzmu AI i polszczyzny (Stage 1), na samej bibliotece standardowej.
- Opcjonalny osąd modelu (Stage 2) za wymiennym interfejsem silnika.
- Trzy bramki jakości: przy zapisie pliku, na merge request, przed publikacją.
- Korektor zamykający pętlę audytu do werdyktu PASS, routing silników, integracja LanguageTool na żądanie.
- Instalacja jako skill Claude Code (clone i plugin przez marketplace).

[Nieopublikowane]: https://github.com/hretheum/sztuczny-miodek/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/hretheum/sztuczny-miodek/releases/tag/v1.1.0
[1.0.0]: https://github.com/hretheum/sztuczny-miodek/releases/tag/v1.0.0
