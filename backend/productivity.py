from __future__ import annotations
import csv
import io
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from collections import defaultdict

from backend.models import ExtractedTask


class ProductivityScheduleManager:
    """
    Converts extracted email tasks into structured schedules, detects workload bottlenecks,
    and exports to iCalendar (.ics), CSV, JSON, and Markdown formats.
    """

    def build_schedule_summary(self, tasks: List[ExtractedTask], reference_date: str = "2026-11-01") -> Dict[str, Any]:
        by_owner: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        by_status: Dict[str, int] = {"Todo": 0, "In Progress": 0, "Blocked": 0, "Completed": 0}
        by_priority: Dict[str, int] = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}

        sorted_tasks = sorted(tasks, key=lambda t: (t.due_date, t.start_date))
        for t in sorted_tasks:
            by_owner[t.owner].append(t.model_dump())
            by_status[t.status] = by_status.get(t.status, 0) + 1
            by_priority[t.priority] = by_priority.get(t.priority, 0) + 1

        owner_workloads = []
        schedule_conflicts = []
        for owner, owner_tasks in by_owner.items():
            active_tasks = [t for t in owner_tasks if t["status"] != "Completed"]
            total_hours = sum(t.get("estimated_hours", 4.0) for t in active_tasks)
            critical_count = sum(1 for t in active_tasks if t["priority"] == "Critical")

            for i in range(len(active_tasks)):
                for j in range(i + 1, len(active_tasks)):
                    t1, t2 = active_tasks[i], active_tasks[j]
                    if t1["start_date"] <= t2["due_date"] and t2["start_date"] <= t1["due_date"]:
                        if t1["priority"] in ("Critical", "High") and t2["priority"] in ("Critical", "High"):
                            schedule_conflicts.append(
                                {
                                    "owner": owner,
                                    "task_a": t1["title"],
                                    "task_b": t2["title"],
                                    "overlap_window": f"{max(t1['start_date'], t2['start_date'])} to {min(t1['due_date'], t2['due_date'])}",
                                    "severity": "High" if "Critical" in (t1["priority"], t2["priority"]) else "Medium",
                                }
                            )

            owner_workloads.append(
                {
                    "owner": owner,
                    "owner_email": owner_tasks[0].get("owner_email"),
                    "total_tasks": len(owner_tasks),
                    "active_tasks": len(active_tasks),
                    "completed_tasks": len(owner_tasks) - len(active_tasks),
                    "critical_tasks": critical_count,
                    "estimated_active_hours": total_hours,
                    "utilization_status": (
                        "Overloaded" if total_hours >= 28 or critical_count >= 2 else ("Balanced" if total_hours >= 12 else "Light")
                    ),
                    "tasks": owner_tasks,
                }
            )

        owner_workloads.sort(key=lambda x: (x["estimated_active_hours"], x["total_tasks"]), reverse=True)

        return {
            "total_tasks": len(tasks),
            "by_status": by_status,
            "by_priority": by_priority,
            "owner_workloads": owner_workloads,
            "schedule_conflicts": schedule_conflicts,
            "reference_date": reference_date,
        }

    def export_icalendar(self, tasks: List[ExtractedTask], owner_filter: Optional[str] = None) -> str:
        """Generate RFC 5545 iCalendar (.ics) file for extracted tasks & deliverables."""
        filtered = [
            t for t in tasks if not owner_filter or owner_filter.lower() in t.owner.lower()
        ]
        now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//NexusAI//Email Intelligence Productivity Scheduler//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "X-WR-CALNAME:Email Intelligence Deliverables Schedule",
        ]
        for t in filtered:
            dt_start = t.start_date.replace("-", "")
            dt_end = t.due_date.replace("-", "")
            summary_esc = f"[{t.priority}] {t.title} ({t.owner})".replace(",", "\\,")
            desc_esc = (
                f"Deliverable: {t.deliverable}\\n"
                f"Owner: {t.owner} ({t.owner_email or 'N/A'})\\n"
                f"Assigned By: {t.assigner or 'N/A'}\\n"
                f"Status: {t.status} | Priority: {t.priority}\\n"
                f"Start: {t.start_date} | Due: {t.due_date}"
            ).replace(",", "\\,")
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{t.id}@email-intelligence.nexusai.io",
                    f"DTSTAMP:{now_stamp}",
                    f"DTSTART;VALUE=DATE:{dt_start}",
                    f"DTEND;VALUE=DATE:{dt_end}",
                    f"SUMMARY:{summary_esc}",
                    f"DESCRIPTION:{desc_esc}",
                    f"STATUS:{'COMPLETED' if t.status == 'Completed' else 'CONFIRMED'}",
                    "END:VEVENT",
                ]
            )
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"

    def export_csv(self, tasks: List[ExtractedTask], owner_filter: Optional[str] = None) -> str:
        """Generate structured CSV for Notion, Linear, Jira, Excel, or Google Sheets."""
        filtered = [
            t for t in tasks if not owner_filter or owner_filter.lower() in t.owner.lower()
        ]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Task ID",
                "Owner",
                "Owner Email",
                "Deliverable",
                "Task Title",
                "Start Date",
                "Due Date",
                "Priority",
                "Status",
                "Estimated Hours",
                "Assigned By",
                "Source Email ID",
            ]
        )
        for t in sorted(filtered, key=lambda x: x.due_date):
            writer.writerow(
                [
                    t.id,
                    t.owner,
                    t.owner_email or "",
                    t.deliverable,
                    t.title,
                    t.start_date,
                    t.due_date,
                    t.priority,
                    t.status,
                    t.estimated_hours,
                    t.assigner or "",
                    t.source_email_id,
                ]
            )
        return output.getvalue()

    def export_markdown_schedule(self, tasks: List[ExtractedTask], owner_filter: Optional[str] = None) -> str:
        """Generate structured Markdown To-Do List and Deliverable Schedule."""
        filtered = [
            t for t in tasks if not owner_filter or owner_filter.lower() in t.owner.lower()
        ]
        md = ["# Structured Deliverable Schedule & Action Plan\n"]
        md.append("| Task ID | Owner | Deliverable | Start Date | Due Date | Priority | Status |")
        md.append("|---|---|---|---|---|---|---|")
        for t in sorted(filtered, key=lambda x: x.due_date):
            md.append(
                f"| `{t.id}` | **{t.owner}** | {t.deliverable} | {t.start_date} | {t.due_date} | `{t.priority}` | {t.status} |"
            )
        return "\n".join(md)

