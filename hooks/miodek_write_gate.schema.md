# Kontrakt hooka write-time: `miodek_write_gate.py` (F1)

Bramka write-time skilla sztuczny-miodek. Uruchamia linter przy zapisie pliku prozy
i zatrzymuje pracę WYŁĄCZNIE przy twardych blokerach. To jedna z trzech bramek:

| Bramka | Kiedy | Co blokuje |
|---|---|---|
| **write-time (F1, ten plik)** | przy każdym zapisie pliku prozy (hook) | tylko twarde blokery (klasa block / FAIL-HARD) |
| CI (F2) | przed mergem | pełny werdykt FAIL/FAIL-HARD (łapie też gęstość) |
| przed publikacją (F3) | przed wysyłką | pełny werdykt plus osąd modelu (Stage 2) |

## Reguła decyzji (serce F1)

Czysta funkcja `gate_decision(manifest) -> (block: bool, reason: str)`.
Wejście: manifest JSON lintera (`ai_linter.py --format json`).

BLOKUJE wyłącznie, gdy w którymkolwiek pliku manifestu:

```
summary["blockers"] > 0   LUB   summary["verdict"] == "FAIL-HARD"
```

Sama wysoka gęstość, czyli `verdict == "FAIL"` przy `blockers == 0`, NIE blokuje.
To świadome odróżnienie od exit code lintera (`ai_linter.py` kończy 1 także przy samej
gęstości, bo `verdict == "FAIL"` odpala się gdy `density > próg` mimo zera blokerów,
patrz `ai_linter.py:536-543`). Dlatego bramka nie używa kodu wyjścia lintera, tylko
czyta pole `blockers` i `verdict` z manifestu.

Powód blokady wymienia twarde blokery per plik (id markera, numer linii, fragment),
żeby agent wiedział, co dokładnie poprawić.

## Tryb 1: hook Claude Code (bez argumentów)

Mechanizm: `PostToolUse` na narzędziach `Write|Edit|MultiEdit` (deklaracja w
`hooks/hooks.json`). Wybrano PostToolUse, bo dla Edit/MultiEdit pełna treść po edycji
jest pewna dopiero po zapisie; hook czyta finalny plik z dysku (`tool_input.file_path`),
nie składa diffa.

Wejście (stdin, JSON od Claude Code):

```json
{
  "session_id": "...",
  "cwd": "...",
  "hook_event_name": "PostToolUse",
  "tool_name": "Write",
  "tool_input": { "file_path": "/abs/sciezka.md", "content": "..." }
}
```

Wyjście przy twardym blokerze (stdout, JSON, exit 0):

```json
{ "decision": "block", "reason": "Bramka write-time...: TWARDE BLOKERY...\n  plik.md: 4 blokerów..." }
```

Brak twardych blokerów: brak wyjścia (lub samo ostrzeżenie gęstości pominięte
w hook-mode), exit 0. Hook nigdy nie blokuje kodem wyjścia, decyzję niesie pole JSON.

## Tryb 2: CLI / git pre-commit (ścieżki w argv)

```bash
hooks/miodek_write_gate.py plik1.md plik2.txt
```

Lintuje podane pliki (filtruje do `.md`/`.txt`), wypisuje powód na stderr i kończy
`exit 1` przy twardym blokerze, `exit 0` w przeciwnym razie. Nadaje się jako
git `pre-commit` (twarde blokery wstrzymują commit). Tryb CLI nie wymaga zmiennej
`MIODEK_WRITE_GATE` (jawne wywołanie = świadoma decyzja).

## Opcjonalność (opt-in, wymóg bezpieczeństwa)

Sama instalacja pluginu deklaruje hook, ale w trybie hooka jest on BIERNY do jawnego
włączenia. Aktywuje go zmienna środowiskowa:

```bash
export MIODEK_WRITE_GATE=1      # albo true / on / yes
```

Bez niej hook robi `exit 0` natychmiast (zerowy koszt, zero blokad). Dzięki temu
instalacja pluginu nie zaczyna nagle blokować edycji wszystkim. Tryb CLI działa
niezależnie od tej zmiennej.

## Zasady bezpieczeństwa (fail-open)

Każda własna awaria bramki przepuszcza zapis: niesparsowany payload, brak pola
`file_path`, plik nieistniejący, błąd lub timeout lintera, niepoprawny manifest JSON,
brak `summary`. Bramka write-time nigdy nie zatrzyma pracy z powodu własnej usterki.

## Zakres plików

Tylko proza: `.md` i `.txt`. Inne rozszerzenia (w tym `.html`/`.htm`, które linter też
umie przez adapter strukturalny) bramka write-time pomija — celuje w prozę pisaną.

## Zero zależności

`json`, `os`, `subprocess`, `sys` (biblioteka standardowa). Linter wołany jako podproces
tym samym interpreterem (`sys.executable`), zamiast importu — izolacja i zero zmian
w zachowaniu lintera. Self-test: `tools/check_write_gate.py` (warstwa gate w
`tests/run_tests.sh`).
