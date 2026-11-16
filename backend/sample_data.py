from __future__ import annotations
import email
from email import policy
from email.utils import parseaddr, getaddresses, parsedate_to_datetime
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from backend.models import EmailMessage


DIRECTORY_PROFILES: Dict[str, Dict[str, str]] = {
    "sarah.chen@nexusai.io": {
        "name": "Sarah Chen",
        "role": "VP of Product",
        "organization": "Product Strategy (NexusAI)",
        "location": "San Francisco",
    },
    "marcus.vance@nexusai.io": {
        "name": "Marcus Vance",
        "role": "Principal Systems Architect",
        "organization": "Core Engineering (NexusAI)",
        "location": "Seattle",
    },
    "elena.rodriguez@nexusai.io": {
        "name": "Elena Rodriguez",
        "role": "Lead Security Engineer",
        "organization": "InfoSec & Compliance (NexusAI)",
        "location": "Austin",
    },
    "david.kim@nexusai.io": {
        "name": "David Kim",
        "role": "Senior Data Engineer",
        "organization": "Data Platform (NexusAI)",
        "location": "New York",
    },
    "priya.patel@nexusai.io": {
        "name": "Priya Patel",
        "role": "General Counsel",
        "organization": "Legal & Governance (NexusAI)",
        "location": "New York",
    },
    "alex.rivera@nexusai.io": {
        "name": "Alex Rivera",
        "role": "Lead Product Designer",
        "organization": "Design Systems (NexusAI)",
        "location": "San Francisco",
    },
    "jordan.taylor@nexusai.io": {
        "name": "Jordan Taylor",
        "role": "Enterprise Account Executive",
        "organization": "Enterprise Sales (NexusAI)",
        "location": "Chicago",
    },
    "liam.oconnor@nexusai.io": {
        "name": "Liam O'Connor",
        "role": "DevOps & SRE Lead",
        "organization": "Cloud Infrastructure (NexusAI)",
        "location": "Dublin",
    },
    "claire.dupont@acmecorp.com": {
        "name": "Claire Dupont",
        "role": "VP of Procurement",
        "organization": "Acme Corp",
        "location": "London",
    },
    "raj.mehta@cyberguard.io": {
        "name": "Raj Mehta",
        "role": "Lead Penetration Tester",
        "organization": "CyberGuard Security",
        "location": "Boston",
    },
}


