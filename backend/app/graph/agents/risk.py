"""
Risk agent - computes both the legacy level/score/reasons (kept for
backward compatibility with the fallback templates and frontend) and the
newer structured Risk Engine metrics (stakeholder-weighted overall score).
"""

from app.core.risk_engine import calculate_all_metrics
from app.graph.state import ORCAState


def risk_agent(state: ORCAState) -> ORCAState:
    if state.get("error"):
        return {"risk": None}
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

    return {
        "risk": {
            "level": level,
            "score": score,
            "reasons": reasons,
            "metrics": structured["metrics"],
            "structured_reasons": structured["reasons"],
            "overall_score": structured["overall_score"],
            "overall_level": structured["overall_level"],
            "recommendation": structured["recommendation"],
        }
    }
