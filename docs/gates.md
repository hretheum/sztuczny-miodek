# Bramki jakości

Skill daje trzy bramki jakości na różnych etapach pracy: przy zapisie pliku, na merge request i przed publikacją. Tabela poniżej zbiera ich polityki i zakresy w jednym miejscu, a sekcje dalej opisują każdą z osobna.

| Bramka | Polityka | Zakres | Model |
|---|---|---|---|
| write-time | tylko twarde blokery, gęstość przechodzi | zapisywany plik, opt-in (`MIODEK_WRITE_GATE=1`) | nie |
| CI na MR | pełny werdykt FAIL/FAIL-HARD, w tym sama gęstość | pliki prozy zmienione w PR względem bazy | nie |
| przed publikacją | pełny werdykt Stage 1 plus opcjonalny osąd Stage 2 | jawnie wskazane pliki do publikacji | opcjonalnie (opt-in) |

## Bramka write-time (hook na zapisie pliku)

Bramka write-time uruchamia linter przy każdym zapisie pliku prozy (`.md`/`.txt`) i zatrzymuje pracę WYŁĄCZNIE przy twardych blokerach.

Niuans: sama wysoka gęstość trafień klasy `review` (czyli `verdict == FAIL` przy zerze blokerów) NIE zatrzymuje write-time, daje co najwyżej ostrzeżenie. Dzięki temu codzienna edycja nie jest przerywana z powodu gęstości. Twarde blokery (cyrylica, em-dash od trzech na akapit, emoji w nagłówku, serie antytez) zatrzymują pracę od razu.

### Włączenie hooka w pluginie (opt-in)

Plugin deklaruje hook `PostToolUse` na `Write|Edit|MultiEdit` w `hooks/hooks.json`, ale w trybie hooka jest on bierny do jawnego włączenia. Sama instalacja pluginu nie blokuje nikomu edycji. Aktywacja zmienną środowiskową:

```bash
export MIODEK_WRITE_GATE=1   # albo true / on / yes
```

Przy twardym blokerze hook blokuje zapis dwoma kanałami naraz, dla odporności na wersję Claude Code. Na stdout wypisuje JSON z polem `decision: block` i powodem (oraz lustrzane `hookSpecificOutput.permissionDecision: deny`), a równolegle kończy kodem 2 z tym samym powodem na stderr (kanon PostToolUse, stderr wraca do agenta). Powód to lista blokerów: ID markera, numer linii, fragment, żeby agent wiedział, co poprawić. Sama wysoka gęstość przechodzi (exit 0, brak wyjścia). Bez ustawionej zmiennej hook kończy natychmiast bez działania.

### Użycie jako git pre-commit

Skrypt działa też z linii poleceń, bez zmiennej środowiskowej, bo jawne wywołanie to świadoma decyzja. Bierze ścieżki z argumentów, kończy kodem 1 przy twardym blokerze.

```bash
hooks/miodek_write_gate.py plik.md notatka.txt
```

W roli `pre-commit` zatrzyma commit, gdy któryś plik prozy ma twardy bloker. Bezpieczeństwo: każda własna awaria bramki (brak pliku, błąd lintera, niepoprawny manifest) przepuszcza zapis (fail-open). Kontrakt pełny w `hooks/miodek_write_gate.schema.md`.

## Bramka CI na merge request

Druga bramka działa na pull requeście, nie przy zapisie. Workflow `.github/workflows/miodek-gate.yml` (GitHub Actions, trigger `pull_request`) liczy pliki prozy (`.md`/`.txt`) ZMIENIONE w PR względem bazy, woła na nich linter i FAIL-uje check przy PEŁNYM werdykcie. Sterownik to moduł `miodek.ci_gate`, wołany `python3 -m miodek.ci_gate` (zero zależności, czysta biblioteka standardowa plus git). To sterownik CI, więc świadomie nie ma go w dispatcherze `miodek`.

Kluczowa różnica wobec write-time: bramka CI zatrzymuje cały pełny werdykt, czyli `FAIL` oraz `FAIL-HARD`, a więc także samą gęstość ponad próg. To odwrotna polityka niż write-time, która gęstość przepuszcza.

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

[← Powrót do README](../README.md)
