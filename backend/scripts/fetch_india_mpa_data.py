"""
One-time (re-runnable) setup script for India's Marine Protected Area
(MPA) geofencing data - fetches LIVE from Protected Planet's official API
(api.protectedplanet.net, maintained by UNEP-WCMC), using YOUR OWN API
token, rather than bundling/redistributing a bulk WDPA extract.

WHY THIS IS A LIVE FETCH, NOT A COMMITTED FILE (full writeup in
PROJECT_CONTEXT.md Section 14o): Protected Planet's own terms of use
state you "may not redistribute the WDPA Data... in whole or in part...
including... web downloads", and their legal page confirms this applies
equally to a country-level extract, not just the full global dataset.
Committing a saved india_mpa.geojson to this repo would BE exactly that
kind of redistribution. Instead, every developer runs this script
themselves, fetching data directly from Protected Planet's own server
using their OWN token - ORCA itself never redistributes anything.

SETUP:
1. Request a free API token at https://api.protectedplanet.net/request
   (approval is manual, not instant - budget a day or two, same as
   MOSDAC's original account process, Section 13a).
2. Add PROTECTEDPLANET_API_TOKEN=<your token> to backend/.env
3. From backend/: python3 scripts/fetch_india_mpa_data.py
   This writes app/data/india_mpa.geojson (gitignored - never commit it).

HONESTY NOTE - NOT YET RUN/VERIFIED END-TO-END IN THIS SESSION: written
against Protected Planet's real v4 API documentation
(api.protectedplanet.net/documentation, fetched and read directly) and a
real HTTP 401 response confirming this exact endpoint exists and expects
a token, but no API token was available to actually execute it. Unlike
every other data source in this project, this one has NOT been verified
by a real successful run - flagged honestly here rather than silently
assumed to work. Whoever obtains a real token should run this once and
sanity-check the output (a FeatureCollection with a few dozen Polygon/
MultiPolygon features - India has roughly 30 designated marine protected
areas) before relying on it.
"""

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # allow running as `python3 scripts/...` from backend/

from app.config import DATA_DIR, PROTECTEDPLANET_API_TOKEN  # noqa: E402

OUTPUT_PATH = DATA_DIR / "india_mpa.geojson"
API_URL = "https://api.protectedplanet.net/v4/protected_areas/search"
PER_PAGE = 50  # documented maximum for this endpoint


def fetch_all_pages() -> list:
    """Paginates through every MARINE protected area in India
    (country=IND, marine=true), requesting full polygon geometry -
    real, documented parameters confirmed directly against
    api.protectedplanet.net/documentation (country, marine, with_geometry,
    page, per_page)."""
    all_areas = []
    page = 1
    while True:
        resp = requests.get(
            API_URL,
            params={
                "token": PROTECTEDPLANET_API_TOKEN,
                "country": "IND",
                "marine": "true",
                "with_geometry": "true",
                "per_page": PER_PAGE,
                "page": page,
            },
            timeout=30,
        )
        resp.raise_for_status()
        areas = resp.json().get("protected_areas", [])
        if not areas:
            break
        all_areas.extend(areas)
        print(f"  fetched page {page}: {len(areas)} protected areas")
        if len(areas) < PER_PAGE:
            break  # last page
        page += 1
    return all_areas


def build_geojson(areas: list) -> dict:
    """Builds a standard FeatureCollection from the API's per-area
    'geojson' field, keeping real attribution properties (same spirit as
    india_eez.geojson's 'source' field, Section 13c) so every feature can
    always be traced back to the real WDPA record."""
    features = []
    for area in areas:
        geojson_feature = area.get("geojson")
        if not geojson_feature or not geojson_feature.get("geometry"):
            continue  # some records genuinely have no geometry - skip, don't fabricate one
        features.append({
            "type": "Feature",
            "geometry": geojson_feature["geometry"],
            "properties": {
                "name": area.get("name"),
                "name_english": area.get("name_english"),
                "wdpa_site_id": area.get("site_id"),
                "designation": (area.get("designation") or {}).get("name"),
                "iucn_category": (area.get("iucn_category") or {}).get("name"),
                "marine": area.get("marine"),
                "reported_area_km2": area.get("reported_area"),
                "source": (
                    "World Database on Protected Areas (WDPA), UNEP-WCMC and IUCN, "
                    "via api.protectedplanet.net - fetched live using this developer's "
                    "own API token, not redistributed by ORCA (PROJECT_CONTEXT.md Section 14o)"
                ),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def main():
    if not PROTECTEDPLANET_API_TOKEN:
        print("ERROR: PROTECTEDPLANET_API_TOKEN not set in backend/.env")
        print("Request a token at https://api.protectedplanet.net/request, then re-run this script.")
        return

    print("Fetching India's marine protected areas from Protected Planet's API...")
    areas = fetch_all_pages()
    print(f"Total marine protected areas fetched: {len(areas)}")

    geojson = build_geojson(areas)
    print(f"Features with usable geometry: {len(geojson['features'])}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(geojson, f)

    print(f"Done. Wrote {OUTPUT_PATH} (gitignored - do not commit this file).")


if __name__ == "__main__":
    main()
