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

echo "== Słownik domenowy: format/classify/zero-zmiany (D2) =="
if python3 "$DIR/../tools/check_dictionary.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL słownik — format/classify/fallback rozjechał się (patrz wyżej)"; fail=1
fi

echo "== build-dict: częstość proponuje, kanon wetuje, allow puste (D3) =="
if python3 "$DIR/../tools/check_build_dict.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL build-dict — ekstrakcja/veto kanonu/format szkicu rozjechał się (patrz wyżej)"; fail=1
fi

echo "== Log decyzji: append-only JSONL, surowiec D3/B3 (D4) =="
if python3 "$DIR/../tools/check_decision_log.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL log decyzji — append-only/walidacja/odczyt rozjechał się (patrz wyżej)"; fail=1
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

echo "== Metryki: redukcja/atrybucja/zdrowie ekonomii z manifestu (E1/E2/E4) =="
if python3 "$DIR/../tools/check_metrics.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL metryki — redukcja (routed vs block vs czysty), atrybucja (warstwa/reguła/silnik) lub alarm zdrowia ekonomii (E4) rozjechał się (patrz wyżej)"; fail=1
fi

echo "== Zdrowie ekonomii (E4): smoke CLI end-to-end (linter -> manifest -> health, czysty=OK) =="
# Czysty plik kontrolny: routed=0% => STATUS OK => exit 0. Wymusza spójność lintera, metrics i CLI.
if python3 "$DIR/../ai_linter.py" --format json "$DIR/control_pl_clean.md" 2>/dev/null \
     | python3 "$DIR/../tools/measure_health.py" --min-words 1 >/dev/null; then
  echo "OK   zdrowie ekonomii — czysty plik daje STATUS OK (exit 0); ALARM dałby exit 1 (gate-owalne)."
else
  echo "FAIL zdrowie ekonomii (E4) — measure_health na czystym pliku zwrócił niezerowy kod (patrz wyżej)"; fail=1
fi

echo "== Runner Stage 2: selekcja review + atrapa + bramka (G1) + instrumentacja log stage2_run (E3) =="
if python3 "$DIR/../tools/check_runner.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL runner Stage 2 — selekcja/bramka/atrapa (G1) lub log stage2_run we wspólnym strumieniu z D4 (E3) rozjechał się (patrz wyżej)"; fail=1
fi

echo "== Bramka write-time: blokuje tylko twarde blokery, sama gęstość NIE (F1) =="
if python3 "$DIR/../tools/check_write_gate.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL bramka write-time — gate_decision blokuje gęstość zamiast tylko twardych blokerów, albo opt-in/smoke rozjechał się (patrz wyżej)"; fail=1
fi

if [[ $fail -eq 0 ]]; then
  echo "WSZYSTKIE TESTY PRZESZŁY."
else
  echo "REGRESJA WYKRYTA — popraw linter/taksonomię przed commitem."
fi
exit $fail
