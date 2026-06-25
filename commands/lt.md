---
description: LanguageTool — pełna korekta polszczyzny (ortografia, gramatyka). Bez LLM; wymaga endpointu.
argument-hint: <ścieżka pliku>
allowed-tools: Bash
---
Uruchom korektę LanguageTool na pliku (wymaga `LANGUAGETOOL_ENDPOINT` w env, np. lokalny serwer `http://localhost:8081/v2/check`):

```bash
uvx miodek lt --file $ARGUMENTS
```

To dostawca poza bramką, na żądanie. Pokaż sugestie; oddziel realne błędy polszczyzny od terminów własnych.
