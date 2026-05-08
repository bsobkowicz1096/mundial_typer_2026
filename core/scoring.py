from django.db.models import Sum

from .models import Bet, Leaderboard, SpecialBet


def calculate_match_points(bet, match):
    """Zwraca 3 (dokładny wynik), 1 (kierunek), 0 (pudło), None (mecz nierozstrzygnięty)."""
    if not match.is_finished:
        return None
    if bet.home_score == match.home_score and bet.away_score == match.away_score:
        return 3
    if bet.bet_direction == match.result_direction:
        return 1
    return 0


def calculate_special_points(special_bet, question):
    """Zwraca 2 (trafienie), 0 (pudło), None (pytanie nierozstrzygnięte)."""
    if not question.is_resolved:
        return None
    if question.answer_type == "PLAYER":
        return 2 if special_bet.answer_player_id == question.correct_player_id else 0
    if question.answer_type == "TEAM":
        return 2 if special_bet.answer_team_id == question.correct_team_id else 0
    if question.answer_type == "NUMBER":
        return 2 if special_bet.answer_number == question.correct_number else 0
    return 0


def apply_special_results(question):
    """Zapisuje punkty do SpecialBetów danego pytania i aktualizuje leaderboard."""
    if not question.is_resolved:
        return
    bets = question.bets.select_related("user")
    for bet in bets:
        bet.points = calculate_special_points(bet, question)
    SpecialBet.objects.bulk_update(bets, ["points"])
    update_leaderboard()


def apply_match_results(match):
    """Zapisuje punkty do betów danego meczu i aktualizuje leaderboard."""
    if not match.is_finished:
        return
    bets = match.bets.select_related("user")
    for bet in bets:
        bet.points = calculate_match_points(bet, match)
    Bet.objects.bulk_update(bets, ["points"])
    update_leaderboard()


def update_leaderboard():
    """Przelicza cały ranking na podstawie zapisanych punktów w Bet i SpecialBet."""
    from django.contrib.auth.models import User

    for user in User.objects.filter(is_active=True):
        match_pts = (
            Bet.objects.filter(user=user, points__isnull=False).aggregate(Sum("points"))["points__sum"] or 0
        )
        special_pts = (
            SpecialBet.objects.filter(user=user, points__isnull=False).aggregate(Sum("points"))["points__sum"] or 0
        )
        exact = Bet.objects.filter(user=user, points=3).count()
        direction = Bet.objects.filter(user=user, points=1).count()

        lb, _ = Leaderboard.objects.get_or_create(user=user)
        lb.prev_position = lb.position
        lb.match_points = match_pts
        lb.special_points = special_pts
        lb.total_points = match_pts + special_pts
        lb.exact_hits = exact
        lb.direction_hits = direction
        lb.save()

    leaderboards = list(
        Leaderboard.objects.order_by("-total_points", "-exact_hits", "-direction_hits", "user__username")
    )
    for i, lb in enumerate(leaderboards, 1):
        lb.position = i
    Leaderboard.objects.bulk_update(leaderboards, ["position"])
