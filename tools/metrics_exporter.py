#!/usr/bin/env python3
"""
Shim wsteczny (KAN-229). Eksporter metryk żyje teraz w pakiecie jako `miodek.metrics_exporter`
(dostępny po instalacji przez entry point `miodek-exporter`). Ten plik pozostaje, by artefakty
deploy (systemd `miodek-exporter.service`, quadlet `miodek-exporter.container`) wołające
`tools/metrics_exporter.py` działały bez zmiany wiringu mbair — montują repo i uruchamiają ten
shim, który deleguje do modułu pakietu.

Dla nowych instalacji preferuj `miodek-exporter` (console_script) albo `python3 -m miodek.metrics_exporter`.
"""
import os
import sys

# Pakiet miodek żyje w src/ — dołóż na ścieżkę, by `from miodek...` działało bez instalacji.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from miodek.metrics_exporter import main  # noqa: E402

if __name__ == "__main__":
    main()
