from __future__ import annotations
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class PersonEntity(BaseModel):
    name: str = Field(..., description="Full name of the person")
    email: Optional[str] = Field(None, description="Email address if known")
    role: Optional[str] = Field(None, description="Job title or inferred role")
    organization: Optional[str] = Field(None, description="Company or department")


class OrganizationEntity(BaseModel):
    name: str = Field(..., description="Organization, company, or department name")
    category: str = Field(
        default="Department/Team",
        description="Type: Internal Team, Client, Vendor, Partner, or External Org",
    )


class LocationEntity(BaseModel):
    name: str = Field(..., description="City, office, region, or virtual location")
    context: Optional[str] = Field(None, description="Context in which location is mentioned")


class ExtractedEntities(BaseModel):
    people: List[PersonEntity] = Field(default_factory=list)
    organizations: List[OrganizationEntity] = Field(default_factory=list)
    locations: List[LocationEntity] = Field(default_factory=list)


class TopicItem(BaseModel):
    name: str = Field(..., description="Concise topic label")
    category: str = Field(
        default="Operations",
        description="High-level category e.g. Engineering, Product, Legal, Security, Finance, Sales",
    )
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    keywords: List[str] = Field(default_factory=list)


class ExtractedTask(BaseModel):
    id: str = Field(..., description="Unique task identifier")
    title: str = Field(..., description="Short action-oriented task title")
    deliverable: str = Field(..., description="Concrete deliverable or expected outcome")
    owner: str = Field(..., description="Assigned owner name")
    owner_email: Optional[str] = Field(None, description="Assigned owner email")
    assigner: Optional[str] = Field(None, description="Person who requested or assigned the task")
    start_date: str = Field(..., description="ISO date YYYY-MM-DD when work begins or was assigned")
    due_date: str = Field(..., description="ISO date YYYY-MM-DD when deliverable is due")
    priority: Literal["Critical", "High", "Medium", "Low"] = Field(default="Medium")
    status: Literal["Todo", "In Progress", "Blocked", "Completed"] = Field(default="Todo")
    estimated_hours: float = Field(default=4.0, description="Estimated effort in hours")
    dependencies: List[str] = Field(default_factory=list, description="Dependent task titles or IDs")
    source_email_id: str = Field(..., description="ID of the email from which this task was extracted")
    thread_id: Optional[str] = Field(None, description="Email thread ID")
    notes: Optional[str] = Field(None, description="Additional context or timeline constraint")
    evidence_quote: Optional[str] = Field(
        None,
        description="Verbatim sentence or span from the source email justifying this task",
    )
    quote_verified: bool = Field(
        default=False,
        description="True when deterministic guardrail verified evidence_quote exists verbatim in email body",
    )


class TimelineEvent(BaseModel):
    date: str = Field(..., description="ISO date YYYY-MM-DD")
    label: str = Field(..., description="Milestone or event description")
    event_type: Literal["Deadline", "Milestone", "Meeting", "Launch", "Review"] = Field(
        default="Milestone"
    )
    related_entities: List[str] = Field(default_factory=list)
    source_email_id: str = Field(...)


class EmailSummary(BaseModel):
    executive_summary: str = Field(..., description="1-2 sentence executive summary of the email")
    key_points: List[str] = Field(default_factory=list, description="Bullet points of key information")
    decisions_made: List[str] = Field(default_factory=list, description="Explicit decisions or approvals")
    sentiment: Literal["Positive", "Neutral", "Urgent", "Concerned"] = Field(default="Neutral")
    urgency_score: int = Field(default=5, ge=1, le=10, description="1-10 urgency rating")


class EmailExtractionResult(BaseModel):
    email_id: str
    extraction_engine: str = Field(default="hybrid", description="gemini-3.8-flash or nlp-hybrid")
    summary: EmailSummary
    topics: List[TopicItem]
    entities: ExtractedEntities
    tasks: List[ExtractedTask]
    timeline_events: List[TimelineEvent]


class EmailMessage(BaseModel):
    id: str
    thread_id: str
    subject: str
    sender_name: str
    sender_email: str
    sender_role: Optional[str] = None
    sender_dept: Optional[str] = None
    recipients: List[Dict[str, str]] = Field(
        default_factory=list, description="List of {'name': ..., 'email': ..., 'type': 'to'|'cc'}"
    )
    timestamp: str = Field(..., description="ISO 8601 timestamp e.g. 2026-10-20T09:15:00Z")
    body: str
    extraction: Optional[EmailExtractionResult] = None


class IngestEmailRequest(BaseModel):
    subject: str
    sender_name: str
    sender_email: str
    recipients: List[str] = Field(default_factory=list, description="List of recipient emails or 'Name <email>'")
    timestamp: Optional[str] = None
    body: str
    thread_id: Optional[str] = None
    use_gemini: bool = True


class QuickPasteEmailRequest(BaseModel):
    raw_text: str = Field(..., description="Raw pasted email text (with or without From/To/Subject/Date headers)")
    use_gemini: bool = True


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    deliverable: Optional[str] = None
    owner: Optional[str] = None
    owner_email: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[Literal["Critical", "High", "Medium", "Low"]] = None
    status: Optional[Literal["Todo", "In Progress", "Blocked", "Completed"]] = None
    estimated_hours: Optional[float] = None


class TaskCreateRequest(BaseModel):
    title: str
    deliverable: str
    owner: str
    owner_email: Optional[str] = None
    start_date: str
    due_date: str
    priority: Literal["Critical", "High", "Medium", "Low"] = "Medium"
    status: Literal["Todo", "In Progress", "Blocked", "Completed"] = "Todo"
    estimated_hours: float = 4.0


class AgentChatRequest(BaseModel):
    message: str
    history: List[Dict[str, str]] = Field(default_factory=list)
    api_key: Optional[str] = None


class AgentToolExecution(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    result_summary: str
    data: Optional[Any] = None


class AgentChatResponse(BaseModel):
    reply: str
    engine: str
    tool_calls: List[AgentToolExecution] = Field(default_factory=list)
    suggested_followups: List[str] = Field(default_factory=list)

