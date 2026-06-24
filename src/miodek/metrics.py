#!/usr/bin/env python3
r"""
metrics.py — miary ekonomii i obserwowalności liczone z MANIFESTU (Stage 1), bez kosztu tokenów.

Granica między etapami to manifest JSON lintera (`ai_linter --format json`):
    { "hits":    [{file, line, id, klasa, match}],
      "summary": [{file, words, hits, emdash_max, density, blockers, verdict}] }

Ten moduł NIE woła lintera ani LLM w rdzeniu. Przyjmuje gotowy manifest (dict) i — w razie potrzeby
mapowania trafień na akapity — treść plików (przez wstrzykiwalny `file_reader`, domyślnie czyta z dysku).

WSPÓŁCZYNNIK REDUKCJI (E1)
==========================
Definicja (precyzyjna i udokumentowana):

    Treść routowana do modelu (Stage 2) = segmenty (AKAPITY) zawierające co najmniej jedno
    trafienie klasy "review". Trafienia klasy "block" linter zamyka sam (twardy bloker, FAIL),
    więc NIE liczą się jako routowane. Akapity bez trafień review są czyste.

    routed_words     = Σ słów akapitów zawierających ≥1 hit klasy "review"   (per plik, sumowane)
    total_words      = Σ summary[*].words
    reduction_ratio  = 1 - routed_words / total_words     # udział treści, której model NIE tyka
    routed_ratio     = routed_words / total_words          # = "hit rate"; ref. autora 0.04–0.05

Mapowanie trafień na akapity robi adapter (TA SAMA segmentacja co linter), nie zgadujemy:
  - adapter wybrany jak w linterze (`ai_linter._select_adapter(path)`),
  - `doc.paragraphs()` daje akapity z polem `line` (1-based, w `doc.text`),
  - zakres linii akapitu = [seg.line, seg.line + seg.text.count("\n")],
  - hit klasy "review" przypisany do akapitu, gdy hit.line mieści się w tym zakresie,
  - słowa akapitu = len(re.findall(r"\w+", seg.text)) — ta sama formuła co `summary.words`.

Liczbą główną są SŁOWA (porównywalne z `summary.words` i z odniesieniem 4–5%). Segmenty raportujemy
pomocniczo (routed_segments / total_segments).

ZNANE OGRANICZENIE: trafienie review, którego linii nie da się przypisać żadnemu akapitowi danego
pliku (np. plik niedostępny dla `file_reader` albo trafienie poza akapitami), jest liczone
zachowawczo jako routed o wadze całego pliku w wariancie awaryjnym — patrz `reduction_from_manifest`
(per_file z flagą "fallback"). W normalnym przebiegu (plik czytelny) to się nie zdarza.

ATRYBUCJA PRACY (E2)
====================
`attribution_from_manifest` rozbija trafienia wg WARSTWY (deklaratywna/proceduralna) i wg REGUŁY
(id markera), czysto z manifestu — odpowiada na „która reguła robi modelowi najwięcej roboty".
`attribution_from_runner` dokłada rozbicie per SILNIK z wyniku runnera Stage 2 (G1), gdy jest
dostępny; sam manifest werdyktów silnika nie zawiera (jawne ograniczenie). Szczegóły niżej.

ZDROWIE EKONOMII (E4)
=====================
`economy_health` bierze współczynnik redukcji (E1) i próg z configu (`config.load_economy`) i zwraca
status zdrowia z alarmem:

    health = "OK"     gdy routed_ratio <= routed_ratio_alarm,
    health = "ALARM"  gdy routed_ratio  > routed_ratio_alarm   # za dużo treści idzie do modelu,
                                                                # linter nie odsiewa = regresja reguł,
    health = "N/A"    gdy total_words < min_words               # próbka za mała na wskaźnik.

Próg żyje w sekcji `economy` w config.json (rodzeństwo `profiles`, nie wewnątrz `thresholds`).
ALARM jest gate-owalny: CLI `tools/measure_health.py` daje exit 1 przy alarmie (CI/pre-publish).
"""

