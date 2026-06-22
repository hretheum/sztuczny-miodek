# Zestaw oceniający antytezę inwersyjną (PL-ANTI) — B2 (KAN-187)

Etykietowane przykłady do pomiaru precyzji/recall wzorca PL-ANTI. Trzy etykiety:
- `TP` — generatorowa antyteza w ZAKRESIE regexu: forma A „To X, nie Y", forma B „X to Y, nie Z",
  lub „X, a nie Y". MA być łapana → liczy się do recall (bramka --min-recall).
- `FP` — naturalne zaprzeczenie/korekta. NIE ma być łapane → liczy się do precyzji.
- `C` — forma C: generatorowa antyteza BEZ ramy „to"/„a nie" (czyste „V, nie Y" / „nie X, Y").
  ŚWIADOME OGRANICZENIE: nieodróżnialna od naturalnej korekty bez analizy semantycznej (regex nie ma
  parsera części mowy). Poza zakresem — NIE liczona do recall ani precyzji; raportowana informacyjnie.
  Domena Stage 2 (osąd LLM). Wymuszanie jej łapania wskrzesiłoby FP na korektach.

Generatorowa antyteza inwersyjna: redefinicja przez kontrast w ramie „To (jest) X, nie Y" (forma A),
„X to Y, nie Z" (forma B), lub przeciwstawne „a nie". Naturalna korekta: poprawka faktu, miejsca,
czasu, sprawcy lub para wyboru („herbatę, nie kawę") — informacja, nie figura.

Konsumowany przez `tools/measure_antithesis.py`. Linie `#`/puste pomijane; sekcja `## PL`.

## PL

TP | To jest opis mojego dnia, a nie ogłoszenie.
TP | To zasada operacyjna, nie hasło.
TP | Liczy się rezultat, a nie wymówki.
TP | To narzędzie wspiera pracę, a nie ją zastępuje.
TP | To wybór architektoniczny, nie przypadek.
TP | To metoda, nie magia.
TP | To opis, nie ozdoba retoryczna.
TP | To nasz cel, a nie przeszkoda.
TP | To rozwiązanie, nie problem.
TP | Pomiar to odczyt, a nie ocena.
TP | Feedback to informacja, nie wyrok.
TP | Sprint to horyzont, nie wyścig.
TP | Kod to komunikacja, nie magia.
TP | Refaktor to inwestycja, nie koszt.
TP | Onboarding to proces, nie wydarzenie.
FP | Proszę przyjść we wtorek, nie w środę.
FP | Mam dwa koty, nie psy.
FP | Zostaw to tutaj, nie ruszaj.
FP | Powiedział, że nie przyjdzie.
FP | Lubię herbatę, nie kawę.
FP | Kup chleb, nie bułki.
FP | Pamiętaj to zadanie, nie tamto.
FP | To zadanie zrobił Jan, nie Marek.
FP | Wiem, że nie zdążymy.
FP | Obawiam się, że nie.
C | Liczy się sygnał, nie hałas.
C | Pomiar nie ocenia, mierzy.
C | Budujemy systemy, nie piszemy izolowanego kodu.
