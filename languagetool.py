#!/usr/bin/env python3
"""
languagetool.py — opcjonalny klient LanguageTool: pełna korekta polszczyzny NA ŻĄDANIE (G4).

POZA Stage 1, Stage 2 i POZA BRAMKĄ. To NIE jest JudgeEngine i NIE wpina się do runnera ani do
bramki jakości. To dostawca pomocniczy: operator świadomie odpytuje serwer LanguageTool (publiczny
api.languagetool.org albo lokalny serwer) i dostaje strukturalne sugestie korekty (literówki,
gramatyka, interpunkcja) — uzupełnienie lekkiego rdzenia o pełną korektę polszczyzny.

ZERO-DEP (biblioteka standardowa: urllib, json). Warstwa HTTP WSTRZYKIWALNA (parametr `transport`,
wzór jak engines.py). W TESTACH transport jest atrapą zwracającą ustaloną kopertę — realne API
LanguageTool NIGDY nie jest wołane w testach. `_default_http_transport` woła sieć tylko produkcyjnie,
gdy operator faktycznie uruchomi CLI bez wstrzykiwania transportu.

API LanguageTool (potwierdzone): POST {endpoint} z ciałem application/x-www-form-urlencoded
(NIE JSON), wymagane pola `text` + `language` (dla polszczyzny `pl-PL`). Odpowiedź JSON:

    { "matches": [ { "message": str, "offset": int, "length": int,
                     "replacements": [ {"value": str}, ... ],
                     "rule": { "id": str, "issueType": str,
                               "category": { "id": str, "name": str } } }, ... ] }

Parsowanie jest DETERMINISTYCZNE i odporne na brak pól: każde pole przez `.get(...)` z bezpiecznym
fallbackiem; błąd JSON lub brak `matches` → pusta lista (nie wyjątek).
"""

import json
import urllib.parse
from dataclasses import dataclass, field
from typing import List

# Domyślny endpoint: publiczny serwer LanguageTool. Konfigurowalny — operator może podać lokalny
# serwer (np. http://localhost:8081/v2/check), żeby nie wysyłać tekstu na zewnątrz.
DEFAULT_ENDPOINT = "https://api.languagetool.org/v2/check"

# Wspólny User-Agent (część serwerów / proxy odrzuca domyślny Python-urllib).
USER_AGENT = "sztuczny-miodek/1.0"


@dataclass(frozen=True)
class Suggestion:
    """Jedna sugestia korekty z LanguageTool (jeden `match`).

    - offset       : pozycja początku problemu w tekście (0-based znak).
    - length       : długość problematycznego fragmentu.
    - message      : opis problemu (po polsku, z LanguageTool).
    - replacements : proponowane zamienniki (lista stringów; może być pusta).
    - rule_id      : identyfikator reguły LanguageTool (np. "ZE_Z_SPOL").
    - category_id  : identyfikator kategorii (np. "TYPOS").
    - issue_type   : typ problemu (np. "misspelling", "grammar").
    - context_text : fragment kontekstu wokół problemu (gdy podany przez API).
    """
    offset: int
    length: int
    message: str
    replacements: List[str] = field(default_factory=list)
    rule_id: str = ""
    category_id: str = ""
    issue_type: str = ""
    context_text: str = ""


def _default_http_transport(url, *, data: bytes, headers: dict, timeout: float) -> str:
    """Jedyne miejsce dotykające sieci. POST form-encoded, zwraca surowe ciało odpowiedzi (str).

    stdlib only (urllib.request). Wstrzykiwalne — w testach podstawiamy atrapę, więc ta funkcja
    NIGDY nie jest wołana offline. Produkcyjnie woła realny serwer LanguageTool."""
    import urllib.request
    import urllib.error
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        raise RuntimeError(f"HTTP do {url} nie powiódł się: {e}")


def parse_response(raw: str) -> List[Suggestion]:
    """Parsuje surową odpowiedź LanguageTool na listę Suggestion. DETERMINISTYCZNE, odporne na braki.

    Błąd JSON, brak obiektu albo brak `matches` → pusta lista (nigdy wyjątek). Każde pole przez
    `.get(...)` z fallbackiem, więc match bez pól daje Suggestion z domyślnymi wartościami."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    matches = data.get("matches")
    if not isinstance(matches, list):
        return []

    out = []
    for m in matches:
        if not isinstance(m, dict):
            continue
        offset = m.get("offset", 0)
        length = m.get("length", 0)
        offset = offset if isinstance(offset, int) and not isinstance(offset, bool) else 0
        length = length if isinstance(length, int) and not isinstance(length, bool) else 0

        message = m.get("message") or ""
        if not isinstance(message, str):
            message = ""

        reps_raw = m.get("replacements")
        replacements = []
        if isinstance(reps_raw, list):
            for r in reps_raw:
                if isinstance(r, dict):
                    v = r.get("value", "")
                    if isinstance(v, str) and v:
                        replacements.append(v)

        rule = m.get("rule") if isinstance(m.get("rule"), dict) else {}
        rule_id = rule.get("id") or ""
        rule_id = rule_id if isinstance(rule_id, str) else ""
        issue_type = rule.get("issueType") or ""
        issue_type = issue_type if isinstance(issue_type, str) else ""
        category = rule.get("category") if isinstance(rule.get("category"), dict) else {}
        category_id = category.get("id") or ""
        category_id = category_id if isinstance(category_id, str) else ""

        ctx = m.get("context") if isinstance(m.get("context"), dict) else {}
        context_text = ctx.get("text") or ""
        context_text = context_text if isinstance(context_text, str) else ""

        out.append(Suggestion(
            offset=offset, length=length, message=message, replacements=replacements,
            rule_id=rule_id, category_id=category_id, issue_type=issue_type,
            context_text=context_text,
        ))
    return out


def check_text(text, *, language="pl-PL", endpoint=DEFAULT_ENDPOINT, transport=None,
               timeout=30.0) -> List[Suggestion]:
    """Odpytuje serwer LanguageTool o korektę `text` i zwraca listę Suggestion.

    POST form-encoded (NIE JSON): `text` + `language`. Endpoint konfigurowalny (publiczny lub
    lokalny serwer). Transport WSTRZYKIWALNY (`transport`); domyślnie `_default_http_transport`.
    W TESTACH podaje się atrapę — realne API nigdy nie jest wołane offline."""
    body = urllib.parse.urlencode({"text": text, "language": language}).encode("utf-8")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    send = transport or _default_http_transport
    raw = send(endpoint, data=body, headers=headers, timeout=timeout)
    return parse_response(raw)
