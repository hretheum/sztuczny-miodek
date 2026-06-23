#!/usr/bin/env python3
"""
check_metrics.py — gate metryk z manifestu (E1: redukcja, E2: atrybucja). ZERO-DEP (stdlib).

Działa na zaszytym mini-manifeście i treści podanej W PAMIĘCI (wstrzyknięty file_reader) — bez I/O,
bez sieci, bez LLM.

E1 — weryfikuje fundamenty definicji redukcji:
  1. akapit z trafieniem klasy "review" jest liczony jako routed,
  2. akapit z samym trafieniem "block" NIE jest routed (block linter zamyka sam),
  3. akapit czysty NIE jest routed,
  4. routed_words = suma słów akapitów review (zgodność z definicją i formułą słów),
  5. inwariant: reduction_ratio + routed_ratio == 1.0,
  6. routed_ratio porównywalny z odniesieniem (tu liczony, nie zaszyty na sztywno),
  7. wariant awaryjny: plik nieczytelny z trafieniem review => fallback, cały plik jako routed.

E2 — weryfikuje atrybucję pracy:
  8.  per_rule sumuje się do total_hits == len(hits) (nic się nie gubi),
  9.  PL-RHYTHM (czysto proceduralny) klasyfikuje się jako warstwa "proceduralna",
  10. PL-SIGN (w MARKER_DEFS) klasyfikuje się jako "deklaratywna",
  11. ranking per_rule jest malejący wg liczby trafień,
  12. udziały (share) w per_rule sumują się do 1.0,
  13. atrybucja per silnik z wyniku runnera rozdziela werdykty rewrite/pass.

E4 — weryfikuje wskaźnik zdrowia ekonomii (economy_health):
  14. routed_ratio nad progiem => "ALARM",
  15. routed_ratio pod progiem => "OK",
  16. total_words < min_words   => "N/A" (alarm wstrzymany przy małej próbce),
  17. alarm_threshold w wyniku = próg podany na wejściu (czytamy ten, nie inny).

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from miodek import metrics  # noqa: E402


# --- Mini-dokument: 3 akapity rozdzielone pustą linią ---
# Akapit 1 (linie 1-1): trafienie review  -> routed
# Akapit 2 (linie 3-3): trafienie block    -> NIE routed
# Akapit 3 (linie 5-5): czysty             -> NIE routed
DOC = (
    "Pierwszy akapit ma trafienie review tutaj.\n"   # linia 1  (8 słów)
    "\n"                                              # linia 2
    "Drugi akapit zawiera twardy bloker block.\n"     # linia 3  (6 słów)
    "\n"                                              # linia 4
    "Trzeci akapit jest zupełnie czysty bez niczego." # linia 5  (7 słów)
)

# Mini-manifest spójny z DOC. Słowa per plik = łączna liczba słów DOC.
WORDS_TOTAL = len(metrics._WORD_RE.findall(DOC))
PARA1_WORDS = len(metrics._WORD_RE.findall("Pierwszy akapit ma trafienie review tutaj."))

MANIFEST = {
    "hits": [
        {"file": "doc.txt", "line": 1, "id": "PL-SIGN", "klasa": "review", "match": "review"},
        {"file": "doc.txt", "line": 3, "id": "EN-DASH", "klasa": "block", "match": "block"},
    ],
    "summary": [
        {"file": "doc.txt", "words": WORDS_TOTAL, "hits": 2, "emdash_max": 0,
         "density": 0.0, "blockers": 1, "verdict": "FAIL"},
    ],
}


def _reader_ok(path):
    if path == "doc.txt":
        return DOC
    raise OSError(f"nieoczekiwana ścieżka: {path}")


def _reader_missing(path):
    raise OSError(f"brak pliku: {path}")


def main():
    fails = []

    # --- Główny przebieg: file_reader w pamięci ---
    r = metrics.reduction_from_manifest(MANIFEST, file_reader=_reader_ok)

    # 1+2+3: routed tylko akapit 1 (review). Block i czysty pominięte.
    if r["routed_segments"] != 1:
        fails.append(f"routed_segments: oczekiwano 1 (tylko akapit review), jest {r['routed_segments']}")
    if r["total_segments"] != 3:
        fails.append(f"total_segments: oczekiwano 3, jest {r['total_segments']}")

    # 4: routed_words = słowa akapitu review.
    if r["routed_words"] != PARA1_WORDS:
        fails.append(f"routed_words: oczekiwano {PARA1_WORDS} (słowa akapitu review), jest {r['routed_words']}")
    if r["total_words"] != WORDS_TOTAL:
        fails.append(f"total_words: oczekiwano {WORDS_TOTAL}, jest {r['total_words']}")

    # 5: inwariant reduction + routed == 1.
    if abs((r["reduction_ratio"] + r["routed_ratio"]) - 1.0) > 1e-9:
        fails.append(f"inwariant: reduction + routed != 1 ({r['reduction_ratio']} + {r['routed_ratio']})")

    # 6: routed_ratio = PARA1_WORDS / WORDS_TOTAL.
    expected_routed = PARA1_WORDS / WORDS_TOTAL
    if abs(r["routed_ratio"] - expected_routed) > 1e-9:
        fails.append(f"routed_ratio: oczekiwano {expected_routed:.4f}, jest {r['routed_ratio']:.4f}")

    # Kontrola: per_file zgodne z agregatem.
    pf = r["per_file"][0]
    if pf["routed_words"] != PARA1_WORDS or pf["fallback"]:
        fails.append(f"per_file: routed_words/fallback rozjazd: {pf}")

    # 7: wariant awaryjny — plik z review, ale nieczytelny => fallback, cały plik routed.
    rf = metrics.reduction_from_manifest(MANIFEST, file_reader=_reader_missing)
    if not rf["per_file"][0]["fallback"]:
        fails.append("fallback: nieczytelny plik z review powinien dać fallback=True")
    if rf["routed_words"] != WORDS_TOTAL:
        fails.append(f"fallback: oczekiwano routed_words={WORDS_TOTAL} (cały plik), jest {rf['routed_words']}")

    # --- E2: atrybucja pracy (per warstwa, per reguła, per silnik) ---
    # Manifest atrybucji: 3x PL-SIGN (deklaratywna), 2x PL-RHYTHM (proceduralna), 1x EN-DASH (proc., block).
    attr_manifest = {
        "hits": [
            {"file": "a.md", "line": 1, "id": "PL-SIGN", "klasa": "review", "match": "x"},
            {"file": "a.md", "line": 2, "id": "PL-SIGN", "klasa": "review", "match": "x"},
            {"file": "a.md", "line": 3, "id": "PL-SIGN", "klasa": "review", "match": "x"},
            {"file": "a.md", "line": 4, "id": "PL-RHYTHM", "klasa": "review", "match": "x"},
            {"file": "a.md", "line": 5, "id": "PL-RHYTHM", "klasa": "review", "match": "x"},
            {"file": "a.md", "line": 6, "id": "EN-DASH", "klasa": "block", "match": "—"},
        ],
        "summary": [{"file": "a.md", "words": 100, "hits": 6, "emdash_max": 1,
                     "density": 0.0, "blockers": 1, "verdict": "FAIL"}],
    }
    a = metrics.attribution_from_manifest(attr_manifest)

    # 8: per_rule sumuje się do total_hits == len(hits).
    sum_rule_hits = sum(r["hits"] for r in a["per_rule"])
    if a["total_hits"] != 6 or sum_rule_hits != 6:
        fails.append(f"atrybucja: total_hits={a['total_hits']}, Σ per_rule.hits={sum_rule_hits}, oczekiwano 6")

    by_id = {r["id"]: r for r in a["per_rule"]}
    # 9: PL-RHYTHM => proceduralna.
    if by_id["PL-RHYTHM"]["layer"] != "proceduralna":
        fails.append(f"warstwa PL-RHYTHM: oczekiwano 'proceduralna', jest {by_id['PL-RHYTHM']['layer']}")
    # 9b: EN-DASH (czysto proceduralny) => proceduralna.
    if by_id["EN-DASH"]["layer"] != "proceduralna":
        fails.append(f"warstwa EN-DASH: oczekiwano 'proceduralna', jest {by_id['EN-DASH']['layer']}")
    # 10: PL-SIGN (w MARKER_DEFS) => deklaratywna.
    if by_id["PL-SIGN"]["layer"] != "deklaratywna":
        fails.append(f"warstwa PL-SIGN: oczekiwano 'deklaratywna', jest {by_id['PL-SIGN']['layer']}")

    # 11: ranking malejący wg trafień — PL-SIGN (3) na czele.
    if a["per_rule"][0]["id"] != "PL-SIGN" or a["per_rule"][0]["hits"] != 3:
        fails.append(f"ranking: oczekiwano PL-SIGN(3) na czele, jest {a['per_rule'][0]['id']}({a['per_rule'][0]['hits']})")

    # 12: udziały sumują się do 1.0.
    sum_share = sum(r["share"] for r in a["per_rule"])
    if abs(sum_share - 1.0) > 1e-9:
        fails.append(f"udziały per_rule: Σ share={sum_share}, oczekiwano 1.0")

    # per_layer: deklaratywna ma 3 trafienia (PL-SIGN), proceduralna 3 (PL-RHYTHM x2 + EN-DASH).
    if a["per_layer"].get("deklaratywna", {}).get("hits") != 3:
        fails.append(f"per_layer deklaratywna.hits: oczekiwano 3, jest {a['per_layer'].get('deklaratywna')}")
    if a["per_layer"].get("proceduralna", {}).get("hits") != 3:
        fails.append(f"per_layer proceduralna.hits: oczekiwano 3, jest {a['per_layer'].get('proceduralna')}")
    # per_class: review 5, block 1.
    if a["per_class"] != {"review": 5, "block": 1}:
        fails.append(f"per_class: oczekiwano review=5/block=1, jest {a['per_class']}")

    # 13: atrybucja per silnik z wyniku runnera (G1) — rozdziela rewrite/pass.
    runner_result = {
        "segments": [
            {"file": "a.md", "seg_index": 0, "line": 1, "verdict": "rewrite", "engine": "stub"},
            {"file": "a.md", "seg_index": 1, "line": 4, "verdict": "rewrite", "engine": "stub"},
            {"file": "b.md", "seg_index": 0, "line": 1, "verdict": "pass", "engine": "inny"},
        ],
    }
    ae = metrics.attribution_from_runner(runner_result)
    if ae["judged"] != 3:
        fails.append(f"per silnik: judged oczekiwano 3, jest {ae['judged']}")
    eng = {e["engine"]: e for e in ae["per_engine"]}
    if eng.get("stub", {}).get("rewrite") != 2 or eng.get("stub", {}).get("judged") != 2:
        fails.append(f"per silnik stub: oczekiwano judged=2/rewrite=2, jest {eng.get('stub')}")
    if eng.get("inny", {}).get("pass") != 1:
        fails.append(f"per silnik inny: oczekiwano pass=1, jest {eng.get('inny')}")
    # Ranking per silnik malejący: stub(2) przed inny(1).
    if ae["per_engine"][0]["engine"] != "stub":
        fails.append(f"ranking per silnik: oczekiwano 'stub' na czele, jest {ae['per_engine'][0]['engine']}")

    # --- E4: wskaźnik zdrowia ekonomii (alarm na wzrost routed_ratio) ---
    # Próg wstrzyknięty w pamięci (bez I/O config.json): alarm 10%, min. próbka 5 słów.
    ECON = {"routed_ratio_alarm": 0.10, "min_words": 5}

    # 14: routed_ratio NAD progiem => ALARM.
    # MANIFEST: routed = słowa akapitu review (8) / total (21) ≈ 0.38 > 0.10.
    h_alarm = metrics.economy_health(MANIFEST, economy=ECON, file_reader=_reader_ok)
    if h_alarm["health"] != "ALARM":
        fails.append(f"E4 alarm: routed {h_alarm['routed_ratio']:.3f} > próg {ECON['routed_ratio_alarm']} "
                     f"powinno dać ALARM, jest {h_alarm['health']}")
    # 17: próg w wyniku = próg na wejściu.
    if abs(h_alarm["alarm_threshold"] - 0.10) > 1e-9:
        fails.append(f"E4 próg: alarm_threshold {h_alarm['alarm_threshold']} != 0.10 (wejście)")

    # 15: routed_ratio POD progiem => OK. Manifest bez trafień review (routed=0) i dość słów.
    manifest_ok = {
        "hits": [],
        "summary": [{"file": "clean.txt", "words": 100, "hits": 0, "emdash_max": 0,
                     "density": 0.0, "blockers": 0, "verdict": "PASS"}],
    }
    h_ok = metrics.economy_health(manifest_ok, economy=ECON, file_reader=lambda p: "")
    if h_ok["health"] != "OK":
        fails.append(f"E4 ok: routed 0% <= próg powinno dać OK, jest {h_ok['health']} ({h_ok['reason']})")

    # 16: total_words < min_words => N/A (alarm wstrzymany mimo wysokiego routed_ratio).
    ECON_BIG_SAMPLE = {"routed_ratio_alarm": 0.10, "min_words": 1000}
    h_na = metrics.economy_health(MANIFEST, economy=ECON_BIG_SAMPLE, file_reader=_reader_ok)
    if h_na["health"] != "N/A":
        fails.append(f"E4 N/A: total_words {h_na['total_words']} < min_words 1000 powinno dać N/A, "
                     f"jest {h_na['health']}")

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)

    print(f"OK   metryki E1: redukcja {r['reduction_ratio']*100:.1f}% / routed {r['routed_ratio']*100:.1f}% "
          f"(akapit review routed, block+czysty pominięte; inwariant red+routed=1; fallback działa).")
    print(f"OK   metryki E2: atrybucja {a['total_hits']} trafień "
          f"(per reguła sumuje się; PL-RHYTHM/EN-DASH proceduralne, PL-SIGN deklaratywna; "
          f"ranking malejący; per silnik rozdziela rewrite/pass).")
    print(f"OK   metryki E4: zdrowie ekonomii "
          f"(routed nad progiem => ALARM, pod progiem => OK, próbka < min_words => N/A; "
          f"próg czytany z wejścia).")


if __name__ == "__main__":
    main()
