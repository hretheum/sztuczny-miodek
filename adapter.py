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


# ---------------------------------------------------------------------------
# Adapter Markdown (C3) — świadomy bloków kodu / tabel / list / nagłówków
# ---------------------------------------------------------------------------

# Ogrodzenie bloku kodu: ``` lub ~~~ (min 3), na początku wiersza (po opcjonalnych spacjach).
_FENCE_RE = _re.compile(r"^[ \t]*(`{3,}|~{3,})", _re.MULTILINE)
# Kod inline: `...` (najkrótsze dopasowanie, w jednej linii).
_INLINE_CODE_RE = _re.compile(r"`[^`\n]+`")


def _blank_preserving(segment: str) -> str:
    """Zwraca napis tej samej długości co `segment`, z zachowanymi „\\n", reszta = spacje.

    Dzięki temu wycięcie kodu NIE zmienia offsetów ani numerów linii w `text` — detektory
    przestają widzieć myślniki/bold w kodzie, a pozycje pozostają wierne (source_map = tożsamość)."""
    return "".join("\n" if ch == "\n" else " " for ch in segment)


def strip_code_spans(text: str) -> str:
    """Zeruje zawartość kodu (bloki ```/~~~ i inline `…`), zachowując długość i nowe linie.

    Wynik ma DOKŁADNIE tę samą długość co wejście (offsety tożsame), więc można go użyć jako
    `NormalizedDoc.text` z pustym `source_map`. Linijki ogrodzeń też są zerowane (to nie proza).
    Świadomy bloków kodu — leczy FP, gdy myślniki/bold/„triady" są w kodzie, nie w prozie."""
    out = list(text)
    # 1) bloki ogrodzone — pary kolejnych ogrodzeń tego samego typu
    fences = list(_FENCE_RE.finditer(text))
    i = 0
    while i < len(fences):
        open_m = fences[i]
        # znajdź ogrodzenie zamykające (kolejne), inaczej do końca tekstu
        close_m = fences[i + 1] if i + 1 < len(fences) else None
        block_start = open_m.start()
        block_end = close_m.end() if close_m else len(text)
        for j in range(block_start, block_end):
            if text[j] != "\n":
                out[j] = " "
        i += 2  # przeskocz parę (otwarcie+zamknięcie)
    stripped = "".join(out)
    # 2) kod inline — tylko poza już wyzerowanymi obszarami (działa, bo tam nie ma już backticków)
    def _blank_inline(m):
        return _blank_preserving(m.group(0))
    stripped = _INLINE_CODE_RE.sub(_blank_inline, stripped)
    return stripped


# Wiersz nie-prozy (struktura MD): nagłówek, lista, lista numerowana, cytat, checklista, tabela.
# Spójne z _NON_PROSE_RE w linterze, plus tabela (wiersz z „|"). Wiersze takie trafiają do
# segmentów kind="block" (nie liczą się jako proza dla em-dash/bold/triad).
_MD_BLOCK_LINE_RE = _re.compile(r"^\s*(?:#{1,6}\s|[-*+]\s|\d+\.\s|>|\[[ xX]\])")


def _is_block_line(line: str) -> bool:
    """Czy wiersz to struktura MD (nie proza): nagłówek/lista/cytat/checklista/tabela."""
    return "|" in line or bool(_MD_BLOCK_LINE_RE.match(line))


