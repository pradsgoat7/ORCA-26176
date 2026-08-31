"""
Location resolution for anything beyond the known demo cities: free
geocoding via Open-Meteo, plus a coastal-proximity sanity check.
"""

import math
from typing import Optional

import requests

# Rough reference points spanning India's coastline (plus a couple of
# neighboring coastal cities), used only to sanity-check that a geocoded
# location is actually near the sea. We don't have real coastline geometry
# data, so this is a pragmatic distance-based heuristic, not a precise
# land/water boundary - documented as a known limitation.
COASTAL_REFERENCE_POINTS = [
    ("Kandla", 23.03, 70.22),
    ("Surat", 21.17, 72.83),
    ("Mumbai", 18.94, 72.84),
    ("Ratnagiri", 17.0, 73.3),
    ("Goa", 15.5, 73.8),
    ("Mangalore", 12.9, 74.8),
    ("Kochi", 9.93, 76.27),
    ("Thiruvananthapuram", 8.5, 76.9),
    ("Chennai", 13.08, 80.27),
    ("Puducherry", 11.9, 79.8),
    ("Visakhapatnam", 17.69, 83.22),
    ("Paradip", 20.3, 86.6),
    ("Digha", 21.6, 87.5),
    ("Karachi", 24.86, 67.0),
]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def is_near_coast(lat: float, lon: float, max_km: float = 120.0) -> bool:
    """True if within max_km of any reference coastal point. This is what
    prevents nonsense like 'safe to fish in Kashmir' - Open-Meteo's marine
    model apparently still returns some interpolated wave value even for
    landlocked, mountainous coordinates, so we can't rely on the marine API
    itself to reject a bad location - we have to check ourselves."""
    return any(
        haversine_km(lat, lon, ref_lat, ref_lon) <= max_km
        for _, ref_lat, ref_lon in COASTAL_REFERENCE_POINTS
    )


def geocode_location(name: str) -> Optional[dict]:
    """Resolves ANY location name to coordinates via Open-Meteo's free
    geocoding API - not just our known demo cities. Returns None on
    failure so the caller can fall back to the 'unknown location' error.

    Includes a sanity check: Open-Meteo's geocoding does fuzzy text search,
    not exact matching, so nonsense input like 'hii' can return a real but
    completely unrelated place (this actually happened - it matched 'Lake
    Havasu City'). Rejecting results where the first few letters don't
    match catches this without needing real NLP."""
    try:
        resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": name, "count": 1, "language": "en", "format": "json"},
            timeout=8,
        )
        resp.raise_for_status()
        results = resp.json().get("results")
        if not results:
            return None
        r = results[0]
        result_name = r["name"]

        prefix_len = min(3, len(name))
        if result_name.lower()[:prefix_len] != name.lower()[:prefix_len]:
            return None  # fuzzy match drifted too far from the input - reject it

        return {"name": result_name, "lat": r["latitude"], "lon": r["longitude"]}
    except Exception:
        return None
