from __future__ import annotations
from typing import List, Dict, Any, Optional
from collections import defaultdict
import networkx as nx
from networkx.algorithms import community as nx_comm

from backend.models import EmailMessage, ExtractedTask


class OrganizationalGraphEngine:
    """
    Constructs and analyzes Organizational, Relational, and Temporal Graphs
    from extracted email intelligence using NetworkX.
    """

    def build_graph(
        self,
        emails: List[EmailMessage],
        tasks: List[ExtractedTask],
        cutoff_date: Optional[str] = None,
        include_task_nodes: bool = True,
    ) -> Dict[str, Any]:
        filtered_emails = []
        for em in emails:
            em_date = em.timestamp[:10]
            if cutoff_date and em_date > cutoff_date:
                continue
            filtered_emails.append(em)

        filtered_email_ids = {em.id for em in filtered_emails}
        filtered_tasks = [
            t for t in tasks if (t.source_email_id in filtered_email_ids) or (not cutoff_date or t.start_date <= cutoff_date)
        ]

        person_digraph = nx.DiGraph()
        full_graph = nx.Graph()

        nodes_dict: Dict[str, Dict[str, Any]] = {}
        edges_dict: Dict[tuple, Dict[str, Any]] = {}

        def upsert_node(node_id: str, label: str, node_type: str, **attrs):
            if node_id not in nodes_dict:
                nodes_dict[node_id] = {
                    "id": node_id,
                    "label": label,
                    "type": node_type,
                    "weight": 1,
                    **attrs,
                }
            else:
                nodes_dict[node_id]["weight"] = nodes_dict[node_id].get("weight", 1) + 1
                for k, v in attrs.items():
                    if v and not nodes_dict[node_id].get(k):
                        nodes_dict[node_id][k] = v

        def upsert_edge(source: str, target: str, relation: str, timestamp: str, weight: float = 1.0, **attrs):
            if source == target:
                return
            key = (source, target, relation)
            if key not in edges_dict:
                edges_dict[key] = {
                    "id": f"{source}__{relation}__{target}",
                    "source": source,
                    "target": target,
                    "relation": relation,
                    "weight": weight,
                    "first_seen": timestamp[:10],
                    "last_seen": timestamp[:10],
                    "interactions": 1,
                    **attrs,
                }
            else:
                edges_dict[key]["weight"] = round(edges_dict[key]["weight"] + weight, 2)
                edges_dict[key]["interactions"] += 1
                if timestamp[:10] < edges_dict[key]["first_seen"]:
                    edges_dict[key]["first_seen"] = timestamp[:10]
                if timestamp[:10] > edges_dict[key]["last_seen"]:
                    edges_dict[key]["last_seen"] = timestamp[:10]

        emails_sent_by_person: Dict[str, int] = defaultdict(int)
        emails_received_by_person: Dict[str, int] = defaultdict(int)
        dept_matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for em in filtered_emails:
            sender_id = f"person:{em.sender_name}"
            sender_org = em.sender_dept or "NexusAI"
            upsert_node(
                sender_id,
                em.sender_name,
                "Person",
                email=em.sender_email,
                role=em.sender_role or "Team Member",
                organization=sender_org,
            )
            emails_sent_by_person[sender_id] += 1
            person_digraph.add_node(sender_id, label=em.sender_name, role=em.sender_role, org=sender_org)

            for rec in em.recipients:
                rec_name = rec.get("name") or rec.get("email", "Unknown")
                rec_id = f"person:{rec_name}"
                rec_type = rec.get("type", "to")
                comm_weight = 1.5 if rec_type == "to" else 0.8

                upsert_node(
                    rec_id,
                    rec_name,
                    "Person",
                    email=rec.get("email"),
                )
                emails_received_by_person[rec_id] += 1
                person_digraph.add_node(rec_id, label=rec_name)

                if person_digraph.has_edge(sender_id, rec_id):
                    person_digraph[sender_id][rec_id]["weight"] += comm_weight
                else:
                    person_digraph.add_edge(sender_id, rec_id, weight=comm_weight)

                upsert_edge(
                    sender_id,
                    rec_id,
                    "COMMUNICATES_WITH",
                    em.timestamp,
                    weight=comm_weight,
                    channel=rec_type.upper(),
                    last_subject=em.subject,
                )
                full_graph.add_edge(sender_id, rec_id, weight=comm_weight)

            if em.extraction:
                ext = em.extraction
                for p in ext.entities.people:
                    pid = f"person:{p.name}"
                    clean_org = (p.organization or "NexusAI").replace(" (NexusAI)", "")
                    upsert_node(
                        pid,
                        p.name,
                        "Person",
                        email=p.email,
                        role=p.role,
                        organization=clean_org,
                    )
                    if p.organization:
                        oid = f"org:{clean_org}"
                        upsert_node(oid, clean_org, "Organization", category="Department/Org")
                        upsert_edge(pid, oid, "BELONGS_TO", em.timestamp, weight=1.0)
                        full_graph.add_edge(pid, oid, weight=1.0)

                for org in ext.entities.organizations:
                    clean_org = org.name.replace(" (NexusAI)", "")
                    oid = f"org:{clean_org}"
                    upsert_node(oid, clean_org, "Organization", category=org.category)
                    # Only link sender to external organizations (clients, vendors, cloud partners)
                    if org.category not in ("Internal Department", "Department/Team", "Internal Company"):
                        upsert_edge(sender_id, oid, "PARTNERS_WITH", em.timestamp, weight=1.0)

                for loc in ext.entities.locations:
                    lid = f"loc:{loc.name}"
                    upsert_node(lid, loc.name, "Location", context=loc.context)
                    upsert_edge(sender_id, lid, "OPERATES_IN", em.timestamp, weight=0.9)

                # Connect sender and primary 'TO' recipients to the top 2 primary topics of the email
                for top in ext.topics[:2]:
                    tid = f"topic:{top.name}"
                    upsert_node(tid, top.name, "Topic", category=top.category, confidence=top.confidence)
                    upsert_edge(sender_id, tid, "DISCUSSES_TOPIC", em.timestamp, weight=top.confidence)
                    for rec in em.recipients[:2]:
                        if rec.get("type") == "to":
                            rec_id = f"person:{rec.get('name')}"
                            upsert_edge(rec_id, tid, "DISCUSSES_TOPIC", em.timestamp, weight=round(top.confidence * 0.7, 2))

        tasks_by_owner: Dict[str, int] = defaultdict(int)
        for t in filtered_tasks:
            owner_id = f"person:{t.owner}"
            upsert_node(owner_id, t.owner, "Person", email=t.owner_email)
            tasks_by_owner[owner_id] += 1

            if t.assigner and t.assigner != t.owner:
                assigner_id = f"person:{t.assigner}"
                upsert_node(assigner_id, t.assigner, "Person")
                prio_weight = 2.0 if t.priority == "Critical" else (1.5 if t.priority == "High" else 1.0)
                upsert_edge(
                    assigner_id,
                    owner_id,
                    "ASSIGNED_TASK_TO",
                    t.start_date,
                    weight=prio_weight,
                    task_title=t.title,
                )
                if person_digraph.has_edge(assigner_id, owner_id):
                    person_digraph[assigner_id][owner_id]["weight"] += prio_weight
                else:
                    person_digraph.add_edge(assigner_id, owner_id, weight=prio_weight)

            if include_task_nodes:
                task_node_id = f"task:{t.id}"
                upsert_node(
                    task_node_id,
                    t.title,
                    "Task",
                    priority=t.priority,
                    status=t.status,
                    due_date=t.due_date,
                    owner=t.owner,
                )
                upsert_edge(owner_id, task_node_id, "OWNS_DELIVERABLE", t.start_date, weight=1.2)

        undirected_people = person_digraph.to_undirected()
        degree_centrality = nx.degree_centrality(person_digraph) if len(person_digraph) > 1 else {}
        betweenness_centrality = (
            nx.betweenness_centrality(undirected_people, weight="weight") if len(undirected_people) > 2 else {}
        )
        try:
            pagerank_scores = nx.pagerank(person_digraph, weight="weight") if len(person_digraph) > 1 else {}
        except Exception:
            pagerank_scores = {n: 1.0 / max(1, len(person_digraph)) for n in person_digraph.nodes}

        community_map: Dict[str, int] = {}
        communities_summary: List[Dict[str, Any]] = []
        if len(undirected_people) >= 2:
            try:
                comms = list(nx_comm.greedy_modularity_communities(undirected_people, weight="weight"))
                for idx, comm_set in enumerate(comms, start=1):
                    members = [nodes_dict[nid]["label"] for nid in comm_set if nid in nodes_dict]
                    for nid in comm_set:
                        community_map[nid] = idx
                    communities_summary.append(
                        {
                            "community_id": idx,
                            "name": f"Cluster #{idx}: {', '.join(members[:2])} Working Group",
                            "size": len(members),
                            "members": members,
                        }
                    )
            except Exception:
                pass

        person_analytics: List[Dict[str, Any]] = []
        for nid, ndata in nodes_dict.items():
            if ndata["type"] == "Person":
                deg = round(degree_centrality.get(nid, 0.0), 3)
                btw = round(betweenness_centrality.get(nid, 0.0), 3)
                pr = round(pagerank_scores.get(nid, 0.0), 3)
                comm_id = community_map.get(nid, 1)
                ndata["degree_centrality"] = deg
                ndata["betweenness_centrality"] = btw
                ndata["pagerank"] = pr
                ndata["community_id"] = comm_id
                ndata["emails_sent"] = emails_sent_by_person.get(nid, 0)
                ndata["emails_received"] = emails_received_by_person.get(nid, 0)
                ndata["tasks_owned"] = tasks_by_owner.get(nid, 0)
                person_analytics.append(
                    {
                        "id": nid,
                        "name": ndata["label"],
                        "email": ndata.get("email"),
                        "role": ndata.get("role", "Team Member"),
                        "organization": ndata.get("organization", "NexusAI"),
                        "degree_centrality": deg,
                        "betweenness_centrality": btw,
                        "pagerank": pr,
                        "community_id": comm_id,
                        "emails_sent": ndata["emails_sent"],
                        "emails_received": ndata["emails_received"],
                        "tasks_owned": ndata["tasks_owned"],
                    }
                )

        person_analytics.sort(key=lambda x: (x["pagerank"], x["degree_centrality"]), reverse=True)

        for (src, tgt, rel), edata in edges_dict.items():
            if rel in ("COMMUNICATES_WITH", "ASSIGNED_TASK_TO"):
                s_org = nodes_dict.get(src, {}).get("organization", "Other")
                t_org = nodes_dict.get(tgt, {}).get("organization", "Other")
                if s_org and t_org:
                    dept_matrix[s_org][t_org] += edata["interactions"]

        dept_flows = []
        for s_org, targets in dept_matrix.items():
            for t_org, count in targets.items():
                dept_flows.append({"source_dept": s_org, "target_dept": t_org, "interactions": count})
        dept_flows.sort(key=lambda x: x["interactions"], reverse=True)

        temporal_series = self._build_temporal_series(emails, tasks)

        return {
            "nodes": list(nodes_dict.values()),
            "edges": list(edges_dict.values()),
            "analytics": {
                "total_nodes": len(nodes_dict),
                "total_edges": len(edges_dict),
                "people_count": sum(1 for n in nodes_dict.values() if n["type"] == "Person"),
                "org_count": sum(1 for n in nodes_dict.values() if n["type"] == "Organization"),
                "topic_count": sum(1 for n in nodes_dict.values() if n["type"] == "Topic"),
                "location_count": sum(1 for n in nodes_dict.values() if n["type"] == "Location"),
                "task_node_count": sum(1 for n in nodes_dict.values() if n["type"] == "Task"),
                "top_influencers": person_analytics[:5],
                "top_bridges": sorted(person_analytics, key=lambda x: x["betweenness_centrality"], reverse=True)[:5],
                "person_rankings": person_analytics,
                "communities": communities_summary,
                "department_flows": dept_flows[:10],
            },
            "temporal": temporal_series,
        }

    def _build_temporal_series(
        self, emails: List[EmailMessage], tasks: List[ExtractedTask]
    ) -> Dict[str, Any]:
        dates_set = set()
        emails_by_date: Dict[str, int] = defaultdict(int)
        tasks_started_by_date: Dict[str, int] = defaultdict(int)
        tasks_due_by_date: Dict[str, int] = defaultdict(int)
        all_milestones = []

        for em in emails:
            d = em.timestamp[:10]
            dates_set.add(d)
            emails_by_date[d] += 1
            if em.extraction:
                for ev in em.extraction.timeline_events:
                    all_milestones.append(
                        {
                            "date": ev.date,
                            "label": ev.label,
                            "event_type": ev.event_type,
                            "related_entities": ev.related_entities,
                            "source_email_id": ev.source_email_id,
                        }
                    )

        for t in tasks:
            dates_set.add(t.start_date)
            dates_set.add(t.due_date)
            tasks_started_by_date[t.start_date] += 1
            tasks_due_by_date[t.due_date] += 1

        sorted_dates = sorted(dates_set)
        daily_activity = []
        cum_emails = 0
        cum_tasks = 0
        for d in sorted_dates:
            cum_emails += emails_by_date.get(d, 0)
            cum_tasks += tasks_started_by_date.get(d, 0)
            daily_activity.append(
                {
                    "date": d,
                    "emails_count": emails_by_date.get(d, 0),
                    "tasks_started": tasks_started_by_date.get(d, 0),
                    "tasks_due": tasks_due_by_date.get(d, 0),
                    "cumulative_emails": cum_emails,
                    "cumulative_tasks": cum_tasks,
                }
            )

        unique_milestones = []
        seen_m = set()
        for m in sorted(all_milestones, key=lambda x: x["date"]):
            k = (m["date"], m["label"])
            if k not in seen_m:
                unique_milestones.append(m)
                seen_m.add(k)

        email_dates = sorted({em.timestamp[:10] for em in emails})
        return {
            "email_dates": email_dates,
            "min_date": sorted_dates[0] if sorted_dates else "2026-10-20",
            "max_date": sorted_dates[-1] if sorted_dates else "2026-11-18",
            "daily_series": daily_activity,
            "milestones": unique_milestones,
        }

