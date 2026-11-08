"""
environment.py — Football MAS · Match Environment  (v4)
========================================================
Added in v4:
  - Club support: name, colors, speed_bonus passed through configure()
  - Club info stored on MatchEnvironment for API serialisation
  - 8-match validation runner: run_validation_suite()
"""

import random
from typing import List, Optional, Dict, Tuple

from agent import (
    FootballAgent, Role, Action,
    PITCH_W, PITCH_H, GOAL_A, GOAL_B,
    INTERCEPT_R, dist, clamp,
)

# ─────────────────────────────────────────────────────────────────────────────
#  Ball
# ─────────────────────────────────────────────────────────────────────────────
class Ball:
    FRICTION: float = 0.86

    def __init__(self) -> None:
        self.x = PITCH_W / 2;  self.y = PITCH_H / 2
        self.vx = 0.0;          self.vy = 0.0

    def step(self, dt: float, owned: bool) -> None:
        if owned: return
        self.x += self.vx * dt;  self.y += self.vy * dt
        decay = self.FRICTION ** dt
        self.vx *= decay;  self.vy *= decay
        if self.x <= 0 or self.x >= PITCH_W:
            self.vx = -self.vx * 0.55
            self.x  = clamp(self.x, 0.5, PITCH_W - 0.5)
        if self.y <= 0 or self.y >= PITCH_H:
            self.vy = -self.vy * 0.55
            self.y  = clamp(self.y, 0.5, PITCH_H - 0.5)

    def to_dict(self):
        return {"x": round(self.x,2), "y": round(self.y,2),
                "vx": round(self.vx,2), "vy": round(self.vy,2)}


# ─────────────────────────────────────────────────────────────────────────────
#  Formations
# ─────────────────────────────────────────────────────────────────────────────
FORMATIONS: Dict[str, List[Tuple]] = {
    "4-3-3": [
        (Role.GOALKEEPER, 0.04, 0.50),
        (Role.DEFENDER,   0.18, 0.15), (Role.DEFENDER,   0.18, 0.37),
        (Role.DEFENDER,   0.18, 0.63), (Role.DEFENDER,   0.18, 0.85),
        (Role.MIDFIELDER, 0.35, 0.24), (Role.MIDFIELDER, 0.35, 0.50),
        (Role.MIDFIELDER, 0.35, 0.76),
        (Role.STRIKER,    0.64, 0.18), (Role.STRIKER,    0.64, 0.50),
        (Role.STRIKER,    0.64, 0.82),
    ],
    "4-4-2": [
        (Role.GOALKEEPER, 0.04, 0.50),
        (Role.DEFENDER,   0.18, 0.15), (Role.DEFENDER,   0.18, 0.37),
        (Role.DEFENDER,   0.18, 0.63), (Role.DEFENDER,   0.18, 0.85),
        (Role.MIDFIELDER, 0.35, 0.15), (Role.MIDFIELDER, 0.35, 0.37),
        (Role.MIDFIELDER, 0.35, 0.63), (Role.MIDFIELDER, 0.35, 0.85),
        (Role.STRIKER,    0.65, 0.33), (Role.STRIKER,    0.65, 0.67),
    ],
    "3-5-2": [
        (Role.GOALKEEPER, 0.04, 0.50),
        (Role.DEFENDER,   0.18, 0.24), (Role.DEFENDER,   0.18, 0.50),
        (Role.DEFENDER,   0.18, 0.76),
        (Role.MIDFIELDER, 0.32, 0.10), (Role.MIDFIELDER, 0.32, 0.30),
        (Role.MIDFIELDER, 0.32, 0.50), (Role.MIDFIELDER, 0.32, 0.70),
        (Role.MIDFIELDER, 0.32, 0.90),
        (Role.STRIKER,    0.64, 0.33), (Role.STRIKER,    0.64, 0.67),
    ],
    "4-5-1": [
        (Role.GOALKEEPER, 0.04, 0.50),
        (Role.DEFENDER,   0.18, 0.15), (Role.DEFENDER,   0.18, 0.37),
        (Role.DEFENDER,   0.18, 0.63), (Role.DEFENDER,   0.18, 0.85),
        (Role.MIDFIELDER, 0.34, 0.10), (Role.MIDFIELDER, 0.34, 0.30),
        (Role.MIDFIELDER, 0.34, 0.50), (Role.MIDFIELDER, 0.34, 0.70),
        (Role.MIDFIELDER, 0.34, 0.90),
        (Role.STRIKER,    0.65, 0.50),
    ],
    # Bayern's 4-2-3-1 — treated as 4-4-2 variant with deeper mids
    "4-2-3-1": [
        (Role.GOALKEEPER, 0.04, 0.50),
        (Role.DEFENDER,   0.18, 0.15), (Role.DEFENDER,   0.18, 0.37),
        (Role.DEFENDER,   0.18, 0.63), (Role.DEFENDER,   0.18, 0.85),
        (Role.MIDFIELDER, 0.30, 0.30), (Role.MIDFIELDER, 0.30, 0.70),
        (Role.MIDFIELDER, 0.42, 0.15), (Role.MIDFIELDER, 0.42, 0.50),
        (Role.MIDFIELDER, 0.42, 0.85),
        (Role.STRIKER,    0.65, 0.50),
    ],
}


