#!/usr/bin/env python3
"""
runpod_lifecycle.py — AUTO-OFFLOAD poda RunPod po przebiegu Stage 2 (Epik H, KAN-220). ZERO-DEP.

PROBLEM: pod z modelem (Bielik na RunPodzie) bije pod prąd GPU także MIĘDZY przebiegami osądu.
Po wsadzie Stage 2 pod powinien gasnąć automatycznie. Sedno zadania to ODPORNOŚĆ teardownu:
musi zadziałać także gdy proces padnie. Stąd TRZY niezależne warstwy, żaden teardown nie jest
pojedynczym punktem awarii:

  1. Warstwa kontekstowa (`managed_pod`, blok `finally`): owija przebieg Stage 2; na wyjściu
     gasi pod ZAWSZE, także przy wyjątku (`__exit__` zwraca False — wyjątek propaguje, nie połyka).
     Na wejściu opcjonalnie wznawia pod (resume), gdy `ensure_running` i status != RUNNING.
  2. Warstwa sygnałów (handlery SIGINT/SIGTERM): przed zniknięciem procesu wołają teardown,
     PRZYWRACAJĄ poprzedni handler i re-raisują sygnał — nie połykają sygnału na stałe.
  3. Backstop po stronie poda (watchdog `tools/runpod_idle_watchdog.sh`): gasi pod po N sekundach
     bezczynności. Zabezpiecza `kill -9`, gdzie `finally` ani handler NIE wykonają się. To artefakt
     uruchamiany NA podzie (poza tym modułem) — patrz runpod-lifecycle.schema.md.

Moduł owija PRZEBIEG, nie zna wnętrza silnika (engines.py). Potrzebuje tylko `pod_id` z configu.

ZERO-DEP (stdlib: urllib.request/error, json, os, sys, signal). Warstwa HTTP jest WSTRZYKIWALNA
(parametr `transport`, DOKŁADNIE jak `_default_http_transport` w engines.py KAN-218), więc testy
są w pełni offline — `_default_rest_transport` NIGDY nie jest wołany pod atrapą.

KLUCZ API: czytany WYŁĄCZNIE z ENV (`RUNPOD_API_KEY`), NIGDY z pliku. Config trzyma tylko nazwę
zmiennej środowiskowej. Separacja: config = CO, ENV = SEKRET (spójnie z engines.py).

BŁĄD TEARDOWNU jest GŁOŚNY (stderr), nigdy połknięty po cichu — to bramka KOSZTOWA: nieugaszony
pod bije pod prąd GPU. Teardown jest bezpieczny do wielokrotnego wywołania (flaga `_torn_down`):
gdyby `finally` i handler sygnału trafiły razem, realny `stop`/`terminate` woła się tylko RAZ.
"""

import json
import os
import signal
import sys

# Baza REST RunPod (REST API v1). Auth: nagłówek Authorization: Bearer <RUNPOD_API_KEY>.
DEFAULT_BASE_URL = "https://rest.runpod.io/v1"
DEFAULT_API_KEY_ENV = "RUNPOD_API_KEY"

# Dozwolone polityki domknięcia poda po przebiegu.
ON_FINISH = ("stop", "terminate")


def _default_rest_transport(url, *, method, data, headers, timeout):
    """Jedyne miejsce dotykające sieci. Zwraca krotkę (status_int, body_str).

    stdlib only (urllib.request). Wstrzykiwalne — w testach podstawiamy atrapę, więc ta funkcja
    NIGDY nie jest wołana offline. W przeciwieństwie do engines._default_http_transport zwraca też
    kod HTTP (potrzebny do rozróżnienia 2xx OK vs 4xx/5xx). Obsługuje dowolną metodę (GET/POST/DELETE).

    HTTPError (4xx/5xx z ciałem) jest odczytywany jako (e.code, body) — to NIE wyjątek transportu,
    bo klient ma sam zmapować kod na RuntimeError. URLError (sieć leży) → RuntimeError."""
    import urllib.request
    import urllib.error
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        # 4xx/5xx: zwróć kod + ciało, niech klient zmapuje na czytelny RuntimeError.
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        return e.code, body
    except urllib.error.URLError as e:
        raise RuntimeError(f"REST RunPod do {url} nie powiódł się (sieć): {e}")