import os
import re
import sys

from miodek import ai_linter  # (_select_adapter — ta sama segmentacja co linter)

_WORD_RE = re.compile(r"\w+")


def _count_words(text):
    """Liczy słowa identycznie jak linter (summary.words): len(re.findall(r'\\w+', text))."""
    return len(_WORD_RE.findall(text))


def _default_file_reader(path):
    """Domyślny czytnik: wczytuje treść pliku z dysku (UTF-8, błędy zastępowane jak w linterze)."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def review_paragraphs_for_file(file_path, review_hits, file_reader=_default_file_reader):
    """Zwraca akapity danego pliku zawierające ≥1 trafienie klasy "review".

    Wspólne źródło prawdy „co idzie do Stage 2" — używane przez E1 (routed_words) ORAZ przez runner
    Stage 2 (select_review_segments). Trzymanie jednej funkcji gwarantuje, że metryka redukcji i
    realna selekcja segmentów liczą dokładnie to samo.

    Zwraca listę krotek (seg, hits_w_tym_akapicie), gdzie `seg` to adapter.Segment (ma .text/.line),
    a `hits_w_tym_akapicie` to lista trafień review (dict z manifestu) przypiętych do tego akapitu.

    Gdy plik jest nieczytelny (file_reader rzuca), zwraca None — sygnał do wariantu awaryjnego.
    """
    try:
        text = file_reader(file_path)
    except (OSError, ValueError):
        return None

    doc = ai_linter._select_adapter(file_path).normalize(text)
    paras = doc.paragraphs()

    # Dla każdego akapitu wyznacz zakres linii [seg.line, seg.line + liczba_\n_w_segmencie].
    out = []
    for seg in paras:
        lo = seg.line
        hi = seg.line + seg.text.count("\n")
        in_para = [h for h in review_hits if lo <= h.get("line", -1) <= hi]
        if in_para:
            out.append((seg, in_para))
    return out


def reduction_from_manifest(manifest, file_reader=_default_file_reader):
    """Liczy współczynnik redukcji z manifestu (bez LLM, bez wołania lintera).

    Wejście: manifest (dict) o kształcie {"hits":[...], "summary":[...]}.
    Zwraca:
        {
          "total_words", "routed_words", "routed_segments", "total_segments",
          "reduction_ratio", "routed_ratio",
          "per_file": [{"file", "words", "routed_words", "routed_ratio",
                        "routed_segments", "total_segments", "fallback"(bool)}]
        }

    Inwariant: reduction_ratio + routed_ratio == 1.0 (gdy total_words > 0). Przy total_words == 0
    oba współczynniki = 0.0 (brak treści = brak redukcji do raportowania).
    """
    hits = manifest.get("hits", [])
    summaries = manifest.get("summary", [])

    # Trafienia review pogrupowane po pliku.
    review_by_file = {}
    for h in hits:
        if h.get("klasa") == "review":
            review_by_file.setdefault(h.get("file"), []).append(h)

    per_file = []
    total_words = 0
    routed_words = 0
    total_segments = 0
    routed_segments = 0

    for s in summaries:
        fpath = s.get("file")
        fwords = int(s.get("words", 0))
        total_words += fwords

        file_reviews = review_by_file.get(fpath, [])
        f_routed_words = 0
        f_routed_segments = 0
        f_total_segments = 0
        fallback = False

        if file_reviews:
            mapped = review_paragraphs_for_file(fpath, file_reviews, file_reader=file_reader)
            if mapped is None:
                # Wariant awaryjny: pliku nie da się odczytać, a ma trafienia review.
                # Zachowawczo traktujemy cały plik jako routed (model i tak musiałby go tknąć).
                fallback = True
                f_routed_words = fwords
                f_routed_segments = 1
                f_total_segments = 1
            else:
                # Policz akapity pliku dla mianownika segmentów (ta sama segmentacja).
                try:
                    text = file_reader(fpath)
                    f_total_segments = len(ai_linter._select_adapter(fpath).normalize(text).paragraphs())
                except (OSError, ValueError):
                    f_total_segments = len(mapped)
                for seg, _seg_hits in mapped:
                    f_routed_words += _count_words(seg.text)
                    f_routed_segments += 1
        else:
            # Brak trafień review w pliku: spróbuj policzyć akapity (mianownik segmentów),
            # ale to opcjonalne — bez review nic nie jest routowane.
            try:
                text = file_reader(fpath)
                f_total_segments = len(ai_linter._select_adapter(fpath).normalize(text).paragraphs())
            except (OSError, ValueError):
                f_total_segments = 0

        routed_words += f_routed_words
        routed_segments += f_routed_segments
        total_segments += f_total_segments

        per_file.append({
            "file": fpath,
            "words": fwords,
            "routed_words": f_routed_words,
            "routed_ratio": (f_routed_words / fwords) if fwords else 0.0,
            "routed_segments": f_routed_segments,
            "total_segments": f_total_segments,
            "fallback": fallback,
        })

    routed_ratio = (routed_words / total_words) if total_words else 0.0
    reduction_ratio = (1.0 - routed_ratio) if total_words else 0.0

    return {
        "total_words": total_words,
        "routed_words": routed_words,
        "routed_segments": routed_segments,
        "total_segments": total_segments,
        "reduction_ratio": reduction_ratio,
        "routed_ratio": routed_ratio,
        "per_file": per_file,
    }


# Punkt odniesienia z praktyki autora (hit rate po wprowadzeniu lintera): 4–5% treści routowanej.
REFERENCE_ROUTED_RATIO = 0.045


# ============================================================================
# ATRYBUCJA PRACY (E2) — rozbicie wkładu w pracę modelu wg WARSTWY i wg REGUŁY.
# ============================================================================
#
# Pytanie E2: „która reguła (i która warstwa) robi najwięcej pracy", czyli generuje
# najwięcej trafień routowanych do osądu modelu (Stage 2). Liczone CZYSTO z manifestu,
# bez LLM i bez wołania lintera.
#
# WARSTWA = źródło trafienia:
#   - deklaratywna  — regex z rules.json: id ∈ {id z ai_linter.MARKER_DEFS},
#   - proceduralna  — detektor kodu: id ∈ ai_linter.PROCEDURAL_MARKER_IDS.
#
# Reguła rozstrzygania nakładki (PL-TYPO bywa w obu zbiorach):
#   ID czysto proceduralne (PL-RHYTHM, EN-DASH — brak ich w MARKER_DEFS) => "proceduralna".
#   ID obecne w MARKER_DEFS (m.in. PL-TYPO, PL-SIGN) => "deklaratywna".
#   Innymi słowy: obecność w MARKER_DEFS wygrywa; jeśli ID nie ma w MARKER_DEFS,
#   a jest w PROCEDURAL_MARKER_IDS — to proceduralna. ID nieznane żadnemu zbiorowi
#   trafia do worka "nieznana" (sygnał rozjazdu reguł).
#
# Główną miarą jest tu LICZBA TRAFIEŃ (nie słowa) — atrybucja odpowiada na „co generuje
# robotę dla modelu", a robotę generuje pojedyncze trafienie review. Liczymy oba: trafienia
# klasy "review" (realnie routowane do Stage 2) oraz "block" (zamknięte przez linter), żeby
# diagnoza pokazała też, co linter odsiewa twardo.


def _declarative_ids():
    """Zbiór ID reguł deklaratywnych (regex z rules.json), z ai_linter.MARKER_DEFS."""
    return {m[0] for m in ai_linter.MARKER_DEFS}


def classify_layer(rule_id):
    """Klasyfikuje ID reguły do warstwy: "deklaratywna" | "proceduralna" | "nieznana".

    Reguła rozstrzygania nakładki: obecność w MARKER_DEFS wygrywa (więc PL-TYPO, które jest
    w obu zbiorach, klasyfikujemy jako deklaratywne). ID spoza MARKER_DEFS, ale w
    PROCEDURAL_MARKER_IDS (PL-RHYTHM, EN-DASH) => proceduralna. Reszta => "nieznana".
    """
    if rule_id in _declarative_ids():
        return "deklaratywna"
    if rule_id in ai_linter.PROCEDURAL_MARKER_IDS:
        return "proceduralna"
    return "nieznana"


def attribution_from_manifest(manifest):
    """Atrybucja pracy z manifestu (bez LLM): per reguła, per warstwa, per klasa.

    Wejście: manifest (dict) {"hits":[...], "summary":[...]}.
    Zwraca:
        {
          "total_hits": N,
          "per_class": {"review": R, "block": B},
          "per_rule": [   # posortowane malejąco wg liczby trafień (potem alfabetycznie po id)
              {"id", "layer", "hits", "review", "block", "share"},  # share = hits/total_hits
              ...
          ],
          "per_layer": {
              "deklaratywna": {"hits", "review", "block", "share"},
              "proceduralna": {"hits", "review", "block", "share"},
              "nieznana":     {"hits", "review", "block", "share"},  # tylko gdy >0
          },
        }

    Inwariant: Σ per_rule[*].hits == total_hits == Σ per_class[*]; udział (share) sumuje się do 1.0
    (gdy total_hits > 0). Przy braku trafień zwraca puste rozbicia i total_hits == 0.
    """
    hits = manifest.get("hits", [])
    total = len(hits)

    per_rule = {}        # id -> {"hits","review","block"}
    per_class = {"review": 0, "block": 0}
    per_layer = {}       # layer -> {"hits","review","block"}

    for h in hits:
        rid = h.get("id", "?")
        klasa = h.get("klasa")
        layer = classify_layer(rid)

        r = per_rule.setdefault(rid, {"hits": 0, "review": 0, "block": 0, "layer": layer})
        r["hits"] += 1
        if klasa in ("review", "block"):
            r[klasa] += 1
            per_class[klasa] += 1

        lyr = per_layer.setdefault(layer, {"hits": 0, "review": 0, "block": 0})
        lyr["hits"] += 1
        if klasa in ("review", "block"):
            lyr[klasa] += 1

    def _share(n):
        return (n / total) if total else 0.0

    per_rule_list = [
        {
            "id": rid,
            "layer": d["layer"],
            "hits": d["hits"],
            "review": d["review"],
            "block": d["block"],
            "share": _share(d["hits"]),
        }
        for rid, d in per_rule.items()
    ]
    # Ranking: najwięcej pracy na górze; remis rozstrzyga alfabet ID (stabilnie).
    per_rule_list.sort(key=lambda x: (-x["hits"], x["id"]))

    per_layer_out = {
        layer: {
            "hits": d["hits"],
            "review": d["review"],
            "block": d["block"],
            "share": _share(d["hits"]),
        }
        for layer, d in per_layer.items()
    }

    return {
        "total_hits": total,
        "per_class": per_class,
        "per_rule": per_rule_list,
        "per_layer": per_layer_out,
    }


def attribution_from_runner(runner_result):
    """Atrybucja per SILNIK z werdyktów runnera Stage 2 (G1), gdy są dostępne.

    OGRANICZENIE (jawne): manifest sam w sobie nie zawiera werdyktów silnika — atrybucja per
    silnik wymaga wyniku `runner.run_stage2(...)`. Gdy danych z runnera brak, użyj
    `attribution_from_manifest` (atrybucja per reguła/warstwa wystarcza z samego manifestu).

    Wejście: `runner_result` = dict zwracany przez `runner.run_stage2` (ma klucz "segments" z
    polami {engine, verdict}). Zwraca rozbicie osądzonych segmentów per silnik:
        {
          "judged": N,
          "per_engine": [  # posortowane malejąco wg liczby osądzonych segmentów
              {"engine", "judged", "rewrite", "pass", "share"},
              ...
          ],
        }
    """
    segments = runner_result.get("segments", [])
    total = len(segments)

    per_engine = {}   # name -> {"judged","rewrite","pass"}
    for s in segments:
        name = s.get("engine", "?")
        e = per_engine.setdefault(name, {"judged": 0, "rewrite": 0, "pass": 0})
        e["judged"] += 1
        if s.get("verdict") == "rewrite":
            e["rewrite"] += 1
        else:
            e["pass"] += 1

    per_engine_list = [
        {
            "engine": name,
            "judged": d["judged"],
            "rewrite": d["rewrite"],
            "pass": d["pass"],
            "share": (d["judged"] / total) if total else 0.0,
        }
        for name, d in per_engine.items()
    ]
    per_engine_list.sort(key=lambda x: (-x["judged"], x["engine"]))

    return {"judged": total, "per_engine": per_engine_list}


# ============================================================================
# ZDROWIE EKONOMII (E4) — wskaźnik OK/ALARM z progiem na wzrost routed_ratio.
# ============================================================================
#
# E4 stoi na E1: bierze routed_ratio (udział treści routowanej do modelu) z manifestu i porównuje
# z progiem alarmu z configu (config.load_economy). Sens biznesowy: gdy linter przestaje odsiewać
# (np. regresja reguł, zmiana korpusu), routed_ratio rośnie i koszt warstwy modelu skacze — to ma
# zapalić alarm zanim wyląduje w rachunku za tokeny. Liczone CZYSTO z manifestu, bez LLM.


def economy_health(manifest, economy=None, file_reader=_default_file_reader):
    """Wskaźnik zdrowia ekonomii (E4): OK / ALARM / N/A z progiem alarmu na routed_ratio.

    Wejście:
      manifest    — manifest lintera (dict) {"hits":[...], "summary":[...]}.
      economy     — opcjonalny dict {"routed_ratio_alarm","min_words"}. Brak => wczytaj z configu
                    (config.load_economy, z fallbackiem na DEFAULT_ECONOMY). Wstrzykiwalny dla testu.
      file_reader — przekazywany do reduction_from_manifest (mapowanie trafień na akapity).

    Zwraca:
        {
          "health": "OK" | "ALARM" | "N/A",
          "routed_ratio": float,        # z E1
          "reduction_ratio": float,     # z E1 (dopełnienie)
          "alarm_threshold": float,     # routed_ratio_alarm użyty do oceny
          "total_words": int,
          "min_words": int,
          "reason": str,                # czytelne uzasadnienie werdyktu
        }

    Reguła:
      total_words < min_words            -> "N/A"  (za mała próbka, nie alarmujemy),
      routed_ratio <= alarm_threshold    -> "OK",
      routed_ratio  > alarm_threshold    -> "ALARM".
    """
    if economy is None:
        # Lokalny import, żeby nie wymuszać configu przy samym imporcie metrics.
        from miodek import config as _config
        economy = _config.load_economy()

    alarm = float(economy.get("routed_ratio_alarm", 0.10))
    min_words = int(economy.get("min_words", 200))

    red = reduction_from_manifest(manifest, file_reader=file_reader)
    routed_ratio = red["routed_ratio"]
    total_words = red["total_words"]

    if total_words < min_words:
        health = "N/A"
        reason = (f"próbka za mała: {total_words} słów < min_words {min_words} "
                  f"(wskaźnik niewiarygodny, alarm wstrzymany)")
    elif routed_ratio > alarm:
        health = "ALARM"
        reason = (f"routed_ratio {routed_ratio*100:.1f}% > próg {alarm*100:.1f}% "
                  f"(za dużo treści idzie do modelu — możliwa regresja reguł lub zmiana korpusu)")
    else:
        health = "OK"
        reason = (f"routed_ratio {routed_ratio*100:.1f}% <= próg {alarm*100:.1f}% "
                  f"(linter odsiewa zgodnie z odniesieniem ~4–5%)")

    return {
        "health": health,
        "routed_ratio": routed_ratio,
        "reduction_ratio": red["reduction_ratio"],
        "alarm_threshold": alarm,
        "total_words": total_words,
        "min_words": min_words,
        "reason": reason,
    }
