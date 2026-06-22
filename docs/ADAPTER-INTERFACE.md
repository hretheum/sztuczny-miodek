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
| `Segment(kind, text, start, end, parent)` | fragment z wiernym zakresem w `doc.text`; `kind ∈ {paragraph, sentence, block}` |
| `NormalizedDoc(text, source, segments, source_map)` | tekst znormalizowany + segmenty + mostek pozycji do źródła |
| `Edit(start, end, replacement)` | poprawka na pozycjach w `doc.text` (`replacement=""` = usunięcie) |
| `InputAdapter` (ABC) | `normalize(raw) -> NormalizedDoc` |
| `OutputAdapter` (ABC) | `write_back(doc, edits) -> str` (zaktualizowane źródło) |

Pomocnik: `apply_edits_to_text(text, edits)` — nanosi edycje od najpóźniejszego offsetu
(wcześniejsze pozostają ważne), wykrywa nakładające się edycje.

## Mapowanie pozycji (zapis zwrotny)

`source_map` to lista par `(offset_w_text, offset_w_source)` posortowana po offsecie w text.
`to_source_offset(t)` znajduje ostatnią kotwicę `t_off <= t` i zwraca `s_off + (t - t_off)`
(mapowanie odcinkami liniowe). Pusty `source_map` = tożsamość (np. czysty `.txt`, gdzie
`text == source`). Wyznaczanie kotwic to zadanie adaptera (C3 Markdown / C4 strukturalny) —
np. każda usunięta sekwencja składni MD przesuwa offset źródła względem tekstu.

## Plan wdrożenia (kolejne zadania Epiku C)

- **C2** — lekki segmenter akapitów/zdań: wierny podział z offsetami; zastąpi przybliżone
  `split_paragraphs` / podział zdań w `detect_svo_rhythm`. Wypełnia `segments`.
- **C3** — adapter Markdown: `normalize` (MD → proza, kotwice w `source_map`) + `write_back`
  zachowujący strukturę MD.
- **C4** — adapter formatu strukturalnego (opcjonalny).

Linter (`ai_linter.py`) NIE jest zmieniany w C1 — interfejs to fundament; podpięcie do
`scan_file` nastąpi gdy segmenter (C2) dostarczy wierny podział, z zachowaniem zachowania
detekcji (kontrakt „bez regresji" jak w Epiku A).
