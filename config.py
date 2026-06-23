#!/usr/bin/env python3
"""
config.py — progi i profile lintera jako KONFIGURACJA (Epik D, D1 / KAN-195).

Wynosi progi proceduralne (em-dash, bold, connector, serie ANTI, gęstość) z literałów w kodzie
do pliku danych config.json z PROFILAMI (default / luzny / ostry). Parsowalne stdlib (moduł json,
ZERO-DEP). Domyślny profil = stan historyczny → ZERO zmiany zachowania bez configu / z profilem default.

Styk z B3 (metodyka kalibracji): kalibracja na korpusie+logu (D4) zapisuje wyniki do tego pliku
(profil/progi), zamiast edytować literały w kodzie. Styk z rules.json (pole `prog`): progi
proceduralne ≠ deklaratywne — `prog` w rules.json dotyczy reguł regex z progiem, config.json
dotyczy detektorów proceduralnych; oba to „progi jako dane".

API:
  load_thresholds(profile=None, path=CONFIG_PATH) -> dict (klucz→wartość progu).
  load_economy(path=CONFIG_PATH)  -> dict (próg alarmu ekonomii E4; górna sekcja `economy`).
"""

import json
import os
import sys

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Domyślne progi = stan historyczny (sprzed D1). Używane gdy config.json nie istnieje LUB jako
# źródło prawdy kluczy/walidacji. MUSZĄ pokrywać się z profilem „default" w config.json.
DEFAULT_THRESHOLDS = {
    "emdash_per_paragraph": 3,
    "bold_per_paragraph": 4,
    "connector_overload_per_file": 3,
    "en_anti_series_per_file": 2,
    "pl_anti_series_per_file": 3,
    "density_per_500_words": 8,
}

_REQUIRED_KEYS = frozenset(DEFAULT_THRESHOLDS)


def load_thresholds(profile: str = None, path: str = CONFIG_PATH) -> dict:
    """Zwraca progi dla profilu. Brak configu → DEFAULT_THRESHOLDS (zero zmiany zachowania).

    `profile=None` → użyj `active_profile` z configu (domyślnie „default"). Nieznany profil lub
    brak wymaganego progu → czytelny błąd (exit 2 przy wywołaniu z CLI; tu ValueError).
    Walidacja: wartości muszą być dodatnimi liczbami całkowitymi, klucze = pełny zestaw progów.
    """
    if not os.path.exists(path):
        return dict(DEFAULT_THRESHOLDS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"config.json: nie można wczytać: {e}")

    profiles = cfg.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("config.json: brak sekcji 'profiles' lub pusta")

    prof = profile or cfg.get("active_profile", "default")
    if prof not in profiles:
        raise ValueError(
            f"config.json: nieznany profil {prof!r} (dostępne: {sorted(profiles)})"
        )

    thresholds = profiles[prof].get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError(f"config.json: profil {prof!r} bez sekcji 'thresholds'")

    missing = _REQUIRED_KEYS - set(thresholds)
    if missing:
        raise ValueError(f"config.json: profil {prof!r} — brakujące progi: {sorted(missing)}")

    out = {}
    for k in _REQUIRED_KEYS:
        v = thresholds[k]
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise ValueError(f"config.json: próg {k} musi być dodatnią liczbą całkowitą, jest {v!r}")
        out[k] = v
    return out


# ============================================================================
# E4 — próg alarmu zdrowia ekonomii (sekcja `economy`, rodzeństwo `profiles`).
# ============================================================================
#
# Sekcja `economy` jest CELOWO poza `profiles[*].thresholds`: load_thresholds
# waliduje DOKŁADNY zestaw kluczy progów i odrzuciłby nadmiarowe. Próg E4 czytamy
# osobną funkcją, więc load_thresholds zostaje nietknięty (zero ryzyka regresji D1).
#
# Fallback (brak sekcji `economy` lub brak configu) = wartości domyślne →
# zero zmiany zachowania bez configu, spójnie z konwencją load_thresholds.

DEFAULT_ECONOMY = {
    # Alarm gdy udział treści routowanej (routed_ratio z E1) przekracza ten próg.
    # Odniesienie autora: 0.04–0.05; 0.10 = ~2x norma = sygnał regresji reguł / lintera.
    "routed_ratio_alarm": 0.10,
    # Poniżej tylu słów łącznie nie alarmuj (próbka za mała na wiarygodny wskaźnik).
    "min_words": 200,
}


def load_economy(path: str = CONFIG_PATH) -> dict:
    """Zwraca próg alarmu zdrowia ekonomii (E4) z sekcji `economy` configu.

    Zwraca {"routed_ratio_alarm": float, "min_words": int}. Brak configu albo brak sekcji
    `economy` → DEFAULT_ECONOMY (bezpieczny fallback, zero zmiany zachowania bez configu).
    Nadpisuje tylko klucze obecne w configu; reszta z domyślnych (tolerancyjnie, bo to raport
    diagnostyczny, nie twarda walidacja jak progi).

    Walidacja wartości obecnych w configu: `routed_ratio_alarm` w (0, 1], `min_words` >= 0.
    Wartość niepoprawna → czytelny ValueError.
    """
    out = dict(DEFAULT_ECONOMY)
    if not os.path.exists(path):
        return out
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"config.json: nie można wczytać: {e}")

    econ = cfg.get("economy")
    if econ is None:
        return out
    if not isinstance(econ, dict):
        raise ValueError("config.json: sekcja 'economy' musi być obiektem")

    if "routed_ratio_alarm" in econ:
        v = econ["routed_ratio_alarm"]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not (0.0 < v <= 1.0):
            raise ValueError(
                f"config.json: economy.routed_ratio_alarm musi być liczbą w (0, 1], jest {v!r}"
            )
        out["routed_ratio_alarm"] = float(v)

    if "min_words" in econ:
        v = econ["min_words"]
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError(
                f"config.json: economy.min_words musi być nieujemną liczbą całkowitą, jest {v!r}"
            )
        out["min_words"] = v

    return out


def _main():
    """CLI: wypisz progi aktywnego/wskazanego profilu (diagnostyka). --profile <nazwa>."""
    profile = None
    if "--profile" in sys.argv:
        profile = sys.argv[sys.argv.index("--profile") + 1]
    try:
        th = load_thresholds(profile)
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(th, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
