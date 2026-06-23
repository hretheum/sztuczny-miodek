# -*- coding: utf-8 -*-
"""
resources.py — jeden punkt dostępu do plików DANYCH spakowanych z narzędziem.

Pakiet instalowalny (wheel / uvx, KAN-227): dane leżą w miodek/data/ i są czytane przez
importlib.resources, więc działają niezależnie od bieżącego katalogu i po instalacji jako
paczka. Reszta kodu (ai_linter, config) woła tylko `packaged_data_path` / `load_packaged_text`,
więc ta zmiana lokalizacji danych nie dotyka logiki lintera ani konfiguracji.

Granica: to są dane READ-ONLY pakietu. Pliki WYJŚCIOWE runtime (log decyzji decisions.jsonl,
manifesty) NIE należą tutaj — katalog pakietu bywa tylko do odczytu po instalacji, więc domyślny
zapis idzie do katalogu roboczego użytkownika (patrz decision_log.DEFAULT_LOG_PATH).

Narzędzia w tools/ (check_*, measure_*, gen_*) czytają dane wprost z repo — deweloperskie/CI,
działają z klonu, nie z wheela, więc świadomie pozostają poza tym punktem.

ZERO-DEP (stdlib).
"""

from importlib import resources as _res

_PKG = "miodek"
_DATA_DIR = "data"  # podkatalog z danymi wewnątrz pakietu


def _data_resource(name):
    """Traversable pliku danych pakietu (importlib.resources). Zip-bezpieczny uchwyt."""
    return _res.files(_PKG) / _DATA_DIR / name


def packaged_data_path(name):
    """Ścieżka bezwzględna (str) do pliku danych pakietu o nazwie `name` (np. 'rules.json').

    Liczona przez importlib.resources, więc niezależna od cwd i poprawna po instalacji jako
    paczka. Zwraca realną ścieżkę dla instalacji rozpakowanej (uvx, pip) — to nasz przypadek.
    Do samego wczytania treści preferuj `load_packaged_text` (działa też dla pakietu w zip).
    """
    return str(_data_resource(name))


def load_packaged_text(name):
    """Surowa zawartość (tekst UTF-8) pliku danych pakietu. Rzuca FileNotFoundError, gdy brak."""
    return _data_resource(name).read_text(encoding="utf-8")
