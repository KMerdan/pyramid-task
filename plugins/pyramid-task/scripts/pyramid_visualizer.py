from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pyramid_core import (
    compile_project,
    graph_snapshot,
    lifecycle_status,
    load_assurance_bundle,
    load_json,
    load_project,
    project_paths,
)


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pyramid Task Map</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f7f8fb;
    --fg: #18202d;
    --muted: #657084;
    --panel: #ffffff;
    --border: #ccd3df;
    --edge: #9aa4b5;
    --ready: #12a594;
    --working: #2878d0;
    --implemented: #8a63d2;
    --rework: #d45d18;
    --verified: #258a4b;
    --blocked: #c43d4e;
    --locked: #7c8798;
    --audit: #c57a13;
    --focus: #2867c7;
    --assurance-covered: #1b9a72;
    --assurance-blocked: #e05a36;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #11151d;
      --fg: #edf1f7;
      --muted: #a9b2c1;
      --panel: #191f2a;
      --border: #3b4556;
      --edge: #596579;
      --ready: #39c6b4;
      --working: #66a9ef;
      --implemented: #aa8ee8;
      --rework: #ff985f;
      --verified: #61c782;
      --blocked: #ed7180;
      --locked: #909bad;
      --audit: #e3a74d;
      --focus: #8dc3ff;
      --assurance-covered: #4fd3a8;
      --assurance-blocked: #ff8d69;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.45 system-ui, sans-serif; }
  main { max-width: 1500px; margin: 0 auto; padding: 18px; }
  h1 { margin: 0 0 4px; font-size: 1.35rem; font-weight: 600; }
  .meta { color: var(--muted); margin-bottom: 14px; }
  .assurance-panel { display: none; margin: 0 0 12px; padding: 10px 12px; background: var(--panel); border: 1px solid var(--border); border-radius: 9px; }
  .assurance-panel.visible { display: block; }
  .assurance-panel strong { margin-right: 8px; }
  .assurance-panel.blocked { border-color: var(--assurance-blocked); }
  .assurance-panel.ready { border-color: var(--assurance-covered); }
  .toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: end; margin-bottom: 12px; }
  .group { display: flex; gap: 6px; flex-wrap: wrap; }
  button, select { font: inherit; color: var(--fg); background: var(--panel); border: 1px solid var(--border); border-radius: 7px; padding: 7px 10px; }
  button { cursor: pointer; }
  button[aria-pressed="true"] { border-color: var(--focus); box-shadow: 0 0 0 2px color-mix(in srgb, var(--focus) 30%, transparent); }
  label { display: grid; gap: 3px; color: var(--muted); font-size: .82rem; }
  select { min-width: 210px; }
  .layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, 340px); gap: 14px; align-items: start; }
  .plot, .detail { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; }
  .plot { min-width: 0; overflow: auto; }
  svg { display: block; width: 100%; min-width: 680px; height: auto; }
  .detail { padding: 14px; position: sticky; top: 12px; }
  .detail h2 { margin: 0 0 6px; font-size: 1.08rem; }
  .detail dl { display: grid; grid-template-columns: max-content 1fr; gap: 5px 9px; margin: 12px 0; }
  .detail dt { color: var(--muted); }
  .detail dd { margin: 0; overflow-wrap: anywhere; }
  .detail ul { margin: 5px 0 12px; padding-left: 20px; }
  .detail a { color: var(--focus); }
  .node { cursor: pointer; }
  .node text { fill: var(--fg); font-size: 12px; pointer-events: none; }
  .node .mark { fill: var(--locked); stroke: var(--panel); stroke-width: 2; }
  .node.ready .mark { fill: var(--ready); }
  .node.working .mark { fill: var(--working); }
  .node.implemented .mark { fill: var(--implemented); }
  .node.needs-rework .mark { fill: var(--rework); }
  .node.verified .mark { fill: var(--verified); }
  .node.blocked .mark { fill: var(--blocked); }
  .node.not-selected { opacity: .34; }
  .node.audit .mark { stroke: var(--audit); stroke-width: 4; }
  .node.work-package .mark { stroke: var(--focus); stroke-width: 4; }
  .node.verification-pending .verify { stroke: var(--audit); stroke-dasharray: 4 3; }
  .node.verification-failed .verify { stroke: var(--blocked); }
  .node.verification-passed .verify { stroke: var(--verified); }
  .node .verify { fill: none; stroke: transparent; stroke-width: 3; }
  .node .assure { fill: none; stroke: transparent; stroke-width: 3; stroke-dasharray: 3 3; }
  .node.assurance-covered .assure { stroke: var(--assurance-covered); }
  .node.assurance-blocked .assure { stroke: var(--assurance-blocked); }
  .node.assurance-hidden .assure { stroke: transparent; }
  .node.selected .verify { stroke: var(--focus); stroke-width: 4; }
  .edge { stroke: var(--edge); stroke-width: 1.25; fill: none; opacity: .65; }
  .edge.dependency { stroke-dasharray: 5 4; }
  .edge.highlight { stroke: var(--focus); stroke-width: 2.5; opacity: 1; }
  .level-label { fill: var(--muted); font-size: 12px; }
  .legend { display: flex; flex-wrap: wrap; gap: 10px 16px; padding: 10px 12px; color: var(--muted); border-top: 1px solid var(--border); }
  .swatch { display: inline-flex; align-items: center; gap: 5px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--locked); }
  .dot.ready { background: var(--ready); } .dot.working { background: var(--working); }
  .dot.verified { background: var(--verified); } .dot.blocked { background: var(--blocked); }
  .dot.rework { background: var(--rework); }
  @media (max-width: 920px) { .layout { grid-template-columns: 1fr; } .detail { position: static; } }
  @media (prefers-reduced-motion: no-preference) { .node, .edge { transition: opacity .18s, transform .18s; } }
