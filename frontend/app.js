// Global Frontend State
const appState = {
  overview: null,
  emails: [],
  selectedEmailId: null,
  graphData: null,
  tasksData: null,
  activeTab: "emails",
  activeTaskView: "table",
  visibleGraphLayers: {
    Person: true,
    Organization: true,
    Topic: true,
    Location: false,
    Task: false,
  },
  temporalDates: [],
  selectedNode: null,
};

const NODE_COLORS = {
  Person: "#6366f1",
  Organization: "#10b981",
  Topic: "#f59e0b",
  Location: "#06b6d4",
  Task: "#f43f5e",
};

window.addEventListener("DOMContentLoaded", async () => {
  initGraphCanvas();
  await refreshAllData();
});

async function refreshAllData() {
  const [ovRes, emRes, grRes, tkRes] = await Promise.all([
    fetch("/api/overview").then((r) => r.json()),
    fetch("/api/emails").then((r) => r.json()),
    fetch("/api/graph").then((r) => r.json()),
    fetch("/api/tasks").then((r) => r.json()),
  ]);

  appState.overview = ovRes;
  appState.emails = emRes.emails || [];
  appState.graphData = grRes;
  appState.tasksData = tkRes;

  if (!appState.selectedEmailId && appState.emails.length > 0) {
    appState.selectedEmailId = appState.emails[0].id;
  }

  appState.temporalDates = (grRes.temporal && grRes.temporal.email_dates) || [];
  const slider = document.getElementById("temporal-slider");
  if (slider && appState.temporalDates.length > 0) {
    slider.max = appState.temporalDates.length - 1;
    slider.value = appState.temporalDates.length - 1;
    document.getElementById("temporal-date-label").textContent = "All Dates (Through " + appState.temporalDates[appState.temporalDates.length - 1] + ")";
  }

  renderKpiRibbon();
  renderEmailList();
  renderSelectedEmailInspector();
  populateOwnerFilterDropdown();
  renderTasksHub();
  renderGraphSidebarAndTimeline();
  rebuildSimulationNodes();
}

function switchTab(tabName) {
  appState.activeTab = tabName;
  document.querySelectorAll(".nav-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${tabName}`);
  });
  if (tabName === "graph") {
    requestAnimationFrame(() => {
      resizeGraphCanvas();
      resetGraphCamera();
      drawGraphCanvas();
    });
  }
}

function renderKpiRibbon() {
  const ov = appState.overview;
  if (!ov) return;
  const m = ov.metrics;

  document.getElementById("badge-emails").textContent = m.total_emails;
  document.getElementById("badge-nodes").textContent = m.graph_nodes;
  document.getElementById("badge-tasks").textContent = m.total_tasks;

  document.getElementById("kpi-emails").textContent = m.total_emails;
  document.getElementById("kpi-threads").textContent = `Across ${m.total_threads} threads`;

  const totalEntities = m.total_people + m.total_organizations + m.total_locations;
  document.getElementById("kpi-entities").textContent = totalEntities;
  document.getElementById("kpi-entities-breakdown").textContent = `${m.total_people} People • ${m.total_organizations} Orgs • ${m.total_locations} Locations`;

  document.getElementById("kpi-topics").textContent = m.total_topics;
  document.getElementById("kpi-tasks").textContent = m.total_tasks;
  document.getElementById("kpi-critical").textContent = `${m.critical_tasks} Critical priority deliverables`;
  document.getElementById("kpi-graph").textContent = `${m.graph_nodes} Nodes`;
  document.getElementById("kpi-edges").textContent = `${m.graph_edges} relational & temporal edges`;
  document.getElementById("kpi-conflicts").textContent = m.schedule_conflicts;

  const dot = document.getElementById("gemini-dot");
  const label = document.getElementById("gemini-status-label");
  if (dot && label) {
    if (ov.gemini_configured) {
      dot.style.background = "#10b981";
      label.textContent = "Engine: Gemini 3.8 Flash (.env)";
    } else {
      dot.style.background = "#6366f1";
      label.textContent = "Engine: Local Hybrid NLP";
    }
  }
}

function renderEmailList() {
  const container = document.getElementById("email-list-container");
  const query = (document.getElementById("email-search").value || "").toLowerCase().trim();

  const filtered = appState.emails.filter((em) => {
    if (!query) return true;
    const hay = `${em.subject} ${em.sender_name} ${em.sender_email} ${em.body}`.toLowerCase();
    return hay.includes(query);
  });

  container.innerHTML = filtered
    .map((em) => {
      const ext = em.extraction || {};
      const taskCount = (ext.tasks || []).length;
      const topTopic = (ext.topics && ext.topics[0] && ext.topics[0].category) || "General";
      const urgency = (ext.summary && ext.summary.urgency_score) || 5;
      const urgBadge =
        urgency >= 8
          ? `<span class="badge badge-rose">Urgency ${urgency}/10</span>`
          : `<span class="badge badge-indigo">${topTopic}</span>`;

      return `
        <div class="email-item ${em.id === appState.selectedEmailId ? "active" : ""}" onclick="selectEmail('${em.id}')">
          <div class="email-item-top">
            <span class="email-sender">${escapeHtml(em.sender_name)}</span>
            <span class="email-date">${em.timestamp.slice(0, 10)}</span>
          </div>
          <div class="email-subject">${escapeHtml(em.subject)}</div>
          <div class="email-tags">
            ${urgBadge}
            <span class="badge badge-emerald">${taskCount} Task${taskCount === 1 ? "" : "s"}</span>
            <span class="badge badge-cyan">${(ext.entities?.people || []).length} People</span>
          </div>
        </div>
      `;
    })
    .join("");
}

function selectEmail(emailId) {
  appState.selectedEmailId = emailId;
  renderEmailList();
  renderSelectedEmailInspector();
}

async function reExtractCurrentEmail(emailId) {
  await fetch(`/api/emails/${encodeURIComponent(emailId)}/re-extract?use_gemini=true`, {
    method: "POST",
  });
  await refreshAllData();
}

