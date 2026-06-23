#!/usr/bin/env python3
"""
engines.py — interfejs WYMIENIALNEGO silnika osądu Stage 2 + atrapa do testów (Epik G, G1).

Architektura: granicą między Stage 1 (linter, deterministyczny, bez kosztu tokenów) a Stage 2
(osąd modelu) jest MANIFEST. Runner (runner.py) wybiera z manifestu segmenty klasy "review"
i przekazuje je do silnika osądu. Silnik jest INTERFEJSEM — runner zna wyłącznie metodę
`JudgeEngine.judge(segment) -> Judgement`. Dzięki temu podmiana silnika (lokalny model przez
Ollama, API przez OpenRouter, model z najwyższej półki jako sędzia apelacyjny) to inny argument
do runnera, ZERO zmian w samym runnerze.

Ten moduł jest ZERO-DEP (stdlib). Domyślny silnik to atrapa `StubJudgeEngine`: deterministyczna,
bez LLM i bez sieci. Służy do testów potoku, do E3 (instrumentacja) i jako żywy kontrakt kształtu
osądu. Realny silnik wpina się przez tę samą klasę bazową — patrz docstring `JudgeEngine`.

KSZTAŁTY (kontrakt, udokumentowany też w runner.schema.md):

    ReviewSegment   — jednostka routowana do Stage 2 (akapit z ≥1 trafieniem klasy "review").
    Judgement       — werdykt silnika dla jednego segmentu.
    JudgeEngine     — klasa bazowa (ABC) wymienialnego silnika; ma .name (atrybucja E2/E3) i .judge.
    StubJudgeEngine — atrapa: ≥1 hit review w segmencie => "rewrite", inaczej "pass".

BRAMKA: "PASS z uwagami to NIE PASS". W kategoriach werdyktu: cokolwiek wymaga ruchu => "rewrite".
Atrapa NIE ocenia treści (nie ma do tego prawa bez modelu) — sygnalizuje jedynie, że segment ma
trafienia review wymagające osądu, więc zwraca "rewrite". To celowo zachowawcze: potok ma być
„czerwony", dopóki realny silnik nie wyda werdyktu "pass" świadomie.
"""

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

# Dozwolone werdykty osądu Stage 2 (bramka "PASS z uwagami to NIE PASS").
VERDICTS = ("pass", "rewrite")


@dataclass(frozen=True)
class ReviewSegment:
    """Jednostka routowana do Stage 2: akapit z ≥1 trafieniem klasy "review".

    - file       : ścieżka pliku źródłowego (z manifestu).
    - seg_index  : indeks akapitu w pliku (kolejność z adapter.paragraphs()).
    - line       : 1-based numer linii początku akapitu (z adapter.Segment.line).
    - text       : treść akapitu (dokładnie doc.text[seg.start:seg.end]).
    - hits       : trafienia klasy "review" przypięte do tego akapitu (lista dict z manifestu:
                   {id, line, klasa, match, file}).
    """
    file: str
    seg_index: int
    line: int
    text: str
    hits: List[dict] = field(default_factory=list)

    def hit_ids(self) -> List[str]:
        """ID trafień review w tym segmencie (kolejność z manifestu)."""
        return [h.get("id") for h in self.hits]


@dataclass(frozen=True)
class Judgement:
    """Werdykt silnika dla jednego segmentu.

    - verdict : "pass" | "rewrite" (bramka: cokolwiek do ruchu => "rewrite").
    - notes   : uzasadnienie / propozycja poprawki (tekst; dla atrapy: wyliczenie ID trafień).
    - engine  : nazwa silnika, który wydał werdykt (= JudgeEngine.name; atrybucja E2/E3).
    """
    verdict: str
    notes: str
    engine: str

    def __post_init__(self):
        if self.verdict not in VERDICTS:
            raise ValueError(
                f"Judgement.verdict musi być jednym z {VERDICTS}, jest {self.verdict!r}"
            )


class JudgeEngine(ABC):
    """Wymienialny silnik osądu Stage 2.

    Kontrakt jest minimalny celowo: runner zna TYLKO `.name` (atrybucja) i `.judge(segment)`.
    Implementacja realnego silnika (lokalny model / API) podmienia się bez dotykania runnera:

        class OllamaBielikEngine(JudgeEngine):
            name = "bielik-ollama"
            def judge(self, segment): ...   # woła model, mapuje odpowiedź na Judgement

    Realny silnik odpowiada za: budowę promptu z `segment.text` i `segment.hits`, wywołanie modelu,
    sparsowanie odpowiedzi do `Judgement(verdict, notes, engine=self.name)`. Runner go tylko woła.
    """

    name: str = "abstract"

    @abstractmethod
    def judge(self, segment: ReviewSegment) -> Judgement:
        """Wydaje werdykt dla jednego segmentu review. Zwraca Judgement."""
        raise NotImplementedError


