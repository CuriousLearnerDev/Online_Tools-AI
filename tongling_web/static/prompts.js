/**
 * 统领 · 提示词库 UI
 */
(function (global) {
  'use strict';

  const TAG_LABEL = {
    scan: '扫描场景',
    daily: '日常助手',
    custom: '自定义',
  };

  let prompts = [];
  let selectedId = '';
  let editingNew = false;

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function apiFetch(url, opts) {
    if (global.tonglingApiFetch) return global.tonglingApiFetch(url, opts);
    return fetch(url, opts);
  }

  function setEditorStatus(text, type) {
    const el = $('prompts-editor-status');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'hint-box' + (type ? ' ' + type : '');
  }

  function truncate(s, n) {
    const t = String(s || '');
    return t.length > n ? t.slice(0, n) + '…' : t;
  }

  function renderKpi(stats) {
    const el = $('prompts-kpi');
    if (!el) return;
    const s = stats || {};
    el.innerHTML = [
      ['全部', s.total || 0],
      ['启用', s.enabled || 0],
      ['内置', s.builtin || 0],
      ['自定义', s.custom || 0],
    ]
      .map(
        ([label, val]) =>
          `<div class="prompts-kpi-item"><span class="prompts-kpi-val mono">${val}</span><span class="prompts-kpi-label">${label}</span></div>`
      )
      .join('');
  }

  function filteredPrompts() {
    const tag = ($('prompts-tag-filter')?.value || '').trim();
    const q = ($('prompts-search')?.value || '').trim().toLowerCase();
    return prompts.filter((p) => {
      if (tag && p.tag !== tag) return false;
      if (!q) return true;
      const hay = `${p.name} ${p.description} ${p.content} ${p.id}`.toLowerCase();
      return hay.includes(q);
    });
  }

  function renderList() {
    const el = $('prompts-list');
    if (!el) return;
    const items = filteredPrompts();
    if (!items.length) {
      el.innerHTML = '<div class="prompts-empty">暂无匹配模板</div>';
      return;
    }
    el.innerHTML = items
      .map((p) => {
        const active = p.id === selectedId ? ' active' : '';
        const badges = [
          `<span class="prompts-tag tag-${escapeHtml(p.tag)}">${escapeHtml(TAG_LABEL[p.tag] || p.tag)}</span>`,
          p.is_builtin ? '<span class="prompts-badge">内置</span>' : '',
          !p.enabled ? '<span class="prompts-badge off">已禁用</span>' : '',
        ]
          .filter(Boolean)
          .join('');
        return `<button type="button" class="prompts-item${active}" data-id="${escapeHtml(p.id)}" role="option">
          <div class="prompts-item-top">
            <div class="prompts-item-title">${escapeHtml(p.name)}</div>
            <div class="prompts-item-badges">${badges}</div>
          </div>
          <div class="prompts-item-desc">${escapeHtml(p.description || truncate(p.content, 72))}</div>
        </button>`;
      })
      .join('');

    el.querySelectorAll('.prompts-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-id');
        if (id) openEditor(id);
      });
    });
  }

  function fillSelects() {
    const enabled = prompts.filter((p) => p.enabled);
    ['select-prompt', 'select-prompt-sheet'].forEach((sid) => {
      const sel = $(sid);
      if (!sel) return;
      const cur = sel.value;
      const placeholder = sel.querySelector('option[value=""]')?.textContent || '不选用';
      sel.innerHTML =
        `<option value="">${escapeHtml(placeholder)}</option>` +
        enabled
          .map((p) => {
            const label = `${p.name} · ${TAG_LABEL[p.tag] || p.tag}`;
            return `<option value="${escapeHtml(p.id)}">${escapeHtml(label)}</option>`;
          })
          .join('');
      if (cur && enabled.some((p) => p.id === cur)) sel.value = cur;
    });
  }

  async function loadPrompts(quiet) {
    try {
      const r = await apiFetch('/tongling/api/prompts');
      const d = await r.json();
      if (!d.success) {
        if (!quiet) setEditorStatus(d.error || '加载失败', 'err');
        return;
      }
      prompts = d.prompts || [];
      renderKpi(d.stats);
      renderList();
      fillSelects();
      if (selectedId && !prompts.some((p) => p.id === selectedId) && !editingNew) {
        selectedId = '';
        showEditorEmpty();
      } else if (selectedId && !editingNew) {
        openEditor(selectedId, true);
      }
    } catch (e) {
      if (!quiet) setEditorStatus(String(e), 'err');
    }
  }

  function showEditorEmpty() {
    editingNew = false;
    selectedId = '';
    const form = $('prompts-editor-form');
    const empty = $('prompts-editor-empty');
    if (form) form.hidden = true;
    if (empty) empty.hidden = false;
    renderList();
  }

  function openEditor(id, keepScroll) {
    const item = prompts.find((p) => p.id === id);
    if (!item) return;
    editingNew = false;
    selectedId = id;
    const form = $('prompts-editor-form');
    const empty = $('prompts-editor-empty');
    if (empty) empty.hidden = true;
    if (form) form.hidden = false;

    $('prompts-editor-title').textContent = item.is_builtin ? '编辑内置模板' : '编辑模板';
    $('pf-id').value = item.id;
    $('pf-name').value = item.name || '';
    $('pf-desc').value = item.description || '';
    $('pf-tag').value = item.tag || 'custom';
    $('pf-tag').disabled = !!item.is_builtin;
    $('pf-enabled').checked = !!item.enabled;
    $('pf-content').value = item.content || '';

    const badges = $('prompts-editor-badges');
    if (badges) {
      badges.innerHTML = [
        item.is_builtin ? '<span class="prompts-badge">内置</span>' : '<span class="prompts-badge custom">自定义</span>',
        `<span class="prompts-tag tag-${escapeHtml(item.tag)}">${escapeHtml(TAG_LABEL[item.tag] || item.tag)}</span>`,
      ].join('');
    }

    const delBtn = $('btn-pf-delete');
    const resetBtn = $('btn-pf-reset');
    if (delBtn) delBtn.hidden = !!item.is_builtin;
    if (resetBtn) resetBtn.hidden = !item.is_builtin;

    $('prompts-preview-box').hidden = true;
    setEditorStatus('');
    if (!keepScroll) renderList();
  }

  function openNewEditor() {
    editingNew = true;
    selectedId = '';
    const form = $('prompts-editor-form');
    const empty = $('prompts-editor-empty');
    if (empty) empty.hidden = true;
    if (form) form.hidden = false;

    $('prompts-editor-title').textContent = '新建模板';
    $('pf-id').value = '';
    $('pf-name').value = '';
    $('pf-desc').value = '';
    $('pf-tag').value = 'custom';
    $('pf-tag').disabled = false;
    $('pf-enabled').checked = true;
    $('pf-content').value = '请对目标 {target} 进行…';
    $('prompts-editor-badges').innerHTML = '<span class="prompts-badge custom">自定义</span>';
    $('btn-pf-delete').hidden = true;
    $('btn-pf-reset').hidden = true;
    $('prompts-preview-box').hidden = true;
    setEditorStatus('');
    renderList();
    $('pf-name')?.focus();
  }

  function collectForm() {
    return {
      name: ($('pf-name')?.value || '').trim(),
      description: ($('pf-desc')?.value || '').trim(),
      tag: ($('pf-tag')?.value || 'custom').trim(),
      enabled: !!$('pf-enabled')?.checked,
      content: ($('pf-content')?.value || '').trim(),
    };
  }

  async function saveForm(ev) {
    if (ev) ev.preventDefault();
    const body = collectForm();
    if (!body.name || !body.content) {
      setEditorStatus('请填写名称和内容', 'err');
      return;
    }
    const id = ($('pf-id')?.value || '').trim();
    try {
      const r = await apiFetch(id ? `/tongling/api/prompts/${encodeURIComponent(id)}` : '/tongling/api/prompts', {
        method: id ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (!d.success) {
        setEditorStatus(d.error || '保存失败', 'err');
        return;
      }
      setEditorStatus(d.message || '已保存', 'ok');
      selectedId = d.prompt?.id || id;
      editingNew = false;
      await loadPrompts(true);
      if (selectedId) openEditor(selectedId, true);
    } catch (e) {
      setEditorStatus(String(e), 'err');
    }
  }

  async function deleteCurrent() {
    const id = ($('pf-id')?.value || '').trim();
    if (!id) return;
    if (!confirm('确定删除此自定义模板？')) return;
    try {
      const r = await apiFetch(`/tongling/api/prompts/${encodeURIComponent(id)}`, { method: 'DELETE' });
      const d = await r.json();
      if (!d.success) {
        setEditorStatus(d.error || '删除失败', 'err');
        return;
      }
      selectedId = '';
      showEditorEmpty();
      await loadPrompts(true);
    } catch (e) {
      setEditorStatus(String(e), 'err');
    }
  }

  async function resetBuiltin() {
    const id = ($('pf-id')?.value || '').trim();
    if (!id) return;
    if (!confirm('恢复为内置默认内容？未保存的修改将丢失。')) return;
    try {
      const r = await apiFetch(`/tongling/api/prompts/${encodeURIComponent(id)}/reset`, { method: 'POST' });
      const d = await r.json();
      if (!d.success) {
        setEditorStatus(d.error || '恢复失败', 'err');
        return;
      }
      setEditorStatus(d.message || '已恢复', 'ok');
      await loadPrompts(true);
      openEditor(id, true);
    } catch (e) {
      setEditorStatus(String(e), 'err');
    }
  }

  function localRender(content, target) {
    const reportPath = 'reports/scan_report.md';
    const t = (target || '').trim() || '{target}';
    return String(content || '')
      .replace(/\{target\}/g, t)
      .replace(/\{report_path\}/g, reportPath);
  }

  function previewVars() {
    const content = ($('pf-content')?.value || '').trim();
    const target =
      ($('input-prompt-target')?.value || '').trim() ||
      ($('input-prompt-target-sheet')?.value || '').trim() ||
      'https://example.com';
    const rendered = localRender(content, target);
    const box = $('prompts-preview-box');
    const text = $('prompts-preview-text');
    if (box) box.hidden = false;
    if (text) text.textContent = rendered;
  }

  async function applyPromptToLaunch(promptId, opts) {
    const id = promptId || ($('pf-id')?.value || '').trim() || ($('select-prompt')?.value || '').trim();
    if (!id && !opts?.fromEditor) {
      // allow applying editor textarea content when creating new
    }
    const target =
      ($('input-prompt-target')?.value || '').trim() ||
      ($('input-prompt-target-sheet')?.value || '').trim();

    let text = '';
    if (opts?.fromEditor) {
      text = localRender(($('pf-content')?.value || '').trim(), target);
    } else if (id) {
      try {
        const r = await apiFetch(`/tongling/api/prompts/${encodeURIComponent(id)}/render`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target, report_path: 'reports/scan_report.md' }),
        });
        const d = await r.json();
        if (!d.success) throw new Error(d.error || '渲染失败');
        text = d.rendered || '';
      } catch (e) {
        const item = prompts.find((p) => p.id === id);
        text = localRender(item?.content || '', target);
        if (!text) throw e;
      }
    }

    if (!text.trim()) return false;

    ['input-prompt', 'input-prompt-sheet'].forEach((fid) => {
      const el = $(fid);
      if (el) el.value = text;
    });
    if (id) {
      ['select-prompt', 'select-prompt-sheet'].forEach((sid) => {
        const sel = $(sid);
        if (sel && [...sel.options].some((o) => o.value === id)) sel.value = id;
      });
    }
    return true;
  }

  function bindUi() {
    $('btn-prompts-refresh')?.addEventListener('click', () => loadPrompts());
    $('btn-prompts-new')?.addEventListener('click', openNewEditor);
    $('prompts-search')?.addEventListener('input', renderList);
    $('prompts-tag-filter')?.addEventListener('change', renderList);
    $('prompts-editor-form')?.addEventListener('submit', saveForm);
    $('btn-pf-cancel')?.addEventListener('click', () => {
      if (editingNew || !selectedId) showEditorEmpty();
      else openEditor(selectedId);
    });
    $('btn-pf-delete')?.addEventListener('click', deleteCurrent);
    $('btn-pf-reset')?.addEventListener('click', resetBuiltin);
    $('btn-pf-preview')?.addEventListener('click', previewVars);
    $('btn-pf-use')?.addEventListener('click', async () => {
      const ok = await applyPromptToLaunch(null, { fromEditor: true });
      setEditorStatus(ok ? '已填入启动选项的初始提示' : '内容为空', ok ? 'ok' : 'err');
      if (ok && global.tonglingSwitchTab) global.tonglingSwitchTab('agent');
    });

    $('btn-prompts-open')?.addEventListener('click', () => {
      if (global.tonglingSwitchTab) global.tonglingSwitchTab('prompts');
    });
    $('btn-prompts-open-sheet')?.addEventListener('click', () => {
      if (global.tonglingSwitchTab) global.tonglingSwitchTab('prompts');
    });

    const applyFromSelect = async (selectId) => {
      const id = ($(selectId)?.value || '').trim();
      if (!id) return;
      try {
        await applyPromptToLaunch(id);
      } catch (e) {
        console.warn(e);
      }
    };

    $('btn-prompt-apply')?.addEventListener('click', () => applyFromSelect('select-prompt'));
    $('btn-prompt-apply-sheet')?.addEventListener('click', () => applyFromSelect('select-prompt-sheet'));
    $('select-prompt')?.addEventListener('change', (e) => {
      if (e.target.value) applyFromSelect('select-prompt');
    });
    $('select-prompt-sheet')?.addEventListener('change', (e) => {
      if (e.target.value) applyFromSelect('select-prompt-sheet');
    });
  }

  global.tonglingPrompts = {
    load: loadPrompts,
    apply: applyPromptToLaunch,
    refreshSelects: fillSelects,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindUi);
  } else {
    bindUi();
  }
})(window);
