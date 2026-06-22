#!/usr/bin/env python3
"""
adapter.py — interfejs adaptera wejścia/wyjścia (Epik C, C1 / KAN-190).

FUNDAMENT leczący główną kruchość lintera: dziś podział na akapity/zdania robi `re.split`
z PRZYBLIŻONYM liczeniem offsetu (`split_paragraphs`: `+2` za odstęp; `detect_svo_rhythm`:
`+1` za separator zdania). Przy nietypowych odstępach („\\n \\n", „\\n\\n\\n") albo wieloznakowych
separatorach („?!", „...") offset się rozjeżdża — a od offsetu zależą numery linii w manifeście
i logika per-akapit. Ten interfejs zastępuje to WIERNYM podziałem z mapowaniem pozycji.

Trzy rzeczy, które adapter musi dać (kontrakt):
  1. NORMALIZACJA źródła do czystego tekstu (np. Markdown → proza, format strukturalny → tekst).
  2. WIERNY PODZIAŁ na akapity i zdania, gdzie każdy segment zna swój DOKŁADNY zakres
     [start, end) znaków w tekście znormalizowanym (bez zgadywania długości separatora).
  3. ZAPIS ZWROTNY: naniesienie poprawek (zamian fragmentów) i odtworzenie źródła — z mapowaniem
     pozycji tekst-znormalizowany → źródło, tak by edycja w prozie trafiła w oryginał.

C1 definiuje WYŁĄCZNIE interfejs (typy + klasy bazowe + kontrakt). Konkretne implementacje:
  - C2: lekki segmenter akapitów/zdań (wierny, z offsetami) — wypełnia `segment_*`.
  - C3: adapter Markdown (normalizacja + zapis zwrotny zachowujący strukturę MD).
  - C4: adapter formatu strukturalnego (opcjonalny).

Zależności: tylko biblioteka standardowa (`dataclasses`, `abc`, `typing`). „Zero-dep poluzowany"
oznacza, że Epik C może w razie potrzeby sięgnąć po zależność, ale interfejs jej nie wymaga.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Typy danych
# ---------------------------------------------------------------------------

# Rodzaje segmentów. „paragraph" i „sentence" to minimum potrzebne linterowi dziś;
# „block" zarezerwowane dla struktur nie-prozy (nagłówek, lista, tabela) wykrywanych przez adapter.
SEGMENT_KINDS = ("paragraph", "sentence", "block")


@dataclass(frozen=True)
class Segment:
    """Fragment tekstu znormalizowanego ze ZNANYM zakresem znaków w tym tekście.

    `start`/`end` to offsety [start, end) w `NormalizedDoc.text` (NIE w źródle) — półotwarte,
    jak w `str` slicing: `doc.text[seg.start:seg.end] == seg.text`. To kontrakt wierności:
    pozycja segmentu nie jest zgadywana z długości separatora, lecz wyznaczona przy podziale.
    """
    kind: str            # jeden z SEGMENT_KINDS
    text: str            # treść segmentu (dokładnie wycinek doc.text[start:end])
    start: int           # offset początku w tekście znormalizowanym (0-based, włącznie)
    end: int             # offset końca w tekście znormalizowanym (wyłącznie)
    parent: Optional[int] = None  # indeks segmentu-rodzica (np. akapit dla zdania); None = top-level

    def __post_init__(self):
        if self.kind not in SEGMENT_KINDS:
            raise ValueError(f"Nieznany rodzaj segmentu: {self.kind!r} (dozwolone: {SEGMENT_KINDS})")
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"Niepoprawny zakres segmentu: [{self.start}, {self.end})")


@dataclass
class NormalizedDoc:
    """Wynik normalizacji źródła: czysty tekst + wierny podział + mostek pozycji do źródła.

    - `text`        : tekst znormalizowany (na nim działa detekcja lintera).
    - `segments`    : akapity/zdania/bloki z dokładnymi offsetami w `text` (kontrakt wierności).
    - `source`      : oryginalne źródło (do zapisu zwrotnego).
    - `source_map`  : lista par (offset_w_text, offset_w_source) posortowana po offset_w_text;
                      pozwala przeliczyć pozycję w `text` na pozycję w `source` (zapis zwrotny).
                      Pusta => mapowanie tożsamościowe (text == source, np. czysty .txt).
    """
    text: str
    source: str
    segments: List[Segment] = field(default_factory=list)
    source_map: List[Tuple[int, int]] = field(default_factory=list)

    def paragraphs(self) -> List[Segment]:
        return [s for s in self.segments if s.kind == "paragraph"]

    def sentences(self) -> List[Segment]:
        return [s for s in self.segments if s.kind == "sentence"]

    def to_source_offset(self, text_offset: int) -> int:
        """Przelicza offset w `text` na offset w `source` używając `source_map`.

        Mapowanie odcinkami liniowe: znajdź ostatni punkt kotwiczący o offsecie_w_text <= zadany
        i dodaj różnicę. Pusty `source_map` => tożsamość. Implementacja kotwic należy do adaptera
        (C3/C4) — tu definiujemy tylko semantykę odczytu.
        """
        if not self.source_map:
            return text_offset
        src = text_offset
        for t_off, s_off in self.source_map:
            if t_off <= text_offset:
                src = s_off + (text_offset - t_off)
            else:
                break
        return src


@dataclass(frozen=True)
class Edit:
    """Pojedyncza poprawka: zamień `doc.text[start:end]` na `replacement`.

    Offsety odnoszą się do tekstu znormalizowanego; zapis zwrotny tłumaczy je na źródło
    przez `NormalizedDoc.to_source_offset`. `replacement=""` oznacza usunięcie fragmentu.
    """
    start: int
    end: int
    replacement: str


# ---------------------------------------------------------------------------
# Klasy bazowe adapterów (kontrakt; implementacje w C2/C3/C4)
# ---------------------------------------------------------------------------

class InputAdapter(ABC):
    """Normalizuje surowe źródło do `NormalizedDoc` (tekst + wierny podział + mostek pozycji)."""

    @abstractmethod
    def normalize(self, raw: str) -> NormalizedDoc:
        """Zwraca `NormalizedDoc`. MUSI wypełnić `text`, `source` i `segments` z wiernymi
        offsetami (`doc.text[s.start:s.end] == s.text` dla każdego segmentu)."""
        raise NotImplementedError


class OutputAdapter(ABC):
    """Nanosi poprawki na dokument i odtwarza źródło (zapis zwrotny)."""

    @abstractmethod
    def write_back(self, doc: NormalizedDoc, edits: List[Edit]) -> str:
        """Stosuje `edits` (na pozycjach w `doc.text`) i zwraca zaktualizowane ŹRÓDŁO.
        Edycje aplikowane od końca ku początkowi, by wcześniejsze offsety pozostały ważne."""
        raise NotImplementedError


def apply_edits_to_text(text: str, edits: List[Edit]) -> str:
    """Pomocnik wspólny: nanosi listę `Edit` na czysty tekst (nie źródło).

    Aplikuje od najpóźniejszego offsetu, więc wcześniejsze pozostają ważne. Wykrywa nakładające
    się edycje (błąd wołającego) i je zgłasza. Adapter wyjścia (C3/C4) używa tego dla `text`,
    a następnie mapuje wynik na źródło — albo operuje wprost na źródle przez `to_source_offset`.
    """
    ordered = sorted(edits, key=lambda e: e.start, reverse=True)
    prev_start = None
    for e in ordered:
        if prev_start is not None and e.end > prev_start:
            raise ValueError(f"Nakładające się edycje: [{e.start},{e.end}) z następną od {prev_start}")
        prev_start = e.start
    out = text
    for e in ordered:
        out = out[:e.start] + e.replacement + out[e.end:]
    return out
