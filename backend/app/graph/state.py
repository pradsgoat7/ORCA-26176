"""
Shared state passed between every agent in the LangGraph workflow.
Field names here must exactly match what every agent reads/writes -
this is the single source of truth for the state shape.
"""

from typing import TypedDict, Optional


class ORCAState(TypedDict, total=False):
    query: str
    language: str
    day_offset: int
    stakeholder: Optional[dict]
    route_request: Optional[dict]
    route_plan: Optional[dict]
    policy_request: Optional[dict]
    policy_answer: Optional[dict]
    location_key: Optional[str]
    location_data: Optional[dict]
    weather: Optional[dict]
    ocean: Optional[dict]  # includes salinity_psu, current_speed_ms, mixed_layer_depth_m (MOSDAC Ocean-Eye)
    risk: Optional[dict]
    geospatial: Optional[dict]
    answer: Optional[str]
    error: Optional[str]
