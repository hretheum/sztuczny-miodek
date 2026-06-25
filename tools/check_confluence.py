#!/usr/bin/env python3
"""
check_confluence.py — gate connectora i adaptera Confluence (KAN-233). ZERO-DEP, ZERO sieci.

Sprawdza offline (atrapa transportu, nie dotykamy Confluence):
  1. resolve_config bez ENV => ConfluenceNotConfigured (nic nie łączy się bez konfiguracji),
  2. fetch_page z atrapą transportu => poprawnie sparsowana ConfluencePage (storage, wersja, tytuł),
  3. ConfluenceStorageAdapter wyłuskuje czystą prozę: makra ac:/ri: i ich parametry POMINIĘTE,
     proza z <p>/<li>/<h*> zachowana (czyste treści, nie zupa tagów).

Exit 1 na rozjeździe (gate w run_tests.sh).
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from miodek import confluence  # noqa: E402
from miodek import adapter as adp  # noqa: E402

# Próbka odpowiedzi API (storage z makrem info, parametrem, blokiem kodu i odwołaniem ri:page).
_SAMPLE_JSON = (
    '{"id":"123","title":"Próbna strona","version":{"number":7},"space":{"key":"TO"},'
    '"body":{"storage":{"value":'
    '"<p>Pierwszy akapit prozy.</p>'
    '<ac:structured-macro ac:name=\\"info\\"><ac:parameter ac:name=\\"title\\">TYTUŁ-MAKRA</ac:parameter>'
    '<ac:rich-text-body><p>tekst w panelu</p></ac:rich-text-body></ac:structured-macro>'
    '<ac:structured-macro ac:name=\\"code\\"><ac:plain-text-body><![CDATA[kod = 1]]></ac:plain-text-body></ac:structured-macro>'
    '<p>Drugi akapit z <ac:link><ri:page ri:content-title=\\"Inna\\"/></ac:link> w środku.</p>",'
    '"representation":"storage"}}}'
)


def main():
    fails = []

    # 1. brak konfiguracji => błąd
    saved = {k: os.environ.pop(k, None) for k in
             (confluence.BASE_URL_ENV, confluence.EMAIL_ENV, confluence.TOKEN_ENV)}
    try:
        confluence.resolve_config()
        fails.append("resolve_config bez ENV powinno rzucić ConfluenceNotConfigured")
    except confluence.ConfluenceNotConfigured:
        pass
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v

    # 1b. nazwane instancje: --instance czyta slot CONFLUENCE_<NAZWA>_*, brak slotu => błąd z nazwą
    b, e, t = confluence._instance_env_names("tc")
    if (b, e, t) != ("CONFLUENCE_TC_BASE_URL", "CONFLUENCE_TC_EMAIL", "CONFLUENCE_TC_TOKEN"):
        fails.append(f"_instance_env_names('tc') rozjechane: {(b, e, t)}")
    os.environ["CONFLUENCE_TC_BASE_URL"] = "https://x.example/wiki"
    os.environ["CONFLUENCE_TC_EMAIL"] = "e@x"
    os.environ["CONFLUENCE_TC_TOKEN"] = "tok"
    try:
        base, _, _ = confluence.resolve_config(instance="tc")
        if base != "https://x.example/wiki":
            fails.append("resolve_config(instance='tc') nie wziął slotu instancji")
    finally:
        for k in ("CONFLUENCE_TC_BASE_URL", "CONFLUENCE_TC_EMAIL", "CONFLUENCE_TC_TOKEN"):
            os.environ.pop(k, None)
    try:
        confluence.resolve_config(instance="orlen")
        fails.append("resolve_config(instance='orlen') bez slotu powinno rzucić błąd")
    except confluence.ConfluenceNotConfigured as exc:
        if "CONFLUENCE_ORLEN_BASE_URL" not in str(exc):
            fails.append("błąd instancji nie wymienia nazwy slotu CONFLUENCE_ORLEN_*")
    # instancja z samych znaków specjalnych => pusty slug => błąd (nie cicha kolizja z domyślnym)
    try:
        confluence._instance_env_names("---")
        fails.append("_instance_env_names('---') powinno rzucić błąd (pusty slug), nie cofnąć się do domyślnego")
    except confluence.ConfluenceNotConfigured:
        pass

    # 2. fetch_page z atrapą transportu (zero sieci) => poprawny parse
    def fake_transport(url, *, headers, timeout):
        if "/rest/api/content/123" not in url:
            raise AssertionError(f"nieoczekiwany URL: {url}")
        if not headers.get("Authorization", "").startswith("Basic "):
            raise AssertionError("brak nagłówka Basic auth")
        return _SAMPLE_JSON

    page = confluence.fetch_page("123", base_url="https://x.example/wiki",
                                 email="e@x", token="tok", transport=fake_transport)
    if page.id != "123" or page.version != 7 or page.space_key != "TO":
        fails.append(f"parse strony: id/version/space rozjechane ({page.id}/{page.version}/{page.space_key})")
    if "Pierwszy akapit" not in page.storage:
        fails.append("parse strony: brak storage XHTML")

    # 3. adapter wyłuskuje prozę, pomija makra/parametry/kod/odwołania
    text = adp.ConfluenceStorageAdapter().normalize(page.storage).text
    if "Pierwszy akapit prozy." not in text or "Drugi akapit" not in text:
        fails.append("adapter: zgubił prozę z akapitów")
    for forbidden in ("TYTUŁ-MAKRA", "tekst w panelu", "kod = 1", "Inna"):
        if forbidden in text:
            fails.append(f"adapter: nie pominął wyspy nie-prozy: {forbidden!r}")

    # 4. write-back (KAN-234): podmiana akapitu prozy, makro nietknięte, re-encode encji
    doc = adp.ConfluenceStorageAdapter().normalize(page.storage)
    paras = doc.paragraphs()
    ed = adp.Edit(paras[0].start, paras[0].end, "Nowy < akapit > & ok.")
    new_storage = adp.ConfluenceStorageAdapter().write_back(doc, [ed])
    if "Nowy &lt; akapit &gt; &amp; ok." not in new_storage:
        fails.append("write_back: nowa proza nieobecna albo encje niezescapowane")
    for keep in ("TYTUŁ-MAKRA", "kod = 1", "Inna"):
        if keep not in new_storage:
            fails.append(f"write_back: zniszczył wyspę nie-prozy: {keep!r}")
    if not adp.verify_prose_only_change(page.storage, new_storage):
        fails.append("verify: zmiana prozy uznana za naruszenie wierności (fałszywy alarm)")
    if adp.verify_prose_only_change(page.storage, new_storage.replace("TYTUŁ-MAKRA", "ZEPSUTE")):
        fails.append("verify: zepsucie makra NIE wykryte (luka bezpieczeństwa)")

    # 5. update_page: skip bez zmian, 409 => ConfluenceConflict (atrapa transportu, zero sieci)
    pg = confluence.ConfluencePage(id="9", title="T", storage=page.storage, version=3)
    if confluence.update_page(pg, page.storage) is not pg:
        fails.append("update_page: brak zmian powinien pominąć PUT (zwrócić tę samą stronę)")

    def t409(url, *, method, headers, data, timeout):
        return 409, "{}"
    try:
        confluence.update_page(pg, new_storage, base_url="https://x/wiki", email="e", token="k",
                               transport=t409)
        fails.append("update_page: 409 nie podniósł ConfluenceConflict")
    except confluence.ConfluenceConflict:
        pass

    if fails:
        print("check_confluence: ROZJAZD", file=sys.stderr)
        for f in fails:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(1)
    print("OK   Confluence (KAN-233/234/235): nazwane instancje (--instance => slot CONFLUENCE_<NAZWA>_*, "
          "brak slotu => błąd z nazwą); resolve_config bez ENV => błąd, fetch_page parsuje storage "
          "przez atrapę transportu (zero sieci), adapter daje czystą prozę (makra/kod jako wyspy); "
          "write_back podmienia akapit (encje zescapowane, makra nietknięte), verify łapie zepsucie "
          "makra, update_page pomija PUT bez zmian i podnosi konflikt na 409.")
    sys.exit(0)


if __name__ == "__main__":
    main()
