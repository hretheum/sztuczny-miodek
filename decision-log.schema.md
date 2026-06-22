# Log decyzji accept/reject (D4 / KAN-198)

Append-only log w formacie **JSONL** (jedna decyzja = jedna linia JSON), łączący TRAFIENIE lintera
(albo wartość metryki progowej) z WERDYKTEM operatora. Surowiec zasilający D3 (słownik) i B3
(kalibracja progów). Moduł: `decision_log.py`. ZERO-DEP (stdlib `json`).

## Po co

- **reject** = false-positive: operator odrzuca trafienie → termin trafia do kandydatów `allow`
  słownika domenowego (D3/D2), próg do rekalibracji (B3).
- **accept** = trafienie słuszne: prawdziwy AI-tell / próg przekroczony zasadnie → potwierdza regułę.

To domyka pętlę uczenia: linter flaguje → operator decyduje → log gromadzi → D3/B3 rekalibrują.

## Format wpisu (JSONL)

Każda linia to obiekt JSON. Pola obowiązkowe: `ts`, `verdict`, `id`, `fragment`.

| Pole | Typ | Obow. | Znaczenie |
|---|---|---|---|
| `ts` | string | tak | znacznik czasu ISO 8601 UTC (podawany jawnie przez wołającego — brak `Date` w środowisku) |
| `verdict` | `"accept"`\|`"reject"` | tak | decyzja operatora |
| `id` | string | tak | ID markera (`EN-CLICHE`, `PL-SIGN`…) lub metryki progowej (`density`, `emdash`) |
| `fragment` | string | tak | dopasowany fragment (termin) lub wartość metryki jako tekst |
| `klasa` | `"review"`\|`"block"` | nie | klasa trafienia |
| `file` | string | nie | plik źródłowy |
| `line` | int | nie | numer linii |
| `profile` | string | nie | profil progów aktywny przy decyzji (styk z D1) |
| `metric_value` | int/number | nie | wartość metryki progowej (styk z B3 — krzywa precyzja/recall po progu) |

Przykład (3 linie):
```
{"fragment": "robust", "id": "EN-CLICHE", "klasa": "review", "ts": "2026-06-23T10:00:00Z", "verdict": "reject"}
{"fragment": "warto podkreślić", "id": "PL-SIGN", "ts": "2026-06-23T10:01:00Z", "verdict": "accept"}
{"fragment": "9.0", "id": "density", "metric_value": 9, "ts": "2026-06-23T10:02:00Z", "verdict": "reject"}
```

## Miejsce zapisu

- Domyślnie: `decisions.jsonl` w katalogu repo (`decision_log.DEFAULT_LOG_PATH`). Konfigurowalne
  ścieżką (`--log` / argument `path`).
- **Nie wersjonowany**: `decisions.jsonl` jest w `.gitignore` — to dane runtime (decyzje operatora),
  nie kod. Append-only (tryb `a`): historia niezmienna, audytowalna.

## API

- `append_decision(entry, path=DEFAULT_LOG_PATH)` — dokleja jeden wpis (waliduje przed zapisem).
- `read_decisions(path=DEFAULT_LOG_PATH) -> list[dict]` — czyta log; brak pliku → `[]`; niepoprawna
  linia → `ValueError` z numerem linii.

## CLI

```bash
python3 decision_log.py --verdict reject --id EN-CLICHE --fragment robust \
    --klasa review --file doc.md --line 12 --ts 2026-06-23T10:00:00Z
```

## Styk z resztą Epiku

- **D3 (build-dict)**: terminy z `reject` (z `klasa`) → kandydaci do `allow`. `read_decisions`
  daje listę do filtra (zamiast/obok korpusu).
- **B3 (kalibracja progów)**: pary `(id, metric_value, verdict)` → krzywa precyzja/recall po progu
  (metodyka `docs/THRESHOLD-CALIBRATION.md`). D4 ODBLOKOWUJE pełną kalibrację, która w B3 była
  niewykonalna z braku logu.
- **D1 (profile)**: pole `profile` wiąże decyzję z aktywnym profilem progów (kalibracja per profil).
