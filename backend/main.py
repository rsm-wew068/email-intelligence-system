from __future__ import annotations
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any
from email.utils import parseaddr

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.models import (
    EmailMessage,
    ExtractedTask,
    IngestEmailRequest,
    QuickPasteEmailRequest,
    SendApprovedEmailRequest,
    TaskUpdateRequest,
    TaskCreateRequest,
    AgentChatRequest,
    AgentChatResponse,
)
from backend.sample_data import get_initial_emails, parse_eml_content
from backend.extractor import EmailIntelligenceExtractor, parse_quick_paste_email
from backend.graph_engine import OrganizationalGraphEngine
from backend.productivity import ProductivityScheduleManager
from backend.agent import EmailIntelligenceAgent

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(
    title="NexusAI — Email Intelligence & Productivity Graph System",
    description="AI-powered email extraction (Topics, Entities, Tasks, Timelines, Summaries), Organizational/Relational/Temporal Graph Engine, and Automated Task Scheduler.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SystemState:
    def __init__(self):
        self.extractor = EmailIntelligenceExtractor()
        self.graph_engine = OrganizationalGraphEngine()
        self.productivity_manager = ProductivityScheduleManager()
        self.agent = EmailIntelligenceAgent(
            self.extractor, self.graph_engine, self.productivity_manager
        )
        self.emails: List[EmailMessage] = []
        self.tasks: List[ExtractedTask] = []
        self.initialize_dataset()

    def initialize_dataset(self):
        self.emails = get_initial_emails()
        self.tasks = []
        for em in self.emails:
            ext = self.extractor.extract(em, prefer_gemini=False)
            em.extraction = ext
            for t in ext.tasks:
                self.tasks.append(t)


state = SystemState()


@app.get("/api/overview")
def get_overview() -> Dict[str, Any]:
    graph_snapshot = state.graph_engine.build_graph(state.emails, state.tasks)
    sched_summary = state.productivity_manager.build_schedule_summary(state.tasks)

    topic_counts: Dict[str, Dict[str, Any]] = {}
    all_people = set()
    all_orgs = set()
    all_locations = set()

    for em in state.emails:
        if em.extraction:
            for top in em.extraction.topics:
                if top.name not in topic_counts:
                    topic_counts[top.name] = {
                        "name": top.name,
                        "category": top.category,
                        "count": 0,
                        "keywords": top.keywords,
                    }
                topic_counts[top.name]["count"] += 1
            for p in em.extraction.entities.people:
                all_people.add(p.name)
            for o in em.extraction.entities.organizations:
                all_orgs.add(o.name)
            for loc in em.extraction.entities.locations:
                all_locations.add(loc.name)

    topics_list = sorted(topic_counts.values(), key=lambda x: x["count"], reverse=True)

    return {
        "status": "ok",
        "gemini_configured": state.extractor.has_api_key(),
        "model_name": state.extractor.model_name if state.extractor.has_api_key() else "NLP Hybrid + Gemini Ready",
        "metrics": {
            "total_emails": len(state.emails),
            "total_threads": len({em.thread_id for em in state.emails}),
            "total_topics": len(topics_list),
            "total_people": len(all_people),
            "total_organizations": len(all_orgs),
            "total_locations": len(all_locations),
            "total_tasks": len(state.tasks),
            "critical_tasks": sched_summary["by_priority"].get("Critical", 0),
            "schedule_conflicts": len(sched_summary["schedule_conflicts"]),
            "graph_nodes": graph_snapshot["analytics"]["total_nodes"],
            "graph_edges": graph_snapshot["analytics"]["total_edges"],
        },
        "topics_distribution": topics_list,
        "schedule_summary": sched_summary,
        "graph_highlights": {
            "top_influencers": graph_snapshot["analytics"]["top_influencers"],
            "top_bridges": graph_snapshot["analytics"]["top_bridges"],
            "communities": graph_snapshot["analytics"]["communities"],
            "temporal": graph_snapshot["temporal"],
        },
    }


@app.get("/api/emails")
def list_emails() -> Dict[str, Any]:
    sorted_emails = sorted(state.emails, key=lambda x: x.timestamp, reverse=True)
    return {
        "count": len(sorted_emails),
        "emails": [em.model_dump() for em in sorted_emails],
    }


@app.get("/api/emails/{email_id}")
def get_email_detail(email_id: str) -> Dict[str, Any]:
    for em in state.emails:
        if em.id == email_id:
            return em.model_dump()
    raise HTTPException(status_code=404, detail=f"Email '{email_id}' not found")


@app.post("/api/emails/ingest")
def ingest_email(req: IngestEmailRequest) -> Dict[str, Any]:
    parsed_recipients = []
    for raw_r in req.recipients:
        for part in raw_r.split(","):
            part = part.strip()
            if not part:
                continue
            r_name, r_email = parseaddr(part)
            if not r_email and "@" in part:
                r_email = part
            if not r_name:
                r_name = (r_email.split("@")[0] if r_email else part).replace(".", " ").title()
            parsed_recipients.append(
                {
                    "name": r_name,
                    "email": r_email or f"{r_name.lower().replace(' ', '.')}@nexusai.io",
                    "type": "to",
                }
            )
    if not parsed_recipients:
        parsed_recipients.append({"name": "Sarah Chen", "email": "sarah.chen@nexusai.io", "type": "to"})

    new_id = f"eml-{len(state.emails) + 1:03d}"
    ts = req.timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    email_msg = EmailMessage(
        id=new_id,
        thread_id=req.thread_id or f"thr-{uuid.uuid4().hex[:6]}",
        subject=req.subject.strip(),
        sender_name=req.sender_name.strip(),
        sender_email=req.sender_email.strip().lower(),
        recipients=parsed_recipients,
        timestamp=ts,
        body=req.body.strip(),
    )
    extraction = state.extractor.extract(email_msg, prefer_gemini=req.use_gemini)
    email_msg.extraction = extraction
    state.emails.append(email_msg)
    for t in extraction.tasks:
        state.tasks.append(t)

    return {
        "status": "extracted",
        "email": email_msg.model_dump(),
        "tasks_added": len(extraction.tasks),
    }


@app.post("/api/emails/quick-paste")
def quick_paste_email(req: QuickPasteEmailRequest) -> Dict[str, Any]:
    if not req.raw_text or not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text cannot be empty")
    parsed = parse_quick_paste_email(req.raw_text)
    ingest_req = IngestEmailRequest(
        subject=parsed["subject"],
        sender_name=parsed["sender_name"],
        sender_email=parsed["sender_email"],
        recipients=parsed["recipients"],
        timestamp=parsed["timestamp"],
        body=parsed["body"],
        use_gemini=req.use_gemini,
    )
    return ingest_email(ingest_req)


@app.post("/api/emails/send")
def send_approved_email(req: SendApprovedEmailRequest) -> Dict[str, Any]:
    """
    Human-in-the-Loop approved email dispatch endpoint:
    1. Sends via live TLS SMTP if SMTP_HOST / SMTP_USER / SMTP_PASSWORD are set in .env.
    2. Records the sent message into the Corporate Thread Stream & Organizational Graph.
    3. Returns a pre-addressed Gmail Compose URL for optional external browser send.
    """
    from urllib.parse import quote

    delivery_mode = "workspace_dispatched"
    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASSWORD", "").strip()

    if smtp_host and smtp_user and smtp_pass:
        import smtplib
        from email.message import EmailMessage as PyEmailMessage

        msg = PyEmailMessage()
        msg["Subject"] = req.subject.strip()
        msg["From"] = smtp_user
        msg["To"] = req.to_email.strip()
        if req.cc:
            msg["Cc"] = ", ".join(req.cc)
        msg.set_content(req.body.strip())

        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        delivery_mode = "smtp_live"

    new_id = f"eml-{len(state.emails) + 1:03d}"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sent_email = EmailMessage(
        id=new_id,
        thread_id=f"thr-{uuid.uuid4().hex[:6]}",
        subject=req.subject.strip(),
        sender_name="Sarah Chen",
        sender_email="sarah.chen@nexusai.io",
        recipients=[
            {
                "name": req.to_name.strip() or req.to_email.split("@")[0],
                "email": req.to_email.strip().lower(),
                "type": "to",
            }
        ],
        timestamp=now_iso,
        body=req.body.strip(),
    )
    extraction = state.extractor.extract(sent_email, prefer_gemini=False)
    sent_email.extraction = extraction
    state.emails.append(sent_email)

    gmail_url = (
        f"https://mail.google.com/mail/?view=cm&fs=1"
        f"&to={quote(req.to_email.strip())}"
        f"&su={quote(req.subject.strip())}"
        f"&body={quote(req.body.strip())}"
    )

    return {
        "status": "sent",
        "delivery_mode": delivery_mode,
        "email_id": sent_email.id,
        "gmail_compose_url": gmail_url,
        "timestamp": now_iso,
    }


@app.post("/api/emails/upload-eml")
async def upload_eml_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    raw_bytes = await file.read()
    parsed = parse_eml_content(raw_bytes)
    parsed["id"] = f"eml-{len(state.emails) + 1:03d}"
    email_msg = EmailMessage(**parsed)
    extraction = state.extractor.extract(email_msg, prefer_gemini=state.extractor.has_api_key())
    email_msg.extraction = extraction
    state.emails.append(email_msg)
    for t in extraction.tasks:
        state.tasks.append(t)
    return {
        "status": "uploaded_and_extracted",
        "email": email_msg.model_dump(),
        "tasks_added": len(extraction.tasks),
    }


@app.post("/api/emails/{email_id}/re-extract")
def re_extract_email(email_id: str, use_gemini: bool = True) -> Dict[str, Any]:
    for em in state.emails:
        if em.id == email_id:
            extraction = state.extractor.extract(em, prefer_gemini=use_gemini)
            em.extraction = extraction
            state.tasks = [t for t in state.tasks if t.source_email_id != email_id]
            for t in extraction.tasks:
                state.tasks.append(t)
            return {"status": "re-extracted", "email": em.model_dump()}
    raise HTTPException(status_code=404, detail=f"Email '{email_id}' not found")


@app.get("/api/graph")
def get_graph_data(
    cutoff_date: Optional[str] = Query(None, description="Optional YYYY-MM-DD temporal filter"),
    include_tasks: bool = Query(True, description="Include deliverable task nodes in graph"),
) -> Dict[str, Any]:
    return state.graph_engine.build_graph(
        state.emails,
        state.tasks,
        cutoff_date=cutoff_date,
        include_task_nodes=include_tasks,
    )


@app.get("/api/tasks")
def list_tasks(
    owner: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    filtered = state.tasks
    if owner:
        filtered = [t for t in filtered if owner.lower() in t.owner.lower()]
    if priority:
        filtered = [t for t in filtered if t.priority.lower() == priority.lower()]
    if status:
        filtered = [t for t in filtered if t.status.lower() == status.lower()]

    schedule_summary = state.productivity_manager.build_schedule_summary(state.tasks)
    return {
        "count": len(filtered),
        "tasks": [t.model_dump() for t in sorted(filtered, key=lambda x: x.due_date)],
        "schedule_summary": schedule_summary,
    }


@app.post("/api/tasks")
def create_task(req: TaskCreateRequest) -> Dict[str, Any]:
    new_task = ExtractedTask(
        id=f"tsk-manual-{len(state.tasks) + 1:02d}",
        title=req.title,
        deliverable=req.deliverable,
        owner=req.owner,
        owner_email=req.owner_email,
        assigner="Manual Schedule Entry",
        start_date=req.start_date,
        due_date=req.due_date,
        priority=req.priority,
        status=req.status,
        estimated_hours=req.estimated_hours,
        dependencies=[],
        source_email_id="manual",
    )
    state.tasks.append(new_task)
    return {"status": "created", "task": new_task.model_dump()}


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: str, req: TaskUpdateRequest) -> Dict[str, Any]:
    for t in state.tasks:
        if t.id == task_id:
            update_data = req.model_dump(exclude_unset=True)
            for k, v in update_data.items():
                if v is not None:
                    setattr(t, k, v)
            return {"status": "updated", "task": t.model_dump()}
    raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str) -> Dict[str, Any]:
    before = len(state.tasks)
    state.tasks = [t for t in state.tasks if t.id != task_id]
    if len(state.tasks) == before:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return {"status": "deleted", "task_id": task_id}


