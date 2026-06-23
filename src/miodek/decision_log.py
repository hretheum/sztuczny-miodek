#!/usr/bin/env python3
"""
decision_log.py — log decyzji accept/reject (Epik D, D4 / KAN-198).

Append-only log w formacie JSONL (jedna decyzja = jedna linia JSON). Każdy wpis łączy TRAFIENIE
lintera (albo wartość metryki progowej) z WERDYKTEM operatora:
  - accept — trafienie słuszne (prawdziwy AI-tell / przekroczony próg zasadnie),
  - reject — false-positive (operator odrzuca; termin do słownika / próg do rekalibracji).

To SUROWIEC zasilający:
  - D3 (build-dict): terminy z reject → kandydaci do `allow` w słowniku domenowym,
  - B3 (kalibracja progów): pary (wartość_metryki, werdykt) → krzywa precyzja/recall po progu
    (metodyka z docs/THRESHOLD-CALIBRATION.md — D4 ODBLOKOWUJE pełną kalibrację).

Format JSONL (ZERO-DEP, stdlib json), spójny z D1/D2 (JSON). Append-only: nigdy nie nadpisuje,
tylko dokleja — historia decyzji jest niezmienna (audyt). Miejsce: domyślnie `decisions.jsonl`
w katalogu roboczym użytkownika (konfigurowalne ścieżką). To plik WYJŚCIOWY, nie dane pakietu —
nie zapisujemy go obok kodu, bo katalog pakietu bywa tylko do odczytu po instalacji (KAN-227).

Schemat wpisu:
  {
    "ts": "2026-06-23T10:00:00Z",   # znacznik czasu (ISO 8601 UTC); podawany przez wołającego
    "verdict": "accept" | "reject",  # decyzja operatora
    "id": "EN-CLICHE",               # ID markera (lub metryki progowej, np. "density")
    "klasa": "review" | "block",     # klasa trafienia
    "fragment": "robust",            # dopasowany fragment / wartość metryki
    "file": "doc.md",                # plik źródłowy (opcjonalny)
    "line": 12,                       # linia (opcjonalna)
    "profile": "default",            # profil progów aktywny przy decyzji (opcjonalny; styk z D1)
    "metric_value": 4                 # wartość metryki progowej, jeśli dotyczy (opcjonalny; styk z B3)
  }

API: append_decision(entry, path) ; read_decisions(path) -> List[dict] ; CLI do dopisywania.
"""

import json
import os
import sys

# Plik WYJŚCIOWY: domyślnie w katalogu roboczym użytkownika (ścieżka względna → cwd przy zapisie).
# Katalog pakietu bywa read-only po instalacji (wheel/uvx), więc NIE zapisujemy obok kodu (KAN-227).
DEFAULT_LOG_PATH = "decisions.jsonl"

VERDICTS = ("accept", "reject")
# Pola obowiązkowe każdego wpisu (minimum, by wpis był użyteczny dla D3/B3).
_REQUIRED = ("ts", "verdict", "id", "fragment")


def validate_entry(entry: dict) -> None:
    """Waliduje wpis decyzji. ValueError z czytelnym komunikatem na błędzie."""
    if not isinstance(entry, dict):
        raise ValueError(f"wpis decyzji musi być obiektem, jest {type(entry).__name__}")
    for k in _REQUIRED:
        if k not in entry or entry[k] in (None, ""):
            raise ValueError(f"wpis decyzji: brak wymaganego pola '{k}'")
    if entry["verdict"] not in VERDICTS:
        raise ValueError(f"wpis decyzji: verdict musi być jednym z {VERDICTS}, jest {entry['verdict']!r}")


def append_decision(entry: dict, path: str = DEFAULT_LOG_PATH) -> None:
    """Dokleja JEDEN wpis decyzji do logu JSONL (append-only). Waliduje przed zapisem.

    Append-only: otwarcie w trybie 'a' — nigdy nie nadpisuje istniejących wpisów. Każdy wpis to
    jedna linia JSON (ensure_ascii=False — pełne diakrytyki) zakończona '\\n'."""
    validate_entry(entry)
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_decisions(path: str = DEFAULT_LOG_PATH) -> list:
    """Czyta log JSONL → lista wpisów (dict). Brak pliku → []. Pomija puste linie.

    Niepoprawna linia JSON → ValueError (z numerem linii) — log ma być spójny dla D3/B3."""
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for i, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}: niepoprawny JSON w linii {i}: {e}")
    return out


def _main(argv=None):
    """CLI: dopisz decyzję do logu.

    Użycie:
        python3 decision_log.py --verdict accept|reject --id ID --fragment FRAG --ts TS
            [--klasa K] [--file F] [--line N] [--profile P] [--metric-value V] [--log ŚCIEŻKA]
    """
    import argparse
    ap = argparse.ArgumentParser(description="Dopisz decyzję accept/reject do logu JSONL (D4).")
    ap.add_argument("--verdict", required=True, choices=VERDICTS)
    ap.add_argument("--id", required=True, dest="mid")
    ap.add_argument("--fragment", required=True)
    ap.add_argument("--ts", required=True, help="Znacznik czasu ISO 8601 UTC (podaj jawnie).")
    ap.add_argument("--klasa", default=None)
    ap.add_argument("--file", default=None, dest="src_file")
    ap.add_argument("--line", type=int, default=None)
    ap.add_argument("--profile", default=None)
    ap.add_argument("--metric-value", default=None, dest="metric_value")
    ap.add_argument("--log", default=DEFAULT_LOG_PATH)
    args = ap.parse_args(argv)

    entry = {"ts": args.ts, "verdict": args.verdict, "id": args.mid, "fragment": args.fragment}
    for key, val in (("klasa", args.klasa), ("file", args.src_file), ("line", args.line),
                     ("profile", args.profile), ("metric_value", args.metric_value)):
        if val is not None:
            entry[key] = val
    try:
        append_decision(entry, args.log)
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(2)
    print(f"Dopisano decyzję ({args.verdict} {args.mid}) do {args.log}")


if __name__ == "__main__":
    _main()
