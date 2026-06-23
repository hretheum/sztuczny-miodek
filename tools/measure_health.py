#!/usr/bin/env python3
"""
measure_health.py — CLI E4: wskaźnik zdrowia ekonomii z alarmem na wzrost routed_ratio.

Cienkie narzędzie nad metrics.economy_health: czyta gotowy MANIFEST JSON (z pliku lub stdin),
liczy współczynnik redukcji (E1) i porównuje routed_ratio z progiem alarmu z config.json
(sekcja `economy`, czytana przez config.load_economy). Wypisuje status OK / ALARM / N/A.

NIE woła lintera ani LLM. Granica między etapami to manifest.

Gate-owalność: exit 1 gdy health == "ALARM" (np. w CI/pre-publish, żeby regresja reguł lub
wzrost udziału treści routowanej do modelu zapalił czerwone światło zanim trafi w rachunek).
Exit 0 dla OK i N/A.

Użycie:
    python3 ai_linter.py --format json *.md > manifest.json
    python3 tools/measure_health.py --manifest manifest.json
    python3 ai_linter.py --format json *.md | python3 tools/measure_health.py
    python3 tools/measure_health.py --manifest m.json --json                # surowy JSON wyniku
    python3 tools/measure_health.py --manifest m.json --alarm 0.08          # nadpisz próg alarmu
    python3 tools/measure_health.py --manifest m.json --min-words 50        # nadpisz min. próbkę
"""

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from miodek import metrics  # noqa: E402
from miodek import config  # noqa: E402


def _pct(x):
    return f"{x * 100:.1f}%"


def main(argv=None):
    p = argparse.ArgumentParser(
        description="E4: wskaźnik zdrowia ekonomii (OK/ALARM/N/A) z progiem alarmu na routed_ratio.",
        epilog="Exit 1 gdy ALARM (gate-owalne). Próg z config.json (sekcja economy), nadpisywalny flagą.",
    )
    p.add_argument("--manifest", metavar="PLIK",
                   help="Ścieżka do manifestu JSON. Brak => czytaj ze stdin.")
    p.add_argument("--json", action="store_true",
                   help="Wypisz surowy JSON wyniku zamiast raportu.")
    p.add_argument("--alarm", type=float, metavar="X",
                   help="Nadpisz próg alarmu routed_ratio (np. 0.08). Brak => z config.json.")
    p.add_argument("--min-words", type=int, metavar="N",
                   help="Nadpisz minimalną liczbę słów łącznie do oceny. Brak => z config.json.")
    args = p.parse_args(argv)

    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = json.load(sys.stdin)

    # Próg: config jako baza, flagi CLI nadpisują punktowo.
    economy = dict(config.load_economy())
    if args.alarm is not None:
        economy["routed_ratio_alarm"] = args.alarm
    if args.min_words is not None:
        economy["min_words"] = args.min_words

    result = metrics.economy_health(manifest, economy=economy)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("== Zdrowie ekonomii (E4) — z manifestu Stage 1, bez kosztu tokenów ==")
        print(f"Routed (hit rate):        {_pct(result['routed_ratio'])}  "
              f"(ref. autora 4–5%)")
        print(f"Redukcja (model NIE tyka): {_pct(result['reduction_ratio'])}")
        print(f"Próg alarmu:              {_pct(result['alarm_threshold'])}  "
              f"(min. próbka: {result['min_words']} słów; jest {result['total_words']})")
        print(f"STATUS: {result['health']}  — {result['reason']}")

    if result["health"] == "ALARM":
        print(f"[ALARM] {result['reason']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
