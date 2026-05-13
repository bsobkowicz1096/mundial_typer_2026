"""
Monte Carlo simulation engine for Mundial Typer 2026.
No Django imports — safe to call from management commands or background tasks.
"""

import math
import logging
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WC 2026 bracket
# ---------------------------------------------------------------------------
GROUPS = {
    'A': ['MEX', 'RSA', 'KOR', 'CZE'],
    'B': ['CAN', 'SUI', 'QAT', 'BIH'],
    'C': ['BRA', 'MAR', 'HAI', 'SCO'],
    'D': ['USA', 'PAR', 'AUS', 'TUR'],
    'E': ['GER', 'CUR', 'CIV', 'ECU'],
    'F': ['NED', 'JPN', 'TUN', 'SWE'],
    'G': ['BEL', 'EGY', 'IRN', 'NZL'],
    'H': ['ESP', 'CPV', 'KSA', 'URY'],
    'I': ['FRA', 'SEN', 'NOR', 'IRQ'],
    'J': ['ARG', 'ALG', 'AUT', 'JOR'],
    'K': ['POR', 'UZB', 'COL', 'COD'],
    'L': ['ENG', 'CRO', 'GHA', 'PAN'],
}

ALL_TEAMS = [team for group in GROUPS.values() for team in group]

TEAM_NAMES = {
    'MEX': 'Mexico',        'RSA': 'South Africa',  'KOR': 'South Korea',
    'CZE': 'Czechia',       'CAN': 'Canada',        'SUI': 'Switzerland',
    'QAT': 'Qatar',         'BIH': 'Bosnia and Herzegovina', 'BRA': 'Brazil',
    'MAR': 'Morocco',       'HAI': 'Haiti',         'SCO': 'Scotland',
    'USA': 'United States', 'PAR': 'Paraguay',      'AUS': 'Australia',
    'TUR': 'Turkey',        'GER': 'Germany',       'CUR': 'Curaçao',
    'CIV': 'Ivory Coast',   'ECU': 'Ecuador',       'NED': 'Netherlands',
    'JPN': 'Japan',         'TUN': 'Tunisia',       'SWE': 'Sweden',
    'BEL': 'Belgium',       'EGY': 'Egypt',         'IRN': 'Iran',
    'NZL': 'New Zealand',   'ESP': 'Spain',         'CPV': 'Cape Verde',
    'KSA': 'Saudi Arabia',  'URY': 'Uruguay',       'FRA': 'France',
    'SEN': 'Senegal',       'NOR': 'Norway',        'IRQ': 'Iraq',
    'ARG': 'Argentina',     'ALG': 'Algeria',       'AUT': 'Austria',
    'JOR': 'Jordan',        'POR': 'Portugal',      'UZB': 'Uzbekistan',
    'COL': 'Colombia',      'COD': 'DR Congo',      'ENG': 'England',
    'CRO': 'Croatia',       'GHA': 'Ghana',         'PAN': 'Panama',
}

HOST_NATIONS = {'USA', 'MEX', 'CAN'}

# Calibrated constants (from notebooks/mundial_2026_monte_carlo.ipynb)
ATTDEF_HALF_LIFE_YEARS = 4
ATTDEF_BASE = 1.3
P_RED_CARD_PER_MATCH = 0.141
P_OWN_GOAL_PER_MATCH = 0.082

CONTINENTAL_FINALS = {
    'European Championship', 'Copa América', 'Copa America',
    'African Nations Cup', 'Asian Cup', 'CONCACAF Championship',
    'Oceania Nations Cup', 'Confederations Cup',
}

# ---------------------------------------------------------------------------
# ELO / Dixon-Coles helpers
# ---------------------------------------------------------------------------

def _base_k(tournament: str) -> float:
    if tournament == 'World Cup':
        return 60
    if tournament in CONTINENTAL_FINALS:
        return 50
    t = tournament.lower()
    if 'world cup' in t or 'qualifier' in t or ' qual' in t or 'nations league' in t:
        return 40
    if 'friendly' in t:
        return 20
    return 30


def _k_goal_diff(gd: int) -> float:
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    if gd == 3:
        return 1.75
    return 1.75 + (gd - 3) / 8


def _elo_expected(elo_h: float, elo_a: float, neutral: bool = False) -> float:
    home_bonus = 0 if neutral else 100
    dr = (elo_h - elo_a) + home_bonus
    return 1 / (10 ** (-dr / 400) + 1)


