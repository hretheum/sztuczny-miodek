#!/usr/bin/env python3
"""
metrics_exporter.py — eksporter metryk Stage 1 w formacie Prometheus (KAN-219). ZERO-DEP (stdlib).

Wystawia HTTP `/metrics` w formacie text exposition (wersja 0.0.4), żeby istniejący Prometheus
na hoście mbair (port 9090) mógł odpytywać ten serwer, a Grafana (port 3000) rysowała dashboard.
NIE stawiamy stacku — budujemy artefakt do wpięcia. Deploy robi operator (patrz deploy/README.md).

GRANICE I UCZCIWOŚĆ DANYCH
==========================
Wszystkie liczby pochodzą z gotowych kontraktów repo (REUŻYCIE, zero przeliczania):
  - metrics.reduction_from_manifest    -> E1 (redukcja, routed_ratio, słowa),
  - metrics.attribution_from_manifest  -> E2 (per reguła / klasa),
  - metrics.economy_health             -> E4 (zdrowie OK/ALARM/N/A + próg z config.load_economy),
  - runner.read_stage2_runs            -> przebiegi Stage 2 per silnik/werdykt (wspólny strumień JSONL).

E1/E2/E4 są REALNE od zaraz: liczą się z manifestu Stage 1 (deterministyczny linter, zero LLM).
Panel przebiegów Stage 2 (miodek_stage2_runs_total) wypełnia się DOPIERO, gdy realny silnik
(Bielik przez Ollama / model przez OpenRouter za interfejs engines.JudgeEngine) nazbiera przebiegów.
Dziś Stage 2 chodzi na atrapie (StubJudgeEngine), więc ta seria może być pusta lub rzadka.
To NIE zaślepka — to realny panel czekający na dane.

ARCHITEKTURA (trzy warstwy, granica testowalna w środku)
========================================================
  (a) collect_state(...)  — efekty uboczne: woła ai_linter na korpusie (podproces), liczy metryki,
                            czyta log Stage 2. Zwraca jeden surowy dict `state` (czyste liczby).
  (b) render_metrics(state) -> str — CZYSTA funkcja: state -> tekst ekspozycji Prometheus.
                            To sedno self-testu offline (check_metrics_exporter.py wstrzykuje state).
  (c) serwer HTTP — http.server.ThreadingHTTPServer: GET /metrics (z cache), /healthz, reszta 404.

Cache: collect_state jest drogie (uruchamia linter na korpusie). Trzymamy ostatni state z
znacznikiem czasu; w oknie TTL (env MIODEK_SCRAPE_CACHE_TTL, domyślnie 30 s) zwracamy cache, żeby
częste scrape'y nie mieliły lintera. Błąd collect_state => fail-soft: serwujemy ostatni dobry state
(miodek_exporter_up 1) albo — gdy go brak — pusty zestaw z miodek_exporter_up 0 (nie 500, żeby
Prometheus widział target up, a my sami sygnalizujemy awarię eksportera metryką).

KONFIGURACJA (env; mirror w argparse):
  MIODEK_CORPUS            ścieżka korpusu (plik/glob/katalog). Domyślnie: katalog repo (proza .md).
  MIODEK_PORT             port serwera (domyślnie 9112).
  MIODEK_LOG              ścieżka decisions.jsonl (domyślnie decision_log.DEFAULT_LOG_PATH).
  MIODEK_PROFILE          opcjonalny profil progów lintera (--profile).
  MIODEK_DICT             opcjonalny słownik domenowy (--dict).
  MIODEK_LANG             język markerów (pl/en/both; domyślnie both).
  MIODEK_SCRAPE_CACHE_TTL TTL cache state w sekundach (domyślnie 30).

SCHEMAT METRYK (nazwy, typy, etykiety) — patrz tools/metrics_exporter.schema.md.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from miodek import metrics  # noqa: E402
from miodek import config as _config  # noqa: E402
from miodek import decision_log  # noqa: E402
from miodek import runner  # noqa: E402

# Linter jako moduł pakietu (KAN-227); subprocess dostaje PYTHONPATH ze src.
AI_LINTER_MODULE = "miodek.ai_linter"
_SRC_DIR = os.path.join(REPO_ROOT, "src")


def _linter_env():
    env = dict(os.environ)
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _SRC_DIR + (os.pathsep + prev if prev else "")
    return env

# Format text exposition Prometheus (wersja kontraktu). Wystawiamy w nagłówku Content-Type.
CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


# ============================================================================
# (b) render_metrics — CZYSTA funkcja: state -> tekst ekspozycji Prometheus.
# ============================================================================
#
# `state` (kontrakt wejścia, budowany przez collect_state albo wstrzyknięty w teście):
#   {
#     "exporter_up": 1|0,                 # 1 gdy ostatni collect_state OK, 0 na fail-soft
#     "scrape_duration_seconds": float,   # czas budowy state (obserwowalność eksportera)
#     "reduction": <wynik metrics.reduction_from_manifest>,
#     "attribution": <wynik metrics.attribution_from_manifest>,
#     "health": <wynik metrics.economy_health>,
#     "stage2_runs": [ {engine, verdict, count}, ... ],   # zagregowane per (engine, stage2_verdict)
#   }
# Gdy exporter_up == 0 (fail-soft bez poprzedniego dobrego state), pozostałe sekcje mogą być None —
# render emituje wtedy tylko miodek_exporter_up 0 (plus duration), bez serii liczbowych.


def _esc_label(value):
    """Escaping wartości etykiety wg formatu Prometheus: \\ -> \\\\, \" -> \\\", newline -> \\n."""
    s = str(value)
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("\n", "\\n")
    return s


