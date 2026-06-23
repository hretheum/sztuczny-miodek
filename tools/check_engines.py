#!/usr/bin/env python3
"""
check_engines.py — gate realnych adapterów silnika Stage 2 (KAN-218). ZERO-DEP (stdlib).

OFFLINE: cała warstwa HTTP jest wstrzykiwana atrapą (closure zwracająca ustalone ciało JSON
modelu). _default_http_transport NIGDY nie jest wołany — żadnych realnych wywołań sieci.

Weryfikuje:
  1. OpenAICompatEngine: JSON {"verdict":"pass"} → Judgement.verdict == "pass", engine == "openai:<model>",
  2. OpenAICompatEngine: JSON {"verdict":"rewrite"} → "rewrite",
  3. OpenAICompatEngine: odpowiedź niejednoznaczna (brak JSON, brak słowa kluczowego) → "rewrite" (fallback),
  4. OpenAICompatEngine: pierwsza linia "REWRITE\n..." (bez JSON) → "rewrite",
  5. OllamaEngine: JSON {"verdict":"pass"} w kopercie /api/chat → "pass", engine == "ollama:<model>",
  6. OllamaEngine: uszkodzona/pusta koperta → "" → fallback "rewrite",
  7. transport dostaje właściwy URL (/chat/completions, /api/chat) i body z segment.text + ID trafień,
  8. Judgement.engine == engine.name,
  9. config.load_stage2: brak sekcji → {"engine":"stub"}; openai bez base_url → ValueError; engine:"foo" → ValueError,
 10. runner.build_engine_from_config: stub → StubJudgeEngine; openai (config w tmp) → OpenAICompatEngine o .name=="openai:<model>".

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import json
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config       # noqa: E402
import runner       # noqa: E402
from engines import (  # noqa: E402
    OpenAICompatEngine, OllamaEngine, StubJudgeEngine, ReviewSegment,
    parse_model_reply, build_judge_prompt,
)

# Segment testowy: akapit z dwoma trafieniami review (ID + match w prompcie).
SEG = ReviewSegment(
    file="doc.txt", seg_index=0, line=1,
    text="To jest szybki, prosty i skuteczny akapit testowy.",
    hits=[
        {"id": "PL-RHET", "match": "szybki, prosty i skuteczny", "klasa": "review", "line": 1},
        {"id": "EN-TRIAD", "match": "fast, simple", "klasa": "review", "line": 1},
    ],
)


def _openai_envelope(content: str) -> str:
    """Koperta OpenAI Chat Completions z danym content (jak OpenRouter / vLLM)."""
    return json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]})


def _ollama_envelope(content: str) -> str:
    """Koperta Ollamy /api/chat (stream=false) z danym content."""
    return json.dumps({"message": {"role": "assistant", "content": content}})


def _capturing_transport(captured: dict, reply: str):
    """Atrapa HTTP: zapisuje url/data/headers do `captured` i zwraca ustalone `reply`.

    To jedyna warstwa sieci w teście — _default_http_transport nie jest wołany."""
    def transport(url, *, data, headers, timeout):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        captured["timeout"] = timeout
        return reply
    return transport


def main():
    fails = []

    # --- 1: OpenAI JSON pass ---
    cap = {}
    eng = OpenAICompatEngine(
        base_url="https://example.test/api/v1", model="m1",
        transport=_capturing_transport(cap, _openai_envelope('{"verdict":"pass","notes":"czysto"}')),
    )
    j = eng.judge(SEG)
    if j.verdict != "pass":
        fails.append(f"OpenAI JSON pass: oczekiwano 'pass', jest {j.verdict!r}")
    if j.engine != "openai:m1":
        fails.append(f"OpenAI engine.name: oczekiwano 'openai:m1', jest {j.engine!r}")
    if j.notes != "czysto":
        fails.append(f"OpenAI notes z JSON: oczekiwano 'czysto', jest {j.notes!r}")
    # 7: właściwy URL + body z segment.text i ID trafień
    if not cap.get("url", "").endswith("/chat/completions"):
        fails.append(f"OpenAI URL: oczekiwano .../chat/completions, jest {cap.get('url')!r}")
    body = json.loads(cap["data"].decode("utf-8"))
    user_msg = body["messages"][1]["content"]
    if SEG.text not in user_msg or "PL-RHET" not in user_msg or "EN-TRIAD" not in user_msg:
        fails.append("OpenAI body: prompt nie zawiera segment.text lub ID trafień")
    if body.get("model") != "m1":
        fails.append(f"OpenAI body.model: oczekiwano 'm1', jest {body.get('model')!r}")

    # --- 2: OpenAI JSON rewrite ---
    eng2 = OpenAICompatEngine(
        base_url="https://example.test/api/v1", model="m1",
        transport=_capturing_transport({}, _openai_envelope('{"verdict":"rewrite","notes":"triada"}')),
    )
    if eng2.judge(SEG).verdict != "rewrite":
        fails.append("OpenAI JSON rewrite: oczekiwano 'rewrite'")

    # --- 3: OpenAI fallback (niejednoznaczne) ---
    eng3 = OpenAICompatEngine(
        base_url="https://example.test/api/v1", model="m1",
        transport=_capturing_transport({}, _openai_envelope("nie wiem, może?")),
    )
    j3 = eng3.judge(SEG)
    if j3.verdict != "rewrite":
        fails.append(f"OpenAI fallback: oczekiwano 'rewrite', jest {j3.verdict!r}")
    if "fail-safe" not in j3.notes:
        fails.append(f"OpenAI fallback notes: brak adnotacji eskalacji, jest {j3.notes!r}")

    # --- 4: OpenAI pierwsza linia REWRITE (bez JSON) ---
    eng4 = OpenAICompatEngine(
        base_url="https://example.test/api/v1", model="m1",
        transport=_capturing_transport({}, _openai_envelope("REWRITE\nbo antyteza")),
    )
    if eng4.judge(SEG).verdict != "rewrite":
        fails.append("OpenAI pierwsza linia REWRITE: oczekiwano 'rewrite'")

    # pierwsza linia PASS (bez JSON) → pass
    engP = OpenAICompatEngine(
        base_url="https://example.test/api/v1", model="m1",
        transport=_capturing_transport({}, _openai_envelope("PASS\nczysty akapit")),
    )
    if engP.judge(SEG).verdict != "pass":
        fails.append("OpenAI pierwsza linia PASS: oczekiwano 'pass'")

    # --- 5: Ollama JSON pass ---
    capo = {}
    engo = OllamaEngine(
        host="http://ollama.test:11434", model="bielik",
        transport=_capturing_transport(capo, _ollama_envelope('{"verdict":"pass","notes":"ok"}')),
    )
    jo = engo.judge(SEG)
    if jo.verdict != "pass":
        fails.append(f"Ollama JSON pass: oczekiwano 'pass', jest {jo.verdict!r}")
    if jo.engine != "ollama:bielik":
        fails.append(f"Ollama engine.name: oczekiwano 'ollama:bielik', jest {jo.engine!r}")
    if not capo.get("url", "").endswith("/api/chat"):
        fails.append(f"Ollama URL: oczekiwano .../api/chat, jest {capo.get('url')!r}")
    bodyo = json.loads(capo["data"].decode("utf-8"))
    if bodyo.get("stream") is not False:
        fails.append("Ollama body: stream powinien być False")
    if SEG.text not in bodyo["messages"][1]["content"]:
        fails.append("Ollama body: prompt nie zawiera segment.text")

    # Ollama JSON rewrite
    engor = OllamaEngine(
        host="http://ollama.test:11434", model="bielik",
        transport=_capturing_transport({}, _ollama_envelope('{"verdict":"rewrite","notes":"x"}')),
    )
    if engor.judge(SEG).verdict != "rewrite":
        fails.append("Ollama JSON rewrite: oczekiwano 'rewrite'")

    # --- 6: Ollama uszkodzona/pusta koperta → fallback rewrite ---
    engbad = OllamaEngine(
        host="http://ollama.test:11434", model="bielik",
        transport=_capturing_transport({}, "{}"),  # brak message → content "" → fallback
    )
    if engbad.judge(SEG).verdict != "rewrite":
        fails.append("Ollama pusta koperta: oczekiwano fallback 'rewrite'")
    engbad2 = OllamaEngine(
        host="http://ollama.test:11434", model="bielik",
        transport=_capturing_transport({}, "to nie jest JSON"),
    )
    if engbad2.judge(SEG).verdict != "rewrite":
        fails.append("Ollama nie-JSON koperta: oczekiwano fallback 'rewrite'")

    # --- parse_model_reply jednostkowo (determinizm parsera) ---
    if parse_model_reply('{"verdict":"pass","notes":"x"}')[0] != "pass":
        fails.append("parse_model_reply JSON pass rozjazd")
    if parse_model_reply("")[0] != "rewrite":
        fails.append("parse_model_reply pusty → powinien być 'rewrite'")
    if parse_model_reply("PASS oraz REWRITE w jednej linii")[0] != "rewrite":
        fails.append("parse_model_reply oba słowa → powinien być 'rewrite' (fallback)")

    # --- build_judge_prompt na pustym text (fallback nieczytelnego pliku) ---
    empty_seg = ReviewSegment(file="x", seg_index=0, line=1, text="",
                              hits=[{"id": "PL-RHET", "match": "abc"}])
    if "PL-RHET" not in build_judge_prompt(empty_seg):
        fails.append("build_judge_prompt: pusty text gubi listę trafień")

    # --- 9: config.load_stage2 ---
    with tempfile.TemporaryDirectory() as tmp:
        # brak sekcji stage2 → stub
        p_nostage2 = os.path.join(tmp, "c1.json")
        with open(p_nostage2, "w", encoding="utf-8") as f:
            json.dump({"profiles": {}, "economy": {}}, f)
        if config.load_stage2(p_nostage2) != {"engine": "stub"}:
            fails.append("load_stage2: brak sekcji stage2 → oczekiwano {'engine':'stub'}")

        # brak pliku → stub
        if config.load_stage2(os.path.join(tmp, "nie-ma.json")) != {"engine": "stub"}:
            fails.append("load_stage2: brak configu → oczekiwano {'engine':'stub'}")

        # openai bez base_url → ValueError
        p_bad = os.path.join(tmp, "c2.json")
        with open(p_bad, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"engine": "openai", "openai": {"model": "m"}}}, f)
        try:
            config.load_stage2(p_bad)
            fails.append("load_stage2: openai bez base_url powinno rzucić ValueError")
        except ValueError:
            pass

        # engine nieznany → ValueError
        p_foo = os.path.join(tmp, "c3.json")
        with open(p_foo, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"engine": "foo"}}, f)
        try:
            config.load_stage2(p_foo)
            fails.append("load_stage2: engine 'foo' powinno rzucić ValueError")
        except ValueError:
            pass

        # poprawny openai → zwraca dict z engine openai
        p_ok = os.path.join(tmp, "c4.json")
        with open(p_ok, "w", encoding="utf-8") as f:
            json.dump({"stage2": {"engine": "openai",
                                  "openai": {"base_url": "https://e.test/api/v1", "model": "mX"}}}, f)
        st = config.load_stage2(p_ok)
        if st.get("engine") != "openai":
            fails.append("load_stage2: poprawny openai nie zwrócił engine 'openai'")

        # --- 10: build_engine_from_config ---
        e_stub = runner.build_engine_from_config(config_path=p_nostage2)
        if not isinstance(e_stub, StubJudgeEngine):
            fails.append(f"build_engine_from_config: brak stage2 → oczekiwano StubJudgeEngine, jest {type(e_stub).__name__}")

        e_openai = runner.build_engine_from_config(config_path=p_ok)
        if not isinstance(e_openai, OpenAICompatEngine):
            fails.append(f"build_engine_from_config: openai → oczekiwano OpenAICompatEngine, jest {type(e_openai).__name__}")
        elif e_openai.name != "openai:mX":
            fails.append(f"build_engine_from_config: openai .name oczekiwano 'openai:mX', jest {e_openai.name!r}")

        # nadpisanie nazwą z CLI: name="stub" wymusza atrapę mimo configu openai
        e_forced = runner.build_engine_from_config(name="stub", config_path=p_ok)
        if not isinstance(e_forced, StubJudgeEngine):
            fails.append("build_engine_from_config: name='stub' powinno nadpisać engine z configu")

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)

    print("OK   adaptery Stage 2 (KAN-218): OpenAICompat + Ollama mapują JSON/PASS/REWRITE na "
          "Judgement, fallback niejednoznaczny → rewrite, engine==name, URL/body poprawne; "
          "load_stage2 (fallback stub + walidacja) i build_engine_from_config spójne. ZERO sieci.")


if __name__ == "__main__":
    main()
