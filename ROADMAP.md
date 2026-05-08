# Mundial Typer 2026 — Roadmap techniczna

Plik roboczy dla Claude Code. Opisuje decyzje projektowe, poprawki względem blueprintu v1.0
i kolejność pracy. **Nie edytować blueprintu** — ten plik jest źródłem prawdy podczas implementacji.

---

## Poprawki względem blueprintu v1.0

### 1. `bet_deadline` — property, nie pole

**Blueprint**: `bet_deadline = DateTimeField()` ustawiane ręcznie jako `match_date - 1h`  
**Zmiana**: usunąć pole, zastąpić `@property`

```python
@property
def bet_deadline(self):
    from datetime import timedelta
    return self.match_date - timedelta(hours=1)
```

Eliminuje ryzyko desynchronizacji gdy admin zmienia `match_date`.

---

### 2. Brakująca funkcja — `apply_match_results(match)`

**Blueprint**: definiuje `calculate_match_points()` i `update_leaderboard()` ale nie ma
funkcji łączącej — `Bet.points` nigdy nie zostanie zapisany.

**Zmiana**: dodać do `scoring.py`:

```python
def apply_match_results(match):
    """Wywołać po ustawieniu wyniku meczu. Zapisuje punkty i aktualizuje leaderboard."""
    if not match.is_finished:
        return
    for bet in match.bets.select_related('user'):
        bet.points = calculate_match_points(bet, match)
        bet.save(update_fields=['points'])
    update_leaderboard()
```

---

### 3. Tiebreaker w `update_leaderboard()`

**Blueprint**: edge case sekcja 5 deklaruje tiebreaker: exact_hits → direction_hits → username
alfabetycznie. `Leaderboard.Meta.ordering` nie zawiera `user__username`.

**Zmiana**:
- `Meta.ordering = ['-total_points', '-exact_hits', '-direction_hits', 'user__username']`
- Druga pętla w `update_leaderboard()`: `Leaderboard.objects.order_by('-total_points', '-exact_hits', '-direction_hits', 'user__username')`

---

### 4. `update_leaderboard()` — `bulk_update` zamiast pętli save

**Blueprint**: druga pętla robi `lb.save(update_fields=['position'])` 50× osobno.

**Zmiana**:
```python
leaderboards = list(Leaderboard.objects.order_by(...))
for i, lb in enumerate(leaderboards, 1):
    lb.position = i
Leaderboard.objects.bulk_update(leaderboards, ['position'])
```

---

### 5. `Bet.updated_at` — dodać pole

**Blueprint**: `Bet` ma tylko `created_at`. Gracz może edytować typ aż do deadline.

**Zmiana**: dodać `updated_at = models.DateTimeField(auto_now=True)` do modelu `Bet`.

---

### 6. `SpecialQuestion.deadline` — jedna wartość dla wszystkich pytań

**Blueprint**: `deadline` jako pole na każdym `SpecialQuestion` — wymaga ustawienia tej samej
daty 8 razy ręcznie.

**Decyzja**: Wszystkie zakłady dodatkowe mają jeden deadline: 24h przed pierwszym meczem
turnieju. Zostawić pole na modelu (elastyczność), ale w adminie ustawić domyślną wartość
i dodać walidację że wszystkie pytania mają ten sam deadline.

Alternatywnie: stała `SPECIAL_BETS_DEADLINE` w settings i walidacja w formularzu.
Do podjęcia przy implementacji Fazy 3.

---

### 7. Flagi drużyn — lokalnie w `static/`

**Blueprint**: `flag_url = URLField()` wskazujący na zewnętrzny CDN.

**Zmiana**: przy imporcie drużyn z API (`import_teams` management command) pobierać flagi
i zapisywać jako `static/flags/<code>.png` (np. `POL.png`). W szablonach używać
`{% static 'flags/POL.png' %}`.

---

### 8. Reset hasła — Django built-ins

**Blueprint**: brak widoku resetu hasła.

**Zmiana**: w `urls.py` projektu dodać:
```python
from django.contrib.auth import views as auth_views
path('password-reset/', include([
    path('', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('complete/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
])),
```
Wymaga konfiguracji EMAIL_BACKEND w settings (na dev: `console`, na prod: SMTP).

---

## Architektura automatyzacji wyników

Pełna automatyzacja bez akcji admina dla rutynowych wyników.

