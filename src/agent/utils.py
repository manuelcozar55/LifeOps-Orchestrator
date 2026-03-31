"""
Shared text utilities for LifeOps agent nodes.
================================================
Pure functions with no side effects — safe to import from any module
without triggering circular dependencies.
"""
import re


# ─────────────────────────────────────────────────────────────────
#  HIL CONFIRMATION HELPERS
# ─────────────────────────────────────────────────────────────────

_CONFIRM_WORDS = frozenset({
    "sí", "si", "yes", "ok", "confirmo", "adelante", "envía", "envia",
    "confirm", "ejecuta", "procede", "dale", "hazlo", "perfecto",
})
_CANCEL_WORDS = frozenset({
    "no", "cancelar", "cancel", "abort", "detén", "para", "stop", "nope",
})


def _is_confirm(text: str) -> bool:
    """Returns True only when the FIRST word of the response is an explicit confirmation.

    First-word matching prevents false positives like
    "I don't think ok is a good idea" being treated as a confirmation.
    Also rejects ambiguous responses that mix confirm + cancel keywords
    (e.g. "sí pero no").
    """
    if not text or not text.strip():
        return False
    first = re.split(r"[\s,\.!?;:]+", text.strip().lower())[0]
    if first not in _CONFIRM_WORDS:
        return False
    # Reject if the full message contains any cancel keyword as a standalone word
    words = set(re.split(r"[\s,\.!?;:]+", text.strip().lower()))
    return not (words & _CANCEL_WORDS)


def _is_cancel(text: str) -> bool:
    """Returns True when the FIRST word of the response is an explicit cancellation."""
    if not text or not text.strip():
        return False
    first = re.split(r"[\s,\.!?;:]+", text.strip().lower())[0]
    return first in _CANCEL_WORDS


# ─────────────────────────────────────────────────────────────────
#  TEXT / DISPLAY UTILS
# ─────────────────────────────────────────────────────────────────

def _sanitize_telegram_html(text: str) -> str:
    """Converts structural HTML tags to Telegram-safe equivalents."""
    if not text:
        return ""
    text = re.sub(r'<!DOCTYPE.*?>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<(html|head|body|script|style)[^>]*>.*?</\1>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<(ul|ol)[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(ul|ol)>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>', '  • ', text, flags=re.IGNORECASE)
    text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<(p|div|br)[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(p|div)>', '\n', text, flags=re.IGNORECASE)
    supported = {'b', 'strong', 'i', 'em', 'u', 's', 'strike', 'del', 'a', 'code', 'pre'}

    def _keep_or_strip(m):
        tag = re.match(r'</?([a-z1-6]+)', m.group(0), re.IGNORECASE)
        return m.group(0) if tag and tag.group(1).lower() in supported else ""

    text = re.sub(r'<[^>]+>', _keep_or_strip, text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _slugify_title(text: str) -> str:
    """Normalises text for fuzzy comparison between Calendar and Obsidian."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", "-", text)[:50]


def _extract_meeting_title(filename: str) -> str:
    """'2026-03-28-reunion-kickoff.md' → 'Reunion Kickoff'"""
    name = filename.replace(".md", "")
    name = re.sub(r"^\d{4}-\d{2}-\d{2}-?", "", name)
    return name.replace("-", " ").strip().title()


def _format_obsidian_list(items: list, label: str, date_filter: str = None) -> str:
    if not items:
        suffix = f" para el {date_filter}" if date_filter else ""
        return f"✨ No hay {label} en Obsidian{suffix}."
    lines = [f"📚 **{label.upper()}** ({len(items)}):\n"]
    for item in items[:8]:
        title = item["title"].replace(".md", "")
        snippet = (item.get("snippet") or "")[:120]
        lines.append(f"• **{title}**\n  _{snippet}_")
    return "\n\n".join(lines)
