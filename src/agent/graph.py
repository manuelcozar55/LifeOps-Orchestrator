from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

from src.agent.state import GraphState
from src.agent.nodes import (
    guardrail_node, orchestrator_node, domain_expert_node,
    technical_architect_node, reviewer_node
)
from src.tools.db_pool import get_shared_pool


def route_next(state: GraphState) -> str:
    """Pure routing function — reads `next_node` set by each agent."""
    node = state.get("next_node", "")
    if node in ("__end__", "end_flow", ""):
        return END
    return node


def build_graph() -> StateGraph:
    """Builds and compiles the LifeOps multi-agent LangGraph.

    Uses the application-wide shared ConnectionPool (src.tools.db_pool)
    for the PostgresSaver checkpointer, eliminating the duplicate pool
    that previously coexisted with DatabaseManager's own pool.
    """
    workflow = StateGraph(GraphState)

    # ── Register nodes ───────────────────────────────────────────
    workflow.add_node("guardrail",    guardrail_node)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("domain_expert", domain_expert_node)
    workflow.add_node("architect",    technical_architect_node)
    workflow.add_node("reviewer",     reviewer_node)

    # ── Entry point (Security First) ─────────────────────────────
    workflow.set_entry_point("guardrail")

    # ── Conditional edges ────────────────────────────────────────
    workflow.add_conditional_edges("guardrail",    route_next, {"orchestrator": "orchestrator", END: END})
    workflow.add_conditional_edges("orchestrator", route_next, {"domain_expert": "domain_expert", "architect": "architect", END: END})
    workflow.add_conditional_edges("domain_expert", route_next, {"architect": "architect", "reviewer": "reviewer", END: END})
    workflow.add_conditional_edges("architect",    route_next, {"reviewer": "reviewer", END: END})
    workflow.add_conditional_edges("reviewer",     route_next, {"orchestrator": "orchestrator", END: END})

    # ── Postgres Checkpointer (shared pool) ──────────────────────
    pool = get_shared_pool()
    memory = PostgresSaver(pool)
    memory.setup()

    return workflow.compile(checkpointer=memory)