function renderSelectedEmailInspector() {
  const container = document.getElementById("email-inspector");
  const em = appState.emails.find((e) => e.id === appState.selectedEmailId);
  if (!em || !em.extraction) {
    container.innerHTML = `<div class="empty-state">Select an email to inspect AI-extracted intelligence.</div>`;
    return;
  }

  const ext = em.extraction;
  const recStr = (em.recipients || [])
    .map((r) => `${escapeHtml(r.name)} &lt;${escapeHtml(r.email)}&gt; (${r.type.toUpperCase()})`)
    .join(", ");

  const topicsHtml = (ext.topics || [])
    .map(
      (t) => `
      <div style="margin-bottom:8px;">
        <div style="display:flex;justify-content:space-between;font-size:12.5px;font-weight:600;">
          <span>${escapeHtml(t.name)} <span class="badge badge-indigo">${escapeHtml(t.category)}</span></span>
          <span>${Math.round(t.confidence * 100)}%</span>
        </div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">Keywords: ${(t.keywords || []).join(", ")}</div>
      </div>`
    )
    .join("");

  const peopleHtml = (ext.entities.people || [])
    .map(
      (p) =>
        `<span class="entity-chip"><strong>${escapeHtml(p.name)}</strong> <small>${escapeHtml(p.role || "")} • ${escapeHtml(p.organization || "")}</small></span>`
    )
    .join("");

  const orgsHtml = (ext.entities.organizations || [])
    .map(
      (o) =>
        `<span class="entity-chip"><strong>${escapeHtml(o.name)}</strong> <small>${escapeHtml(o.category)}</small></span>`
    )
    .join("");

  const locsHtml = (ext.entities.locations || [])
    .map(
      (l) =>
        `<span class="entity-chip"><strong>${escapeHtml(l.name)}</strong> <small>${escapeHtml(l.context || "")}</small></span>`
    )
    .join("");

  const tasksHtml = (ext.tasks || [])
    .map((t) => {
      const pBadge =
        t.priority === "Critical"
          ? "badge-rose"
          : t.priority === "High"
          ? "badge-amber"
          : "badge-indigo";
      const quoteHtml = t.evidence_quote
        ? `<div class="evidence-quote-box ${t.quote_verified ? "" : "unverified"}">
            <span class="quote-pill ${t.quote_verified ? "" : "unverified"}">${t.quote_verified ? "&#10003; Grounded Quote" : "&#9888; Unverified Span"}</span>
            &ldquo;${escapeHtml(t.evidence_quote)}&rdquo;
          </div>`
        : "";
      return `
        <div class="task-mini-card">
          <div style="flex:1;min-width:0;">
            <div style="font-weight:700;font-size:13px;color:#fff;">
              <code>${t.id}</code> — ${escapeHtml(t.deliverable)}
            </div>
            <div style="font-size:12px;color:var(--text-secondary);margin-top:3px;">
              <strong>Owner:</strong> ${escapeHtml(t.owner)} &bull;
              <strong>Start:</strong> ${t.start_date} &bull;
              <strong>Due:</strong> ${t.due_date}
            </div>
            ${quoteHtml}
          </div>
          <div style="display:flex;gap:6px;align-items:center;flex-shrink:0;">
            <span class="badge ${pBadge}">${t.priority}</span>
            <span class="badge badge-emerald">${t.status}</span>
          </div>
        </div>
      `;
    })
    .join("");

  const timelineHtml = (ext.timeline_events || [])
    .map(
      (ev) => `
      <div style="display:flex;gap:10px;align-items:center;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:12.5px;">
        <span class="badge badge-cyan">${ev.date}</span>
        <span class="badge badge-indigo">${ev.event_type}</span>
        <span>${escapeHtml(ev.label)}</span>
      </div>`
    )
    .join("");

  container.innerHTML = `
    <div class="inspector-header">
      <div class="inspector-title-row">
        <h2>${escapeHtml(em.subject)}</h2>
        <div style="display:flex;gap:8px;align-items:center;">
          <span class="badge badge-amber">Sentiment: ${ext.summary.sentiment} (Urgency ${ext.summary.urgency_score}/10)</span>
          <span class="badge badge-indigo">Engine: ${escapeHtml(ext.extraction_engine)}</span>
          <button class="btn btn-xs btn-primary" onclick="reExtractCurrentEmail('${em.id}')">&#10024; Re-Extract with Gemini</button>
        </div>
      </div>
      <div class="meta-grid">
        <div><strong>From:</strong> ${escapeHtml(em.sender_name)} &lt;${escapeHtml(em.sender_email)}&gt;</div>
        <div><strong>Timestamp:</strong> ${em.timestamp}</div>
        <div><strong>Recipients:</strong> ${recStr}</div>
      </div>
    </div>

    <div class="extraction-grid">
      <!-- Executive Summary & Key Points -->
      <div class="ext-box">
        <h4>
          <span>1d. AI Executive Summary &amp; Decisions</span>
          <span class="badge badge-emerald">Synthesized</span>
        </h4>
        <p class="summary-text">${escapeHtml(ext.summary.executive_summary)}</p>
        <div class="entity-group-label">Key Extracted Points:</div>
        <ul class="bullet-list">
          ${(ext.summary.key_points || []).map((kp) => `<li>${escapeHtml(kp)}</li>`).join("")}
        </ul>
      </div>

      <!-- Topics & Timeline -->
      <div class="ext-box">
        <h4>
          <span>1a. Extracted Topics &amp; Domain Taxonomy</span>
          <span class="badge badge-indigo">${(ext.topics || []).length} Topics</span>
        </h4>
        ${topicsHtml}
        <h4 style="margin-top:14px;">
          <span>Chronological Timeline Milestones</span>
        </h4>
        ${timelineHtml || '<div class="muted-sm">No explicit timeline milestones.</div>'}
      </div>
    </div>

    <!-- Entities Box -->
    <div class="ext-box">
      <h4>
        <span>1b. Extracted Entities (People, Organizations, Locations)</span>
        <span class="badge badge-cyan">Disambiguated</span>
      </h4>
      <div class="entity-group">
        <div class="entity-group-label">People (${(ext.entities.people || []).length})</div>
        <div class="chip-row">${peopleHtml}</div>
      </div>
      <div class="entity-group">
        <div class="entity-group-label">Organizations &amp; Teams (${(ext.entities.organizations || []).length})</div>
        <div class="chip-row">${orgsHtml}</div>
      </div>
      <div class="entity-group" style="margin-bottom:0;">
        <div class="entity-group-label">Locations &amp; Regions (${(ext.entities.locations || []).length})</div>
        <div class="chip-row">${locsHtml || '<span class="muted-sm">None mentioned</span>'}</div>
      </div>
    </div>

    <!-- Extracted Tasks & Associated Timelines -->
    <div class="ext-box">
      <h4>
        <span>1c. Extracted Tasks, Deliverables &amp; Associated Timelines</span>
        <button class="btn btn-xs btn-primary" onclick="switchTab('tasks')">Open in Productivity Schedule Hub &rarr;</button>
      </h4>
      ${tasksHtml || '<div class="muted-sm">No actionable tasks extracted from this email.</div>'}
    </div>

    <!-- Raw Email Body -->
    <div class="ext-box">
      <h4><span>Source Unstructured Email Body</span></h4>
      <div class="raw-email-box">${escapeHtml(em.body)}</div>
    </div>
  `;
}