@app.get("/api/schedule/export/{fmt}")
def export_schedule(fmt: str, owner: Optional[str] = None):
    fmt_clean = fmt.lower().strip()
    if fmt_clean in ("ics", "ical"):
        content = state.productivity_manager.export_icalendar(state.tasks, owner_filter=owner)
        return Response(
            content=content,
            media_type="text/calendar",
            headers={"Content-Disposition": "attachment; filename=email-intelligence-schedule.ics"},
        )
    elif fmt_clean == "csv":
        content = state.productivity_manager.export_csv(state.tasks, owner_filter=owner)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=email-intelligence-tasks.csv"},
        )
    elif fmt_clean in ("md", "markdown"):
        content = state.productivity_manager.export_markdown_schedule(state.tasks, owner_filter=owner)
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": "attachment; filename=email-intelligence-schedule.md"},
        )
    elif fmt_clean == "json":
        return JSONResponse(
            content={
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "tasks": [t.model_dump() for t in state.tasks],
            }
        )
    raise HTTPException(status_code=400, detail=f"Unsupported export format: {fmt}")


@app.post("/api/agent/chat", response_model=AgentChatResponse)
def agent_chat(req: AgentChatRequest) -> AgentChatResponse:
    return state.agent.run_chat(
        message=req.message,
        emails=state.emails,
        tasks=state.tasks,
        api_key=req.api_key,
    )


