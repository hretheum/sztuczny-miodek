# Schemat adapterów silnika Stage 2 — kontrakt realnych silników osądu (KAN-218)

Realne adaptery silnika osądu Stage 2 za interfejsem `engines.JudgeEngine`. Dziś istnieje atrapa
`StubJudgeEngine` (bez LLM, bez sieci); KAN-218 dokłada DWA realne adaptery, które gadają z modelem
serwowanym po HTTP (np. Bielik na RunPodzie). Oba ZERO-DEP (biblioteka standardowa: `urllib.request`,
`json`, `os`, `re`). Bez `requests`, bez SDK.

Komplement do `runner.schema.md` (orkiestracja) i `config.schema.md` (sekcja `stage2`).

## Kontrakt bazowy (nietknięty)

Runner zna TYLKO `JudgeEngine.name` (atrybucja E2/E3) i `JudgeEngine.judge(segment) -> Judgement`.
Realny silnik nadpisuje regułę atrapy faktyczną oceną modelu, zachowując ten kontrakt:

- `ReviewSegment(file, seg_index, line, text, hits: list[dict])`, `.hit_ids() -> [id, ...]`.
- `Judgement(verdict, notes, engine)`, `verdict ∈ {"pass", "rewrite"}` (walidacja w `__post_init__`).
- Bramka „PASS z uwagami to NIE PASS": cokolwiek do ruchu => `"rewrite"`.

## Zdolność `rewrite` (G2 — korektor)

`JudgeEngine.rewrite(segment, judgement) -> str` to ROZSZERZENIE kontraktu (nie metoda abstrakcyjna):
domyślna implementacja jest NO-OP (`return segment.text`), więc istniejące silniki tylko-osądzające
(StubJudgeEngine, realne adaptery sprzed G2) nie pękają. Pętla korektora (`corrector.py`) traktuje
zwrot równy oryginałowi jako BRAK POSTĘPU i zatrzymuje się, zamiast psuć tekst.

- `StubRewriteEngine` (podklasa `StubJudgeEngine`) — atrapa KOREKTORA, deterministyczna, bez sieci.
  `judge` dziedziczy (review → rewrite); `rewrite` przez `neutralize_match` usuwa KAŻDY wykryty
  wzorzec tak, by ponowny audyt go nie łapał (triada „A, B i C” → „A i C”; antyteza „X, a nie Y” →
  usunięcie spójnika; reszta → usunięcie dopasowanego fragmentu). Match nie do przypięcia →
  tekst bez zmian (= brak postępu → STOP w pętli, nigdy nieskończona pętla). `StubJudgeEngine`
  zostaje atrapą TYLKO-osądzającą (jej `rewrite` to no-op z bazy — testy G1 nietknięte).
- `OpenAICompatEngine` / `OllamaEngine` — nadpisują `rewrite`: osobny prompt PO POLSKU
  (`REWRITE_SYSTEM_PROMPT` + `build_rewrite_prompt(segment, judgement)`), `temperature: 0`, ta sama
  koperta i wstrzykiwalny `transport` co `judge`. Odpowiedź czyści `clean_rewrite_reply(content,
  fallback=segment.text)` (zdejmuje opakowujące cudzysłowy/backticki; pusta odpowiedź → oryginał, by
  pętla widziała brak postępu, nie utratę treści).

Pętla korektora woła silnik wyłącznie przez `judge` + `rewrite`; wybór i podmiana atrapy →
`corrector.build_corrector_engine`. Szczegóły w `corrector.schema.md`.

## Dwa adaptery

### `OpenAICompatEngine` — dowolny endpoint zgodny z OpenAI Chat Completions

Obsługuje OpenRouter ORAZ vLLM/RunPod (ta sama koperta). `POST {base_url}/chat/completions`.

| Parametr | Znaczenie | Domyślnie |
|---|---|---|
| `base_url` | bazowy URL API (np. `https://openrouter.ai/api/v1`) | wymagany |
| `model` | nazwa modelu | wymagany |
| `api_key` | klucz; gdy brak, czytany z ENV `api_key_env` | `None` → ENV |
| `api_key_env` | nazwa zmiennej środowiskowej z kluczem | `OPENROUTER_API_KEY` |
| `extra_headers` | dodatkowe nagłówki (np. OpenRouter `HTTP-Referer`/`X-Title`) | `{}` |
| `timeout` | timeout HTTP (s) | `60.0` |
| `transport` | wstrzykiwalna warstwa HTTP (testy podstawiają atrapę) | `_default_http_transport` |

- `name == "openai:<model>"`.
- Nagłówek `Authorization: Bearer <key>` dokładany tylko gdy klucz niepusty.
- Odpowiedź wyłuskiwana z `choices[0].message.content`; błąd/brak pola → `""` → fallback `rewrite`.

### `OllamaEngine` — Ollama po HTTP (lokalna i zdalna RunPod)

`POST {host}/api/chat` ze `stream: false` i `options.temperature: 0`. Wybór `/api/chat` (nie
`/api/generate`) bo ma role system+user — symetria promptu z OpenAI.

