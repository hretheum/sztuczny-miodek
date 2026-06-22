# Kalibracja progów lintera manieryzmu AI — metodyka i przegląd

Dokument B3 (KAN-188), Epik B. Dwie części:
1. **Przegląd progów** — ocena obecnych progów względem dostępnych danych (GROUND_TRUTH + baseline/control) z 2026-06-22.
2. **Metodyka kalibracji na korpusie + logu** — procedura na przyszłość, gdy pojawi się korpus produkcyjny i log decyzji (log = D4).

---

## 1. Przegląd progów (stan 2026-06-22)

### Inwentarz progów

Progi wykrywania (część w kodzie `ai_linter.py`, bo to detektory proceduralne; część jako serie liczone w `scan_file`):

| Próg | Wartość | Klasa | Lokalizacja | Cel |
|---|---|---|---|---|
| em-dash / akapit | ≥3 | block | `detect_emdash_overuse` | nadużycie myślnika |
| bold / akapit | ≥4 | review | `detect_bold_overload` | bold-overload |
| connector-otwarcia / plik | ≥3 | block | `detect_connector_overload` | nawał łączników |
| SVO: zdania z tym samym tokenem | 3 z rzędu | review | `detect_svo_rhythm` | monotonia szyku |
| EN-ANTI seria / plik | ≥2 | block | `scan_file` | nagromadzenie antytez EN |
| PL-ANTI seria / plik | ≥3 | block | `scan_file` | nagromadzenie antytez PL |
| gęstość ważona | >8 / 500 słów | FAIL | `scan_file` | ogólne nasycenie tellami |
| PL-RHET redefinicja: współwystąpienie | ≥1 inny marker w akapicie | block | `scan_file` | eskalacja antytezy redefinicyjnej |

### Dane pomiarowe (per plik testowy)

| plik | em-dash max | bold max | connector | SVO | EN-ANTI | PL-ANTI | gęstość | werdykt |
|---|---|---|---|---|---|---|---|---|
| baseline_pl_raport | 4 | 0 | 0 | 1 (×3) | 0 | 0 | 19.0 | FAIL |
| baseline_pl_intro | 2 | 0 | 3 | 1 (×3) | 0 | 0 | 12.0 | FAIL |
| baseline_en_cover_letter | 3 | 0 | 0 | 0 | 2 | 0 | 19.0 | FAIL |
| baseline_en_doc | 2 | 0 | 0 | 0 | 2 | 0 | 17.0 | FAIL |
| control_pl_clean | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | PASS |

### Ocena progów względem danych

