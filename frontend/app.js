/* LLM Wiki Frontend Controller: Force-Directed Graph, Reader, Similarity Ingest, Linter, Chat */

const CATEGORY_COLORS = {
  concepts: "#6366f1",
  entities: "#14b8a6",
  sources: "#f59e0b",
  syntheses: "#ec4899",
};

const state = {
  pages: [],
  pagesBySlug: {},
  currentSlug: null,
  graph: { nodes: [], edges: [] },
  chatHistory: [],
  activeSubtab: "index",
  settings: null,
};

// ---------------------------------------------------------------------------
// Safe HTML Sanitizer (Native Sanitizer API with strict DOM fallback)
// ---------------------------------------------------------------------------
const SAFE_TAGS = new Set([
  "p", "br", "strong", "b", "em", "i", "code", "pre", "blockquote",
  "ul", "ol", "li", "h1", "h2", "h3", "h4", "table", "thead", "tbody",
  "tr", "th", "td", "hr", "button", "span", "div", "a",
]);
const SAFE_ATTRS = new Set(["class", "data-slug", "type", "href", "title"]);

function safeSetHTML(el, html) {
  if ("setHTML" in Element.prototype && typeof Sanitizer === "function") {
    try {
      const sanitizer = new Sanitizer({
        elements: [...SAFE_TAGS],
        attributes: [...SAFE_ATTRS],
      });
      el.setHTML(html, { sanitizer });
      return;
    } catch (_) {
      // Fall through to strict DOM parser sanitizer if custom config throws
    }
  }
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");
  const cleanNode = (node) => {
    for (const child of [...node.childNodes]) {
      if (child.nodeType === Node.ELEMENT_NODE) {
        const tag = child.tagName.toLowerCase();
        if (!SAFE_TAGS.has(tag)) {
          child.remove();
          continue;
        }
        for (const attr of [...child.attributes]) {
          const name = attr.name.toLowerCase();
          if (!SAFE_ATTRS.has(name) || name.startsWith("on")) {
            child.removeAttribute(attr.name);
          } else if (name === "href" && !/^https?:\/\//i.test(attr.value)) {
            child.removeAttribute(attr.name);
          }
        }
        cleanNode(child);
      } else if (child.nodeType === Node.COMMENT_NODE) {
        child.remove();
      }
    }
  };
  cleanNode(doc.body);
  el.replaceChildren(...doc.body.childNodes);
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Lightweight Markdown -> Safe HTML with clickable [[wikilinks]]
function renderMarkdown(mdText) {
  if (!mdText) return "";
  const lines = mdText.replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let inCode = false;
  let inList = false;
  let listTag = "ul";
  let inTable = false;
  let tableHeaderDone = false;

  const formatInline = (txt) => {
    let s = escapeHtml(txt);
    s = s.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    s = s.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_, target, label) => {
      const slug = target.trim().toLowerCase().replace(/[^a-z0-9\s-]/g, "").replace(/[\s_]+/g, "-");
      const display = label ? label.trim() : target.trim();
      return `<button type="button" class="wikilink-btn" data-slug="${escapeHtml(slug)}">${escapeHtml(display)}</button>`;
    });
    return s;
  };

  const closeList = () => {
    if (inList) {
      out.push(`</${listTag}>`);
      inList = false;
    }
  };
  const closeTable = () => {
    if (inTable) {
      out.push("</tbody></table>");
      inTable = false;
      tableHeaderDone = false;
    }
  };

  for (const rawLine of lines) {
    const line = rawLine;
    if (line.trim().startsWith("```")) {
      closeList();
      closeTable();
      if (!inCode) {
        out.push("<pre><code>");
        inCode = true;
      } else {
        out.push("</code></pre>");
        inCode = false;
      }
      continue;
    }
    if (inCode) {
      out.push(escapeHtml(line) + "\n");
      continue;
    }

    const trimmed = line.trim();
    if (!trimmed) {
      closeList();
      closeTable();
      continue;
    }

    // Markdown table
    if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
      closeList();
      const cells = trimmed.slice(1, -1).split("|").map((c) => c.trim());
      if (cells.every((c) => /^:?-{2,}:?$/.test(c))) {
        tableHeaderDone = true;
        continue;
      }
      if (!inTable) {
        out.push("<table><thead><tr>" + cells.map((c) => `<th>${formatInline(c)}</th>`).join("") + "</tr></thead><tbody>");
        inTable = true;
        tableHeaderDone = false;
      } else {
        out.push("<tr>" + cells.map((c) => `<td>${formatInline(c)}</td>`).join("") + "</tr>");
      }
      continue;
    } else {
      closeTable();
    }

    const hMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (hMatch) {
      closeList();
      const lvl = hMatch[1].length;
      out.push(`<h${lvl}>${formatInline(hMatch[2])}</h${lvl}>`);
      continue;
    }

    if (trimmed.startsWith("> ")) {
      closeList();
      out.push(`<blockquote><p>${formatInline(trimmed.slice(2))}</p></blockquote>`);
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      if (!inList || listTag !== "ul") {
        closeList();
        out.push("<ul>");
        inList = true;
        listTag = "ul";
      }
      out.push(`<li>${formatInline(trimmed.replace(/^[-*]\s+/, ""))}</li>`);
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      if (!inList || listTag !== "ol") {
        closeList();
        out.push("<ol>");
        inList = true;
        listTag = "ol";
      }
      out.push(`<li>${formatInline(trimmed.replace(/^\d+\.\s+/, ""))}</li>`);
      continue;
    }

    closeList();
    out.push(`<p>${formatInline(trimmed)}</p>`);
  }

  closeList();
  closeTable();
  if (inCode) out.push("</code></pre>");
  return out.join("");
}

