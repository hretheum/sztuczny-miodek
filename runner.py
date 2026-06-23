#!/usr/bin/env python3
"""
runner.py — runner Stage 2: orkiestracja osądu modelu na wycinku z manifestu (Epik G, G1).

FUNDAMENT ORKIESTRACJI. Bierze gotowy MANIFEST lintera (Stage 1), wybiera segmenty (akapity)
zawierające trafienia klasy "review", woła WYMIENIALNY silnik osądu (engines.JudgeEngine) i agreguje
werdykt według bramki "PASS z uwagami to NIE PASS".

Granica wymienialności: runner zna TYLKO `JudgeEngine.judge`. Podmiana silnika (atrapa → lokalny
model → API) = inny argument `engine`, ZERO zmian w runnerze. Domyślny silnik to atrapa
`StubJudgeEngine` — deterministyczna, bez LLM i bez sieci (rdzeń jest ZERO-DEP, stdlib).

JEDNO ŹRÓDŁO PRAWDY „co idzie do Stage 2": `select_review_segments` opiera się na tej samej funkcji
`metrics.review_paragraphs_for_file`, której E1 używa do liczenia `routed_words`. Dzięki temu zbiór
segmentów osądzanych przez runner jest DOKŁADNIE tym samym zbiorem, który E1 raportuje jako
routowany do modelu. Mapowanie linii i wybór adaptera pochodzą z `ai_linter` (przez metrics), nie są
reimplementowane.

BRAMKA (surowa): gate == "FAIL", gdy jakikolwiek osąd ma verdict == "rewrite". gate == "PASS"
tylko gdy wszystkie osądy to "pass" (lub brak segmentów review). To realizacja zasady „PASS
z uwagami to NIE PASS": jedno trafienie wymagające ruchu zamyka całość. Twarde blokery (klasa
"block") linter zamyka sam na Stage 1 — do Stage 2 nie docierają, więc runner ich nie ocenia.

ROZSZERZALNOŚĆ (E2/E3): API zaprojektowane tak, by dołożyć instrumentację (E3: zapis każdego
osądu do strumienia decyzji) i atrybucję (E2) BEZ przeróbki rdzenia. Parametry-haki `log_path`
i `ts_provider` są przyjmowane już teraz; ich obsługę (zapis JSONL) dokłada E3 w jednym miejscu
(`_emit_stage2_run`), nie ruszając selekcji ani bramki.

INSTRUMENTACJA E3 (wspólny strumień z D4): gdy `run_stage2` dostanie `log_path`, każdy osąd Stage 2
dopisuje się do TEGO SAMEGO logu JSONL co ręczne decyzje operatora (D4, `decision_log.py`). Wpisy
rozróżnia nowe pole `kind`: brak `kind` lub `"decision"` to wpis D4 (accept/reject), `"stage2_run"`
to automatyczny osąd Stage 2. Wstecznie zgodne: istniejące wpisy D4 nie mają `kind`, a walidacja D4
(`_REQUIRED = ts/verdict/id/fragment`) zostaje nietknięta. Mapowanie osądu na wymagane pola D4:
`verdict` = `pass`→`accept`, `rewrite`→`reject` (reject = „trafienie słuszne, do poprawy"),
`id` = ID trafienia, `fragment` = `match`. Pola `engine`, `stage2_verdict`, `stage2_notes`, `kind`,
`klasa`, `file`, `line` są dodatkowe (D4 ignoruje nieznane pola). Tym samym log decyzji staje się
wspólnym strumieniem audytu: ręczne decyzje (D4) i automatyczne osądy (E3) w jednym JSONL,
filtrowane po `kind`. Jeden wpis = jedno trafienie review w segmencie (segment z N trafieniami daje
N wpisów — atrybucja per reguła jest wtedy ziarnista).
"""

