"""
News Handler
============
Handles the news intent: fetches RSS feeds, summarises with LLM,
caches in Obsidian vault (0-token cache) and in a local JSON file.
Routes directly to end_flow — news is curated content, Reviewer bypass is intentional.
"""
import structlog
from datetime import datetime
from zoneinfo import ZoneInfo
from langchain_core.messages import AIMessage

from src.tools.obsidian import ObsidianVaultTool
from src.tools.news import NewsFetcherTool
from src.agent.llm_client import llm, extract_tokens
from src.agent.utils import _sanitize_telegram_html

logger = structlog.get_logger()

MADRID_TZ = ZoneInfo("Europe/Madrid")


def _news_title() -> str:
    """Returns a formatted news header for today's date in Madrid timezone."""
    today = datetime.now(MADRID_TZ)
    return f"📰 *Noticias {today.day:02d}/{today.month:02d}/{today.year}*\n\n"


def handle_news(iterations: int, trace: list) -> dict:
    """
    Two-layer cache strategy:
      1. Obsidian vault: if today's digest already exists, serve it directly (0 LLM tokens).
      2. JSON cache in data/: raw RSS cached daily to avoid repeated HTTP calls.
      3. LLM summarisation only when no cache is available.
    News bypasses Reviewer because content is externally curated — not an LLM answer.
    """
    obs_tool = ObsidianVaultTool()
    title = _news_title()

    cached = obs_tool.get_today_news()
    if cached:
        logger.info("Serving news from Obsidian 0-token cache")
        # Prepend date title if not already present (idempotent guard)
        content = cached if cached.startswith("📰") else title + cached
        return {
            "iterations": iterations,
            "next_node": "end_flow",
            "messages": [AIMessage(content=content)],
            "agent_trace": trace + ["TechnicalArchitect"],
            "confidence_score": 0.95,
        }

    fetcher = NewsFetcherTool()
    news = fetcher.fetch_news()

    if not news:
        return {
            "iterations": iterations,
            "next_node": "end_flow",
            "messages": [AIMessage(content=(
                "⚠️ No se pudieron obtener noticias en este momento. Intenta de nuevo más tarde."
            ))],
            "agent_trace": trace + ["TechnicalArchitect"],
            "confidence_score": 0.5,
        }

    prompt_news = (
        "Resume estas noticias en español con bullets, máximo 400 palabras.\n"
        "IMPORTANTE: usa *Título* (un solo asterisco) para negrita — Telegram no soporta **doble**.\n"
        "Formato: [Emoji categoría] *Título* — _resumen breve_\n"
        "Categorías: 💻 Tech, 💰 Finanzas, 🌍 Internacional, 🏥 Salud, 🎭 Cultura\n"
        "Incluye el enlace de cada noticia entre paréntesis al final de cada bullet.\n"
        "No uses líneas ---  ni  # encabezados. Solo bullets con emojis.\n"
        f"Noticias: {str(news[:8])}"
    )

    try:
        response = llm.invoke(prompt_news)
        summary = response.content or ""
        inp, out = extract_tokens(response)
    except Exception as e:
        logger.error("News LLM summarisation failed", error=str(e))
        lines = [f"• *{n['title']}*" for n in news[:6]]
        fallback = title + "\n".join(lines)
        return {
            "iterations": iterations,
            "next_node": "end_flow",
            "messages": [AIMessage(content=fallback)],
            "agent_trace": trace + ["TechnicalArchitect"],
            "confidence_score": 0.6,
        }

    cleaned = _sanitize_telegram_html(summary)
    if len(cleaned) < 100:
        lines = [f"• *{n['title']}*" for n in news[:6]]
        cleaned = "\n".join(lines)

    # Compose final message with date title
    final = title + cleaned

    # Cache the body (without title) so the date title is always dynamically generated
    obs_tool.create_news_log(cleaned)

    return {
        "iterations": iterations,
        "next_node": "end_flow",
        "messages": [AIMessage(content=final)],
        "agent_trace": trace + ["TechnicalArchitect"],
        "confidence_score": 0.9,
        "_token_delta": (inp, out),
    }
