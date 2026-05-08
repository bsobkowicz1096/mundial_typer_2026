from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .models import Bet, Leaderboard, Match, Team
from .scoring import (
    apply_match_results,
    calculate_match_points,
    calculate_special_points,
    update_leaderboard,
)


# ── helpers for pure-function tests (no DB) ───────────────────────────────────

def _match(home, away, finished=True):
    direction = "1" if home > away else ("2" if home < away else "X")
    return SimpleNamespace(
        is_finished=finished,
        home_score=home,
        away_score=away,
        result_direction=direction,
    )


def _bet(home, away):
    direction = "1" if home > away else ("2" if home < away else "X")
    return SimpleNamespace(home_score=home, away_score=away, bet_direction=direction)


def _question(answer_type, resolved=True, **correct):
    return SimpleNamespace(is_resolved=resolved, answer_type=answer_type, **correct)


# ── calculate_match_points ────────────────────────────────────────────────────

class CalculateMatchPointsTest(SimpleTestCase):

    def test_exact_score_returns_3(self):
        self.assertEqual(calculate_match_points(_bet(2, 1), _match(2, 1)), 3)

    def test_exact_draw_returns_3(self):
        self.assertEqual(calculate_match_points(_bet(1, 1), _match(1, 1)), 3)

    def test_exact_zero_zero_returns_3(self):
        self.assertEqual(calculate_match_points(_bet(0, 0), _match(0, 0)), 3)

    def test_correct_direction_home_win_returns_1(self):
        self.assertEqual(calculate_match_points(_bet(3, 0), _match(2, 1)), 1)

    def test_correct_direction_away_win_returns_1(self):
        self.assertEqual(calculate_match_points(_bet(0, 2), _match(1, 3)), 1)

    def test_correct_direction_draw_returns_1(self):
        # bet 2:2, match 0:0 — both draws, wrong score → 1 pt
        self.assertEqual(calculate_match_points(_bet(2, 2), _match(0, 0)), 1)

    def test_wrong_prediction_returns_0(self):
        # bet home win, match away win
        self.assertEqual(calculate_match_points(_bet(2, 0), _match(0, 2)), 0)

    def test_bet_draw_match_home_win_returns_0(self):
        self.assertEqual(calculate_match_points(_bet(1, 1), _match(2, 0)), 0)

    def test_unfinished_match_returns_none(self):
        self.assertIsNone(
            calculate_match_points(_bet(1, 0), _match(1, 0, finished=False))
        )

    def test_extra_time_90min_draw_exact_returns_3(self):
        # Match went to ET; only 90-min result is stored (1:1). Exact bet → 3 pts.
        self.assertEqual(calculate_match_points(_bet(1, 1), _match(1, 1)), 3)

    def test_extra_time_90min_draw_direction_returns_1(self):
        # Same ET match (1:1 at 90 min); user bet 0:0 — correct direction, wrong score → 1 pt.
        self.assertEqual(calculate_match_points(_bet(0, 0), _match(1, 1)), 1)

    def test_extra_time_winner_bet_gets_0_if_draw_at_90(self):
        # User bet 2:1 (home win), but 90-min result was 1:1 (draw) → 0 pts.
        self.assertEqual(calculate_match_points(_bet(2, 1), _match(1, 1)), 0)


# ── calculate_special_points ─────────────────────────────────────────────────

class CalculateSpecialPointsTest(SimpleTestCase):

    def test_correct_player_returns_2(self):
        q = _question("PLAYER", correct_player_id=7)
        self.assertEqual(calculate_special_points(SimpleNamespace(answer_player_id=7), q), 2)

    def test_wrong_player_returns_0(self):
        q = _question("PLAYER", correct_player_id=7)
        self.assertEqual(calculate_special_points(SimpleNamespace(answer_player_id=9), q), 0)

    def test_correct_team_returns_2(self):
        q = _question("TEAM", correct_team_id=3)
        self.assertEqual(calculate_special_points(SimpleNamespace(answer_team_id=3), q), 2)

    def test_wrong_team_returns_0(self):
        q = _question("TEAM", correct_team_id=3)
        self.assertEqual(calculate_special_points(SimpleNamespace(answer_team_id=5), q), 0)

    def test_correct_number_returns_2(self):
        q = _question("NUMBER", correct_number=6)
        self.assertEqual(calculate_special_points(SimpleNamespace(answer_number=6), q), 2)

    def test_wrong_number_returns_0(self):
        q = _question("NUMBER", correct_number=6)
        self.assertEqual(calculate_special_points(SimpleNamespace(answer_number=5), q), 0)

    def test_unresolved_returns_none(self):
        q = _question("NUMBER", resolved=False, correct_number=6)
        self.assertIsNone(calculate_special_points(SimpleNamespace(answer_number=6), q))


# ── apply_match_results ───────────────────────────────────────────────────────

class ApplyMatchResultsTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("player", password="x")
        home = Team.objects.create(name="Home FC", code="HFC")
        away = Team.objects.create(name="Away FC", code="AFC")
        self.match = Match.objects.create(
            home_team=home, away_team=away,
            stage="GROUP", match_date=timezone.now(),
            home_score=2, away_score=1, is_finished=True,
        )

    def _place_bet(self, home, away):
        return Bet.objects.create(
            user=self.user, match=self.match, home_score=home, away_score=away
        )

    def test_exact_bet_gets_3(self):
        bet = self._place_bet(2, 1)
        apply_match_results(self.match)
        bet.refresh_from_db()
        self.assertEqual(bet.points, 3)

    def test_direction_bet_gets_1(self):
        bet = self._place_bet(3, 2)  # home win, wrong score
        apply_match_results(self.match)
        bet.refresh_from_db()
        self.assertEqual(bet.points, 1)

    def test_wrong_bet_gets_0(self):
        bet = self._place_bet(0, 2)  # away win, match was home win
        apply_match_results(self.match)
        bet.refresh_from_db()
        self.assertEqual(bet.points, 0)

    def test_unfinished_match_does_nothing(self):
        bet = self._place_bet(2, 1)
        self.match.is_finished = False
        self.match.save()
        apply_match_results(self.match)
        bet.refresh_from_db()
        self.assertIsNone(bet.points)

    def test_leaderboard_updated_after_apply(self):
        self._place_bet(2, 1)
        apply_match_results(self.match)
        lb = Leaderboard.objects.get(user=self.user)
        self.assertEqual(lb.total_points, 3)
        self.assertEqual(lb.exact_hits, 1)
        self.assertEqual(lb.direction_hits, 0)


# ── update_leaderboard ────────────────────────────────────────────────────────

class UpdateLeaderboardTest(TestCase):

    def setUp(self):
        self._counter = 0

    def _new_match(self):
        self._counter += 1
        n = self._counter
        home = Team.objects.create(name=f"Home {n}", code=f"H{n:02d}")
        away = Team.objects.create(name=f"Away {n}", code=f"A{n:02d}")
        return Match.objects.create(
            home_team=home, away_team=away,
            stage="GROUP", match_date=timezone.now(),
            home_score=1, away_score=0, is_finished=True,
        )

    def _user_with_bets(self, username, pts_list):
        """Create user whose bets already have points saved (simulates post-scoring state)."""
        user = User.objects.create_user(username, password="x")
        for pts in pts_list:
            Bet.objects.create(
                user=user, match=self._new_match(),
                home_score=1, away_score=0, points=pts,
            )
        return user

    def test_ranking_by_total_points(self):
        u1 = self._user_with_bets("alice", [3, 3, 1])   # 7 pts
        u2 = self._user_with_bets("bob",   [3, 1, 1])   # 5 pts
        u3 = self._user_with_bets("carol", [3, 3, 3])   # 9 pts

        update_leaderboard()

        self.assertEqual(Leaderboard.objects.get(user=u3).position, 1)
        self.assertEqual(Leaderboard.objects.get(user=u1).position, 2)
        self.assertEqual(Leaderboard.objects.get(user=u2).position, 3)

    def test_tiebreaker_exact_hits(self):
        # Both 4 pts; u1 has 1 exact, u2 has 0 exact → u1 wins
        u1 = self._user_with_bets("anna",  [3, 1])           # 4 pts, 1 exact
        u2 = self._user_with_bets("berta", [1, 1, 1, 1])     # 4 pts, 0 exact

        update_leaderboard()

        self.assertEqual(Leaderboard.objects.get(user=u1).position, 1)
        self.assertEqual(Leaderboard.objects.get(user=u2).position, 2)

    def test_tiebreaker_username_alphabetical(self):
        # Fully tied (same pts, same exact, same direction) → alphabetical username
        u_adam = self._user_with_bets("adam", [3, 1])
        u_zara = self._user_with_bets("zara", [3, 1])

        update_leaderboard()

        self.assertEqual(Leaderboard.objects.get(user=u_adam).position, 1)
        self.assertEqual(Leaderboard.objects.get(user=u_zara).position, 2)

    def test_position_trend_up(self):
        u1 = self._user_with_bets("leader", [3])
        u2 = self._user_with_bets("chaser", [1])
        update_leaderboard()

        # u2 overtakes u1 — give u2 more points
        Bet.objects.filter(user=u2).update(points=3)
        Bet.objects.filter(user=u1).update(points=0)
        update_leaderboard()

        lb2 = Leaderboard.objects.get(user=u2)
        self.assertEqual(lb2.position, 1)
        self.assertEqual(lb2.position_trend, "up")

    def test_position_trend_same(self):
        u = self._user_with_bets("stable", [3])
        update_leaderboard()
        update_leaderboard()
        lb = Leaderboard.objects.get(user=u)
        self.assertEqual(lb.position_trend, "same")
