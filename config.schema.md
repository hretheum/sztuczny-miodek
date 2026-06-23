# Schemat `config.json` — progi i profile lintera (D1 / KAN-195)

`config.json` wynosi progi proceduralne lintera z literałów w kodzie do danych z PROFILAMI.
Parsowalny biblioteką standardową Pythona (moduł `json`) — bez zależności z pip (ZERO-DEP).

## Struktura

```json
{
  "active_profile": "default",
  "profiles": {
    "<nazwa>": { "opis": "...", "thresholds": { ... } }
  },
  "economy": { "routed_ratio_alarm": 0.10, "min_words": 200 }
}
```

- `active_profile` (string) — profil używany domyślnie (gdy linter wołany bez `--profile`).
- `profiles` (obiekt) — mapa nazwa→profil; każdy profil ma `opis` (string) i `thresholds` (obiekt).
- `economy` (obiekt, opcjonalny) — próg alarmu zdrowia ekonomii (E4); patrz sekcja niżej.

## Progi (`thresholds`) — wszystkie obowiązkowe, dodatnie liczby całkowite

| Klucz | Detektor | Znaczenie | Default |
|---|---|---|---|
| `emdash_per_paragraph` | em-dash overuse | ≥N myślników w akapicie → block | 3 |
| `bold_per_paragraph` | bold-overload | ≥N pogrubień w akapicie → review | 4 |
| `connector_overload_per_file` | nawał łączników | ≥N łączników-otwarć w pliku → block | 3 |
| `en_anti_series_per_file` | seria EN-ANTI | ≥N antytez EN w pliku → block | 2 |
| `pl_anti_series_per_file` | seria PL-ANTI | ≥N antytez PL w pliku → block | 3 |
| `density_per_500_words` | gęstość ważona | density > N → FAIL | 8 |

## Profile (bieżące)

- `default` — progi = stan historyczny (sprzed D1). **ZERO zmiany zachowania.**
- `luzny` — wyższe progi (mniej czuły; teksty swobodne).
- `ostry` — niższe progi (bardziej czuły; teksty formalne/CV).

## Zasady i fallback

- Brak `config.json` → linter używa `config.DEFAULT_THRESHOLDS` (= profil `default`). Bezpieczny fallback.
- `default` w `config.json` MUSI pokrywać się z `config.DEFAULT_THRESHOLDS` — pilnuje tego
  `tools/check_config.py` (gate w `run_tests.sh`).
- Nieznany profil / brak progu / wartość nie-całkowita lub < 1 → czytelny błąd (exit 2 z CLI).
- Wybór profilu: `python3 ai_linter.py --profile <nazwa> …` (nadpisuje `active_profile`).

## Sekcja `economy` — próg alarmu zdrowia ekonomii (E4)

Górna sekcja, **rodzeństwo `profiles`** (celowo poza `thresholds`, bo `load_thresholds` waliduje
dokładny zestaw kluczy progów i odrzuciłby nadmiarowe). Czytana osobną funkcją `config.load_economy`,
więc `load_thresholds` (D1) zostaje nietknięty.

| Klucz | Typ | Znaczenie | Default |
|---|---|---|---|
| `routed_ratio_alarm` | float w (0, 1] | alarm gdy `routed_ratio` (E1) > tego progu | 0.10 |
| `min_words` | int >= 0 | poniżej tylu słów łącznie nie alarmuj (za mała próbka) | 200 |

- Brak `config.json` lub brak sekcji `economy` → `config.DEFAULT_ECONOMY` (fallback, zero zmiany
  zachowania bez configu). Klucze obecne w configu nadpisują domyślne punktowo.
- Wartość niepoprawna (`routed_ratio_alarm` poza `(0, 1]`, `min_words` ujemny lub nie-całkowity) →
  czytelny błąd (`ValueError`).
- Konsument: `metrics.economy_health` i CLI `tools/measure_health.py` (exit 1 na `ALARM`).
  Odniesienie autora: `routed_ratio` ~4–5%; `0.10` = ~2x norma = sygnał regresji reguł.

## Sekcja `stage2` (wybór silnika osądu, KAN-218)

Rodzeństwo `economy`. Wskazuje, którym silnikiem osądzać Stage 2. Czytana osobną funkcją
`config.load_stage2(path)`, więc `load_thresholds` (D1) i `load_economy` (E4) zostają nietknięte.

```json
"stage2": {
  "engine": "stub",
  "openai": { "base_url": "https://openrouter.ai/api/v1", "model": "...",
              "api_key_env": "OPENROUTER_API_KEY", "extra_headers": {} },
  "ollama": { "host": "http://localhost:11434", "model": "bielik" }
}
```

