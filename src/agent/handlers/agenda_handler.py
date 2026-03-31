"""
Agenda Handler
==============
Handles agenda_query intent: unified view merging Google Calendar events,
Obsidian meeting notes, and Obsidian tasks for a given date or query.
"""
import re
import structlog
from datetime import datetime
from langchain_core.messages import AIMessage

from src.tools.google_cli import GoogleCLITool
from src.tools.obsidian import ObsidianVaultTool, _parse_frontmatter
from src.agent.utils import _extract_meeting_title

logger = structlog.get_logger()


def handle_agenda_query(context: dict, messages: list, iterations: int, trace: list) -> dict:
    """Fetches from Google Calendar, Obsidian meetings and Obsidian tasks, merges them."""
    params = context.get("calendar_params", {})
    query = params.get("query") or (messages[-1].content if messages else "")
    date_filter = params.get("query_date")
    is_today = (
        any(w in query.lower() for w in ["hoy", "today", "agenda", "día", "dia"])
        or date_filter == datetime.now().strftime("%Y-%m-%d")
    )

    cal_section = _fetch_calendar(query, date_filter, is_today)
    meetings_section = _fetch_obsidian_meetings(query, date_filter, is_today)
    tasks_section = _fetch_obsidian_tasks(date_filter, is_today)

    date_label = datetime.now().strftime("%d/%m/%Y") if is_today else (date_filter or query)

    msg = (
        f"📅 *AGENDA COMBINADA — {date_label}*\n\n"
        "*🗓️ Google Calendar:*\n"
        f"{cal_section}\n\n"
        "*📓 Reuniones en Obsidian:*\n"
        f"{meetings_section}\n\n"
        "*✅ Tareas pendientes:*\n"
        f"{tasks_section}\n\n"
        "_💡 Di 'Sincroniza mis reuniones' para mantener Calendar y Obsidian al día._"
    )
    return {
        "iterations": iterations,
        "next_node": "reviewer",
        "messages": [AIMessage(content=msg)],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": 0.88,
    }


# ── Private helpers ────────────────────────────────────────────────────────────

def _fetch_calendar(query: str, date_filter: str, is_today: bool) -> str:
    """Returns formatted Google Calendar events."""
    try:
        cli = GoogleCLITool()
        if not cli.creds:
            return "_(sin credenciales Google — ejecuta auth\\_setup.py)_"
        if is_today:
            raw = cli.get_todays_events() or ""
            if not raw or "No hay eventos" in raw:
                return "_(sin eventos hoy en Calendar)_"
            # Format each line as a bullet if not already
            lines = [
                f"• {line.lstrip('• ').strip()}"
                for line in raw.splitlines()
                if line.strip()
            ]
            return "\n".join(lines)
        search_q = date_filter or query
        events = cli.search_events(search_q, max_results=8)
        if not events:
            return "_(sin eventos en Calendar para esa búsqueda)_"
        lines = []
        for e in events:
            start = e["start"][:16].replace("T", " ")
            lines.append(f"• {start} — {e['summary']}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("agenda_query: calendar error", error=str(e))
        return f"_(error Calendar: {str(e)[:80]})_"


def _fetch_obsidian_meetings(query: str, date_filter: str, is_today: bool) -> str:
    """Returns Obsidian meeting notes relevant to the query or date."""
    try:
        obs_tool = ObsidianVaultTool()
        all_meetings = obs_tool.list_items("meeting", date_filter=date_filter)
        today_str = datetime.now().strftime("%Y-%m-%d")

        relevant = []
        for m in all_meetings:
            meta = _parse_frontmatter(m.get("full_content", ""))
            fecha = meta.get("fecha", "")
            hora = meta.get("hora_inicio", meta.get("hora", ""))
            title_match = query.lower() in m.get("title", "").lower()
            if is_today:
                if fecha == today_str or not fecha:
                    relevant.append((hora or "—", fecha or "—", m))
            elif title_match or fecha == date_filter:
                relevant.append((hora or "—", fecha or "—", m))

        if not relevant:
            return "_(sin reuniones en Obsidian para esa búsqueda)_"

        lines = []
        for hora, fecha, m in sorted(relevant)[:6]:
            title = _extract_meeting_title(m["title"])
            hora_str = f" {hora}" if hora and hora != "—" else ""
            lines.append(f"• [{fecha}{hora_str}] {title}")
        return "\n".join(lines)

    except Exception as e:
        logger.warning("agenda_query: obsidian meetings error", error=str(e))
        return f"_(error Obsidian reuniones: {str(e)[:80]})_"


def _fetch_obsidian_tasks(date_filter: str, is_today: bool) -> str:
    """Returns Obsidian tasks due today (or matching date_filter)."""
    try:
        obs_tool = ObsidianVaultTool()
        # For today's agenda, fetch all tasks and filter by due date
        all_tasks = obs_tool.list_items("task")
        today_str = datetime.now().strftime("%Y-%m-%d")
        target_date = today_str if is_today else (date_filter or "")

        relevant = []
        for t in all_tasks:
            meta = _parse_frontmatter(t.get("full_content", ""))
            due = meta.get("fecha_limite", "") or meta.get("due", "") or meta.get("fecha", "")
            prio = meta.get("prioridad", "media").lower()

            if target_date:
                # Show tasks due on target_date OR tasks with no due date (if today)
                if due == target_date or (is_today and not due):
                    relevant.append((prio, t, due))
            else:
                relevant.append((prio, t, due))

        if not relevant:
            suffix = " para hoy" if is_today else (f" para {target_date}" if target_date else "")
            return f"_(sin tareas pendientes{suffix})_"

        # Sort: alta → media → baja
        _prio_order = {"alta": 0, "media": 1, "baja": 2}
        relevant.sort(key=lambda x: _prio_order.get(x[0], 1))

        lines = []
        for prio, t, due in relevant[:6]:
            raw_title = t["title"].replace(".md", "")
            # Strip leading date prefix (YYYY-MM-DD-)
            clean = re.sub(r"^\d{4}-\d{2}-\d{2}-?", "", raw_title)
            title = clean.replace("-", " ").strip().title()
            prio_emoji = "🔴" if prio == "alta" else "🟡" if prio == "media" else "🟢"
            due_str = f" _(vence {due})_" if due and due != today_str else ""
            lines.append(f"• {prio_emoji} {title}{due_str}")
        return "\n".join(lines)

    except Exception as e:
        logger.warning("agenda_query: obsidian tasks error", error=str(e))
        return f"_(error Obsidian tareas: {str(e)[:80]})_"
