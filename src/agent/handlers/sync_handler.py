"""
Sync Handler
============
Handles sync_preview intent and its HIL executor.
Builds an Obsidian ↔ Calendar diff, presents it for approval, then executes.

Fix: sync now reads hora_inicio / hora_fin from Obsidian frontmatter instead of
hardcoding every event at 10:00–11:00. Falls back to 09:00–10:00 when absent.
"""
import re
import structlog
from datetime import datetime
from langchain_core.messages import AIMessage

from src.tools.google_cli import GoogleCLITool
from src.tools.obsidian import ObsidianVaultTool, _parse_frontmatter
from src.agent.utils import _slugify_title, _extract_meeting_title, _is_confirm, _is_cancel

logger = structlog.get_logger()

# Default times used when an Obsidian meeting has no time metadata.
_DEFAULT_START = "09:00"
_DEFAULT_END   = "10:00"
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def handle_sync_preview(context: dict, iterations: int, trace: list) -> dict:
    """
    Builds an Obsidian ↔ Calendar diff and presents it for HIL approval.
    Slug-based title matching avoids false positives between similar but distinct events.
    """
    cli = GoogleCLITool()
    obs_tool = ObsidianVaultTool()

    try:
        cal_events = cli.search_events("", max_results=30)
    except Exception as e:
        cal_events = []
        logger.warning("sync_preview: calendar fetch failed", error=str(e))

    try:
        obs_meetings = obs_tool.list_items("meeting")
    except Exception as e:
        obs_meetings = []
        logger.warning("sync_preview: obsidian fetch failed", error=str(e))

    cal_by_slug: dict = {
        _slugify_title(e.get("summary", "")): e
        for e in cal_events
        if _slugify_title(e.get("summary", ""))
    }
    obs_by_slug: dict = {}
    for m in obs_meetings:
        clean_title = _extract_meeting_title(m["title"])
        slug = _slugify_title(clean_title)
        if slug:
            obs_by_slug[slug] = {**m, "_clean_title": clean_title}

    only_in_obs = [obs_by_slug[s] for s in obs_by_slug if s not in cal_by_slug]
    only_in_cal = [cal_by_slug[s] for s in cal_by_slug if s not in obs_by_slug]
    synced_count = sum(1 for s in obs_by_slug if s in cal_by_slug)

    if not only_in_obs and not only_in_cal:
        return {
            "iterations": iterations,
            "next_node": "reviewer",
            "messages": [AIMessage(content=(
                f"🎉 **¡Todo sincronizado!**\n\n"
                f"Obsidian y Google Calendar comparten {synced_count} elemento(s). No hay nada que hacer."
            ))],
            "agent_trace": trace + ["TechnicalArchitect"],
            "confidence_score": 0.95,
        }

    lines = ["🔄 **PLAN DE SINCRONIZACIÓN**\n*Obsidian ↔ Google Calendar*\n"]

    if only_in_obs:
        lines.append(f"📤 **Añadir al Calendar** ({len(only_in_obs)} de Obsidian):")
        for m in only_in_obs[:7]:
            meta = _parse_frontmatter(m.get("full_content", ""))
            fecha = meta.get("fecha", "sin fecha")
            hora = meta.get("hora_inicio", _DEFAULT_START)
            lines.append(f"  ➕ {m['_clean_title']} ({fecha} {hora})")

    if only_in_cal:
        lines.append(f"\n📥 **Añadir a Obsidian** ({len(only_in_cal)} de Calendar):")
        for e in only_in_cal[:7]:
            lines.append(f"  ➕ {e['summary']} ({e['start'][:10]})")

    if synced_count:
        lines.append(f"\n✅ **Ya sincronizados:** {synced_count} elemento(s).")

    lines.append(
        "\n\n¿Confirmas la sincronización?\n"
        "Responde **sí** para ejecutar o **no** para cancelar."
    )

    new_ctx = {
        **context,
        "sync_plan": {
            "to_add_to_calendar": only_in_obs,
            "to_add_to_obsidian": only_in_cal,
        },
    }
    return {
        "iterations": iterations,
        "awaiting_user_input": True,
        "active_context": new_ctx,
        "next_node": "end_flow",
        "messages": [AIMessage(content="\n".join(lines))],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": 0.9,
    }


def exec_sync(context: dict, confirm_text: str, iterations: int, trace: list) -> dict:
    """Executes or cancels the stored sync plan after HIL confirmation."""
    sync_plan = context["sync_plan"]
    clean_ctx = {k: v for k, v in context.items() if k != "sync_plan"}

    if _is_cancel(confirm_text) or not _is_confirm(confirm_text):
        return {
            "iterations": iterations,
            "awaiting_user_input": False,
            "active_context": clean_ctx,
            "next_node": "end_flow",
            "messages": [AIMessage(content="❌ Sincronización cancelada.")],
            "agent_trace": trace + ["TechnicalArchitect"],
        }

    cli = GoogleCLITool()
    obs_tool = ObsidianVaultTool()
    created_cal, created_obs, errors = 0, 0, []

    for meeting in sync_plan.get("to_add_to_calendar", []):
        try:
            title = meeting.get("_clean_title") or _extract_meeting_title(meeting.get("title", "Reunión"))
            meta = _parse_frontmatter(meeting.get("full_content", ""))
            date_str = meta.get("fecha") or datetime.now().strftime("%Y-%m-%d")

            hora_inicio = meta.get("hora_inicio", _DEFAULT_START)
            hora_fin = meta.get("hora_fin", _DEFAULT_END)
            # Sanitize: ensure HH:MM format; reset to default if malformed
            if not _TIME_RE.match(str(hora_inicio)):
                hora_inicio = _DEFAULT_START
            if not _TIME_RE.match(str(hora_fin)):
                hora_fin = _DEFAULT_END

            ok = cli.create_event(title, f"{date_str}T{hora_inicio}:00", f"{date_str}T{hora_fin}:00")
            if ok:
                created_cal += 1
        except Exception as e:
            errors.append(f"Calendar←{str(e)[:60]}")

    for event in sync_plan.get("to_add_to_obsidian", []):
        try:
            title = event.get("summary", "Reunión")
            date = event.get("start", "")[:10]
            obs_tool.upsert_note(
                title, "meeting",
                f"Reunión importada de Google Calendar.\nFecha: {date}",
                metadata={"tipo": "reunion", "fecha": date, "fuente": "google_calendar"},
            )
            created_obs += 1
        except Exception as e:
            errors.append(f"Obsidian←{str(e)[:60]}")

    msg = (
        f"✅ **Sincronización completada**\n\n"
        f"• 📤 {created_cal} evento(s) creado(s) en Google Calendar\n"
        f"• 📥 {created_obs} reunión/es creada(s) en Obsidian"
    )
    if errors:
        msg += f"\n\n⚠️ {len(errors)} error(es):\n" + "\n".join(f"  • {e}" for e in errors[:3])

    return {
        "iterations": iterations,
        "awaiting_user_input": False,
        "active_context": clean_ctx,
        "next_node": "reviewer",
        "messages": [AIMessage(content=msg)],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": 0.9 if not errors else 0.55,
    }


