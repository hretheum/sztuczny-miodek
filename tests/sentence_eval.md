# Zestaw oceniający podział zdań (segmenter C2) — KAN-191

Sprawdza, czy `adapter.split_sentences_faithful` poprawnie liczy zdania w obecności skrótów,
inicjałów, liczb i wieloznakowych separatorów. Format: `oczekiwana_liczba_zdań | tekst`.
Linie `#`/puste pomijane. Konsumowany przez `tools/measure_sentences.py`.

Liczone są zdania niepuste (po `.strip()`). Cel: regresja segmentera — obsługa skrótów nie może
się cofnąć, a wieloznakowe separatory nie mogą rozbijać/sklejać błędnie.

## PL

2 | Użyj np. tego rozwiązania. Mózg działa dobrze.
2 | Zatrudniliśmy dr. Kowalskiego. To była dobra decyzja.
2 | Spotkanie o godz. 15 trwało długo. Wszyscy byli zmęczeni.
2 | Projekt kosztował ok. 100 tys. Wynik był zadowalający.
2 | Czemu tak?! Bo tak właśnie jest.
2 | No więc... Czas na podsumowanie.
3 | Pierwsze zdanie. Drugie zdanie. Trzecie zdanie.
1 | To jedno zdanie bez kropki na końcu
2 | A. Candidate złożył podanie. Rozmowa poszła dobrze.

## EN

2 | We use e.g. this approach. The system works.
3 | Design it. Build it. Ship it.
2 | Wait, what?! That makes sense now.