// TAB 2: Interactive Force-Directed Organizational, Relational & Temporal Graph
let canvas, ctx;
let canvasWidth = 960;
let canvasHeight = 540;
let simNodes = [];
let simEdges = [];
let simAlpha = 1.0;
let camera = { x: 480, y: 270, zoom: 0.88 };
let dragNode = null;
let isPanning = false;
let panStart = { x: 0, y: 0 };
let hoveredNode = null;

function initGraphCanvas() {
  canvas = document.getElementById("network-canvas");
  if (!canvas) return;
  ctx = canvas.getContext("2d");
  resizeGraphCanvas();
  window.addEventListener("resize", () => {
    resizeGraphCanvas();
    if (appState.activeTab === "graph") {
      resetGraphCamera();
      drawGraphCanvas();
    }
  });

  canvas.addEventListener("mousedown", onCanvasMouseDown);
  canvas.addEventListener("mousemove", onCanvasMouseMove);
  window.addEventListener("mouseup", onCanvasMouseUp);
  canvas.addEventListener("wheel", onCanvasWheel, { passive: false });

  requestAnimationFrame(stepGraphPhysics);
}

function resizeGraphCanvas() {
  if (!canvas || !canvas.parentElement) return;
  const w = canvas.parentElement.clientWidth;
  const h = canvas.parentElement.clientHeight;
  if (w > 50 && h > 50) {
    canvasWidth = w;
    canvasHeight = h;
  }
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(canvasWidth * dpr);
  canvas.height = Math.round(canvasHeight * dpr);
  canvas.style.width = canvasWidth + "px";
  canvas.style.height = canvasHeight + "px";
}

function resetGraphCamera() {
  if (!canvas) return;
  if (!simNodes || simNodes.length === 0) {
    camera = { x: canvasWidth / 2, y: canvasHeight / 2, zoom: 0.88 };
    return;
  }
  let minX = Infinity,
    maxX = -Infinity,
    minY = Infinity,
    maxY = -Infinity;
  for (const n of simNodes) {
    const pad = n.radius + 45;
    if (n.x - pad < minX) minX = n.x - pad;
    if (n.x + pad > maxX) maxX = n.x + pad;
    if (n.y - pad < minY) minY = n.y - pad;
    if (n.y + pad > maxY) maxY = n.y + pad;
  }
  const graphW = Math.max(300, maxX - minX);
  const graphH = Math.max(240, maxY - minY);
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;

  const zoomX = (canvasWidth * 0.86) / graphW;
  const zoomY = (canvasHeight * 0.84) / graphH;
  const fitZoom = Math.max(0.45, Math.min(1.25, Math.min(zoomX, zoomY)));

  camera = {
    x: canvasWidth / 2 - centerX * fitZoom,
    y: canvasHeight / 2 - centerY * fitZoom,
    zoom: fitZoom,
  };
}

function reheatGraphSimulation() {
  rebuildSimulationNodes(true);
  resetGraphCamera();
  drawGraphCanvas();
}

function rebuildSimulationNodes(forceResetPositions = false) {
  if (!appState.graphData) return;
  const rawNodes = appState.graphData.nodes || [];
  const rawEdges = appState.graphData.edges || [];

  const existingPos = {};
  if (!forceResetPositions) {
    simNodes.forEach((n) => {
      existingPos[n.id] = { x: n.x, y: n.y };
    });
  }

  const visibleRaw = rawNodes.filter((n) => appState.visibleGraphLayers[n.type] !== false);
  const visibleIds = new Set(visibleRaw.map((n) => n.id));

  const byType = { Person: [], Organization: [], Topic: [], Location: [], Task: [] };
  visibleRaw.forEach((n) => {
    (byType[n.type] || byType.Topic).push(n);
  });

  const ringConfig = {
    Person: { radius: 115, angleOffset: 0 },
    Organization: { radius: 220, angleOffset: Math.PI / 10 },
    Topic: { radius: 295, angleOffset: Math.PI / 5 },
    Location: { radius: 340, angleOffset: Math.PI / 3 },
    Task: { radius: 380, angleOffset: Math.PI / 7 },
  };

  simNodes = [];
  Object.entries(byType).forEach(([type, list]) => {
    const cfg = ringConfig[type] || { radius: 320, angleOffset: 0 };
    list.forEach((n, idx) => {
      const angle = cfg.angleOffset + (idx / Math.max(1, list.length)) * Math.PI * 2;
      const prev = existingPos[n.id];
      const nodeRadius =
        n.type === "Person"
          ? 16 + Math.min(10, (n.pagerank || 0.08) * 55)
          : n.type === "Organization"
          ? 14
          : n.type === "Topic"
          ? 12
          : 10;

      simNodes.push({
        ...n,
        x: prev ? prev.x : Math.cos(angle) * cfg.radius,
        y: prev ? prev.y : Math.sin(angle) * cfg.radius * 0.82,
        vx: 0,
        vy: 0,
        radius: nodeRadius,
      });
    });
  });

  const nodeMap = {};
  simNodes.forEach((n) => (nodeMap[n.id] = n));

  simEdges = rawEdges
    .filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target))
    .map((e) => ({
      ...e,
      sourceNode: nodeMap[e.source],
      targetNode: nodeMap[e.target],
    }));

  simAlpha = 1.0;
  for (let iter = 0; iter < 110; iter++) {
    runPhysicsTick(0.65);
  }
  simAlpha = 0.25;
  resetGraphCamera();
}

