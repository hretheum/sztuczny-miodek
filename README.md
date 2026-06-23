# sztuczny-miodek

Skill Claude Code do audytu polszczyzny i eradykacji manieryzmu AI (AI-tellów) w tekstach polskich i angielskich. Metodologia: pragmatyczny puryzm Jana Miodka.

## Co robi

Skill realizuje dwie misje:

1. **Wzorcowa polszczyzna (PL)** — pełny audyt tekstu polskiego wg dziesięciu priorytetów: cyrylica, kalki angielskie, fałszywi przyjaciele, anglicyzmy, sztuczne kolokacje, interpunkcja, styl i gramatyka, ortografia terminów łacińskich/greckich, manieryzm AI, typografia.
2. **Usuwanie AI-tellów (PL + EN)** — wykrywa i usuwa manieryzmy generatywne: puste signposty, triady (rule-of-three), antytezę „nie X — to Y", paralelizm, nadużycie myślnika, puste superlatywy, klisze redefinicyjne, emoji w nagłówkach. Dla raportów, syntez, listów motywacyjnych, CV i dokumentacji.

Skill działa jako **twarda bramka jakości** przed deklaracją „done". Obowiązuje semantyka **„PASS z uwagami = NIE PASS"**: każdy nierozwiązany flag blokuje werdykt PASS. Werdykt FAIL zapada przy cyrylicy w tekście PL (FAIL-HARD), markerze klasy `block` po przekroczeniu progu albo gęstości ważonej trafień powyżej 8 na 500 słów.

Zasada Miodka: poprawiaj to, co ma polski odpowiednik; zachowuj to, co przyjęło się w danej dziedzinie. Dla manieryzmu AI: zmieniaj teksturę prozy, zachowuj fakty i metryki.

## Kluczowe funkcje

**Deterministyczny linter `ai_linter.py` (Stage 1).** Pre-scan bez kosztu tokenów LLM. Generuje manifest podejrzeń w formacie `plik:linia:ID:KLASA:fragment` plus blok `== SUMMARY ==` z liczbą słów, trafień, maksymalną liczbą myślników na akapit, gęstością i werdyktem. Linter łapie szeroko (wysoki recall), świadomie dopuszcza false-positives w klasie `review`. Wyłącznie biblioteka standardowa Pythona 3, zero zależności pip.

**Osąd kontekstowy (Stage 2).** Dla każdego trafienia z manifestu: przeczytaj pełne zdanie, rozstrzygnij czy to realny manieryzm czy uzasadnienie kontekstowe, nanieś poprawkę, zweryfikuj kolokację po zamianie, wystaw werdykt. Wzorzec manifest → celowany Edit oszczędza około 60% tokenów względem czytania całych plików.

**Kanon 14 kategorii manieryzmu (`manieryzm-ai.md`).** Źródło prawdy taksonomii. Każde ID kategorii ma odpowiednik w linterze. Kategorie PL: PL-SIGN, PL-CLICHE, PL-RHET, PL-RHYTHM, PL-HEDGE, PL-TYPO. Kategorie EN: EN-DASH, EN-ANTI, EN-TRIAD, EN-PARA, EN-CLICHE, EN-HEDGE, EN-SUPER, EN-CONCL.

