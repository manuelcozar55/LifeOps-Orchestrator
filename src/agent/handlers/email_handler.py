"""
Email Handler
=============
Handles email, email_query and email_unread intents.
email / email_unread use HIL confirmation before sending.

Natural language support:
  - "revisa mi último correo" / "dame mi último correo sin leer" → email_unread
  - When 'último'/'reciente'/'last'/'recent'/'one' is detected in query_text,
    only the most recent unread email is fetched and a draft is proposed.
"""
import re
import structlog
from langchain_core.messages import AIMessage

from src.tools.google_cli import GoogleCLITool
from src.agent.llm_client import llm, extract_tokens
from src.agent.utils import _is_confirm

logger = structlog.get_logger()

_LAST_PATTERNS = re.compile(
    r"\b(último|ultima|último|last|reciente|recent|one|uno)\b", re.IGNORECASE
)


def _wants_last_only(context: dict) -> bool:
    """Returns True when the user's query refers to a single most-recent email."""
    query = context.get("email_query") or context.get("query_text") or ""
    return bool(_LAST_PATTERNS.search(query))


def handle_email(intent: str, context: dict, iterations: int, trace: list) -> dict:
    """Dispatches to email_query or email compose (with HIL)."""
    if intent == "email_query":
        return _query(context, iterations, trace)
    return _compose_with_hil(context, iterations, trace)


def handle_email_unread(context: dict, iterations: int, trace: list) -> dict:
    """Fetches unread Gmail, summarises with LLM, proposes a reply draft for HIL approval.

    Adapts to natural language:
    - Generic ("correos sin leer") → fetches up to 3 unread emails, picks most important.
    - Specific ("último correo", "dame el último") → fetches only 1 (most recent) email.
    """
    cli = GoogleCLITool()

    # Distinguish between "no credentials" and "no emails"
    if not cli.creds:
        return {
            "iterations": iterations,
            "next_node": "reviewer",
            "messages": [AIMessage(content=(
                "❌ *No hay credenciales de Google configuradas.*\n\n"
                "Para activar Gmail, ejecuta `python scripts/auth_setup.py` en el host "
                "y asegúrate de que `token.json` está disponible en la ruta configurada "
                "(`GOOGLE_TOKEN_PATH` en .env)."
            ))],
            "agent_trace": trace + ["TechnicalArchitect"],
            "confidence_score": 0.1,
        }

    last_only = _wants_last_only(context)
    max_fetch = 1 if last_only else 5

    emails = cli.search_emails("is:unread", max_results=max_fetch)

    if not emails:
        return {
            "iterations": iterations,
            "next_node": "reviewer",
            "messages": [AIMessage(content="✅ No tienes correos sin leer en este momento.")],
            "agent_trace": trace + ["TechnicalArchitect"],
            "confidence_score": 0.95,
        }

    # Enrich with full body (respect the max_fetch cap already applied)
    enriched = []
    for e in emails[:3]:
        body = cli.get_email_body(e["id"])
        enriched.append({**e, "body": body})

    email_blocks = []
    for i, e in enumerate(enriched, 1):
        email_blocks.append(
            f"[{i}] De: {e['from']}\n"
            f"    Asunto: {e['subject']}\n"
            f"    Fragmento: {e['snippet'][:200]}\n"
            f"    Cuerpo: {e['body'][:500]}"
        )

    if last_only:
        # Focused prompt: single email, always propose draft
        summary_prompt = (
            "Eres un asistente ejecutivo experto. Analiza este correo no leído y:\n"
            "1. Resúmelo en 2-3 frases.\n"
            "2. Propón un borrador de respuesta profesional en español.\n\n"
            "CORREO:\n" + "\n\n".join(email_blocks) + "\n\n"
            "Formato de respuesta:\n"
            "📬 ÚLTIMO CORREO SIN LEER\n"
            "[resumen del correo]\n\n"
            "📝 BORRADOR DE RESPUESTA:\n"
            "Para: [email]\n"
            "Asunto: Re: [asunto]\n\n"
            "[cuerpo del borrador]\n\n"
            "---DRAFT_SEP---\n"
            "to:[email_destinatario]\n"
            "subject:Re: [asunto]\n"
            "body:[cuerpo completo del borrador]"
        )
    else:
        summary_prompt = (
            "Eres un asistente ejecutivo experto. Analiza estos correos no leídos y:\n"
            "1. Resume cada uno en 1-2 frases.\n"
            "2. Identifica el más importante/urgente.\n"
            "3. Propón un borrador de respuesta profesional en español para ese correo.\n\n"
            "CORREOS:\n" + "\n\n".join(email_blocks) + "\n\n"
            "Formato de respuesta:\n"
            "📬 RESUMEN DE CORREOS SIN LEER\n"
            "[resúmenes numerados]\n\n"
            "📝 BORRADOR SUGERIDO (para el más importante):\n"
            "Para: [email]\n"
            "Asunto: Re: [asunto]\n\n"
            "[cuerpo del borrador]\n\n"
            "---DRAFT_SEP---\n"
            "to:[email_destinatario]\n"
            "subject:Re: [asunto]\n"
            "body:[cuerpo completo del borrador]"
        )

    try:
        response = llm.invoke(summary_prompt)
        raw = response.content or ""
        inp, out = extract_tokens(response)
    except Exception as e:
        return {
            "iterations": iterations,
            "next_node": "reviewer",
            "messages": [AIMessage(content=f"❌ Error al analizar correos: {str(e)[:150]}")],
            "agent_trace": trace + ["TechnicalArchitect"],
            "confidence_score": 0.2,
        }

    draft = {}
    if "---DRAFT_SEP---" in raw:
        parts = raw.split("---DRAFT_SEP---")
        display_part = parts[0].strip()
        meta_part = parts[1].strip() if len(parts) > 1 else ""
        for line in meta_part.splitlines():
            if line.startswith("to:"):
                draft["to"] = line[3:].strip()
            elif line.startswith("subject:"):
                draft["subject"] = line[8:].strip()
            elif line.startswith("body:"):
                draft["body"] = line[5:].strip()
    else:
        display_part = raw

    msg_lines = [display_part.strip()]
    if not last_only:
        msg_lines.append(f"\n_📬 {len(emails)} correo(s) sin leer en total._")

    if draft.get("to"):
        msg_lines.append(
            "\n\n¿Confirmas el envío de este borrador?\n"
            "Responde *sí* para enviar o *no* para cancelar."
        )
        new_ctx = {**context, "unread_reply_draft": draft, "unread_reply_pending": True}
        return {
            "iterations": iterations,
            "awaiting_user_input": True,
            "active_context": new_ctx,
            "next_node": "end_flow",
            "messages": [AIMessage(content="\n".join(msg_lines))],
            "agent_trace": trace + ["TechnicalArchitect"],
            "confidence_score": 0.88,
            "_token_delta": (inp, out),
        }

    return {
        "iterations": iterations,
        "next_node": "reviewer",
        "messages": [AIMessage(content=display_part.strip())],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": 0.8,
        "_token_delta": (inp, out),
    }


