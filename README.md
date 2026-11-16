# NexusAI — AI-Powered Email Intelligence, Organizational Graph & Productivity System

**Live Demo (Google Cloud Run):** [https://email-intelligence-system-249816165253.us-central1.run.app](https://email-intelligence-system-249816165253.us-central1.run.app)

An end-to-end full-stack AI system that extracts structured intelligence from unstructured corporate emails, constructs an **Organizational, Relational, and Temporal Knowledge Graph**, automates deliverable scheduling & conflict detection, and provides an autonomous **Multi-Tool AI Agent**.

---

## Key Capabilities & Architecture

1. **AI-Powered Email Extraction & Safety Guardrails (`backend/extractor.py`)**
   - **Structured LLM Extraction**: Powered by Google Gemini (`gemini-3.8-flash` with automatic model failover and Pydantic v2 schema validation) paired with a zero-latency deterministic **Local Hybrid NLP Engine** for offline execution.
   - **Prompt-Injection Isolation**: Wraps untrusted raw email bodies inside `<UNTRUSTED_EMAIL_CONTENT>` boundaries so embedded instructions inside emails are treated strictly as data, never system commands.
   - **Deterministic Verbatim Quote Grounding (`verify_evidence_quote`)**: Verifies every extracted task's supporting quote against the raw email text to prevent hallucinated deliverables, surfacing a **`✓ Grounded Quote`** callout in the UI.
   - **Zero-Friction Ingestion**: Supports **1-Click Quick-Paste** (`POST /api/emails/quick-paste` for headered or headerless messages) as well as RFC 5322 `.eml` file uploads.

2. **Multi-Faceted Information Extraction (`backend/models.py`)**
   - **Topics**: Multi-domain taxonomy classification (`AI_ML`, `Security`, `Cloud FinOps`, `Compliance`, etc.) with confidence scores and matched keywords.
   - **Entities**: Disambiguated **People** (name, email, role, department), **Organizations** (internal teams, clients, vendors), and **Locations** (offices & cloud regions).
   - **Tasks & Timelines**: Actionable deliverables with `owner`, `deliverable`, `start_date`, `due_date`, `priority`, `status`, `estimated_hours`, and verified `evidence_quote`.
   - **Executive Summaries**: Thesis synthesis, key takeaways, explicit decisions made, sentiment, and urgency score (`1–10`).

3. **Organizational, Relational & Temporal Graph Engine (`backend/graph_engine.py`)**
   - Built on **NetworkX** modeling typed edges (`COMMUNICATES_WITH`, `ASSIGNED_TASK_TO`, `BELONGS_TO`, `PARTNERS_WITH`, `DISCUSSES_TOPIC`, `OPERATES_IN`, `OWNS_DELIVERABLE`).
   - Computes **PageRank** (organizational influence), **Betweenness Centrality** (cross-team bridges/bottlenecks), and **Greedy Modularity Communities** (working clusters).
   - Interactive Retina HiDPI HTML5 Canvas force-directed layout with a **Temporal Evolution Slider** to inspect network snapshots across dates.

4. **Automated Productivity & Schedule Hub (`backend/productivity.py`)**
   - Converts extracted tasks into a **Structured Deliverable Table**, **Interactive Kanban Board**, and **Gantt Timeline & Workload Chart**.
   - Automatically detects **Schedule Conflicts** (overlapping high/critical priority windows per owner).
   - **One-Click Exports**: Download schedules as **iCalendar (`.ics`)**, **CSV**, or **Markdown**.

5. **Autonomous Multi-Tool ReAct Agent (`backend/agent.py`)**
   - Native function-calling agent with visible tool execution traces:
     - `extract_email_intelligence`
     - `query_organizational_graph`
     - `list_and_filter_tasks`
     - `create_or_update_task`
     - `export_schedule_to_tool`

---

## Quick Start

### 1. Configure Environment (Optional)
```bash
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your_key_here
# (If omitted, the system runs automatically in Local Hybrid NLP Mode)
```

### 2. Start the Full-Stack Server
```bash
python3 run.py
```
*(If port `8000` is in use, `run.py` automatically selects the next available port, or pass a custom port via `python3 run.py 8080`.)*

### 3. Run Automated Tests
```bash
python3 -s -m pytest tests/test_system.py -v
```

---

## Deployment

Containerized via `Dockerfile` and `docker-compose.yml`. See [DEPLOYMENT.md](DEPLOYMENT.md) for deployment guides covering **Google Cloud Run**, Docker Compose, Render/Railway/Fly.io, and Linux VPS setups.