def classify_md_segments(text: str) -> List[Segment]:
    """Dzieli tekst na segmenty `paragraph` (proza) i `block` (struktura MD), z wiernymi offsetami.

    Akapit = blok oddzielony pustą linią (jak `split_paragraphs_faithful`). Wewnątrz akapitu wiersze
    strukturalne (nagłówek/lista/tabela/cytat) są grupowane w segmenty `block`, a ciągi prozy w
    `paragraph`. Niezmiennik: `text[s.start:s.end] == s.text`. Bloki kodu są już wyzerowane
    (spacje) przez `strip_code_spans` przed wywołaniem, więc tu trafiają jako proza pustych spacji
    — nieszkodliwe (0 myślników/bold). To czyni adapter samodzielnym nośnikiem wiedzy o strukturze."""
    segments: List[Segment] = []
    for para in split_paragraphs_faithful(text):
        if not para.text:
            continue
        # podziel akapit na ciągłe pasma: block-lines vs prose-lines, zachowując offsety wierszy
        line_start = para.start
        run_start = para.start
        run_is_block = None
        # iteruj po wierszach akapitu (z „\n" jako separatorem, offsety wierne)
        lines = para.text.split("\n")
        for idx, ln in enumerate(lines):
            ln_is_block = _is_block_line(ln)
            ln_end = line_start + len(ln)
            if run_is_block is None:
                run_is_block = ln_is_block
                run_start = line_start
            elif ln_is_block != run_is_block:
                # zamknij poprzednie pasmo [run_start, line_start-1) (bez końcowego „\n")
                seg_end = line_start - 1  # poprzedni „\n"
                kind = "block" if run_is_block else "paragraph"
                segments.append(Segment(kind, text[run_start:seg_end], run_start, seg_end,
                                        line=text.count("\n", 0, run_start) + 1))
                run_start = line_start
                run_is_block = ln_is_block
            # następny wiersz zaczyna się po „\n"
            line_start = ln_end + 1
        # zamknij ostatnie pasmo do końca akapitu
        if run_is_block is not None:
            kind = "block" if run_is_block else "paragraph"
            segments.append(Segment(kind, text[run_start:para.end], run_start, para.end,
                                    line=text.count("\n", 0, run_start) + 1))
    return segments


class MarkdownAdapter(InputAdapter, OutputAdapter):
    """Adapter Markdown (C3): wierna ekstrakcja prozy świadoma składni MD.

    `normalize` produkuje `text` = źródło z WYZEROWANĄ zawartością kodu (bloki ```/~~~ i inline
    `…`), zachowując długość i nowe linie — więc offsety pozostają tożsame ze źródłem
    (`source_map = []`, zapis zwrotny bezpośredni). Dzięki temu detektory (em-dash, bold) nie
    liczą znaków w kodzie jako manieryzmu prozy.

    Segmenty: proza → `paragraph`, struktura MD (nagłówki, listy, tabele, cytaty, checklisty oraz
    wyzerowane bloki kodu) → `block`. Konsument może pominąć `block` przy regułach prozy. Linter
    nadal stosuje `_prose_only` per-wiersz (zachowanie z C1) — adapter to UOGÓLNIA na poziomie
    segmentów, nie dublując ani nie pogarszając."""

    def normalize(self, raw: str) -> NormalizedDoc:
        text = strip_code_spans(raw)
        return NormalizedDoc(
            text=text,
            source=raw,
            segments=classify_md_segments(text),
            source_map=[],  # długość zachowana → offsety tożsame ze źródłem
        )

    def write_back(self, doc: NormalizedDoc, edits: List[Edit]) -> str:
        # offsety w doc.text == offsety w source (długość zachowana), więc edycje aplikujemy
        # do ŹRÓDŁA (nie do tekstu z wyzerowanym kodem, by nie utracić treści kodu).
        return apply_edits_to_text(doc.source, edits)


# ---------------------------------------------------------------------------
# Adapter formatu strukturalnego (C4, opcjonalny) — HTML / storage wiki
# ---------------------------------------------------------------------------
#
# Po co: storage stron wiki (np. Confluence) i HTML wyznaczają granice akapitów ZNACZNIKAMI
# (<p>, <li>, <h1-6>, <div>…), a NIE pustymi liniami. Podział tekstowy (PlainText/Markdown)
# zlewa wtedy cały dokument w jeden akapit → myślniki/bold z RÓŻNYCH <p> liczone razem =
# fałszywy em-dash overuse (realny powód FP przy audycie stron wiki).
#
# Ten adapter używa `html.parser` ze STDLIB (zero-dep — bez ciężkiej biblioteki HTML). Ekstrahuje
# tekst, wstawiając granicę akapitu („\n\n") na znacznikach blokowych, oraz buduje `source_map`
# (proza→źródło), bo usuwanie tagów ZMIENIA długość — to pierwszy adapter z nietożsamym mapowaniem.
#
# STATUS: działający SZKIELET (brief: „jeśli zakres za duży, dostarczyć szkielet + plan").
# Pokrywa rdzeń (granice akapitów ze struktury, ekstrakcja prozy, source_map, segmenty block/
# paragraph). Plan rozbudowy w docs/ADAPTER-INTERFACE.md. NIE wpięty do produkcyjnej ścieżki
# scan_file (collect_files obsługuje .md/.txt; HTML to osobny typ wejścia — wpięcie = przyszły krok).

