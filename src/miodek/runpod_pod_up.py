#!/usr/bin/env python3
"""
runpod_pod_up.py — launcher poda RunPod z podłączonym wolumenem sieciowym (towarzysz runpod_lifecycle.py).

Cel: postawić pod z Ollamą tak, by model (Bielik) leżał na TRWAŁYM wolumenie sieciowym i nie był
pobierany ponownie. MCP `create-pod` nie ma pola networkVolumeId, więc używamy REST RunPoda
(POST https://rest.runpod.io/v1/pods, pole `networkVolumeId`). Klucz z env RUNPOD_API_KEY.

ZERO-DEP (stdlib urllib). Wstrzykiwalny transport (jak engines.py / runpod_lifecycle.py) — testy offline.

Użycie:
    source ~/.config/runpod/runpod.env
    python3 tools/runpod_pod_up.py --volume 5lb05arqur --dc EU-NL-1 \
        --mount /root/.ollama --model hf.co/speakleash/Bielik-11B-v3.0-Instruct-GGUF:Q4_K_M
Wypisuje JSON {podId, url} na stdout po gotowości (Ollama wstała + model obecny na wolumenie).
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

REST_BASE = "https://rest.runpod.io/v1"
# Szeroka lista GPU — RunPod wybierze dostępny w danym DC. Wolumen wiąże pod z DC.
DEFAULT_GPUS = [
    "NVIDIA GeForce RTX 4090", "NVIDIA RTX A5000", "NVIDIA RTX A6000",
    "NVIDIA L40S", "NVIDIA L40", "NVIDIA A40",
    "NVIDIA H100 80GB HBM3", "NVIDIA H100 PCIe", "NVIDIA H200", "NVIDIA A100 80GB PCIe",
]


def _default_transport(method, url, *, data, headers, timeout):
    """Jedyne miejsce dotykające sieci REST. Zwraca (status, body_str). Wstrzykiwalne (testy offline)."""
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def _rest(method, path, api_key, body=None, transport=None, timeout=60.0):
    transport = transport or _default_transport
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    status, raw = transport(method, REST_BASE + path, data=data, headers=headers, timeout=timeout)
    if not (200 <= status < 300):
        raise RuntimeError(f"REST {method} {path} -> HTTP {status}: {raw[:300]}")
    return json.loads(raw) if raw.strip() else {}


def _http_get(url, timeout=8.0, ua="sztuczny-miodek/1.0"):
    """Pomocniczy GET na proxy poda (User-Agent obowiązkowy — proxy RunPoda blokuje domyślny urllib UA)."""
    req = urllib.request.Request(url, headers={"User-Agent": ua}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _http_post(url, body, timeout=900.0, ua="sztuczny-miodek/1.0"):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"User-Agent": ua, "Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def create_pod(api_key, volume_id, dc, mount, image, gpus, name, transport=None):
    body = {
        "name": name,
        "imageName": image,
        "computeType": "GPU",
        "gpuTypeIds": gpus,
        "gpuCount": 1,
        "dataCenterIds": [dc],
        "networkVolumeId": volume_id,
        "volumeMountPath": mount,
        "containerDiskInGb": 20,
        "ports": ["11434/http"],
        "env": {"OLLAMA_HOST": "0.0.0.0:11434"},
    }
    return _rest("POST", "/pods", api_key, body=body, transport=transport)


def wait_for_ollama(url, tries=40, delay=6.0, sleep=time.sleep):
    for _ in range(tries):
        try:
            if "ollama" in _http_get(url + "/", timeout=8.0).lower():
                return True
        except Exception:
            pass
        sleep(delay)
    return False


def ensure_model(url, model, sleep=time.sleep):
    """Pobiera model TYLKO gdy go nie ma (na wolumenie już może leżeć). Zwraca True gdy obecny."""
    try:
        tags = json.loads(_http_get(url + "/api/tags", timeout=10.0))
        if any(m.get("name") == model for m in tags.get("models", [])):
            return True  # już na wolumenie — bez pobierania
    except Exception:
        pass
    # pull blokujący (stream=false) — pierwszy raz trafia na wolumen, potem persystuje
    out = _http_post(url + "/api/pull", {"model": model, "stream": False}, timeout=1800.0)
    return '"status":"success"' in out.replace(" ", "")


def main():
    ap = argparse.ArgumentParser(description="Launcher poda RunPod z wolumenem (Ollama + model).")
    ap.add_argument("--volume", required=True, help="ID wolumenu sieciowego (networkVolumeId).")
    ap.add_argument("--dc", required=True, help="Data center ID wolumenu (pod musi tu stanąć).")
    ap.add_argument("--mount", default="/root/.ollama", help="Mount wolumenu (modele Ollamy).")
    ap.add_argument("--image", default="ollama/ollama:latest")
    ap.add_argument("--model", default="hf.co/speakleash/Bielik-11B-v3.0-Instruct-GGUF:Q4_K_M")
    ap.add_argument("--name", default="miodek-bielik")
    ap.add_argument("--gpus", nargs="*", default=DEFAULT_GPUS)
    ap.add_argument("--no-model", action="store_true", help="Nie pobieraj modelu (sam pod).")
    args = ap.parse_args()

    api_key = os.environ.get("RUNPOD_API_KEY", "")
    if not api_key:
        print("BŁĄD: brak RUNPOD_API_KEY w env (source ~/.config/runpod/runpod.env).", file=sys.stderr)
        sys.exit(2)

    pod = create_pod(api_key, args.volume, args.dc, args.mount, args.image, args.gpus, args.name)
    pod_id = pod["id"]
    url = f"https://{pod_id}-11434.proxy.runpod.net"
    print(f"[pod_up] utworzony pod {pod_id} (GPU {pod.get('machine', {}).get('gpuTypeId', '?')}, "
          f"{pod.get('costPerHr', '?')} USD/h, DC {args.dc})", file=sys.stderr)

    if not wait_for_ollama(url):
        print(f"BŁĄD: Ollama nie wstała na {url}", file=sys.stderr)
        print(json.dumps({"podId": pod_id, "url": url, "ready": False}))
        sys.exit(1)
    print("[pod_up] Ollama gotowa", file=sys.stderr)

    if not args.no_model:
        if ensure_model(url, args.model):
            print(f"[pod_up] model obecny na wolumenie: {args.model}", file=sys.stderr)
        else:
            print(f"BŁĄD: nie udało się zapewnić modelu {args.model}", file=sys.stderr)
            print(json.dumps({"podId": pod_id, "url": url, "ready": False}))
            sys.exit(1)

    print(json.dumps({"podId": pod_id, "url": url, "ready": True}))


if __name__ == "__main__":
    main()
