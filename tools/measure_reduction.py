#!/usr/bin/env python3
"""
measure_reduction.py — CLI E1: współczynnik redukcji z manifestu lintera (Stage 1).

Cienkie narzędzie: czyta gotowy MANIFEST JSON (z pliku lub stdin), mapuje trafienia review na
akapity przez adapter (ta sama segmentacja co linter) i wypisuje współczynnik redukcji per plik
oraz łączny — w procentach, porównywalny z odniesieniem autora 4–5% treści routowanej.

NIE woła lintera ani LLM. Granica między etapami to manifest.

Użycie:
    python3 ai_linter.py --format json *.md > manifest.json
    python3 tools/measure_reduction.py --manifest manifest.json
    python3 ai_linter.py --format json *.md | python3 tools/measure_reduction.py
    python3 tools/measure_reduction.py --manifest m.json --json        # surowy JSON wyniku
    python3 tools/measure_reduction.py --manifest m.json --max-routed 0.10   # exit 1 gdy routed > 10%
    python3 tools/measure_reduction.py --manifest m.json --min-reduction 0.90 # exit 1 gdy redukcja < 90%

Kod wyjścia: 1 gdy przekroczony próg (--max-routed / --min-reduction), w przeciwnym razie 0.
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
        description="E1: współczynnik redukcji (udział treści routowanej do Stage 2) z manifestu.",
        epilog="Odniesienie autora: ~4–5%% treści routowanej (routed_ratio).",
    )
    p.add_argument("--manifest", metavar="PLIK",
                   help="Ścieżka do manifestu JSON. Brak => czytaj ze stdin.")
    p.add_argument("--json", action="store_true",
                   help="Wypisz surowy JSON wyniku zamiast tabeli.")
    p.add_argument("--max-routed", type=float, metavar="X",
                   help="Próg: exit 1 gdy routed_ratio > X (np. 0.10).")
    p.add_argument("--min-reduction", type=float, metavar="Y",
                   help="Próg: exit 1 gdy reduction_ratio < Y (np. 0.90).")
    args = p.parse_args(argv)

    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = json.load(sys.stdin)

    result = metrics.reduction_from_manifest(manifest)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("== Współczynnik redukcji (E1) — z manifestu Stage 1, bez kosztu tokenów ==")
        print(f"{'plik':<40} {'słowa':>8} {'routed':>8} {'routed%':>9} {'segm.':>10}")
        for pf in result["per_file"]:
            seg = f"{pf['routed_segments']}/{pf['total_segments']}"
            flag = "  [fallback]" if pf.get("fallback") else ""
            print(f"{str(pf['file']):<40} {pf['words']:>8} {pf['routed_words']:>8} "
                  f"{_pct(pf['routed_ratio']):>9} {seg:>10}{flag}")
        print("-" * 80)
        print(f"{'RAZEM':<40} {result['total_words']:>8} {result['routed_words']:>8} "
              f"{_pct(result['routed_ratio']):>9} "
              f"{result['routed_segments']}/{result['total_segments']:>10}")
        print(f"Redukcja (treść, której model NIE tyka): {_pct(result['reduction_ratio'])}")
        print(f"Routed (hit rate, ref. autora 4–5%):     {_pct(result['routed_ratio'])}")

    rc = 0
    if args.max_routed is not None and result["routed_ratio"] > args.max_routed:
        print(f"[PRÓG] routed_ratio {_pct(result['routed_ratio'])} > max {_pct(args.max_routed)}",
              file=sys.stderr)
        rc = 1
    if args.min_reduction is not None and result["reduction_ratio"] < args.min_reduction:
        print(f"[PRÓG] reduction_ratio {_pct(result['reduction_ratio'])} < min {_pct(args.min_reduction)}",
              file=sys.stderr)
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
