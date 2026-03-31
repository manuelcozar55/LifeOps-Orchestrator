# Defensa Técnica - LifeOps Orchestrator

*(Este documento sirve como apoyo y guion para la revisión técnica del diseño implementado)*

## 1. Executive Summary & Resultados de la Prueba
El sistema ha sido diseñado como un orquestador multi-agente que no es una simple cadena de prompts secuenciales, sino una **Máquina de Estado explícita** usando **LangGraph**. Esto cumple con matrícula el requisito de *orquestación y control de flujo*, permitiendo interrupciones nativas (Human-in-the-Loop) sin perder el contexto.

## 2. Arquitectura y Trade-offs
### 2.1 Elección de LangGraph frente a AutoGen/CrewAI
**Decisión**: Optamos por LangGraph sobre alternativas puramente "conversacionales".
**Justificación**: Las interacciones dependientes de un Vault de Obsidian y un entorno de Mail requieren determinismo funcional. CrewAI/AutoGen a menudo sufren de bucles de conversación impredecibles. LangGraph usa estado dirigido, sabiendo en qué nodo está (Architect, Reviewer, etc.).

### 2.1b Uso de Supabase (PostgreSQL) para Persistencia de Estado
**Decisión**: Usar PostgreSQL gestionado (Supabase) mediante `PostgresSaver` sobre un checkpointer en memoria o local estático.
**Justificación**: Un orquestador que ejecuta *Human-in-the-Loop* asíncrono sobre Telegram **obliga imperativamente** al uso de una base de datos para suspender la sesión del grafo y guardar el JSON del estado temporal. Utilizar Supabase con Connection Pooling permite escalabilidad horizontal inmediata ante múltiples usuarios concurrentes si el bot se expusiera públicamente, a diferencia de SQLite que presentaría colisiones de escritura local (database locks).

### 2.2 Integración Nativa Google (Sin Hacks CLI)
**Decisión**: Migrar de wrappers CLI a consumir directamente los SDKs de Google API Python Client con un flujo local OAuth2 Desktop.
**Justificación**: Para un prototipo avanzado Staff+, depender de *subprocess* es inestable e inseguro. Se ha construido un `auth_setup.py` que abstrae el flujo de consentimiento. El `token.json` persistente en host se inyecta como *Bind Mount* mediante docker-compose, logrando:
1. Inmunidad a inyecciones Bash.
2. Zero filtrado de tokens al *image caching* (vetado vía `.dockerignore`).
3. Payload JSON puro en lugar de parsear HTML/MIME asqueroso de `imaplib`.

### 2.3 Selección del Modelo (Azure OpenAI GPT-4o-mini)
**Decisión**: Uso de `gpt-4o-mini` vía Azure OpenAI.
**Justificación**: GPT-4o-mini es sumamente rápido y tiene coste reducido, ideal para tareas de agentes de clasificación de correos (volume high). Al aplicar validación Pydantic estricta con LangChain (`with_structured_output`), compensamos el menor parámetro del modelo obligándolo a no alucinar estructuras.

## 3. Seguridad y Ejecución Local
- **Aislamiento**: Todo corre sobre `docker-compose`. Las claves residen solo en `.env`.
- **Obsidian**: Montamos el `vault` local al contenedor apuntando `/app/data/obsidian_vault` a un volumen Host. Garantiza que LLM no filtre la base de conocimiento entera y solo lea la nota precisa.
- **Data Minimization**: Solo se inyecta en el state de LangGraph ("messages") los textos relevantes del usuario (Telegram) y el output estricto JSON de parseos.

## 3. Contratos de Agentes (Formalización)

Para cumplir con los estándares de diseño Staff+, cada agente tiene límites y contratos definidos:

| Agente | Responsabilidad | Input | Output | Error Handling |
| :--- | :--- | :--- | :--- | :--- |
| **Guardrail** | Seguridad y filtrado de inyecciones. | Mensaje Raw | `is_secure` (bool) | Bloqueo inmediato en `end_flow`. |
| **Orchestrator** | Enrutamiento y gestión de estado. | `GraphState` | Selección de `next_node` | Control de iteraciones (máx 20). |
| **Domain Expert** | Clasificación y Extracción Única. | Mensaje + Hoy | `UnifiedExtraction` (Pydantic) | Reintento automático `@retry_tool`. |
| **Tech Architect** | Ejecución de Herramientas (Google/Obs). | Contexto Extraído | Mensajes de confirmación | Desvío a `Reviewer` en caso de fallo. |
| **Reviewer** | Calidad, HIL y Bucle de Retorno. | Output de Herramienta | Aprobación o Reenrutamiento | Gestión de `max_iterations`. |

