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

def calculate_all_metrics(weather: dict, ocean: dict, stakeholder_type: str = "general") -> dict:
    """Takes the existing weather/ocean dicts ORCA already produces (live
    or mock, doesn't matter - this function only cares about the values)
    and returns the four deterministic risk metrics, structured reasons,
    AND the stakeholder-weighted overall score/level/recommendation."""
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

    raw_scores = {k: v["score"] for k, v in raw.items()}
    overall = calculate_overall_risk(raw_scores, stakeholder_type)

    return {
        "metrics": metrics,
        "reasons": reasons,
        "raw_scores": raw_scores,
        "overall_score": overall["overall_score"],
        "overall_level": overall["overall_level"],
        "recommendation": overall["recommendation"],
    }


# ---------- Phase 3: stakeholder-weighted overall score ----------

# Weights per stakeholder - each set sums to 1.0. Chosen per the spec's
# own guidance (fisherman leans wave/wind/cyclone; disaster management
# leans cyclone/regional hazard); coast_guard sits between the two,
# reflecting broader operational/vessel-safety concern across all hazards.
STAKEHOLDER_WEIGHTS = {
    "fisherman": {"wave_risk": 0.35, "wind_risk": 0.25, "cyclone_risk": 0.30, "lightning_risk": 0.10},
    "coast_guard": {"wave_risk": 0.30, "wind_risk": 0.25, "cyclone_risk": 0.30, "lightning_risk": 0.15},
    "disaster_management": {"wave_risk": 0.15, "wind_risk": 0.25, "cyclone_risk": 0.40, "lightning_risk": 0.20},
    "general": {"wave_risk": 0.25, "wind_risk": 0.25, "cyclone_risk": 0.25, "lightning_risk": 0.25},
}

RECOMMENDATIONS = {
    "fisherman": {
        "LOW": "Conditions are currently suitable for fishing. Normal precautions are advised.",
        "MODERATE": "Exercise caution before heading out - monitor conditions closely and be ready to return early.",
        "HIGH": "Avoid offshore fishing due to severe marine hazards.",
        "CRITICAL": "Do not go to sea. Conditions are extremely hazardous.",
    },
    "coast_guard": {
        "LOW": "Routine monitoring is sufficient. No elevated response needed.",
        "MODERATE": "Maintain standard patrol coverage and monitor for changes.",
        "HIGH": "Increase coastal monitoring, maintain rescue readiness, and monitor vessels in affected waters.",
        "CRITICAL": "Activate emergency response protocols and prioritize rescue readiness in the affected sector.",
    },
    "disaster_management": {
        "LOW": "No immediate preparedness action required. Maintain routine monitoring.",
        "MODERATE": "Monitor conditions closely and prepare advisories if hazards increase.",
        "HIGH": "Issue a coastal advisory, increase monitoring, and coordinate emergency preparedness.",
        "CRITICAL": "Immediate preparedness required - issue emergency advisory and coordinate evacuation readiness.",
    },
    "general": {
        "LOW": "Conditions are currently safe.",
        "MODERATE": "Some caution is advised given current conditions.",
        "HIGH": "Hazardous conditions are present in this area.",
        "CRITICAL": "Severe hazards present - avoid this area.",
    },
}


def classify_level(score: int) -> str:
    """Thresholds per the spec: 0-24 LOW, 25-49 MODERATE, 50-74 HIGH, 75-100 CRITICAL."""
    if score >= 75:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 25:
        return "MODERATE"
    return "LOW"


def calculate_overall_risk(raw_scores: dict, stakeholder_type: str) -> dict:
    """Combines the four individual metrics into one overall score using
    stakeholder-specific weights. Falls back to 'general' weights for any
    unrecognized stakeholder type, so this never crashes on bad input."""
    weights = STAKEHOLDER_WEIGHTS.get(stakeholder_type, STAKEHOLDER_WEIGHTS["general"])

    overall_score = round(sum(weights[k] * raw_scores.get(k, 0) for k in weights))
    overall_score = max(0, min(100, overall_score))  # clamp, just in case
    overall_level = classify_level(overall_score)

    recommendations = RECOMMENDATIONS.get(stakeholder_type, RECOMMENDATIONS["general"])
    recommendation = recommendations[overall_level]

    return {
        "overall_score": overall_score,
        "overall_level": overall_level,
        "recommendation": recommendation,
        "weights_used": weights,
    }


