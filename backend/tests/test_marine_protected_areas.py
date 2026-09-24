"""
Marine Protected Area (MPA) geofencing tests - Section 14o (built), now
verified against REAL WDPA/Protected Planet data (Section 14u - the
Protected Planet API token arrived, `scripts/fetch_india_mpa_data.py` was
actually run, and `app/data/india_mpa.geojson` now contains genuine
India marine protected area polygons, not the earlier Wikipedia-sourced
TEST-ONLY placeholder rectangle).

WHAT CHANGED FROM THE PLACEHOLDER VERSION OF THIS FILE: Test 1 no longer
mocks `_get_mpa_boundary()` with a hand-built rectangle - it uses the
REAL lazily-loaded `india_mpa.geojson`, and its destination coordinate
was updated to a point actually verified (via direct shapely inspection)
to sit inside the real Gulf of Mannar Marine Biosphere Reserve polygon
(WDPA site ID 555795353, a 526.7 km^2 Ramsar-listed MultiPolygon of 5
separate island/reef areas - NOT the same WDPA record as the much larger
10,500 km^2 "Gulf of Mannar" UNESCO-MAB Biosphere Reserve entry, WDPA ID
900665, which the API only returns as a single Point with no boundary
geometry at all - see marine_protected_areas.py's docstring for why
Point-only records are excluded from the proximity check rather than
faked into a boundary that doesn't exist in the source data).
Reassuringly, the real polygon's bounding box (8.817-9.252N,
78.192-79.250E) is remarkably close to the Wikipedia-sourced placeholder
rectangle Section 14o originally built by hand (8.75-9.25N, 78.20-79.25E)
- a good real-world confirmation that the placeholder was a genuinely
reasonable approximation, not a guess that happened to be wrong.

Run with:
    cd backend
    source venv/bin/activate
    python3 -m tests.test_marine_protected_areas
"""

from pathlib import Path
from unittest.mock import patch

from shapely.geometry import shape

import app.services.marine_protected_areas as mpa_module
from app.core.route_engine import generate_candidate_routes, check_mpa_proximity, check_boundary_proximity
from app.services.maritime_boundary import distance_to_eez_boundary_km, DEFAULT_BOUNDARY_WARNING_THRESHOLD_KM
from app.services.marine_protected_areas import DEFAULT_MPA_WARNING_THRESHOLD_KM

passed = 0
failed = 0


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {label}")
        passed += 1
    else:
        print(f"  FAIL: {label} {detail}")
        failed += 1


def _reset_mpa_cache():
    """The module caches its loaded boundary after the first call
    (Section 14o's lazy-load design) - tests that need a fresh load (a
    different mocked path, or the real file after a previous test patched
    it away) must reset both cache globals first."""
    mpa_module._mpa_boundary = None
    mpa_module._load_attempted = False


# ---------- Test 0: the real fetched file itself is valid, real, and geographically sane ----------
print("=" * 70)
print("TEST 0: the real india_mpa.geojson - valid GeoJSON, real India MPA polygons, sane geography")

geojson_path = mpa_module.MPA_PATH
check("app/data/india_mpa.geojson exists (fetch_india_mpa_data.py has been run)", geojson_path.exists())

