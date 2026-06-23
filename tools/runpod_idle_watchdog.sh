#!/usr/bin/env bash
# runpod_idle_watchdog.sh — backstop auto-offloadu poda RunPod (KAN-220, warstwa 3 z trzech).
#
# URUCHAMIANY NA PODZIE (nie lokalnie). To OSTATNIA linia obrony teardownu: gasi pod po N sekundach
# bezczynności. Zabezpiecza scenariusze, w których proces sterujący padł twardo (kill -9, OOM, utrata
# sieci) i ani blok `finally` menedżera kontekstu (warstwa 1), ani handler sygnału (warstwa 2) NIE
# zdążyły zgasić poda. Watchdog jest NIEZALEŻNY od procesu sterującego — żyje obok serwera modelu.
#
# DEFINICJA BEZCZYNNOŚCI: brak nowych żądań do serwera modelu. Domyślnie watchdog śledzi mtime pliku
# heartbeat, który serwer/proxy dotyka przy każdym żądaniu osądu. Gdy heartbeatu brak, można oprzeć
# się na wykorzystaniu GPU (nvidia-smi) jako sygnale aktywności (patrz tryb GPU niżej).
#
# GASZENIE: REST RunPod stop (POST /pods/{RUNPOD_POD_ID}/stop) z RUNPOD_API_KEY, albo `runpodctl`,
# jeśli dostępny. Po stopie GPU przestaje bić; model zostaje na dysku /workspace.
#
# ZERO ZALEŻNOŚCI ponad to, co i tak jest na podzie: bash, curl (do REST) albo runpodctl, opcjonalnie
# nvidia-smi (tryb GPU). Bez Pythona, bez pip.
#
# ZMIENNE ŚRODOWISKOWE:
#   IDLE_BACKSTOP_S   — próg bezczynności w sekundach (= stage2.lifecycle.idle_backstop_s). Domyślnie 600.
#   RUNPOD_POD_ID     — id poda (RunPod wstrzykuje je do env poda automatycznie).
#   RUNPOD_API_KEY    — klucz API (do REST stop). NIE trzymaj go w obrazie; wstrzyknij jako secret poda.
#   HEARTBEAT_FILE    — ścieżka pliku heartbeat (domyślnie /tmp/miodek_stage2.heartbeat). Serwer modelu
#                       / proxy powinien dotykać go przy każdym żądaniu (`touch "$HEARTBEAT_FILE"`).
#   WATCH_MODE        — "heartbeat" (domyślnie) albo "gpu" (aktywność = nvidia-smi utilization > 0).
#   CHECK_INTERVAL_S  — co ile sprawdzać (domyślnie 30).
#   RUNPOD_API_BASE   — baza REST (domyślnie https://rest.runpod.io/v1).
#
# INSTALACJA: patrz tools/runpod_idle_watchdog.README.md (komenda startowa poda / Docker CMD).

set -u

IDLE_BACKSTOP_S="${IDLE_BACKSTOP_S:-600}"
HEARTBEAT_FILE="${HEARTBEAT_FILE:-/tmp/miodek_stage2.heartbeat}"
WATCH_MODE="${WATCH_MODE:-heartbeat}"
CHECK_INTERVAL_S="${CHECK_INTERVAL_S:-30}"
RUNPOD_API_BASE="${RUNPOD_API_BASE:-https://rest.runpod.io/v1}"

log() { echo "[idle_watchdog $(date -u +%FT%TZ)] $*" >&2; }

now_epoch() { date +%s; }

# Zwraca epokę ostatniej aktywności. Tryb heartbeat: mtime pliku (lub teraz, gdy plik brak — świeży
# start nie gasi od razu). Tryb gpu: jeśli jakikolwiek GPU ma utilization > 0, aktywność = teraz.
last_activity_epoch() {
  if [ "$WATCH_MODE" = "gpu" ] && command -v nvidia-smi >/dev/null 2>&1; then
    local util
    util="$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null \
            | tr -d ' ' | sort -nr | head -1)"
    if [ -n "${util:-}" ] && [ "$util" -gt 0 ] 2>/dev/null; then
      now_epoch
      return
    fi
  fi
  # tryb heartbeat (i fallback dla gpu, gdy GPU idle): mtime pliku heartbeat
  if [ -f "$HEARTBEAT_FILE" ]; then
    stat -c %Y "$HEARTBEAT_FILE" 2>/dev/null || stat -f %m "$HEARTBEAT_FILE" 2>/dev/null
  else
    now_epoch  # brak pliku = traktuj świeży start jako aktywność (nie gaś od razu)
  fi
}

stop_pod() {
  log "BEZCZYNNOŚĆ >= ${IDLE_BACKSTOP_S}s — gaszę pod ${RUNPOD_POD_ID:-?} (backstop)."
  if command -v runpodctl >/dev/null 2>&1 && [ -n "${RUNPOD_POD_ID:-}" ]; then
    runpodctl stop pod "$RUNPOD_POD_ID" && { log "runpodctl stop OK"; return 0; }
    log "runpodctl stop nie powiódł się — próbuję REST."
  fi
  if [ -n "${RUNPOD_API_KEY:-}" ] && [ -n "${RUNPOD_POD_ID:-}" ]; then
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' -X POST \
      -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
      "${RUNPOD_API_BASE}/pods/${RUNPOD_POD_ID}/stop")"
    if [ "$code" = "200" ] || [ "$code" = "204" ]; then
      log "REST stop OK (HTTP $code)"; return 0
    fi
    log "REST stop ZWRÓCIŁ HTTP $code — POD MOŻE NADAL BIĆ POD PRĄD, sprawdź ręcznie."
    return 1
  fi
  log "BRAK runpodctl ORAZ RUNPOD_API_KEY/RUNPOD_POD_ID — nie mam czym zgasić poda!"
  return 1
}

log "start: tryb=${WATCH_MODE}, próg=${IDLE_BACKSTOP_S}s, heartbeat=${HEARTBEAT_FILE}, interwał=${CHECK_INTERVAL_S}s"
while true; do
  last="$(last_activity_epoch)"
  if [ -n "${last:-}" ]; then
    idle=$(( $(now_epoch) - last ))
    if [ "$idle" -ge "$IDLE_BACKSTOP_S" ]; then
      stop_pod
      exit 0  # po zgaszeniu watchdog kończy (pod i tak gaśnie)
    fi
  fi
  sleep "$CHECK_INTERVAL_S"
done