function runPhysicsTick(alphaScale = 1.0) {
  const N = simNodes.length;
  if (N === 0) return;

  for (let i = 0; i < N; i++) {
    for (let j = i + 1; j < N; j++) {
      const a = simNodes[i];
      const b = simNodes[j];
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      if (Math.abs(dx) < 0.01 && Math.abs(dy) < 0.01) {
        dx = (i % 2 === 0 ? 1 : -1) * 2;
        dy = (j % 2 === 0 ? 1 : -1) * 2;
      }
      const distSq = dx * dx + dy * dy + 1;
      const dist = Math.sqrt(distSq);

      const repulse = (11000 / distSq) * alphaScale;
      const fx = (dx / dist) * repulse;
      const fy = (dy / dist) * repulse;

      if (a !== dragNode) {
        a.vx -= fx;
        a.vy -= fy;
      }
      if (b !== dragNode) {
        b.vx += fx;
        b.vy += fy;
      }

      const minDist = a.radius + b.radius + 38;
      if (dist < minDist) {
        const push = ((minDist - dist) / dist) * 0.38;
        const px = dx * push;
        const py = dy * push;
        if (a !== dragNode) {
          a.x -= px;
          a.y -= py;
        }
        if (b !== dragNode) {
          b.x += px;
          b.y += py;
        }
      }
    }
  }

    for (const e of simEdges) {
      const a = e.sourceNode;
      const b = e.targetNode;
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const targetLen =
        e.relation === "COMMUNICATES_WITH"
          ? 125
          : e.relation === "BELONGS_TO"
          ? 110
          : e.relation === "PARTNERS_WITH"
          ? 145
          : 160;
      const force = (dist - targetLen) * 0.032 * alphaScale;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      if (a !== dragNode) {
        a.vx += fx;
        a.vy += fy;
      }
      if (b !== dragNode) {
        b.vx -= fx;
        b.vy -= fy;
      }
    }

  for (const n of simNodes) {
    if (n === dragNode) continue;
    const gravity = n.type === "Person" ? 0.012 : 0.007;
    n.vx -= n.x * gravity * alphaScale;
    n.vy -= n.y * (gravity * 1.3) * alphaScale;
    n.vx *= 0.76;
    n.vy *= 0.76;

    const speed = Math.sqrt(n.vx * n.vx + n.vy * n.vy);
    if (speed > 14) {
      n.vx = (n.vx / speed) * 14;
      n.vy = (n.vy / speed) * 14;
    }

    n.x += n.vx;
    n.y += n.vy;
  }
}

function stepGraphPhysics() {
  if (appState.activeTab === "graph" && canvas && ctx) {
    if (simAlpha > 0.008 || dragNode) {
      runPhysicsTick(dragNode ? 0.5 : simAlpha);
      if (!dragNode) {
        simAlpha *= 0.95;
      }
    }
    drawGraphCanvas();
  }
  requestAnimationFrame(stepGraphPhysics);
}

function getInitials(label) {
  const parts = String(label || "")
    .replace(/[^a-zA-Z0-9 ]/g, "")
    .trim()
    .split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return (parts[0] || "?").slice(0, 2).toUpperCase();
}

function drawGraphCanvas() {
  if (!canvas || !ctx) return;
  const dpr = window.devicePixelRatio || 1;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, canvasWidth, canvasHeight);

  ctx.save();
  ctx.translate(camera.x, camera.y);
  ctx.scale(camera.zoom, camera.zoom);

  ctx.save();
  ctx.strokeStyle = "rgba(148, 163, 184, 0.06)";
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 6]);
  [160, 310, 440].forEach((r) => {
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.stroke();
  });
  ctx.restore();

  const activeNode = hoveredNode || appState.selectedNode;
  const activeId = activeNode ? activeNode.id : null;
  const connectedIds = new Set();
  if (activeId) {
    connectedIds.add(activeId);
    simEdges.forEach((e) => {
      if (e.source === activeId) connectedIds.add(e.target);
      if (e.target === activeId) connectedIds.add(e.source);
    });
  }

  for (const e of simEdges) {
    const a = e.sourceNode;
    const b = e.targetNode;
    if (!a || !b) continue;

    const isHighlighted = !activeId || e.source === activeId || e.target === activeId;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;

    ctx.save();
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);

    const baseWidth = Math.min(3.2, 1.0 + (e.weight || 1) * 0.45);
    ctx.lineWidth = isHighlighted && activeId ? baseWidth + 0.6 : baseWidth;

    if (e.relation === "ASSIGNED_TASK_TO") {
      ctx.strokeStyle = isHighlighted ? "rgba(244, 63, 94, 0.78)" : "rgba(244, 63, 94, 0.08)";
    } else if (e.relation === "COMMUNICATES_WITH") {
      ctx.strokeStyle = isHighlighted ? "rgba(99, 102, 241, 0.72)" : "rgba(99, 102, 241, 0.08)";
    } else if (e.relation === "BELONGS_TO") {
      ctx.strokeStyle = isHighlighted ? "rgba(16, 185, 129, 0.55)" : "rgba(16, 185, 129, 0.07)";
    } else if (e.relation === "PARTNERS_WITH") {
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = isHighlighted ? "rgba(6, 182, 212, 0.60)" : "rgba(6, 182, 212, 0.07)";
    } else {
      ctx.strokeStyle = isHighlighted ? "rgba(245, 158, 11, 0.42)" : "rgba(148, 163, 184, 0.06)";
    }
    ctx.stroke();
    ctx.setLineDash([]);

    if (
      isHighlighted &&
      dist > a.radius + b.radius + 14 &&
      (e.relation === "COMMUNICATES_WITH" || e.relation === "ASSIGNED_TASK_TO")
    ) {
      const ux = dx / dist;
      const uy = dy / dist;
      const tipX = b.x - ux * (b.radius + 3);
      const tipY = b.y - uy * (b.radius + 3);
      const arrowLen = 7;
      const arrowWidth = 3.6;

      ctx.beginPath();
      ctx.moveTo(tipX, tipY);
      ctx.lineTo(
        tipX - ux * arrowLen - uy * arrowWidth,
        tipY - uy * arrowLen + ux * arrowWidth
      );
      ctx.lineTo(
        tipX - ux * arrowLen + uy * arrowWidth,
        tipY - uy * arrowLen - ux * arrowWidth
      );
      ctx.closePath();
      ctx.fillStyle =
        e.relation === "ASSIGNED_TASK_TO"
          ? "rgba(244, 63, 94, 0.85)"
          : "rgba(129, 140, 248, 0.85)";
      ctx.fill();
    }

    if (activeId && (e.source === activeId || e.target === activeId) && dist > 90) {
      const mx = (a.x + b.x) / 2;
      const my = (a.y + b.y) / 2;
      const relLabel =
        e.relation === "COMMUNICATES_WITH"
          ? `${e.weight || 1}x email`
          : e.relation.replace(/_/g, " ").toLowerCase();
      ctx.font = "500 9px Inter, -apple-system, sans-serif";
      const tw = ctx.measureText(relLabel).width + 8;
      ctx.fillStyle = "rgba(15, 23, 42, 0.88)";
      ctx.fillRect(mx - tw / 2, my - 7, tw, 13);
      ctx.fillStyle = "#cbd5e1";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(relLabel, mx, my);
    }
    ctx.restore();
  }

  const sortedNodes = [...simNodes].sort((a, b) =>
    a.type === "Person" && b.type !== "Person" ? 1 : b.type === "Person" && a.type !== "Person" ? -1 : 0
  );

  for (const n of sortedNodes) {
    const dim = activeId && !connectedIds.has(n.id);
    const isSelected =
      (appState.selectedNode && appState.selectedNode.id === n.id) || hoveredNode === n;
    const baseColor = NODE_COLORS[n.type] || "#6366f1";

    ctx.save();
    ctx.globalAlpha = dim ? 0.2 : 1.0;

    if (n.type === "Person" || isSelected) {
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.radius + (isSelected ? 6 : 4), 0, Math.PI * 2);
      ctx.fillStyle = isSelected
        ? "rgba(255, 255, 255, 0.22)"
        : "rgba(99, 102, 241, 0.20)";
      ctx.fill();
    }

    ctx.beginPath();
    ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
    ctx.fillStyle = baseColor;
    ctx.fill();

    ctx.lineWidth = isSelected ? 2.8 : 1.8;
    ctx.strokeStyle = isSelected ? "#ffffff" : "#0f172a";
    ctx.stroke();

    ctx.fillStyle = "#ffffff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    if (n.type === "Person") {
      ctx.font = "700 10px Inter, -apple-system, sans-serif";
      ctx.fillText(getInitials(n.label), n.x, n.y + 0.5);
    } else if (n.type === "Organization") {
      ctx.font = "700 8.5px Inter, -apple-system, sans-serif";
      ctx.fillText("ORG", n.x, n.y + 0.5);
    }

    const maxLen = n.type === "Person" ? 24 : 22;
    const shortLabel =
      n.label.length > maxLen ? n.label.slice(0, maxLen - 1) + "..." : n.label;
    ctx.font =
      n.type === "Person"
        ? "600 11px Inter, -apple-system, sans-serif"
        : "500 10px Inter, -apple-system, sans-serif";

    const textWidth = ctx.measureText(shortLabel).width;
    const pillW = textWidth + 10;
    const pillH = 16;
    const pillX = n.x - pillW / 2;
    const pillY = n.y + n.radius + 5;

    ctx.fillStyle = isSelected
      ? "rgba(30, 41, 59, 0.96)"
      : "rgba(15, 23, 42, 0.86)";
    ctx.beginPath();
    if (ctx.roundRect) {
      ctx.roundRect(pillX, pillY, pillW, pillH, 4);
    } else {
      ctx.rect(pillX, pillY, pillW, pillH);
    }
    ctx.fill();

    if (isSelected) {
      ctx.lineWidth = 1;
      ctx.strokeStyle = baseColor;
      ctx.stroke();
    }

    ctx.fillStyle = n.type === "Person" ? "#f8fafc" : "#e2e8f0";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(shortLabel, n.x, pillY + pillH / 2 + 0.5);

    ctx.restore();
  }

  ctx.restore();
}

