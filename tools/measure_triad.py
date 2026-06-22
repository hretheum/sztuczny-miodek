#!/usr/bin/env python3
"""
measure_triad.py — pomiar precyzji/recall wzorca triady (PL-RHET „triada?" / EN-TRIAD).

Czyta wzorce triady WPROST z rules.json (źródło prawdy) i ocenia je na etykietowanym zestawie
tests/triad_eval.md (TP = retoryczna triada, FP = wyliczenie faktów). Raportuje TP/FP/FN,
precyzję i recall dla PL i EN łącznie. ZERO-DEP (stdlib: json, re).

Użycie:
    python3 tools/measure_triad.py
    python3 tools/measure_triad.py --min-recall 1.0   # exit 1 jeśli recall spadnie poniżej progu

Wzorce dobiera po (id, opis-prefix): PL-RHET z opisem zaczynającym się od „triada", EN-TRIAD.
"""

import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_PATH = os.path.join(REPO_ROOT, "rules.json")
EVAL_PATH = os.path.join(REPO_ROOT, "tests", "triad_eval.md")

FLAGS = re.IGNORECASE | re.UNICODE


def triad_patterns():
    """Zwraca {'PL': skompilowany_regex, 'EN': skompilowany_regex} z rules.json."""
    rules = json.load(open(RULES_PATH, encoding="utf-8"))
    out = {}
    for r in rules:
        if r["id"] == "PL-RHET" and r["opis"].startswith("triada"):
            out["PL"] = re.compile(r["pattern"], FLAGS)
        elif r["id"] == "EN-TRIAD":
            out["EN"] = re.compile(r["pattern"], FLAGS)
    missing = {"PL", "EN"} - set(out)
    if missing:
        print(f"[ERROR] Nie znaleziono wzorca triady dla: {sorted(missing)}", file=sys.stderr)
        sys.exit(2)
    return out


def load_eval():
    """Czyta tests/triad_eval.md → lista (label, lang, tekst). Sekcje '## PL'/'## EN' wyznaczają lang."""
    items = []
    lang = None
    for line in open(EVAL_PATH, encoding="utf-8"):
        s = line.strip()
        if s.startswith("## "):
            tag = s[3:].strip().upper()
            lang = "PL" if tag.startswith("PL") else "EN" if tag.startswith("EN") else None
            continue
        if not s or s.startswith("#") or "|" not in s:
            continue
        label, _, text = s.partition("|")
        label = label.strip().upper()
        if label in ("TP", "FP") and lang:
            items.append((label, lang, text.strip()))
    return items


def main():
    pats = triad_patterns()
    items = load_eval()

    tp = fp = fn = tn = 0
    fp_examples, fn_examples = [], []
    for label, lang, text in items:
        hit = bool(pats[lang].search(text))
        if label == "TP":
            if hit:
                tp += 1
            else:
                fn += 1
                fn_examples.append(f"[{lang}] {text}")
        else:  # FP-kandydat
            if hit:
                fp += 1
                fp_examples.append(f"[{lang}] {text}")
            else:
                tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0

    print(f"Triada — zestaw {len(items)} przykładów: TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"  precyzja = {precision:.0%}   recall = {recall:.0%}")
    if fp_examples:
        print("  pozostałe FP (wyliczenia faktów wciąż łapane):")
        for e in fp_examples:
            print(f"    - {e}")
    if fn_examples:
        print("  FN (retoryczne triady przeoczone — to regresja recall!):")
        for e in fn_examples:
            print(f"    - {e}")

    min_recall = None
    if "--min-recall" in sys.argv:
        min_recall = float(sys.argv[sys.argv.index("--min-recall") + 1])
    if min_recall is not None and recall < min_recall:
        print(f"[ERROR] recall {recall:.0%} < próg {min_recall:.0%}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
