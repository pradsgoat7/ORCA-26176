"""
Risk agent - computes both the legacy level/score/reasons (kept for
backward compatibility with the fallback templates and frontend) and the
newer structured Risk Engine metrics (stakeholder-weighted overall score),
then applies the hard-safety override layer and computes a confidence
score on top of that (see PROJECT_CONTEXT.md for the full write-up).
"""

from app.core.risk_engine import RECOMMENDATIONS, apply_safety_override, calculate_all_metrics, calculate_confidence_score
from app.graph.state import ORCAState


def risk_agent(state: ORCAState) -> ORCAState:
    # weather/ocean are None either on a genuine error, or for a pure
    # policy question that deliberately has no location (see planner.py) -
    # either way, there's no environmental data to score here.
    if state.get("error") or state.get("weather") is None or state.get("ocean") is None:
        return {"risk": None, "confidence": None}
    weather = state["weather"]
    ocean = state["ocean"]

    reasons = []
    score = 0  # higher = riskier

    if weather["cyclone_alert"]:
        score += 3
        reasons.append(f"Active cyclone alert: {weather.get('cyclone_name', 'unnamed system')}")
    if weather["lightning_alert"]:
        score += 2
        reasons.append("Lightning alert in the area")
    if ocean["wave_height_m"] > 2.0:
        score += 2
        reasons.append(f"High wave height ({ocean['wave_height_m']} m)")
    if weather["wind_speed_kmph"] > 30:
        score += 1
        reasons.append(f"Strong winds ({weather['wind_speed_kmph']} km/h)")

    if score >= 3:
        level = "unsafe"
    elif score >= 1:
        level = "caution"
    else:
        level = "safe"

    if not reasons:
        reasons.append("No significant hazards detected")

    # Structured metrics + stakeholder-weighted overall score, computed
    # independently of the legacy score above. Added alongside the
    # existing level/score/reasons - nothing existing changes, so the
    # frontend and fallback templates keep working unmodified.
    stakeholder_info = state.get("stakeholder") or {}
    stakeholder_type = stakeholder_info.get("type", "general")
    structured = calculate_all_metrics(weather, ocean, stakeholder_type)

    # Hard-safety override layer, applied AFTER the weighted calculation -
    # can only escalate overall_level, never de-escalate it (see
    # apply_safety_override's docstring / PROJECT_CONTEXT.md). The
    # underlying overall_score is NOT touched - only the level
    # classification (and the recommendation text derived from it) can be
    # escalated, so overall_score always still reflects the weighted
    # calculation alone.
    override = apply_safety_override(structured["overall_score"], structured["overall_level"], weather, ocean)
    final_level = override["level"]
    recommendations = RECOMMENDATIONS.get(stakeholder_type, RECOMMENDATIONS["general"])
    final_recommendation = recommendations[final_level] if final_level != structured["overall_level"] else structured["recommendation"]

    confidence = calculate_confidence_score(weather, ocean)

    return {
        "risk": {
            "level": level,
            "score": score,
            "reasons": reasons,
            "metrics": structured["metrics"],
            "structured_reasons": structured["reasons"],
            "overall_score": structured["overall_score"],
            "overall_level": final_level,
            # What the weighted calculation alone produced, BEFORE any
            # hard-safety override - kept for transparency, never hidden.
            "pre_override_level": structured["overall_level"],
            "override_fired": override["override_fired"],
            "override_reasons": override["override_reasons"],
            "recommendation": final_recommendation,
        },
        "confidence": confidence,
    }