class RunPodClient:
    """Klient REST RunPod (REST API v1) — start/stop/terminate/status poda. ZERO-DEP.

    Operacje (potwierdzone w blueprincie KAN-220):
      stop(pod_id)      → POST   /pods/{id}/stop    — zwolnij GPU, dane w /workspace zostają,
      start(pod_id)     → POST   /pods/{id}/start   — wznów zatrzymany pod (resume),
      terminate(pod_id) → DELETE /pods/{id}         — trwała kasacja (poza network volume),
      status(pod_id)    → GET    /pods/{id}         — zwraca desiredStatus (RUNNING/EXITED/...).

    Klucz API czytany z ENV (`api_key_env`) w KONSTRUKTORZE (separacja config=CO, ENV=SEKRET, jak
    engines.py). Brak klucza => zapamiętany pusty; metody rzucą czytelny błąd przy realnym wywołaniu
    (offline z atrapą transportu klucz nie jest potrzebny). Warstwa HTTP wstrzykiwalna (`transport`)."""

    def __init__(self, api_key_env=DEFAULT_API_KEY_ENV, base_url=DEFAULT_BASE_URL,
                 timeout=30.0, transport=None):
        self._api_key = os.environ.get(api_key_env, "")
        self._api_key_env = api_key_env
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport or _default_rest_transport

    def _call(self, method, path, body=None):
        """Wspólna ścieżka: buduje nagłówki, woła transport, mapuje status (2xx OK, inaczej błąd).

        Realne wywołanie bez klucza => czytelny RuntimeError (zanim dotknie sieci). Zwraca
        sparsowany dict ciała (albo {} gdy ciało puste/nie-JSON)."""
        if not self._api_key:
            raise RuntimeError(
                f"RunPodClient: brak klucza API w ENV {self._api_key_env!r} "
                f"(sekret czytany WYŁĄCZNIE z ENV, nigdy z pliku)"
            )
        url = self.base_url + path
        headers = {"Authorization": f"Bearer {self._api_key}"}
        data = None
        if method in ("POST", "DELETE"):
            headers["Content-Type"] = "application/json"
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        status, raw = self._transport(
            url, method=method, data=data, headers=headers, timeout=self._timeout
        )
        if not (200 <= status < 300):
            raise RuntimeError(
                f"REST RunPod {method} {path} → HTTP {status}: {raw[:300]}"
            )
        try:
            return json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            return {}

    def stop(self, pod_id):
        """POST /pods/{id}/stop — zwolnij GPU (model zostaje na dysku)."""
        return self._call("POST", f"/pods/{pod_id}/stop")

    def start(self, pod_id):
        """POST /pods/{id}/start — wznów zatrzymany pod (resume)."""
        return self._call("POST", f"/pods/{pod_id}/start")

    def terminate(self, pod_id):
        """DELETE /pods/{id} — trwała kasacja poda."""
        return self._call("DELETE", f"/pods/{pod_id}")

    def status(self, pod_id):
        """GET /pods/{id} — zwraca desiredStatus (str) albo surowy dict, gdy brak pola."""
        data = self._call("GET", f"/pods/{pod_id}")
        ds = data.get("desiredStatus") if isinstance(data, dict) else None
        return ds if ds is not None else data