import json
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import metrics  # noqa: E402  (review_paragraphs_for_file — jedno źródło prawdy selekcji)
import decision_log  # noqa: E402  (E3: wspólny strumień JSONL z D4 — append_decision/read_decisions)
import config  # noqa: E402  (KAN-218: load_stage2 — wybór silnika Stage 2 z configu)
import runpod_lifecycle  # noqa: E402  (KAN-220: auto-offload poda RunPod po przebiegu Stage 2)
from engines import (  # noqa: E402
    JudgeEngine, ReviewSegment, StubJudgeEngine, OpenAICompatEngine, OllamaEngine,
    RoutingJudgeEngine,
)

# Wartość pola `kind` dla wpisów instrumentacji E3 (odróżnia je od wpisów D4 accept/reject).
STAGE2_KIND = "stage2_run"

# Prefiksy nazw silników ZDALNYCH (engine.name == "ollama:<m>" / "openai:<m>"). Tylko dla nich
# auto-offload poda ma sens — atrapa (stub) jest lokalna, nie ma żadnego poda do gaszenia (KAN-220).
_REMOTE_ENGINE_PREFIXES = ("ollama:", "openai:")


def _is_remote_engine(engine):
    """True, gdy silnik osądu jest zdalny (ollama/openai), więc stoi za nim pod do auto-offloadu.

    Atrapa (`stub`) jest lokalna — zwraca False (managed_pod się NIE owija). Wzór z blueprintu
    KAN-220: `engine.name.startswith(("ollama:", "openai:"))`."""
    return str(getattr(engine, "name", "")).startswith(_REMOTE_ENGINE_PREFIXES)

# Mapowanie werdyktu Stage 2 (pass/rewrite) na werdykt D4 (accept/reject), by wpis przeszedł
# walidację decision_log (_REQUIRED zawiera verdict ∈ {accept, reject}). Sens: rewrite = trafienie
# słuszne wymagające ruchu = reject (false-positive odwrotnie: pass = trafienie do zaakceptowania).
_VERDICT_MAP = {"pass": "accept", "rewrite": "reject"}


def select_review_segments(manifest, file_reader=metrics._default_file_reader):
    """Wybiera z manifestu segmenty (akapity) do osądu Stage 2.

    Zwraca listę `engines.ReviewSegment` — dokładnie te akapity, które E1 liczy jako routed_words
    (wspólna funkcja `metrics.review_paragraphs_for_file`). Akapity z samym trafieniem "block"
    oraz akapity czyste NIE trafiają tu.

    Kolejność: pliki w kolejności z manifestu["summary"], akapity w kolejności dokumentu.

    Wariant awaryjny (plik nieczytelny, a ma trafienia review): tworzony jest jeden ReviewSegment
    zastępczy obejmujący całość trafień pliku (text pusty, seg_index 0) — spójnie z fallbackiem E1,
    który wtedy traktuje cały plik jako routed. Dzięki temu runner nie gubi trafień, których nie da
    się przypiąć do akapitu.
    """
    hits = manifest.get("hits", [])
    summaries = manifest.get("summary", [])

    review_by_file = {}
    for h in hits:
        if h.get("klasa") == "review":
            review_by_file.setdefault(h.get("file"), []).append(h)

    segments = []
    for s in summaries:
        fpath = s.get("file")
        file_reviews = review_by_file.get(fpath, [])
        if not file_reviews:
            continue

        mapped = metrics.review_paragraphs_for_file(fpath, file_reviews, file_reader=file_reader)
        if mapped is None:
            # Fallback: pliku nie da się odczytać — jeden segment zastępczy z całością trafień.
            line = min((h.get("line", 1) for h in file_reviews), default=1)
            segments.append(ReviewSegment(
                file=fpath, seg_index=0, line=line, text="", hits=list(file_reviews),
            ))
            continue

        for idx, (seg, seg_hits) in enumerate(mapped):
            segments.append(ReviewSegment(
                file=fpath, seg_index=idx, line=seg.line, text=seg.text, hits=list(seg_hits),
            ))

    return segments


