import uuid

from django.contrib import admin, messages

from .models import Bet, InviteCode, Leaderboard, Match, Player, SimulationSnapshot, SpecialBet, SpecialQuestion, Team
from .scoring import apply_match_results, apply_special_results


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "group"]
    list_filter = ["group"]
    search_fields = ["name", "code"]
    ordering = ["group", "name"]


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ["name", "team", "position"]
    list_filter = ["position", "team"]
    search_fields = ["name", "team__name"]


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ["__str__", "stage", "match_date", "home_score", "away_score", "is_finished"]
    list_filter = ["stage", "is_finished", "group_label"]
    search_fields = ["home_team__name", "away_team__name", "home_team__code", "away_team__code"]
    readonly_fields = ["bet_deadline_display"]
    actions = ["recalculate_points"]

    def bet_deadline_display(self, obj):
        return obj.bet_deadline if obj.match_date else "—"
    bet_deadline_display.short_description = "Deadline obstawiania"

    @admin.action(description="Przelicz punkty dla wybranych meczów")
    def recalculate_points(self, request, queryset):
        count = 0
        for match in queryset.filter(is_finished=True):
            apply_match_results(match)
            count += 1
        if count:
            self.message_user(request, f"Przeliczono punkty dla {count} meczów.", messages.SUCCESS)
        else:
            self.message_user(request, "Żaden wybrany mecz nie jest zakończony.", messages.WARNING)


@admin.register(Bet)
class BetAdmin(admin.ModelAdmin):
    list_display = ["user", "match", "home_score", "away_score", "points", "updated_at"]
    list_filter = ["points", "match__stage"]
    search_fields = ["user__username", "match__home_team__code", "match__away_team__code"]
    raw_id_fields = ["match"]


@admin.register(SpecialQuestion)
class SpecialQuestionAdmin(admin.ModelAdmin):
    list_display = ["text", "answer_type", "is_resolved", "deadline"]
    list_filter = ["answer_type", "is_resolved"]
    actions = ["resolve_questions"]

    @admin.action(description="Rozstrzygnij wybrane pytania i nalicz punkty")
    def resolve_questions(self, request, queryset):
        resolved = skipped = 0
        for question in queryset:
            has_answer = (
                (question.answer_type == "PLAYER" and question.correct_player_id) or
                (question.answer_type == "TEAM" and question.correct_team_id) or
                (question.answer_type == "NUMBER" and question.correct_number is not None)
            )
            if not has_answer:
                skipped += 1
                continue
            question.is_resolved = True
            question.save(update_fields=["is_resolved"])
            apply_special_results(question)
            resolved += 1

        if resolved:
            self.message_user(request, f"Rozstrzygnięto {resolved} pytań i naliczono punkty.", messages.SUCCESS)
        if skipped:
            self.message_user(request, f"Pominięto {skipped} pytań bez podanej poprawnej odpowiedzi.", messages.WARNING)


@admin.register(SpecialBet)
class SpecialBetAdmin(admin.ModelAdmin):
    list_display = ["user", "question", "points"]
    list_filter = ["points", "question"]
    search_fields = ["user__username"]


@admin.register(Leaderboard)
class LeaderboardAdmin(admin.ModelAdmin):
    list_display = ["position", "user", "total_points", "match_points", "special_points", "exact_hits", "direction_hits"]
    ordering = ["position"]
    readonly_fields = ["position", "prev_position", "updated_at"]


@admin.register(SimulationSnapshot)
class SimulationSnapshotAdmin(admin.ModelAdmin):
    list_display = ["__str__", "n_simulations", "created_at"]
    readonly_fields = ["created_at", "n_simulations", "data"]
    actions = ["run_new_simulation"]

    @admin.action(description="Uruchom nową symulację Monte Carlo")
    def run_new_simulation(self, request, queryset):
        from django.core.management import call_command
        call_command("run_simulation")
        self.message_user(request, "Symulacja zakończona — nowy snapshot zapisany.", messages.SUCCESS)


@admin.register(InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    list_display = ["code", "created_by", "used_by", "is_used", "created_at"]
    list_filter = ["is_used"]
    actions = ["generate_codes"]

    @admin.action(description="Wygeneruj 10 nowych kodów zaproszenia")
    def generate_codes(self, request, queryset):
        created = [
            InviteCode(code=uuid.uuid4().hex[:8].upper(), created_by=request.user)
            for _ in range(10)
        ]
        InviteCode.objects.bulk_create(created)
        self.message_user(request, f"Wygenerowano 10 nowych kodów.", messages.SUCCESS)
