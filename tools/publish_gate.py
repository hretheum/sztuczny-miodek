#!/usr/bin/env python3
"""
publish_gate.py — bramka przed publikacją (F3). ZERO-DEP (stdlib).

Sens: najsurowsza z trzech bramek. WYMIENNY KROK, który inny przepływ publikacji (wysyłka prozy
na Confluence/Notion/stronę) woła PRZED publikacją na JAWNIE wskazanych plikach „do publikacji",
żeby zatrzymać tekst nieprzechodzący jakości. Dwa poziomy:

  Stage 1 (ZAWSZE): pełny werdykt lintera na podanych plikach. Jak F2 (ci_gate), ale na jawnych
    plikach, nie na diffie. FAIL/FAIL-HARD (blokery LUB gęstość) => publikacja zablokowana.
  Stage 2 (OPCJONALNIE, tylko z --stage2): osąd modelu na segmentach review przez runner.
    Bramka „PASS z uwagami to NIE PASS": jakikolwiek werdykt „rewrite" => publikacja zablokowana.

Różnica wobec dwóch pozostałych bramek (NIE pomyl polityk):
  - F1 (hooks/miodek_write_gate.py, write-time): tylko twarde blokery, gęstość przechodzi,
    opt-in; zakres: zapisywany plik. Polityka „nie przeszkadzaj w pisaniu".
  - F2 (tools/ci_gate.py, CI na MR): pełny werdykt Stage 1; zakres: pliki prozy zmienione w PR
    (diff base...HEAD).
  - F3 (ten plik, pre-publish): pełny werdykt Stage 1 PLUS opcjonalny osąd Stage 2; zakres:
    jawnie wskazane pliki „do publikacji". Najsurowsza, bo jako JEDYNA może dołożyć model.

REUŻYCIE (ZERO duplikacji logiki):
  - Stage 1 reużywa ci_gate.filter_prose + ci_gate.run_linter (ta sama polityka pełnego werdyktu
    co F2, na jawnych plikach). Kody wyjścia lintera niosą semantykę: 0=PASS, 1=FAIL/FAIL-HARD,
    2=błąd reguł.
  - Manifest dla Stage 2 to ai_linter.py --format json (kontrakt, którego oczekuje runner).
  - Stage 2 reużywa runner.build_engine_from_config (wybór silnika z configu, KAN-218) oraz
    runner.run_stage2_managed (osąd + auto-offload poda RunPod, KAN-220). F3 z nich KORZYSTA,
    nie reimplementuje wyboru silnika ani gaszenia poda.

DOMYŚLNIE WYŁĄCZONY STAGE 2 (twardy wymóg, zero sieci):
  - Bez --stage2: F3 NIGDY nie buduje silnika ani nie woła run_stage2 — sam Stage 1, zero importu
    sieci, zero ryzyka.
  - Z --stage2 ale domyślnym configiem (stage2.engine == "stub"): buduje się StubJudgeEngine
    (deterministyczna, bez sieci). Czyli nawet z włączonym Stage 2 domyślny config daje osąd
    OFFLINE na atrapie — realny endpoint wymaga jawnej zmiany config.json na openai/ollama lub
    flagi --engine. „Bez żywego endpointu/configu => sam Stage 1" w sensie: bez sieci nawet przy
    włączonym Stage 2.

Kody wyjścia (najsurowsza polityka):
  0 — brak prozy LUB Stage 1 PASS i (Stage 2 wyłączony LUB gate PASS),
  1 — Stage 1 FAIL/FAIL-HARD (blokery/gęstość) LUB Stage 2 gate FAIL (jakiś „rewrite"),
  2 — błąd reguł/konfiguracji lintera (linter exit 2) LUB błąd budowy silnika (ValueError)
      LUB niepoprawny manifest JSON. Bramka jakości nie zazielenia się po cichu na błędzie.
"""

