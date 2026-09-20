"""
API routes. Kept as one router file since ORCA currently has exactly
three endpoints - splitting further would add indirection without benefit
at this size. If the API grows meaningfully, this is the natural place to
split into routes/chat.py and routes/zones.py.
"""

from fastapi import APIRouter

from app.api.schemas import AskRequest
from app.graph.agents.zones import get_zone_risks
from app.graph.workflow import run_query

router = APIRouter()


@router.get("/")
def health_check():
    return {"status": "ORCA backend is running"}


@router.get("/zones")
def zones(stakeholder: str = "general"):
    """Powers the map's multi-zone risk visualization. Called independently
    of /ask (not bundled into every chat response) since re-fetching live
    weather for every location on every single message would add
    unnecessary latency to the chat itself. The frontend calls this once
    on page load and again after each response, passing along the
    just-detected stakeholder so the zone weighting stays consistent
    with the chat."""
    return {
        "zones": get_zone_risks(stakeholder),
        "legend": {
            "LOW": "🟢",
            "MODERATE": "🟡",
            "HIGH": "🟠",
            "CRITICAL": "🔴",
        },
    }


def _build_route_field(result: dict) -> dict:
    """Builds the API's 'route' field from the internal route_plan. Present
    (non-None) in EVERY /ask response whenever the query was a route
    request - regardless of whether the query also happens to trigger the
    main pipeline's own location error, since route resolution has its own
    completely independent origin/destination extraction and can legitimately
    succeed (or fail with its own specific message) either way."""
    route_plan = result.get("route_plan")
    if route_plan is None:
        return None  # not a route request at all

    if route_plan.get("error"):
        return {
            "is_route": True,
            "error": route_plan["error"],
            "origin": None,
            "destination": None,
            "candidate_routes": [],
            "recommended_route_id": None,
            "explanation": None,
        }

    return {
        "is_route": True,
        "error": None,
        "origin": route_plan["origin"],
        "destination": route_plan["destination"],
        "candidate_routes": [
            {
                "id": r["id"],
                "label": r["label"],
                "distance_km": r["distance_km"],
                "travel_time_min": r["travel_time_min"],
                "route_risk_score": r["route_risk_score"],
                "route_risk_level": r["route_risk_level"],
                "primary_risk_factor": r["primary_risk_factor"],
                "is_recommended": r["is_recommended"],
                "waypoints": r["waypoints"],  # for map polyline rendering
                # --- Government/hard-safety override layer, per-route
                # (Section 14t) - additive, mirrors the main risk
                # response's own pre_override_level/override_fired/
                # override_reasons fields (Section 14n) exactly. Computed
                # from the SAME worst waypoint route_risk_score/
                # route_risk_level already reflect (see route_planning.py).
                "pre_override_level": r["pre_override_level"],
                "override_fired": r["override_fired"],
                "override_reasons": r["override_reasons"],
                # --- Maritime boundary geofencing (India EEZ) ---
                "boundary_warning": r["boundary_warning"],
                "boundary_distance_km": r["boundary_distance_km"],
                # --- Marine Protected Area geofencing (Section 14o) ---
                # A SEPARATE field from boundary_warning above, deliberately
                # not merged - crossing an international boundary and
                # entering a protected conservation area are different
                # kinds of problems (legal/territorial vs environmental/
                # fishing-restriction). mpa_warning is None (not False)
                # when MPA data hasn't been fetched yet - see
                # services/marine_protected_areas.py.
                "mpa_warning": r["mpa_warning"],
                "mpa_distance_km": r["mpa_distance_km"],
            }
            for r in route_plan["candidate_routes"]
        ],
        "recommended_route_id": route_plan["recommended_route_id"],
        "explanation": route_plan["explanation"],
    }


def _build_policy_field(result: dict) -> dict:
    """Builds the API's 'policy_answer' field - additive only, alongside
    whatever else the response already contains (risk data, route data,
    both, or neither). None when the query wasn't a policy question at
    all, so existing clients that ignore this field see no change."""
    policy_answer = result.get("policy_answer")
    if policy_answer is None:
        return None
    return {
        "is_policy_answer": True,
        "answer": policy_answer["answer"],
        "mode": policy_answer["mode"],
        "sources": policy_answer["sources"],
    }


