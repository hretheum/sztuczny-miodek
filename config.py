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


# ============================================================================
# KAN-218 — wybór silnika osądu Stage 2 (sekcja `stage2`, rodzeństwo `economy`).
# ============================================================================
#
# Sekcja `stage2` jest CELOWO poza `profiles` i `economy`: load_thresholds i load_economy
# walidują swoje sekcje i ignorują tę nową. Wybór silnika czytamy osobną funkcją
# load_stage2, więc load_thresholds (D1) i load_economy (E4) zostają nietknięte.
#
# Fallback (brak sekcji `stage2` lub brak configu) => {"engine": "stub"} → zero zmiany
# zachowania bez configu (runner i tak domyślnie buduje atrapę). Klucz API NIGDY w pliku —
# config trzyma tylko nazwę zmiennej środowiskowej (api_key_env); sekret czyta konstruktor
# silnika z os.environ. Separacja: config = CO, ENV = SEKRET.

DEFAULT_STAGE2 = {"engine": "stub"}

_STAGE2_ENGINES = ("stub", "openai", "ollama", "routing")
# Silniki nie-routujące (dozwolone jako primary/appellate w routingu — routing nie zagnieżdża się).
_STAGE2_LEAF_ENGINES = ("stub", "openai", "ollama")
# Klucze wymagane w podsłowniku konfiguracji dla każdego realnego silnika.
_STAGE2_REQUIRED = {
    "openai": ("base_url", "model"),
    "ollama": ("host", "model"),
}


def _validate_leaf_engine(sub, where):
    """Waliduje pod-config pojedynczego (nie-routującego) silnika — używane przez routing (G3).

    `sub` to dict o kształcie sekcji `stage2`: `engine` ∈ leaf + (dla openai/ollama) podsłownik
    z wymaganymi kluczami. `where` to etykieta do komunikatu błędu (np. "stage2.routing.primary").
    Zakaz `engine: "routing"` (routing jest jednopoziomowy — ochrona przed cyklem rekurencji)."""
    if not isinstance(sub, dict):
        raise ValueError(f"config.json: {where} musi być obiektem (pod-config silnika)")
    engine = sub.get("engine", "stub")
    if engine == "routing":
        raise ValueError(
            f"config.json: {where}.engine nie może być 'routing' "
            f"(routing jest jednopoziomowy — bez zagnieżdżania)"
        )
    if engine not in _STAGE2_LEAF_ENGINES:
        raise ValueError(
            f"config.json: {where}.engine musi być jednym z {_STAGE2_LEAF_ENGINES}, jest {engine!r}"
        )
    if engine in _STAGE2_REQUIRED:
        inner = sub.get(engine)
        if not isinstance(inner, dict):
            raise ValueError(
                f"config.json: {where}.engine={engine!r} wymaga sekcji '{where}.{engine}' (obiekt)"
            )
        missing = [k for k in _STAGE2_REQUIRED[engine] if not inner.get(k)]
        if missing:
            raise ValueError(f"config.json: {where}.{engine} — brakujące/puste klucze: {missing}")