class StubJudgeEngine(JudgeEngine):
    """Atrapa silnika: deterministyczna, bez LLM, bez sieci.

    Reguła atrapy: jeśli segment ma ≥1 trafienie klasy "review" => "rewrite" z notatką wymieniającą
    ID trafień; w przeciwnym razie "pass". To NIE jest ocena treści — atrapa sygnalizuje tylko, że
    segment wpadł do Stage 2 (ma trafienia do osądu). Służy do testów potoku, E3 i jako kontrakt.

    Realny silnik NADPISUJE tę regułę faktyczną oceną modelu, zachowując sygnaturę `judge`.
    """

    name = "stub"

    def judge(self, segment: ReviewSegment) -> Judgement:
        if segment.hits:
            ids = ", ".join(str(i) for i in segment.hit_ids())
            return Judgement(
                verdict="rewrite",
                notes=f"atrapa: segment ma trafienia review do osądu ({ids})",
                engine=self.name,
            )
        return Judgement(verdict="pass", notes="atrapa: brak trafień review", engine=self.name)


# ============================================================================
# KAN-218 — REALNE adaptery silnika Stage 2 (OpenAI-compatible + Ollama).
# ============================================================================
#
# Oba ZERO-DEP (stdlib: urllib.request, json, os, re). Bez requests, bez SDK.
# Realny silnik nadpisuje regułę atrapy faktyczną oceną modelu, zachowując
# kontrakt JudgeEngine (.name + .judge -> Judgement). Runner zna tylko ten kontrakt.
#
# Warstwa HTTP jest WSTRZYKIWALNA (parametr `transport`, wzór file_reader/ts_provider
# z runnera). W produkcji domyślny `_default_http_transport` woła urllib; w testach
# podstawia się atrapę zwracającą ustalone ciało JSON modelu — ZERO realnej sieci.

# System prompt sędziego (wspólny dla obu adapterów). Surowa bramka: jakakolwiek
# poprawka => "rewrite"; "pass" tylko dla akapitu czystego i naturalnego.
JUDGE_SYSTEM_PROMPT = (
    "Jesteś surowym korektorem polszczyzny. Oceniasz JEDEN akapit pod kątem manieryzmu AI "
    "(sztuczne sygnały generatora: triady, antytezy \"X, a nie Y\", puste superlatywy, nadmiar "
    "myślników, signposty). Bramka jest surowa: jeśli akapit wymaga JAKIEJKOLWIEK poprawki, "
    "werdykt to \"rewrite\". \"pass\" tylko gdy akapit jest czysty i naturalny. "
    "Odpowiedz WYŁĄCZNIE jednym obiektem JSON: "
    "{\"verdict\": \"pass\"|\"rewrite\", \"notes\": \"<krótkie uzasadnienie po polsku>\"}."
)

# Notatka fallback: odpowiedź modelu niejednoznaczna => eskalacja do rewrite (zachowawczo).
_FALLBACK_NOTES = "niejednoznaczna odpowiedź modelu; eskalacja do rewrite (fail-safe)"

# KAN-221: domyślny User-Agent. Proxy RunPoda (proxy.runpod.net) zwraca 403 Forbidden dla
# domyślnego UA urllib (Python-urllib), a przepuszcza klienta z jawnym UA. Oba adaptery wysyłają
# ten nagłówek domyślnie, żeby działać ze zdalnym modelem za proxy bez wstrzykiwania transportu.
USER_AGENT = "sztuczny-miodek/1.0"


def _default_http_transport(url, *, data: bytes, headers: dict, timeout: float) -> str:
    """Jedyne miejsce dotykające sieci. Zwraca surowe ciało odpowiedzi (str).

    stdlib only (urllib.request). Wstrzykiwalne — w testach podstawiamy atrapę, więc ta
    funkcja NIGDY nie jest wołana offline. POST z podanym ciałem i nagłówkami."""
    import urllib.request
    import urllib.error
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.URLError as e:
        raise RuntimeError(f"HTTP do {url} nie powiódł się: {e}")


