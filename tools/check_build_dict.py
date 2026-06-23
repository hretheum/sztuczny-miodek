#!/usr/bin/env python3
"""
check_build_dict.py — gate narzędzia build_dict (D3 / KAN-197). ZERO-DEP (stdlib).

Weryfikuje zasadę „częstość proponuje, kanon wetuje, człowiek zatwierdza" na minimalnym korpusie:
  1. częstość proponuje: termin domenowy (np. „platform") trafia do review,
  2. kanon wetuje: AI-tell (np. „robust") NIE trafia do review, trafia do _vetoed_by_canon,
  3. człowiek zatwierdza: allow jest PUSTE w szkicu,
  4. filtr słów ogólnych: termin z wordlist nie trafia do review,
  5. szkic jest wczytywalny przez D2 (dictionary.load_dictionary) — spójność formatów.

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
import build_dict   # noqa: E402
from miodek import dictionary   # noqa: E402


def main():
    fails = []
    with tempfile.TemporaryDirectory() as d:
        # korpus: termin domenowy „platform" (×3, 2 pliki) + AI-tell „robust" + słowo ogólne „oraz"
        for i, body in enumerate([
            "Nasza platform jest szybka. Robust solution. Robust znowu oraz oraz.",
            "Platform rośnie. Inna platform też. Robust raz jeszcze. Oraz oraz oraz.",
        ]):
            open(os.path.join(d, f"f{i}.txt"), "w", encoding="utf-8").write(body)
        wl = os.path.join(d, "wl.txt")
        open(wl, "w", encoding="utf-8").write("oraz\n")

        draft = build_dict.build([d], min_count=2, min_files=1, wordlist_path=wl, projekt="gate")

        # 1. częstość proponuje
        if "platform" not in draft["review"]:
            fails.append("'platform' (termin domenowy) powinien być w review")
        # 2. kanon wetuje
        veto = {v["termin"] for v in draft["_vetoed_by_canon"]}
        if "robust" not in veto:
            fails.append("'robust' (AI-tell) powinien być zawetowany przez kanon")
        if "robust" in draft["review"]:
            fails.append("'robust' NIE powinien trafić do review (kanon wetuje)")
        # 3. człowiek zatwierdza — allow puste
        if draft["allow"] != []:
            fails.append("allow powinno być PUSTE w szkicu (człowiek zatwierdza)")
        # 4. filtr słów ogólnych
        if "oraz" in draft["review"]:
            fails.append("'oraz' (słowo ogólne z wordlist) nie powinno trafić do review")

        # 5. szkic wczytywalny przez D2
        import json
        p = os.path.join(d, "draft.json")
        json.dump(draft, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        try:
            loaded = dictionary.load_dictionary(p)
            if loaded is None:
                fails.append("szkic D3 nie wczytuje się przez D2 load_dictionary")
        except ValueError as e:
            fails.append(f"szkic D3 niespójny z formatem D2: {e}")

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)
    print("OK   build_dict: częstość proponuje (review), kanon wetuje (robust), allow puste, "
          "wordlist odsiewa, szkic spójny z D2.")


if __name__ == "__main__":
    main()