def load_stage2(path: str = CONFIG_PATH) -> dict:
    """Zwraca konfigurację wyboru silnika Stage 2 (sekcja `stage2` configu).

    Brak configu albo brak sekcji `stage2` → DEFAULT_STAGE2 ({"engine": "stub"}): bezpieczny
    fallback, zero zmiany zachowania bez configu. Zwraca SUROWY dict konfiguracji (runner
    buduje z niego instancję silnika; ENV czyta dopiero konstruktor silnika, nie ta funkcja).

    Walidacja: `engine` ∈ {stub, openai, ollama}; dla openai/ollama wymagany podsłownik o tej
    nazwie z wymaganymi kluczami (openai: base_url+model; ollama: host+model). Brak → czytelny
    ValueError. Sekcje nieaktywnych silników nie są walidowane (to tylko parametry w rezerwie)."""
    if not os.path.exists(path):
        return dict(DEFAULT_STAGE2)
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"config.json: nie można wczytać: {e}")

    st = cfg.get("stage2")
    if st is None:
        return dict(DEFAULT_STAGE2)
    if not isinstance(st, dict):
        raise ValueError("config.json: sekcja 'stage2' musi być obiektem")

    engine = st.get("engine", "stub")
    if engine not in _STAGE2_ENGINES:
        raise ValueError(
            f"config.json: stage2.engine musi być jednym z {_STAGE2_ENGINES}, jest {engine!r}"
        )

    if engine in _STAGE2_REQUIRED:
        sub = st.get(engine)
        if not isinstance(sub, dict):
            raise ValueError(
                f"config.json: stage2.engine={engine!r} wymaga sekcji 'stage2.{engine}' (obiekt)"
            )
        missing = [k for k in _STAGE2_REQUIRED[engine] if not sub.get(k)]
        if missing:
            raise ValueError(
                f"config.json: stage2.{engine} — brakujące/puste klucze: {missing}"
            )

    # G3: routing wymaga podsekcji `routing` z `primary` i `appellate` (każdy to pod-config
    # nie-routującego silnika). Walidujemy rekurencyjnie przez _validate_leaf_engine, z zakazem
    # zagnieżdżonego routingu. `hard_hits_threshold` (jeśli obecny) musi być dodatnią liczbą całk.
    if engine == "routing":
        routing = st.get("routing")
        if not isinstance(routing, dict):
            raise ValueError(
                "config.json: stage2.engine='routing' wymaga sekcji 'stage2.routing' (obiekt)"
            )
        for role in ("primary", "appellate"):
            if role not in routing:
                raise ValueError(f"config.json: stage2.routing wymaga podsekcji '{role}'")
            _validate_leaf_engine(routing[role], f"stage2.routing.{role}")
        if "hard_hits_threshold" in routing and routing["hard_hits_threshold"] is not None:
            v = routing["hard_hits_threshold"]
            if isinstance(v, bool) or not isinstance(v, int) or v < 1:
                raise ValueError(
                    "config.json: stage2.routing.hard_hits_threshold musi być null albo dodatnią "
                    f"liczbą całkowitą, jest {v!r}"
                )

    return st


# ============================================================================
# KAN-220 — auto-offload poda RunPod (podsekcja `stage2.lifecycle`).
# ============================================================================
#
# Podsekcja `lifecycle` żyje WEWNĄTRZ sekcji `stage2` (rodzeństwo `openai`/`ollama`). Steruje
# automatycznym gaszeniem poda po przebiegu Stage 2 (managed_pod w runpod_lifecycle.py).
# Czytana OSOBNĄ funkcją load_lifecycle, więc load_thresholds (D1), load_economy (E4) i
# load_stage2 (KAN-218) zostają NIETKNIĘTE.
#
# Fallback (brak sekcji `lifecycle`, brak `stage2` lub brak configu) => {"manage": False}
# => NO-OP: runner NIE owija przebiegu, zero zmiany zachowania. To kluczowy wymóg bezpieczeństwa
# (domyślnie nikt nie gasi żadnego poda). Klucz API NIGDY w pliku — config trzyma tylko nazwę
# zmiennej środowiskowej (`api_key_env`); sekret czyta konstruktor klienta z os.environ.

DEFAULT_LIFECYCLE = {"manage": False}

_LIFECYCLE_ON_FINISH = ("stop", "terminate")


def load_lifecycle(path: str = CONFIG_PATH) -> dict:
    """Zwraca konfigurację auto-offloadu poda (podsekcja `stage2.lifecycle` configu).

    Brak configu, brak sekcji `stage2` albo brak podsekcji `lifecycle` → DEFAULT_LIFECYCLE
    ({"manage": False}): bezpieczny fallback, NO-OP, zero zmiany zachowania.

    Walidacja (tylko gdy `manage` jest prawdziwe — bo wtedy realnie ruszamy pod):
      - `pod_id` wymagany (niepusty string),
      - `on_finish` ∈ {stop, terminate} (domyślnie stop),
      - `idle_backstop_s` (jeśli obecny) dodatnia liczba całkowita.
    Gdy `manage=false` walidacji nie ma (sekcja może być szkicem w rezerwie). Zwraca surowy dict
    (runner buduje z niego klienta i menedżera kontekstu; ENV czyta dopiero konstruktor klienta)."""
    if not os.path.exists(path):
        return dict(DEFAULT_LIFECYCLE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"config.json: nie można wczytać: {e}")

    st = cfg.get("stage2")
    if not isinstance(st, dict):
        return dict(DEFAULT_LIFECYCLE)
    lc = st.get("lifecycle")
    if lc is None:
        return dict(DEFAULT_LIFECYCLE)
    if not isinstance(lc, dict):
        raise ValueError("config.json: sekcja 'stage2.lifecycle' musi być obiektem")

    manage = bool(lc.get("manage", False))
    if not manage:
        # NO-OP: nie walidujemy reszty (sekcja może być szkicem w rezerwie).
        return lc

    pod_id = lc.get("pod_id")
    if not isinstance(pod_id, str) or not pod_id:
        raise ValueError(
            "config.json: stage2.lifecycle.manage=true wymaga niepustego 'pod_id'"
        )

    on_finish = lc.get("on_finish", "stop")
    if on_finish not in _LIFECYCLE_ON_FINISH:
        raise ValueError(
            f"config.json: stage2.lifecycle.on_finish musi być jednym z "
            f"{_LIFECYCLE_ON_FINISH}, jest {on_finish!r}"
        )

    if "idle_backstop_s" in lc:
        v = lc["idle_backstop_s"]
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            raise ValueError(
                f"config.json: stage2.lifecycle.idle_backstop_s musi być dodatnią liczbą "
                f"całkowitą, jest {v!r}"
            )

    return lc


