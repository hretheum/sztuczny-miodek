#!/usr/bin/env python3
"""
measure_attribution.py — CLI E2: atrybucja pracy z manifestu lintera (Stage 1).

Raport diagnostyczny „która reguła (i która warstwa) robi modelowi najwięcej roboty".
Rozbicie liczone CZYSTO z manifestu — bez wołania lintera i bez LLM. Granica między etapami
to manifest.

Dwa rozbicia:
  - per WARSTWA: deklaratywna (regex z rules.json) vs proceduralna (detektor kodu),
  - per REGUŁA: ranking ID markerów wg liczby trafień, z udziałem procentowym wkładu.
Dla każdej pozycji rozdzielamy klasę "review" (realnie routowane do Stage 2) od "block"
(zamknięte przez linter). To raport diagnostyczny — bez progu i exitu (zawsze 0).

Atrybucja per SILNIK wymaga osobnego wyniku runnera Stage 2 (G1) — manifest werdyktów
silnika nie zawiera. Tu jej świadomie nie liczymy (jawne ograniczenie modułu).

Użycie:
    python3 ai_linter.py --format json *.md > manifest.json
    python3 tools/measure_attribution.py --manifest manifest.json
    python3 ai_linter.py --format json *.md | python3 tools/measure_attribution.py
    python3 tools/measure_attribution.py --manifest m.json --json    # surowy JSON wyniku
"""

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from miodek import metrics  # noqa: E402


def _pct(x):
    return f"{x * 100:.1f}%"


def main(argv=None):
    p = argparse.ArgumentParser(
        description="E2: atrybucja pracy (per warstwa i per reguła) z manifestu Stage 1.",
        epilog="Raport diagnostyczny — bez progu. Per silnik wymaga wyniku runnera Stage 2.",
    )
    p.add_argument("--manifest", metavar="PLIK",
                   help="Ścieżka do manifestu JSON. Brak => czytaj ze stdin.")
    p.add_argument("--json", action="store_true",
                   help="Wypisz surowy JSON wyniku zamiast tabeli.")
    args = p.parse_args(argv)

    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = json.load(sys.stdin)

    result = metrics.attribution_from_manifest(manifest)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    total = result["total_hits"]
    pc = result["per_class"]
    print("== Atrybucja pracy (E2) — z manifestu Stage 1, bez kosztu tokenów ==")
    print(f"Trafienia łącznie: {total}  (review {pc['review']} / block {pc['block']})")
    print()

    print("-- per WARSTWA (źródło trafienia) --")
    print(f"{'warstwa':<16} {'trafienia':>10} {'review':>8} {'block':>8} {'udział':>9}")
    # Kolejność warstw: malejąco wg trafień, dla stabilnego raportu.
    layers = sorted(result["per_layer"].items(), key=lambda kv: (-kv[1]["hits"], kv[0]))
    for name, d in layers:
        print(f"{name:<16} {d['hits']:>10} {d['review']:>8} {d['block']:>8} {_pct(d['share']):>9}")
    print()

    print("-- per REGUŁA (która reguła robi najwięcej roboty) --")
    print(f"{'id':<14} {'warstwa':<14} {'trafienia':>10} {'review':>8} {'block':>8} {'udział':>9}")
    for r in result["per_rule"]:
        print(f"{r['id']:<14} {r['layer']:<14} {r['hits']:>10} {r['review']:>8} "
              f"{r['block']:>8} {_pct(r['share']):>9}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