def _build_route_answer(route_field: dict) -> str:
    """Deterministic, route-focused chat answer - built entirely from
    already-computed numbers, never invented. Includes the required
    prototype disclaimer (this is decision support, not certified
    maritime navigation)."""
    recommended = next(r for r in route_field["candidate_routes"] if r["is_recommended"])
    return (
        f"Recommended route: {recommended['label']} from {route_field['origin']['name']} to "
        f"{route_field['destination']['name']} \u2014 {recommended['distance_km']} km, about "
        f"{recommended['travel_time_min']} min, risk {recommended['route_risk_score']}/100 "
        f"({recommended['route_risk_level']}). {route_field['explanation']} "
        f"This is a prototype recommendation based on currently available environmental data, "
        f"not certified maritime navigation."
    )


@router.post("/ask")
def ask(request: AskRequest):
    result = run_query(request.query)

    # Compute the route field, the policy field, and the final answer text
    # ONCE, consistently, regardless of which response branch fires below -
    # this is what fixes a bug where a route-specific error would otherwise
    # get silently replaced by the main pipeline's more generic error
    # message, and (additively) does the same for policy answers.
    route_field = _build_route_field(result)
    policy_field = _build_policy_field(result)

    if route_field:
        final_answer = route_field["error"] if route_field["error"] else _build_route_answer(route_field)
    elif policy_field and not result.get("location_data"):
        # Pure policy question, no location involved at all - the policy
        # answer IS the whole response (synthesis_agent already mirrored
        # this into result["answer"], but read it from policy_field
        # directly here so this stays correct even if that ever changes).
        final_answer = policy_field["answer"]
    else:
        final_answer = result["answer"]

    if result.get("error"):
        return {
            "answer": final_answer,
            "error": result["error"],
            "stakeholder": result.get("stakeholder"),
            "language": result.get("language", "en"),
            "risk": None,
            "route": route_field,
            "policy_answer": policy_field,
            "confidence": None,
        }

    if not result.get("location_data"):
        # No location was resolved - either a pure policy question that
        # deliberately skipped location-finding (see planner.py's guard),
        # or a route-only request layered on top of one. There's honestly
        # no risk/weather/ocean data to report here, but this is NOT the
        # generic "could not identify location" error - policy_answer
        # and/or route may still carry a real, useful answer, so this
        # takes its own response shape rather than the error branch above.
        return {
            "answer": final_answer,
            "risk_level": None,
            "risk_reasons": [],
            "weather": None,
            "ocean": None,
            "map": None,
            "stakeholder": result.get("stakeholder"),
            "language": result.get("language", "en"),
            "risk": None,
            "route": route_field,
            "policy_answer": policy_field,
            "confidence": None,
        }

    risk_data = result["risk"]

    return {
        "answer": final_answer,
        # --- Existing fields, unchanged, for backward compatibility ---
        "risk_level": risk_data["level"],
        "risk_reasons": risk_data["reasons"],
        "weather": result["weather"],
        "ocean": result["ocean"],
        "map": {
            "user_location": result["geospatial"]["location_coords"],
            "location_name": result["geospatial"]["location_name"],
            "nearest_pfz": result["geospatial"]["nearest_pfz"],
        },
        # --- Stakeholder + structured risk contract ---
        "stakeholder": result.get("stakeholder"),
        "language": result.get("language", "en"),  # needed for voice output to speak the correct language
        "risk": {
            "overall_score": risk_data.get("overall_score"),
            "overall_level": risk_data.get("overall_level"),
            "metrics": risk_data.get("metrics", []),
            "reasons": risk_data.get("structured_reasons", []),
            "recommendation": risk_data.get("recommendation"),
            # --- Government/hard-safety override layer ---
            "pre_override_level": risk_data.get("pre_override_level"),
            "override_fired": risk_data.get("override_fired", False),
            "override_reasons": risk_data.get("override_reasons", []),
        },
        # --- Marine Route Optimization ---
        "route": route_field,
        # --- Policy RAG (Step 2) ---
        "policy_answer": policy_field,
        # --- Confidence score (completeness/freshness/agreement) ---
        "confidence": result.get("confidence"),
    }