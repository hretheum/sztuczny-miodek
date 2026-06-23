#!/usr/bin/env python3
"""
ci_gate.py — bramka jakości CI na merge request (F2). ZERO-DEP (stdlib).

Sens: na pull requeście CI uruchamia linter na ZMIENIONYCH plikach prozy
(.md/.txt) i FAIL-uje check, jeśli którykolwiek nie przechodzi PEŁNEGO werdyktu.

Różnica wobec F1 (write-time, hook):
  - F1 (hooks/miodek_write_gate.py) blokuje WYŁĄCZNIE twarde blokery
    (klasa block / FAIL-HARD), sama gęstość przechodzi. Polityka „nie przeszkadzaj
    w pisaniu".
  - F2 (ten plik) to PEŁNA bramka: FAIL-uje na pełnym werdykcie lintera, czyli gdy
    verdict ∈ {FAIL, FAIL-HARD} — blokery LUB gęstość ponad próg.

F2 NIE importuje miodek_write_gate i NIE woła gate_decision. Polega WYŁĄCZNIE na
kodzie wyjścia lintera, który daje dokładnie tę semantykę:
  0 = wszystkie pliki PASS,
  1 = którykolwiek plik FAIL/FAIL-HARD,
  2 = błąd wczytania reguł/konfiguracji (--profile/--dict/rules.json).

Tryby:
  Tryb 1 — jawne ścieżki (self-test, ręczne użycie):
      python3 tools/ci_gate.py PLIK [...]
    Filtruje argumenty do prozy (.md/.txt, istniejące pliki), woła linter na nich.

  Tryb 2 — zmienione pliki względem bazy (CI):
      python3 tools/ci_gate.py --changed --base <ref> [--head <ref>]
    Liczy zmienione pliki przez `git diff --name-only --diff-filter=d <base>...<head>`
    (trójkropek = diff od merge-base, kanon recenzji PR), filtruje do prozy istniejącej
    w drzewie, woła linter.

Kody wyjścia (pełny werdykt, NIE hard-only):
  0 — brak zmienionych plików prozy LUB wszystkie PASS (linter exit 0)
  1 — którykolwiek plik = FAIL/FAIL-HARD (linter exit 1)
  2 — błąd reguł/konfiguracji lintera (przepuszczamy exit 2) LUB błąd `git diff`/braku gita

Zasada: brak plików prozy w diffie → exit 0 (zielony check), NIE błąd. Bramka nie
wywraca PR-ów, które nie tykają prozy. To bramka jakości: fail-zamknięty na błędzie
lintera/reguł (exit 2 idzie dalej), ale błąd środowiska (brak gita/bazy) ma czytelny
komunikat i też kończy niezerowo, żeby check nie zazielenił się po cichu.
"""

import argparse
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINTER = os.path.join(REPO_ROOT, "ai_linter.py")

# Rozszerzenia prozy, które bramka lintuje. Linter sam skanuje szerzej (.html itp.),
# ale na merge request pilnujemy prozy: .md/.txt.
PROSE_EXTS = (".md", ".txt")


def is_prose(path):
    return path.lower().endswith(PROSE_EXTS)


def filter_prose(paths):
    """Zostaw tylko istniejące pliki prozy (.md/.txt). Pomija katalogi, .py, usunięte."""
    out = []
    for p in paths:
        if not p:
            continue
        if is_prose(p) and os.path.isfile(p):
            out.append(p)
    return out


def changed_prose_files(base, head):
    """
    Zwróć listę zmienionych plików prozy względem bazy.

    Diff symetryczny od merge-base (`base...head`, trzy kropki) — kanon recenzji PR:
    nie flaguje zmian, które weszły do bazy po rozejściu gałęzi.
    --diff-filter=d: pomija usunięte (nie ma czego lintować).
    Diff liczymy w katalogu roboczym procesu (CWD) — w CI to checkout repo, w self-teście
    to tymczasowe repo. Korzeń repo bierzemy z `git rev-parse --show-toplevel`, bo ścieżki
    z `git diff` są względem korzenia; rozwijamy je do bezwzględnych i filtrujemy do prozy.
    """
    rng = f"{base}...{head}"
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
        if top.returncode != 0:
            print("[ERROR] Bieżący katalog nie jest repozytorium git — bramka CI nie policzy "
                  "zmienionych plików.", file=sys.stderr)
            if top.stderr.strip():
                print(top.stderr.rstrip(), file=sys.stderr)
            sys.exit(2)
        git_root = top.stdout.strip()

        proc = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=d", rng],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        # Brak gita w środowisku — błąd środowiska, nie cisza.
        print("[ERROR] Brak gita w PATH — bramka CI nie policzy zmienionych plików.",
              file=sys.stderr)
        sys.exit(2)

    if proc.returncode != 0:
        print(f"[ERROR] `git diff {rng}` zwrócił kod {proc.returncode}. "
              f"Czy baza '{base}' i head '{head}' są dostępne (fetch-depth: 0)?",
              file=sys.stderr)
        if proc.stderr.strip():
            print(proc.stderr.rstrip(), file=sys.stderr)
        sys.exit(2)

    rel_paths = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    abs_paths = [os.path.join(git_root, p) for p in rel_paths]
    return filter_prose(abs_paths)


