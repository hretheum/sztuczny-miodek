---
description: Zbuduj szkic słownika domenowego z korpusu (częstość proponuje, kanon wetuje). Bez LLM.
argument-hint: <ścieżki korpusu> [--out szkic.json]
allowed-tools: Bash
---
Zbuduj szkic słownika domenowego (deterministyczne, bez modelu):

```bash
uvx miodek build-dict $ARGUMENTS
```

Szkic ma `allow` puste, kandydaci w `review` — po przeglądzie przenosisz zaakceptowane do `allow`, potem używasz przez `miodek lint --dict`.
