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

    def rewrite(self, segment: ReviewSegment, judgement: Judgement) -> str:
        """Przepisuje sporny segment, usuwając manieryzm (zdolność korektora, G2).

        Domyślna implementacja jest NO-OP: zwraca `segment.text` bez zmian. To kontrakt
        ROZSZERZAJĄCY (nie abstrakcyjny), więc istniejące silniki tylko-osądzające (StubJudgeEngine,
        realne adaptery sprzed G2) nie pękają — dziedziczą no-op. Pętla korektora (corrector.py)
        traktuje zwrot równy oryginałowi jako BRAK POSTĘPU i zatrzymuje się (ochrona przed pętlą
        nieskończoną), zamiast psuć tekst.

        Realny silnik (OpenAICompat/Ollama) NADPISUJE tę metodę wywołaniem modelu z promptem
        przepisującym; atrapa korektora (StubRewriteEngine) — deterministyczną neutralizacją wzorca.
        """
        return segment.text


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


# Spójniki, które przy usuwaniu antytezy „X, a nie Y" znikają wraz z dopasowanym fragmentem.
# Detektor PL-ANTI zwraca match w rodzaju „, a nie" / „, nie" / „a nie" — usunięcie match z tekstu
# rozspaja antytezę, więc ponowny audyt jej nie złapie. Zostawiamy oba człony obok siebie.
_TRIADA_TAIL_RE = re.compile(
    r"^(?P<a>.+?)(?P<sep1>,\s*)(?P<b>.+?)(?P<sep2>\s+i\s+|\s+oraz\s+|\s+and\s+)(?P<c>.+)$",
    re.DOTALL,
)


def neutralize_match(text: str, hit: dict) -> str:
    """Deterministycznie neutralizuje JEDEN wykryty wzorzec w `text` tak, by ponowny audyt go nie
    łapał. Strategia regułowa per rodzaj manieryzmu (atrapa korektora, bez sieci, bez modelu):

      - triada „A, B i C" (PL-RHET / EN-TRIAD review): skróć do DWÓCH członów „A i C" (audyt triady
        wymaga trzech — po skróceniu nie trafia),
      - antyteza „X, a nie Y" (PL-ANTI / EN-ANTI): usuń dopasowany spójnik (np. „, a nie") —
        rozspaja konstrukcję, audyt PL-ANTI jej nie widzi,
      - pozostałe (signpost, superlatyw, nadmiar myślników): usuń dopasowany fragment match
        (z normalizacją spacji wokół miejsca cięcia).

    Bezpieczeństwo zbieżności: działamy WYŁĄCZNIE na pierwszym wystąpieniu `hit["match"]` jako
    podłańcucha `text`. Gdy match nie jest podłańcuchem (np. przycięty „…" albo z innego pliku),
    zwracamy `text` BEZ ZMIAN — pętla korektora wykryje brak postępu i zatrzyma się, nigdy nie
    zapętli się w nieskończoność.
    """
    match = (hit or {}).get("match", "") or ""
    mid = (hit or {}).get("id", "") or ""
    if not match or match not in text:
        return text  # nie da się przypiąć dopasowania → brak postępu (świadomy STOP w pętli)

    i = text.index(match)
    before, after = text[:i], text[i + len(match):]

    # 1) Triada: spróbuj rozłożyć match na trzy człony i zostawić dwa.
    m = _TRIADA_TAIL_RE.match(match)
    if m and ("RHET" in mid or "TRIAD" in mid):
        replacement = f"{m.group('a').strip()}{m.group('sep2').rstrip()} {m.group('c').strip()}"
        replacement = re.sub(r"\s+", " ", replacement).strip()
        return before + replacement + after

    # 2) Antyteza: usuń sam spójnik (match to „, a nie" / „a nie" / „, nie"). Sklej człony spacją.
    if "ANTI" in mid:
        joined = (before.rstrip() + " " + after.lstrip()).strip()
        return re.sub(r"[ \t]{2,}", " ", joined)

    # 3) Reszta: usuń dopasowany fragment, znormalizuj spacje wokół cięcia.
    joined = before.rstrip() + ("" if (not after or after[:1] in ".,;:!?") else " ") + after.lstrip()
    joined = re.sub(r"[ \t]{2,}", " ", joined).strip()
    # Wielka litera na początku, jeśli usunęliśmy fragment otwierający zdanie.
    if joined and before.strip() == "" and joined[:1].islower():
        joined = joined[:1].upper() + joined[1:]
    return joined


