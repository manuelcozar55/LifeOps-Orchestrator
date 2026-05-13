import os
import re
import queue
import weakref
import asyncio
import structlog
from datetime import time as dtime
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from telegram.constants import ParseMode
from langchain_core.messages import HumanMessage, AIMessage

from src.agent.graph import build_graph
from src.tools.database import DatabaseManager

logger = structlog.get_logger()
db = DatabaseManager()
MADRID_TZ = ZoneInfo("Europe/Madrid")

# ─────────────────────────────────────────────────────────────────
#  GLOBAL — LangGraph instance
# ─────────────────────────────────────────────────────────────────
graph_app = build_graph()

# Per-chat locks to prevent concurrent executions.
# WeakValueDictionary: entries are garbage-collected automatically when no active
# coroutine holds a reference to the lock, preventing unbounded memory growth.
_chat_locks: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def get_chat_lock(chat_id: int) -> asyncio.Lock:
    """Returns (or creates) a per-chat asyncio.Lock."""
    lock = _chat_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _chat_locks[chat_id] = lock
    return lock


# ─────────────────────────────────────────────────────────────────
#  TELEMETRY
# ─────────────────────────────────────────────────────────────────
def record_tokens(chat_id: str, input_tokens: int, output_tokens: int) -> None:
    """Persist LLM tokens in Supabase."""
    if input_tokens > 0 or output_tokens > 0:
        db.record_usage(chat_id, input_tokens, output_tokens)


def _check_budget(chat_id: int) -> tuple[bool, str]:
    """Returns (over_limit, warning_message).

    Checks the daily token budget for this chat. If the limit is exceeded
    the caller should send the message and skip graph invocation.
    """
    over, used, limit = db.check_daily_budget(str(chat_id))
    if over:
        pct = int(used / limit * 100) if limit else 100
        msg = (
            f"⚠️ *Límite diario de tokens alcanzado* ({used:,} / {limit:,} tokens, {pct}%)\n\n"
            "Has consumido el presupuesto diario de tokens LLM. "
            "El límite se restablece automáticamente mañana a las 00:00.\n\n"
            "Usa /stats para ver el detalle del consumo."
        )
        return True, msg
    return False, ""


# ─────────────────────────────────────────────────────────────────
#  TEXT UTILITIES
# ─────────────────────────────────────────────────────────────────
def _detect_html(text: str) -> bool:
    """Returns True if the message already contains HTML anchor tags."""
    return bool(re.search(r"<a\s+href=", text, re.IGNORECASE))


def _sanitize_markdown(text: str) -> str:
    """Fixes common LLM Markdown for Telegram MarkdownV1 compatibility.

    - Converts **bold** → *bold* (Telegram only supports single asterisk)
    - Removes standalone '---' horizontal rules (not supported, can break parsing)
    - Removes '# heading' lines (not supported, renders as literal text with #)
    - Removes '> blockquote' lines (not supported in MarkdownV1)
    """
    # ** → * (must run before other rules to avoid double processing)
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text, flags=re.DOTALL)
    # Remove standalone horizontal rules
    text = re.sub(r'(?m)^---+\s*$', '', text)
    # Remove # headings (keep content, strip the # prefix)
    text = re.sub(r'(?m)^#{1,6}\s+', '', text)
    # Remove > blockquote markers
    text = re.sub(r'(?m)^>\s*', '', text)
    # Collapse triple+ newlines into double
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _send_kwargs(text: str, trace: list = None, confidence: float = None) -> dict:
    """Builds Telegram send kwargs with correct parse mode.

    Note: trace and confidence params are accepted but intentionally unused —
    the observability footer has been removed per user preference to keep
    messages clean and readable.
    """
    clean = text.strip()
    if _detect_html(clean):
        return {"text": clean, "parse_mode": ParseMode.HTML}
    return {"text": _sanitize_markdown(clean), "parse_mode": ParseMode.MARKDOWN}