| Klucz | Typ | Znaczenie |
|---|---|---|
| `engine` | `stub`\|`openai`\|`ollama`\|`routing` | aktywny silnik osądu |
| `openai.base_url`, `openai.model` | string | wymagane gdy `engine="openai"` |
| `openai.api_key_env` | string | nazwa ENV z kluczem (sekret NIGDY w pliku) |
| `openai.extra_headers` | obiekt | dodatkowe nagłówki (np. OpenRouter `HTTP-Referer`) |
| `ollama.host`, `ollama.model` | string | wymagane gdy `engine="ollama"` |
| `routing.primary`, `routing.appellate` | obiekt | wymagane gdy `engine="routing"` (G3); pod-config jak `stage2` |
| `routing.escalate_on_rewrite` | bool | eskaluj do appellate gdy primary wyda `rewrite` (domyślnie `true`) |
| `routing.hard_hits_threshold` | int\|null | eskaluj gdy `len(hits) >=` tej liczby (segment „trudny") |

- Brak sekcji `stage2` lub brak configu → `{"engine": "stub"}` (zero zmiany zachowania, zero sieci).
- Walidacja: `engine` z dozwolonych; dla aktywnego realnego silnika wymagany podsłownik z kluczami
  (openai: `base_url`+`model`; ollama: `host`+`model`). Brak → `ValueError`. Sekcje nieaktywnych
  silników nie są walidowane.
- **Routing (G3)**: gdy `engine="routing"`, wymagana podsekcja `routing` z `primary` i `appellate` —
  każdy to pod-config o kształcie `stage2` (`engine` + sekcja silnika), budowany REKURENCYJNIE przez
  `runner._build_single_engine`. Routing jest JEDNOPOZIOMOWY: `engine="routing"` wewnątrz
  `primary`/`appellate` jest zabronione (`ValueError`) — ochrona przed cyklem rekurencji. Polityka
  eskalacji (`escalate_on_rewrite`, `hard_hits_threshold`) i ograniczenie wobec auto-offloadu poda
  opisuje `engines.schema.md` (sekcja „Routing silnika").
- Klucz API czytany WYŁĄCZNIE z ENV (przez `api_key_env`) w konstruktorze silnika, nigdy z pliku.
- Konsument: `runner.build_engine_from_config` (CLI `runner.py --engine ... --config ...`).
  Kontrakt adapterów: `engines.schema.md`.

## Podsekcja `stage2.runpod` — efemeryczny pod dla `--runpod` (KAN-222)

Parametry, z których flaga `--runpod` stawia EFEMERYCZNY pod RunPod (`managed_ephemeral_pod`):
jeden krok zamiast ręcznej sekwencji (postaw pod z wolumenu, osądź realnym Bielikiem przez Ollamę,
zgaś pod automatycznie). Czytana osobną funkcją `config.load_runpod(path)`, więc `load_thresholds`
(D1), `load_economy` (E4), `load_stage2` (KAN-218) i `load_lifecycle` (KAN-220) zostają NIETKNIĘTE.

```json
"stage2": {
  "runpod": {
    "volume": "5lb05arqur",
    "dc": "EU-NL-1",
    "mount": "/root/.ollama",
    "image": "ollama/ollama:latest",
    "model": "hf.co/speakleash/Bielik-11B-v3.0-Instruct-GGUF:Q4_K_M",
    "name": "miodek-bielik",
    "api_key_env": "RUNPOD_API_KEY",
    "base_url": "https://rest.runpod.io/v1"
  }
}
```

| Klucz | Typ | Znaczenie | Default |
|---|---|---|---|
| `volume` | string (niepusty) | ID wolumenu sieciowego (model leży tu trwale, nie pobierany ponownie) | `5lb05arqur` |
| `dc` | string (niepusty) | data center wolumenu (pod musi tu stanąć) | `EU-NL-1` |
| `model` | string (niepusty) | tag modelu Ollamy (ten sam dla `ensure_model` i `OllamaEngine`) | Bielik GGUF Q4_K_M |
| `mount` | string | mount wolumenu (modele Ollamy) | `/root/.ollama` |
| `image` | string | obraz kontenera | `ollama/ollama:latest` |
| `gpu` | lista stringów | dozwolone GPU (RunPod wybiera dostępne); brak → `DEFAULT_GPUS` launchera | — |
| `name` | string | nazwa poda | `miodek-bielik` |
| `api_key_env` | string | nazwa ENV z kluczem (sekret NIGDY w pliku) | `RUNPOD_API_KEY` |
| `base_url` | string | baza REST RunPod | `https://rest.runpod.io/v1` |

- Brak `config.json`, brak `stage2` lub brak podsekcji `runpod` → `config.DEFAULT_RUNPOD` (= wartości
  launchera `tools/runpod_pod_up.py`). Klucze obecne w configu nadpisują domyślne PUNKTOWO (operator
  może podać tylko `volume`+`dc`, reszta z domyślnych).
- Walidacja kluczy load-bearing: `volume`, `dc`, `model` muszą być niepustymi stringami; `gpu` (jeśli
  obecny) listą stringów. Niepoprawne → `ValueError`.
- Konsument: `runner.build_ephemeral_runpod` + `runner.build_runpod_engine` (flaga `--runpod` w
  `runner.py`, `corrector.py`, `tools/publish_gate.py`). Cykl i teardown: `runpod-lifecycle.schema.md`
  (sekcja „Tryb EFEMERYCZNY").

## Styk z resztą systemu

- **B3 (kalibracja progów)**: metodyka z `docs/THRESHOLD-CALIBRATION.md` zakłada, że kalibracja na
  korpusie+logu (D4) zapisuje wynikowe progi do `config.json` (profil), nie do literałów w kodzie.
- **`prog` w `rules.json`**: progi proceduralne (config.json) ≠ deklaratywne (`prog` w regule regex).
  To dwa rozłączne nośniki „progów jako danych" — config dla detektorów proceduralnych, `prog` dla
  ewentualnych progów reguł regexowych.

## Diagnostyka

```bash
python3 config.py                    # progi aktywnego profilu
python3 config.py --profile ostry    # progi wskazanego profilu
```
