"""
Calendar Handler
================
Handles calendar_create, calendar_update, calendar_delete, calendar_query intents.
Destructive operations (delete) always require HIL confirmation before execution.
"""
import structlog
from langchain_core.messages import AIMessage

from src.tools.google_cli import GoogleCLITool
from src.agent.utils import _is_confirm

logger = structlog.get_logger()


def handle_calendar(intent: str, context: dict, iterations: int, trace: list) -> dict:
    """Routes to the appropriate Calendar sub-handler based on intent."""
    params = context.get("calendar_params", {})
    cli = GoogleCLITool()

    if "create" in intent:
        return _create(cli, params, iterations, trace)
    if "update" in intent:
        return _update(cli, params, iterations, trace)
    if "delete" in intent:
        return _request_delete_confirmation(cli, context, params, iterations, trace)
    if "query" in intent:
        return _query(cli, params, iterations, trace)

    return {
        "iterations": iterations,
        "next_node": "reviewer",
        "messages": [AIMessage(content="Acción de calendario no reconocida.")],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": 0.2,
    }


def exec_calendar_delete(context: dict, confirm_text: str, iterations: int, trace: list) -> dict:
    """Executes or cancels a calendar deletion after HIL confirmation."""
    event_id = context["delete_event_id"]
    event_title = context.get("delete_event_title", "")
    clean_ctx = {k: v for k, v in context.items() if k not in ("delete_event_id", "delete_event_title")}

    if not _is_confirm(confirm_text):
        return {
            "iterations": iterations,
            "awaiting_user_input": False,
            "active_context": clean_ctx,
            "next_node": "end_flow",
            "messages": [AIMessage(content="❌ Eliminación cancelada.")],
            "agent_trace": trace + ["TechnicalArchitect"],
        }

    ok = GoogleCLITool().delete_event(event_id)
    return {
        "iterations": iterations,
        "awaiting_user_input": False,
        "active_context": clean_ctx,
        "next_node": "reviewer",
        "messages": [AIMessage(
            content=f"✅ Evento **'{event_title}'** eliminado." if ok else "❌ Error al eliminar el evento."
        )],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": 0.9 if ok else 0.2,
    }


# ── Private sub-handlers ──────────────────────────────────────────

def _create(cli: GoogleCLITool, params: dict, iterations: int, trace: list) -> dict:
    title = params.get("title")
    start = params.get("start")
    if not title or not start:
        return {
            "iterations": iterations,
            "next_node": "reviewer",
            "messages": [AIMessage(content="⚠️ Necesito el título y la fecha/hora de inicio del evento.")],
            "agent_trace": trace + ["TechnicalArchitect"],
            "confidence_score": 0.3,
        }
    ok = cli.create_event(title, start, params.get("end") or start)
    return {
        "iterations": iterations,
        "next_node": "reviewer",
        "messages": [AIMessage(
            content=f"✅ Evento **'{title}'** creado en Google Calendar." if ok else "❌ Error al crear el evento."
        )],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": 0.9 if ok else 0.2,
    }


def _update(cli: GoogleCLITool, params: dict, iterations: int, trace: list) -> dict:
    title = params.get("title") or params.get("query")
    if not title:
        return {
            "iterations": iterations,
            "next_node": "reviewer",
            "messages": [AIMessage(content="⚠️ Indica el título del evento que quieres actualizar.")],
            "agent_trace": trace + ["TechnicalArchitect"],
            "confidence_score": 0.3,
        }
    events = cli.search_events(title, max_results=1)
    if not events:
        return {
            "iterations": iterations,
            "next_node": "reviewer",
            "messages": [AIMessage(content=f"No encontré ningún evento con '{title}' en el calendario.")],
            "agent_trace": trace + ["TechnicalArchitect"],
            "confidence_score": 0.4,
        }
    ok = cli.update_event(
        events[0]["id"],
        new_title=params.get("title"),
        new_start_dt=params.get("start"),
        new_end_dt=params.get("end"),
    )
    return {
        "iterations": iterations,
        "next_node": "reviewer",
        "messages": [AIMessage(
            content="✅ Evento actualizado." if ok else "❌ Error al actualizar el evento."
        )],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": 0.9 if ok else 0.2,
    }


def _request_delete_confirmation(
    cli: GoogleCLITool, context: dict, params: dict, iterations: int, trace: list
) -> dict:
    """Searches for the event and asks the user to confirm deletion (HIL)."""
    title = params.get("title") or params.get("query")
    if not title:
        return {
            "iterations": iterations,
            "next_node": "reviewer",
            "messages": [AIMessage(content="⚠️ Indica qué evento quieres eliminar.")],
            "agent_trace": trace + ["TechnicalArchitect"],
            "confidence_score": 0.3,
        }
    events = cli.search_events(title, max_results=1)
    if not events:
        return {
            "iterations": iterations,
            "next_node": "reviewer",
            "messages": [AIMessage(content=f"No encontré ningún evento con '{title}'.")],
            "agent_trace": trace + ["TechnicalArchitect"],
            "confidence_score": 0.4,
        }
    event = events[0]
    new_ctx = {**context, "delete_event_id": event["id"], "delete_event_title": event["summary"]}
    return {
        "iterations": iterations,
        "awaiting_user_input": True,
        "active_context": new_ctx,
        "next_node": "end_flow",
        "messages": [AIMessage(content=(
            f"⚠️ **Confirmación requerida**\n\n"
            f"¿Eliminar el evento **'{event['summary']}'** ({event['start'][:10]})?\n\n"
            "Responde **sí** para confirmar o **no** para cancelar."
        ))],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": 0.9,
    }


def _query(cli: GoogleCLITool, params: dict, iterations: int, trace: list) -> dict:
    query = params.get("query") or ""
    is_today = any(w in query.lower() for w in ["hoy", "today", "día", "dia"])
    if is_today:
        res = cli.get_todays_events() or "No hay eventos hoy en el calendario."
    else:
        events = cli.search_events(query, max_results=8)
        res = (
            "\n".join(f"• {e['start'][:16].replace('T', ' ')} — {e['summary']}" for e in events)
            if events else "No se encontraron eventos."
        )
    return {
        "iterations": iterations,
        "next_node": "reviewer",
        "messages": [AIMessage(content=res)],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": 0.85,
    }