// ---------------------------------------------------------------------------
// API Helpers
// ---------------------------------------------------------------------------
async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(errText || `HTTP ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Navigation & Data Loading
// ---------------------------------------------------------------------------
function switchView(viewName) {
  document.querySelectorAll(".tab-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === viewName);
  });
  document.querySelectorAll(".stage-view").forEach((sec) => {
    sec.classList.toggle("active", sec.id === `view-${viewName}`);
  });
  if (viewName === "graph") {
    resizeGraphCanvas();
  } else if (viewName === "lint") {
    loadLintAudit();
  } else if (viewName === "vault") {
    loadVaultLayer(state.activeSubtab);
  }
}

async function refreshAll() {
  const [overview, pagesData, graphData, settingsData] = await Promise.all([
    api("/api/overview"),
    api("/api/pages"),
    api(`/api/graph?include_semantic=${document.getElementById("toggle-semantic-edges").checked}`),
    api("/api/settings"),
  ]);

  state.settings = settingsData;
  state.pages = pagesData.pages;
  state.pagesBySlug = Object.fromEntries(pagesData.pages.map((p) => [p.slug, p]));
  updateTopMetrics(overview);
  renderExplorerTree();
  loadGraphData(graphData);
}

function updateTopMetrics(overview) {
  document.getElementById("metric-pages").textContent = `${overview.total_pages} pages`;
  document.getElementById("metric-raw").textContent = `${overview.total_raw_sources} raw`;
  document.getElementById("btn-health-pill").textContent = `Health: ${overview.health_score}%`;
  const modelLabel = overview.model_name && overview.model_name !== overview.provider_mode
    ? `${overview.provider_mode} (${overview.model_name})`
    : overview.provider_mode;
  document.getElementById("metric-provider").textContent = modelLabel;

  const telTotals = overview.telemetry?.totals;
  const telBtn = document.getElementById("btn-telemetry-pill");
  if (telBtn && telTotals) {
    telBtn.textContent = `${telTotals.total_tokens.toLocaleString()} tok · $${telTotals.total_cost_usd.toFixed(4)} (${telTotals.llm_calls_total} LLM / ${telTotals.local_smart_executions} local)`;
  }
}

function formatTelemetryBadge(tel) {
  if (!tel) return "";
  const modeBadge = tel.llm_used
    ? `LLM Used (${tel.llm_calls} call${tel.llm_calls > 1 ? "s" : ""})`
    : "Local Deterministic (0 LLM calls)";
  const models = (tel.models || []).join(", ") || "local_smart";
  return `${modeBadge} · Model: ${models} · Tokens: ${tel.total_tokens} (${tel.input_tokens}in/${tel.output_tokens}out) · Cost: $${Number(tel.cost_usd || 0).toFixed(6)} · Saved: ${tel.estimated_tokens_saved} tok ($${Number(tel.estimated_cost_saved_usd || 0).toFixed(6)}) · ${tel.total_latency_ms}ms`;
}

function renderExplorerTree() {
  const tree = document.getElementById("explorer-tree");
  const groups = { concepts: [], entities: [], sources: [], syntheses: [] };
  for (const p of state.pages) {
    (groups[p.category] ||= []).push(p);
  }

  tree.innerHTML = "";
  for (const [cat, items] of Object.entries(groups)) {
    const sec = document.createElement("div");
    sec.className = "explorer-group";
    const h3 = document.createElement("h3");
    h3.textContent = `${cat} (${items.length})`;
    sec.appendChild(h3);

    for (const p of items) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `explorer-item${state.currentSlug === p.slug ? " active" : ""}`;
      btn.dataset.slug = p.slug;
      const titleSpan = document.createElement("span");
      titleSpan.textContent = p.title;
      const revSpan = document.createElement("span");
      revSpan.className = "rev-tag";
      revSpan.textContent = `r${p.revision_count}`;
      btn.append(titleSpan, revSpan);
      btn.addEventListener("click", () => openPage(p.slug));
      sec.appendChild(btn);
    }
    tree.appendChild(sec);
  }
}

// ---------------------------------------------------------------------------
// Wiki Page Reader, Editor, Backlinks, Similar Pages & Diffs
// ---------------------------------------------------------------------------
async function openPage(slug) {
  const data = await api(`/api/pages/${encodeURIComponent(slug)}`);
  const page = data.page;
  state.currentSlug = page.slug;
  renderExplorerTree();
  switchView("reader");

  document.getElementById("reader-category").textContent = page.category;
  document.getElementById("reader-title").textContent = page.title;

  const fmBar = document.getElementById("reader-frontmatter");
  fmBar.innerHTML = "";
  const pills = [
    `slug: ${page.slug}`,
    `rev: ${page.revision_count}`,
    `sources: ${page.sources.length}`,
    `updated: ${(page.updated_at || "").slice(0, 10)}`,
    ...page.tags.map((t) => `#${t}`),
  ];
  for (const txt of pills) {
    const s = document.createElement("span");
    s.className = "fm-pill";
    s.textContent = txt;
    fmBar.appendChild(s);
  }

  const bodyEl = document.getElementById("reader-rendered-body");
  safeSetHTML(bodyEl, renderMarkdown(page.body));
  bodyEl.classList.remove("hidden");
  document.getElementById("reader-editor-wrap").classList.add("hidden");
  document.getElementById("editor-textarea").value = page.body;

  // Similar Existing Pages + Merge button
  const simEl = document.getElementById("reader-similar-list");
  simEl.innerHTML = "";
  if (!data.similar_pages.length) {
    simEl.innerHTML = `<span class="muted" style="font-size:0.78rem">No close matches yet.</span>`;
  } else {
    for (const m of data.similar_pages) {
      const row = document.createElement("div");
      row.className = "link-chip-row";
      const openBtn = document.createElement("button");
      openBtn.type = "button";
      openBtn.className = "link-chip-btn";
      openBtn.textContent = `${m.title} (${Math.round(m.score * 100)}%)`;
      openBtn.addEventListener("click", () => openPage(m.slug));

      const mergeBtn = document.createElement("button");
      mergeBtn.type = "button";
      mergeBtn.className = "btn btn-sm";
      mergeBtn.textContent = "Merge";
      mergeBtn.title = `Merge ${page.title} into ${m.title}`;
      mergeBtn.addEventListener("click", async () => {
        await api("/api/merge", {
          method: "POST",
          body: JSON.stringify({ source_slug: page.slug, target_slug: m.slug }),
        });
        await refreshAll();
        await openPage(m.slug);
      });
      row.append(openBtn, mergeBtn);
      simEl.appendChild(row);
    }
  }

  // Backlinks & Outbound links
  renderSlugList("reader-backlinks-list", page.backlinks, "No inbound backlinks (orphan!)");
  renderSlugList("reader-outbound-list", page.outbound_links, "No outbound links yet");

  // Mini history
  const histEl = document.getElementById("reader-history-list");
  histEl.innerHTML = "";
  if (!data.history.length) {
    histEl.innerHTML = `<span class="muted" style="font-size:0.78rem">Initial seed revision.</span>`;
  } else {
    for (const h of data.history.slice(0, 4)) {
      const div = document.createElement("div");
      div.className = "history-mini-item";
      div.textContent = `r${h.revision} [${h.operation}] — ${h.note}`;
      histEl.appendChild(div);
    }
  }
}

