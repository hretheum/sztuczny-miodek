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


class _SignalTeardownMixin:
    """Wspólne warstwy 2 teardownu (handlery SIGINT/SIGTERM) dla menedżerów kontekstu poda.

    Wydzielone z `managed_pod`, by `managed_ephemeral_pod` (KAN-222) miało TĘ SAMĄ odporność
    (KAN-220) bez duplikacji: instalacja/przywrócenie/handler sygnałów + flaga `_torn_down`.
    Klasa pochodna MUSI zdefiniować `_teardown(self)` (gaszenie wg własnej polityki) oraz w
    konstruktorze ustawić `self._torn_down = False` i `self._prev_handlers = {}`.

    INWARIANTY:
      - handlery SIGINT/SIGTERM wołają teardown, przywracają poprzedni handler i RE-RAISUJĄ sygnał,
      - instalacja działa tylko w głównym wątku (ograniczenie modułu signal); poza nim po cichu
        pomijana — warstwa 1 (finally) i warstwa 3 (watchdog na podzie) zostają.
    """

    def _install_signal_handlers(self):
        """Instaluje handlery SIGINT/SIGTERM, zapamiętując poprzednie (do przywrócenia)."""
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
            try:
                if prev is not None:
                    signal.signal(signum, prev)
                    self._prev_handlers.pop(signum, None)
            except (ValueError, OSError):
                pass
            os.kill(os.getpid(), signum)


class managed_pod(_SignalTeardownMixin):
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

    # ---- Warstwa 2: handlery sygnałów (wspólne, w _SignalTeardownMixin) ----

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


# ============================================================================
# KAN-222 — EFEMERYCZNY pod (jeden krok zamiast ręcznej sekwencji, flaga --runpod).
# ============================================================================
#
# Inny cykl życia niż managed_pod: tamto ZARZĄDZA istniejącym podem (start/stop/terminate),
# to TWORZY pod na wejściu i TERMINUJE na wyjściu. Reużywa launcher tools/runpod_pod_up.py
# (create_pod/wait_for_ollama/ensure_model) — zero duplikacji logiki stawiania.