import html as _html
from html.parser import HTMLParser as _HTMLParser

# Znaczniki blokowe HTML — ich start/koniec wyznacza granicę akapitu prozy.
_HTML_BLOCK_TAGS = frozenset({
    "p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "tr", "td", "th", "table", "section", "article", "header",
    "footer", "pre", "br", "hr",
})
# Znaczniki, których ZAWARTOŚĆ to nie proza (jak bloki kodu w MD) — pomijana.
_HTML_SKIP_CONTENT_TAGS = frozenset({"code", "pre", "script", "style"})


class _ProseHTMLParser(_HTMLParser):
    """Zbiera prozę z HTML: tekst + mapowanie (offset_w_prozie → offset_w_źródle).

    Na znacznikach blokowych wstawia separator akapitu. Zawartość code/pre/script/style pomija.
    `source_map` to lista kotwic (offset_text, offset_source) wystarczająca do `to_source_offset`."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.text_len = 0
        self.source_map: List[Tuple[int, int]] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _HTML_SKIP_CONTENT_TAGS:
            self._skip_depth += 1
        if tag in _HTML_BLOCK_TAGS and self.parts and not self.parts[-1].endswith("\n\n"):
            self.parts.append("\n\n")
            self.text_len += 2

    def handle_endtag(self, tag):
        if tag in _HTML_SKIP_CONTENT_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag in _HTML_BLOCK_TAGS and self.parts and not self.parts[-1].endswith("\n\n"):
            self.parts.append("\n\n")
            self.text_len += 2

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        # kotwica: bieżąca pozycja w prozie ↔ pozycja danych w źródle (getpos → wiersz/kol → offset)
        src_off = self._current_source_offset()
        self.source_map.append((self.text_len, src_off))
        self.parts.append(data)
        self.text_len += len(data)

    # offset źródłowy bieżącego tokenu (z numeru wiersza/kolumny parsera)
    _raw = ""

    def _current_source_offset(self) -> int:
        line, col = self.getpos()
        # zsumuj długości poprzednich wierszy + kolumna
        lines = self._raw.split("\n")
        return sum(len(l) + 1 for l in lines[: line - 1]) + col


class StructuralAdapter(InputAdapter):
    """Adapter formatu strukturalnego (C4): HTML / storage wiki. Lekki, czysty Python (html.parser).

    Wyznacza granice akapitów ze ZNACZNIKÓW blokowych (nie z pustych linii), ekstrahuje prozę i
    buduje `source_map` (proza→źródło) — bo usuwanie tagów zmienia długość. Segmenty: `paragraph`
    (proza). Zawartość code/pre/script/style pomijana. SZKIELET: rdzeń działa; pełne pokrycie
    (zagnieżdżone tabele, encje brzegowe, atrybuty alt/title) — plan w docs."""

    def normalize(self, raw: str) -> NormalizedDoc:
        parser = _ProseHTMLParser()
        parser._raw = raw
        parser.feed(raw)
        parser.close()
        text = "".join(parser.parts)
        return NormalizedDoc(
            text=text,
            source=raw,
            segments=split_paragraphs_faithful(text),
            source_map=parser.source_map,
        )


def load(source: str, adapter: Optional[InputAdapter] = None) -> NormalizedDoc:
    """Wygodny wrapper: normalizuje źródło wskazanym adapterem (domyślnie `PlainTextAdapter`)."""
    return (adapter or PlainTextAdapter()).normalize(source)
