"""The decision rules of a single agent, checked in situations where the right choice is clear."""

from agent import GOAL_B, Action, FootballAgent, Role, dist
from environment import MatchEnvironment


def make_env(formation="4-3-3"):
    env = MatchEnvironment()
    env.configure(formation, formation, "A", "medium")
    return env


def test_dist_is_euclidean():
    assert dist((0, 0), (3, 4)) == 5


def test_striker_in_front_of_goal_shoots():
    env = make_env()
    striker = next(a for a in env.agents if a.team == "A" and a.role == Role.STRIKER)
    striker.x, striker.y = GOAL_B[0] - 8, GOAL_B[1]
    env.transfer_possession(striker)
    assert striker.decide(striker.perceive(env)) == Action.SHOOT


def test_goalkeeper_never_shoots():
    env = make_env()
    keeper = next(a for a in env.agents if a.team == "A" and a.role == Role.GOALKEEPER)
    keeper.x, keeper.y = GOAL_B[0] - 5, GOAL_B[1]
    env.transfer_possession(keeper)
    for _ in range(20):
        assert keeper.decide(keeper.perceive(env)) != Action.SHOOT


def test_defenders_chase_a_loose_ball_nearby():
    env = make_env()
    for agent in env.agents:
        agent.has_ball = False
    defender = next(a for a in env.agents if a.team == "B" and a.role == Role.DEFENDER)
    env.ball.x, env.ball.y = defender.x + 2, defender.y
    assert defender.decide(defender.perceive(env)) == Action.INTERCEPT


def test_stamina_drains_when_running():
    agent = FootballAgent("A1", "A", Role.MIDFIELDER, (50.0, 30.0))
    env = make_env()
    obs = agent.perceive(env)
    agent.act(Action.PRESS, obs, env, 1.0)
    assert agent.stamina < 100
