#!/usr/bin/env python3
"""
check_write_gate.py — gate bramki write-time (F1). ZERO-DEP (stdlib).

Pilnuje, by czysta reguła `gate_decision` blokowała WYŁĄCZNIE twarde blokery:
  (a) blockers > 0                         → block
  (b) sama wysoka gęstość (FAIL, blockers==0) → NIE block  ← serce F1
  (c) verdict == FAIL-HARD                  → block
  (d) PASS, blockers == 0                   → NIE block
Plus: powód blokady wymienia id + linię blokera; smoke end-to-end na realnych
plikach testowych (baseline = block, control = przepuść) przez tryb CLI hooka.

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_DIR = os.path.join(REPO_ROOT, "hooks")
sys.path.insert(0, HOOKS_DIR)
import miodek_write_gate as gate  # noqa: E402

GATE_SCRIPT = os.path.join(HOOKS_DIR, "miodek_write_gate.py")
TESTS_DIR = os.path.join(REPO_ROOT, "tests")


def _m(summaries, hits=None):
    return {"summary": summaries, "hits": hits or []}


def main():
    fails = []

    # (a) blockers > 0 → block
    block, reason = gate.gate_decision(_m(
        [{"file": "a.md", "blockers": 3, "verdict": "FAIL", "density": 19.0}],
        [{"file": "a.md", "line": 1, "id": "PL-TYPO", "klasa": "block", "match": "# 🚀 Nagłówek"}],
    ))
    if not block:
        fails.append("(a) blockers>0 powinno blokować, a nie blokuje.")
    if block and "PL-TYPO" not in reason:
        fails.append("(a) powód blokady nie wymienia id blokera (PL-TYPO).")
    if block and "linia 1" not in reason:
        fails.append("(a) powód blokady nie wymienia numeru linii blokera.")

    # (b) sama gęstość: FAIL z blockers == 0 → NIE block  (serce F1)
    block, reason = gate.gate_decision(_m(
        [{"file": "b.md", "blockers": 0, "verdict": "FAIL", "density": 12.0}],
    ))
    if block:
        fails.append("(b) sama gęstość (FAIL, blockers==0) NIE powinna blokować — a blokuje. To łamie F1.")
    if not reason:
        fails.append("(b) sama gęstość powinna dać ostrzeżenie w reason (bez blokady).")

    # (c) FAIL-HARD → block (nawet sprawdzane jawnie)
    block, _ = gate.gate_decision(_m(
        [{"file": "c.md", "blockers": 1, "verdict": "FAIL-HARD", "density": 2.0}],
    ))
    if not block:
        fails.append("(c) FAIL-HARD powinno blokować, a nie blokuje.")

    # (c2) FAIL-HARD przy blockers==0 (skrajny przypadek) też blokuje
    block, _ = gate.gate_decision(_m(
        [{"file": "c2.md", "blockers": 0, "verdict": "FAIL-HARD", "density": 2.0}],
    ))
    if not block:
        fails.append("(c2) FAIL-HARD przy blockers==0 powinno blokować (jawny warunek), a nie blokuje.")

    # (d) PASS → przepuść
    block, reason = gate.gate_decision(_m(
        [{"file": "d.md", "blockers": 0, "verdict": "PASS", "density": 1.0}],
    ))
    if block:
        fails.append("(d) PASS nie powinno blokować, a blokuje.")
    if reason:
        fails.append("(d) PASS nie powinno dawać żadnego powodu.")

    # (e) wiele plików: jeden z blokerem wśród czystych → block
    block, _ = gate.gate_decision(_m(
        [
            {"file": "ok.md", "blockers": 0, "verdict": "PASS", "density": 1.0},
            {"file": "bad.md", "blockers": 2, "verdict": "FAIL", "density": 9.0},
        ],
        [{"file": "bad.md", "line": 5, "id": "PL-ANTI", "klasa": "block", "match": "X, a nie Y"}],
    ))
    if not block:
        fails.append("(e) zestaw z jednym plikiem z blokerem powinien blokować, a nie blokuje.")

    # (f) smoke end-to-end przez tryb CLI hooka: baseline = exit 1, control = exit 0,
    #     triad_eval = exit 0 (sama gęstość FAIL bez blokerów, realny przebieg lintera).
    baseline = os.path.join(TESTS_DIR, "baseline_pl_raport.md")
    control = os.path.join(TESTS_DIR, "control_pl_clean.md")
    density_only = os.path.join(TESTS_DIR, "triad_eval.md")
    rc_bad = subprocess.run(
        [sys.executable, GATE_SCRIPT, baseline], capture_output=True, text=True
    ).returncode
    if rc_bad != 1:
        fails.append(f"(f) CLI na baseline_pl_raport.md powinno exit 1 (twardy bloker), było {rc_bad}.")
    rc_ok = subprocess.run(
        [sys.executable, GATE_SCRIPT, control], capture_output=True, text=True
    ).returncode
    if rc_ok != 0:
        fails.append(f"(f) CLI na control_pl_clean.md powinno exit 0 (czysty), było {rc_ok}.")
    # (f3) realny przebieg lintera na triad_eval.md daje FAIL z density wysoką
    #      i blockers==0 — bramka MUSI przepuścić (serce F1, pętla end-to-end).
    rc_density = subprocess.run(
        [sys.executable, GATE_SCRIPT, density_only], capture_output=True, text=True
    ).returncode
    if rc_density != 0:
        fails.append(
            f"(f) CLI na triad_eval.md (FAIL, density wysoka, blockers==0) powinno exit 0 "
            f"— sama gęstość NIE blokuje write-time end-to-end; było {rc_density}."
        )

    # (g) smoke hook-mode: payload na stdin + MIODEK_WRITE_GATE=1 → blokada dla baseline.
    #     Blokada jest dwukanałowa: JSON decision=block na stdout ORAZ exit 2 z reason na stderr
    #     (kanon PostToolUse, odporność na wersję Claude Code).
    env = dict(os.environ, MIODEK_WRITE_GATE="1")
    payload = json.dumps({
        "tool_name": "Write",
        "tool_input": {"file_path": baseline, "content": ""},
    })
    proc = subprocess.run(
        [sys.executable, GATE_SCRIPT], input=payload, capture_output=True, text=True, env=env
    )
    if proc.returncode != 2:
        fails.append(f"(g) hook-mode na baseline powinien blokować exit 2 (kanon PostToolUse); było {proc.returncode}.")
    if "TWARDE BLOKERY" not in proc.stderr:
        fails.append("(g) hook-mode na baseline powinien wypisać powód na stderr (kanał exit 2).")
    try:
        decision = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except Exception:
        decision = {}
        fails.append("(g) hook-mode na baseline nie zwrócił poprawnego JSON na stdout.")
    if decision.get("decision") != "block":
        fails.append("(g) hook-mode (MIODEK_WRITE_GATE=1) na baseline powinien dać decision=block na stdout.")
    if decision.get("hookSpecificOutput", {}).get("permissionDecision") != "deny":
        fails.append("(g) hook-mode na baseline powinien dać hookSpecificOutput.permissionDecision=deny (lustro dla nowszej konwencji).")

    # (h) opt-in: bez MIODEK_WRITE_GATE hook-mode nie blokuje (puste stdout).
    env_off = {k: v for k, v in os.environ.items() if k != "MIODEK_WRITE_GATE"}
    proc_off = subprocess.run(
        [sys.executable, GATE_SCRIPT], input=payload, capture_output=True, text=True, env=env_off
    )
    if proc_off.stdout.strip():
        fails.append("(h) bez MIODEK_WRITE_GATE hook-mode powinien być bierny (puste stdout), a coś wypisał.")
    if proc_off.returncode != 0:
        fails.append(f"(h) bez MIODEK_WRITE_GATE hook-mode powinien exit 0 (bierny), było {proc_off.returncode}.")

    # (i) smoke hook-mode na pliku z samą gęstością (FAIL, blockers==0) → NIE blokuje:
    #     exit 0, puste stdout (serce F1 także w pełnym przebiegu hook-mode).
    density_only = os.path.join(TESTS_DIR, "triad_eval.md")
    payload_density = json.dumps({
        "tool_name": "Write",
        "tool_input": {"file_path": density_only, "content": ""},
    })
    proc_density = subprocess.run(
        [sys.executable, GATE_SCRIPT], input=payload_density, capture_output=True, text=True, env=env
    )
    if proc_density.returncode != 0:
        fails.append(f"(i) hook-mode na triad_eval.md (sama gęstość) powinien exit 0 (nie blokuje), było {proc_density.returncode}.")
    if proc_density.stdout.strip():
        fails.append("(i) hook-mode na triad_eval.md (sama gęstość) nie powinien nic wypisać na stdout — to serce F1.")

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)
    print("OK   bramka write-time (F1): blokuje tylko twarde blokery; sama gęstość NIE blokuje; "
          "opt-in działa; smoke CLI+hook zielony.")


if __name__ == "__main__":
    main()
