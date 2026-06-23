#!/usr/bin/env python3
"""
dictionary.py — słownik domenowy per projekt jako warstwa nadrzędna terminów (Epik D, D2 / KAN-196).

Z analizy 03 (warstwa terminologii domenowej z SKILL.md): pewne terminy branżowe wyglądają jak
AI-tell, ale w danej dziedzinie są poprawne/nieuniknione (np. „robust" jako nazwa produktu,
„leverage" w finansach). Słownik pozwala je OZNACZYĆ, by linter ich nie flagował (allow) lub
flagował tylko do przeglądu (review). To warstwa NADRZĘDNA: gdy słownik mówi „allow", trafienie
markera na ten termin jest pomijane.

Format (JSON, stdlib, ZERO-DEP; spójny z D1 config.json):
  {
    "provenance": { "projekt": "...", "wersja": "...", "data": "...", "autor": "...", "zrodlo": "..." },
    "allow":  ["termin", ...],   # terminy NIE flagowane (warstwa nadrzędna nad markerami)
    "review": ["termin", ...]    # terminy obniżane do klasy „review" (informacyjne, nie blokują)
  }

Dopasowanie terminu: case-insensitive, jako całe słowo (granica \\b…\\b), wewnątrz
`match_fragment` trafienia markera. Pusty/nieobecny słownik → obecne zachowanie (zero zmiany).

API: load_dictionary(path) -> Dictionary | None ; Dictionary.classify(fragment) -> 'allow'|'review'|None.
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Dictionary:
    """Słownik domenowy: zbiory terminów allow/review + provenance. Dopasowanie po całym słowie."""
    allow: List[str] = field(default_factory=list)
    review: List[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    _allow_re: Optional[re.Pattern] = None
    _review_re: Optional[re.Pattern] = None

    def __post_init__(self):
        self._allow_re = self._compile(self.allow)
        self._review_re = self._compile(self.review)

    @staticmethod
    def _compile(terms: List[str]) -> Optional[re.Pattern]:
        """Alternatywa terminów jako całe słowa, case-insensitive. Pusta lista → None."""
        cleaned = [t.strip() for t in terms if t and t.strip()]
        if not cleaned:
            return None
        # \b nie działa dobrze na granicy litera/myślnik dla wielowyrazowych — używamy lookarounds
        # na znaki nie-słowne (z polskimi literami w klasie „słowo").
        word = r"[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ]"
        alts = "|".join(re.escape(t) for t in sorted(cleaned, key=len, reverse=True))
        return re.compile(rf"(?<!{word})(?:{alts})(?!{word})", re.IGNORECASE | re.UNICODE)

    def classify(self, fragment: str) -> Optional[str]:
        """Zwraca 'allow' jeśli fragment zawiera termin allow, 'review' jeśli review, inaczej None.

        Allow ma priorytet nad review (warstwa nadrzędna — jawne dopuszczenie wygrywa)."""
        if self._allow_re and self._allow_re.search(fragment):
            return "allow"
        if self._review_re and self._review_re.search(fragment):
            return "review"
        return None


def load_dictionary(path: Optional[str]) -> Optional[Dictionary]:
    """Wczytuje słownik z pliku JSON. Brak ścieżki / brak pliku → None (obecne zachowanie).

    Walidacja: allow/review muszą być listami stringów (jeśli obecne); provenance dict (jeśli obecny).
    Błąd parsowania/struktury → ValueError (czytelny komunikat dla wołającego/CLI)."""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"słownik domenowy: nie można wczytać {path}: {e}")
    if not isinstance(raw, dict):
        raise ValueError(f"słownik domenowy: oczekiwano obiektu JSON, otrzymano {type(raw).__name__}")

    def _str_list(key):
        v = raw.get(key, [])
        if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
            raise ValueError(f"słownik domenowy: '{key}' musi być listą stringów")
        return v

    prov = raw.get("provenance", {})
    if not isinstance(prov, dict):
        raise ValueError("słownik domenowy: 'provenance' musi być obiektem")

    return Dictionary(allow=_str_list("allow"), review=_str_list("review"), provenance=prov)