import argparse
import json
import os
import subprocess
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
# Importy z korzenia repo (runner, config) i z tego katalogu (ci_gate).
for _p in (_REPO_ROOT, _THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ci_gate  # noqa: E402  (filter_prose, run_linter, LINTER — Stage 1 = ta sama polityka co F2)
import runner  # noqa: E402  (build_engine_from_config, run_stage2_managed — Stage 2)
import config  # noqa: E402  (CONFIG_PATH — domyślna ścieżka configu sekcji stage2)

REPO_ROOT = _REPO_ROOT
LINTER = ci_gate.LINTER


def build_manifest(files, lang, profile, dict_path):
    """Buduje manifest Stage 2: ai_linter.py --format json na podanych plikach.

    Linter na plikach z trafieniami review zwraca exit 1 — to SPODZIEWANE (nie błąd: nas interesuje
    JSON manifestu, nie kod). Exit 2 = błąd reguł/konfiguracji => podnosimy RuntimeError (F3 kończy
    exit 2). Zwraca dict {"hits":[...], "summary":[...]} — kontrakt runnera."""
    cmd = [sys.executable, LINTER, "--lang", lang, "--format", "json"]
    if profile:
        cmd += ["--profile", profile]
    if dict_path:
        cmd += ["--dict", dict_path]
    cmd += files
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 2:
        raise RuntimeError(
            "linter --format json zwrócił exit 2 (błąd reguł/konfiguracji): "
            + (proc.stderr.strip() or "brak szczegółów")
        )
    try:
        return json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError) as e:
        raise RuntimeError(f"niepoprawny manifest JSON z lintera: {e}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Bramka przed publikacją (F3): pełny werdykt lintera (Stage 1, zawsze) plus "
                    "opcjonalny osąd modelu (Stage 2, --stage2) na jawnie wskazanych plikach prozy.",
        epilog="Exit 0 = brak prozy lub Stage 1 PASS i (Stage 2 OFF lub gate PASS); "
               "1 = Stage 1 FAIL/FAIL-HARD lub Stage 2 gate FAIL; "
               "2 = błąd reguł/konfiguracji lintera lub budowy silnika lub manifestu.",
    )
    parser.add_argument(
        "paths", nargs="*", metavar="PLIK",
        help="Jawne ścieżki plików prozy DO PUBLIKACJI (.md/.txt).",
    )
    parser.add_argument("--lang", default="both", choices=["pl", "en", "both"],
                        help="Język markerów przekazany do lintera (domyślnie both).")
    parser.add_argument("--profile", default=None,
                        help="Profil progów przekazany do lintera (opcjonalnie).")
    parser.add_argument("--dict", default=None, dest="dict_path",
                        help="Słownik domenowy przekazany do lintera (opcjonalnie).")
    parser.add_argument(
        "--stage2", action="store_true",
        help="Włącz Stage 2 (osąd modelu na segmentach review). DOMYŚLNIE WYŁĄCZONE — bez tej "
             "flagi F3 robi sam Stage 1 (zero sieci). Silnik z config.json (sekcja stage2; "
             "domyślnie stub = offline).",
    )
    parser.add_argument(
        "--engine", default=None, choices=("stub", "openai", "ollama"),
        help="Nadpisz silnik Stage 2 z CLI (domyślnie czytany z config.json). 'openai'/'ollama' "
             "wymagają sieci — świadomy wybór operatora.",
    )
    parser.add_argument("--config", default=config.CONFIG_PATH,
                        help="Ścieżka do config.json (sekcja stage2). Domyślnie config repo.")
    parser.add_argument(
        "--runpod", action="store_true",
        help="KAN-222: jeden krok zamiast ręcznej sekwencji. Włącza Stage 2 i osądza na "
             "EFEMERYCZNYM podzie RunPod (parametry stage2.runpod): postaw pod z wolumenu, "
             "osądź realnym Bielikiem (Ollama), zgaś pod automatycznie. Nadpisuje --engine i "
             "lifecycle. Wymaga RUNPOD_API_KEY w ENV.",
    )
    args = parser.parse_args(argv)

    files = ci_gate.filter_prose(args.paths)
    if not files:
        # Nic do publikacji = przejście. Bramka nie wywraca pustego zakresu (jak ci_gate).
        print("[publish_gate] Brak plików prozy w zakresie. Nic do publikacji — bramka przepuszcza "
              "(exit 0).")
        return 0

    print(f"[publish_gate] Bramka przed publikacją na {len(files)} plik(ach) prozy:")
    for f in files:
        print(f"  - {os.path.relpath(f, REPO_ROOT)}")
    print()

    # --- Stage 1: pełny werdykt lintera (ZAWSZE), ta sama polityka co F2. ---
    print("[publish_gate] Stage 1 — pełny werdykt lintera:")
    rc1 = ci_gate.run_linter(files, args.lang, args.profile, args.dict_path)
    print()
    if rc1 == 2:
        print("[publish_gate] BŁĄD reguł/konfiguracji lintera (exit 2). "
              "PUBLIKACJA WSTRZYMANA — bramka jakości nie zazielenia się na błędzie (exit 2).")
        return 2
    if rc1 == 1:
        print("[publish_gate] Stage 1: FAIL — blokery LUB gęstość ponad próg. "
              "PUBLIKACJA ZABLOKOWANA — Stage 1 (exit 1). Stage 2 pominięty (nie marnujemy modelu "
              "na tekst nieprzechodzący lintera).")
        return 1
    print("[publish_gate] Stage 1: PASS.")

    # --- Stage 2: opcjonalny osąd modelu (tylko z --stage2 LUB --runpod). ---
    # KAN-222: --runpod sam włącza Stage 2 (efemeryczny pod ma sens tylko dla osądu modelu).
    if not args.stage2 and not args.runpod:
        print("[publish_gate] Stage 2 wyłączony (brak --stage2). "
              "PUBLIKACJA DOZWOLONA — Stage 1 PASS (exit 0).")
        return 0

    print()
    print("[publish_gate] Stage 2 — osąd modelu na segmentach review:")
    try:
        manifest = build_manifest(files, args.lang, args.profile, args.dict_path)
    except RuntimeError as e:
        print(f"[publish_gate] BŁĄD manifestu Stage 2: {e}. PUBLIKACJA WSTRZYMANA (exit 2).")
        return 2

    if args.runpod:
        # KAN-222: efemeryczny pod SAM owija przebieg (create→...→terminate). Wewnątrz wołamy
        # CZYSTY run_stage2 na realnym Bieliku. Pod gaśnie automatycznie po osądzie.
        try:
            with runner.build_ephemeral_runpod(args.config) as pod:
                engine = runner.build_runpod_engine(args.config, pod=pod)
                result = runner.run_stage2(manifest, engine=engine)
        except ValueError as e:
            print(f"[publish_gate] BŁĄD konfiguracji efemerycznego poda: {e}. "
                  "PUBLIKACJA WSTRZYMANA (exit 2).")
            return 2
    else:
        try:
            engine = runner.build_engine_from_config(name=args.engine, config_path=args.config)
        except ValueError as e:
            # Np. openai bez base_url/model w config.json — świadomy błąd konfiguracji, zero sieci.
            print(f"[publish_gate] BŁĄD budowy silnika Stage 2: {e}. PUBLIKACJA WSTRZYMANA (exit 2).")
            return 2

        # run_stage2_managed: osąd + auto-offload poda RunPod (KAN-220) dla silników zdalnych.
        # Za atrapą/lokalnym silnikiem to czysty run_stage2 (NO-OP lifecycle), zero sieci.
        result = runner.run_stage2_managed(manifest, engine=engine, config_path=args.config)

    for seg in result["segments"]:
        ids = ", ".join(str(i) for i in seg["hit_ids"])
        print(f"  [{seg['verdict']:>7}] {seg['file']}:{seg['line']} ({ids}) — {seg['notes']}")
    print(f"[publish_gate] Stage 2 (silnik: {result['engine']}): osądzono {result['judged']} "
          f"segmentów review → rewrite {result['rewrite']}, pass {result['pass']} "
          f"→ BRAMKA: {result['gate']}")

    if result["gate"] == "FAIL":
        print("[publish_gate] PUBLIKACJA ZABLOKOWANA — Stage 2 (rewrite). "
              "Bramka „PASS z uwagami to NIE PASS”: jakikolwiek segment do przepisania "
              "zamyka publikację (exit 1).")
        return 1

    print("[publish_gate] PUBLIKACJA DOZWOLONA — Stage 1 PASS i Stage 2 gate PASS (exit 0).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
