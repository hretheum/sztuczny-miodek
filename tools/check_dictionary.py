#!/usr/bin/env python3
"""
check_dictionary.py — gate słownika domenowego (D2 / KAN-196). ZERO-DEP (stdlib).

Weryfikuje:
  1. dictionary.example.json ładuje się (poprawna struktura allow/review/provenance),
  2. classify() działa: allow pomija, review klasyfikuje, dopasowanie po całym słowie,
  3. brak słownika / None → None (obecne zachowanie, zero zmiany),
  4. niepoprawna struktura → ValueError (czytelny błąd).

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import json
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
from miodek import dictionary  # noqa: E402

EXAMPLE = os.path.join(REPO_ROOT, "dictionary.example.json")


def main():
    fails = []

    # 1. przykładowy słownik ładuje się
    try:
        d = dictionary.load_dictionary(EXAMPLE)
        if d is None:
            fails.append("dictionary.example.json nie istnieje")
    except ValueError as e:
        fails.append(f"dictionary.example.json nie ładuje się: {e}")
        d = None

    # 2. classify: allow / review / całe słowo
    if d is not None:
        if d.classify("robust") != "allow":
            fails.append("classify('robust') != allow")
        if d.classify("robustness") is not None:
            fails.append("classify('robustness') powinno być None (całe słowo)")
        if d.classify("we leverage X") != "review":
            fails.append("classify('we leverage X') != review")
        if d.classify("zwykły tekst bez terminów") is not None:
            fails.append("classify(zwykły) powinno być None")

    # 3. brak słownika → None (zero zmiany)
    if dictionary.load_dictionary(None) is not None:
        fails.append("load_dictionary(None) powinno zwrócić None")
    if dictionary.load_dictionary("/nieistnieje.json") is not None:
        fails.append("load_dictionary(brak pliku) powinno zwrócić None")

    # 4. niepoprawna struktura → ValueError
    with tempfile.TemporaryDirectory() as t:
        bad = os.path.join(t, "bad.json")
        json.dump({"allow": "nie-lista"}, open(bad, "w"))
        try:
            dictionary.load_dictionary(bad)
            fails.append("niepoprawny słownik nie zgłosił ValueError")
        except ValueError:
            pass

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)
    print("OK   słownik domenowy: example ładuje się, classify allow/review/całe-słowo OK, "
          "brak słownika → zero zmiany, walidacja błędów działa.")


if __name__ == "__main__":
    main()