def _elo_actual(goals_h: int, goals_a: int):
    if goals_h > goals_a:
        return 1.0, 0.0
    if goals_h < goals_a:
        return 0.0, 1.0
    return 0.5, 0.5


def _fit_dixon_coles(df: pd.DataFrame, home_advantage: float,
                     reference_date: pd.Timestamp,
                     half_life: float = ATTDEF_HALF_LIFE_YEARS,
                     max_iter: int = 200, tol: float = 1e-6):
    matches = []
    for _, row in df.iterrows():
        neutral = bool(row.get('neutral', False))
        c = 1.0 if neutral else home_advantage
        k_t = _base_k(row['tournament'])
        years_ago = (reference_date - row['date']).days / 365.25
        w = k_t * math.exp(-math.log(2) * years_ago / half_life)
        if w < 1e-9:
            continue
        matches.append((row['home_team'], row['away_team'],
                        int(row['home_score']), int(row['away_score']), w, c))

    att = defaultdict(lambda: 1.0)
    def_ = defaultdict(lambda: 1.0)

    for iteration in range(max_iter):
        att_prev = dict(att)
        def_prev = dict(def_)

        num_a, den_a = defaultdict(float), defaultdict(float)
        for h, a, gh, ga, w, c in matches:
            num_a[h] += w * gh;  den_a[h] += w * def_[a] * c
            num_a[a] += w * ga;  den_a[a] += w * def_[h] / c
        for t in num_a:
            if den_a[t] > 0:
                att[t] = num_a[t] / den_a[t]

        num_d, den_d = defaultdict(float), defaultdict(float)
        for h, a, gh, ga, w, c in matches:
            num_d[h] += w * ga;  den_d[h] += w * att[a] / c
            num_d[a] += w * gh;  den_d[a] += w * att[h] * c
        for t in num_d:
            if den_d[t] > 0:
                def_[t] = num_d[t] / den_d[t]

        tracked = set(num_a) | set(num_d)
        delta = max(abs(att[t] - att_prev.get(t, 1.0)) for t in tracked)
        delta = max(delta, max(abs(def_[t] - def_prev.get(t, 1.0)) for t in tracked))
        if delta < tol:
            logger.debug("Dixon-Coles converged after %d iterations (δ=%.2e)", iteration + 1, delta)
            break

    return att, def_


# ---------------------------------------------------------------------------
# Match / stage simulators
# ---------------------------------------------------------------------------

def _simulate_match(code_h: str, code_a: str, stats: dict,
                    host_advantage: float = 0.15) -> tuple[int, int]:
    att_h = stats[code_h]['att']
    att_a = stats[code_a]['att']
    def_h = stats[code_h]['def']
    def_a = stats[code_a]['def']
    c = 1 + host_advantage if code_h in HOST_NATIONS else 1.0
    lam_h = max(att_h * def_a * c, 0.01)
    lam_a = max(att_a * def_h / c, 0.01)
    return int(np.random.poisson(lam_h)), int(np.random.poisson(lam_a))


def _simulate_knockout_match(code_h: str, code_a: str, stats: dict) -> tuple[int, int, str]:
    gh, ga = _simulate_match(code_h, code_a, stats)
    if gh == ga:
        winner = code_h if np.random.random() < 0.5 else code_a
    else:
        winner = code_h if gh > ga else code_a
    return gh, ga, winner


def _simulate_group_stage(stats: dict) -> tuple[dict, list]:
    group_standings = {}
    match_results = []
    for group_name, teams in GROUPS.items():
        table = {t: {'pts': 0, 'gf': 0, 'ga': 0} for t in teams}
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                h, a = teams[i], teams[j]
                gh, ga = _simulate_match(h, a, stats)
                table[h]['gf'] += gh;  table[h]['ga'] += ga
                table[a]['gf'] += ga;  table[a]['ga'] += gh
                if gh > ga:
                    table[h]['pts'] += 3
                elif gh == ga:
                    table[h]['pts'] += 1;  table[a]['pts'] += 1
                else:
                    table[a]['pts'] += 3
                match_results.append({
                    'group': group_name, 'home': h, 'away': a,
                    'gh': gh, 'ga': ga, 'draw': gh == ga,
                })
        for t in table:
            table[t]['gd'] = table[t]['gf'] - table[t]['ga']
        group_standings[group_name] = sorted(
            table.items(),
            key=lambda x: (x[1]['pts'], x[1]['gd'], x[1]['gf']),
            reverse=True,
        )
    return group_standings, match_results