if geojson_path.exists():
    import json
    with open(geojson_path) as f:
        raw = json.load(f)

    check("top-level type is FeatureCollection", raw.get("type") == "FeatureCollection")
    features = raw.get("features", [])
    check("at least one feature was fetched", len(features) > 0, f"got {len(features)}")
    print(f"  Total features fetched: {len(features)}")

    all_parse_ok = True
    for feat in features:
        try:
            shape(feat["geometry"])
        except Exception as e:
            all_parse_ok = False
            print(f"  FAIL to parse geometry for {feat.get('properties', {}).get('name')}: {e}")
    check("every feature's geometry is parseable by shapely (genuinely valid GeoJSON geometry)", all_parse_ok)

    has_attribution = all(
        "World Database on Protected Areas" in (feat["properties"].get("source") or "")
        for feat in features
    )
    check("every feature carries real WDPA attribution in its properties (never anonymous/unsourced)",
          has_attribution)

    has_wdpa_ids = all(feat["properties"].get("wdpa_site_id") is not None for feat in features)
    check("every feature carries a real WDPA site ID (traceable to the real source record)", has_wdpa_ids)

    # Geographic sanity check: a Gulf of Mannar area record should exist,
    # with real polygon geometry, at plausible real-world coordinates
    # (Tamil Nadu coast, roughly 8-10N / 78-80E) - not a placeholder, not
    # somewhere obviously wrong like the Arctic.
    mannar_features = [
        f for f in features
        if "mannar" in (f["properties"].get("name") or "").lower()
        or "mannar" in (f["properties"].get("name_english") or "").lower()
    ]
    check("a Gulf of Mannar area record exists in the real fetched data", len(mannar_features) > 0)

    mannar_polygon_features = [f for f in mannar_features if f["geometry"]["type"] != "Point"]
    check("at least one Gulf of Mannar record has REAL polygon geometry (not just a point)",
          len(mannar_polygon_features) > 0)

    if mannar_polygon_features:
        g = shape(mannar_polygon_features[0]["geometry"])
        minx, miny, maxx, maxy = g.bounds
        print(f"  Gulf of Mannar polygon bounds: lat {miny:.3f}-{maxy:.3f}, lon {minx:.3f}-{maxx:.3f}"
              f" (name_english={mannar_polygon_features[0]['properties'].get('name_english')!r},"
              f" wdpa_site_id={mannar_polygon_features[0]['properties'].get('wdpa_site_id')})")
        check("Gulf of Mannar polygon sits at the real, expected coordinates (8-10N, 78-80E, Tamil Nadu coast)",
              8.0 <= miny and maxy <= 10.0 and 78.0 <= minx and maxx <= 80.0,
              f"got lat {miny}-{maxy}, lon {minx}-{maxx}")
        check("Gulf of Mannar polygon's bounding box closely matches Section 14o's hand-built "
              "Wikipedia-sourced placeholder rectangle (8.75-9.25N, 78.20-79.25E) - a real confirmation "
              "the earlier approximation was reasonable",
              abs(miny - 8.75) < 0.3 and abs(maxy - 9.25) < 0.3 and abs(minx - 78.20) < 0.3 and abs(maxx - 79.25) < 0.3,
              f"got lat {miny}-{maxy}, lon {minx}-{maxx}")

    # Real data-quality issues found and handled by marine_protected_areas.py
    # itself (see that module's docstring) - confirmed present here too, so
    # this test documents WHY the loader needs the Point-exclusion and
    # buffer(0) repair, not just that it happens to work.
    point_only = [f for f in features if f["geometry"]["type"] in ("Point", "MultiPoint")]
    print(f"  Point-only records (no real boundary, excluded from proximity checks): {len(point_only)}")
    invalid_geoms = [f for f in features if f["geometry"]["type"] not in ("Point", "MultiPoint")
                      and not shape(f["geometry"]).is_valid]
    print(f"  Invalid/self-intersecting polygon records (repaired via buffer(0)): {len(invalid_geoms)}")
print()


# ---------- Test 1: a route through the REAL Gulf of Mannar MPA polygon ----------
print("=" * 70)
print("TEST 1: Route from Mandapam toward a point inside the REAL Gulf of Mannar MPA polygon")
print("(Mandapam is a real coastal town directly adjacent to the real park)")

_reset_mpa_cache()
mandapam = (9.2876, 79.1367)  # real town, mainland coast near Gulf of Mannar
# A real point verified (via direct shapely .representative_point()/bounds
# inspection of the actual fetched polygon) to sit inside/very near the
# real Gulf of Mannar Marine Biosphere Reserve archipelago - not a guess.
inside_real_mpa = (9.15, 78.95)
routes = generate_candidate_routes(mandapam, inside_real_mpa)

for route in routes:
    distances = [mpa_module.distance_to_nearest_mpa_km(wp["lat"], wp["lon"]) for wp in route["waypoints"]]
    check_mpa_proximity(route, distances, DEFAULT_MPA_WARNING_THRESHOLD_KM)
    print(f"  {route['label']:8s} distance_km={route['distance_km']:6.1f}  "
          f"mpa_distance_km={route['mpa_distance_km']:6.2f}  mpa_warning={route['mpa_warning']}")

check("at least one route triggers mpa_warning=True against the REAL polygon",
      any(r["mpa_warning"] is True for r in routes),
      f"got {[r['mpa_warning'] for r in routes]}")
check("no route's mpa_distance_km is None (real data is loaded, not the honest-unavailable fallback)",
      all(r["mpa_distance_km"] is not None for r in routes))
print()


# ---------- Test 2: existing Kochi -> PFZ route - no warnings of either kind ----------
print("=" * 70)
print("TEST 2: Kochi -> Kochi's nearest_pfz - expect NO boundary warning AND no MPA warning (real data)")

