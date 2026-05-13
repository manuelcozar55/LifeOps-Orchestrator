"""
Obsidian Expert Agent Tool
==========================
Smart CRUD for Tasks, Projects and Meetings.
Automatically maps item types to the correct folders in the vault.
"""
import os
import re
import shutil
import structlog
from datetime import datetime
from typing import Dict, Any, List, Optional
from langsmith import traceable

logger = structlog.get_logger()


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:60]


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _frontmatter(fields: Dict[str, Any]) -> str:
    lines = ["---"]
    for k, v in fields.items():
        if v is not None:
            lines.append(f"{k}: {v}")
    lines.append("---\n")
    return "\n".join(lines)


def _parse_frontmatter(content: str) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if match:
        for line in match.group(1).splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                meta[key.strip()] = val.strip()
    return meta


class ObsidianVaultTool:
    """Folder-aware Obsidian Agent with Smart CRUD capabilities."""

    DIRS = {
        "project": "proyectos",
        "task": "tareas",
        "meeting": "reuniones",
        "news": "noticias",
        "archive": "archivo",
        "inbox": "inbox",
        "templates": "plantillas",
    }

    def __init__(self, vault_path: Optional[str] = None):
        self.vault = vault_path or os.getenv("OBSIDIAN_VAULT_PATH", "app/obsidian_vault")
        for d in self.DIRS.values():
            os.makedirs(os.path.join(self.vault, d), exist_ok=True)
        logger.info("Obsidian Smart CRUD initialized", vault=self.vault)

    def _get_folder(self, item_type: str) -> str:
        return self.DIRS.get(item_type.lower(), self.DIRS["inbox"])

    def _read(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""

    def _write(self, path: str, content: str) -> bool:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error("Write failed", path=path, error=str(e))
            return False

    @traceable(run_type="tool", name="obsidian_get_note")
    def get_note(self, title: str, item_type: str) -> Dict[str, Any]:
        """Finds a note by title in the corresponding folder and returns its content."""
        folder = self._get_folder(item_type)
        search_dir = os.path.join(self.vault, folder)
        
        # Exact match or slug match
        slug = _slugify(title)
        for fname in os.listdir(search_dir):
            if slug in _slugify(fname) or _slugify(title) == _slugify(fname.replace(".md", "")):
                path = os.path.join(search_dir, fname)
                content = self._read(path)
                return {"success": True, "title": fname, "content": content, "path": path}
        
        return {"success": False, "message": f"No se encontró '{title}' en {folder}"}

    @traceable(run_type="tool", name="obsidian_list_items")
    def list_items(self, item_type: str, date_filter: str = None) -> List[Dict[str, Any]]:
        """Lists items of a specific type. Optionally filters by date (YYYY-MM-DD)."""
        folder = self._get_folder(item_type)
        dir_path = os.path.join(self.vault, folder)
        results = []
        for fname in sorted(os.listdir(dir_path)):
            if fname.endswith(".md"):
                # Date filtering (Filename match e.g. "2024-03-28.md" or contains "2024-03-28")
                if date_filter and date_filter not in fname:
                    continue
                
                content = self._read(os.path.join(dir_path, fname))
                # Strip frontmatter
                body = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL).strip()
                results.append({"title": fname, "snippet": body[:200], "full_content": content})
        return results

    @traceable(run_type="tool", name="obsidian_upsert_note")
    def upsert_note(self, title: str, item_type: str, content: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Creates or overwrites a note in the correct folder."""
        folder = self._get_folder(item_type)
        # Determine filename based on title or date
        clean_title = _slugify(title.replace(".md", ""))
        date_prefix = metadata.get("fecha") or _today()
        
        # News special case: One file per day
        if item_type == "news":
            filename = f"{date_prefix}-noticias.md"
        else:
            filename = f"{date_prefix}-{clean_title}.md"
        
        path = os.path.join(self.vault, folder, filename)
        
        full_text = content
        if metadata:
            full_text = _frontmatter(metadata) + content
            
        ok = self._write(path, full_text)
        return {"success": ok, "message": f"✅ Nota '{filename}' guardada en {folder}", "path": path}

    @traceable(run_type="tool", name="obsidian_delete_note")
    def delete_note(self, title: str, item_type: str) -> Dict[str, Any]:
        """Moves a note to the archive folder."""
        note = self.get_note(title, item_type)
        if not note["success"]:
            return note
        
        archive_path = os.path.join(self.vault, self.DIRS["archive"], os.path.basename(note["path"]))
        try:
            shutil.move(note["path"], archive_path)
            return {"success": True, "message": f"Nota archivada en {self.DIRS['archive']}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @traceable(run_type="tool", name="obsidian_append_inbox")
    def append_inbox(self, text: str) -> Dict[str, Any]:
        path = os.path.join(self.vault, self.DIRS["inbox"], "inbox.md")
        content = self._read(path)
        content += f"\n- [ ] [{_today()}] {text}"
        ok = self._write(path, content)
        return {"success": ok, "message": "Añadido al inbox"}

    # Compatibility methods to avoid breaking existing logic in prompt
    def create_task(self, title, desc="", due="", prio="media"):
        return self.upsert_note(title, "task", desc, {"tipo": "tarea", "prioridad": prio, "fecha_limite": due})

    def list_tasks(self): 
        return self.list_items("task")

    def create_project(self, title, desc="", objective=""):
        return self.upsert_note(title, "project", desc, {"tipo": "proyecto", "objetivo": objective})
    
    def list_projects(self):
        return self.list_items("project")

    def create_meeting(self, title, date="", attendees=None, agenda=""):
        meta = {
            "tipo": "reunion",
            "fecha": date or _today(),
            "hora": datetime.now().strftime("%H:%M"),
            "asistentes": attendees or [],
            "estado": "pendiente"
        }
        return self.upsert_note(title, "meeting", agenda, meta)

    def list_meetings(self):
        return self.list_items("meeting")

    def create_news_log(self, summary):
        meta = {
            "tipo": "noticias",
            "fecha": _today(),
            "tags": ["🤖 ia", "📰 noticias", "global"]
        }
        # Store the summary directly — no wrappers that break Telegram Markdown
        return self.upsert_note("noticias", "news", summary.strip() + "\n", meta)

    def get_today_news(self) -> Optional[str]:
        """Returns today's cached news content, or None if not yet generated.

        Strips the YAML frontmatter block and any legacy wrapper markup
        (# headers, > blockquotes, --- horizontal rules, footer tip) that
        used to be written by the old create_news_log() format.
        """
        folder = self.DIRS["news"]
        filename = f"{_today()}-noticias.md"
        path = os.path.join(self.vault, folder, filename)

        if not os.path.exists(path):
            return None

        content = self._read(path)
        # Strip the leading YAML frontmatter (first ---...--- block only)
        body = re.sub(r"^---\n.*?\n---\n?", "", content, flags=re.DOTALL).strip()

        # Strip legacy wrapper: "# 📰 ..." header line
        body = re.sub(r"^#[^\n]*\n+", "", body)
        # Strip legacy wrapper: "> *Generado automáticamente...*" blockquote
        body = re.sub(r"^>[^\n]*\n+", "", body)
        # Strip legacy horizontal rules (standalone --- lines)
        body = re.sub(r"(?m)^---+\s*$\n?", "", body)
        # Strip legacy footer tip line
        body = re.sub(r"\n💡[^\n]*$", "", body.strip(), flags=re.DOTALL)

        body = body.strip()
        # Return None (cache miss) if only whitespace or too short
        if not body or len(body) < 80:
            return None
        return body