- **em-dash ≥3** — trafnie łapie raport (4) i cover (3); zasiane telle nadużycia myślnika (#15, #27) wymagają tego progu. Obniżenie do 2 złapałoby intro/doc (em-dash=2) niepotrzebnie. **Bez zmian.**
- **connector ≥3** — intro=3 trafia dokładnie w zasiany tell #25 (nawał spójników). Obniżenie → ryzyko FP na naturalnej prozie z 1-2 łącznikami. **Bez zmian.**
- **EN-ANTI seria ≥2** — cover=2 i doc=2 trafnie eskalują do block (zasiane #30/#38/#43, #52). **Bez zmian.**
- **SVO 3 z rzędu** — intro wykrywa „mózg×3" (zasiany #23). Recall OK. **Bez zmian.**
- **gęstość >8** — baseline 12-19 ≫ próg 8 ≫ control 0. Ogromny margines separacji; próg dobrze rozdziela teksty nasycone od czystych. **Bez zmian.**
- **PL-ANTI seria ≥3** — wszystkie pliki=0; **brak danych w korpusie**, brak podstaw do zmiany. (Próg dobrany konserwatywnie wyżej niż EN, bo „nie"/„a nie" są częstsze w naturalnej polszczyźnie.)
- **bold ≥4** — wszystkie pliki=0; **brak danych**, brak podstaw.
- **PL-RHET redefinicja ≥1** — działa na zasianych #11/#12 (antyteza redefinicyjna). **Bez zmian.**

### Wniosek B3

**Żadna korekta progu nie jest uzasadniona danymi.** Każdy próg pokryty danymi trafnie rozdziela
zasiane telle (recall) od czystej kontroli (0 FP), z dużym marginesem (zwłaszcza gęstość). Progi
nieobjęte korpusem (PL-ANTI ≥3, bold ≥4) nie mają podstaw empirycznych do zmiany — zmiana „w ciemno"
byłaby zgadywaniem. Zgodnie z briefem: „jeśli żadna korekta nie jest uzasadniona, to też wynik".

Korpus testowy (5 plików, 59 zasianych tellów) jest jednak za mały do *precyzyjnej* kalibracji
progów — daje sygnał binarny (łapie/nie łapie), nie rozkład wartości. Pełna kalibracja wymaga
korpusu produkcyjnego i logu decyzji (część 2).

### Próg serii PL-ANTI ≥3 w świetle B2 (ryzyko fałszywego bloku)

B2 (KAN-187) wykazał, że forma B PL-ANTI („X to Y, nie Z") strukturalnie łapie też **korekty
faktualne** z rzeczownikiem pospolitym („Piotr to kierownik, nie pracownik") — nieusuwalne bez
analizy części mowy. Próg serii PL-ANTI ≥3 eskaluje do `block`, więc 3 takie FP w jednym pliku
dałyby fałszywy blok. Czy próg jest dobrze dobrany?

Ocena — **próg ≥3 zostaje, jest właściwie dobrany**, z uzasadnieniem:
- Jest **konserwatywny z założenia**: wyższy niż EN-ANTI ≥2 dokładnie dlatego, że polskie „nie"/
  „a nie"/„to … nie" są częstsze w naturalnej prozie, więc pojedyncze trafienie nie blokuje.
- Pojedyncza korekta faktualna jest tania (klasa `review`); fałszywy **blok** wymaga **trzech**
  korekt faktualnych formy „X to Y, nie Z" w jednym pliku — to konstrukcja na tyle nietypowa, że
  jej trzykrotne nagromadzenie samo w sobie jest sygnałem (albo realnej maniery, albo tekstu
  wartego przeglądu). Filtr dni/liczb z B2 dodatkowo odsiewa najczęstsze korekty faktualne.
- Brak danych korpusowych (0 trafień PL-ANTI w 5 plikach) — obniżenie progu byłoby zgadywaniem,
  a podniesienie (≥4) osłabiłoby recall serii bez dowodu, że ≥3 daje FP.

**Wniosek:** próg ≥3 jest najlepszym dostępnym kompromisem; ryzyko fałszywego bloku jest realne,
ale niskie i ograniczone filtrem B2. Docelowa weryfikacja: gdy log decyzji (D4) pokaże realne
serie PL-ANTI, policzyć udział korekt faktualnych w trafieniach serii i — jeśli >akceptowalny —
rozważyć podniesienie progu serii lub osłabienie eskalacji do `review`. Do tego czasu: bez zmian.

---

## 2. Metodyka kalibracji na korpusie + logu (na przyszłość)

Gdy pojawi się **korpus produkcyjny** (realne teksty oceniane przez skill) oraz **log decyzji**
(operator akceptuje/odrzuca trafienia — to dostarczy D4), próg każdej reguły kalibrujemy danymi,
nie intuicją. Procedura:

### Krok 1 — zbierz dane decyzji
Z logu D4 zbierz dla każdej reguły/progu pary `(wartość_metryki, werdykt_operatora)`:
trafienie zaakceptowane (prawdziwy tell) vs odrzucone (false-positive).

### Krok 2 — zbuduj krzywą precyzja/recall po progu
Dla progu kandydującego `t` przejdź zakres wartości (np. em-dash 2..6) i policz dla każdej:
- recall = zaakceptowane trafienia z metryką ≥ t / wszystkie zaakceptowane,
- precyzja = zaakceptowane ≥ t / wszystkie trafienia ≥ t.

### Krok 3 — wybierz próg wg polityki klasy
- **Reguły `block`** (em-dash, connector, serie ANTI, gęstość): precyzja ma priorytet — fałszywy
  blok jest kosztowny. Wybierz najniższy próg, przy którym precyzja ≥ ustalonego celu (np. 95%).
- **Reguły `review`** (bold, SVO): recall ma priorytet — to tylko sygnał do przeglądu. Można
  zejść z progiem niżej, akceptując więcej FP.

### Krok 4 — waliduj bez regresji
Przed zmianą progu: zmierz na GROUND_TRUTH + baseline/control oraz zestawach eval
(`triad_eval.md`, `antithesis_eval.md`). Zmiana progu NIE może:
- zepsuć werdyktów regresji (baseline=FAIL, control=PASS),
- obniżyć recall poniżej bramek (`measure_triad.py`, `measure_antithesis.py` z `--min-recall`),
- naruszyć spójności ID (`check_id_consistency.py`).

### Krok 5 — zmień tylko uzasadnione, udokumentuj
Każdą zmianę progu opisz: stara→nowa wartość, dane uzasadniające (precyzja/recall przed/po),
liczba decyzji w próbce. Brak wystarczającej próbki (np. <30 decyzji dla reguły) = NIE zmieniaj.

### Gdzie progi „mieszkają" — styk z D1 (konfiguracja)
Obecnie progi proceduralne są stałymi w kodzie (`ai_linter.py`), bo to algorytmy z progiem, nie
czyste wzorce (patrz kontrakt detektorów proceduralnych w `manieryzm-ai.md`). Schemat danych
(`rules.schema.md`) **już przewiduje pole `prog`** (z A1) — wyniesienie progów do `rules.json`
uczyniłoby zmianę progu edycją danych, nie kodu.

**Styk z D1 (NIE dubluję — notka):** wyniesienie progów do konfiguracji to naturalnie zakres D1
(parametryzacja/konfiguracja narzędzia), nie B3. B3 świadomie NIE wynosi progów — to byłaby
przedwczesna parametryzacja bez potrzeby (progi są dziś stabilne i adekwatne). Gdy D1 zdefiniuje
warstwę konfiguracji, kalibracja z części 2 powinna zapisywać wyniki do tej warstwy (pole `prog`
per reguła w `rules.json` lub osobny plik configu), a nie do literałów w kodzie. Rekomendacja dla
D1: jeśli wprowadza konfigurację, niech obejmie progi proceduralne (`emdash≥3`, `bold≥4`,
`connector≥3`, `EN-ANTI≥2`, `PL-ANTI≥3`, `gęstość>8`) jako parametry — wtedy B3-metodyka stanie
się w pełni wykonalna bez zmian w kodzie. Do czasu D1 progi pozostają w kodzie (brak powodu do
przedwczesnej parametryzacji, brak danych do kalibracji).