def build_judge_prompt(segment: ReviewSegment) -> str:
    """Buduje treść user-message PO POLSKU z segment.text i segment.hits.

    Wykryte podejrzenia (ID + dopasowany fragment) podajemy jawnie, żeby model wiedział,
    co linter zaznaczył. Pusty text (fallback nieczytelnego pliku) daje wciąż sensowny
    prompt — sama lista trafień. Model proszony jest o JSON {verdict, notes}."""
    lines = ["Akapit do oceny:", '"""', segment.text or "", '"""']
    if segment.hits:
        lines.append("Linter oznaczył w nim następujące podejrzenia (ID + dopasowany fragment):")
        for h in segment.hits:
            hid = h.get("id", "?")
            match = h.get("match", "")
            lines.append(f"- {hid}: \"{match}\"")
    else:
        lines.append("Linter nie podał szczegółowych trafień; oceń akapit całościowo.")
    lines.append("Oceń, czy akapit wymaga przepisania.")
    return "\n".join(lines)


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_model_reply(content: str):
    """Deterministyczne parsowanie odpowiedzi modelu na (verdict, notes).

    Kolejność prób (fail-safe domyślnie "rewrite" — bezpieczniej eskalować niż przepuścić):
      1. wyłuskaj pierwszy blok {...}, json.loads; jeśli verdict ∈ {pass, rewrite} → bierz go,
      2. brak JSON / brak pola: pierwsza niepusta linia zawiera PASS (i nie REWRITE) → pass;
         zawiera REWRITE → rewrite,
      3. cokolwiek niejednoznacznego (oba słowa, żadne, pusto, śmieci) → "rewrite" z notatką.

    Zwraca krotkę (verdict, notes)."""
    text = (content or "").strip()

    # 1. Próba JSON.
    m = _JSON_BLOCK_RE.search(text)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                v = obj.get("verdict")
                if isinstance(v, str):
                    v_norm = v.strip().lower()
                    if v_norm in VERDICTS:
                        notes = obj.get("notes")
                        notes = notes.strip() if isinstance(notes, str) else ""
                        return v_norm, notes
        except (json.JSONDecodeError, ValueError):
            pass

    # 2. Pierwsza niepusta linia: PASS vs REWRITE (jednoznacznie).
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        up = line.upper()
        has_pass = "PASS" in up
        has_rewrite = "REWRITE" in up
        if has_rewrite and not has_pass:
            return "rewrite", line
        if has_pass and not has_rewrite:
            return "pass", line
        break  # pierwsza niepusta linia niejednoznaczna → fallback

    # 3. Fallback: eskalacja do rewrite.
    return "rewrite", _FALLBACK_NOTES


def _extract_openai_content(raw: str) -> str:
    """Wyłuskuje content z koperty OpenAI Chat Completions: choices[0].message.content.

    Wspólne dla OpenRouter i vLLM/RunPod (ta sama koperta). Błąd parsowania / brak pola →
    pusty string (prowadzi do fallbacku "rewrite" w parse_model_reply)."""
    try:
        data = json.loads(raw)
        return data["choices"][0]["message"]["content"] or ""
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return ""


def _extract_ollama_content(raw: str) -> str:
    """Wyłuskuje content z koperty Ollamy /api/chat (stream=false): message.content.

    Błąd parsowania / brak pola → pusty string (fallback "rewrite")."""
    try:
        data = json.loads(raw)
        return data["message"]["content"] or ""
    except (json.JSONDecodeError, KeyError, TypeError):
        return ""


class OpenAICompatEngine(JudgeEngine):
    """Adapter dowolnego endpointu zgodnego z OpenAI Chat Completions (OpenRouter, vLLM/RunPod).

    Konfiguracja: base_url (np. https://openrouter.ai/api/v1), model, api_key (z ENV przez
    api_key_env, nigdy z pliku), opcjonalne extra_headers (np. OpenRouter HTTP-Referer/X-Title).
    name = "openai:<model>" (atrybucja E2/E3). Warstwa HTTP wstrzykiwalna (transport)."""

    def __init__(self, base_url, model, api_key=None, api_key_env="OPENROUTER_API_KEY",
                 extra_headers=None, timeout=60.0, transport=None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key or os.environ.get(api_key_env, "")
        self._extra_headers = dict(extra_headers or {})
        self._timeout = timeout
        self._transport = transport or _default_http_transport
        self.name = f"openai:{model}"

    def judge(self, segment: ReviewSegment) -> Judgement:
        url = self.base_url + "/chat/completions"
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": build_judge_prompt(segment)},
            ],
        }
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT, **self._extra_headers}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        raw = self._transport(
            url, data=json.dumps(body).encode("utf-8"), headers=headers, timeout=self._timeout
        )
        content = _extract_openai_content(raw)
        verdict, notes = parse_model_reply(content)
        return Judgement(verdict=verdict, notes=notes, engine=self.name)


class OllamaEngine(JudgeEngine):
    """Adapter Ollamy po HTTP (POST /api/chat, stream=false) — lokalnej i zdalnej (RunPod).

    Konfiguracja: host (np. http://localhost:11434 albo zdalny RunPod), model (np. bielik).
    /api/chat (nie /api/generate) bo ma role system+user — symetria promptu z OpenAI.
    name = "ollama:<model>" (atrybucja E2/E3). Warstwa HTTP wstrzykiwalna (transport)."""

    def __init__(self, host="http://localhost:11434", model="bielik",
                 timeout=120.0, transport=None):
        self.base_url = host.rstrip("/")
        self.model = model
        self._timeout = timeout
        self._transport = transport or _default_http_transport
        self.name = f"ollama:{model}"

    def judge(self, segment: ReviewSegment) -> Judgement:
        url = self.base_url + "/api/chat"
        body = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": build_judge_prompt(segment)},
            ],
        }
        raw = self._transport(
            url, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            timeout=self._timeout,
        )
        content = _extract_ollama_content(raw)
        verdict, notes = parse_model_reply(content)
        return Judgement(verdict=verdict, notes=notes, engine=self.name)
