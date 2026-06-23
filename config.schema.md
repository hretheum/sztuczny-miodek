# Schemat `config.json` — progi i profile lintera (D1 / KAN-195)

`config.json` wynosi progi proceduralne lintera z literałów w kodzie do danych z PROFILAMI.
Parsowalny biblioteką standardową Pythona (moduł `json`) — bez zależności z pip (ZERO-DEP).

## Struktura

```json
{
  "active_profile": "default",
  "profiles": {
    "<nazwa>": { "opis": "...", "thresholds": { ... } }
  },
  "economy": { "routed_ratio_alarm": 0.10, "min_words": 200 }
}
```

- `active_profile` (string) — profil używany domyślnie (gdy linter wołany bez `--profile`).
- `profiles` (obiekt) — mapa nazwa→profil; każdy profil ma `opis` (string) i `thresholds` (obiekt).
- `economy` (obiekt, opcjonalny) — próg alarmu zdrowia ekonomii (E4); patrz sekcja niżej.

## Progi (`thresholds`) — wszystkie obowiązkowe, dodatnie liczby całkowite

| Klucz | Detektor | Znaczenie | Default |
|---|---|---|---|
| `emdash_per_paragraph` | em-dash overuse | ≥N myślników w akapicie → block | 3 |
| `bold_per_paragraph` | bold-overload | ≥N pogrubień w akapicie → review | 4 |
| `connector_overload_per_file` | nawał łączników | ≥N łączników-otwarć w pliku → block | 3 |
| `en_anti_series_per_file` | seria EN-ANTI | ≥N antytez EN w pliku → block | 2 |
| `pl_anti_series_per_file` | seria PL-ANTI | ≥N antytez PL w pliku → block | 3 |
| `density_per_500_words` | gęstość ważona | density > N → FAIL | 8 |

## Profile (bieżące)

- `default` — progi = stan historyczny (sprzed D1). **ZERO zmiany zachowania.**
- `luzny` — wyższe progi (mniej czuły; teksty swobodne).
- `ostry` — niższe progi (bardziej czuły; teksty formalne/CV).

## Zasady i fallback

- Brak `config.json` → linter używa `config.DEFAULT_THRESHOLDS` (= profil `default`). Bezpieczny fallback.
- `default` w `config.json` MUSI pokrywać się z `config.DEFAULT_THRESHOLDS` — pilnuje tego
  `tools/check_config.py` (gate w `run_tests.sh`).
- Nieznany profil / brak progu / wartość nie-całkowita lub < 1 → czytelny błąd (exit 2 z CLI).
- Wybór profilu: `python3 ai_linter.py --profile <nazwa> …` (nadpisuje `active_profile`).

## Sekcja `economy` — próg alarmu zdrowia ekonomii (E4)

Górna sekcja, **rodzeństwo `profiles`** (celowo poza `thresholds`, bo `load_thresholds` waliduje
dokładny zestaw kluczy progów i odrzuciłby nadmiarowe). Czytana osobną funkcją `config.load_economy`,
więc `load_thresholds` (D1) zostaje nietknięty.

| Klucz | Typ | Znaczenie | Default |
|---|---|---|---|
| `routed_ratio_alarm` | float w (0, 1] | alarm gdy `routed_ratio` (E1) > tego progu | 0.10 |
| `min_words` | int >= 0 | poniżej tylu słów łącznie nie alarmuj (za mała próbka) | 200 |

- Brak `config.json` lub brak sekcji `economy` → `config.DEFAULT_ECONOMY` (fallback, zero zmiany
  zachowania bez configu). Klucze obecne w configu nadpisują domyślne punktowo.
- Wartość niepoprawna (`routed_ratio_alarm` poza `(0, 1]`, `min_words` ujemny lub nie-całkowity) →
  czytelny błąd (`ValueError`).
- Konsument: `metrics.economy_health` i CLI `tools/measure_health.py` (exit 1 na `ALARM`).
  Odniesienie autora: `routed_ratio` ~4–5%; `0.10` = ~2x norma = sygnał regresji reguł.

## Styk z resztą systemu

- **B3 (kalibracja progów)**: metodyka z `docs/THRESHOLD-CALIBRATION.md` zakłada, że kalibracja na
  korpusie+logu (D4) zapisuje wynikowe progi do `config.json` (profil), nie do literałów w kodzie.
- **`prog` w `rules.json`**: progi proceduralne (config.json) ≠ deklaratywne (`prog` w regule regex).
  To dwa rozłączne nośniki „progów jako danych" — config dla detektorów proceduralnych, `prog` dla
  ewentualnych progów reguł regexowych.

## Diagnostyka

```bash
python3 config.py                    # progi aktywnego profilu
python3 config.py --profile ostry    # progi wskazanego profilu
```
