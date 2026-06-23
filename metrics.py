#!/usr/bin/env python3
"""
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
"""

import os
import re
import sys

# Import lintera/adaptera bez wymuszania ścieżki w środowisku wywołującego.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import ai_linter  # noqa: E402  (_select_adapter — ta sama segmentacja co linter)

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
