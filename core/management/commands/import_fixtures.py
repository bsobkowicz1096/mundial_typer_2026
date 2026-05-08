import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime

from core.models import Match, Team

STAGE_MAP = {
    "GROUP_STAGE": "GROUP",
    "ROUND_OF_32": "R32",
    "ROUND_OF_16": "R16",
    "QUARTER_FINALS": "QF",
    "SEMI_FINALS": "SF",
    "THIRD_PLACE": "3RD",
    "FINAL": "FINAL",
}


class Command(BaseCommand):
    help = "Import fixtures from football-data.org WC 2026"

    def handle(self, *args, **options):
        api_key = settings.FOOTBALL_DATA_API_KEY
        if not api_key:
            self.stderr.write("FOOTBALL_DATA_API_KEY not set in .env")
            return

        headers = {"X-Auth-Token": api_key}
        resp = requests.get(
            "https://api.football-data.org/v4/competitions/WC/matches",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        matches_data = resp.json().get("matches", [])

        created = updated = skipped = 0
        for m in matches_data:
            home_code = (m.get("homeTeam") or {}).get("tla", "")
            away_code = (m.get("awayTeam") or {}).get("tla", "")
            match_date = parse_datetime(m.get("utcDate", ""))
            api_id = m.get("id")

            if not match_date or not home_code or not away_code:
                skipped += 1
                continue

            try:
                home_team = Team.objects.get(code=home_code)
                away_team = Team.objects.get(code=away_code)
            except Team.DoesNotExist:
                self.stderr.write(f"Team not found: {home_code} or {away_code} — run import_teams first")
                skipped += 1
                continue

            stage = STAGE_MAP.get(m.get("stage", ""), "GROUP")
            # football-data returns e.g. "GROUP_A" → extract single letter
            raw_group = m.get("group") or ""
            group_label = raw_group.replace("GROUP_", "")[:1]

            if stage == "GROUP" and group_label:
                Team.objects.filter(code__in=[home_code, away_code]).update(group=group_label)

            _, was_created = Match.objects.update_or_create(
                api_id=api_id,
                defaults={
                    "home_team": home_team,
                    "away_team": away_team,
                    "stage": stage,
                    "group_label": group_label,
                    "match_date": match_date,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"Fixtures: {created} created, {updated} updated, {skipped} skipped.")
        )
