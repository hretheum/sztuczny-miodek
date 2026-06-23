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

echo "== Dostęp do danych pakietu: centralny resources, podłączenie ai_linter/config (KAN-226) =="
if python3 "$DIR/../tools/check_resources.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL resources — dane pakietu nie idą przez jeden punkt (resources.packaged_data_path), ai_linter/config rozjechały podłączenie albo nieznany plik nie daje błędu (patrz wyżej)"; fail=1
fi

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

echo "== Adaptery Stage 2: OpenAICompat + Ollama, parsowanie/fallback, load_stage2 (KAN-218) =="
if python3 "$DIR/../tools/check_engines.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL adaptery Stage 2 — mapowanie odpowiedzi na Judgement, fallback rewrite, atrybucja name, config stage2 lub fabryka silnika rozjechały się (patrz wyżej)"; fail=1
fi

echo "== Auto-offload poda RunPod: klient REST + managed_pod (3 warstwy) + load_lifecycle (KAN-220) =="
if python3 "$DIR/../tools/check_runpod_lifecycle.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL auto-offload — klient REST, teardown w finally/sygnale, idempotencja, on_finish, load_lifecycle lub NO-OP manage=false rozjechał się (patrz wyżej)"; fail=1
fi

echo "== Efemeryczny pod RunPod + flaga --runpod: create/terminate + bramka UX korektora (KAN-222) =="
if python3 "$DIR/../tools/check_runpod_ephemeral.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL efemeryczny pod / --runpod — managed_ephemeral_pod nie tworzy/terminuje (też przy wyjątku, osierocony pod), idempotencja teardownu, load_runpod (fallback/walidacja), build_ephemeral_runpod/build_runpod_engine albo bramka UX korektora (odmowa bez silnika) rozjechały się (patrz wyżej)"; fail=1
fi

echo "== Bramka write-time: blokuje tylko twarde blokery, sama gęstość NIE (F1) =="
if python3 "$DIR/../tools/check_write_gate.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL bramka write-time — gate_decision blokuje gęstość zamiast tylko twardych blokerów, albo opt-in/smoke rozjechał się (patrz wyżej)"; fail=1
fi

echo "== Bramka CI na MR: pełny werdykt na zmienionych plikach prozy (F2) =="
if python3 "$DIR/../tools/check_ci_gate.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL bramka CI — ci_gate przepuścił FAIL/gęstość, wywrócił się na braku plików prozy albo workflow zgubił krytyczne pola (patrz wyżej)"; fail=1
fi

echo "== Bramka przed publikacją: pełny werdykt Stage 1 plus opcjonalny osąd Stage 2 offline (F3) =="
if python3 "$DIR/../tools/check_publish_gate.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL bramka przed publikacją — publish_gate przepuścił FAIL/gęstość, Stage 2 ze stubem nie jest surowszy niż F2, błąd silnika nie dał exit 2, albo README zgubił sekcję F3 (patrz wyżej)"; fail=1
fi

echo "== Korektor G2: petla audyt -> poprawka -> ponowny audyt do PASS (zbieznosc / brak postepu / limit) =="
if python3 "$DIR/../tools/check_corrector.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL korektor G2 — petla nie zbiega do PASS na atrapie, nie zatrzymuje sie na braku postepu/limicie iteracji, zapis zwrotny rozjechal akapity albo kontrakt rewrite (domyslny no-op / atrapa korektora) pekl (patrz wyzej)"; fail=1
fi

echo "== Routing G3: lejek kosztowy (primary na masę, appellate na margines) + fabryka rekurencyjna =="
if python3 "$DIR/../tools/check_routing.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL routing G3 — eskalacja do apelacji na rewrite/trudnym, ufanie primary na łatwym (appellate niedotknięty), .name/.rewrite/delegacja albo fabryka z configu (rekurencja/zakaz zagnieżdżenia/walidacja) rozjechały się (patrz wyżej)"; fail=1
fi

echo "== LanguageTool G4: klient korekty na żądanie (parse /v2/check, form-encode, odporność) =="
if python3 "$DIR/../tools/check_languagetool.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL LanguageTool G4 — parsowanie matches na Suggestion, POST form-encoded text+language, Content-Type/User-Agent albo odporność na pusty/uszkodzony JSON rozjechały się (patrz wyżej)"; fail=1
fi

echo "== Eksporter metryk Prometheus: render serii + artefakty deploy (KAN-219) =="
if python3 "$DIR/../tools/check_metrics_exporter.py"; then
  : # OK — komunikat wypisuje sam skrypt
else
  echo "FAIL eksporter metryk — render_metrics zgubił HELP/TYPE, złamał format (etykiety/escaping/inwariant red+routed), pomylił mapowanie zdrowia OK/ALARM/N/A, źle agregował Stage 2, fail-soft przeciekł albo artefakty deploy (service/scrape/provider/dashboard) zgubiły krytyczne pola (patrz wyżej)"; fail=1
fi

if [[ $fail -eq 0 ]]; then
  echo "WSZYSTKIE TESTY PRZESZŁY."
else
  echo "REGRESJA WYKRYTA — popraw linter/taksonomię przed commitem."
fi
exit $fail