def _fmt(x):
    """Formatuje wartość liczbową: int bez kropki, float zwięźle (6 cyfr znaczących).

    Bez nan/inf (Prometheus ich nie lubi w prostym przebiegu) — zastępujemy 0 z ostrożności,
    ale w praktyce metryki tu są skończone (ratio w [0,1], zliczenia całkowite)."""
    if isinstance(x, bool):
        return "1" if x else "0"
    if isinstance(x, int):
        return str(x)
    xf = float(x)
    if xf != xf or xf in (float("inf"), float("-inf")):
        return "0"
    if xf == int(xf):
        return str(int(xf))
    return f"{xf:.6g}"


def _block(out, name, mtype, help_text, samples):
    """Dopisuje jeden blok metryki: # HELP, # TYPE, potem serie. Pomija blok bez serii? Nie —

    HELP/TYPE emitujemy ZAWSZE (nawet bez serii), żeby panel istniał i był jawnie „czeka na dane".
    `samples` to lista krotek (labels_dict_or_None, value). Labels None => seria bez etykiet."""
    out.append(f"# HELP {name} {help_text}")
    out.append(f"# TYPE {name} {mtype}")
    for labels, value in samples:
        if labels:
            parts = ",".join(f'{k}="{_esc_label(v)}"' for k, v in labels.items())
            out.append(f"{name}{{{parts}}} {_fmt(value)}")
        else:
            out.append(f"{name} {_fmt(value)}")


