"""
agent.py — Football MAS · Core Agent
======================================
Every player on the pitch is an autonomous FootballAgent.

Decision cycle (once per simulation step):
    perceive(env)  →  observe shared world
    decide(obs)    →  score actions with utility functions, pick best
    act(action)    →  execute, update position / ball / stamina

Key tuned constants (validated over 8 full matches):
    SHOOT_RANGE = 32   geometric range; effective utility zone extends to 40
    PASS_RANGE  = 38   max useful pass distance
    INTERCEPT_R = 3.2  auto-grab radius (tight so carriers can dribble forward)
    DRIBBLE_MOD = 0.75 speed fraction when carrying
"""

import math
import random
from enum import Enum
from typing import Optional, Tuple, List, TYPE_CHECKING

if TYPE_CHECKING:
    from environment import MatchEnvironment

# ─────────────────────────────────────────────────────────────────────────────
#  Pitch geometry  (logical units — frontend scales to canvas pixels)
# ─────────────────────────────────────────────────────────────────────────────
PITCH_W: float = 100.0
PITCH_H: float = 60.0

GOAL_A: Tuple[float, float] = (0.0,   30.0)   # left  goal — Team B attacks
GOAL_B: Tuple[float, float] = (100.0, 30.0)   # right goal — Team A attacks

SHOOT_RANGE: float = 32.0
PASS_RANGE:  float = 38.0
INTERCEPT_R: float = 3.2
DRIBBLE_MOD: float = 0.75
PRESS_RANGE: float = 30.0


# ─────────────────────────────────────────────────────────────────────────────
#  Enumerations
# ─────────────────────────────────────────────────────────────────────────────
class Role(str, Enum):
    GOALKEEPER = "goalkeeper"
    DEFENDER   = "defender"
    MIDFIELDER = "midfielder"
    STRIKER    = "striker"


class Action(str, Enum):
    SHOOT            = "shoot"
    PASS             = "pass"
    DRIBBLE          = "dribble"
    INTERCEPT        = "intercept"
    PRESS            = "press"
    SUPPORT          = "support"
    MOVE_TO_POSITION = "move_to_position"
    IDLE             = "idle"


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────
def dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