# ---------- Government/hard-safety override layer ----------

# Douglas Sea Scale (the real, standard WMO sea-state code for describing
# sea surface roughness by wave height) - State 6, "Very Rough", is
# 4-6 metres. This is a genuine, citable maritime standard, unlike an
# invented "INCOIS Red Warning" threshold we don't actually have a feed
# for. The trigger uses the LOWER bound (4.0m) so the override fires as
# soon as a query genuinely enters "very rough" territory, not only once
# it's near the top of that band.
VERY_ROUGH_SEA_THRESHOLD_M = 4.0

_LEVEL_ORDER = ["LOW", "MODERATE", "HIGH", "CRITICAL"]


def _escalate(level: str, minimum: str) -> str:
    """Returns whichever of level/minimum is more severe - this is what
    guarantees an override can only ESCALATE, never de-escalate, a level
    that was already higher from the normal weighted calculation."""
    return minimum if _LEVEL_ORDER.index(minimum) > _LEVEL_ORDER.index(level) else level


def apply_safety_override(overall_score: int, overall_level: str, weather: dict, ocean: dict) -> dict:
    """Hard safety rules applied AFTER the normal stakeholder-weighted
    calculation (calculate_overall_risk) - these can only ESCALATE the
    level, never de-escalate it, and every rule here is based ENTIRELY on
    real fields ORCA actually has. Deliberately does NOT check for a
    fabricated "INCOIS High Wave Red Alert" or "IMD Orange Warning" feed -
    ORCA has no such feeds (see PROJECT_CONTEXT.md Section 4 for exactly
    what's live vs mock) - every rule below cites the real signal it's
    actually based on:

    - weather['cyclone_alert'] (mock for demo cities, e.g. Chennai - see
      Section 4) True -> forces CRITICAL. A real active cyclone alert is a
      hard stop that should never get diluted into a moderate-looking
      average by calm wave/wind numbers elsewhere in the weighted score.
    - ocean['wave_height_m'] (LIVE, Open-Meteo Marine API) at or above
      VERY_ROUGH_SEA_THRESHOLD_M (4.0m - Douglas Sea Scale "Very Rough",
      the real WMO Sea State 6 threshold) -> forces at least HIGH.
      Genuinely rough seas are a hard safety concern regardless of how the
      weighted average of wave/wind/cyclone/lightning happens to land.
    - weather['lightning_alert'] (LIVE-DERIVED from Open-Meteo's WMO
      weather code - Section 4) True -> forces at least MODERATE.
      Lightning is an immediate, binary hazard that shouldn't be averaged
      away by good wave/wind conditions.

    Returns the (possibly escalated) level plus an explicit, always-visible
    record of which rules matched and why - "override_fired" is True
    whenever at least one hard-safety CONDITION is true, even if the
    weighted score had already reached that level or higher on its own
    (so a user can always see "yes, there genuinely is an active cyclone
    alert" as a fact, not just infer it from the number never changing).
    Never silent - a user seeing CRITICAL should know whether that's the
    normal weighted score, a hard override, or both."""
    weather = weather or {}
    ocean = ocean or {}

    final_level = overall_level
    reasons = []

    if weather.get("cyclone_alert"):
        final_level = _escalate(final_level, "CRITICAL")
        reasons.append(
            "Active cyclone alert (weather.cyclone_alert) forces CRITICAL, regardless of the weighted score."
        )

    wave_height = ocean.get("wave_height_m")
    if wave_height is not None and wave_height >= VERY_ROUGH_SEA_THRESHOLD_M:
        final_level = _escalate(final_level, "HIGH")
        reasons.append(
            f"Wave height ({wave_height} m) has reached 'Very Rough' on the Douglas Sea Scale "
            f"(WMO Sea State 6, {VERY_ROUGH_SEA_THRESHOLD_M}m+) - forces at least HIGH."
        )

    if weather.get("lightning_alert"):
        final_level = _escalate(final_level, "MODERATE")
        reasons.append("Lightning activity detected (weather.lightning_alert) - forces at least MODERATE.")

    return {
        "level": final_level,
        "override_fired": len(reasons) > 0,
        "override_reasons": reasons,  # empty list if nothing fired
    }


# ---------- Confidence score ----------