function screenToWorld(sx, sy) {
  return {
    x: (sx - camera.x) / camera.zoom,
    y: (sy - camera.y) / camera.zoom,
  };
}

function findNodeAt(wx, wy) {
  for (let i = simNodes.length - 1; i >= 0; i--) {
    const n = simNodes[i];
    const dx = wx - n.x;
    const dy = wy - n.y;
    if (dx * dx + dy * dy <= (n.radius + 4) * (n.radius + 4)) {
      return n;
    }
  }
  return null;
}

function onCanvasMouseDown(e) {
  const rect = canvas.getBoundingClientRect();
  const sx = e.clientX - rect.left;
  const sy = e.clientY - rect.top;
  const { x, y } = screenToWorld(sx, sy);
  const hit = findNodeAt(x, y);
  if (hit) {
    dragNode = hit;
    selectGraphNode(hit);
  } else {
    isPanning = true;
    panStart = { x: e.clientX - camera.x, y: e.clientY - camera.y };
  }
}

function onCanvasMouseMove(e) {
  const rect = canvas.getBoundingClientRect();
  const sx = e.clientX - rect.left;
  const sy = e.clientY - rect.top;
  const { x, y } = screenToWorld(sx, sy);

  if (dragNode) {
    dragNode.x = x;
    dragNode.y = y;
    return;
  }
  if (isPanning) {
    camera.x = e.clientX - panStart.x;
    camera.y = e.clientY - panStart.y;
    return;
  }

  const hit = findNodeAt(x, y);
  hoveredNode = hit;
  const tooltip = document.getElementById("graph-tooltip");
  if (hit) {
    tooltip.style.display = "block";
    tooltip.style.left = `${sx + 14}px`;
    tooltip.style.top = `${sy + 14}px`;
    let details = `<strong>${escapeHtml(hit.label)}</strong> <span class="badge badge-indigo">${hit.type}</span>`;
    if (hit.type === "Person") {
      details += `<div style="margin-top:4px;color:#cbd5e1;">${escapeHtml(hit.role || "")} • ${escapeHtml(hit.organization || "")}</div>`;
      details += `<div style="margin-top:3px;font-size:11px;color:#94a3b8;">PageRank: ${hit.pagerank} | Betweenness: ${hit.betweenness_centrality} | Tasks: ${hit.tasks_owned}</div>`;
    } else if (hit.type === "Task") {
      details += `<div style="margin-top:4px;color:#cbd5e1;">Owner: ${escapeHtml(hit.owner || "")} • Due: ${hit.due_date || ""} (${hit.priority})</div>`;
    }
    tooltip.innerHTML = details;
  } else {
    tooltip.style.display = "none";
  }
}

function onCanvasMouseUp() {
  dragNode = null;
  isPanning = false;
}

function onCanvasWheel(e) {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.1 : 0.9;
  camera.zoom = Math.max(0.35, Math.min(2.6, camera.zoom * factor));
}

function toggleGraphLayer(layerType, checked) {
  appState.visibleGraphLayers[layerType] = checked;
  rebuildSimulationNodes();
}

async function onTemporalSliderChange(indexVal) {
  const idx = parseInt(indexVal, 10);
  const cutoffDate = appState.temporalDates[idx];
  const label = document.getElementById("temporal-date-label");
  if (!cutoffDate) return;

  if (idx >= appState.temporalDates.length - 1) {
    label.textContent = `All Dates (Through ${cutoffDate})`;
    const res = await fetch("/api/graph").then((r) => r.json());
    appState.graphData = res;
  } else {
    label.textContent = `Snapshot <= ${cutoffDate}`;
    const res = await fetch(`/api/graph?cutoff_date=${encodeURIComponent(cutoffDate)}`).then((r) => r.json());
    appState.graphData = res;
  }
  renderGraphSidebarAndTimeline();
  rebuildSimulationNodes();
}

