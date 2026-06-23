# -*- coding: utf-8 -*-
"""
resources.py — jeden punkt dostępu do plików DANYCH spakowanych z narzędziem.

Warunek wstępny pakietyzacji (wheel / uvx, KAN-226). Dziś moduły leżą flat, a pliki danych
(rules.json, config.json) obok nich; ścieżka liczona względem TEGO pliku, żeby narzędzie
działało wołane z dowolnego katalogu. Gdy w KAN-227 powstanie pakiet instalowalny, podmienimy
implementację TUTAJ — w jednym miejscu — na importlib.resources; reszta kodu (ai_linter, config)
nie drgnie, bo woła tylko `packaged_data_path` / `load_packaged_text`.

Granica: to są dane READ-ONLY pakietu. Pliki WYJŚCIOWE runtime (log decyzji decisions.jsonl,
manifesty) NIE należą tutaj — po instalacji jako paczka katalog bywa tylko do odczytu, więc
domyślny zapis musi iść do katalogu roboczego użytkownika, a nie obok kodu (do domknięcia w KAN-227).

Zakres KAN-226: przez ten punkt idą wyłącznie moduły RUNTIME wchodzące do paczki CLI (ai_linter,
config). Narzędzia w tools/ (check_*, measure_*, gen_*) czytają dane wprost z katalogu repo —
to deweloperskie/CI, działają z klonu, nie z wheela, więc świadomie pozostają poza tym punktem.

ZERO-DEP (stdlib).
"""

import os

# Katalog z danymi pakietu. Dziś = katalog tego modułu (flat layout). W KAN-227 ten szczegół
# zniknie za importlib.resources.files(__package__).
_DATA_DIR = os.path.dirname(os.path.abspath(__file__))


def packaged_data_path(name):
    """Ścieżka bezwzględna do pliku danych pakietu o nazwie `name` (np. 'rules.json').

    Nie sprawdza istnienia — to robi wywołujący przy otwarciu (zachowuje dotychczasową obsługę
    błędów w ai_linter/config). Zwraca ścieżkę liczoną względem modułu, więc niezależną od cwd.
    """
    return os.path.join(_DATA_DIR, name)


def load_packaged_text(name):
    """Surowa zawartość (tekst UTF-8) pliku danych pakietu. Rzuca, gdy pliku brak."""
    with open(packaged_data_path(name), "r", encoding="utf-8") as f:
        return f.read()
