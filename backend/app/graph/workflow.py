"""
Builds the LangGraph workflow and exposes run_query() as the single
entry point the API layer calls. The graph topology (fan-out/barrier
structure) is unchanged from the original monolithic agents.py -
only the imports moved.
"""

from langgraph.graph import StateGraph, END

from app.graph.state import ORCAState
from app.graph.agents.language import language_node
from app.graph.agents.stakeholder import stakeholder_agent
from app.graph.agents.route_detection import route_detection_agent
from app.graph.agents.route_planning import route_planning_agent
from app.graph.agents.planner import planner_agent
from app.graph.agents.weather import weather_agent
from app.graph.agents.ocean import ocean_agent
from app.graph.agents.geospatial import geospatial_agent
from app.graph.agents.risk import risk_agent
from app.graph.agents.synthesis import synthesis_agent


def build_graph():
    graph = StateGraph(ORCAState)
    graph.add_node("language_node", language_node)
    graph.add_node("planner_node", planner_agent)
    graph.add_node("stakeholder_node", stakeholder_agent)
    graph.add_node("route_detection_node", route_detection_agent)
    graph.add_node("route_planning_node", route_planning_agent)
    graph.add_node("weather_node", weather_agent)
    graph.add_node("ocean_node", ocean_agent)
    graph.add_node("risk_node", risk_agent)
    graph.add_node("geospatial_node", geospatial_agent)
    graph.add_node("synthesis_node", synthesis_agent)

    graph.set_entry_point("language_node")
    graph.add_edge("language_node", "planner_node")

    # Fan-out: the Planner dispatches to all specialist agents at once,
    # each running independently off the Planner's output.
    graph.add_edge("planner_node", "weather_node")
    graph.add_edge("planner_node", "ocean_node")
    graph.add_edge("planner_node", "geospatial_node")
    graph.add_edge("planner_node", "stakeholder_node")
    graph.add_edge("planner_node", "route_detection_node")

    # Risk agent acts as the sync point: it only reasons over weather+ocean
    # data, but waiting on all these edges (including geospatial and
    # stakeholder) means it only fires once every specialist has genuinely
    # finished - avoiding a race where Synthesis could start before every
    # agent has reported back.
    graph.add_edge("weather_node", "risk_node")
    graph.add_edge("ocean_node", "risk_node")
    graph.add_edge("geospatial_node", "risk_node")
    graph.add_edge("stakeholder_node", "risk_node")

    # route_planning_node depends on route_detection_node's output, so it
    # can't be a same-depth sibling of weather/ocean/etc - it must come
    # AFTER route_detection_node, then join synthesis_node at the same
    # depth as risk_node to avoid a sync-race bug.
    graph.add_edge("route_detection_node", "route_planning_node")

    graph.add_edge("risk_node", "synthesis_node")
    graph.add_edge("route_planning_node", "synthesis_node")
    graph.add_edge("synthesis_node", END)

    return graph.compile()


orca_graph = build_graph()


def run_query(query: str) -> ORCAState:
    initial_state: ORCAState = {"query": query}
    result = orca_graph.invoke(initial_state)
    return result
