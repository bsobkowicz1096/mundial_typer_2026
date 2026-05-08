from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("matches/", views.match_list, name="match_list"),
    path("matches/<int:match_id>/bet/", views.place_bet, name="place_bet"),
    path("special-bets/", views.special_bets, name="special_bets"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("ajax/players/<int:team_id>/", views.players_by_team, name="players_by_team"),
    path("profile/<str:username>/", views.profile, name="profile"),
]