function renderSlugList(containerId, slugs, emptyMsg) {
  const el = document.getElementById(containerId);
  el.innerHTML = "";
  if (!slugs.length) {
    el.innerHTML = `<span class="muted" style="font-size:0.78rem">${escapeHtml(emptyMsg)}</span>`;
    return;
  }
  for (const s of slugs) {
    const row = document.createElement("div");
    row.className = "link-chip-row";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "link-chip-btn";
    btn.textContent = state.pagesBySlug[s]?.title || s;
    btn.addEventListener("click", () => openPage(s));
    row.appendChild(btn);
    el.appendChild(row);
  }
}

// ---------------------------------------------------------------------------
// Live Hybrid Search
// ---------------------------------------------------------------------------
let searchTimer = null;
document.getElementById("wiki-search-input").addEventListener("input", (e) => {
  const q = e.target.value.trim();
  clearTimeout(searchTimer);
  const panel = document.getElementById("search-results-panel");
  if (!q) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }
  searchTimer = setTimeout(async () => {
    const data = await api("/api/search", {
      method: "POST",
      body: JSON.stringify({ query: q, top_k: 6 }),
    });
    panel.classList.remove("hidden");
    panel.innerHTML = "";
    if (!data.results.length) {
      panel.innerHTML = `<p class="muted" style="font-size:0.78rem;margin:0.3rem">No matching pages found.</p>`;
      return;
    }
    for (const r of data.results) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "search-hit";
      const top = document.createElement("div");
      top.className = "search-hit-top";
      top.innerHTML = `<span>${escapeHtml(r.title)}</span><span class="score-badge">${Math.round(r.score * 100)}%</span>`;
      const sub = document.createElement("span");
      sub.className = "muted";
      sub.style.fontSize = "0.72rem";
      sub.textContent = `${r.category} · title ${Math.round(r.breakdown.title_alias * 100)}% · bm25 ${Math.round(r.breakdown.bm25 * 100)}%`;
      btn.append(top, sub);
      btn.addEventListener("click", () => {
        openPage(r.slug);
        panel.classList.add("hidden");
      });
      panel.appendChild(btn);
    }
  }, 160);
});

// ---------------------------------------------------------------------------
// Force-Directed Interactive Knowledge Graph (<canvas>)
// ---------------------------------------------------------------------------
const graphSim = {
  nodes: [],
  edges: [],
  camX: 0,
  camY: 0,
  zoom: 1,
  hoveredId: null,
  draggingNode: null,
  panning: false,
  panStart: { x: 0, y: 0 },
  dragMoved: false,
};

function loadGraphData(data) {
  const prevPos = Object.fromEntries(graphSim.nodes.map((n) => [n.id, { x: n.x, y: n.y }]));
  const count = data.nodes.length || 1;
  graphSim.nodes = data.nodes.map((n, i) => {
    const angle = (i / count) * Math.PI * 2;
    const prev = prevPos[n.id];
    return {
      ...n,
      x: prev ? prev.x : Math.cos(angle) * 140,
      y: prev ? prev.y : Math.sin(angle) * 140,
      vx: 0,
      vy: 0,
      radius: Math.min(20, 8 + n.degree * 1.6),
    };
  });
  graphSim.edges = data.edges;
}

function resizeGraphCanvas() {
  const canvas = document.getElementById("graph-canvas");
  const rect = canvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(300, Math.floor(rect.width * dpr));
  canvas.height = Math.max(260, Math.floor(rect.height * dpr));
}

function stepPhysics() {
  const nodes = graphSim.nodes;
  const nodeMap = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const kRepel = 4200;
  const kSpring = 0.015;
  const centerPull = 0.008;

  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i];
    if (graphSim.draggingNode === a) continue;
    a.vx += -a.x * centerPull;
    a.vy += -a.y * centerPull;
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j];
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const distSq = dx * dx + dy * dy + 40;
      const force = kRepel / distSq;
      const dist = Math.sqrt(distSq);
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      a.vx += fx;
      a.vy += fy;
      if (graphSim.draggingNode !== b) {
        b.vx -= fx;
        b.vy -= fy;
      }
    }
  }

  for (const e of graphSim.edges) {
    const s = nodeMap[e.source];
    const t = nodeMap[e.target];
    if (!s || !t) continue;
    const dx = t.x - s.x;
    const dy = t.y - s.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const restLen = e.type === "wikilink" ? 130 : 185;
    const strength = e.type === "wikilink" ? kSpring : kSpring * 0.45;
    const f = (dist - restLen) * strength;
    const fx = (dx / dist) * f;
    const fy = (dy / dist) * f;
    if (graphSim.draggingNode !== s) {
      s.vx += fx;
      s.vy += fy;
    }
    if (graphSim.draggingNode !== t) {
      t.vx -= fx;
      t.vy -= fy;
    }
  }

  for (const n of nodes) {
    if (graphSim.draggingNode === n) continue;
    n.vx *= 0.85;
    n.vy *= 0.85;
    n.x += n.vx;
    n.y += n.vy;
  }
}

