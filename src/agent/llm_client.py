"""
Shared LLM instance for all agent nodes.
=========================================
Single source of truth for the Azure OpenAI client.
All nodes import `llm` from here to avoid duplicated configuration
and to ensure a consistent model, temperature and retry policy.
"""
import os
import structlog
from langchain_openai import AzureChatOpenAI

logger = structlog.get_logger()

_deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")
_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

llm = AzureChatOpenAI(
    azure_deployment=_deployment,
    openai_api_version=_api_version,
    temperature=0,
    max_retries=3,
)

# ── Tiktoken encoder (lazy-loaded, used only as fallback) ──────────────────────
_tiktoken_enc = None

def _get_tiktoken_encoder():
    """Returns a tiktoken encoder for cl100k_base (gpt-4o/gpt-4o-mini)."""
    global _tiktoken_enc
    if _tiktoken_enc is None:
        try:
            import tiktoken
            _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _tiktoken_enc = False  # Disable permanently if unavailable
    return _tiktoken_enc if _tiktoken_enc else None


def _tiktoken_count(text: str) -> int:
    """Fast local token estimate via tiktoken (cl100k_base encoding)."""
    enc = _get_tiktoken_encoder()
    if enc is None:
        return 0
    try:
        return len(enc.encode(text, disallowed_special=()))
    except Exception:
        return 0


def extract_tokens(response) -> tuple[int, int]:
    """Returns (input_tokens, output_tokens) from any LLM response object.

    Resolution order (most-precise first):
      1. response_metadata["token_usage"]   — standard LangChain / Azure path
      2. response_metadata["usage"]         — alternative Azure API version path
      3. additional_kwargs["usage"]         — some LangChain proxy wrappers
      4. tiktoken estimate on response text — local fallback when API omits counts

    The API-reported counts are always preferred because they include system
    overhead that tiktoken can't see. Tiktoken only kicks in when the API
    returns zeros (e.g. some Azure proxy configurations strip usage data).
    """
    if response is None:
        return (0, 0)

    # ── Path 1 & 2: response_metadata ─────────────────────────────────────────
    meta = getattr(response, "response_metadata", {}) or {}
    usage = meta.get("token_usage") or meta.get("usage") or {}
    inp = int(usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0)
    out = int(usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0)

    if inp or out:
        return (inp, out)

    # ── Path 3: additional_kwargs (some proxy wrappers) ───────────────────────
    add_kw = getattr(response, "additional_kwargs", {}) or {}
    usage2 = add_kw.get("usage") or {}
    inp2 = int(usage2.get("prompt_tokens", 0) or 0)
    out2 = int(usage2.get("completion_tokens", 0) or 0)
    if inp2 or out2:
        return (inp2, out2)

    # ── Path 4: tiktoken fallback ─────────────────────────────────────────────
    # Estimate output tokens from the response text when API omits usage data.
    # Input tokens cannot be estimated here (prompt not available), so we
    # return (0, estimated_output) to at least capture something meaningful.
    content = getattr(response, "content", "") or ""
    if content:
        estimated_out = _tiktoken_count(content)
        if estimated_out:
            logger.debug("extract_tokens: using tiktoken fallback", estimated_out=estimated_out)
            return (0, estimated_out)

    return (0, 0)
