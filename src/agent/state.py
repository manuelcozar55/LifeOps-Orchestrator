from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class GraphState(TypedDict):
    """
    LangGraph shared state flowing through all agent nodes.

    Design decisions:
    - agent_trace: NO reducer (direct replacement). Guardrail resets to ["Guardrail"]
      at the start of each new request; subsequent nodes read current list and extend it.
      This avoids cross-request accumulation when using Postgres checkpointing.
    - turn_tokens: same no-reducer pattern. Guardrail resets to its own token cost,
      each LLM-calling node reads and accumulates on top. Enables accurate per-turn
      telemetry without looping over all accumulated messages.
    """
    messages: Annotated[List[BaseMessage], add_messages]

    # Security (set by Guardrail)
    is_secure: Optional[bool]
    security_alert: Optional[str]

    # Business state
    user_intent: Optional[str]          # e.g. "calendar_create", "obsidian_crud", "agenda_query" ...
    active_context: Dict[str, Any]      # Temporary data: event dicts, drafts, sync plans, obsidian requests
    error: Optional[str]                # Tool error description for retry loops
    calendar_action: Optional[str]      # "create" | "update" | "delete"
    obsidian_request: Optional[dict]    # Serialized ObsidianRequest for Architect consumption

    # Control flags
    awaiting_user_input: bool           # HIL: True when waiting for human confirmation
    iterations: int                     # Loop counter (guarded at MAX_ITERATIONS)
    next_node: str                      # Routing decision read by route_next()

    # Observability & Traceability
    # No reducer: each node reads current list and returns extended version.
    # Guardrail resets to ["Guardrail"] at the start of each new request.
    agent_trace: Optional[List[str]]
    confidence_score: Optional[float]   # 0.0–1.0, set by DomainExpert/Architect/Reviewer

    # Token telemetry — accumulated across all LLM calls within a single user turn.
    # No reducer: Guardrail resets to its own cost; each subsequent LLM-calling node
    # reads state["turn_tokens"] and adds its delta before returning.
    # telegram_bot reads result["turn_tokens"] to record usage per request.
    turn_tokens: Optional[Dict[str, int]]  # {"input": N, "output": N}