function drawGraph() {
  const canvas = document.getElementById("graph-canvas");
  if (!canvas || !document.getElementById("view-graph").classList.contains("active")) {
    requestAnimationFrame(drawGraph);
    return;
  }
  stepPhysics();
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const catFilter = document.getElementById("filter-graph-category").value;
  const visibleNodes = graphSim.nodes.filter((n) => catFilter === "all" || n.category === catFilter);
  const visibleMap = Object.fromEntries(visibleNodes.map((n) => [n.id, n]));

  const isDark = getComputedStyle(document.documentElement).colorScheme.includes("dark") &&
    (document.querySelector('meta[name="color-scheme"]').content === "dark" ||
      (document.querySelector('meta[name="color-scheme"]').content === "light dark" &&
        window.matchMedia("(prefers-color-scheme: dark)").matches));
  const labelColor = isDark ? "#e6edf3" : "#161b26";
  const edgeColor = isDark ? "rgba(148,163,184,0.35)" : "rgba(71,85,105,0.28)";
  const semColor = isDark ? "rgba(129,140,248,0.42)" : "rgba(79,70,229,0.35)";

  ctx.save();
  ctx.translate(w / 2 + graphSim.camX * dpr, h / 2 + graphSim.camY * dpr);
  ctx.scale(graphSim.zoom * dpr, graphSim.zoom * dpr);

  const hovered = graphSim.hoveredId;
  const neighbors = new Set();
  if (hovered) {
    neighbors.add(hovered);
    for (const e of graphSim.edges) {
      if (e.source === hovered) neighbors.add(e.target);
      if (e.target === hovered) neighbors.add(e.source);
    }
  }

  // Draw edges
  for (const e of graphSim.edges) {
    const s = visibleMap[e.source];
    const t = visibleMap[e.target];
    if (!s || !t) continue;
    const dim = hovered && !(e.source === hovered || e.target === hovered);
    ctx.save();
    ctx.globalAlpha = dim ? 0.14 : 1;
    ctx.beginPath();
    if (e.type === "semantic") {
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = semColor;
      ctx.lineWidth = 1.3;
    } else {
      ctx.strokeStyle = hovered ? "#818cf8" : edgeColor;
      ctx.lineWidth = hovered ? 2 : 1.5;
    }
    ctx.moveTo(s.x, s.y);
    ctx.lineTo(t.x, t.y);
    ctx.stroke();
    ctx.restore();
  }

  // Draw nodes
  for (const n of visibleNodes) {
    const dim = hovered && !neighbors.has(n.id);
    ctx.save();
    ctx.globalAlpha = dim ? 0.25 : 1;

    if (n.is_hub) {
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.radius + 5, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(99, 102, 241, 0.45)";
      ctx.lineWidth = 2;
      ctx.stroke();
    }
    if (n.is_orphan) {
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.radius + 4, 0, Math.PI * 2);
      ctx.strokeStyle = "#f59e0b";
      ctx.setLineDash([3, 3]);
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.setLineDash([]);
    }

    ctx.beginPath();
    ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
    ctx.fillStyle = CATEGORY_COLORS[n.category] || "#6366f1";
    ctx.fill();
    ctx.lineWidth = hovered === n.id || state.currentSlug === n.id ? 3 : 1.5;
    ctx.strokeStyle = isDark ? "#0e1117" : "#ffffff";
    ctx.stroke();

    ctx.font = "600 11px Inter, sans-serif";
    ctx.fillStyle = labelColor;
    ctx.textAlign = "center";
    ctx.fillText(n.title, n.x, n.y + n.radius + 13);
    ctx.restore();
  }

  ctx.restore();
  requestAnimationFrame(drawGraph);
}

function screenToWorld(clientX, clientY) {
  const canvas = document.getElementById("graph-canvas");
  const rect = canvas.getBoundingClientRect();
  const sx = clientX - rect.left - rect.width / 2 - graphSim.camX;
  const sy = clientY - rect.top - rect.height / 2 - graphSim.camY;
  return { x: sx / graphSim.zoom, y: sy / graphSim.zoom };
}

function findNodeAt(wx, wy) {
  const catFilter = document.getElementById("filter-graph-category").value;
  for (let i = graphSim.nodes.length - 1; i >= 0; i--) {
    const n = graphSim.nodes[i];
    if (catFilter !== "all" && n.category !== catFilter) continue;
    const dx = wx - n.x;
    const dy = wy - n.y;
    if (dx * dx + dy * dy <= (n.radius + 6) ** 2) return n;
  }
  return null;
}

const graphCanvas = document.getElementById("graph-canvas");
graphCanvas.addEventListener("pointerdown", (e) => {
  const pt = screenToWorld(e.clientX, e.clientY);
  const hit = findNodeAt(pt.x, pt.y);
  graphSim.dragMoved = false;
  if (hit) {
    graphSim.draggingNode = hit;
  } else {
    graphSim.panning = true;
    graphSim.panStart = { x: e.clientX - graphSim.camX, y: e.clientY - graphSim.camY };
  }
});

graphCanvas.addEventListener("pointermove", (e) => {
  const pt = screenToWorld(e.clientX, e.clientY);
  if (graphSim.draggingNode) {
    graphSim.dragMoved = true;
    graphSim.draggingNode.x = pt.x;
    graphSim.draggingNode.y = pt.y;
    return;
  }
  if (graphSim.panning) {
    graphSim.dragMoved = true;
    graphSim.camX = e.clientX - graphSim.panStart.x;
    graphSim.camY = e.clientY - graphSim.panStart.y;
    return;
  }
  const hit = findNodeAt(pt.x, pt.y);
  graphSim.hoveredId = hit ? hit.id : null;
  const card = document.getElementById("graph-hover-card");
  if (hit) {
    card.classList.remove("hidden");
    card.innerHTML = `<strong>${escapeHtml(hit.title)}</strong> <span class="cat-badge">${escapeHtml(hit.category)}</span><p style="margin:0.35rem 0 0">${escapeHtml(hit.summary)}</p><p class="muted" style="margin:0.3rem 0 0;font-size:0.72rem">Degree: ${hit.degree} · Revisions: ${hit.revision_count}${hit.is_orphan ? " · Orphan" : ""}</p>`;
  } else {
    card.classList.add("hidden");
  }
});

window.addEventListener("pointerup", () => {
  if (graphSim.draggingNode && !graphSim.dragMoved) {
    openPage(graphSim.draggingNode.id);
  }
  graphSim.draggingNode = null;
  graphSim.panning = false;
});

graphCanvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.1 : 0.91;
  graphSim.zoom = Math.max(0.35, Math.min(2.6, graphSim.zoom * factor));
}, { passive: false });

document.getElementById("btn-reset-graph").addEventListener("click", () => {
  graphSim.camX = 0;
  graphSim.camY = 0;
  graphSim.zoom = 1;
});

document.getElementById("toggle-semantic-edges").addEventListener("change", refreshAll);

// ---------------------------------------------------------------------------
// Ingest & Similarity-First Update Studio
// ---------------------------------------------------------------------------
const thresholdSlider = document.getElementById("ingest-threshold");
thresholdSlider.addEventListener("input", () => {
  document.getElementById("threshold-display").textContent = Number(thresholdSlider.value).toFixed(2);
});

document.getElementById("btn-load-sample-ingest").addEventListener("click", () => {
  document.getElementById("ingest-title").value = "LLM Wiki Pattern: Incremental Contradiction Tracking";
  document.getElementById("ingest-content").value =
    "Recent experiments with the LLM Wiki Pattern show that maintaining explicit contradiction sections prevents silent drift when newer benchmarks supersede older claims.\n\nUnlike stateless RAG pipelines, a compiled wiki updates canonical pages in-place and tracks revision counts in YAML frontmatter.";
});

