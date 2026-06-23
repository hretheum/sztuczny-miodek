#!/usr/bin/env python3
"""
check_runpod_ephemeral.py — gate trybu EFEMERYCZNEGO poda i flagi --runpod (KAN-222). ZERO-DEP.

OFFLINE: cała warstwa REST wstrzyknięta atrapą. Launcher (runpod_pod_up) jest atrapowany modułem
zastępczym (create_pod/wait_for_ollama/ensure_model), a RunPodClient.terminate idzie przez atrapę
transportu zapisującą wywołania. ŻADNEJ realnej sieci ani realnego poda. urllib NIGDY nie wołany.

Weryfikuje:
  (managed_ephemeral_pod — cykl create → terminate, trzy warstwy teardownu)
  1. happy path: na wejściu create wołane, url = https://<id>-11434.proxy.runpod.net; na wyjściu
     DOKŁADNIE jeden terminate (DELETE /pods/<id>);
  2. wyjątek wewnątrz `with` → terminate MIMO TO (finally) + wyjątek propaguje;
  3. wait_for_ollama → False w __enter__ → terminate (sprzątanie osieroconego poda) + RuntimeError;
  4. ensure_model → False w __enter__ → terminate + RuntimeError;
  5. podwójny _teardown → tylko 1 realny terminate (flaga _torn_down);
  6. brak klucza w ENV → RuntimeError przy __enter__ (sekret tylko z ENV), create NIE wołany;
  7. SIGTERM podczas `with` → terminate + poprzedni handler przywrócony;
  (flaga --runpod)
  8. build_ephemeral_runpod + build_runpod_engine: OllamaEngine.name == "ollama:<model>",
     host == url efemerycznego poda; owinięcie buduje create+terminate (atrapa);
  9. config.load_runpod: fallback (DEFAULT_RUNPOD) + walidacja (puste volume/dc/model → ValueError);
  (bramka UX korektora)
 10. corrector._main ze stubem i bez --runpod → exit 2 + komunikat ODMOWY na stderr;
 11. corrector._main z furtką MIODEK_ALLOW_STUB_CORRECTOR=1 → przechodzi (stub = tryb testowy).

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
import runner              # noqa: E402
import runpod_lifecycle    # noqa: E402
from runpod_lifecycle import managed_ephemeral_pod  # noqa: E402

_TEST_KEY_ENV = "MIODEK_TEST_RUNPOD_EPH_KEY"


def _recording_transport(calls, status=200, body="{}"):
    """Atrapa REST dla RunPodClient.terminate: zapisuje (method, url), zwraca ustalone (status, body).

    To jedyna warstwa sieci w teście klienta — _default_rest_transport NIGDY nie wołany."""
    def transport(url, *, method, data, headers, timeout):
        calls.append({"method": method, "url": url, "headers": dict(headers)})
        return status, body
    return transport


class _FakePodUp:
    """Atrapa modułu runpod_pod_up: create_pod/wait_for_ollama/ensure_model bez sieci.

    create_pod zwraca {"id": pod_id}; wait_for_ollama/ensure_model zwracają ustalone bool.
    Zapamiętuje wywołania, by test sprawdził sekwencję create→wait→ensure. DEFAULT_GPUS jak launcher."""

    DEFAULT_GPUS = ["NVIDIA GeForce RTX 4090"]

    def __init__(self, pod_id="pod-xyz", wait_ok=True, ensure_ok=True):
        self.pod_id = pod_id
        self._wait_ok = wait_ok
        self._ensure_ok = ensure_ok
        self.create_calls = 0
        self.wait_calls = 0
        self.ensure_calls = 0
        self.create_transport = "SENTINEL_UNSET"

    def create_pod(self, api_key, volume_id, dc, mount, image, gpus, name, transport=None):
        self.create_calls += 1
        self.create_transport = transport
        return {"id": self.pod_id}

    def wait_for_ollama(self, url, **kwargs):
        self.wait_calls += 1
        return self._wait_ok

    def ensure_model(self, url, model, **kwargs):
        self.ensure_calls += 1
        return self._ensure_ok


def main():
    fails = []
    os.environ[_TEST_KEY_ENV] = "tajny-klucz-efem"

    # Osobny sentinel transportu LAUNCHERA (kontrakt runpod_pod_up._default_transport: method, url
    # pozycyjnie). NIEZGODNY z client_transport (kontrakt RunPodClient: url pozycyjnie, method kw).
    # Test pilnuje, że create_pod dostaje WŁAŚNIE ten, a NIE transportu klienta REST (regresja KAN-222).
    def _pod_up_sentinel(method, url, *, data, headers, timeout):  # noqa: ARG001
        # Atrapa launchera; w teście create_pod jej nie WYWOŁUJE (atrapuje _FakePodUp), liczy się
        # tylko TOŻSAMOŚĆ obiektu przekazanego do create_pod(transport=...).
        return 200, "{}"

    def _ctx(pod_up, term_calls, **over):
        """Buduje managed_ephemeral_pod z atrapami (launcher + DWA rozdzielne transporty)."""
        kw = dict(
            api_key_env=_TEST_KEY_ENV, base_url="https://rest.example.test/v1",
            volume_id="vol-1", dc="EU-NL-1", mount="/root/.ollama",
            image="ollama/ollama:latest", model="bielik-test",
            name="miodek-test", pod_up=pod_up,
            client_transport=_recording_transport(term_calls),
            pod_up_transport=_pod_up_sentinel,
            wait_kwargs={"sleep": lambda *_a, **_k: None},
        )
        kw.update(over)
        return managed_ephemeral_pod(**kw)

    # 1: happy path — create na wejściu, terminate raz na wyjściu, url poprawny.
    pu = _FakePodUp(pod_id="pod-aaa")
    term = []
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        with _ctx(pu, term) as pod:
            inner_url = pod.url
            inner_id = pod.pod_id
    if pu.create_calls != 1:
        fails.append(f"happy: oczekiwano 1 create_pod, jest {pu.create_calls}")
    if inner_url != "https://pod-aaa-11434.proxy.runpod.net":
        fails.append(f"happy: zły url efemerycznego poda: {inner_url!r}")
    if inner_id != "pod-aaa":
        fails.append(f"happy: pod_id z create_pod['id'] rozjechany: {inner_id!r}")
    if pu.wait_calls != 1 or pu.ensure_calls != 1:
        fails.append(f"happy: oczekiwano wait=1 ensure=1, jest wait={pu.wait_calls} ensure={pu.ensure_calls}")
    if len(term) != 1 or term[0]["method"] != "DELETE" or not term[0]["url"].endswith("/pods/pod-aaa"):
        fails.append(f"happy: oczekiwano 1 DELETE /pods/pod-aaa, jest {term}")
    # KAN-222 (review): create_pod dostaje transport LAUNCHERA (pod_up_transport), NIE transport
    # klienta REST (client_transport). To dwa NIEZGODNE kontrakty — gdyby się zlały, realny
    # create_pod z client_transportem pękłby po cichu (method/url w złej pozycji). Pilnujemy
    # TOŻSAMOŚCI obiektu: create_pod.transport IS pod_up_sentinel.
    if pu.create_transport is not _pod_up_sentinel:
        fails.append(
            "happy: create_pod dostał ZŁY transport — oczekiwano pod_up_transport (kontrakt "
            f"launchera), jest {pu.create_transport!r} (regresja rozdziału transportów KAN-222)"
        )

    # 2: wyjątek w with → terminate MIMO TO + propaguje.
    pu2 = _FakePodUp(pod_id="pod-bbb")
    term2 = []
    raised = False
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            with _ctx(pu2, term2):
                raise ValueError("wybuch w przebiegu efemerycznym")
        except ValueError:
            raised = True
    if not raised:
        fails.append("wyjątek w with: powinien propagować (ephemeral nie połyka)")
    if len(term2) != 1 or term2[0]["method"] != "DELETE":
        fails.append(f"wyjątek w with: terminate powinien zadziałać w finally, jest {term2}")

    # 3: wait_for_ollama False → terminate (sprzątanie osieroconego poda) + RuntimeError.
    pu3 = _FakePodUp(pod_id="pod-ccc", wait_ok=False)
    term3 = []
    rt_raised = False
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            with _ctx(pu3, term3):
                fails.append("wait=False: nie powinniśmy wejść do bloku with")
        except RuntimeError:
            rt_raised = True
    if not rt_raised:
        fails.append("wait=False: oczekiwano RuntimeError z __enter__")
    if len(term3) != 1 or term3[0]["method"] != "DELETE":
        fails.append(f"wait=False: osierocony pod powinien być zterminowany, jest {term3}")
    if pu3.ensure_calls != 0:
        fails.append("wait=False: ensure_model NIE powinno być wołane po nieudanym wait")

    # 4: ensure_model False → terminate + RuntimeError.
    pu4 = _FakePodUp(pod_id="pod-ddd", ensure_ok=False)
    term4 = []
    rt_raised4 = False
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            with _ctx(pu4, term4):
                fails.append("ensure=False: nie powinniśmy wejść do bloku with")
        except RuntimeError:
            rt_raised4 = True
    if not rt_raised4:
        fails.append("ensure=False: oczekiwano RuntimeError z __enter__")
    if len(term4) != 1 or term4[0]["method"] != "DELETE":
        fails.append(f"ensure=False: osierocony pod powinien być zterminowany, jest {term4}")

    # 4b: no_model=True → ensure_model POMINIĘTY, pod gotowy.
    pu4b = _FakePodUp(pod_id="pod-ddd2", ensure_ok=False)
    term4b = []
    with contextlib.redirect_stderr(io.StringIO()):
        with _ctx(pu4b, term4b, no_model=True):
            pass
    if pu4b.ensure_calls != 0:
        fails.append("no_model=True: ensure_model NIE powinno być wołane")
    if len(term4b) != 1:
        fails.append(f"no_model=True: terminate powinien zadziałać na wyjściu, jest {term4b}")

    # 5: podwójny _teardown → 1 realny terminate (flaga).
    pu5 = _FakePodUp(pod_id="pod-eee")
    term5 = []
    with contextlib.redirect_stderr(io.StringIO()):
        ctx5 = _ctx(pu5, term5)
        ctx5.__enter__()
        ctx5._teardown()
        ctx5._teardown()
    if len(term5) != 1:
        fails.append(f"idempotencja: podwójny _teardown powinien dać 1 terminate, jest {len(term5)}")

    # 6: brak klucza w ENV → RuntimeError przy __enter__, create NIE wołany.
    pu6 = _FakePodUp(pod_id="pod-fff")
    term6 = []
    nokey_raised = False
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            with _ctx(pu6, term6, api_key_env="MIODEK_TEST_BRAK_KLUCZA_EPH_ZZZ"):
                pass
        except RuntimeError:
            nokey_raised = True
    if not nokey_raised:
        fails.append("brak klucza ENV: oczekiwano RuntimeError z __enter__")
    if pu6.create_calls != 0:
        fails.append("brak klucza ENV: create_pod NIE powinno być wołane bez klucza")

    # 7: SIGTERM podczas with → terminate + poprzedni handler przywrócony.
    sentinel = signal.getsignal(signal.SIGTERM)
    def _prev_handler(signum, frame):
        pass
    signal.signal(signal.SIGTERM, _prev_handler)
    pu7 = _FakePodUp(pod_id="pod-ggg")
    term7 = []
    with contextlib.redirect_stderr(io.StringIO()):
        ctx7 = _ctx(pu7, term7)
        ctx7.__enter__()
        ctx7._signal_handler(signal.SIGTERM, None)  # re-raise trafi w no-op _prev_handler
    if len(term7) != 1 or term7[0]["method"] != "DELETE":
        fails.append(f"SIGTERM: teardown powinien zterminować pod raz, jest {term7}")
    if signal.getsignal(signal.SIGTERM) is not _prev_handler:
        fails.append("SIGTERM: poprzedni handler nie został przywrócony przez handler sygnału")
    signal.signal(signal.SIGTERM, sentinel)

    # === config.load_runpod ===
    with tempfile.TemporaryDirectory() as tmp:
        # brak pliku → DEFAULT_RUNPOD
        d = config.load_runpod(os.path.join(tmp, "nie-ma.json"))
        if d.get("volume") != config.DEFAULT_RUNPOD["volume"] or d.get("model") != config.DEFAULT_RUNPOD["model"]:
            fails.append(f"load_runpod: brak configu → oczekiwano DEFAULT_RUNPOD, jest {d}")

        # brak sekcji runpod → DEFAULT_RUNPOD
        p1 = os.path.join(tmp, "c1.json")
        with open(p1, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"engine": "stub"}}, f)
        if config.load_runpod(p1).get("dc") != config.DEFAULT_RUNPOD["dc"]:
            fails.append("load_runpod: stage2 bez runpod → oczekiwano DEFAULT_RUNPOD")

        # scalanie punktowe: tylko volume+dc, reszta z domyślnych
        p2 = os.path.join(tmp, "c2.json")
        with open(p2, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"runpod": {"volume": "vol-X", "dc": "EU-RO-1"}}}, f)
        d2 = config.load_runpod(p2)
        if d2["volume"] != "vol-X" or d2["dc"] != "EU-RO-1":
            fails.append(f"load_runpod: nadpisanie punktowe rozjechane: {d2}")
        if d2["model"] != config.DEFAULT_RUNPOD["model"]:
            fails.append("load_runpod: brakujący model powinien spaść do domyślnego")

        # puste volume → ValueError
        p3 = os.path.join(tmp, "c3.json")
        with open(p3, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"runpod": {"volume": "", "dc": "EU-NL-1"}}}, f)
        try:
            config.load_runpod(p3)
            fails.append("load_runpod: puste volume → oczekiwano ValueError")
        except ValueError:
            pass

        # model=null → ValueError
        p4 = os.path.join(tmp, "c4.json")
        with open(p4, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"runpod": {"volume": "v", "dc": "d", "model": None}}}, f)
        try:
            config.load_runpod(p4)
            fails.append("load_runpod: model=null → oczekiwano ValueError")
        except ValueError:
            pass

        # gpu nie-lista → ValueError
        p5 = os.path.join(tmp, "c5.json")
        with open(p5, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"runpod": {"volume": "v", "dc": "d", "gpu": "RTX"}}}, f)
        try:
            config.load_runpod(p5)
            fails.append("load_runpod: gpu='RTX' (nie lista) → oczekiwano ValueError")
        except ValueError:
            pass

    # === 8: build_ephemeral_runpod + build_runpod_engine (flaga --runpod) ===
    with tempfile.TemporaryDirectory() as tmp:
        cfgp = os.path.join(tmp, "config.json")
        with open(cfgp, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"runpod": {
                "volume": "vol-flag", "dc": "EU-NL-1", "model": "bielik-flag",
                "api_key_env": _TEST_KEY_ENV, "base_url": "https://rest.example.test/v1",
            }}}, f)
        pu8 = _FakePodUp(pod_id="pod-flag")
        term8 = []
        ctx8 = runner.build_ephemeral_runpod(
            cfgp, client_transport=_recording_transport(term8), pod_up=pu8,
            wait_kwargs={"sleep": lambda *_a, **_k: None},
        )
        with contextlib.redirect_stderr(io.StringIO()):
            with ctx8 as pod8:
                eng = runner.build_runpod_engine(cfgp, pod=pod8)
                if eng.name != "ollama:bielik-flag":
                    fails.append(f"--runpod: engine.name oczekiwano 'ollama:bielik-flag', jest {eng.name!r}")
                if eng.base_url != "https://pod-flag-11434.proxy.runpod.net":
                    fails.append(f"--runpod: engine host != url efemerycznego poda: {eng.base_url!r}")
        if pu8.create_calls != 1:
            fails.append(f"--runpod: oczekiwano 1 create_pod, jest {pu8.create_calls}")
        if len(term8) != 1 or term8[0]["method"] != "DELETE" or not term8[0]["url"].endswith("/pods/pod-flag"):
            fails.append(f"--runpod: oczekiwano 1 DELETE /pods/pod-flag, jest {term8}")

    # === 8b: kontrakty obu transportów (regresja rozdziału KAN-222) ===
    # Dowód, że oba transporty są wołane ZGODNIE ze swoim kontraktem przez REALNY kod (create_pod
    # z launchera + RunPodClient._call) — bez sieci (atrapy zapisują pozycje argumentów). Gdyby
    # transporty się zlały (jeden parametr do obu funkcji), tu pękłoby na pozycji method/url.
    import runpod_pod_up as _rpu  # noqa: E402

    pod_up_seen = {}
    def _pod_up_contract(method, url, *, data, headers, timeout):
        # Kontrakt launchera: method i url POZYCYJNIE.
        pod_up_seen.update(method=method, url=url)
        return 200, json.dumps({"id": "pod-contract"})
    res = _rpu.create_pod(
        "klucz", "vol", "EU-NL-1", "/root/.ollama", "ollama/ollama:latest",
        ["RTX"], "miodek-test", transport=_pod_up_contract,
    )
    if res.get("id") != "pod-contract":
        fails.append(f"kontrakt launchera: create_pod nie zwrócił id, jest {res}")
    if pod_up_seen.get("method") != "POST" or not pod_up_seen.get("url", "").endswith("/pods"):
        fails.append(f"kontrakt launchera: method/url w złej pozycji: {pod_up_seen}")

    client_seen = {}
    def _client_contract(url, *, method, data, headers, timeout):
        # Kontrakt klienta REST: url POZYCYJNIE, method jako keyword.
        client_seen.update(method=method, url=url)
        return 200, "{}"
    os.environ["MIODEK_TEST_CONTRACT_KEY"] = "k"
    _client = runpod_lifecycle.RunPodClient(
        api_key_env="MIODEK_TEST_CONTRACT_KEY", base_url="https://rest.example.test/v1",
        transport=_client_contract,
    )
    _client.terminate("pod-contract")
    os.environ.pop("MIODEK_TEST_CONTRACT_KEY", None)
    if client_seen.get("method") != "DELETE" or not client_seen.get("url", "").endswith("/pods/pod-contract"):
        fails.append(f"kontrakt klienta: method/url w złej pozycji: {client_seen}")

    # === 12: publish_gate --runpod bez RUNPOD_API_KEY → exit 2 (NIE traceback) ===
    # RuntimeError z managed_ephemeral_pod.__enter__ (brak klucza) musi zmapować się na czysty
    # exit 2, nie wyciec tracebackiem (review KAN-222, drobna #2).
    _tools_dir = os.path.dirname(os.path.abspath(__file__))
    if _tools_dir not in sys.path:
        sys.path.insert(0, _tools_dir)
    import publish_gate as pg  # noqa: E402
    with tempfile.TemporaryDirectory() as tmp:
        proza = os.path.join(tmp, "tekst.md")
        with open(proza, "w", encoding="utf-8") as f:
            f.write("To jest zwykly akapit prozy bez blokerow do publikacji testowej.\n")
        cfgp = os.path.join(tmp, "config.json")
        # api_key_env wskazuje na ENV, której NA PEWNO nie ma → __enter__ rzuci RuntimeError.
        with open(cfgp, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"runpod": {
                "volume": "v", "dc": "EU-NL-1", "model": "m",
                "api_key_env": "MIODEK_TEST_BRAK_KLUCZA_PG_ZZZ",
            }}}, f)
        os.environ.pop("MIODEK_TEST_BRAK_KLUCZA_PG_ZZZ", None)
        rc_pg = None
        outbuf = io.StringIO()
        with contextlib.redirect_stdout(outbuf), contextlib.redirect_stderr(io.StringIO()):
            try:
                rc_pg = pg.main(["--runpod", "--config", cfgp, proza])
            except SystemExit as e:
                rc_pg = e.code
            except BaseException as e:  # traceback zamiast exit 2 = regresja
                fails.append(f"publish_gate --runpod bez klucza: wyciekł {type(e).__name__} zamiast exit 2: {e}")
        if rc_pg != 2:
            fails.append(f"publish_gate --runpod bez klucza: oczekiwano exit 2, jest {rc_pg}")
        if "WSTRZYMANA" not in outbuf.getvalue():
            fails.append("publish_gate --runpod bez klucza: brak komunikatu PUBLIKACJA WSTRZYMANA")

    # === 10/11: bramka UX korektora ===
    import corrector  # noqa: E402
    with tempfile.TemporaryDirectory() as tmp:
        proza = os.path.join(tmp, "tekst.md")
        with open(proza, "w", encoding="utf-8") as f:
            f.write("To jest zwykły akapit prozy do sprawdzenia korektorem.\n")
        cfgp = os.path.join(tmp, "config.json")
        with open(cfgp, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"engine": "stub"}}, f)

        # 10: stub + brak --runpod → exit 2 + ODMOWA na stderr.
        os.environ.pop("MIODEK_ALLOW_STUB_CORRECTOR", None)
        errbuf = io.StringIO()
        rc = None
        with contextlib.redirect_stderr(errbuf):
            try:
                corrector._main(["--file", proza, "--config", cfgp])
            except SystemExit as e:
                rc = e.code
        if rc != 2:
            fails.append(f"bramka UX: stub bez --runpod powinno dać exit 2, jest {rc}")
        if "ODMOWA" not in errbuf.getvalue():
            fails.append("bramka UX: brak komunikatu ODMOWY na stderr")
        if "--runpod" not in errbuf.getvalue():
            fails.append("bramka UX: komunikat powinien kierować na --runpod / stage2.engine")

        # 11: furtka testowa MIODEK_ALLOW_STUB_CORRECTOR=1 → przechodzi (nie exit 2).
        os.environ["MIODEK_ALLOW_STUB_CORRECTOR"] = "1"
        rc2 = None
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            try:
                corrector._main(["--file", proza, "--config", cfgp])
            except SystemExit as e:
                rc2 = e.code
        os.environ.pop("MIODEK_ALLOW_STUB_CORRECTOR", None)
        if rc2 == 2:
            fails.append("bramka UX: furtka MIODEK_ALLOW_STUB_CORRECTOR=1 powinna przepuścić stub")

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)

    print("OK   efemeryczny pod + flaga --runpod (KAN-222): managed_ephemeral_pod create na wejściu / "
          "terminate na wyjściu (też przy wyjątku — finally), sprzątanie osieroconego poda gdy wait/"
          "ensure_model padnie w __enter__, idempotencja teardownu (1 terminate), brak klucza ENV → "
          "RuntimeError bez create, SIGTERM → terminate + przywrócony handler; build_ephemeral_runpod/"
          "build_runpod_engine (OllamaEngine na url poda, name=ollama:<model>); config.load_runpod "
          "(fallback DEFAULT_RUNPOD + scalanie punktowe + walidacja volume/dc/model/gpu); bramka UX "
          "korektora odmawia (exit 2) bez realnego silnika, furtka stub dla self-testów. ZERO sieci.")


if __name__ == "__main__":
    main()
