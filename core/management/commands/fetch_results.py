import logging

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import Match
from core.scoring import apply_match_results

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fetch finished match results and apply scoring (cron target, every 5 min)"

    def handle(self, *args, **options):
        api_key = settings.FOOTBALL_DATA_API_KEY
        if not api_key:
            self.stderr.write("FOOTBALL_DATA_API_KEY not set in .env")
            return

        headers = {"X-Auth-Token": api_key}
        try:
            resp = requests.get(
                "https://api.football-data.org/v4/competitions/WC/matches",
                params={"status": "FINISHED"},
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error("API request failed: %s", e)
            self.stderr.write(f"API request failed: {e}")
            return

        updated = 0
        for m in resp.json().get("matches", []):
            api_id = m.get("id")
            full_time = (m.get("score") or {}).get("fullTime") or {}
            home_score = full_time.get("home")
            away_score = full_time.get("away")

            if home_score is None or away_score is None:
                continue

            try:
                match = Match.objects.get(api_id=api_id, is_finished=False)
            except Match.DoesNotExist:
                continue  # already processed or not in DB

            match.home_score = home_score
            match.away_score = away_score
            match.is_finished = True
            match.save(update_fields=["home_score", "away_score", "is_finished"])
            apply_match_results(match)
            updated += 1
            self.stdout.write(f"  {match}")

        self.stdout.write(self.style.SUCCESS(f"Done: {updated} match(es) updated."))