document.getElementById("btn-preview-ingest").addEventListener("click", async () => {
  const title = document.getElementById("ingest-title").value.trim();
  const content = document.getElementById("ingest-content").value.trim();
  if (!title || !content) return;
  const data = await api("/api/ingest/preview", {
    method: "POST",
    body: JSON.stringify({ title, content, threshold: Number(thresholdSlider.value) }),
  });

  const panel = document.getElementById("ingest-preview-panel");
  panel.classList.remove("hidden");
  panel.innerHTML = `<h3>Similarity Search Plan (threshold: ${Math.round(data.threshold * 100)}%)</h3>`;
  for (const item of data.items) {
    const card = document.createElement("div");
    card.className = `plan-card decision-${item.decision}`;
    const pct = Math.round(item.best_score * 100);
    const actionLabel =
      item.decision === "update"
        ? `UPDATE EXISTING → [[${escapeHtml(item.target_slug)}]] (${pct}% match)`
        : `CREATE NEW PAGE (best existing match only ${pct}%)`;
    card.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;gap:0.5rem;flex-wrap:wrap">
        <strong>${escapeHtml(item.extracted_title)}</strong>
        <span class="decision-pill ${item.decision}">${actionLabel}</span>
      </div>
      <p class="muted" style="margin:0.35rem 0">${escapeHtml(item.summary)}</p>
      <div style="font-size:0.76rem">Top candidates: ${
        item.matches.slice(0, 3).map((m) => `${escapeHtml(m.title)} (${Math.round(m.score * 100)}%)`).join(" · ") || "None"
      }</div>
    `;
    panel.appendChild(card);
  }
});

document.getElementById("ingest-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const title = document.getElementById("ingest-title").value.trim();
  const content = document.getElementById("ingest-content").value.trim();
  const data = await api("/api/ingest/execute", {
    method: "POST",
    body: JSON.stringify({ title, content, threshold: Number(thresholdSlider.value) }),
  });

  const resPanel = document.getElementById("ingest-result-panel");
  resPanel.classList.remove("hidden");
  resPanel.innerHTML = `<h3>Ingest Complete (${escapeHtml(data.provider_mode)} / ${escapeHtml(data.model_name || data.provider_mode)})</h3>`;
  if (data.telemetry) {
    const telP = document.createElement("p");
    telP.className = "meta-hint";
    telP.style.fontFamily = "monospace";
    telP.textContent = formatTelemetryBadge(data.telemetry);
    resPanel.appendChild(telP);
  }
  for (const r of data.results) {
    const card = document.createElement("div");
    card.className = `plan-card decision-${r.action === "updated" ? "update" : "create"}`;
    card.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;gap:0.5rem">
        <strong>${escapeHtml(r.title)} (rev ${r.revision_count})</strong>
        <span class="decision-pill ${r.action === "updated" ? "update" : "create"}">${escapeHtml(r.action.toUpperCase())}</span>
      </div>
      <p style="margin:0.3rem 0">${escapeHtml(r.change_note)}</p>
      <pre class="diff-block">${escapeHtml(r.diff || "")}</pre>
    `;
    const openBtn = document.createElement("button");
    openBtn.type = "button";
    openBtn.className = "btn btn-sm btn-primary";
    openBtn.textContent = `Open [[${r.slug}]]`;
    openBtn.addEventListener("click", () => openPage(r.slug));
    card.appendChild(openBtn);
    resPanel.appendChild(card);
  }
  await refreshAll();
});

// ---------------------------------------------------------------------------
// Self-Maintenance & Health Center
// ---------------------------------------------------------------------------
async function loadLintAudit() {
  const data = await api("/api/lint");
  renderLintReport(data);
}

function renderLintReport(data, healActions = null) {
  const container = document.getElementById("lint-container");
  container.innerHTML = "";

  if (healActions) {
    const banner = document.createElement("div");
    banner.className = "lint-section";
    banner.innerHTML = `<h3>Auto-Heal Completed (${healActions.length} action(s))</h3>` +
      (healActions.length
        ? `<ul>${healActions.map((a) => `<li>${escapeHtml(a)}</li>`).join("")}</ul>`
        : `<p class="muted">Wiki was already healthy — index.md verified.</p>`);
    container.appendChild(banner);
  }

  const grid = document.createElement("div");
  grid.className = "health-grid";
  const stats = [
    ["Health Score", `${data.health_score}%`],
    ["Unlinked Mentions", data.summary.unlinked_mentions],
    ["Orphan Pages", data.summary.orphan_pages],
    ["Dangling Links", data.summary.dangling_links],
    ["Near-Duplicates", data.summary.near_duplicates],
    ["Tracked Tensions", data.summary.contradictions_tracked],
  ];
  for (const [lbl, val] of stats) {
    const card = document.createElement("div");
    card.className = "stat-card";
    card.innerHTML = `<div class="stat-val">${escapeHtml(val)}</div><div class="stat-lbl">${escapeHtml(lbl)}</div>`;
    grid.appendChild(card);
  }
  container.appendChild(grid);

  const addSection = (title, items, renderItem) => {
    const sec = document.createElement("div");
    sec.className = "lint-section";
    sec.innerHTML = `<h3>${escapeHtml(title)} (${items.length})</h3>`;
    if (!items.length) {
      sec.innerHTML += `<p class="muted" style="margin:0">None detected.</p>`;
    } else {
      const ul = document.createElement("ul");
      for (const it of items) {
        const li = document.createElement("li");
        li.innerHTML = renderItem(it);
        ul.appendChild(li);
      }
      sec.appendChild(ul);
    }
    container.appendChild(sec);
  };

  addSection("Unlinked Mentions", data.unlinked_mentions, (m) =>
    `In <strong>${escapeHtml(m.source_title)}</strong>: plain-text "${escapeHtml(m.matched_term)}" → <code>[[${escapeHtml(m.target_slug)}]]</code>`
  );
  addSection("Orphan Pages (0 inbound links)", data.orphan_pages, (o) =>
    `<strong>${escapeHtml(o.title)}</strong> (<code>${escapeHtml(o.slug)}</code>)`
  );
  addSection("Dangling [[Wikilinks]]", data.dangling_links, (d) =>
    `In <strong>${escapeHtml(d.source_title)}</strong>: <code>[[${escapeHtml(d.target_raw)}]]</code>` +
    (d.suggested_slug ? ` (suggested: <code>[[${escapeHtml(d.suggested_slug)}]]</code>)` : " (will create stub)")
  );
  addSection("Near-Duplicate Candidates", data.near_duplicates, (nd) =>
    `${escapeHtml(nd.title_a)} ↔ ${escapeHtml(nd.title_b)} (${Math.round(nd.score * 100)}% overlap)`
  );
  addSection("Documented Contradictions & Tensions", data.contradictions, (c) =>
    `<strong>${escapeHtml(c.title)}</strong>: ${escapeHtml(c.notes[0] || "")}`
  );
}

