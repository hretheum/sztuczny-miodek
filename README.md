# sztuczny-miodek

Skill Claude Code do audytu polszczyzny i eradykacji manieryzmu AI (AI-tellów) w tekstach polskich i angielskich. Metodologia: pragmatyczny puryzm Jana Miodka.

> **Ten projekt to fork.** Rdzeń pochodzi od Tomasza Jakubowskiego, z oryginalnego repozytorium [researchanddeploy/sztuczny-miodek](https://github.com/researchanddeploy/sztuczny-miodek): deterministyczny linter Stage 1, kanon manieryzmu, metodologia Miodka, instalacja jako skill Claude Code oraz słownik domenowy.

Fork rozwija narzędzie o kolejne warstwy:

- CLI przez `uvx` z ujednoliconym poleceniem `miodek`,
- trzy bramki jakości: przy zapisie pliku, na merge request, przed publikacją,
- korektor zamykający pętlę audytu do werdyktu PASS,
- osąd modelu Stage 2 z routingiem silników i lejkiem kosztowym,
- ekonomię i obserwowalność: metryki z manifestu oraz eksporter Prometheus,
- integrację LanguageTool na żądanie.

Czysty skill (tryby A i B) żyje w Claude Code: wywołujesz go w rozmowie, a model prowadzi audyt i korektę. CLI przez `uvx` (tryb C) wynosi te same reguły poza Claude Code, do terminala i do potoku CI, jako samodzielne polecenie `miodek` działające bez asystenta.

## Spis treści

- [Co robi](#co-robi)
- [Kluczowe funkcje](#kluczowe-funkcje)
- [Instalacja](#instalacja)
  - [Tryb A — bezpośredni clone (skill)](#tryb-a--bezpośredni-clone-skill)
  - [Tryb B — plugin przez marketplace](#tryb-b--plugin-przez-marketplace)
  - [Tryb C — CLI przez uvx](#tryb-c--cli-przez-uvx)
- [Użycie](#użycie)
  - [W Claude Code](#w-claude-code)
  - [Linter z linii poleceń](#linter-z-linii-poleceń)
  - [Interpretacja manifestu i werdyktu](#interpretacja-manifestu-i-werdyktu)
- [Bramka write-time (hook na zapisie pliku)](#bramka-write-time-hook-na-zapisie-pliku)
  - [Włączenie hooka w pluginie (opt-in)](#włączenie-hooka-w-pluginie-opt-in)
  - [Użycie jako git pre-commit](#użycie-jako-git-pre-commit)
- [Bramka CI na merge request](#bramka-ci-na-merge-request)
- [Bramka przed publikacją](#bramka-przed-publikacją)
- [Testy](#testy)
- [Ekonomia i obserwowalność (metryki z manifestu)](#ekonomia-i-obserwowalność-metryki-z-manifestu)
  - [Eksporter metryk Prometheus i dashboard Grafany](#eksporter-metryk-prometheus-i-dashboard-grafany)
  - [Auto-offload poda RunPod po przebiegu Stage 2](#auto-offload-poda-runpod-po-przebiegu-stage-2)
  - [Efemeryczny pod jednym krokiem: flaga `--runpod`](#efemeryczny-pod-jednym-krokiem-flaga---runpod)
  - [Routing silnika: lejek kosztowy](#routing-silnika-lejek-kosztowy)
- [Korektor: pętla audyt, poprawka, ponowny audyt](#korektor-pętla-audyt-poprawka-ponowny-audyt)
- [LanguageTool: pełna korekta polszczyzny na żądanie](#languagetool-pełna-korekta-polszczyzny-na-żądanie)
- [Opcjonalna warstwa terminologii domenowej](#opcjonalna-warstwa-terminologii-domenowej)
- [Atrybucja i licencja](#atrybucja-i-licencja)

## Co robi

Skill realizuje dwie misje:

1. **Wzorcowa polszczyzna (PL)** — pełny audyt tekstu polskiego wg dziesięciu priorytetów: cyrylica, kalki angielskie, fałszywi przyjaciele, anglicyzmy, sztuczne kolokacje, interpunkcja, styl i gramatyka, ortografia terminów łacińskich/greckich, manieryzm AI, typografia.
2. **Usuwanie AI-tellów (PL + EN)** — wykrywa i usuwa manieryzmy generatywne: puste signposty, triady (rule-of-three), antytezę „nie X — to Y”, paralelizm, nadużycie myślnika, puste superlatywy, klisze redefinicyjne, emoji w nagłówkach. Dla raportów, syntez, listów motywacyjnych, CV i dokumentacji.

Skill działa jako **twarda bramka jakości** przed deklaracją „done”. Obowiązuje semantyka **„PASS z uwagami = NIE PASS”**: każdy nierozwiązany flag blokuje werdykt PASS. Werdykt FAIL zapada przy cyrylicy w tekście PL (FAIL-HARD), markerze klasy `block` po przekroczeniu progu albo gęstości ważonej trafień powyżej 8 na 500 słów.

Zasada Miodka: poprawiaj to, co ma polski odpowiednik; zachowuj to, co przyjęło się w danej dziedzinie. Dla manieryzmu AI: zmieniaj teksturę prozy, zachowuj fakty i metryki.

## Kluczowe funkcje

**Deterministyczny linter `ai_linter.py` (Stage 1).** Pre-scan bez kosztu tokenów LLM. Generuje manifest podejrzeń w formacie `plik:linia:ID:KLASA:fragment` plus blok `== SUMMARY ==` z liczbą słów, trafień, maksymalną liczbą myślników na akapit, gęstością i werdyktem. Linter łapie szeroko (wysoki recall), świadomie dopuszcza false-positives w klasie `review`. Wyłącznie biblioteka standardowa Pythona 3, zero zależności pip.

**Osąd kontekstowy (Stage 2).** Dla każdego trafienia z manifestu: przeczytaj pełne zdanie, rozstrzygnij czy to realny manieryzm czy uzasadnienie kontekstowe, nanieś poprawkę, zweryfikuj kolokację po zamianie, wystaw werdykt. Wzorzec manifest → celowany Edit oszczędza około 60% tokenów względem czytania całych plików.

**Kanon 14 kategorii manieryzmu (`manieryzm-ai.md`).** Źródło prawdy taksonomii. Każde ID kategorii ma odpowiednik w linterze. Kategorie PL: PL-SIGN, PL-CLICHE, PL-RHET, PL-RHYTHM, PL-HEDGE, PL-TYPO. Kategorie EN: EN-DASH, EN-ANTI, EN-TRIAD, EN-PARA, EN-CLICHE, EN-HEDGE, EN-SUPER, EN-CONCL.

**Priorytety 1–10 (`SKILL.md`).** Ranking wykrywania błędów polszczyzny, od cyrylicy (Priorytet 1) przez sztuczne kolokacje (Priorytet 5, „najczęściej przeoczana kategoria”) i interpunkcję (Priorytet 6) po typografię (Priorytet 10). Każdy priorytet ma tabelę wzorców z poprawkami i regexami skanowania.

## Instalacja

### Tryb A — bezpośredni clone (skill)

Najprostszy. Skill ląduje wprost w katalogu skilli Claude Code:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/researchanddeploy/sztuczny-miodek.git ~/.claude/skills/sztuczny-miodek
```

Claude Code wykryje skill automatycznie na podstawie `SKILL.md`. Wywołanie: `/sztuczny-miodek`.

Aktualizacja: `cd ~/.claude/skills/sztuczny-miodek && git pull`.

### Tryb B — plugin przez marketplace

Wersjonowane aktualizacje i instalacja jedną komendą:

```text
/plugin marketplace add researchanddeploy/sztuczny-miodek
/plugin install sztuczny-miodek@sztuczny-miodek
```

Wywołanie: `/sztuczny-miodek:sztuczny-miodek`. Aktualizacja: `/plugin update sztuczny-miodek@sztuczny-miodek`.

Oba tryby korzystają z tego samego `SKILL.md` w korzeniu repo. Katalog `.claude-plugin/` jest używany tylko w trybie B.

### Tryb C — CLI przez uvx

Narzędzie linii poleceń `miodek` można uruchomić bez ręcznej instalacji. Wymaga [uv](https://docs.astral.sh/uv/). Najprościej, wprost z PyPI:

```bash
uvx miodek lint --lang both ŚCIEŻKA_DO_PLIKU.md
```

`uvx` pobiera paczkę do cache i uruchamia ulotnie, bez instalowania niczego na stałe. Polecenie `miodek` to dispatcher z podkomendami `lint`, `correct`, `gate`, `lt`. Eksporter metryk Prometheus jest osobnym poleceniem `miodek-exporter`:

```bash
uvx --from miodek miodek-exporter --help
```

Alternatywnie, wprost ze źródła git (np. dla gałęzi roboczej przed wydaniem na PyPI):

```bash
uvx --from git+https://github.com/hretheum/sztuczny-miodek@epic-a-reguly-jako-dane \
  miodek lint --lang both ŚCIEŻKA_DO_PLIKU.md
```

Co daje tryb C, czego nie ma czysty skill z trybów A i B:

- działa poza Claude Code, w dowolnym terminalu i w potoku CI, bez asystenta;
- batch na całych katalogach i wzorcach glob z jednym zbiorczym kodem wyjścia (audyt dużych wolumenów);
- trzy bramki jakości jako kroki automatyzacji: przy zapisie, na merge request, przed publikacją;
- osąd modelu Stage 2 z routingiem silników oraz korektor doprowadzający tekst do werdyktu PASS;
- eksporter metryk Prometheus jako osobne polecenie `miodek-exporter`.

Tryby A i B zostają najlepsze do pracy w rozmowie z Claude Code; tryb C jest do skryptów, CI i hooków gita.

Rdzeń nie ma żadnych zależności (sama biblioteka standardowa). Warstwy opcjonalne wydzielają extras `[exporter]` i `[lt]`. Są one dziś puste, bo wszystkie komponenty działają na bibliotece standardowej, więc instalacja z extra (`uv tool install "miodek[exporter]"`) daje na razie ten sam wynik co bez niego. Powiązanie z homelabem (quadlet, systemd) zostaje poza paczką, deklaratywnie w repozytorium infrastruktury.

## Użycie

### W Claude Code

Skill uruchamia się przez jeden z wyzwalaczy w rozmowie:

- `sprawdź polszczyznę`
- `sztuczny miodek`
- `audyt językowy`
- `korekta tekstu`, `manieryzm AI`, `AI-tell`, `de-AI`, `usuń ślady AI`, `odAI-uj`

Claude przeprowadzi pełny protokół: pre-scan linterem, osąd kontekstowy, korektę, przebieg weryfikacyjny i werdykt PASS/FAIL.

### Linter z linii poleceń

Pre-scan można uruchomić samodzielnie podkomendą `lint`:

```bash
miodek lint --lang both ŚCIEŻKA_DO_PLIKU.md
```

Po instalacji przez uvx (Tryb C) zadziała też bez klonu repo. Z klonu repo, bez instalacji, ten sam linter uruchomisz przez `python3 -m miodek.ai_linter --lang both ŚCIEŻKA_DO_PLIKU.md` (z `PYTHONPATH=src`).

Flaga `--lang` przyjmuje `pl`, `en` lub `both`. Można podać kilka ścieżek naraz.

#### Batch: katalog, wzorzec, raport zbiorczy

Linter przyjmuje wiele ścieżek, wzorce glob i całe katalogi (rekursywnie po `*.md` i `*.txt`), więc audyt dużego wolumenu to jedno polecenie:

```bash
miodek lint ./content            # cały katalog rekurencyjnie
miodek lint "**/*.md"            # wzorzec glob
```

Kod wyjścia jest zbiorczy: `1`, gdy którykolwiek plik kończy się werdyktem `FAIL`/`FAIL-HARD`, więc nadaje się wprost jako bramka jakości na całym drzewie. Flaga `--report` dokłada po blokach per-plik zbiorczy agregat `== BATCH ==`: rozkład werdyktów, sumy słów i trafień, najbardziej problematyczne pliki oraz najczęstsze reguły. W trybie `--format json` ten agregat trafia do klucza `batch`. Bez `--report` wyjście jest niezmienione.

```bash
miodek lint --report ./content
```

#### Pozostałe flagi

- `--profile NAZWA` — profil progów z `config.json` (np. `default`, `luzny`, `ostry`). Domyślnie `active_profile` z konfiguracji.
- `--dict slownik.json` — słownik domenowy jako warstwa nadrzędna terminów (opis niżej). Domyślnie brak słownika oznacza obecne zachowanie.
- `--format manifest|json` — format wyjścia (domyślnie `manifest`).

### Interpretacja manifestu i werdyktu

Manifest to jedna linia na trafienie:

```text
raport.md:42:PL-SIGN:review:Warto podkreślić, że
```

Pola: ścieżka pliku, numer linii, ID kategorii, klasa (`review` lub `block`), dopasowany fragment. Klasa `review` wymaga osądu kontekstowego (możliwy false-positive). Klasa `block` to bloker werdyktu po przekroczeniu progu.

Blok `== SUMMARY ==` podaje werdykt na końcu:

```text
== SUMMARY ==
plik | słowa | trafienia | em-dash/akapit(max) | gęstość/500 | blokery | WERDYKT
```

PASS zapada tylko przy zerze blokerów i gęstości nie większej niż 8.

## Bramka write-time (hook na zapisie pliku)

Bramka write-time uruchamia linter przy każdym zapisie pliku prozy (`.md`/`.txt`) i zatrzymuje pracę WYŁĄCZNIE przy twardych blokerach. To inna bramka niż dwie pozostałe:

| Bramka | Kiedy | Co zatrzymuje |
|---|---|---|
| write-time (ta) | przy zapisie pliku prozy (hook lub pre-commit) | tylko twarde blokery (klasa `block` lub `FAIL-HARD`) |
| CI | przed mergem (`ai_linter.py`, exit 1) | pełny werdykt FAIL/FAIL-HARD, łapie też samą gęstość |
| przed publikacją | przed wysyłką | pełny werdykt plus osąd modelu (Stage 2) |

Niuans: sama wysoka gęstość trafień klasy `review` (czyli `verdict == FAIL` przy zerze blokerów) NIE zatrzymuje write-time, daje co najwyżej ostrzeżenie. Dzięki temu codzienna edycja nie jest przerywana z powodu gęstości, a twarde blokery (cyrylica, em-dash od trzech na akapit, emoji w nagłówku, serie antytez) zatrzymują pracę od razu.

### Włączenie hooka w pluginie (opt-in)

Plugin deklaruje hook `PostToolUse` na `Write|Edit|MultiEdit` w `hooks/hooks.json`, ale w trybie hooka jest on bierny do jawnego włączenia. Sama instalacja pluginu nie zaczyna nikomu blokować edycji. Aktywacja zmienną środowiskową:

```bash
export MIODEK_WRITE_GATE=1   # albo true / on / yes
```

Przy twardym blokerze hook blokuje zapis dwoma kanałami naraz, dla odporności na wersję Claude Code: na stdout wypisuje JSON z polem `decision: block` i powodem (oraz lustrzane `hookSpecificOutput.permissionDecision: deny`), a równolegle kończy kodem 2 z tym samym powodem na stderr (kanon PostToolUse, stderr wraca do agenta). Powód to lista blokerów: ID markera, numer linii, fragment, żeby agent wiedział, co poprawić. Sama wysoka gęstość przechodzi (exit 0, brak wyjścia). Bez ustawionej zmiennej hook kończy natychmiast bez działania.

### Użycie jako git pre-commit

Skrypt działa też z linii poleceń (bez zmiennej środowiskowej, bo jawne wywołanie to świadoma decyzja): bierze ścieżki z argumentów, kończy kodem 1 przy twardym blokerze.

```bash
hooks/miodek_write_gate.py plik.md notatka.txt
```

W roli `pre-commit` zatrzyma commit, gdy któryś plik prozy ma twardy bloker. Bezpieczeństwo: każda własna awaria bramki (brak pliku, błąd lintera, niepoprawny manifest) przepuszcza zapis (fail-open). Kontrakt pełny w `hooks/miodek_write_gate.schema.md`.

## Bramka CI na merge request

Druga bramka działa na pull requeście, nie przy zapisie. Workflow `.github/workflows/miodek-gate.yml` (GitHub Actions, trigger `pull_request`) liczy pliki prozy (`.md`/`.txt`) ZMIENIONE w PR względem bazy, woła na nich linter i FAIL-uje check przy PEŁNYM werdykcie. Sterownik to moduł `miodek.ci_gate`, wołany `python3 -m miodek.ci_gate` (zero zależności, czysta biblioteka standardowa plus git). To sterownik CI, więc świadomie nie ma go w dispatcherze `miodek`.

Kluczowa różnica wobec write-time. Bramka CI zatrzymuje cały pełny werdykt, czyli `FAIL` oraz `FAIL-HARD`, a więc także samą gęstość ponad próg, nie tylko twarde blokery. To odwrotna polityka niż write-time, która gęstość przepuszcza. Z tabeli trzech bramek (sekcja wyżej) bierze wiersz „CI”: pełny werdykt, łapie też samą gęstość. Trzecią bramkę, przed publikacją (z opcjonalnym osądem modelu Stage 2), opisuje sekcja „Bramka przed publikacją” niżej.

| Bramka | Polityka | Zakres |
|---|---|---|
| write-time | tylko twarde blokery, gęstość przechodzi | zapisywany plik, opt-in (`MIODEK_WRITE_GATE=1`) |
| CI na MR | pełny werdykt FAIL/FAIL-HARD, w tym sama gęstość | pliki prozy zmienione w PR względem bazy |
| przed publikacją | pełny werdykt Stage 1 plus opcjonalny osąd Stage 2 (opt-in, domyślnie wyłączony) | jawnie wskazane pliki do publikacji |

Zakres ograniczony do zmienionych plików jest celowy. Bramka FAIL-uje wyłącznie na prozie tkniętej w PR, nigdy na zastanym długu w plikach nieruszanych. Diff liczony jest symetrycznie od wspólnego przodka (`base...HEAD`, trzy kropki), kanon recenzji PR. Plik bez żadnej zmienionej prozy daje zielony check (exit 0), nie błąd.

Kody wyjścia `ci_gate.py` (równe kodom lintera):

| Exit | Znaczenie |
|---|---|
| 0 | brak zmienionych plików prozy LUB wszystkie PASS |
| 1 | którykolwiek zmieniony plik FAIL/FAIL-HARD (blokery lub gęstość) |
| 2 | błąd reguł/konfiguracji lintera lub błąd git/środowiska (bramka jakości nie zazielenia się po cichu) |

Użycie ręczne i w self-teście (jawne ścieżki):

```bash
python3 -m miodek.ci_gate plik.md notatka.txt        # exit 1 przy pełnym werdykcie FAIL
python3 -m miodek.ci_gate --changed --base origin/main   # tryb CI: diff względem bazy
```

W przeciwieństwie do write-time bramka CI nie jest fail-open: błąd reguł lub konfiguracji lintera kończy check niezerowo, bo to bramka jakości przed mergem. Self-test rdzenia: `tools/check_ci_gate.py` (wpięty do `tests/run_tests.sh`).

## Bramka przed publikacją

Trzecia i najsurowsza bramka to wymienny krok wołany PRZED publikacją prozy (wysyłka na Confluence, Notion lub stronę). Inny przepływ publikacji woła ją na jawnie wskazanych plikach „do publikacji”, żeby zatrzymać tekst nieprzechodzący jakości. Sterownik to podkomenda `miodek gate` (moduł `miodek.publish_gate`, zero zależności, czysta biblioteka standardowa). Bramka ma dwa poziomy.

Stage 1 działa zawsze. To pełny werdykt lintera na podanych plikach, ta sama polityka co bramka CI, tylko na jawnych plikach zamiast na diffie. Werdykt `FAIL` albo `FAIL-HARD` (blokery lub gęstość ponad próg) zamyka publikację. Stage 1 reużywa `ci_gate.filter_prose` i `ci_gate.run_linter`, więc polityka pełnego werdyktu jest jednym kodem dla bramki CI i bramki przed publikacją.

Stage 2 jest opcjonalny i włącza się flagą `--stage2`. Buduje manifest (`ai_linter.py --format json`), wybiera silnik osądu z `config.json` (sekcja `stage2`) przez `runner.build_engine_from_config` i woła `runner.run_stage2_managed` (osąd plus auto-offload poda RunPod dla silników zdalnych). Bramka jest surowa: jakikolwiek werdykt `rewrite` zamyka publikację. To realizuje zasadę „PASS z uwagami to NIE PASS”, więc bramka przed publikacją jako jedyna może dołożyć osąd modelu i jest tym surowsza niż bramka CI.

Czym bramka przed publikacją różni się od dwóch pozostałych bramek:

| Bramka | Polityka | Zakres | Model |
|---|---|---|---|
| write-time | tylko twarde blokery, gęstość przechodzi | zapisywany plik | nie |
| CI na MR | pełny werdykt Stage 1 | pliki prozy zmienione w PR | nie |
| przed publikacją | pełny werdykt Stage 1 plus opcjonalny osąd Stage 2 | jawnie wskazane pliki do publikacji | opcjonalnie (opt-in) |

Domyślnie bramka przed publikacją nie sięga sieci. Bez `--stage2` woła sam Stage 1, więc nie buduje silnika ani nie rusza modelu. Z `--stage2` na domyślnym configu (`stage2.engine` to `stub`) buduje atrapę `StubJudgeEngine`, czyli osąd offline bez sieci. Realny endpoint wymaga jawnej zmiany `config.json` na `openai` albo `ollama` (lub flagi `--engine`) oraz klucza w zmiennej środowiskowej. To znaczy: nawet z włączonym Stage 2 sieć rusza dopiero po świadomym wskazaniu żywego silnika.

Kody wyjścia `publish_gate.py`:

| Exit | Znaczenie |
|---|---|
| 0 | brak prozy LUB Stage 1 PASS i (Stage 2 wyłączony LUB gate PASS) |
| 1 | Stage 1 FAIL/FAIL-HARD (blokery lub gęstość) LUB Stage 2 gate FAIL (jakiś `rewrite`) |
| 2 | błąd reguł/konfiguracji lintera LUB błąd budowy silnika LUB niepoprawny manifest (bramka jakości nie zazielenia się po cichu) |

Wpięcie w przepływ publikacji i ręczne użycie:

```bash
miodek gate artykul.md notatka.txt          # sam Stage 1 (zero sieci)
miodek gate --stage2 artykul.md             # plus osąd Stage 2 (silnik z config.json)
miodek gate --stage2 --engine ollama art.md # Stage 2 na wskazanym silniku
```

Przepływ publikacji woła ten krok przed wysyłką i przerywa wysyłkę na kodzie niezerowym. Jak bramka CI, bramka przed publikacją nie jest fail-open: błąd reguł albo budowy silnika kończy się niezerowo, bo to bramka jakości. Self-test rdzenia: `tools/check_publish_gate.py` (wpięty do `tests/run_tests.sh`, w całości offline na atrapie silnika).

## Testy

Katalog `tests/` zawiera zestaw regresyjny:

- `run_tests.sh` — uruchamia linter na plikach bazowych i porównuje wynik z oczekiwaniami.
- `GROUND_TRUTH.md` — oczekiwane werdykty i trafienia dla każdego pliku testowego (oracle).
- Pliki bazowe z manieryzmem (`baseline_pl_raport.md`, `baseline_pl_intro.md`, `baseline_en_doc.md`, `baseline_en_cover_letter.md`) oraz plik kontrolny czystego tekstu (`control_pl_clean.md`), na którym linter ma zwrócić PASS bez false-positives.

Uruchomienie:

```bash
cd tests && ./run_tests.sh
```

## Ekonomia i obserwowalność (metryki z manifestu)

Linter zdejmuje pracę z modelu. Ile dokładnie, da się zmierzyć z samego manifestu, bez wołania LLM i bez kosztu tokenów. Granicą między etapami jest manifest, więc te metryki liczy się po stronie Stage 1. Moduł `metrics.py`, narzędzia w `tools/`.

Najpierw zbuduj manifest maszynowy, potem przepuść go przez narzędzie:

```bash
miodek lint --format json *.md > manifest.json
```

**Współczynnik redukcji (`tools/measure_reduction.py`).** Udział treści wejścia, której model NIE tyka. Treść routowana do Stage 2 to akapity z trafieniem klasy `review`. Punkt odniesienia z praktyki autora po wprowadzeniu lintera: routed rzędu 4 do 5 procent.

```bash
python3 tools/measure_reduction.py --manifest manifest.json
python3 tools/measure_reduction.py --manifest manifest.json --max-routed 0.10   # exit 1 gdy za dużo idzie do modelu
```

**Atrybucja pracy (`tools/measure_attribution.py`).** Która reguła i która warstwa generuje najwięcej trafień. Raport diagnostyczny, bez progu.

```bash
python3 tools/measure_attribution.py --manifest manifest.json
```

**Zdrowie ekonomii (`tools/measure_health.py`).** Bierze współczynnik routed i porównuje z progiem alarmu z `config.json` (sekcja `economy`). Gdy linter przestaje odsiewać, routed rośnie i alarm zapala się, zanim wyląduje w rachunku za tokeny. Exit 1 przy ALARM, więc nadaje się na bramkę w CI.

```bash
python3 tools/measure_health.py --manifest manifest.json
python3 tools/measure_health.py --manifest manifest.json --alarm 0.08    # nadpisz próg
```

### Eksporter metryk Prometheus i dashboard Grafany

Te same metryki da się podać na dashboard. Polecenie `miodek-exporter` (moduł `miodek.metrics_exporter`, osobny entry point) to eksporter HTTP zero-dep (biblioteka standardowa, `http.server`), który na ścieżce `/metrics` wystawia format tekstowy Prometheus. Czyta `--corpus`, `--port` i `--log` także ze zmiennych środowiskowych (`MIODEK_CORPUS`, `MIODEK_PORT`, `MIODEK_LOG`). Na scrape buduje manifest (uruchamia linter na korpusie, z krótkim cache, żeby nie mielić go na każde zapytanie), liczy `metrics.py` i doczytuje log Stage 2. Stack Prometheus plus Grafana zakładamy gotowy; tu dostarczamy artefakty do wpięcia.

```bash
miodek-exporter --corpus . --port 9112
curl -s localhost:9112/metrics | head
```

Serie: `miodek_reduction_ratio`, `miodek_routed_ratio`, `miodek_total_words`, `miodek_routed_words`, `miodek_hits_total{rule,klasa}`, `miodek_health` (1 OK, 0 ALARM) plus `miodek_health_na`, `miodek_routed_ratio_alarm_threshold`, `miodek_stage2_runs_total{engine,verdict}`, oraz zdrowie samego eksportera (`miodek_exporter_up`, `miodek_scrape_duration_seconds`). Konfiguracja przez zmienne środowiskowe (`MIODEK_CORPUS`, `MIODEK_PORT`, `MIODEK_LOG`, `MIODEK_PROFILE`, `MIODEK_DICT`).

Uczciwość danych: współczynnik redukcji, atrybucja per reguła i wskaźnik zdrowia są realne od zaraz (z manifestu Stage 1, zero kosztu modelu). Panel przebiegów Stage 2 wypełnia się dopiero, gdy realny silnik osądu nazbiera przebiegów; dziś osąd chodzi na atrapie, więc ta seria bywa pusta. To realny panel czekający na dane (żadna zaślepka).

Artefakty wdrożeniowe (jednostka systemd eksportera, fragment scrape do `prometheus.yml`, provider provisioningu i dashboard Grafany) leżą w `deploy/`. Runbook wdrożenia i pełen schemat metryk: `deploy/README.md` oraz `metrics-exporter.schema.md`.

**Runner Stage 2 (moduł `miodek.runner`, wołany `python3 -m miodek.runner`).** Spina linter z osądem modelu. Czyta manifest, wybiera segmenty `review` (tą samą funkcją co współczynnik redukcji), woła wymienialny silnik osądu i stosuje bramkę „PASS z uwagami to NIE PASS”. Domyślny silnik to deterministyczna atrapa (bez sieci); realny silnik wpina się przez `engines.JudgeEngine` bez zmian w runnerze.

```bash
python3 -m miodek.runner --manifest manifest.json        # exit 1 gdy bramka FAIL
```

**Realny silnik osądu (`engines.py`).** Domyślnie runner woła atrapę (bez kosztu, bez sieci). Realny model serwowany po HTTP wpina się przez dwa adaptery zero-dep (biblioteka standardowa, `urllib`), wybierane sekcją `stage2` w `config.json`. Klucz API czytany jest wyłącznie ze zmiennej środowiskowej (`api_key_env`), nigdy z pliku.

Endpoint zgodny z OpenAI Chat Completions (OpenRouter, vLLM, RunPod):

```json
"stage2": {
  "engine": "openai",
  "openai": { "base_url": "https://openrouter.ai/api/v1", "model": "speakleash/bielik-11b-v2.3-instruct",
              "api_key_env": "OPENROUTER_API_KEY", "extra_headers": {} }
}
```

```bash
export OPENROUTER_API_KEY=...                      # sekret czytany z ENV
python3 -m miodek.runner --manifest manifest.json --engine openai
```

Ollama (lokalna albo zdalna na RunPodzie) — `base_url` wskazuje host Ollamy:

```json
"stage2": { "engine": "ollama", "ollama": { "host": "http://localhost:11434", "model": "bielik" } }
```

```bash
python3 -m miodek.runner --manifest manifest.json --engine ollama
```

`--engine` na CLI nadpisuje wybór z configu; brak sekcji `stage2` znaczy atrapa (zero zmiany). Adaptery, prompt osądu i fail-safe parsowania opisuje `engines.schema.md`. Uwaga: realny smoke (Bielik) wymaga dostępnego endpointu, np. modelu serwowanego na RunPodzie; testy w repo działają w pełni offline na atrapie HTTP, bez wywołań sieci.

### Auto-offload poda RunPod po przebiegu Stage 2

Gdy model serwowany jest na podzie RunPod, pod może bić pod prąd GPU także między przebiegami osądu. Skill umie zgasić pod automatycznie po wsadzie Stage 2. Włącza się to podsekcją `lifecycle` w `stage2` (`config.json`); domyślnie `manage: false`, więc nic się nie dzieje (zero zmiany zachowania).

```json
"stage2": {
  "engine": "ollama",
  "ollama": { "host": "https://<pod>.runpod.net", "model": "bielik" },
  "lifecycle": {
    "manage": true,
    "pod_id": "<id-poda>",
    "on_finish": "stop",
    "idle_backstop_s": 600,
    "api_key_env": "RUNPOD_API_KEY"
  }
}
```

```bash
export RUNPOD_API_KEY=...                          # sekret WYŁĄCZNIE z ENV, nigdy z pliku
python3 -m miodek.runner --manifest manifest.json --engine ollama
```

Gdy `manage: true` i silnik jest zdalny (`ollama`/`openai`), runner owija przebieg w menedżer kontekstu, który gasi pod ZAWSZE po wsadzie. Odporność na padnięcie procesu zbudowano warstwowo: blok `finally` (gasi też przy wyjątku), handlery SIGINT/SIGTERM (gaszą przed zniknięciem procesu i przywracają poprzedni handler), oraz backstop NA PODZIE (`tools/runpod_idle_watchdog.sh`) gaszący pod po `idle_backstop_s` bezczynności na wypadek `kill -9`. Polityka `on_finish`: `stop` (domyślne, GPU gaśnie, model zostaje na dysku) albo `terminate` (trwała kasacja). Błąd gaszenia leci głośno na stderr, bo to bramka kosztowa. Klucz API czytany wyłącznie z ENV (`RUNPOD_API_KEY`). Szczegóły: `runpod-lifecycle.schema.md`; instalacja watchdoga na podzie: `tools/runpod_idle_watchdog.README.md`.

### Efemeryczny pod jednym krokiem: flaga `--runpod`

Flaga `--runpod` osądza tekst realnym Bielikiem w jednym kroku. Stawia efemeryczny pod z wolumenu sieciowego (model nie jest pobierany, jeśli już leży na wolumenie), uruchamia przebieg na realnym silniku (Ollama na podzie) i gasi pod automatycznie przez `terminate` po zakończeniu. Bez tej flagi pod stawia się ręcznie: `tools/runpod_pod_up.py`, wpis hosta do `config.json`, przebieg, wygaszenie.

Parametry poda czyta podsekcja `stage2.runpod` z `config.json` (wolumen, data center, model, GPU, mount, obraz) z bezpiecznymi domyślnymi, więc flaga działa od ręki. Cykl to create, czekanie na Ollamę, zapewnienie modelu, przebieg, terminate. Teardown jest gwarantowany tą samą warstwową odpornością co auto-offload (blok `finally`, handlery sygnałów, backstop na podzie), z dodatkowym sprzątaniem osieroconego poda: gdy Ollama nie wstanie albo modelu nie da się zapewnić w fazie wejścia, już utworzony pod jest terminowany przed zgłoszeniem błędu. Klucz API wyłącznie z ENV (`RUNPOD_API_KEY`).

```bash
python3 -m miodek.runner --manifest manifest.json --runpod            # osąd na świeżym efemerycznym Bieliku
miodek correct --file artykul.md --runpod                # korekta realnym Bielikiem, pod gaśnie sam
miodek gate --runpod artykul.md              # --runpod sam włącza Stage 2 na podzie
```

Flaga nadpisuje `--engine` i sekcję `lifecycle` (efemeryczny pod sam jest owijaczem przebiegu). Bez `--runpod` zachowanie jest bez zmian: domyślnie stub, zero sieci, zero kosztu. Szczegóły cyklu i testu offline: `runpod-lifecycle.schema.md` (sekcja „Tryb EFEMERYCZNY”); parametry poda: `config.schema.md` (podsekcja `stage2.runpod`).

### Routing silnika: lejek kosztowy

Stage 2 da się prowadzić dwoma silnikami naraz, żeby mocny model dotykał tylko trudnego marginesu. Silnik `routing` owija dwa silniki za tym samym interfejsem: `primary` (lekki, lokalny, na przykład Bielik przez Ollama) osądza każdy segment, a `appellate` (mocniejszy sędzia apelacyjny) jest wołany tylko po eskalacji. Domyślna polityka eskaluje, gdy primary chce ruszyć tekst (werdykt `rewrite`, czyli potencjalny fałszywy alarm) albo gdy segment jest trudny (liczba trafień review co najmniej `hard_hits_threshold`). Po eskalacji werdykt apelacji jest ostateczny, więc sędzia tnie fałszywe alarmy primary. Gdy primary daje `pass` na łatwym segmencie, appellate nie jest wołany. To obniża koszt rozumowy: mocny model dotyka tylko marginesu.

```json
"stage2": {
  "engine": "routing",
  "routing": {
    "escalate_on_rewrite": true,
    "hard_hits_threshold": 2,
    "primary":   { "engine": "ollama", "ollama": { "host": "http://localhost:11434", "model": "bielik" } },
    "appellate": { "engine": "openai", "openai": { "base_url": "https://openrouter.ai/api/v1", "model": "..." } }
  }
}
```

`primary` i `appellate` to pod-konfiguracje o tym samym kształcie co sekcja `stage2`, budowane rekurencyjnie. Routing jest jednopoziomowy: nie wolno zagnieżdżać `engine: "routing"` w primary ani appellate. Kontrakt routingu wobec auto-offloadu poda opisuje `engines.schema.md` (sekcja „Routing silnika”). Self-test offline na atrapach: `tools/check_routing.py`.

Schematy: `metrics.schema.md` (redukcja, atrybucja, zdrowie), `runner.schema.md` (kontrakt orkiestracji), `engines.schema.md` (kontrakt realnych adapterów silnika), `runpod-lifecycle.schema.md` (auto-offload poda RunPod), `decision-log.schema.md` (wspólny strumień zdarzeń runnera i logu decyzji).

## Korektor: pętla audyt, poprawka, ponowny audyt

Korektor (podkomenda `miodek correct`, moduł `miodek.corrector`) zamyka pętlę nad linterem i osądem modelu, więc narzędzie samo doprowadza tekst do czysta, a nie tylko wytyka manieryzm. Jedna iteracja to audyt (Stage 1 plus osąd Stage 2), przepisanie spornych akapitów przez silnik, zapis zwrotny przez adapter i ponowny audyt na poprawionym tekście.

Pętla zatrzymuje się w jednym z trzech przypadków. Pierwszy to PASS, czyli bramka Stage 2 nie zwraca już segmentów do przepisania. Drugi to brak postępu, gdy żadne przepisanie nie zmieniło tekstu w danej iteracji (ochrona przed pętlą bez końca). Trzeci to wyczerpanie limitu iteracji (domyślnie 4, konfigurowalne). Zwracany jest finalny tekst plus raport: liczba iteracji, czy osiągnięto PASS, powód zatrzymania, ślad ile segmentów poprawiono w każdej iteracji.

Silnik jest wymienny przez ten sam interfejs co osąd Stage 2. Korektor woła go wyłącznie przez `judge` i `rewrite`. Domyślny silnik z configu (`stub`) daje deterministyczną atrapę offline (`StubRewriteEngine`), która neutralizuje wykryty wzorzec tak, by ponowny audyt go nie łapał, więc pętla zbiega bez sieci. Realny model (`openai`/`ollama`) wpina się bez zmiany pętli: dostaje osobny prompt po polsku „przepisz akapit usuwając manieryzm, zachowaj sens i rejestr”.

```bash
miodek correct --file artykul.md --engine ollama  # korekta realnym modelem (sieć)
miodek correct --file artykul.md --runpod         # realny Bielik na efemerycznym podzie
miodek correct --file artykul.md --runpod --in-place  # plus zapis poprawionego tekstu do pliku
```

Bramka UX: korektor mieli tekst, więc na atrapie (stub) nic realnie nie poprawi i nie wolno mu udawać pracy. Bez `--runpod` i bez jawnie wskazanego realnego silnika (`stage2.engine` na `ollama`/`openai` w `config.json` albo `--engine ollama/openai`) korektor odmawia z kodem wyjścia 2 i kieruje: użyj `--runpod` (efemeryczny Bielik jednym krokiem) albo ustaw realny silnik. Stub zostaje trybem testowym, nie ścieżką użytkownika (furtka self-testów: zmienna `MIODEK_ALLOW_STUB_CORRECTOR=1`). Runner i bramka publikacji tej odmowy nie mają, bo osąd na atrapie bywa tam legalny jako diagnostyka. Odmowa dotyczy tylko korektora, który przepisuje tekst.

Zakres korektora to proza klasy review. Twarde blokery Stage 1 spoza prozy zostają nietknięte: emoji w nagłówku, cyrylica czy struktura nie-akapitowa to robota lintera i autora, bo korektor przepisuje wyłącznie sporne akapity. Dlatego dokument z czystą już prozą, ale z emoji w nagłówku, da PASS na bramce Stage 2 korektora i wciąż FAIL na pełnym werdykcie lintera. To podział celowy.

Jakość przepisania zależy od silnika. Atrapa offline (`stub`) neutralizuje wzorzec deterministycznie, więc pętla zbiega bez sieci i nadaje się do testów potoku, ale jej wynik tekstowy bywa pokaleczony (wycina dopasowany fragment). Naturalne przepisanie daje dopiero realny model za interfejsem, na przykład Bielik przez Ollama lub model z półki przez OpenRouter. Pełny smoke z żywym endpointem jest osobnym krokiem.

Dwa wzmocnienia chronią pętlę przed gadatliwym modelem. Parser odpowiedzi (`clean_rewrite_reply`) odcina meta-preambuły i komentarze, na przykład „Poprawiona wersja:” czy „Oto poprawiony akapit:”, a gdy model poda dwie wersje, bierze pierwszy zwarty akapit prozy. Zestaw fraz jest zamknięty i etykieta musi być krótka, więc legalne zdanie z dwukropkiem nie jest zjadane; pusta lub bezsensowna odpowiedź wciąż daje fallback na oryginał. Strażnik regresji po każdym przepisaniu robi tani audyt Stage 1 obu wersji akapitu i odrzuca poprawkę, która pogarsza, czyli ma więcej trafień lub dokłada bloker. Realny model bywa „leczy chorobę, dokłada gorączkę”: przepisując dorzuca nowy manieryzm. Strażnik akceptuje tylko poprawki nie pogarszające, dzięki czemu taki rozjazd kończy się brakiem postępu zamiast biegu do limitu iteracji. Zmiana neutralna przechodzi, więc realny postęp bez zbieżności nadal trafia na limit.

Flagi korektora: `--file` (plik wejściowy), `--engine` (silnik osądu, np. `ollama`, `openai`), `--runpod` (efemeryczny pod z Bielikiem na czas korekty), `--in-place` (zapis poprawy z powrotem do pliku zamiast na stdout), `--max-iter N` (limit iteracji pętli; domyślnie `stage2.max_iter` z `config.json`), oraz `--lang`, `--profile`, `--dict`, `--config` (jak w linterze).

Finalny tekst leci na stdout, raport na stderr. Exit 0, gdy osiągnięto PASS, 1 w przeciwnym razie (gate-owalne). Kontrakt pętli, mapowanie segmentu na edycję i warunki zatrzymania opisuje `corrector.schema.md`; zdolność `rewrite` w silniku jest w `engines.schema.md`. Self-test offline: `tools/check_corrector.py` (wpięty do `tests/run_tests.sh`).

## LanguageTool: pełna korekta polszczyzny na żądanie

Rdzeń skilla jest lekki i celuje w manieryzm AI. Czasem przyda się pełna korekta polszczyzny: literówki, gramatyka, interpunkcja. Do tego jest opcjonalny dostawca na żądanie: klient LanguageTool (`languagetool.py`). To narzędzie pomocnicze poza bramką. Nie jest częścią Stage 1, Stage 2 ani żadnej bramki jakości i nie odpala się nigdzie automatycznie. Operator uruchamia je świadomie, gdy chce drugiej pary oczu nad polszczyzną.

```bash
miodek lt --file artykul.md
miodek lt --text "Mam pewien błont ortograficzny."
miodek lt --file artykul.md --json
miodek lt --text "..." --endpoint http://localhost:8081/v2/check
LANGUAGETOOL_ENDPOINT=http://localhost:8081/v2/check miodek lt --file artykul.md
```

Klient jest zero-dep (biblioteka standardowa, `urllib`) i odpytuje serwer LanguageTool po HTTP. Endpoint wybiera priorytet: flaga `--endpoint`, potem zmienna środowiskowa `LANGUAGETOOL_ENDPOINT`. Domyślnego endpointu NIE ma: bez wyboru klient zgłasza błąd, więc nie wysyła tekstu nigdzie domyślnie. Operator świadomie wskazuje jedną z dwóch dróg: lokalny serwer (np. `http://localhost:8081/v2/check`, tekst zostaje u niego) albo publiczne `api.languagetool.org` (wysyła tekst na cudze serwery). Wzór w `.env.example`. Wejście wskazujesz flagą `--file` albo `--text`, kod języka flagą `--language` (domyślnie `pl-PL`), a `--json` daje wyjście maszynowe. Zwraca strukturalne sugestie: pozycja, długość, komunikat, proponowane zamienniki, identyfikator reguły i kategorii. Parsowanie odpowiedzi jest odporne na brak pól. Realny serwer jest wołany wyłącznie przy faktycznym uruchomieniu; self-test (`tools/check_languagetool.py`) działa w pełni offline na atrapie transportu, bez wywołań sieci. Kontrakt: `languagetool.schema.md`.

## Opcjonalna warstwa terminologii domenowej

Niektóre terminy branżowe wyglądają jak manieryzm AI, choć w danej dziedzinie są poprawne (na przykład „robust” jako nazwa produktu albo „leverage” w finansach). Słownik domenowy pozwala je oznaczyć, żeby linter ich nie flagował. To warstwa nadrzędna nad regułami: gdy słownik mówi `allow`, trafienie markera na ten termin jest pomijane.

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

Dopasowanie idzie po całym słowie, bez względu na wielkość liter. Wskazujesz słownik flagą `--dict`:

```bash
miodek lint --dict slownik.json --lang both ŚCIEŻKA_DO_PLIKU.md
```

Bez słownika skill działa w trybie ogólnym: pełny audyt polszczyzny i manieryzmu AI. Słownik użytkownika jest zwykle zewnętrzny, dopasowany do jego dziedziny. Szkic można zbudować z własnego korpusu narzędziem `tools/build_dict.py` (świadomie poza paczką, dla dewelopera): częstość proponuje kandydatów, a człowiek decyduje, co trafi do `allow`.

Repo zawiera własny słownik projektu `dictionary.project.json` (dogfooding). Oznacza terminy, które linter łapie jako manieryzm, choć w tej dokumentacji są poprawne, na przykład `robust` i `leverage` użyte jako przykłady terminów branżowych. Audyt z tym słownikiem wygasza te trafienia:

```bash
miodek lint --dict dictionary.project.json --lang both README.md
```

```bash
python3 tools/build_dict.py ./korpus --out slownik.json
```

## Atrybucja i licencja

Autor oryginalnego skilla: **Tomasz Jakubowski** (upstream: [github.com/researchanddeploy/sztuczny-miodek](https://github.com/researchanddeploy/sztuczny-miodek)). To repozytorium rozwija jego narzędzie jako fork zgodny z licencją MIT.

Kod, taksonomia AI-tellów, reguły polszczyzny i układ skilla: licencja **MIT** (zob. plik `LICENSE`).

Metodologia opiera się na pracy **Jana Miodka** (pragmatyczny puryzm, „Ojczyzna polszczyzna”). To referencja i atrybucja, nie redystrybucja chronionej treści. Licencja MIT obejmuje wyłącznie materiały tego repozytorium; nie rozciąga się na cudzą własność intelektualną, do której repo się odwołuje.
