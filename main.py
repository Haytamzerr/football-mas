"""
main.py — Football MAS · FastAPI Server  (v4)
==============================================
New in v4:
  GET  /               — the simulator page (index.html)
  GET  /clubs          — list all available clubs
  POST /start          — now accepts optional clubA / clubB club IDs
  POST /validate       — run 8-match validation suite (blocking, ~8s)
"""

import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional

from environment import MatchEnvironment, run_validation_suite
from clubs import CLUBS, CLUBS_LIST

app = FastAPI(title="Football MAS Simulator", version="4.0.0", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ── Shared state ─────────────────────────────────────────────────────────────
env        = MatchEnvironment()
lock       = threading.Lock()
sim_thread: threading.Thread | None = None

VALID_FORMATIONS = {"4-3-3", "4-4-2", "3-5-2", "4-5-1", "4-2-3-1"}
VALID_AGGRESSION = {"low", "medium", "high"}

_EMPTY_STATE = {
    "running": False, "elapsed": 0.0, "time_remaining": 30.0,
    "score": {"A": 0, "B": 0},
    "ball":  {"x": 50.0, "y": 30.0, "vx": 0.0, "vy": 0.0},
    "agents": [], "club_a": {}, "club_b": {},
    "stats": {
        "passes": {"A": 0, "B": 0}, "interceptions": {"A": 0, "B": 0},
        "possession_pct": {"A": 50, "B": 50}, "shots": {"A": 0, "B": 0},
    },
    "events": ["Select clubs and press START."],
}


# ── Schemas ───────────────────────────────────────────────────────────────────
class StartRequest(BaseModel):
    formationA: str = Field(default="4-3-3")
    formationB: str = Field(default="4-4-2")
    attackTeam: str = Field(default="A")
    aggression: str = Field(default="medium")
    clubA: Optional[str] = Field(default=None, description="Club ID from /clubs")
    clubB: Optional[str] = Field(default=None, description="Club ID from /clubs")


class ValidateRequest(BaseModel):
    clubA: str = Field(description="Club ID for Team A")
    clubB: str = Field(description="Club ID for Team B")


# ── Simulation loop ───────────────────────────────────────────────────────────
def _sim_loop(environment: MatchEnvironment):
    step_s = environment.DT
    while True:
        t0 = time.perf_counter()
        with lock:
            alive = environment.step()
        if not alive: break
        wait = step_s - (time.perf_counter() - t0)
        if wait > 0: time.sleep(wait)


# ── Endpoints ─────────────────────────────────────────────────────────────────
INDEX = Path(__file__).with_name("index.html")


@app.get("/", include_in_schema=False)
async def home():
    """The simulator page, served by the same server so one command runs everything."""
    return FileResponse(INDEX)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "online", "service": "Football MAS Simulator v4"}


@app.get("/clubs", tags=["clubs"])
async def get_clubs():
    """Return all available clubs for the frontend dropdowns."""
    return {"clubs": CLUBS_LIST}


@app.post("/start", tags=["simulation"])
async def start(req: StartRequest):
    global sim_thread

    # Resolve clubs
    club_a_data = None
    club_b_data = None
    if req.clubA:
        if req.clubA not in CLUBS:
            raise HTTPException(400, f"Unknown clubA '{req.clubA}'")
        club_a_data = dict(CLUBS[req.clubA])
    if req.clubB:
        if req.clubB not in CLUBS:
            raise HTTPException(400, f"Unknown clubB '{req.clubB}'")
        club_b_data = dict(CLUBS[req.clubB])

    # Validate manual overrides
    if req.attackTeam not in ("A", "B"):
        raise HTTPException(400, "attackTeam must be 'A' or 'B'")
    if req.aggression not in VALID_AGGRESSION:
        raise HTTPException(400, f"aggression must be one of {sorted(VALID_AGGRESSION)}")

    # Stop previous sim
    with lock: env.running = False
    if sim_thread and sim_thread.is_alive():
        sim_thread.join(timeout=2.0)

    with lock:
        env.configure(
            formation_a    = req.formationA,
            formation_b    = req.formationB,
            attacking_team = req.attackTeam,
            aggression_str = req.aggression,
            club_a         = club_a_data,
            club_b         = club_b_data,
        )
        initial = env.to_state_dict()

    sim_thread = threading.Thread(target=_sim_loop, args=(env,), daemon=True, name="SimThread")
    sim_thread.start()
    return {"status": "started", "state": initial}


@app.get("/state", tags=["simulation"])
async def state():
    with lock:
        if not env.agents: return _EMPTY_STATE
        if not env.running: return env.get_final_summary()
        return env.to_state_dict()


@app.post("/reset", tags=["simulation"])
async def reset():
    global sim_thread
    with lock: env.running = False
    if sim_thread and sim_thread.is_alive():
        sim_thread.join(timeout=2.0)
    with lock: env.__init__()
    return {"status": "reset"}


@app.post("/validate", tags=["validation"])
async def validate(req: ValidateRequest):
    """
    Run 8 automated full matches between two clubs.
    Blocking call — takes ~8 seconds. Returns complete stats breakdown.
    """
    if req.clubA not in CLUBS:
        raise HTTPException(400, f"Unknown clubA '{req.clubA}'")
    if req.clubB not in CLUBS:
        raise HTTPException(400, f"Unknown clubB '{req.clubB}'")

    # Stop any live match first
    with lock: env.running = False
    if sim_thread and sim_thread.is_alive():
        sim_thread.join(timeout=2.0)

    club_a = dict(CLUBS[req.clubA])
    club_b = dict(CLUBS[req.clubB])
    result = run_validation_suite(club_a, club_b)
    return result


if __name__ == "__main__":
    print("\n  Football MAS is running: open http://localhost:8000 in your browser\n")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, log_level="info")