function selectGraphNode(node) {
  appState.selectedNode = node;
  const card = document.getElementById("selected-node-card");
  const content = document.getElementById("selected-node-content");
  card.style.display = "block";

  const neighbors = [];
  (appState.graphData.edges || []).forEach((e) => {
    if (e.source === node.id) neighbors.push({ rel: e.relation, target: e.target });
    if (e.target === node.id) neighbors.push({ rel: e.relation, target: e.source });
  });

  content.innerHTML = `
    <div style="font-weight:700;font-size:14px;margin-bottom:4px;">${escapeHtml(node.label)} <span class="badge badge-indigo">${node.type}</span></div>
    ${node.role ? `<div class="muted-sm">${escapeHtml(node.role)} (${escapeHtml(node.organization || "")})</div>` : ""}
    ${node.pagerank !== undefined ? `<div style="margin-top:6px;font-size:12px;">PageRank: <code>${node.pagerank}</code> &bull; Betweenness: <code>${node.betweenness_centrality}</code></div>` : ""}
    <div style="margin-top:8px;font-size:11.5px;color:var(--text-secondary);">Connected Relations (${neighbors.length}):</div>
    <div style="max-height:130px;overflow-y:auto;margin-top:4px;font-size:11.5px;">
      ${neighbors.slice(0, 12).map((nb) => `<div>&bull; <code>${nb.rel}</code> &rarr; ${escapeHtml(nb.target.split(":")[1] || nb.target)}</div>`).join("")}
    </div>
  `;
}

function clearSelectedNode() {
  appState.selectedNode = null;
  document.getElementById("selected-node-card").style.display = "none";
}

function focusPersonInGraph(personId) {
  const found = simNodes.find((n) => n.id === personId);
  if (found) {
    selectGraphNode(found);
  }
}

function renderGraphSidebarAndTimeline() {
  if (!appState.graphData) return;
  const an = appState.graphData.analytics;

  document.getElementById("influencers-list").innerHTML = (an.top_influencers || [])
    .map(
      (p) => `
      <div class="metric-row" onclick="focusPersonInGraph('${p.id}')">
        <div>
          <strong>${escapeHtml(p.name)}</strong>
          <div class="muted-sm">${escapeHtml(p.role)}</div>
        </div>
        <span class="badge badge-indigo">PR ${p.pagerank}</span>
      </div>`
    )
    .join("");

  document.getElementById("bridges-list").innerHTML = (an.top_bridges || [])
    .map(
      (p) => `
      <div class="metric-row" onclick="focusPersonInGraph('${p.id}')">
        <div>
          <strong>${escapeHtml(p.name)}</strong>
          <div class="muted-sm">${escapeHtml(p.organization)}</div>
        </div>
        <span class="badge badge-cyan">Btw ${p.betweenness_centrality}</span>
      </div>`
    )
    .join("");

  document.getElementById("communities-list").innerHTML = (an.communities || [])
    .map(
      (c) => `
      <div class="comm-card">
        <div style="font-weight:700;color:#a5b4fc;margin-bottom:3px;">${escapeHtml(c.name)}</div>
        <div class="muted-sm">Members: ${(c.members || []).map(escapeHtml).join(", ")}</div>
      </div>`
    )
    .join("");

  const milestones = (appState.graphData.temporal && appState.graphData.temporal.milestones) || [];
  document.getElementById("milestone-track").innerHTML = milestones
    .slice(0, 12)
    .map(
      (m) => `
      <div class="milestone-card">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
          <span class="badge badge-cyan">${m.date}</span>
          <span class="badge badge-indigo">${m.event_type}</span>
        </div>
        <div style="font-weight:600;">${escapeHtml(m.label)}</div>
      </div>`
    )
    .join("");
}

function populateOwnerFilterDropdown() {
  if (!appState.tasksData) return;
  const select = document.getElementById("filter-owner");
  const current = select.value;
  const owners = Array.from(new Set((appState.tasksData.tasks || []).map((t) => t.owner))).sort();
  select.innerHTML =
    `<option value="">All Owners (${owners.length})</option>` +
    owners.map((o) => `<option value="${escapeHtml(o)}">${escapeHtml(o)}</option>`).join("");
  select.value = current;
}

function switchTaskView(viewName) {
  appState.activeTaskView = viewName;
  ["table", "kanban", "gantt"].forEach((v) => {
    document.getElementById(`view-btn-${v}`).classList.toggle("active", v === viewName);
    document.getElementById(`task-view-${v}`).classList.toggle("active", v === viewName);
  });
}

function getFilteredTasks() {
  const all = (appState.tasksData && appState.tasksData.tasks) || [];
  const ownerFilter = document.getElementById("filter-owner").value;
  const prioFilter = document.getElementById("filter-priority").value;
  const statusFilter = document.getElementById("filter-status").value;

  return all.filter((t) => {
    if (ownerFilter && t.owner !== ownerFilter) return false;
    if (prioFilter && t.priority !== prioFilter) return false;
    if (statusFilter && t.status !== statusFilter) return false;
    return true;
  });
}

