/**
 * 统领项目目录文件管理（只读）：列表 / 预览 / 下载
 */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  let currentPath = '';
  let loading = false;
  let selectedPath = '';
  let bound = false;

  function escapeHtml(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function apiFetch(url, options) {
    if (typeof window.tonglingApiFetch === 'function') {
      return window.tonglingApiFetch(url, options);
    }
    return fetch(url, options);
  }

  function formatSize(n) {
    const v = Number(n) || 0;
    if (v < 1024) return `${v} B`;
    if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
    if (v < 1024 * 1024 * 1024) return `${(v / (1024 * 1024)).toFixed(1)} MB`;
    return `${(v / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  }

  function formatTime(ts) {
    if (!ts) return '—';
    try {
      return new Date(ts * 1000).toLocaleString('zh-CN', {
        month: 'numeric',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      });
    } catch {
      return '—';
    }
  }

  function setStatus(msg, isErr) {
    const el = $('files-status');
    if (!el) return;
    el.textContent = msg || '';
    el.classList.toggle('is-err', !!isErr);
  }

  function renderCrumbs(path, crumbs) {
    const el = $('files-crumbs');
    if (!el) return;
    const parts = [
      `<button type="button" class="files-crumb" data-path="">${(window.tonglingI18n?.t?.('files.root')) || '统领根目录'}</button>`,
      ...(crumbs || []).map((c) =>
        `<span class="files-crumb-sep">/</span><button type="button" class="files-crumb" data-path="${escapeHtml(c.path)}">${escapeHtml(c.name)}</button>`
      ),
    ];
    el.innerHTML = parts.join('');
    el.querySelectorAll('.files-crumb').forEach((btn) => {
      btn.addEventListener('click', () => loadList(btn.getAttribute('data-path') || ''));
    });
    const cur = $('files-current-path');
    if (cur) cur.textContent = path ? `/${path}` : '/';
  }

  function renderList(entries, truncated) {
    const el = $('files-list');
    if (!el) return;
    if (!entries?.length) {
      el.innerHTML = `<div class="files-empty">${(window.tonglingI18n?.t?.('files.empty')) || '此目录为空'}</div>`;
      return;
    }
    el.innerHTML = entries.map((e) => {
      const isDir = e.type === 'dir';
      const icon = isDir ? '📁' : '📄';
      const meta = isDir ? ((window.tonglingI18n?.t?.('files.folder')) || '文件夹') : formatSize(e.size);
      return `<button type="button" class="files-row ${isDir ? 'is-dir' : 'is-file'}" data-type="${escapeHtml(e.type)}" data-path="${escapeHtml(e.path)}" title="${escapeHtml(e.name)}">
        <span class="files-row-icon" aria-hidden="true">${icon}</span>
        <span class="files-row-name">${escapeHtml(e.name)}</span>
        <span class="files-row-meta">${escapeHtml(meta)}</span>
        <span class="files-row-time">${escapeHtml(formatTime(e.mtime))}</span>
      </button>`;
    }).join('') + (truncated
      ? '<div class="files-empty">条目过多，仅显示前一部分</div>'
      : '');

    el.querySelectorAll('.files-row').forEach((btn) => {
      btn.addEventListener('click', () => {
        const type = btn.getAttribute('data-type');
        const path = btn.getAttribute('data-path') || '';
        if (type === 'dir') loadList(path);
        else openFile(path);
      });
      btn.addEventListener('dblclick', () => {
        const type = btn.getAttribute('data-type');
        const path = btn.getAttribute('data-path') || '';
        if (type === 'file') downloadFile(path);
      });
    });
  }

  async function loadList(path) {
    if (loading) return;
    loading = true;
    setStatus('加载中…');
    const preview = $('files-preview');
    if (preview) {
      preview.hidden = true;
      preview.textContent = '';
    }
    selectedPath = '';
    syncActions();
    try {
      const q = new URLSearchParams();
      if (path) q.set('path', path);
      const r = await apiFetch(`/tongling/api/files/list?${q}`);
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.success) throw new Error(d.error || '加载失败');
      currentPath = d.path || '';
      renderCrumbs(currentPath, d.crumbs || []);
      renderList(d.entries || [], !!d.truncated);
      const rootEl = $('files-root-hint');
      if (rootEl && d.root) rootEl.textContent = d.root;
      setStatus(`${(d.entries || []).length} 项` + (d.truncated ? '（已截断）' : ''));
    } catch (e) {
      setStatus(String(e.message || e), true);
      const el = $('files-list');
      if (el) el.innerHTML = `<div class="files-empty">${escapeHtml(String(e.message || e))}</div>`;
    } finally {
      loading = false;
    }
  }

  function syncActions() {
    const dl = $('btn-files-download');
    const up = $('btn-files-up');
    if (dl) dl.disabled = !selectedPath;
    if (up) up.disabled = !currentPath;
  }

  async function openFile(path) {
    selectedPath = path;
    syncActions();
    const preview = $('files-preview');
    const title = $('files-preview-title');
    if (title) title.textContent = path.split('/').pop() || path;
    if (preview) {
      preview.hidden = false;
      preview.textContent = '加载预览…';
    }
    setStatus('读取文件…');
    try {
      const q = new URLSearchParams({ path });
      const r = await apiFetch(`/tongling/api/files/read?${q}`);
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.success) throw new Error(d.error || '无法预览');
      if (preview) {
        preview.textContent = d.content || '';
        preview.scrollTop = 0;
      }
      setStatus(
        `${d.name || path} · ${formatSize(d.size)}`
        + (d.truncated ? ' · 预览已截断' : ''),
      );
    } catch (e) {
      if (preview) preview.textContent = String(e.message || e);
      setStatus(String(e.message || e), true);
    }
  }

  function downloadFile(path) {
    const p = path || selectedPath;
    if (!p) return;
    const q = new URLSearchParams({ path: p });
    const url = `/tongling/api/files/download?${q}`;
    setStatus('准备下载…');
    apiFetch(url)
      .then(async (r) => {
        if (!r.ok) {
          const d = await r.json().catch(() => ({}));
          throw new Error(d.error || '下载失败');
        }
        const blob = await r.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = p.split('/').pop() || 'download';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(a.href);
        setStatus(`已下载 ${p.split('/').pop()}`);
      })
      .catch((e) => setStatus(String(e.message || e), true));
  }

  function bind() {
    if (bound) return;
    bound = true;
    $('btn-files-refresh')?.addEventListener('click', () => loadList(currentPath));
    $('btn-files-up')?.addEventListener('click', () => {
      if (!currentPath) return;
      const parts = currentPath.split('/');
      parts.pop();
      loadList(parts.join('/'));
    });
    $('btn-files-home')?.addEventListener('click', () => loadList(''));
    $('btn-files-download')?.addEventListener('click', () => downloadFile(selectedPath));
    $('btn-files-close-preview')?.addEventListener('click', () => {
      const preview = $('files-preview');
      if (preview) {
        preview.hidden = true;
        preview.textContent = '';
      }
      selectedPath = '';
      syncActions();
    });
  }

  function load() {
    bind();
    loadList(currentPath || '');
  }

  window.tonglingFiles = {
    load,
    refresh: () => loadList(currentPath),
    open: (path) => loadList(path || ''),
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
