#!/usr/bin/env python3
"""
check_metrics_exporter.py — self-test OFFLINE eksportera metryk Prometheus (KAN-219). ZERO-DEP.

ŻADNEJ sieci, ŻADNEGO lintera, ŻADNEGO Prometheusa. Wstrzykujemy `state` zbudowany z ustalonego
mini-manifestu w pamięci i sprawdzamy wyłącznie CZYSTĄ funkcję metrics_exporter.render_metrics —
to granica testowalna eksportera (collect_state/serwer to efekty uboczne, tu ich nie ruszamy).

Asercje (na render_metrics(state)):
  1.  Każda metryka ma # HELP i # TYPE PRZED pierwszą serią; TYPE zgodny (gauge/counter).
  2.  miodek_reduction_ratio i miodek_routed_ratio obecne; suma wartości == 1.0.
  3.  miodek_hits_total{rule=...,klasa="review"} oraz {klasa="block"} renderują się poprawnie.
  4.  Escaping etykiety: rule-id z " i \\ renderuje się jako \\" / \\\\ (regresja formatu).
  5.  miodek_health 1 dla OK / 0 dla ALARM; miodek_health_na 1 dla N/A (N/A nie udaje OK);
      miodek_routed_ratio_alarm_threshold == próg z health.
  6.  miodek_stage2_runs_total{engine,verdict} agreguje; przy pustym logu seria nieobecna,
      ale HELP/TYPE są (panel czeka na dane) — bez błędu.
  7.  Brak końcowych spacji w liniach; brak duplikatu # TYPE dla tej samej metryki; koniec na \\n.
  8.  Walidacja artefaktów deploy (wzór check_ci_gate „needle in plik"): service/scrape/dashboard/
      provider istnieją i mają krytyczne pola; dashboard parsuje się jako JSON.
  9.  Fail-soft: state z exporter_up=0 renderuje miodek_exporter_up 0 bez serii liczbowych, bez błędu.

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import metrics  # noqa: E402
import metrics_exporter as mx  # noqa: E402


# --- Ustalony manifest w pamięci (ten sam wzorzec co check_metrics.py) ---
# Akapit review routed, akapit block i czysty nie. Rule-id z " i \ do testu escapingu (asercja 4).
TRICKY_ID = 'PL-"X\\Y'

MANIFEST = {
    "hits": [
        {"file": "doc.txt", "line": 1, "id": "PL-SIGN", "klasa": "review", "match": "review"},
        {"file": "doc.txt", "line": 3, "id": "EN-DASH", "klasa": "block", "match": "block"},
        {"file": "doc.txt", "line": 1, "id": TRICKY_ID, "klasa": "review", "match": "x"},
    ],
    "summary": [
        {"file": "doc.txt", "words": 21, "hits": 3, "emdash_max": 0,
         "density": 0.0, "blockers": 1, "verdict": "FAIL"},
    ],
}

DOC = (
    "Pierwszy akapit ma trafienie review tutaj.\n"
    "\n"
    "Drugi akapit zawiera twardy bloker block.\n"
    "\n"
    "Trzeci akapit jest zupełnie czysty bez niczego."
)


def _reader(path):
    if path == "doc.txt":
        return DOC
    raise OSError(path)


def _build_state(manifest, economy, stage2_runs, doc_reader=_reader):
    """Buduje `state` jak collect_state, ale czysto w pamięci (wstrzyknięty reader, bez lintera).

    `stage2_runs` to lista wpisów logu (dict z engine/stage2_verdict) — agregujemy jak eksporter."""
    reduction = metrics.reduction_from_manifest(manifest, file_reader=doc_reader)
    attribution = metrics.attribution_from_manifest(manifest)
    health = metrics.economy_health(manifest, economy=economy, file_reader=doc_reader)
    agg = {}
    for r in stage2_runs:
        key = (r.get("engine", "?"), r.get("stage2_verdict", "?"))
        agg[key] = agg.get(key, 0) + 1
    stage2 = [{"engine": e, "verdict": v, "count": c} for (e, v), c in sorted(agg.items())]
    return {
        "exporter_up": 1,
        "scrape_duration_seconds": 0.123,
        "reduction": reduction,
        "attribution": attribution,
        "health": health,
        "stage2_runs": stage2,
    }


def _parse_series(text):
    """Parsuje tekst ekspozycji do: {metric_name: {"type":..., "help":bool, "series":[(labels,val)]}}.

    Etykiety zwracamy jako surowy string między { } (do asercji escapingu). Wartość jako float gdy
    się da, inaczej string."""
    out = {}
    type_order = {}  # name -> czy # TYPE pojawił się przed pierwszą serią
    seen_series = set()
    for raw in text.split("\n"):
        if raw == "":
            continue
        if raw.startswith("# HELP "):
            name = raw[len("# HELP "):].split(" ", 1)[0]
            out.setdefault(name, {"type": None, "help": False, "series": []})
            out[name]["help"] = True
        elif raw.startswith("# TYPE "):
            rest = raw[len("# TYPE "):]
            name, mtype = rest.split(" ", 1)
            out.setdefault(name, {"type": None, "help": False, "series": []})
            out[name]["type"] = mtype.strip()
            type_order.setdefault(name, name not in seen_series)
        else:
            # seria: name{labels} value  albo  name value
            if "{" in raw:
                name = raw[:raw.index("{")]
                labels = raw[raw.index("{") + 1:raw.rindex("}")]
                value = raw[raw.rindex("}") + 1:].strip()
            else:
                name, value = raw.split(" ", 1)
                labels = ""
                value = value.strip()
            seen_series.add(name)
            out.setdefault(name, {"type": None, "help": False, "series": []})
            try:
                val = float(value)
            except ValueError:
                val = value
            out[name]["series"].append((labels, val))
    return out, type_order


def main():
    fails = []
    economy = {"routed_ratio_alarm": 0.10, "min_words": 5}

    # --- Przebieg główny: ALARM (routed ~0.38 > 0.10), log Stage 2 z dwoma wpisami ---
    stage2_runs = [
        {"engine": "stub", "stage2_verdict": "rewrite"},
        {"engine": "stub", "stage2_verdict": "rewrite"},
        {"engine": "stub", "stage2_verdict": "pass"},
    ]
    state = _build_state(MANIFEST, economy, stage2_runs)
    text = mx.render_metrics(state)
    parsed, type_order = _parse_series(text)

    # 1: HELP/TYPE przed pierwszą serią + typy zgodne.
    expected_types = {
        "miodek_reduction_ratio": "gauge",
        "miodek_routed_ratio": "gauge",
        "miodek_total_words": "gauge",
        "miodek_routed_words": "gauge",
        "miodek_hits_total": "gauge",
        "miodek_health": "gauge",
        "miodek_health_na": "gauge",
        "miodek_routed_ratio_alarm_threshold": "gauge",
        "miodek_stage2_runs_total": "counter",
        "miodek_exporter_up": "gauge",
        "miodek_scrape_duration_seconds": "gauge",
    }
    for name, mtype in expected_types.items():
        if name not in parsed:
            fails.append(f"brak metryki {name} w wyjściu")
            continue
        if not parsed[name]["help"]:
            fails.append(f"{name}: brak # HELP")
        if parsed[name]["type"] != mtype:
            fails.append(f"{name}: TYPE oczekiwano {mtype}, jest {parsed[name]['type']}")
        if type_order.get(name) is False:
            fails.append(f"{name}: # TYPE pojawił się PO pierwszej serii (powinien przed)")

    # 2: reduction + routed == 1.0.
    if "miodek_reduction_ratio" in parsed and "miodek_routed_ratio" in parsed:
        red = parsed["miodek_reduction_ratio"]["series"][0][1]
        rou = parsed["miodek_routed_ratio"]["series"][0][1]
        if abs((red + rou) - 1.0) > 1e-9:
            fails.append(f"reduction+routed != 1.0 ({red} + {rou})")
    else:
        fails.append("brak reduction_ratio/routed_ratio do sprawdzenia inwariantu")

    # 3: hits_total z etykietami rule/klasa — review i block.
    hits_series = parsed.get("miodek_hits_total", {}).get("series", [])
    labels_joined = " ".join(lbl for lbl, _ in hits_series)
    if 'rule="PL-SIGN"' not in labels_joined or 'klasa="review"' not in labels_joined:
        fails.append(f"hits_total: brak serii PL-SIGN/review; etykiety: {labels_joined}")
    if 'rule="EN-DASH"' not in labels_joined or 'klasa="block"' not in labels_joined:
        fails.append(f"hits_total: brak serii EN-DASH/block; etykiety: {labels_joined}")
    # wartość PL-SIGN review == 1.
    pl_sign_val = next((v for lbl, v in hits_series
                        if 'rule="PL-SIGN"' in lbl and 'klasa="review"' in lbl), None)
    if pl_sign_val != 1.0:
        fails.append(f"hits_total PL-SIGN/review: oczekiwano 1, jest {pl_sign_val}")

    # 4: escaping — TRICKY_ID 'PL-"X\\Y' -> w etykiecie rule="PL-\"X\\Y".
    if 'rule="PL-\\"X\\\\Y"' not in labels_joined:
        fails.append(f"escaping etykiety nie zadziałał dla {TRICKY_ID!r}; etykiety: {labels_joined}")

    # 5: health ALARM => 0; health_na => 0; próg == 0.10.
    h_series = parsed.get("miodek_health", {}).get("series", [])
    if not h_series or h_series[0][1] != 0.0:
        fails.append(f"miodek_health: oczekiwano 0 (ALARM), jest {h_series}")
    hna = parsed.get("miodek_health_na", {}).get("series", [])
    if not hna or hna[0][1] != 0.0:
        fails.append(f"miodek_health_na: oczekiwano 0 (nie N/A), jest {hna}")
    thr = parsed.get("miodek_routed_ratio_alarm_threshold", {}).get("series", [])
    if not thr or abs(thr[0][1] - 0.10) > 1e-9:
        fails.append(f"alarm_threshold: oczekiwano 0.10, jest {thr}")

    # 6: stage2_runs agreguje stub/rewrite=2, stub/pass=1.
    s2 = parsed.get("miodek_stage2_runs_total", {}).get("series", [])
    s2_rewrite = next((v for lbl, v in s2 if 'engine="stub"' in lbl and 'verdict="rewrite"' in lbl), None)
    s2_pass = next((v for lbl, v in s2 if 'engine="stub"' in lbl and 'verdict="pass"' in lbl), None)
    if s2_rewrite != 2.0:
        fails.append(f"stage2 stub/rewrite: oczekiwano 2, jest {s2_rewrite}")
    if s2_pass != 1.0:
        fails.append(f"stage2 stub/pass: oczekiwano 1, jest {s2_pass}")

    # 7: brak końcowych spacji; brak duplikatu # TYPE; koniec na \n.
    for ln in text.split("\n"):
        if ln != ln.rstrip():
            fails.append(f"linia z końcową spacją: {ln!r}")
            break
    type_lines = [ln for ln in text.split("\n") if ln.startswith("# TYPE ")]
    type_names = [ln.split(" ")[2] for ln in type_lines]
    if len(type_names) != len(set(type_names)):
        fails.append(f"duplikat # TYPE: {type_names}")
    if not text.endswith("\n"):
        fails.append("wyjście nie kończy się na \\n")

    # --- Przebieg OK: routed pod progiem => health 1 ---
    manifest_ok = {
        "hits": [],
        "summary": [{"file": "clean.txt", "words": 100, "hits": 0, "emdash_max": 0,
                     "density": 0.0, "blockers": 0, "verdict": "PASS"}],
    }
    state_ok = _build_state(manifest_ok, economy, [], doc_reader=lambda p: "")
    parsed_ok, _ = _parse_series(mx.render_metrics(state_ok))
    h_ok = parsed_ok.get("miodek_health", {}).get("series", [])
    if not h_ok or h_ok[0][1] != 1.0:
        fails.append(f"OK: miodek_health oczekiwano 1, jest {h_ok}")
    # 6b: pusty log Stage 2 => seria nieobecna, ale HELP/TYPE są (panel czeka na dane).
    s2_ok = parsed_ok.get("miodek_stage2_runs_total")
    if s2_ok is None or not s2_ok["help"] or s2_ok["type"] != "counter":
        fails.append("OK: miodek_stage2_runs_total bez HELP/TYPE przy pustym logu")
    if s2_ok and s2_ok["series"]:
        fails.append(f"OK: przy pustym logu stage2 nie powinno być serii, jest {s2_ok['series']}")

    # --- Przebieg N/A: za mała próbka => health_na 1, brak serii miodek_health ---
    economy_big = {"routed_ratio_alarm": 0.10, "min_words": 1000}
    state_na = _build_state(MANIFEST, economy_big, [])
    parsed_na, _ = _parse_series(mx.render_metrics(state_na))
    hna2 = parsed_na.get("miodek_health_na", {}).get("series", [])
    if not hna2 or hna2[0][1] != 1.0:
        fails.append(f"N/A: miodek_health_na oczekiwano 1, jest {hna2}")
    if parsed_na.get("miodek_health", {}).get("series"):
        fails.append("N/A: miodek_health nie powinno mieć serii (N/A nie udaje OK/ALARM)")
    if not parsed_na.get("miodek_health", {}).get("help"):
        fails.append("N/A: miodek_health powinno zachować HELP/TYPE mimo braku serii")

    # 9: fail-soft — exporter_up=0 renderuje up 0 bez serii liczbowych, bez wyjątku.
    soft = mx.render_metrics({"exporter_up": 0, "scrape_duration_seconds": 0.0})
    parsed_soft, _ = _parse_series(soft)
    up = parsed_soft.get("miodek_exporter_up", {}).get("series", [])
    if not up or up[0][1] != 0.0:
        fails.append(f"fail-soft: miodek_exporter_up oczekiwano 0, jest {up}")
    if "miodek_reduction_ratio" in parsed_soft:
        fails.append("fail-soft: nie powinno być serii E1 przy exporter_up=0")

    # --- 8: walidacja artefaktów deploy (needle-in-plik, wzór check_ci_gate) ---
    deploy = os.path.join(REPO_ROOT, "deploy")
    checks = [
        ("systemd/miodek-exporter.service", ["metrics_exporter.py", "9112", "MIODEK_CORPUS"]),
        ("prometheus/miodek-scrape.snippet.yml", ["job_name", "9112"]),
        ("grafana/provider.yaml", ["apiVersion", "providers"]),
    ]
    for rel, needles in checks:
        p = os.path.join(deploy, rel)
        if not os.path.exists(p):
            fails.append(f"deploy: brak pliku {rel}")
            continue
        with open(p, "r", encoding="utf-8") as f:
            content = f.read()
        for n in needles:
            if n not in content:
                fails.append(f"deploy/{rel}: brak '{n}'")

    dash = os.path.join(deploy, "grafana", "miodek-dashboard.json")
    if not os.path.exists(dash):
        fails.append("deploy: brak grafana/miodek-dashboard.json")
    else:
        with open(dash, "r", encoding="utf-8") as f:
            raw = f.read()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            obj = None
            fails.append(f"dashboard JSON nie parsuje się: {e}")
        if obj is not None:
            # Dashboard musi odwoływać się do naszych metryk (sanity: w którymś targecie).
            for needle in ("miodek_reduction_ratio", "miodek_routed_ratio", "miodek_stage2_runs_total"):
                if needle not in raw:
                    fails.append(f"dashboard: brak odwołania do {needle}")
            if "${DS_PROMETHEUS}" not in raw:
                fails.append("dashboard: brak zmiennej datasource ${DS_PROMETHEUS}")

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)

    print("OK   eksporter metryk: render serii Prometheus (HELP/TYPE przed serią, typy gauge/counter, "
          "inwariant red+routed=1, hits_total{rule,klasa}, escaping etykiet).")
    print("OK   eksporter E4: health 1/0 dla OK/ALARM, health_na dla N/A (nie udaje OK), próg z configu.")
    print("OK   eksporter Stage 2: agregacja per silnik/werdykt; pusty log => panel bez serii (czeka "
          "na realny silnik); fail-soft => exporter_up 0 bez serii liczbowych.")
    print("OK   artefakty deploy: service/scrape/provider/dashboard obecne; dashboard parsuje się jako "
          "JSON i odwołuje do metryk miodek_*.")


if __name__ == "__main__":
    main()