def _get_qualifiers(group_standings: dict) -> tuple[dict, list]:
    top2 = {}
    thirds = []
    for group, standings in group_standings.items():
        top2[group] = [standings[0][0], standings[1][0]]
        thirds.append((standings[2][0], standings[2][1]))
    thirds_sorted = sorted(thirds, key=lambda x: (x[1]['pts'], x[1]['gd'], x[1]['gf']), reverse=True)
    best_thirds = [t[0] for t in thirds_sorted[:8]]
    return top2, best_thirds


def _simulate_knockout_stage(top2: dict, best_thirds: list, stats: dict) -> dict:
    slot = {}
    for group, (t1, t2) in top2.items():
        slot[f'1{group}'] = t1
        slot[f'2{group}'] = t2

    thirds = list(best_thirds)
    np.random.shuffle(thirds)
    third_slots = [74, 77, 79, 80, 81, 82, 85, 87]
    thirds_map = {m: t for m, t in zip(third_slots, thirds)}

    def play(m, k1, k2):
        t1 = slot[k1] if isinstance(k1, str) else thirds_map[k1]
        t2 = slot[k2] if isinstance(k2, str) else thirds_map[k2]
        _, _, winner = _simulate_knockout_match(t1, t2, stats)
        slot[f'W{m}'] = winner
        slot[f'L{m}'] = t2 if winner == t1 else t1

    play(73, '2A', '2B');   play(74, '1E', 74);   play(75, '1F', '2C');  play(76, '1C', '2F')
    play(77, '1I', 77);     play(78, '2E', '2I'); play(79, '1A', 79);    play(80, '1L', 80)
    play(81, '1D', 81);     play(82, '1G', 82);   play(83, '2K', '2L'); play(84, '1H', '2J')
    play(85, '1B', 85);     play(86, '1J', '2H'); play(87, '1K', 87);    play(88, '2D', '2G')

    play(89, 'W74', 'W77'); play(90, 'W73', 'W75')
    play(91, 'W76', 'W78'); play(92, 'W79', 'W80')
    play(93, 'W83', 'W84'); play(94, 'W81', 'W82')
    play(95, 'W86', 'W88'); play(96, 'W85', 'W87')

    play(97, 'W89', 'W90'); play(98, 'W93', 'W94')
    play(99, 'W91', 'W92'); play(100, 'W95', 'W96')

    play(101, 'W97',  'W98')
    play(102, 'W99',  'W100')
    play(103, 'L101', 'L102')
    play(104, 'W101', 'W102')

    return {
        'qf':        [slot[f'W{m}'] for m in [89, 90, 91, 92, 93, 94, 95, 96]],
        'sf':        [slot[f'W{m}'] for m in [97, 98, 99, 100]],
        'finalists': (slot['W101'], slot['W102']),
        'third':     slot['W103'],
        'winner':    slot['W104'],
    }


def _simulate_red_cards_and_og(match_results: list) -> tuple[str | None, int]:
    first_red = None
    total_og = 0
    for match in match_results:
        if first_red is None and np.random.random() < P_RED_CARD_PER_MATCH:
            first_red = match['home'] if np.random.random() < 0.5 else match['away']
        total_og += int(np.random.poisson(P_OWN_GOAL_PER_MATCH))
    return first_red, total_og


# ---------------------------------------------------------------------------
# Model fitting
# ---------------------------------------------------------------------------