| Parametr | Znaczenie | Domyślnie |
|---|---|---|
| `host` | host Ollamy (lokalny lub zdalny RunPod) | `http://localhost:11434` |
| `model` | nazwa modelu (np. `bielik`) | `bielik` |
| `timeout` | timeout HTTP (s) | `120.0` |
| `transport` | wstrzykiwalna warstwa HTTP | `_default_http_transport` |

- `name == "ollama:<model>"`.
- Odpowiedź wyłuskiwana z `message.content`; błąd/brak pola → `""` → fallback `rewrite`.

## Warstwa HTTP wstrzykiwalna (klucz testów offline)

`_default_http_transport(url, *, data, headers, timeout) -> str` to JEDYNE miejsce dotykające sieci
(`urllib.request`). Konstruktor obu silników przyjmuje `transport=...`; w produkcji domyślny urllib,
w testach atrapa zwracająca ustalone ciało JSON modelu. Wzór jak `file_reader`/`ts_provider`
w runnerze: testuje bez podklasy i bez globalnego monkeypatch. Offline `_default_http_transport`
nigdy nie jest wołany.

## Prompt osądu (PO POLSKU)

- System prompt (`JUDGE_SYSTEM_PROMPT`): rola surowego korektora, surowa bramka (jakakolwiek
  poprawka => `rewrite`, `pass` tylko dla akapitu czystego), prośba o JSON `{"verdict","notes"}`.
- User message (`build_judge_prompt(segment)`): `segment.text` w cudzysłowie blokowym + lista
  podejrzeń z `segment.hits` (ID + dopasowany fragment). Pusty `text` (fallback nieczytelnego pliku)
  daje wciąż sensowny prompt — samą listę trafień.
- `temperature: 0` — determinizm osądu sędziego.

## Parsowanie odpowiedzi na `(verdict, notes)`

`parse_model_reply(content)` — deterministyczne, fail-safe domyślnie `rewrite` (bezpieczniej
eskalować niż przepuścić tekst). Kolejność prób:

1. wyłuskaj pierwszy blok `{...}` (regex DOTALL), `json.loads`; jeśli `verdict ∈ {pass, rewrite}` →
   bierz go (notes z pola albo `""`),
2. brak JSON / brak pola: pierwsza niepusta linia zawiera `PASS` (i nie `REWRITE`) → `pass`;
   zawiera `REWRITE` (i nie `PASS`) → `rewrite`,
3. cokolwiek niejednoznacznego (oba słowa, żadne, pusto, śmieci) → `rewrite` z notatką
   „niejednoznaczna odpowiedź modelu; eskalacja do rewrite (fail-safe)".

## Konfiguracja: sekcja `stage2` w `config.json`

```json
"stage2": {
  "engine": "stub",
  "openai": { "base_url": "https://openrouter.ai/api/v1", "model": "...",
              "api_key_env": "OPENROUTER_API_KEY", "extra_headers": {} },
  "ollama": { "host": "http://localhost:11434", "model": "bielik" }
}
```

- `engine ∈ {stub, openai, ollama}`. Brak sekcji `stage2` lub brak configu → `{"engine": "stub"}`
  (zero zmiany zachowania bez configu, zero kosztu, zero sieci).
- Klucz API NIGDY w pliku — config trzyma tylko nazwę zmiennej środowiskowej (`api_key_env`);
  sekret czyta konstruktor silnika z `os.environ`. Separacja: config = CO, ENV = SEKRET.
- `config.load_stage2(path)` zwraca surowy dict konfiguracji. Waliduje `engine` i (dla aktywnego
  realnego silnika) obecność podsłownika z wymaganymi kluczami (openai: `base_url`+`model`; ollama:
  `host`+`model`). Sekcje nieaktywnych silników nie są walidowane. `load_thresholds` (D1) i
  `load_economy` (E4) zostają nietknięte — osobne funkcje, osobne sekcje.

## Fabryka silnika w runnerze

`runner.build_engine_from_config(name=None, config_path=...)`:

- `name=None` → użyj `stage2.engine` z configu (fallback `stub`).
- `name` (np. z CLI `--engine`) nadpisuje wybór z configu.
- Mapowanie: `stub` → `StubJudgeEngine`; `openai` → `OpenAICompatEngine` z `stage2.openai`;
  `ollama` → `OllamaEngine` z `stage2.ollama`.
- Klucz API NIE jest tu czytany — robi to konstruktor silnika z ENV.

CLI: `runner.py --manifest plik.json [--engine stub|openai|ollama] [--config config.json]`.
Domyślnie silnik z configu (fallback atrapa). `openai`/`ollama` wymagają sieci — świadomy wybór
operatora, nie ścieżka testowa.

## Test offline

`tools/check_engines.py` (wpięty do `tests/run_tests.sh`) weryfikuje OFFLINE: mapowanie
JSON/`PASS`/`REWRITE` na `Judgement`, fallback niejednoznaczny → `rewrite`, `Judgement.engine ==
name`, poprawny URL i body (z `segment.text` + ID trafień), `load_stage2` (fallback stub +
walidacja) i `build_engine_from_config`. Cała warstwa HTTP wstrzyknięta atrapą — ZERO realnych
wywołań sieci.
```bash
python3 tools/check_engines.py
```
