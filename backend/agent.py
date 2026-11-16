from __future__ import annotations
import re
import uuid
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import List, Dict, Any, Optional

from backend.models import (
    EmailMessage,
    ExtractedTask,
    AgentChatResponse,
    AgentToolExecution,
)
from backend.extractor import EmailIntelligenceExtractor
from backend.graph_engine import OrganizationalGraphEngine
from backend.productivity import ProductivityScheduleManager


AGENT_SYSTEM_INSTRUCTION = """You are the NexusAI Autonomous Email Intelligence & Productivity Agent.
You have direct access to live tools that interact with the company's email extraction engine, organizational/relational/temporal graph database (NetworkX), and productivity task scheduler.

Always use your tools to inspect real state or perform actions before answering:
1. Use `extract_email_intelligence` whenever the user provides raw email text or asks to extract/ingest an email.
2. Use `query_organizational_graph` to inspect organizational influencers (PageRank), cross-team bridges/bottlenecks (Betweenness Centrality), working clusters/communities, temporal evolution, or specific people/organizations.
3. Use `list_and_filter_tasks` to inspect the structured to-do list, deliverable schedule, owner workloads, and schedule conflicts/overlaps.
4. Use `create_or_update_task` when asked to schedule a new task, reassign an owner, change dates/priority, or update a task status (Todo, In Progress, Blocked, Completed).
5. Use `export_schedule_to_tool` when asked to export schedules to iCalendar (.ics), CSV, or Markdown.

Format your final answers clearly using GitHub-flavored Markdown tables and concise bullet points grounded strictly in the tool outputs.
"""


