#!/usr/bin/env python3
"""
check_decision_log.py — gate logu decyzji accept/reject (D4 / KAN-198). ZERO-DEP (stdlib).

Weryfikuje na tymczasowym logu:
  1. append-only: kolejne append_decision dokładają wpisy (nie nadpisują), 1 wpis = 1 linia JSONL,
  2. round-trip: read_decisions odczytuje to, co zapisano (accept/reject, pola),
  3. walidacja: zły verdict / brak pola → ValueError,
  4. brak pliku → [] (czysty start),
  5. surowiec dla D3/B3: z logu da się wyłuskać terminy reject (→ słownik) i pary metryka/werdykt.

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
from miodek import decision_log as DL  # noqa: E402


def main():
    fails = []
    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, "dec.jsonl")

        # 4. brak pliku → []
        if DL.read_decisions(log) != []:
            fails.append("brak pliku powinien dać [] ")

        # 1. append-only + 2. round-trip
        DL.append_decision({"ts": "2026-06-23T10:00:00Z", "verdict": "reject", "id": "EN-CLICHE",
                            "klasa": "review", "fragment": "robust", "file": "doc.md", "line": 1}, log)
        DL.append_decision({"ts": "2026-06-23T10:01:00Z", "verdict": "accept", "id": "PL-SIGN",
                            "fragment": "warto podkreślić"}, log)
        DL.append_decision({"ts": "2026-06-23T10:02:00Z", "verdict": "reject", "id": "density",
                            "fragment": "9.0", "metric_value": 9}, log)

        items = DL.read_decisions(log)
        if len(items) != 3:
            fails.append(f"append-only: oczekiwano 3 wpisów, jest {len(items)}")
        if sum(1 for _ in open(log, encoding="utf-8")) != 3:
            fails.append("JSONL: oczekiwano 3 linii (1 wpis = 1 linia)")
        if not items or items[0]["verdict"] != "reject" or items[0]["fragment"] != "robust":
            fails.append("round-trip: pierwszy wpis nie zgadza się")

        # 3. walidacja
        try:
            DL.append_decision({"ts": "x", "verdict": "maybe", "id": "X", "fragment": "y"}, log)
            fails.append("zły verdict nie zgłosił ValueError")
        except ValueError:
            pass
        try:
            DL.append_decision({"ts": "x", "verdict": "accept", "id": "X"}, log)  # brak fragment
            fails.append("brak wymaganego pola nie zgłosił ValueError")
        except ValueError:
            pass

        # 5. surowiec dla D3/B3
        reject_terms = [it["fragment"] for it in items if it["verdict"] == "reject" and it.get("klasa")]
        if "robust" not in reject_terms:
            fails.append("D3: termin reject 'robust' niewyłuskiwalny z logu")
        metric_pairs = [(it["id"], it["metric_value"], it["verdict"]) for it in items if "metric_value" in it]
        if ("density", 9, "reject") not in metric_pairs:
            fails.append("B3: para (metryka, werdykt) niewyłuskiwalna z logu")

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)
    print("OK   log decyzji: append-only (3 linie JSONL), round-trip, walidacja, brak pliku→[], "
          "surowiec dla D3 (reject→termin) i B3 (metryka/werdykt) wyłuskiwalny.")


if __name__ == "__main__":
    main()
