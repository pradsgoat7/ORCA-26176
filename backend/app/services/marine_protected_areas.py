"""
India's Marine Protected Areas (MPAs) - second geofencing layer alongside
maritime_boundary.py's EEZ boundary check. Same shapely nearest_points() +
haversine distance-to-boundary pattern, but LAZILY loaded rather than at
import time, since app/data/india_mpa.geojson is NOT committed to this
repo (see PROJECT_CONTEXT.md Section 14o for why - Protected Planet's
terms prohibit redistributing WDPA data even as a country extract) and
won't exist until a developer runs scripts/fetch_india_mpa_data.py with
their own API token. Every function here returns None honestly when the
data isn't available yet - never a fabricated "no MPAs nearby" default.
"""

import json
from typing import Optional

from shapely.geometry import Point, shape
from shapely.ops import nearest_points, unary_union

from app.config import DATA_DIR
from app.services.geocoding import haversine_km

MPA_PATH = DATA_DIR / "india_mpa.geojson"

# MPAs are typically much smaller, more tightly-bounded conservation areas
# than the whole EEZ (Section 13b's DEFAULT_BOUNDARY_WARNING_THRESHOLD_KM
# is 8.0km), so "how close is too close" uses a tighter threshold - a
# fishing-restriction zone is immediately consequential right at its edge,
# not just near it. 5.0km sits within the same 5-10km range originally
# scoped for the EEZ threshold.
DEFAULT_MPA_WARNING_THRESHOLD_KM = 5.0

_mpa_boundary = None
_load_attempted = False


def _load_boundary_from_path(path) -> Optional[object]:
    """Loads a GeoJSON FeatureCollection of MPA polygons from `path` and
    returns their unioned boundary (the edge lines of all polygons
    combined), or None on any failure - missing file, malformed JSON,
    empty feature list. Never raises; callers treat None as 'MPA data
    unavailable', not an error.

    Two real data-quality issues confirmed against the actual Protected
    Planet API response (Section 14u - the real india_mpa.geojson, not
    the earlier test-only placeholder), handled explicitly rather than
    letting them silently degrade into 'no MPA data at all':

    1. Not every WDPA record for country=IND&marine=true has real polygon
       geometry - some (e.g. the Gulf of Mannar Biosphere Reserve, WDPA
       ID 900665 - a DIFFERENT, larger record than the real Ramsar
       polygon covering the same area under WDPA ID 555795353) only carry
       a single Point coordinate. Using a lone point as a stand-in for a
       10,500 km^2 area's 'edge' would fabricate false precision (a route
       could pass through the real area while reading as far from its
       single reference point, or vice versa) - so Point geometries are
       deliberately EXCLUDED from the boundary union used for proximity
       distance. This does mean a handful of real WDPA entries contribute
       no geofencing protection here - an honest, documented limitation
       of the API's own data completeness, not something ORCA can fix by
       computing a boundary that doesn't exist in the source data.
    2. Real-world WDPA polygons are not guaranteed topologically valid -
       one real fetched polygon ('Thane Creek') is self-intersecting
       (confirmed via geom.is_valid), which crashes shapely's
       unary_union() outright if left as-is. Repaired via the standard,
       well-established shapely idiom for minor self-intersections -
       buffer(0) - which does not meaningfully change the geometry's
       shape or extent, only resolves the topology error."""
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            geojson = json.load(f)
        polygons = []
        for feat in geojson.get("features", []):
            geom = shape(feat["geometry"])
            if geom.geom_type in ("Point", "MultiPoint"):
                continue  # no real boundary to check proximity against - see docstring
            if not geom.is_valid:
                geom = geom.buffer(0)
            polygons.append(geom)
        if not polygons:
            return None
        return unary_union(polygons).boundary
    except Exception as e:
        print(f"[ORCA] Failed to load MPA data from {path}: {e}")
        return None


def _get_mpa_boundary():
    """Lazily loads and caches india_mpa.geojson's unioned boundary. This
    is expected to return None on a fresh checkout - the file is
    gitignored until a developer runs scripts/fetch_india_mpa_data.py."""
    global _mpa_boundary, _load_attempted
    if _mpa_boundary is not None or _load_attempted:
        return _mpa_boundary
    _load_attempted = True
    _mpa_boundary = _load_boundary_from_path(MPA_PATH)
    return _mpa_boundary


def distance_to_nearest_mpa_km(lat: float, lon: float) -> Optional[float]:
    """Real-world distance (km) from (lat, lon) to the nearest Marine
    Protected Area boundary edge - same nearest_points()+haversine_km
    pattern as maritime_boundary.distance_to_eez_boundary_km(), works the
    same whether the point is just inside or just outside an MPA. Returns
    None (not 0, not a large fallback number) if MPA data isn't loaded
    yet - callers must treat None as 'unknown', never as 'confirmed no
    nearby MPA'."""
    boundary = _get_mpa_boundary()
    if boundary is None:
        return None
    point = Point(lon, lat)
    nearest_on_boundary, _ = nearest_points(boundary, point)
    return haversine_km(lat, lon, nearest_on_boundary.y, nearest_on_boundary.x)