def render_metrics(state):
    """state -> tekst ekspozycji Prometheus (CZYSTA funkcja, sedno self-testu offline).

    Zawsze emituje miodek_exporter_up i miodek_scrape_duration_seconds. Gdy exporter_up == 1
    (state ma dane), emituje pełny zestaw E1/E2/E4 + przebiegi Stage 2. Plik kończy się \\n.
    """
    out = []

    up = int(state.get("exporter_up", 0))
    dur = float(state.get("scrape_duration_seconds", 0.0))

    if up == 1:
        red = state.get("reduction") or {}
        attr = state.get("attribution") or {}
        health = state.get("health") or {}
        stage2 = state.get("stage2_runs") or []

        # --- E1: redukcja i wolumeny ---
        _block(out, "miodek_reduction_ratio", "gauge",
               "Udział treści, której model NIE tyka (1 - routed_ratio). Liczone z manifestu Stage 1.",
               [(None, red.get("reduction_ratio", 0.0))])
        _block(out, "miodek_routed_ratio", "gauge",
               "Udział treści routowanej do Stage 2 (hit rate; odniesienie autora ~0.04-0.05).",
               [(None, red.get("routed_ratio", 0.0))])
        _block(out, "miodek_total_words", "gauge",
               "Łączna liczba słów w korpusie (mianownik redukcji).",
               [(None, red.get("total_words", 0))])
        _block(out, "miodek_routed_words", "gauge",
               "Liczba słów w akapitach routowanych do Stage 2 (zawierających trafienie review).",
               [(None, red.get("routed_words", 0))])

        # --- E2: atrybucja per reguła i klasa (migawka bieżącego korpusu) ---
        hit_samples = []
        for r in attr.get("per_rule", []):
            rid = r.get("id", "?")
            if r.get("review", 0):
                hit_samples.append(({"rule": rid, "klasa": "review"}, r["review"]))
            if r.get("block", 0):
                hit_samples.append(({"rule": rid, "klasa": "block"}, r["block"]))
        _block(out, "miodek_hits_total", "gauge",
               "Trafienia per reguła i klasa (review/block) na bieżącym korpusie. UWAGA: to MIGAWKA "
               "(gauge), nie monotoniczny licznik mimo sufiksu _total (nazwa narzucona kontraktem). "
               "Serie zerowe pominięte.",
               hit_samples)

        # --- E4: zdrowie ekonomii + próg alarmu ---
        h = health.get("health", "N/A")
        # miodek_health: 1 dla OK, 0 dla ALARM. N/A NIE udaje OK — jawne osobną serią health_na.
        if h in ("OK", "ALARM"):
            _block(out, "miodek_health", "gauge",
                   "Zdrowie ekonomii E4: 1=OK (linter odsiewa), 0=ALARM (za dużo treści do modelu). "
                   "Stan N/A (próbka za mała) NIE jest tu emitowany — patrz miodek_health_na.",
                   [(None, 1 if h == "OK" else 0)])
        else:
            # N/A: nie emitujemy miodek_health (nie udajemy OK ani ALARM), tylko HELP/TYPE.
            _block(out, "miodek_health", "gauge",
                   "Zdrowie ekonomii E4: 1=OK, 0=ALARM. Bieżąco N/A (próbka za mała) — seria pominięta, "
                   "stan N/A sygnalizuje miodek_health_na.",
                   [])
        _block(out, "miodek_health_na", "gauge",
               "1 gdy zdrowie ekonomii = N/A (próbka < min_words, wskaźnik niewiarygodny), inaczej 0. "
               "Mała próbka NIE udaje OK.",
               [(None, 1 if h == "N/A" else 0)])
        _block(out, "miodek_routed_ratio_alarm_threshold", "gauge",
               "Próg alarmu E4 (routed_ratio_alarm z config.json). Linia odniesienia pod routed_ratio.",
               [(None, health.get("alarm_threshold", 0.0))])

        # --- Przebiegi Stage 2 per silnik/werdykt (REALNY panel, dziś pusty na atrapie) ---
        s2_samples = []
        for s in stage2:
            s2_samples.append(({"engine": s.get("engine", "?"),
                                "verdict": s.get("verdict", "?")}, s.get("count", 0)))
        _block(out, "miodek_stage2_runs_total", "counter",
               "Przebiegi Stage 2 per silnik i werdykt (append-only log decisions.jsonl). "
               "Wypełnia się DOPIERO gdy realny silnik (Bielik/OpenRouter) nazbiera przebiegów; "
               "dziś atrapa => może być pusty. Realny panel czekający na dane, nie zaślepka.",
               s2_samples)

    # --- Obserwowalność samego eksportera (zawsze) ---
    _block(out, "miodek_exporter_up", "gauge",
           "1 gdy ostatni zbiór metryk (collect_state) się udał, 0 na fail-soft (korpus/linter padł).",
           [(None, up)])
    _block(out, "miodek_scrape_duration_seconds", "gauge",
           "Czas budowy zestawu metryk przy ostatnim scrape (uruchomienie lintera + obliczenia).",
           [(None, dur)])

    return "\n".join(out) + "\n"


