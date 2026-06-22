#!/usr/bin/env bash
# Regresja skilla sztuczny-miodek — warstwa manieryzmu AI (PL+EN).
# Asercje: 4 pliki baseline = FAIL (linter łapie zasiane AI-tells),
#          plik kontrolny (czysty, ludzki PL) = PASS (0 false-positives).
# Użycie: bash tests/run_tests.sh   (z katalogu skilla lub dowolnego)
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LINT="$DIR/../ai_linter.py"
fail=0

assert_verdict() {
  local file="$1" want="$2" lang="$3"
  local out verdict
  out="$(python3 "$LINT" --lang "$lang" "$DIR/$file" 2>/dev/null)"
  verdict="$(printf '%s\n' "$out" | awk -F'|' '/PASS|FAIL/ {gsub(/ /,"",$NF); print $NF}' | tail -1)"
  if [[ "$verdict" == "$want"* ]]; then
    echo "OK   $file → $verdict (oczekiwano $want)"
  else
    echo "FAIL $file → '$verdict' (oczekiwano $want)"; fail=1
  fi
}

echo "== Regresja: baseline (oczekiwane FAIL) =="
assert_verdict baseline_pl_raport.md     FAIL both
assert_verdict baseline_pl_intro.md      FAIL both
assert_verdict baseline_en_cover_letter.md FAIL both
assert_verdict baseline_en_doc.md        FAIL both
echo "== Regresja: kontrola (oczekiwane PASS, 0 false-positives) =="
assert_verdict control_pl_clean.md       PASS pl

echo "== Spójność ID: rules.json == linter == manieryzm-ai.md (A4) =="
if python3 "$DIR/../tools/check_id_consistency.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL spójność ID — rozjazd identyfikatorów (patrz wyżej)"; fail=1
fi

echo "== Spójność config: profile/progi config.json (D1) =="
if python3 "$DIR/../tools/check_config.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL config — profil default != progi historyczne lub niepoprawny profil (patrz wyżej)"; fail=1
fi

echo "== Recall triady: PL-RHET/EN-TRIAD na tests/triad_eval.md (B1) =="
if python3 "$DIR/../tools/measure_triad.py" --min-recall 1.0; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL recall triady — zawężenie wzorca przeoczyło realną triadę (patrz wyżej)"; fail=1
fi

echo "== Recall antytezy: PL-ANTI na tests/antithesis_eval.md (B2) =="
if python3 "$DIR/../tools/measure_antithesis.py" --min-recall 1.0; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL recall antytezy — zawężenie wzorca przeoczyło generatorową antytezę (patrz wyżej)"; fail=1
fi

echo "== Segmenter zdań: skróty/inicjały/separatory na tests/sentence_eval.md (C2) =="
if python3 "$DIR/../tools/measure_sentences.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL segmenter zdań — podział zdań rozjechał się (patrz wyżej)"; fail=1
fi

echo "== Adapter Markdown: zerowanie kodu (bloki/inline) (C3) =="
if python3 "$DIR/../tools/measure_markdown.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL adapter Markdown — ekstrakcja prozy / zerowanie kodu rozjechało się (patrz wyżej)"; fail=1
fi

echo "== Adapter strukturalny: granice akapitów z HTML (C4 szkielet) =="
if python3 "$DIR/../tools/measure_structural.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL adapter strukturalny — ekstrakcja prozy z HTML rozjechała się (patrz wyżej)"; fail=1
fi

if [[ $fail -eq 0 ]]; then
  echo "WSZYSTKIE TESTY PRZESZŁY."
else
  echo "REGRESJA WYKRYTA — popraw linter/taksonomię przed commitem."
fi
exit $fail
