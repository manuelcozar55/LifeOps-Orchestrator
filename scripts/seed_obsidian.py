"""
Seed script: creates 1 project, 5 tasks and 3 meetings in the real Obsidian vault,
using the existing plantillas/ templates.
Run: python seed_obsidian.py
"""
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

VAULT = os.getenv("OBSIDIAN_VAULT_PATH", r"C:\Users\ManuelCozarBaranguan\Downloads\Memory")
TPL_DIR = os.path.join(VAULT, "memoria", "plantillas")
PROJ_DIR = os.path.join(VAULT, "01-proyectos")
TASK_DIR = os.path.join(VAULT, "02-tareas")
MEET_DIR = os.path.join(VAULT, "08-reuniones")

today = datetime.now()


def read_tpl(name: str) -> str:
    p = os.path.join(TPL_DIR, name)
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def write(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    print(f"  ✓  {os.path.basename(path)}")


# ─────────────────────────────────────────────────────────────────
#  PROJECT
# ─────────────────────────────────────────────────────────────────
tpl = read_tpl("plantilla-proyecto.md")
start_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
end_date = (today + timedelta(days=30)).strftime("%Y-%m-%d")

content = (
    tpl
    .replace("[YYYY-MM-DD]", start_date, 1)   # first occurrence = inicio
    .replace("[YYYY-MM-DD]", end_date, 1)     # second = fin (if exists)
    .replace("[FIN]", end_date)
    .replace("[AREA]", "tecnologia")
    .replace("[TITULO_PROYECTO]", "LifeOps Orchestrator v2")
    .replace(
        "[DESCRIPCION_OBJETIVO]",
        "Automatizar las operaciones diarias utilizando agentes de IA con LangGraph, "
        "conectados a Google Calendar, Gmail y Obsidian via Telegram."
    )
    .replace(
        "[JUSTIFICACION]",
        "Reducir el tiempo dedicado a tareas repetitivas de gestion y aumentar "
        "la productividad personal en un 40%."
    )
    .replace(
        "[RESULTADO]",
        "Sistema multi-agente desplegado en Docker con bot de Telegram operativo 24/7."
    )
    .replace("[NUEVA_TAREA_1]", "Configurar infraestructura Docker y variables de entorno")
    .replace("[NUEVA_TAREA_2]", "Integrar Google Calendar API con zona horaria Europe/Madrid")
    .replace(
        "[NOTAS_GENERADAS_POR_AGENTE]",
        f"Proyecto creado por LifeOps Orchestrator el {today.strftime('%Y-%m-%d')} "
        "como datos de prueba del sistema."
    )
)

proj_slug = f"{today.strftime('%Y-%m-%d')}-lifeops-orchestrator-v2.md"
write(os.path.join(PROJ_DIR, proj_slug), content)
print("\n[1/3] Proyecto creado.\n")

# ─────────────────────────────────────────────────────────────────
#  TASKS (Mon → Fri next week)
# ─────────────────────────────────────────────────────────────────
days_ahead = (7 - today.weekday()) % 7
if days_ahead == 0:
    days_ahead = 7
next_monday = today + timedelta(days=days_ahead)

tasks = [
    (
        "Lunes", next_monday,
        "ALTA",
        "Definir arquitectura y roadmap del sprint",
        "Revisar los requisitos actuales del sistema, identificar gaps y disenar el plan de "
        "trabajo para la semana. Incluye sesion de kick-off con el equipo.",
    ),
    (
        "Martes", next_monday + timedelta(1),
        "ALTA",
        "Integrar Azure OpenAI con modelos estructurados",
        "Configurar correctamente el deployment de gpt-4o-mini, validar los schemas Pydantic "
        "para Calendar y Obsidian, y ejecutar pruebas de clasificacion de intents.",
    ),
    (
        "Miercoles", next_monday + timedelta(2),
        "MEDIA",
        "Optimizar cache de noticias y formato HTML",
        "Revisar el pipeline de noticias RSS, ajustar el prompt para hipervinculos en Telegram, "
        "y validar que la cache diaria funciona correctamente evitando llamadas redundantes.",
    ),
    (
        "Jueves", next_monday + timedelta(3),
        "MEDIA",
        "Pruebas E2E del agente de Obsidian",
        "Ejecutar el flujo completo de creacion, actualizacion y eliminacion de tareas y "
        "proyectos desde Telegram. Verificar que los archivos se generan en el vault real.",
    ),
    (
        "Viernes", next_monday + timedelta(4),
        "BAJA",
        "Documentacion tecnica y revision final",
        "Actualizar el README con los resultados de las pruebas, documentar los ADR nuevos "
        "y preparar el informe de la semana para el equipo.",
    ),
]

tpl_task = read_tpl("plantilla-tarea.md")

for day, date, prio, title, desc in tasks:
    slug_name = title.lower().replace(" ", "-")[:45]
    slug = f"{date.strftime('%Y-%m-%d')}-{slug_name}.md"
    content = (
        tpl_task
        .replace("[YYYY-MM-DD]", date.strftime("%Y-%m-%d"))
        .replace("[ALTA|MEDIA|BAJA]", prio)
        .replace("[PROYECTO]", "LifeOps Orchestrator v2")
        .replace("[TITULO_TAREA]", f"[{day}] {title}")
        .replace("[DESCRIPCION_DETALLADA]", desc)
        .replace(
            "[NOTAS]",
            f"Tarea del {day} ({date.strftime('%d/%m/%Y')}) generada por LifeOps Orchestrator."
        )
        .replace("[SUBTAREA_1]", "Preparar entorno y materiales necesarios")
        .replace("[SUBTAREA_2]", "Ejecutar, documentar y validar resultados")
    )
    write(os.path.join(TASK_DIR, slug), content)

print(f"\n[2/3] 5 tareas creadas (semana {next_monday.strftime('%d/%m/%Y')}).\n")

# ─────────────────────────────────────────────────────────────────
#  MEETINGS (3)
# ─────────────────────────────────────────────────────────────────
tpl_meet = read_tpl("plantilla-reunion.md")

meetings = [
    (
        next_monday, "09:00",
        "Kick-off Sprint LifeOps v2",
        "Manuel Cozar, Laura Garcia, Team Backend",
        "planning",
        "1. Presentacion del proyecto\n2. Asignacion de tareas\n3. Definition of Done\n4. Proximos pasos",
    ),
    (
        next_monday + timedelta(2), "11:00",
        "Revision de Arquitectura Agentes",
        "Manuel Cozar, Tech Lead",
        "decision",
        (
            "1. Revision del grafo LangGraph\n"
            "2. Validacion de schemas Pydantic\n"
            "3. Decision sobre estrategia de caching\n"
            "4. Aprobacion del diseno final"
        ),
    ),
    (
        next_monday + timedelta(4), "16:00",
        "Retrospectiva de la Semana",
        "Manuel Cozar, Equipo completo",
        "brainstorming",
        (
            "1. Que fue bien esta semana\n"
            "2. Que podemos mejorar\n"
            "3. Acciones de mejora para el proximo sprint\n"
            "4. Celebraciones del equipo"
        ),
    ),
]

for date, hour, title, attendees, tipo, agenda_items in meetings:
    slug_name = title.lower().replace(" ", "-")[:45]
    slug = f"{date.strftime('%Y-%m-%d')}-{slug_name}.md"
    content = (
        tpl_meet
        .replace("[YYYY-MM-DD]", date.strftime("%Y-%m-%d"))
        .replace("[HH:MM]", hour)
        .replace("[TITULO_REUNION]", title)
        .replace("[ASISTENTES]", attendees)
        .replace("[PROYECTO]", "LifeOps Orchestrator v2")
        .replace("standup | planning | 1:1 | brainstorming | decision", tipo)
        .replace("[NUEVA_TAREA_1]", "Enviar resumen y actas de la reunion")
        .replace("[NUEVA_TAREA_2]", "Ejecutar acciones definidas en la reunion")
        .replace("asistentes: []", f"asistentes: [{attendees}]")
        .replace("[[proyecto-relacionado]]", "[[lifeops-orchestrator-v2]]")
    )
    # Hydrate agenda section
    content = content.replace("## Agenda\n1.", f"## Agenda\n{agenda_items}")
    write(os.path.join(MEET_DIR, slug), content)

print(f"\n[3/3] 3 reuniones creadas.\n")
print("=" * 60)
print("SEED COMPLETADO")
print(f"  Vault     : {VAULT}")
print(f"  Proyecto  : 01-proyectos/{proj_slug}")
print(f"  Tareas    : 02-areas/ (5 archivos)")
print(f"  Reuniones : 08-reuniones/ (3 archivos)")
print("=" * 60)