class StubRewriteEngine(StubJudgeEngine):
    """Atrapa KOREKTORA (G2): osądza jak `StubJudgeEngine`, ale UMIE deterministycznie przepisać.

    `judge` dziedziczy z bazy (≥1 hit review => "rewrite"). `rewrite` neutralizuje KAŻDE trafienie
    review w segmencie przez `neutralize_match`, tak by ponowny audyt już go nie łapał — dzięki temu
    pętla korektora ZBIEGA do PASS bez sieci i bez modelu. Gdy żadnego match nie da się przypiąć,
    `rewrite` zwraca tekst bez zmian (= brak postępu → pętla się zatrzymuje, nie zapętla).

    To rozdziela odpowiedzialności: `StubJudgeEngine` zostaje atrapą TYLKO-osądzającą (jej `rewrite`
    to no-op z bazy, więc testy G1 są nietknięte), a `StubRewriteEngine` jest atrapą korektora G2.
    """

    name = "stub-rewrite"

    def rewrite(self, segment: ReviewSegment, judgement: Judgement) -> str:
        text = segment.text
        for hit in segment.hits:
            text = neutralize_match(text, hit)
        return text


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

# System prompt KOREKTORA (G2). Osobny od JUDGE_SYSTEM_PROMPT: tu model nie ocenia, lecz przepisuje.
# Twarde wymaganie: zwróć WYŁĄCZNIE poprawioną prozę (bez komentarza, bez cudzysłowów), zachowaj sens,
# fakty i rejestr — usuń tylko manieryzm AI.
REWRITE_SYSTEM_PROMPT = (
    "Jesteś redaktorem polszczyzny. Dostajesz JEDEN akapit oznaczony przez linter jako manieryzm AI "
    "(triady „A, B i C”, antytezy „X, a nie Y”, puste superlatywy, nadmiar myślników, signposty). "
    "Przepisz ten akapit, USUWAJĄC manieryzm, ale ZACHOWUJĄC sens, fakty, rejestr i język oryginału. "
    "Nie skracaj treści merytorycznej, nie dodawaj nowych myśli. "
    "Zwróć WYŁĄCZNIE poprawioną prozę: bez komentarza, bez wyjaśnień, bez cudzysłowów, bez opakowania."
)

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


def build_rewrite_prompt(segment: ReviewSegment, judgement: Judgement) -> str:
    """Buduje user-message KOREKTORA (G2) PO POLSKU z segment.text, trafień i notatek osądu.

    Podajemy modelowi co linter zaznaczył (ID + fragment) oraz uzasadnienie osądu (judgement.notes),
    żeby wiedział, CO usunąć. Prosimy o samą poprawioną prozę (egzekwowane też w system prompt)."""
    lines = ["Akapit do przepisania:", '"""', segment.text or "", '"""']
    if segment.hits:
        lines.append("Linter oznaczył w nim manieryzm (ID + dopasowany fragment):")
        for h in segment.hits:
            lines.append(f"- {h.get('id', '?')}: \"{h.get('match', '')}\"")
    if judgement is not None and getattr(judgement, "notes", ""):
        lines.append(f"Uwaga sędziego: {judgement.notes}")
    lines.append("Przepisz akapit bez manieryzmu. Zwróć WYŁĄCZNIE poprawioną prozę.")
    return "\n".join(lines)


