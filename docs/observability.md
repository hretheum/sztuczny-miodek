# Ekonomia i obserwowalność

Linter zdejmuje pracę z modelu, a ile dokładnie, da się zmierzyć z samego manifestu, bez wołania LLM i bez kosztu tokenów.

## Metryki z manifestu

Granicą między etapami jest manifest, więc te metryki liczy się po stronie Stage 1. Moduł `metrics.py`, narzędzia w `tools/`.

Najpierw zbuduj manifest maszynowy, potem przepuść go przez narzędzie:

```bash
miodek lint --format json *.md > manifest.json
```

### Współczynnik redukcji (`tools/measure_reduction.py`)

Udział treści wejścia, której model NIE tyka. Treść routowana do Stage 2 to akapity z trafieniem klasy `review`. Punkt odniesienia z praktyki autora po wprowadzeniu lintera: routed rzędu 4 do 5 procent.

```bash
python3 tools/measure_reduction.py --manifest manifest.json
python3 tools/measure_reduction.py --manifest manifest.json --max-routed 0.10   # exit 1 gdy za dużo idzie do modelu
```

### Atrybucja pracy (`tools/measure_attribution.py`)

Która reguła i która warstwa generuje najwięcej trafień. Raport diagnostyczny, bez progu.

```bash
python3 tools/measure_attribution.py --manifest manifest.json
```

### Zdrowie ekonomii (`tools/measure_health.py`)

Bierze współczynnik routed i porównuje z progiem alarmu z `config.json` (sekcja `economy`). Gdy linter przestaje odsiewać, routed rośnie i alarm zapala się, zanim wyląduje w rachunku za tokeny. Exit 1 przy ALARM, więc nadaje się na bramkę w CI.

```bash
python3 tools/measure_health.py --manifest manifest.json
python3 tools/measure_health.py --manifest manifest.json --alarm 0.08    # nadpisz próg
```

## Eksporter metryk Prometheus i dashboard Grafany

Te same metryki da się podać na dashboard. Polecenie `miodek-exporter` (moduł `miodek.metrics_exporter`, osobny entry point) to eksporter HTTP zero-dep (biblioteka standardowa, `http.server`), który na ścieżce `/metrics` wystawia format tekstowy Prometheus. Czyta `--corpus`, `--port` i `--log` także ze zmiennych środowiskowych (`MIODEK_CORPUS`, `MIODEK_PORT`, `MIODEK_LOG`). Na scrape buduje manifest (uruchamia linter na korpusie, z krótkim cache, żeby nie mielić go na każde zapytanie), liczy `metrics.py` i doczytuje log Stage 2. Stack Prometheus plus Grafana zakładamy gotowy; tu dostarczamy artefakty do wpięcia.

```bash
miodek-exporter --corpus . --port 9112
curl -s localhost:9112/metrics | head
```

Serie: `miodek_reduction_ratio`, `miodek_routed_ratio`, `miodek_total_words`, `miodek_routed_words`, `miodek_hits_total{rule,klasa}`, `miodek_health` (1 OK, 0 ALARM) plus `miodek_health_na`, `miodek_routed_ratio_alarm_threshold`, `miodek_stage2_runs_total{engine,verdict}`, oraz zdrowie samego eksportera (`miodek_exporter_up`, `miodek_scrape_duration_seconds`). Konfiguracja przez zmienne środowiskowe (`MIODEK_CORPUS`, `MIODEK_PORT`, `MIODEK_LOG`, `MIODEK_PROFILE`, `MIODEK_DICT`).

Uczciwość danych: współczynnik redukcji, atrybucja per reguła i wskaźnik zdrowia są realne od zaraz (z manifestu Stage 1, zero kosztu modelu). Panel przebiegów Stage 2 wypełnia się dopiero, gdy realny silnik osądu nazbiera przebiegów; dziś osąd chodzi na atrapie, więc ta seria bywa pusta. To realny panel czekający na dane, nie zaślepka.

Artefakty wdrożeniowe (jednostka systemd eksportera, fragment scrape do `prometheus.yml`, provider provisioningu i dashboard Grafany) leżą w `deploy/`. Runbook wdrożenia i pełen schemat metryk: `deploy/README.md` oraz `metrics-exporter.schema.md`.

[← Powrót do README](../README.md)