def apply_formation(team, name, speed_base, aggression):
    template = FORMATIONS.get(name, FORMATIONS["4-4-2"])
    agents = []
    for idx, (role, xf, yf) in enumerate(template):
        ax = xf * PITCH_W if team == "A" else (1.0 - xf) * PITCH_W
        ay = yf * PITCH_H
        agents.append(FootballAgent(
            agent_id=f"{team}{idx+1}", team=team, role=role,
            formation_pos=(ax, ay), speed_base=speed_base, aggression=aggression,
        ))
    return agents


# ─────────────────────────────────────────────────────────────────────────────
#  MatchEnvironment
# ─────────────────────────────────────────────────────────────────────────────
class MatchEnvironment:
    DURATION: float = 30.0
    DT:       float = 0.05

    def __init__(self) -> None:
        self.agents:  List[FootballAgent] = []
        self.ball:    Ball = Ball()
        self.running: bool = False
        self.elapsed: float = 0.0
        self.score               = {"A": 0, "B": 0}
        self.stats_passes        = {"A": 0, "B": 0}
        self.stats_interceptions = {"A": 0, "B": 0}
        self.stats_possession    = {"A": 0, "B": 0}
        self._events: List[str] = []
        self._step: int = 0
        # Club info (set by configure)
        self.club_a: dict = {}
        self.club_b: dict = {}

    def configure(
        self,
        formation_a:    str,
        formation_b:    str,
        attacking_team: str,
        aggression_str: str,
        club_a:         dict = None,
        club_b:         dict = None,
    ) -> None:
        agg_map = {"low": 0.22, "medium": 0.55, "high": 0.90}

        # If clubs provided, use their preferred aggression & speed
        if club_a:
            agg_a   = agg_map.get(club_a.get("aggression", aggression_str), 0.55)
            spd_a   = 7.5 + agg_a * 3.0 + club_a.get("speed_bonus", 0.0)
            form_a  = club_a.get("formation", formation_a)
        else:
            agg_a   = agg_map.get(aggression_str, 0.55)
            spd_a   = 7.5 + agg_a * 3.0
            form_a  = formation_a

        if club_b:
            agg_b   = agg_map.get(club_b.get("aggression", aggression_str), 0.55)
            spd_b   = 7.5 + agg_b * 3.0 + club_b.get("speed_bonus", 0.0)
            form_b  = club_b.get("formation", formation_b)
        else:
            agg_b   = agg_map.get(aggression_str, 0.55)
            spd_b   = 7.5 + agg_b * 3.0
            form_b  = formation_b

        self.club_a = club_a or {}
        self.club_b = club_b or {}

        self.agents = (
            apply_formation("A", form_a, spd_a, agg_a) +
            apply_formation("B", form_b, spd_b, agg_b)
        )
        self.ball                = Ball()
        self.score               = {"A": 0, "B": 0}
        self.stats_passes        = {"A": 0, "B": 0}
        self.stats_interceptions = {"A": 0, "B": 0}
        self.stats_possession    = {"A": 0, "B": 0}
        self._events             = []
        self.elapsed             = 0.0
        self._step               = 0
        self.running             = True
        self._kick_off(attacking_team)

    def step(self) -> bool:
        if not self.running: return False
        self.elapsed += self.DT;  self._step += 1
        carrier = self.ball_carrier
        if carrier: self.stats_possession[carrier.team] += 1
        order = list(range(len(self.agents)))
        random.shuffle(order)
        for i in order:
            agent  = self.agents[i]
            obs    = agent.perceive(self)
            action = agent.decide(obs)
            agent.act(action, obs, self, self.DT)
        owned = self.ball_carrier is not None
        self.ball.step(self.DT, owned)
        if not owned: self._auto_pickup()
        if self.elapsed >= self.DURATION:
            self.running = False;  self.log("⏱ Full Time!");  return False
        return True

    @property
    def ball_carrier(self) -> Optional[FootballAgent]:
        return next((a for a in self.agents if a.has_ball), None)

    def transfer_possession(self, new_owner):
        for a in self.agents: a.has_ball = False
        if new_owner:
            new_owner.has_ball = True;  new_owner._possession_ticks = 0
            self.ball.x = new_owner.x;  self.ball.y = new_owner.y
            self.ball.vx = 0.0;          self.ball.vy = 0.0

    def _auto_pickup(self):
        bx, by = self.ball.x, self.ball.y
        nearest, nd = None, float("inf")
        for a in self.agents:
            d = dist(a.pos, (bx, by))
            if d < nd: nearest, nd = a, d
        if nearest and nd < INTERCEPT_R * 1.8:
            self.transfer_possession(nearest)

    def reset_after_goal(self):
        for a in self.agents:
            a.x, a.y = a.formation_pos;  a.vx = a.vy = 0.0
            a.has_ball = False;           a._possession_ticks = 0
        self.ball = Ball()
        conceding = "A" if self.score["B"] > self.score["A"] else "B"
        self._kick_off(conceding)

    def _kick_off(self, team):
        mids = [a for a in self.agents if a.team == team and a.role == Role.MIDFIELDER]
        if not mids: mids = [a for a in self.agents if a.team == team]
        centre = (PITCH_W / 2, PITCH_H / 2)
        chosen = min(mids, key=lambda a: dist(a.pos, centre))
        self.transfer_possession(chosen)

    def log(self, msg):
        self._events.append(msg)
        if len(self._events) > 30: self._events.pop(0)

    def to_state_dict(self):
        total    = max(1, sum(self.stats_possession.values()))
        poss_pct = {t: round(100 * v / total) for t, v in self.stats_possession.items()}
        shots_a  = sum(a.stat_shots for a in self.agents if a.team == "A")
        shots_b  = sum(a.stat_shots for a in self.agents if a.team == "B")
        return {
            "running":        self.running,
            "elapsed":        round(self.elapsed, 2),
            "time_remaining": round(max(0.0, self.DURATION - self.elapsed), 2),
            "score":          dict(self.score),
            "ball":           self.ball.to_dict(),
            "agents":         [a.to_dict() for a in self.agents],
            "club_a":         self.club_a,
            "club_b":         self.club_b,
            "stats": {
                "passes":         dict(self.stats_passes),
                "interceptions":  dict(self.stats_interceptions),
                "possession_pct": poss_pct,
                "shots":          {"A": shots_a, "B": shots_b},
            },
            "events": list(self._events[-8:]),
        }

    def get_final_summary(self):
        state    = self.to_state_dict()
        shots_a  = state["stats"]["shots"]["A"]
        shots_b  = state["stats"]["shots"]["B"]
        poss     = state["stats"]["possession_pct"]
        dominant = "A" if poss.get("A", 0) >= poss.get("B", 0) else "B"
        winner   = ("A" if self.score["A"] > self.score["B"] else
                    "B" if self.score["B"] > self.score["A"] else "Draw")
        state["summary"] = {
            "winner":   winner,
            "dominant": dominant,
            "shots":    {"A": shots_a, "B": shots_b},
            "notes":    self._notes(shots_a, shots_b),
        }
        return state

    def _notes(self, sa, sb):
        n = []
        name_a = self.club_a.get("name", "Team A")
        name_b = self.club_b.get("name", "Team B")
        if sa > sb * 1.4:   n.append(f"{name_a} created significantly more chances.")
        elif sb > sa * 1.4: n.append(f"{name_b} generated the better opportunities.")
        else:               n.append("Both teams produced an evenly matched attacking threat.")
        ia = self.stats_interceptions["A"];  ib = self.stats_interceptions["B"]
        if ia > ib:   n.append(f"{name_a}'s defensive block was decisive.")
        elif ib > ia: n.append(f"{name_b}'s compactness limited the opposition.")
        pa = self.stats_passes["A"];  pb = self.stats_passes["B"]
        if pa > 20: n.append(f"{name_a} circulated the ball with composure.")
        if pb > 20: n.append(f"{name_b} maintained disciplined passing sequences.")
        return " ".join(n) or "A tightly contested encounter."


