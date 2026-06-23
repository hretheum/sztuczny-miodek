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
