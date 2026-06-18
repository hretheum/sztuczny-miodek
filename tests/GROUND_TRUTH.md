# Ground Truth — zasiane AI-tells (oczekiwane wykrycia)

Lista wzorców celowo wstrzykniętych w korpus. Linter i skill MUSZĄ je wykryć (recall=100%).
Plik kontrolny `control_pl_clean.md` MUSI dać 0 blokerów (false-positive=0).

## baseline_pl_raport.md
| # | Wzorzec | Kategoria | Fragment |
|---|---|---|---|
| 1 | emoji w nagłówku | PL-TYPO | `# 🚀 Wdrożenie` |
| 2 | „W dzisiejszych czasach" | PL-SIGN | otwarcie akapitu |
| 3 | „odgrywa kluczową rolę" | PL-CLICHE | |
| 4 | „Warto podkreślić, że" | PL-SIGN | |
| 5 | „rewolucyjne" (puste) | PL-CLICHE | |
| 6 | „możliwości (...) nieograniczone" | PL-CLICHE | |
| 7 | „Należy zauważyć, że" | PL-SIGN | |
| 8 | triada „szybko, sprawnie i skutecznie" | PL-RHET | |
| 9 | „Co istotne," | PL-SIGN | |
| 10 | paralelizm „nie tylko (...) ale również" | PL-RHET | |
| 11 | antyteza redefinicyjna „To nie zwykłe narzędzie — to fundament" | PL-RHET | |
| 12 | antyteza redefinicyjna „Pomiar to nie ocena — to odczyt" | PL-RHET | |
| 13 | „Z jednej strony (...) z drugiej strony" | PL-RHET | |
| 14 | hedging „mogłoby potencjalnie" | PL-HEDGE | |
| 15 | nadużycie myślnika (≥4 wtrącenia w pliku) | PL-TYPO | |
| 16 | nagłówek-klisza „Kluczowe wnioski" | PL-TYPO | |
| 17 | „Podsumowując," | PL-SIGN | |
| 18 | „stanowi integralną część" | PL-CLICHE | |

## baseline_pl_intro.md
| # | Wzorzec | Kategoria |
|---|---|---|
| 19 | „Zanurzmy się" | PL-SIGN |
| 20 | „Jak powszechnie wiadomo" | PL-SIGN |
| 21 | „Nie sposób przecenić" | PL-SIGN |
| 22 | „Przyjrzyjmy się bliżej" | PL-SIGN |
| 23 | powtarzalny szyk SVO „Mózg przetwarza/generuje/wytwarza" | PL-RHYTHM |
| 24 | „warto byłoby rozważyć możliwość" | PL-HEDGE |
| 25 | nawał spójników „Ponadto / Co więcej / Dodatkowo" | PL-RHYTHM |
| 26 | „W obliczu" | PL-SIGN |
| 27 | nadużycie myślnika | PL-TYPO |

## baseline_en_cover_letter.md
| # | Wzorzec | Kategoria |
|---|---|---|
| 28 | em-dash overuse (≥5) | EN-DASH |
| 29 | „In today's fast-paced world" | EN-CLICHE |
| 30 | antyteza „not just (...) it's about" | EN-ANTI |
| 31 | „navigate the complexities" | EN-CLICHE |
| 32 | „I am excited to" | EN-CLICHE |
| 33 | „passionate about" | EN-CLICHE |
| 34 | „delve into" | EN-CLICHE |
| 35 | triada „fast, reliable, and scalable" | EN-TRIAD |
| 36 | „a testament to" | EN-CLICHE |
| 37 | paralelizm „self-documenting and self-checking" | EN-PARA |
| 38 | antyteza „I don't just write code — I craft solutions" | EN-ANTI |
| 39 | „I am confident that" | EN-CLICHE |
| 40 | superlatyw „incredibly" | EN-SUPER |
| 41 | „first-class" | EN-CLICHE |
| 42 | superlatyw „remarkably" / „truly" | EN-SUPER |
| 43 | antyteza „not merely (...) it is" | EN-ANTI |
| 44 | „In conclusion" | EN-CONCL |
| 45 | „Ultimately" | EN-CONCL |

## baseline_en_doc.md
| # | Wzorzec | Kategoria |
|---|---|---|
| 46 | „leverage" | EN-CLICHE |
| 47 | „robust" | EN-CLICHE |
| 48 | „seamless" | EN-CLICHE |
| 49 | „It is worth noting" | EN-CLICHE |
| 50 | „first-class" | EN-CLICHE |
| 51 | „ever-evolving landscape" | EN-CLICHE |
| 52 | antyteza „not slow, but fast; not fragile, but resilient" | EN-ANTI |
| 53 | hedging „It could be argued / to some extent" | EN-HEDGE |
| 54 | „tapestry" | EN-CLICHE |
| 55 | triada „design, build, and ship" | EN-TRIAD |
| 56 | superlatyw „incredibly / truly" | EN-SUPER |
| 57 | „Overall" | EN-CONCL |
| 58 | „All in all" | EN-CONCL |
| 59 | „a testament to" | EN-CLICHE |

**Łącznie: 59 zasianych tellów.** Kontrola: `control_pl_clean.md` → 0.