def clean_rewrite_reply(content: str, fallback: str) -> str:
    """Wyłuskuje czystą prozę z odpowiedzi modelu korektora.

    Zdejmuje opakowujące potrójne cudzysłowy / pojedyncze cudzysłowy / backticki i białe znaki.
    PUSTA lub bezsensowna odpowiedź → zwraca `fallback` (= oryginalny segment), dzięki czemu pętla
    korektora widzi BRAK POSTĘPU (nie psuje tekstu przy awarii modelu). Fail-safe: nigdy nie
    zwracamy pustego napisu."""
    text = (content or "").strip()
    if not text:
        return fallback
    # zdejmij opakowujące potrójne cudzysłowy / backtick-fence
    for fence in ('"""', "'''", "```"):
        if text.startswith(fence) and text.endswith(fence) and len(text) >= 2 * len(fence):
            text = text[len(fence):-len(fence)].strip()
    # zdejmij pojedyncze opakowujące cudzysłowy
    if len(text) >= 2 and text[0] in "\"'„“" and text[-1] in "\"'”“":
        text = text[1:-1].strip()
    return text or fallback


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

    def rewrite(self, segment: ReviewSegment, judgement: Judgement) -> str:
        """G2: woła model promptem przepisującym; zwraca poprawioną prozę. Pusta/awaryjna
        odpowiedź → oryginał (fallback), by pętla widziała brak postępu zamiast utraty treści."""
        url = self.base_url + "/chat/completions"
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
                {"role": "user", "content": build_rewrite_prompt(segment, judgement)},
            ],
        }
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT, **self._extra_headers}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        raw = self._transport(
            url, data=json.dumps(body).encode("utf-8"), headers=headers, timeout=self._timeout
        )
        return clean_rewrite_reply(_extract_openai_content(raw), fallback=segment.text)


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

    def rewrite(self, segment: ReviewSegment, judgement: Judgement) -> str:
        """G2: woła model (POST /api/chat) promptem przepisującym; zwraca poprawioną prozę.
        Pusta/awaryjna odpowiedź → oryginał (fallback), by pętla widziała brak postępu."""
        url = self.base_url + "/api/chat"
        body = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
                {"role": "user", "content": build_rewrite_prompt(segment, judgement)},
            ],
        }
        raw = self._transport(
            url, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            timeout=self._timeout,
        )
        return clean_rewrite_reply(_extract_ollama_content(raw), fallback=segment.text)


# ============================================================================
# G3 — ROUTING silnika osądu (lejek kosztowy: lekki na masę, mocny na margines).
# ============================================================================
#
# RoutingJudgeEngine OWIJA dwa silniki za tym samym interfejsem JudgeEngine:
#   - primary   — lekki/lokalny model (np. Bielik przez Ollama), osądza KAŻDY segment (na masę),
#   - appellate — mocniejszy model (np. model z najwyższej półki przez OpenRouter), sędzia
#                 apelacyjny dotykany TYLKO trudnego marginesu.
#
# Polityka eskalacji jest KONFIGUROWALNA i UDOKUMENTOWANA. Domyślny przykład (z blueprintu):
#   1) primary osądza segment,
#   2) eskaluj do appellate, gdy primary wyda "rewrite" (potencjalny fałszywy alarm — prosimy o
#      drugą opinię) ALBO segment jest "trudny" (liczba trafień review >= hard_hits_threshold),
#   3) gdy eskalacja: werdykt APELACJI jest ostateczny (sędzia apelacyjny tnie fałszywe alarmy),
#   4) gdy primary "pass" na łatwym segmencie: ufaj primary, appellate NIE jest wołany (oszczędność).
#
# Cel: mocny model dotyka wyłącznie marginesu → koszt rozumowy spada o rzędy wielkości.
#
# .name odzwierciedla skład ("routing:<primary>-><appellate>"). .rewrite deleguje do silnika, który
# wydałby OSTATECZNY werdykt — decyzję podejmuje deterministycznie ta sama polityka should_escalate
# na (segment, judgement), więc rewrite jest bezstanowy (nie polega na ukrytym stanie z judge) i
# bezpieczny w pętli korektora, która woła judge i rewrite osobno.
#
# OGRANICZENIE (known-limitation): routing NIE integruje się z auto-offloadem poda RunPod (KAN-220)
# w tej iteracji. `_is_remote_engine` w runnerze rozpoznaje silnik po prefiksie name ("ollama:" /
# "openai:"); name routingu zaczyna się od "routing:", więc managed_pod się NIE owinie wokół
# routingu nawet gdy owija on silnik zdalny. Lifecycle to osobny epik; tu świadomie zostawiamy to
# jako udokumentowane ograniczenie (mniejsze ryzyko regresji niż rozszerzanie wykrywania).


