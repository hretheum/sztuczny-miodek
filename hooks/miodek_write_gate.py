#!/usr/bin/env python3
"""
miodek_write_gate.py — bramka write-time skilla sztuczny-miodek (F1).

Sens: gdy agent zapisze plik prozy (.md/.txt), ta bramka uruchamia linter
i ZATRZYMUJE pracę WYŁĄCZNIE przy twardych blokerach (klasa „block").
Sama wysoka gęstość (trafienia klasy „review" bez ani jednego blokera) NIE blokuje —
co najwyżej dokłada krótkie ostrzeżenie. To odróżnia bramkę write-time od bramki CI
(`ai_linter.py` exit 1 łapie też gęstość) i od bramki przed publikacją.

KLUCZOWY NIUANS WERDYKTU (potwierdzony w ai_linter.py:536-543):
  verdict == "FAIL" odpala się także gdy density > próg PRZY blockers == 0.
  Dlatego bramka NIE może opierać się na exit code lintera. Blokuje tylko gdy:
      summary["blockers"] > 0  LUB  summary["verdict"] == "FAIL-HARD".

Dwa tryby:
  1. Hook Claude Code (bez argumentów): czyta payload JSON ze stdin
     ({tool_name, tool_input:{file_path,...}}), filtruje do .md/.txt, lintuje,
     i przy blokerach wypisuje na stdout {"decision":"block","reason":...} (exit 0).
     OPT-IN: aktywna tylko gdy MIODEK_WRITE_GATE ∈ {1,true,on} — sama instalacja
     pluginu NIE zaczyna blokować edycji.
  2. CLI / pre-commit (ścieżki w argv): lintuje podane pliki, wypisuje powód
     na stderr i kończy exit 1 przy twardym blokerze, exit 0 w przeciwnym razie.
     Tryb CLI nie wymaga MIODEK_WRITE_GATE (jawne wywołanie = świadoma decyzja).

ZERO-DEP (stdlib: json, os, subprocess, sys). Linter wołany jako podproces —
zachowanie lintera bez zmian, izolacja. Fail-open: każda własna awaria → brak blokady.
"""

import json
import os
import subprocess
import sys

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
LINTER = os.path.join(HOOK_DIR, "..", "ai_linter.py")
PROSE_EXTS = (".md", ".txt")


# ----------------------------------------------------------------------------
# Czysta reguła decyzji — bez I/O, w pełni testowalna (wzorzec config.load_*).
# ----------------------------------------------------------------------------
def gate_decision(manifest):
    """Reguła F1. Wejście: manifest JSON lintera ({"hits":[...], "summary":[...]}).
    Zwraca (block: bool, reason: str).

    BLOKUJE wyłącznie gdy w którymkolwiek pliku:
        summary["blockers"] > 0  LUB  summary["verdict"] == "FAIL-HARD".
    Sama gęstość (verdict == "FAIL" przy blockers == 0) NIE blokuje — ostrzeżenie.

    Powód blokady wymienia twarde blokery (id + linia + plik), żeby agent
    wiedział, co poprawić.
    """
    summaries = manifest.get("summary", []) or []
    hits = manifest.get("hits", []) or []

    blocking_files = []  # pliki z twardym blokerem
    warn_files = []      # pliki z samą gęstością (FAIL bez blokerów)
    for s in summaries:
        verdict = s.get("verdict", "")
        blockers = s.get("blockers", 0)
        if verdict == "FAIL-HARD" or blockers > 0:
            blocking_files.append(s)
        elif verdict == "FAIL":  # tu blockers == 0 → wyłącznie gęstość
            warn_files.append(s)

    if not blocking_files:
        if warn_files:
            names = ", ".join(s.get("file", "?") for s in warn_files)
            return False, (
                f"Bramka write-time: brak twardych blokerów, zapis przepuszczony. "
                f"Ostrzeżenie — wysoka gęstość trafień klasy review w: {names} "
                f"(to nie blokuje write-time; rozstrzygnij przed publikacją)."
            )
        return False, ""

    # Zbuduj ludzki powód: per-plik lista blokerów (id + linia).
    block_paths = {s.get("file") for s in blocking_files}
    block_ids = [h for h in hits if h.get("file") in block_paths and h.get("klasa") == "block"]

    lines = ["Bramka write-time sztuczny-miodek: TWARDE BLOKERY — popraw przed dalszą pracą."]
    for s in blocking_files:
        fp = s.get("file", "?")
        verdict = s.get("verdict", "")
        n = s.get("blockers", 0)
        head = "FAIL-HARD (np. cyrylica)" if verdict == "FAIL-HARD" else f"{n} blokerów"
        lines.append(f"  {fp}: {head} (werdykt {verdict}).")
        per_file = [h for h in block_ids if h.get("file") == fp]
        for h in per_file[:12]:  # cap, żeby powód nie spuchł
            frag = (h.get("match", "") or "").strip().replace("\n", " ")
            if len(frag) > 70:
                frag = frag[:67] + "..."
            lines.append(f"    - {h.get('id')} (linia {h.get('line')}): {frag}")
        if len(per_file) > 12:
            lines.append(f"    ... oraz {len(per_file) - 12} więcej.")
    lines.append(
        "Reguła F1: blokujemy WYŁĄCZNIE twarde blokery (klasa block / FAIL-HARD); "
        "samej gęstości tu nie blokujemy."
    )
    return True, "\n".join(lines)