</style>
</head>
<body>
<main>
  <h1 id="page-title"></h1>
  <div class="meta" id="page-meta"></div>
  <div class="assurance-panel" id="assurance-panel"></div>
  <div class="toolbar">
    <div class="group" aria-label="Graph view">
      <button type="button" data-view="star" aria-pressed="true">Star</button>
      <button type="button" data-view="pyramid" aria-pressed="false">Pyramid</button>
      <button type="button" data-view="dependency" aria-pressed="false">Dependencies</button>
    </div>
    <div class="group" aria-label="Status filter">
      <button type="button" data-filter="all" aria-pressed="true">All</button>
      <button type="button" data-filter="ready" aria-pressed="false">Ready</button>
      <button type="button" data-filter="working" aria-pressed="false">Working</button>
      <button type="button" data-filter="needs-rework" aria-pressed="false">Rework</button>
      <button type="button" data-filter="blocked" aria-pressed="false">Blocked</button>
      <button type="button" data-filter="audit" aria-pressed="false">Audit</button>
      <button type="button" data-filter="work-package" aria-pressed="false">Work packages</button>
      <button type="button" data-filter="verified" aria-pressed="false">Verified</button>
      <button type="button" data-filter="assurance-blocked" aria-pressed="false">Assurance blocked</button>
    </div>
    <div class="group" aria-label="Assurance overlay">
      <button type="button" data-overlay="none" aria-pressed="false">No assurance</button>
      <button type="button" data-overlay="status" aria-pressed="true">Assurance status</button>
      <button type="button" data-overlay="impact" aria-pressed="false">Impact</button>
      <button type="button" data-overlay="inspection" aria-pressed="false">Inspections</button>
      <button type="button" data-overlay="finding" aria-pressed="false">Findings</button>
      <button type="button" data-overlay="drift" aria-pressed="false">Scope drift</button>
    </div>
    <label>Selected node<select id="node-select"></select></label>
  </div>
  <div class="layout">
    <section class="plot" aria-label="Task graph">
      <svg id="graph" viewBox="0 0 1000 720" role="img" aria-labelledby="graph-title graph-desc">
        <title id="graph-title">Pyramid task graph</title>
        <desc id="graph-desc">Interactive graph of task outcomes, dependencies, execution, verification, and blockers.</desc>
        <g id="level-layer"></g><g id="edge-layer"></g><g id="node-layer"></g>
      </svg>
      <div class="legend" aria-label="Status legend">
        <span class="swatch"><span class="dot ready"></span>Ready</span>
        <span class="swatch"><span class="dot working"></span>Working</span>
        <span class="swatch"><span class="dot rework"></span>Needs rework</span>
        <span class="swatch"><span class="dot verified"></span>Verified</span>
        <span class="swatch"><span class="dot blocked"></span>Blocked</span>
        <span class="swatch"><span class="dot"></span>Locked or inactive</span>
        <span class="swatch">Dashed ring: brownfield assurance</span>
      </div>
    </section>
    <aside class="detail" id="detail" aria-live="polite"></aside>
  </div>
