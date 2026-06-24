# Audyt stron Confluence

Miodek czyta strony Confluence przez adapter i audytuje czystą prozę, nie surowy storage. Connector pobiera stronę w formacie storage (XHTML), adapter wyłuskuje tekst z akapitów, a makra, kod i odwołania traktuje jak wyspy nie-prozy i pomija. To tryb tylko do odczytu; zapis zredagowanej wersji z powrotem do Confluence to osobny, kolejny krok.

## Konfiguracja

Poświadczenia idą wyłącznie ze zmiennych środowiskowych (jak klucz RunPod, jak endpoint LanguageTool). Bez nich connector odmawia, więc nic nie łączy się nigdzie bez świadomej konfiguracji:

```bash
export CONFLUENCE_BASE_URL=https://twoja-domena.atlassian.net/wiki
export CONFLUENCE_EMAIL=ty@example.com
export CONFLUENCE_TOKEN=...   # token API Atlassiana
```

Wzór w `.env.example`. Token o zawężonym zakresie (tylko odczyt treści) jest bezpieczniejszy, zgodnie z zasadą najmniejszych uprawnień.

## Pull: audyt prozy strony

```bash
miodek confluence pull --page 11763713
```

Connector pobiera stronę, adapter wyłuskuje prozę, a linter audytuje ją jak zwykły tekst. Wyłuskana proza ląduje jako plik `.txt` w katalogu `--out` (domyślnie `./conflu`), więc audyt możesz powtórzyć offline albo obejrzeć dokładnie, co poszło do lintera.

Flagi:
- `--page ID [ID ...]` — jedna lub wiele stron po identyfikatorze.
- `--out KATALOG` — gdzie zapisać wyłuskaną prozę (domyślnie `./conflu`).
- `--lang pl|en|both` — katalog reguł (domyślnie `both`).
- `--report` — zbiorczy agregat `== BATCH ==` (przydatny przy wielu stronach).

Kod wyjścia jest zbiorczy: `1`, gdy którakolwiek strona kończy się werdyktem `FAIL`/`FAIL-HARD`.

## Co adapter pomija

Storage Confluence to nie czysty HTML. Adapter traktuje jak wyspy nie-prozy i pomija ich zawartość:
- makra `ac:structured-macro` wraz z parametrami i ciałem (panele, spis treści, status, osadzenia),
- bloki kodu (`ac:plain-text-body`, `pre`, `code`),
- odwołania i linki (`ac:link`, `ri:page`, `ri:user`, `ri:attachment`, osadzone obrazy).

Dzięki temu audyt widzi tekst dla czytelnika, a nie nazwy makr ani parametry. Proza z akapitów (`<p>`, `<li>`, `<h1>`-`<h6>`, `<blockquote>`) jest analizowana normalnie.

[← Powrót do README](../README.md)
