from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand

from core.models import SpecialQuestion

QUESTIONS = [
    {"text": "Król strzelców — kto zdobędzie najwięcej bramek?", "answer_type": "PLAYER"},
    {"text": "Najlepszy asystent — kto zanotuje najwięcej asyst?", "answer_type": "PLAYER"},
    {"text": "Zwycięzca klasyfikacji kanadyjskiej (gole + asysty)?", "answer_type": "PLAYER"},
    {"text": "Finalista — wskaż jedną drużynę która dotrze do finału", "answer_type": "TEAM"},
    {"text": "Która drużyna zdobędzie najwięcej bramek w fazie grupowej?", "answer_type": "TEAM"},
    {"text": "Która drużyna pierwsza zobaczy czerwoną kartkę w turnieju?", "answer_type": "TEAM"},
    {"text": "Która drużyna awansuje z 3. miejsca w swojej grupie?", "answer_type": "TEAM"},
    {"text": "Ile bramek samobójczych padnie w całym turnieju?", "answer_type": "NUMBER"},
    {"text": "Ile meczów w fazie grupowej zakończy się remisem?", "answer_type": "NUMBER"},
]

WARSAW = ZoneInfo("Europe/Warsaw")
# Deadline: 24h przed pierwszym meczem (11 czerwca 2026, 21:00 Warsaw)
DEFAULT_DEADLINE = datetime(2026, 6, 10, 21, 0, tzinfo=WARSAW)


class Command(BaseCommand):
    help = "Tworzy 9 pytań do zakładów dodatkowych (idempotentne)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--deadline",
            type=str,
            help="Deadline w formacie YYYY-MM-DD HH:MM (domyślnie: 2026-06-10 21:00 Warsaw)",
        )

    def handle(self, *args, **options):
        if options["deadline"]:
            deadline = datetime.strptime(options["deadline"], "%Y-%m-%d %H:%M").replace(tzinfo=WARSAW)
        else:
            deadline = DEFAULT_DEADLINE

        created = skipped = 0
        for q in QUESTIONS:
            _, was_created = SpecialQuestion.objects.get_or_create(
                text=q["text"],
                defaults={"answer_type": q["answer_type"], "deadline": deadline},
            )
            if was_created:
                created += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(f"Pytania: {created} utworzone, {skipped} już istniało.")
        )