# Fields checked for "completeness" - do we have a NUMBER to show the
# user, regardless of whether it's live or mock. sea_surface_temp_c is
# included here even though ocean_agent guarantees it's never None (it
# falls back to DEFAULT_SST_C mock if both MOSDAC and Open-Meteo fail) -
# that's correct for completeness ("is there a number") even though the
# same field is deliberately EXCLUDED from freshness below (see there for
# why).
_COMPLETENESS_WEATHER_FIELDS = ["wind_speed_kmph"]
_COMPLETENESS_OCEAN_FIELDS = [
    "wave_height_m", "sea_surface_temp_c", "salinity_psu",
    "current_speed_ms", "mixed_layer_depth_m",
]


def calculate_confidence_score(weather: dict, ocean: dict) -> dict:
    """Genuinely-adapted confidence score (40% completeness / 30%
    freshness / 30% agreement), built ONLY from real, already-available
    signals - no fabricated "sensor uptime" or "data quality API" we don't
    have. See PROJECT_CONTEXT.md for the honest reasoning behind each
    component, especially "agreement" (see below - it's a documented
    simplification of the original idea, not the original idea itself).

    - Completeness (40%): fraction of the 6 fields above that are
      non-None. Measures "do we have a number to show", not "is it real".
    - Freshness (30%): fraction of ORCA's real, separately-tracked
      data-source signals that report "live" rather than "mock"/missing -
      weather['wind_source'], ocean['ocean_source'], and (as a proxy,
      since these 3 fields have NO mock fallback at all - see ocean_agent)
      whether each MOSDAC-sourced field came back non-None. Deliberately
      does NOT include sea_surface_temp_c: unlike wave_height_m (which has
      an explicit ocean_source flag), the ocean dict does not separately
      record whether SST came from MOSDAC (live), Open-Meteo (live), or
      the DEFAULT_SST_C mock fallback - guessing its provenance here would
      be dishonest, so it's excluded rather than assumed.
    - Agreement (30%): HONEST REINTERPRETATION, explicitly flagged as a
      simplification. The original idea - "do two independent
      measurements of the SAME variable agree" - doesn't apply to ORCA's
      real data: Open-Meteo and MOSDAC measure DIFFERENT variables
      (wind/wave vs temp/salinity/current/MLD), never the same one twice,
      so there is nothing to literally cross-check numerically. Instead,
      this treats "agreement" as: are BOTH of ORCA's genuinely independent
      live systems (Open-Meteo, MOSDAC) actually up and returning real
      data this call, rather than one succeeding while the other silently
      falls back? This is a proxy for overall pipeline health, not a
      literal value comparison. Because it's built from the SAME
      underlying source-availability signals as freshness above, it will
      correlate closely with freshness in practice - that correlation is
      an honest, direct consequence of not having two measurements of the
      same physical variable to compare, not a bug."""
    weather = weather or {}
    ocean = ocean or {}

    fields = [weather.get(f) for f in _COMPLETENESS_WEATHER_FIELDS] + \
             [ocean.get(f) for f in _COMPLETENESS_OCEAN_FIELDS]
    completeness = sum(1 for v in fields if v is not None) / len(fields)

    freshness_signals = [
        weather.get("wind_source") == "live",
        ocean.get("ocean_source") == "live",
        ocean.get("salinity_psu") is not None,
        ocean.get("current_speed_ms") is not None,
        ocean.get("mixed_layer_depth_m") is not None,
    ]
    freshness = sum(1 for s in freshness_signals if s) / len(freshness_signals)

    # Open-Meteo "system" success = fraction of its own two feeds (wind,
    # wave) that came back live. MOSDAC "system" success = fraction of its
    # three independently-fetched layers (salinity, current, MLD) that
    # came back non-None. Averaging these two system-level fractions is
    # the "both independent systems up" proxy described above.
    open_meteo_success = sum([
        weather.get("wind_source") == "live",
        ocean.get("ocean_source") == "live",
    ]) / 2
    mosdac_success = sum([
        ocean.get("salinity_psu") is not None,
        ocean.get("current_speed_ms") is not None,
        ocean.get("mixed_layer_depth_m") is not None,
    ]) / 3
    agreement = (open_meteo_success + mosdac_success) / 2

    confidence_score = round(100 * (0.40 * completeness + 0.30 * freshness + 0.30 * agreement))
    confidence_score = max(0, min(100, confidence_score))

    return {
        "confidence_score": confidence_score,
        "completeness": round(completeness, 2),
        "freshness": round(freshness, 2),
        "agreement": round(agreement, 2),
    }