document.getElementById("btn-run-audit").addEventListener("click", loadLintAudit);
document.getElementById("btn-auto-heal").addEventListener("click", async () => {
  const res = await api("/api/lint/heal", {
    method: "POST",
    body: JSON.stringify({ create_stubs_for_dangling: true }),
  });
  renderLintReport(res.audit, res.actions_taken);
  await refreshAll();
});

// ---------------------------------------------------------------------------
// Vault Layers (SCHEMA.md, index.md, log.md, raw/)
// ---------------------------------------------------------------------------
async function loadVaultLayer(subtab) {
  state.activeSubtab = subtab;
  document.querySelectorAll(".vault-subtab").forEach((b) => {
    b.classList.toggle("active", b.dataset.subtab === subtab);
  });
  const container = document.getElementById("vault-layer-content");
  if (subtab === "telemetry") {
    const data = await api("/api/telemetry?limit=80");
    renderTelemetryDashboard(container, data);
    return;
  }
  if (subtab === "raw") {
    const data = await api("/api/raw");
    container.innerHTML = "";
    for (const r of data.raw_sources) {
      const card = document.createElement("div");
      card.className = "lint-section";
      card.innerHTML = `<h3>${escapeHtml(r.filename)} — ${escapeHtml(r.title)}</h3><pre class="diff-block">${escapeHtml(r.content)}</pre>`;
      container.appendChild(card);
    }
    return;
  }
  const data = await api("/api/index-log");
  const mdMap = { index: data.index_md, log: data.log_md, schema: data.schema_md };
  const div = document.createElement("div");
  div.className = "markdown-body";
  safeSetHTML(div, renderMarkdown(mdMap[subtab] || ""));
  container.replaceChildren(div);
}

document.querySelectorAll(".vault-subtab").forEach((b) => {
  b.addEventListener("click", () => loadVaultLayer(b.dataset.subtab));
});

const telemetryPillBtn = document.getElementById("btn-telemetry-pill");
if (telemetryPillBtn) {
  telemetryPillBtn.addEventListener("click", () => {
    state.activeSubtab = "telemetry";
    switchView("vault");
  });
}

function renderTelemetryDashboard(container, data) {
  const t = data.totals || {};
  container.innerHTML = "";

  const headerRow = document.createElement("div");
  headerRow.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:0.75rem;flex-wrap:wrap;margin-bottom:0.9rem;";
  headerRow.innerHTML = `
    <div>
      <h3 style="margin:0">LLM Observability, Token Usage &amp; Cost</h3>
      <p class="meta-hint" style="margin:0.2rem 0 0">Active: <strong>${escapeHtml(data.active_provider)}</strong> (${escapeHtml(data.active_model)}) · Log file: <code>${escapeHtml(data.log_file || "in-memory")}</code></p>
    </div>
  `;
  const btnWrap = document.createElement("div");
  btnWrap.style.cssText = "display:flex;gap:0.5rem;";
  const refreshBtn = document.createElement("button");
  refreshBtn.type = "button";
  refreshBtn.className = "btn btn-sm btn-secondary";
  refreshBtn.textContent = "Refresh";
  refreshBtn.addEventListener("click", () => loadVaultLayer("telemetry"));
  const resetBtn = document.createElement("button");
  resetBtn.type = "button";
  resetBtn.className = "btn btn-sm btn-ghost";
  resetBtn.textContent = "Reset Telemetry";
  resetBtn.addEventListener("click", async () => {
    const fresh = await api("/api/telemetry/reset", { method: "POST" });
    renderTelemetryDashboard(container, fresh);
    await refreshAll();
  });
  btnWrap.append(refreshBtn, resetBtn);
  headerRow.appendChild(btnWrap);
  container.appendChild(headerRow);

  const statsGrid = document.createElement("div");
  statsGrid.style.cssText = "display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:0.65rem;margin-bottom:1rem;";
  const cards = [
    ["LLM Calls / Local Ops", `${t.llm_calls_total || 0} LLM / ${t.local_smart_executions || 0} local`, `Skipped by dedup: ${t.llm_calls_skipped_by_dedup || 0}`],
    ["Total Tokens Used", `${(t.total_tokens || 0).toLocaleString()}`, `${(t.input_tokens || 0).toLocaleString()} in / ${(t.output_tokens || 0).toLocaleString()} out`],
    ["Total API Cost", `$${Number(t.total_cost_usd || 0).toFixed(6)}`, `Failures: ${t.llm_calls_failed || 0} · Fallbacks: ${t.llm_fallbacks_to_local || 0}`],
    ["Est. Cost & Tokens Saved", `$${Number(t.estimated_cost_saved_usd || 0).toFixed(6)}`, `${(t.estimated_tokens_saved || 0).toLocaleString()} tokens avoided`],
    ["Avg Latency (LLM vs Local)", `${t.avg_llm_latency_ms || 0} ms LLM`, `${t.avg_local_latency_ms || 0} ms local`],
  ];
  for (const [label, val, sub] of cards) {
    const c = document.createElement("div");
    c.className = "lint-section";
    c.style.margin = "0";
    c.innerHTML = `<div class="meta-hint">${escapeHtml(label)}</div><div style="font-size:1.05rem;font-weight:700;margin:0.2rem 0">${escapeHtml(val)}</div><div class="meta-hint">${escapeHtml(sub)}</div>`;
    statsGrid.appendChild(c);
  }
  container.appendChild(statsGrid);

  if (data.by_model?.length) {
    const mSec = document.createElement("div");
    mSec.className = "lint-section";
    mSec.innerHTML = `<h3>Breakdown by Provider &amp; Model</h3>`;
    const list = document.createElement("div");
    list.style.cssText = "display:flex;flex-direction:column;gap:0.4rem;font-family:monospace;font-size:0.78rem;";
    for (const m of data.by_model) {
      const row = document.createElement("div");
      row.textContent = `${m.provider}:${m.model} | llm_used=${m.llm_used} | calls=${m.calls} (ok=${m.succeeded}) | tokens=${m.total_tokens} (${m.input_tokens}in/${m.output_tokens}out) | cost=$${Number(m.cost_usd).toFixed(6)} | saved=${m.estimated_tokens_saved} tok ($${Number(m.estimated_cost_saved_usd).toFixed(6)})`;
      list.appendChild(row);
    }
    mSec.appendChild(list);
    container.appendChild(mSec);
  }

  const evSec = document.createElement("div");
  evSec.className = "lint-section";
  evSec.innerHTML = `<h3>Recent Execution Events (${(data.recent_events || []).length})</h3>`;
  if (!data.recent_events?.length) {
    evSec.innerHTML += `<p class="muted">No telemetry events recorded yet. Run an ingest, search, or chat query.</p>`;
  } else {
    const evList = document.createElement("div");
    evList.style.cssText = "display:flex;flex-direction:column;gap:0.45rem;max-height:360px;overflow:auto;font-family:monospace;font-size:0.76rem;";
    for (const ev of data.recent_events) {
      const row = document.createElement("div");
      row.style.cssText = "padding:0.45rem 0.6rem;border-radius:6px;border:1px solid var(--border,rgba(148,163,184,0.2));";
      const llmTag = ev.llm_used ? "LLM" : (ev.execution_mode === "local_dedup_prefilter" ? "DEDUP-SKIP" : "LOCAL");
      row.textContent = `[${ev.timestamp}] #${ev.event_id} [${llmTag}] op=${ev.operation} provider=${ev.provider} model=${ev.model} status=${ev.status} tokens=${ev.input_tokens}in/${ev.output_tokens}out/${ev.total_tokens}tot (${ev.token_source}) cost=$${Number(ev.cost_usd).toFixed(6)} saved=${ev.estimated_tokens_saved}tok lat=${ev.latency_ms}ms ${ev.target_slug ? "slug=" + ev.target_slug : ""} — ${ev.reason}`;
      evList.appendChild(row);
    }
    evSec.appendChild(evList);
  }
  container.appendChild(evSec);
}

