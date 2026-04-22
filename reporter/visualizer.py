"""
Generates a self-contained HTML knowledge graph visualisation using D3.js v7.
Dark legal-intelligence aesthetic: deep navy background, amber/gold high-importance nodes,
steel-blue connections, elegant typography.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import date


TYPE_COLORS = {
    "regulation": "#e8c547",   # gold
    "principle": "#7ecfff",    # sky blue
    "obligation": "#ff9f6b",   # amber-orange
    "right": "#7affa0",        # mint green
    "risk": "#ff6b6b",         # red
    "term": "#b8a9ff",         # lavender
    "standard": "#66d9e8",     # cyan
    "entity": "#f8a5c2",       # pink
    "concept": "#aaaaaa",      # grey
}

IMPORTANCE_SIZE = {
    "high": 14,
    "medium": 9,
    "low": 6,
}


def build_graph_data(
    concepts: list[dict],
    connections: list[dict],
    gaps: dict
) -> dict:
    """Build D3-compatible graph data with metadata."""
    concept_names = {c["name"] for c in concepts}
    
    nodes = [
        {
            "id": c["name"],
            "type": c.get("type", "concept"),
            "importance": c.get("importance", "medium"),
            "definition": c.get("definition", ""),
            "color": TYPE_COLORS.get(c.get("type", "concept"), "#aaaaaa"),
            "size": IMPORTANCE_SIZE.get(c.get("importance", "medium"), 9),
            "gap": any(
                g.get("concept") == c["name"]
                for g in gaps.get("missing_definitions", [])
            )
        }
        for c in concepts
    ]
    
    # Deduplicate connections
    seen = set()
    links = []
    for conn in connections:
        src, tgt = conn.get("source", ""), conn.get("target", "")
        if src in concept_names and tgt in concept_names:
            key = tuple(sorted([src, tgt]))
            if key not in seen:
                seen.add(key)
                links.append({
                    "source": src,
                    "target": tgt,
                    "relationship": conn.get("relationship", "related to")
                })
    
    return {"nodes": nodes, "links": links, "gaps": gaps}


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Crimson+Pro:ital,wght@0,300;0,400;0,600;1,300&family=JetBrains+Mono:wght@300;400&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #080c14;
    --surface: #0e1421;
    --surface2: #141c2e;
    --border: #1e2d47;
    --text: #c8d8f0;
    --text-dim: #5a7a9a;
    --accent: #e8c547;
    --accent2: #3a6fd8;
    --gap-color: #ff6b6b;
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Crimson Pro', Georgia, serif;
    height: 100vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }}

  /* ── Header ────────────────────────────────────────── */
  header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 24px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    z-index: 10;
    flex-shrink: 0;
  }}

  .brand {{
    display: flex;
    align-items: baseline;
    gap: 10px;
  }}

  .brand h1 {{
    font-size: 1.1rem;
    font-weight: 300;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--accent);
  }}

  .brand span {{
    font-size: 0.75rem;
    color: var(--text-dim);
    font-family: 'JetBrains Mono', monospace;
  }}

  .header-right {{
    display: flex;
    align-items: center;
    gap: 16px;
  }}

  .stats {{
    display: flex;
    gap: 20px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: var(--text-dim);
  }}

  .stats span b {{
    color: var(--accent);
    font-weight: 400;
  }}

  /* ── Search ─────────────────────────────────────────── */
  #search {{
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 14px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    width: 220px;
    outline: none;
    transition: border-color 0.2s;
  }}
  #search:focus {{ border-color: var(--accent); }}
  #search::placeholder {{ color: var(--text-dim); }}

  /* ── Main layout ────────────────────────────────────── */
  .main {{
    display: flex;
    flex: 1;
    overflow: hidden;
  }}

  /* ── Canvas ─────────────────────────────────────────── */
  #canvas {{
    flex: 1;
    position: relative;
  }}

  svg {{
    width: 100%;
    height: 100%;
    cursor: grab;
  }}
  svg:active {{ cursor: grabbing; }}

  .link {{
    stroke: #1e3a5f;
    stroke-width: 1.2;
    stroke-opacity: 0.6;
    transition: stroke-opacity 0.2s;
  }}
  .link.highlighted {{ stroke: var(--accent2); stroke-opacity: 1; stroke-width: 2; }}
  .link.gap-link {{ stroke: var(--gap-color); stroke-opacity: 0.4; }}

  .node circle {{
    stroke: rgba(255,255,255,0.08);
    stroke-width: 1.2;
    transition: r 0.2s, stroke 0.2s;
    cursor: pointer;
  }}
  .node circle.gap {{ stroke: var(--gap-color); stroke-width: 2; stroke-dasharray: 3,2; }}
  .node:hover circle {{ stroke: rgba(255,255,255,0.4); stroke-width: 2; }}
  .node.selected circle {{ stroke: var(--accent); stroke-width: 2.5; }}

  .node-label {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    fill: var(--text-dim);
    pointer-events: none;
    transition: fill 0.2s;
  }}
  .node:hover .node-label,
  .node.selected .node-label {{ fill: var(--text); }}

  /* ── Right panel ────────────────────────────────────── */
  .panel {{
    width: 300px;
    background: var(--surface);
    border-left: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    flex-shrink: 0;
  }}

  .panel-tabs {{
    display: flex;
    border-bottom: 1px solid var(--border);
  }}

  .tab {{
    flex: 1;
    padding: 10px;
    font-size: 0.7rem;
    text-align: center;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-dim);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all 0.2s;
    font-family: 'JetBrains Mono', monospace;
  }}
  .tab.active {{ color: var(--accent); border-bottom-color: var(--accent); }}

  .panel-content {{
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    font-size: 0.88rem;
    line-height: 1.6;
  }}
  .panel-content::-webkit-scrollbar {{ width: 4px; }}
  .panel-content::-webkit-scrollbar-thumb {{ background: var(--border); }}

  /* ── Detail panel ───────────────────────────────────── */
  #detail-panel .concept-name {{
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--accent);
    margin-bottom: 4px;
  }}

  #detail-panel .concept-type {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-dim);
    margin-bottom: 12px;
  }}

  #detail-panel .definition {{
    color: var(--text);
    margin-bottom: 16px;
    font-style: italic;
  }}

  #detail-panel h4 {{
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-dim);
    margin-bottom: 8px;
    margin-top: 14px;
    font-family: 'JetBrains Mono', monospace;
  }}

  .connection-item {{
    padding: 5px 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.82rem;
  }}
  .connection-item .rel-name {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    color: var(--accent2);
  }}
  .connection-item .rel-target {{
    color: var(--text);
    cursor: pointer;
  }}
  .connection-item .rel-target:hover {{ color: var(--accent); }}

  .empty-state {{
    color: var(--text-dim);
    font-style: italic;
    font-size: 0.82rem;
    padding: 20px 0;
    text-align: center;
  }}

  /* ── Gap panel ──────────────────────────────────────── */
  .gap-section h4 {{
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--gap-color);
    margin-bottom: 8px;
    margin-top: 16px;
    font-family: 'JetBrains Mono', monospace;
  }}
  .gap-section h4:first-child {{ margin-top: 0; }}

  .gap-item {{
    padding: 8px 10px;
    background: rgba(255, 107, 107, 0.06);
    border-left: 2px solid var(--gap-color);
    margin-bottom: 8px;
    font-size: 0.82rem;
  }}

  .gap-item .gap-title {{ color: var(--text); font-weight: 600; }}
  .gap-item .gap-desc {{ color: var(--text-dim); font-size: 0.78rem; margin-top: 3px; }}

  .question-item {{
    padding: 8px 10px;
    background: rgba(58, 111, 216, 0.06);
    border-left: 2px solid var(--accent2);
    margin-bottom: 8px;
    font-size: 0.82rem;
    color: var(--text);
  }}
  .question-item .priority {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    text-transform: uppercase;
    color: var(--accent2);
    margin-bottom: 2px;
  }}

  /* ── Legend ─────────────────────────────────────────── */
  .legend {{
    padding: 10px 16px;
    border-top: 1px solid var(--border);
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }}
  .legend-item {{
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 0.68rem;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-dim);
  }}
  .legend-dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }}

  /* ── Tooltip ────────────────────────────────────────── */
  #tooltip {{
    position: fixed;
    background: var(--surface2);
    border: 1px solid var(--border);
    padding: 8px 12px;
    font-size: 0.78rem;
    max-width: 240px;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s;
    z-index: 100;
    line-height: 1.5;
  }}
  #tooltip.visible {{ opacity: 1; }}
  #tooltip .tip-name {{ color: var(--accent); font-weight: 600; margin-bottom: 4px; }}
  #tooltip .tip-def {{ color: var(--text-dim); font-style: italic; }}

  /* ── Controls ───────────────────────────────────────── */
  .controls {{
    position: absolute;
    bottom: 16px;
    left: 16px;
    display: flex;
    gap: 6px;
  }}
  .ctrl-btn {{
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text-dim);
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    font-size: 1rem;
    transition: all 0.2s;
  }}
  .ctrl-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
</style>
</head>
<body>

<header>
  <div class="brand">
    <h1>⚖ Legal Knowledge Graph</h1>
    <span>{title} — {date}</span>
  </div>
  <div class="header-right">
    <div class="stats">
      <span><b id="stat-nodes">0</b> concepts</span>
      <span><b id="stat-links">0</b> connections</span>
      <span><b id="stat-gaps">0</b> gaps</span>
    </div>
    <input id="search" type="text" placeholder="Search concepts..." />
  </div>
</header>

<div class="main">
  <div id="canvas">
    <svg id="graph"></svg>
    <div class="controls">
      <div class="ctrl-btn" id="zoom-in" title="Zoom in">+</div>
      <div class="ctrl-btn" id="zoom-out" title="Zoom out">−</div>
      <div class="ctrl-btn" id="zoom-reset" title="Reset view">⊙</div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-tabs">
      <div class="tab active" data-tab="detail">Concept</div>
      <div class="tab" data-tab="gaps">Gaps</div>
      <div class="tab" data-tab="legend">Legend</div>
    </div>

    <div class="panel-content" id="detail-panel">
      <div class="empty-state">Click a concept node<br>to explore its details</div>
    </div>

    <div class="panel-content" id="gaps-panel" style="display:none">
      <div class="gap-section" id="gaps-content">
        <div class="empty-state">Gap analysis loading...</div>
      </div>
    </div>

    <div class="panel-content" id="legend-panel" style="display:none">
      <!-- populated by JS -->
    </div>

    <div class="legend" id="mini-legend"></div>
  </div>
</div>

<div id="tooltip">
  <div class="tip-name" id="tip-name"></div>
  <div class="tip-def" id="tip-def"></div>
</div>

<script>
const GRAPH_DATA = {graph_data_json};

const typeColors = {type_colors_json};

// ── Init stats ─────────────────────────────────────────
document.getElementById('stat-nodes').textContent = GRAPH_DATA.nodes.length;
document.getElementById('stat-links').textContent = GRAPH_DATA.links.length;
const gapCount = (GRAPH_DATA.gaps?.missing_definitions?.length || 0) +
                 (GRAPH_DATA.gaps?.knowledge_gaps?.length || 0);
document.getElementById('stat-gaps').textContent = gapCount;

// ── Tabs ──────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {{
  tab.addEventListener('click', () => {{
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel-content').forEach(p => p.style.display = 'none');
    tab.classList.add('active');
    document.getElementById(tab.dataset.tab + '-panel').style.display = 'block';
  }});
}});

// ── Gap panel ─────────────────────────────────────────
function buildGapsPanel() {{
  const gaps = GRAPH_DATA.gaps || {{}};
  const container = document.getElementById('gaps-content');
  let html = '';

  if (gaps.missing_definitions?.length) {{
    html += '<h4>⚠ Missing Definitions</h4>';
    gaps.missing_definitions.forEach(g => {{
      html += `<div class="gap-item"><div class="gap-title">${{g.concept}}</div><div class="gap-desc">${{g.reason}}</div></div>`;
    }});
  }}

  if (gaps.knowledge_gaps?.length) {{
    html += '<h4>◌ Knowledge Gaps</h4>';
    gaps.knowledge_gaps.forEach(g => {{
      html += `<div class="gap-item"><div class="gap-title">${{g.area}}</div><div class="gap-desc">${{g.description}}</div></div>`;
    }});
  }}

  if (gaps.research_questions?.length) {{
    html += '<h4>? Research Questions</h4>';
    gaps.research_questions.forEach(q => {{
      html += `<div class="question-item"><div class="priority">${{q.priority}}</div>${{q.question}}</div>`;
    }});
  }}

  if (!html) html = '<div class="empty-state">No significant gaps identified</div>';
  container.innerHTML = html;
}}
buildGapsPanel();

// ── Legend panel ──────────────────────────────────────
function buildLegendPanel() {{
  const panel = document.getElementById('legend-panel');
  const mini = document.getElementById('mini-legend');
  let html = '<h4 style="font-family:monospace;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.1em;color:var(--text-dim);margin-bottom:12px;">Node Types</h4>';
  let miniHtml = '';
  Object.entries(typeColors).forEach(([type, color]) => {{
    html += `<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
      <div style="width:12px;height:12px;border-radius:50%;background:${{color}};flex-shrink:0"></div>
      <span style="font-size:0.85rem;text-transform:capitalize;">${{type}}</span>
    </div>`;
    miniHtml += `<div class="legend-item"><div class="legend-dot" style="background:${{color}}"></div>${{type}}</div>`;
  }});
  html += '<div style="margin-top:16px;font-size:0.78rem;color:var(--text-dim);">';
  html += '<div style="margin-bottom:6px;"><span style="border:1px dashed #ff6b6b;padding:1px 5px;font-size:0.7rem;">dashed ring</span> = knowledge gap</div>';
  html += '<div>Node size = importance (high/medium/low)</div></div>';
  panel.innerHTML = html;
  mini.innerHTML = miniHtml;
}}
buildLegendPanel();

// ── D3 Graph ──────────────────────────────────────────
const svg = d3.select('#graph');
const container = d3.select('#canvas');
let width = container.node().offsetWidth;
let height = container.node().offsetHeight;

const g = svg.append('g');

// Zoom
const zoom = d3.zoom()
  .scaleExtent([0.1, 4])
  .on('zoom', (event) => g.attr('transform', event.transform));
svg.call(zoom);

// Controls
document.getElementById('zoom-in').addEventListener('click', () =>
  svg.transition().call(zoom.scaleBy, 1.4));
document.getElementById('zoom-out').addEventListener('click', () =>
  svg.transition().call(zoom.scaleBy, 0.7));
document.getElementById('zoom-reset').addEventListener('click', () =>
  svg.transition().call(zoom.transform, d3.zoomIdentity));

// Build lookup
const gapConcepts = new Set((GRAPH_DATA.gaps?.missing_definitions || []).map(g => g.concept));

// Links
const link = g.append('g').attr('class', 'links')
  .selectAll('.link')
  .data(GRAPH_DATA.links)
  .join('line')
  .attr('class', 'link');

// Nodes
const node = g.append('g').attr('class', 'nodes')
  .selectAll('.node')
  .data(GRAPH_DATA.nodes)
  .join('g')
  .attr('class', 'node')
  .call(d3.drag()
    .on('start', dragStarted)
    .on('drag', dragged)
    .on('end', dragEnded));

node.append('circle')
  .attr('r', d => d.size)
  .attr('fill', d => d.color)
  .attr('class', d => gapConcepts.has(d.id) ? 'gap' : '');

node.append('text')
  .attr('class', 'node-label')
  .attr('x', d => d.size + 3)
  .attr('y', 4)
  .text(d => d.id.length > 22 ? d.id.slice(0, 20) + '…' : d.id);

// Simulation
const simulation = d3.forceSimulation(GRAPH_DATA.nodes)
  .force('link', d3.forceLink(GRAPH_DATA.links).id(d => d.id).distance(80).strength(0.4))
  .force('charge', d3.forceManyBody().strength(-200))
  .force('center', d3.forceCenter(width / 2, height / 2))
  .force('collision', d3.forceCollide(d => d.size + 8))
  .on('tick', ticked);

function ticked() {{
  link
    .attr('x1', d => d.source.x)
    .attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x)
    .attr('y2', d => d.target.y);
  node.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
}}

// ── Tooltip ───────────────────────────────────────────
const tooltip = document.getElementById('tooltip');
node
  .on('mouseover', (event, d) => {{
    document.getElementById('tip-name').textContent = d.id;
    document.getElementById('tip-def').textContent = d.definition?.slice(0, 120) || '';
    tooltip.classList.add('visible');
  }})
  .on('mousemove', (event) => {{
    tooltip.style.left = (event.clientX + 14) + 'px';
    tooltip.style.top = (event.clientY - 10) + 'px';
  }})
  .on('mouseout', () => tooltip.classList.remove('visible'));

// ── Click to select ───────────────────────────────────
let selectedNode = null;
const linksByNode = {{}};
GRAPH_DATA.links.forEach(l => {{
  const src = typeof l.source === 'object' ? l.source.id : l.source;
  const tgt = typeof l.target === 'object' ? l.target.id : l.target;
  if (!linksByNode[src]) linksByNode[src] = [];
  if (!linksByNode[tgt]) linksByNode[tgt] = [];
  linksByNode[src].push({{ other: tgt, rel: l.relationship, direction: 'out' }});
  linksByNode[tgt].push({{ other: src, rel: l.relationship, direction: 'in' }});
}});

node.on('click', (event, d) => {{
  event.stopPropagation();
  selectedNode = d.id;

  // Update node classes
  node.classed('selected', n => n.id === d.id);

  // Highlight connected links
  link.classed('highlighted', l => {{
    const src = typeof l.source === 'object' ? l.source.id : l.source;
    const tgt = typeof l.target === 'object' ? l.target.id : l.target;
    return src === d.id || tgt === d.id;
  }});

  // Show detail panel
  showDetail(d);

  // Switch to detail tab
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel-content').forEach(p => p.style.display = 'none');
  document.querySelector('[data-tab="detail"]').classList.add('active');
  document.getElementById('detail-panel').style.display = 'block';
}});

svg.on('click', () => {{
  selectedNode = null;
  node.classed('selected', false);
  link.classed('highlighted', false);
  document.getElementById('detail-panel').innerHTML =
    '<div class="empty-state">Click a concept node<br>to explore its details</div>';
}});

function showDetail(d) {{
  const connections = linksByNode[d.id] || [];
  const isGap = gapConcepts.has(d.id);
  let html = `
    <div class="concept-name">${{d.id}}</div>
    <div class="concept-type">${{d.type}} · ${{d.importance}} importance${{isGap ? ' · ⚠ gap' : ''}}</div>
    <div class="definition">${{d.definition || 'No definition available.'}}</div>
  `;

  if (connections.length) {{
    html += '<h4>Connections (' + connections.length + ')</h4>';
    connections.forEach(c => {{
      html += `<div class="connection-item">
        <div class="rel-name">${{c.rel}}</div>
        <div class="rel-target" onclick="selectNodeById('${{c.other}}')">${{c.other}}</div>
      </div>`;
    }});
  }} else {{
    html += '<h4>Connections</h4><div class="empty-state" style="padding:8px 0">No connections found</div>';
  }}

  document.getElementById('detail-panel').innerHTML = html;
}}

window.selectNodeById = function(id) {{
  const d = GRAPH_DATA.nodes.find(n => n.id === id);
  if (d) {{
    node.classed('selected', n => n.id === id);
    link.classed('highlighted', l => {{
      const src = typeof l.source === 'object' ? l.source.id : l.source;
      const tgt = typeof l.target === 'object' ? l.target.id : l.target;
      return src === id || tgt === id;
    }});
    showDetail(d);
    // Pan to node
    if (d.x && d.y) {{
      svg.transition().duration(600)
        .call(zoom.transform, d3.zoomIdentity
          .translate(width/2 - d.x, height/2 - d.y));
    }}
  }}
}};

// ── Search ────────────────────────────────────────────
document.getElementById('search').addEventListener('input', function() {{
  const q = this.value.toLowerCase().trim();
  if (!q) {{
    node.selectAll('circle').attr('fill', d => d.color).attr('opacity', 1);
    node.selectAll('.node-label').attr('opacity', 1);
    link.attr('opacity', 0.6);
    return;
  }}
  node.each(function(d) {{
    const match = d.id.toLowerCase().includes(q);
    d3.select(this).selectAll('circle').attr('opacity', match ? 1 : 0.1);
    d3.select(this).selectAll('.node-label').attr('opacity', match ? 1 : 0.1);
  }});
  link.attr('opacity', 0.1);
}});

// ── Drag ──────────────────────────────────────────────
function dragStarted(event, d) {{
  if (!event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x; d.fy = d.y;
}}
function dragged(event, d) {{
  d.fx = event.x; d.fy = event.y;
}}
function dragEnded(event, d) {{
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null; d.fy = null;
}}

// ── Resize ────────────────────────────────────────────
window.addEventListener('resize', () => {{
  width = container.node().offsetWidth;
  height = container.node().offsetHeight;
  simulation.force('center', d3.forceCenter(width / 2, height / 2)).restart();
}});
</script>
</body>
</html>"""


def generate_html(
    graph_data: dict,
    output_path: Path,
    title: str = "Legal Knowledge Graph"
) -> None:
    """Write the self-contained HTML visualisation."""
    html = HTML_TEMPLATE.format(
        title=title,
        date=date.today().isoformat(),
        graph_data_json=json.dumps(graph_data, ensure_ascii=False),
        type_colors_json=json.dumps(TYPE_COLORS, ensure_ascii=False)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
