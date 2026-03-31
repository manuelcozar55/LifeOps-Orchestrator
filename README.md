# 🌌 LifeOps Orchestrator — AI Multi-Agent System

[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-ff6b35?style=for-the-badge)](https://github.com/langchain-ai/langgraph)
[![Azure OpenAI](https://img.shields.io/badge/LLM-Azure_OpenAI_GPT--4o--mini-0078d4?style=for-the-badge&logo=microsoft)](https://azure.microsoft.com/en-us/products/ai-services/openai-service)
[![Supabase](https://img.shields.io/badge/Persistence-Supabase_Postgres-3ecf8e?style=for-the-badge&logo=supabase)](https://supabase.com/)
[![LangSmith](https://img.shields.io/badge/Tracing-LangSmith-f7c59f?style=for-the-badge)](https://smith.langchain.com/)

> Un sistema multi-agente determinista para gestión de vida digital — Calendar, Gmail, Obsidian y Noticias — orquestado con LangGraph, persistido en Supabase y accesible a través de Telegram.

---

## 📐 Arquitectura del Sistema

El sistema implementa una **máquina de estados determinista de 5 nodos** con seguridad-first, calidad garantizada por LLM-reviewer y capacidad de pausa Human-in-the-Loop nativa.

```
👤 User (Telegram)
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│                  LangGraph State Machine                       │
│                                                               │
│  🛡️ Guardrail ──(blocked)──► 🛑 END                           │
│       │                                                       │
│       ▼ (secure)                                              │
│  🧩 Orchestrator ◄──────────────────── retry ─────┐           │
│       │ new request / HIL resume                  │           │
│       ▼                                           │           │
│  🧠 DomainExpert ──(3x fail)──────────────────► ⚖️ Reviewer   │
│       │ intent extracted                          │  ▲        │
│       ▼                                           │  │        │
│  🛠️ Architect ──(result)───────────────────────────┘  │        │
│       │                                               │        │
│       ├──(news/direct)──────────────────────────► ✅ END      │
│       └──(HIL: sync/delete/email)──► ⏸️ HIL Pause             │
│                                          │                    │
└──────────────────────────────────────────┼────────────────────┘
                                           │ human confirms
                                           ▼
                                     ✅ / ❌ Executed
```

### Diagramas editables

| Diagrama | Archivo | Descripción |
|---|---|---|
| Agent State Machine | `docs/diagram_flow.drawio.xml` | Flujo completo con HIL, reintentos y paths de seguridad |
| System Architecture | `docs/diagram_architecture.drawio.xml` | Capas: Interface → Agentes → Herramientas → Servicios externos |

Importa cualquier archivo `.drawio.xml` en [app.diagrams.net](https://app.diagrams.net/) para visualizarlo y editarlo.

---

## 🤖 Contratos de Agentes

Cada nodo tiene responsabilidad, input, output y condición de error bien definidos:

### 🛡️ Guardrail Agent
| Campo | Detalle |
|---|---|
| **Responsabilidad** | Auditar seguridad de cada petición. Detectar prompt injection y solicitudes fuera de dominio. Resetear `agent_trace` y `turn_tokens` al inicio de cada request. |
| **NO hace** | No procesa la lógica de negocio. No accede a tools externas. |
| **Input** | Último `HumanMessage` del estado |
| **Output** | `{is_secure, security_alert?, next_node, agent_trace: ["Guardrail"], turn_tokens: {input, output}}` |
| **Error** | Fail-open: si el LLM de auditoría falla, permite el paso |

### 🧩 Orchestrator Agent
| Campo | Detalle |
|---|---|
| **Responsabilidad** | Routing coordinator. Gestiona el flag HIL (`awaiting_user_input`). Resetea `iterations` y `error` en requests nuevas. |
| **NO hace** | No llama a tools. No analiza intención. |
| **Input** | Estado completo; tipo del último mensaje (Human vs AI) |
| **Output** | `{next_node: "domain_expert"/"architect", iterations, error, agent_trace}` |
| **Error** | Si no hay mensajes → `end_flow` |

### 🧠 Domain Expert Agent
| Campo | Detalle |
|---|---|
| **Responsabilidad** | Clasificar intención del usuario (12 intents) y extraer parámetros estructurados en un solo paso LLM con `UnifiedExtraction` (Pydantic). Calcular `confidence_score` inicial. |
| **NO hace** | No ejecuta herramientas. No valida calidad. |
| **Input** | Último `HumanMessage`, timestamp actual, lista de intents |
| **Output** | `{user_intent, active_context, confidence_score, next_node, agent_trace}` |
| **Error** | 3 reintentos internos; si fallan todos → `next_node: "reviewer"` con `confidence_score: 0.0` |

### 🛠️ Technical Architect Agent
| Campo | Detalle |
|---|---|
| **Responsabilidad** | Ejecutar herramientas según intent. Gestionar flows HIL antes de despachar por intent. Guardar resultados como `AIMessage`. |
| **NO hace** | No clasifica intención. No evalúa calidad de respuesta. |
| **Input** | `user_intent`, `active_context`, `messages`, `iterations` |
| **Output** | `{messages: [AIMessage], next_node, confidence_score, agent_trace}` |
| **Error** | Excepción no controlada → `error`, `next_node: "reviewer"` |

### ⚖️ Reviewer Agent
| Campo | Detalle |
|---|---|
| **Responsabilidad** | QA gate. Evalúa el último `AIMessage` con LLM. Aprueba o solicita reintento. Gestiona `MAX_ITERATIONS=5`. |
| **NO hace** | No llama a tools. No modifica respuestas directamente. |
| **Input** | Último `AIMessage`, `error` flag, `iterations` |
| **Output** | `{next_node: "end_flow"/"orchestrator", confidence_score, agent_trace}` |
| **Error** | Si el LLM de revisión falla → fail-open (aprueba por defecto). Si `MAX_ITERATIONS` → END con mensaje de error |

---

## 🧪 Intents Soportados

| Intent | Routing | Herramientas |
|---|---|---|
| `calendar_create/update/delete/query` | Architect → Calendar | Google Calendar API |
| `agenda_query` | Architect → Calendar + Obsidian | Calendar API + Obsidian |
| `obsidian_crud` | Architect → Obsidian | ObsidianVaultTool |
| `email` | Architect → HIL → Gmail send | Gmail API |
| `email_query` | Architect → Gmail search | Gmail API |
| `email_unread` | Architect → Gmail fetch + LLM summary → HIL reply | Gmail API |
| `sync_preview` | Architect → HIL → sync exec | Calendar + Obsidian |
| `news` | Architect → RSS + LLM → Obsidian cache → **END directo** | NewsFetcherTool |
| `unknown` | Architect → LLM general → Reviewer | Azure OpenAI |

---

## 🚀 Quickstart

### 1. Prerrequisitos

- Python 3.11+ o Docker
- Cuentas activas en: Azure OpenAI · Telegram BotFather · Supabase · Google Cloud
- `token.json` de Google OAuth (generado en el paso 4)

### 2. Configurar variables de entorno

```bash
cp .env.example .env
```

Edita `.env` con tus valores reales:

```env
# Azure OpenAI (obligatorio)
AZURE_OPENAI_ENDPOINT=https://TU-RECURSO.openai.azure.com/
AZURE_OPENAI_API_KEY=tu_clave_azure
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Telegram (obligatorio)
TELEGRAM_BOT_TOKEN=tu_token_del_bot

# Supabase (obligatorio — para checkpointing HIL y telemetría)
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

### 3. Autenticación Google OAuth (una sola vez, en local)

```bash
pip install google-auth-oauthlib google-api-python-client
python scripts/auth_setup.py
# Sigue el flujo OAuth en el navegador → genera token.json
```

### 4. Despliegue con Docker (recomendado)

```bash
docker-compose up --build -d
docker-compose logs -f  # Ver logs en tiempo real
```

### 5. Despliegue local sin Docker

```bash
pip install -r requirements.txt
python scripts/seed_obsidian.py  # Poblar vault de demo (opcional)
python -m src.main
```

---

## 💬 Ejemplos de Uso

### Consultas de agenda y tareas
```
"¿Qué tengo hoy?"                    → agenda_query (Calendar + Obsidian)
"Mis tareas pendientes"              → obsidian_crud/list/task
"Mis proyectos activos"              → obsidian_crud/list/project
"Mis reuniones de la semana"         → agenda_query (Calendar + Obsidian)
```

### Gestión de calendario
```
"Crea una reunión el lunes a las 10 con el equipo"  → calendar_create
"Mueve la reunión de kickoff al martes"             → calendar_update
"Borra el evento de revisión"                       → calendar_delete + HIL ✋
```

### Email inteligente
```
"Busca correos de Zebra"             → email_query
"¿Tengo correos sin leer?"           → email_unread → resumen + borrador HIL
"Redacta un email a ana@empresa.com" → email → borrador + HIL ✋
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

## 📊 Observabilidad

Cada respuesta en Telegram incluye automáticamente:

```
[contenido de la respuesta]

🧭 Ruta: Guardrail ➔ Orchestrator ➔ DomainExpert ➔ TechnicalArchitect ➔ Reviewer
📊 Confianza: 🟢 92%
```

| Mecanismo | Descripción |
|---|---|
| **structlog** | Logs estructurados (JSON) en todos los módulos |
| **agent_trace** | Trazado de nodos visitados; reset en cada request |
| **confidence_score** | Score 0.0–1.0 calculado en DomainExpert y refinado por Reviewer |
| **LangSmith @traceable** | Trazas de todas las herramientas en tiempo real |
| **turn_tokens** | Acumulación exacta de tokens de TODOS los nodos LLM (Guardrail, DomainExpert, Architect, Reviewer) vía campo de estado; no solo AIMessages |
| **Token telemetry** | Input/output tokens almacenados en Supabase por request via `turn_tokens` |
| **/stats** | Resumen: tokens hoy + totales + coste USD estimado |

---

## 🧪 Tests

```bash
# Ejecutar todos los tests (37 casos)
python -m pytest tests/test_agents.py -v

# Tests por categoría
python -m pytest tests/test_agents.py -k "TestObsidianVaultTool" -v
python -m pytest tests/test_agents.py -k "TestGuardrailNode" -v
python -m pytest tests/test_agents.py -k "TestDomainExpertNode" -v
```

Cobertura de tests:
- ✅ Utilidades de texto puro (`_slugify_title`, `_is_confirm`, `_is_cancel`)
- ✅ Obsidian CRUD completo (upsert, list, delete→archive, inbox, news)
- ✅ Validación de `GraphState` (todos los campos requeridos)
- ✅ Guardrail (allow, block, fail-open, trace reset)
- ✅ Orchestrator (routing, HIL resume, reset de error)
- ✅ DomainExpert (clasificación, confianza, error routing, serialización Enum)
- ✅ Sync plan building (slug matching)

---

## 🏗️ Estructura del Proyecto

```
LifeOps Orchestrator/
├── src/
│   ├── agent/
│   │   ├── graph.py          # LangGraph compilation + Postgres checkpointer (shared pool)
│   │   ├── nodes.py          # 5 agent nodes — lean orchestration only (~370 líneas)
│   │   ├── state.py          # GraphState TypedDict (shared state + turn_tokens)
│   │   ├── llm_client.py     # Instancia compartida AzureChatOpenAI + extract_tokens()
│   │   ├── utils.py          # Utilidades texto + _is_confirm/_is_cancel (first-word matching)
│   │   └── handlers/         # Lógica de dominio separada por integración
│   │       ├── calendar_handler.py   # create/update/delete/query + HIL delete
│   │       ├── email_handler.py      # compose/query/unread + HIL send
│   │       ├── obsidian_handler.py   # CRUD completo del vault
│   │       ├── agenda_handler.py     # Agenda combinada Calendar + Obsidian
│   │       ├── sync_handler.py       # Diff preview + HIL exec (lee hora_inicio/fin)
│   │       └── news_handler.py       # RSS + LLM + caché Obsidian
│   ├── models/
│   │   └── schemas.py        # Pydantic schemas: UnifiedExtraction, Enums, etc.
│   └── tools/
│       ├── telegram_bot.py   # Interface: WeakValueDictionary locks, turn_tokens telemetry
│       ├── google_cli.py     # Gmail + Calendar (CRUD + email body fetch)
│       ├── obsidian.py       # Vault CRUD: tasks, projects, meetings, news cache
│       ├── news.py           # RSS fetching + daily cache (path absoluto via __file__)
│       ├── database.py       # Token telemetry + stats (usa shared pool)
│       └── db_pool.py        # Singleton ConnectionPool compartido (LangGraph + DB)
├── docs/
│   ├── diagram_flow.drawio.xml         # State Machine diagram
│   ├── diagram_architecture.drawio.xml # System Architecture diagram
│   ├── DEFENSA_TECNICA.md              # ADR: decisiones técnicas y trade-offs
│   └── requirements_extracted.md       # Rubrica del reto técnico
├── tests/
│   └── test_agents.py      # 37 unit tests
├── scripts/
│   ├── auth_setup.py       # Google OAuth flow (ejecutar en local)
│   └── seed_obsidian.py    # Poblar vault de demo
├── data/
│   ├── obsidian_vault/     # Vault montado en Docker
│   └── news_cache.json     # Caché de noticias (renovación diaria)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## ⚙️ Decisiones Técnicas Clave

| Decisión | Alternativa | Justificación |
|---|---|---|
| **LangGraph** sobre CrewAI/AutoGen | Frameworks de agentes autónomos | Determinismo total; flujos predecibles; checkpointing nativo |
| **Postgres checkpointing** | In-memory | HIL real entre sesiones de Telegram; thread_id = chat_id |
| **agent_trace sin reducer** | Reducer acumulativo | Evita duplicación cross-request en Postgres checkpointing |
| **turn_tokens sin reducer** | Iterar AIMessages | Captura tokens de Guardrail/Reviewer (no generan AIMessages en state); telemetría exacta |
| **UnifiedExtraction con include_raw=True** | structured_output estándar | Permite extraer token_usage del mensaje raw para turn_tokens |
| **handlers/ separados de nodes.py** | Monolito único (~1.200 líneas) | Responsabilidad única por dominio; testabilidad y mantenibilidad |
| **Shared ConnectionPool (db_pool.py)** | Pool doble (graph + database) | Elimina conexiones duplicadas a Supabase; reducción ~50% conexiones |
| **WeakValueDictionary para chat locks** | Dict plano sin eviction | Locks inactivos se recolectan automáticamente; no hay memory leak |
| **_is_confirm() first-word matching** | Búsqueda de substring | Evita falsos positivos ("I don't think **ok**..."); seguro para operaciones destructivas |
| **sync hora_inicio/hora_fin desde frontmatter** | Hora fija 10:00–11:00 | Respeta los metadatos de cada reunión; evita colisiones en Calendar |
| **news cache path via __file__** | Ruta relativa "data/" | Funciona desde cualquier working directory; no falla en Docker |
| **UnifiedExtraction single-pass** | Múltiples LLM calls por dominio | Reducción de ~60% en tokens de extracción |
| **News → end_flow directo** | News → Reviewer | Contenido RSS ya curado; Reviewer innecesario y causaba retry loop |
| **Guardrail fail-open** | Fail-closed | UX: mejor tolerar 1 petición mala que bloquear todas por fallo LLM |
| **Obsidian 0-token cache** | Re-llamar LLM cada vez | Las noticias no cambian durante el día; $0 en tokens repetidos |
| **check_connection + max_idle=60** | Sin health check, max_idle=300 | Elimina `SSL error: unexpected eof` causado por PgBouncer de Supabase cerrando conexiones idle tras ~60s |
| **TCP keepalives (idle=30s)** | Sin keepalives | Heartbeat a nivel OS; detecta desconexiones silenciosas en NAT/firewalls antes de que fallen queries |
| **reconnect_timeout=300 en pool** | Sin reconexión automática | El pool se recupera solo de outages transitorios hasta 5 min; zero downtime para el usuario |
| **_with_retry() en DatabaseManager** | Sin reintentos a nivel app | 2 reintentos con backoff (0.5s, 1s) para errores mid-query que escapan al check_connection |

---

## 🛠️ Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| `SUPABASE_DB_URL` error al arrancar | URL incorrecta o DB no inicializada | Revisa el formato en `docs/SUPABASE_GUIDE.md` |
| `token.json not found` | Sin autenticación Google | Ejecuta `python scripts/auth_setup.py` en local y copia el archivo |
| Bot no responde | Token de Telegram incorrecto | Verifica `TELEGRAM_BOT_TOKEN` en `.env` |
| Todos los intents → `unknown` | Deployment de Azure incorrecto | Verifica `AZURE_OPENAI_CHAT_DEPLOYMENT` y que el modelo esté desplegado |
| `/stats` devuelve 0 tokens | Pool DB no inicializado | La tabla se crea automáticamente; comprueba logs de `_init_schema` |
| `/stats` subestima tokens | Versión anterior usaba AIMessages | Actualizado: `turn_tokens` captura todos los nodos (Guardrail, Reviewer incluidos) |
| Noticias muestran solo el header | Cache corrupta de hoy | Borra `data/obsidian_vault/noticias/YYYY-MM-DD-noticias.md` |
| `SSL error: unexpected eof` / `discarding closed connection` | PgBouncer cierra conexiones idle antes que el pool cliente | Resuelto: `check_connection` + `max_idle=60` + TCP keepalives en `db_pool.py` |

---

## 📦 Dependencias Principales

| Librería | Versión | Uso |
|---|---|---|
| `langgraph` | ≥0.0.26 | State machine multi-agente |
| `langgraph-checkpoint-postgres` | ≥1.0.1 | HIL persistente |
| `langchain-openai` | ≥0.1.3 | Azure OpenAI + structured output |
| `psycopg[binary,pool]` | ≥3.1.18 | Pool Postgres |
| `pydantic` | ≥2.6.3 | Contratos de datos (v2) |
| `python-telegram-bot` | ≥21.0.1 | Interface Telegram async |
| `structlog` | ≥24.1.0 | Logs estructurados |
| `langsmith` | ≥0.1.23 | Trazabilidad LLM |
| `google-api-python-client` | ≥2.122.0 | Gmail + Calendar |

---

*LifeOps Orchestrator — Prueba técnica para Zebra AI Transformation Company · Ingeniero/a de IA*
