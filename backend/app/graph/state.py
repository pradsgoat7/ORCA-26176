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
    location_key: Optional[str]
    location_data: Optional[dict]
    weather: Optional[dict]
    ocean: Optional[dict]
    risk: Optional[dict]
    geospatial: Optional[dict]
    answer: Optional[str]
    error: Optional[str]