# ============================================================================
# (a) collect_state — efekty uboczne: linter (podproces), metryki, log Stage 2.
# ============================================================================


def _corpus_paths(corpus):
    """Zwraca listę ścieżek do przekazania linterowi. Linter sam rozwija katalog (rekursywnie

    *.md/*.txt) i globy, więc przekazujemy ścieżkę jak jest. Pusta/niepodana => katalog repo."""
    if not corpus:
        return [REPO_ROOT]
    return [corpus]


def build_manifest(corpus, profile=None, dict_path=None, lang="both"):
    """Buduje manifest Stage 1 uruchamiając ai_linter --format json na korpusie (podproces).

    UWAGA: linter zwraca exit 1 gdy którykolwiek plik = FAIL — to NORMALNY stan korpusu z
    manieryzmem, NIE błąd eksportera. Manifest JSON jest na stdout niezależnie od kodu wyjścia,
    więc parsujemy stdout i ignorujemy kod 0/1. Dopiero brak stdout / niepoprawny JSON / wyjątek
    podprocesu to realny błąd (sygnał do fail-soft w warstwie wyżej)."""
    cmd = [sys.executable, "-m", AI_LINTER_MODULE, "--format", "json", "--lang", lang]
    if profile:
        cmd += ["--profile", profile]
    if dict_path:
        cmd += ["--dict", dict_path]
    cmd += _corpus_paths(corpus)

    proc = subprocess.run(cmd, capture_output=True, text=True, env=_linter_env())
    stdout = proc.stdout or ""
    if not stdout.strip():
        raise RuntimeError(
            f"ai_linter nie zwrócił manifestu (exit {proc.returncode}); stderr: {proc.stderr[:300]}"
        )
    return json.loads(stdout)


def aggregate_stage2(log_path):
    """Czyta wspólny strumień JSONL i agreguje przebiegi Stage 2 per (engine, stage2_verdict).

    Zwraca listę {engine, verdict, count}, posortowaną stabilnie. Pusty/brakujący log => []
    (panel istnieje, ale bez serii — czeka na realny silnik). Odporne na brak pliku."""
    try:
        runs = runner.read_stage2_runs(log_path)
    except (OSError, ValueError):
        return []
    agg = {}
    for r in runs:
        key = (r.get("engine", "?"), r.get("stage2_verdict", "?"))
        agg[key] = agg.get(key, 0) + 1
    out = [{"engine": e, "verdict": v, "count": c} for (e, v), c in agg.items()]
    out.sort(key=lambda d: (d["engine"], d["verdict"]))
    return out


def collect_state(corpus, log_path, profile=None, dict_path=None, lang="both"):
    """Zbiera surowy state (czyste liczby) — efekty uboczne tu, render_metrics zostaje czysty.

    Woła build_manifest (podproces lintera), liczy metrics.* i economy_health (z progiem z configu),
    agreguje log Stage 2. Czas budowy mierzymy do miodek_scrape_duration_seconds. Wyjątek propaguje
    w górę (warstwa serwera robi fail-soft)."""
    t0 = time.monotonic()
    manifest = build_manifest(corpus, profile=profile, dict_path=dict_path, lang=lang)
    reduction = metrics.reduction_from_manifest(manifest)
    attribution = metrics.attribution_from_manifest(manifest)
    health = metrics.economy_health(manifest, economy=_config.load_economy())
    stage2 = aggregate_stage2(log_path)
    dur = time.monotonic() - t0
    return {
        "exporter_up": 1,
        "scrape_duration_seconds": dur,
        "reduction": reduction,
        "attribution": attribution,
        "health": health,
        "stage2_runs": stage2,
    }


# ============================================================================
# (c) serwer HTTP — cache state + fail-soft.
# ============================================================================


