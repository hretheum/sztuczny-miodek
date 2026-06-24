# Stage 2: osąd modelu, silniki, korekta

Po deterministycznym linterze Stage 1 przychodzi osąd kontekstowy modelu: runner, wymienne silniki, auto-offload poda RunPod, routing apelacyjny, korektor zamykający pętlę do PASS oraz LanguageTool na żądanie.

## Runner Stage 2 i silniki

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

`--engine` na CLI nadpisuje wybór z configu; brak sekcji `stage2` znaczy atrapa (zero zmiany). Adaptery, prompt osądu i fail-safe parsowania opisuje `engines.schema.md`. Uwaga: realny smoke (Bielik) wymaga dostępnego endpointu, np. modelu serwowanego na RunPodzie. Testy w repo działają w pełni offline na atrapie HTTP, bez wywołań sieci.

## Auto-offload poda RunPod po przebiegu Stage 2

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

## Efemeryczny pod jednym krokiem: flaga `--runpod`

Flaga `--runpod` osądza tekst realnym Bielikiem w jednym kroku. Stawia efemeryczny pod z wolumenu sieciowego (model nie jest pobierany, jeśli już leży na wolumenie), uruchamia przebieg na realnym silniku (Ollama na podzie) i gasi pod automatycznie przez `terminate` po zakończeniu. Bez tej flagi pod stawia się ręcznie: `tools/runpod_pod_up.py`, wpis hosta do `config.json`, przebieg, wygaszenie.

Parametry poda czyta podsekcja `stage2.runpod` z `config.json` (wolumen, data center, model, GPU, mount, obraz) z bezpiecznymi domyślnymi, więc flaga działa od ręki. Cykl to create, czekanie na Ollamę, zapewnienie modelu, przebieg, terminate. Teardown jest gwarantowany tą samą warstwową odpornością co auto-offload (blok `finally`, handlery sygnałów, backstop na podzie), z dodatkowym sprzątaniem osieroconego poda: gdy Ollama nie wstanie albo modelu nie da się zapewnić w fazie wejścia, już utworzony pod jest terminowany przed zgłoszeniem błędu. Klucz API wyłącznie z ENV (`RUNPOD_API_KEY`).

```bash
python3 -m miodek.runner --manifest manifest.json --runpod            # osąd na świeżym efemerycznym Bieliku
miodek correct --file artykul.md --runpod                # korekta realnym Bielikiem, pod gaśnie sam
miodek gate --runpod artykul.md              # --runpod sam włącza Stage 2 na podzie
```

Flaga nadpisuje `--engine` i sekcję `lifecycle` (efemeryczny pod sam jest owijaczem przebiegu). Bez `--runpod` zachowanie jest bez zmian: domyślnie stub, zero sieci, zero kosztu. Szczegóły cyklu i testu offline: `runpod-lifecycle.schema.md` (sekcja „Tryb EFEMERYCZNY”); parametry poda: `config.schema.md` (podsekcja `stage2.runpod`).

## Routing silnika: lejek kosztowy

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

Korektor (podkomenda `miodek correct`, moduł `miodek.corrector`) zamyka pętlę nad linterem i osądem modelu. Narzędzie samo doprowadza tekst do czysta, zamiast tylko wytykać manieryzm. Jedna iteracja to audyt (Stage 1 plus osąd Stage 2), przepisanie spornych akapitów przez silnik, zapis zwrotny przez adapter i ponowny audyt na poprawionym tekście.

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

[← Powrót do README](../README.md)
