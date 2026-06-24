#!/usr/bin/env python3
"""
check_cli.py — gate unified CLI `miodek` (KAN-228). ZERO-DEP (stdlib).

Dispatcher miodek.cli mapuje podkomendy na moduły pakietu:
  lint    -> ai_linter         correct -> corrector
  gate    -> publish_gate      lt      -> languagetool_check

Pilnuje, by `python3 -m miodek.cli <cmd> ...`:
  1. lint: baseline -> exit 1 (FAIL), plik kontrolny -> exit 0 (PASS),
  2. gate: plik kontrolny -> exit 0 (Stage 1 czysty), baseline -> exit != 0 (FAIL),
  3. correct z engine stub -> exit 2 (bramka UX KAN-222: bez realnego silnika ODMAWIA,
     zamiast mleć atrapą; to zarazem dowód delegacji cli->corrector),
  4. brak komendy / --help -> exit 0 z usage; nieznana komenda -> exit 2,
  5. lt --help -> exit 0 (zero sieci),
  6. delegacja zachowuje kod wyjścia podkomendy (nie gubi go).

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

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

    rc, _ = run(["lint", "--lang", "both", BASELINE])
    if rc != 1:
        fails.append(f"lint baseline: exit {rc}, oczekiwano 1 (FAIL)")
    rc, _ = run(["lint", "--lang", "pl", CONTROL])
    if rc != 0:
        fails.append(f"lint control: exit {rc}, oczekiwano 0 (PASS)")

    rc, _ = run(["gate", CONTROL])
    if rc != 0:
        fails.append(f"gate control: exit {rc}, oczekiwano 0 (Stage 1 czysty)")
    rc, _ = run(["gate", BASELINE])
    if rc == 0:
        fails.append("gate baseline: exit 0, oczekiwano != 0 (FAIL)")

    rc, _ = run(["correct", "--file", CONTROL, "--engine", "stub", "--lang", "pl"])
    if rc != 2:
        fails.append(f"correct (stub): exit {rc}, oczekiwano 2 (bramka UX KAN-222 — odmowa bez realnego silnika)")

    rc, out = run([])
    if rc != 0 or "Użycie" not in out:
        fails.append(f"brak komendy: exit {rc} / usage {'jest' if 'Użycie' in out else 'BRAK'} (oczekiwano 0+usage)")
    rc, _ = run(["--help"])
    if rc != 0:
        fails.append(f"--help: exit {rc}, oczekiwano 0")
    rc, _ = run(["nieznana-komenda"])
    if rc != 2:
        fails.append(f"nieznana komenda: exit {rc}, oczekiwano 2")

    rc, _ = run(["lt", "--help"])
    if rc != 0:
        fails.append(f"lt --help: exit {rc}, oczekiwano 0 (zero sieci)")

    rc, _ = run(["build-dict", "--help"])
    if rc != 0:
        fails.append(f"build-dict --help: exit {rc}, oczekiwano 0")
    rc, out = run(["build-dict", CONTROL, "--min-count", "1", "--min-files", "1", "--projekt", "gate"])
    if rc != 0:
        fails.append(f"build-dict: exit {rc}, oczekiwano 0")
    if '"review"' not in out or '"allow"' not in out:
        fails.append("build-dict: wyjście nie jest szkicem słownika (brak kluczy allow/review)")

    if fails:
        print("FAIL check_cli:", file=sys.stderr)
        for f in fails:
            print("  -", f, file=sys.stderr)
        sys.exit(1)
    print("OK   CLI miodek: dispatcher lint/correct/gate/lt/build-dict deleguje i zachowuje kody "
          "wyjścia (baseline FAIL, control PASS, gate, correct stub, usage/--help, nieznana=2, "
          "lt --help, build-dict szkic z allow/review).")


if __name__ == "__main__":
    main()
