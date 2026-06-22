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
    line: int = 1        # numer linii (1-based) początku segmentu w tekście znormalizowanym
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
        if not (0 <= text_offset <= len(self.text)):
            raise ValueError(
                f"text_offset poza zakresem: {text_offset} (dozwolone 0..{len(self.text)})"
            )
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

    def __post_init__(self):
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"Niepoprawny zakres edycji: [{self.start}, {self.end})")


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


# ---------------------------------------------------------------------------
# Domyślny adapter „plain / markdown-lite" (C1) — wierny podział akapitów
# ---------------------------------------------------------------------------

import re as _re

# Separator akapitu: pusta linia (z dowolnymi białymi znakami). Ten sam wzorzec co historyczny
# split_paragraphs, ale tu offset KAŻDEGO akapitu jest wyznaczany WPROST z `finditer` na separatorach
# (a nie zliczany przybliżeniem `+2`) — to leczy kruchość przy „\n \n", „\n\n\n" itd.
_PARA_SEP_RE = _re.compile(r"\n\s*\n")


def split_paragraphs_faithful(text: str) -> List[Segment]:
    """Wierny podział na akapity: każdy `Segment` zna dokładny [start, end) i numer linii.

    Niezmiennik: `text[seg.start:seg.end] == seg.text`. Zwraca segmenty „paragraph" w kolejności
    wystąpienia, włącznie z akapitami pustymi (by zachować zgodność liczby/indeksów z historycznym
    `re.split(r"\\n\\s*\\n", text)`, które również zwraca puste pola na brzegach/zwielokrotnieniach)."""
    segments: List[Segment] = []
    starts_ends: List[Tuple[int, int]] = []
    pos = 0
    for m in _PARA_SEP_RE.finditer(text):
        starts_ends.append((pos, m.start()))
        pos = m.end()
    starts_ends.append((pos, len(text)))
    for start, end in starts_ends:
        line = text.count("\n", 0, start) + 1
        segments.append(Segment("paragraph", text[start:end], start, end, line=line))
    return segments


# Separator zdania: sekwencja . ! ? (wieloznakowa „?!", „..." traktowana jako jeden separator).
# Historyczny detect_svo_rhythm robił re.split(r"[.!?]+") + przybliżenie `pos += len(sent) + 1`
# (zakłada 1-znakowy separator → rozjazd przy „?!"/„..."). Tu offset KAŻDEGO zdania liczony WPROST.
_SENT_SEP_RE = _re.compile(r"[.!?]+")

# Skróty, po których kropka NIE kończy zdania (segmenter regułowy, bez parsera — „na ile rozsądne").
# Lista typowych polskich/uniwersalnych skrótów; rozszerzalna. Nieznany skrót → zachowanie domyślne.
_ABBREVIATIONS = frozenset({
    "np", "itd", "itp", "tj", "tzn", "tzw", "min", "dr", "prof", "inż", "mgr",
    "płk", "gen", "ul", "al", "nr", "str", "godz", "cdn", "ww", "śp", "św",
    "pl", "ang", "łac", "por", "zob", "wg", "ok", "tel", "ds", "im",
})

_TOKEN_RE = _re.compile(r"[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+", _re.UNICODE)


def _is_false_sentence_boundary(left: str, sep: str, right: str) -> bool:
    """Czy kropka to FAŁSZYWA granica zdania (skrót / inicjał / liczba / kontynuacja małą literą).

    `left` = tekst zdania przed separatorem, `sep` = separator („.", „?!", …), `right` = tekst po nim.
    Tylko pojedyncza kropka bywa fałszywa; „?!"/„..." traktujemy jako realny koniec."""
    toks = _TOKEN_RE.findall(left)
    last = toks[-1].lower() if toks else ""
    if last in _ABBREVIATIONS:
        return True
    if len(last) == 1 and last.isalpha():        # inicjał „A."
        return True
    if last.isdigit():                            # liczba „15."
        return True
    rs = right.lstrip()
    if sep == "." and rs and not rs[0].isupper():  # kontynuacja zdania małą literą
        return True
    return False


def split_sentences_faithful(text: str) -> List[Segment]:
    """Wierny podział na zdania: każdy `Segment` zna dokładny [start, end) i numer linii.

    Niezmiennik: `text[seg.start:seg.end] == seg.text`. Offset wyznaczony przez `finditer` —
    poprawny też dla wieloznakowych separatorów („?!", „...") tam, gdzie stare `pos += len(sent)+1`
    się rozjeżdżało. `text` segmentu to surowy wycinek (bez `.strip()`).

    Segmenter regułowy (C2): kropka po znanym SKRÓCIE („np.", „dr."), INICJALE („A.") lub LICZBIE
    („15.") oraz kropka przed kontynuacją małą literą NIE kończy zdania — sąsiednie fragmenty są
    scalane (start scalonego = start pierwszego → wierność offsetu zachowana). To „na ile rozsądne
    bez parsera"; nieznany skrót spoza listy domyślnie kończy zdanie."""
    # 1) surowe granice z finditer
    raw: List[Tuple[int, int, str, int]] = []  # (start_frag, end_frag, separator, end_sep)
    pos = 0
    for m in _SENT_SEP_RE.finditer(text):
        raw.append((pos, m.start(), m.group(0), m.end()))
        pos = m.end()
    raw.append((pos, len(text), "", len(text)))

    # 2) scal fałszywe granice
    starts_ends: List[Tuple[int, int]] = []
    seg_start = raw[0][0] if raw else 0
    for (fs, fe, sep, se) in raw:
        if sep == "":
            starts_ends.append((seg_start, fe))
            break
        if _is_false_sentence_boundary(text[seg_start:fe], sep, text[se:se + 30]):
            continue  # nie tnij — zdanie rozciąga się do następnej granicy
        starts_ends.append((seg_start, fe))
        seg_start = se

    segments: List[Segment] = []
    for start, end in starts_ends:
        line = text.count("\n", 0, start) + 1
        segments.append(Segment("sentence", text[start:end], start, end, line=line))
    return segments


class PlainTextAdapter(InputAdapter, OutputAdapter):
    """Domyślny adapter: traktuje źródło jako czysty tekst (markdown-lite — bez przekształceń).

    `text == source` (mapowanie tożsamościowe, pusty `source_map`), więc offsety w `doc.text`
    pokrywają się ze źródłem i zapis zwrotny jest bezpośredni. Podział akapitów jest WIERNY
    (`split_paragraphs_faithful`). Zachowuje zgodność z historycznym `split_paragraphs`
    (te same granice akapitów), różniąc się tylko TYM, że offset nie jest przybliżony.
    """

    def normalize(self, raw: str) -> NormalizedDoc:
        return NormalizedDoc(
            text=raw,
            source=raw,
            segments=split_paragraphs_faithful(raw),
            source_map=[],  # tożsamość: text == source
        )

    def write_back(self, doc: NormalizedDoc, edits: List[Edit]) -> str:
        # text == source, więc edycje na doc.text aplikujemy wprost i to jest już źródło.
        return apply_edits_to_text(doc.text, edits)


def load(source: str, adapter: Optional[InputAdapter] = None) -> NormalizedDoc:
    """Wygodny wrapper: normalizuje źródło wskazanym adapterem (domyślnie `PlainTextAdapter`)."""
    return (adapter or PlainTextAdapter()).normalize(source)
