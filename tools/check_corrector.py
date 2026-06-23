#!/usr/bin/env python3
"""
check_corrector.py — gate korektora G2 (pętla audyt → poprawka → ponowny audyt). ZERO-DEP, OFFLINE.

Bez LLM, bez sieci. Silnik to atrapa korektora (engines.StubRewriteEngine) albo lokalne atrapy
testowe. Audyt to make_default_audit (Stage 1 linter na pliku tymczasowym — offline, bez sieci).
Weryfikuje:

  1. ZBIEŻNOŚĆ do PASS: dokument z manieryzmem (triada PL-RHET + antyteza PL-ANTI) → po ≤ max_iter
     pętla daje passed==True, reason=="pass", ślad pokazuje ≥1 poprawiony segment, a finalny tekst
     po ponownym audycie NIE ma już trafień review.
  2. CZYSTY tekst → zero iteracji: brak segmentów review → iterations==0, passed==True,
     reason=="pass", tekst BEZ zmian.
  3. BRAK POSTĘPU: silnik osądza rewrite, ale jego rewrite to no-op (domyślny JudgeEngine.rewrite)
     → STOP po pierwszej iteracji, reason=="brak postępu", passed==False (ochrona przed pętlą).
  4. LIMIT ITERACJI: silnik ZMIENIA tekst, ale NIE usuwa wzorca (postęp bez zbieżności) → STOP po
     dokładnie max_iter iteracjach, reason=="limit iteracji", passed==False, len(trace)==max_iter.
  5. ZAPIS ZWROTNY wierny: w dokumencie 2-akapitowym poprawiony jest TYLKO sporny akapit, drugi
     (czysty) zostaje znak w znak — Edit nanoszony przez write_back na właściwych offsetach.
  6. KONTRAKT rewrite: domyślny JudgeEngine.rewrite zwraca segment.text (no-op); StubRewriteEngine
     realnie neutralizuje match; StubJudgeEngine dalej TYLKO osądza (brak regresji G1).
  7. STRAŻNIK REGRESJI (KAN-223): rewrite dokładający NOWY manieryzm (więcej trafień) jest
     ODRZUCany — segment zostaje oryginałem, pętla kończy „brak postępu” (chroni zbieżność na
     żywym modelu). 7b: zmiana NEUTRALNA (spacja, zero nowych trafień) przechodzi (granica strażnika).

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import corrector  # noqa: E402
import engines    # noqa: E402
from engines import ReviewSegment, Judgement, StubJudgeEngine, StubRewriteEngine  # noqa: E402

failed = []


def check(cond, msg):
    if not cond:
        failed.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print(f"  ok: {msg}")


# Audyt offline wspólny dla testów (linter na pliku tymczasowym; bez sieci).
AUDIT = corrector.make_default_audit(lang="both")

# Dokument z manieryzmem: akapit 1 = triada (PL-RHET review), akapit 2 = antyteza (PL-ANTI review).
DIRTY = (
    "To rozwiazanie jest szybkie, proste i skuteczne w kazdej sytuacji biznesowej.\n"
    "\n"
    "Liczy sie jakosc, a nie ilosc dostarczanych komponentow projektu.\n"
)
CLEAN = "To jest zwykly akapit prozy bez zadnych sztucznych sygnalow generatora.\n"


def review_hits(text, file_path="x.txt"):
    """Liczba trafień review w manifeście audytu (do weryfikacji „czysty po korekcie")."""
    manifest, _doc = AUDIT(text, file_path)
    return [h for h in manifest["hits"] if h.get("klasa") == "review"]


# --- 1. Zbieżność do PASS na atrapie korektora ---
print("[1] zbieżność do PASS (StubRewriteEngine)")
r1 = corrector.correct_document(DIRTY, file_path="x.txt", engine=StubRewriteEngine(),
                                audit_fn=AUDIT, max_iter=4)
check(r1.passed is True, "passed == True")
check(r1.reason == "pass", f"reason == 'pass' (jest {r1.reason!r})")
check(r1.iterations <= 4, f"iterations <= max_iter (jest {r1.iterations})")
check(sum(t["poprawione"] for t in r1.trace) >= 1, "ślad: ≥1 poprawiony segment")
check(len(review_hits(r1.text)) == 0, "finalny tekst NIE ma już trafień review (czysty)")


# --- 2. Czysty tekst → zero iteracji ---
print("[2] czysty tekst → zero iteracji")
r2 = corrector.correct_document(CLEAN, file_path="x.txt", engine=StubRewriteEngine(),
                                audit_fn=AUDIT, max_iter=4)
check(r2.iterations == 0, f"iterations == 0 (jest {r2.iterations})")
check(r2.passed is True, "passed == True")
check(r2.reason == "pass", "reason == 'pass'")
check(r2.text == CLEAN, "tekst BEZ zmian")
check(r2.trace == [], "ślad pusty (brak iteracji)")


# --- 3. Brak postępu: silnik osądza rewrite, ale jego rewrite to no-op ---
print("[3] brak postępu (rewrite = no-op → STOP)")
r3 = corrector.correct_document(DIRTY, file_path="x.txt", engine=StubJudgeEngine(),
                                audit_fn=AUDIT, max_iter=4)
check(r3.reason == "brak postępu", f"reason == 'brak postępu' (jest {r3.reason!r})")
check(r3.passed is False, "passed == False")
check(r3.iterations == 1, f"STOP po pierwszej iteracji (jest {r3.iterations})")
check(r3.text == DIRTY, "tekst BEZ zmian (no-op nie ruszył)")


# --- 4. Limit iteracji: postęp bez zbieżności ---
# Atrapa, która ZMIENIA tekst (dopisuje znak), ale NIGDY nie usuwa wzorca → wzorzec łapany w
# każdej iteracji, edycja zawsze != oryginał → pętla dochodzi do max_iter (nie „brak postępu").
class NonConvergingEngine(StubJudgeEngine):
    name = "stub-nonconverging"

    def rewrite(self, segment, judgement):
        # zachowaj manieryzm (triadę/antytezę), tylko dopisz spację na końcu — zawsze postęp,
        # nigdy zbieżność.
        return segment.text + " "


print("[4] limit iteracji (postęp bez zbieżności)")
r4 = corrector.correct_document(DIRTY, file_path="x.txt", engine=NonConvergingEngine(),
                                audit_fn=AUDIT, max_iter=3)
check(r4.reason == "limit iteracji", f"reason == 'limit iteracji' (jest {r4.reason!r})")
check(r4.passed is False, "passed == False (niezbieżny)")
check(r4.iterations == 3, f"iterations == max_iter (jest {r4.iterations})")
check(len(r4.trace) == 3, f"ślad ma max_iter wpisów (jest {len(r4.trace)})")


# --- 5. Zapis zwrotny wierny: tylko sporny akapit zmieniony, drugi nietknięty ---
print("[5] zapis zwrotny wierny")
# Akapit 1 brudny (antyteza), akapit 2 czysty i UNIKALNY — sprawdzamy, że zostaje znak w znak.
MIX = (
    "Liczy sie jakosc, a nie ilosc dostarczanych komponentow projektu.\n"
    "\n"
    "Drugi akapit jest zupelnie spokojny i nie zawiera zadnych sygnalow.\n"
)
r5 = corrector.correct_document(MIX, file_path="x.txt", engine=StubRewriteEngine(),
                                audit_fn=AUDIT, max_iter=4)
check("Drugi akapit jest zupelnie spokojny i nie zawiera zadnych sygnalow." in r5.text,
      "czysty akapit pozostał nietknięty (znak w znak)")
check(", a nie " not in r5.text, "sporny akapit zmieniony (antyteza usunięta)")
check(r5.passed is True, "passed == True (zbieżność)")


# --- 6. Kontrakt rewrite ---
print("[6] kontrakt rewrite (domyślny no-op vs atrapa korektora vs osądzająca)")
seg = ReviewSegment(file="x.txt", seg_index=0, line=1,
                    text="szybkie, proste i skuteczne rozwiazanie",
                    hits=[{"id": "PL-RHET", "klasa": "review",
                           "match": "szybkie, proste i skuteczne", "line": 1}])
j = Judgement(verdict="rewrite", notes="t", engine="t")

# domyślny JudgeEngine.rewrite (przez StubJudgeEngine, która go NIE nadpisuje) = no-op.
check(StubJudgeEngine().rewrite(seg, j) == seg.text,
      "domyślny rewrite (StubJudgeEngine) = no-op (zwraca segment.text)")
# StubRewriteEngine realnie neutralizuje triadę (≠ oryginał i bez 3 członów).
rw = StubRewriteEngine().rewrite(seg, j)
check(rw != seg.text, "StubRewriteEngine.rewrite faktycznie zmienia tekst")
check("proste" not in rw, "StubRewriteEngine skraca triadę (środkowy człon usunięty)")
# StubJudgeEngine dalej tylko osądza (G1 bez regresji): review → rewrite.
check(StubJudgeEngine().judge(seg).verdict == "rewrite",
      "StubJudgeEngine.judge nadal zwraca 'rewrite' dla review (G1 bez regresji)")


# --- 7. STRAŻNIK REGRESJI (KAN-223): poprawka wprowadzająca NOWY manieryzm jest odrzucana ---
# Atrapa osądza segment jako rewrite, ale jej rewrite DOKŁADA manieryzm (zamienia akapit na taki
# z większą liczbą trafień). Strażnik liczy trafienia obu wersji segmentu i odrzuca pogorszenie:
# segment zostaje oryginałem, pętla kończy „brak postępu” (a nie rozjeżdża tekstu do limitu).
print("[7] strażnik regresji (rewrite dokłada manieryzm → poprawka odrzucona)")

# Akapit wejściowy: JEDEN manieryzm (antyteza PL-ANTI). Rewrite zwraca akapit z triadą PL-RHET +
# antytezą — WIĘCEJ trafień niż oryginał, więc strażnik MUSI go odrzucić.
ONE_HIT = "Liczy sie jakosc, a nie ilosc dostarczanych elementow.\n"
WORSE = "To rozwiazanie jest szybkie, proste i skuteczne, a nie wolne i zawodne."


class RegressingEngine(StubJudgeEngine):
    """Atrapa, której rewrite POGARSZA segment (dokłada triadę do istniejącej antytezy)."""
    name = "stub-regressing"

    def rewrite(self, segment, judgement):
        return WORSE


# kontrola wstępna: WORSE faktycznie ma więcej trafień niż ONE_HIT (inaczej test nic nie sprawdza).
hits_one = len(AUDIT(ONE_HIT, "x.txt")[0]["hits"])
hits_worse = len(AUDIT(WORSE, "x.txt")[0]["hits"])
check(hits_worse > hits_one,
      f"setup: WORSE ma więcej trafień niż ONE_HIT ({hits_worse} > {hits_one})")

r7 = corrector.correct_document(ONE_HIT, file_path="x.txt", engine=RegressingEngine(),
                                audit_fn=AUDIT, max_iter=4)
check(r7.reason == "brak postępu",
      f"strażnik: reason == 'brak postępu' (jest {r7.reason!r})")
check(r7.passed is False, "strażnik: passed == False")
check(r7.iterations == 1, f"strażnik: STOP po 1. iteracji (jest {r7.iterations})")
check(r7.text == ONE_HIT, "strażnik: tekst BEZ zmian (pogarszająca poprawka odrzucona)")
check(WORSE.strip() not in r7.text, "strażnik: nowy manieryzm NIE trafił do tekstu")

# Granica strażnika: zmiana NEUTRALNA (NonConvergingEngine dokłada tylko spację, ZERO nowych
# trafień) MUSI przejść — inaczej zepsulibyśmy test [4] „limit iteracji”. To potwierdza, że
# strażnik odrzuca tylko POGORSZENIE (ostre nierówności), nie zmianę neutralną.
print("[7b] strażnik przepuszcza zmianę neutralną (spacja, bez nowych trafień)")
r7b = corrector.correct_document(DIRTY, file_path="x.txt", engine=NonConvergingEngine(),
                                 audit_fn=AUDIT, max_iter=3)
check(r7b.reason == "limit iteracji",
      f"neutralna zmiana dochodzi do limitu (jest {r7b.reason!r})")
check(len(r7b.trace) == 3, "neutralna zmiana: pętla iteruje do max_iter (strażnik nie blokuje)")


# --- podsumowanie ---
if failed:
    print(f"\nKOREKTOR G2: {len(failed)} ASERCJI NIE PRZESZŁO.")
    sys.exit(1)
print("\nKOREKTOR G2: pętla audyt → poprawka → ponowny audyt do PASS — wszystkie asercje OK "
      "(zbieżność, zero iteracji, brak postępu, limit iteracji, zapis zwrotny, kontrakt rewrite).")
sys.exit(0)
