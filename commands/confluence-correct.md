---
description: Stage 2 — korekta strony Confluence i zapis zwrotny. Używa modelu. Dry-run domyślny.
argument-hint: <ID strony> [--instance nazwa] [--runpod] [--apply]
allowed-tools: Bash
---
Popraw prozę strony Confluence korektorem i (z `--apply`) zapisz nową wersję. Warstwa z modelem; wymaga `CONFLUENCE_*` w env. DRY-RUN jest domyślny — bez `--apply` pokazuje tylko diff:

```bash
uvx miodek confluence correct --page $ARGUMENTS
```

Makra i struktura nietknięte (twarda weryfikacja przed zapisem). Pokaż diff; zapis dopiero po świadomym dodaniu `--apply`.
