import logging

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import Match
from core.scoring import apply_match_results, update_leaderboard

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
LIVE_STATUSES = {"IN_PLAY", "PAUSED", "HALFTIME"}


def _fetch_frozen_scores(api_id, headers):
    """
    Fetch goal events and return (home_80, away_80, home_90, away_90).
    _80 = goals with minute <= 80 (no 80+X stoppage time).
    _90 = goals with minute <= 90 (no 90+X stoppage time, no ET).
    45+X goals count for both (doliczony czas 1. połowy).
    Returns (None, None, None, None) on API error.
    """
    try:
        resp = requests.get(
            f"https://api.football-data.org/v4/matches/{api_id}",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Detail fetch failed for api_id=%s: %s", api_id, e)
        return None, None, None, None

    data = resp.json()
    home_team_id = (data.get("homeTeam") or {}).get("id")
    away_team_id = (data.get("awayTeam") or {}).get("id")
    if home_team_id is None:
        return None, None, None, None

    home_80 = away_80 = home_90 = away_90 = 0
    for goal in data.get("goals") or []:
        minute = goal.get("minute", 999)
        injury = goal.get("injuryTime")

        if minute > 90:
            continue  # ET goal — skip for both
        if minute == 90 and injury:
            continue  # 90+X — skip for both
        # goal counts toward score_90
        if minute > 80:
            pass  # counts for 90 only
        elif minute == 80 and injury:
            pass  # 80+X — counts for 90 only
        else:
            # counts for both 80 and 90
            team_id = (goal.get("team") or {}).get("id")
            if team_id == home_team_id:
                home_80 += 1
            elif team_id == away_team_id:
                away_80 += 1

        team_id = (goal.get("team") or {}).get("id")
        if team_id == home_team_id:
            home_90 += 1
        elif team_id == away_team_id:
            away_90 += 1

    return home_80, away_80, home_90, away_90


class Command(BaseCommand):
    help = "Fetch match results and live scores (cron target, every 5 min)"

    def handle(self, *args, **options):
        api_key = settings.FOOTBALL_DATA_API_KEY
        if not api_key:
            self.stderr.write("FOOTBALL_DATA_API_KEY not set in .env")
            return

        pending = list(
            Match.objects.filter(is_finished=False, api_id__isnull=False)
            .values_list("api_id", flat=True)
        )
        if not pending:
            self.stdout.write("No pending matches.")
            return

        self.stdout.write(f"Checking {len(pending)} unfinished match(es)…")

        headers = {"X-Auth-Token": api_key}
        finished_data = {}
        live_data = {}

        for i in range(0, len(pending), BATCH_SIZE):
            batch = pending[i : i + BATCH_SIZE]
            ids = ",".join(str(x) for x in batch)
            try:
                resp = requests.get(
                    "https://api.football-data.org/v4/matches",
                    params={"ids": ids},
                    headers=headers,
                    timeout=10,
                )
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.error("API request failed: %s", e)
                self.stderr.write(f"API error: {e}")
                return

            for m in resp.json().get("matches", []):
                status = m.get("status")
                score  = m.get("score") or {}

                if status == "FINISHED":
                    ft = score.get("fullTime") or {}
                    if ft.get("home") is not None:
                        finished_data[m["id"]] = (ft["home"], ft["away"])

                elif status in LIVE_STATUSES:
                    # current score during the match
                    cur = score.get("fullTime") or score.get("halfTime") or {}
                    if cur.get("home") is not None:
                        live_data[m["id"]] = (cur["home"], cur["away"])

        # ── Apply finished results ────────────────────────────────────────────
        updated = 0
        for api_id, (hs, as_) in finished_data.items():
            try:
                match = Match.objects.get(api_id=api_id, is_finished=False)
            except Match.DoesNotExist:
                continue

            h80, a80, h90, a90 = _fetch_frozen_scores(api_id, headers)

            match.home_score = hs
            match.away_score = as_
            match.home_score_80 = h80
            match.away_score_80 = a80
            match.home_score_90 = h90
            match.away_score_90 = a90
            match.is_finished = True
            match.save(update_fields=[
                "home_score", "away_score",
                "home_score_80", "away_score_80",
                "home_score_90", "away_score_90",
                "is_finished",
            ])
            apply_match_results(match)
            updated += 1
            suffix = f"  (80': {h80}:{a80}  90': {h90}:{a90})" if h90 is not None else ""
            self.stdout.write(f"  ✓ FINISHED {match}  {hs}:{as_}{suffix}")

        if updated:
            update_leaderboard()

        # ── Update live scores (no is_finished change) ────────────────────────
        live_updated = 0
        for api_id, (hs, as_) in live_data.items():
            n = Match.objects.filter(api_id=api_id, is_finished=False).update(
                home_score=hs, away_score=as_
            )
            if n:
                live_updated += 1
                self.stdout.write(f"  ~ LIVE     api_id={api_id}  {hs}:{as_}")

        self.stdout.write(self.style.SUCCESS(
            f"Done: {updated} finished, {live_updated} live score(s) updated."
        ))
