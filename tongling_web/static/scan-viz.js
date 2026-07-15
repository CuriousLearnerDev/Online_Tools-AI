(function () {
  'use strict';

  const NODE_W = 168;
  const NODE_H = 64;
  const GAP_X = 36;
  const GAP_Y = 48;
  const PAD = 48;
  const LANE_W = NODE_W + GAP_X + 24;

  const PHASE_COL = { target: 0, recon: 1, vuln: 2, exploit: 3, action: 4 };
  const PHASE_LANES = [
    { id: 'target', label: 'Target', type: 'target' },
    { id: 'recon', label: 'Recon', type: 'recon' },
    { id: 'vuln', label: 'Scan', type: 'vuln' },
    { id: 'exploit', label: 'Exploit', type: 'exploit' },
    { id: 'action', label: 'Action', type: 'action' },
  ];

  const TYPE_COLORS = {
    target: { fill: '#3d2a32', stroke: '#f7768e', text: '#ffc2c9' },
    recon: { fill: '#3d3028', stroke: '#ff9e64', text: '#ffd4b8' },
    vuln: { fill: '#3d3828', stroke: '#e0af68', text: '#ffe6b8' },
    exploit: { fill: '#3d2228', stroke: '#f7768e', text: '#ffc2c9' },
    action: { fill: '#2a2d3d', stroke: '#565f89', text: '#c0caf5' },
  };

  const AUTH_KEY = 'tongling_token';
  const LS_SCAN_LAYOUT = 'tongling_scan_layout';
  const LS_SCAN_AGGREGATE = 'tongling_scan_aggregate';
  const LS_SCAN_STEP_FILTER = 'tongling_scan_step_filter';
  const NOISE_TOOLS = new Set(['curl', 'wget', 'httpx']);

  function token() {
    const u = new URLSearchParams(location.search).get('token');
    if (u) sessionStorage.setItem(AUTH_KEY, u);
    return u || sessionStorage.getItem(AUTH_KEY) || '';
  }

  function api(url) {
    const t = token();
    const sep = url.includes('?') ? '&' : '?';
    return fetch(t ? `${url}${sep}token=${encodeURIComponent(t)}` : url);
  }

  function $(id) { return document.getElementById(id); }

  let state = {
    graph: { nodes: [], edges: [], timeline: [], phases: [] },
    fullGraph: null,
    scale: 1,
    tx: 0,
    ty: 0,
    selectedNodeId: null,
    claudeWorkdir: '',
    claudeSession: null,
    detailRun: null,
    detailNode: null,
    graphBounds: null,
    graphMeta: null,
    risk: null,
    facts: null,
    chain: null,
  };
  let positions = {};
  /** @type {'hexstrike'|'claude'} */
  let dataSource = 'claude';
  let activeSessionId = null;
  /** @type {'mindmap'|'swimlane'} */
  let layoutMode = localStorage.getItem(LS_SCAN_LAYOUT) || 'mindmap';
  let aggregateProbes = localStorage.getItem(LS_SCAN_AGGREGATE) !== '0';
  /** @type {'key'|'probes'|'all'} */
  let stepFilter = localStorage.getItem(LS_SCAN_STEP_FILTER) || 'key';

  const playback = {
    playing: false,
    index: -1,
    timer: null,
    steps: [],
  };
  function isNoiseProbeNode(n) {
    if (!n || n.type === 'target') return false;
    if (n.is_noise_probe) return true;
    return NOISE_TOOLS.has(String(n.tool || '').toLowerCase());
  }

  function shouldKeepNode(n, mode) {
    if (n.type === 'target') return true;
    const noise = isNoiseProbeNode(n);
    if (mode === 'all') return true;
    if (mode === 'key') return !noise;
    if (mode === 'probes') {
      if (!noise) return true;
      return !!n.grouped && (n.group_count || 0) > 1;
    }
    return true;
  }

  function rewireEdges(allNodes, allEdges, keptIds) {
    const byId = Object.fromEntries(allNodes.map((n) => [n.id, n]));
    const nextMap = new Map();
    (allEdges || []).forEach((e) => nextMap.set(e.from, e.to));
    const newEdges = [];
    allNodes.filter((n) => n.type === 'target').forEach((t) => {
      let prev = t.id;
      let cur = nextMap.get(prev);
      while (cur) {
        if (keptIds.has(cur)) {
          newEdges.push({ from: prev, to: cur, label: byId[cur]?.phase_label || '' });
          prev = cur;
        }
        cur = nextMap.get(cur);
      }
    });
    return newEdges;
  }

  function applyStepFilter(graph, mode) {
    if (!graph || mode === 'all') return graph;
    const nodes = graph.nodes || [];
    const edges = graph.edges || [];
    const filteredNodes = nodes.filter((n) => shouldKeepNode(n, mode));
    const keptIds = new Set(filteredNodes.map((n) => n.id));
    if (keptIds.size === nodes.length) return graph;
    return { ...graph, nodes: filteredNodes, edges: rewireEdges(nodes, edges, keptIds) };
  }

  function countHiddenStepNodes(fullGraph, mode) {
    if (!fullGraph || mode === 'all') return 0;
    const total = (fullGraph.nodes || []).filter((n) => n.type !== 'target').length;
    const visible = (applyStepFilter(fullGraph, mode).nodes || []).filter((n) => n.type !== 'target').length;
    return Math.max(0, total - visible);
  }

  function setStepFilter(mode) {
    stopPlayback();
    stepFilter = mode === 'probes' || mode === 'all' ? mode : 'key';
    localStorage.setItem(LS_SCAN_STEP_FILTER, stepFilter);
    document.querySelectorAll('.scan-step-filter-tab').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-filter') === stepFilter);
    });
    if (state.fullGraph) {
      state.graph = applyStepFilter(state.fullGraph, stepFilter);
      renderGraph(state.graph);
      renderFilteredTimeline();
      if (!state.selectedNodeId) setTimeout(fitView, 50);
    }
  }

  function renderFilteredTimeline() {
    const tl = state.fullGraph?.timeline || state.graph?.timeline || [];
    const filtered = filterTimeline(tl, stepFilter);
    playback.steps = filtered.filter((t) => t.node_id);
    if (playback.index >= playback.steps.length) playback.index = playback.steps.length - 1;
    renderTimeline(filtered);
    updateReplayPos();
  }

  function filterTimeline(timeline, mode) {
    if (mode === 'all') return timeline || [];
    return (timeline || []).filter((t) => {
      const noise = t.is_noise_probe || NOISE_TOOLS.has(String(t.raw_tool || '').toLowerCase());
      if (mode === 'key') return !noise;
      if (mode === 'probes') {
        if (!noise) return true;
        return !!t.grouped && (t.group_count || 0) > 1;
      }
      return true;
    });
  }

  function updateReplayPos() {
    const el = $('replay-pos');
    if (!el) return;
    const n = playback.steps.length;
    if (!n) {
      el.textContent = '—';
      return;
    }
    const i = playback.index < 0 ? 0 : playback.index + 1;
    el.textContent = `${Math.min(i, n)}/${n}`;
  }

  function stopPlayback() {
    playback.playing = false;
    if (playback.timer) {
      clearInterval(playback.timer);
      playback.timer = null;
    }
    const btn = $('btn-replay-toggle');
    if (btn) btn.textContent = '▶';
  }

  function centerOnNode(nodeId) {
    const wrap = $('graph-wrap');
    const pos = positions[nodeId];
    if (!wrap || !pos) return;
    const cx = pos.x + NODE_W / 2;
    const cy = pos.y + NODE_H / 2;
    state.tx = wrap.clientWidth / 2 - cx * state.scale;
    state.ty = wrap.clientHeight / 2 - cy * state.scale;
    const g = $('graph-svg')?.querySelector('#graph-root');
    if (g) g.setAttribute('transform', `translate(${state.tx},${state.ty}) scale(${state.scale})`);
    updateMinimapViewport();
  }

  function jumpPlayback(index, { openDetail } = { openDetail: true }) {
    if (!playback.steps.length) return;
    playback.index = Math.max(0, Math.min(index, playback.steps.length - 1));
    const step = playback.steps[playback.index];
    updateReplayPos();
    const node = (state.graph.nodes || []).find((n) => n.id === step.node_id);
    if (node) {
      highlightNode(node.id);
      centerOnNode(node.id);
      if (openDetail) showDetail(node);
    } else {
      highlightNode(step.node_id);
    }
  }

  function stepPlayback(delta) {
    if (!playback.steps.length) return;
    const next = playback.index < 0 ? 0 : playback.index + delta;
    jumpPlayback(next);
  }

  function togglePlayback() {
    if (!playback.steps.length) return;
    if (playback.playing) {
      stopPlayback();
      return;
    }
    playback.playing = true;
    const btn = $('btn-replay-toggle');
    if (btn) btn.textContent = '❚❚';
    if (playback.index < 0 || playback.index >= playback.steps.length - 1) {
      jumpPlayback(0);
    }
    playback.timer = setInterval(() => {
      if (playback.index >= playback.steps.length - 1) {
        stopPlayback();
        return;
      }
      jumpPlayback(playback.index + 1, { openDetail: false });
    }, 1400);
  }

  function renderRisk(risk) {
    const el = $('scan-risk-card');
    if (!el) return;
    if (!risk) {
      el.innerHTML = '<div class="scan-risk-empty">暂无评分</div>';
      return;
    }
    const sev = risk.severity || {};
    const drivers = (risk.drivers || []).map((d) => `<li>${escapeHtml(d)}</li>`).join('');
    el.innerHTML = `
      <div class="scan-risk-main">
        <div class="scan-risk-score level-${escapeHtml(risk.level || 'none')}">
          <span class="scan-risk-num">${risk.score ?? 0}</span>
          <span class="scan-risk-max">/100</span>
        </div>
        <div class="scan-risk-meta">
          <div class="scan-risk-label">${escapeHtml(risk.label || '')}</div>
          <div class="scan-risk-sev mono">
            <span class="sev-c">C${sev.critical || 0}</span>
            <span class="sev-h">H${sev.high || 0}</span>
            <span class="sev-m">M${sev.medium || 0}</span>
            <span class="sev-l">L${sev.low || 0}</span>
          </div>
        </div>
      </div>
      <ul class="scan-risk-drivers">${drivers || '<li>暂无驱动因素</li>'}</ul>`;
  }

  function renderFacts(facts, chain) {
    const el = $('scan-facts');
    if (!el) return;
    if (!facts || (!(facts.targets || []).length && !(facts.vulns || []).length)) {
      el.innerHTML = '<div class="scan-empty">暂无聚合事实。完成扫描步骤后将按目标汇总端口/漏洞/工具</div>';
      return;
    }
    const related = chain?.cross_session?.related_sessions || [];
    const targets = (facts.targets || []).slice(0, 8).map((t) => {
      const ports = (t.ports || []).slice(0, 8).join(', ') || '—';
      const tools = (t.tools || []).slice(0, 4).join(', ');
      return `<div class="scan-fact-target">
        <div class="scan-fact-host mono">${escapeHtml(t.host)}
          <span class="scan-fact-risk level-${escapeHtml(t.risk_level || 'none')}">${t.risk_score ?? 0}</span>
        </div>
        <div class="scan-fact-line">端口 ${escapeHtml(ports)}</div>
        <div class="scan-fact-line">${t.findings || 0} 线索 · ${t.run_count || 0} 步${tools ? ` · ${escapeHtml(tools)}` : ''}</div>
        ${t.session_count > 1 ? `<div class="scan-fact-line accent">关联 ${t.session_count} 个会话</div>` : ''}
      </div>`;
    }).join('');

    const relatedHtml = related.length
      ? `<div class="scan-fact-related">
          <div class="scan-fact-related-title">跨会话关联（同目标）</div>
          ${related.slice(0, 5).map((s) =>
            `<button type="button" class="scan-fact-session" data-sid="${escapeHtml(s.session_id)}">
              <span class="scan-fact-session-title">${escapeHtml(s.title || s.session_id)}</span>
              <span class="scan-fact-session-meta mono">${escapeHtml((s.shared_hosts || []).join(', '))}</span>
            </button>`
          ).join('')}
        </div>`
      : '';

    el.innerHTML = `
      <div class="scan-fact-summary mono">
        目标 ${facts.target_count || 0} · 端口 ${facts.port_count || 0} · 线索 ${facts.finding_count || 0}
      </div>
      ${targets}
      ${relatedHtml}`;

    el.querySelectorAll('.scan-fact-session').forEach((btn) => {
      btn.addEventListener('click', () => {
        const sid = btn.getAttribute('data-sid');
        if (sid) loadClaudeSession(sid, true);
      });
    });
  }

  const STEP_FILTER_LABELS = { key: '关键步骤', probes: '含探测', all: '全部' };

  function updateDetailTabLabels() {
    document.querySelectorAll('.scan-detail-tab').forEach((btn) => {
      const tab = btn.getAttribute('data-tab');
      if (tab === 'output') btn.textContent = dataSource === 'claude' ? 'Claude 输出' : '工具输出';
      if (tab === 'terminal') btn.textContent = dataSource === 'claude' ? '终端上下文' : '终端上下文';
    });
  }

  function setSourceTab(source) {
    dataSource = source;
    activeSessionId = null;
    document.querySelectorAll('.scan-source-tab').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-source') === source);
    });
    const title = $('session-panel-title');
    if (title) {
      title.textContent = source === 'claude' ? 'Claude 历史会话' : 'HexStrike 扫描会话';
    }
    updateDetailTabLabels();
  }

  function layoutGraph(graph) {
    const pos = {};
    const nodes = graph.nodes || [];
    const laneRows = { target: 0, recon: 0, vuln: 0, exploit: 0, action: 0 };

    const targets = nodes.filter((n) => n.type === 'target');
    targets.forEach((n) => {
      const row = laneRows.target++;
      pos[n.id] = {
        x: PAD + PHASE_COL.target * LANE_W,
        y: PAD + 28 + row * (NODE_H + GAP_Y),
      };
    });

    const runs = nodes
      .filter((n) => n.type !== 'target')
      .slice()
      .sort((a, b) => (a.sequence || 0) - (b.sequence || 0) || String(a.id).localeCompare(String(b.id)));

    runs.forEach((n) => {
      const phase = n.phase || n.type || 'action';
      const laneKey = PHASE_COL[phase] !== undefined ? phase : 'action';
      if (laneKey === 'target') return;
      const row = laneRows[laneKey] || 0;
      laneRows[laneKey] = row + 1;
      pos[n.id] = {
        x: PAD + (PHASE_COL[phase] ?? PHASE_COL.action) * LANE_W,
        y: PAD + 28 + row * (NODE_H + GAP_Y),
      };
    });

    nodes.forEach((n, i) => {
      if (pos[n.id]) return;
      const phase = n.phase || n.type || 'action';
      const laneKey = phase in laneRows ? phase : 'action';
      const row = laneRows[laneKey] || 0;
      laneRows[laneKey] = row + 1;
      pos[n.id] = {
        x: PAD + (PHASE_COL[phase] ?? PHASE_COL.action) * LANE_W,
        y: PAD + 28 + row * (NODE_H + GAP_Y) + i * 8,
      };
    });

    return pos;
  }

  function drawSwimlanes(g, maxY) {
    PHASE_LANES.forEach((lane) => {
      const col = PHASE_COL[lane.type] ?? 1;
      const x = PAD + col * LANE_W - 12;
      const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      bg.setAttribute('x', x);
      bg.setAttribute('y', PAD - 28);
      bg.setAttribute('width', NODE_W + 24);
      bg.setAttribute('height', Math.max(maxY - PAD + 40, 200));
      bg.setAttribute('rx', '10');
      bg.setAttribute('fill', 'rgba(255,255,255,0.02)');
      bg.setAttribute('stroke', 'rgba(86,95,137,0.35)');
      bg.setAttribute('stroke-width', '1');
      g.appendChild(bg);

      const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      label.setAttribute('x', x + (NODE_W + 24) / 2);
      label.setAttribute('y', PAD - 10);
      label.setAttribute('text-anchor', 'middle');
      label.setAttribute('class', 'graph-lane-label');
      label.textContent = lane.label;
      g.appendChild(label);
    });
  }

  function layoutMindMap(graph) {
    const pos = {};
    const nodes = graph.nodes || [];
    const centerX = 400;
    const centerY = 260;
    const target = nodes.find((n) => n.type === 'target') || nodes[0];

    if (target) {
      pos[target.id] = { x: centerX - NODE_W / 2, y: centerY - NODE_H / 2 };
    }

    const byPhase = { recon: [], vuln: [], exploit: [], action: [] };
    nodes
      .filter((n) => n.type !== 'target')
      .sort((a, b) => (a.sequence || 0) - (b.sequence || 0))
      .forEach((n) => {
        const p = n.phase || n.type || 'action';
        (byPhase[p] || byPhase.action).push(n);
      });

    const phaseAngles = { recon: -Math.PI / 2, vuln: 0.08, exploit: Math.PI / 2, action: Math.PI + 0.08 };
    const R0 = 190;
    const Rstep = 78;

    Object.entries(byPhase).forEach(([phase, list]) => {
      const base = phaseAngles[phase] ?? 0;
      list.forEach((n, i) => {
        const r = R0 + i * Rstep;
        const fan = (i - (list.length - 1) / 2) * 0.12;
        const a = base + fan;
        pos[n.id] = {
          x: centerX + Math.cos(a) * r - NODE_W / 2,
          y: centerY + Math.sin(a) * r - NODE_H / 2,
        };
      });
    });

    let minX = Infinity;
    let minY = Infinity;
    Object.values(pos).forEach((p) => {
      minX = Math.min(minX, p.x);
      minY = Math.min(minY, p.y);
    });
    const dx = minX < PAD ? PAD - minX : 0;
    const dy = minY < PAD + 20 ? PAD + 20 - minY : 0;
    if (dx || dy) {
      Object.keys(pos).forEach((id) => {
        pos[id].x += dx;
        pos[id].y += dy;
      });
    }
    return pos;
  }

  function computeLayout(graph) {
    return layoutMode === 'swimlane' ? layoutGraph(graph) : layoutMindMap(graph);
  }

  function setLayoutMode(mode) {
    layoutMode = mode === 'swimlane' ? 'swimlane' : 'mindmap';
    localStorage.setItem(LS_SCAN_LAYOUT, layoutMode);
    document.querySelectorAll('.scan-layout-tab').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-layout') === layoutMode);
    });
    renderGraph(state.graph);
    if (!state.selectedNodeId) setTimeout(fitView, 50);
  }

  function drawMindMapSpokes(g, targetId) {
    const tp = positions[targetId];
    if (!tp) return;
    const cx = tp.x + NODE_W / 2;
    const cy = tp.y + NODE_H / 2;
    (state.graph.nodes || []).forEach((n) => {
      if (n.type === 'target' || !positions[n.id]) return;
      const p = positions[n.id];
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', cx);
      line.setAttribute('y1', cy);
      line.setAttribute('x2', p.x + NODE_W / 2);
      line.setAttribute('y2', p.y + NODE_H / 2);
      line.setAttribute('stroke', 'rgba(86,95,137,0.35)');
      line.setAttribute('stroke-width', '1');
      line.setAttribute('class', 'graph-spoke');
      if (state.selectedNodeId === n.id) {
        line.setAttribute('class', 'graph-spoke graph-spoke-active');
        line.setAttribute('stroke', '#00e676');
        line.setAttribute('stroke-width', '2');
      }
      g.insertBefore(line, g.firstChild);
    });
  }

  function renderGraph(graph) {
    positions = computeLayout(graph);
    const svg = $('graph-svg');
    const wrap = $('graph-wrap');
    if (!svg || !wrap) return;

    const nodes = graph.nodes || [];
    const edges = graph.edges || [];
    if (!nodes.length) {
      svg.innerHTML = '';
      $('graph-minimap') && ($('graph-minimap').hidden = true);
      const hint = dataSource === 'claude'
        ? '该 Claude 会话中未识别到扫描工具。请在 AI 终端通过 MCP 或 Bash 运行 nmap、nuclei、curl 等命令后刷新'
        : '暂无扫描数据，请通过 MCP/接口运行工具后刷新';
      $('graph-hint').textContent = hint;
      return;
    }

    let maxX = 0;
    let maxY = 0;
    Object.values(positions).forEach((p) => {
      maxX = Math.max(maxX, p.x + NODE_W);
      maxY = Math.max(maxY, p.y + NODE_H);
    });

    const vbW = Math.max(maxX + PAD, wrap.clientWidth);
    const vbH = Math.max(maxY + PAD, wrap.clientHeight);
    svg.setAttribute('viewBox', `0 0 ${vbW} ${vbH}`);

    state.graphBounds = { minX: PAD, minY: PAD, maxX: maxX + PAD, maxY: maxY + PAD, vbW, vbH };

    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('id', 'graph-root');
    g.setAttribute('transform', `translate(${state.tx},${state.ty}) scale(${state.scale})`);

    if (layoutMode === 'swimlane') {
      drawSwimlanes(g, maxY);
    } else {
      const targetNode = nodes.find((n) => n.type === 'target');
      if (targetNode) drawMindMapSpokes(g, targetNode.id);
    }

    edges.forEach((e) => {
      const a = positions[e.from];
      const b = positions[e.to];
      if (!a || !b) return;
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      const x1 = a.x + NODE_W;
      const y1 = a.y + NODE_H / 2;
      const x2 = b.x;
      const y2 = b.y + NODE_H / 2;
      const mx = (x1 + x2) / 2;
      path.setAttribute('d', `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`);
      path.setAttribute('fill', 'none');
      if (layoutMode === 'mindmap') {
        path.setAttribute('stroke', 'none');
        path.setAttribute('opacity', '0');
      } else {
        path.setAttribute('stroke', '#565f89');
        path.setAttribute('stroke-width', '1.5');
        path.setAttribute('opacity', '0.7');
      }
      const isActive = state.selectedNodeId && (e.to === state.selectedNodeId || e.from === state.selectedNodeId);
      if (isActive) {
        path.setAttribute('class', 'graph-edge graph-edge-active');
        path.setAttribute('stroke', '#00e676');
        path.setAttribute('stroke-width', '2.5');
        path.setAttribute('opacity', '1');
      } else {
        path.setAttribute('class', 'graph-edge');
      }
      path.setAttribute('data-from', e.from);
      path.setAttribute('data-to', e.to);
      g.appendChild(path);
    });

    nodes.forEach((n) => {
      const p = positions[n.id];
      if (!p) return;
      const colors = TYPE_COLORS[n.type] || TYPE_COLORS.action;
      const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      group.setAttribute('class', 'graph-node' + (state.selectedNodeId === n.id ? ' selected' : ''));
      group.setAttribute('data-id', n.id);
      group.style.cursor = 'pointer';

      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', p.x);
      rect.setAttribute('y', p.y);
      rect.setAttribute('width', NODE_W);
      rect.setAttribute('height', NODE_H);
      rect.setAttribute('rx', '8');
      rect.setAttribute('fill', colors.fill);
      rect.setAttribute('stroke', n.status === 'failed' ? '#ff4d4d' : colors.stroke);
      rect.setAttribute('stroke-width', state.selectedNodeId === n.id ? '2.5' : '1.5');
      group.appendChild(rect);

      if (n.grouped && n.group_count > 1) {
        const countBg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        countBg.setAttribute('x', p.x + NODE_W - 34);
        countBg.setAttribute('y', p.y + NODE_H - 20);
        countBg.setAttribute('width', '28');
        countBg.setAttribute('height', '14');
        countBg.setAttribute('rx', '4');
        countBg.setAttribute('fill', 'rgba(0,230,118,0.25)');
        group.appendChild(countBg);
        const countText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        countText.setAttribute('x', p.x + NODE_W - 20);
        countText.setAttribute('y', p.y + NODE_H - 9);
        countText.setAttribute('text-anchor', 'middle');
        countText.setAttribute('fill', '#00e676');
        countText.setAttribute('font-size', '9');
        countText.setAttribute('font-weight', '700');
        countText.textContent = `×${n.group_count}`;
        group.appendChild(countText);
      }

      if (n.type !== 'target' && n.status === 'failed') {
        const failDot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        failDot.setAttribute('cx', p.x + NODE_W - 10);
        failDot.setAttribute('cy', p.y + 10);
        failDot.setAttribute('r', '4');
        failDot.setAttribute('fill', '#ff4d4d');
        group.appendChild(failDot);
      }

      const kind = toolKindLabel(n.tool_kind);
      if (kind && n.type !== 'target') {
        const badgeBg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        badgeBg.setAttribute('x', p.x + 6);
        badgeBg.setAttribute('y', p.y + 6);
        badgeBg.setAttribute('width', kind.length * 5.5 + 10);
        badgeBg.setAttribute('height', '14');
        badgeBg.setAttribute('rx', '4');
        badgeBg.setAttribute('fill', n.tool_kind === 'mcp' ? 'rgba(0,230,118,0.18)' : 'rgba(86,95,137,0.35)');
        group.appendChild(badgeBg);
        const badgeText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        badgeText.setAttribute('x', p.x + 11);
        badgeText.setAttribute('y', p.y + 16);
        badgeText.setAttribute('fill', n.tool_kind === 'mcp' ? '#00e676' : '#c0caf5');
        badgeText.setAttribute('font-size', '8');
        badgeText.setAttribute('font-family', 'Plus Jakarta Sans, Noto Sans SC, sans-serif');
        badgeText.textContent = kind;
        group.appendChild(badgeText);
      }

      const phaseText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      phaseText.setAttribute('x', p.x + NODE_W / 2);
      phaseText.setAttribute('y', p.y + (kind ? 28 : 16));
      phaseText.setAttribute('text-anchor', 'middle');
      phaseText.setAttribute('fill', colors.stroke);
      phaseText.setAttribute('font-size', '9');
      phaseText.setAttribute('font-family', 'Plus Jakarta Sans, Noto Sans SC, sans-serif');
      phaseText.textContent = n.phase_label
        ? String(n.phase_label).replace(/^(Recon|Scan|Exploit|Action).*/, '$1')
        : (n.type === 'target' ? 'Target' : '');

      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', p.x + NODE_W / 2);
      text.setAttribute('y', p.y + (n.type === 'target' ? NODE_H / 2 + 4 : (kind ? 44 : 36)));
      text.setAttribute('text-anchor', 'middle');
      text.setAttribute('fill', colors.text);
      text.setAttribute('font-size', '12');
      text.setAttribute('font-weight', '600');
      text.setAttribute('font-family', 'Plus Jakarta Sans, Noto Sans SC, sans-serif');
      const label = truncate(nodeDisplayLabel(n), 16);

      if (n.type !== 'target') group.appendChild(phaseText);
      text.textContent = label;
      group.appendChild(text);

      const sub = n.subtitle || (n.type === 'target' && n.probe_summary ? n.probe_summary : '');
      if (sub) {
        const subText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        subText.setAttribute('x', p.x + NODE_W / 2);
        subText.setAttribute('y', p.y + NODE_H - 8);
        subText.setAttribute('text-anchor', 'middle');
        subText.setAttribute('fill', colors.stroke);
        subText.setAttribute('font-size', '9');
        subText.setAttribute('opacity', '0.85');
        subText.setAttribute('font-family', 'IBM Plex Mono, monospace');
        subText.textContent = truncate(sub, 22);
        group.appendChild(subText);
      }
      group.addEventListener('click', (ev) => {
        ev.stopPropagation();
        showDetail(n);
      });
      g.appendChild(group);
    });

    svg.innerHTML = '';
    svg.appendChild(g);
    const meta = state.graphMeta || graph;
    const merged = meta.merged_step_count || graph.merged_step_count || 0;
    const raw = meta.raw_step_count || graph.raw_step_count || nodes.length;
    const disp = meta.display_step_count || graph.display_step_count || nodes.length;
    let hint = `${disp} 节点`;
    if (layoutMode === 'mindmap') hint += ' · 思维导图';
    else hint += ' · 泳道图';
    if (merged > 0) hint += ` · 已合并 ${merged} 步 curl/探测（共 ${raw} 步）`;
    else hint += ` · 共 ${raw} 步`;
    const hidden = state.fullGraph ? countHiddenStepNodes(state.fullGraph, stepFilter) : 0;
    if (hidden > 0) hint += ` · 已隐藏 ${hidden} 个探测`;
    hint += ` · ${STEP_FILTER_LABELS[stepFilter] || stepFilter}`;
    $('graph-hint').textContent = hint;
    renderMinimap();
    updateMinimapViewport();
  }

  function highlightNode(nodeId) {
    state.selectedNodeId = nodeId || null;
    renderFilteredTimeline();
    renderGraph(state.graph);
  }

  function setDetailTab(tab) {
    document.querySelectorAll('.scan-detail-tab').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-tab') === tab);
    });
    ['summary', 'output', 'terminal'].forEach((name) => {
      const pane = $(`detail-pane-${name}`);
      if (pane) pane.classList.toggle('active', name === tab);
      if (pane) pane.hidden = name !== tab;
    });
  }

  function fillDetailLinks(run) {
    const hs = $('detail-hs-link');
    const audit = $('detail-audit-link');
    const agent = $('detail-agent-link');
    if (hs) {
      if (run?.hexstrike_run_url && dataSource === 'hexstrike') {
        hs.href = withToken('/tongling/hs/');
        hs.hidden = false;
        hs.title = `Run #${run.run_id}`;
      } else {
        hs.hidden = true;
      }
    }
    if (audit) {
      if (run?.audit_id) {
        audit.href = withToken(`/tongling/api/audit/${encodeURIComponent(run.audit_id)}/report`);
        audit.hidden = false;
      } else {
        audit.hidden = true;
      }
    }
    if (agent) {
      updateAgentResumeLink(dataSource === 'claude' ? activeSessionId : null);
    }
  }

  function fillClaudeDetailMeta(node, run) {
    const el = $('detail-claude-meta');
    if (!el) return;
    if (dataSource !== 'claude' || (!node?.claude_tool && !run?.claude_tool)) {
      el.hidden = true;
      el.innerHTML = '';
      return;
    }
    const claudeTool = run?.claude_tool || node.claude_tool || '';
    const kind = toolKindLabel(run?.tool_kind || node.tool_kind || (claudeTool.startsWith('mcp__') ? 'mcp' : ''));
    el.hidden = false;
    el.innerHTML = [
      kind ? `<span class="scan-detail-kind kind-${kind.toLowerCase()}">${escapeHtml(kind)}</span>` : '',
      claudeTool ? `<span class="mono scan-detail-claude-tool" title="${escapeHtml(claudeTool)}">${escapeHtml(claudeTool)}</span>` : '',
      node.subtitle ? `<span class="scan-detail-subtitle">${escapeHtml(node.subtitle)}</span>` : '',
    ].filter(Boolean).join('');
  }

  function fillDetailFromRun(run, node) {
    state.detailRun = run;
    state.detailNode = node;
    fillClaudeDetailMeta(node, run);
    const outText = run.stdout || run.stderr || node.stdout_preview
      || '（无工具输出，可能尚未同步 HexStrike 或 Claude 未返回 tool_result）';
    renderFormattedOutput(outText, run.tool || node.tool);
    $('detail-terminal').textContent = formatToolOutput(run.terminal_excerpt
      || (run.audit_id ? '终端日志中未定位到该工具输出片段，可在审计报告中查看完整 terminal.log' : '未匹配到同时段的 Web 终端审计任务'));
    const findings = (run.findings || []).length ? run.findings : (node.findings || []);
    renderFindingsTable(findings);
    const hint = $('detail-terminal-hint');
    if (hint) {
      hint.textContent = run.audit_id
        ? `已关联审计 ${run.audit_id} · 以下为 scrollback 匹配片段`
        : '启动 Web 终端并完成 MCP 调用后，可在此看到终端上下文';
    }
    fillDetailLinks(run);
  }

  function withToken(url) {
    const t = token();
    if (!t) return url;
    return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(t)}`;
  }

  async function showDetail(node) {
    const panel = $('detail-panel');
    if (!panel || !node) return;
    panel.hidden = false;
    highlightNode(node.id);
    $('detail-title').textContent = nodeDisplayLabel(node);
    $('detail-phase-badge').textContent = node.phase_label || (node.type === 'target' ? '目标' : '');
    $('detail-body').textContent = node.detail || '';
    fillClaudeDetailMeta(node, null);
    state.detailNode = node;
    state.detailRun = null;
    const ul = $('detail-findings');
    if (ul) ul.innerHTML = '';
    renderFindingsTable(node.findings || []);
    setDetailTab('summary');

    if (!node.id.startsWith('run_') && !node.id.startsWith('group_')) {
      $('detail-output-formatted') && ($('detail-output-formatted').innerHTML = '');
      $('detail-terminal').textContent = '目标节点无工具输出';
      fillDetailLinks(null);
      return;
    }

    renderFormattedOutput(node.stdout_preview, node.tool);
    $('detail-terminal').textContent = '加载终端上下文…';
    try {
      const params = new URLSearchParams({
        node_id: node.id,
        source: dataSource,
      });
      if (dataSource === 'claude' && activeSessionId) {
        params.set('claude_session', activeSessionId);
      }
      if (state.claudeWorkdir) params.set('workdir', state.claudeWorkdir);
      const r = await api(`/tongling/api/scan/node/detail?${params}`);
      const d = await r.json();
      if (d.success && d.run) {
        fillDetailFromRun(d.run, node);
        if ((d.run.findings || []).length) {
          renderFindingsTable(d.run.findings);
        }
      }
    } catch (e) {
      $('detail-output').textContent = '加载失败: ' + e.message;
    }
  }

  function renderTimeline(timeline) {
    const el = $('attack-timeline');
    if (!el) return;
    if (!timeline?.length) {
      el.innerHTML = '<div class="scan-empty">暂无攻击链步骤。通过 MCP 运行 nmap/nuclei 等工具后会自动生成</div>';
      return;
    }
    el.innerHTML = timeline.map((step) => {
      const sub = step.subtitle || step.target || '';
      const rel = formatRelativeTime(step.timestamp);
      const errPreview = step.stderr_preview || '';
      const errBlock = step.success === false && errPreview
        ? `<div class="attack-step-err" hidden><pre class="mono">${escapeHtml(truncate(errPreview, 400))}</pre></div>
           <button type="button" class="attack-step-err-btn" data-action="toggle-err">查看错误</button>`
        : '';
      return `<button type="button" class="attack-step${step.success === false ? ' failed' : ''}${step.node_id === state.selectedNodeId ? ' active pulse' : ''}${step.grouped ? ' grouped' : ''}" data-node-id="${escapeHtml(step.node_id)}">
        <span class="attack-step-seq">${step.sequence || ''}</span>
        <span class="attack-step-body">
          <div class="attack-step-tool">${escapeHtml(step.tool || step.raw_tool || '')}${step.grouped && step.group_count ? ` <span class="attack-step-kind">×${step.group_count}</span>` : ''}${step.tool_kind === 'mcp' ? ' <span class="attack-step-kind">MCP</span>' : ''}${step.tool_kind === 'bash' ? ' <span class="attack-step-kind bash">Bash</span>' : ''}</div>
          <div class="attack-step-meta">
            <span class="attack-step-phase phase-${escapeHtml(step.phase || 'action')}">${escapeHtml(step.phase_label || step.phase || '')}</span>
            <span class="attack-step-target" title="${escapeHtml(sub)}">${escapeHtml(truncate(sub, 36))}</span>
            ${rel ? `<span class="attack-step-time">${escapeHtml(rel)}</span>` : ''}
          </div>
          ${errBlock}
        </span>
      </button>`;
    }).join('');
    el.querySelectorAll('.attack-step').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        if (ev.target.closest('[data-action="toggle-err"]')) {
          ev.stopPropagation();
          const errEl = btn.querySelector('.attack-step-err');
          if (errEl) {
            errEl.hidden = !errEl.hidden;
            ev.target.textContent = errEl.hidden ? '查看错误' : '收起错误';
          }
          return;
        }
        const nid = btn.getAttribute('data-node-id');
        const node = (state.graph.nodes || []).find((n) => n.id === nid);
        if (node) showDetail(node);
      });
    });
  }

  function renderKpis(stats, source) {
    const el = $('scan-kpis');
    if (!el || !stats) return;
    const sev = stats.severity || {};
    const vulnHint = (sev.critical || 0) + (sev.high || 0);
    const risk = stats.risk_score != null ? stats.risk_score : (state.risk?.score ?? '—');
    const items = source === 'claude'
      ? [
          ['风险分', risk],
          ['扫描步骤', stats.total_runs],
          ['目标数', stats.unique_targets],
          ['漏洞线索', vulnHint],
        ]
      : [
          ['风险分', risk],
          ['运行次数', stats.total_runs],
          ['活跃会话', stats.active_sessions],
          ['漏洞线索', vulnHint],
        ];
    el.innerHTML = items.map(([label, val]) =>
      `<div class="scan-kpi"><div class="scan-kpi-val">${val}</div><div class="scan-kpi-label">${label}</div></div>`
    ).join('');
  }

  function applyViewData(d, source) {
    stopPlayback();
    playback.index = -1;
    state.fullGraph = d.graph || { nodes: [], edges: [], timeline: [], phases: [] };
    state.graph = applyStepFilter(state.fullGraph, stepFilter);
    state.graphMeta = d.graph_meta || null;
    state.risk = d.risk || d.chain?.risk || null;
    state.facts = d.facts || d.chain?.facts || null;
    state.chain = d.chain || null;
    if (d.workdir) state.claudeWorkdir = d.workdir;
    if (source === 'claude' && d.session) {
      state.claudeSession = d.session;
      renderClaudeSessionBanner(d.session);
    } else if (source !== 'claude') {
      state.claudeSession = null;
      renderClaudeSessionBanner(null);
    }
    updateAgentResumeLink(source === 'claude' ? activeSessionId : null);
    renderKpis(d.stats, source);
    renderRisk(state.risk);
    renderFacts(state.facts, state.chain);
    renderFindings(d.recent_findings);
    renderToolBars(d.top_tools);
    renderFilteredTimeline();
    renderGraph(state.graph);
    if (!state.selectedNodeId) setTimeout(fitView, 50);
    setTimeout(applyFocusFromUrl, 80);
  }

  function applyFocusFromUrl() {
    const params = new URLSearchParams(location.search);
    const host = (params.get('focus_host') || '').trim().toLowerCase();
    const tool = (params.get('focus_tool') || '').trim().toLowerCase();
    const q = (params.get('focus_q') || '').trim().toLowerCase();
    if (!host && !tool && !q) return;
    const nodes = state.graph?.nodes || [];
    let node = null;
    if (host) {
      node = nodes.find((n) => {
        if (n.type !== 'target') return false;
        const label = String(n.label || n.target || n.id || '').toLowerCase();
        return label === host || label.includes(host) || host.includes(label);
      });
    }
    if (!node && (tool || q)) {
      node = nodes.find((n) => {
        if (n.type === 'target') return false;
        const blob = [
          n.label, n.display_label, n.tool, n.target, n.subtitle, ...(n.detail || []),
        ].join(' ').toLowerCase();
        if (tool && blob.includes(tool)) return true;
        if (q && blob.includes(q.slice(0, 40))) return true;
        return false;
      });
    }
    if (!node) return;
    highlightNode(node.id);
    centerOnNode(node.id);
    showDetail(node);
  }

  function renderHexstrikeSessions(sessions) {
    const el = $('session-list');
    if (!el) return;
    if (!sessions?.length) {
      el.innerHTML = '<div class="scan-empty">暂无 HexStrike 会话，通过 MCP 启动扫描后会出现</div>';
      return;
    }
    el.innerHTML = sessions.map((s) =>
      `<div class="scan-session-item${s.session_id === activeSessionId ? ' active' : ''}" data-sid="${escapeHtml(s.session_id)}" data-kind="hexstrike">
        <div class="target mono">${escapeHtml(s.target)}</div>
        <div class="scan-session-meta">
          <span>${s.active ? '进行中' : '已完成'}</span>
          <span>${s.total_findings} findings</span>
          <span>${(s.tools_executed || []).length} 工具</span>
        </div>
      </div>`
    ).join('');
    bindSessionClicks(el);
  }

  function renderClaudeSessions(sessions) {
    const el = $('session-list');
    if (!el) return;
    if (!sessions?.length) {
      el.innerHTML = '<div class="scan-empty">暂无 Claude 会话记录。请先在 AI 终端新建对话并运行扫描工具</div>';
      return;
    }
    el.innerHTML = sessions.map((s) => {
      const hasRuns = (s.tool_run_count || 0) > 0;
      const title = s.title || s.first_prompt || s.session_id.slice(0, 8);
      const tools = (s.scan_tools || []).slice(0, 4);
      const toolHtml = tools.length
        ? `<div class="scan-session-tools">${tools.map((t) => `<span class="scan-tool-chip">${escapeHtml(t)}</span>`).join('')}</div>`
        : '';
      return `<div class="scan-session-item${s.session_id === activeSessionId ? ' active' : ''}${hasRuns ? ' has-runs' : ''}" data-sid="${escapeHtml(s.session_id)}" data-kind="claude">
        <div class="session-title">${escapeHtml(truncate(title, 64))}</div>
        ${s.first_prompt && s.title ? `<div class="session-prompt">${escapeHtml(truncate(s.first_prompt, 72))}</div>` : ''}
        <div class="scan-session-meta">
          <span>${escapeHtml(s.modified_text || '')}</span>
          <span class="${hasRuns ? 'scan-meta-highlight' : ''}">${s.tool_run_count || 0} 扫描步</span>
          <span>${s.message_count || 0} 消息</span>
        </div>
        ${toolHtml}
      </div>`;
    }).join('');
    bindSessionClicks(el);
  }

  function bindSessionClicks(el) {
    el.querySelectorAll('.scan-session-item').forEach((item) => {
      item.addEventListener('click', () => {
        const sid = item.getAttribute('data-sid');
        const kind = item.getAttribute('data-kind') || dataSource;
        if (kind === 'claude') loadClaudeSession(sid);
        else loadHexstrikeSession(sid);
      });
    });
  }

  function renderFindings(findings) {
    const el = $('findings-list');
    if (!el) return;
    if (!findings?.length) {
      el.innerHTML = '<div class="scan-empty">工具输出中暂未解析到 CVE/高危关键字</div>';
      return;
    }
    el.innerHTML = findings.map((f) =>
      `<div class="scan-finding-item sev-${f.severity}">
        <div class="mono scan-finding-meta">${escapeHtml(f.tool)} · ${escapeHtml(f.target)}${f.cve ? ` · <mark class="cve-mark">${escapeHtml(f.cve)}</mark>` : ''}</div>
        ${escapeHtml(f.text)}
      </div>`
    ).join('');
  }

  function renderToolBars(tools) {
    const el = $('tool-bars');
    if (!el) return;
    if (!tools?.length) {
      el.innerHTML = '<div class="scan-empty">暂无工具运行记录</div>';
      return;
    }
    const max = Math.max(...tools.map((t) => t.count), 1);
    el.innerHTML = tools.map((t) =>
      `<div class="scan-tool-bar-row">
        <span class="name" title="${escapeHtml(t.tool)}">${escapeHtml(t.tool)}</span>
        <div class="bar"><div class="fill" style="width:${Math.round(t.count / max * 100)}%"></div></div>
        <span class="mono">${t.count}</span>
      </div>`
    ).join('');
  }

  function formatRelativeTime(ts) {
    if (!ts) return '';
    let ms = 0;
    const n = Number(ts);
    if (!Number.isNaN(n) && n > 1e9) {
      ms = n > 1e12 ? n : n * 1000;
    } else {
      const d = new Date(String(ts).replace(' ', 'T'));
      ms = d.getTime();
    }
    if (!ms || Number.isNaN(ms)) return String(ts).slice(0, 16);
    const diff = Date.now() - ms;
    const sec = Math.floor(diff / 1000);
    if (sec < 60) return '刚刚';
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min} 分钟前`;
    const hr = Math.floor(min / 60);
    if (hr < 48) return `${hr} 小时前`;
    const day = Math.floor(hr / 24);
    if (day < 14) return `${day} 天前`;
    return new Date(ms).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  function sevLabel(sev) {
    const m = { critical: '严重', high: '高危', medium: '中危', low: '低危', info: '信息' };
    return m[sev] || sev || '—';
  }

  function renderFindingsTable(findings) {
    const wrap = $('detail-findings-wrap');
    const tbody = $('detail-findings-table');
    const ul = $('detail-findings');
    if (!tbody || !wrap) return;
    const rows = (findings || []).filter((f) => f && (f.text || f.cve));
    if (!rows.length) {
      wrap.hidden = true;
      tbody.innerHTML = '';
      if (ul) ul.innerHTML = '';
      return;
    }
    wrap.hidden = false;
    if (ul) ul.innerHTML = '';
    tbody.innerHTML = rows.map((f) =>
      `<tr class="sev-row sev-${escapeHtml(f.severity || 'info')}">
        <td><span class="sev-pill sev-${escapeHtml(f.severity || 'info')}">${escapeHtml(sevLabel(f.severity))}</span></td>
        <td class="mono">${f.cve ? escapeHtml(f.cve) : '—'}</td>
        <td>${escapeHtml(f.text || '')}</td>
      </tr>`
    ).join('');
  }

  function renderFormattedOutput(text, tool) {
    const box = $('detail-output-formatted');
    const pre = $('detail-output');
    const raw = formatToolOutput(text);
    if (!box) return raw;
    if (!raw) {
      box.innerHTML = '<span class="scan-output-empty">（无输出）</span>';
      if (pre) pre.hidden = true;
      return '';
    }
    const t = (tool || '').toLowerCase();
    const lines = raw.split('\n');
    const html = lines.map((line) => {
      let cls = 'scan-out-line';
      const upper = line.toUpperCase();
      if (/^\[critical\]|\bcritical\b/i.test(line)) cls += ' sev-critical';
      else if (/^\[high\]|\bhigh\b/i.test(upper)) cls += ' sev-high';
      else if (/^\[medium\]|\bmedium\b/i.test(upper)) cls += ' sev-medium';
      else if (/^\[low\]|\blow\b/i.test(upper)) cls += ' sev-low';
      else if (/error|failed|denied|refused/i.test(line)) cls += ' sev-error';
      else if (/open|discovered|\d+\/tcp|\d+\/udp/i.test(line) && (t.includes('nmap') || t.includes('rustscan'))) cls += ' sev-port';
      else if (/^\+|^\-{3,}|^Nmap scan|^Starting Nmap/i.test(line)) cls += ' sev-header';
      let body = escapeHtml(line);
      body = body.replace(/(CVE-\d{4}-\d+)/gi, '<mark class="cve-mark">$1</mark>');
      return `<div class="${cls}">${body || '&nbsp;'}</div>`;
    }).join('');
    box.innerHTML = html;
    if (pre) {
      pre.textContent = raw;
      pre.hidden = true;
    }
    return raw;
  }

  function renderMinimap() {
    const mm = $('graph-minimap');
    const canvas = $('minimap-canvas');
    const b = state.graphBounds;
    if (!mm || !canvas || !b || !Object.keys(positions).length) {
      if (mm) mm.hidden = true;
      return;
    }
    mm.hidden = false;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const W = canvas.width;
    const H = canvas.height;
    const gw = Math.max(b.maxX - b.minX, 1);
    const gh = Math.max(b.maxY - b.minY, 1);
    const scale = Math.min(W / gw, H / gh) * 0.92;
    const ox = (W - gw * scale) / 2;
    const oy = (H - gh * scale) / 2;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(10,12,16,0.92)';
    ctx.fillRect(0, 0, W, H);
    (state.graph.nodes || []).forEach((n) => {
      const p = positions[n.id];
      if (!p) return;
      const colors = TYPE_COLORS[n.type] || TYPE_COLORS.action;
      ctx.fillStyle = colors.stroke;
      ctx.globalAlpha = n.id === state.selectedNodeId ? 1 : 0.75;
      ctx.fillRect(
        ox + (p.x - b.minX) * scale,
        oy + (p.y - b.minY) * scale,
        Math.max(NODE_W * scale, 3),
        Math.max(NODE_H * scale, 2),
      );
    });
    ctx.globalAlpha = 1;
    mm._mm = { ox, oy, scale, gw, gh, W, H };
  }

  function updateMinimapViewport() {
    const mm = $('graph-minimap');
    const vp = $('minimap-viewport');
    const wrap = $('graph-wrap');
    const b = state.graphBounds;
    if (!mm || !vp || !wrap || !b || !mm._mm || mm.hidden) return;
    const { ox, oy, scale } = mm._mm;
    const visW = wrap.clientWidth / state.scale;
    const visH = wrap.clientHeight / state.scale;
    const visX = (-state.tx) / state.scale;
    const visY = (-state.ty) / state.scale;
    vp.style.left = `${ox + (visX - b.minX) * scale}px`;
    vp.style.top = `${oy + (visY - b.minY) * scale}px`;
    vp.style.width = `${Math.min(mm._mm.W, visW * scale)}px`;
    vp.style.height = `${Math.min(mm._mm.H, visH * scale)}px`;
  }

  async function copyDetailOutput() {
    const raw = formatToolOutput($('detail-output')?.textContent || $('detail-output-formatted')?.innerText || '');
    if (!raw) return;
    try {
      await navigator.clipboard.writeText(raw);
      const btn = $('btn-copy-output');
      if (btn) {
        const prev = btn.textContent;
        btn.textContent = '已复制';
        setTimeout(() => { btn.textContent = prev; }, 1200);
      }
    } catch (e) {
      alert('复制失败: ' + e.message);
    }
  }

  function exportDetailJson() {
    const payload = {
      source: dataSource,
      session_id: activeSessionId,
      node: state.detailNode,
      run: state.detailRun,
      exported_at: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `scan-node-${state.detailNode?.id || 'export'}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function escapeHtml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function truncate(s, n) {
    const t = String(s || '');
    return t.length > n ? t.slice(0, n - 1) + '…' : t;
  }

  function formatToolOutput(text) {
    return String(text || '')
      .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .trim();
  }

  function toolKindLabel(kind) {
    if (kind === 'mcp') return 'MCP';
    if (kind === 'bash') return 'Bash';
    return '';
  }

  function nodeDisplayLabel(node) {
    return node.display_label || node.label || node.tool || node.id;
  }

  function renderClaudeSessionBanner(session) {
    const banner = $('claude-session-banner');
    const titleEl = $('claude-session-title');
    const metaEl = $('claude-session-meta');
    if (!banner || !titleEl || !metaEl) return;
    if (dataSource !== 'claude' || !session) {
      banner.hidden = true;
      return;
    }
    banner.hidden = false;
    titleEl.textContent = session.title || session.first_prompt || session.session_id?.slice(0, 8) || 'Claude 会话';
    const tools = (session.scan_tools || []).slice(0, 6);
    const toolChips = tools.map((t) => `<span class="scan-tool-chip">${escapeHtml(t)}</span>`).join('');
    metaEl.innerHTML = [
      session.modified_text ? `<span>${escapeHtml(session.modified_text)}</span>` : '',
      `<span>${session.tool_run_count || 0} 扫描步</span>`,
      `<span>${session.message_count || 0} 消息</span>`,
      toolChips ? `<span class="scan-tool-chips">${toolChips}</span>` : '',
    ].filter(Boolean).join('');
  }

  function updateAgentResumeLink(sessionId) {
    const link = $('detail-agent-link');
    if (!link) return;
    if (dataSource === 'claude' && sessionId) {
      link.href = withToken(`/tongling/?claude_session=${encodeURIComponent(sessionId)}`);
      link.textContent = '在 AI 终端恢复此会话';
      link.hidden = false;
    } else {
      link.href = withToken('/tongling/');
      link.textContent = '返回 AI 终端';
    }
  }

  async function loadOverview() {
    $('graph-hint').textContent = '加载中…';
    try {
      if (dataSource === 'claude') {
        await loadClaudeSessionsList(true);
        return;
      }
      const r = await api('/tongling/api/scan/overview');
      const d = await r.json();
      if (!d.success) {
        $('graph-hint').textContent = d.error || '加载失败';
        return;
      }
      applyViewData(d, 'hexstrike');
      renderHexstrikeSessions(d.sessions);
      const hasHexGraph = (d.graph?.nodes || []).length > 0;
      if (!hasHexGraph) {
        try {
          const cr = await api('/tongling/api/scan/claude/sessions');
          const cd = await cr.json();
          if (cd.success && cd.sessions?.some((s) => s.tool_run_count > 0)) {
            switchSource('claude');
            return;
          }
        } catch (e) { /* ignore */ }
      }
    } catch (e) {
      $('graph-hint').textContent = '加载失败: ' + e.message;
    }
  }

  async function loadClaudeSessionsList(selectFirstWithRuns) {
    $('graph-hint').textContent = '加载 Claude 会话…';
    try {
      const r = await api('/tongling/api/scan/claude/sessions');
      const d = await r.json();
      if (!d.success) {
        $('graph-hint').textContent = d.error || '加载失败';
        return;
      }
      if (d.workdir) state.claudeWorkdir = d.workdir;
      renderClaudeSessions(d.sessions);
      const urlSid = new URLSearchParams(location.search).get('claude_session');
      const noSelect = new URLSearchParams(location.search).get('noselect') === '1';
      let pick = urlSid || activeSessionId || null;
      if (!pick && selectFirstWithRuns && !noSelect) {
        pick = d.sessions?.find((s) => (s.tool_run_count || 0) > 0)?.session_id
          || d.sessions?.[0]?.session_id
          || null;
      }
      if (pick) {
        await loadClaudeSession(pick, false);
      } else {
        applyViewData({ graph: { nodes: [], edges: [] }, stats: { total_runs: 0, success_rate: 0, unique_targets: 0, severity: {} }, recent_findings: [], top_tools: [] }, 'claude');
        $('graph-hint').textContent = noSelect
          ? '未指定当前会话 · 请从左侧选择，或从 AI 终端扫描摘要跳转'
          : '暂无会话';
      }
    } catch (e) {
      $('graph-hint').textContent = '加载失败: ' + e.message;
    }
  }

  async function loadHexstrikeSession(sid) {
    if (!sid) return;
    activeSessionId = sid;
    document.querySelectorAll('.scan-session-item[data-kind="hexstrike"]').forEach((el) => {
      el.classList.toggle('active', el.getAttribute('data-sid') === sid);
    });
    $('graph-hint').textContent = '加载 HexStrike 会话…';
    try {
      const r = await api(`/tongling/api/scan/session/${encodeURIComponent(sid)}`);
      const d = await r.json();
      if (!d.success) return;
      applyViewData(d, 'hexstrike');
    } catch (e) { /* ignore */ }
  }

  async function loadClaudeSession(sid, updateListHighlight = true) {
    if (!sid) return;
    activeSessionId = sid;
    if (updateListHighlight) {
      document.querySelectorAll('.scan-session-item[data-kind="claude"]').forEach((el) => {
        el.classList.toggle('active', el.getAttribute('data-sid') === sid);
      });
    }
    $('graph-hint').textContent = '解析 Claude 会话…';
    try {
      const params = new URLSearchParams();
      if (!aggregateProbes) params.set('aggregate', '0');
      if (state.claudeWorkdir) params.set('workdir', state.claudeWorkdir);
      const qs = params.toString();
      const r = await api(`/tongling/api/scan/claude/${encodeURIComponent(sid)}${qs ? `?${qs}` : ''}`);
      const d = await r.json();
      if (!d.success) {
        $('graph-hint').textContent = d.error || '加载失败';
        return;
      }
      applyViewData(d, 'claude');
      if (updateListHighlight) {
        document.querySelectorAll('.scan-session-item[data-kind="claude"]').forEach((el) => {
          el.classList.toggle('active', el.getAttribute('data-sid') === sid);
        });
      }
      const u = new URL(location.href);
      u.searchParams.set('claude_session', sid);
      history.replaceState(null, '', u.pathname + u.search + u.hash);
    } catch (e) {
      $('graph-hint').textContent = '加载失败: ' + e.message;
    }
  }

  function switchSource(source) {
    if (source === dataSource) return;
    setSourceTab(source);
    activeSessionId = null;
    state.claudeSession = null;
    renderClaudeSessionBanner(null);
    loadOverview();
  }

  function setupPanZoom() {
    const wrap = $('graph-wrap');
    const svg = $('graph-svg');
    if (!wrap || !svg) return;

    let dragging = false;
    let lastX = 0;
    let lastY = 0;

    function applyTransform() {
      const g = svg.querySelector('#graph-root');
      if (g) g.setAttribute('transform', `translate(${state.tx},${state.ty}) scale(${state.scale})`);
      updateMinimapViewport();
    }

    wrap.addEventListener('mousedown', (e) => {
      if (e.target.closest('.graph-node')) return;
      dragging = true;
      wrap.classList.add('dragging');
      lastX = e.clientX;
      lastY = e.clientY;
    });
    window.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      state.tx += e.clientX - lastX;
      state.ty += e.clientY - lastY;
      lastX = e.clientX;
      lastY = e.clientY;
      applyTransform();
    });
    window.addEventListener('mouseup', () => {
      dragging = false;
      wrap.classList.remove('dragging');
    });

    wrap.addEventListener('wheel', (e) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? 0.92 : 1.08;
      state.scale = Math.min(2.5, Math.max(0.35, state.scale * delta));
      applyTransform();
    }, { passive: false });

    let touchLast = null;
    wrap.addEventListener('touchstart', (e) => {
      if (e.touches.length === 1) touchLast = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    }, { passive: true });
    wrap.addEventListener('touchmove', (e) => {
      if (e.touches.length !== 1 || !touchLast) return;
      e.preventDefault();
      state.tx += e.touches[0].clientX - touchLast.x;
      state.ty += e.touches[0].clientY - touchLast.y;
      touchLast = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      applyTransform();
    }, { passive: false });
  }

  function fitView() {
    const wrap = $('graph-wrap');
    const b = state.graphBounds;
    if (!wrap || !b || !Object.keys(positions).length) {
      state.tx = 0;
      state.ty = 0;
      state.scale = 1;
      const g = $('graph-svg')?.querySelector('#graph-root');
      if (g) g.setAttribute('transform', 'translate(0,0) scale(1)');
      updateMinimapViewport();
      return;
    }
    const pad = 24;
    const gw = b.maxX - b.minX + pad * 2;
    const gh = b.maxY - b.minY + pad * 2;
    const sx = wrap.clientWidth / gw;
    const sy = wrap.clientHeight / gh;
    state.scale = Math.min(2, Math.max(0.25, Math.min(sx, sy)));
    state.tx = (wrap.clientWidth - gw * state.scale) / 2 + (pad - b.minX) * state.scale;
    state.ty = (wrap.clientHeight - gh * state.scale) / 2 + (pad - b.minY) * state.scale;
    const g = $('graph-svg')?.querySelector('#graph-root');
    if (g) g.setAttribute('transform', `translate(${state.tx},${state.ty}) scale(${state.scale})`);
    updateMinimapViewport();
  }

  $('btn-refresh')?.addEventListener('click', loadOverview);
  $('btn-fit')?.addEventListener('click', fitView);
  $('btn-replay-prev')?.addEventListener('click', () => { stopPlayback(); stepPlayback(-1); });
  $('btn-replay-next')?.addEventListener('click', () => { stopPlayback(); stepPlayback(1); });
  $('btn-replay-toggle')?.addEventListener('click', togglePlayback);
  $('chk-aggregate')?.addEventListener('change', (ev) => {
    aggregateProbes = !!ev.target.checked;
    localStorage.setItem(LS_SCAN_AGGREGATE, aggregateProbes ? '1' : '0');
    if (activeSessionId) loadClaudeSession(activeSessionId);
    else loadOverview();
  });
  document.querySelectorAll('.scan-layout-tab').forEach((btn) => {
    btn.addEventListener('click', () => setLayoutMode(btn.getAttribute('data-layout') || 'mindmap'));
  });
  if ($('chk-aggregate')) $('chk-aggregate').checked = aggregateProbes;
  document.querySelectorAll('.scan-step-filter-tab').forEach((btn) => {
    btn.classList.toggle('active', btn.getAttribute('data-filter') === stepFilter);
    btn.addEventListener('click', () => setStepFilter(btn.getAttribute('data-filter') || 'key'));
  });
  document.querySelectorAll('.scan-layout-tab').forEach((btn) => {
    btn.classList.toggle('active', btn.getAttribute('data-layout') === layoutMode);
  });
  $('btn-copy-output')?.addEventListener('click', copyDetailOutput);
  $('btn-export-json')?.addEventListener('click', exportDetailJson);
  $('minimap-canvas')?.addEventListener('click', (ev) => {
    const mm = $('graph-minimap');
    const wrap = $('graph-wrap');
    const b = state.graphBounds;
    if (!mm?._mm || !wrap || !b) return;
    const rect = ev.target.getBoundingClientRect();
    const cx = ev.clientX - rect.left;
    const cy = ev.clientY - rect.top;
    const gx = b.minX + (cx - mm._mm.ox) / mm._mm.scale;
    const gy = b.minY + (cy - mm._mm.oy) / mm._mm.scale;
    state.tx = wrap.clientWidth / 2 - gx * state.scale;
    state.ty = wrap.clientHeight / 2 - gy * state.scale;
    const g = $('graph-svg')?.querySelector('#graph-root');
    if (g) g.setAttribute('transform', `translate(${state.tx},${state.ty}) scale(${state.scale})`);
    updateMinimapViewport();
  });
  $('detail-close')?.addEventListener('click', () => {
    $('detail-panel').hidden = true;
    highlightNode(null);
  });

  document.querySelectorAll('.scan-detail-tab').forEach((btn) => {
    btn.addEventListener('click', () => setDetailTab(btn.getAttribute('data-tab') || 'summary'));
  });

  document.querySelectorAll('.scan-source-tab').forEach((btn) => {
    btn.addEventListener('click', () => switchSource(btn.getAttribute('data-source') || 'hexstrike'));
  });

  setupPanZoom();

  const initClaude = new URLSearchParams(location.search).get('claude_session');
  const initHex = new URLSearchParams(location.search).get('hexstrike_session')
    || new URLSearchParams(location.search).get('session');

  if (initClaude) {
    setSourceTab('claude');
    loadClaudeSessionsList(false).then(() => loadClaudeSession(initClaude));
  } else if (initHex) {
    setSourceTab('hexstrike');
    loadOverview().then(() => loadHexstrikeSession(initHex));
  } else if (new URLSearchParams(location.search).get('noselect') === '1') {
    setSourceTab('claude');
    loadClaudeSessionsList(false);
  } else {
    setSourceTab('claude');
    loadClaudeSessionsList(true);
  }
  setInterval(() => {
    if (document.hidden) return;
    if (dataSource === 'hexstrike') loadOverview();
    else if (activeSessionId) loadClaudeSession(activeSessionId, false);
    else loadClaudeSessionsList(true);
  }, 30000);
})();