# ----------------------------------------------------------------------------
# I/O wokół czystej reguły.
# ----------------------------------------------------------------------------
def _enabled():
    """Bramka hook-mode aktywna tylko po jawnym włączeniu (opt-in)."""
    return os.environ.get("MIODEK_WRITE_GATE", "").strip().lower() in ("1", "true", "on", "yes")


def run_linter(paths):
    """Uruchom linter jako podproces, zwróć manifest JSON (dict) albo None przy awarii."""
    if not paths:
        return None
    try:
        proc = subprocess.run(
            [sys.executable, LINTER, "--format", "json", *paths],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:
        return None  # fail-open
    if not proc.stdout:
        return None
    try:
        return json.loads(proc.stdout)
    except Exception:
        return None  # fail-open


def _is_prose(path):
    return bool(path) and path.lower().endswith(PROSE_EXTS)


def hook_mode():
    """Tryb hooka Claude Code: payload JSON na stdin → ewentualna decyzja block na stdout.
    Zawsze exit 0 (decyzja przekazywana polem JSON, nie kodem). Fail-open."""
    if not _enabled():
        return 0  # opt-in: bez MIODEK_WRITE_GATE bramka jest bierna

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # nie umiemy sparsować → nie blokuj

    tool_input = payload.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not _is_prose(file_path):
        return 0  # nie nasza domena (tylko proza .md/.txt)
    if not os.path.isfile(file_path):
        return 0  # PostToolUse: plik powinien istnieć; brak → nie blokuj

    manifest = run_linter([file_path])
    if manifest is None:
        return 0  # awaria lintera → fail-open

    block, reason = gate_decision(manifest)
    if block:
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


def cli_mode(paths):
    """Tryb CLI / pre-commit: lintuje podane ścieżki, blokuje (exit 1) przy twardym blokerze.
    Filtruje do prozy (.md/.txt). Powód na stderr."""
    prose = [p for p in paths if _is_prose(p) and os.path.isfile(p)]
    if not prose:
        return 0  # nic prozatorskiego do sprawdzenia

    manifest = run_linter(prose)
    if manifest is None:
        print("[miodek-write-gate] linter nie zwrócił manifestu — przepuszczam (fail-open).",
              file=sys.stderr)
        return 0

    block, reason = gate_decision(manifest)
    if block:
        print(reason, file=sys.stderr)
        return 1
    if reason:
        print(reason, file=sys.stderr)  # ostrzeżenie gęstości, ale nie blokuje
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        return cli_mode(argv)
    return hook_mode()


if __name__ == "__main__":
    sys.exit(main())
