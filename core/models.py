from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Team(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=3, unique=True)
    group = models.CharField(max_length=1, blank=True)
    flag = models.CharField(max_length=10, blank=True)  # nazwa pliku, np. "POL.png"

    def __str__(self):
        return f"{self.name} ({self.code})"

    class Meta:
        ordering = ["group", "name"]


class Player(models.Model):
    POSITION_CHOICES = [
        ("GK", "Bramkarz"),
        ("DEF", "Obrońca"),
        ("MID", "Pomocnik"),
        ("FWD", "Napastnik"),
    ]

    name = models.CharField(max_length=100)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="players")
    position = models.CharField(max_length=3, choices=POSITION_CHOICES, blank=True)

    def __str__(self):
        return f"{self.name} ({self.team.code})"

    class Meta:
        ordering = ["team", "name"]


class Match(models.Model):
    STAGE_CHOICES = [
        ("LEAGUE", "Liga"),
        ("GROUP", "Faza grupowa"),
        ("R32", "1/16 finału"),
        ("R16", "1/8 finału"),
        ("QF", "Ćwierćfinał"),
        ("SF", "Półfinał"),
        ("3RD", "Mecz o 3. miejsce"),
        ("FINAL", "Finał"),
    ]

    api_id = models.IntegerField(unique=True, null=True, blank=True)
    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="home_matches")
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="away_matches")
    stage = models.CharField(max_length=10, choices=STAGE_CHOICES)
    group_label = models.CharField(max_length=1, blank=True)
    match_date = models.DateTimeField()
    home_score = models.PositiveIntegerField(blank=True, null=True)
    away_score = models.PositiveIntegerField(blank=True, null=True)
    home_score_80 = models.PositiveIntegerField(blank=True, null=True)
    away_score_80 = models.PositiveIntegerField(blank=True, null=True)
    home_score_90 = models.PositiveIntegerField(blank=True, null=True)
    away_score_90 = models.PositiveIntegerField(blank=True, null=True)
    is_finished = models.BooleanField(default=False)

    class Meta:
        ordering = ["match_date"]
        verbose_name_plural = "Matches"

    def __str__(self):
        return f"{self.home_team.code} vs {self.away_team.code} ({self.get_stage_display()})"

    @property
    def bet_deadline(self):
        return self.match_date - timedelta(hours=1)

    @property
    def is_bettable(self):
        return timezone.now() < self.bet_deadline

    @property
    def result_direction(self):
        if self.home_score is None:
            return None
        if self.home_score > self.away_score:
            return "1"
        if self.home_score < self.away_score:
            return "2"
        return "X"


class Bet(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bets")
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="bets")
    home_score = models.PositiveIntegerField()
    away_score = models.PositiveIntegerField()
    points = models.IntegerField(null=True, blank=True)  # null = mecz nierozstrzygnięty
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "match")]

    def __str__(self):
        return f"{self.user.username}: {self.match} → {self.home_score}:{self.away_score}"

    @property
    def bet_direction(self):
        if self.home_score > self.away_score:
            return "1"
        if self.home_score < self.away_score:
            return "2"
        return "X"


class SpecialQuestion(models.Model):
    ANSWER_TYPE_CHOICES = [
        ("PLAYER", "Zawodnik"),
        ("TEAM", "Drużyna"),
        ("NUMBER", "Liczba"),
    ]

    text = models.CharField(max_length=255)
    answer_type = models.CharField(max_length=10, choices=ANSWER_TYPE_CHOICES)
    correct_player = models.ForeignKey(
        Player, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    correct_team = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    correct_number = models.IntegerField(null=True, blank=True)
    is_resolved = models.BooleanField(default=False)
    deadline = models.DateTimeField()

    def __str__(self):
        return self.text


class SpecialBet(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="special_bets")
    question = models.ForeignKey(SpecialQuestion, on_delete=models.CASCADE, related_name="bets")
    answer_player = models.ForeignKey(
        Player, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    answer_team = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    answer_number = models.IntegerField(null=True, blank=True)
    points = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "question")]

    def __str__(self):
        return f"{self.user.username}: {self.question}"


class Leaderboard(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="ranking")
    total_points = models.IntegerField(default=0)
    match_points = models.IntegerField(default=0)
    special_points = models.IntegerField(default=0)
    exact_hits = models.IntegerField(default=0)
    direction_hits = models.IntegerField(default=0)
    position = models.IntegerField(default=0)
    prev_position = models.IntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-total_points", "-exact_hits", "-direction_hits", "user__username"]

    def __str__(self):
        return f"{self.position}. {self.user.username} ({self.total_points} pkt)"

    @property
    def position_trend(self):
        if self.prev_position is None:
            return "new"
        if self.position < self.prev_position:
            return "up"
        if self.position > self.prev_position:
            return "down"
        return "same"


class SimulationSnapshot(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    n_simulations = models.IntegerField()
    data = models.JSONField()

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = "created_at"

    def __str__(self):
        return f"Snapshot {self.created_at:%Y-%m-%d %H:%M} ({self.n_simulations:,} sims)"

    @classmethod
    def latest(cls):
        return cls.objects.first()


class InviteCode(models.Model):
    code = models.CharField(max_length=20, unique=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_invites")
    used_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="used_invite"
    )
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = f"użyty przez {self.used_by}" if self.is_used else "aktywny"
        return f"{self.code} ({status})"
