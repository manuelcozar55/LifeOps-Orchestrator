import os
import structlog
import base64
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from email.message import EmailMessage
from typing import List, Dict, Any, Optional
from langsmith import traceable

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except ImportError:
    pass

logger = structlog.get_logger()
MADRID_TZ = ZoneInfo("Europe/Madrid")


class GoogleCLITool:
    """Official Google API Python Client — Gmail v1 + Calendar v3.
    
    Handles token refresh automatically on every instantiation.
    All methods return explicit success/failure booleans or typed lists.
    """

    def __init__(self, timeout_secs: int = 15):
        self.creds = None
        token_path = os.getenv("GOOGLE_TOKEN_PATH", "token.json")
        if os.path.exists(token_path):
            self.creds = Credentials.from_authorized_user_file(token_path)
            # Auto-refresh expired token
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                    with open(token_path, "w") as f:
                        f.write(self.creds.to_json())
                    logger.info("Google token refreshed automatically")
                except Exception as e:
                    logger.error("Failed to refresh Google token", error=str(e))
                    self.creds = None
        else:
            logger.warning("token.json not found! Run auth_setup.py on host first.", path=token_path)

    def _dt_to_rfc3339(self, dt: Any, default_now: bool = False) -> str:
        """Converts any datetime-like value to RFC3339 string with Madrid offset."""
        if dt is None:
            if not default_now: return ""
            dt = datetime.now()
            
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            except ValueError:
                dt = datetime.now()
                
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=MADRID_TZ)
            else:
                dt = dt.astimezone(MADRID_TZ)
        return dt.isoformat()

    # ─────────────────────────────────────────
    #  GMAIL
    # ─────────────────────────────────────────

    @traceable(run_type="tool", name="gmail_search_emails")
    def search_emails(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Searches emails matching a free-text query (e.g. 'from:boss', 'meeting')."""
        if not self.creds:
            return []
        try:
            service = build("gmail", "v1", credentials=self.creds)
            results = service.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()
            messages = results.get("messages", [])
            found = []
            for msg in messages:
                msg_data = service.users().messages().get(
                    userId="me", id=msg["id"], format="metadata",
                    metadataHeaders=["Subject", "From"]
                ).execute()
                headers = msg_data.get("payload", {}).get("headers", [])
                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
                sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
                found.append({
                    "id": msg["id"], 
                    "from": sender, 
                    "subject": subject,
                    "snippet": msg_data.get("snippet", "")
                })
            logger.info("Gmail search completed", query=query, found=len(found))
            return found
        except Exception as e:
            logger.error("Failed to search Gmail", error=str(e))
            return []

    @traceable(run_type="tool", name="gmail_get_email_body")
    def get_email_body(self, email_id: str) -> str:
        """Fetches the plain-text body of an email by ID (max 2 000 chars)."""
        if not self.creds:
            return ""
        try:
            service = build("gmail", "v1", credentials=self.creds)
            msg = service.users().messages().get(
                userId="me", id=email_id, format="full"
            ).execute()

            def _extract(part: dict) -> str:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        import base64 as _b64
                        return _b64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                for sub in part.get("parts", []):
                    result = _extract(sub)
                    if result:
                        return result
                return ""

            body = _extract(msg.get("payload", {}))
            return body[:2000]
        except Exception as e:
            logger.error("Failed to get email body", error=str(e))
            return ""

    @traceable(run_type="tool", name="gmail_send_email")
    def send_email(self, to: str, subject: str, body: str) -> bool:
        if not self.creds:
            return False
        try:
            service = build("gmail", "v1", credentials=self.creds)
            message = EmailMessage()
            message.set_content(body)
            message["To"] = to
            message["From"] = "me"
            message["Subject"] = subject
            encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
            service.users().messages().send(userId="me", body={"raw": encoded}).execute()
            logger.info("Email sent", to=to, subject=subject)
            return True
        except Exception as e:
            logger.error("Failed to send email", error=str(e))
            return False

    # ─────────────────────────────────────────
    #  GOOGLE CALENDAR — CRUD COMPLETO
    # ─────────────────────────────────────────

    @traceable(run_type="tool", name="calendar_create_event")
    def create_event(self, title: str, start_dt: Any, end_dt: Any,
                     attendees: Optional[List[str]] = None) -> bool:
        """Creates a calendar event. Accepts datetime objects or ISO strings."""
        if not self.creds:
            return False
        try:
            service = build("calendar", "v3", credentials=self.creds)
            start_iso = self._dt_to_rfc3339(start_dt)
            end_iso = self._dt_to_rfc3339(end_dt)

            event_body: Dict[str, Any] = {
                "summary": title,
                "start": {"dateTime": start_iso, "timeZone": "Europe/Madrid"},
                "end": {"dateTime": end_iso, "timeZone": "Europe/Madrid"},
            }
            if attendees:
                event_body["attendees"] = [{"email": a} for a in attendees]

            result = service.events().insert(calendarId="primary", body=event_body).execute()
            logger.info("Calendar event created", title=title, start=start_iso,
                        event_id=result.get("id"))
            return True
        except Exception as e:
            logger.error("Failed to create calendar event", error=str(e), 
                         title=title, start=start_dt)
            return False

    @traceable(run_type="tool", name="calendar_search_events")
    def search_events(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Searches upcoming events matching a free-text query."""
        if not self.creds:
            return []
        try:
            service = build("calendar", "v3", credentials=self.creds)
            now_utc = datetime.now(timezone.utc).isoformat()
            future = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
            result = service.events().list(
                calendarId="primary", q=query, timeMin=now_utc, timeMax=future,
                maxResults=max_results, singleEvents=True, orderBy="startTime"
            ).execute()
            events = result.get("items", [])
            found = []
            for e in events:
                found.append({
                    "id": e.get("id"),
                    "summary": e.get("summary", "Sin título"),
                    "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date", "")),
                })
            logger.info("Calendar search completed", query=query, found=len(found))
            return found
        except Exception as e:
            logger.error("Failed to search calendar events", error=str(e))
            return []

    @traceable(run_type="tool", name="calendar_update_event")
    def update_event(self, event_id: str, new_title: Optional[str] = None,
                     new_start_dt: Optional[Any] = None,
                     new_end_dt: Optional[Any] = None) -> bool:
        """Patches an existing calendar event by its ID."""
        if not self.creds:
            return False
        try:
            service = build("calendar", "v3", credentials=self.creds)
            event = service.events().get(calendarId="primary", eventId=event_id).execute()

            if new_title:
                event["summary"] = new_title
            if new_start_dt:
                event["start"] = {"dateTime": self._dt_to_rfc3339(new_start_dt),
                                  "timeZone": "Europe/Madrid"}
            if new_end_dt:
                event["end"] = {"dateTime": self._dt_to_rfc3339(new_end_dt),
                                "timeZone": "Europe/Madrid"}

            service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
            logger.info("Calendar event updated", event_id=event_id)
            return True
        except Exception as e:
            logger.error("Failed to update calendar event", error=str(e))
            return False

    @traceable(run_type="tool", name="calendar_delete_event")
    def delete_event(self, event_id: str) -> bool:
        """Deletes a calendar event permanently by its ID."""
        if not self.creds:
            return False
        try:
            service = build("calendar", "v3", credentials=self.creds)
            service.events().delete(calendarId="primary", eventId=event_id).execute()
            logger.info("Calendar event deleted", event_id=event_id)
            return True
        except Exception as e:
            logger.error("Failed to delete calendar event", error=str(e))
            return False

    @traceable(run_type="tool", name="calendar_get_today")
    def get_todays_events(self) -> str:
        """Returns a formatted string of today's events."""
        if not self.creds:
            return "No token.json found. Run auth_setup.py."
        try:
            service = build("calendar", "v3", credentials=self.creds)
            now = datetime.now(timezone.utc).isoformat()
            time_max = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
            result = service.events().list(
                calendarId="primary", timeMin=now, timeMax=time_max,
                maxResults=10, singleEvents=True, orderBy="startTime"
            ).execute()
            events = result.get("items", [])
            if not events:
                return "No hay eventos en el calendario hoy."
            lines = []
            for e in events:
                start = e["start"].get("dateTime", e["start"].get("date", ""))
                lines.append(f"• {start} — {e.get('summary', 'Sin título')}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error al obtener agenda: {str(e)}"
