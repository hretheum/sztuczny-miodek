#!/usr/bin/env python3
"""
check_publish_gate.py — gate bramki przed publikacją (F3). ZERO-DEP (stdlib). OFFLINE.

Pilnuje, by publish_gate.py:
  (a) jawny plik z twardym blokerem (baseline_pl_raport.md), bez --stage2 → exit 1,
  (b) jawny plik czysty (control_pl_clean.md), bez --stage2 → exit 0,
  (c) RÓŻNICA WOBEC F1 (jak F2): sama gęstość (triad_eval.md, FAIL, blockers==0),
      bez --stage2 → exit 1 (Stage 1 pełnym werdyktem łapie gęstość),
  (d) mieszanka (czysty + bloker), bez --stage2 → exit 1,
  (e) brak plików prozy (.py albo pusta lista) → exit 0 (nie wywraca się),
  (f) --stage2 ze STUB (config domyślny = stub, OFFLINE) na pliku CZYSTYM bez trafień review
      → Stage 2 osądza 0 segmentów → gate PASS → exit 0 (włączony Stage 2 NIE sięga sieci),
  (g) RÓŻNICA WOBEC F2 (najsurowsza): --stage2 ze STUB na pliku, który Stage 1 PRZECHODZI,
      ale ma trafienie review (sentence_eval.md: PASS + PL-RHET) → stub wydaje „rewrite”
      → gate FAIL → exit 1. To dowodzi, że F3 dokłada model i jest surowsza niż F2.
  (h) --stage2 z configiem, w którym stage2.engine=openai bez base_url/model → błąd
      konfiguracji silnika → exit 2 (świadomy błąd, nadal ZERO sieci),
  (i) workflow F2 NIE jest tu sprawdzany; sprawdzamy obecność sekcji F3 w README
      (wiersz tabeli „przed publikacją (F3)” bez „jeszcze nie ma”).

Stage 2 w teście używa WYŁĄCZNIE atrapy (StubJudgeEngine) — żaden przypadek nie woła realnego
endpointu. Przypadki (f)/(g) idą domyślnym configiem repo (stage2.engine == "stub"); (h) używa
tymczasowego configu z openai bez kluczy, więc błąd zapada PRZED jakimkolwiek wywołaniem sieci.

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import json
import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# publish_gate to moduł pakietu (KAN-228) — wołany przez -m z PYTHONPATH=src.
_SRC = os.path.join(REPO_ROOT, "src")
_ENV = dict(os.environ)
_ENV["PYTHONPATH"] = _SRC + (os.pathsep + _ENV["PYTHONPATH"] if _ENV.get("PYTHONPATH") else "")
PUBLISH_GATE_CMD = [sys.executable, "-m", "miodek.publish_gate"]
TESTS_DIR = os.path.join(REPO_ROOT, "tests")
README = os.path.join(REPO_ROOT, "README.md")

BASELINE = os.path.join(TESTS_DIR, "baseline_pl_raport.md")   # twardy bloker → Stage 1 FAIL
CONTROL = os.path.join(TESTS_DIR, "control_pl_clean.md")      # czysty, 0 trafień review → PASS
DENSITY_ONLY = os.path.join(TESTS_DIR, "triad_eval.md")       # sama gęstość → Stage 1 FAIL
REVIEW_CLEAN = os.path.join(TESTS_DIR, "sentence_eval.md")    # Stage 1 PASS + trafienie review


def rc(*args):
    """Uruchom publish_gate.py z podanymi argumentami, zwróć kod wyjścia."""
    return subprocess.run(
        [*PUBLISH_GATE_CMD, *args], capture_output=True, text=True, env=_ENV
    ).returncode


def main():
    fails = []

    # (a) twardy bloker, bez Stage 2 → exit 1
    if rc(BASELINE) != 1:
        fails.append("(a) baseline_pl_raport.md (twardy bloker) bez --stage2 powinien dać exit 1.")

    # (b) czysty, bez Stage 2 → exit 0
    if rc(CONTROL) != 0:
        fails.append("(b) control_pl_clean.md (czysty) bez --stage2 powinien dać exit 0.")

    # (c) sama gęstość → exit 1 (jak F2, inaczej niż F1)
    if rc(DENSITY_ONLY) != 1:
        fails.append("(c) triad_eval.md (FAIL z samej gęstości, blockers==0) powinien dać exit 1 "
                     "— Stage 1 łapie gęstość (pełny werdykt), inaczej niż F1.")

    # (d) mieszanka czysty + bloker → exit 1
    if rc(CONTROL, BASELINE) != 1:
        fails.append("(d) mieszanka (czysty + bloker) powinna dać exit 1.")

    # (e1) ścieżka nie-proza (.py) → exit 0
    if rc(os.path.abspath(__file__)) != 0:
        fails.append("(e) jawna ścieżka .py (nie-proza) powinna dać exit 0 (brak prozy = przejście).")
    # (e2) pusta lista → exit 0
    if rc() != 0:
        fails.append("(e) brak argumentów (zero plików prozy) powinien dać exit 0.")

    # (f) --stage2 stub na czystym pliku (0 trafień review) → gate PASS → exit 0, ZERO sieci
    if rc("--stage2", CONTROL) != 0:
        fails.append("(f) --stage2 (stub) na czystym control_pl_clean.md powinien dać exit 0 "
                     "(Stage 2 osądza 0 segmentów, gate PASS, bez sieci).")

    # (g) NAJSUROWSZA: --stage2 stub na pliku Stage1-PASS z trafieniem review → rewrite → exit 1.
    #     Potwierdza, że F3 dokłada model i jest surowsza niż F2 (która ten plik przepuszcza).
    if rc("--stage2", REVIEW_CLEAN) != 1:
        fails.append("(g) --stage2 (stub) na sentence_eval.md (Stage 1 PASS + trafienie review "
                     "PL-RHET) powinien dać exit 1 — stub wydaje 'rewrite', gate FAIL. To dowód, "
                     "że F3 jest surowsza niż F2 (dokłada osąd Stage 2).")

    # (g-kontrola) ten sam plik BEZ --stage2 → exit 0 (Stage 1 sam go przepuszcza).
    #     Bez tego (g) nie dowodziłoby, że to Stage 2 zamknął publikację.
    if rc(REVIEW_CLEAN) != 0:
        fails.append("(g-kontrola) sentence_eval.md BEZ --stage2 powinien dać exit 0 "
                     "(Stage 1 PASS) — różnica musi pochodzić z włączonego Stage 2.")

    # (h) --stage2 z configiem openai bez base_url/model → błąd konfiguracji → exit 2 (zero sieci).
    tmp = tempfile.mkdtemp(prefix="publish_gate_test_")
    bad_cfg = os.path.join(tmp, "badcfg.json")
    try:
        with open(bad_cfg, "w", encoding="utf-8") as fh:
            json.dump({
                "active_profile": "default",
                "profiles": {"default": {"thresholds": {
                    "emdash_per_paragraph": 3, "bold_per_paragraph": 4,
                    "connector_overload_per_file": 3, "en_anti_series_per_file": 2,
                    "pl_anti_series_per_file": 3, "density_per_500_words": 8,
                }}},
                "stage2": {"engine": "openai", "openai": {}},
            }, fh)
        if rc("--stage2", "--config", bad_cfg, CONTROL) != 2:
            fails.append("(h) --stage2 z config openai bez base_url/model powinien dać exit 2 "
                         "(błąd konfiguracji silnika, zero sieci).")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    # (i) README ma sekcję F3 i nie mówi już „jeszcze nie ma" w wierszu F3.
    if not os.path.isfile(README):
        fails.append("(i) brak README.md.")
    else:
        with open(README, encoding="utf-8") as fh:
            readme = fh.read()
        if "Bramka przed publikacją" not in readme:
            fails.append("(i) README nie zawiera sekcji 'Bramka przed publikacją'.")
        if "publish_gate.py" not in readme:
            fails.append("(i) README nie wspomina sterownika 'publish_gate.py'.")
        if "jeszcze nie ma" in readme:
            fails.append("(i) README wciąż mówi 'jeszcze nie ma' (wiersz F3 nieaktualny).")

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)
    print("OK   bramka przed publikacją (F3): Stage 1 pełnym werdyktem (gęstość łapana), "
          "Stage 2 opcjonalny ze stubem (offline) surowszy niż F2 (rewrite→FAIL), brak prozy = "
          "zielono, błąd silnika = exit 2; README ma sekcję F3.")


if __name__ == "__main__":
    main()
