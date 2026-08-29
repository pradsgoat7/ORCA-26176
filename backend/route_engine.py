"""
Marine route generation - Phase 2 of Route Optimization.

Pure geometry functions only - no live data fetching (that stays in
agents.py, reusing the exact same fetch_live_wind/fetch_live_marine
already used everywhere else in ORCA) and no risk scoring (that's
risk_engine.py, wired in during Phase 3). Keeping this file pure means
route generation is fully testable without any network access.
"""

import math


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _interpolate(p1, p2, t):
    """Linear interpolation between two (lat, lon) points at fraction t.
    Fine for the short coastal distances involved here - not correcting
    for great-circle curvature, which would be overkill for this scale."""
    return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)


def _offset_point(p1, p2, t, offset_km, side):
    """A point at fraction t along p1->p2, shifted perpendicular to the
    path by roughly offset_km. Uses a simple degrees-per-km approximation -
    accurate enough at this scale, not meant for precise navigation."""
    mid = _interpolate(p1, p2, t)
    dlat, dlon = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dlat, dlon) or 1e-9
    perp_lat, perp_lon = -dlon / length, dlat / length

    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * math.cos(math.radians(mid[0])) or 1e-6

    offset_lat = perp_lat * (offset_km / km_per_deg_lat) * side
    offset_lon = perp_lon * (offset_km / km_per_deg_lon) * side
    return (mid[0] + offset_lat, mid[1] + offset_lon)


def generate_candidate_routes(origin: tuple, destination: tuple, num_samples: int = 5) -> list:
    """Generates 3 candidate marine routes between origin and destination
    (lat, lon) tuples:
      - Direct: straight line
      - Route B / Route C: bent via a midpoint offset to each side

    This is a deliberately simple prototype approach - no real marine
    navigation charts, shipping lanes, or land-avoidance data are
    available to ORCA. It produces genuinely different paths so the risk
    engine (Phase 3) has something meaningful to compare, without
    pretending ORCA has routing authority it doesn't actually have."""
    distance_km = haversine_km(origin[0], origin[1], destination[0], destination[1])
    offset_km = max(5.0, distance_km * 0.15)  # bend scales with trip length

    def build_waypoints(bend_side):
        points = []
        for i in range(num_samples):
            t = i / (num_samples - 1) if num_samples > 1 else 0
            if bend_side == 0 or distance_km < 2:
                pt = _interpolate(origin, destination, t)
            else:
                bend_factor = math.sin(t * math.pi)  # 0 at ends, 1 at midpoint
                pt = _offset_point(origin, destination, t, offset_km * bend_factor, bend_side)
            points.append({"lat": round(pt[0], 5), "lon": round(pt[1], 5)})
        return points

    routes = [
        {"id": "route_direct", "label": "Direct", "waypoints": build_waypoints(0)},
        {"id": "route_b", "label": "Route B", "waypoints": build_waypoints(1)},
        {"id": "route_c", "label": "Route C", "waypoints": build_waypoints(-1)},
    ]

    for route in routes:
        wps = route["waypoints"]
        total = sum(
            haversine_km(wps[i]["lat"], wps[i]["lon"], wps[i + 1]["lat"], wps[i + 1]["lon"])
            for i in range(len(wps) - 1)
        )
        route["distance_km"] = round(total, 1)

    return routes


def estimate_travel_time_minutes(distance_km: float, speed_kmph: float = 15.0) -> int:
    """Rough estimate assuming a typical small fishing vessel speed
    (~8 knots / 15 km/h) - a prototype approximation, not vessel-specific
    data ORCA doesn't have."""
    if distance_km <= 0:
        return 0
    return round((distance_km / speed_kmph) * 60)


def score_route(route: dict, sample_overall_scores: list, sample_metrics_lists: list) -> dict:
    """Aggregates per-sample Risk Engine outputs into one route-level risk
    score. Uses the WORST sample along the route - a route is only as safe
    as its most hazardous point, not its average. Does NOT compute any risk
    formula itself: sample_overall_scores/sample_metrics_lists must already
    come from the existing Risk Engine (calculate_all_metrics)."""
    worst_idx = max(range(len(sample_overall_scores)), key=lambda i: sample_overall_scores[i])
    route["route_risk_score"] = sample_overall_scores[worst_idx]

    worst_metrics = sample_metrics_lists[worst_idx]
    top_metric = max(worst_metrics, key=lambda m: m["score"])
    route["primary_risk_factor"] = top_metric["name"] if top_metric["score"] > 0 else "No significant hazard"
    return route


def select_recommended_route(scored_routes: list, distance_penalty_per_km: float = 2.0) -> dict:
    """Combines route risk with a distance penalty (relative to the
    shortest candidate) to pick the recommended route - explicitly NOT
    'shortest wins'. A safer route can win despite being longer; an
    excessively long detour still loses out even if marginally safer.
    distance_penalty_per_km=2.0 means each extra km costs 2 risk-equivalent
    points - tuned so the spec's own example (17km/risk78 vs 21km/risk24)
    correctly picks the 21km route, matching the spec's expected outcome."""
    min_distance = min(r["distance_km"] for r in scored_routes)
    for r in scored_routes:
        extra_km = max(0.0, r["distance_km"] - min_distance)
        r["combined_score"] = round(r["route_risk_score"] + extra_km * distance_penalty_per_km, 1)

    best = min(scored_routes, key=lambda r: r["combined_score"])
    for r in scored_routes:
        r["is_recommended"] = (r["id"] == best["id"])
    return best


def build_route_explanation(recommended: dict, all_routes: list) -> str:
    """Deterministic explanation built from the actual computed numbers -
    never invented. Can be spoken as-is, or reworded later by the LLM
    synthesis layer without changing the underlying facts."""
    shortest = min(all_routes, key=lambda r: r["distance_km"])

    if recommended["id"] == shortest["id"]:
        return (f"{recommended['label']} is both the shortest option and has the lowest marine risk "
                f"({recommended['route_risk_score']}/100).")

    extra_km = round(recommended["distance_km"] - shortest["distance_km"], 1)
    return (f"{recommended['label']} is approximately {extra_km} km longer than the shortest route, "
            f"but has notably lower marine risk ({recommended['route_risk_score']}/100 vs "
            f"{shortest['route_risk_score']}/100 for the shortest route), which is elevated mainly "
            f"due to {shortest['primary_risk_factor'].lower()}.")