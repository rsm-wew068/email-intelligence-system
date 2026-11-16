from fastapi.testclient import TestClient
from backend.main import app


client = TestClient(app)


def test_overview_and_initial_extractions():
    res = client.get("/api/overview")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    metrics = data["metrics"]
    assert metrics["total_emails"] >= 8
    assert metrics["total_topics"] >= 5
    assert metrics["total_people"] >= 8
    assert metrics["total_organizations"] >= 4
    assert metrics["total_locations"] >= 5
    assert metrics["total_tasks"] >= 15
    assert metrics["graph_nodes"] >= 20
    assert metrics["graph_edges"] >= 30


def test_email_extraction_fields():
    res = client.get("/api/emails/eml-001")
    assert res.status_code == 200
    em = res.json()
    ext = em["extraction"]
    assert ext is not None
    assert len(ext["summary"]["executive_summary"]) > 20
    assert len(ext["topics"]) >= 1
    assert len(ext["entities"]["people"]) >= 3
    assert len(ext["entities"]["organizations"]) >= 1
    assert len(ext["entities"]["locations"]) >= 1
    assert len(ext["tasks"]) == 3
    first_task = ext["tasks"][0]
    assert first_task["owner"] == "Marcus Vance"
    assert first_task["start_date"] == "2026-10-21"
    assert first_task["due_date"] == "2026-10-28"
    assert first_task["priority"] == "High"


def test_organizational_and_temporal_graph():
    res_full = client.get("/api/graph")
    assert res_full.status_code == 200
    g_full = res_full.json()
    assert g_full["analytics"]["people_count"] >= 8
    assert len(g_full["analytics"]["top_influencers"]) >= 3
    assert len(g_full["analytics"]["communities"]) >= 1
    assert len(g_full["temporal"]["daily_series"]) >= 5

    res_early = client.get("/api/graph?cutoff_date=2026-10-22")
    assert res_early.status_code == 200
    g_early = res_early.json()
    assert g_early["analytics"]["total_nodes"] < g_full["analytics"]["total_nodes"]


def test_productivity_schedule_and_exports():
    res_tasks = client.get("/api/tasks")
    assert res_tasks.status_code == 200
    tdata = res_tasks.json()
    assert tdata["count"] >= 15
    assert len(tdata["schedule_summary"]["owner_workloads"]) >= 5

    res_ics = client.get("/api/schedule/export/ics")
    assert res_ics.status_code == 200
    assert "BEGIN:VCALENDAR" in res_ics.text
    assert "BEGIN:VEVENT" in res_ics.text

    res_csv = client.get("/api/schedule/export/csv")
    assert res_csv.status_code == 200
    assert "Task ID,Owner,Owner Email,Deliverable" in res_csv.text


def test_ingest_new_email_and_agent_tools():
    ingest_payload = {
        "subject": "Q4 Security Sign-Off & Cloud Failover Verification",
        "sender_name": "Elena Rodriguez",
        "sender_email": "elena.rodriguez@nexusai.io",
        "recipients": ["Liam O'Connor <liam.oconnor@nexusai.io>", "Sarah Chen <sarah.chen@nexusai.io>"],
        "timestamp": "2026-11-01T14:00:00Z",
        "body": (
            "Hi Liam,\n\n"
            "Following our audit in Austin and Dublin, please complete the following:\n"
            "1. Liam O'Connor: Finalize mutual TLS certificate pinning across all production pods starting 2026-11-02, due by 2026-11-07 (Critical Priority).\n"
        ),
        "use_gemini": False,
    }
    res_ing = client.post("/api/emails/ingest", json=ingest_payload)
    assert res_ing.status_code == 200
    ing_data = res_ing.json()
    assert ing_data["status"] == "extracted"
    assert ing_data["tasks_added"] >= 1

    res_agent = client.post(
        "/api/agent/chat",
        json={"message": "Who are the top organizational influencers and show Liam O'Connor's tasks?"},
    )
    assert res_agent.status_code == 200
    agent_data = res_agent.json()
    assert len(agent_data["tool_calls"]) >= 1
    assert "Liam O'Connor" in agent_data["reply"]

    client.post("/api/system/reset")


def test_hitl_email_draft_and_approved_send():
    res_draft = client.post(
        "/api/agent/chat",
        json={"message": "Draft a follow-up email to Marcus Vance about his Critical deliverables"},
    )
    assert res_draft.status_code == 200
    d_data = res_draft.json()
    assert len(d_data["pending_email_drafts"]) >= 1
    draft = d_data["pending_email_drafts"][0]
    assert draft["status"] == "pending_approval"
    assert "Marcus" in draft["to_name"]

    res_send = client.post(
        "/api/emails/send",
        json={
            "draft_id": draft["draft_id"],
            "to_name": draft["to_name"],
            "to_email": draft["to_email"],
            "subject": draft["subject"],
            "body": draft["body"],
        },
    )
    assert res_send.status_code == 200
    s_data = res_send.json()
    assert s_data["status"] == "sent"
    assert "mail.google.com" in s_data["gmail_compose_url"]

    client.post("/api/system/reset")


def test_verbatim_quote_grounding_and_quick_paste():
    from backend.extractor import verify_evidence_quote

    sample_body = (
        "Hi Priya,\n"
        "- Priya Nair: Deliver H100 GPU benchmark worksheet starting 2026-11-04, due by 2026-11-10 (Critical Priority).\n"
        "Thanks,\nMarcus Vance"
    )
    # 1. Exact verbatim span passes guardrail
    quote_ok, verified_ok = verify_evidence_quote(
        "Priya Nair: Deliver H100 GPU benchmark worksheet starting 2026-11-04",
        "Deliver H100 GPU benchmark worksheet",
        "Priya Nair",
        sample_body,
    )
    assert verified_ok is True
    assert "H100 GPU benchmark" in (quote_ok or "")

    # 2. Completely fabricated quote + unrelated task fails guardrail
    quote_bad, verified_bad = verify_evidence_quote(
        "Send marketing brochures to Tokyo office",
        "Marketing brochures",
        "Jane Doe",
        sample_body,
    )
    assert verified_bad is False

    # 3. Quick-Paste headerless raw email endpoint
    res_qp = client.post(
        "/api/emails/quick-paste",
        json={"raw_text": sample_body, "use_gemini": False},
    )
    assert res_qp.status_code == 200
    qp_data = res_qp.json()
    assert qp_data["email"]["sender_name"] == "Marcus Vance"
    assert qp_data["tasks_added"] >= 1
    extracted_task = qp_data["email"]["extraction"]["tasks"][0]
    assert extracted_task["quote_verified"] is True
    assert "H100 GPU benchmark" in extracted_task["evidence_quote"]

    client.post("/api/system/reset")

