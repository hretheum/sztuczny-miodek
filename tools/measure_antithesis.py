#!/usr/bin/env python3
"""
measure_antithesis.py — pomiar precyzji/recall antytezy inwersyjnej PL-ANTI.

Czyta WSZYSTKIE wzorce PL-ANTI z rules.json (źródło prawdy) i ocenia je łącznie (OR) na
etykietowanym zestawie tests/antithesis_eval.md (TP = generatorowa antyteza, FP = naturalne
zaprzeczenie/korekta). Raportuje TP/FP/FN, precyzję i recall. ZERO-DEP (stdlib: json, re).

Trafienie = którykolwiek wzorzec PL-ANTI łapie (tak działa linter: każdy wpis to osobny marker).

Użycie:
    python3 tools/measure_antithesis.py
    python3 tools/measure_antithesis.py --min-recall 1.0   # exit 1 gdy recall < próg (gate)
"""

import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_PATH = os.path.join(REPO_ROOT, "rules.json")
EVAL_PATH = os.path.join(REPO_ROOT, "tests", "antithesis_eval.md")

FLAGS = re.IGNORECASE | re.UNICODE


def anti_patterns():
    """Lista skompilowanych wzorców PL-ANTI z rules.json (zachowuje wszystkie warianty)."""
    rules = json.load(open(RULES_PATH, encoding="utf-8"))
    pats = [re.compile(r["pattern"], FLAGS) for r in rules if r["id"] == "PL-ANTI"]
    if not pats:
        print("[ERROR] Brak wzorców PL-ANTI w rules.json", file=sys.stderr)
        sys.exit(2)
    return pats


def load_eval():
    """Czyta tests/antithesis_eval.md → lista (label, tekst)."""
    items = []
    for line in open(EVAL_PATH, encoding="utf-8"):
        s = line.strip()
        if not s or s.startswith("#") or "|" not in s:
            continue
        label, _, text = s.partition("|")
        label = label.strip().upper()
        if label in ("TP", "FP"):
            items.append((label, text.strip()))
    return items


def main():
    pats = anti_patterns()
    items = load_eval()

    def hit(text):
        return any(p.search(text) for p in pats)

    tp = fp = fn = tn = 0
    fp_examples, fn_examples = [], []
    for label, text in items:
        h = hit(text)
        if label == "TP":
            tp += h
            if not h:
                fn += 1
                fn_examples.append(text)
        else:
            if h:
                fp += 1
                fp_examples.append(text)
            else:
                tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0

    print(f"Antyteza PL-ANTI — zestaw {len(items)}: TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"  precyzja = {precision:.0%}   recall = {recall:.0%}")
    if fp_examples:
        print("  pozostałe FP (naturalne korekty wciąż łapane):")
        for e in fp_examples:
            print(f"    - {e}")
    if fn_examples:
        print("  FN (generatorowe antytezy przeoczone — regresja recall!):")
        for e in fn_examples:
            print(f"    - {e}")

    if "--min-recall" in sys.argv:
        min_recall = float(sys.argv[sys.argv.index("--min-recall") + 1])
        if recall < min_recall:
            print(f"[ERROR] recall {recall:.0%} < próg {min_recall:.0%}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
