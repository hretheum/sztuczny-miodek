#!/usr/bin/env python3
"""
check_routing.py — gate routingu silnika osądu Stage 2 (G3). ZERO-DEP (stdlib), OFFLINE.

RoutingJudgeEngine owija DWA silniki (primary lekki na masę, appellate mocny sędzia apelacyjny).
Cały test stoi na ATRAPACH JudgeEngine o ustalonych werdyktach — żadnej realnej sieci, żadnego
modelu, żadnego transportu HTTP. Liczymy też wywołania appellate, by udowodnić, że na łatwym
segmencie sędzia apelacyjny NIE jest dotykany (sedno lejka kosztowego).

Weryfikuje:
  1. primary "pass" na łatwym segmencie (0-1 trafień) → appellate NIE wołany; werdykt = primary.
  2. primary "rewrite" → eskalacja; appellate "pass" nadpisuje → finał "pass" (apelacja tnie
     fałszywy alarm — istota sędziego apelacyjnego).
  3. segment "trudny" (hits >= hard_hits_threshold) mimo primary "pass" → eskalacja; werdykt appellate.
  4. .name == "routing:<primary>-><appellate>".
  5. .rewrite deleguje do silnika, który wydałby ostateczny werdykt (atrapy z rozróżnialnym zwrotem).
  6. build_engine_from_config: routing (config w tmp) → RoutingJudgeEngine o oczekiwanym .name;
     zagnieżdżony engine:"routing" → ValueError; brak primary/appellate → ValueError.

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import json
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from miodek import config       # noqa: E402
from miodek import runner       # noqa: E402
from miodek.engines import (  # noqa: E402
    JudgeEngine, Judgement, ReviewSegment, RoutingJudgeEngine, StubJudgeEngine,
)


class _FixedEngine(JudgeEngine):
    """Atrapa silnika o USTALONYM werdykcie, licząca wywołania judge/rewrite. Bez sieci, bez modelu.

    `rewrite` zwraca rozróżnialny znacznik ("<name>:REWRITE"), by udowodnić, do którego silnika
    routing oddelegował przepisanie."""

    def __init__(self, name, verdict):
        self.name = name
        self._verdict = verdict
        self.judge_calls = 0
        self.rewrite_calls = 0

    def judge(self, segment):
        self.judge_calls += 1
        return Judgement(verdict=self._verdict, notes=f"{self.name} mówi {self._verdict}",
                         engine=self.name)

    def rewrite(self, segment, judgement):
        self.rewrite_calls += 1
        return f"{self.name}:REWRITE"


def _seg(n_hits):
    """Segment z `n_hits` trafieniami review (treść nieistotna dla atrap)."""
    hits = [{"id": f"PL-RHET-{i}", "match": "x", "klasa": "review", "line": 1} for i in range(n_hits)]
    return ReviewSegment(file="doc.txt", seg_index=0, line=1, text="akapit", hits=hits)


def main():
    fails = []

    # --- 1: primary pass na łatwym segmencie → appellate NIE wołany ---
    prim = _FixedEngine("primary", "pass")
    appe = _FixedEngine("appellate", "pass")
    routing = RoutingJudgeEngine(prim, appe, escalate_on_rewrite=True, hard_hits_threshold=2)
    j = routing.judge(_seg(1))  # 1 trafienie < próg 2 → łatwy
    if j.verdict != "pass":
        fails.append(f"1) łatwy primary pass: oczekiwano 'pass', jest {j.verdict!r}")
    if appe.judge_calls != 0:
        fails.append(f"1) appellate NIE powinien być wołany na łatwym segmencie, judge_calls={appe.judge_calls}")
    if j.engine != "primary":
        fails.append(f"1) werdykt łatwy: engine powinien być primary, jest {j.engine!r}")

    # --- 2: primary rewrite → eskalacja; appellate pass nadpisuje → finał pass ---
    prim2 = _FixedEngine("primary", "rewrite")
    appe2 = _FixedEngine("appellate", "pass")
    routing2 = RoutingJudgeEngine(prim2, appe2, escalate_on_rewrite=True, hard_hits_threshold=None)
    j2 = routing2.judge(_seg(1))
    if j2.verdict != "pass":
        fails.append(f"2) eskalacja rewrite→apelacja: oczekiwano finał 'pass', jest {j2.verdict!r}")
    if appe2.judge_calls != 1:
        fails.append(f"2) appellate POWINIEN być wołany przy primary rewrite, judge_calls={appe2.judge_calls}")
    if j2.engine != "appellate":
        fails.append(f"2) eskalacja: engine finalny powinien być appellate, jest {j2.engine!r}")
    if "primary rewrite" not in j2.notes or "appellate pass" not in j2.notes:
        fails.append(f"2) notatki powinny łączyć obie opinie, są {j2.notes!r}")

    # --- 3: segment trudny (hits >= próg) mimo primary pass → eskalacja, werdykt appellate ---
    prim3 = _FixedEngine("primary", "pass")
    appe3 = _FixedEngine("appellate", "rewrite")
    routing3 = RoutingJudgeEngine(prim3, appe3, escalate_on_rewrite=True, hard_hits_threshold=2)
    j3 = routing3.judge(_seg(3))  # 3 trafienia >= próg 2 → trudny
    if j3.verdict != "rewrite":
        fails.append(f"3) trudny segment: oczekiwano werdykt appellate 'rewrite', jest {j3.verdict!r}")
    if appe3.judge_calls != 1:
        fails.append(f"3) appellate POWINIEN być wołany na trudnym segmencie, judge_calls={appe3.judge_calls}")

    # --- 4: .name odzwierciedla skład ---
    if routing.name != "routing:primary->appellate":
        fails.append(f"4) .name: oczekiwano 'routing:primary->appellate', jest {routing.name!r}")

    # --- 5: .rewrite deleguje do właściwego silnika ---
    # 5a: łatwy (primary pass, brak eskalacji) → primary.rewrite
    prim5 = _FixedEngine("primary", "pass")
    appe5 = _FixedEngine("appellate", "pass")
    r5 = RoutingJudgeEngine(prim5, appe5, escalate_on_rewrite=True, hard_hits_threshold=2)
    out5 = r5.rewrite(_seg(1), Judgement("rewrite", "x", "routing"))
    if out5 != "primary:REWRITE":
        fails.append(f"5a) rewrite łatwy powinien iść do primary, jest {out5!r}")
    if appe5.rewrite_calls != 0:
        fails.append(f"5a) appellate.rewrite NIE powinien być wołany na łatwym, calls={appe5.rewrite_calls}")
    # 5b: primary rewrite → eskalacja → appellate.rewrite
    prim5b = _FixedEngine("primary", "rewrite")
    appe5b = _FixedEngine("appellate", "pass")
    r5b = RoutingJudgeEngine(prim5b, appe5b, escalate_on_rewrite=True, hard_hits_threshold=None)
    out5b = r5b.rewrite(_seg(1), Judgement("rewrite", "x", "routing"))
    if out5b != "appellate:REWRITE":
        fails.append(f"5b) rewrite po eskalacji powinien iść do appellate, jest {out5b!r}")

    # --- konstruktor: walidacja hard_hits_threshold i braku silników ---
    try:
        RoutingJudgeEngine(prim, appe, hard_hits_threshold=0)
        fails.append("konstruktor: hard_hits_threshold=0 powinien rzucić ValueError")
    except ValueError:
        pass
    try:
        RoutingJudgeEngine(None, appe)
        fails.append("konstruktor: primary=None powinien rzucić ValueError")
    except ValueError:
        pass

    # --- 6: build_engine_from_config (routing z configu w tmp) ---
    with tempfile.TemporaryDirectory() as tmp:
        p_ok = os.path.join(tmp, "routing.json")
        with open(p_ok, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"engine": "routing", "routing": {
                "escalate_on_rewrite": True, "hard_hits_threshold": 2,
                "primary": {"engine": "stub"},
                "appellate": {"engine": "stub"},
            }}}, f)
        eng = runner.build_engine_from_config(config_path=p_ok)
        if not isinstance(eng, RoutingJudgeEngine):
            fails.append(f"6) build routing → oczekiwano RoutingJudgeEngine, jest {type(eng).__name__}")
        elif eng.name != "routing:stub->stub":
            fails.append(f"6) build routing .name: oczekiwano 'routing:stub->stub', jest {eng.name!r}")
        elif not (isinstance(eng.primary, StubJudgeEngine) and isinstance(eng.appellate, StubJudgeEngine)):
            fails.append("6) build routing: primary/appellate powinny być StubJudgeEngine")
        elif eng.hard_hits_threshold != 2 or eng.escalate_on_rewrite is not True:
            fails.append(f"6) build routing: polityka nie przeniesiona z configu "
                         f"(threshold={eng.hard_hits_threshold}, on_rewrite={eng.escalate_on_rewrite})")

        # zagnieżdżony routing → ValueError (przez config.load_stage2)
        p_nest = os.path.join(tmp, "nest.json")
        with open(p_nest, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"engine": "routing", "routing": {
                "primary": {"engine": "routing"}, "appellate": {"engine": "stub"}}}}, f)
        try:
            runner.build_engine_from_config(config_path=p_nest)
            fails.append("6) zagnieżdżony routing powinien rzucić ValueError")
        except ValueError:
            pass

        # brak appellate → ValueError
        p_miss = os.path.join(tmp, "miss.json")
        with open(p_miss, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"engine": "routing", "routing": {
                "primary": {"engine": "stub"}}}}, f)
        try:
            runner.build_engine_from_config(config_path=p_miss)
            fails.append("6) brak appellate powinien rzucić ValueError")
        except ValueError:
            pass

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)

    print("OK   routing Stage 2 (G3): lejek kosztowy działa — łatwy segment ufa primary (appellate "
          "nie dotknięty), rewrite/trudny eskaluje do apelacji, werdykt appellate ostateczny, "
          ".name odzwierciedla skład, .rewrite deleguje do właściwego silnika, fabryka z configu "
          "(rekurencja + zakaz zagnieżdżenia + walidacja). ZERO sieci, ZERO modelu.")


if __name__ == "__main__":
    main()
