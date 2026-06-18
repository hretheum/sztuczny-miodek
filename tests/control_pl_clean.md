# Notatka z testu obciążeniowego

Puściliśmy 10 tysięcy równoległych zapytań. Serwer wytrzymał. Czas odpowiedzi wzrósł z 40 do 120 ms przy szczycie, potem wrócił do normy w ciągu dwóch minut.

Jedna rzecz nas zaskoczyła. Kolejka zadań rosła szybciej, niż przewidywał model. Powód okazał się prozaiczny: limit połączeń do bazy był ustawiony za nisko. Podnieśliśmy go do 200 i problem zniknął.

Następnym razem trzeba przetestować z zimnym cache. Dziś baza była rozgrzana, więc wyniki są optymistyczne. Realny ruch da gorsze liczby.

Kod poprawki leży na gałęzi `fix/db-pool`. Wymaga jeszcze przeglądu, bo zmienia konfigurację produkcyjną.