# ─────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────
def _record_turn_tokens(result: dict, chat_id: int) -> None:
    """Records LLM token usage from the graph result's turn_tokens field.

    turn_tokens is accumulated across ALL nodes in a single turn (Guardrail,
    DomainExpert, Architect handlers, Reviewer) — ensuring accurate per-request
    telemetry even when news is served from the Obsidian 0-token cache
    (Guardrail + DomainExpert tokens still get recorded).
    """
    tokens = result.get("turn_tokens") or {}
    inp = tokens.get("input", 0)
    out = tokens.get("output", 0)
    record_tokens(str(chat_id), inp, out)


async def _run_graph_streaming(
    graph, inputs: dict, config: dict, bot, chat_id: int
) -> dict:
    """Runs LangGraph with streaming and notifies the user if the Reviewer retries.

    Uses asyncio.Queue + loop.call_soon_threadsafe for zero-latency communication
    between the synchronous graph thread and the async Telegram handler, avoiding
    busy-polling.

    Returns the complete final graph state (equivalent to graph.invoke()).
    """
    async_q: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _sync_stream() -> None:
        try:
            for chunk in graph.stream(inputs, config, stream_mode="values"):
                # Detect reviewer retry: Reviewer ran and is routing back to orchestrator
                trace = chunk.get("agent_trace") or []
                if (
                    trace
                    and trace[-1] == "Reviewer"
                    and chunk.get("next_node") == "orchestrator"
                ):
                    loop.call_soon_threadsafe(async_q.put_nowait, ("reviewer_retry", None))
                # Always track the latest complete state
                loop.call_soon_threadsafe(async_q.put_nowait, ("state", chunk))
        except Exception as e:
            loop.call_soon_threadsafe(async_q.put_nowait, ("error", e))
        finally:
            loop.call_soon_threadsafe(async_q.put_nowait, ("done", None))

    future = loop.run_in_executor(None, _sync_stream)

    last_state: dict = {}
    reviewer_notified = False

    while True:
        kind, payload = await async_q.get()

        if kind == "state":
            last_state = payload
        elif kind == "reviewer_retry" and not reviewer_notified:
            reviewer_notified = True
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text="🔄 *Revisando y mejorando la respuesta, un momento más...*",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                pass  # Non-fatal — the main response will still arrive
        elif kind == "error":
            await future  # Clean up thread
            raise payload
        elif kind == "done":
            break

    await future  # Ensure thread is fully joined
    return last_state


