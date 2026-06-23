# Schemat: eksporter metryk Prometheus (KAN-219)

Kontrakt eksportera `tools/metrics_exporter.py` i dashboardu Grafany. Stan: KAN-219.

## Po co to jest

Stack obserwowalności (Prometheus na porcie 9090, Grafana na 3000) JUŻ stoi na hoście mbair jako
usługi systemd-podman. Eksporter wystawia metryki Stage 1 (E1, E2, E4) plus przebiegi Stage 2 w
formacie tekstowym Prometheus, żeby Prometheus mógł je odpytywać, a Grafana rysować dashboard.
Eksporter nic nie liczy od nowa: reużywa `metrics.py`, `config.py`, `runner.py`.

## Endpointy serwera

- `GET /metrics` — ekspozycja w formacie Prometheus 0.0.4 (`text/plain; version=0.0.4`). Na scrape
  buduje lub odświeża state z cache (TTL `MIODEK_SCRAPE_CACHE_TTL`, domyślnie 30 s), żeby częste
  scrape'y nie mieliły lintera.
- `GET /healthz` — liveness, zwraca `ok` bez uruchamiania lintera.
- pozostałe ścieżki — `404`.

## Metryki

| Nazwa | Typ | Etykiety | Źródło | Znaczenie |
|---|---|---|---|---|
| `miodek_reduction_ratio` | gauge | brak | `metrics.reduction_from_manifest` | udział treści, której model nie tyka (E1) |
| `miodek_routed_ratio` | gauge | brak | jw. | udział treści routowanej do Stage 2 (hit rate, odniesienie ~0.04-0.05) |
| `miodek_total_words` | gauge | brak | jw. | łączna liczba słów korpusu |
| `miodek_routed_words` | gauge | brak | jw. | słowa w akapitach z trafieniem review |
| `miodek_hits_total` | gauge | `rule`, `klasa` | `metrics.attribution_from_manifest` | trafienia per reguła i klasa (review/block) na bieżącym korpusie (E2) |
| `miodek_health` | gauge | brak | `metrics.economy_health` | 1=OK, 0=ALARM (E4). Stan N/A NIE jest tu emitowany |
| `miodek_health_na` | gauge | brak | jw. | 1 gdy zdrowie = N/A (próbka za mała); mała próbka nie udaje OK |
| `miodek_routed_ratio_alarm_threshold` | gauge | brak | `config.load_economy` (przez economy_health) | próg alarmu E4, linia odniesienia pod routed_ratio |
| `miodek_stage2_runs_total` | counter | `engine`, `verdict` | `runner.read_stage2_runs` | przebiegi Stage 2 per silnik i werdykt (append-only log) |
| `miodek_exporter_up` | gauge | brak | serwer | 1 gdy ostatni zbiór metryk się udał, 0 na fail-soft |
| `miodek_scrape_duration_seconds` | gauge | brak | serwer | czas budowy zestawu metryk (linter + obliczenia) |

### Uwagi do kontraktu

- `miodek_hits_total` to mimo sufiksu `_total` migawka bieżącego korpusu (typ gauge). Nie jest
  monotonicznym licznikiem. Nazwa narzucona kontraktem zadania, znaczenie wyjaśnione w polu HELP.
  Serie zerowe są pomijane, żeby ekspozycja nie puchła.
- `miodek_stage2_runs_total` to prawdziwy counter (append-only log decyzji). Wypełnia się dopiero,
  gdy realny silnik Stage 2 (Bielik przez Ollama, model przez OpenRouter za interfejs
  `engines.JudgeEngine`) nazbiera przebiegów. Dziś Stage 2 chodzi na atrapie (`StubJudgeEngine`),
  więc seria bywa pusta. To realny panel czekający na dane (żadna zaślepka). Przy pustym logu ekspozycja
  zawiera tylko HELP i TYPE bez serii (poprawne).
- Uczciwość danych: E1, E2 i E4 są realne od zaraz (liczą się z manifestu Stage 1, zero kosztu LLM).

## Format ekspozycji

Dla każdej metryki najpierw `# HELP <name> <opis>`, potem `# TYPE <name> <gauge|counter>`, potem
serie. Etykiety w postaci `name{k="v",k2="v2"} value`. Escaping wartości etykiety: `\` na `\\`,
`"` na `\"`, znak nowej linii na `\n`. Brak końcowych spacji. Plik kończy się znakiem nowej linii.

## Architektura kodu

Trzy warstwy, granica testowalna w środku:

- `collect_state(corpus, log_path, profile, dict_path, lang)` — efekty uboczne: uruchamia
  `ai_linter --format json` na korpusie jako podproces (exit 1 lintera na FAIL to normalny stan
  korpusu z manieryzmem (eksporter traktuje to normalnie); manifest jest na stdout niezależnie od kodu wyjścia,
  liczy metryki, czyta log Stage 2. Zwraca surowy dict liczb.
- `render_metrics(state)` — czysta funkcja: state na tekst ekspozycji. Sedno self-testu offline.
- serwer HTTP z cache i fail-soft: błąd `collect_state` serwuje ostatni dobry state, a gdy go brak,
  minimalny zestaw z `miodek_exporter_up 0` (nie 500, żeby Prometheus widział target up).

## Konfiguracja (env, mirror w argparse)

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `MIODEK_CORPUS` | katalog repo | ścieżka korpusu (plik, glob lub katalog) |
| `MIODEK_PORT` | 9112 | port serwera |
| `MIODEK_LOG` | `decisions.jsonl` w repo | ścieżka wspólnego strumienia JSONL |
| `MIODEK_PROFILE` | brak | profil progów lintera |
| `MIODEK_DICT` | brak | słownik domenowy |
| `MIODEK_LANG` | both | język markerów (pl/en/both) |
| `MIODEK_SCRAPE_CACHE_TTL` | 30 | TTL cache state w sekundach |
| `MIODEK_HOST` | 0.0.0.0 | adres nasłuchu |

## Artefakty deploy (do wpięcia, NIE wdrażamy)

- `deploy/systemd/miodek-exporter.service` — goła usługa systemd (Python 3.14 na mbair, zero-dep).
- `deploy/prometheus/miodek-scrape.snippet.yml` — fragment scrape do `prometheus.yml`, target 9112.
- `deploy/grafana/provider.yaml` — provider provisioningu dashboardów.
- `deploy/grafana/miodek-dashboard.json` — dashboard z datasource jako zmienną `${DS_PROMETHEUS}`.
- `deploy/README.md` — runbook wdrożenia plus akapit o uczciwości danych.

## Test offline

`tools/check_metrics_exporter.py` (wpięty do `tests/run_tests.sh`) wstrzykuje state zbudowany z
ustalonego mini-manifestu w pamięci i sprawdza wyłącznie `render_metrics`. Bez sieci, bez lintera,
bez Prometheusa. Pokrywa: kolejność HELP i TYPE, typy serii, inwariant redukcja plus routed równa
jeden, etykiety reguła i klasa, escaping, mapowanie zdrowia OK/ALARM/N/A, agregację Stage 2, pusty
log Stage 2 (panel bez serii), fail-soft, oraz obecność i krytyczne pola artefaktów deploy.