// ---------------------------------------------------------------------------
// Wiki Chat & File-to-Wiki
// ---------------------------------------------------------------------------
async function submitChatQuestion(question) {
  if (!question.trim()) return;
  const chatLog = document.getElementById("chat-messages");
  const userDiv = document.createElement("div");
  userDiv.className = "chat-msg user";
  userDiv.innerHTML = `<div class="chat-bubble"><p>${escapeHtml(question)}</p></div>`;
  chatLog.appendChild(userDiv);
  chatLog.scrollTop = chatLog.scrollHeight;

  state.chatHistory.push({ role: "user", content: question });
  const data = await api("/api/chat", {
    method: "POST",
    body: JSON.stringify({ question, history: state.chatHistory.slice(-8) }),
  });
  state.chatHistory.push({ role: "assistant", content: data.answer });

  const botDiv = document.createElement("div");
  botDiv.className = "chat-msg assistant";
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble markdown-body";
  safeSetHTML(bubble, renderMarkdown(data.answer));
  botDiv.appendChild(bubble);

  if (data.cited_pages?.length) {
    const citeRow = document.createElement("div");
    citeRow.className = "chat-citations";
    for (const c of data.cited_pages) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip-btn";
      chip.textContent = `${c.title} (${Math.round(c.score * 100)}%)`;
      chip.addEventListener("click", () => openPage(c.slug));
      citeRow.appendChild(chip);
    }
    botDiv.appendChild(citeRow);
  }

  if (data.telemetry) {
    const telNote = document.createElement("div");
    telNote.className = "meta-hint";
    telNote.style.cssText = "font-family:monospace;font-size:0.72rem;margin-top:0.35rem;";
    telNote.textContent = formatTelemetryBadge(data.telemetry);
    botDiv.appendChild(telNote);
  }

  const fileBtn = document.createElement("button");
  fileBtn.type = "button";
  fileBtn.className = "btn btn-sm btn-secondary";
  fileBtn.textContent = "File Answer to Wiki (Search Similar / Update)";
  fileBtn.addEventListener("click", async () => {
    fileBtn.disabled = true;
    fileBtn.textContent = "Filing to Wiki…";
    const filed = await api("/api/chat/file-to-wiki", {
      method: "POST",
      body: JSON.stringify({
        title: question.replace(/[?]+$/, "").slice(0, 72),
        answer_markdown: data.answer,
        question,
      }),
    });
    const first = filed.results[0];
    fileBtn.textContent = first
      ? `${first.action === "updated" ? "Updated" : "Created"} [[${first.slug}]]`
      : "Filed to Wiki";
    await refreshAll();
  });
  botDiv.appendChild(fileBtn);

  chatLog.appendChild(botDiv);
  chatLog.scrollTop = chatLog.scrollHeight;
}

document.getElementById("chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const q = input.value.trim();
  if (!q) return;
  input.value = "";
  await submitChatQuestion(q);
});

document.getElementById("chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    document.getElementById("chat-form").requestSubmit();
  }
});

document.getElementById("btn-clear-chat").addEventListener("click", () => {
  state.chatHistory = [];
  const chatLog = document.getElementById("chat-messages");
  while (chatLog.children.length > 1) {
    chatLog.removeChild(chatLog.lastChild);
  }
});

// ---------------------------------------------------------------------------
// Dialogs, Light-Dismiss Fallback, Theme Toggle & Global Delegation
// ---------------------------------------------------------------------------
for (const dialog of document.querySelectorAll("dialog")) {
  dialog.addEventListener("close", () => {
    dialog.returnValue = "";
  });
  if (!("closedBy" in HTMLDialogElement.prototype)) {
    const outside = (e, d) => {
      const r = d.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };
    if (dialog.getAttribute("closedby") === "any") {
      let pressedOutside = false;
      dialog.addEventListener("pointerdown", (e) => {
        pressedOutside = outside(e, dialog);
      });
      dialog.addEventListener("pointerup", (e) => {
        if (pressedOutside && outside(e, dialog)) dialog.close();
      });
    }
  }
}

function applyThemePreference(mode) {
  const meta = document.querySelector('meta[name="color-scheme"]');
  meta.content = mode;
  try {
    if (mode === "light dark") {
      localStorage.removeItem("color-scheme");
    } else {
      localStorage.setItem("color-scheme", mode);
    }
  } catch (_) {}
}

window.addEventListener("storage", (e) => {
  if (e.key === "color-scheme") {
    document.querySelector('meta[name="color-scheme"]').content = e.newValue ?? "light dark";
  }
});

function syncProviderFields(provider) {
  document.querySelectorAll(".provider-field").forEach((el) => {
    el.classList.toggle("hidden", el.dataset.provider !== provider);
  });
}