class managed_ephemeral_pod(_SignalTeardownMixin):
    """Menedżer kontekstu EFEMERYCZNEGO poda RunPod (KAN-222): create → wait → ensure_model →
    (przebieg) → TERMINATE. Ten sam warstwowy teardown co managed_pod (finally + sygnały +
    bezpieczeństwo wielokrotnego wywołania, KAN-220), tylko że gasimy przez `terminate` (kasacja
    efemerycznego poda — nie ma czego zachowywać poza wolumenem sieciowym z modelem).

    Użycie (flaga --runpod):
        ctx = managed_ephemeral_pod(api_key_env="RUNPOD_API_KEY", volume_id="...", dc="EU-NL-1",
                                    mount="/root/.ollama", image="ollama/ollama:latest",
                                    model="hf.co/.../Bielik-...-GGUF:Q4_K_M")
        with ctx as pod:
            engine = OllamaEngine(host=pod.url, model=...)
            result = run_stage2(manifest, engine=engine)
        # tu pod jest już zterminowany — także przy wyjątku / SIGTERM.

    GWARANCJA braku osieroconego poda: jeśli `wait_for_ollama`/`ensure_model` zawiodą w __enter__,
    JUŻ utworzony pod jest terminowany PRZED rzuceniem RuntimeError (inaczej pod bije pod prąd, a
    proces nie wszedł nawet w `with`, więc finally by go nie dotknęło). Plus: __exit__/finally,
    handler sygnału, flaga `_torn_down` (realny terminate raz).

    Klucz API z ENV (`api_key_env`) — sekret NIGDY w pliku/argumencie (spójnie z RunPodClient).
    Warstwa REST WSTRZYKIWALNA dla testów offline. UWAGA: są DWA NIEZGODNE kontrakty transportu,
    więc są DWA osobne parametry (nie wolno ich mieszać):
      - `pod_up` (domyślnie moduł runpod_pod_up): test podstawia atrapę z create_pod/wait/ensure,
      - `pod_up_transport`: transport launchera (KONTRAKT `runpod_pod_up._default_transport`:
        `(method, url, *, data, headers, timeout)` — method i url POZYCYJNIE). Idzie do create_pod.
      - `client_transport`: transport klienta REST (KONTRAKT `RunPodClient._default_rest_transport`:
        `(url, *, method, data, headers, timeout)` — url pozycyjnie, method jako keyword). Idzie do
        RunPodClient.terminate. NIE jest kompatybilny z create_pod (inna sygnatura) — dlatego osobno.
    Pod żadną atrapą realna sieć (urllib) nie jest dotykana.
    """

    def __init__(self, *, api_key_env=DEFAULT_API_KEY_ENV, base_url=DEFAULT_BASE_URL,
                 volume_id, dc, mount="/root/.ollama", image="ollama/ollama:latest",
                 model="hf.co/speakleash/Bielik-11B-v3.0-Instruct-GGUF:Q4_K_M",
                 gpus=None, name="miodek-bielik", no_model=False,
                 client_transport=None, pod_up_transport=None, pod_up=None, wait_kwargs=None):
        if not volume_id:
            raise ValueError("managed_ephemeral_pod wymaga niepustego volume_id")
        if not dc:
            raise ValueError("managed_ephemeral_pod wymaga niepustego dc (data center)")
        if not model and not no_model:
            raise ValueError("managed_ephemeral_pod wymaga model (albo no_model=True)")
        self._api_key_env = api_key_env
        self.base_url = base_url
        self.volume_id = volume_id
        self.dc = dc
        self.mount = mount
        self.image = image
        self.model = model
        self.no_model = no_model
        self.name = name
        # Lazy-import launchera, by uniknąć cyklu importów na poziomie modułu (i pozwolić wstrzyknąć).
        if pod_up is None:
            from miodek import runpod_pod_up as pod_up
        self._pod_up = pod_up
        self.gpus = gpus if gpus is not None else list(pod_up.DEFAULT_GPUS)
        # DWA niezgodne kontrakty transportu (patrz docstring) — trzymane ROZDZIELNIE:
        #   _pod_up_transport → create_pod (kontrakt launchera: method, url pozycyjnie),
        #   _client_transport → RunPodClient.terminate (kontrakt klienta: url pozycyjnie, method kw).
        self._pod_up_transport = pod_up_transport
        self._client_transport = client_transport
        self._wait_kwargs = dict(wait_kwargs or {})
        # Klient REST do TERMINATE — klucz z ENV w konstruktorze (separacja config=CO, ENV=SEKRET).
        self._client = RunPodClient(
            api_key_env=api_key_env, base_url=base_url, transport=client_transport
        )
        self.url = None
        self.pod_id = None
        self._torn_down = False
        self._prev_handlers = {}

    @classmethod
    def from_config(cls, cfg, *, client_transport=None, pod_up_transport=None,
                    pod_up=None, wait_kwargs=None):
        """Buduje menedżera z sekcji config `stage2.runpod` (dict z config.load_runpod).

        Dwa rozdzielne transporty (niezgodne kontrakty — patrz docstring klasy): `client_transport`
        do RunPodClient.terminate, `pod_up_transport` do create_pod (launcher)."""
        return cls(
            api_key_env=cfg.get("api_key_env", DEFAULT_API_KEY_ENV),
            base_url=cfg.get("base_url", DEFAULT_BASE_URL),
            volume_id=cfg.get("volume"),
            dc=cfg.get("dc"),
            mount=cfg.get("mount", "/root/.ollama"),
            image=cfg.get("image", "ollama/ollama:latest"),
            model=cfg.get("model"),
            gpus=cfg.get("gpu"),
            name=cfg.get("name", "miodek-bielik"),
            no_model=bool(cfg.get("no_model", False)),
            client_transport=client_transport,
            pod_up_transport=pod_up_transport,
            pod_up=pod_up,
            wait_kwargs=wait_kwargs,
        )

    # ---- Warstwa 1: kontekst (create na wejściu, terminate w finally) ----

    def __enter__(self):
        api_key = os.environ.get(self._api_key_env, "")
        if not api_key:
            raise RuntimeError(
                f"managed_ephemeral_pod: brak klucza API w ENV {self._api_key_env!r} "
                f"(sekret czytany WYŁĄCZNIE z ENV, nigdy z pliku)"
            )
        # 1. Postaw pod (z wolumenu — model nie jest pobierany, jeśli już leży na wolumenie).
        pod = self._pod_up.create_pod(
            api_key, self.volume_id, self.dc, self.mount, self.image,
            self.gpus, self.name, transport=self._pod_up_transport,
        )
        self.pod_id = pod["id"]  # launcher czyta pod["id"] (NIE podId) — spójnie.
        self.url = f"https://{self.pod_id}-11434.proxy.runpod.net"
        print(
            f"[managed_ephemeral_pod] utworzony efemeryczny pod {self.pod_id} "
            f"(DC {self.dc}, wolumen {self.volume_id})",
            file=sys.stderr,
        )
        # Handlery sygnałów instalujemy ZARAZ po utworzeniu poda — od tej chwili SIGTERM ma go zgasić.
        self._install_signal_handlers()
        # 2. Czekaj na Ollamę; 3. zapewnij model. Błąd => zterminuj osierocony pod PRZED rzuceniem.
        try:
            if not self._pod_up.wait_for_ollama(self.url, **self._wait_kwargs):
                raise RuntimeError(
                    f"managed_ephemeral_pod: Ollama nie wstała na {self.url} "
                    f"(pod {self.pod_id} zostanie zterminowany)"
                )
            if not self.no_model:
                if not self._pod_up.ensure_model(self.url, self.model):
                    raise RuntimeError(
                        f"managed_ephemeral_pod: nie udało się zapewnić modelu {self.model} "
                        f"na {self.url} (pod {self.pod_id} zostanie zterminowany)"
                    )
        except BaseException:
            # Sprzątanie osieroconego poda: terminate PRZED propagacją (finally by go nie dotknęło,
            # bo proces nie wszedł w blok `with`). Restore handlerów, by nie zostawić ich na stałe.
            self._teardown()
            self._restore_signal_handlers()
            raise
        print(
            f"[managed_ephemeral_pod] pod {self.pod_id} gotowy (Ollama + model {self.model})",
            file=sys.stderr,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._teardown()  # ZAWSZE — także przy wyjątku w bloku with
        finally:
            self._restore_signal_handlers()
        return False  # NIE połykaj wyjątku — niech propaguje

    # ---- Teardown bezpieczny do wielokrotnego wywołania ----

    def _teardown(self):
        """TERMINUJE efemeryczny pod. Bezpieczny do wielokrotnego wywołania (flaga _torn_down):

        pierwsze wejście ustawia flagę PRZED realnym wywołaniem i woła client.terminate; każde
        kolejne to NO-OP. Gdy pod jeszcze nie powstał (create_pod nie zwrócił id), nie ma czego
        gasić. Błąd terminacji leci GŁOŚNO na stderr — to bramka KOSZTOWA GPU (nieugaszony pod)."""
        if self._torn_down:
            return
        self._torn_down = True
        if not self.pod_id:
            return  # pod nie powstał — nic do gaszenia
        try:
            self._client.terminate(self.pod_id)
        except Exception as e:
            print(
                f"[managed_ephemeral_pod] BŁĄD TEARDOWNU: nie udało się zterminować poda "
                f"{self.pod_id}: {e} — POD MOŻE NADAL BIĆ POD PRĄD GPU, sprawdź ręcznie "
                f"(REST DELETE / panel RunPod).",
                file=sys.stderr,
            )
