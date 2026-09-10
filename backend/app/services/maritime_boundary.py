"""
India's EEZ boundary, loaded once at import time (same pattern as
app/data/loader.py loading marine_data.json). Provides a
distance-to-boundary-edge check, in the same style as is_near_coast() in
this package's geocoding.py - a pragmatic, explainable heuristic rather
than a certified navigation tool.

See PROJECT_CONTEXT.md Section 13c for exactly where india_eez.geojson
came from and the "EEZ_land_union" nuance (the polygon merges India's
land territory + EEZ waters into one shape, so it's a boundary-proximity
check against the outer edge of that combined shape - correct for
flagging routes that get close to leaving Indian waters, since a fishing
route's waypoints are never on land anyway).
"""

import json

from shapely.geometry import Point, shape
from shapely.ops import nearest_points

from app.config import DATA_DIR
from app.services.geocoding import haversine_km

EEZ_PATH = DATA_DIR / "india_eez.geojson"

with open(EEZ_PATH, "r") as f:
    _eez_geojson = json.load(f)

INDIA_EEZ_POLYGON = shape(_eez_geojson["features"][0]["geometry"])
INDIA_EEZ_BOUNDARY = INDIA_EEZ_POLYGON.boundary  # the edge line, not the filled area

# A route can be worryingly close to the boundary without technically
# crossing it - this is the "how close is too close" threshold for the
# geofencing warning, not an inside/outside check.
DEFAULT_BOUNDARY_WARNING_THRESHOLD_KM = 8.0


def distance_to_eez_boundary_km(lat: float, lon: float) -> float:
    """Real-world distance (km) from (lat, lon) to the nearest point on
    India's EEZ boundary EDGE - works the same whether the point is just
    inside or just outside, which is what makes this useful for an
    'approaching the boundary' warning rather than a simple inside/outside
    check. Finds the nearest boundary point via shapely (cheap - local
    polygon geometry, no network call) then measures the real distance
    with haversine_km, reusing the same distance function geocoding.py
    already uses, rather than a raw degree-distance approximation."""
    point = Point(lon, lat)
    nearest_on_boundary, _ = nearest_points(INDIA_EEZ_BOUNDARY, point)
    return haversine_km(lat, lon, nearest_on_boundary.y, nearest_on_boundary.x)
