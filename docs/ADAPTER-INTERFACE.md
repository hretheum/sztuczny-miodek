# Interfejs adaptera wejścia/wyjścia — C1 (KAN-190)

Fundament Epiku C, leczący główną kruchość lintera: dziś podział na akapity/zdania używa
`re.split` z **przybliżonym** liczeniem offsetu (`split_paragraphs`: `+2` za odstęp;
`detect_svo_rhythm`: `+1` za separator zdania). Przy nietypowych odstępach (`\n \n`, `\n\n\n`)
lub wieloznakowych separatorach (`?!`, `...`) offset się rozjeżdża, a od niego zależą numery
linii w manifeście i logika per-akapit. Interfejs adaptera zastępuje to **wiernym podziałem z
mapowaniem pozycji**.

Moduł: `adapter.py`. Zależności: tylko stdlib (`dataclasses`, `abc`, `typing`).
„Zero-dep poluzowany" — interfejs nie wymaga zależności; implementacje (C2-C4) mogą sięgnąć
po zależność tylko jeśli to konieczne.

## Kontrakt — trzy obowiązki adaptera

1. **Normalizacja** źródła do czystego tekstu (`InputAdapter.normalize`).
2. **Wierny podział** na akapity/zdania/bloki — każdy `Segment` zna dokładny zakres
   `[start, end)` w tekście znormalizowanym; niezmiennik: `doc.text[s.start:s.end] == s.text`.
   Pozycja NIE jest zgadywana z długości separatora.
3. **Zapis zwrotny** (`OutputAdapter.write_back`) — naniesienie `Edit` i odtworzenie źródła,
   z mapowaniem pozycji tekst→źródło (`NormalizedDoc.to_source_offset` + `source_map`).

## Typy

| Typ | Rola |
|---|---|
| `Segment(kind, text, start, end, line, parent)` | fragment z wiernym zakresem w `doc.text`; `kind ∈ {paragraph, sentence, block}` |
| `NormalizedDoc(text, source, segments, source_map)` | tekst znormalizowany + segmenty + mostek pozycji do źródła |
| `Edit(start, end, replacement)` | poprawka na pozycjach w `doc.text` (`replacement=""` = usunięcie); waliduje `start>=0`, `end>=start` |
| `InputAdapter` (ABC) | `normalize(raw) -> NormalizedDoc` |
| `OutputAdapter` (ABC) | `write_back(doc, edits) -> str` (zaktualizowane źródło) |

Pole `Segment.line` to numer linii **1-based** początku segmentu w tekście znormalizowanym,
wyliczany jako `text.count("\n", 0, start) + 1` (nie wymaga `source_map`). To jedna z głównych
motywacji Epiku C — poprawne numery linii w manifeście lintera.

Pomocnik: `apply_edits_to_text(text, edits)` — nanosi edycje od najpóźniejszego offsetu
(wcześniejsze pozostają ważne), wykrywa nakładające się edycje.

`NormalizedDoc.to_source_offset(t)` waliduje `0 <= t <= len(text)` (czytelny błąd przy
offsecie poza zakresem — chroni adaptery C3/C4).

## Mapowanie pozycji (zapis zwrotny)

`source_map` to lista par `(offset_w_text, offset_w_source)` posortowana po offsecie w text.
`to_source_offset(t)` znajduje ostatnią kotwicę `t_off <= t` i zwraca `s_off + (t - t_off)`
(mapowanie odcinkami liniowe). Pusty `source_map` = tożsamość (np. czysty `.txt`, gdzie
`text == source`). Wyznaczanie kotwic to zadanie adaptera (C3 Markdown / C4 strukturalny) —
np. każda usunięta sekwencja składni MD przesuwa offset źródła względem tekstu.

## Domyślna implementacja (C1) + wpięcie

`PlainTextAdapter` (w `adapter.py`) — domyślny adapter „plain / markdown-lite":
- `normalize(raw)` → `NormalizedDoc` z `text == source` (mapowanie tożsamościowe, pusty
  `source_map`) i wiernym podziałem akapitów (`split_paragraphs_faithful`).
- `write_back(doc, edits)` → nanosi edycje wprost (text == source).
- `load(source, adapter=None)` — wygodny wrapper (domyślnie `PlainTextAdapter`).

`split_paragraphs_faithful(text)` wyznacza offset KAŻDEGO akapitu wprost przez `finditer` po
separatorach (`\n\s*\n`), zamiast historycznego przybliżenia `+2`. Każdy `Segment` spełnia
`text[s.start:s.end] == s.text` i niesie numer linii.

**Wpięcie do lintera:** `ai_linter.split_paragraphs` deleguje teraz do
`adapter.split_paragraphs_faithful` (zwraca ten sam format `(offset, tekst)` — konsumenci
`scan_file`/`detect_*` niezmienieni). Granice akapitów identyczne jak historyczne `re.split`;
różnica tylko w POPRAWNOŚCI offsetu przy nieregularnych odstępach. Dowód braku regresji: wyjście
lintera bajt-w-bajt identyczne vs przed wpięciem (6/6 kombinacji lang × format na korpusie),
`run_tests.sh` zielone (werdykty + oba gate recall), `check_id_consistency` OK.

## Segmenter zdań (C2)

