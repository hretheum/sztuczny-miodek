# Wdrożenie eksportera metryk i dashboardu (KAN-219)

Runbook dla operatora. Stack obserwowalności (Prometheus na porcie 9090, Grafana na 3000) JUŻ stoi
na hoście mbair jako usługi systemd-podman. Tu wpinamy eksporter metryk Stage 1 i dashboard. Niczego
nie stawiamy od zera.

Wszystkie artefakty są zero-dep (Python 3.14 na mbair wystarcza, bez budowania obrazu).

## Co wdrażamy

| Artefakt | Cel na mbair |
|---|---|
| `tools/metrics_exporter.py` | eksporter HTTP na porcie 9112 (goła usługa systemd) |
| `deploy/systemd/miodek-exporter.service` | jednostka systemd uruchamiająca eksporter |
| `deploy/prometheus/miodek-scrape.snippet.yml` | fragment scrape do `/home/mac/prometheus/prometheus.yml` |
| `deploy/grafana/provider.yaml` | provider provisioningu dashboardów |
| `deploy/grafana/miodek-dashboard.json` | dashboard Grafany |

## Krok 1: repo na host

Skopiuj repo na mbair (rsync albo git), np. do `/opt/sztuczny-miodek`:

```
rsync -a --delete ./ mac@mbair:/opt/sztuczny-miodek/
```

Ścieżki w jednostce systemd są placeholderowe (`/opt/sztuczny-miodek`). Dostosuj je, jeśli repo
leży gdzie indziej.

## Krok 2: usługa eksportera

Eksporter biegnie jako usługa systemd użytkownika `mac` (zero-dep, goły Python):

```
mkdir -p ~/.config/systemd/user
cp /opt/sztuczny-miodek/deploy/systemd/miodek-exporter.service ~/.config/systemd/user/
# uzupełnij MIODEK_CORPUS i ścieżki w jednostce, jeśli repo leży gdzie indziej
systemctl --user daemon-reload
systemctl --user enable --now miodek-exporter.service
loginctl enable-linger mac          # żeby usługa żyła bez aktywnej sesji
```

Sprawdzenie:

```
systemctl --user status miodek-exporter.service
curl -s localhost:9112/metrics | head -40
curl -s localhost:9112/healthz
```

Korpus do lintowania ustaw przez `MIODEK_CORPUS` (plik, glob lub katalog prozy). Brak ustawienia
znaczy katalog repo. Eksporter trzyma cache state z TTL 30 s, więc częste scrape'y nie mielą lintera.

### Wariant alternatywny (quadlet, jeśli wolisz kontener)

Goła usługa systemd jest tu preferowana (zadanie: bez budowania obrazu). Gdyby jednak eksporter miał
biec w kontenerze podman w tej samej sieci co Prometheus, opakuj `python:3` z bind-mountem repo jako
quadlet `~/.config/containers/systemd/miodek-exporter.container`, komenda
`python3 /opt/sztuczny-miodek/tools/metrics_exporter.py`, port 9112. Wtedy w scrape użyj nazwy serwisu
zamiast `localhost` (patrz Krok 3).

## Krok 3: scrape w Prometheusie

Dopisz blok z `deploy/prometheus/miodek-scrape.snippet.yml` do listy `scrape_configs:` w
`/home/mac/prometheus/prometheus.yml`, potem przeładuj Prometheusa:

```
curl -X POST http://localhost:9090/-/reload     # gdy włączone --web.enable-lifecycle
# albo restart/reload jednostki Prometheusa
```

Dobór targetu (w snippecie są warianty w komentarzu):
- eksporter i Prometheus na hoście: `localhost:9112` (domyślne),
- Prometheus w kontenerze, eksporter na hoście: `host.containers.internal:9112`,
- oba w kontenerach w tej samej sieci: nazwa serwisu `miodek-exporter:9112`.

Weryfikacja: w Prometheusie `Status -> Targets` job `miodek` powinien być `UP`, a zapytanie
`miodek_reduction_ratio` zwracać wartość.

## Krok 4: dashboard w Grafanie

Grafana czyta provisioning z `/home/mac/grafana/provisioning`:

```
cp /opt/sztuczny-miodek/deploy/grafana/provider.yaml        /home/mac/grafana/provisioning/dashboards/miodek.yaml
cp /opt/sztuczny-miodek/deploy/grafana/miodek-dashboard.json /home/mac/grafana/provisioning/dashboards/
# przeładuj Grafanę (restart kontenera albo provisioning sam podchwytuje pliki)
```

Dostosuj `path` w `provider.yaml` do tego, jak provisioning jest zamontowany w kontenerze Grafany
(domyślnie `/etc/grafana/provisioning/dashboards`). Dashboard używa datasource jako zmiennej
`${DS_PROMETHEUS}`, więc przy imporcie wybierz swój datasource Prometheus. Dashboard pojawi się w
folderze „Sztuczny Miodek" pod tytułem „Sztuczny Miodek — obserwowalność".

## Panele dashboardu

1. Współczynnik redukcji (stat, E1).
2. Słowa: total i routed (stat).
3. Zdrowie ekonomii E4 (stat, OK na zielono, ALARM na czerwono).
4. Próbka N/A (stat, gdy próbka za mała na wiarygodny wskaźnik).
5. Routed ratio na tle progu alarmu (wykres czasowy, E4).
6. Atrybucja per reguła, top 10 trafień review (wykres słupkowy, E2).
7. Stage 2, przebiegi per silnik i werdykt (wykres czasowy).
8. Eksporter: up i czas scrape (wykres czasowy, zdrowie samego eksportera).

## Uczciwość danych (ważne)

Metryki E1, E2 i E4 (redukcja, atrybucja, zdrowie ekonomii) są realne od zaraz. Liczą się z manifestu
Stage 1, czyli z deterministycznego lintera, bez kosztu modelu językowego.

Panel „Stage 2, przebiegi per silnik" (`miodek_stage2_runs_total`) wypełnia się dopiero, gdy realny
silnik Stage 2 (Bielik przez Ollama lokalnie albo model przez OpenRouter, za interfejs
`engines.JudgeEngine`) nazbiera przebiegów. Dziś Stage 2 chodzi na atrapie (`StubJudgeEngine`), więc
ten panel może być pusty lub rzadki. To nie zaślepka: to realny panel czekający na dane. Gdy podepniesz
silnik i ustawisz `MIODEK_LOG` na wspólny strumień `decisions.jsonl`, panel zacznie pokazywać werdykty.

## Bezpieczeństwo

- Eksporter serwuje tylko odczyt metryk Stage 1, nie wystawia treści korpusu (jedynie liczby i ID reguł).
- Port 9112 trzymaj w sieci wewnętrznej hosta. Jednostka ma `NoNewPrivileges` i `PrivateTmp`.
- Eksporter nie woła sieci ani modelu. Buduje manifest lokalnym linterem, czyta lokalny log.
