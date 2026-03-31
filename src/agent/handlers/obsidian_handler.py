"""
Obsidian Handler
================
Handles obsidian_crud intent: create, read, update, delete, list, inbox operations
against the local Obsidian markdown vault.
"""
import structlog
from datetime import datetime
from langchain_core.messages import AIMessage

from src.tools.obsidian import ObsidianVaultTool
from src.agent.utils import _format_obsidian_list

logger = structlog.get_logger()


def handle_obsidian(context: dict, messages: list, iterations: int, trace: list) -> dict:
    """Dispatches Obsidian CRUD operations based on the action extracted by DomainExpert."""
    req = context.get("obsidian_request", {})
    action = str(req.get("action") or "").lower()
    item_type = str(req.get("type") or "task").lower()
    tool = ObsidianVaultTool()
    date_filter = req.get("query_date")

    if action == "list":
        items = tool.list_items(item_type, date_filter=date_filter)
        res = _format_obsidian_list(items, item_type, date_filter=date_filter)
        confidence = 0.95

    elif action == "read":
        data = tool.get_note(req.get("title") or "", item_type)
        res = f"📝 **{data['title']}**\n\n{data['content']}" if data["success"] else data["message"]
        confidence = 0.9 if data.get("success") else 0.4

    elif action in ("create", "update"):
        data = tool.upsert_note(
            title=req.get("title") or "Sin título",
            item_type=item_type,
            content=req.get("content") or "",
            metadata={
                "tipo": item_type,
                "prio": req.get("prio"),
                "fecha_limite": req.get("due"),
                "fecha": req.get("due") or datetime.now().strftime("%Y-%m-%d"),
            },
        )
        res = data["message"]
        confidence = 0.9

    elif action == "delete":
        data = tool.delete_note(req.get("title") or "", item_type)
        res = data["message"]
        confidence = 0.85

    elif action == "inbox":
        text = req.get("content") or (messages[-1].content if messages else "")
        tool.append_inbox(text)
        res = "✅ Añadido al inbox de Obsidian"
        confidence = 0.95

    else:
        res = f"Acción '{action}' no reconocida. Disponibles: create, read, update, delete, list, inbox."
        confidence = 0.3

    return {
        "iterations": iterations,
        "next_node": "reviewer",
        "messages": [AIMessage(content=res)],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": confidence,
    }