def _build_team_stats(df: pd.DataFrame,
                      known_wc_results: list | None,
                      reference_date: pd.Timestamp) -> dict:
    """Fits ELO + Dixon-Coles and returns team_stats dict for all 48 WC teams."""

    # Add known WC results to training data
    if known_wc_results:
        wc_rows = []
        for r in known_wc_results:
            wc_rows.append({
                'home_team':  r['home'],
                'away_team':  r['away'],
                'home_score': r['home_score'],
                'away_score': r['away_score'],
                'tournament': 'World Cup',
                'neutral':    True,
                'date':       pd.Timestamp(r.get('date', reference_date)),
            })
        df = pd.concat([df, pd.DataFrame(wc_rows)], ignore_index=True)
        logger.info("Added %d known WC results to training data", len(wc_rows))

    # Home advantage (computed from data, non-neutral matches post-2000)
    modern = df[(df['neutral'] == False) & (df['date'].dt.year >= 2000)]
    home_advantage = (modern['home_score'].mean() / modern['away_score'].mean()
                      if len(modern) > 0 else 1.664)

    # ELO
    elo: dict[str, float] = defaultdict(lambda: 1300.0)
    for _, row in df.iterrows():
        h, a = row['home_team'], row['away_team']
        neutral = bool(row.get('neutral', False))
        gh, ga = int(row['home_score']), int(row['away_score'])
        gd = abs(gh - ga)
        k = _base_k(row['tournament']) * _k_goal_diff(gd)
        we_h = _elo_expected(elo[h], elo[a], neutral=neutral)
        wa_h, wa_a = _elo_actual(gh, ga)
        elo[h] += k * (wa_h - we_h)
        elo[a] += k * (wa_a - (1 - we_h))

    elo_wc = {code: elo[TEAM_NAMES[code]] for code in ALL_TEAMS}

    # Dixon-Coles
    att_raw, def_raw = _fit_dixon_coles(df, home_advantage, reference_date)

    wc_att = [att_raw[TEAM_NAMES[c]] for c in ALL_TEAMS]
    wc_def = [def_raw[TEAM_NAMES[c]] for c in ALL_TEAMS]
    att_geomean = np.exp(np.mean(np.log(wc_att)))
    def_geomean = np.exp(np.mean(np.log(wc_def)))
    att_n = {name: v / att_geomean for name, v in att_raw.items()}
    def_n = {name: v / def_geomean for name, v in def_raw.items()}

    df_wc_ref = df[(df['tournament'] == 'World Cup') & (df['date'] > '2010-01-01')]
    xg_sides = []
    for _, row in df_wc_ref.iterrows():
        h, a = row['home_team'], row['away_team']
        xg_sides.append(att_n.get(h, 1.0) * def_n.get(a, 1.0))
        xg_sides.append(att_n.get(a, 1.0) * def_n.get(h, 1.0))
    avg_xg_model = np.mean(xg_sides) if xg_sides else 1.0
    target = (df_wc_ref['home_score'].mean() + df_wc_ref['away_score'].mean()) / 2
    scale = math.sqrt(target / avg_xg_model)

    att_s: dict[str, float] = defaultdict(lambda: scale)
    def_s: dict[str, float] = defaultdict(lambda: scale)
    for name, v in att_n.items():
        att_s[name] = v * scale
    for name, v in def_n.items():
        def_s[name] = v * scale

    return {
        code: {
            'att':  att_s[TEAM_NAMES[code]],
            'def':  def_s[TEAM_NAMES[code]],
            'elo':  elo_wc[code],
            'name': TEAM_NAMES[code],
        }
        for code in ALL_TEAMS
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_simulation(data_path: str,
                   n_simulations: int = 10_000,
                   known_wc_results: list | None = None) -> dict:
    """
    Run the full Monte Carlo simulation.

    Args:
        data_path: absolute path to all_matches.csv
        n_simulations: number of MC iterations
        known_wc_results: list of dicts with keys
            {home, away, home_score, away_score, date (optional)}

    Returns:
        dict with keys 'tournament' and 'n_simulations'
    """
    logger.info("Loading historical data from %s", data_path)
    df = pd.read_csv(data_path)
    df = df.dropna(subset=['home_score', 'away_score'])
    df['date'] = pd.to_datetime(df['date'])

    reference_date = pd.Timestamp(datetime.now().date())

    logger.info("Fitting model (reference_date=%s)", reference_date.date())
    team_stats = _build_team_stats(df, known_wc_results, reference_date)

    # Counters
    wins_tournament  = Counter()
    third_place      = Counter()
    finalist_count   = Counter()
    top4_count       = Counter()
    top8_count       = Counter()
    group_winner     = Counter()
    group_qualify    = Counter()
    third_advance    = Counter()
    most_goals_group = Counter()
    first_red_card   = Counter()
    own_goals_dist   = Counter()
    draws_dist       = Counter()

    logger.info("Running %d simulations…", n_simulations)
    for sim in range(n_simulations):
        group_standings, match_results = _simulate_group_stage(team_stats)
        top2, best_thirds = _get_qualifiers(group_standings)

        group_goals: Counter = Counter()
        draws_this = 0
        for m in match_results:
            group_goals[m['home']] += m['gh']
            group_goals[m['away']] += m['ga']
            if m['draw']:
                draws_this += 1

        draws_dist[draws_this] += 1
        most_goals_group[max(group_goals, key=group_goals.get)] += 1

        for group, standings in group_standings.items():
            group_winner[standings[0][0]] += 1
            group_qualify[standings[0][0]] += 1
            group_qualify[standings[1][0]] += 1

        for code in best_thirds:
            third_advance[code] += 1

        red_team, n_og = _simulate_red_cards_and_og(match_results)
        if red_team:
            first_red_card[red_team] += 1
        own_goals_dist[n_og] += 1

        ko = _simulate_knockout_stage(top2, best_thirds, team_stats)
        for code in ko['qf']:
            top8_count[code] += 1
        for code in ko['sf']:
            top4_count[code] += 1
        for code in ko['finalists']:
            finalist_count[code] += 1
        third_place[ko['third']] += 1
        wins_tournament[ko['winner']] += 1

        if (sim + 1) % 2000 == 0:
            logger.info("  %d / %d", sim + 1, n_simulations)

    logger.info("Simulation complete.")

    def _probs(counter):
        return {code: round(counter.get(code, 0) / n_simulations, 6)
                for code in ALL_TEAMS}

    tournament_data = {
        'wins':           _probs(wins_tournament),
        'finalist':       _probs(finalist_count),
        'top4':           _probs(top4_count),
        'top8':           _probs(top8_count),
        'group_winner':   _probs(group_winner),
        'group_qualify':  _probs(group_qualify),
        'third_advance':  _probs(third_advance),
        'most_goals_gs':  _probs(most_goals_group),
        'first_red_card': _probs(first_red_card),
        'own_goals_dist': {
            k: round(v / n_simulations, 6)
            for k, v in own_goals_dist.items()
        },
        'draws_dist': {
            k: round(v / n_simulations, 6)
            for k, v in draws_dist.items()
        },
    }

    return {
        'tournament':    tournament_data,
        'team_stats':    {code: {'att': s['att'], 'def': s['def']}
                          for code, s in team_stats.items()},
        'n_simulations': n_simulations,
        'generated_at':  datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# Typer competition simulation (herding model, calibrated on Euro 2024)
# ---------------------------------------------------------------------------

_HERDING_RATE = 0.33
_DROPOUT_GS   = 0.08
_DROPOUT_R16  = 0.21
_DROPOUT_KO   = 0.27
_SPECIAL_PTS  = 2


def _modal_score(lam_h: float, lam_a: float, max_g: int = 8):
    from scipy.stats import poisson as sp_poisson
    probs = np.outer(
        sp_poisson.pmf(np.arange(max_g + 1), lam_h),
        sp_poisson.pmf(np.arange(max_g + 1), lam_a),
    )
    idx = np.unravel_index(np.argmax(probs), probs.shape)
    return int(idx[0]), int(idx[1])


def _simulate_match_bets(lam_h: float, lam_a: float, ah: int, aa: int,
                          n_players: int, dropout: float = 0.0,
                          herding_rate: float = _HERDING_RATE) -> np.ndarray:
    """Vectorised: returns points array of length n_players for one match."""
    mh, ma = _modal_score(lam_h, lam_a)
    active   = np.random.random(n_players) >= dropout
    herds    = np.random.random(n_players) < herding_rate
    bet_h    = np.where(herds, mh, np.random.poisson(lam_h, n_players)).astype(int)
    bet_a    = np.where(herds, ma, np.random.poisson(lam_a, n_players)).astype(int)
    exact    = (bet_h == ah) & (bet_a == aa)
    direction = np.sign(bet_h - bet_a) == np.sign(ah - aa)
    pts      = np.where(exact, 3, np.where(direction, 1, 0))
    return np.where(active, pts, 0).astype(float)


def _normed_arr(counter: dict, keys) -> np.ndarray:
    vals = np.array([counter.get(k, 0) for k in keys], dtype=float)
    s = vals.sum()
    return vals / s if s > 0 else np.ones(len(vals)) / len(vals)


def _simulate_special_bets(tournament_data: dict, n_players: int,
                            herding_rate: float = _HERDING_RATE) -> np.ndarray:
    """
    Simulate 9 special questions (2 pts each) using MC tournament distributions.
    PLAYER questions (top scorer/assister/combined) approximated with P(correct)~0.12.
    """
    t = tournament_data
    pts = np.zeros(n_players)

    # Build distributions from tournament counters
    teams_arr = np.array(ALL_TEAMS)
    questions = [
        _normed_arr(t.get('finalist',      {}), ALL_TEAMS),   # Q4 Finalista
        _normed_arr(t.get('most_goals_gs', {}), ALL_TEAMS),   # Q5 Gole GS
        _normed_arr(t.get('first_red_card',{}), ALL_TEAMS),   # Q6 Czerwona
        _normed_arr(t.get('third_advance', {}), ALL_TEAMS),   # Q7 3. miejsce
    ]

    og_keys    = list(range(15))
    draws_keys = list(range(50))
    questions.append(_normed_arr(t.get('own_goals_dist', {}), og_keys))    # Q8
    questions.append(_normed_arr(t.get('draws_dist',     {}), draws_keys)) # Q9

    # TEAM / NUMBER questions — herded simulation
    for probs in questions:
        n_out     = len(probs)
        outcome   = np.random.choice(n_out, p=probs)
        modal     = int(np.argmax(probs))
        is_herder = np.random.random(n_players) < herding_rate
        indep     = np.random.choice(n_out, size=n_players, p=probs)
        bets      = np.where(is_herder, modal, indep)
        pts      += np.where(bets == outcome, _SPECIAL_PTS, 0)

    # PLAYER questions (Q1 krol strzeleow, Q2 asystent, Q3 kanadyjska)
    # Approximation: P(any player correct) ~ 0.12; herder bets on "favourite"
    for _ in range(3):
        p_correct = 0.12
        # herders all pick the same player → correlated outcome
        herder_correct  = float(np.random.random() < p_correct)
        indep_correct   = np.random.random(n_players) < p_correct
        is_herder       = np.random.random(n_players) < herding_rate
        correct         = np.where(is_herder, herder_correct, indep_correct)
        pts            += correct * _SPECIAL_PTS

    return pts


def run_typer_simulation(team_stats: dict,
                          user_scores: dict,
                          tournament_data: dict,
                          n_simulations: int = 5_000) -> dict:
    """
    Simulate the typer league standings at end of tournament.

    Args:
        team_stats:      output of _build_team_stats()  (stored in snapshot)
        user_scores:     {username: current_total_points}
        tournament_data: snapshot['tournament'] dict (MC distributions)
        n_simulations:   number of iterations

    Returns:
        {username: {win, top3, top5, top10}}
    """
    if not user_scores:
        return {}

    usernames   = list(user_scores.keys())
    n_users     = len(usernames)
    base_scores = np.array([user_scores[u] for u in usernames], dtype=float)

    # Pre-compute GS lambdas
    gs_matches = []
    for group_name, teams in GROUPS.items():
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                h, a = teams[i], teams[j]
                lh = max(team_stats[h]['att'] * team_stats[a]['def'], 0.01)
                la = max(team_stats[a]['att'] * team_stats[h]['def'], 0.01)
                gs_matches.append((lh, la))

    avg_lh = float(np.mean([m[0] for m in gs_matches]))
    avg_la = float(np.mean([m[1] for m in gs_matches]))
    ko_dropouts = [_DROPOUT_R16] * 24 + [_DROPOUT_KO] * 8

    # Rank counters: rank_mat[i] = list of ranks user i achieved
    win_count  = np.zeros(n_users, dtype=int)
    top3_count = np.zeros(n_users, dtype=int)
    top5_count = np.zeros(n_users, dtype=int)
    top10_count = np.zeros(n_users, dtype=int)

    logger.info("Running typer simulation (%d users, %d sims)…", n_users, n_simulations)

    for sim in range(n_simulations):
        pts = base_scores.copy()

        for lh, la in gs_matches:
            ah = int(np.random.poisson(lh))
            aa = int(np.random.poisson(la))
            pts += _simulate_match_bets(lh, la, ah, aa, n_users, _DROPOUT_GS)

        for do in ko_dropouts:
            ah = int(np.random.poisson(avg_lh))
            aa = int(np.random.poisson(avg_la))
            pts += _simulate_match_bets(avg_lh, avg_la, ah, aa, n_users, do)

        pts += _simulate_special_bets(tournament_data, n_users)

        # Rank: argsort twice gives dense rank (1 = best)
        order = np.argsort(-pts)
        ranks = np.empty_like(order)
        ranks[order] = np.arange(1, n_users + 1)

        win_count   += (ranks == 1)
        top3_count  += (ranks <= 3)
        top5_count  += (ranks <= 5)
        top10_count += (ranks <= 10)

    logger.info("Typer simulation complete.")

    return {
        usernames[i]: {
            'win':   round(int(win_count[i])   / n_simulations, 4),
            'top3':  round(int(top3_count[i])  / n_simulations, 4),
            'top5':  round(int(top5_count[i])  / n_simulations, 4),
            'top10': round(int(top10_count[i]) / n_simulations, 4),
        }
        for i in range(n_users)
    }