document.getElementById("setting-provider").addEventListener("change", (e) => {
  syncProviderFields(e.target.value);
});
document.getElementById("setting-sim-threshold").addEventListener("input", (e) => {
  document.getElementById("setting-sim-val").textContent = Number(e.target.value).toFixed(2);
});

document.getElementById("btn-open-settings").addEventListener("click", async () => {
  const s = await api("/api/settings");
  state.settings = s;
  let themeVal = "light dark";
  try {
    themeVal = localStorage.getItem("color-scheme") ?? "light dark";
  } catch (_) {}
  document.getElementById("setting-theme").value = themeVal;
  document.getElementById("setting-provider").value = s.provider;
  document.getElementById("setting-gemini-key").value = s.gemini_api_key || "";
  document.getElementById("setting-gemini-model").value = s.gemini_model || "gemini-4-hydrogen";
  document.getElementById("setting-openai-key").value = s.openai_api_key || "";
  document.getElementById("setting-openai-url").value = s.openai_base_url || "https://api.openai.com/v1";
  document.getElementById("setting-openai-model").value = s.openai_model || "gpt-4o-mini";
  const customHeaders = s.openai_custom_headers && Object.keys(s.openai_custom_headers).length
    ? JSON.stringify(s.openai_custom_headers, null, 2)
    : "";
  document.getElementById("setting-openai-headers").value = customHeaders;
  document.getElementById("setting-ollama-url").value = s.ollama_base_url || "http://127.0.0.1:11434";
  document.getElementById("setting-ollama-model").value = s.ollama_model || "llama3.2";
  document.getElementById("setting-sim-threshold").value = s.similarity_threshold;
  document.getElementById("setting-sim-val").textContent = Number(s.similarity_threshold).toFixed(2);
  document.getElementById("setting-auto-maintain").checked = s.auto_maintain_after_ingest;
  syncProviderFields(s.provider);
  document.getElementById("settings-dialog").showModal();
});

document.getElementById("btn-cancel-settings").addEventListener("click", () => {
  document.getElementById("settings-dialog").close();
});

document.getElementById("settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  let parsedHeaders = {};
  const rawHeaders = document.getElementById("setting-openai-headers").value.trim();
  if (rawHeaders) {
    try {
      const candidate = JSON.parse(rawHeaders);
      if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
        alert("Custom Headers must be a JSON object, e.g. {\"sid\": \"...\", \"env\": \"...\"}");
        return;
      }
      parsedHeaders = Object.fromEntries(
        Object.entries(candidate).map(([k, v]) => [String(k), String(v)])
      );
    } catch (err) {
      alert(`Invalid Custom Headers JSON: ${err.message}`);
      return;
    }
  }
  applyThemePreference(document.getElementById("setting-theme").value);
  await api("/api/settings", {
    method: "POST",
    body: JSON.stringify({
      provider: document.getElementById("setting-provider").value,
      gemini_api_key: document.getElementById("setting-gemini-key").value,
      gemini_model: document.getElementById("setting-gemini-model").value,
      openai_api_key: document.getElementById("setting-openai-key").value,
      openai_base_url: document.getElementById("setting-openai-url").value,
      openai_model: document.getElementById("setting-openai-model").value,
      openai_custom_headers: parsedHeaders,
      ollama_base_url: document.getElementById("setting-ollama-url").value,
      ollama_model: document.getElementById("setting-ollama-model").value,
      similarity_threshold: Number(document.getElementById("setting-sim-threshold").value),
      auto_maintain_after_ingest: document.getElementById("setting-auto-maintain").checked,
    }),
  });
  document.getElementById("settings-dialog").close();
  await refreshAll();
});

document.getElementById("btn-view-history").addEventListener("click", async () => {
  if (!state.currentSlug) return;
  const data = await api(`/api/pages/${encodeURIComponent(state.currentSlug)}`);
  const body = document.getElementById("diff-dialog-body");
  body.innerHTML = "";
  if (!data.history.length) {
    body.innerHTML = `<p class="muted">No revision diffs recorded yet for this page.</p>`;
  } else {
    for (const h of data.history) {
      const card = document.createElement("div");
      card.innerHTML = `<strong>Revision ${h.revision} · ${escapeHtml(h.operation)}</strong> <span class="muted">${escapeHtml(h.timestamp)}</span><p style="margin:0.25rem 0">${escapeHtml(h.note)}</p><pre class="diff-block">${escapeHtml(h.diff || "")}</pre>`;
      body.appendChild(card);
    }
  }
  document.getElementById("diff-dialog").showModal();
});

// Edit page controls
document.getElementById("btn-edit-page").addEventListener("click", () => {
  if (!state.currentSlug) return;
  document.getElementById("reader-rendered-body").classList.add("hidden");
  document.getElementById("reader-editor-wrap").classList.remove("hidden");
});
document.getElementById("btn-cancel-edit").addEventListener("click", () => {
  document.getElementById("reader-editor-wrap").classList.add("hidden");
  document.getElementById("reader-rendered-body").classList.remove("hidden");
});
document.getElementById("btn-save-edit").addEventListener("click", async () => {
  if (!state.currentSlug) return;
  const p = state.pagesBySlug[state.currentSlug];
  await api(`/api/pages/${encodeURIComponent(state.currentSlug)}`, {
    method: "PUT",
    body: JSON.stringify({
      title: p.title,
      category: p.category,
      body: document.getElementById("editor-textarea").value,
      aliases: p.aliases,
      tags: p.tags,
      summary: p.summary,
      confidence: p.confidence,
    }),
  });
  await refreshAll();
  await openPage(state.currentSlug);
});

// Event delegation for wikilinks & suggestion chips
document.addEventListener("click", (e) => {
  const wikiBtn = e.target.closest(".wikilink-btn");
  if (wikiBtn && wikiBtn.dataset.slug) {
    openPage(wikiBtn.dataset.slug).catch(() => {});
    return;
  }
  const chip = e.target.closest(".chip-btn[data-prompt]");
  if (chip) {
    submitChatQuestion(chip.dataset.prompt);
  }
});

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});
document.getElementById("btn-open-ingest").addEventListener("click", () => switchView("ingest"));
document.getElementById("btn-health-pill").addEventListener("click", () => switchView("lint"));
window.addEventListener("resize", resizeGraphCanvas);

// Boot
(async function init() {
  resizeGraphCanvas();
  await refreshAll();
  requestAnimationFrame(drawGraph);
})();