_reset_mpa_cache()
kochi = (9.9312, 76.2673)
kochi_pfz = (9.75, 75.95)  # same as test_boundary_geofencing.py's Scenario 2
routes = generate_candidate_routes(kochi, kochi_pfz)

for route in routes:
    boundary_distances = [distance_to_eez_boundary_km(wp["lat"], wp["lon"]) for wp in route["waypoints"]]
    check_boundary_proximity(route, boundary_distances, DEFAULT_BOUNDARY_WARNING_THRESHOLD_KM)
    mpa_distances = [mpa_module.distance_to_nearest_mpa_km(wp["lat"], wp["lon"]) for wp in route["waypoints"]]
    check_mpa_proximity(route, mpa_distances, DEFAULT_MPA_WARNING_THRESHOLD_KM)
    print(f"  {route['label']:8s} boundary_warning={route['boundary_warning']!s:5}  "
          f"mpa_warning={route['mpa_warning']!s:5}  mpa_distance_km={route['mpa_distance_km']:.1f}")

check("no route triggers boundary_warning", all(r["boundary_warning"] is False for r in routes))
check("no route triggers mpa_warning against the real MPA data (Kochi is genuinely ~240km away)",
      all(r["mpa_warning"] is False for r in routes))
print()


# ---------- Test 3: near the EEZ boundary but far from the real MPA - only EEZ should warn ----------
print("=" * 70)
print("TEST 3: Rameswaram -> Palk Strait boundary point - EEZ should warn, MPA should NOT (real-data false-positive check)")
print("(Palk Strait is north of Rameswaram; the real Gulf of Mannar polygon is south/west of it - different water bodies)")

_reset_mpa_cache()
rameswaram = (9.29, 79.31)
palk_strait_boundary_point = (9.15, 79.55)  # same as test_boundary_geofencing.py's Scenario 1
routes = generate_candidate_routes(rameswaram, palk_strait_boundary_point)

for route in routes:
    boundary_distances = [distance_to_eez_boundary_km(wp["lat"], wp["lon"]) for wp in route["waypoints"]]
    check_boundary_proximity(route, boundary_distances, DEFAULT_BOUNDARY_WARNING_THRESHOLD_KM)
    mpa_distances = [mpa_module.distance_to_nearest_mpa_km(wp["lat"], wp["lon"]) for wp in route["waypoints"]]
    check_mpa_proximity(route, mpa_distances, DEFAULT_MPA_WARNING_THRESHOLD_KM)
    print(f"  {route['label']:8s} boundary_warning={route['boundary_warning']!s:5} "
          f"(dist={route['boundary_distance_km']:.2f} km)   "
          f"mpa_warning={route['mpa_warning']!s:5} (dist={route['mpa_distance_km']:.2f} km)")

check("at least one route triggers boundary_warning (real EEZ proximity)",
      any(r["boundary_warning"] for r in routes))
check("NO route falsely triggers mpa_warning against the real MPA data (different water body)",
      all(r["mpa_warning"] is False for r in routes),
      f"got {[r['mpa_warning'] for r in routes]}")
print()


# ---------- Test 4: MPA data unavailable (simulated) - honest None, not fabricated False ----------
print("=" * 70)
print("TEST 4: MPA data unavailable (simulated missing file) - must be honest None, never a fabricated warning")
print("(real data now exists in this repo checkout, so this scenario is explicitly simulated,")
print(" not the genuine current state as it was before Section 14u - still real regression coverage")
print(" for a fresh checkout where scripts/fetch_india_mpa_data.py hasn't been run yet)")

with patch.object(mpa_module, "MPA_PATH", Path("/nonexistent/india_mpa.geojson")):
    _reset_mpa_cache()
    real_distance = mpa_module.distance_to_nearest_mpa_km(9.15, 79.47)
    check("distance_to_nearest_mpa_km returns None when no data file exists", real_distance is None, f"got {real_distance}")

route = {"id": "x", "label": "x"}
check_mpa_proximity(route, [None, None, None], DEFAULT_MPA_WARNING_THRESHOLD_KM)
check("mpa_distance_km is None (not 0, not a fabricated default)", route["mpa_distance_km"] is None)
check("mpa_warning is None (not False - 'unknown' must be distinguishable from 'confirmed safe')", route["mpa_warning"] is None)

_reset_mpa_cache()  # restore the real cache for anything that runs after this file
print()


# ---------- Summary ----------
print("=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed")
if failed == 0:
    print("All MPA geofencing checks pass, against the REAL WDPA/Protected Planet data.")
else:
    print("Some checks failed - review the FAIL lines above before considering this feature complete.")