# ============================================================================
# KAN-222 — efemeryczny pod RunPod dla flagi --runpod (podsekcja `stage2.runpod`).
# ============================================================================
#
# Podsekcja `runpod` żyje WEWNĄTRZ `stage2` (rodzeństwo `lifecycle`). Trzyma parametry, z których
# flaga --runpod stawia EFEMERYCZNY pod (managed_ephemeral_pod): wolumen sieciowy (model), DC,
# model, GPU, mount, obraz. Czytana OSOBNĄ funkcją load_runpod — load_thresholds/economy/stage2/
# lifecycle zostają NIETKNIĘTE.
#
# Domyślne = wartości z launchera tools/runpod_pod_up.py (wolumen i model jak w przykładzie użycia),
# więc bez configu flaga --runpod działa „od ręki". Klucz API NIGDY w pliku — config trzyma tylko
# nazwę ENV (`api_key_env`); sekret czyta konstruktor klienta/menedżera z os.environ.

DEFAULT_RUNPOD = {
    "volume": "5lb05arqur",
    "dc": "EU-NL-1",
    "mount": "/root/.ollama",
    "image": "ollama/ollama:latest",
    "model": "hf.co/speakleash/Bielik-11B-v3.0-Instruct-GGUF:Q4_K_M",
    "name": "miodek-bielik",
    "api_key_env": "RUNPOD_API_KEY",
    "base_url": "https://rest.runpod.io/v1",
}


def load_runpod(path: str = CONFIG_PATH) -> dict:
    """Zwraca konfigurację efemerycznego poda dla --runpod (podsekcja `stage2.runpod`).

    Brak configu, brak sekcji `stage2` albo brak podsekcji `runpod` → DEFAULT_RUNPOD (bezpieczny
    fallback = wartości launchera). Klucze obecne w configu nadpisują domyślne PUNKTOWO (tolerancyjnie,
    spójnie z load_economy): operator może podać tylko `volume`+`dc`, reszta z domyślnych.

    Walidacja kluczy load-bearing (bez nich nie da się postawić poda): `volume`, `dc`, `model`
    muszą być niepustymi stringami. `gpu` (jeśli obecny) musi być listą stringów. Niepoprawne →
    czytelny ValueError. Zwraca surowy scalony dict (menedżer buduje z niego managed_ephemeral_pod;
    ENV czyta dopiero konstruktor)."""
    out = dict(DEFAULT_RUNPOD)
    if not os.path.exists(path):
        return out
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"config.json: nie można wczytać: {e}")

    st = cfg.get("stage2")
    if not isinstance(st, dict):
        return out
    rp = st.get("runpod")
    if rp is None:
        return out
    if not isinstance(rp, dict):
        raise ValueError("config.json: sekcja 'stage2.runpod' musi być obiektem")

    # Scal punktowo (pomijamy klucz informacyjny `opis`).
    for k, v in rp.items():
        if k == "opis":
            continue
        out[k] = v

    for k in ("volume", "dc", "model"):
        v = out.get(k)
        if not isinstance(v, str) or not v:
            raise ValueError(
                f"config.json: stage2.runpod.{k} musi być niepustym stringiem, jest {v!r}"
            )
    if "gpu" in out and out["gpu"] is not None:
        g = out["gpu"]
        if not isinstance(g, list) or not all(isinstance(x, str) for x in g):
            raise ValueError(
                f"config.json: stage2.runpod.gpu musi być listą stringów, jest {g!r}"
            )

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
