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
- [Dokumentacja](#dokumentacja)
- [Atrybucja i licencja](#atrybucja-i-licencja)

## Co robi

Skill realizuje dwie misje:

1. **Wzorcowa polszczyzna (PL)** — pełny audyt tekstu polskiego wg dziesięciu priorytetów: cyrylica, kalki angielskie, fałszywi przyjaciele, anglicyzmy, sztuczne kolokacje, interpunkcja, styl i gramatyka, ortografia terminów łacińskich/greckich, manieryzm AI, typografia.
2. **Usuwanie AI-tellów (PL + EN)** — wykrywa i usuwa manieryzmy generatywne: puste signposty, triady (rule-of-three), antytezę „nie X — to Y”, paralelizm, nadużycie myślnika, puste superlatywy, klisze redefinicyjne, emoji w nagłówkach. Dla raportów, syntez, listów motywacyjnych, CV i dokumentacji.

Skill działa jako **twarda bramka jakości** przed deklaracją „done”. Obowiązuje semantyka **„PASS z uwagami = NIE PASS”**: każdy nierozwiązany flag blokuje werdykt PASS. Werdykt FAIL zapada przy cyrylicy w tekście PL (FAIL-HARD), markerze klasy `block` po przekroczeniu progu albo gęstości ważonej trafień powyżej 8 na 500 słów.

Zasada Miodka: poprawiaj to, co ma polski odpowiednik; zachowuj to, co przyjęło się w danej dziedzinie. Dla manieryzmu AI: zmieniaj teksturę prozy, zachowuj fakty i metryki.

## Kluczowe funkcje

- **Deterministyczny linter (Stage 1).** Wykrywa manieryzm bez kosztu tokenów LLM, na samej bibliotece standardowej Pythona. Łapie szeroko, a niepewne trafienia oznacza do przeglądu.
- **Opcjonalny osąd modelu (Stage 2).** Rozstrzyga niepewne trafienia w kontekście całego zdania i nanosi poprawkę tylko tam, gdzie trzeba.
- **Kanon manieryzmu PL i EN.** Czternaście kategorii ze wspólnym źródłem w `manieryzm-ai.md`, każda z odpowiednikiem w linterze.
- **Pełny audyt polszczyzny.** Priorytety od cyrylicy po typografię, wedle pragmatycznego puryzmu Jana Miodka (szczegóły w `SKILL.md`).

Format manifestu i czytanie werdyktu opisuje sekcja [Interpretacja manifestu i werdyktu](#interpretacja-manifestu-i-werdyktu).

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

`uvx` pobiera paczkę do cache i uruchamia ulotnie, bez instalowania niczego na stałe. Polecenie `miodek` to dispatcher z podkomendami `lint`, `correct`, `gate`, `lt` oraz `build-dict`. Eksporter metryk Prometheus jest osobnym poleceniem `miodek-exporter`.

Alternatywnie, wprost ze źródła git (np. dla gałęzi roboczej przed wydaniem na PyPI):

```bash
uvx --from git+https://github.com/hretheum/sztuczny-miodek@epic-a-reguly-jako-dane \
  miodek lint --lang both ŚCIEŻKA_DO_PLIKU.md
```

Czysty skill (tryby A i B) żyje w Claude Code: wywołujesz go w rozmowie, a model prowadzi audyt i korektę. Tryb C wynosi te same reguły poza Claude Code, do terminala i do potoku CI, jako samodzielne polecenie. Co daje:

- działa poza Claude Code, w dowolnym terminalu i w potoku CI, bez asystenta;
- batch na całych katalogach i wzorcach glob z jednym zbiorczym kodem wyjścia ([Użycie z CLI](docs/usage.md));
- trzy [bramki jakości](docs/gates.md) jako kroki automatyzacji;
- [osąd modelu Stage 2](docs/stage2.md) z routingiem silników oraz korektor do werdyktu PASS;
- budowa [słownika domenowego](docs/dictionary.md) podkomendą `miodek build-dict`;
- [eksporter metryk Prometheus](docs/observability.md) jako polecenie `miodek-exporter`.

Rdzeń nie ma żadnych zależności (sama biblioteka standardowa). Warstwy opcjonalne wydzielają extras `[exporter]` i `[lt]`, dziś puste, bo wszystkie komponenty działają na bibliotece standardowej. Powiązanie z homelabem (quadlet, systemd) zostaje poza paczką.

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

Flaga `--lang` przyjmuje `pl`, `en` lub `both`. Można podać kilka ścieżek naraz. Audyt całych katalogów i wzorców glob, raport zbiorczy `--report` oraz pozostałe flagi opisuje [Użycie z CLI: batch i flagi](docs/usage.md).

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

## Dokumentacja

Pełny opis warstw zaawansowanych żyje w katalogu `docs/`. Pełną listę flag każdej komendy pokazuje `miodek <komenda> --help`.

- [Użycie z CLI: batch i flagi](docs/usage.md) — audyt katalogów, wzorce glob, raport zbiorczy, profile i format wyjścia.
- [Bramki jakości](docs/gates.md) — trzy bramki: przy zapisie pliku, na merge request, przed publikacją.
- [Stage 2: osąd modelu, silniki, korekta](docs/stage2.md) — runner, wymienne silniki, RunPod, routing apelacyjny, korektor, LanguageTool.
- [Ekonomia i obserwowalność](docs/observability.md) — współczynnik redukcji, metryki z manifestu, eksporter Prometheus i dashboard.
- [Słownik domenowy](docs/dictionary.md) — warstwa terminologii, format JSON, budowa przez `miodek build-dict`.
- [Audyt stron Confluence](docs/confluence.md) — `miodek confluence pull`, czysta proza przez adapter (read-only).
- [Interfejs adaptera](docs/ADAPTER-INTERFACE.md) — adaptery wejścia i wyjścia, segmentacja.
- [Kalibracja progów](docs/THRESHOLD-CALIBRATION.md) — metodyka strojenia progów na korpusie.
- [Współtworzenie](CONTRIBUTING.md) — bramka jakości, testy, styl, pull requesty.
- [Changelog](CHANGELOG.md) — historia wersji.

## Atrybucja i licencja

Autor oryginalnego skilla: **Tomasz Jakubowski** (upstream: [github.com/researchanddeploy/sztuczny-miodek](https://github.com/researchanddeploy/sztuczny-miodek)). To repozytorium rozwija jego narzędzie jako fork zgodny z licencją MIT.

Kod, taksonomia AI-tellów, reguły polszczyzny i układ skilla: licencja **MIT** (zob. plik `LICENSE`).

Metodologia opiera się na pracy **Jana Miodka** (pragmatyczny puryzm, „Ojczyzna polszczyzna”). To referencja i atrybucja, nie redystrybucja chronionej treści. Licencja MIT obejmuje wyłącznie materiały tego repozytorium; nie rozciąga się na cudzą własność intelektualną, do której repo się odwołuje.
