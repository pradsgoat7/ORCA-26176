from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents import run_query, get_zone_risks

app = FastAPI(title="ORCA - Marine Intelligence Prototype")

# Allow the frontend (opened as a local file or on a different port) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    query: str


@app.get("/")
def health_check():
    return {"status": "ORCA backend is running"}


@app.get("/zones")
def zones(stakeholder: str = "general"):
    """Powers the map's multi-zone risk visualization. Called independently
    of /ask (not bundled into every chat response) since re-fetching live
    weather for 3 locations on every single message would add unnecessary
    latency to the chat itself. The frontend calls this once on page load
    and again after each response, passing along the just-detected
    stakeholder so the zone weighting stays consistent with the chat."""
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
                "waypoints": r["waypoints"],  # for map polyline rendering (Phase 5)
            }
            for r in route_plan["candidate_routes"]
        ],
        "recommended_route_id": route_plan["recommended_route_id"],
        "explanation": route_plan["explanation"],
    }


def _build_route_answer(route_field: dict) -> str:
    """Deterministic, route-focused chat answer - built entirely from
    already-computed numbers, never invented. Includes the required
    prototype disclaimer per the spec (this is decision support, not
    certified maritime navigation)."""
    recommended = next(r for r in route_field["candidate_routes"] if r["is_recommended"])
    return (
        f"Recommended route: {recommended['label']} from {route_field['origin']['name']} to "
        f"{route_field['destination']['name']} \u2014 {recommended['distance_km']} km, about "
        f"{recommended['travel_time_min']} min, risk {recommended['route_risk_score']}/100 "
        f"({recommended['route_risk_level']}). {route_field['explanation']} "
        f"This is a prototype recommendation based on currently available environmental data, "
        f"not certified maritime navigation."
    )


@app.post("/ask")
def ask(request: AskRequest):
    result = run_query(request.query)

    # Compute the route field and the final answer text ONCE, consistently,
    # regardless of which response branch fires below - this is what fixes
    # the bug where a route-specific error would otherwise get silently
    # replaced by the main pipeline's more generic error message.
    route_field = _build_route_field(result)

    if route_field:
        final_answer = route_field["error"] if route_field["error"] else _build_route_answer(route_field)
    else:
        final_answer = result["answer"]

    if result.get("error"):
        return {
            "answer": final_answer,
            "error": result["error"],
            "stakeholder": result.get("stakeholder"),
            "risk": None,
            "route": route_field,
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
        # --- Phase 4 additions: stakeholder + structured risk contract ---
        "stakeholder": result.get("stakeholder"),
        "risk": {
            "overall_score": risk_data.get("overall_score"),
            "overall_level": risk_data.get("overall_level"),
            "metrics": risk_data.get("metrics", []),
            "reasons": risk_data.get("structured_reasons", []),
            "recommendation": risk_data.get("recommendation"),
        },
        # --- Phase 4 (Route Optimization) addition ---
        "route": route_field,
    }