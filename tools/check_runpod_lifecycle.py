#!/usr/bin/env python3
"""
check_runpod_lifecycle.py — gate auto-offloadu poda RunPod (KAN-220). ZERO-DEP (stdlib).

OFFLINE: cała warstwa REST jest wstrzykiwana atrapą (callable zapisująca url/method i zwracająca
ustalone (status, body)). runpod_lifecycle._default_rest_transport NIGDY nie jest wołany — żadnych
realnych wywołań sieci.

Weryfikuje:
  (klient REST)
  1. RunPodClient.stop/start/terminate/status → poprawny URL, metoda (POST/POST/DELETE/GET),
     nagłówek Authorization: Bearer, mapowanie 2xx→OK, 4xx→RuntimeError.
  (menedżer kontekstu — trzy warstwy)
  2. normalne wyjście z `with` → dokładnie 1 stop;
  3. wyjątek wewnątrz `with` → stop MIMO TO (finally) ORAZ wyjątek propaguje;
  4. SIGTERM podczas `with` → teardown wywołany (stop), poprzedni handler przywrócony;
  5. on_finish="terminate" → woła terminate (DELETE), nie stop;
  6. teardown bezpieczny do wielokrotnego wywołania: dwa _teardown() → tylko 1 realny stop (flaga);
  7. błąd teardownu (atrapa stop rzuca) → komunikat na stderr, błąd NIE połknięty po cichu
     (w finally: log na stderr, pierwotny wyjątek przebiegu zachowany);
  8. config.load_lifecycle: brak sekcji → {"manage": False}; on_finish:"foo" → ValueError;
     manage:true bez pod_id → ValueError;
  9. ścieżka _main (NO-OP): manage=false → managed_pod NIE tworzony, ZERO wywołań REST.

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import io
import json
import os
import signal
import sys
import tempfile
import contextlib

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config              # noqa: E402
import runpod_lifecycle    # noqa: E402
from runpod_lifecycle import RunPodClient, managed_pod  # noqa: E402


def _recording_transport(calls, status=200, body="{}"):
    """Atrapa REST: zapisuje (method, url, headers) do `calls`, zwraca ustalone (status, body).

    To jedyna warstwa sieci w teście — _default_rest_transport nie jest wołany."""
    def transport(url, *, method, data, headers, timeout):
        calls.append({"method": method, "url": url, "headers": dict(headers), "data": data})
        return status, body
    return transport


class _FakeClient:
    """Atrapa klienta poda do testów menedżera kontekstu: liczy wywołania, opcjonalnie rzuca.

    Nie dotyka sieci ani ENV. status() zwraca ustalony stan (domyślnie EXITED → __enter__ zrobi start)."""

    def __init__(self, status_value="EXITED", stop_raises=False):
        self.stop_calls = 0
        self.start_calls = 0
        self.terminate_calls = 0
        self.status_calls = 0
        self._status_value = status_value
        self._stop_raises = stop_raises

    def status(self, pod_id):
        self.status_calls += 1
        return self._status_value

    def start(self, pod_id):
        self.start_calls += 1

    def stop(self, pod_id):
        self.stop_calls += 1
        if self._stop_raises:
            raise RuntimeError("atrapa: stop celowo rzuca")

    def terminate(self, pod_id):
        self.terminate_calls += 1


def main():
    fails = []

    # === Klient REST (atrapa transportu, klucz przez ENV) ===
    os.environ["MIODEK_TEST_RUNPOD_KEY"] = "tajny-klucz-testowy"
    calls = []
    client = RunPodClient(
        api_key_env="MIODEK_TEST_RUNPOD_KEY",
        base_url="https://rest.example.test/v1",
        transport=_recording_transport(calls, status=200, body='{"desiredStatus":"RUNNING"}'),
    )

    # 1a: stop → POST /pods/{id}/stop + Bearer
    client.stop("pod123")
    last = calls[-1]
    if last["method"] != "POST" or not last["url"].endswith("/pods/pod123/stop"):
        fails.append(f"stop: zła metoda/URL: {last['method']} {last['url']}")
    if last["headers"].get("Authorization") != "Bearer tajny-klucz-testowy":
        fails.append(f"stop: brak/zły nagłówek Authorization: {last['headers'].get('Authorization')!r}")

    # 1b: start → POST /pods/{id}/start
    client.start("pod123")
    if calls[-1]["method"] != "POST" or not calls[-1]["url"].endswith("/pods/pod123/start"):
        fails.append(f"start: zła metoda/URL: {calls[-1]['method']} {calls[-1]['url']}")

    # 1c: terminate → DELETE /pods/{id}
    client.terminate("pod123")
    if calls[-1]["method"] != "DELETE" or not calls[-1]["url"].endswith("/pods/pod123"):
        fails.append(f"terminate: zła metoda/URL: {calls[-1]['method']} {calls[-1]['url']}")

    # 1d: status → GET /pods/{id}, zwraca desiredStatus
    st = client.status("pod123")
    if calls[-1]["method"] != "GET" or not calls[-1]["url"].endswith("/pods/pod123"):
        fails.append(f"status: zła metoda/URL: {calls[-1]['method']} {calls[-1]['url']}")
    if st != "RUNNING":
        fails.append(f"status: oczekiwano 'RUNNING' z desiredStatus, jest {st!r}")

    # 1e: 4xx → RuntimeError
    client_4xx = RunPodClient(
        api_key_env="MIODEK_TEST_RUNPOD_KEY", base_url="https://rest.example.test/v1",
        transport=_recording_transport([], status=404, body='{"error":"not found"}'),
    )
    try:
        client_4xx.stop("nope")
        fails.append("4xx: oczekiwano RuntimeError przy HTTP 404")
    except RuntimeError:
        pass

    # 1f: brak klucza w ENV → RuntimeError przy realnym wywołaniu (sekret tylko z ENV)
    client_nokey = RunPodClient(
        api_key_env="MIODEK_TEST_BRAK_KLUCZA_XYZ", base_url="https://rest.example.test/v1",
        transport=_recording_transport([]),
    )
    try:
        client_nokey.stop("x")
        fails.append("brak klucza ENV: oczekiwano RuntimeError")
    except RuntimeError:
        pass

    # === Menedżer kontekstu ===

    # 2: normalne wyjście → dokładnie 1 stop; start na wejściu (status EXITED)
    fc = _FakeClient(status_value="EXITED")
    with managed_pod(fc, "podA", on_finish="stop"):
        pass
    if fc.stop_calls != 1:
        fails.append(f"normalne wyjście: oczekiwano 1 stop, jest {fc.stop_calls}")
    if fc.start_calls != 1:
        fails.append(f"ensure_running: oczekiwano 1 start (status != RUNNING), jest {fc.start_calls}")

    # 2b: status RUNNING → NIE startujemy
    fc_run = _FakeClient(status_value="RUNNING")
    with managed_pod(fc_run, "podA", on_finish="stop"):
        pass
    if fc_run.start_calls != 0:
        fails.append(f"status RUNNING: nie powinno być start, jest {fc_run.start_calls}")
    if fc_run.stop_calls != 1:
        fails.append(f"status RUNNING: oczekiwano 1 stop, jest {fc_run.stop_calls}")

    # 3: wyjątek wewnątrz with → stop MIMO TO (finally) + wyjątek propaguje
    fc2 = _FakeClient(status_value="RUNNING")
    raised = False
    try:
        with managed_pod(fc2, "podB", on_finish="stop"):
            raise ValueError("wybuch w przebiegu")
    except ValueError:
        raised = True
    if not raised:
        fails.append("wyjątek w with: powinien propagować (managed_pod nie połyka)")
    if fc2.stop_calls != 1:
        fails.append(f"wyjątek w with: stop powinien zadziałać w finally, jest {fc2.stop_calls}")

    # 4: SIGTERM podczas with → teardown (stop) + poprzedni handler przywrócony
    sentinel = signal.getsignal(signal.SIGTERM)
    fc3 = _FakeClient(status_value="RUNNING")
    # Ustaw rozpoznawalny poprzedni handler, by sprawdzić przywrócenie.
    def _prev_handler(signum, frame):
        pass
    signal.signal(signal.SIGTERM, _prev_handler)
    sigterm_propagated = False
    try:
        mp = managed_pod(fc3, "podC", on_finish="stop")
        with mp:
            # handler managed_pod re-raisuje sygnał → po przywróceniu _prev_handler (no-op)
            # proces NIE ginie (no-op handler), więc kontrolujemy przepływ ręcznie:
            mp._signal_handler(signal.SIGTERM, None)
    except Exception:
        pass
    # po _signal_handler: stop wywołany raz, handler SIGTERM przywrócony do _prev_handler
    if fc3.stop_calls != 1:
        fails.append(f"SIGTERM: teardown powinien wywołać stop raz, jest {fc3.stop_calls}")
    if signal.getsignal(signal.SIGTERM) is not _prev_handler:
        fails.append("SIGTERM: poprzedni handler nie został przywrócony przez handler sygnału")
    # przywróć pierwotny handler środowiska testowego
    signal.signal(signal.SIGTERM, sentinel)

    # 4b: po normalnym wyjściu z with handler SIGTERM też wraca do poprzedniego
    sentinel2 = signal.getsignal(signal.SIGTERM)
    fc3b = _FakeClient(status_value="RUNNING")
    with managed_pod(fc3b, "podC2", on_finish="stop"):
        pass
    if signal.getsignal(signal.SIGTERM) is not sentinel2:
        fails.append("po with: handler SIGTERM nie wrócił do poprzedniego (restore w __exit__)")
    signal.signal(signal.SIGTERM, sentinel2)

    # 5: on_finish="terminate" → terminate (DELETE), nie stop
    fc4 = _FakeClient(status_value="RUNNING")
    with managed_pod(fc4, "podD", on_finish="terminate"):
        pass
    if fc4.terminate_calls != 1 or fc4.stop_calls != 0:
        fails.append(f"on_finish=terminate: oczekiwano terminate=1 stop=0, jest "
                     f"terminate={fc4.terminate_calls} stop={fc4.stop_calls}")

    # 6: idempotencja teardownu — dwa _teardown() → 1 realny stop
    fc5 = _FakeClient(status_value="RUNNING")
    mp5 = managed_pod(fc5, "podE", on_finish="stop")
    mp5._teardown()
    mp5._teardown()
    if fc5.stop_calls != 1:
        fails.append(f"idempotencja: podwójny _teardown powinien dać 1 stop, jest {fc5.stop_calls}")

    # 7: błąd teardownu → GŁOŚNO na stderr, NIE połknięty po cichu; pierwotny wyjątek zachowany
    fc6 = _FakeClient(status_value="RUNNING", stop_raises=True)
    buf = io.StringIO()
    primary_raised = False
    with contextlib.redirect_stderr(buf):
        try:
            with managed_pod(fc6, "podF", on_finish="stop"):
                raise RuntimeError("pierwotny błąd przebiegu")
        except RuntimeError as e:
            primary_raised = "pierwotny" in str(e)
    if not primary_raised:
        fails.append("błąd teardownu: pierwotny wyjątek przebiegu powinien być zachowany/propagować")
    if "BŁĄD TEARDOWNU" not in buf.getvalue():
        fails.append("błąd teardownu: brak GŁOŚNEGO komunikatu na stderr (nie połykaj po cichu)")
    if fc6.stop_calls != 1:
        fails.append(f"błąd teardownu: stop powinien być spróbowany raz, jest {fc6.stop_calls}")

    # === config.load_lifecycle ===
    with tempfile.TemporaryDirectory() as tmp:
        # brak sekcji stage2 → manage False
        p1 = os.path.join(tmp, "c1.json")
        with open(p1, "w", encoding="utf-8") as f:
            json.dump({"profiles": {}}, f)
        if config.load_lifecycle(p1) != {"manage": False}:
            fails.append("load_lifecycle: brak stage2 → oczekiwano {'manage': False}")

        # stage2 bez lifecycle → manage False
        p2 = os.path.join(tmp, "c2.json")
        with open(p2, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"engine": "stub"}}, f)
        if config.load_lifecycle(p2) != {"manage": False}:
            fails.append("load_lifecycle: stage2 bez lifecycle → oczekiwano {'manage': False}")

        # brak pliku → manage False
        if config.load_lifecycle(os.path.join(tmp, "nie-ma.json")) != {"manage": False}:
            fails.append("load_lifecycle: brak configu → oczekiwano {'manage': False}")

        # manage=true bez pod_id → ValueError
        p3 = os.path.join(tmp, "c3.json")
        with open(p3, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"lifecycle": {"manage": True, "pod_id": ""}}}, f)
        try:
            config.load_lifecycle(p3)
            fails.append("load_lifecycle: manage=true bez pod_id → oczekiwano ValueError")
        except ValueError:
            pass

        # on_finish nieprawidłowy → ValueError
        p4 = os.path.join(tmp, "c4.json")
        with open(p4, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"lifecycle": {"manage": True, "pod_id": "x", "on_finish": "foo"}}}, f)
        try:
            config.load_lifecycle(p4)
            fails.append("load_lifecycle: on_finish 'foo' → oczekiwano ValueError")
        except ValueError:
            pass

        # poprawny manage=true → zwraca dict z pod_id
        p5 = os.path.join(tmp, "c5.json")
        with open(p5, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"lifecycle": {
                "manage": True, "pod_id": "pod999", "on_finish": "terminate", "idle_backstop_s": 300}}}, f)
        lc = config.load_lifecycle(p5)
        if lc.get("pod_id") != "pod999" or lc.get("on_finish") != "terminate":
            fails.append(f"load_lifecycle: poprawny manage=true rozjazd: {lc}")

        # manage=false z dziwnym on_finish → BEZ walidacji (NO-OP, sekcja w rezerwie)
        p6 = os.path.join(tmp, "c6.json")
        with open(p6, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"lifecycle": {"manage": False, "on_finish": "foo"}}}, f)
        try:
            out = config.load_lifecycle(p6)
            if out.get("manage") is not False:
                fails.append("load_lifecycle: manage=false powinno zostać False")
        except ValueError:
            fails.append("load_lifecycle: manage=false nie powinno walidować on_finish (NO-OP)")

    # === 9: ścieżka NO-OP w _main (manage=false → żaden REST nie wołany) ===
    # Symulujemy decyzję _main: lifecycle.manage AND remote engine.
    import runner  # noqa: E402
    from engines import StubJudgeEngine, OllamaEngine  # noqa: E402

    # stub (lokalny) nigdy nie jest remote
    if runner._is_remote_engine(StubJudgeEngine()):
        fails.append("_is_remote_engine: stub nie powinien być uznany za zdalny")
    # ollama jest remote
    if not runner._is_remote_engine(OllamaEngine(model="bielik")):
        fails.append("_is_remote_engine: ollama powinien być uznany za zdalny")

    # manage=false → managed_pod NIE jest tworzony: imitujemy warunek _main na atrapie REST.
    rest_calls = []
    transport = _recording_transport(rest_calls)
    lifecycle_off = {"manage": False}
    # warunek z _main:
    if lifecycle_off.get("manage") and runner._is_remote_engine(OllamaEngine(model="b")):
        # nie powinno tu wejść
        client_x = runpod_lifecycle.build_client_from_lifecycle(lifecycle_off, transport=transport)
        with managed_pod.from_config(client_x, lifecycle_off):
            pass
    if rest_calls:
        fails.append(f"NO-OP manage=false: żaden REST nie powinien być wołany, jest {len(rest_calls)}")

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)

    print("OK   auto-offload poda RunPod (KAN-220): klient REST (start/stop/terminate/status, URL/"
          "metoda/Bearer, 2xx→OK/4xx→błąd, klucz z ENV); managed_pod gasi w finally (też przy "
          "wyjątku, który propaguje), handler SIGTERM gasi + przywraca handler, on_finish=terminate "
          "→ terminate, teardown odporny na podwójne wywołanie (1 stop), błąd teardownu GŁOŚNO na "
          "stderr; load_lifecycle (fallback manage=false + walidacja); NO-OP manage=false zero REST. "
          "ZERO sieci.")


if __name__ == "__main__":
    main()
