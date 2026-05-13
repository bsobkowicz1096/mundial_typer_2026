from django.utils import timezone


def special_bets_deadline(request):
    from .models import SpecialQuestion
    earliest = (
        SpecialQuestion.objects
        .order_by("deadline")
        .values_list("deadline", flat=True)
        .first()
    )
    return {
        "special_bets_deadline_passed": bool(earliest and timezone.now() > earliest)
    }
