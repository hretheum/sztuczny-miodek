# Schemat auto-offloadu poda RunPod — `runpod_lifecycle.py` (KAN-220)

Automatyczne gaszenie poda z modelem (np. Bielik na RunPodzie) PO przebiegu osądu Stage 2, żeby GPU
nie biło pod prąd między przebiegami. Sedno to ODPORNOŚĆ: teardown ma zadziałać także gdy proces
padnie. Stąd TRZY niezależne warstwy — żaden teardown nie jest pojedynczym punktem awarii.

ZERO-DEP (biblioteka standardowa: `urllib`, `json`, `os`, `signal`, `sys`). Warstwa HTTP jest
wstrzykiwalna (parametr `transport`), więc testy są w pełni offline. Klucz API czytany WYŁĄCZNIE
z ENV (`RUNPOD_API_KEY`), nigdy z pliku. Komplement do `engines.schema.md` (silnik) i
`config.schema.md` (sekcja `stage2.lifecycle`).

## Trzy warstwy teardownu

1. **Warstwa kontekstowa (`managed_pod`, blok `finally`).** Menedżer kontekstu owija przebieg
   Stage 2. Na wejściu opcjonalnie wznawia pod (resume), gdy `ensure_running` i status != `RUNNING`.
   Na wyjściu w bloku `finally` gasi pod ZAWSZE — także przy wyjątku. `__exit__` zwraca `False`,
   więc wyjątek przebiegu PROPAGUJE (nie jest połknięty).
2. **Warstwa sygnałów (handlery SIGINT/SIGTERM).** Przed zniknięciem procesu handler woła teardown,
   PRZYWRACA poprzedni handler (`signal.getsignal` zapamiętany na wejściu) i RE-RAISUJE sygnał
   (`os.kill(getpid, signum)`) — nie połyka sygnału na stałe.
3. **Backstop po stronie poda (`tools/runpod_idle_watchdog.sh`).** Watchdog uruchamiany NA podzie
   gasi go po `idle_backstop_s` sekundach bezczynności. Zabezpiecza `kill -9` / OOM / utratę sieci,
   gdzie `finally` ani handler się NIE wykonają. Artefakt + dokumentacja
   (`tools/runpod_idle_watchdog.README.md`), poza testami offline (nie da się go odpalić bez poda).

## Klient REST: `RunPodClient` (REST API v1)

Baza `https://rest.runpod.io/v1`, auth nagłówkiem `Authorization: Bearer <RUNPOD_API_KEY>`.

| Metoda | HTTP | Ścieżka | Sens |
|---|---|---|---|
| `stop(pod_id)` | POST | `/pods/{id}/stop` | zwolnij GPU, model zostaje na `/workspace` |
| `start(pod_id)` | POST | `/pods/{id}/start` | wznów zatrzymany pod (resume) |
| `terminate(pod_id)` | DELETE | `/pods/{id}` | trwała kasacja (poza network volume) |
| `status(pod_id)` | GET | `/pods/{id}` | zwraca `desiredStatus` (`RUNNING`/`EXITED`/...) |

- Konstruktor: `RunPodClient(api_key_env="RUNPOD_API_KEY", base_url=..., timeout=30.0, transport=None)`.
- Klucz API czytany z ENV w KONSTRUKTORZE (separacja config=CO, ENV=SEKRET). Brak klucza → metody
  rzucają czytelny `RuntimeError` przy realnym wywołaniu (offline z atrapą klucz nie jest potrzebny).
- `_call` mapuje status: `2xx` → OK (zwraca sparsowany dict albo `{}`), inaczej `RuntimeError`
  z kodem i wycinkiem ciała.
- `_default_rest_transport(url, *, method, data, headers, timeout) -> (status_int, body_str)` —
  JEDYNE miejsce dotykające sieci (`urllib`). `HTTPError` (4xx/5xx) zwracany jako `(code, body)`,
  by klient sam zmapował na błąd; `URLError` (sieć leży) → `RuntimeError`. W testach podstawiana
  atrapa; `_default_rest_transport` NIGDY nie jest wołany offline.

## Menedżer kontekstu: `managed_pod`

```python
client = RunPodClient(api_key_env="RUNPOD_API_KEY")
with managed_pod(client, pod_id, on_finish="stop", ensure_running=True, idle_backstop_s=600):
    result = run_stage2(manifest, engine=engine)
# tu pod jest już zgaszony — także gdyby run_stage2 rzucił albo przyszedł SIGTERM
```

| Parametr | Znaczenie | Domyślnie |
|---|---|---|
| `client` | `RunPodClient` (lub obiekt z `.stop/.start/.terminate/.status`) | wymagany |
| `pod_id` | id poda, którym zarządzamy (niepusty) | wymagany |
| `on_finish` | `"stop"` (GPU gaśnie, model zostaje) \| `"terminate"` (kasacja) | `"stop"` |
| `ensure_running` | na wejściu wznów pod (start), jeśli status != `RUNNING` | `True` |
| `idle_backstop_s` | informacyjnie (próg backstopu egzekwowanego przez watchdog NA podzie) | `None` |

