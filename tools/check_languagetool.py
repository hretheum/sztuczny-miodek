#!/usr/bin/env python3
"""
check_languagetool.py — gate klienta LanguageTool (G4). ZERO-DEP (stdlib), OFFLINE.

Cała warstwa HTTP jest wstrzykiwana atrapą zwracającą USTALONĄ kopertę /v2/check — realne API
LanguageTool NIGDY nie jest wołane w teście. `languagetool._default_http_transport` nie jest
dotykany (asercja przez wyłączny transport-atrapę).

Weryfikuje:
  1. parse_response na kopercie z 1 matchem (ZE_Z_SPOL) → 1 Suggestion o poprawnych polach
     (offset/length/message/rule_id/category_id/issue_type/replacements/context_text).
  2. check_text z atrapą transportu: poprawny endpoint jako URL, body form-encoded zawiera
     `text=` i `language=pl-PL`, nagłówek Content-Type application/x-www-form-urlencoded,
     User-Agent obecny; _default_http_transport NIE wołany.
  3. Odporność: pusty JSON {} → []; {"matches":[{}]} (match bez pól) → 1 Suggestion z fallbackami
     bez wyjątku; nie-JSON → [].

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import json
import os
import sys
import urllib.parse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import languagetool  # noqa: E402

# Ustalona koperta /v2/check z jednym matchem — zweryfikowana realnym wywołaniem (ZE_Z_SPOL).
_ENVELOPE = json.dumps({
    "matches": [{
        "message": "Prawdopodobnie brakuje spacji.",
        "shortMessage": "Pisownia",
        "offset": 7,
        "length": 6,
        "replacements": [{"value": "z błędem"}, {"value": "zbłędem"}],
        "context": {"text": "Mam pewien błont tutaj.", "offset": 7, "length": 6},
        "sentence": "Mam pewien błont tutaj.",
        "rule": {
            "id": "ZE_Z_SPOL",
            "description": "Pisownia łączna/rozdzielna",
            "issueType": "misspelling",
            "category": {"id": "TYPOS", "name": "Literówki"},
        },
    }]
})


def _capturing_transport(captured: dict, reply: str):
    """Atrapa HTTP: zapisuje url/data/headers do `captured` i zwraca ustaloną kopertę.

    To JEDYNA warstwa sieci w teście — languagetool._default_http_transport nie jest wołany."""
    def transport(url, *, data, headers, timeout):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        captured["timeout"] = timeout
        return reply
    return transport


def _boom_transport(url, *, data, headers, timeout):
    """Strażnik: gdyby produkcyjny _default_http_transport został podmieniony na to, test pęknie.
    Nie używany do realnego wywołania — sam fakt jego niewywołania jest częścią asercji offline."""
    raise AssertionError("REALNA SIEĆ w teście — transport-atrapa nie zadziałała")


def main():
    fails = []

    # --- 1: parse_response na pełnej kopercie ---
    sugg = languagetool.parse_response(_ENVELOPE)
    if len(sugg) != 1:
        fails.append(f"1) parse_response: oczekiwano 1 sugestii, jest {len(sugg)}")
    else:
        s = sugg[0]
        if s.offset != 7:
            fails.append(f"1) offset: oczekiwano 7, jest {s.offset!r}")
        if s.length != 6:
            fails.append(f"1) length: oczekiwano 6, jest {s.length!r}")
        if s.rule_id != "ZE_Z_SPOL":
            fails.append(f"1) rule_id: oczekiwano 'ZE_Z_SPOL', jest {s.rule_id!r}")
        if s.category_id != "TYPOS":
            fails.append(f"1) category_id: oczekiwano 'TYPOS', jest {s.category_id!r}")
        if s.issue_type != "misspelling":
            fails.append(f"1) issue_type: oczekiwano 'misspelling', jest {s.issue_type!r}")
        if s.replacements != ["z błędem", "zbłędem"]:
            fails.append(f"1) replacements rozjazd: {s.replacements!r}")
        if "Mam pewien" not in s.context_text:
            fails.append(f"1) context_text rozjazd: {s.context_text!r}")
        if "spacji" not in s.message:
            fails.append(f"1) message rozjazd: {s.message!r}")

    # --- 2: check_text z atrapą transportu ---
    cap = {}
    sugg2 = languagetool.check_text(
        "Mam pewien błont tutaj.", language="pl-PL",
        endpoint="https://lt.test/v2/check",
        transport=_capturing_transport(cap, _ENVELOPE),
    )
    if len(sugg2) != 1:
        fails.append(f"2) check_text: oczekiwano 1 sugestii, jest {len(sugg2)}")
    if cap.get("url") != "https://lt.test/v2/check":
        fails.append(f"2) endpoint jako URL: oczekiwano 'https://lt.test/v2/check', jest {cap.get('url')!r}")
    body = cap.get("data", b"").decode("utf-8")
    parsed = dict(urllib.parse.parse_qsl(body))
    if "text" not in parsed:
        fails.append(f"2) body form-encoded brak 'text=': {body!r}")
    if parsed.get("language") != "pl-PL":
        fails.append(f"2) body language: oczekiwano 'pl-PL', jest {parsed.get('language')!r}")
    ct = cap.get("headers", {}).get("Content-Type")
    if ct != "application/x-www-form-urlencoded":
        fails.append(f"2) Content-Type: oczekiwano form-urlencoded, jest {ct!r}")
    if not cap.get("headers", {}).get("User-Agent"):
        fails.append("2) brak nagłówka User-Agent")

    # potwierdzenie: bez jawnego endpointu i bez zmiennej środowiskowej → publiczny serwer
    _saved_env = os.environ.pop(languagetool.ENDPOINT_ENV_VAR, None)
    try:
        cap2 = {}
        languagetool.check_text("x", transport=_capturing_transport(cap2, "{}"))
        if cap2.get("url") != languagetool.PUBLIC_ENDPOINT:
            fails.append(f"2) domyślny endpoint: oczekiwano {languagetool.PUBLIC_ENDPOINT!r}, jest {cap2.get('url')!r}")

        # zmienna środowiskowa LANGUAGETOOL_ENDPOINT przekierowuje na lokalny serwer
        os.environ[languagetool.ENDPOINT_ENV_VAR] = "http://localhost:8081/v2/check"
        cap3 = {}
        languagetool.check_text("x", transport=_capturing_transport(cap3, "{}"))
        if cap3.get("url") != "http://localhost:8081/v2/check":
            fails.append(f"2) LANGUAGETOOL_ENDPOINT ignorowany: oczekiwano localhost:8081, jest {cap3.get('url')!r}")

        # jawny endpoint ma pierwszeństwo nad zmienną środowiskową
        cap4 = {}
        languagetool.check_text("x", endpoint="https://jawny.test/v2/check",
                                transport=_capturing_transport(cap4, "{}"))
        if cap4.get("url") != "https://jawny.test/v2/check":
            fails.append(f"2) jawny endpoint nie wygrał z env: jest {cap4.get('url')!r}")
    finally:
        os.environ.pop(languagetool.ENDPOINT_ENV_VAR, None)
        if _saved_env is not None:
            os.environ[languagetool.ENDPOINT_ENV_VAR] = _saved_env

    # --- 3: odporność na braki ---
    if languagetool.parse_response("{}") != []:
        fails.append("3) pusty JSON {} powinien dać []")
    if languagetool.parse_response("to nie jest JSON") != []:
        fails.append("3) nie-JSON powinien dać []")
    if languagetool.parse_response('{"matches": "x"}') != []:
        fails.append("3) matches nie-lista powinno dać []")
    bare = languagetool.parse_response('{"matches": [{}]}')
    if len(bare) != 1:
        fails.append(f"3) match bez pól: oczekiwano 1 Suggestion z fallbackami, jest {len(bare)}")
    else:
        b = bare[0]
        if (b.offset, b.length, b.message, b.replacements, b.rule_id) != (0, 0, "", [], ""):
            fails.append(f"3) match bez pól: fallbacki rozjechały się: {b!r}")

    if fails:
        for f in fails:
            print(f"  [FAIL] {f}", file=sys.stderr)
        sys.exit(1)

    print("OK   LanguageTool (G4): parse_response mapuje match na Suggestion (offset/length/rule_id/"
          "category_id/issue_type/replacements/context), check_text POST form-encoded z text+pl-PL "
          "i Content-Type/User-Agent na właściwy endpoint, odporność na pusty/uszkodzony JSON. "
          "ZERO realnej sieci (transport-atrapa).")


if __name__ == "__main__":
    main()