```
crontab (co 5 minut podczas turnieju)
    └── python manage.py fetch_results
            ├── GET /v4/competitions/WC/matches?status=FINISHED
            ├── dla każdego meczu który właśnie przeszedł na FINISHED:
            │       match.home_score = ...
            │       match.away_score = ...
            │       match.is_finished = True
            │       match.save()
            │       apply_match_results(match)   ← scoring.py
            └── (loguje ile meczów zaktualizowano)
```

**Źródło danych**: football-data.org free tier (10 req/min).  
Daje `status=FINISHED` ~2-5 minut po końcowym gwizdku. Wystarczy.

**Live score (w trakcie meczu)**: NIE implementujemy. Free tier nie daje real-time,
scraping niepotrzebny. Leaderboard aktualizuje się po meczu.

**Ręczna korekta**: admin może zmienić wynik w panelu Django Admin jeśli API zwróci błąd.
Po korekcie: custom action "Przelicz punkty dla tego meczu" odpala `apply_match_results(match)`.

**Rola admina** (tylko te kroki są ręczne):
1. Przed turniejem: `import_teams`, `import_fixtures` (jednorazowo)
2. Zakłady dodatkowe: rozstrzyganie po zakończeniu turnieju/wydarzenia
3. Invite codes: generowanie (jednorazowo)
4. Korekta błędnych wyników API (sporadycznie)

---

## Moduł DS — Monte Carlo (Faza 7, po starcie turnieju)

Osobna aplikacja Django (`analytics/`). Nie blokuje MVP.

**Kafelek "Szansa na wygraną"** — prawdopodobieństwo zajęcia 1. miejsca przez gracza:
- Wejście: aktualne punkty + nierozstrzygnięte mecze + nierozstrzygnięte zakłady dodatkowe
- Symulacja: 10 000 iteracji, każda losuje wyniki pozostałych meczów z rozkładu historycznego
- Źródło danych historycznych: do ustalenia przy implementacji (football-data.org za poprzednie mundiale lub ręcznie przygotowany plik)
- Wynik: `P(wygrana)` per gracz, wyświetlany jako kafelek na dashboardzie

**Zależności od core modeli** (muszą być odpytywalne efektywnie):
- `Bet.points` — nullable, null = nierozstrzygnięty
- `SpecialBet.points` — nullable, null = nierozstrzygnięty
- `Match.is_finished` + `Match.stage`

Żadnych zmian w modelu core przy dodawaniu tego modułu.

---

## Fazy implementacji (zaktualizowane)

> Start turnieju: **11 czerwca 2026**. Dziś: 29 kwietnia 2026. Zostało ~6 tygodni.

| Faza | Zakres | Priorytet | Termin |
|---|---|---|---|
| **1** | Django scaffold, modele (z poprawkami), migracje, admin, auth + invite codes, reset hasła | MUST | ASAP |
| **2** | Widoki: lista meczów, formularz obstawiania, leaderboard; htmx + Tailwind | MUST | do ~15 maja |
| **3** | Zakłady dodatkowe (SpecialQuestion/SpecialBet), formularze, dropdown zawodników | MUST | do ~25 maja |
| **4** | `fetch_results` + cron, `import_teams`, `import_fixtures`, flagi lokalnie | MUST | do ~31 maja |
| **5** | Deploy: Hetzner VPS, PostgreSQL, Gunicorn, Caddy, SSL, testy beta | MUST | do ~8 czerwca |
| **6** | Soft launch: invite codes, onboarding 50 graczy | MUST | 1–10 czerwca |
| **7** | Analytics: wykresy, Monte Carlo, kafelek P(wygrana), LLM ciekawostki | NICE | w trakcie turnieju |

---

## Rzeczy do zapamiętania przy implementacji

- `Bet.points = null` oznacza nierozstrzygnięty (mecz się nie skończył) — nie mylić z `0` (pudło)
- Punktujemy **regulaminowy czas gry** — wynik po 90 min, bez dogrywki/karnych
- `@login_required` na wszystkich widokach poza `/register/` i `/login/`
- Tailwind przez CDN — bez konfiguracji builda
- Jeden app Django (`core`) + przyszłe: `analytics/`, `llm_insights/`
- EMAIL_BACKEND = `django.core.mail.backends.console.EmailBackend` na dev
