"""Builds the LangGraph ``StateGraph`` for one customer-service turn."""

from langgraph.graph import END, START, StateGraph

from agent.config import AgentSettings
from agent.intent import IntentClassifier
from agent.nodes import Nodes, route_intent, route_start
from agent.state import AgentState
from agent.tools import AgentTools

REPLY_NODES = (
    "handoff",
    "answer_policy",
    "request_auth",
    "ask_details",
    "request_step_up",
    "run_account_tool",
    "greet",
    "clarify",
)


def build_graph(tools: AgentTools, settings: AgentSettings, classifier: IntentClassifier) -> StateGraph[AgentState]:
    """Wire nodes and conditional edges; compile the result with a checkpointer."""
    nodes = Nodes(tools, settings, classifier)
    graph = StateGraph(AgentState)

    graph.add_node("start_turn", nodes.start_turn)
    graph.add_node("authenticate", nodes.authenticate)
    graph.add_node("classify_intent", nodes.classify_intent)
    for name in REPLY_NODES:
        graph.add_node(name, getattr(nodes, name))
        graph.add_edge(name, END)

    graph.add_edge(START, "start_turn")
    graph.add_conditional_edges("start_turn", route_start, ["handoff", "authenticate"])
    graph.add_edge("authenticate", "classify_intent")
    graph.add_conditional_edges("classify_intent", route_intent, list(REPLY_NODES))
    return graph