- `managed_pod.from_config(client, cfg)` buduje menedżera z sekcji `stage2.lifecycle`.
- **Teardown bezpieczny do wielokrotnego wywołania**: flaga `_torn_down`. Gdyby `finally` i handler
  sygnału trafiły razem, realny `stop`/`terminate` woła się TYLKO RAZ.
- **Błąd teardownu jest GŁOŚNY** (komunikat na `stderr`), nigdy połknięty po cichu — to bramka
  KOSZTOWA: nieugaszony pod bije pod prąd GPU. W kontekście `finally` log nie maskuje pierwotnego
  wyjątku przebiegu (ten propaguje dalej).
- Instalacja handlerów sygnałów działa tylko w głównym wątku; poza nim po cichu pomijana (warstwa 1
  i 3 zostają).

## Konfiguracja: `stage2.lifecycle` (`config.json`)

```json
"stage2": {
  "engine": "stub",
  "lifecycle": {
    "manage": false,
    "pod_id": "",
    "on_finish": "stop",
    "ensure_running": true,
    "idle_backstop_s": 600,
    "api_key_env": "RUNPOD_API_KEY"
  }
}
```

- `manage=false` lub BRAK sekcji `lifecycle` / `stage2` / configu → `config.load_lifecycle` zwraca
  `{"manage": False}` → **NO-OP**: runner NIE owija przebiegu (zero zmiany zachowania, fallback
  bezpieczny). To kluczowy wymóg: domyślnie nikt nie rusza żadnego poda.
- `config.load_lifecycle(path)` czyta podsekcję osobną funkcją; `load_thresholds` (D1),
  `load_economy` (E4) i `load_stage2` (KAN-218) zostają NIETKNIĘTE.
- Walidacja TYLKO gdy `manage=true`: `pod_id` niepusty wymagany; `on_finish ∈ {stop, terminate}`;
  `idle_backstop_s` (jeśli obecny) dodatnia liczba całkowita. Przy `manage=false` reszta nie jest
  walidowana (sekcja może być szkicem w rezerwie).
- Klucz API NIGDY w pliku — config trzyma tylko nazwę ENV (`api_key_env`).

## Wpięcie w runner (`_main`)

Kontrakt `run_stage2` jest NIETKNIĘTY. Owijanie żyje wyłącznie w `_main`:

```python
lifecycle = config.load_lifecycle(args.config)
if lifecycle.get("manage") and runner._is_remote_engine(engine):   # tylko ollama:/openai:
    client = runpod_lifecycle.build_client_from_lifecycle(lifecycle)
    with runpod_lifecycle.managed_pod.from_config(client, lifecycle):
        result = run_stage2(manifest, engine=engine)
else:
    result = run_stage2(manifest, engine=engine)   # stub / brak lifecycle → bez zmian
```

Owijamy tylko gdy `manage=true` ORAZ silnik zdalny (`engine.name` zaczyna się od `ollama:`/`openai:`).
Atrapa (`stub`) jest lokalna — nie ma żadnego poda do gaszenia, ścieżka identyczna jak dziś.

## Tryb EFEMERYCZNY: `managed_ephemeral_pod` (KAN-222)

Inny cykl życia niż `managed_pod`: tamten ZARZĄDZA istniejącym podem (start/stop/terminate po
`pod_id` z configu), ten TWORZY pod na wejściu i TERMINUJE na wyjściu. Realizuje flagę `--runpod`:
jeden krok zamiast ręcznej sekwencji (postaw pod z wolumenu, osądź na realnym Bieliku, zgaś pod).

Cykl: `create_pod` → `wait_for_ollama` → `ensure_model` → (przebieg Stage 2) → `terminate`.
Stawianie reużywa launcher `tools/runpod_pod_up.py` (zero duplikacji logiki). URL poda =
`https://<pod_id>-11434.proxy.runpod.net`, gdzie `pod_id` to `pod["id"]` z `create_pod`.

```python
ctx = managed_ephemeral_pod.from_config(config.load_runpod(path))
with ctx as pod:
    engine = OllamaEngine(host=pod.url, model=...)   # świeży efemeryczny pod
    result = run_stage2(manifest, engine=engine)     # CZYSTY run_stage2 — pod już owinięty
# tu pod jest już ZTERMINOWANY — także przy wyjątku / SIGTERM
```

Te same TRZY warstwy teardownu co `managed_pod` (wspólny `_SignalTeardownMixin`):
1. **finally** (`__exit__`): `terminate` ZAWSZE, też przy wyjątku; `__exit__` zwraca `False` (wyjątek
   propaguje).