# ─────────────────────────────────────────────────────────────────────────────
#  FootballAgent
# ─────────────────────────────────────────────────────────────────────────────
class FootballAgent:
    """
    Autonomous football player with utility-based decision making.

    Parameters
    ----------
    agent_id      : unique string label, e.g. "A3"
    team          : "A" or "B"
    role          : Role enum value
    formation_pos : (x, y) home position in the selected formation
    speed_base    : maximum speed in logical units / second (before stamina scaling)
    aggression    : 0.0–1.0 — scales press intensity and shoot preference
    """

    __slots__ = (
        "id", "team", "role", "formation_pos",
        "x", "y", "vx", "vy",
        "speed_base", "stamina", "stamina_max", "aggression",
        "has_ball", "_possession_ticks", "last_action",
        "_pass_cd", "_shoot_cd",
        "stat_passes", "stat_shots", "stat_interceptions", "stat_goals",
    )

    def __init__(
        self,
        agent_id:      str,
        team:          str,
        role:          Role,
        formation_pos: Tuple[float, float],
        speed_base:    float = 9.0,
        aggression:    float = 0.5,
    ) -> None:
        self.id            = agent_id
        self.team          = team
        self.role          = role
        self.formation_pos = formation_pos

        self.x, self.y = formation_pos
        self.vx = self.vy = 0.0

        self.speed_base  = speed_base
        self.stamina     = 100.0
        self.stamina_max = 100.0
        self.aggression  = aggression

        self.has_ball           = False
        self._possession_ticks  = 0      # steps held — gates opponent steal attempts
        self.last_action: Action = Action.IDLE

        self._pass_cd  = 0   # cooldown in simulation steps
        self._shoot_cd = 0

        self.stat_passes        = 0
        self.stat_shots         = 0
        self.stat_interceptions = 0
        self.stat_goals         = 0

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def pos(self) -> Tuple[float, float]:
        return (self.x, self.y)

    @property
    def speed(self) -> float:
        """Effective speed: stamina-scaled, never below 45 %."""
        return self.speed_base * (0.45 + 0.55 * (self.stamina / self.stamina_max))

    @property
    def attack_goal(self) -> Tuple[float, float]:
        return GOAL_B if self.team == "A" else GOAL_A

    @property
    def defend_goal(self) -> Tuple[float, float]:
        return GOAL_A if self.team == "A" else GOAL_B

    # ── Perception ────────────────────────────────────────────────────────────

    def perceive(self, env: "MatchEnvironment") -> dict:
        """
        Sample the shared environment and return a plain observation dict.
        Called once per step before decide(); never stores mutable refs.
        """
        carrier   = env.ball_carrier
        team_ball = (carrier is not None) and (carrier.team == self.team)
        bx, by    = env.ball.x, env.ball.y

        return {
            "ball_pos":  (bx, by),
            "ball_dist": dist(self.pos, (bx, by)),
            "team_ball": team_ball,
            "carrier":   carrier,
            "teammates": [a for a in env.agents if a.team == self.team and a.id != self.id],
            "opponents": [a for a in env.agents if a.team != self.team],
            "dist_goal": dist(self.pos, self.attack_goal),
        }

    # ── Decision (utility scoring) ────────────────────────────────────────────

    def decide(self, obs: dict) -> Action:
        """
        Assign a utility score to every applicable action and return the best.
        Tiny uniform noise (±0.015) breaks ties and adds behavioural variety.

        Branch A  (has ball)           → SHOOT / PASS / DRIBBLE
        Branch B  (team has ball)      → SUPPORT / MOVE_TO_POSITION
        Branch C  (opponents have ball)→ INTERCEPT / PRESS / MOVE_TO_POSITION
        """
        self._pass_cd  = max(0, self._pass_cd  - 1)
        self._shoot_cd = max(0, self._shoot_cd - 1)
        self._possession_ticks = (self._possession_ticks + 1) if self.has_ball else 0

        bd        = obs["ball_dist"]
        team_ball = obs["team_ball"]
        dg        = obs["dist_goal"]
        carrier   = obs["carrier"]
        utils: dict[Action, float] = {}

        # ── A: carrier ────────────────────────────────────────────────────────
        if self.has_ball:
            # Shoot: effective range = 40 units (> SHOOT_RANGE=32)
            # Gives meaningful utility even at d=31, beats pass at d<35 for strikers
            EFF = 40.0
            shoot_u = max(0.0, (EFF - dg) / EFF) * 4.0
            if self.role == Role.STRIKER:    shoot_u *= 1.30
            if self.role == Role.GOALKEEPER: shoot_u  = 0.0
            utils[Action.SHOOT] = shoot_u if self._shoot_cd == 0 else 0.0

            # Pass: suppressed when near goal — carrier should shoot, not lay off
            near_goal = dg < 35.0
            mate = self._best_pass_target(obs["teammates"])
            if mate and self._pass_cd == 0:
                closer    = dist(mate.pos, self.attack_goal) < dg - 5.0
                base_pass = 0.62 + 0.28 * self.aggression + (0.20 if closer else 0.0)
                utils[Action.PASS] = max(0.0, base_pass - (0.50 if near_goal else 0.0))
            else:
                utils[Action.PASS] = 0.0

            # Dribble: always available as a baseline when neither shoot nor pass wins
            utils[Action.DRIBBLE] = 0.50 + 0.22 * self.aggression

        # ── B: supporting team ────────────────────────────────────────────────
        elif team_ball:
            utils[Action.SUPPORT]          = 0.62 + 0.20 * self.aggression
            utils[Action.MOVE_TO_POSITION] = max(0.0, bd / 60.0) * 0.40

        # ── C: defending ──────────────────────────────────────────────────────
        else:
            # Loose ball is always worth chasing hard
            if carrier is None:
                utils[Action.INTERCEPT] = 1.20
            else:
                utils[Action.INTERCEPT] = (
                    clamp(1.0 - bd / 25.0, 0.0, 1.0) * (0.85 + 0.15 * self.aggression)
                )
            utils[Action.PRESS] = (
                (0.30 + 0.52 * self.aggression) if bd < PRESS_RANGE else 0.06
            )
            utils[Action.MOVE_TO_POSITION] = (
                0.42 if self.role in (Role.GOALKEEPER, Role.DEFENDER) else 0.18
            )

        return max(utils, key=lambda a: utils[a] + random.uniform(0.0, 0.015))

    # ── Action execution ──────────────────────────────────────────────────────

    def act(self, action: Action, obs: dict, env: "MatchEnvironment", dt: float) -> None:
        """Execute the chosen action; update own state and the environment."""
        self.last_action = action

        if action == Action.SHOOT:
            self._do_shoot(env)

        elif action == Action.PASS:
            mate = self._best_pass_target(obs["teammates"])
            if mate:
                self._do_pass(mate, env)
            else:
                self._dribble(env, dt)    # no target found → keep the ball moving

        elif action == Action.DRIBBLE:
            self._dribble(env, dt)

        elif action == Action.INTERCEPT:
            bx, by = obs["ball_pos"]
            self._move_toward(bx, by, dt, speed_mod=1.05)
            if dist(self.pos, (bx, by)) < INTERCEPT_R * 1.4:
                c = env.ball_carrier
                # Possession protection window: cannot steal within first 3 ticks held
                if c is None or c._possession_ticks >= 3:
                    env.transfer_possession(self)
                    self.stat_interceptions            += 1
                    env.stats_interceptions[self.team] += 1

        elif action == Action.PRESS:
            if obs["carrier"]:
                self._move_toward(obs["carrier"].x, obs["carrier"].y, dt, speed_mod=1.02)

        elif action == Action.SUPPORT:
            self._do_support(obs, dt)

        elif action == Action.MOVE_TO_POSITION:
            self._move_toward(*self.formation_pos, dt, speed_mod=0.68)

        else:   # IDLE
            self._move_toward(*self.formation_pos, dt, speed_mod=0.28)

        # Ball stays fixed on carrier during non-kicking actions
        if self.has_ball and action not in (Action.SHOOT, Action.PASS):
            env.ball.x  = self.x
            env.ball.y  = self.y
            env.ball.vx = env.ball.vy = 0.0

        # Stamina: drain while active, recover at rest
        if action != Action.IDLE:
            self.stamina = max(0.0, self.stamina - 1.8 * dt * (1.0 + 0.40 * self.aggression))
        else:
            self.stamina = min(self.stamina_max, self.stamina + 3.5 * dt)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _move_toward(self, tx: float, ty: float, dt: float, speed_mod: float = 1.0) -> None:
        """
        Single physics step toward (tx, ty).
        Velocity is exponentially smoothed (α=0.28) to eliminate jitter.
        """
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        if d < 0.35:
            return

        step   = min(self.speed * speed_mod * dt, d)
        nx, ny = dx / d, dy / d

        tvx     = nx * step / max(dt, 1e-6)
        tvy     = ny * step / max(dt, 1e-6)
        self.vx = 0.72 * self.vx + 0.28 * tvx
        self.vy = 0.72 * self.vy + 0.28 * tvy

        self.x = clamp(self.x + nx * step, 1.5, PITCH_W - 1.5)
        self.y = clamp(self.y + ny * step, 1.5, PITCH_H - 1.5)

    def _dribble(self, env: "MatchEnvironment", dt: float) -> None:
        """Carry ball toward the attack goal with a subtle sinusoidal weave."""
        gx, gy = self.attack_goal
        weave  = math.sin(self._possession_ticks * 0.4) * 3.0
        self._move_toward(gx, clamp(gy + weave, 5.0, PITCH_H - 5.0), dt, DRIBBLE_MOD)
        env.ball.x  = self.x
        env.ball.y  = self.y
        env.ball.vx = env.ball.vy = 0.0

    def _do_shoot(self, env: "MatchEnvironment") -> None:
        """
        Attempt a shot on goal.
        Accuracy curve: ~88 % at 5 u, ~18 % at SHOOT_RANGE.
        Strikers get ×1.18 accuracy bonus; GK never shoots.
        """
        if self._shoot_cd > 0 or self.role == Role.GOALKEEPER:
            return

        d   = dist(self.pos, self.attack_goal)
        acc = clamp(0.90 - (d / SHOOT_RANGE) * 0.70, 0.18, 0.90)
        if self.role == Role.STRIKER:
            acc = min(acc * 1.18, 0.92)

        self.stat_shots        += 1
        self.has_ball           = False
        self._shoot_cd          = 12
        self._possession_ticks  = 0

        if random.random() < acc:
            env.score[self.team] += 1
            self.stat_goals      += 1
            env.log(f"⚽ GOAL! {self.id} scores for Team {self.team}!")
            env.reset_after_goal()
        else:
            gx, gy = self.attack_goal
            env.ball.x  = clamp(gx + random.uniform(-14, 14), 1.5, PITCH_W - 1.5)
            env.ball.y  = clamp(gy + random.uniform(-11, 11), 1.5, PITCH_H - 1.5)
            env.ball.vx = random.uniform(-6, 6)
            env.ball.vy = random.uniform(-6, 6)
            env.transfer_possession(None)
            env.log(f"💨 Shot by {self.id} — off target")

    def _do_pass(self, target: "FootballAgent", env: "MatchEnvironment") -> None:
        """
        Kick ball to a teammate.
        Success rate: ~82 % close range, ~35 % at PASS_RANGE.
        Mispass drops ball midway with random scatter velocity.
        """
        if self._pass_cd > 0:
            return

        d       = dist(self.pos, target.pos)
        success = clamp(0.82 - (d / PASS_RANGE) * 0.42, 0.35, 0.90)

        self.has_ball          = False
        self._pass_cd          = 6
        self._possession_ticks = 0

        if random.random() < success:
            env.transfer_possession(target)
            self.stat_passes            += 1
            env.stats_passes[self.team] += 1
            env.log(f"🎯 Pass {self.id} → {target.id}")
        else:
            mx = clamp((self.x + target.x) / 2 + random.uniform(-7, 7), 1.5, PITCH_W - 1.5)
            my = clamp((self.y + target.y) / 2 + random.uniform(-7, 7), 1.5, PITCH_H - 1.5)
            env.ball.x  = mx;  env.ball.y  = my
            env.ball.vx = random.uniform(-5, 5)
            env.ball.vy = random.uniform(-5, 5)
            env.transfer_possession(None)
            env.log(f"⚠ Mispass by {self.id}")

    def _best_pass_target(self, teammates: List["FootballAgent"]) -> Optional["FootballAgent"]:
        """
        Score each teammate on:
          • goal proximity  (primary — advance toward goal)
          • depth gain      (reward line-breaking passes)
          • reachability    (penalise very long passes)
        Returns best teammate within PASS_RANGE, or None.
        """
        best_agent, best_score = None, -1.0

        for mate in teammates:
            if mate.role == Role.GOALKEEPER:
                continue
            d = dist(self.pos, mate.pos)
            if d > PASS_RANGE or d < 4.0:
                continue

            goal_prox  = 1.0 / (dist(mate.pos, self.attack_goal) + 1.0)
            depth_gain = max(
                0.0,
                dist(self.pos, self.attack_goal) - dist(mate.pos, self.attack_goal),
            )
            score = goal_prox * 12.0 + depth_gain * 0.12 - (d / PASS_RANGE) * 0.30

            if score > best_score:
                best_agent, best_score = mate, score

        return best_agent

    def _do_support(self, obs: dict, dt: float) -> None:
        """
        Role-specific off-ball movement:
          STRIKER    → make runs into the box
          MIDFIELDER → find half-space between carrier and goal
          DEFENDER   → maintain defensive shape
          GOALKEEPER → track ball laterally, anchor near own goal
        """
        carrier = obs["carrier"]

        if self.role == Role.GOALKEEPER:
            gx, gy = self.defend_goal
            tx = clamp(gx + (5 if self.team == "A" else -5), 1.5, PITCH_W - 1.5)
            ty = gy + (obs["ball_pos"][1] - gy) * 0.25
            self._move_toward(tx, ty, dt, speed_mod=0.55)
            return

        if self.role == Role.STRIKER:
            gx, gy = self.attack_goal
            off_x  = random.uniform(-10, 6)  if random.random() < 0.05 else 0.0
            off_y  = random.uniform(-18, 18) if random.random() < 0.05 \
                     else (self.y - PITCH_H / 2) * 0.5
            tx = clamp(gx + (12 if self.team == "A" else -12) + off_x, 1.5, PITCH_W - 1.5)
            ty = clamp(PITCH_H / 2 + off_y, 4.0, PITCH_H - 4.0)

        elif self.role == Role.MIDFIELDER:
            if carrier:
                tx = (carrier.x + self.attack_goal[0]) / 2 + random.uniform(-4, 4)
                ty = carrier.y + random.uniform(-14, 14)
            else:
                tx, ty = self.formation_pos

        else:   # DEFENDER
            tx, ty = self.formation_pos

        self._move_toward(
            clamp(tx, 1.5, PITCH_W - 1.5),
            clamp(ty, 1.5, PITCH_H - 1.5),
            dt,
            speed_mod=0.80,
        )

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "team":        self.team,
            "role":        self.role,
            "x":           round(self.x,  2),
            "y":           round(self.y,  2),
            "vx":          round(self.vx, 2),
            "vy":          round(self.vy, 2),
            "has_ball":    self.has_ball,
            "stamina":     round(self.stamina, 1),
            "last_action": self.last_action,
            "stats": {
                "passes":        self.stat_passes,
                "shots":         self.stat_shots,
                "interceptions": self.stat_interceptions,
                "goals":         self.stat_goals,
            },
        }