function renderTasksHub() {
  if (!appState.tasksData) return;
  const tasks = getFilteredTasks();
  const sched = appState.tasksData.schedule_summary || {};

  const conflicts = sched.schedule_conflicts || [];
  const banner = document.getElementById("conflict-banner");
  if (conflicts.length > 0) {
    banner.style.display = "block";
    banner.innerHTML = `<strong>Schedule Overlap Alert (${conflicts.length} detected):</strong> ` +
      conflicts
        .slice(0, 2)
        .map((c) => `${escapeHtml(c.owner)} has overlapping high-priority tasks (<em>${escapeHtml(c.task_a)}</em> &amp; <em>${escapeHtml(c.task_b)}</em> during ${c.overlap_window})`)
        .join(" • ");
  } else {
    banner.style.display = "none";
  }

  const tbody = document.getElementById("schedule-table-body");
  tbody.innerHTML = tasks
    .map((t) => {
      const pBadge =
        t.priority === "Critical"
          ? "badge-rose"
          : t.priority === "High"
          ? "badge-amber"
          : "badge-indigo";
      const quoteRow = t.evidence_quote
        ? `<div class="evidence-quote-box ${t.quote_verified ? "" : "unverified"}" style="margin-top:5px;">
            <span class="quote-pill ${t.quote_verified ? "" : "unverified"}">${t.quote_verified ? "&#10003; Grounded" : "Unverified"}</span>
            &ldquo;${escapeHtml(t.evidence_quote)}&rdquo;
          </div>`
        : "";
      return `
        <tr>
          <td><code>${t.id}</code></td>
          <td>
            <strong>${escapeHtml(t.owner)}</strong>
            <div class="muted-sm">${escapeHtml(t.owner_email || "")}</div>
          </td>
          <td>
            <div style="font-weight:600;color:#fff;">${escapeHtml(t.deliverable)}</div>
            <div class="muted-sm">Assigned by ${escapeHtml(t.assigner || "Team")}</div>
            ${quoteRow}
          </td>
          <td>${t.start_date}</td>
          <td><strong>${t.due_date}</strong></td>
          <td><span class="badge ${pBadge}">${t.priority}</span></td>
          <td>
            <select class="status-select" onchange="updateTaskStatus('${t.id}', this.value)">
              ${["Todo", "In Progress", "Blocked", "Completed"]
                .map((s) => `<option value="${s}" ${t.status === s ? "selected" : ""}>${s}</option>`)
                .join("")}
            </select>
          </td>
          <td>
            <button class="btn btn-xs btn-outline" onclick="jumpToSourceEmail('${t.source_email_id}')" title="Inspect source email">${t.source_email_id} &rarr;</button>
          </td>
        </tr>
      `;
    })
    .join("");

  const statuses = ["Todo", "In Progress", "Blocked", "Completed"];
  const kanbanGrid = document.getElementById("kanban-grid");
  kanbanGrid.innerHTML = statuses
    .map((st) => {
      const colTasks = tasks.filter((t) => t.status === st);
      return `
        <div class="kanban-col">
          <div class="kanban-col-header">
            <span>${st}</span>
            <span class="badge badge-indigo">${colTasks.length}</span>
          </div>
          ${colTasks
            .map((t) => {
              const pBadge =
                t.priority === "Critical"
                  ? "badge-rose"
                  : t.priority === "High"
                  ? "badge-amber"
                  : "badge-indigo";
              return `
                <div class="kanban-card">
                  <div style="display:flex;justify-content:space-between;align-items:center;">
                    <code>${t.id}</code>
                    <span class="badge ${pBadge}">${t.priority}</span>
                  </div>
                  <div class="kanban-card-title">${escapeHtml(t.deliverable)}</div>
                  <div class="muted-sm" style="margin-bottom:8px;">
                    <strong>${escapeHtml(t.owner)}</strong> &bull; ${t.start_date} &rarr; ${t.due_date}
                  </div>
                  <select class="status-select" style="width:100%;" onchange="updateTaskStatus('${t.id}', this.value)">
                    ${statuses.map((s) => `<option value="${s}" ${t.status === s ? "selected" : ""}>Move to: ${s}</option>`).join("")}
                  </select>
                </div>
              `;
            })
            .join("")}
        </div>
      `;
    })
    .join("");

  renderGanttAndWorkload(tasks, sched.owner_workloads || []);
}

function renderGanttAndWorkload(tasks, workloads) {
  const ganttEl = document.getElementById("gantt-chart-container");
  const minTime = new Date("2026-10-20").getTime();
  const maxTime = new Date("2026-11-15").getTime();
  const span = Math.max(1, maxTime - minTime);

  ganttEl.innerHTML = tasks
    .map((t) => {
      const s = Math.max(minTime, new Date(t.start_date).getTime());
      const e = Math.min(maxTime, new Date(t.due_date).getTime());
      const leftPct = Math.max(0, Math.min(92, ((s - minTime) / span) * 100));
      const widthPct = Math.max(7, Math.min(100 - leftPct, ((e - s) / span) * 100));
      const barColor =
        t.priority === "Critical"
          ? "#f43f5e"
          : t.priority === "High"
          ? "#f59e0b"
          : "#6366f1";
      return `
        <div class="gantt-row">
          <div>
            <strong>${escapeHtml(t.owner)}</strong>
            <div class="muted-sm" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(t.title)}</div>
          </div>
          <div class="gantt-track">
            <div class="gantt-bar" style="left:${leftPct}%;width:${widthPct}%;background:${barColor};" title="${escapeHtml(t.deliverable)} (${t.start_date} to ${t.due_date})">
              ${t.start_date.slice(5)} &rarr; ${t.due_date.slice(5)}
            </div>
          </div>
        </div>
      `;
    })
    .join("");

  const wlEl = document.getElementById("workload-list-container");
  wlEl.innerHTML = workloads
    .map((w) => {
      const badgeClass =
        w.utilization_status === "Overloaded"
          ? "badge-rose"
          : w.utilization_status === "Balanced"
          ? "badge-emerald"
          : "badge-indigo";
      return `
        <div style="background:var(--bg-card);border:1px solid var(--border-color);border-radius:8px;padding:10px 12px;margin-bottom:8px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <strong>${escapeHtml(w.owner)}</strong>
            <span class="badge ${badgeClass}">${w.utilization_status} (${w.estimated_active_hours}h active)</span>
          </div>
          <div class="muted-sm" style="margin-top:4px;">
            Total Tasks: ${w.total_tasks} &bull; Active: ${w.active_tasks} &bull; Critical: ${w.critical_tasks}
          </div>
        </div>
      `;
    })
    .join("");
}

async function updateTaskStatus(taskId, newStatus) {
  await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: newStatus }),
  });
  await refreshAllData();
}

function jumpToSourceEmail(emailId) {
  if (!emailId || emailId === "manual") return;
  appState.selectedEmailId = emailId;
  switchTab("emails");
  renderEmailList();
  renderSelectedEmailInspector();
}

