#!/usr/bin/env python3
"""
Shim wsteczny (KAN-232). Budowa szkicu słownika domenowego żyje teraz w pakiecie jako
`miodek.build_dict` (dostępna po instalacji przez podkomendę `miodek build-dict`). Ten plik
zachowuje wywołanie z klonu repo (`python3 tools/build_dict.py ...`) bez instalacji: dokłada
src/ na ścieżkę i deleguje do modułu pakietu.

Dla nowych instalacji preferuj `miodek build-dict` albo `python3 -m miodek.build_dict`.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from miodek.build_dict import main  # noqa: E402

if __name__ == "__main__":
    main()
