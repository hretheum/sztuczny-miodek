# Watchdog bezczynności poda RunPod — backstop auto-offloadu (KAN-220)

`tools/runpod_idle_watchdog.sh` to TRZECIA, niezależna warstwa auto-offloadu poda Stage 2. Dwie
pozostałe (blok `finally` menedżera kontekstu i handlery sygnałów) żyją w `runpod_lifecycle.py`
po stronie procesu sterującego. Ten skrypt żyje NA PODZIE i gasi go po zadanym czasie bezczynności,
nawet gdy proces sterujący padł twardo (`kill -9`, OOM, utrata sieci) i ani `finally`, ani handler
sygnału się NIE wykonały. To ostatnia linia obrony bramki kosztowej GPU.

Skryptu nie da się sensownie przetestować lokalnie bez poda, dlatego jest dostarczany jako artefakt
plus ta dokumentacja, a NIE jako część testów offline w `tests/run_tests.sh`.

## Co liczy się jako bezczynność

- Tryb `heartbeat` (domyślny): serwer modelu albo cienki proxy dotyka pliku heartbeat przy KAŻDYM
  żądaniu osądu (`touch "$HEARTBEAT_FILE"`). Watchdog śledzi `mtime` tego pliku. Brak nowych żądań
  przez `IDLE_BACKSTOP_S` sekund => gaszenie.
- Tryb `gpu` (`WATCH_MODE=gpu`): aktywnością jest `nvidia-smi` z utilization > 0. Gdy GPU jest
  bezczynne, watchdog spada do mtime heartbeatu (fallback). Przydatne, gdy nie chcesz instrumentować
  serwera modelu, a wystarcza Ci sygnał z karty.

## Zmienne środowiskowe

| Zmienna | Znaczenie | Domyślnie |
|---|---|---|
| `IDLE_BACKSTOP_S` | próg bezczynności w sekundach (= `stage2.lifecycle.idle_backstop_s`) | `600` |
| `RUNPOD_POD_ID` | id poda; RunPod wstrzykuje je do env poda automatycznie | (z env poda) |
| `RUNPOD_API_KEY` | klucz API do REST stop; wstrzyknij jako secret poda, nie do obrazu | (secret) |
| `HEARTBEAT_FILE` | ścieżka pliku heartbeat | `/tmp/miodek_stage2.heartbeat` |
| `WATCH_MODE` | `heartbeat` albo `gpu` | `heartbeat` |
| `CHECK_INTERVAL_S` | co ile sekund sprawdzać | `30` |
| `RUNPOD_API_BASE` | baza REST RunPod | `https://rest.runpod.io/v1` |

Próg `IDLE_BACKSTOP_S` ustaw zgodnie z `stage2.lifecycle.idle_backstop_s` z `config.json`, żeby
backstop poda i konfiguracja procesu sterującego mówiły jednym głosem.

## Jak go uruchomić (komenda startowa poda)

Watchdog ma działać W TLE obok serwera modelu, od startu poda. Wzorzec w Docker `CMD` / komendzie
startowej template'u RunPod (uruchom serwer i watchdog, czekaj na proces serwera):

```bash
# przykład: serwer Ollamy + watchdog jako backstop
export IDLE_BACKSTOP_S=600
export HEARTBEAT_FILE=/tmp/miodek_stage2.heartbeat

# 1. serwer modelu (przykład: ollama serve)
ollama serve &
SERVER_PID=$!

# 2. watchdog w tle (RUNPOD_POD_ID i RUNPOD_API_KEY przychodzą z env/secretów poda)
bash /workspace/tools/runpod_idle_watchdog.sh &

# 3. trzymaj pod żywy tak długo, jak żyje serwer
wait $SERVER_PID
```

Heartbeat z serwera modelu: najprościej proxy/wrapper, który przed przekazaniem żądania do modelu
robi `touch "$HEARTBEAT_FILE"`. Jeśli wolisz nie ruszać serwera, użyj `WATCH_MODE=gpu`.

## Gaszenie

Skrypt najpierw próbuje `runpodctl stop pod "$RUNPOD_POD_ID"` (gdy `runpodctl` jest na podzie),
a w razie braku/błędu woła REST `POST {RUNPOD_API_BASE}/pods/{RUNPOD_POD_ID}/stop` z nagłówkiem
`Authorization: Bearer $RUNPOD_API_KEY`. Po udanym stopie GPU przestaje bić, model zostaje na dysku
`/workspace`, a watchdog kończy działanie (exit 0). Każdy nieudany stop leci GŁOŚNO na stderr —
to świadomy sygnał, że pod może nadal generować koszt i trzeba sprawdzić go ręcznie.

## Relacja do `on_finish`

Watchdog wykonuje wyłącznie `stop` (zwolnienie GPU, model zostaje) — bezpieczny domyślny backstop.
Polityka `terminate` (trwała kasacja) jest celowo zostawiona warstwie sterującej (`managed_pod`
z `on_finish="terminate"`), bo kasacja jest nieodwracalna i nie powinna wynikać z samej bezczynności.