</main>
<script id="pyramid-data" type="application/json">__GRAPH_DATA__</script>
<script>
(() => {
  const data = JSON.parse(document.getElementById('pyramid-data').textContent);
  const svg = document.getElementById('graph');
  const nodeLayer = document.getElementById('node-layer');
  const edgeLayer = document.getElementById('edge-layer');
  const levelLayer = document.getElementById('level-layer');
  const detail = document.getElementById('detail');
  const select = document.getElementById('node-select');
  const assurancePanel = document.getElementById('assurance-panel');
  const nodeById = new Map(data.nodes.map(node => [node.id, node]));
  let view = 'star';
  let filter = 'all';
  let overlay = data.assurance ? 'status' : 'none';
  let selected = data.intent.id;
  let positions = new Map();
  let canvas = {width: 1000, height: 720};

  document.getElementById('page-title').textContent = data.title;
  const projectMode = data.project?.mode || 'legacy';
  document.getElementById('page-meta').textContent = `${projectMode} · ${data.lifecycle.status} · revision ${data.revision} · graph ${data.graph_version} · ${data.summary.verified_primary_nodes}/${data.summary.primary_nodes} primary nodes verified`;
  if (data.assurance) {
    const summary = data.assurance.summary;
    assurancePanel.classList.add('visible', summary.status);
    assurancePanel.innerHTML = `<strong>Change assurance: ${esc(summary.status)}</strong> baseline r${summary.baseline_revision} (${esc(summary.baseline_status)}) · ${summary.sufficiently_inspected_assets}/${summary.impacted_assets} impacted assets sufficiently inspected · ${summary.open_scope_drift} open drift · ${summary.open_material_findings} material findings`;
  }
  data.nodes.forEach(node => {
    const option = document.createElement('option');
    option.value = node.id;
    option.textContent = `${node.id} — ${node.title}`;
    select.appendChild(option);
  });
  select.value = selected;

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  }
  function starPoints(cx, cy, outer, inner) {
    const points = [];
    for (let i = 0; i < 10; i++) {
      const angle = -Math.PI / 2 + i * Math.PI / 5;
      const radius = i % 2 === 0 ? outer : inner;
      points.push(`${cx + Math.cos(angle) * radius},${cy + Math.sin(angle) * radius}`);
    }
    return points.join(' ');
  }
  function visible(node) {
    if (filter === 'all') return true;
    if (filter === 'audit') return node.kind === 'audit';
    if (filter === 'work-package') return node.kind === 'work-package';
    if (filter === 'assurance-blocked') return node.assurance?.status === 'blocked';
    if (filter === 'blocked') return node.availability === 'blocked' || node.availability === 'locked';
    return node.availability === filter;
  }
  function computePositions() {
    const map = new Map();
    if (view === 'star') {
      const groups = new Map();
      data.nodes.forEach(node => {
        if (!groups.has(node.level)) groups.set(node.level, []);
        groups.get(node.level).push(node);
      });
      const levels = [...groups.keys()].sort((a,b) => a-b);
      const radii = new Map();
      let previous = 0;
      levels.filter(level => level > 0).forEach(level => {
        const count = groups.get(level).length;
        const circumferenceRadius = count * 92 / (Math.PI * 2);
        const radius = Math.max(92 + (level - 1) * 108, previous + 108, circumferenceRadius);
        radii.set(level, radius);
        previous = radius;
      });
      const outer = Math.max(270, previous);
      const width = Math.max(1000, outer * 2 + 190);
      const height = width;
      const cx = width / 2, cy = height / 2;
      levels.forEach(level => {
        const nodes = groups.get(level);
        nodes.sort((a,b) => a.wave-b.wave || a.id.localeCompare(b.id));
        if (level === 0) { nodes.forEach(node => map.set(node.id, {x: cx, y: cy})); return; }
        const radius = radii.get(level);
        nodes.forEach((node, index) => {
          const angle = -Math.PI / 2 + (index * Math.PI * 2 / nodes.length) + level * 0.17;
          map.set(node.id, {x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius});
        });
      });
      return {map, width, height};
    } else if (view === 'pyramid') {
      const groups = new Map();
      data.nodes.forEach(node => {
        if (!groups.has(node.level)) groups.set(node.level, []);
        groups.get(node.level).push(node);
      });
      const levels = [...groups.keys()].sort((a,b) => a-b);
      const largestLevel = Math.max(...levels.map(level => groups.get(level).length));
      const width = Math.max(1000, largestLevel * 155 + 140);
      levels.forEach((level, levelIndex) => {
        const nodes = groups.get(level).sort((a,b) => a.wave-b.wave || a.id.localeCompare(b.id));
        const span = Math.max(140, (nodes.length - 1) * 150);
        nodes.forEach((node, index) => {
          const x = nodes.length === 1 ? width/2 : width/2 - span/2 + index * span/(nodes.length-1);
          map.set(node.id, {x, y: 85 + levelIndex * 145});
        });
      });
      return {map, width, height: Math.max(430, 155 + (levels.length - 1) * 145)};
    } else {
      const workstreams = [...new Set(data.nodes.map(node => node.workstream))].sort();
      const waves = [...new Set(data.nodes.map(node => node.wave))].sort((a,b) => a-b);
      const rowCounts = new Map();
      data.nodes.slice().sort((a,b) => a.id.localeCompare(b.id)).forEach(node => {
        const key = `${node.wave}:${node.workstream}`;
        const offset = rowCounts.get(key) || 0;
        rowCounts.set(key, offset + 1);
        map.set(node.id, {x: 110 + waves.indexOf(node.wave) * 190, y: 80 + workstreams.indexOf(node.workstream) * 125 + offset * 32});
      });
      return {
        map,
        width: Math.max(1000, 220 + Math.max(0, waves.length - 1) * 190),
        height: Math.max(430, 130 + workstreams.length * 125)
      };
    }
  }
  function render() {
    const layout = computePositions();
    positions = layout.map;
    canvas = {width: layout.width, height: layout.height};
    svg.setAttribute('viewBox', `0 0 ${canvas.width} ${canvas.height}`);
    svg.style.minWidth = `${Math.max(680, canvas.width)}px`;
    edgeLayer.replaceChildren(); nodeLayer.replaceChildren(); levelLayer.replaceChildren();
    const highlight = new Set(nodeById.get(selected)?.goal_trace || []);
    data.edges.forEach(edge => {
      const a = positions.get(edge.from), b = positions.get(edge.to);
      if (!a || !b) return;
      const sourceVisible = visible(nodeById.get(edge.from));
      const targetVisible = visible(nodeById.get(edge.to));
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', a.x); line.setAttribute('y1', a.y);
      line.setAttribute('x2', b.x); line.setAttribute('y2', b.y);
      line.setAttribute('class', `edge ${edge.type === 'contributes-to' ? '' : 'dependency'} ${highlight.has(edge.from) && highlight.has(edge.to) ? 'highlight' : ''}`);
      if (!sourceVisible || !targetVisible) line.style.opacity = '.08';
      edgeLayer.appendChild(line);
    });
    data.nodes.forEach(node => {
      const p = positions.get(node.id);
      const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      const classes = ['node', node.availability, node.kind === 'audit' ? 'audit' : '', node.kind === 'work-package' ? 'work-package' : '', `verification-${node.state.verification}`, node.selection !== 'primary' ? 'not-selected' : '', node.id === selected ? 'selected' : ''].filter(Boolean);
      const assuranceStatus = node.assurance?.status;
      if (assuranceStatus) classes.push(`assurance-${assuranceStatus}`);
      const overlayRecords = overlay === 'impact' ? node.assurance?.impact_ids : overlay === 'inspection' ? node.assurance?.inspection_ids : overlay === 'finding' ? node.assurance?.finding_ids : overlay === 'drift' ? node.assurance?.scope_drift_ids : null;
      if (overlay === 'none' || (overlayRecords && !overlayRecords.length)) classes.push('assurance-hidden');
      group.setAttribute('class', classes.join(' '));
      group.dataset.id = node.id;
      group.style.opacity = visible(node) ? '' : '.08';
      const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      title.textContent = `${node.id}: ${node.title}; ${node.availability}; verification ${node.state.verification}`;
      group.appendChild(title);
      const ring = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      ring.setAttribute('class', 'verify'); ring.setAttribute('cx', p.x); ring.setAttribute('cy', p.y); ring.setAttribute('r', node.level === 0 ? 25 : 20);
      group.appendChild(ring);
      const assure = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      assure.setAttribute('class', 'assure'); assure.setAttribute('cx', p.x); assure.setAttribute('cy', p.y); assure.setAttribute('r', node.level === 0 ? 30 : 25);
      group.appendChild(assure);
      const mark = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      mark.setAttribute('class', 'mark'); mark.setAttribute('points', starPoints(p.x, p.y, node.level === 0 ? 22 : 17, node.level === 0 ? 10 : 8));
      group.appendChild(mark);
      const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      label.setAttribute('x', p.x); label.setAttribute('y', p.y + 34); label.setAttribute('text-anchor', 'middle');
      label.textContent = node.id.length > 18 ? node.id.slice(0, 17) + '…' : node.id;
      group.appendChild(label);
      group.addEventListener('click', () => choose(node.id));
      nodeLayer.appendChild(group);
    });
    renderDetail();
  }
  function list(items, formatter = item => item) {
    return items?.length ? `<ul>${items.map(item => `<li>${formatter(item)}</li>`).join('')}</ul>` : '<p>None</p>';
  }
  function renderDetail() {
    const node = nodeById.get(selected);
    if (!node) return;
    const source = node.source_path ? `<a href="../${esc(node.source_path)}">Open generated task</a>` : '';
    const assurance = node.assurance;
    const assuranceDetail = assurance ? `
      <strong>Assurance status</strong><p>${esc(assurance.status)}</p>
      <strong>Affected assets</strong>${list(assurance.asset_ids, item => `<code>${esc(item)}</code>`)}
      <strong>Impact records</strong>${list(assurance.impact_ids, item => `<code>${esc(item)}</code>`)}
      <strong>Inspections</strong>${list(assurance.inspection_ids, item => `<code>${esc(item)}</code>`)}
      <strong>Findings</strong>${list(assurance.finding_ids, item => `<code>${esc(item)}</code>`)}
      <strong>Scope drift</strong>${list(assurance.scope_drift_ids, item => `<code>${esc(item)}</code>`)}
      <strong>Assurance blockers</strong>${list(assurance.blockers, item => esc(item))}` : '';
    detail.innerHTML = `
      <h2>${esc(node.id)}: ${esc(node.title)}</h2>
      <p>${esc(node.summary)}</p>
      <dl>
        <dt>Kind</dt><dd>${esc(node.kind)}</dd><dt>Selection</dt><dd>${esc(node.selection)}</dd>
        <dt>Level / wave</dt><dd>${node.level} / ${node.wave}</dd><dt>Workstream</dt><dd>${esc(node.workstream)}</dd>
        <dt>Execution</dt><dd>${esc(node.state.execution)}</dd><dt>Verification</dt><dd>${esc(node.state.verification)}</dd>
        <dt>Health</dt><dd>${esc(node.state.health)}</dd><dt>Availability</dt><dd>${esc(node.availability)}</dd>
        <dt>Owner</dt><dd>${esc(node.state.owner || '—')}</dd>
        <dt>Plan lifecycle</dt><dd>${esc(data.lifecycle.status)}</dd>
      </dl>
      <strong>Goal trace</strong>${list(node.goal_trace, item => esc(item))}
      <strong>Parent nodes</strong>${list(node.parents, item => esc(item))}
      <strong>Child nodes</strong>${list(node.children, item => esc(item))}
      <strong>Blocked by</strong>${list(node.blocked_by, item => esc(item))}
      <strong>Audit gates</strong>${list(node.audit_gates, item => esc(item))}
      <strong>Acceptance</strong>${list(node.acceptance_criteria, item => `<code>${esc(item.id)}</code> — ${esc(item.description)}`)}
      ${assuranceDetail}
      ${source}`;
  }
  function choose(id) { selected = id; select.value = id; render(); }
  select.addEventListener('change', event => choose(event.target.value));
  document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => {
    view = button.dataset.view;
    document.querySelectorAll('[data-view]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    render();
  }));
  document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
    filter = button.dataset.filter;
    document.querySelectorAll('[data-filter]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    render();
  }));
  document.querySelectorAll('[data-overlay]').forEach(button => {
    if (!data.assurance) button.disabled = true;
    button.setAttribute('aria-pressed', String(button.dataset.overlay === overlay));
    button.addEventListener('click', () => {
      overlay = button.dataset.overlay;
      document.querySelectorAll('[data-overlay]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      render();
    });
  });
  render();
})();
</script>
</body>
</html>
"""


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def render_visualization(project: str | Path, output: str | Path | None = None) -> dict[str, Any]:
    paths = project_paths(project)
    _, plan, state = load_project(project)
    manifest, baseline, assurance = load_assurance_bundle(paths, plan)
    if lifecycle_status(state) == "archived":
        graph = (
            load_json(paths["graph"])
            if paths["graph"].exists()
            else graph_snapshot(plan, state, baseline, assurance, manifest)
        )
    else:
        compile_project(project)
        graph = load_json(paths["graph"])
    graph_json = json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__GRAPH_DATA__", graph_json)
    destination = Path(output).expanduser().resolve() if output else paths["html"]
    write_text_atomic(destination, html)
    return {
        "status": "rendered",
        "output": str(destination),
        "graph_version": graph["graph_version"],
        "nodes": len(graph["nodes"]),
        "views": ["star", "pyramid", "dependency"],
        "overlays": ["assurance-status", "impact", "inspection", "finding", "scope-drift"],
    }