def get_initial_emails() -> List[EmailMessage]:
    raw_emails = [
        {
            "id": "eml-001",
            "thread_id": "thr-horizon-launch",
            "subject": "Project Horizon Q4 Launch Roadmap & Deliverable Assignments",
            "sender_name": "Sarah Chen",
            "sender_email": "sarah.chen@nexusai.io",
            "sender_role": "VP of Product",
            "sender_dept": "Product Strategy",
            "recipients": [
                {"name": "Marcus Vance", "email": "marcus.vance@nexusai.io", "type": "to"},
                {"name": "Alex Rivera", "email": "alex.rivera@nexusai.io", "type": "to"},
                {"name": "David Kim", "email": "david.kim@nexusai.io", "type": "cc"},
                {"name": "Elena Rodriguez", "email": "elena.rodriguez@nexusai.io", "type": "cc"},
            ],
            "timestamp": "2026-10-20T09:15:00Z",
            "body": (
                "Team,\n\n"
                "Following yesterday's executive steering committee meeting in San Francisco, we have officially locked "
                "November 18, 2026 as the General Availability launch date for Project Horizon.\n\n"
                "To hit our readiness gates, please note the following critical deliverables and timelines:\n"
                "1. Marcus Vance: Finalize the distributed graph inference API specification and latency benchmarks. "
                "Start on 2026-10-21 and deliver the spec document by 2026-10-28 (High Priority).\n"
                "2. Alex Rivera: Complete the interactive graph explorer Figma prototypes and accessibility audit for the "
                "San Francisco design review. Start 2026-10-22, due by 2026-10-30.\n"
                "3. David Kim: Build the real-time streaming ingestion connector for enterprise email webhooks in the "
                "New York data cluster. Start on 2026-10-23 and finish by 2026-11-04 (Critical Priority).\n\n"
                "We will hold our mid-sprint architecture checkpoint on 2026-10-29. Please flag any blockers immediately.\n\n"
                "Best,\nSarah Chen\nVP of Product, NexusAI"
            ),
        },
        {
            "id": "eml-002",
            "thread_id": "thr-horizon-launch",
            "subject": "Re: Project Horizon Q4 Launch Roadmap & Deliverable Assignments",
            "sender_name": "Marcus Vance",
            "sender_email": "marcus.vance@nexusai.io",
            "sender_role": "Principal Systems Architect",
            "sender_dept": "Core Engineering",
            "recipients": [
                {"name": "Sarah Chen", "email": "sarah.chen@nexusai.io", "type": "to"},
                {"name": "Liam O'Connor", "email": "liam.oconnor@nexusai.io", "type": "to"},
                {"name": "David Kim", "email": "david.kim@nexusai.io", "type": "cc"},
            ],
            "timestamp": "2026-10-21T14:30:00Z",
            "body": (
                "Hi Sarah,\n\n"
                "I've started drafting the distributed graph inference API spec in Seattle. Our initial load tests show "
                "sub-120ms p99 latency on AWS us-west-2, which exceeds our Q4 SLA target.\n\n"
                "However, we need Kubernetes GPU autoscaling provisioned in the Dublin and Seattle clusters before "
                "David's streaming connector goes live.\n"
                "- Action for Liam O'Connor: Provision Terraform GPU node pools and Redis cluster failover in Dublin "
                "starting 2026-10-24, with full staging deployment due by 2026-11-02 (Critical Priority).\n"
                "- Action for Marcus Vance: Deliver the OpenAPI 3.1 contract and gRPC protobuf schemas to David Kim "
                "between 2026-10-22 and 2026-10-27.\n\n"
                "Once Liam completes the staging cluster setup on November 2, we can run the full end-to-end soak test.\n\n"
                "Regards,\nMarcus Vance\nPrincipal Systems Architect"
            ),
        },
        {
            "id": "eml-003",
            "thread_id": "thr-security-audit",
            "subject": "URGENT: SOC2 Type II Penetration Test & Zero-Trust Token Remediation",
            "sender_name": "Elena Rodriguez",
            "sender_email": "elena.rodriguez@nexusai.io",
            "sender_role": "Lead Security Engineer",
            "sender_dept": "InfoSec & Compliance",
            "recipients": [
                {"name": "Marcus Vance", "email": "marcus.vance@nexusai.io", "type": "to"},
                {"name": "Liam O'Connor", "email": "liam.oconnor@nexusai.io", "type": "to"},
                {"name": "Raj Mehta", "email": "raj.mehta@cyberguard.io", "type": "cc"},
                {"name": "Sarah Chen", "email": "sarah.chen@nexusai.io", "type": "cc"},
            ],
            "timestamp": "2026-10-23T11:05:00Z",
            "body": (
                "Marcus, Liam,\n\n"
                "CyberGuard Security (led by Raj Mehta in Boston) completed phase 1 of our external penetration test "
                "for SOC2 Type II certification. While core encryption passed, they identified two findings that must "
                "be remediated before the Acme Corp security sign-off on November 10, 2026:\n\n"
                "1. Elena Rodriguez will implement OAuth2 PKCE token rotation and strict CSP headers on the API gateway. "
                "Start date: 2026-10-24, Due date: 2026-11-03 (Critical Priority).\n"
                "2. Liam O'Connor must rotate all production KMS encryption keys and enforce mutual TLS (mTLS) across "
                "internal microservices in Austin and Dublin. Start: 2026-10-26, Due: 2026-11-05 (High Priority).\n"
                "3. Raj Mehta will execute the re-verification penetration test report for CyberGuard Security starting "
                "2026-11-06 and deliver the final attestation letter by 2026-11-09.\n\n"
                "Please prioritize this alongside the Project Horizon staging work.\n\n"
                "Thanks,\nElena Rodriguez\nLead Security Engineer, Austin Office"
            ),
        },
        {
            "id": "eml-004",
            "thread_id": "thr-acme-deal",
            "subject": "Acme Corp $1.2M Enterprise Agreement - DPA & SLA Redlines",
            "sender_name": "Jordan Taylor",
            "sender_email": "jordan.taylor@nexusai.io",
            "sender_role": "Enterprise Account Executive",
            "sender_dept": "Enterprise Sales",
            "recipients": [
                {"name": "Priya Patel", "email": "priya.patel@nexusai.io", "type": "to"},
                {"name": "Elena Rodriguez", "email": "elena.rodriguez@nexusai.io", "type": "to"},
                {"name": "Claire Dupont", "email": "claire.dupont@acmecorp.com", "type": "cc"},
                {"name": "Sarah Chen", "email": "sarah.chen@nexusai.io", "type": "cc"},
            ],
            "timestamp": "2026-10-25T16:20:00Z",
            "body": (
                "Hi Priya and Elena,\n\n"
                "I just wrapped up our commercial negotiation call in Chicago with Claire Dupont (VP of Procurement at "
                "Acme Corp in London). Acme Corp is ready to sign the $1.2M multi-year enterprise license for Project "
                "Horizon, provided we finalize two contract items before their November 12 board meeting:\n\n"
                "- Priya Patel: Complete legal redlines on the EU GDPR Data Processing Addendum (DPA) and 99.95% uptime "
                "SLA indemnification clause. Start on 2026-10-26 and send the revised contract to Claire Dupont by "
                "2026-11-04 (Critical Priority).\n"
                "- Jordan Taylor: Prepare the custom enterprise onboarding and executive QBR schedule for Acme Corp "
                "in London. Start 2026-10-28, due by 2026-11-06 (Medium Priority).\n"
                "- Elena Rodriguez: Share the SOC2 bridge letter and data residency architecture diagram with Acme Corp's "
                "CISO by 2026-11-05 (High Priority).\n\n"
                "Closing Acme Corp is our #1 Q4 revenue milestone. Let's sync on Tuesday.\n\n"
                "Best,\nJordan Taylor\nEnterprise Account Executive, Chicago"
            ),
        },
        {
            "id": "eml-005",
            "thread_id": "thr-acme-deal",
            "subject": "Re: Acme Corp $1.2M Enterprise Agreement - DPA & SLA Redlines",
            "sender_name": "Priya Patel",
            "sender_email": "priya.patel@nexusai.io",
            "sender_role": "General Counsel",
            "sender_dept": "Legal & Governance",
            "recipients": [
                {"name": "Jordan Taylor", "email": "jordan.taylor@nexusai.io", "type": "to"},
                {"name": "Claire Dupont", "email": "claire.dupont@acmecorp.com", "type": "to"},
                {"name": "Sarah Chen", "email": "sarah.chen@nexusai.io", "type": "cc"},
            ],
            "timestamp": "2026-10-27T10:45:00Z",
            "body": (
                "Jordan, Claire,\n\n"
                "Our New York legal team has reviewed Acme Corp's redlines on the Master Services Agreement and EU GDPR "
                "Data Processing Addendum. We approve the 99.95% SLA credit tier and the Dublin EU data residency commitment.\n\n"
                "Next steps:\n"
                "1. Claire Dupont: Review final legal redlines with Acme Corp's London counsel and confirm signature "
                "readiness between 2026-10-29 and 2026-11-07 (High Priority).\n"
                "2. Priya Patel: Finalize the sub-processor disclosure annex for AWS and Google Cloud Vertex AI starting "
                "2026-10-28, due 2026-11-02 (Medium Priority).\n\n"
                "Warm regards,\nPriya Patel\nGeneral Counsel, NexusAI (New York)"
            ),
        },
        {
            "id": "eml-006",
            "thread_id": "thr-data-pipeline",
            "subject": "Entity Resolution Pipeline & Temporal Graph Indexing Benchmarks",
            "sender_name": "David Kim",
            "sender_email": "david.kim@nexusai.io",
            "sender_role": "Senior Data Engineer",
            "sender_dept": "Data Platform",
            "recipients": [
                {"name": "Marcus Vance", "email": "marcus.vance@nexusai.io", "type": "to"},
                {"name": "Alex Rivera", "email": "alex.rivera@nexusai.io", "type": "to"},
                {"name": "Sarah Chen", "email": "sarah.chen@nexusai.io", "type": "cc"},
            ],
            "timestamp": "2026-10-28T15:10:00Z",
            "body": (
                "Hey Marcus and Alex,\n\n"
                "Great news from the New York Data Platform team! We integrated the Gemini structured entity extraction "
                "pipeline with our temporal graph indexer. Entity disambiguation accuracy across people, organizations, "
                "and locations jumped from 84% to 97.4%.\n\n"
                "To wire this into the frontend UI before code freeze on November 12, we need the following:\n"
                "- David Kim: Expose the temporal graph snapshot endpoint (/api/graph/temporal) and community clustering "
                "metrics. Start 2026-10-29, due by 2026-11-05 (High Priority).\n"
                "- Alex Rivera: Integrate the interactive timeline slider and iCalendar (.ics) schedule export modal into "
                "the React dashboard. Start 2026-10-30, due by 2026-11-07 (High Priority).\n\n"
                "Let's demo the live graph to Sarah Chen during Friday's product review in San Francisco.\n\n"
                "Cheers,\nDavid Kim\nSenior Data Engineer"
            ),
        },
        {
            "id": "eml-007",
            "thread_id": "thr-horizon-launch",
            "subject": "Design Review Sign-off & Executive Launch Deck Deliverables",
            "sender_name": "Alex Rivera",
            "sender_email": "alex.rivera@nexusai.io",
            "sender_role": "Lead Product Designer",
            "sender_dept": "Design Systems",
            "recipients": [
                {"name": "Sarah Chen", "email": "sarah.chen@nexusai.io", "type": "to"},
                {"name": "Jordan Taylor", "email": "jordan.taylor@nexusai.io", "type": "to"},
                {"name": "David Kim", "email": "david.kim@nexusai.io", "type": "cc"},
            ],
            "timestamp": "2026-10-30T13:00:00Z",
            "body": (
                "Hi Sarah and Jordan,\n\n"
                "The interactive graph explorer Figma prototypes and WCAG AA accessibility audit are now 100% complete! "
                "Our usability testing with five pilot customers in San Francisco and Chicago received a 4.9/5 score.\n\n"
                "For the November 18 launch campaign, here are the remaining creative and GTM tasks:\n"
                "1. Sarah Chen: Author the Project Horizon executive launch blog post and keynote narrative. Start "
                "2026-11-01, due by 2026-11-10 (High Priority).\n"
                "2. Alex Rivera: Produce the interactive product walkthrough video and customer ROI calculator widget. "
                "Start 2026-11-02, due by 2026-11-11 (Medium Priority).\n"
                "3. Jordan Taylor: Coordinate pilot customer case study quotes with Claire Dupont at Acme Corp. Start "
                "2026-11-03, due by 2026-11-12 (Medium Priority).\n\n"
                "Best,\nAlex Rivera\nLead Product Designer"
            ),
        },
        {
            "id": "eml-008",
            "thread_id": "thr-security-audit",
            "subject": "Staging Cluster Readiness & Disaster Recovery Drill Schedule",
            "sender_name": "Liam O'Connor",
            "sender_email": "liam.oconnor@nexusai.io",
            "sender_role": "DevOps & SRE Lead",
            "sender_dept": "Cloud Infrastructure",
            "recipients": [
                {"name": "Elena Rodriguez", "email": "elena.rodriguez@nexusai.io", "type": "to"},
                {"name": "Marcus Vance", "email": "marcus.vance@nexusai.io", "type": "to"},
                {"name": "Sarah Chen", "email": "sarah.chen@nexusai.io", "type": "cc"},
            ],
            "timestamp": "2026-10-31T17:40:00Z",
            "body": (
                "Team,\n\n"
                "Quick infrastructure update from Dublin: Terraform GPU node pools are live in staging, and KMS key "
                "rotation is 80% complete across our US and EU regions.\n\n"
                "Before our November 18 GA launch, we must complete our mandatory production readiness drill:\n"
                "- Liam O'Connor: Execute multi-region chaos engineering and failover drill between Dublin and Seattle "
                "clusters. Start 2026-11-04, due by 2026-11-08 (Critical Priority).\n"
                "- Marcus Vance: Verify zero-downtime database migration scripts and rollback runbooks. Start 2026-11-03, "
                "due by 2026-11-09 (High Priority).\n\n"
                "All metrics are streaming into Grafana. Have a great weekend!\n\n"
                "Slainte,\nLiam O'Connor\nDevOps & SRE Lead, Dublin"
            ),
        },
    ]
    return [EmailMessage(**item) for item in raw_emails]