# ─────────────────────────────────────────────────────────────────
#  SCHEDULED JOBS
# ─────────────────────────────────────────────────────────────────
async def _prefetch_daily_news(_context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pre-fetches today's news at 07:00 and saves it to the Obsidian vault.

    Runs the full pipeline: RSS fetch → LLM summarise → write .md cache.
    No Telegram message is sent. The benefit is that the first user request
    for news that day is served instantly from cache (0 LLM tokens, ~0 ms).
    """
    logger.info("Daily news pre-fetch started (07:00 Europe/Madrid)")
    try:
        from src.agent.handlers.news_handler import handle_news
        await asyncio.to_thread(handle_news, 0, [])
        logger.info("Daily news pre-fetch completed — Obsidian cache ready")
    except Exception as e:
        logger.error("Daily news pre-fetch failed", error=str(e))


# ─────────────────────────────────────────────────────────────────
#  COMMAND HANDLERS
# ─────────────────────────────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message with quick-action keyboard."""
    user = update.effective_user
    keyboard = [
        [
            InlineKeyboardButton("📰 Noticias del día", callback_data="Resume las noticias de hoy por favor"),
            InlineKeyboardButton("📅 Mi agenda hoy", callback_data="¿Qué tengo en mi agenda hoy?"),
        ],
        [
            InlineKeyboardButton("✅ Mis tareas", callback_data="Lista mis tareas pendientes en Obsidian"),
            InlineKeyboardButton("🗂️ Mis proyectos", callback_data="Lista mis proyectos activos en Obsidian"),
        ],
        [
            InlineKeyboardButton("🔄 Sincronizar reuniones", callback_data="Sincroniza mis reuniones entre Obsidian y Google Calendar"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome = (
        f"✨ *Hola {user.first_name}!* Soy tu LifeOps Orchestrator.\n\n"
        "Comandos disponibles:\n"
        "  🚀 /start  — Menu principal\n"
        "  📊 /stats  — Tokens consumidos\n\n"
        "Escríbeme en lenguaje natural:\n"
        "  • _\"Tareas para mañana\"_\n"
        "  • _\"Crea un evento el lunes\"_\n"
        "  • _\"Resumen de noticias\"_\n"
    )
    await update.message.reply_text(welcome, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reports persistent cumulative + today's LLM token usage from Supabase."""
    stats = db.get_aggregate_stats()

    if not stats:
        await update.message.reply_text(
            "⚠️ No se pudo conectar a la base de datos. Comprueba SUPABASE\\_DB\\_URL.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    t_in      = stats.get("total_input", 0) or 0
    t_out     = stats.get("total_output", 0) or 0
    t_total   = stats.get("grand_total", 0) or 0
    t_reqs    = stats.get("total_requests", 0) or 0
    d_in      = stats.get("today_input", 0) or 0
    d_out     = stats.get("today_output", 0) or 0
    d_total   = stats.get("today_total", 0) or 0
    d_reqs    = stats.get("today_requests", 0) or 0
    d_limit   = stats.get("daily_limit", 0) or 0
    d_remain  = stats.get("today_remaining", 0) or 0

    cost_usd = (t_in * 0.00000015) + (t_out * 0.00000060)
    d_pct    = int(d_total / d_limit * 100) if d_limit else 0
    bar_fill = min(d_pct // 10, 10)
    bar      = "█" * bar_fill + "░" * (10 - bar_fill)

    msg = (
        "📊 *Estadísticas de Consumo LLM*\n\n"
        "*Hoy:*\n"
        f"  📥 Input: `{d_in:,}` tokens\n"
        f"  📤 Output: `{d_out:,}` tokens\n"
        f"  🔢 Total: `{d_total:,}` / `{d_limit:,}` tokens\n"
        f"  📊 `{bar}` {d_pct}%\n"
        f"  💬 Solicitudes: `{d_reqs}`\n"
        f"  ✅ Restantes hoy: `{d_remain:,}` tokens\n\n"
        "─────────────────────\n"
        "*Acumulado total:*\n"
        f"  📥 Input: `{t_in:,}` tokens\n"
        f"  📤 Output: `{t_out:,}` tokens\n"
        f"  💬 Solicitudes: `{t_reqs:,}`\n"
        f"  🔢 Total: `{t_total:,}` tokens\n\n"
        f"💰 *Coste estimado:* `${cost_usd:.4f}` USD\n"
        "_(Basado en precios GPT-4o-mini)_"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# ─────────────────────────────────────────────────────────────────
#  MESSAGE HANDLERS
# ─────────────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Routes free-text messages through the LangGraph pipeline with concurrency lock."""
    text = update.message.text
    chat_id = update.message.chat_id
    lock = get_chat_lock(chat_id)

    if lock.locked():
        await update.message.reply_text("⏳ Ya estoy procesando una solicitud tuya. Por favor, espera a que termine.")
        return

    async with lock:
        logger.info("User message received", chat_id=chat_id, text=text[:80])

        over_budget, budget_msg = _check_budget(chat_id)
        if over_budget:
            await update.message.reply_text(budget_msg, parse_mode=ParseMode.MARKDOWN)
            return

        config = {"configurable": {"thread_id": str(chat_id)}}
        msg = HumanMessage(content=text)

        try:
            temp_msg = await update.message.reply_text("🛡️ Verificando seguridad y enrutando...")
            result = await _run_graph_streaming(
                graph_app, {"messages": [msg]}, config,
                bot=context.bot, chat_id=chat_id,
            )

            if result.get("is_secure") is False:
                await temp_msg.edit_text(f"🛑 Solicitud bloqueada: {result.get('security_alert')}")
                return

            _record_turn_tokens(result, chat_id)

            replies = [m for m in result.get("messages", []) if isinstance(m, AIMessage)]
            if replies:
                kwargs = _send_kwargs(
                    replies[-1].content,
                    trace=result.get("agent_trace"),
                    confidence=result.get("confidence_score"),
                )
                await temp_msg.delete()
                await update.message.reply_text(**kwargs)
            elif result.get("awaiting_user_input"):
                await temp_msg.edit_text("⏳ *Esperando tu confirmación...*", parse_mode=ParseMode.MARKDOWN)
            else:
                await temp_msg.edit_text("✨ *Acción completada con éxito.*", parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            logger.error("LangGraph error on user message", error=str(e))
            await update.message.reply_text(f"❌ Error al procesar tu solicitud. Detalle: {str(e)[:200]}")


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inline button presses with concurrency lock."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data
    lock = get_chat_lock(chat_id)

    if lock.locked():
        await context.bot.send_message(chat_id=chat_id, text="⏳ Procesando acción previa...")
        return

    async with lock:
        logger.info("Callback query received", chat_id=chat_id, data=data[:80])

        over_budget, budget_msg = _check_budget(chat_id)
        if over_budget:
            await context.bot.send_message(chat_id=chat_id, text=budget_msg, parse_mode=ParseMode.MARKDOWN)
            return

        config = {"configurable": {"thread_id": str(chat_id)}}
        msg = HumanMessage(content=data)

        try:
            await query.edit_message_text(text=f"🛡️ Validando y ejecutando: {data[:40]}...")
            result = await _run_graph_streaming(
                graph_app, {"messages": [msg]}, config,
                bot=context.bot, chat_id=chat_id,
            )

            if result.get("is_secure") is False:
                await context.bot.send_message(chat_id=chat_id, text=f"🛑 Bloqueo de seguridad: {result.get('security_alert')}")
                return

            _record_turn_tokens(result, chat_id)

            replies = [m for m in result.get("messages", []) if isinstance(m, AIMessage)]
            if replies:
                kwargs = _send_kwargs(
                    replies[-1].content,
                    trace=result.get("agent_trace"),
                    confidence=result.get("confidence_score"),
                )
                await context.bot.send_message(chat_id=chat_id, **kwargs)
            else:
                await context.bot.send_message(chat_id=chat_id, text="✨ *Hecho.*", parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            logger.error("LangGraph error on callback", error=str(e))
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Error al procesar la acción: {str(e)[:200]}"
            )


# ─────────────────────────────────────────────────────────────────
#  APP FACTORY
# ─────────────────────────────────────────────────────────────────
def get_telegram_app() -> Application:
    """Constructs and returns the fully configured Telegram Application.

    Registers:
    - /start, /stats command handlers
    - Free-text message handler
    - Inline keyboard callback handler
    - Daily news job at 07:00 Europe/Madrid (requires TELEGRAM_CHAT_ID in .env
      and 'python-telegram-bot[job-queue]' installed)
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "tu_telegram_bot_token":
        logger.warning("TELEGRAM_BOT_TOKEN is not set or is the placeholder value.")

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # ── 7 AM daily news job ──────────────────────────────────────
    if application.job_queue is not None:
        application.job_queue.run_daily(
            callback=_prefetch_daily_news,
            time=dtime(7, 0, 0, tzinfo=MADRID_TZ),
            name="daily_news_prefetch",
        )
        logger.info("Daily news pre-fetch job registered at 07:00 Europe/Madrid")
    else:
        logger.warning(
            "JobQueue not available — install 'python-telegram-bot[job-queue]' "
            "to enable the 07:00 automatic news pre-fetch."
        )

    return application