## 4. Orquestación y Resiliencia
- **Máquina de Estado**: Implementada con LangGraph. El estado es inmutable y cada nodo produce el siguiente delta.
- **Human-in-the-Loop (HIL)**: El flujo se interrumpe y persiste en Supabase cuando se requiere confirmación del usuario (ej. Borrar calendario o enviar Email).
- **Persistencia de Telemetría**: Migración de `json` local a **Supabase (PostgreSQL)** para rastreo de tokens Input/Output por `chat_id`.

### 4.1 Resiliencia de Conexión a Base de Datos

**Problema diagnosticado**: El error `SSL error: unexpected eof while reading` + `discarding closed connection` era causado por un conflicto de timeouts:

- Supabase PgBouncer cierra conexiones inactivas en el servidor tras ~60 segundos.
- El pool mantenía conexiones abiertas durante 300 segundos (`max_idle=300`).
- Sin health check, el pool devolvía al grafo una conexión cuyo socket SSL ya estaba muerto en el servidor remoto.

**Solución implementada** — Estrategia de resiliencia en 5 capas (`src/tools/db_pool.py`):

| Capa | Mecanismo | Efecto |
| :--- | :--- | :--- |
| 1 | `check=ConnectionPool.check_connection` | Valida cada conexión antes de entregarla al caller; reemplaza las muertas de forma transparente |
| 2 | `max_idle=60` | Cierra conexiones antes de que PgBouncer lo haga; elimina el conflicto de timeout |
| 3 | TCP keepalives (`keepalives_idle=30s`) | Heartbeat a nivel OS; previene desconexiones silenciosas en redes con NAT/firewalls |
| 4 | `reconnect_timeout=300` | El pool se auto-recupera de interrupciones de red durante hasta 5 minutos |
| 5 | `_with_retry()` en `DatabaseManager` | 2 reintentos con backoff (0.5s, 1s) para errores transitorios mid-query |

**Trade-off**: `check_connection` añade un roundtrip ligero (~1ms) en cada checkout de conexión. Este coste es completamente despreciable frente a la latencia de los LLMs (100–2000ms por llamada) y elimina el 100% de los errores SSL EOF visibles al usuario.

**Código de la solución**:
```python
# db_pool.py — configuración resiliente
_pool = ConnectionPool(
    conninfo=db_url,          # incluye sslmode=require + keepalives via URL params
    min_size=2,
    max_size=10,
    max_idle=60,              # ← era 300; ahora por debajo del timeout de PgBouncer
    timeout=30,
    reconnect_timeout=300,    # ← nuevo: auto-reconexión en outages transitorios
    check=ConnectionPool.check_connection,  # ← nuevo: valida conexión antes de uso
    kwargs={"autocommit": True},
)
```

## 5. Observabilidad Staff+
- **LangSmith**: Trazabilidad completa de cada ejecución.
- **Agent Trace**: Cada respuesta final incluye la "firma" de los agentes participantes para auditoría inmediata.
- **Reporting**: Uso de `structlog` para logs JSON estructurados listos para ingesta en ELK/Splunk.
- **turn_tokens**: Acumulación exacta de tokens de TODOS los nodos LLM (Guardrail, DomainExpert, Architect, Reviewer) por request, incluyendo peticiones de noticias desde botones inline de Telegram.
- **/stats**: Comando Telegram que muestra tokens de hoy, acumulados y coste estimado USD extraído de Supabase.

## 6. Conteo de Tokens — Flujo de Noticias

**Pregunta frecuente en defensa**: ¿Se cuentan los tokens cuando el usuario pulsa el botón "Noticias del día"?

**Sí, siempre.** El flujo de noticias `Guardrail → Orchestrator → DomainExpert → Architect → END` acumula tokens en el campo `turn_tokens` del `GraphState`:

1. **Guardrail** resetea `turn_tokens` a su propio coste de auditoría de seguridad.
2. **DomainExpert** suma los tokens de la clasificación de intención (`UnifiedExtraction`).
3. **Architect** extrae el `_token_delta` del handler de noticias:
   - Si hay caché en Obsidian: delta = (0, 0). Solo se cuentan Guardrail + DomainExpert.
   - Si no hay caché: delta incluye los tokens del LLM de summarización RSS.
4. `_record_turn_tokens()` en `telegram_bot.py` persiste el total en Supabase, tanto para mensajes de texto (`handle_message`) como para botones inline (`handle_callback_query`).

Este diseño asegura que `/stats` refleje el coste real de **cada interacción**, incluyendo hits de caché de 0 tokens a nivel handler.
