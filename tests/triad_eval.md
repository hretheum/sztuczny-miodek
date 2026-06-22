# Zestaw oceniający triadę (PL-RHET „triada?" / EN-TRIAD) — B1 (KAN-186)

Zestaw etykietowanych przykładów do pomiaru precyzji/recall wzorca triady.
Każdy wiersz: `label | tekst`, gdzie label = `TP` (retoryczna triada AI = ma być łapana)
lub `FP` (zwykłe wyliczenie faktów = NIE ma być łapane).

Retoryczna triada AI: trzy paralelne, semantycznie równorzędne wyrazy (zwykle przymiotniki,
przysłówki lub czasowniki) jako figura rytmiczna. Wyliczenie faktów: nazwy własne, liczby,
daty, rzeczowniki konkretne — informacja, nie ozdoba retoryczna.

Format konsumowany przez `tools/measure_triad.py`. Linie zaczynające się od `#` lub puste są pomijane.

## PL

FP | Kupiłem mleko, chleb i masło.
FP | Spotkanie odbędzie się we wtorek, środę i czwartek.
FP | W zespole są Anna, Marek i Tomasz.
FP | Plik zawiera dane z roku 2021, 2022 i 2023.
FP | Funkcja przyjmuje argumenty x, y oraz z.
FP | Repozytorium ma pliki .py, .md i .json.
FP | Zatrudniliśmy Kowalskiego, Nowaka i Wiśniewską.
TP | Pracujemy szybko, sprawnie i skutecznie.
TP | Rozwiązanie jest wydajne, niezawodne i skalowalne.
TP | Działa prosto, szybko i niezawodnie.
TP | Szybko, sprawnie i tanio — oto nasza dewiza.
TP | Projekt jest nowoczesny, elastyczny oraz intuicyjny.

## EN

FP | The file contains rows for 2021, 2022, and 2023.
FP | Add salt, pepper, and oil.
FP | The team includes Anna, Mark, and Tom.
FP | Parameters are x, y, and z.
FP | Supported files: .py, .md, and .json.
FP | We hired Smith, Jones, and Lee.
TP | It is fast, reliable, and scalable.
TP | We design, build, and ship.
TP | Clean, simple, and elegant.
TP | The API is fast, secure, and well-documented.
