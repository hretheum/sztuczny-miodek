#!/usr/bin/env python3
"""
check_config.py — gate spójności config.json (D1 / KAN-195). ZERO-DEP (stdlib).

Pilnuje, by:
  1. profil „default" w config.json == config.DEFAULT_THRESHOLDS (zero zmiany zachowania —
     gdyby ktoś zmienił default w pliku, zachowanie lintera by się rozjechało po cichu),
  2. każdy profil miał PEŁNY zestaw progów o poprawnych wartościach (load_thresholds nie rzuca),
  3. active_profile wskazywał istniejący profil.

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
import config  # noqa: E402

CONFIG_PATH = os.path.join(REPO_ROOT, "config.json")


def main():
    fails = []

    if not os.path.exists(CONFIG_PATH):
        print(f"[ERROR] brak {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)

    cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))
    profiles = cfg.get("profiles", {})

    # 1. default == DEFAULT_THRESHOLDS
    try:
        default_th = config.load_thresholds("default")
        if default_th != config.DEFAULT_THRESHOLDS:
            fails.append(f"profil 'default' != config.DEFAULT_THRESHOLDS: {default_th} vs {config.DEFAULT_THRESHOLDS}")
    except ValueError as e:
        fails.append(f"profil 'default' nie ładuje się: {e}")

    # 2. każdy profil ładuje się z pełnym, poprawnym zestawem progów
    for name in profiles:
        try:
            config.load_thresholds(name)
        except ValueError as e:
            fails.append(f"profil {name!r}: {e}")

    # 3. active_profile istnieje
    active = cfg.get("active_profile", "default")
    if active not in profiles:
        fails.append(f"active_profile {active!r} nie istnieje (dostępne: {sorted(profiles)})")

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)
    print(f"OK   config.json spójny: {len(profiles)} profili, default == DEFAULT_THRESHOLDS, "
          f"active_profile={active!r}.")


if __name__ == "__main__":
    main()