`split_sentences_faithful(text)` — wierny podział na zdania (segmenty `sentence`): offset każdego
zdania wyznaczony przez `finditer` po separatorach `[.!?]+`, zamiast historycznego przybliżenia
`pos += len(sent) + 1`. Niezmiennik `text[s.start:s.end] == s.text`; `text` segmentu to surowy
wycinek (bez `.strip()`), by pozycja zgadzała się z konsumentem.

**Segmenter regułowy (skróty/inicjały/liczby):** kropka po znanym skrócie (`_ABBREVIATIONS`:
`np.`, `dr.`, `itd.`, `ok.`, `godz.` …), po inicjale (`A.`), po liczbie (`15.`) lub przed
kontynuacją małą literą NIE kończy zdania — sąsiednie fragmenty są scalane (start scalonego =
start pierwszego, więc wierność offsetu zachowana). „?!"/„..." traktowane jako realny koniec.
To podejście „na ile rozsądne bez parsera"; skrót spoza listy domyślnie kończy zdanie. Regresję
chroni zestaw `tests/sentence_eval.md` + gate `tools/measure_sentences.py` w `run_tests.sh`.

**Wpięcie:** `detect_svo_rhythm` używa teraz `adapter.split_sentences_faithful` zamiast
`re.split(r"[.!?]+")` + ręcznego liczenia `pos`. Logika detekcji (3 zdania z tym samym tokenem
otwierającym, ≥3 znaki) bez zmian. Granice zdań i pozycje identyczne jak historyczny `re.split`
na korpusie; różnica tylko w POPRAWNOŚCI offsetu przy wieloznacznych separatorach („?!", „...")
— gdzie stary kod dawał offset niewierny (np. 10/18/27 zamiast 11/19/30).

Po C2 linter NIE ma już żadnego `re.split` do podziału tekstu — cały podział (akapity + zdania)
idzie przez wierny adapter. Dowód braku regresji: wyjście bajt-w-bajt identyczne vs przed
wpięciem (6/6 kombinacji), `run_tests.sh` + oba gate recall + `check_id_consistency` zielone.

## Adapter Markdown (C3)

`MarkdownAdapter` + `strip_code_spans(text)` — świadomość składni MD: zeruje zawartość bloków
kodu (``` / ~~~) i kodu inline (`` `…` ``), zachowując DŁUGOŚĆ i nowe linie. Wynik ma offsety
tożsame ze źródłem (`source_map = []`, zapis zwrotny aplikowany do `source`), więc numery linii
pozostają wierne, a detektory przestają widzieć myślniki/bold/„triady" w kodzie.

**Segmenty `block` vs `paragraph`:** `MarkdownAdapter.normalize` (przez `classify_md_segments`)
oznacza struktury MD — nagłówki, listy, listy numerowane, cytaty, checklisty, tabele oraz
wyzerowane bloki kodu — jako segmenty `kind="block"`, a ciągi prozy jako `paragraph`, z wiernymi
offsetami (`doc.text[s.start:s.end] == s.text`). Adapter jest więc samodzielnym nośnikiem wiedzy
o strukturze (konsument może pominąć `block` przy regułach prozy), uogólniając per-wierszowy
`_prose_only` na poziom segmentów — bez dublowania i bez zmiany detekcji.

**Wpięcie (wybór adaptera wg rozszerzenia):** `scan_file` wybiera adapter przez
`_select_adapter(filepath)` — `.md`/`.markdown` → `MarkdownAdapter`, reszta → `PlainTextAdapter`
(domyślna ścieżka, zachowanie sprzed C3). Wywołuje `adapter.normalize(text)` i podaje `doc.text`
detektorom PROCEDURALNYM (em-dash, bold, SVO, connector, emoji) — bo liczą znaki PROZY; dla
Markdown `doc.text` ma wyzerowany kod. Markery regex deklaratywne działają na oryginalnym tekście.
Tabele/listy/nagłówki/cytaty są nadal odsiewane per-wiersz przez `_prose_only` (zachowanie z C1 —
nie dublujemy; segmenty `block` to równoległa, strukturalna reprezentacja dla konsumentów adaptera).

Różnica wg typu (zweryfikowana): ten sam tekst z blokiem ``` z 4 myślnikami → `.md` = PASS (kod
wyzerowany), `.txt` = FAIL (PlainText nie zna składni MD). Domyślna ścieżka `.txt`/inne nietknięta.

Leczona kruchość (dowód): blok ```` ```python\nx = a — b — c — d ```` był liczony jako em-dash
overuse → werdykt FAIL. Po C3 kod jest wyzerowany → PASS. Na korpusie testowym (brak prozy w
kodzie) wyjście bajt-w-bajt identyczne vs przed wpięciem (6/6 kombinacji) — control ma inline
`` `fix/db-pool` `` (1 myślnik < próg 3), więc werdykt PASS bez zmian. Regresję chroni
`tools/measure_markdown.py` (gate w `run_tests.sh`).

## Plan wdrożenia (kolejne zadania Epiku C)

- **C4** — adapter formatu strukturalnego (opcjonalny).

Zrealizowane: C1 (interfejs + PlainTextAdapter + podział akapitów), C2 (segmenter zdań +
skróty), C3 (adapter Markdown — świadomość kodu). Wszystkie bez regresji na korpusie.
