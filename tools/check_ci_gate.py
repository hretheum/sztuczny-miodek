#!/usr/bin/env python3
"""
check_ci_gate.py — gate bramki jakości CI na merge request (F2). ZERO-DEP (stdlib).

Pilnuje, by ci_gate.py:
  (a) jawna ścieżka z twardym blokerem (baseline_pl_raport.md) → exit 1,
  (b) jawna ścieżka czysta (control_pl_clean.md)               → exit 0,
  (c) RÓŻNICA WOBEC F1: jawna ścieżka z samą gęstością (triad_eval.md,
      FAIL, blockers==0) → exit 1 (pełny werdykt łapie gęstość; w F1 ten sam
      plik daje exit 0),
  (d) mieszanka (jeden FAIL + jeden PASS) → exit 1,
  (e) brak plików prozy (ścieżka .py albo pusta lista) → exit 0 (nie wywraca się),
  (f) tryb --changed na lokalnym repo git w tempfile:
        diff z brudnym plikiem → exit 1,
        diff z samym czystym plikiem → exit 0,
        diff bez plików prozy → exit 0,
  (g) workflow .github/workflows/miodek-gate.yml istnieje i ma krytyczne pola
      (pull_request, fetch-depth, ci_gate.py) — bez parsera YAML, prosty grep.

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import os
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CI_GATE = os.path.join(REPO_ROOT, "tools", "ci_gate.py")
TESTS_DIR = os.path.join(REPO_ROOT, "tests")
WORKFLOW = os.path.join(REPO_ROOT, ".github", "workflows", "miodek-gate.yml")

BASELINE = os.path.join(TESTS_DIR, "baseline_pl_raport.md")   # twardy bloker → FAIL
CONTROL = os.path.join(TESTS_DIR, "control_pl_clean.md")      # czysty → PASS
DENSITY_ONLY = os.path.join(TESTS_DIR, "triad_eval.md")       # sama gęstość → FAIL


def rc_paths(*paths):
    """Uruchom ci_gate.py w trybie jawnych ścieżek, zwróć kod wyjścia."""
    return subprocess.run(
        [sys.executable, CI_GATE, *paths], capture_output=True, text=True
    ).returncode


def _git(args, cwd):
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
    )
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, env=env
    )


def main():
    fails = []

    # (a) twardy bloker → exit 1
    if rc_paths(BASELINE) != 1:
        fails.append("(a) baseline_pl_raport.md (twardy bloker) powinien dać exit 1.")

    # (b) czysty → exit 0
    if rc_paths(CONTROL) != 0:
        fails.append("(b) control_pl_clean.md (czysty) powinien dać exit 0.")

    # (c) sama gęstość → exit 1 (różnica wobec F1, gdzie ten sam plik = exit 0)
    if rc_paths(DENSITY_ONLY) != 1:
        fails.append("(c) triad_eval.md (FAIL z samej gęstości, blockers==0) powinien dać "
                     "exit 1 — F2 łapie gęstość (pełny werdykt), w odróżnieniu od F1.")

    # (d) mieszanka FAIL + PASS → exit 1
    if rc_paths(CONTROL, BASELINE) != 1:
        fails.append("(d) mieszanka (czysty + bloker) powinna dać exit 1.")

    # (e1) ścieżka nie-prozy (.py) → exit 0 (filtr odsiewa, brak prozy = zielono)
    if rc_paths(CI_GATE) != 0:
        fails.append("(e) jawna ścieżka .py (nie-proza) powinna dać exit 0 (brak prozy nie wywraca).")
    # (e2) pusta lista argumentów → exit 0
    if rc_paths() != 0:
        fails.append("(e) brak argumentów (zero plików prozy) powinien dać exit 0.")

    # (f) tryb --changed na świeżym repo git w tempfile
    if shutil.which("git") is None:
        fails.append("(f) brak gita — nie da się zweryfikować trybu --changed.")
    else:
        tmp = tempfile.mkdtemp(prefix="ci_gate_test_")
        try:
            _git(["init", "-q"], tmp)
            _git(["checkout", "-q", "-b", "main"], tmp)
            # baza: czysty plik prozy + plik nie-proza
            shutil.copy(CONTROL, os.path.join(tmp, "doc.md"))
            with open(os.path.join(tmp, "code.py"), "w", encoding="utf-8") as fh:
                fh.write("x = 1\n")
            _git(["add", "-A"], tmp)
            _git(["commit", "-q", "-m", "baza"], tmp)

            # f1: gałąź dokłada brudny plik prozy → diff main...HEAD = exit 1
            _git(["checkout", "-q", "-b", "feature"], tmp)
            shutil.copy(BASELINE, os.path.join(tmp, "raport.md"))
            _git(["add", "-A"], tmp)
            _git(["commit", "-q", "-m", "brudny raport"], tmp)
            r = subprocess.run(
                [sys.executable, CI_GATE, "--changed", "--base", "main", "--head", "HEAD"],
                cwd=tmp, capture_output=True, text=True,
            ).returncode
            if r != 1:
                fails.append(f"(f1) --changed z brudnym plikiem prozy powinno dać exit 1, było {r}.")

            # f2: gałąź dokłada tylko czysty plik prozy → exit 0
            _git(["checkout", "-q", "main"], tmp)
            _git(["checkout", "-q", "-b", "feature-clean"], tmp)
            shutil.copy(CONTROL, os.path.join(tmp, "doc2.md"))
            _git(["add", "-A"], tmp)
            _git(["commit", "-q", "-m", "czysty doc2"], tmp)
            r = subprocess.run(
                [sys.executable, CI_GATE, "--changed", "--base", "main", "--head", "HEAD"],
                cwd=tmp, capture_output=True, text=True,
            ).returncode
            if r != 0:
                fails.append(f"(f2) --changed z samym czystym plikiem prozy powinno dać exit 0, było {r}.")

            # f3: gałąź dokłada tylko plik nie-proza → brak prozy → exit 0
            _git(["checkout", "-q", "main"], tmp)
            _git(["checkout", "-q", "-b", "feature-code"], tmp)
            with open(os.path.join(tmp, "more.py"), "w", encoding="utf-8") as fh:
                fh.write("y = 2\n")
            _git(["add", "-A"], tmp)
            _git(["commit", "-q", "-m", "tylko kod"], tmp)
            r = subprocess.run(
                [sys.executable, CI_GATE, "--changed", "--base", "main", "--head", "HEAD"],
                cwd=tmp, capture_output=True, text=True,
            ).returncode
            if r != 0:
                fails.append(f"(f3) --changed bez plików prozy powinno dać exit 0 (brak prozy), było {r}.")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # (g) workflow istnieje i ma krytyczne pola
    if not os.path.isfile(WORKFLOW):
        fails.append(f"(g) brak workflow {os.path.relpath(WORKFLOW, REPO_ROOT)}.")
    else:
        with open(WORKFLOW, encoding="utf-8") as fh:
            wf = fh.read()
        for needle in ("pull_request", "fetch-depth", "ci_gate.py", "--changed"):
            if needle not in wf:
                fails.append(f"(g) workflow nie zawiera krytycznego pola '{needle}'.")

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)
    print("OK   bramka CI na MR (F2): pełny werdykt na jawnych i zmienionych plikach prozy "
          "(gęstość łapana, brak prozy = zielono); workflow ma krytyczne pola.")


if __name__ == "__main__":
    main()
