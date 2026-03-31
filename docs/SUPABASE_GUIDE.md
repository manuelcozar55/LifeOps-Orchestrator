# Guía de Integración con Supabase (PostgreSQL)

## 1. ¿Por qué es necesaria una base de datos?
En LangGraph, si un agente necesita **esperar a que el usuario haga algo** (como aprobar un email en Telegram), el grafo corta su ejecución (se suspende). Para poder *reanudar* la ejecución más tarde exactamente donde lo dejó, conservando todo el contexto de la conversación, los borradores redactados y la intención, **LangGraph necesita un "Checkpointer"**.
Sin base de datos, el orquestador tiene "amnesia" entre mensaje y mensaje, haciendo imposible el patrón requerido de Human-in-the-loop. Inicialmente usamos SQLite por simplicidad local, pero Supabase ofrece un sistema robusto, listo para producción y con un dashboard para debuggear el estado.

## 2. Ventajas de Supabase (PostgreSQL) en la arquitectura
- **Despliegue Serverless**: No necesitas arrancar una BBDD local en Docker pesado.
- **Connection Pooling Nativo**: Ideal para arquitecturas *serverless* o bots asíncronos concurrentes.
- **Seguridad y Backups**: Gestionado por Supabase.
- **Visualización**: Interfaz web intuitiva en Supabase Studio para inspeccionar las tablas `checkpoints` que LangGraph crea automáticamente.

## 3. Pasos para configurarlo a la perfección

### Paso 1: Crear proyecto en Supabase
1. Ve a [Supabase.com](https://supabase.com/) y entra con tu cuenta o GitHub.
2. Da click en **"New Project"**.
3. Elige tu organización, un nombre (ej. `LifeOps-Orchestrator`), y define una **contraseña segura para la base de datos** (Guárdala bien).
4. Selecciona la región más cercana a ti (ej. Frankfurt o London) y dale a "Create new project".
5. Espera unos 1-2 minutos a que la base de datos se aprovisione.

### Paso 2: Obtener la cadena de conexión
1. En el panel de control de tu proyecto Supabase, ve a **Settings** (icono engranaje) -> **Database**.
2. Haz scroll hasta la sección **"Connection string"**.
3. Asegúrate de seleccionar el tab **Use connection pooling** (Modo Transaction o Session valen, transaction suele ser recomendado en bots). Esto apuntará al puerto `6543`.
4. Selecciona el formato **URI** en lugar de JDBC o psql.
5. Copia la URL, debería lucir algo como: `postgresql://postgres.[ID]:[PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres`.

### Paso 3: Configurar LifeOps Orchestrator
1. Abre tu fichero local `.env` (si no lo tienes, copia `.env.example`).
2. Sustituye la variable `SUPABASE_DB_URL` por la URL que copiaste.
3. **MUUY IMPORTANTE**: En la URL que copiaste, reemplaza el literal `[YOUR-PASSWORD]` con la contraseña segura del Paso 1 sin corchetes. En las URL debes hacer url-encode de caracteres especiales si tu password los tiene (por ej. si tu password es `P@ssword!`, el `@` es `%40`, aunque Supabase recomienda usar passwords alfanuméricos puros para evitar parseos URI fallidos).
   
EJEMPLO `.env`:
```env
SUPABASE_DB_URL=postgresql://postgres.xxx:MiPasswordSeguro123@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
```

### Paso 4: Levantar el proyecto
El código (en `src/agent/graph.py`) ya asume Supabase y usa la librería `psycopg` y `langgraph-checkpoint-postgres`.
1. Para aplicar los cambios en las librerías `requirements.txt`:
   ```bash
   docker-compose build
   ```
2. Levanta el contenedor:
   ```bash
   docker-compose up -d
   ```
3. Mira los logs del contenedor para verificar que conectó bien:
   ```bash
   docker logs fileops-orchestrator -f
   ```

### 4. ¿Qué ocurre "bajo el capó"?
Cuando el código haga `memory.setup()` (línea 56 en `graph.py`), LangGraph creará automáticamente **tres tablas** en tu base de datos de Supabase:
- `checkpoints`: Guarda el UUID del grafo y la iteración.
- `checkpoint_blobs`: Guarda todo el JSON del estado (el contexto y mensajes).
- `checkpoint_writes`: Mantiene writes asíncronos intermedios.
Puedes ir al "Table Editor" dentro del dashboard web de Supabase y ver cómo estas tablas se llenan mientras usas el bot en Telegram!
