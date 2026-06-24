#!/usr/bin/env python3
"""
check_batch.py — gate agregatu zbiorczego batch (KAN-231, flaga --report). ZERO-DEP (stdlib).

Pilnuje, przez dispatcher `python3 -m miodek.cli lint`:
  1. --report na pliku FAIL: wyjście ZAWIERA blok '== BATCH ==', exit 1 (werdykt zbiorczy),
  2. BEZ --report: wyjście NIE zawiera '== BATCH ==' (brak regresji),
  3. --format json --report: JSON parsuje się i ma klucz 'batch' ze spójną strukturą
     (files, verdicts jako obiekt, top_rules jako lista obiektów {rule, count}),
  4. batch po wielu plikach (FAIL + PASS): files==2, verdicts liczy oba werdykty.

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src")
TESTS = os.path.join(REPO_ROOT, "tests")
BASELINE = os.path.join(TESTS, "baseline_pl_raport.md")
CONTROL = os.path.join(TESTS, "control_pl_clean.md")


def run(args):
    """Uruchom `python3 -m miodek.cli <args>` z PYTHONPATH=src. Zwróć (rc, out+err)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    p = subprocess.run([sys.executable, "-m", "miodek.cli", *args],
                       capture_output=True, text=True, env=env)
    return p.returncode, (p.stdout + p.stderr)


def main():
    fails = []

    # 1. --report na FAIL: blok BATCH obecny, exit 1
    rc, out = run(["lint", "--lang", "both", "--report", BASELINE])
    if "== BATCH ==" not in out:
        fails.append("--report nie wyprodukował bloku '== BATCH ==' na pliku FAIL")
    if rc != 1:
        fails.append(f"--report na FAIL: oczekiwano exit 1, jest {rc}")

    # 2. brak regresji: bez --report ZERO bloku BATCH
    rc, out = run(["lint", "--lang", "both", BASELINE])
    if "== BATCH ==" in out:
        fails.append("bez --report pojawił się blok '== BATCH ==' (regresja wyjścia)")

    # 3. JSON + --report: parsuje się, klucz batch, spójna struktura
    rc, out = run(["lint", "--lang", "both", "--format", "json", "--report", BASELINE])
    # wytnij ewentualny szum: bierzemy od pierwszego '{'
    payload = out[out.find("{"):] if "{" in out else out
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        data = None
        fails.append(f"--format json --report: wynik nie jest poprawnym JSON ({e})")
    if data is not None:
        b = data.get("batch")
        if not isinstance(b, dict):
            fails.append("JSON --report: brak obiektu 'batch'")
        else:
            if not isinstance(b.get("verdicts"), dict):
                fails.append("batch.verdicts powinno być obiektem (dict)")
            tr = b.get("top_rules")
            if not isinstance(tr, list) or (tr and not all(
                    isinstance(x, dict) and "rule" in x and "count" in x for x in tr)):
                fails.append("batch.top_rules powinno być listą obiektów {rule, count}")

    # 4. wiele plików (FAIL + PASS): files==2, oba werdykty policzone
    rc, out = run(["lint", "--lang", "both", "--format", "json", "--report", BASELINE, CONTROL])
    payload = out[out.find("{"):] if "{" in out else out
    try:
        b = json.loads(payload)["batch"]
        if b["files"] != 2:
            fails.append(f"batch.files dla 2 plików = {b['files']} (oczekiwano 2)")
        if b["verdicts"].get("PASS", 0) < 1 or (b["verdicts"].get("FAIL", 0) + b["verdicts"].get("FAIL-HARD", 0)) < 1:
            fails.append(f"batch.verdicts nie policzył FAIL i PASS: {b['verdicts']}")
    except (json.JSONDecodeError, KeyError) as e:
        fails.append(f"batch dla wielu plików: błąd struktury ({e})")

    if fails:
        print("check_batch: ROZJAZD")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    print("OK   agregat batch (KAN-231): --report daje blok == BATCH == (exit 1 na FAIL), bez flagi "
          "zero bloku, JSON ma spójny klucz 'batch' (verdicts obiekt, top_rules lista {rule,count}), "
          "agregat po wielu plikach liczy files i oba werdykty. ZERO sieci, ZERO modelu.")
    sys.exit(0)


if __name__ == "__main__":
    main()