**Priorytety 1–10 (`SKILL.md`).** Ranking wykrywania błędów polszczyzny, od cyrylicy (Priorytet 1) przez sztuczne kolokacje (Priorytet 5, „najczęściej przeoczana kategoria") i interpunkcję (Priorytet 6) po typografię (Priorytet 10). Każdy priorytet ma tabelę wzorców z poprawkami i regexami skanowania.

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

## Użycie

### W Claude Code

Skill uruchamia się przez jeden z wyzwalaczy w rozmowie:

- `sprawdź polszczyznę`
- `sztuczny miodek`
- `audyt językowy`
- `korekta tekstu`, `manieryzm AI`, `AI-tell`, `de-AI`, `usuń ślady AI`, `odAI-uj`

Claude przeprowadzi pełny protokół: pre-scan linterem, osąd kontekstowy, korektę, przebieg weryfikacyjny i werdykt PASS/FAIL.

### Linter z linii poleceń

Pre-scan można uruchomić samodzielnie:

```bash
python3 ai_linter.py --lang both ŚCIEŻKA_DO_PLIKU.md
```

Flaga `--lang` przyjmuje `pl`, `en` lub `both`. Można podać kilka ścieżek naraz.

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

## Bramka CI na merge request (F2)

Druga bramka działa na pull requeście, nie przy zapisie. Workflow `.github/workflows/miodek-gate.yml` (GitHub Actions, trigger `pull_request`) liczy pliki prozy (`.md`/`.txt`) ZMIENIONE w PR względem bazy, woła na nich `ai_linter.py` i FAIL-uje check przy PEŁNYM werdykcie. Sterownik to `tools/ci_gate.py` (zero zależności, czysta biblioteka standardowa plus git).

Kluczowa różnica wobec write-time. Bramka CI zatrzymuje cały pełny werdykt, czyli `FAIL` oraz `FAIL-HARD`, a więc także samą gęstość ponad próg, nie tylko twarde blokery. To odwrotna polityka niż write-time, która gęstość przepuszcza. Z tabeli trzech bramek (sekcja wyżej) bierze wiersz „CI": pełny werdykt, łapie też samą gęstość. Trzecia bramka, przed publikacją (osąd modelu Stage 2), jeszcze nie istnieje.

| Bramka | Polityka | Zakres |
|---|---|---|
| write-time (F1) | tylko twarde blokery, gęstość przechodzi | zapisywany plik, opt-in (`MIODEK_WRITE_GATE=1`) |
| CI na MR (F2) | pełny werdykt FAIL/FAIL-HARD, w tym sama gęstość | pliki prozy zmienione w PR względem bazy |
| przed publikacją (F3) | pełny werdykt plus osąd modelu | jeszcze nie ma |

Zakres ograniczony do zmienionych plików jest celowy. Bramka FAIL-uje wyłącznie na prozie tkniętej w PR, nigdy na zastanym długu w plikach nieruszanych. Diff liczony jest symetrycznie od wspólnego przodka (`base...HEAD`, trzy kropki), kanon recenzji PR. Plik bez żadnej zmienionej prozy daje zielony check (exit 0), nie błąd.

Kody wyjścia `ci_gate.py` (równe kodom lintera):

| Exit | Znaczenie |
|---|---|
| 0 | brak zmienionych plików prozy LUB wszystkie PASS |
| 1 | którykolwiek zmieniony plik FAIL/FAIL-HARD (blokery lub gęstość) |
| 2 | błąd reguł/konfiguracji lintera lub błąd git/środowiska (bramka jakości nie zazielenia się po cichu) |

Użycie ręczne i w self-teście (jawne ścieżki):

```bash
python3 tools/ci_gate.py plik.md notatka.txt        # exit 1 przy pełnym werdykcie FAIL
python3 tools/ci_gate.py --changed --base origin/main   # tryb CI: diff względem bazy
```

W przeciwieństwie do write-time bramka CI nie jest fail-open: błąd reguł lub konfiguracji lintera kończy check niezerowo, bo to bramka jakości przed mergem. Self-test rdzenia: `tools/check_ci_gate.py` (wpięty do `tests/run_tests.sh`).

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
python3 ai_linter.py --format json *.md > manifest.json
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

**Runner Stage 2 (`runner.py`).** Spina linter z osądem modelu. Czyta manifest, wybiera segmenty `review` (tą samą funkcją co współczynnik redukcji), woła wymienialny silnik osądu i stosuje bramkę „PASS z uwagami to NIE PASS". Domyślny silnik to deterministyczna atrapa (bez sieci); realny silnik wpina się przez `engines.JudgeEngine` bez zmian w runnerze.

```bash
python3 runner.py --manifest manifest.json        # exit 1 gdy bramka FAIL
```

Schematy: `metrics.schema.md` (redukcja, atrybucja, zdrowie), `runner.schema.md` (kontrakt orkiestracji), `decision-log.schema.md` (wspólny strumień zdarzeń runnera i logu decyzji).

## Opcjonalna warstwa terminologii domenowej

Skill obsługuje opcjonalny tryb z własnym słownikiem terminów branżowych. Jeśli posiadasz taki plik, terminy w nim zdefiniowane mają pierwszeństwo nad ogólnymi regułami dla swojej dziedziny. Bez słownika skill działa w trybie ogólnym: pełny audyt polszczyzny i manieryzmu AI. Słownik domenowy jest zewnętrzny i nie wchodzi w skład repozytorium.

## Atrybucja i licencja

Kod, taksonomia AI-tellów, reguły polszczyzny i układ skilla: licencja **MIT** (zob. plik `LICENSE`).

Metodologia opiera się na pracy **Jana Miodka** (pragmatyczny puryzm, „Ojczyzna polszczyzna"). To referencja i atrybucja, nie redystrybucja chronionej treści. Licencja MIT obejmuje wyłącznie materiały tego repozytorium; nie rozciąga się na cudzą własność intelektualną, do której repo się odwołuje.
