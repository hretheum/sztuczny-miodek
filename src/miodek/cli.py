# -*- coding: utf-8 -*-
"""
miodek — unified CLI (KAN-228). Jeden punkt wejścia z podkomendami; każda deleguje do modułu
pakietu, zachowując jego kod wyjścia. Zastępuje prowizoryczny entry point z KAN-227.

  lint     Stage 1: deterministyczny audyt (manifest + werdykt). 0 tokenów LLM.   -> ai_linter.main
  correct  Stage 2: korektor (pętla audyt->poprawka->PASS; silnik z configu / --runpod). -> corrector._main
  gate     Bramka przed publikacją (Stage 1 zawsze, opcjonalnie Stage 2 --stage2).  -> publish_gate.main
  lt       Pełna korekta przez LanguageTool (na żądanie, wymaga endpointu).         -> languagetool_check.main

Delegacja: podkomendy mają własne parsery argparse — podmieniamy sys.argv tak, by widziały
wyłącznie swoje argumenty. Kody wyjścia ujednolicamy (część modułów woła sys.exit, część zwraca
kod) — przechwytujemy SystemExit i zwracamy spójny int.

ZERO-DEP (stdlib).
"""

import sys

_USAGE = """miodek — audyt polszczyzny i eradykacja manieryzmu AI (PL/EN)

Użycie: miodek <komenda> [argumenty]

Komendy:
  lint      Stage 1: deterministyczny audyt (manifest + werdykt). Zero tokenów LLM.
  correct   Stage 2: korektor — pętla audyt, poprawka, ponowny audyt do PASS
            (silnik z config.json; --runpod = efemeryczny Bielik na RunPodzie).
  gate      Bramka przed publikacją: Stage 1 zawsze, opcjonalnie Stage 2 (--stage2).
  lt        Pełna korekta przez LanguageTool (na żądanie; wymaga endpointu).

Pomoc podkomendy:  miodek <komenda> --help
"""

_COMMANDS = ("lint", "correct", "gate", "lt")


def _delegate(loader, rest):
    """Wywołaj `loader()` -> funkcja modułu, z sys.argv = [prog] + rest. Zwróć spójny kod wyjścia."""
    fn = loader()
    try:
        rc = fn(rest) if _takes_argv(fn) else fn()
    except SystemExit as e:
        code = e.code
        if code is None:
            return 0
        return code if isinstance(code, int) else 1
    return rc if isinstance(rc, int) else 0


def _takes_argv(fn):
    """Czy funkcja przyjmuje argv (corrector._main/publish_gate.main/languagetool_check.main)?"""
    import inspect
    try:
        return len(inspect.signature(fn).parameters) >= 1
    except (TypeError, ValueError):
        return False


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_USAGE)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd not in _COMMANDS:
        sys.stderr.write(f"miodek: nieznana komenda '{cmd}'\n\n")
        sys.stderr.write(_USAGE)
        return 2

    # Podkomendy parsują sys.argv[1:]; ustawiamy prog czytelnie i podajemy tylko ich argumenty.
    sys.argv = [f"miodek {cmd}"] + rest

    if cmd == "lint":
        def load():
            from miodek import ai_linter
            return ai_linter.main
    elif cmd == "correct":
        def load():
            from miodek import corrector
            return corrector._main
    elif cmd == "gate":
        def load():
            from miodek import publish_gate
            return publish_gate.main
    elif cmd == "lt":
        def load():
            from miodek import languagetool_check
            return languagetool_check.main

    return _delegate(load, rest)


if __name__ == "__main__":
    sys.exit(main())