// TAB 4: AI INTELLIGENCE AGENT
async function handleAgentSubmit(e) {
  e.preventDefault();
  const input = document.getElementById("agent-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  await sendAgentPrompt(text);
}

async function sendAgentPrompt(promptText) {
  switchTab("agent");
  const chatBox = document.getElementById("chat-messages");

  chatBox.insertAdjacentHTML(
    "beforeend",
    `<div class="chat-msg user">
      <div class="msg-header"><strong>You</strong></div>
      <div class="msg-body">${escapeHtml(promptText)}</div>
    </div>`
  );
  chatBox.scrollTop = chatBox.scrollHeight;

  const btn = document.getElementById("agent-send-btn");
  btn.disabled = true;
  btn.textContent = "Executing Tools...";

  try {
    const response = await fetch("/api/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: promptText }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    }
    const res = await response.json();

    const toolsHtml = (res.tool_calls || [])
      .map(
        (tc) => `
        <div class="tool-trace-box">
          <div style="color:#6ee7b7;font-weight:700;">&#9881; Tool Executed: <code>${escapeHtml(tc.tool_name)}</code></div>
          <div style="color:var(--text-secondary);margin-top:2px;">${escapeHtml(tc.result_summary)}</div>
        </div>`
      )
      .join("");

    chatBox.insertAdjacentHTML(
      "beforeend",
      `<div class="chat-msg agent">
        <div class="msg-header">
          <strong>NexusAI Intelligence Agent</strong>
          <span class="badge badge-indigo">${escapeHtml(res.engine)}</span>
        </div>
        ${toolsHtml}
        <div class="msg-body">${renderMarkdownToHtml(res.reply)}</div>
      </div>`
    );
    chatBox.scrollTop = chatBox.scrollHeight;
    await refreshAllData();
  } catch (err) {
    chatBox.insertAdjacentHTML(
      "beforeend",
      `<div class="chat-msg agent">
        <div class="msg-header">
          <strong>NexusAI Intelligence Agent</strong>
          <span class="badge badge-rose">Error</span>
        </div>
        <div class="msg-body">Failed to execute agent request: <code>${escapeHtml(err.message)}</code></div>
      </div>`
    );
    chatBox.scrollTop = chatBox.scrollHeight;
  } finally {
    btn.disabled = false;
    btn.textContent = "Run Agent";
  }
}

// Modals & Ingestion
function openIngestModal() {
  document.getElementById("ingest-modal").style.display = "flex";
}
function closeIngestModal() {
  document.getElementById("ingest-modal").style.display = "none";
}

const QUICK_PASTE_PRESETS = {
  security: `From: Sarah Chen <sarah.chen@nexusai.io>
To: Marcus Vance <marcus.vance@nexusai.io>, Elena Rodriguez <elena.rodriguez@nexusai.io>
Date: 2026-11-01
Subject: Final Go/No-Go Production Readiness & SOC2 Sign-Off

Hi Marcus and Elena,

Following our executive review in San Francisco with Acme Corp, please complete these final readiness items:
1. Marcus Vance: Complete final load testing benchmark report in Seattle starting 2026-11-02, due by 2026-11-08 (Critical Priority).
2. Elena Rodriguez: Deliver final SOC2 compliance attestation package to Claire Dupont at Acme Corp in London starting 2026-11-03, due by 2026-11-09 (High Priority).

Best,
Sarah Chen`,
  gpu: `Hey Priya and David,

Quick follow-up from our AWS infrastructure sync in New York with Snowflake:
- Priya Nair: Finalize H100 GPU cluster autoscaling benchmark for the RAG pipeline starting 2026-11-04, due by 2026-11-11 (Critical Priority).
- David Kim: Deliver updated Q4 Cloud FinOps reserved-instance cost model starting 2026-11-03, due by 2026-11-10 (High Priority).

Thanks,
Marcus Vance`,
};

function loadQuickPastePreset(key) {
  const el = document.getElementById("ing-raw-paste");
  if (el && QUICK_PASTE_PRESETS[key]) {
    el.value = QUICK_PASTE_PRESETS[key];
  }
}

async function submitIngestEmail(e) {
  e.preventDefault();
  const btn = document.getElementById("ing-submit-btn");
  const rawEl = document.getElementById("ing-raw-paste");
  const rawText = rawEl ? rawEl.value.trim() : "";
  if (!rawText) return;

  btn.disabled = true;
  btn.textContent = "Extracting & Grounding Quotes...";

  try {
    const res = await fetch("/api/emails/quick-paste", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_text: rawText, use_gemini: true }),
    }).then((r) => r.json());

    closeIngestModal();
    if (res.email) {
      appState.selectedEmailId = res.email.id;
    }
    await refreshAllData();
    switchTab("emails");
  } finally {
    btn.disabled = false;
    btn.textContent = "✨ Extract & Update Graph";
  }
}

async function handleEmlUpload(event) {
  const file = event.target.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch("/api/emails/upload-eml", {
    method: "POST",
    body: formData,
  }).then((r) => r.json());
  if (res.email) {
    appState.selectedEmailId = res.email.id;
    await refreshAllData();
  }
}

function openNewTaskModal() {
  document.getElementById("task-modal").style.display = "flex";
}
function closeNewTaskModal() {
  document.getElementById("task-modal").style.display = "none";
}

async function submitNewTask(e) {
  e.preventDefault();
  const payload = {
    title: document.getElementById("nt-title").value,
    deliverable: document.getElementById("nt-deliverable").value,
    owner: document.getElementById("nt-owner").value,
    priority: document.getElementById("nt-priority").value,
    start_date: document.getElementById("nt-start").value,
    due_date: document.getElementById("nt-due").value,
  };
  await fetch("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  closeNewTaskModal();
  await refreshAllData();
}

function renderMarkdownToHtml(md) {
  if (!md) return "";
  const lines = md.split("\n");
  let html = "";
  let inTable = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith("|") && line.endsWith("|")) {
      if (line.includes("---")) continue;
      const cells = line
        .slice(1, -1)
        .split("|")
        .map((c) => formatInlineMd(c.trim()));
      if (!inTable) {
        inTable = true;
        html += "<table><thead><tr>" + cells.map((c) => `<th>${c}</th>`).join("") + "</tr></thead><tbody>";
      } else {
        html += "<tr>" + cells.map((c) => `<td>${c}</td>`).join("") + "</tr>";
      }
      continue;
    } else if (inTable) {
      html += "</tbody></table>";
      inTable = false;
    }

    if (line.startsWith("### ")) {
      html += `<h3 style="margin:10px 0 6px;">${formatInlineMd(line.slice(4))}</h3>`;
    } else if (line.startsWith("#### ")) {
      html += `<h4 style="margin:10px 0 6px;color:#a5b4fc;">${formatInlineMd(line.slice(5))}</h4>`;
    } else if (line.startsWith("- ")) {
      html += `<div style="margin-left:10px;margin-bottom:4px;">&bull; ${formatInlineMd(line.slice(2))}</div>`;
    } else if (line.length > 0) {
      html += `<p style="margin-bottom:6px;">${formatInlineMd(line)}</p>`;
    }
  }
  if (inTable) html += "</tbody></table>";
  return html;
}

function formatInlineMd(str) {
  return escapeHtml(str)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