# ─────────────────────────────────────────────────────────────────────────────
#  8-Match Validation Suite
# ─────────────────────────────────────────────────────────────────────────────
def run_validation_suite(club_a: dict, club_b: dict, seed: Optional[int] = None) -> dict:
    """
    Run 8 automated full matches between two clubs.
    Alternates kick-off team each match and cycles through the aggression levels
    (the level of each match replaces the clubs' usual style for that match).
    Returns aggregated statistics and per-match breakdown.
    Pass a seed to get the same 8 matches every time (useful for tests and comparisons).
    """
    if seed is not None:
        random.seed(seed)
    configs = [
        ("A", "high"),   ("B", "high"),
        ("A", "medium"), ("B", "medium"),
        ("A", "low"),    ("B", "low"),
        ("A", "high"),   ("B", "medium"),
    ]
    results = []
    totals  = {
        "goals_a": 0, "goals_b": 0,
        "shots_a": 0, "shots_b": 0,
        "passes_a": 0, "passes_b": 0,
        "poss_a": 0,  "poss_b": 0,
        "wins_a": 0,  "wins_b": 0, "draws": 0,
    }

    for i, (kick_off, agg) in enumerate(configs):
        env = MatchEnvironment()
        env.configure(
            formation_a    = club_a.get("formation", "4-4-2"),
            formation_b    = club_b.get("formation", "4-4-2"),
            attacking_team = kick_off,
            aggression_str = agg,
            club_a         = {**club_a, "aggression": agg},
            club_b         = {**club_b, "aggression": agg},
        )
        while env.step():
            pass
        fin = env.get_final_summary()

        ga, gb  = fin["score"]["A"], fin["score"]["B"]
        sa, sb  = fin["summary"]["shots"]["A"], fin["summary"]["shots"]["B"]
        pa, pb  = fin["stats"]["passes"]["A"], fin["stats"]["passes"]["B"]
        pca     = fin["stats"]["possession_pct"].get("A", 50)
        pcb     = fin["stats"]["possession_pct"].get("B", 50)
        winner  = fin["summary"]["winner"]

        results.append({
            "match":      i + 1,
            "kick_off":   kick_off,
            "aggression": agg,
            "score_a":    ga,
            "score_b":    gb,
            "shots_a":    sa,
            "shots_b":    sb,
            "passes_a":   pa,
            "passes_b":   pb,
            "poss_a":     pca,
            "poss_b":     pcb,
            "winner":     winner,
        })

        totals["goals_a"]  += ga;   totals["goals_b"]  += gb
        totals["shots_a"]  += sa;   totals["shots_b"]  += sb
        totals["passes_a"] += pa;   totals["passes_b"] += pb
        totals["poss_a"]   += pca;  totals["poss_b"]   += pcb
        if winner == "A":    totals["wins_a"] += 1
        elif winner == "B":  totals["wins_b"] += 1
        else:                totals["draws"]  += 1

    n = len(results)
    overall_winner = (
        club_a.get("name", "Team A") if totals["wins_a"] > totals["wins_b"] else
        club_b.get("name", "Team B") if totals["wins_b"] > totals["wins_a"] else
        "Draw"
    )

    return {
        "club_a":          club_a,
        "club_b":          club_b,
        "matches":         results,
        "totals":          totals,
        "averages": {
            "goals_a":  round(totals["goals_a"]  / n, 1),
            "goals_b":  round(totals["goals_b"]  / n, 1),
            "shots_a":  round(totals["shots_a"]  / n, 1),
            "shots_b":  round(totals["shots_b"]  / n, 1),
            "passes_a": round(totals["passes_a"] / n, 1),
            "passes_b": round(totals["passes_b"] / n, 1),
            "poss_a":   round(totals["poss_a"]   / n, 1),
            "poss_b":   round(totals["poss_b"]   / n, 1),
        },
        "overall_winner": overall_winner,
        "record": {
            "wins_a": totals["wins_a"],
            "wins_b": totals["wins_b"],
            "draws":  totals["draws"],
        },
    }