class _StateCache:
    """Cache ostatniego dobrego state z TTL. Wątkowo bezpieczny (lock).

    Scrape w oknie TTL zwraca cache (nie mieli lintera). Po TTL przebudowuje; błąd => fail-soft:
    zwraca ostatni dobry state, a gdy go brak — minimalny state z exporter_up=0."""

    def __init__(self, builder, ttl):
        self._builder = builder
        self._ttl = ttl
        self._lock = threading.Lock()
        self._ts = None
        self._state = None

    def get(self):
        with self._lock:
            now = time.monotonic()
            if self._state is not None and self._ts is not None and (now - self._ts) < self._ttl:
                return self._state
            try:
                state = self._builder()
                self._state = state
                self._ts = now
                return state
            except Exception as e:  # fail-soft: nie wywalamy serwera na awarii korpusu/lintera
                sys.stderr.write(f"[metrics_exporter] collect_state padło: {e}\n")
                if self._state is not None:
                    # Serwujemy ostatni dobry state (exporter_up zostaje 1 z poprzedniego zbioru).
                    return self._state
                return {"exporter_up": 0, "scrape_duration_seconds": 0.0}


def _make_handler(cache):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, content_type="text/plain; charset=utf-8"):
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802 (API http.server)
            path = self.path.split("?", 1)[0]
            if path == "/metrics":
                text = render_metrics(cache.get())
                self._send(200, text, CONTENT_TYPE)
            elif path == "/healthz":
                self._send(200, "ok\n")
            else:
                self._send(404, "not found\n")

        def log_message(self, fmt, *args):  # cisza: bez spamu access-log na stderr
            return

    return Handler


def _env(name, default=None):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def serve(host, port, corpus, log_path, profile, dict_path, lang, ttl):
    builder = lambda: collect_state(corpus, log_path, profile=profile, dict_path=dict_path, lang=lang)
    cache = _StateCache(builder, ttl)
    handler = _make_handler(cache)
    httpd = ThreadingHTTPServer((host, port), handler)
    sys.stderr.write(
        f"[metrics_exporter] nasłuch http://{host}:{port}/metrics "
        f"(korpus={corpus or REPO_ROOT}, log={log_path}, ttl={ttl}s)\n"
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


def main():
    ap = argparse.ArgumentParser(
        description="Eksporter metryk Stage 1 (E1/E2/E4) w formacie Prometheus (KAN-219). Zero-dep.",
    )
    ap.add_argument("--host", default=_env("MIODEK_HOST", "0.0.0.0"),
                    help="Adres nasłuchu (domyślnie 0.0.0.0 / env MIODEK_HOST).")
    ap.add_argument("--port", type=int, default=int(_env("MIODEK_PORT", "9112")),
                    help="Port serwera (domyślnie 9112 / env MIODEK_PORT).")
    ap.add_argument("--corpus", default=_env("MIODEK_CORPUS"),
                    help="Korpus do lintera (plik/glob/katalog). Domyślnie katalog repo / env MIODEK_CORPUS.")
    ap.add_argument("--log", default=_env("MIODEK_LOG", decision_log.DEFAULT_LOG_PATH),
                    help="Ścieżka decisions.jsonl (przebiegi Stage 2). Env MIODEK_LOG.")
    ap.add_argument("--profile", default=_env("MIODEK_PROFILE"),
                    help="Profil progów lintera (--profile). Env MIODEK_PROFILE.")
    ap.add_argument("--dict", dest="dict_path", default=_env("MIODEK_DICT"),
                    help="Słownik domenowy (--dict). Env MIODEK_DICT.")
    ap.add_argument("--lang", default=_env("MIODEK_LANG", "both"), choices=["pl", "en", "both"],
                    help="Język markerów (domyślnie both / env MIODEK_LANG).")
    ap.add_argument("--cache-ttl", type=float, default=float(_env("MIODEK_SCRAPE_CACHE_TTL", "30")),
                    help="TTL cache state w sekundach (domyślnie 30 / env MIODEK_SCRAPE_CACHE_TTL).")
    args = ap.parse_args()

    serve(args.host, args.port, args.corpus, args.log, args.profile, args.dict_path,
          args.lang, args.cache_ttl)


if __name__ == "__main__":
    main()
