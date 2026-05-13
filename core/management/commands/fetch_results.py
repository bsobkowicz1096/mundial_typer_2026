import logging

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import Match
from core.scoring import apply_match_results, update_leaderboard

logger = logging.getLogger(__name__)

BATCH_SIZE = 50  # max IDs per request (API limit)


class Command(BaseCommand):
    help = "Fetch finished match results and apply scoring (cron target, every 5 min)"

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
                if m.get("status") == "FINISHED":
                    ft = (m.get("score") or {}).get("fullTime") or {}
                    if ft.get("home") is not None and ft.get("away") is not None:
                        finished_data[m["id"]] = (ft["home"], ft["away"])

        if not finished_data:
            self.stdout.write("No newly finished matches.")
            return

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
            self.stdout.write(f"  ✓ {match}  {hs}:{as_}")

        if updated:
            update_leaderboard()

        self.stdout.write(self.style.SUCCESS(f"Done: {updated} match(es) updated."))
