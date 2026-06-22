#!/usr/bin/env python3
"""
build_dict.py — budowa szkicu słownika domenowego z korpusu (Epik D, D3 / KAN-197).

Zasada: CZĘSTOŚĆ PROPONUJE, KANON WETUJE, CZŁOWIEK ZATWIERDZA.
- częstość proponuje: kandydaci = terminy częste w korpusie i o szerokim rozrzucie (wiele plików),
- filtr słów ogólnych: opcjonalna lista (wordlist) pospolitych słów do odsiania,
- veto kanonu: termin, który łapie którykolwiek MARKER lintera (rules.json) — czyli ma być
  flagowany jako AI-tell/kalka — NIE może trafić do `allow`; ląduje w `review` (do decyzji człowieka),
- człowiek zatwierdza: emisja SZKICU w formacie D2 (dictionary.schema.md) z PUSTYM `allow`
  (kandydaci w `review`) — operator ręcznie przenosi zaakceptowane do `allow`.

ZERO-DEP (stdlib: re, json, collections, argparse). Nie modyfikuje lintera ani słownika
produkcyjnego — produkuje plik szkicu na stdout lub do --out.

Użycie:
    python3 tools/build_dict.py KORPUS... [--min-count N] [--min-files M]
                                [--wordlist plik] [--out szkic.json] [--projekt nazwa]
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
import ai_linter  # noqa: E402 — compile_markers do veta kanonu

# Token: ciąg liter (z polskimi), min 3 znaki. Liczby/interpunkcja pomijane.
_TOKEN_RE = re.compile(r"[a-ząćęłńóśźżA-ZĄĆĘŁŃÓŚŹŻ]{3,}")


def _iter_corpus_files(paths):
    """Zbiera pliki .md/.txt/.html z podanych ścieżek (pliki wprost lub katalogi rekursywnie)."""
    exts = (".md", ".txt", ".html", ".htm", ".xhtml")
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for fn in files:
                    if fn.endswith(exts):
                        yield os.path.join(root, fn)
        elif os.path.isfile(p):
            yield p


def load_wordlist(path):
    """Wczytuje listę słów ogólnych (jedno słowo / linia, lowercase). Brak → pusty zbiór."""
    if not path or not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return {ln.strip().lower() for ln in f if ln.strip() and not ln.startswith("#")}


def extract_candidates(paths, min_count, min_files, bigrams=True):
    """Zwraca {termin: (liczba_wystąpień, liczba_plików)} dla terminów spełniających progi.

    Kandydaci = pojedyncze tokeny ORAZ krótkie n-gramy (bigramy sąsiednich tokenów, jeśli
    `bigrams`), bo terminy domenowe bywają wielowyrazowe („design system"). Częstość = suma
    wystąpień; rozrzut = liczba różnych plików (chroni przed terminem z jednego pliku)."""
    total = Counter()
    files_with = Counter()
    n_files = 0
    for fp in _iter_corpus_files(paths):
        n_files += 1
        try:
            text = open(fp, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        toks = [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]
        seen = set()
        for t in toks:
            total[t] += 1
            seen.add(t)
        if bigrams:
            for a, b in zip(toks, toks[1:]):
                bg = f"{a} {b}"
                total[bg] += 1
                seen.add(bg)
        for t in seen:
            files_with[t] += 1
    candidates = {
        t: (total[t], files_with[t])
        for t in total
        if total[t] >= min_count and files_with[t] >= min_files
    }
    return candidates, n_files


def canon_vetoes(term):
    """Czy KANON wetuje termin? True, jeśli term łapie którykolwiek marker lintera (rules.json),
    czyli jest AI-tellem/kliszą — nie wolno go dopuścić (allow). Sprawdzane na samym terminie."""
    for _mid, _lang, _klasa, cre, _desc in ai_linter.compile_markers("both"):
        if cre.search(term):
            return True
    return False


def build(paths, min_count, min_files, wordlist_path, projekt):
    general = load_wordlist(wordlist_path)
    candidates, n_files = extract_candidates(paths, min_count, min_files)

    review = []      # kandydaci do decyzji człowieka (częstość zaproponowała, kanon nie zawetował twardo)
    vetoed = []      # zawetowane przez kanon (AI-tell/kalka — informacyjnie w komentarzu)
    for term, (cnt, nf) in sorted(candidates.items(), key=lambda kv: (-kv[1][0], kv[0])):
        if term in general:
            continue  # słowo ogólne — odsiane
        if canon_vetoes(term):
            vetoed.append({"termin": term, "count": cnt, "pliki": nf, "powod": "veto kanonu (AI-tell)"})
            continue
        review.append(term)

    return {
        "provenance": {
            "projekt": projekt,
            "zrodlo": "build_dict.py z korpusu",
            "korpus_plikow": n_files,
            "progi": {"min_count": min_count, "min_files": min_files},
            "uwaga": "SZKIC do akceptacji człowieka. allow PUSTE — przenieś zaakceptowane terminy "
                     "z review do allow. Zasada: częstość proponuje, kanon wetuje, człowiek zatwierdza.",
        },
        "allow": [],                 # PUSTE — wypełnia człowiek po przeglądzie review
        "review": review,            # kandydaci zaproponowani przez częstość, nie zawetowani
        "_vetoed_by_canon": vetoed,  # informacyjnie: odrzucone przez kanon (nie część formatu D2)
    }


def main():
    ap = argparse.ArgumentParser(description="Buduje szkic słownika domenowego z korpusu (D3).")
    ap.add_argument("paths", nargs="+", metavar="KORPUS", help="Pliki/katalogi korpusu (.md/.txt/.html).")
    ap.add_argument("--min-count", type=int, default=3, help="Min. liczba wystąpień terminu (domyślnie 3).")
    ap.add_argument("--min-files", type=int, default=2, help="Min. liczba plików z terminem (domyślnie 2).")
    ap.add_argument("--wordlist", default=None, help="Opcjonalna lista słów ogólnych do odsiania.")
    ap.add_argument("--out", default=None, help="Plik wyjściowy szkicu (domyślnie: stdout).")
    ap.add_argument("--projekt", default="nienazwany", help="Nazwa projektu do provenance.")
    args = ap.parse_args()

    draft = build(args.paths, args.min_count, args.min_files, args.wordlist, args.projekt)
    out = json.dumps(draft, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"Zapisano szkic: {args.out} (review={len(draft['review'])}, "
              f"veto={len(draft['_vetoed_by_canon'])})", file=sys.stderr)
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