def _default_ts_provider():
    """Domyślny dostawca znacznika czasu: bieżąca chwila ISO 8601 UTC.

    Wstrzykiwalny przez `ts_provider`, żeby test podał stały znacznik (determinizm) bez sięgania do
    zegara. Produkcja używa tej funkcji domyślnie."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _emit_stage2_run(judgement, segment, hit, log_path, ts_provider):
    """Hak instrumentacji E3: zapis JEDNEGO osądu (per trafienie review) do strumienia decyzji.

    Dopisuje wpis `kind="stage2_run"` przez `decision_log.append_decision` — TEN SAM append-only
    JSONL co log decyzji D4. Reużywa warstwy zapisu D4 (nie duplikuje I/O plikowego). Sygnatura
    jest stała, więc pętla `run_stage2` go tylko woła. NO-OP, dopóki `log_path` jest None
    (wywoływane wyłącznie spod warunku w `run_stage2`).

    Mapowanie na wymagane pola D4 (ts/verdict/id/fragment) plus pola dodatkowe (kind/engine/…)."""
    ts = (ts_provider or _default_ts_provider)()
    entry = {
        "kind": STAGE2_KIND,
        "ts": ts,
        "verdict": _VERDICT_MAP.get(judgement.verdict, "reject"),
        "id": hit.get("id"),
        "fragment": hit.get("match", ""),
        "klasa": hit.get("klasa", "review"),
        "file": segment.file,
        "line": hit.get("line", segment.line),
        "engine": judgement.engine,
        "stage2_verdict": judgement.verdict,
        "stage2_notes": judgement.notes,
    }
    decision_log.append_decision(entry, log_path)
    return entry


def read_stage2_runs(log_path=decision_log.DEFAULT_LOG_PATH):
    """Czyta ze wspólnego strumienia tylko wpisy instrumentacji E3 (`kind == "stage2_run"`).

    Filtr po `kind` rozdziela strumienie bez kolizji: `decision_log.read_decisions` widzi wszystkie
    wpisy (D4 + E3), a ta funkcja zwraca wyłącznie automatyczne osądy Stage 2. Wpisy D4 (bez pola
    `kind`) są pomijane."""
    return [w for w in decision_log.read_decisions(log_path) if w.get("kind") == STAGE2_KIND]


def run_stage2(manifest, engine: JudgeEngine = None, file_reader=metrics._default_file_reader,
               log_path=None, ts_provider=None):
    """Uruchamia Stage 2 na manifeście: selekcja review → osąd silnikiem → agregacja + bramka.

    Argumenty:
        manifest    — dict {"hits":[...], "summary":[...]} (kontrakt między etapami).
        engine      — wymienialny JudgeEngine; domyślnie atrapa StubJudgeEngine().
        file_reader — wstrzykiwalny czytnik treści (testy podają treść w pamięci, bez I/O).
        log_path    — (E3) ścieżka wspólnego strumienia decyzji JSONL (D4 + E3). Gdy podana, każdy
                      osąd dopisuje wpis kind="stage2_run" przez decision_log.append_decision.
                      None (domyślnie) = bez instrumentacji (zachowanie G1 bez zmian).
        ts_provider — (E3) dostawca znacznika czasu (callable bez argumentów → str ISO 8601 UTC).
                      None = bieżąca chwila UTC. Test podaje stały znacznik (determinizm).

    Zwraca:
        {
          "segments": [{file, seg_index, line, verdict, engine, notes, hit_ids}],
          "judged": N,           # liczba osądzonych segmentów
          "rewrite": M,          # liczba werdyktów "rewrite"
          "pass": K,             # liczba werdyktów "pass"
          "engine": nazwa_silnika,
          "gate": "PASS" | "FAIL"  # FAIL, gdy jakikolwiek verdict == "rewrite" (bramka surowa)
        }
    """
    if engine is None:
        engine = StubJudgeEngine()

    segments = select_review_segments(manifest, file_reader=file_reader)

    out_segments = []
    n_rewrite = 0
    n_pass = 0
    for seg in segments:
        j = engine.judge(seg)
        if j.verdict == "rewrite":
            n_rewrite += 1
        else:
            n_pass += 1

        out_segments.append({
            "file": seg.file,
            "seg_index": seg.seg_index,
            "line": seg.line,
            "verdict": j.verdict,
            "engine": j.engine,
            "notes": j.notes,
            "hit_ids": seg.hit_ids(),
        })

        # Instrumentacja E3: gdy log_path podane, dopisz wpis stage2_run per trafienie review
        # do wspólnego strumienia JSONL (D4 + E3). Bez log_path — zachowanie G1 bez zmian.
        if log_path is not None:
            for hit in seg.hits:
                _emit_stage2_run(j, seg, hit, log_path, ts_provider)

    gate = "FAIL" if n_rewrite > 0 else "PASS"

    return {
        "segments": out_segments,
        "judged": len(out_segments),
        "rewrite": n_rewrite,
        "pass": n_pass,
        "engine": engine.name,
        "gate": gate,
    }


def _build_single_engine(sub_cfg):
    """Buduje JEDEN nie-routujący silnik z pod-configu o kształcie sekcji `stage2`.

    Pod-config: `{"engine": "stub"|"openai"|"ollama", <sekcja silnika>}`. Wydzielone z
    `build_engine_from_config`, by routing (G3) mógł zbudować primary i appellate REKURENCYJNIE
    tą samą logiką. Zakaz `engine: "routing"` tutaj — routing nie zagnieżdża się w sobie (płaski,
    jednopoziomowy; ochrona przed cyklem/nieskończoną rekurencją). Klucz API NIE jest tu czytany —
    robi to konstruktor silnika z os.environ.

    Mapowanie:
      stub   → StubJudgeEngine() (domyślny, zero-dep, bez sieci),
      openai → OpenAICompatEngine z `openai` (base_url/model/api_key_env/extra_headers),
      ollama → OllamaEngine z `ollama` (host/model)."""
    engine = sub_cfg.get("engine", "stub")
    if engine == "routing":
        raise ValueError(
            "stage2.routing.{primary,appellate} nie może mieć engine='routing' "
            "(routing jest jednopoziomowy — bez zagnieżdżania)"
        )
    if engine == "stub":
        return StubJudgeEngine()
    if engine == "openai":
        o = sub_cfg.get("openai", {})
        if not o.get("base_url") or not o.get("model"):
            raise ValueError("stage2.openai wymaga base_url i model (uzupełnij config.json)")
        return OpenAICompatEngine(
            base_url=o["base_url"], model=o["model"],
            api_key_env=o.get("api_key_env", "OPENROUTER_API_KEY"),
            extra_headers=o.get("extra_headers"),
        )
    if engine == "ollama":
        o = sub_cfg.get("ollama", {})
        if not o.get("model"):
            raise ValueError("stage2.ollama wymaga model (uzupełnij config.json)")
        return OllamaEngine(
            host=o.get("host", "http://localhost:11434"), model=o["model"],
        )
    raise ValueError(f"nieznany silnik Stage 2: {engine!r} (dozwolone: stub, openai, ollama)")


def build_engine_from_config(name=None, config_path=config.CONFIG_PATH):
    """Buduje instancję silnika Stage 2 z konfiguracji (KAN-218, rozszerzone o routing w G3).

    `name` (jeśli podane) nadpisuje `stage2.engine` z configu — pozwala wymusić silnik z CLI.
    `name=None` → użyj `engine` z `config.load_stage2` (fallback: "stub", gdy brak sekcji/configu).

    Mapowanie:
      stub    → StubJudgeEngine() (domyślny, zero-dep, bez sieci),
      openai  → OpenAICompatEngine z `stage2.openai`,
      ollama  → OllamaEngine z `stage2.ollama`,
      routing → RoutingJudgeEngine (G3): primary i appellate budowane REKURENCYJNIE z
                `stage2.routing.{primary,appellate}` (każdy to pod-config jak dzisiejsze stage2),
                polityka z `stage2.routing.{escalate_on_rewrite,hard_hits_threshold}`.

    Klucz API NIE jest tu czytany — robi to konstruktor silnika z os.environ (separacja:
    config = co, ENV = sekret). Realny silnik zadziała tylko z siecią; to świadomy wybór
    operatora, nie ścieżka testowa."""
    cfg = config.load_stage2(config_path)
    engine = name or cfg.get("engine", "stub")

    if engine == "routing":
        routing = cfg.get("routing", {})
        primary = _build_single_engine(routing.get("primary", {}))
        appellate = _build_single_engine(routing.get("appellate", {}))
        return RoutingJudgeEngine(
            primary, appellate,
            escalate_on_rewrite=routing.get("escalate_on_rewrite", True),
            hard_hits_threshold=routing.get("hard_hits_threshold"),
        )
    return _build_single_engine({"engine": engine, **{k: v for k, v in cfg.items() if k != "engine"}})


def run_stage2_managed(manifest, engine, config_path=config.CONFIG_PATH,
                       file_reader=metrics._default_file_reader, log_path=None, ts_provider=None):
    """Owija run_stage2 w auto-offload poda RunPod (KAN-220), gdy silnik jest zdalny.

    JEDNO ŹRÓDŁO PRAWDY orkiestracji lifecycle: woła ją zarówno CLI runnera (`_main`), jak i
    bramka przed publikacją (F3, `tools/publish_gate.py`). Dzięki temu F3 dostaje auto-gaszenie
    poda za darmo, a wzór `load_lifecycle + _is_remote_engine + managed_pod` nie jest duplikowany.

    Kontrakt: identyczny zwrot co run_stage2. Owijanie managed_pod aktywne TYLKO gdy
    `lifecycle.manage` ORAZ silnik zdalny (ollama/openai) — za atrapą/lokalnym silnikiem ścieżka
    jest IDENTYCZNA jak run_stage2 (NO-OP). To realizuje „bez żywego endpointu => zero sieci":
    domyślny config (stub, manage=false) nigdy nie buduje klienta RunPoda."""
    lifecycle = config.load_lifecycle(config_path)
    if lifecycle.get("manage") and _is_remote_engine(engine):
        client = runpod_lifecycle.build_client_from_lifecycle(lifecycle)
        with runpod_lifecycle.managed_pod.from_config(client, lifecycle):
            return run_stage2(manifest, engine=engine, file_reader=file_reader,
                              log_path=log_path, ts_provider=ts_provider)
    return run_stage2(manifest, engine=engine, file_reader=file_reader,
                      log_path=log_path, ts_provider=ts_provider)


def build_ephemeral_runpod(config_path=config.CONFIG_PATH, *, client_transport=None,
                           pod_up_transport=None, pod_up=None, wait_kwargs=None):
    """KAN-222: buduje menedżer EFEMERYCZNEGO poda RunPod z sekcji config `stage2.runpod`.

    JEDNO ŹRÓDŁO PRAWDY orkiestracji --runpod: woła ją runner._main, corrector._main oraz
    tools/publish_gate.main. Każde CLU dostaje ten sam menedżer (managed_ephemeral_pod), więc
    create→wait→ensure_model→terminate nie jest duplikowane.

    Zwraca `runpod_lifecycle.managed_ephemeral_pod`. Parametry wstrzykiwalne (`client_transport`,
    `pod_up_transport`, `pod_up`, `wait_kwargs`) wyłącznie do testów offline — produkcja używa
    domyślnych (realny transport REST i moduł runpod_pod_up). UWAGA: `client_transport` (kontrakt
    RunPodClient) i `pod_up_transport` (kontrakt launchera) to DWA NIEZGODNE kontrakty — osobno."""
    rp = config.load_runpod(config_path)
    return runpod_lifecycle.managed_ephemeral_pod.from_config(
        rp, client_transport=client_transport, pod_up_transport=pod_up_transport,
        pod_up=pod_up, wait_kwargs=wait_kwargs,
    )


def build_runpod_engine(config_path=config.CONFIG_PATH, pod=None):
    """KAN-222: buduje OllamaEngine wskazujący na URL świeżego efemerycznego poda (`pod.url`).

    Model brany z sekcji `stage2.runpod` (ten sam tag co ensure_model), więc engine.name =
    "ollama:<model>" — spójna atrybucja E2/E3 i zdalny prefiks (gdyby ktoś owijał lifecycle).
    `pod` to wszedłszy w kontekst managed_ephemeral_pod (ma .url). Bez sieci tutaj — sam konstruktor."""
    rp = config.load_runpod(config_path)
    return OllamaEngine(host=pod.url, model=rp["model"])


def _load_manifest(path):
    """Wczytuje manifest z pliku JSON; '-' = stdin."""
    if path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _main(argv=None):
    """CLI: runner.py --manifest plik.json [--engine stub].

    Wypisuje raport + JSON; exit 1, gdy gate == "FAIL" (gate-owalne w CI/pre-publish)."""
    import argparse
    ap = argparse.ArgumentParser(
        description="Runner Stage 2: osąd modelu na segmentach review z manifestu (G1)."
    )
    ap.add_argument("--manifest", required=True, help="Ścieżka do manifestu JSON ('-' = stdin).")
    ap.add_argument("--engine", default=None, choices=("stub", "openai", "ollama", "routing"),
                    help="Silnik osądu. Domyślnie czytany z config.json (sekcja stage2; fallback "
                         "'stub'). 'openai'/'ollama' wymagają sieci — świadomy wybór operatora. "
                         "'routing' wymaga sekcji stage2.routing (primary + appellate).")
    ap.add_argument("--config", default=config.CONFIG_PATH,
                    help="Ścieżka do config.json (sekcja stage2). Domyślnie config repo.")
    ap.add_argument("--runpod", action="store_true",
                    help="KAN-222: jeden krok zamiast ręcznej sekwencji. Postaw EFEMERYCZNY pod "
                         "z wolumenu (parametry stage2.runpod), osądź na realnym Bieliku (Ollama), "
                         "zgaś pod automatycznie. Nadpisuje --engine i lifecycle. Wymaga "
                         "RUNPOD_API_KEY w ENV.")
    args = ap.parse_args(argv)

    manifest = _load_manifest(args.manifest)

    if args.runpod:
        # KAN-222: efemeryczny pod SAM jest owijaczem (create→...→terminate). Wewnątrz wołamy
        # CZYSTY run_stage2 (bez lifecycle-owijania — pod już zarządzany przez ten kontekst).
        with build_ephemeral_runpod(args.config) as pod:
            engine = build_runpod_engine(args.config, pod=pod)
            result = run_stage2(manifest, engine=engine)
    else:
        engine = build_engine_from_config(name=args.engine, config_path=args.config)
        # KAN-220: auto-offload poda RunPod. Orkiestracja lifecycle wydzielona do
        # run_stage2_managed (jedno źródło prawdy, reużywane przez F3). Owijanie managed_pod
        # aktywne TYLKO gdy lifecycle.manage ORAZ silnik zdalny; domyślnie (stub / manage=false)
        # ścieżka jest IDENTYCZNA jak dotąd (NO-OP). Kontrakt run_stage2 nietknięty.
        result = run_stage2_managed(manifest, engine=engine, config_path=args.config)

    print(f"Stage 2 (silnik: {result['engine']}): osądzono {result['judged']} segmentów review "
          f"→ rewrite {result['rewrite']}, pass {result['pass']} → BRAMKA: {result['gate']}")
    for seg in result["segments"]:
        ids = ", ".join(str(i) for i in seg["hit_ids"])
        print(f"  [{seg['verdict']:>7}] {seg['file']}:{seg['line']} ({ids}) — {seg['notes']}")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))

    sys.exit(1 if result["gate"] == "FAIL" else 0)


if __name__ == "__main__":
    _main()
