---
name: sztuczny-miodek
description: Use when auditing language quality or stripping AI mannerisms (AI-tells) from Polish or English text, and as a hard quality gate before declaring work "done" — flags signpost openers, rule-of-three triads, "not X but Y" antithesis, balanced parallelism, em-dash overuse, empty superlatives, redefinition clichés, heading emoji, plus Polish Cyrillic, calques, false friends, anglicisms, phantom collocations, and punctuation (Jan Miodek pragmatic purism). Covers reports, syntheses, cover letters, CVs, docs. Triggers on "sprawdź polszczyznę", "korekta tekstu", "audyt językowy", "sztuczny miodek", "manieryzm AI", "AI-tell", "de-AI", "stealth", "brzmi jak AI", "usuń ślady AI", "kalki AI", "odAI-uj".
---

# Sztuczny Miodek — Audyt Polszczyzny

## 1. Przegląd

**Co**: Audyt i korekta polszczyzny oraz eradykacja manieryzmu AI w tekstach PL i EN. Dwie misje: (1) wzorcowa polszczyzna wg Miodka; (2) usunięcie AI-tellów (manieryzmów generatywnych) z każdego tekstu dla człowieka: raportów, syntez, listów motywacyjnych, CV, dokumentacji.

**Zakres**: Teksty PL (pełen audyt Priorytety 1–10 + warstwa manieryzmu AI) oraz teksty EN (warstwa anty-AI-tell: nadużycie myślnika, „not X but Y", triady, klisze, superlatywy). Opcjonalnie: jeśli posiadasz własny plik terminologii domenowej (np. słownik terminów branżowych), możesz wczytać go jako dodatkową warstwę nadrzędną dla terminów z tej dziedziny.

**Rola bramki**: Skill jest twardą bramką jakości przed „done". Semantyka „PASS z uwagami = NIE PASS" — każdy nierozwiązany flag blokuje werdykt PASS.

**Pełna taksonomia manieryzmu AI**: plik referencyjny `manieryzm-ai.md` (kanon 14 kategorii PL+EN). Deterministyczny pre-scan: `ai_linter.py` (Priorytet 0 protokołu).

**Metodologia**: Pragmatyczny puryzm Jana Miodka — poprawiaj to, co ma polski odpowiednik; zachowaj to, co przyjęło się w domenie. Dla manieryzmu AI: zmieniaj teksturę prozy, zachowuj fakty.

**Wyzwalacze**: `sprawdź polszczyznę`, `korekta tekstu`, `audyt językowy`, `sztuczny miodek`.

---

## 2. Hierarchia Źródeł

Kolejność rozstrzygania konfliktów:

### Tryb ogólny (domyślny)
1. **SKILL.md** (ten dokument) — jedyne źródło reguł.
2. Terminy domenowe pliku (np. naukowe, filozoficzne) zachowuj w formie przyjętej w danej dziedzinie.

### Tryb z własną warstwą terminologii domenowej (opcjonalny)
Jeśli posiadasz własny plik słownika terminów branżowych:
1. **Słownik domenowy** — nadrzędne źródło dla terminów z danej dziedziny. Gdy słownik definiuje termin, jego wersja obowiązuje dla tej dziedziny.
2. **SKILL.md** (ten dokument) — nadrzędne źródło dla procesu audytu, wzorców detekcji, ogólnych reguł polszczyzny, kategorii błędów.
3. **W razie sprzeczności** — słownik domenowy wygrywa dla terminów branżowych, SKILL.md wygrywa dla ogólnych reguł językowych.

---

## 3. Wykrywanie Błędów — Ranking Priorytetów

### Priorytet 1: Cyrylica [A-Яa-яЁё]

**Regex:** `[А-Яа-яЁё]`

- Oznacza błąd adiustacji (rosyjskie znaki zamiast łacińskich w polskim tekście)
- Zawsze poprawiać — to nigdy nie jest celowe
- Typowe przypadki: `а` (cyrylica) zamiast `a` (łaciński), `о` zamiast `o`, `с` zamiast `c`
- Uwaga: mogą się pojawić całe słowa cyrylicą wklejone ze źródeł (np. `Память` zamiast `Pamięć`)

---

### Priorytet 2: Kalki Angielskie

| Błąd | Poprawna forma | Kontekst |
|---|---|---|
| detektujesz / detektować | **wykrywasz / wykrywać** | audyt, analiza |
| ekstraktować / ekstraktujesz | **wydobywać, pozyskiwać** | dane, informacja |
| implementować (poza IT) | **wdrażać, realizować, zastosować** | procesy, strategie |
| raportować (relacja) | **meldować, sprawozdawać** | komunikacja |
| raport (w znaczeniu rapport) | **więź, relacja, powiązanie** | interpersonalne |
| wizualny | **wzrokowy** (percepcja) | zmysły |
| audytywny / audialny | **słuchowy** | zmysły |
| manifestować | **przejawiać, wyrażać, objawiać** | cechy, objawy |
| konfrontować | **stawiać czoła, mierzyć się z** | wyzwania |
| triggerować | **wyzwalać, uruchamiać** | mechanizmy |
| compliance (ogólnie) | **zgodność, uległość** | wymogi |
| baseline (ogólnie) | **punkt odniesienia, stan początkowy** | pomiary |
| engage (z osobą) | **zaangażować, włączyć** | ludzie |
| feedback | **opinia, informacja zwrotna** | komunikacja |
| validować | **potwierdzać, weryfikować** | testy |
| konsystentny / konsystentnie | **spójny / spójnie** | opis, dane, zachowanie |
| rezonować (z kimś) | **współbrzmieć, trafiać do** | komunikacja, odbiorca |
| adresować (problem) | **zająć się, odnieść się do** | problemy, kwestie |
| dedykowany (= przeznaczony) | **przeznaczony, wydzielony** | zasoby, narzędzia |
| focusować się | **skupiać się, koncentrować się** | uwaga, zadanie |
| targetować | **celować w, kierować do** | osoby, grupy |
| priorytetyzować | **ustalać priorytety** | zadania, cele |
| eskalować (ogólnie) | **nasilać się, zaostrzać się** | sytuacje, konflikty |
| proaktywny | **aktywny, zapobiegawczy** | działanie |
| ewaluować | **oceniać, szacować** | wyniki, skuteczność |
| generować (poza IT) | **wytwarzać, powodować** | emocje, reakcje |
| finalizować | **kończyć, doprowadzać do końca** | procesy |
| aplikacja (= zastosowanie) | **zastosowanie** | poza IT |
| dla opisania / dla wyjaśnienia | **do opisu / do wyjaśnienia** | kalka z ang. *for describing* |
| cerebrospinalny | **mózgowo-rdzeniowy** | kalka z ang. *cerebrospinal*; pol. termin medyczny: PMR |
| kardiowasku­larny | **sercowo-naczyniowy** | kalka z ang. *cardiovascular* |
| muskuloskeletalny | **mięśniowo-szkieletowy** | kalka z ang. *musculoskeletal* |
| transceiver | **nadajnik-odbiornik** | pol. termin radiotechniczny |

---

### Priorytet 3: Fałszywi Przyjaciele

| Błąd | Znaczenie angielskie | Poprawny polski |
|---|---|---|
| sensitivny | wrażliwy (sensitive) | **wrażliwy, czuły** |
| efektywnie (= effectively) | skutecznie | **skutecznie** (gdy chodzi o efekt, nie wydajność) |
| kooptować | przejąć (co-opt) | **przejąć, przeciągnąć na swoją stronę** |
| aktualnie (= actually) | w rzeczywistości | **właściwie, w rzeczywistości** |
| ewentualnie (= eventually) | w końcu, ostatecznie | **ostatecznie, w końcu** |
| sympatyczny (= sympathetic) | współczujący | **współczujący, pełen zrozumienia** |
| intencja (= intention, luźno) | zamiar | **zamiar, cel** (gdy nie jest termin prawniczy) |
| transparentny | przejrzysty (transparent) | **przejrzysty, jawny** |
| kompetentny (o rzeczy) | odpowiedni (competent) | **odpowiedni, właściwy** |
| agresywny (pozytywnie) | zdecydowany (aggressive) | **zdecydowany, intensywny** |
| dekada (= decade) | dziesięciolecie | **dziesięciolecie** (jeśli nie w kontekście muzycznym) |
| definitywnie (= definitely) | zdecydowanie | **zdecydowanie, bez wątpienia** |

**Uwaga**: Fałszywi przyjaciele wymagają analizy kontekstu. Samo wystąpienie słowa to jeszcze nie błąd — np. "aktualnie" w znaczeniu "obecnie" jest poprawne.

---

### Priorytet 4: Anglicyzmy z Polskim Odpowiednikiem

| Anglicyzm | Polski odpowiednik |
|---|---|
| pattern | **wzór, schemat, motyw** |
| mindset | **mentalność, nastawienie** |
| skillset | **zestaw umiejętności, kompetencje** |
| leverage (czasownik) | **wykorzystywać, operować** |
| insight | **spostrzeżenie, wgląd** |
| feedback loop | **pętla informacji zwrotnej** |
| framework (nie jako nazwa własna) | **ramy, struktura** |
| approach (w tekście mieszanym) | **podejście** |
| scaffolding (nie w IT) | **szkielet pojęciowy, ramy** |

**Wyjątek**: Jeśli anglicyzm jest nazwą własną (np. "Chase Hughes Framework"), zachowaj go.

#### Podtyp: Hybrydy angielsko-polskie

Angielski rdzeń z polską deklinacją/koniugacją. Nie są to zaadaptowane pożyczki — to formy ad hoc, które nie trafiły do słowników.

| Hybryda | Poprawna forma | Uzasadnienie |
|---|---|---|
| lesionami | **lezjami** | ang. *lesion* → pol. *lezja* (zaadaptowane); „lesion" + pol. -ami = hybryda |
| scrollować | **przewijać** | ang. *scroll* + pol. -ować |
| pushować | **wypychać, przesyłać** | ang. *push* + pol. -ować (poza git) |
| fetchować | **pobierać** | ang. *fetch* + pol. -ować (poza IT) |

**Test**: Czy słowo z polską końcówką istnieje w SJP/WSPP? Jeśli nie — szukaj zaadaptowanej formy lub polskiego odpowiednika.

---

### Priorytet 5: Sztuczne Kolokacje i Związki Frazeologiczne

**KLUCZOWA KATEGORIA** — najczęściej przeoczana, bo oba słowa z osobna są poprawne.

Zamiana anglicyzmu na polski odpowiednik NIE wystarczy. Trzeba sprawdzić, czy powstała kolokacja faktycznie funkcjonuje w polszczyźnie.

| Sztuczna kolokacja | Naturalny związek frazeologiczny | Źródło błędu |
|---|---|---|
| rusztowanie pojęciowe | **szkielet pojęciowy, ramy pojęciowe** | kalka z ang. *conceptual scaffolding* |
| zbiegać na wniosku | **prowadzić do wniosku** | „zbiegać się" wymaga „w punkcie", nie „na wniosku" |
| adresować problem | **zająć się problemem, odnieść się do problemu** | kalka z ang. *address a problem* |
| budować rapport | **budować więź** | *rapport* nie jest polskim słowem |

**Procedura weryfikacji kolokacji:**
1. Po zamianie anglicyzmu na polski odpowiednik — przeczytaj pełne zdanie na głos
2. Zadaj pytanie: „Czy ktokolwiek naturalnie by tak powiedział?"
3. Jeśli wątpliwość — szukaj ustalonego związku frazeologicznego
4. Typowe pułapki:
   - Czasownik + przyimek: „zbiegać **na**" zamiast „prowadzić **do**"
   - Rzeczownik + przymiotnik: „rusztowanie **pojęciowe**" zamiast „szkielet **pojęciowy**"
   - Czasownik + rzeczownik: „budować **rapport**" zamiast „budować **więź**"

---

### Priorytet 6: Interpunkcja

Najczęstsza kategoria błędów ilościowo (często 50%+ wszystkich poprawek w pliku).

#### Obowiązkowy przecinek PRZED:

| Spójnik/zaimek | Przykład błędny | Poprawka |
|---|---|---|
| **który/która/które** | `odkrycie które doprowadziło` | `odkrycie, które doprowadziło` |
| **że** | `stwierdzał że mają` | `stwierdzał, że mają` |
| **żeby/aby** | `raport żeby odpowiedzieć` | `raport, żeby odpowiedzieć` |
| **gdy/kiedy** | `nie spodziewałem się gdy` | `nie spodziewałem się, gdy` |
| **co** (zaimek względny po „to") | `to co mierzalne` | `to, co mierzalne` |
| **do czego / o czym** (zaimek wzgl.) | `tam do czego mamy dostęp` | `tam, do czego mamy dostęp` |

#### Obowiązkowy przecinek w wyliczeniach z zaprzeczeniem:

| Przykład błędny | Poprawka |
|---|---|
| `transceiver nie źródło` | `transceiver, nie źródło` |
| `w celach praktycznych nie eksploracyjnych` | `w celach praktycznych, nie eksploracyjnych` |

**Regex skanowania** (główne wzorce):
```
\w+ któr[yaeąegomuychim]\b    → sprawdź czy jest przecinek przed
\w+ że \b                      → sprawdź czy jest przecinek przed
\w+ żeby \b                    → sprawdź czy jest przecinek przed
\w+ gdy \b                     → sprawdź czy jest przecinek przed
 to co \b                      → sprawdź czy jest przecinek między
```

---

### Priorytet 7: Błędy Stylu i Gramatyki

**Imiesłowy przymiotnikowe czynne tworzone od kalek:**
- Błędnie: "Osoba detektująca błąd"
- Poprawnie: "Osoba wykrywająca błąd"

**Strona bierna tam, gdzie naturalna jest czynna:**
- Błędnie: "Błąd jest detektowany przez audytora"
- Poprawnie: "Audytor wykrywa błąd"

**Zbędne nominalizacje:**
- Błędnie: "Przeprowadzanie procesu analizy"
- Poprawnie: "Analiza"

**Błędny szyk zdania (kalka SVO):**
- Błędnie: "Osoba wykonuje ruch. Osoba wykazuje stres. Osoba zmienia temat."
- Poprawnie: "Wykonuje ruch, wykazuje stres, zmienia temat." (naturalny szyk polski)

**Zawieszony przysłówek (kalka szyku angielskiego):**
W angielskim przysłówek często stoi po dopełnieniu. W polskim — przed rzeczownikiem, który modyfikuje.
- Błędnie: "przepływu informacji-energii **cyklicznie** między domenami"
- Poprawnie: "**cyklicznego** przepływu informacji-energii między domenami"
- Błędnie: "model świadomości **holistycznie** obejmujący całość"
- Poprawnie: "**holistyczny** model świadomości obejmujący całość"
- **Test**: Czy przysłówek modyfikuje czasownik, czy w rzeczywistości opisuje rzeczownik? Jeśli rzeczownik — zamień na przymiotnik i przenieś przed rzeczownik.

**Powtórzenia leksykalne w jednym zdaniu:**
- Błędnie: "**niewielkie** ablacje kory i stwierdzał, że mają **niewielki** wpływ"
- Poprawnie: "**drobne** ablacje kory i stwierdzał, że mają niewielki wpływ"
- **Reguła**: Jeśli to samo słowo (lub rdzeń) pojawia się 2× w jednym zdaniu i nie jest celowym powtórzeniem retorycznym — zamień jedno na synonim.

---

### Priorytet 8: Ortografia terminów łacińskich i greckich

Terminy naukowe zaadaptowane z łaciny/greki mają ustalone formy polskie. Błędy często dotyczą samogłosek.

| Błędna forma | Poprawna forma | Etymologia |
|---|---|---|
| homonkulus | **homunkulus** | łac. *homunculus* (drugie „u", nie „o") |
| encelafografia | **encefalografia** | gr. *enkephalos* |
| hipotalamus | **podwzgórze** (lub *hypothalamus* w kontekście ang.) | gr. *hypo* + *thalamos* |

**Procedura**: Przy terminach łacińskich/greckich — sprawdź pisownię w SJP/WSPP. Częsty błąd: zamiana samogłosek (*u↔o*, *e↔a*) przez analogię do angielskiej wymowy.

---

### Priorytet 9: Manieryzm AI (warstwa rozszerzona — PL+EN)

**Pełny kanon: `manieryzm-ai.md`.** Ta sekcja to skrót operacyjny; pełna taksonomia 14 kategorii
(z regexami, przykładami, poprawkami i progami) żyje w pliku referencyjnym
`~/.claude/skills/sztuczny-miodek/manieryzm-ai.md`. Deterministyczny pre-scan robi
`ai_linter.py` (patrz „Protokół dwuetapowy"). Przy audycie tekstu wczytaj `manieryzm-ai.md`.

Kategorie kanonu (te same ID w dok i linterze):

| ID | Język | Co łapie |
|---|---|---|
| PL-SIGN | PL | puste otwarcia/signposty („Warto podkreślić", „W dzisiejszych czasach", „Zanurzmy się") |
| PL-CLICHE | PL | frazy-wytrychy („odgrywa kluczową rolę", „rewolucyjny", „stanowi integralną część") |
| PL-RHET | PL | antyteza redefinicyjna „to nie X — to Y", paralelizm „nie tylko… ale również", triady, „z jednej… z drugiej strony" |
| PL-RHYTHM | PL | monotonny szyk SVO, nawał łączników-otwarć („Ponadto/Co więcej/Dodatkowo") |
| PL-HEDGE | PL | hedging („mogłoby potencjalnie", „warto byłoby rozważyć") |
| PL-TYPO | PL | nadużycie myślnika, emoji w nagłówkach, bold-overload, nagłówki-klisze |
| EN-DASH | EN | em-dash overuse |
| EN-ANTI | EN | „not X, but Y" / „it's not X — it's Y" |
| EN-TRIAD | EN | rule-of-three („fast, reliable, and scalable") |
| EN-PARA | EN | balanced parallelism („self-documenting and self-checking") |
| EN-CLICHE | EN | „delve into", „testament to", „leverage", „seamless", „first-class", „I am excited to" |
| EN-HEDGE | EN | „arguably", „to some extent" |
| EN-SUPER | EN | puste superlatywy („incredibly", „truly", „remarkably") |
| EN-CONCL | EN | signposty zamknięcia („In conclusion", „Overall", „Ultimately") |

Skrót wzorców PL (artefakty maszynowe, które nie brzmią naturalnie po polsku):

| Wzorzec | Przykład błędny | Poprawna forma |
|---|---|---|
| Nadmierne hedgowanie | "Mogłoby to potencjalnie wskazywać..." | "To wskazuje na..." |
| Nienaturalna formalność | "Niniejszy dokument ma na celu..." | "Ten dokument opisuje..." |
| Powtarzalny szyk SVO | "Osoba wykonuje ruch. Osoba wykazuje stres." | "Wykonuje ruch. Wykazuje stres." |
| Nadużycie strony biernej | "Jest to obserwowane przez badacza" | "Badacz to obserwuje" |
| Zbędne wzmacniacze | "Bardzo istotne i niezwykle ważne" | "Kluczowe" |
| Nadmierne nominalizacje | "Przeprowadzanie procesu analizy danych" | "Analiza danych" |
| Błędny aspekt czasownika | "Wykrywać anomalię" (jednorazowo) | "Wykryć anomalię" |
| Złe przyimki (kalki) | "bazować na czymś" | "opierać się na czymś" |
| Sztuczne łączniki zdań | "Co więcej, dodatkowo, ponadto" (jeden po drugim) | Usuń nadmiarowe, zostaw jeden |
| Nadmierna grzeczność | "Warto byłoby rozważyć możliwość..." | "Rozważ..." |
| **Kalka redefinicyjna "to nie X — to Y"** | "Dziennik to nie refleksja — to kalibracja. Pomiar to nie ocena — to odczyt." (>3× na plik) | Zachowaj max 1-2 na plik. Reszta: zdanie twierdzące ("Dziennik kalibruje."), "=" ("Pomiar = odczyt stanu"), lub przeformułuj konstrukcję. |

**Kalka redefinicyjna** — szczegóły:
- Wzorzec: `[Rzeczownik] to nie [X] — to [Y]` lub `To nie jest [X]. To [Y].`
- Dlaczego to artefakt: AI nadużywa tej figury retorycznej jako "sztucznej epifanii" — czytelnik ma poczuć wgląd. Gdy jest 3+ razy na plik, efekt zanika i tekst brzmi jak manifest.
- **Regex detekcji:** `[Tt]o nie .{1,40}[—–-] to |[Tt]o nie .{1,40}\. [Tt]o `
- **Próg ilościowy:** max 1-2 na plik. Powyżej = popraw nadmiarowe.
- **Próg kontekstowy (ważniejszy):** nawet 1 wystąpienie wymaga poprawki, gdy kalka współwystępuje z innymi markerami AI (hedgowanie, sztuczny cytat, nienaturalna retoryka). Przykład: `„to nie jest magia — to jest fizyka, których jeszcze nie rozumiemy w pełni"` — kalka redefinicyjna + hedgowanie + pseudo-cytat = potrójny marker, popraw niezależnie od progu ilościowego.
- **Alternatywy:** zdanie twierdzące, konstrukcja z "=", metafora, pytanie retoryczne.

**Test praktyczny**: Przeczytaj fragment na głos. Jeśli brzmi jak tłumaczenie maszynowe albo jak podręcznik biurokracji — wymaga poprawki.

---

### Priorytet 10: Typografia

| Błąd | Poprawka | Kontekst |
|---|---|---|
| "cytat" (ang. cudzysłów) | **„cytat"** (pol. cudzysłów) | w tekście polskim |
| 'cytat' (ang. pojedynczy) | **'cytat'** lub **«cytat»** | zagnieżdżone cytaty |

**Wyjątek**: W blokach kodu, w angielskich cytatach i w polach technicznych — zachowaj oryginalne znaki.

---

## 4. Zasady Miodka — Praktyczne Decyzje

### Zasada 1: Czy istnieje polski odpowiednik?
- **Tak** — zmień na polski
- **Nie** — zachowaj anglicyzm (ewentualnie z wyjaśnieniem w nawiasie)

### Zasada 2: Czy jest to termin domenowy ustanowiony?
- Termin ustalony w danej dziedzinie (np. **"elicytacja"** = wydobywanie informacji) — ZACHOWAJ w formie przyjętej w tej dziedzinie
- Pseudo-termin będący kalką (np. **"detektować sprzeczność"**) — ZMIEŃ na polski odpowiednik ("wykrywać sprzeczność")
- W naukach ścisłych: terminy łacińskie/greckie zaadaptowane — sprawdź pisownię w SJP

### Zasada 3: Test Naturalności
Przeczytaj fragment na głos. Czy to brzmi jak polska mowa, czy jak tłumaczenie z Google?
- Jeśli "jak tłumaczenie" — popraw

### Zasada 4: Minimalność Ingerencji
Nie rób zmian "dla lepszego stylu", jeśli tekst jest poprawny gramatycznie i merytorycznie. Audyt to nie redakcja literacka.

### Zasada 5: Weryfikacja kolokacji
Po każdej zamianie anglicyzmu na polski odpowiednik — sprawdź, czy powstały związek frazeologiczny faktycznie istnieje w naturalnej polszczyźnie. Dwa poprawne słowa mogą tworzyć sztuczną kolokację (np. „rusztowanie pojęciowe" — oba słowa OK, ale nikt tak nie mówi; poprawnie: „szkielet pojęciowy").

---

## 5. Bramka PASS/FAIL, Protokół Dwuetapowy i Racjonalizacje

### 5.1. Bramka PASS/FAIL

Skill kończy audyt jawnym werdyktem. Reguła nadrzędna: **„PASS z uwagami = NIE PASS".**

Werdykt **FAIL**, gdy zachodzi którykolwiek warunek:
- **FAIL-HARD**: jakakolwiek cyrylica `[А-Яа-яЁё]` w tekście PL.
- Marker klasy `block` po przekroczeniu progu: akapit z em-dash ≥3; emoji w linii nagłówka;
  antyteza redefinicyjna PL współwystępująca z ≥1 innym markerem w tym samym akapicie; seria
  antytez EN; ≥3 łączniki-otwarcia w pliku (PL-RHYTHM).
- Gęstość ważona > progu: trafienia / (słowa / 500) > **8**.
- Po korekcie został choć jeden nierozwiązany flag.

Werdykt **PASS** tylko przy zerze blokerów i gęstości ≤ próg. Blok werdyktu na końcu raportu:

```
== WERDYKT: PASS | FAIL ==
Blokery: [lista ID + linia] lub „brak"
Gęstość/500: X (próg 8)
```

### 5.2. Protokół dwuetapowy (linter → osąd)

Zgodny z regułą dwustopniowości: deterministyczny pre-scan, potem osąd kontekstowy.

**Stage 1 — `ai_linter.py` (0 tokenów LLM).** Pre-scan generuje manifest:
```bash
python3 ~/.claude/skills/sztuczny-miodek/ai_linter.py --lang both ŚCIEŻKA…
# wyjście: plik:linia:ID:KLASA:fragment  +  blok == SUMMARY ==
```
Manifest = mapa podejrzeń. Linter łapie szeroko (wysoki recall), świadomie dopuszcza
false-positives w klasie `review` — to zadanie Stage 2, nie powód, by mu nie ufać.

**Stage 2 — osąd.** Dla każdego trafienia z manifestu:
1. Przeczytaj pełne zdanie (nie wyrywaj z kontekstu).
2. Rozstrzygnij: realny manieryzm czy uzasadniony kontekstem (klasa `review`).
3. Nanieś poprawkę — zmień teksturę prozy, zachowaj fakt/metrykę.
4. Zweryfikuj kolokację po zamianie (Zasada 5).
5. Wystaw werdykt wg 5.1.

Wzorzec oszczędza ~60% tokenów względem czytania całych plików (manifest → celowany Edit).

### 5.3. Tabela racjonalizacji — kontry na wymówki

Manieryzm AI przetrwa audyt tylko wtedy, gdy audytor da sobie wmówić, że to nie manieryzm.
Zasada-fundament: **łamanie litery reguł jest łamaniem ich ducha.**

| Wymówka | Rzeczywistość |
|---|---|
| „Ten myślnik jest stylistyczny" | Policz. ≥2 wtrącenia myślnikiem na akapit = maniera. Przecinek lub kropka. |
| „Ta triada jest celowa" | Tylko gdy wszystkie 3 człony to fakty nośne. Inaczej tnij do 2. |
| „Antyteza dodaje mocy" | Max 1 redefinicyjna na plik. Powtórzony wzór „to nie X — to Y" = manifest, nie myśl. |
| „Brzmi profesjonalnie" | „Profesjonalnie" to często właśnie etykieta AI-tellu. Konkret bije ton. |
| „Tekst jest wygenerowany, ale poprawny" | Poprawność gramatyczna ≠ brak manieryzmu. To dwie różne osie. |
| „To drobiazg, zostawię" | Reguła bramki: PASS z uwagami = NIE PASS. Drobiazg też blokuje. |
| „Signpost porządkuje wywód" | „Warto zauważyć / Podsumowując" nie niesie treści. Zacznij od rzeczy. |
| „Superlatyw oddaje skalę" | „Niezwykle/incredibly" nie mierzy. Podaj liczbę albo wytnij. |
| „To tylko jedno wystąpienie" | Marker klasy block przy współwystąpieniu blokuje niezależnie od progu ilościowego. |

### 5.4. Red Flags — STOP i popraw

Te myśli w trakcie audytu znaczą, że właśnie racjonalizujesz manieryzm:
- „Zostawię ten akapit, bo zmiana go spłaszczy."
- „Autor pewnie chciał tak brzmieć."
- „To zbyt subtelne, żeby czytelnik wyłapał."
- „Wszystkie trzy człony triady pasują." (sprawdź: czy każdy to fakt?)
- „PASS, ale z drobnymi uwagami."

Każda z nich oznacza: wróć do manifestu, popraw flag, nie wystawiaj PASS przedwcześnie.

---

## 6. Protokół Audytu

### Faza 0: Pre-scan linterem (Stage 1, 0 tokenów LLM)

Przed audytem manualnym uruchom `ai_linter.py` (sekcja 5.2) — manifest kieruje uwagę
celowanie zamiast czytania na ślepo. Jeśli linter niedostępny, przejdź wprost do Fazy 1.

### Faza 1: Skanowanie — przebieg pierwszy (każdy plik osobno)

```
1. Regex cyrylicy: [А-Яа-яЁё]
   → Zapisz linie z cyrylicą

2. Słowa kluczowe (przeszukaj z kontekstem):
   - "detekt" → sprawdź kontekst
   - "ekstrak" → sprawdź kontekst
   - "implemen" → sprawdź kontekst (poza IT?)
   - "raport" → sprawdź kontekst (więź czy dokument?)
   - "wizuali" → sprawdź kontekst (zmysł?)
   - "audyt" → sprawdź (słuchowy?)
   - "manifest" → sprawdź kontekst
   - "konfront" → sprawdź kontekst
   - "trigger" → sprawdź kontekst
   - "compliance" → sprawdź kontekst
   - "baseline" → sprawdź kontekst
   - "konsystent" → sprawdź kontekst
   - "rezonow" → sprawdź kontekst
   - "adresow" → sprawdź kontekst (problem?)
   - "dedykow" → sprawdź kontekst
   - "fokus" / "focus" → sprawdź kontekst
   - "target" → sprawdź kontekst
   - "priorytety" → sprawdź formę
   - "eskalow" → sprawdź kontekst
   - "ewaluow" → sprawdź kontekst
   - "finaliz" → sprawdź kontekst
   - "aplikacj" → sprawdź kontekst (IT vs zastosowanie)
   - "scaffolding" → zamień na szkielet/ramy

3. Interpunkcja (regex):
   - \w+ któr[yaeąegomuychim]\b → sprawdź przecinek przed "który"
   - \w+ że \b → sprawdź przecinek przed "że"
   - \w+ żeby \b → sprawdź przecinek przed "żeby"
   - \w+ gdy \b → sprawdź przecinek przed "gdy"
   - " to co " → sprawdź przecinek między "to" i "co"
   - "\w+ do czego" → sprawdź przecinek przed "do czego"

4. Artefakty AI:
   - Szukaj "niniejszy", "ponadto", "co więcej" (nadmiarowe)
   - Szukaj powtarzalnego szyku podmiot-orzeczenie-dopełnienie
   - Szukaj hedgowania: "potencjalnie", "mogłoby", "ewentualnie"
   - Szukaj zbędnych wzmacniaczy: "bardzo", "niezwykle", "wyjątkowo"
   - Szukaj kalki redefinicyjnej: "to nie X — to Y" (>2× na plik)

5. Gramatyka:
   - Szukaj imiesłowów: -ący, -ujący — czy pochodzą od kalek?
   - Sprawdź stronę bierną — czy jest naturalna?
   - Sprawdź aspekt czasowników — dokonany vs niedokonany
   - Szukaj nominalizacji — czy można uprościć?
   - Szukaj zawieszonych przysłówków (ang. szyk)
   - Szukaj powtórzeń leksykalnych w jednym zdaniu

6. Fałszywi przyjaciele:
   - "aktualnie" → sprawdź znaczenie (obecnie vs w rzeczywistości)
   - "ewentualnie" → sprawdź znaczenie (opcjonalnie vs w końcu)
   - "sympatyczn" → sprawdź kontekst
   - "transparentn" → sprawdź kontekst
   - "definitywn" → sprawdź kontekst
   - "dekad" → sprawdź kontekst (dziesięciolecie?)

7. Hybrydy angielsko-polskie:
   - Szukaj angielskich rdzeni z polskimi końcówkami: -ować, -ami, -ów
   - Jeśli forma nie istnieje w SJP — zamień na zaadaptowaną pożyczkę lub polski odpowiednik

8. Ortografia terminów łacińskich/greckich:
   - Szukaj terminów naukowych i sprawdź pisownię (częste: zamiana u↔o, e↔a)

9. Typografia:
   - Szukaj angielskich cudzysłowów "..." w polskim tekście (poza blokami kodu)
```

### Faza 2: Analiza Kontekstu

Dla każdego znalezionego potencjalnego błędu:
1. Przeczytaj pełne zdanie (nie wyrywaj z kontekstu)
2. **[Opcjonalnie]** Jeśli używasz własnego słownika domenowego — sprawdź, czy termin jest w nim zdefiniowany
3. Oceń, czy to naprawdę błąd (czasem anglicyzm jest celowy lub termin jest domenowy)
4. Jeśli błąd — zaproponuj konkretną poprawkę z uzasadnieniem
5. **Przy zamianach anglicyzmów — weryfikuj kolokację** (Zasada 5)

### Faza 3: Raport

Format dla każdego pliku:

```
## Plik: NAZWA.md

### Cyrylica
- Linia X: `[cytat]` → Zmienić na: `[poprawka]`

### Kalki Angielskie
- Linia Y: `[cytat]` → Zmienić na: `[poprawka]`

### Fałszywi Przyjaciele
- Linia Z: `[cytat]` → Zmienić na: `[poprawka]`

### Anglicyzmy / Hybrydy
- Linia W: `[cytat]` → Zmienić na: `[poprawka]`

### Sztuczne Kolokacje
- Linia S: `[cytat]` → Zmienić na: `[poprawka]`

### Interpunkcja
- Linia I: `[cytat]` → Zmienić na: `[poprawka]`

### Styl i Gramatyka
- Linia V: `[cytat]` → Zmienić na: `[poprawka]`

### Artefakty AI
- Linia U: `[cytat]` → Zmienić na: `[poprawka]`

### Podsumowanie
Liczba błędów: X | Krytycznych: Y | Drobnych: Z
```

Jeśli plik jest czysty — napisz: "Brak błędów."

### Faza 4: Automatyczna Korekta

Edycja każdego pliku z naniesionymi poprawkami.

### Faza 5: Przebieg weryfikacyjny (OBOWIĄZKOWY)

Jednoprzebiegowy audyt regularnie pomija ~40% usterek (empirycznie: 14 znalezione w przebiegu 1., dodatkowe 11 w przebiegu 2.). Dlatego po korekcie:

1. Wczytaj plik ponownie (pełny odczyt)
2. Skanuj pod kątem kategorii **najczęściej pomijanych w przebiegu 1.**:
   - **Interpunkcja** — przejdź grep po `\w+ któr`, `\w+ że `, `\w+ żeby `, ` to co `
   - **Kolokacje** — przeczytaj każdą zmienioną frazę w kontekście zdania
   - **Hybrydy** — szukaj ang. rdzeni z pol. końcówkami
   - **Ortografia terminów naukowych** — sprawdź samogłoski
   - **Cudzysłowy** — szukaj `"..."` w tekście polskim
   - **Powtórzenia** — szukaj zdań z 2× tym samym rdzeniem
3. Raportuj dodatkowe znaleziska jako "Runda 2"
4. Weryfikacja końcowa: `grep -rP "[А-Яа-яЁё]"` powinien dać 0 trafień

---

## 7. Wyjątki i Przypadki Szczególne

### Cytaty i Fragmenty Angielskie
Jeśli fragment jest cytatem z angielskiego źródła — zachowaj z wyjaśnieniem w komentarzu.

### Nazwy Własne
Nie poprawiać: nazwisk, miejsc, tytułów publikacji, nazw modeli (np. "Six-Minute X-Ray" jako tytuł).

### Terminy Techniczne (IT)
- "API", "machine learning", "JSON", "YAML" — zachować
- Ale "trigger" w znaczeniu ogólnym — zmienić na "wyzwalacz"

### Terminy Naukowe w Blokach Kodu
Angielskie terminy w blokach kodu (```) z polskim objaśnieniem obok — zachować. Przykład: `SURFACE STRUCTURE — zlokalizowane obwody neuronowe` — OK, bo to oryginalna terminologia autora umieszczona w schemacie.

### Terminy Zdefiniowane w Słowniku Domenowym (tryb opcjonalny)
Jeśli korzystasz z własnego słownika terminów branżowych — zawsze stosuj wersję z tego słownika. Nie zmieniaj samodzielnie terminów, które słownik ustalił dla danej dziedziny.

### Polskie Słowa Rzadkie
Jeśli poprawka używa słowa rzadkiego, dodaj wyjaśnienie:
- "Elicytacja (ang. *elicitation* — wydobywanie informacji)"

---

## 8. Szybka Ściąga — Najczęstsze Błędy

| # | Błąd | Poprawka | Kategoria |
|---|---|---|---|
| 1 | brak przecinka przed „który/że/żeby" | **dodaj przecinek** | Interpunkcja |
| 2 | rusztowanie pojęciowe | **szkielet pojęciowy** | Sztuczna kolokacja |
| 3 | raport (= więź) | **więź, relacja** | Fałszywy przyjaciel |
| 4 | detektować | **wykrywać** | Kalka angielska |
| 5 | lesionami / scrollować | **lezjami / przewijać** | Hybryda ang.-pol. |
| 6 | dekady | **dziesięciolecia** | Fałszywy przyjaciel |
| 7 | konsystentny | **spójny** | Kalka angielska |
| 8 | "Niniejszy dokument..." | **"Ten dokument..."** | Artefakt AI |
| 9 | bazować na | **opierać się na** | Zły przyimek / kalka |
| 10 | dla opisania | **do opisu** | Kalka składniowa |
| 11 | homonkulus | **homunkulus** | Ortografia łac./gr. |
| 12 | "cytat" | **„cytat"** | Typografia |
| 13 | „Warto podkreślić, że / Podsumowując" | **zacznij od rzeczy** | Manieryzm AI (PL-SIGN) |
| 14 | „odgrywa kluczową rolę / rewolucyjny" | **konkret lub metryka** | Manieryzm AI (PL-CLICHE) |
| 15 | triada „szybko, sprawnie i skutecznie" | **2 człony, jeśli nie wszystkie nośne** | Manieryzm AI (PL/EN-TRIAD) |
| 16 | myślnik w każdym zdaniu | **przecinek/kropka** | Manieryzm AI (PL-TYPO / EN-DASH) |
| 17 | „not just X — it's Y" / „it's not X, it's Y" | **state the positive directly** | Manieryzm AI (EN-ANTI) |
| 18 | „delve into / leverage / seamless / I am excited to" | **plain verb, cut filler** | Manieryzm AI (EN-CLICHE) |

---

## 9. Przykładowy Raport Audytu

```
## Plik: Bentov+Pribram+Bohm — Zintegrowany model.md

### Cyrylica
- Linia 264: "Память jako rezonans"
  → Zmienić na: "Pamięć jako rezonans"
  Uzasadnienie: rosyjskie „Память" zamiast polskiego „Pamięć"

### Sztuczne Kolokacje
- Linia 331: "dostarczyli rusztowania pojęciowego"
  → Zmienić na: "dostarczyli szkieletu pojęciowego"
  Uzasadnienie: „rusztowanie pojęciowe" nie funkcjonuje w polszczyźnie
- Linia 15: "linie myślenia, które zbiegają na tym samym wniosku"
  → Zmienić na: "linie myślenia, które prowadzą do tego samego wniosku"
  Uzasadnienie: „zbiegać na wniosku" — nienaturalna kolokacja

### Hybrydy Angielsko-Polskie
- Linia 288: "Pribram mierzył to EEG i lesionami."
  → Zmienić na: "Pribram mierzył to EEG i lezjami."
  Uzasadnienie: ang. lesion + pol. -ami = hybryda; zaadaptowana forma: lezja

### Interpunkcja
- Linia 107: "stwierdzał że mają"
  → Zmienić na: "stwierdzał, że mają"
- Linia 160: "to co mierzalne"
  → Zmienić na: "to, co mierzalne"
- Linia 329: "raport żeby odpowiedzieć"
  → Zmienić na: "raport, żeby odpowiedzieć"

### Styl i Gramatyka
- Linia 174: "przepływu informacji-energii cyklicznie między"
  → Zmienić na: "cyklicznego przepływu informacji-energii między"
  Uzasadnienie: zawieszony przysłówek (kalka ang. szyku)
- Linia 107: "niewielkie ablacje ... niewielki wpływ"
  → Zmienić na: "drobne ablacje ... niewielki wpływ"
  Uzasadnienie: powtórzenie leksykalne w jednym zdaniu

### Podsumowanie
Liczba błędów: 25 | Krytycznych: 1 (cyrylica) | Kolokacje: 3 | Interpunkcja: 14 | Drobnych: 7
```

---

## 10. Checklist Audytu

- [ ] **Faza 0 — pre-scan linterem** (`python3 ai_linter.py --lang both …` → manifest)
- [ ] Skanowanie cyrylicy (regex `[А-Яа-яЁё]`)
- [ ] Skanowanie kalek angielskich (lista 29 słów kluczowych)
- [ ] Skanowanie fałszywych przyjaciół (13 wzorców)
- [ ] Skanowanie anglicyzmów z polskim odpowiednikiem
- [ ] Skanowanie hybryd angielsko-polskich (ang. rdzeń + pol. deklinacja)
- [ ] **Skanowanie interpunkcji** (przecinki przed który/że/żeby/gdy, „to, co")
- [ ] **Weryfikacja kolokacji** (każda zamiana anglicyzmu → sprawdź naturalność frazy)
- [ ] **Manieryzm AI — warstwa PL** (PL-SIGN signposty, PL-CLICHE wytrychy, PL-RHET triady/paralelizm/antyteza, PL-RHYTHM rytm, PL-HEDGE, PL-TYPO myślniki/emoji) — wg `manieryzm-ai.md`
- [ ] **Manieryzm AI — warstwa EN** (EN-DASH, EN-ANTI, EN-TRIAD, EN-PARA, EN-CLICHE, EN-HEDGE, EN-SUPER, EN-CONCL) dla tekstów angielskich
- [ ] Analiza gramatyki (strona bierna, imiesłowy, nominalizacje, zawieszony przysłówek, powtórzenia)
- [ ] Sprawdzenie aspektu czasowników (dokonany vs niedokonany)
- [ ] **Ortografia terminów łacińskich/greckich** (sprawdź samogłoski)
- [ ] **Typografia** (cudzysłowy angielskie → polskie)
- [ ] **[Opcjonalnie]** Weryfikacja terminów z własnego słownika domenowego (jeśli używany)
- [ ] Raportowanie z numerami linii i uzasadnieniami
- [ ] Automatyczna korekta (edycja plików)
- [ ] **PRZEBIEG WERYFIKACYJNY** — ponowne skanowanie po korekcie (interpunkcja, kolokacje, hybrydy, ortografia, cudzysłowy, powtórzenia)
- [ ] Weryfikacja końcowa: `grep -rP "[А-Яа-яЁё]"` powinien dać 0 trafień
- [ ] **Werdykt bramki PASS/FAIL** (sekcja 5.1) — „PASS z uwagami = NIE PASS"; re-run lintera, 0 blokerów
- [ ] Podsumowanie dla użytkownika (liczba poprawek na plik, podział na kategorie)

---

## 11. Referencje

- **Jan Miodek**, "Ojczyzna polszczyzna" — metodologia puryzmu pragmatycznego
- **`manieryzm-ai.md`** — kanoniczna taksonomia manieryzmu AI (14 kategorii PL+EN), źródło prawdy
- **`ai_linter.py`** — deterministyczny pre-scan (Stage 1), operacyjne lustro taksonomii
- **Słownik Języka Polskiego PWN** — weryfikacja form ogólnopolskich
- **Wielki Słownik Poprawnej Polszczyzny PWN (WSPP)** — rozstrzyganie wątpliwości poprawnościowych
- **Sesja audytowa Bentov/Pribram/Bohm (2026-03-29)** — empiryczna walidacja protokołu: 14+11 usterek w 2 przebiegach, 7 kategorii błędów nie pokrytych przez wersję 1.0
