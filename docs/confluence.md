# Audyt stron Confluence

Miodek czyta strony Confluence przez adapter i audytuje czystą prozę, nie surowy storage. Connector pobiera stronę w formacie storage (XHTML), adapter wyłuskuje tekst z akapitów, a makra, kod i odwołania traktuje jak wyspy nie-prozy i pomija. Tryb `pull` audytuje (read-only), tryb `correct` poprawia prozę i zapisuje zredagowaną wersję z powrotem, z dry-run i jawnym potwierdzeniem.

## Konfiguracja

Poświadczenia idą wyłącznie ze zmiennych środowiskowych (jak klucz RunPod, jak endpoint LanguageTool). Bez nich connector odmawia, więc nic nie łączy się nigdzie bez świadomej konfiguracji:

```bash
export CONFLUENCE_BASE_URL=https://twoja-domena.atlassian.net/wiki
export CONFLUENCE_EMAIL=ty@example.com
export CONFLUENCE_TOKEN=...   # token API Atlassiana
```

Wzór w `.env.example`. Token o zawężonym zakresie (tylko odczyt treści) jest bezpieczniejszy, zgodnie z zasadą najmniejszych uprawnień.

### Wiele instancji

Do obsługi kilku przestrzeni Confluence (na przykład osobistej i firmowej) bez podmiany zmiennych użyj nazwanych slotów. Slot to zestaw z prefiksem `CONFLUENCE_<NAZWA>_`:

```bash
export CONFLUENCE_TC_BASE_URL=https://twoja-domena.atlassian.net/wiki
export CONFLUENCE_TC_EMAIL=ty@example.com
export CONFLUENCE_TC_TOKEN=...
```

Flaga `--instance tc` wybiera ten slot:

```bash
miodek confluence pull --page 11763713 --instance tc
```

Nazwa instancji jest normalizowana do wielkich liter (`--instance tc` szuka `CONFLUENCE_TC_*`). Bez flagi `--instance` używany jest domyślny zestaw `CONFLUENCE_*`. Brak slotu wskazanej instancji daje czytelny błąd z nazwami brakujących zmiennych.

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

## Correct: korekta prozy i zapis zwrotny

Tryb `correct` poprawia prozę korektorem (Stage 2) i zapisuje zredagowaną wersję z powrotem do Confluence. Makra, kod i struktura zostają nietknięte, edytowane są wyłącznie akapity prozy.

```bash
miodek confluence correct --page 11763713 --engine ollama
```

Domyślnie to **dry-run**: narzędzie pokazuje diff proponowanej korekty prozy i nic nie zapisuje. Zapis wymaga jawnej flagi `--apply` oraz interaktywnego potwierdzenia per strona. Flaga `--yes` pomija potwierdzenie (dla CI, tylko w parze z `--apply`).

Flagi:
- `--page ID [ID ...]` — strony do poprawy.
- `--engine stub|openai|ollama` — silnik korekty (nadpisuje `config.json`). Atrapa `stub` zwykle nic nie zmienia, realna korekta wymaga silnika `openai`/`ollama` z żywym endpointem.
- `--apply` — zapisz zmiany. Bez tej flagi: dry-run.
- `--yes` — pomiń potwierdzenie (CI).

Bezpieczeństwo zapisu:
- przed każdym zapisem twarda weryfikacja wierności: nowy storage może różnić się od oryginału wyłącznie prozą. Gdyby zmiana dotknęła makra albo struktury, narzędzie przerywa i nie zapisuje;
- zapis tworzy nową wersję strony (numer o jeden wyższy), z komentarzem wersji, więc łatwo go cofnąć;
- konflikt wersji (ktoś edytował stronę w międzyczasie) przerywa zapis, bez nadpisania cudzej zmiany;
- ponowny przebieg bez zmian pomija zapis, więc nie pompuje numeru wersji.

[← Powrót do README](../README.md)
