"""
Deterministic risk engine - Phase 2 of the stakeholder/risk upgrade.

Pure functions only: given raw environmental values, return explainable
0-100 risk scores. No LLM calls, no randomness - the same input always
produces the same output. This is exactly why the synthesis agent is
instructed to treat these numbers as ground truth it can explain, never
invent or override.

Phase 3 will add stakeholder-specific weighting on top of these individual
metrics to produce a single overall_score/overall_level - that logic
deliberately does NOT live in this file yet, to keep this phase testable
in isolation first.
"""

from typing import Optional

METRIC_LABELS = {
    "wave_risk": "Wave Risk",
    "wind_risk": "Wind Risk",
    "cyclone_risk": "Cyclone Risk",
    "lightning_risk": "Lightning Risk",
}


# ---------- Individual metric calculators ----------

def calculate_wave_risk(wave_height_m: Optional[float]) -> dict:
    """Scales linearly: 0m -> 0 risk, capped at 100 by ~3m+.
    Thresholds are prototype logic, not an official maritime safety standard."""
    if wave_height_m is None:
        return {"score": 0, "reason": "No wave height data available."}

    score = min(100, round((wave_height_m / 3.0) * 100))

    if wave_height_m > 2.5:
        reason = f"Wave height ({wave_height_m} m) is well above the safe operating range."
    elif wave_height_m > 1.5:
        reason = f"Wave height ({wave_height_m} m) is above the preferred operating range."
    else:
        reason = f"Wave height ({wave_height_m} m) is within a manageable range."

    return {"score": score, "reason": reason}


def calculate_wind_risk(wind_speed_kmph: Optional[float]) -> dict:
    """Scales linearly: 0 km/h -> 0 risk, capped at 100 by ~50 km/h+."""
    if wind_speed_kmph is None:
        return {"score": 0, "reason": "No wind speed data available."}

    score = min(100, round((wind_speed_kmph / 50.0) * 100))

    if wind_speed_kmph > 35:
        reason = f"Wind speed ({wind_speed_kmph} km/h) is strong enough to be hazardous."
    elif wind_speed_kmph > 25:
        reason = f"Wind speed ({wind_speed_kmph} km/h) is elevated."
    else:
        reason = f"Wind speed ({wind_speed_kmph} km/h) is calm to moderate."

    return {"score": score, "reason": reason}


def calculate_cyclone_risk(cyclone_alert: bool, cyclone_name: Optional[str] = None) -> dict:
    """Binary for now, matching the available data - 100 if an alert is
    active, 0 otherwise. Deliberately not inventing an in-between score,
    since there's no intensity/category data to base one on yet."""
    if cyclone_alert:
        name = cyclone_name or "an unnamed system"
        return {"score": 100, "reason": f"Active cyclone alert: {name}."}
    return {"score": 0, "reason": "No active cyclone alert."}


def calculate_lightning_risk(lightning_alert: bool) -> dict:
    """Binary for now, matching the available data."""
    if lightning_alert:
        return {"score": 100, "reason": "Lightning activity detected in the area."}
    return {"score": 0, "reason": "No lightning activity detected."}


# ---------- Combine into the structured metrics + reasons contract ----------

def calculate_all_metrics(weather: dict, ocean: dict) -> dict:
    """Takes the existing weather/ocean dicts ORCA already produces (live
    or mock, doesn't matter - this function only cares about the values)
    and returns the four deterministic risk metrics plus structured
    reasons, ready for Phase 3 to combine into a stakeholder-weighted
    overall score."""
    weather = weather or {}
    ocean = ocean or {}

    wave = calculate_wave_risk(ocean.get("wave_height_m"))
    wind = calculate_wind_risk(weather.get("wind_speed_kmph"))
    cyclone = calculate_cyclone_risk(weather.get("cyclone_alert"), weather.get("cyclone_name"))
    lightning = calculate_lightning_risk(weather.get("lightning_alert"))

    raw = {
        "wave_risk": wave,
        "wind_risk": wind,
        "cyclone_risk": cyclone,
        "lightning_risk": lightning,
    }

    metrics = [
        {"name": METRIC_LABELS[key], "key": key, "score": val["score"]}
        for key, val in raw.items()
    ]

    reasons = [
        {
            "factor": METRIC_LABELS[key].replace(" Risk", ""),
            "score": val["score"],
            "reason": val["reason"],
        }
        for key, val in raw.items()
        if val["score"] > 0  # only surface factors that actually contribute
    ]

    if not reasons:
        reasons = [{"factor": "Overall", "score": 0, "reason": "No significant hazards detected."}]

    return {"metrics": metrics, "reasons": reasons, "raw_scores": {k: v["score"] for k, v in raw.items()}}