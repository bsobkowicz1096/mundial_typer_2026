import time
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import Team


class Command(BaseCommand):
    help = "Import teams from football-data.org WC 2026"

    def handle(self, *args, **options):
        api_key = settings.FOOTBALL_DATA_API_KEY
        if not api_key:
            self.stderr.write("FOOTBALL_DATA_API_KEY not set in .env")
            return

        headers = {"X-Auth-Token": api_key}
        resp = requests.get(
            "https://api.football-data.org/v4/competitions/WC/teams",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        teams_data = resp.json().get("teams", [])

        flags_dir = Path(settings.BASE_DIR) / "static" / "flags"
        flags_dir.mkdir(parents=True, exist_ok=True)

        created = updated = 0
        for t in teams_data:
            code = (t.get("tla") or "")[:3].upper()
            if not code:
                continue

            flag_filename = self._download_flag(t.get("crest", ""), code, flags_dir)

            _, was_created = Team.objects.update_or_create(
                code=code,
                defaults={"name": t.get("name", ""), "flag": flag_filename},
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Teams: {created} created, {updated} updated."))

    def _download_flag(self, crest_url, code, flags_dir):
        if not crest_url:
            return ""
        ext = crest_url.rsplit(".", 1)[-1].lower() if "." in crest_url.split("/")[-1] else "png"
        flag_filename = f"{code}.{ext}"
        flag_path = flags_dir / flag_filename
        if flag_path.exists():
            return flag_filename
        try:
            r = requests.get(crest_url, timeout=10)
            r.raise_for_status()
            flag_path.write_bytes(r.content)
            time.sleep(0.15)  # stay under 10 req/min free tier
        except Exception as e:
            self.stderr.write(f"Flag download failed for {code}: {e}")
            return ""
        return flag_filename
