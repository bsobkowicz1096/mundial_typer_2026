# ⚽ Mundial 2026 Typer

Aplikacja webowa do obstawiania meczów Mistrzostw Świata 2026.

**Stack:** Django + htmx + PostgreSQL  
**Gracze:** ~50 | **Mecze:** 104 | **Max punktów:** 328

---

## Quickstart

```bash
# 1. Sklonuj repo
git clone <repo-url>
cd mundial-typer

# 2. Stwórz i aktywuj venv
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Zainstaluj zależności
pip install -r requirements.txt

# 4. Skopiuj .env
cp .env.example .env
# Uzupełnij dane w .env (SECRET_KEY, DATABASE_URL)

# 5. Migracje i superuser
python manage.py migrate
python manage.py createsuperuser

# 6. Odpal serwer dev
python manage.py runserver
```

---

## Checklist — Faza 1: Fundament (marzec 2026)

### Setup projektu
- [ ] Utworzyć repo na GitHub
- [ ] `django-admin startproject mundial_typer .`
- [ ] `python manage.py startapp core`
- [ ] Skonfigurować settings.py (baza danych, apps, static, timezone)
- [ ] Utworzyć plik .env.example z wymaganymi zmiennymi
- [ ] Zweryfikować że `runserver` działa

### Modele danych
- [ ] Zaimplementować model Team
- [ ] Zaimplementować model Player
- [ ] Zaimplementować model Match
- [ ] Zaimplementować model Bet (z unique_together)
- [ ] Zaimplementować model SpecialQuestion
- [ ] Zaimplementować model SpecialBet (z FK na Player/Team + number)
- [ ] Zaimplementować model Leaderboard
- [ ] Zaimplementować model InviteCode
- [ ] Uruchomić `makemigrations` + `migrate`
- [ ] Przetestować modele w Django shell

### Panel admina
- [ ] Zarejestrować wszystkie modele w admin.py
- [ ] Dodać filtry i search fields (Match: stage, date; Bet: user, match)
- [ ] Custom action: generowanie invite codes
- [ ] Custom action: przeliczanie punktów po meczu
- [ ] Przetestować dodawanie drużyn/meczów przez admin

### System autentykacji
- [ ] Widok rejestracji z walidacją invite code
- [ ] Widok logowania (Django auth)
- [ ] Widok wylogowania
- [ ] Ochrona widoków (@login_required)
- [ ] Szablon base.html z nawigacją (zalogowany/niezalogowany)

### Logika punktacji
- [ ] Implementacja calculate_match_points() w scoring.py
- [ ] Implementacja calculate_special_points() w scoring.py
- [ ] Implementacja update_leaderboard() w scoring.py
- [ ] Testy jednostkowe punktacji (dokładny wynik, kierunek, pudło)
- [ ] Test edge case: mecz 0:0, mecz pucharowy po dogrywce

---

## Checklist — Faza 2: Core (kwiecień 1-15)

- [ ] Widok listy meczów (pogrupowane per dzień)
- [ ] Formularz obstawiania meczu (z walidacją deadline)
- [ ] Widok tabeli rankingowej (Leaderboard)
- [ ] Integracja htmx (dynamiczne obstawianie, auto-refresh tabeli)
- [ ] Styling z Tailwind CSS (CDN)
- [ ] Responsywność (mobile-first)

## Checklist — Faza 3: Zakłady dodatkowe (kwiecień 16-30)

- [ ] Widok zakładów dodatkowych
- [ ] Dynamiczny formularz (dropdown Player/Team, input Number)
- [ ] Walidacja deadline (24h przed turniejem)
- [ ] Rozstrzyganie zakładów przez admina

## Checklist — Faza 4: Integracja API (maj 1-15)

- [ ] Management command: import drużyn z football-data.org
- [ ] Management command: import terminarza meczów
- [ ] Management command: aktualizacja wyników (fetch_results)
- [ ] Cron job do automatycznej aktualizacji

## Checklist — Faza 5: Deploy (maj 16-31)

- [ ] Zakup domeny
- [ ] Postawienie VPS Hetzner CX23 (Nuremberg)
- [ ] Instalacja: Python, PostgreSQL, Caddy/Nginx
- [ ] Deploy aplikacji (git clone, venv, migrate, collectstatic)
- [ ] Konfiguracja Gunicorn + systemd
- [ ] SSL przez Let's Encrypt / Caddy
- [ ] Testy z grupą beta (~5 osób)

## Checklist — Faza 6: Launch (czerwiec 1-10)

- [ ] Generowanie 50+ invite codes
- [ ] Wysłanie zaproszeń do graczy
- [ ] Onboarding — gracze rejestrują się i obstawiają zakłady dodatkowe
- [ ] Monitoring (czy wszystko działa pod obciążeniem)

## Checklist — Faza 7: Live + DS (czerwiec-lipiec)

- [ ] Moduł analytics (wykresy, statystyki per gracz)
- [ ] Monte Carlo — prawdopodobieństwo wygrania ligi
- [ ] Moduł LLM — ciekawostki dnia
- [ ] Snapshoty JSON po golach (nice to have)
