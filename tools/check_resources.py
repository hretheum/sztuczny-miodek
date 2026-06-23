#!/usr/bin/env python3
"""
check_resources.py — gate centralnego dostępu do danych pakietu (KAN-226). ZERO-DEP (stdlib).

Warunek wstępny pakietyzacji (wheel/uvx): wszystkie pliki danych READ-ONLY narzędzia
(rules.json, config.json) wczytywane są przez JEDEN punkt — moduł `resources` — zamiast
inline `os.path.join(dirname(__file__), ...)` rozsianego po modułach. To miejsce przełączymy
na importlib.resources w KAN-227, a reszta kodu nie drgnie.

Pilnuje, by:
  1. resources.packaged_data_path(name) zwracał ścieżkę bezwzględną do ISTNIEJĄCEGO pliku,
     niezależnie od bieżącego katalogu (linter bywa wołany z dowolnego miejsca),
  2. resources.load_packaged_text(name) zwracał treść parsowalną (rules=lista, config=dict),
  3. PODŁĄCZENIE było realne: ai_linter.RULES_PATH i config.CONFIG_PATH wskazują DOKŁADNIE
     to, co resources.packaged_data_path(...) — inaczej refaktor jest pozorny,
  4. nieznany plik danych kończył czytelnym błędem (nie cichym pustym wynikiem).

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import json
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from miodek import resources  # noqa: E402
from miodek import ai_linter  # noqa: E402
from miodek import config  # noqa: E402


def main():
    fails = []

    # 1. ścieżka bezwzględna do istniejącego pliku, niezależna od cwd
    cwd0 = os.getcwd()
    try:
        os.chdir("/")  # celowo inny katalog niż repo
        for name in ("rules.json", "config.json"):
            p = resources.packaged_data_path(name)
            if not os.path.isabs(p):
                fails.append(f"packaged_data_path({name!r}) nie jest bezwzględna: {p}")
            if not os.path.isfile(p):
                fails.append(f"packaged_data_path({name!r}) nie wskazuje pliku: {p}")
    finally:
        os.chdir(cwd0)

    # 2. treść parsowalna i sensowna
    try:
        rules = json.loads(resources.load_packaged_text("rules.json"))
        if not isinstance(rules, list) or not rules:
            fails.append("load_packaged_text('rules.json') nie daje niepustej listy reguł")
    except Exception as e:
        fails.append(f"load_packaged_text('rules.json') rzuca: {e}")
    try:
        cfg = json.loads(resources.load_packaged_text("config.json"))
        if not isinstance(cfg, dict) or "profiles" not in cfg:
            fails.append("load_packaged_text('config.json') nie daje dict z 'profiles'")
    except Exception as e:
        fails.append(f"load_packaged_text('config.json') rzuca: {e}")

    # 3. realne podłączenie — moduły biorą ścieżkę z resources, nie z własnego inline
    if os.path.realpath(ai_linter.RULES_PATH) != os.path.realpath(resources.packaged_data_path("rules.json")):
        fails.append(f"ai_linter.RULES_PATH != resources.packaged_data_path('rules.json') "
                     f"({ai_linter.RULES_PATH} vs {resources.packaged_data_path('rules.json')})")
    if os.path.realpath(config.CONFIG_PATH) != os.path.realpath(resources.packaged_data_path("config.json")):
        fails.append(f"config.CONFIG_PATH != resources.packaged_data_path('config.json') "
                     f"({config.CONFIG_PATH} vs {resources.packaged_data_path('config.json')})")

    # 4. nieznany plik → czytelny błąd, nie cisza
    try:
        resources.load_packaged_text("nie-istnieje-zaden-taki-plik.json")
        fails.append("load_packaged_text na nieznanym pliku NIE rzuca (cichy pusty wynik)")
    except FileNotFoundError:
        pass  # oczekiwane
    except Exception:
        pass  # dowolny twardy błąd też akceptowalny — byle nie cisza

    # 5. flaga --rules ma PIERWSZEŃSTWO nad domyślną z pakietu — dowód, że centralizacja
    #    domyślnej ścieżki nie zabrała wczytywania reguł z dysku wskazanego przez użytkownika.
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump([{"id": "X-TEST-ONLY", "lang": "pl", "klasa": "review",
                        "pattern": "x", "opis": "marker testowy"}], tmp)
            tmp_path = tmp.name
        defs = ai_linter.load_marker_defs(tmp_path)
        if len(defs) != 1 or defs[0][0] != "X-TEST-ONLY":
            fails.append(f"load_marker_defs(path) nie honoruje ścieżki z dysku — --rules bez "
                         f"pierwszeństwa (dostałem {len(defs)} reguł, oczekiwano 1 testowej)")
    except SystemExit as e:
        fails.append(f"load_marker_defs(path) wywrócił się na poprawnym pliku reguł (exit {e.code})")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if fails:
        print("FAIL check_resources:", file=sys.stderr)
        for f in fails:
            print("  -", f, file=sys.stderr)
        sys.exit(1)
    print("OK   resources: centralny dostęp do danych pakietu (path bezwzględny, treść parsowalna, "
          "ai_linter/config podłączone, nieznany plik = błąd). Gotowe pod importlib.resources (KAN-227).")


if __name__ == "__main__":
    main()