def run_linter(files, lang, profile, dict_path):
    """Woła ai_linter.py jako podproces na podanych plikach. Propaguje jego exit code."""
    cmd = [sys.executable, LINTER, "--lang", lang]
    if profile:
        cmd += ["--profile", profile]
    if dict_path:
        cmd += ["--dict", dict_path]
    cmd += files
    proc = subprocess.run(cmd, capture_output=True, text=True)
    # Manifest lintera na stdout — do logu CI.
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Bramka jakości CI na merge request (F2): pełny werdykt lintera "
                    "na zmienionych plikach prozy.",
        epilog="Exit 0 = brak prozy lub wszystkie PASS; 1 = którykolwiek FAIL/FAIL-HARD; "
               "2 = błąd reguł/konfiguracji lintera lub błąd git/środowiska.",
    )
    parser.add_argument(
        "paths", nargs="*", metavar="PLIK",
        help="Jawne ścieżki plików prozy do bramki (tryb ręczny / self-test).",
    )
    parser.add_argument(
        "--changed", action="store_true",
        help="Tryb CI: lintuj pliki prozy zmienione względem bazy (wymaga --base).",
    )
    parser.add_argument(
        "--base", default=None, metavar="REF",
        help="Ref bazy PR do diffa (np. origin/main). Wymagane przy --changed.",
    )
    parser.add_argument(
        "--head", default="HEAD", metavar="REF",
        help="Ref szczytu gałęzi PR (domyślnie HEAD).",
    )
    parser.add_argument("--lang", default="both", choices=["pl", "en", "both"],
                        help="Język markerów przekazany do lintera (domyślnie both).")
    parser.add_argument("--profile", default=None,
                        help="Profil progów przekazany do lintera (opcjonalnie).")
    parser.add_argument("--dict", default=None, dest="dict_path",
                        help="Słownik domenowy przekazany do lintera (opcjonalnie).")
    args = parser.parse_args()

    if args.changed:
        if not args.base:
            print("[ERROR] Tryb --changed wymaga --base <ref> (np. origin/main).",
                  file=sys.stderr)
            sys.exit(2)
        files = changed_prose_files(args.base, args.head)
        scope = f"zmienione pliki prozy ({args.base}...{args.head})"
    else:
        files = filter_prose(args.paths)
        scope = "jawne pliki prozy"

    if not files:
        # Brak prozy do sprawdzenia → zielony check, NIE błąd.
        print(f"[ci_gate] Brak plików prozy w zakresie ({scope}). Bramka przepuszcza (exit 0).")
        sys.exit(0)

    print(f"[ci_gate] Bramka jakości na {len(files)} plik(ach) prozy ({scope}):")
    for f in files:
        print(f"  - {os.path.relpath(f, REPO_ROOT)}")
    print()

    rc = run_linter(files, args.lang, args.profile, args.dict_path)

    print()
    if rc == 0:
        print("[ci_gate] WERDYKT: wszystkie zmienione pliki prozy PASS. Bramka zielona (exit 0).")
    elif rc == 1:
        print("[ci_gate] WERDYKT: którykolwiek plik FAIL/FAIL-HARD (blokery LUB gęstość ponad próg). "
              "Bramka czerwona (exit 1). Szczegóły w manifeście wyżej, kolumna WERDYKT.")
    else:
        print(f"[ci_gate] BŁĄD lintera/reguł (exit {rc}). Bramka czerwona — to bramka jakości, "
              f"błąd konfiguracji nie może zazielenić checka.")
    sys.exit(rc)


if __name__ == "__main__":
    main()
