# Zestaw oceniający antytezę inwersyjną (PL-ANTI) — B2 (KAN-187)

Etykietowane przykłady do pomiaru precyzji/recall wzorca PL-ANTI „X, a nie Y" / „To X, nie Y".
`label | tekst`: `TP` = generatorowa antyteza (figura retoryczna, ma być łapana),
`FP` = naturalne zaprzeczenie/korekta (NIE ma być łapane).

Generatorowa antyteza inwersyjna: redefinicja przez kontrast, zwykle w ramie definicyjnej
„To (jest) X, nie Y" lub z przeciwstawnym „a nie". Naturalna korekta: poprawka faktu, miejsca,
czasu, sprawcy lub prosta para wyboru („herbatę, nie kawę") — informacja, nie figura.

Konsumowany przez `tools/measure_antithesis.py`. Linie `#`/puste pomijane; sekcje `## PL`.

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
