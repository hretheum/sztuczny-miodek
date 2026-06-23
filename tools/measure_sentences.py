#!/usr/bin/env python3
"""
measure_sentences.py — regresja segmentera zdań (C2 / KAN-191).

Sprawdza, czy `adapter.split_sentences_faithful` zwraca oczekiwaną liczbę zdań na etykietowanym
zestawie tests/sentence_eval.md (obsługa skrótów, inicjałów, liczb, wieloznakowych separatorów).
ZERO-DEP (stdlib). Exit 1 gdy którykolwiek przypadek się nie zgadza (gate w run_tests.sh).

Użycie:
    python3 tools/measure_sentences.py
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_PATH = os.path.join(REPO_ROOT, "tests", "sentence_eval.md")

sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
from miodek import adapter  # noqa: E402


def load_cases():
    cases = []
    for line in open(EVAL_PATH, encoding="utf-8"):
        s = line.strip()
        if not s or s.startswith("#") or "|" not in s:
            continue
        head, _, text = s.partition("|")
        head = head.strip()
        if not head.isdigit():
            continue
        cases.append((int(head), text.strip()))
    return cases


def main():
    cases = load_cases()
    fails = []
    for expected, text in cases:
        got = len([seg for seg in adapter.split_sentences_faithful(text) if seg.text.strip()])
        if got != expected:
            fails.append((expected, got, text))

    ok = len(cases) - len(fails)
    print(f"Segmenter zdań — {ok}/{len(cases)} przypadków OK")
    for expected, got, text in fails:
        print(f"  [FAIL] oczekiwano {expected}, otrzymano {got}: {text}", file=sys.stderr)

    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
