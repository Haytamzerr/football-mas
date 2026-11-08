"""
clubs.py — Club definitions for Football MAS
Each club has: name, short name, primary/secondary colors, 
preferred formation, aggression style, and speed rating.
"""

CLUBS = {
    "real_madrid": {
        "name":        "Real Madrid",
        "short":       "RMA",
        "color_a":     "FFFFFF",   # white kit
        "color_b":     "FFD700",   # gold accent
        "formation":   "4-3-3",
        "aggression":  "high",
        "speed_bonus": 0.5,        # bonus added to base speed
        "badge":       "👑",
    },
    "barcelona": {
        "name":        "FC Barcelona",
        "short":       "BAR",
        "color_a":     "A50044",   # deep red
        "color_b":     "004D98",   # blue
        "formation":   "4-3-3",
        "aggression":  "high",
        "speed_bonus": 0.3,
        "badge":       "🔵🔴",
    },
    "man_united": {
        "name":        "Man United",
        "short":       "MUN",
        "color_a":     "DA291C",   # red
        "color_b":     "FFE500",   # gold
        "formation":   "4-4-2",
        "aggression":  "medium",
        "speed_bonus": 0.0,
        "badge":       "🔴",
    },
    "man_city": {
        "name":        "Man City",
        "short":       "MCI",
        "color_a":     "6CABDD",   # sky blue
        "color_b":     "1C2C5B",   # navy
        "formation":   "4-3-3",
        "aggression":  "high",
        "speed_bonus": 0.4,
        "badge":       "🔵",
    },
    "liverpool": {
        "name":        "Liverpool",
        "short":       "LIV",
        "color_a":     "C8102E",   # red
        "color_b":     "00B2A9",   # teal
        "formation":   "4-3-3",
        "aggression":  "high",
        "speed_bonus": 0.6,
        "badge":       "🦅",
    },
    "juventus": {
        "name":        "Juventus",
        "short":       "JUV",
        "color_a":     "000000",   # black
        "color_b":     "FFFFFF",   # white
        "formation":   "4-4-2",
        "aggression":  "medium",
        "speed_bonus": -0.2,
        "badge":       "⚫",
    },
    "psg": {
        "name":        "PSG",
        "short":       "PSG",
        "color_a":     "003399",   # dark blue
        "color_b":     "DA291C",   # red
        "formation":   "4-3-3",
        "aggression":  "high",
        "speed_bonus": 0.8,
        "badge":       "🗼",
    },
    "bayern": {
        "name":        "Bayern Munich",
        "short":       "BAY",
        "color_a":     "DC052D",   # red
        "color_b":     "0066B2",   # blue
        "formation":   "4-2-3-1",
        "aggression":  "high",
        "speed_bonus": 0.5,
        "badge":       "🔴",
    },
}

# Export as list for frontend
CLUBS_LIST = [
    {"id": k, **{f: v for f, v in v.items() if f not in ("speed_bonus",)}}
    for k, v in CLUBS.items()
]
