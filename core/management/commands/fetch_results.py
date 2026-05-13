import logging

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import Match
from core.scoring import apply_match_results, update_leaderboard

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
LIVE_STATUSES = {"IN_PLAY", "PAUSED", "HALFTIME"}


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
            match.home_score = hs
            match.away_score = as_
            match.is_finished = True
            match.save(update_fields=["home_score", "away_score", "is_finished"])
            apply_match_results(match)
            updated += 1
            self.stdout.write(f"  ✓ FINISHED {match}  {hs}:{as_}")

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
