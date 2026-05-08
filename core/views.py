from itertools import groupby

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localtime

from .forms import BetForm, RegisterForm, SpecialBetForm
from .models import Bet, Leaderboard, Match, Player, SpecialBet, SpecialQuestion, Team


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def register(request):
    if request.user.is_authenticated:
        return redirect("core:home")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Witaj w lidze! Możesz już obstawiać.")
            return redirect("core:home")
    else:
        form = RegisterForm()
    return render(request, "core/register.html", {"form": form})


class LoginView(auth_views.LoginView):
    template_name = "core/login.html"


@login_required
def home(request):
    from django.utils import timezone
    upcoming = list(
        Match.objects.filter(is_finished=False, match_date__gte=timezone.now())
        .select_related("home_team", "away_team")
        .order_by("match_date")[:5]
    )
    user_bets = {
        b.match_id: b
        for b in Bet.objects.filter(user=request.user, match__in=upcoming)
    }
    for match in upcoming:
        match.user_bet = user_bets.get(match.id)

    top5 = Leaderboard.objects.select_related("user").order_by("position")[:5]
    user_rank = Leaderboard.objects.filter(user=request.user).first()

    return render(request, "core/home.html", {
        "upcoming": upcoming,
        "top5": top5,
        "user_rank": user_rank,
    })


@login_required
def match_list(request):
    matches = list(
        Match.objects.select_related("home_team", "away_team").order_by("match_date")
    )
    user_bets = {b.match_id: b for b in Bet.objects.filter(user=request.user)}
    for match in matches:
        match.user_bet = user_bets.get(match.id)

    grouped = [
        (date_key, list(day_matches))
        for date_key, day_matches in groupby(
            matches, key=lambda m: localtime(m.match_date).date()
        )
    ]
    return render(request, "core/matches.html", {"grouped_matches": grouped})


@login_required
def place_bet(request, match_id):
    match = get_object_or_404(
        Match.objects.select_related("home_team", "away_team"), pk=match_id
    )
    existing_bet = Bet.objects.filter(user=request.user, match=match).first()
    htmx = _is_htmx(request)

    if request.method == "POST":
        if not match.is_bettable:
            match.user_bet = existing_bet
            if htmx:
                return render(request, "core/partials/bet_cell.html", {"match": match})
            messages.error(request, "Czas na obstawianie tego meczu minął.")
            return redirect("core:match_list")

        form = BetForm(request.POST, instance=existing_bet)
        if form.is_valid():
            bet = form.save(commit=False)
            bet.user = request.user
            bet.match = match
            bet.save()
            match.user_bet = bet
            if htmx:
                return render(request, "core/partials/bet_cell.html", {"match": match})
            messages.success(request, "Typ zapisany!")
            return redirect("core:match_list")

        match.user_bet = existing_bet
        if htmx:
            return render(request, "core/partials/bet_cell.html", {
                "match": match, "form_errors": True
            })

    match.user_bet = existing_bet
    form = BetForm(instance=existing_bet)
    return render(request, "core/match_bet.html", {"match": match, "form": form})


@login_required
def leaderboard(request):
    rankings = Leaderboard.objects.select_related("user").order_by("position")
    if _is_htmx(request):
        return render(request, "core/partials/leaderboard_table.html", {"rankings": rankings})
    return render(request, "core/leaderboard.html", {"rankings": rankings})


@login_required
def profile(request, username):
    viewed_user = get_object_or_404(User, username=username)
    user_rank = Leaderboard.objects.filter(user=viewed_user).first()
    bets = (
        Bet.objects.filter(user=viewed_user)
        .select_related("match__home_team", "match__away_team")
        .order_by("-match__match_date")
    )
    return render(request, "core/profile.html", {
        "viewed_user": viewed_user,
        "user_rank": user_rank,
        "bets": bets,
    })


@login_required
def players_by_team(request, team_id):
    players = Player.objects.filter(team_id=team_id).order_by("name")
    q_id = request.GET.get("q", "")
    selected_id = request.GET.get("selected", "")
    return render(request, "core/partials/players_dropdown.html", {
        "players": players,
        "q_id": q_id,
        "selected_id": selected_id,
    })


@login_required
def special_bets(request):
    from django.utils import timezone

    questions = SpecialQuestion.objects.order_by("id")
    existing = {
        sb.question_id: sb
        for sb in SpecialBet.objects.filter(user=request.user).select_related(
            "answer_player__team", "answer_team"
        )
    }

    if request.method == "POST":
        question_id = request.POST.get("question_id")
        question = get_object_or_404(SpecialQuestion, pk=question_id)

        if timezone.now() > question.deadline:
            messages.error(request, "Deadline minął, nie można już zmieniać tego zakładu.")
            return redirect("core:special_bets")

        existing_bet = existing.get(question.id)
        form = SpecialBetForm(question, request.POST, instance=existing_bet)
        if form.is_valid():
            bet = form.save(commit=False)
            bet.user = request.user
            bet.question = question
            bet.save()
            messages.success(request, "Zakład zapisany!")
        else:
            messages.error(request, "Nieprawidłowe dane — spróbuj ponownie.")
        return redirect("core:special_bets")

    teams = Team.objects.order_by("name")
    items = []
    for q in questions:
        bet = existing.get(q.id)
        preloaded_players = []
        selected_team_id = ""
        if bet and bet.answer_player_id:
            selected_team_id = str(bet.answer_player.team_id)
            preloaded_players = list(Player.objects.filter(team_id=selected_team_id).order_by("name"))
        items.append({
            "question": q,
            "existing": bet,
            "preloaded_players": preloaded_players,
            "selected_team_id": selected_team_id,
        })

    return render(request, "core/special_bets.html", {"items": items, "teams": teams})
