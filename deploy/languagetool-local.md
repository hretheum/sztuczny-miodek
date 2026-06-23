# LanguageTool lokalnie (G4) — serwer korekty polszczyzny bez wysyłania tekstu na zewnątrz

G4 to opcjonalny dostawca pełnej korekty polszczyzny (ortografia, gramatyka, interpunkcja), poza bramką, na żądanie. Klient (`languagetool.py`) jest cienki i bez zależności; serwer LanguageTool stoi obok. Ta nota opisuje uruchomienie serwera lokalnie, żeby tekst nie opuszczał maszyny.

## Wybór endpointu (klient)

`resolve_endpoint()` rozstrzyga z priorytetem: flaga `--endpoint` przed zmienną `LANGUAGETOOL_ENDPOINT`. Domyślnego endpointu NIE ma (KAN-225): bez wyboru zgłasza błąd, więc nie wysyła tekstu nigdzie. Zmienna jest czytana przy każdym wywołaniu. Żeby kierować G4 na lokalny serwer bez wysyłki na zewnątrz:

```bash
export LANGUAGETOOL_ENDPOINT=http://localhost:8081/v2/check
python3 tools/languagetool_check.py --file tekst.md
```

Bez tej zmiennej i bez flagi klient zgłasza błąd i prosi o wybór jednej z dwóch dróg (KAN-225). Nie wysyła tekstu nigdzie domyślnie.

## Serwer lokalny (macOS, Homebrew)

LanguageTool 6.x jako usługa Homebrew, port 8081, tylko localhost:

```bash
brew install languagetool
brew services start languagetool
brew services list | grep languagetool          # status
tail -f /opt/homebrew/var/log/languagetool/languagetool-server.log   # log
```

## Wykrywanie języka przez fastText

Domyślne wykrywanie języka LanguageTool jest słabe na krótkich tekstach. Lepsze jest fastText z modelem `lid.176`. Konfiguracja w `/opt/homebrew/etc/languagetool/server.properties`:

```
fasttextModel=/ścieżka/do/fastText/lid.176.bin
fasttextBinary=/ścieżka/do/fastText/fasttext
```

Binarka fastText (zbudowana lokalnie) i model `lid.176.bin` (około 125 MB, pobrany) leżą poza repozytoriami z kodem i dokumentacją (to narzędzie i model, nie kod projektu). Po edycji `server.properties` przeładuj serwer:

```bash
brew services restart languagetool
```

Sprawdzenie, że fastText wpięty: log serwera potwierdza ładowanie modelu, a zapytanie z `language=auto` na polskim zdaniu zwraca `pl-PL`.

## Walidacja

```bash
LANGUAGETOOL_ENDPOINT=http://localhost:8081/v2/check python3 - <<'PY'
import languagetool as LT
print("endpoint:", LT.resolve_endpoint())
for s in LT.check_text("Ide do domu.", language="pl-PL"):
    print(s.rule_id, "->", s.replacements[:2])
PY
```

Oczekiwane: endpoint lokalny, sugestia `MORFOLOGIK_RULE_PL_PL` z poprawką `Idę`.
