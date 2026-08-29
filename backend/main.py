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


@app.post("/ask")
def ask(request: AskRequest):
    result = run_query(request.query)

    if result.get("error"):
        return {
            "answer": result["answer"],
            "error": result["error"],
            # Phase 4: stakeholder detection runs independently of location
            # resolution (Phase 1 fix), so it's still meaningful even here.
            "stakeholder": result.get("stakeholder"),
            "risk": None,
        }

    risk_data = result["risk"]

    return {
        "answer": result["answer"],
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
    }