class RoutingJudgeEngine(JudgeEngine):
    """Routing dwóch silników osądu za interfejsem JudgeEngine (G3 — lejek kosztowy).

    Konstruktor `(primary, appellate, *, escalate_on_rewrite=True, hard_hits_threshold=None)`:
      - primary             : JudgeEngine osądzający KAŻDY segment (lekki/lokalny, na masę),
      - appellate           : JudgeEngine — sędzia apelacyjny dotykany tylko trudnego marginesu,
      - escalate_on_rewrite : gdy True, primary "rewrite" eskaluje do appellate (druga opinia),
      - hard_hits_threshold : gdy ustawiony (int), segment z >= tylu trafieniami review eskaluje
                              niezależnie od werdyktu primary (segment „trudny").

    Polityka eskalacji jest świadoma i bezstanowa — patrz `should_escalate`. Werdykt appellate jest
    ostateczny po eskalacji; bez eskalacji bierzemy werdykt primary (oszczędność). `.name` odzwierciedla
    skład. `.rewrite` deleguje do silnika, który wydał ostateczny werdykt.
    """

    def __init__(self, primary: JudgeEngine, appellate: JudgeEngine, *,
                 escalate_on_rewrite: bool = True, hard_hits_threshold=None):
        if primary is None or appellate is None:
            raise ValueError("RoutingJudgeEngine wymaga primary i appellate (oba JudgeEngine)")
        if hard_hits_threshold is not None:
            if isinstance(hard_hits_threshold, bool) or not isinstance(hard_hits_threshold, int) \
                    or hard_hits_threshold < 1:
                raise ValueError(
                    "hard_hits_threshold musi być None albo dodatnią liczbą całkowitą, "
                    f"jest {hard_hits_threshold!r}"
                )
        self.primary = primary
        self.appellate = appellate
        self.escalate_on_rewrite = bool(escalate_on_rewrite)
        self.hard_hits_threshold = hard_hits_threshold
        self.name = f"routing:{primary.name}->{appellate.name}"

    def should_escalate(self, segment: ReviewSegment, primary_judgement: Judgement) -> bool:
        """Polityka eskalacji (deterministyczna, bezstanowa). True => zapytaj appellate.

        Eskalujemy gdy primary chce ruszyć tekst (potencjalny fałszywy alarm — druga opinia)
        ALBO segment jest „trudny" wg liczby trafień review (>= hard_hits_threshold)."""
        if self.escalate_on_rewrite and primary_judgement.verdict == "rewrite":
            return True
        if self.hard_hits_threshold is not None and len(segment.hits) >= self.hard_hits_threshold:
            return True
        return False

    def judge(self, segment: ReviewSegment) -> Judgement:
        jp = self.primary.judge(segment)
        if not self.should_escalate(segment, jp):
            # Łatwy segment, primary ufny — appellate nie dotknięty (oszczędność, sedno lejka).
            return jp
        ja = self.appellate.judge(segment)
        # Werdykt apelacji jest ostateczny; notatki łączą obie opinie dla audytu.
        notes = (f"[primary {jp.verdict}: {jp.notes}] -> "
                 f"[appellate {ja.verdict}: {ja.notes}]")
        return Judgement(verdict=ja.verdict, notes=notes, engine=ja.engine)

    def rewrite(self, segment: ReviewSegment, judgement: Judgement) -> str:
        """Deleguje przepisanie do silnika, który wydałby OSTATECZNY werdykt.

        Pętla korektora woła judge i rewrite osobno, więc rewrite nie może polegać na stanie z judge.
        Ponawiamy tanią ocenę primary i tę samą politykę `should_escalate(segment, primary_judgement)`:
        gdy eskalacja → appellate.rewrite, inaczej → primary.rewrite. Deterministyczne i bezstanowe."""
        jp = self.primary.judge(segment)
        if self.should_escalate(segment, jp):
            return self.appellate.rewrite(segment, judgement)
        return self.primary.rewrite(segment, judgement)
