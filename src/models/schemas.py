from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Any, Dict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from enum import Enum

MADRID_TZ = ZoneInfo("Europe/Madrid")

# ─────────────────────────────────────────
#  NEWS
# ─────────────────────────────────────────
class Story(BaseModel):
    title: str = Field(description="Titular")
    summary: str = Field(description="Resumen")
    url: str = Field(description="URL")


class DailyNewsDigest(BaseModel):
    top_stories: List[Story]
    tech_brief: Optional[str] = None


# ─────────────────────────────────────────
#  EMAIL
# ─────────────────────────────────────────
class EmailStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class EmailDraftProposal(BaseModel):
    to: str
    subject: str
    body: str


# ─────────────────────────────────────────
#  CALENDAR (CONSOLIDATED)
# ─────────────────────────────────────────
def _ensure_madrid_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=MADRID_TZ)
    return dt.astimezone(MADRID_TZ)


class CalendarEventRequest(BaseModel):
    title: str
    start_datetime: datetime
    end_datetime: datetime
    attendees: Optional[List[str]] = None

    @field_validator("start_datetime", "end_datetime", mode="before")
    @classmethod
    def parse_and_localize(cls, v):
        if isinstance(v, str): v = datetime.fromisoformat(v)
        return _ensure_madrid_tz(v) if isinstance(v, datetime) else v


# ─────────────────────────────────────────
#  OBSIDIAN SMART CRUD (TOKEN SAVER)
# ─────────────────────────────────────────
class ObsidianAction(str, Enum):
    create = "create"
    read = "read"
    update = "update"
    delete = "delete"
    list = "list"
    inbox = "inbox"


class ObsidianItemType(str, Enum):
    task = "task"
    project = "project"
    meeting = "meeting"


class ObsidianRequest(BaseModel):
    """Simplified Obsidian Request for Smart CRUD."""
    action: ObsidianAction
    item_type: Optional[ObsidianItemType] = None
    title: Optional[str] = None
    content: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None


# ─────────────────────────────────────────
#  UNIFIED EXTRACTION (TOKEN SAVER)
# ─────────────────────────────────────────
class UnifiedExtraction(BaseModel):
    """Refined single-pass extraction to minimize token usage."""
    intent: str = Field(description="Intent label (e.g. calendar_create, obsidian_crud, email, news)")
    
    # Generic Search/Query
    query_text: Optional[str] = None
    query_date: Optional[str] = None # ISO date or "YYYY-MM-DD"
    
    # Calendar
    calendar_title: Optional[str] = None
    calendar_start: Optional[str] = None
    calendar_end: Optional[str] = None
    
    # Obsidian (Consolidated)
    obs_action: Optional[ObsidianAction] = None
    obs_type: Optional[ObsidianItemType] = None
    obs_title: Optional[str] = None
    obs_content: Optional[str] = None
    obs_prio: Optional[str] = None
    obs_due: Optional[str] = None
    
    # Email
    email_to: Optional[str] = None
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
