import os
import logging

from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run Monte Carlo simulation and save a SimulationSnapshot."

    def add_arguments(self, parser):
        parser.add_argument(
            "--n-sims",
            type=int,
            default=10_000,
            help="Number of tournament MC iterations (default: 10 000)",
        )
        parser.add_argument(
            "--n-typer-sims",
            type=int,
            default=10_000,
            help="Number of typer simulation iterations (default: 10 000)",
        )

    def handle(self, *args, **options):
        from core.analytics import run_simulation, run_typer_simulation
        from core.models import Leaderboard, Match, SimulationSnapshot

        n_sims       = options["n_sims"]
        n_typer_sims = options["n_typer_sims"]
        data_path    = os.path.join(settings.BASE_DIR, "notebooks", "data", "all_matches.csv")

        if not os.path.exists(data_path):
            self.stderr.write(self.style.ERROR(f"Data file not found: {data_path}"))
            return

        # Known WC 2026 results from DB
        finished = Match.objects.filter(is_finished=True).select_related(
            "home_team", "away_team"
        )
        known_wc_results = [
            {
                "home":       m.home_team.code,
                "away":       m.away_team.code,
                "home_score": m.home_score,
                "away_score": m.away_score,
                "date":       m.match_date.date().isoformat(),
            }
            for m in finished
        ]

        self.stdout.write(
            f"Running {n_sims:,} tournament simulations "
            f"({len(known_wc_results)} known WC results)…"
        )

        result = run_simulation(
            data_path=data_path,
            n_simulations=n_sims,
            known_wc_results=known_wc_results or None,
        )

        # Typer simulation — current leaderboard scores
        user_scores = {
            lb.user.username: lb.total_points
            for lb in Leaderboard.objects.select_related("user").all()
        }

        self.stdout.write(
            f"Running typer simulation ({len(user_scores)} users, {n_typer_sims:,} sims)…"
        )

        typer_probs = run_typer_simulation(
            team_stats=result["team_stats"],
            user_scores=user_scores,
            tournament_data=result["tournament"],
            n_simulations=n_typer_sims,
        )

        result["typers"] = typer_probs

        snapshot = SimulationSnapshot.objects.create(
            n_simulations=n_sims,
            data=result,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Snapshot #{snapshot.pk} saved "
                f"({len(typer_probs)} typers, generated_at={result['generated_at']})"
            )
        )