@app.middleware("http")
async def disable_static_cache(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.post("/api/config/api-key")
def set_gemini_api_key(payload: Dict[str, str]) -> Dict[str, Any]:
    api_key = payload.get("api_key", "").strip()
    state.extractor.set_api_key(api_key)
    if api_key:
        try:
            env_path = BASE_DIR / ".env"
            env_path.write_text(f"GEMINI_API_KEY={api_key}\n", encoding="utf-8")
        except Exception:
            pass
    return {
        "status": "updated",
        "gemini_configured": state.extractor.has_api_key(),
        "model": state.extractor.model_name,
    }


@app.post("/api/system/reset")
def reset_dataset() -> Dict[str, Any]:
    state.initialize_dataset()
    return {"status": "reset", "emails": len(state.emails), "tasks": len(state.tasks)}


@app.get("/favicon.ico", include_in_schema=False)
def get_favicon():
    svg_favicon = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="2.2"><circle cx="12" cy="5" r="3"/><circle cx="5" cy="19" r="3"/><circle cx="19" cy="19" r="3"/><line x1="10.5" y1="7.5" x2="6.5" y2="16.5"/><line x1="13.5" y1="7.5" x2="17.5" y2="16.5"/><line x1="8" y1="19" x2="16" y2="19"/></svg>"""
    return Response(content=svg_favicon, media_type="image/svg+xml")


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def serve_frontend():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "NexusAI Email Intelligence API is running. Visit /docs for OpenAPI documentation."}