2. **handler SIGINT/SIGTERM**: gasi, przywraca poprzedni handler, re-raisuje sygnał.
3. **backstop watchdog NA podzie**: aktualny i dla efemerycznego poda (`kill -9`).

Plus **gwarancja braku osieroconego poda**: jeśli `wait_for_ollama`/`ensure_model` zawiedzie w
`__enter__`, JUŻ utworzony pod jest terminowany PRZED rzuceniem `RuntimeError` (proces nie wszedł
w `with`, więc samo `finally` by go nie dotknęło). Teardown bezpieczny do wielokrotnego wywołania
(flaga `_torn_down`) — realny `terminate` raz. Błąd terminacji GŁOŚNO na `stderr` (bramka kosztowa GPU).

Klucz API z ENV (`api_key_env`, domyślnie `RUNPOD_API_KEY`) — sekret NIGDY w pliku/argumencie.
Warstwa REST WSTRZYKIWALNA dla testów offline: `pod_up` (atrapa modułu launchera),
`client_transport` (atrapa REST do `terminate`). Pod żadną atrapą `urllib` nie jest dotykany.

Parametry z `config.load_runpod` (podsekcja `stage2.runpod`): `volume`, `dc`, `mount`, `image`,
`model`, `gpu`, `name`, `api_key_env`, `base_url` — domyślne = wartości launchera, patrz
`config.schema.md`.

### Wpięcie flagi `--runpod` (jedno źródło prawdy)

`runner.build_ephemeral_runpod(config_path)` buduje menedżer; `runner.build_runpod_engine(config_path,
pod=pod)` buduje `OllamaEngine(host=pod.url, model=runpod.model)`. Trzy CLI (`runner.py`,
`corrector.py`, `tools/publish_gate.py`) z flagą `--runpod`:

```python
with runner.build_ephemeral_runpod(args.config) as pod:
    engine = runner.build_runpod_engine(args.config, pod=pod)
    result = runner.run_stage2(manifest, engine=engine)   # czysty — ephemeral SAM owija
```

Bez flagi: ścieżka BEZ ZMIAN (domyślnie stub, zero sieci, zero kosztu). `--runpod` w `publish_gate`
sam włącza Stage 2. W `corrector` współgra z **bramką UX**: bez `--runpod` i bez realnego silnika
(stub) korektor ODMAWIA (`exit 2`) i kieruje na `--runpod` albo `stage2.engine=ollama/openai` —
stub nie miele tekstu po cichu (furtka self-testów: `MIODEK_ALLOW_STUB_CORRECTOR=1`).

## Test offline: `tools/check_runpod_lifecycle.py`

Wpięty do `tests/run_tests.sh`. Cała warstwa REST wstrzyknięta atrapą (callable zapisująca
method/url, zwracająca ustalone `(status, body)`) — `_default_rest_transport` NIGDY nie wołany.
Weryfikuje: klient (URL/metoda/Bearer, 2xx→OK / 4xx→błąd, klucz z ENV); `managed_pod` (1 stop przy
normalnym wyjściu; stop w `finally` przy wyjątku, który propaguje; SIGTERM → teardown + przywrócony
handler; `on_finish=terminate` → terminate; odporność na podwójny teardown → 1 stop; błąd teardownu
GŁOŚNO na stderr); `load_lifecycle` (fallback `manage=false` + walidacja); NO-OP `manage=false` →
zero wywołań REST. ZERO realnej sieci.

```bash
python3 tools/check_runpod_lifecycle.py
```

## Test offline trybu efemerycznego: `tools/check_runpod_ephemeral.py` (KAN-222)

Wpięty do `tests/run_tests.sh`. Launcher `runpod_pod_up` atrapowany modułem zastępczym
(`create_pod`/`wait_for_ollama`/`ensure_model`), `terminate` przez atrapę transportu REST. Weryfikuje:
`managed_ephemeral_pod` (create na wejściu + URL poprawny; dokładnie 1 `terminate` na wyjściu, też
przy wyjątku w `finally`; sprzątanie osieroconego poda gdy `wait`/`ensure_model` padnie w `__enter__`;
idempotencja teardownu → 1 `terminate`; brak klucza ENV → `RuntimeError` bez `create`; SIGTERM →
`terminate` + przywrócony handler; `no_model=True` pomija `ensure_model`); `config.load_runpod`
(fallback `DEFAULT_RUNPOD` + scalanie punktowe + walidacja `volume`/`dc`/`model`/`gpu`);
`build_ephemeral_runpod`/`build_runpod_engine` (`OllamaEngine` na `url` poda, `name=ollama:<model>`,
owinięcie buduje create+terminate); bramka UX korektora (`exit 2` bez realnego silnika, furtka
`MIODEK_ALLOW_STUB_CORRECTOR=1`). ZERO realnej sieci, ZERO realnego poda.

```bash
python3 tools/check_runpod_ephemeral.py
```
