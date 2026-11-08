"""Whole matches: the simulation ends, stays on the pitch and keeps consistent statistics."""

from agent import PITCH_H, PITCH_W
from clubs import CLUBS
from environment import MatchEnvironment, run_validation_suite


def test_match_runs_to_full_time_with_22_players():
    env = MatchEnvironment()
    env.configure("4-3-3", "4-4-2", "A", "high")
    assert len(env.agents) == 22
    steps = 0
    while env.step():
        steps += 1
        assert 0 <= env.ball.x <= PITCH_W and 0 <= env.ball.y <= PITCH_H
    assert steps == round(env.DURATION / env.DT) - 1
    assert not env.running


def test_at_most_one_player_has_the_ball():
    env = MatchEnvironment()
    env.configure("4-3-3", "4-3-3", "B", "medium")
    while env.step():
        assert sum(a.has_ball for a in env.agents) <= 1


def test_every_formation_has_eleven_players():
    for formation in ("4-3-3", "4-4-2", "3-5-2", "4-5-1", "4-2-3-1"):
        env = MatchEnvironment()
        env.configure(formation, formation, "A", "low")
        assert sum(a.team == "A" for a in env.agents) == 11


def test_validation_suite_is_consistent_and_reproducible():
    a, b = dict(CLUBS["real_madrid"]), dict(CLUBS["liverpool"])
    first = run_validation_suite(a, b, seed=7)
    second = run_validation_suite(a, b, seed=7)
    assert first["matches"] == second["matches"]
    assert len(first["matches"]) == 8
    record = first["record"]
    assert record["wins_a"] + record["wins_b"] + record["draws"] == 8
    assert first["totals"]["goals_a"] == sum(m["score_a"] for m in first["matches"])
    # each match is played at the aggression level it reports
    assert [m["aggression"] for m in first["matches"]][:2] == ["high", "high"]
