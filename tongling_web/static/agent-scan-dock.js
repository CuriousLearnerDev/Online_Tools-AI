/**
 * AI 智能体悬浮扫描摘要：攻击链事实 / 漏洞线索 / 工具统计
 * 数据同源自 scan-viz API。
 */
(function () {
  const LS_OPEN = 'tongling_agent_scan_dock_v2';
  const LS_MIN = 'tongling_agent_scan_dock_min';
  const LS_POS = 'tongling_agent_scan_dock_pos';
  const POLL_MS = 12000;

  const $ = (id) => document.getElementById(id);

  let sessionId = '';
  let workdir = '';
  let agentTabActive = true;
  let pollTimer = null;
  let loading = false;
  let lastBadge = '';
  // v2：默认打开；若用户点过关闭则为 '0'
  let open = localStorage.getItem(LS_OPEN) !== '0';
  let minimized = localStorage.getItem(LS_MIN) === '1';
  let dragState = null;

  function escapeHtml(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  async function apiJson(url, options) {
    // 必须走 app.js 的 withAuth，否则带 Token 的站点会 401
    if (typeof window.tonglingApiFetch !== 'function') {
      throw new Error('控制台未就绪');
    }
    const r = await window.tonglingApiFetch(url, options);
    return r.json();
  }

  function persist() {
    localStorage.setItem(LS_OPEN, open ? '1' : '0');
    localStorage.setItem(LS_MIN, minimized ? '1' : '0');
  }

  function loadPos() {
    try {
      const raw = localStorage.getItem(LS_POS);
      if (!raw) return null;
      const p = JSON.parse(raw);
      if (typeof p?.left !== 'number' || typeof p?.top !== 'number') return null;
      return p;
    } catch {
      return null;
    }
  }

  function savePos(left, top) {
    localStorage.setItem(LS_POS, JSON.stringify({ left, top }));
  }

  function isMacDesktop() {
    return document.body.classList.contains('term-fs');
  }

  /** 拖动边界：普通模式相对终端区域；悬浮桌面相对 panel-agent */
  function getDragHost() {
    if (isMacDesktop()) {
      return $('panel-agent') || document.body;
    }
    return $('terminal-host') || $('panel-agent') || document.body;
  }

  /** 视口坐标放置：适配 html zoom，避免 clientX 与 host 宽高坐标系混用导致乱跳 */
  function placeViewport(el, viewLeft, viewTop) {
    if (!el) return null;
    const host = getDragHost();
    if (!host) return null;
    const hostRect = host.getBoundingClientRect();
    const box = el.getBoundingClientRect();
    const elW = box.width || el.offsetWidth || 280;
    const elH = box.height || el.offsetHeight || 40;
    const margin = 4;
    const minL = hostRect.left + margin;
    const minT = hostRect.top + margin;
    const maxL = Math.max(minL, hostRect.right - elW - margin);
    const maxT = Math.max(minT, hostRect.bottom - elH - margin);
    const L = Math.min(Math.max(minL, viewLeft), maxL);
    const T = Math.min(Math.max(minT, viewTop), maxT);
    el.style.position = 'fixed';
    el.style.left = `${L}px`;
    el.style.top = `${T}px`;
    el.style.right = 'auto';
    el.style.bottom = 'auto';
    return {
      left: L - hostRect.left,
      top: T - hostRect.top,
    };
  }

  /** 相对 host 的坐标（用于持久化还原） */
  function placeFixed(el, hostLeft, hostTop) {
    if (!el) return null;
    const host = getDragHost();
    if (!host) return null;
    const hostRect = host.getBoundingClientRect();
    return placeViewport(el, hostRect.left + hostLeft, hostRect.top + hostTop);
  }

  function applyPos(left, top) {
    const dock = $('agent-scan-dock');
    return placeFixed(dock, left, top);
  }

  function applyChipPos() {
    const chip = $('agent-scan-dock-chip');
    if (!chip || chip.hidden) return;
    const saved = loadPos();
    const host = getDragHost();
    if (!host) return;
    if (saved) {
      placeFixed(chip, saved.left, saved.top);
      return;
    }
    const hostRect = host.getBoundingClientRect();
    const top = isMacDesktop() ? 34 : 10;
    const w = chip.getBoundingClientRect().width || chip.offsetWidth || 120;
    placeViewport(chip, hostRect.right - w - 10, hostRect.top + top);
  }

  function restorePos() {
    const dock = $('agent-scan-dock');
    const host = getDragHost();
    if (!dock || !host || dock.hidden) return;
    const saved = loadPos();
    if (saved) {
      applyPos(saved.left, saved.top);
      return;
    }
    const hostRect = host.getBoundingClientRect();
    const top = isMacDesktop() ? 34 : 10;
    const w = dock.getBoundingClientRect().width || dock.offsetWidth || 280;
    placeViewport(dock, hostRect.right - w - 10, hostRect.top + top);
  }

  function raiseScanPanel(el) {
    if (!isMacDesktop() || !open || !el) return;
    let maxZ = 58;
    document.querySelectorAll('.mac-term-win, .mac-app-win').forEach((w) => {
      const z = parseInt(w.style.zIndex, 10) || 0;
      if (z > maxZ) maxZ = z;
    });
    el.style.zIndex = String(maxZ + 2);
  }

  /** 通用拖动：摘要面板 / 最小化胶囊共用 */
  function bindPanelDrag(el, { handle, skipSelector, onTap } = {}) {
    if (!el) return;
    const target = handle || el;
    let local = null;
    let moved = false;
    const DRAG_THRESHOLD = 6;

    target.addEventListener('pointerdown', (e) => {
      if (e.button != null && e.button !== 0) return;
      if (skipSelector && e.target.closest(skipSelector)) return;
      const rect = el.getBoundingClientRect();
      local = {
        pointerId: e.pointerId,
        // 视口坐标下，指针相对元素左上角的偏移
        offsetX: e.clientX - rect.left,
        offsetY: e.clientY - rect.top,
        startX: e.clientX,
        startY: e.clientY,
        originLeft: rect.left,
        originTop: rect.top,
      };
      moved = false;
      dragState = local;
      raiseScanPanel(el);
      try {
        target.setPointerCapture(e.pointerId);
      } catch {
        /* ignore */
      }
      e.preventDefault();
    });

    target.addEventListener('pointermove', (e) => {
      if (!local || local.pointerId !== e.pointerId) return;
      const dx = e.clientX - local.startX;
      const dy = e.clientY - local.startY;
      if (!moved && Math.abs(dx) + Math.abs(dy) < DRAG_THRESHOLD) return;
      if (!moved) {
        moved = true;
        el.classList.add('asd-dragging');
      }
      placeViewport(el, e.clientX - local.offsetX, e.clientY - local.offsetY);
    });

    const endDrag = (e) => {
      if (!local || (e && local.pointerId !== e.pointerId)) return;
      const wasMoved = moved;
      if (wasMoved) {
        const p = placeViewport(el, e.clientX - local.offsetX, e.clientY - local.offsetY);
        if (p) savePos(p.left, p.top);
      } else {
        // 未拖动则保持原位
        placeViewport(el, local.originLeft, local.originTop);
      }
      el.classList.remove('asd-dragging');
      local = null;
      dragState = null;
      moved = false;
      if (!wasMoved && typeof onTap === 'function') onTap();
    };

    target.addEventListener('pointerup', endDrag);
    target.addEventListener('pointercancel', endDrag);
  }

  function bindDrag() {
    const handle = $('asd-drag-handle');
    const dock = $('agent-scan-dock');
    const chip = $('agent-scan-dock-chip');

    bindPanelDrag(dock, {
      handle,
      skipSelector: '.asd-icon-btn',
    });
    // 最小化胶囊可拖；轻点展开（避免与 click 抢事件）
    bindPanelDrag(chip, {
      onTap: () => setMinimized(false),
    });

    window.addEventListener('resize', () => {
      if (!open) return;
      if (minimized) applyChipPos();
      else restorePos();
    });
  }

  function syncChrome() {
    const dock = $('agent-scan-dock');
    const chip = $('agent-scan-dock-chip');
    const btn = $('btn-agent-scan-dock');
    const macBtn = $('btn-mac-scan-dock');
    const mBtn = $('m-btn-scan-dock');

    const showDock = open && !minimized;
    const showChip = open && minimized;

    if (dock) dock.hidden = !showDock;
    if (chip) chip.hidden = !showChip;

    if (btn) {
      btn.setAttribute('aria-pressed', open ? 'true' : 'false');
      btn.classList.toggle('active', open);
    }
    if (macBtn) {
      macBtn.setAttribute('aria-pressed', open ? 'true' : 'false');
      macBtn.classList.toggle('active', open);
    }
    if (mBtn) mBtn.classList.toggle('active', open);

    if (isMacDesktop()) {
      // 保持在窗口之上（避免被抬层后的终端盖住；菜单栏几何上仍在面板上方）
      let maxZ = 58;
      document.querySelectorAll('.mac-term-win, .mac-app-win').forEach((el) => {
        const z = parseInt(el.style.zIndex, 10) || 0;
        if (z > maxZ) maxZ = z;
      });
      const z = String(maxZ + 2);
      if (dock) dock.style.zIndex = z;
      if (chip) chip.style.zIndex = z;
    }

    if (showDock) {
      requestAnimationFrame(() => restorePos());
    } else if (showChip) {
      requestAnimationFrame(() => applyChipPos());
    }
  }

  function setOpen(next) {
    open = !!next;
    if (!open) minimized = false;
    persist();
    syncChrome();
    if (open) refresh(false);
    updatePolling();
  }

  function setMinimized(next) {
    minimized = !!next;
    persist();
    syncChrome();
  }

  function openScanViz(opts = {}) {
    const payload = {
      sessionId: opts.sessionId || sessionId || '',
      host: opts.host || '',
      tool: opts.tool || '',
      q: opts.q || '',
      currentOnly: true,
    };
    if (typeof window.tonglingOpenScanViz === 'function') {
      window.tonglingOpenScanViz(payload);
      return;
    }
    if (typeof window.tonglingSwitchTab === 'function') {
      window.tonglingSwitchTab('scanviz');
    }
  }

  function renderFacts(facts, chain) {
    const el = $('asd-facts');
    if (!el) return;
    if (!facts || (!(facts.targets || []).length && !(facts.vulns || []).length)) {
      el.innerHTML = '<div class="asd-empty">暂无当前会话事实。新建或恢复终端并跑扫描后，这里会汇总目标端口 / 漏洞 / 工具</div>';
      return;
    }
    const related = chain?.cross_session?.related_sessions || [];
    const targets = (facts.targets || []).slice(0, 8).map((t) => {
      const ports = (t.ports || []).slice(0, 8).join(', ') || '—';
      const tools = (t.tools || []).slice(0, 4).join(', ');
      return `<button type="button" class="asd-fact-target asd-nav" data-host="${escapeHtml(t.host)}" title="打开扫描图谱 · ${escapeHtml(t.host)}">
        <div class="asd-fact-host mono">${escapeHtml(t.host)}
          <span class="asd-fact-risk level-${escapeHtml(t.risk_level || 'none')}">${t.risk_score ?? 0}</span>
        </div>
        <div class="asd-fact-line">端口 ${escapeHtml(ports)}</div>
        <div class="asd-fact-line">${t.findings || 0} 线索 · ${t.run_count || 0} 步${tools ? ` · ${escapeHtml(tools)}` : ''}</div>
        ${t.session_count > 1 ? `<div class="asd-fact-line" style="color:var(--cyan,#5ad1e6)">关联 ${t.session_count} 个会话</div>` : ''}
      </button>`;
    }).join('');

    const relatedHtml = related.length
      ? `<div class="asd-fact-summary">跨会话关联 ${related.length} 个</div>
         ${related.slice(0, 4).map((s) =>
           `<button type="button" class="asd-fact-target asd-nav" data-sid="${escapeHtml(s.session_id)}" data-host="${escapeHtml((s.shared_hosts || [])[0] || '')}" title="打开该会话图谱">
              <div class="asd-fact-host">${escapeHtml(s.title || s.session_id)}</div>
              <div class="asd-fact-line mono">${escapeHtml((s.shared_hosts || []).join(', '))}</div>
            </button>`
         ).join('')}`
      : '';

    el.innerHTML = `
      <div class="asd-fact-summary mono">
        目标 ${facts.target_count || 0} · 端口 ${facts.port_count || 0} · 线索 ${facts.finding_count || 0}
      </div>
      ${targets}
      ${relatedHtml}`;

    el.querySelectorAll('.asd-nav').forEach((btn) => {
      btn.addEventListener('click', () => {
        openScanViz({
          sessionId: btn.getAttribute('data-sid') || sessionId,
          host: btn.getAttribute('data-host') || '',
        });
      });
    });
  }

  function renderFindings(findings) {
    const el = $('asd-findings');
    if (!el) return;
    if (!findings?.length) {
      el.innerHTML = '<div class="asd-empty">当前会话暂未解析到 CVE / 高危关键字</div>';
      return;
    }
    el.innerHTML = findings.slice(0, 24).map((f) =>
      `<button type="button" class="asd-finding-item asd-nav sev-${escapeHtml(f.severity || 'info')}" data-host="${escapeHtml(f.host || f.target || '')}" data-tool="${escapeHtml(f.tool || '')}" data-q="${escapeHtml(f.cve || f.text || '')}" title="打开扫描图谱">
        <div class="mono asd-finding-meta">${escapeHtml(f.tool || '—')} · ${escapeHtml(f.target || '—')}${f.cve ? ` · <mark class="cve-mark">${escapeHtml(f.cve)}</mark>` : ''}</div>
        ${escapeHtml(f.text || '')}
      </button>`
    ).join('');
    el.querySelectorAll('.asd-nav').forEach((btn) => {
      btn.addEventListener('click', () => {
        openScanViz({
          host: btn.getAttribute('data-host') || '',
          tool: btn.getAttribute('data-tool') || '',
          q: btn.getAttribute('data-q') || '',
        });
      });
    });
  }

  function renderTools(tools) {
    const el = $('asd-tools');
    if (!el) return;
    if (!tools?.length) {
      el.innerHTML = '<div class="asd-empty">当前会话暂无工具运行记录</div>';
      return;
    }
    const max = Math.max(...tools.map((t) => t.count), 1);
    el.innerHTML = tools.slice(0, 12).map((t) =>
      `<button type="button" class="asd-tool-row asd-nav" data-tool="${escapeHtml(t.tool)}" title="打开扫描图谱 · ${escapeHtml(t.tool)}">
        <span class="name" title="${escapeHtml(t.tool)}">${escapeHtml(t.tool)}</span>
        <div class="bar"><div class="fill" style="width:${Math.round((t.count / max) * 100)}%"></div></div>
        <span class="mono">${t.count}</span>
      </button>`
    ).join('');
    el.querySelectorAll('.asd-nav').forEach((btn) => {
      btn.addEventListener('click', () => {
        openScanViz({ tool: btn.getAttribute('data-tool') || '' });
      });
    });
  }

  function updateMeta(d) {
    const meta = $('asd-meta');
    const badge = $('asd-chip-badge');
    const risk = d.risk?.score ?? d.stats?.risk_score;
    const findingCount = (d.recent_findings || []).length || d.facts?.finding_count || 0;
    const sidShort = sessionId ? `终端会话 ${sessionId.slice(0, 8)}` : '未绑定终端';
    const riskText = risk != null ? `风险 ${risk}` : '';
    if (meta) {
      meta.textContent = [sidShort, riskText, findingCount ? `${findingCount} 线索` : '']
        .filter(Boolean)
        .join(' · ');
    }
    lastBadge = risk != null ? String(risk) : (findingCount ? String(findingCount) : '');
    if (badge) {
      badge.hidden = !lastBadge;
      badge.textContent = lastBadge;
    }
  }

  function applyData(d) {
    const facts = d.facts || d.chain?.facts || null;
    const chain = d.chain || null;
    renderFacts(facts, chain);
    renderFindings(d.recent_findings || facts?.vulns || []);
    renderTools(d.top_tools || facts?.top_tools || []);
    updateMeta(d);
  }

  function showEmptyCurrent() {
    const meta = $('asd-meta');
    if (meta) {
      meta.textContent = sessionId
        ? `当前终端 · ${sessionId.slice(0, 8)} · 暂无扫描数据`
        : '等待当前终端绑定…';
    }
    renderFacts(null, null);
    renderFindings([]);
    renderTools([]);
    const badge = $('asd-chip-badge');
    if (badge) badge.hidden = true;
  }

  async function refresh(silent) {
    if (loading || !open) return;
    loading = true;
    const meta = $('asd-meta');
    if (meta && !silent) meta.textContent = '加载中…';
    try {
      // 不回退 overview，避免默认刷出历史全局数据
      if (!sessionId) {
        showEmptyCurrent();
        return;
      }
      const q = new URLSearchParams({ aggregate: '1' });
      if (workdir) q.set('workdir', workdir);
      const url = `/tongling/api/scan/claude/${encodeURIComponent(sessionId)}?${q}`;
      const d = await apiJson(url);
      if (!d || d.success === false) {
        throw new Error(d?.error || '加载失败');
      }
      applyData(d);
    } catch (e) {
      if (meta) meta.textContent = String(e.message || e).slice(0, 48);
      if (!silent) showEmptyCurrent();
    } finally {
      loading = false;
    }
  }

  function updatePolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    if (open && agentTabActive) {
      pollTimer = setInterval(() => refresh(true), POLL_MS);
    }
  }

  function bind() {
    const toggleSoft = () => {
      if (!open) setOpen(true);
      else if (minimized) setMinimized(false);
      else setOpen(false);
    };
    $('btn-agent-scan-dock')?.addEventListener('click', () => setOpen(!open));
    $('btn-mac-scan-dock')?.addEventListener('click', toggleSoft);
    $('m-btn-scan-dock')?.addEventListener('click', toggleSoft);
    $('asd-close')?.addEventListener('click', () => setOpen(false));
    $('asd-minimize')?.addEventListener('click', () => setMinimized(true));
    // 胶囊展开由 bindPanelDrag 的轻点处理（拖动不触发展开）
    $('asd-refresh')?.addEventListener('click', () => refresh(false));
    $('asd-open-viz')?.addEventListener('click', () => openScanViz());
  }

  function init() {
    bind();
    bindDrag();
    syncChrome();
    updatePolling();
  }

  window.tonglingAgentScanDock = {
    init,
    setSessionId(id) {
      sessionId = id || '';
      if (open && typeof window.tonglingApiFetch === 'function') refresh(true);
    },
    setWorkdir(wd) {
      workdir = wd || '';
    },
    setAgentTabActive(active) {
      agentTabActive = !!active;
      updatePolling();
      if (agentTabActive && open && typeof window.tonglingApiFetch === 'function') refresh(true);
    },
    refresh: () => refresh(false),
    toggle: () => setOpen(!open),
    show: () => setOpen(true),
    ready() {
      // 确保 UI 与开关状态同步，避免仍带 HTML hidden
      syncChrome();
      if (open) refresh(false);
      updatePolling();
    },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
