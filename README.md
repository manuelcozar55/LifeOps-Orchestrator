<p align="center">
  <img src="data/icon.png" alt="LifeOps Logo" width="1000"/>
</p>

# LifeOps Orchestrator — AI Multi-Agent System

[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-ff6b35?style=for-the-badge)](https://github.com/langchain-ai/langgraph)
[![Azure OpenAI](https://img.shields.io/badge/LLM-Azure_OpenAI_GPT--4o--mini-0078d4?style=for-the-badge&logo=microsoft)](https://azure.microsoft.com/en-us/products/ai-services/openai-service)
[![Supabase](https://img.shields.io/badge/Persistence-Supabase_Postgres-3ecf8e?style=for-the-badge&logo=supabase)](https://supabase.com/)
[![LangSmith](https://img.shields.io/badge/Tracing-LangSmith-f7c59f?style=for-the-badge)](https://smith.langchain.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776ab?style=for-the-badge&logo=python)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-37%20passing-success?style=for-the-badge)](tests/test_agents.py)

> Sistema multi-agente determinista para gestión de vida digital: Calendar, Gmail, Obsidian y Noticias. Orquestado con LangGraph, persistido en Supabase PostgreSQL y accesible vía Telegram.

---

## Arquitectura del Sistema

### Diagrama General

![LifeOps Orchestrator — System Architecture](docs/LifeOpsDiagram.png)

### Qué muestra el diagrama

El diagrama describe las **cuatro capas** que componen el sistema y cómo interactúan entre sí:

**1. Interfaz de usuario (izquierda)**
El punto de entrada es un **Telegram Bot** (`python-telegram-bot`). El usuario envía un mensaje en lenguaje natural — por ejemplo, "¿Qué tengo mañana?" o "Redacta un correo a Ana" — y el bot lo inyecta en el grafo como un `HumanMessage`.

**2. LangGraph AI Pipeline (centro izquierda)**
El núcleo del sistema es una **máquina de estados de 5 nodos** implementada con LangGraph. Cada nodo tiene un rol exclusivo y contratos de entrada/salida estrictos:

| Nodo | Rol | Detalle |
|---|---|---|
| **Guardrail** | Seguridad | Primer filtro de cada request. Detecta prompt injection y solicitudes fuera de dominio. Fail-open si el LLM de auditoría falla. |
| **Orchestrator** | Routing | Decide el siguiente nodo según el tipo de mensaje (nuevo request vs. respuesta HIL) y gestiona el flag `awaiting_user_input`. |
| **DomainExpert** | Extracción | Clasifica la intención del usuario entre 12 intents y extrae parámetros con un único call LLM (`UnifiedExtraction` Pydantic). |
| **TechnicalArchitect** | Ejecución | Despacha la herramienta correcta según el intent. Es el único nodo que llama a los Domain Handlers e integraciones externas. |
| **Reviewer** | Calidad | Gate de QA final. Evalúa el output con LLM. Puede aprobar (`end_flow`) o solicitar reintento (`orchestrator`). Límite: `MAX_ITERATIONS=5`. |

El diagrama también muestra tres tipos de flujo especiales:
- **Retry loop** (línea roja): si el Reviewer rechaza la respuesta, el grafo vuelve al Orchestrator para reintentar.
- **HIL Pause** (rombo naranja 07:00): el grafo se suspende en Supabase esperando confirmación del usuario antes de ejecutar operaciones destructivas (borrar evento, enviar email, sincronizar).
- **Scheduled trigger** (flecha naranja): el job de las 07:00 inyecta automáticamente "Noticias del día" en el grafo.

**3. Domain Handlers y Servicios Externos (centro derecha)**
El `TechnicalArchitect` no llama directamente a las APIs externas — delega en handlers especializados que encapsulan toda la lógica de integración:

| Handler | Servicio externo |
|---|---|
| Calendar Handler | Google Calendar API |
| Email Handler | Gmail API |
| News Handler | RSS Feeds → LLM summarization → Obsidian cache |
| Obsidian Handler | Sistema de ficheros local (vault montado) |
| Agenda Handler | Google Calendar + Obsidian (vista combinada) |
| Sync Handler | Diff Calendar ↔ Obsidian → HIL → sincronización |

Todos los nodos LLM del pipeline llaman a **Azure OpenAI GPT-4o-mini** (flechas azules discontinuas). Las trazas de todas las ejecuciones se envían a **LangSmith** automáticamente.

**4. Capa de Persistencia (inferior)**
Tres mecanismos de persistencia con responsabilidades diferenciadas:
- **Supabase PostgreSQL**: checkpointing del estado LangGraph (necesario para HIL asíncrono) y telemetría de tokens por conversación.
- **Obsidian Vault**: base de conocimiento estructurada del usuario (tareas, proyectos, reuniones, caché de noticias).
- **news_cache.json**: caché diaria de artículos RSS formateados, evita tokens repetidos.

---

### Máquina de Estado — Flujo Detallado

```
Usuario (Telegram)
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│                 LangGraph State Machine                      │
│                                                             │
│  Guardrail ──(blocked)──► END                               │
│      │                                                      │
│      ▼ (secure)                                             │
│  Orchestrator ◄──────────────── retry ──────────┐           │
│      │ new request / HIL resume                 │           │
│      ▼                                          │           │
│  DomainExpert ──(3x fail)──────────────────► Reviewer       │
│      │ intent extracted                         │  ▲        │
│      ▼                                          │  │        │
│  TechnicalArchitect ──(result)──────────────────┘  │        │
│      │                                             │        │
│      ├──(news/direct)──────────────────────► END            │
│      └──(HIL: sync/delete/email)──► Pause (Supabase)        │
│                                          │                  │
└──────────────────────────────────────────┼──────────────────┘
                                           │ usuario confirma
                                           ▼
                                     Ejecutado / Cancelado
```

---

## Contratos de Agentes

Cada nodo tiene responsabilidad, input, output y condición de error bien definidos:

### Guardrail Agent
| Campo | Detalle |
|---|---|
| **Responsabilidad** | Auditar seguridad de cada petición. Detectar prompt injection y solicitudes fuera de dominio. Resetear `agent_trace` y `turn_tokens` al inicio de cada request. |
| **NO hace** | No procesa lógica de negocio. No accede a herramientas externas. |
| **Input** | Último `HumanMessage` del estado |
| **Output** | `{is_secure, security_alert?, next_node, agent_trace: ["Guardrail"], turn_tokens: {input, output}}` |
| **Error** | Fail-open: si el LLM de auditoría falla, permite el paso para no bloquear UX |

### Orchestrator Agent
| Campo | Detalle |
|---|---|
| **Responsabilidad** | Routing coordinator. Gestiona el flag HIL (`awaiting_user_input`). Resetea `iterations` y `error` en requests nuevas. |
| **NO hace** | No llama a herramientas. No analiza intención. |
| **Input** | Estado completo; tipo del último mensaje (Human vs AI) |
| **Output** | `{next_node: "domain_expert"/"architect", iterations, error, agent_trace}` |
| **Error** | Si no hay mensajes → `end_flow` |

### Domain Expert Agent
| Campo | Detalle |
|---|---|
| **Responsabilidad** | Clasificar intención del usuario (12 intents) y extraer parámetros estructurados en un único call LLM con `UnifiedExtraction` (Pydantic). Calcular `confidence_score` inicial. |
| **NO hace** | No ejecuta herramientas. No valida calidad. |
| **Input** | Último `HumanMessage`, timestamp actual, lista de intents |
| **Output** | `{user_intent, active_context, confidence_score, next_node, agent_trace}` |
| **Error** | 3 reintentos internos; si fallan todos → `next_node: "reviewer"` con `confidence_score: 0.0` |

### Technical Architect Agent
| Campo | Detalle |
|---|---|
| **Responsabilidad** | Ejecutar herramientas según intent. Gestionar flows HIL antes de despachar por intent. Guardar resultados como `AIMessage`. |
| **NO hace** | No clasifica intención. No evalúa calidad de respuesta. |
| **Input** | `user_intent`, `active_context`, `messages`, `iterations` |
| **Output** | `{messages: [AIMessage], next_node, confidence_score, agent_trace}` |
| **Error** | Excepción no controlada → `error`, `next_node: "reviewer"` |

### Reviewer Agent
| Campo | Detalle |
|---|---|
| **Responsabilidad** | QA gate. Evalúa el último `AIMessage` con LLM. Aprueba o solicita reintento. Gestiona `MAX_ITERATIONS=5`. |
| **NO hace** | No llama a herramientas. No modifica respuestas directamente. |
| **Input** | Último `AIMessage`, `error` flag, `iterations` |
| **Output** | `{next_node: "end_flow"/"orchestrator", confidence_score, agent_trace}` |
| **Error** | Si el LLM de revisión falla → fail-open (aprueba por defecto). Si `MAX_ITERATIONS` → END con mensaje de error |

---

## Intents Soportados

| Intent | Routing | Herramientas |
|---|---|---|
| `calendar_create/update/delete/query` | Architect → Calendar Handler | Google Calendar API |
| `agenda_query` | Architect → Agenda Handler | Calendar API + Obsidian |
| `obsidian_crud` | Architect → Obsidian Handler | Vault local |
| `email` | Architect → HIL → Gmail send | Gmail API |
| `email_query` | Architect → Gmail search | Gmail API |
| `email_unread` | Architect → Gmail fetch + LLM summary | Gmail API |
| `sync_preview` | Architect → HIL → sync exec | Calendar + Obsidian |
| `news` | Architect → RSS + LLM → cache → **END directo** | NewsFetcher + Obsidian |
| `unknown` | Architect → LLM general → Reviewer | Azure OpenAI |

---

## Quickstart

### 1. Prerrequisitos

- Python 3.11+ o Docker
- Cuentas activas en: Azure OpenAI · Telegram BotFather · Supabase · Google Cloud

### 2. Clonar e instalar dependencias

```bash
git clone https://github.com/ManuelCozarBaranguan/LifeOps-Orchestrator.git
cd LifeOps-Orchestrator
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```bash
cp .env.example .env
```

Edita `.env` con tus valores:

```env
# Azure OpenAI (obligatorio)
AZURE_OPENAI_ENDPOINT=https://TU-RECURSO.openai.azure.com/
AZURE_OPENAI_API_KEY=tu_clave_azure
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Telegram (obligatorio)
TELEGRAM_BOT_TOKEN=tu_token_del_bot

# Supabase — checkpointing HIL + telemetría de tokens
SUPABASE_DB_URL=postgresql://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-eu-west-1.pooler.supabase.com:5432/postgres

# Google OAuth (obligatorio para Gmail/Calendar)
GOOGLE_TOKEN_PATH=/app/token.json

# LangSmith (opcional — activa trazabilidad completa)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=tu_clave_langsmith
LANGCHAIN_PROJECT=lifeops-orchestrator

# Obsidian vault path (dentro del contenedor)
OBSIDIAN_VAULT_PATH=/app/obsidian_vault
```

### 4. Autenticación Google OAuth (una sola vez, en local)

```bash
pip install google-auth-oauthlib google-api-python-client
python scripts/auth_setup.py
# Sigue el flujo OAuth en el navegador → genera token.json
```

### 5. Despliegue con Docker (recomendado)

```bash
docker-compose up --build -d
docker-compose logs -f
```

### 6. Despliegue local sin Docker

```bash
python scripts/seed_obsidian.py  # Poblar vault de demo (opcional)
python -m src.main
```

---

## Guía de configuración de Supabase

Supabase es necesario para dos funciones críticas: el checkpointing de LangGraph (que permite pausar el grafo entre mensajes de Telegram para Human-in-the-Loop) y la telemetría de tokens.

### Pasos

1. Crea un proyecto en [supabase.com](https://supabase.com) (plan gratuito suficiente)
2. En **Settings → Database → Connection string**, copia la URL de **Transaction pooler** (puerto 5432)
3. Pégala en `.env` como `SUPABASE_DB_URL`
4. Las tablas se crean automáticamente al arrancar el sistema:
   - `checkpoints`, `checkpoint_blobs`, `checkpoint_writes` — gestionadas por LangGraph
   - `token_usage` — gestionada por `DatabaseManager` (telemetría)

Para instrucciones detalladas: [`docs/SUPABASE_GUIDE.md`](docs/SUPABASE_GUIDE.md)

---

## Ejemplos de Uso

### Agenda y tareas
```
"¿Qué tengo hoy?"                    → agenda_query (Calendar + Obsidian)
"Mis tareas pendientes"              → obsidian_crud/list/task
"Mis proyectos activos"              → obsidian_crud/list/project
"Mis reuniones de la semana"         → agenda_query
```

### Gestión de calendario
```
"Crea una reunión el lunes a las 10 con el equipo"  → calendar_create
"Mueve la reunión de kickoff al martes"             → calendar_update
"Borra el evento de revisión"                       → calendar_delete + HIL
```

### Email inteligente
```
"Busca correos de Zebra"             → email_query
"¿Tengo correos sin leer?"           → email_unread → resumen + borrador HIL
"Redacta un email a ana@empresa.com" → email → borrador + HIL
```

### Sincronización y noticias
```
"Sincroniza mis reuniones"           → sync_preview → diff → HIL → sync_execute
"Noticias del día"                   → news (cache Obsidian → si miss: RSS+LLM)
```

### Comandos de sistema
```
/start   → Menú principal con botones inline
/stats   → Telemetría: tokens hoy/total + coste estimado USD
```

---

## Observabilidad

Cada respuesta incluye metadatos de trazabilidad:

| Mecanismo | Descripción |
|---|---|
| **structlog** | Logs estructurados JSON en todos los módulos |
| **agent_trace** | Secuencia de nodos visitados; se resetea en cada request |
| **confidence_score** | Score 0.0–1.0 calculado en DomainExpert y refinado por Reviewer |
| **LangSmith** | Trazas de todas las ejecuciones de herramientas en tiempo real |
| **turn_tokens** | Tokens acumulados de todos los nodos LLM (Guardrail, DomainExpert, Architect, Reviewer) |
| **Token telemetry** | Input/output tokens almacenados en Supabase por request |
| **/stats** | Resumen: tokens hoy + totales + coste USD estimado |

---

## Tests

```bash
# Ejecutar todos los tests (37 casos)
python -m pytest tests/test_agents.py -v

# Tests por módulo
python -m pytest tests/test_agents.py -k "TestObsidianVaultTool" -v
python -m pytest tests/test_agents.py -k "TestGuardrailNode" -v
python -m pytest tests/test_agents.py -k "TestDomainExpertNode" -v
```

Cobertura:
- Utilidades de texto puro (`_slugify_title`, `_is_confirm`, `_is_cancel`)
- Obsidian CRUD completo (upsert, list, delete→archive, inbox, news)
- Validación de `GraphState` (todos los campos requeridos)
- Guardrail (allow, block, fail-open, trace reset)
- Orchestrator (routing, HIL resume, reset de error)
- DomainExpert (clasificación, confianza, error routing, serialización Enum)
- Sync plan building (slug matching)

---

## Estructura del Proyecto

```
LifeOps-Orchestrator/
├── src/
│   ├── agent/
│   │   ├── graph.py          # Compilación LangGraph + checkpointer Postgres
│   │   ├── nodes.py          # 5 nodos agente (Guardrail, Orchestrator, DomainExpert, Architect, Reviewer)
│   │   ├── state.py          # GraphState TypedDict — estado compartido
│   │   ├── llm_client.py     # Instancia compartida AzureChatOpenAI + extract_tokens()
│   │   ├── utils.py          # Utilidades texto + _is_confirm/_is_cancel (first-word matching)
│   │   └── handlers/
│   │       ├── calendar_handler.py   # CRUD Google Calendar + HIL delete
│   │       ├── email_handler.py      # Compose/query/unread Gmail + HIL send
│   │       ├── obsidian_handler.py   # CRUD vault local
│   │       ├── agenda_handler.py     # Vista combinada Calendar + Obsidian
│   │       ├── sync_handler.py       # Diff preview + HIL sync execution
│   │       └── news_handler.py       # RSS + LLM + caché Obsidian
│   ├── models/
│   │   └── schemas.py        # Pydantic schemas: UnifiedExtraction, Enums, etc.
│   └── tools/
│       ├── telegram_bot.py   # Interface Telegram async + telemetría turn_tokens
│       ├── google_cli.py     # Gmail + Calendar (OAuth2 directo)
│       ├── obsidian.py       # Vault CRUD: tasks, projects, meetings, news
│       ├── news.py           # RSS fetching + caché diaria
│       ├── database.py       # Telemetría de tokens + /stats (usa shared pool)
│       └── db_pool.py        # Singleton ConnectionPool — compartido por LangGraph y DB
├── docs/
│   ├── LifeOpsDiagram.png          # Diagrama de arquitectura (este README)
│   ├── LifeOpsDiagram.excalidraw   # Fuente editable del diagrama
│   ├── DEFENSA_TECNICA.md          # Guion de presentación + ADR completo
│   ├── SUPABASE_GUIDE.md           # Configuración de Supabase paso a paso
│   └── requirements_extracted.md   # Rúbrica del reto técnico
├── tests/
│   └── test_agents.py      # 37 unit tests
├── scripts/
│   ├── auth_setup.py       # Google OAuth flow (ejecutar en local, una vez)
│   └── seed_obsidian.py    # Poblar vault con datos de demo
├── data/
│   ├── obsidian_vault/     # Vault montado en Docker
│   └── news_cache.json     # Caché de noticias (renovación diaria)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Decisiones Técnicas Clave

| Decisión | Alternativa descartada | Justificación |
|---|---|---|
| **LangGraph** sobre CrewAI/AutoGen | Frameworks conversacionales autónomos | Determinismo total; flujos predecibles; checkpointing nativo para HIL |
| **Postgres checkpointing** | In-memory / SQLite | HIL real entre sesiones Telegram asíncronas; `thread_id = chat_id` |
| **UnifiedExtraction single-pass** | Múltiples calls LLM por dominio | ~60% menos tokens en extracción; menor latencia |
| **handlers/ separados de nodes.py** | Monolito (~1.200 líneas) | Responsabilidad única por dominio; testabilidad independiente |
| **Shared ConnectionPool** | Pool doble (graph + database) | ~50% menos conexiones a Supabase; sin deadlocks |
| **WeakValueDictionary para chat locks** | Dict plano | Locks inactivos se recolectan automáticamente; no hay memory leak |
| **_is_confirm() first-word matching** | Búsqueda de substring | Evita falsos positivos en operaciones destructivas |
| **Guardrail fail-open** | Fail-closed | UX: mejor tolerar 1 petición mala que bloquear todas por fallo LLM |
| **News → end_flow directo** | News → Reviewer | RSS ya curado; Reviewer innecesario causaba retry loop artificial |
| **check_connection + max_idle=60** | Sin health check, max_idle=300 | Elimina `SSL EOF` por timeout de PgBouncer de Supabase |
| **TCP keepalives (idle=30s)** | Sin keepalives | Detecta desconexiones silenciosas en NAT antes de que fallen queries |

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| Error en `SUPABASE_DB_URL` al arrancar | URL incorrecta o DB no inicializada | Revisa formato en `docs/SUPABASE_GUIDE.md` |
| `token.json not found` | Sin autenticación Google | Ejecuta `python scripts/auth_setup.py` en local |
| Bot no responde | Token de Telegram incorrecto | Verifica `TELEGRAM_BOT_TOKEN` en `.env` |
| Todos los intents → `unknown` | Deployment Azure incorrecto | Verifica `AZURE_OPENAI_CHAT_DEPLOYMENT` |
| `/stats` devuelve 0 tokens | Pool DB no inicializado | Tabla se crea automáticamente; revisa logs de `_init_schema` |
| Noticias muestran solo el header | Caché corrupta | Borra `data/obsidian_vault/noticias/YYYY-MM-DD-noticias.md` |
| `SSL error: unexpected eof` | PgBouncer cierra idle connections | Resuelto en `db_pool.py`: `check_connection` + `max_idle=60` + keepalives |

---

## Dependencias Principales

| Librería | Versión | Uso |
|---|---|---|
| `langgraph` | ≥0.0.26 | State machine multi-agente |
| `langgraph-checkpoint-postgres` | ≥1.0.1 | HIL persistente entre sesiones |
| `langchain-openai` | ≥0.1.3 | Azure OpenAI + structured output Pydantic |
| `psycopg[binary,pool]` | ≥3.1.18 | Pool Postgres resiliente |
| `pydantic` | ≥2.6.3 | Contratos de datos (v2) |
| `python-telegram-bot` | ≥21.0.1 | Interface Telegram async |
| `structlog` | ≥24.1.0 | Logs estructurados JSON |
| `langsmith` | ≥0.1.23 | Trazabilidad LLM |
| `google-api-python-client` | ≥2.122.0 | Gmail + Calendar |

---

*LifeOps Orchestrator — Sistema multi-agente determinista para gestión de vida digital: Calendar, Gmail, Obsidian y Noticias. Orquestado con LangGraph, persistido en Supabase PostgreSQL y accesible vía Telegram. Diseñado como prueba técnica de Ingeniero/a de IA para Zebra AI Transformation Company.*
