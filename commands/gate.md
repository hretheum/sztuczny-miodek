---
description: Bramka przed publikacją — pełny werdykt na wskazanych plikach. Bez LLM (Stage 1).
argument-hint: <ścieżki plików prozy do publikacji>
allowed-tools: Bash
---
Uruchom bramkę przed publikacją (deterministyczna, bez modelu):

```bash
uvx miodek gate $ARGUMENTS
```

Kod wyjścia 0 = publikacja dozwolona, niezerowy = zablokowana. Pokaż werdykt bez dodatkowej interpretacji.