class EmailIntelligenceAgent:
    """
    Autonomous LLM Agent powered by Google Gemini native Function Calling (ReAct loop).
    Reasons over user requests, autonomously selects and invokes multiple backend tools,
    mutates live email/graph/task state, and synthesizes insights.
    """

    def __init__(
        self,
        extractor: EmailIntelligenceExtractor,
        graph_engine: OrganizationalGraphEngine,
        productivity_manager: ProductivityScheduleManager,
    ):
        self.extractor = extractor
        self.graph_engine = graph_engine
        self.productivity_manager = productivity_manager

    def run_chat(
        self,
        message: str,
        emails: List[EmailMessage],
        tasks: List[ExtractedTask],
        api_key: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AgentChatResponse:
        if api_key:
            self.extractor.set_api_key(api_key)

        if self.extractor.has_api_key():
            try:
                return self._run_gemini_tool_calling_loop(message, emails, tasks, history or [])
            except Exception as exc:
                print(f"[Agent] Gemini native tool-calling loop error ({exc}), falling back.")

        return self._run_autonomous_multi_tool_engine(message, emails, tasks)

    def _run_gemini_tool_calling_loop(
        self,
        message: str,
        emails: List[EmailMessage],
        tasks: List[ExtractedTask],
        history: List[Dict[str, str]],
    ) -> AgentChatResponse:
        from google import genai
        from google.genai import types

        tool_calls_log: List[AgentToolExecution] = []

        def extract_email_intelligence(
            subject: str,
            sender_name: str,
            sender_email: str,
            body: str,
            recipients: Optional[List[str]] = None,
            timestamp: str = "",
        ) -> Dict[str, Any]:
            """Extract topics, entities (people, organizations, locations), tasks, timelines, and summary from an unstructured email and add it to the workspace."""
            rec_list = []
            for r in recipients or ["Team <team@nexusai.io>"]:
                r_name, r_addr = parseaddr(r)
                rec_list.append(
                    {
                        "name": r_name or r.split("<")[0].strip() or r,
                        "email": r_addr or r,
                        "type": "to",
                    }
                )
            new_email = EmailMessage(
                id=f"eml-{len(emails) + 1:03d}",
                thread_id=f"thr-{uuid.uuid4().hex[:6]}",
                subject=subject,
                sender_name=sender_name,
                sender_email=sender_email,
                recipients=rec_list,
                timestamp=timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                body=body,
            )
            ext_res = self.extractor.extract(new_email, prefer_gemini=True)
            new_email.extraction = ext_res
            emails.append(new_email)
            for t in ext_res.tasks:
                tasks.append(t)

            result_payload = {
                "email_id": new_email.id,
                "summary": ext_res.summary.model_dump(),
                "topics": [t.model_dump() for t in ext_res.topics],
                "entities": ext_res.entities.model_dump(),
                "tasks_extracted": [t.model_dump() for t in ext_res.tasks],
                "timeline_events": [ev.model_dump() for ev in ext_res.timeline_events],
            }
            tool_calls_log.append(
                AgentToolExecution(
                    tool_name="extract_email_intelligence",
                    arguments={"subject": subject, "sender_name": sender_name},
                    result_summary=f"Extracted {len(ext_res.topics)} topics, {len(ext_res.entities.people)} people, and {len(ext_res.tasks)} scheduled tasks.",
                    data=result_payload,
                )
            )
            return result_payload

        def query_organizational_graph(
            entity_name: str = "",
            cutoff_date: str = "",
            include_task_nodes: bool = True,
        ) -> Dict[str, Any]:
            """Query the NetworkX organizational, relational, and temporal graph for centrality rankings (PageRank, Betweenness), communities, department flows, and entity connections."""
            g = self.graph_engine.build_graph(
                emails,
                tasks,
                cutoff_date=cutoff_date or None,
                include_task_nodes=include_task_nodes,
            )
            entity_edges = []
            if entity_name:
                elower = entity_name.lower()
                for e in g["edges"]:
                    if elower in e["source"].lower() or elower in e["target"].lower():
                        entity_edges.append(e)

            result_payload = {
                "analytics": g["analytics"],
                "temporal_summary": {
                    "min_date": g["temporal"]["min_date"],
                    "max_date": g["temporal"]["max_date"],
                    "milestones": g["temporal"]["milestones"][:10],
                },
                "entity_connections": entity_edges[:20],
            }
            tool_calls_log.append(
                AgentToolExecution(
                    tool_name="query_organizational_graph",
                    arguments={"entity_name": entity_name or "ALL", "cutoff_date": cutoff_date or "ALL"},
                    result_summary=(
                        f"Queried NetworkX graph ({g['analytics']['total_nodes']} nodes, "
                        f"{g['analytics']['total_edges']} edges, {len(g['analytics']['communities'])} clusters)."
                    ),
                    data=result_payload,
                )
            )
            return result_payload

        def list_and_filter_tasks(
            owner: str = "",
            priority: str = "",
            status: str = "",
        ) -> Dict[str, Any]:
            """List structured tasks and deliverables from the productivity schedule, filtered by owner, priority (Critical, High, Medium, Low), or status (Todo, In Progress, Blocked, Completed), including workload and conflict analysis."""
            filtered = list(tasks)
            if owner:
                filtered = [t for t in filtered if owner.lower() in t.owner.lower()]
            if priority:
                filtered = [t for t in filtered if t.priority.lower() == priority.lower()]
            if status:
                filtered = [t for t in filtered if t.status.lower() == status.lower()]

            sched = self.productivity_manager.build_schedule_summary(tasks)
            result_payload = {
                "matched_count": len(filtered),
                "tasks": [t.model_dump() for t in sorted(filtered, key=lambda x: x.due_date)],
                "schedule_conflicts": sched["schedule_conflicts"],
                "owner_workloads": sched["owner_workloads"],
            }
            tool_calls_log.append(
                AgentToolExecution(
                    tool_name="list_and_filter_tasks",
                    arguments={"owner": owner or "ALL", "priority": priority or "ALL", "status": status or "ALL"},
                    result_summary=f"Retrieved {len(filtered)} deliverables and analyzed {len(sched['schedule_conflicts'])} schedule conflict(s).",
                    data=result_payload,
                )
            )
            return result_payload

        def create_or_update_task(
            action: str,
            task_id: str = "",
            title: str = "",
            deliverable: str = "",
            owner: str = "",
            start_date: str = "",
            due_date: str = "",
            priority: str = "Medium",
            status: str = "Todo",
        ) -> Dict[str, Any]:
            """Create a new scheduled task ('action'='create') or update an existing task ('action'='update') by task_id."""
            if action.lower() == "update" and task_id:
                for t in tasks:
                    if t.id.lower() == task_id.lower():
                        if title:
                            t.title = title
                        if deliverable:
                            t.deliverable = deliverable
                        if owner:
                            t.owner = owner
                        if start_date:
                            t.start_date = start_date
                        if due_date:
                            t.due_date = due_date
                        if priority in ("Critical", "High", "Medium", "Low"):
                            t.priority = priority  # type: ignore
                        if status in ("Todo", "In Progress", "Blocked", "Completed"):
                            t.status = status  # type: ignore
                        payload = {"status": "updated", "task": t.model_dump()}
                        tool_calls_log.append(
                            AgentToolExecution(
                                tool_name="create_or_update_task",
                                arguments={"action": "update", "task_id": task_id, "status": t.status},
                                result_summary=f"Updated task {t.id} ('{t.title}') -> Status: {t.status}, Due: {t.due_date}.",
                                data=payload,
                            )
                        )
                        return payload
                return {"error": f"Task ID '{task_id}' not found."}
            else:
                prio = priority if priority in ("Critical", "High", "Medium", "Low") else "Medium"
                st = status if status in ("Todo", "In Progress", "Blocked", "Completed") else "Todo"
                new_t = ExtractedTask(
                    id=f"tsk-agent-{len(tasks) + 1:02d}",
                    title=title or deliverable[:40] or "Scheduled Deliverable",
                    deliverable=deliverable or title or "Deliverable",
                    owner=owner or "Unassigned",
                    assigner="NexusAI Agent",
                    start_date=start_date or "2026-11-02",
                    due_date=due_date or "2026-11-09",
                    priority=prio,  # type: ignore
                    status=st,  # type: ignore
                    estimated_hours=8.0,
                    dependencies=[],
                    source_email_id="agent",
                )
                tasks.append(new_t)
                payload = {"status": "created", "task": new_t.model_dump()}
                tool_calls_log.append(
                    AgentToolExecution(
                        tool_name="create_or_update_task",
                        arguments={"action": "create", "owner": new_t.owner, "title": new_t.title},
                        result_summary=f"Created task {new_t.id} for {new_t.owner} (Due {new_t.due_date}).",
                        data=payload,
                    )
                )
                return payload

        def export_schedule_to_tool(format: str = "markdown", owner: str = "") -> Dict[str, Any]:
            """Generate a structured schedule export in 'ics' (iCalendar), 'csv', or 'markdown' format for a given owner or all owners."""
            fmt = format.lower().strip()
            if fmt in ("ics", "ical"):
                content = self.productivity_manager.export_icalendar(tasks, owner_filter=owner or None)
            elif fmt == "csv":
                content = self.productivity_manager.export_csv(tasks, owner_filter=owner or None)
            else:
                content = self.productivity_manager.export_markdown_schedule(tasks, owner_filter=owner or None)

            payload = {"format": fmt, "owner_filter": owner or "ALL", "export_content": content[:1500]}
            tool_calls_log.append(
                AgentToolExecution(
                    tool_name="export_schedule_to_tool",
                    arguments={"format": fmt, "owner": owner or "ALL"},
                    result_summary=f"Generated {fmt.upper()} schedule export ({len(content)} bytes).",
                    data=payload,
                )
            )
            return payload

        client = genai.Client(api_key=self.extractor.api_key)
        candidate_models = [self.extractor.model_name]
        for fallback_m in ("gemini-2.5-flash", "gemini-2.0-flash"):
            if fallback_m not in candidate_models:
                candidate_models.append(fallback_m)

        response = None
        last_err = None
        for m_name in candidate_models:
            try:
                response = client.models.generate_content(
                    model=m_name,
                    contents=message,
                    config=types.GenerateContentConfig(
                        system_instruction=AGENT_SYSTEM_INSTRUCTION,
                        tools=[
                            extract_email_intelligence,
                            query_organizational_graph,
                            list_and_filter_tasks,
                            create_or_update_task,
                            export_schedule_to_tool,
                        ],
                        temperature=0.1,
                    ),
                )
                break
            except Exception as err:
                last_err = err
                if "404" in str(err) or "NOT_FOUND" in str(err):
                    continue
                raise

        if response is None:
            raise RuntimeError(f"Gemini tool-calling failed across models: {last_err}")

        return AgentChatResponse(
            reply=response.text or "Completed tool execution.",
            engine=f"{self.extractor.model_name} (Native Function-Calling Agent)",
            tool_calls=tool_calls_log,
            suggested_followups=self._get_followups(),
        )

    def _parse_embedded_email(self, raw_text: str) -> Dict[str, Any]:
        """Parse Subject, From, To, Date, and Body from a user prompt containing an embedded email."""
        subj_m = re.search(r"Subject:\s*([^\n]+?)(?=\s+(?:From:|To:|Date:|Hi\b|Team\b|Hello\b)|\n|$)", raw_text, re.IGNORECASE)
        from_m = re.search(r"From:\s*([^\n]+?)(?=\s+(?:To:|Date:|Subject:)|\n|$)", raw_text, re.IGNORECASE)
        to_m = re.search(r"To:\s*([^\n]+?)(?=\s+(?:Date:|Subject:|Team\b|Hi\b)|\n|$)", raw_text, re.IGNORECASE)
        date_m = re.search(r"Date:\s*([0-9T:\-Z]+)", raw_text, re.IGNORECASE)

        subject = subj_m.group(1).strip() if subj_m else "Ad-Hoc Agent Extracted Email"
        sender_name = "Workspace User"
        sender_email = "user@nexusai.io"
        if from_m:
            s_name, s_addr = parseaddr(from_m.group(1).strip())
            if s_name:
                sender_name = s_name
            if s_addr:
                sender_email = s_addr

        recipients = []
        if to_m:
            for part in to_m.group(1).split(","):
                r_name, r_addr = parseaddr(part.strip())
                if r_name or r_addr:
                    recipients.append(
                        {
                            "name": r_name or r_addr.split("@")[0].replace(".", " ").title(),
                            "email": r_addr or f"{r_name.lower().replace(' ', '.')}@nexusai.io",
                            "type": "to",
                        }
                    )
        if not recipients:
            recipients = [{"name": "Team", "email": "team@nexusai.io", "type": "to"}]

        timestamp = date_m.group(1).strip() if date_m else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        body = raw_text
        if subj_m:
            body = raw_text[subj_m.start():]
        return {
            "subject": subject,
            "sender_name": sender_name,
            "sender_email": sender_email,
            "recipients": recipients,
            "timestamp": timestamp,
            "body": body,
        }

    def _run_autonomous_multi_tool_engine(
        self,
        message: str,
        emails: List[EmailMessage],
        tasks: List[ExtractedTask],
    ) -> AgentChatResponse:
        """
        Multi-tool autonomous execution engine that executes every requested tool
        (email extraction, task creation/updates, graph centrality analysis, conflict
        detection, and schedule export) and synthesizes a complete multi-part response.
        """
        tool_calls: List[AgentToolExecution] = []
        msg_lower = message.lower().strip()
        sections: List[str] = []

        extracted_email_obj: Optional[EmailMessage] = None
        if any(kw in msg_lower for kw in ["extract", "parse this email", "subject:", "new email:", "from:"]):
            parsed_hdrs = self._parse_embedded_email(message)
            temp_email = EmailMessage(
                id=f"eml-{len(emails) + 1:03d}",
                thread_id=f"thr-agent-{len(emails) + 1:02d}",
                subject=parsed_hdrs["subject"],
                sender_name=parsed_hdrs["sender_name"],
                sender_email=parsed_hdrs["sender_email"],
                recipients=parsed_hdrs["recipients"],
                timestamp=parsed_hdrs["timestamp"],
                body=parsed_hdrs["body"],
            )
            ext_result = self.extractor.extract(temp_email, prefer_gemini=False)
            temp_email.extraction = ext_result
            emails.append(temp_email)
            for t in ext_result.tasks:
                tasks.append(t)
            extracted_email_obj = temp_email

            tool_calls.append(
                AgentToolExecution(
                    tool_name="extract_email_intelligence",
                    arguments={"email_id": temp_email.id, "subject": temp_email.subject, "sender": temp_email.sender_name},
                    result_summary=f"Extracted {len(ext_result.topics)} topics, {len(ext_result.entities.people)} people, and {len(ext_result.tasks)} new tasks into the schedule.",
                    data=ext_result.model_dump(),
                )
            )

            sections.append(f"### 📨 Extracted Email Intelligence (`{temp_email.id}`: *{temp_email.subject}*)")
            sections.append(
                f"- **Executive Summary**: {ext_result.summary.executive_summary}\n"
                f"- **Topics**: {', '.join(f'`{t.name}` ({int(t.confidence*100)}%)' for t in ext_result.topics)}\n"
                f"- **People Identified**: {', '.join(p.name for p in ext_result.entities.people)}\n"
                f"- **Locations & Orgs**: {', '.join([o.name for o in ext_result.entities.organizations] + [l.name for l in ext_result.entities.locations])}"
            )
            if ext_result.tasks:
                sections.append("\n#### Newly Extracted & Scheduled Deliverables")
                sections.append("| Task ID | Owner | Deliverable | Start Date | Due Date | Priority | Status |")
                sections.append("|---|---|---|---|---|---|---|")
                for t in ext_result.tasks:
                    sections.append(
                        f"| `{t.id}` | **{t.owner}** | {t.deliverable} | {t.start_date} | **{t.due_date}** | `{t.priority}` | {t.status} |"
                    )

        status_match = re.search(
            r"(?:mark|set|update)\s+(?:task\s+)?(tsk-[a-z0-9\-]+)\s+(?:as|to)\s+(completed|in progress|blocked|todo)",
            msg_lower,
        )
        if status_match:
            target_id = status_match.group(1)
            new_status_raw = status_match.group(2)
            status_map = {
                "completed": "Completed",
                "in progress": "In Progress",
                "blocked": "Blocked",
                "todo": "Todo",
            }
            new_status = status_map.get(new_status_raw, "In Progress")
            for t in tasks:
                if t.id.lower() == target_id:
                    t.status = new_status  # type: ignore
                    tool_calls.append(
                        AgentToolExecution(
                            tool_name="create_or_update_task",
                            arguments={"action": "update", "task_id": t.id, "status": new_status},
                            result_summary=f"Updated task {t.id} ('{t.title}') to status '{new_status}'.",
                            data=t.model_dump(),
                        )
                    )
                    sections.append(
                        f"### ✅ Task Schedule Updated\n"
                        f"- Updated **`{t.id}`** (*{t.deliverable}*, Owner: **{t.owner}**) status to **`{new_status}`**."
                    )
                    break

        graph_data = self.graph_engine.build_graph(emails, tasks)
        sched_summary = self.productivity_manager.build_schedule_summary(tasks)

        matched_owners: List[str] = []
        for w in sched_summary["owner_workloads"]:
            owner_full = w["owner"]
            if owner_full.lower() in msg_lower or owner_full.split()[0].lower() in msg_lower:
                if owner_full not in matched_owners:
                    matched_owners.append(owner_full)

        if "betweenness" in msg_lower or "bottleneck" in msg_lower:
            top_bridge = graph_data["analytics"]["top_bridges"][0]["name"] if graph_data["analytics"]["top_bridges"] else None
            if top_bridge and top_bridge not in matched_owners:
                matched_owners.append(top_bridge)

        wants_graph = any(
            kw in msg_lower
            for kw in ["graph", "central", "influencer", "bottleneck", "bridge", "network", "pagerank", "betweenness", "cluster", "community"]
        )
        if wants_graph or not sections:
            tool_calls.append(
                AgentToolExecution(
                    tool_name="query_organizational_graph",
                    arguments={"focus_entities": matched_owners or "ALL", "metrics": ["pagerank", "betweenness_centrality", "communities"]},
                    result_summary=(
                        f"Analyzed {graph_data['analytics']['total_nodes']} nodes and "
                        f"{graph_data['analytics']['total_edges']} edges across "
                        f"{len(graph_data['analytics']['communities'])} organizational clusters."
                    ),
                    data={"top_influencers": graph_data["analytics"]["top_influencers"][:5]},
                )
            )
            sections.append("### 🕸️ Organizational Graph Centrality & Influence")
            rankings = graph_data["analytics"]["person_rankings"]
            if matched_owners and extracted_email_obj:
                focus_people = [p for p in rankings if p["name"] in matched_owners]
            else:
                focus_people = rankings[:6]

            sections.append("| Person | Role | Organization | PageRank (Influence) | Betweenness (Bridge Score) | Community | Tasks Owned |")
            sections.append("|---|---|---|---|---|---|---|")
            for p in focus_people:
                sections.append(
                    f"| **{p['name']}** | {p['role']} | {p['organization']} | `{p['pagerank']}` | `{p['betweenness_centrality']}` | Cluster #{p['community_id']} | {p['tasks_owned']} |"
                )

        wants_tasks = any(
            kw in msg_lower
            for kw in ["task", "schedule", "conflict", "workload", "deliverable", "todo", "due", "critical", "priority", "overloaded"]
        ) or bool(matched_owners)

        if wants_tasks:
            tool_calls.append(
                AgentToolExecution(
                    tool_name="list_and_filter_tasks",
                    arguments={"owners": matched_owners or "ALL", "detect_conflicts": True},
                    result_summary=(
                        f"Evaluated {len(tasks)} deliverables across {len(sched_summary['owner_workloads'])} owners; "
                        f"detected {len(sched_summary['schedule_conflicts'])} high-priority schedule conflict(s)."
                    ),
                    data={"conflicts": sched_summary["schedule_conflicts"]},
                )
            )

            relevant_conflicts = [
                c for c in sched_summary["schedule_conflicts"]
                if not matched_owners or c["owner"] in matched_owners
            ]
            if relevant_conflicts:
                sections.append("### ⚠️ Detected High-Priority Schedule Conflicts & Overlaps")
                for c in relevant_conflicts:
                    sections.append(
                        f"- **{c['owner']}** (`{c['overlap_window']}`, **{c['severity']} Risk**): *{c['task_a']}* overlaps with *{c['task_b']}*"
                    )

            if matched_owners:
                owner_tasks = [t for t in tasks if t.owner in matched_owners]
                owner_tasks.sort(key=lambda x: (x.owner, x.due_date))
                sections.append(f"### 📅 Active Deliverable Schedule ({', '.join(matched_owners)})")
                sections.append("| Task ID | Owner | Deliverable | Start Date | Due Date | Priority | Status |")
                sections.append("|---|---|---|---|---|---|---|")
                for t in owner_tasks:
                    sections.append(
                        f"| `{t.id}` | **{t.owner}** | {t.deliverable} | {t.start_date} | **{t.due_date}** | `{t.priority}` | {t.status} |"
                    )
            else:
                due_before_m = re.search(r"before\s+(202\d-\d{2}-\d{2})", msg_lower)
                cutoff_due = due_before_m.group(1) if due_before_m else None
                filtered_t = list(tasks)
                if "critical" in msg_lower and "high" in msg_lower:
                    filtered_t = [t for t in filtered_t if t.priority in ("Critical", "High")]
                elif "critical" in msg_lower:
                    filtered_t = [t for t in filtered_t if t.priority == "Critical"]
                if "todo" in msg_lower or "in progress" in msg_lower:
                    filtered_t = [t for t in filtered_t if t.status != "Completed"]
                if cutoff_due:
                    filtered_t = [t for t in filtered_t if t.due_date <= cutoff_due]
                filtered_t.sort(key=lambda x: x.due_date)

                sections.append("### 📋 Filtered Deliverable Schedule & Workload Analysis")
                overloaded = [w for w in sched_summary["owner_workloads"] if w["utilization_status"] == "Overloaded"]
                if overloaded:
                    sections.append(
                        "- **Overloaded Owners**: "
                        + ", ".join(f"**{w['owner']}** (`{w['estimated_active_hours']}h` active, `{w['critical_tasks']}` Critical)" for w in overloaded)
                    )
                sections.append("\n| Task ID | Owner | Deliverable | Start Date | Due Date | Priority | Status |")
                sections.append("|---|---|---|---|---|---|---|")
                for t in filtered_t[:14]:
                    sections.append(
                        f"| `{t.id}` | **{t.owner}** | {t.deliverable} | {t.start_date} | **{t.due_date}** | `{t.priority}` | {t.status} |"
                    )

        if any(kw in msg_lower for kw in ["export", "markdown", "ics", "ical", "csv"]):
            tool_calls.append(
                AgentToolExecution(
                    tool_name="export_schedule_to_tool",
                    arguments={"format": "markdown", "owners": matched_owners or "ALL"},
                    result_summary="Generated structured schedule export ready for download in Productivity Hub.",
                    data={"export_links": ["/api/schedule/export/ics", "/api/schedule/export/csv", "/api/schedule/export/md"]},
                )
            )

        return AgentChatResponse(
            reply="\n\n".join(sections),
            engine=f"{self.extractor.model_name} Multi-Tool Agent",
            tool_calls=tool_calls,
            suggested_followups=self._get_followups(),
        )

    def _get_followups(self) -> List[str]:
        return [
            "Who are the top organizational influencers and cross-team bridges in the graph?",
            "Show all Critical priority deliverables and detect schedule conflicts",
            "Show Liam O'Connor's deliverable schedule and workload utilization",
            "Mark task tsk-002-01 as Completed and show updated schedule conflicts",
        ]

