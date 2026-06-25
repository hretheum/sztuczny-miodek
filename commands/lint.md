---
description: Stage 1 — deterministyczny audyt prozy (manieryzm AI + polszczyzna). Bez LLM, 0 tokenów.
argument-hint: <ścieżki lub glob, np. raport.md albo ./docs>
allowed-tools: Bash
---
Uruchom deterministyczny linter (bez modelu) na wskazanych plikach i pokaż wynik:

```bash
uvx miodek lint --lang both --report $ARGUMENTS
```

To warstwa deterministyczna. Odczytaj blok `== SUMMARY ==`: zero blokerów = PASS, blokery = FAIL. Nie dokładaj własnej interpretacji ponad werdykt.
