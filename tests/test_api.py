"""The HTTP API, called the way the front end calls it."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_home_serves_the_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "FOOTBALL MAS" in response.text.upper()


def test_clubs_hide_internal_ratings():
    clubs = client.get("/clubs").json()["clubs"]
    assert len(clubs) == 8
    assert all("speed_bonus" not in c for c in clubs)


def test_start_then_state_then_reset():
    started = client.post("/start", json={"clubA": "psg", "clubB": "bayern"})
    assert started.status_code == 200
    state = client.get("/state").json()
    assert len(state["agents"]) == 22
    assert state["club_a"]["name"] == "PSG"
    assert client.post("/reset").json() == {"status": "reset"}


def test_unknown_club_is_rejected():
    assert client.post("/start", json={"clubA": "nowhere_fc"}).status_code == 400


def test_validate_returns_eight_matches():
    result = client.post("/validate", json={"clubA": "juventus", "clubB": "man_city"}).json()
    assert len(result["matches"]) == 8