def parse_eml_content(raw_bytes: bytes) -> Dict[str, Any]:
    """Parse standard RFC 5322 .eml file bytes into an EmailMessage-compatible dict."""
    msg = email.message_from_bytes(raw_bytes, policy=policy.default)
    subject = str(msg.get("subject", "Untitled Email")).strip()
    from_hdr = str(msg.get("from", "Unknown Sender <unknown@example.com>"))
    sender_name, sender_email = parseaddr(from_hdr)
    if not sender_name:
        sender_name = sender_email.split("@")[0].replace(".", " ").title()

    to_addrs = getaddresses(msg.get_all("to", []))
    cc_addrs = getaddresses(msg.get_all("cc", []))
    recipients = []
    for name, addr in to_addrs:
        if addr:
            recipients.append({
                "name": name or addr.split("@")[0].replace(".", " ").title(),
                "email": addr.lower(),
                "type": "to",
            })
    for name, addr in cc_addrs:
        if addr:
            recipients.append({
                "name": name or addr.split("@")[0].replace(".", " ").title(),
                "email": addr.lower(),
                "type": "cc",
            })

    date_hdr = msg.get("date")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if date_hdr:
        try:
            dt = parsedate_to_datetime(str(date_hdr))
            timestamp = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    body = part.get_content()
                    break
                except Exception:
                    pass
    else:
        try:
            body = msg.get_content()
        except Exception:
            body = msg.get_payload(decode=True).decode("utf-8", errors="replace")

    return {
        "id": f"eml-{uuid.uuid4().hex[:6]}",
        "thread_id": f"thr-{uuid.uuid4().hex[:6]}",
        "subject": subject,
        "sender_name": sender_name,
        "sender_email": sender_email.lower() or "unknown@example.com",
        "recipients": recipients,
        "timestamp": timestamp,
        "body": body.strip(),
    }