class managed_pod:
    """Menedżer kontekstu auto-offloadu poda RunPod (trzy warstwy teardownu — patrz docstring modułu).

    Użycie:
        client = RunPodClient(api_key_env=...)
        with managed_pod(client, pod_id, on_finish="stop"):
            result = run_stage2(manifest, engine=engine)
        # tu pod jest już zgaszony — także gdyby run_stage2 rzucił wyjątek albo przyszedł SIGTERM.

    Parametry (budowane z config stage2.lifecycle):
      client          — RunPodClient (albo dowolny obiekt z .stop/.start/.terminate/.status),
      pod_id          — id poda, którym zarządzamy,
      on_finish       — "stop" (domyślne: GPU gaśnie, model zostaje) | "terminate" (kasacja),
      ensure_running  — gdy True: na wejściu wznów pod (start), jeśli status != RUNNING,
      idle_backstop_s — informacyjnie (próg backstopu po stronie poda; tu nie wymuszany — to robi
                        watchdog NA podzie). Trzymany dla spójności konfiguracji i logu.

    Konstruktor z config: `managed_pod.from_config(client, cfg)` (cfg = sekcja lifecycle).

    INWARIANTY (sedno odporności):
      - teardown ZAWSZE w `finally` (też przy wyjątku; wyjątek propaguje — __exit__ zwraca False),
      - handlery SIGINT/SIGTERM wołają teardown, przywracają poprzedni handler i re-raisują sygnał,
      - teardown bezpieczny do wielokrotnego wywołania (flaga `_torn_down`) — realny stop raz,
      - błąd teardownu GŁOŚNO na stderr (nie połknięty) — bramka kosztowa GPU.
    """

    def __init__(self, client, pod_id, on_finish="stop", ensure_running=True,
                 idle_backstop_s=None):
        if on_finish not in ON_FINISH:
            raise ValueError(
                f"managed_pod.on_finish musi być jednym z {ON_FINISH}, jest {on_finish!r}"
            )
        if not pod_id:
            raise ValueError("managed_pod wymaga niepustego pod_id")
        self.client = client
        self.pod_id = pod_id
        self.on_finish = on_finish
        self.ensure_running = ensure_running
        self.idle_backstop_s = idle_backstop_s
        self._torn_down = False
        self._prev_handlers = {}  # sig -> poprzedni handler (przywracany w __exit__/handlerze)

    @classmethod
    def from_config(cls, client, cfg):
        """Buduje menedżera z sekcji config stage2.lifecycle (dict). Walidacja w __init__."""
        return cls(
            client,
            pod_id=cfg.get("pod_id", ""),
            on_finish=cfg.get("on_finish", "stop"),
            ensure_running=cfg.get("ensure_running", True),
            idle_backstop_s=cfg.get("idle_backstop_s"),
        )

    # ---- Warstwa 1: kontekst (finally-teardown) ----

    def __enter__(self):
        # Wejście: opcjonalnie wznów pod (resume), gdy ma być RUNNING a nie jest.
        if self.ensure_running:
            try:
                st = self.client.status(self.pod_id)
                if st != "RUNNING":
                    self.client.start(self.pod_id)
            except Exception as e:
                # Wznowienie to best-effort: silnik i tak rzuci, jeśli endpoint nieżywy. Nie
                # przerywamy przebiegu — ale logujemy głośno, bo to sygnał diagnostyczny.
                print(
                    f"[managed_pod] OSTRZEŻENIE: wznowienie poda {self.pod_id} nie powiodło się: {e}",
                    file=sys.stderr,
                )
        self._install_signal_handlers()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._teardown()  # ZAWSZE — także przy wyjątku w bloku with
        finally:
            self._restore_signal_handlers()
        return False  # NIE połykaj wyjątku — niech propaguje

    # ---- Warstwa 2: handlery sygnałów ----

    def _install_signal_handlers(self):
        """Instaluje handlery SIGINT/SIGTERM, zapamiętując poprzednie (do przywrócenia).

        Instalacja sygnałów działa tylko w głównym wątku procesu (ograniczenie modułu signal);
        w innym wątku po cichu pomijamy — warstwa 1 (finally) i warstwa 3 (watchdog) zostają."""
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self._prev_handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, self._signal_handler)
            except (ValueError, OSError):
                # np. nie główny wątek — pomijamy instalację dla tego sygnału.
                self._prev_handlers.pop(sig, None)

    def _restore_signal_handlers(self):
        """Przywraca poprzednie handlery SIGINT/SIGTERM (nie połykamy sygnału na stałe)."""
        for sig, prev in list(self._prev_handlers.items()):
            try:
                signal.signal(sig, prev)
            except (ValueError, OSError):
                pass
        self._prev_handlers.clear()

    def _signal_handler(self, signum, frame):
        """Handler SIGINT/SIGTERM: gasi pod, przywraca poprzedni handler i RE-RAISUJE sygnał.

        Re-raise (os.kill(getpid, signum)) zachowuje normalną semantykę sygnału (np. domyślne
        zakończenie procesu / KeyboardInterrupt) — nie połykamy sygnału na stałe."""
        try:
            self._teardown()
        finally:
            prev = self._prev_handlers.get(signum)
            # Przywróć poprzedni handler tego sygnału, potem re-raise.
            try:
                if prev is not None:
                    signal.signal(signum, prev)
                    self._prev_handlers.pop(signum, None)
            except (ValueError, OSError):
                pass
            os.kill(os.getpid(), signum)

    # ---- Teardown bezpieczny do wielokrotnego wywołania ----

    def _teardown(self):
        """Gasi pod wg `on_finish`. Bezpieczny do wielokrotnego wywołania (flaga _torn_down):

        pierwsze wejście ustawia flagę PRZED realnym wywołaniem (gdyby stop sam wywołał re-entrancy)
        i woła client.stop/terminate; każde kolejne wejście to NO-OP. Błąd gaszenia leci GŁOŚNO na
        stderr i NIE jest połykany w sensie ciszy — to bramka kosztowa GPU. (W kontekście finally
        wyjątek teardownu nie powinien jednak maskować pierwotnego wyjątku przebiegu, więc logujemy
        i kontynuujemy; głośny log na stderr jest tu sygnałem operacyjnym.)"""
        if self._torn_down:
            return
        self._torn_down = True
        try:
            if self.on_finish == "terminate":
                self.client.terminate(self.pod_id)
            else:
                self.client.stop(self.pod_id)
        except Exception as e:
            print(
                f"[managed_pod] BŁĄD TEARDOWNU: nie udało się {self.on_finish} poda "
                f"{self.pod_id}: {e} — POD MOŻE NADAL BIĆ POD PRĄD GPU, sprawdź ręcznie "
                f"(REST stop / panel RunPod).",
                file=sys.stderr,
            )


def build_client_from_lifecycle(cfg, transport=None):
    """Buduje RunPodClient z sekcji config stage2.lifecycle.

    `cfg` to dict lifecycle (z config.load_lifecycle). Czyta nazwę ENV z `api_key_env`
    (domyślnie RUNPOD_API_KEY); sam sekret bierze konstruktor klienta z os.environ.
    `transport` wstrzykiwalny (testy). Zwraca RunPodClient."""
    return RunPodClient(
        api_key_env=cfg.get("api_key_env", DEFAULT_API_KEY_ENV),
        base_url=cfg.get("base_url", DEFAULT_BASE_URL),
        transport=transport,
    )
