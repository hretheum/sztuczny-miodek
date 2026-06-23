# Schemat klienta LanguageTool — pełna korekta polszczyzny NA ŻĄDANIE (G4)

`languagetool.py` to OPCJONALNY dostawca pełnej korekty polszczyzny przez serwer LanguageTool.
ZERO-DEP (biblioteka standardowa: `urllib`, `json`). Warstwa HTTP wstrzykiwalna (`transport`), wzór
jak `engines.py`.

## NA ŻĄDANIE, POZA bramką, NIE w testach realnego API

To NIE jest `JudgeEngine` i NIE wpina się do runnera, Stage 1, Stage 2 ani do żadnej bramki jakości
tekstu. To narzędzie pomocnicze: operator świadomie odpytuje serwer LanguageTool i dostaje
strukturalne sugestie (literówki, gramatyka, interpunkcja) ponad lekkim rdzeniem skilla. Domyślnie
NIE odpala się nigdzie automatycznie — brak hooka, brak wpięcia do `tests/run_tests.sh` jako gate
jakości. Test (`tools/check_languagetool.py`) jest wpięty, ale wyłącznie OFFLINE (atrapa transportu);
realne API LanguageTool jest wołane TYLKO przy faktycznym uruchomieniu CLI przez operatora.

## Endpoint

Endpoint rozstrzyga `resolve_endpoint` wg priorytetu: jawny argument > zmienna środowiskowa
`LANGUAGETOOL_ENDPOINT` > publiczny serwer (`PUBLIC_ENDPOINT = "https://api.languagetool.org/v2/check"`,
stała `DEFAULT_ENDPOINT` to jego alias zgodności wstecznej). Operator może wskazać lokalny serwer (np.
`http://localhost:8081/v2/check`), żeby nie wysyłać tekstu na zewnątrz: przez zmienną środowiskową
(`LANGUAGETOOL_ENDPOINT=...`) albo jednorazowo flagą CLI `--endpoint`. Zmienna jest czytana przy każdym
wywołaniu, nie przy imporcie modułu.

## API LanguageTool (potwierdzone realnym wywołaniem)

`POST {endpoint}`, ciało `application/x-www-form-urlencoded` (NIE JSON): wymagane `text` + `language`
(dla polszczyzny `pl-PL`). Odpowiedź JSON:

```json
{ "matches": [ {
    "message": "...", "offset": 7, "length": 6,
    "replacements": [ { "value": "z błędem" }, ... ],
    "context": { "text": "...", "offset": 7, "length": 6 },
    "rule": { "id": "ZE_Z_SPOL", "issueType": "misspelling",
              "category": { "id": "TYPOS", "name": "Literówki" } }
} ] }
```

## Kontrakt

### `Suggestion` (jedna sugestia korekty = jeden `match`)

| Pole | Typ | Opis |
|---|---|---|
| `offset` | int | pozycja początku problemu (0-based znak) |
| `length` | int | długość problematycznego fragmentu |
| `message` | string | opis problemu (po polsku, z LanguageTool) |
| `replacements` | list[str] | proponowane zamienniki (może być pusta) |
| `rule_id` | string | identyfikator reguły (np. `ZE_Z_SPOL`) |
| `category_id` | string | identyfikator kategorii (np. `TYPOS`) |
| `issue_type` | string | typ problemu (np. `misspelling`, `grammar`) |
| `context_text` | string | fragment kontekstu wokół problemu (gdy podany) |

`frozen=True` (spójnie ze stylem `engines.py`).

### `parse_response(raw: str) -> List[Suggestion]`

Deterministyczne, ODPORNE NA BRAK PÓL. Każde pole przez `.get(...)` z bezpiecznym fallbackiem
(`offset`/`length` → 0, `message` → `""`, `replacements` → wartości `value` niepuste, `rule.id` /
`issueType` / `category.id` → `""`). Błąd JSON, brak obiektu, brak listy `matches` → pusta lista
(NIGDY wyjątek). Match bez pól → `Suggestion` z domyślnymi wartościami.

### `check_text(text, *, language="pl-PL", endpoint=DEFAULT_ENDPOINT, transport=None, timeout=30.0)`

Buduje body `urllib.parse.urlencode({"text": text, "language": language})`, nagłówki
`Content-Type: application/x-www-form-urlencoded` + `User-Agent`, woła `transport` (domyślnie
`_default_http_transport`), parsuje przez `parse_response`. Transport WSTRZYKIWALNY — w testach atrapa
zwraca ustaloną kopertę, więc `_default_http_transport` nie jest wołany.

## Warstwa HTTP wstrzykiwalna

`_default_http_transport(url, *, data, headers, timeout) -> str` to JEDYNE miejsce dotykające sieci
(`urllib.request`, POST). W produkcji domyślne; w testach atrapa zwracająca ustalone ciało. Offline
nigdy nie wołane.

## CLI

`tools/languagetool_check.py`:

```bash
python3 tools/languagetool_check.py --file dokument.md
python3 tools/languagetool_check.py --text "Mam pewien błont."
python3 tools/languagetool_check.py --file x.md --json
python3 tools/languagetool_check.py --text "..." --endpoint http://localhost:8081/v2/check
LANGUAGETOOL_ENDPOINT=http://localhost:8081/v2/check python3 tools/languagetool_check.py --file x.md
```

`--file` i `--text` są rozłączne (jedno wymagane). `--json` wypisuje surowe sugestie jako JSON; bez
niego — czytelny wiersz per sugestia (`offset:length | rule_id | message | → replacements`). Transport
NIE jest wystawiony w CLI — produkcyjnie zawsze `_default_http_transport`.

## Test offline

`tools/check_languagetool.py` (wpięty do `tests/run_tests.sh`) weryfikuje na atrapie transportu:
`parse_response` mapuje match na `Suggestion`, `check_text` POST form-encoded z `text`+`pl-PL` i
poprawnymi nagłówkami na wskazany endpoint, odporność na pusty/uszkodzony JSON. ZERO realnej sieci.
```bash
python3 tools/check_languagetool.py
```
