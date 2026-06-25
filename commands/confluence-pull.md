---
description: Audyt prozy strony Confluence (read-only, bez LLM). Wymaga poświadczeń w env.
argument-hint: <ID strony> [--instance nazwa]
allowed-tools: Bash
---
Pobierz stronę Confluence przez adapter i zaudytuj czystą prozę (read-only, bez modelu). Wymaga `CONFLUENCE_*` w env (lub `CONFLUENCE_<INSTANCJA>_*` przy `--instance`); jeśli trzeba, najpierw `set -a; source .env; set +a`:

```bash
uvx miodek confluence pull --page $ARGUMENTS --out ./audyt --report
```

Adapter pomija makra i kod. Pokaż werdykt; wyłuskana proza ląduje w `./audyt`.
