(function () {
  'use strict';

  const fpState = { category: '' };
  const nuState = { severity: '', loading: false };

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  async function apiFetch(path, opts) {
    const fn = window.tonglingApiFetch || window.apiFetch;
    if (typeof fn === 'function') return fn(path, opts);
    return fetch(path, opts);
  }

  function setHint(el, text, type) {
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('err', type === 'err');
    el.classList.toggle('ok', type === 'ok');
  }

  function renderPreview(el, payload, serverName) {
    if (!el) return;
    if (payload && payload.command) {
      el.textContent = JSON.stringify({ mcpServers: { [serverName]: payload } }, null, 2);
    } else {
      el.textContent = '（无法生成 MCP 配置，请检查 Python311 环境）';
    }
  }

  function setBadge(el, configured) {
    if (!el) return;
    el.textContent = configured ? 'MCP 已导入' : '未导入 MCP';
    el.classList.toggle('ok', configured);
  }

  function renderFpFilters(categories) {
    const row = $('fp-filter-row');
    if (!row) return;
    const chips = ['<button type="button" class="lib-chip' + (!fpState.category ? ' active' : '') + '" data-cat="">全部</button>'];
    (categories || []).forEach((c) => {
      chips.push(
        `<button type="button" class="lib-chip${fpState.category === c ? ' active' : ''}" data-cat="${escapeHtml(c)}">${escapeHtml(c)}</button>`
      );
    });
    row.innerHTML = chips.join('');
    row.querySelectorAll('.lib-chip').forEach((btn) => {
      btn.addEventListener('click', () => {
        fpState.category = btn.getAttribute('data-cat') || '';
        row.querySelectorAll('.lib-chip').forEach((b) => b.classList.toggle('active', b === btn));
        searchFingerprints();
      });
    });
  }

  function bindGridClicks(el, kind) {
    if (!el) return;
    el.querySelectorAll('.lib-card[data-id]').forEach((card) => {
      card.addEventListener('click', () => openLibDetail(kind, card.getAttribute('data-id')));
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          openLibDetail(kind, card.getAttribute('data-id'));
        }
      });
    });
  }

  function renderGrid(el, items, kind, emptyHint) {
    if (!el) return;
    if (!items || !items.length) {
      el.innerHTML = `<div class="lib-empty"><span class="lib-empty-icon">⌕</span><p>${escapeHtml(emptyHint || '暂无数据')}</p></div>`;
      return;
    }
    el.innerHTML = items.map((it) => {
      const tags = (it.tags || []).filter((t) => t !== 'nuclei' && t !== 'hfinger').slice(0, 5);
      const tagHtml = tags.map((t) => `<span class="lib-tag">${escapeHtml(t)}</span>`).join('');
      if (kind === 'fp') {
        return `<article class="lib-card lib-card-fp" data-id="${escapeHtml(it.id)}" tabindex="0" role="button" title="点击查看详情">
          <div class="lib-card-top">
            <h4 class="lib-card-title">${escapeHtml(it.name)}</h4>
            <span class="lib-pill lib-pill-cat">${escapeHtml(it.category || 'other')}</span>
          </div>
          <p class="lib-card-desc">${escapeHtml(it.description || '')}</p>
          <div class="lib-card-foot">
            <code class="lib-card-id">${escapeHtml(it.id)}</code>
            <div class="lib-card-tags">${tagHtml}</div>
          </div>
          <span class="lib-card-hint">点击查看详情</span>
        </article>`;
      }
      const sev = (it.severity || 'info').toLowerCase();
      const src = (it.source || 'nuclei').toLowerCase();
      return `<article class="lib-card lib-card-nu" data-id="${escapeHtml(it.id)}" tabindex="0" role="button" title="点击查看详情">
        <div class="lib-card-top">
          <h4 class="lib-card-title">${escapeHtml(it.name)}</h4>
          <span class="lib-pill lib-sev lib-sev-${escapeHtml(sev)}">${escapeHtml(sev)}</span>
        </div>
        <p class="lib-card-path mono" title="${escapeHtml(it.template_path || '')}">${escapeHtml(it.template_path || '')}</p>
        <div class="lib-card-foot">
          <code class="lib-card-id">${escapeHtml(it.id)}</code>
          <span class="lib-pill lib-pill-cat">${escapeHtml(src)}</span>
          <div class="lib-card-tags">${tagHtml}</div>
        </div>
        <span class="lib-card-hint">点击查看详情</span>
      </article>`;
    }).join('');
    bindGridClicks(el, kind);
  }

  function renderDetailTags(tags) {
    const list = (tags || []).filter(Boolean);
    if (!list.length) return '';
    return `<div class="lib-detail-tags">${list.map((t) => `<span class="lib-tag">${escapeHtml(t)}</span>`).join('')}</div>`;
  }

  function renderFpDetail(item) {
    const rules = (item.match_rules || []).map((r) => `<li><code>${escapeHtml(r)}</code></li>`).join('');
    return `
      <div class="lib-detail-badges">
        <span class="lib-pill lib-pill-cat">${escapeHtml(item.category || '')}</span>
        ${item.enabled !== false ? '<span class="lib-pill lib-pill-ok">可用</span>' : '<span class="lib-pill">已禁用</span>'}
      </div>
      ${item.description ? `<section class="lib-detail-section"><h3>描述</h3><p>${escapeHtml(item.description)}</p></section>` : ''}
      <section class="lib-detail-section">
        <h3>匹配规则</h3>
        <dl class="lib-detail-dl">
          <dt>方法</dt><dd>${escapeHtml(item.match_method || '—')}</dd>
          <dt>位置</dt><dd>${escapeHtml(item.match_location || '—')}</dd>
          <dt>逻辑</dt><dd>${escapeHtml(item.match_logic || '—')}</dd>
        </dl>
        ${rules ? `<ul class="lib-detail-rules">${rules}</ul>` : '<p class="lib-detail-muted">无规则</p>'}
      </section>
      <section class="lib-detail-section">
        <h3>标签</h3>
        ${renderDetailTags(item.tags)}
      </section>
      <section class="lib-detail-section">
        <h3>MCP 调用</h3>
        <p class="lib-detail-muted">Claude 可使用 <code>fingerprint_probe</code> 或 <code>fingerprint_scan</code>，指纹 ID：<code>${escapeHtml(item.id)}</code></p>
      </section>`;
  }

  function renderNuDetail(item) {
    const sev = (item.severity || 'info').toLowerCase();
    const src = item.source || 'nuclei';
    return `
      <div class="lib-detail-badges">
        <span class="lib-pill lib-sev lib-sev-${escapeHtml(sev)}">${escapeHtml(sev)}</span>
        <span class="lib-pill lib-pill-cat">${escapeHtml(src)}</span>
      </div>
      ${item.description ? `<section class="lib-detail-section"><h3>描述</h3><p>${escapeHtml(item.description)}</p></section>` : ''}
      <section class="lib-detail-section">
        <h3>模板路径</h3>
        <code class="lib-source-path mono">${escapeHtml(item.template_path || '')}</code>
        ${item.yaml_path_abs ? `<code class="lib-source-path mono lib-source-sub">${escapeHtml(item.yaml_path_abs)}</code>` : ''}
      </section>
      <section class="lib-detail-section">
        <h3>标签</h3>
        ${renderDetailTags(item.tags)}
      </section>
      ${item.yaml_preview ? `<section class="lib-detail-section"><h3>YAML 预览</h3><pre class="code-block mono lib-yaml-preview">${escapeHtml(item.yaml_preview)}</pre></section>` : ''}
      <section class="lib-detail-section">
        <h3>MCP 调用</h3>
        <p class="lib-detail-muted">须先 <code>fingerprint_scan</code> 识别组件，再 <code>nuclei_scan(target, identified_products)</code> 定向扫描；可用 <code>nuclei_select_pocs</code> 预览匹配模板。</p>
      </section>`;
  }

  function closeLibDetail() {
    const modal = $('lib-detail-modal');
    if (!modal) return;
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  }

  function openLibDetail(kind, id) {
    if (!id) return;
    const modal = $('lib-detail-modal');
    const body = $('lib-detail-body');
    const titleEl = $('lib-detail-title');
    const idEl = $('lib-detail-id');
    const kindEl = $('lib-detail-kind');
    if (!modal || !body) return;

    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
    if (kindEl) kindEl.textContent = kind === 'fp' ? '指纹规则' : 'Nuclei 模板';
    if (titleEl) titleEl.textContent = '加载中…';
    if (idEl) idEl.textContent = id;
    body.innerHTML = '<p class="lib-detail-loading">加载中…</p>';

    const path = kind === 'fp'
      ? `/tongling/api/lib/fingerprint/${encodeURIComponent(id)}`
      : `/tongling/api/lib/nuclei/${encodeURIComponent(id)}`;

    apiFetch(path).then((r) => r.json()).then((d) => {
      if (!d.success || !d.item) {
        body.innerHTML = `<p class="lib-detail-error">${escapeHtml(d.error || '加载失败')}</p>`;
        return;
      }
      const item = d.item;
      if (titleEl) titleEl.textContent = item.name || id;
      if (idEl) idEl.textContent = item.id || id;
      body.innerHTML = kind === 'fp' ? renderFpDetail(item) : renderNuDetail(item);
    }).catch((e) => {
      body.innerHTML = `<p class="lib-detail-error">${escapeHtml(e.message)}</p>`;
    });
  }

  async function searchFingerprints() {
    const listEl = $('fp-search-list');
    const q = ($('fp-search-input')?.value || '').trim();
    const params = new URLSearchParams({ q, limit: '48' });
    if (fpState.category) params.set('category', fpState.category);
    try {
      const sr = await apiFetch(`/tongling/api/lib/fingerprint/search?${params}`);
      const sd = await sr.json();
      if (!sd.success) {
        renderGrid(listEl, [], 'fp', sd.error || '搜索失败');
        return;
      }
      renderGrid(listEl, sd.items, 'fp', q || fpState.category ? '无匹配指纹，换个关键词试试' : '输入关键词开始搜索');
      if ($('fp-search-count')) {
        $('fp-search-count').textContent = `匹配 ${sd.total || 0} 条 · 显示 ${sd.shown || 0} 条 · 点击卡片查看详情`;
      }
    } catch (e) {
      renderGrid(listEl, [], 'fp', '搜索失败: ' + e.message);
    }
  }

  async function loadFingerprintPanel() {
    const statusEl = $('fp-mcp-status');
    const hint = $('fp-status');
    try {
      const r = await apiFetch('/tongling/api/lib/fingerprint/status');
      const d = await r.json();
      if (!d.success) {
        setHint(statusEl, d.error || '加载失败', 'err');
        return;
      }
      const stats = d.stats || {};
      setBadge($('fp-mcp-badge'), d.configured);
      if (statusEl) {
        statusEl.textContent = stats.source_exists
          ? (d.configured ? 'Claude 终端输入 /mcp 查看 hfinger-lib' : '导入 MCP 后新建终端即可调用')
          : '指纹库文件不存在';
        statusEl.classList.toggle('err', !stats.source_exists);
      }
      if ($('fp-kpi-total')) $('fp-kpi-total').textContent = String(stats.total || 0);
      if ($('fp-kpi-cats')) $('fp-kpi-cats').textContent = String((stats.categories || []).length);
      if ($('fp-path-line')) $('fp-path-line').textContent = stats.source_path || '';
      renderPreview($('fp-mcp-preview'), d.pending_payload, d.mcp_server_name || 'hfinger-lib');
      const btn = $('btn-fp-mcp-connect');
      if (btn) btn.textContent = d.configured ? '重新导入指纹库 MCP' : '一键导入指纹库 MCP';
      renderFpFilters(stats.categories || []);
      await searchFingerprints();
      setHint(hint, '');
    } catch (e) {
      setHint(statusEl, '加载失败: ' + e.message, 'err');
    }
  }

  async function connectFingerprintMcp() {
    const hint = $('fp-status');
    const btn = $('btn-fp-mcp-connect');
    setHint(hint, '正在导入指纹库 MCP…');
    if (btn) btn.disabled = true;
    try {
      const r = await apiFetch('/tongling/api/lib/fingerprint/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const d = await r.json();
      setHint(hint, d.success ? (d.detail || '导入成功') : (d.error || '导入失败'), d.success ? 'ok' : 'err');
      if (d.success) await loadFingerprintPanel();
    } catch (e) {
      setHint(hint, '导入失败: ' + e.message, 'err');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function searchNuclei() {
    const listEl = $('nu-search-list');
    const q = ($('nu-search-input')?.value || '').trim();
    const params = new URLSearchParams({ q, limit: '48' });
    if (nuState.severity) params.set('severity', nuState.severity);
    try {
      const sr = await apiFetch(`/tongling/api/lib/nuclei/search?${params}`);
      const sd = await sr.json();
      if (!sd.success) {
        renderGrid(listEl, [], 'nu', sd.error || '搜索失败');
        return;
      }
      renderGrid(listEl, sd.items, 'nu', q || nuState.severity ? '无匹配模板' : '输入 CVE 或漏洞类型搜索');
      if ($('nu-search-count')) {
        $('nu-search-count').textContent = `匹配 ${sd.total || 0} 条 · 显示 ${sd.shown || 0} 条 · 点击卡片查看详情`;
      }
    } catch (e) {
      renderGrid(listEl, [], 'nu', '搜索失败: ' + e.message);
    }
  }

  function renderBootstrapSteps(steps) {
    const ul = $('nu-bootstrap-steps');
    if (!ul) return;
    const icons = { running: '◌', ok: '✓', warn: '⚠', err: '✗', skip: '−' };
    ul.innerHTML = (steps || []).map((s) => {
      const st = s.status || 'running';
      const icon = icons[st] || '·';
      return `<li class="lib-boot-step lib-boot-${escapeHtml(st)}"><span class="lib-boot-icon" aria-hidden="true">${icon}</span><div class="lib-boot-body"><strong>${escapeHtml(s.label || '')}</strong>${s.detail ? `<p>${escapeHtml(s.detail)}</p>` : ''}</div></li>`;
    }).join('');
  }

  function setBootstrapPanel(show, title) {
    const panel = $('nu-bootstrap-panel');
    const content = $('nu-main-content');
    if (panel) panel.classList.toggle('is-active', !!show);
    if (content) content.classList.toggle('is-hidden', !!show);
    if (title && $('nu-bootstrap-title')) $('nu-bootstrap-title').textContent = title;
  }

  async function bootstrapVulnLibrary() {
    const r = await apiFetch('/tongling/api/lib/pocs/bootstrap', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    const d = await r.json();
    renderBootstrapSteps(d.steps || []);
    return d;
  }

  async function loadNucleiPanel(options) {
    const opts = options || {};
    const doBootstrap = opts.bootstrap !== false;
    const statusEl = $('nu-mcp-status');
    const hint = $('nu-status');
    if (nuState.loading) return;
    nuState.loading = true;
    try {
      if (doBootstrap) {
        setBootstrapPanel(true, '正在加载漏洞库…');
        renderBootstrapSteps([{ label: '准备中…', status: 'running', detail: '检测本地模板与 POC 目录' }]);
        setHint(hint, '');
        const bd = await bootstrapVulnLibrary();
        if (!bd.success) {
          setHint(hint, bd.error || '漏洞库加载失败', 'err');
          if ((bd.notes || []).length) setHint(hint, (bd.error || '失败') + ' · ' + bd.notes.join('；'), 'err');
          return;
        }
        const idx = bd.index || {};
        const note = (bd.notes || []).join('；');
        setHint(
          hint,
          `漏洞库已就绪：共 ${idx.indexed || (bd.stats || {}).total || 0} 条 POC${note ? ' · ' + note : ''}`,
          'ok',
        );
      }

      setBootstrapPanel(false);
      const r = await apiFetch('/tongling/api/lib/nuclei/status');
      const d = await r.json();
      if (!d.success) {
        setHint(statusEl, d.error || '加载失败', 'err');
        return;
      }
      const stats = d.stats || {};
      const sev = stats.severity || {};
      setBadge($('nu-mcp-badge'), d.configured);
      if (statusEl) {
        statusEl.textContent = stats.source_exists
          ? (d.configured ? 'Claude 终端输入 /mcp 查看 nuclei-lib' : '导入 MCP 后新建终端即可调用')
          : 'Nuclei 模板目录不存在';
        statusEl.classList.toggle('err', !stats.source_exists);
      }
      if ($('nu-kpi-total')) $('nu-kpi-total').textContent = String(stats.total || 0);
      if ($('nu-kpi-critical')) $('nu-kpi-critical').textContent = String(sev.critical || 0);
      if ($('nu-kpi-high')) $('nu-kpi-high').textContent = String(sev.high || 0);
      if ($('nu-kpi-yaml')) {
        const ny = stats.nuclei_yaml_total || 0;
        const ay = stats.afrog_yaml_total || 0;
        $('nu-kpi-yaml').textContent = `${ny} / ${ay}`;
      }
      if ($('nu-path-line')) $('nu-path-line').textContent = stats.source_path || '';
      if ($('nu-afrog-line')) $('nu-afrog-line').textContent = stats.afrog_path ? `Afrog: ${stats.afrog_path}` : '';
      if ($('nu-cache-line')) {
        const nuIdx = stats.nuclei_indexed || 0;
        const afIdx = stats.afrog_indexed || 0;
        $('nu-cache-line').textContent = stats.index_cached
          ? `索引: Nuclei ${nuIdx} + Afrog ${afIdx} · ${stats.index_cache || ''}`
          : '索引缓存: 尚未生成';
      }
      renderPreview($('nu-mcp-preview'), d.pending_payload, d.mcp_server_name || 'nuclei-lib');
      const btn = $('btn-nu-mcp-connect');
      if (btn) btn.textContent = d.configured ? '重新导入漏洞库 MCP' : '一键导入漏洞库 MCP';
      await searchNuclei();
      if (!doBootstrap) setHint(hint, '');
    } catch (e) {
      setBootstrapPanel(false);
      setHint(hint, '加载失败: ' + e.message, 'err');
      setHint(statusEl, '加载失败: ' + e.message, 'err');
    } finally {
      nuState.loading = false;
    }
  }

  async function connectNucleiMcp() {
    const hint = $('nu-status');
    const btn = $('btn-nu-mcp-connect');
    setHint(hint, '正在导入漏洞库 MCP…');
    if (btn) btn.disabled = true;
    try {
      const r = await apiFetch('/tongling/api/lib/nuclei/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const d = await r.json();
      setHint(hint, d.success ? (d.detail || '导入成功') : (d.error || '导入失败'), d.success ? 'ok' : 'err');
      if (d.success) await loadNucleiPanel({ bootstrap: false });
    } catch (e) {
      setHint(hint, '导入失败: ' + e.message, 'err');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function syncPocLibraries() {
    const hint = $('nu-status');
    const btn = $('btn-nu-reindex');
    if (nuState.loading) return;
    nuState.loading = true;
    setBootstrapPanel(true, '正在拉取最新 POC…');
    renderBootstrapSteps([{ label: '连接 GitHub', status: 'running', detail: '代理 127.0.0.1:7897' }]);
    setHint(hint, '');
    if (btn) btn.disabled = true;
    try {
      const r = await apiFetch('/tongling/api/lib/pocs/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const d = await r.json();
      if (!d.success) {
        renderBootstrapSteps([{ label: '拉取失败', status: 'err', detail: d.error || '同步失败' }]);
        setHint(hint, d.error || '同步失败', 'err');
        return;
      }
      const idx = d.index || {};
      const notes = (d.notes || []).join('；');
      renderBootstrapSteps([
        { label: 'Nuclei 模板', status: d.nuclei ? 'ok' : 'warn', detail: '已更新' },
        { label: 'Afrog POC', status: d.afrog ? 'ok' : 'warn', detail: '已更新' },
        { label: '建立索引', status: 'ok', detail: `共 ${idx.indexed || 0} 条` },
      ]);
      const msg = `已索引 ${idx.indexed || 0} 条（Nuclei ${idx.nuclei_indexed || 0} + Afrog ${idx.afrog_indexed || 0}）${notes ? ' · ' + notes : ''}`;
      setHint(hint, msg, 'ok');
      await loadNucleiPanel({ bootstrap: false });
    } catch (e) {
      setBootstrapPanel(true);
      renderBootstrapSteps([{ label: '拉取失败', status: 'err', detail: e.message }]);
      setHint(hint, '同步失败: ' + e.message, 'err');
    } finally {
      setBootstrapPanel(false);
      if (btn) btn.disabled = false;
      nuState.loading = false;
    }
  }

  function bindLibraryUi() {
    $('btn-fp-mcp-connect')?.addEventListener('click', connectFingerprintMcp);
    $('btn-fp-refresh')?.addEventListener('click', loadFingerprintPanel);
    $('btn-fp-search')?.addEventListener('click', searchFingerprints);
    $('fp-search-input')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') searchFingerprints();
    });

    $('btn-nu-mcp-connect')?.addEventListener('click', connectNucleiMcp);
    $('btn-nu-refresh')?.addEventListener('click', () => loadNucleiPanel({ bootstrap: false }));
    $('btn-nu-reindex')?.addEventListener('click', syncPocLibraries);
    $('btn-nu-search')?.addEventListener('click', searchNuclei);
    $('nu-search-input')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') searchNuclei();
    });

    $('nu-filter-row')?.querySelectorAll('.lib-chip').forEach((btn) => {
      btn.addEventListener('click', () => {
        nuState.severity = btn.getAttribute('data-sev') || '';
        $('nu-filter-row')?.querySelectorAll('.lib-chip').forEach((b) => b.classList.toggle('active', b === btn));
        searchNuclei();
      });
    });

    $('lib-detail-close')?.addEventListener('click', closeLibDetail);
    $('lib-detail-close-btn')?.addEventListener('click', closeLibDetail);
    $('lib-detail-modal')?.addEventListener('click', (e) => {
      if (e.target === $('lib-detail-modal')) closeLibDetail();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !$('lib-detail-modal')?.classList.contains('hidden')) {
        closeLibDetail();
      }
    });
  }

  window.tonglingLibraries = {
    loadFingerprintPanel,
    loadNucleiPanel,
    bindLibraryUi,
    openLibDetail,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindLibraryUi);
  } else {
    bindLibraryUi();
  }
})();
