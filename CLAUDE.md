# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

Planning/blueprint phase — no code scaffolded yet. The README.md contains the full phase checklist (Phases 1–7). Start at Phase 1 before writing any logic.

## Stack

- **Backend**: Django (single `core` app) + PostgreSQL
- **Frontend**: htmx + Tailwind CSS (CDN)
- **Deploy target**: Hetzner VPS, Gunicorn + Caddy, systemd

## Setup (once scaffolded)

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill SECRET_KEY and DATABASE_URL
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Planned Architecture

### Django project layout

```
mundial_typer/        # project package (settings, urls, wsgi)
core/                 # single app — all models, views, forms, templates
  models.py           # Team, Player, Match, Bet, SpecialQuestion, SpecialBet, Leaderboard, InviteCode
  scoring.py          # calculate_match_points(), calculate_special_points(), update_leaderboard()
  admin.py            # all models registered; custom actions: generate invite codes, recalculate points
  views.py            # @login_required throughout; match list, bet form, leaderboard, special bets
  forms.py            # registration (validates InviteCode), bet form (validates deadline)
  urls.py
  templates/core/     # base.html + per-view templates
  management/commands/
    import_teams.py       # Phase 4: football-data.org
    import_fixtures.py    # Phase 4
    fetch_results.py      # Phase 4: cron target
```

### Key model relationships

- `Bet` has `unique_together = (user, match)` — one bet per user per match.
- `SpecialBet` references either a `Player` or `Team` FK plus a numeric field (e.g. top scorer goals).
- `InviteCode` is consumed on registration; invite-only access.
- `Leaderboard` is recalculated (not incremental) via `update_leaderboard()` after each result.

### Scoring rules

| Outcome | Points |
|---|---|
| Exact score | 3 |
| Correct result direction (W/D/L) | 1 |
| Wrong | 0 |

Special questions have their own point values defined per `SpecialQuestion`. Max total: 328 pts across 104 matches.

### htmx integration points

- Bet form submission — no full-page reload.
- Leaderboard — auto-refresh after results are updated.

## Running tests

```bash
python manage.py test core          # all core tests
python manage.py test core.tests.test_scoring   # scoring unit tests only
```

Scoring logic (`scoring.py`) must have unit tests covering: exact score, correct direction, miss, 0–0 draw, extra-time match.

## Environment variables

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DATABASE_URL` | PostgreSQL connection string |
| `FOOTBALL_DATA_API_KEY` | football-data.org API key (Phase 4) |
| `DEBUG` | Set to `False` in production |
