"""
Sanity test for the India EEZ boundary data (Day 2 of the 10-day plan,
Section 13b of PROJECT_CONTEXT.md). This ONLY verifies the GeoJSON file
loads and produces geographically sane inside/outside results - it does
NOT wire the boundary into route_engine.py yet (that's Days 3-4).

Loads app/data/india_eez.geojson with the plain json module, then parses
the geometry with shapely - same library/pattern as is_near_coast() in
app/services/geocoding.py, just using an actual polygon instead of a
haversine-distance heuristic.

Usage:
    cd backend
    source venv/bin/activate
    python3 -m tests.test_maritime_boundary
"""

import json

from shapely.geometry import Point, shape

from app.config import DATA_DIR

EEZ_PATH = DATA_DIR / "india_eez.geojson"

with open(EEZ_PATH, "r") as f:
    _eez_geojson = json.load(f)

_feature = _eez_geojson["features"][0]
INDIA_EEZ_POLYGON = shape(_feature["geometry"])


def is_inside_india_eez(lat: float, lon: float) -> bool:
    """Point-in-polygon check against India's EEZ boundary. Mirrors the
    shapely usage style of is_near_coast(), but checks actual polygon
    containment rather than distance to reference points."""
    return INDIA_EEZ_POLYGON.covers(Point(lon, lat))


print("=" * 70)
print(f"Loading: {EEZ_PATH}")
print(f"Feature properties: {_feature['properties']}")
print(f"Geometry type: {INDIA_EEZ_POLYGON.geom_type}")
print(f"Polygon is_valid: {INDIA_EEZ_POLYGON.is_valid}")
print(f"Polygon bounds (minLon, minLat, maxLon, maxLat): {INDIA_EEZ_POLYGON.bounds}")
print()

assert INDIA_EEZ_POLYGON.geom_type in ("Polygon", "MultiPolygon"), (
    "Expected a Polygon/MultiPolygon geometry"
)
assert INDIA_EEZ_POLYGON.is_valid, "Loaded EEZ polygon is not geometrically valid"

TEST_POINTS = [
    ("Offshore near Mumbai, Arabian Sea (inside India's EEZ)", 18.90, 70.00, True),
    ("Offshore near Chennai, Bay of Bengal (inside India's EEZ)", 12.50, 82.00, True),
    ("Mumbai city itself (land, inside India's territory)", 18.94, 72.84, True),
    ("Mid Arabian Sea, far from India (international waters)", 15.00, 60.00, False),
    ("Deep Indian Ocean south of Sri Lanka (international waters)", -5.00, 80.00, False),
    ("Off the Myanmar coast, far side of Bay of Bengal (international waters)", 10.00, 95.00, False),
    ("Middle of the Pacific Ocean (nowhere near India)", 0.00, 160.00, False),
]

print("=" * 70)
all_passed = True
for label, lat, lon, expected in TEST_POINTS:
    actual = is_inside_india_eez(lat, lon)
    status = "OK" if actual == expected else "FAIL"
    if actual != expected:
        all_passed = False
    print(
        f"[{status}] {label}\n"
        f"       lat={lat}, lon={lon} -> inside_india_eez={actual} (expected {expected})"
    )

print("=" * 70)
if all_passed:
    print("ALL CHECKS PASSED: india_eez.geojson loads correctly and the polygon")
    print("gives geographically sane results for known inside/outside points.")
else:
    print("SOME CHECKS FAILED - see [FAIL] lines above.")
