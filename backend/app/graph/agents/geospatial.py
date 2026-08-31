"""
Geospatial agent - packages the resolved location's coordinates and
nearest fishing zone (if known) for the map and synthesis layers.
"""

from app.graph.state import ORCAState


def geospatial_agent(state: ORCAState) -> ORCAState:
    if state.get("error"):
        return {"geospatial": None}
    loc = state["location_data"]
    geo = {
        "location_name": loc["name"],
        "location_coords": {"lat": loc["lat"], "lon": loc["lon"]},
        "nearest_pfz": loc.get("nearest_pfz"),  # may be None for non-demo cities
    }
    return {"geospatial": geo}