def exec_email_send(context: dict, confirm_text: str, iterations: int, trace: list) -> dict:
    """Sends or cancels the composed email after HIL confirmation."""
    draft = context.get("draft", {})
    clean_ctx = {k: v for k, v in context.items() if k != "draft_pending_approval"}

    if not _is_confirm(confirm_text):
        return {
            "iterations": iterations,
            "awaiting_user_input": False,
            "active_context": clean_ctx,
            "next_node": "end_flow",
            "messages": [AIMessage(content="❌ Envío cancelado.")],
            "agent_trace": trace + ["TechnicalArchitect"],
        }

    ok = GoogleCLITool().send_email(
        draft.get("to", ""), draft.get("subject", ""), draft.get("body", "")
    )
    return {
        "iterations": iterations,
        "awaiting_user_input": False,
        "active_context": clean_ctx,
        "next_node": "reviewer",
        "messages": [AIMessage(
            content=f"📧 Email enviado a {draft.get('to')}." if ok else "❌ Error al enviar."
        )],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": 0.95 if ok else 0.2,
    }


def exec_unread_reply(context: dict, confirm_text: str, iterations: int, trace: list) -> dict:
    """Sends or cancels the reply draft proposed after reading unread emails."""
    draft = context.get("unread_reply_draft", {})
    clean_ctx = {k: v for k, v in context.items()
                 if k not in ("unread_reply_draft", "unread_reply_pending")}

    if not _is_confirm(confirm_text):
        return {
            "iterations": iterations,
            "awaiting_user_input": False,
            "active_context": clean_ctx,
            "next_node": "end_flow",
            "messages": [AIMessage(content="❌ Envío cancelado.")],
            "agent_trace": trace + ["TechnicalArchitect"],
        }

    ok = GoogleCLITool().send_email(
        draft.get("to", ""), draft.get("subject", ""), draft.get("body", "")
    )
    return {
        "iterations": iterations,
        "awaiting_user_input": False,
        "active_context": clean_ctx,
        "next_node": "reviewer",
        "messages": [AIMessage(
            content=f"📧 Respuesta enviada a {draft.get('to')}." if ok else "❌ Error al enviar la respuesta."
        )],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": 0.95 if ok else 0.2,
    }


# ── Private sub-handlers ──────────────────────────────────────────

def _query(context: dict, iterations: int, trace: list) -> dict:
    query = context.get("query") or ""
    emails = GoogleCLITool().search_emails(query, max_results=5)
    if emails:
        lines = [f"📧 **Emails encontrados** ({len(emails)}):\n"]
        for e in emails:
            snippet = e.get("snippet", "")[:100]
            lines.append(f"• **{e['subject']}**\n  De: {e['from']}\n  _{snippet}_")
        msg = "\n\n".join(lines)
    else:
        msg = "No se encontraron emails con esa búsqueda."
    return {
        "iterations": iterations,
        "next_node": "reviewer",
        "messages": [AIMessage(content=msg)],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": 0.85,
    }


def _compose_with_hil(context: dict, iterations: int, trace: list) -> dict:
    draft = context.get("draft", {})
    preview = (
        f"📧 **Borrador de correo**\n\n"
        f"**Para:** {draft.get('to', '?')}\n"
        f"**Asunto:** {draft.get('subject', '?')}\n\n"
        f"{draft.get('body', '')}\n\n"
        "¿Confirmas el envío? Responde **sí** para enviar o **no** para cancelar."
    )
    new_ctx = {**context, "draft_pending_approval": True}
    return {
        "iterations": iterations,
        "awaiting_user_input": True,
        "active_context": new_ctx,
        "next_node": "end_flow",
        "messages": [AIMessage(content=preview)],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": 0.88,
    }
