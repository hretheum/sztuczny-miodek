---
description: Stage 2 — korektor manieryzmu pliku (pętla do PASS). Używa modelu (silnik z configu/--runpod).
argument-hint: <ścieżka pliku> [--engine ollama|--runpod]
allowed-tools: Bash
---
Uruchom korektor Stage 2 na pliku. To warstwa z modelem (silnik osądu z `config.json`, albo `--runpod` dla Bielika na efemerycznym podzie):

```bash
uvx miodek correct --file $ARGUMENTS
```

Finalny tekst na stdout, raport na stderr. Bez realnego silnika (stub) korektor odmawia — wskaż `--engine ollama` albo `--runpod`.
