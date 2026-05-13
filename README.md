<div align="center">

<!-- HEADER -->
<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,50:1a1b27,100:0f2027&height=200&section=header&text=LifeOps%20Orchestrator&fontSize=44&fontColor=58A6FF&animation=fadeIn&fontAlignY=40&desc=Deterministic%20Multi-Agent%20AI%20System%20for%20Digital%20Life%20Management&descAlignY=62&descSize=16&descColor=8b949e" width="100%" />

<!-- BADGES -->
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-State%20Machine-FF6B6B?style=for-the-badge&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com)
[![Telegram](https://img.shields.io/badge/Telegram-Bot%20UI-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![Tests](https://img.shields.io/badge/Tests-37%20passing-3fb950?style=for-the-badge&logo=pytest&logoColor=white)](#testing)
[![LangSmith](https://img.shields.io/badge/LangSmith-Observability-F97316?style=for-the-badge&logoColor=white)](https://smith.langchain.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

<br/>

> **A production-grade, security-first multi-agent system** that orchestrates your digital life —
> Calendar, Gmail, Obsidian, and News — through a single Telegram interface, built on a
> deterministic LangGraph state machine with native Human-in-the-Loop and full observability.

</div>

---

## 🎯 Why LifeOps?

Most AI assistants are **conversational wrappers** — they hallucinate, lose state, and can't be trusted with real actions. LifeOps is architected differently:

| Problem with typical AI agents | LifeOps solution |
|--------------------------------|-----------------|
| Non-deterministic outputs | Deterministic 5-node state machine |
| No security boundary | Dedicated Guardrail node (prompt injection detection) |
| Stateless between messages | Supabase PostgreSQL checkpointing |
| Blind tool execution | Human-in-the-Loop gate before destructive actions |
| No quality control | QA Reviewer node with up to 5 retry iterations |
| Expensive LLM calls | Unified extraction pattern — **60% token reduction** |

---

## 🏗️ Architecture

The system is a **5-node deterministic state machine** built on LangGraph. Every message flows through the pipeline in a fixed, auditable sequence:

```mermaid
flowchart LR
    A["🛡️ Guardrail\nSecurity Filter"] -->|safe| B["🧭 Orchestrator\nRouting + HiTL"]
    A -->|blocked| X(["❌ Rejected"])
    B -->|needs approval| H["👤 Human-in-the-Loop\nasync Postgres pause"]
    H -->|approved| C
    B -->|direct| C["🧠 Domain Expert\nIntent Classification"]
    C --> D["⚙️ Tech Architect\nTool Execution & Dispatch"]
    D --> E["✅ Reviewer\nQA Gate · Retry ≤ 5"]
    E -->|approved| T(["📱 Telegram User"])
    E -->|retry| D

    style A fill:#1f2937,stroke:#58A6FF,color:#fff
    style B fill:#1f2937,stroke:#58A6FF,color:#fff
    style C fill:#1f2937,stroke:#58A6FF,color:#fff
    style D fill:#1f2937,stroke:#58A6FF,color:#fff
    style E fill:#1f2937,stroke:#3fb950,color:#fff
    style H fill:#2d1f00,stroke:#F97316,color:#fff
    style X fill:#3b1212,stroke:#f85149,color:#fff
    style T fill:#0d2818,stroke:#3fb950,color:#fff
```

### Node Responsibilities

| Node | Role | Key Capability |
|------|------|----------------|
| **🛡️ Guardrail** | Security boundary | Detects prompt injection, out-of-domain requests |
| **🧭 Orchestrator** | Traffic control | Routes intent, coordinates Human-in-the-Loop pauses |
| **🧠 Domain Expert** | Intent engine | Classifies across **12 intent types**, extracts parameters |
| **⚙️ Technical Architect** | Execution layer | Dispatches to Google Calendar, Gmail, Obsidian, News APIs |
| **✅ Reviewer** | Quality gate | Validates output, retries up to 5x before surfacing failure |

### State Persistence

State is checkpointed in **Supabase PostgreSQL**, enabling true asynchronous HiTL — the agent pauses mid-graph, waits for Telegram approval, and resumes exactly where it left off. No polling, no timeouts.

---

## ✨ Features

<table>
<tr>
<td>

**📅 Calendar Management**
- Create, update, delete events
- Query upcoming agenda
- Smart conflict detection
- Sync with Obsidian notes

</td>
<td>

**📧 Gmail Integration**
- Compose and send emails
- Retrieve and summarize inbox
- Context-aware drafting
- Attachment awareness

</td>
</tr>
<tr>
<td>

**📓 Obsidian Vault**
- Create and update notes
- Link calendar entries to notes
- Search across vault
- Automated daily notes

</td>
<td>

**📰 News & RSS**
- Aggregate from multiple feeds
- LLM-powered summarization
- Digest delivery on demand
- Custom topic filtering

</td>
</tr>
</table>

---

## 🛠️ Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Orchestration** | LangGraph | Native HiTL, checkpointing, deterministic graph |
| **LLM** | Azure OpenAI GPT-4o-mini | Cost-efficient, enterprise-grade |
| **State / Persistence** | Supabase PostgreSQL | Async HiTL, durable checkpoints |
| **Interface** | python-telegram-bot | Async, battle-tested, easy UX |
| **Observability** | LangSmith + structlog | Trace every LLM call, structured logs |
| **Containerization** | Docker Compose | One-command deployment |
| **Testing** | pytest | 37 unit tests across all nodes |
| **Schemas** | Pydantic v2 | Strict runtime validation |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Azure OpenAI API key
- Telegram Bot token ([create via @BotFather](https://t.me/botfather))
- Supabase project (free tier works)
- Google Cloud project with Calendar + Gmail APIs enabled

### 1. Clone & configure

```bash
git clone https://github.com/manuelcozar55/LifeOps-Orchestrator.git
cd LifeOps-Orchestrator
cp .env.example .env
```

Edit `.env` with your credentials:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini

TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_ALLOWED_USERS=your-telegram-id

SUPABASE_DB_URL=postgresql://user:pass@host:5432/postgres

LANGSMITH_API_KEY=your-langsmith-key   # optional, for observability
```

### 2. Set up Google OAuth

```bash
python scripts/setup_oauth.py   # opens browser for Calendar + Gmail consent
```

### 3. Run with Docker

```bash
docker-compose up -d
```

Or locally:

```bash
pip install -r requirements.txt
python -m src.main
```

---

## 💬 Usage Examples

Once running, interact via Telegram:

```
You: "Schedule a team standup tomorrow at 10am for 30 minutes"
Bot: ✅ Created: Team Standup — Wed 14 May · 10:00–10:30

You: "What's on my agenda this week?"
Bot: 📅 Week of 13–19 May:
     · Mon 13  →  Product review (14:00)
     · Wed 15  →  Team standup (10:00)
     · Fri 17  →  1:1 with mentor (16:00)

You: "Summarize today's AI news"
Bot: 📰 Top AI headlines for 13 May:
     · OpenAI releases o3-mini...
     · Google DeepMind announces...

You: "Delete the Friday 1:1"
Bot: ⚠️ This will permanently delete "1:1 with mentor" on Fri 17 May.
     Confirm? [Yes / No]           ← Human-in-the-Loop gate
```

### Supported Intents

| Category | Intents |
|----------|---------|
| **Calendar** | `calendar_create` · `calendar_update` · `calendar_delete` · `calendar_query` |
| **Agenda** | `agenda_query` · `agenda_sync_preview` |
| **Email** | `email_send` · `email_query` |
| **Obsidian** | `obsidian_create` · `obsidian_query` |
| **News** | `news_query` |
| **Fallback** | `unknown` → general LLM reasoning |

---

## 📁 Project Structure

```
LifeOps-Orchestrator/
├── src/
│   ├── agent/
│   │   ├── graph.py          # LangGraph state machine definition
│   │   ├── nodes/            # guardrail, orchestrator, domain_expert,
│   │   │                     # tech_architect, reviewer
│   │   ├── state.py          # Shared AgentState schema
│   │   └── handlers/         # Telegram message handlers
│   ├── models/               # Pydantic schemas for all intents
│   └── tools/                # Google Calendar, Gmail, Obsidian, News
├── tests/                    # 37 unit tests (pytest)
├── docs/
│   ├── LifeOpsDiagram.png    # Architecture diagram
│   └── DEFENSA_TECNICA.md    # ADR & technical decisions
├── scripts/
│   └── setup_oauth.py        # Google OAuth setup
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## 🧪 Testing

```bash
pytest tests/ -v
```

```
tests/test_guardrail.py          ✅  8 passed
tests/test_orchestrator.py       ✅  7 passed
tests/test_domain_expert.py      ✅  9 passed
tests/test_tech_architect.py     ✅  8 passed
tests/test_reviewer.py           ✅  5 passed
─────────────────────────────────
37 passed in 2.14s
```

---

## 🔑 Key Design Decisions

**Why LangGraph over CrewAI/AutoGen?**
LangGraph provides native Postgres checkpointing for asynchronous Human-in-the-Loop — the agent pauses mid-graph while waiting for Telegram approval, then resumes exactly where it left off. No other framework offers this out of the box.

**Why a Unified LLM Extraction Pattern?**
A single LLM call classifies intent AND extracts all parameters simultaneously, reducing API round-trips by ~60% compared to chained domain-specific calls.

**Why Determinism over Autonomy?**
Agents that write emails and delete calendar events must be predictable and auditable. The 5-node pipeline guarantees every action passes through security filtering, human approval (when needed), and quality review.

---

## 📊 Observability

Every LLM call is traced in **LangSmith** with full token counts and latency. Structured logs via `structlog` include node names, intent types, and token telemetry — making it straightforward to track costs and debug failures in production.

---

## 🗺️ Roadmap

- [ ] Voice message support (Whisper transcription → same pipeline)
- [ ] Notion integration
- [ ] Weekly digest automation (cron-based)
- [ ] Multi-user support with per-user Supabase namespacing
- [ ] Web dashboard for conversation history

---

## 👤 Author

**Manuel Antonio Cózar Baranguán**
*AI Engineer & Innovation Researcher*

[![LinkedIn](https://img.shields.io/badge/LinkedIn-@manuelcozarb-0A66C2?style=flat-square&logo=linkedin&logoColor=white)](https://linkedin.com/in/manuelcozarb)
[![GitHub](https://img.shields.io/badge/GitHub-@manuelcozar55-181717?style=flat-square&logo=github&logoColor=white)](https://github.com/manuelcozar55)
[![Email](https://img.shields.io/badge/Email-manuelcozarb@gmail.com-EA4335?style=flat-square&logo=gmail&logoColor=white)](mailto:manuelcozarb@gmail.com)

---

<div align="center">

*Built with curiosity, structured with intention.*

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f2027,60:1a1b27,100:0d1117&height=100&section=footer" width="100%" />

</div>
