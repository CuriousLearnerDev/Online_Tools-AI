/**
 * 统领文件管理（Dolphin 风格）：本机任意目录 / 历史 / 剪贴板 / 右键菜单
 */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const LS_SORT = 'tongling_files_sort';
  const LS_HIDDEN = 'tongling_files_show_hidden';
  const LS_VIEW = 'tongling_files_view';
  const COMPUTER = '__computer__';

  let currentPath = '';
  let parentPath = COMPUTER;
  let projectRoot = '';
  let loading = false;
  let selectedPath = '';
  let selectedType = '';
  let bound = false;
  /** @type {Array<{name:string,path:string,type:string,size:number,mtime:number}>} */
  let allEntries = [];
  let truncated = false;
  let previewText = '';
  let previewEditable = false;
  let previewDirty = false;
  let viewMode = 'icons';
  let dirWritable = true;

  /** @type {string[]} */
  let histBack = [];
  /** @type {string[]} */
  let histFwd = [];
  let skipHist = false;

  /** @type {{mode:'copy'|'cut', paths:string[]} | null} */
  let clipboard = null;
  let placesLoaded = false;

  const ICON_DIR = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>';
  const ICON_FILE = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3v5h5"/></svg>';

  function t(key, fallback) {
    return window.tonglingI18n?.t?.(key) || fallback || key;
  }

  function escapeHtml(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function cssEscape(s) {
    if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(s);
    return String(s).replace(/["\\]/g, '\\$&');
  }

  function apiFetch(url, options) {
    if (typeof window.tonglingApiFetch === 'function') {
      return window.tonglingApiFetch(url, options);
    }
    return fetch(url, options);
  }

  async function apiJson(url, options) {
    const r = await apiFetch(url, options);
    const d = await r.json().catch(() => ({}));
    if (!r.ok || d.success === false) {
      throw new Error(d.error || `请求失败 (${r.status})`);
    }
    return d;
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
      const loc = window.tonglingI18n?.locale === 'en' ? 'en-US' : 'zh-CN';
      return new Date(ts * 1000).toLocaleString(loc, {
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

  function getSort() {
    return $('files-sort')?.value || 'name';
  }

  function showHidden() {
    return !!$('files-show-hidden')?.checked;
  }

  function getQuery() {
    return ($('files-search')?.value || '').trim().toLowerCase();
  }

  function filteredEntries() {
    const q = getQuery();
    const hideDot = !showHidden();
    let list = allEntries.filter((e) => {
      if (hideDot && String(e.name || '').startsWith('.')) return false;
      if (q && !String(e.name || '').toLowerCase().includes(q)) return false;
      return true;
    });
    const sort = getSort();
    list = list.slice().sort((a, b) => {
      if (a.type !== b.type) return a.type === 'dir' ? -1 : 1;
      if (sort === 'size') return (b.size || 0) - (a.size || 0) || a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
      if (sort === 'mtime') return (b.mtime || 0) - (a.mtime || 0) || a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
      return String(a.name).localeCompare(String(b.name), undefined, { sensitivity: 'base' });
    });
    return list;
  }

  function pushHistory(fromPath) {
    if (skipHist) return;
    if (fromPath === currentPath) return;
    histBack.push(fromPath);
    if (histBack.length > 80) histBack.shift();
    histFwd = [];
  }

  function syncNavButtons() {
    const back = $('btn-files-back');
    const fwd = $('btn-files-forward');
    const up = $('btn-files-up');
    if (back) back.disabled = !histBack.length;
    if (fwd) fwd.disabled = !histFwd.length;
    if (up) up.disabled = currentPath === COMPUTER;
  }

  function syncPlaces(path) {
    const p = path || '';
    document.querySelectorAll('#files-places-list .files-place[data-jump]').forEach((btn) => {
      const jump = btn.getAttribute('data-jump') || '';
      btn.classList.toggle('is-active', jump === p);
    });
  }

  function syncViewButtons() {
    const icons = $('btn-files-view-icons');
    const details = $('btn-files-view-details');
    const list = $('files-list');
    icons?.classList.toggle('is-active', viewMode === 'icons');
    details?.classList.toggle('is-active', viewMode === 'details');
    if (list) {
      list.classList.toggle('view-icons', viewMode === 'icons');
      list.classList.toggle('view-details', viewMode === 'details');
    }
  }

  function setView(mode) {
    viewMode = mode === 'details' ? 'details' : 'icons';
    try { localStorage.setItem(LS_VIEW, viewMode); } catch { /* ignore */ }
    syncViewButtons();
    renderList();
  }

  async function loadPlaces() {
    const box = $('files-places-list');
    if (!box) return;
    try {
      const d = await apiJson('/tongling/api/files/places');
      if (d.project) projectRoot = d.project;
      const places = Array.isArray(d.places) ? d.places : [];
      box.innerHTML = places.map((p) =>
        `<button type="button" class="files-place" data-jump="${escapeHtml(p.path)}"><span class="files-place-ico" aria-hidden="true">${escapeHtml(p.icon || '•')}</span>${escapeHtml(p.name)}</button>`
      ).join('');
      placesLoaded = true;
      syncPlaces(currentPath);
    } catch {
      if (!placesLoaded) {
        box.innerHTML = `<button type="button" class="files-place" data-jump="${COMPUTER}"><span class="files-place-ico">▣</span>计算机</button>`;
      }
    }
  }

  function renderCrumbs(path, crumbs) {
    const el = $('files-crumbs');
    if (!el) return;
    const list = crumbs && crumbs.length
      ? crumbs
      : [{ name: path === COMPUTER ? '计算机' : (path || '/'), path: path || COMPUTER }];
    el.innerHTML = list.map((c, i) => {
      const btn = `<button type="button" class="files-crumb" data-path="${escapeHtml(c.path)}">${escapeHtml(c.name)}</button>`;
      return i === 0 ? btn : `<span class="files-crumb-sep">/</span>${btn}`;
    }).join('');
    el.querySelectorAll('.files-crumb').forEach((btn) => {
      btn.addEventListener('click', () => navigateTo(btn.getAttribute('data-path') || COMPUTER));
    });
    const cur = $('files-current-path');
    if (cur) cur.textContent = path === COMPUTER ? '计算机' : (path || '/');
    syncPlaces(path);
  }

  function renderList() {
    const el = $('files-list');
    if (!el) return;
    syncViewButtons();
    const entries = filteredEntries();
    if (!entries.length) {
      const msg = allEntries.length
        ? (getQuery() ? '无匹配项' : (showHidden() ? t('files.empty', '此目录为空') : '无可见项（可勾选「隐藏项」）'))
        : t('files.empty', '此目录为空');
      el.innerHTML = `<div class="files-empty">${escapeHtml(msg)}</div>`;
      return;
    }
    el.innerHTML = entries.map((e) => {
      const isDir = e.type === 'dir';
      const icon = isDir ? ICON_DIR : ICON_FILE;
      const meta = isDir ? t('files.folder', '文件夹') : formatSize(e.size);
      const sel = e.path === selectedPath ? ' is-selected' : '';
      return `<button type="button" class="files-row ${isDir ? 'is-dir' : 'is-file'}${sel}" data-type="${escapeHtml(e.type)}" data-path="${escapeHtml(e.path)}" data-name="${escapeHtml(e.name)}" title="${escapeHtml(e.name)}">
        <span class="files-row-icon" aria-hidden="true">${icon}</span>
        <span class="files-row-name">${escapeHtml(e.name)}</span>
        <span class="files-row-meta">${escapeHtml(meta)}</span>
        <span class="files-row-time">${escapeHtml(formatTime(e.mtime))}</span>
      </button>`;
    }).join('') + (truncated
      ? '<div class="files-empty">条目过多，仅显示前一部分</div>'
      : '');

    el.querySelectorAll('.files-row').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const type = btn.getAttribute('data-type');
        const path = btn.getAttribute('data-path') || '';
        selectEntry(path, type);
        if (type === 'file') openFile(path);
      });
      btn.addEventListener('dblclick', (ev) => {
        ev.preventDefault();
        const type = btn.getAttribute('data-type');
        const path = btn.getAttribute('data-path') || '';
        if (type === 'dir') navigateTo(path);
        else downloadFile(path);
      });
      btn.addEventListener('contextmenu', (ev) => {
        ev.preventDefault();
        const type = btn.getAttribute('data-type');
        const path = btn.getAttribute('data-path') || '';
        selectEntry(path, type);
        showCtx(ev.clientX, ev.clientY, true);
      });
    });
  }

  function selectEntry(path, type) {
    selectedPath = path || '';
    selectedType = type || '';
    document.querySelectorAll('.files-row.is-selected').forEach((n) => n.classList.remove('is-selected'));
    if (path) {
      const row = document.querySelector(`.files-row[data-path="${cssEscape(path)}"]`);
      row?.classList.add('is-selected');
    }
    syncActions();
  }

  function syncActions() {
    const hasSel = !!selectedPath;
    const isFile = selectedType === 'file';
    const canWrite = dirWritable && currentPath !== COMPUTER;
    const ids = {
      'btn-files-download': isFile,
      'btn-files-cut': hasSel && canWrite,
      'btn-files-copy': hasSel,
      'btn-files-rename': hasSel && canWrite,
      'btn-files-delete': hasSel && canWrite,
      'btn-files-paste': !!(clipboard && clipboard.paths.length) && canWrite,
      'btn-files-save-preview': previewEditable && previewDirty,
      'btn-files-copy-preview': !!previewText,
      'btn-files-mkdir': canWrite,
      'btn-files-newfile': canWrite,
      'btn-files-upload': canWrite,
    };
    Object.entries(ids).forEach(([id, en]) => {
      const el = $(id);
      if (el) el.disabled = !en;
    });
    syncNavButtons();
  }

  async function navigateTo(path, opts) {
    const options = opts || {};
    if (loading) return;
    const from = currentPath;
    const target = path || projectRoot || '';
    if (!options.replaceHist && from !== target && !options.fromHist) {
      pushHistory(from);
    }
    await loadList(target, { keepSelection: !!options.keepSelection });
  }

  async function goBack() {
    if (!histBack.length) return;
    const prev = histBack.pop();
    histFwd.push(currentPath);
    skipHist = true;
    try {
      await loadList(prev || projectRoot || '');
    } finally {
      skipHist = false;
      syncNavButtons();
    }
  }

  async function goForward() {
    if (!histFwd.length) return;
    const next = histFwd.pop();
    histBack.push(currentPath);
    skipHist = true;
    try {
      await loadList(next || projectRoot || '');
    } finally {
      skipHist = false;
      syncNavButtons();
    }
  }

  async function loadList(path, opts) {
    if (loading) return;
    loading = true;
    const keep = !!(opts && opts.keepSelection);
    setStatus(t('status.loading', '加载中…'));
    if (!keep) {
      clearPreview(false);
      selectedPath = '';
      selectedType = '';
    }
    syncActions();
    try {
      const q = new URLSearchParams();
      if (path) q.set('path', path);
      const d = await apiJson(`/tongling/api/files/list?${q}`);
      currentPath = d.path || '';
      parentPath = d.parent != null ? d.parent : COMPUTER;
      dirWritable = d.writable !== false;
      if (d.project) projectRoot = d.project;
      allEntries = Array.isArray(d.entries) ? d.entries : [];
      truncated = !!d.truncated;
      renderCrumbs(currentPath, d.crumbs || []);
      renderList();
      const rootEl = $('files-root-hint');
      if (rootEl) {
        rootEl.textContent = currentPath === COMPUTER
          ? '本机磁盘（双击盘符进入）'
          : `${currentPath} · 可读写`;
      }
      const shown = filteredEntries().length;
      setStatus(`${shown} / ${allEntries.length} 项` + (truncated ? '（已截断）' : ''));
      syncActions();
    } catch (e) {
      setStatus(String(e.message || e), true);
      allEntries = [];
      const el = $('files-list');
      if (el) el.innerHTML = `<div class="files-empty">${escapeHtml(String(e.message || e))}</div>`;
    } finally {
      loading = false;
      syncNavButtons();
    }
  }

  function clearPreview(clearSelection) {
    const preview = $('files-preview');
    const title = $('files-preview-title');
    const info = $('files-info');
    previewText = '';
    previewEditable = false;
    previewDirty = false;
    if (preview) {
      preview.hidden = true;
      preview.value = '';
      preview.readOnly = true;
    }
    if (title) title.textContent = '信息 / 预览';
    if (info) info.hidden = false;
    if (clearSelection) {
      selectedPath = '';
      selectedType = '';
      document.querySelectorAll('.files-row.is-selected').forEach((n) => n.classList.remove('is-selected'));
    }
    syncActions();
  }

  async function openFile(path) {
    selectedPath = path;
    selectedType = 'file';
    syncActions();
    document.querySelectorAll('.files-row.is-selected').forEach((n) => n.classList.remove('is-selected'));
    document.querySelector(`.files-row[data-path="${cssEscape(path)}"]`)?.classList.add('is-selected');

    const preview = $('files-preview');
    const title = $('files-preview-title');
    const info = $('files-info');
    if (title) title.textContent = path.split('/').pop() || path;
    if (info) info.hidden = true;
    if (preview) {
      preview.hidden = false;
      preview.value = '加载预览…';
      preview.readOnly = true;
    }
    previewDirty = false;
    previewEditable = false;
    setStatus('读取文件…');
    try {
      const q = new URLSearchParams({ path });
      const d = await apiJson(`/tongling/api/files/read?${q}`);
      previewText = d.content || '';
      previewEditable = !!d.editable;
      if (preview) {
        preview.value = previewText;
        preview.readOnly = !previewEditable;
        preview.scrollTop = 0;
      }
      setStatus(
        `${d.name || path} · ${formatSize(d.size)}`
        + (d.truncated ? ' · 预览已截断' : '')
        + (previewEditable ? ' · 可编辑' : ''),
      );
      syncActions();
    } catch (e) {
      previewText = '';
      previewEditable = false;
      if (preview) preview.value = String(e.message || e);
      setStatus(String(e.message || e), true);
      syncActions();
    }
  }

  async function savePreview() {
    if (!selectedPath || selectedType !== 'file' || !previewEditable) return;
    const preview = $('files-preview');
    const content = preview ? preview.value : previewText;
    setStatus('保存中…');
    try {
      await apiJson('/tongling/api/files/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: selectedPath, content }),
      });
      previewText = content;
      previewDirty = false;
      setStatus(`已保存 ${selectedPath.split('/').pop()}`);
      syncActions();
      await loadList(currentPath, { keepSelection: true });
    } catch (e) {
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

  async function copyText(text, okMsg) {
    const s = String(text || '');
    if (!s) return;
    try {
      await navigator.clipboard.writeText(s);
      setStatus(okMsg || '已复制');
    } catch {
      setStatus('复制失败（浏览器权限）', true);
    }
  }

  function pathToCopy() {
    if (selectedPath) return selectedPath;
    return currentPath === COMPUTER ? '计算机' : (currentPath || '/');
  }

  async function revealInSystem() {
    const path = selectedPath || (currentPath === COMPUTER ? '' : currentPath) || projectRoot || '';
    setStatus('正在打开系统文件夹…');
    try {
      const d = await apiJson('/tongling/api/files/reveal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      setStatus(d.message || '已在系统文件管理器中打开');
    } catch (e) {
      setStatus(String(e.message || e), true);
    }
  }

  function goUp() {
    if (currentPath === COMPUTER) return;
    navigateTo(parentPath || COMPUTER);
  }

  function doGoto() {
    const cur = currentPath === COMPUTER ? (projectRoot || '') : currentPath;
    const input = window.prompt('转到路径（如 D:/桌面 或 C:/Users）：', cur);
    if (input == null) return;
    const p = String(input).trim().replace(/\\/g, '/');
    if (!p) return;
    navigateTo(p);
  }

  function setClipboard(mode) {
    if (!selectedPath) return;
    clipboard = { mode, paths: [selectedPath] };
    setStatus(mode === 'cut' ? `已剪切 ${selectedPath.split('/').pop()}` : `已复制 ${selectedPath.split('/').pop()}`);
    syncActions();
  }

  async function pasteClipboard() {
    if (!clipboard || !clipboard.paths.length) return;
    if (currentPath === COMPUTER) {
      setStatus('请先进入某个磁盘目录再粘贴', true);
      return;
    }
    const destDir = currentPath || '';
    const mode = clipboard.mode;
    const paths = clipboard.paths.slice();
    setStatus(mode === 'cut' ? '移动中…' : '复制中…');
    try {
      for (const src of paths) {
        const endpoint = mode === 'cut' ? '/tongling/api/files/move' : '/tongling/api/files/copy';
        await apiJson(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ src, dest_dir: destDir }),
        });
      }
      if (mode === 'cut') clipboard = null;
      setStatus(mode === 'cut' ? '已移动' : '已粘贴');
      await loadList(currentPath);
    } catch (e) {
      setStatus(String(e.message || e), true);
    }
  }

  async function doMkdir() {
    if (currentPath === COMPUTER) return;
    const name = window.prompt('新建文件夹名称：', '新建文件夹');
    if (!name) return;
    try {
      await apiJson('/tongling/api/files/mkdir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: currentPath || '', name }),
      });
      setStatus(`已创建文件夹 ${name}`);
      await loadList(currentPath);
    } catch (e) {
      setStatus(String(e.message || e), true);
    }
  }

  async function doNewFile() {
    if (currentPath === COMPUTER) return;
    const name = window.prompt('新建文件名称：', 'untitled.txt');
    if (!name) return;
    try {
      const d = await apiJson('/tongling/api/files/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: currentPath || '', name, content: '' }),
      });
      setStatus(`已创建文件 ${name}`);
      await loadList(currentPath);
      if (d.path) await openFile(d.path);
    } catch (e) {
      setStatus(String(e.message || e), true);
    }
  }

  async function doRename() {
    if (!selectedPath) return;
    const oldName = selectedPath.split('/').filter(Boolean).pop() || '';
    const newName = window.prompt('重命名为：', oldName);
    if (!newName || newName === oldName) return;
    try {
      const d = await apiJson('/tongling/api/files/rename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: selectedPath, new_name: newName }),
      });
      setStatus(`已重命名为 ${newName}`);
      selectedPath = d.path || '';
      await loadList(currentPath, { keepSelection: true });
      if (selectedType === 'file' && selectedPath) await openFile(selectedPath);
    } catch (e) {
      setStatus(String(e.message || e), true);
    }
  }

  async function doDelete() {
    if (!selectedPath) return;
    const name = selectedPath.split('/').filter(Boolean).pop() || selectedPath;
    if (!window.confirm(`确定删除「${name}」？\n此操作不可撤销。`)) return;
    try {
      await apiJson('/tongling/api/files/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths: [selectedPath] }),
      });
      setStatus(`已删除 ${name}`);
      clearPreview(true);
      await loadList(currentPath);
    } catch (e) {
      setStatus(String(e.message || e), true);
    }
  }

  function triggerUpload() {
    if (currentPath === COMPUTER) return;
    $('files-upload-input')?.click();
  }

  async function onUploadChange(ev) {
    const input = ev.target;
    const files = input?.files;
    if (!files || !files.length) return;
    const fd = new FormData();
    fd.append('path', currentPath || '');
    for (const f of files) fd.append('files', f);
    setStatus(`上传 ${files.length} 个文件…`);
    try {
      const d = await apiJson('/tongling/api/files/upload', { method: 'POST', body: fd });
      setStatus(`已上传 ${(d.paths || []).length} 个文件`);
      await loadList(currentPath);
    } catch (e) {
      setStatus(String(e.message || e), true);
    } finally {
      if (input) input.value = '';
    }
  }

  function hideCtx() {
    const ctx = $('files-ctx');
    if (ctx) ctx.hidden = true;
  }

  function showCtx(x, y, onItem) {
    const ctx = $('files-ctx');
    if (!ctx) return;
    ctx.hidden = false;
    const canWrite = dirWritable && currentPath !== COMPUTER;
    const pasteBtn = ctx.querySelector('[data-act="paste"]');
    const itemActs = ['open', 'download', 'cut', 'copy', 'rename', 'delete'];
    itemActs.forEach((act) => {
      const btn = ctx.querySelector(`[data-act="${act}"]`);
      if (!btn) return;
      if (!onItem) {
        btn.disabled = true;
      } else {
        btn.disabled = false;
        if (act === 'download') btn.disabled = selectedType !== 'file';
        if (['cut', 'rename', 'delete'].includes(act)) btn.disabled = !canWrite;
      }
    });
    if (pasteBtn) pasteBtn.disabled = !(clipboard && clipboard.paths.length) || !canWrite;
    const mkdirBtn = ctx.querySelector('[data-act="mkdir"]');
    const newfileBtn = ctx.querySelector('[data-act="newfile"]');
    const uploadBtn = ctx.querySelector('[data-act="upload"]');
    if (mkdirBtn) mkdirBtn.disabled = !canWrite;
    if (newfileBtn) newfileBtn.disabled = !canWrite;
    if (uploadBtn) uploadBtn.disabled = !canWrite;

    const pad = 8;
    const w = ctx.offsetWidth || 160;
    const h = ctx.offsetHeight || 280;
    let left = x;
    let top = y;
    if (left + w > window.innerWidth - pad) left = window.innerWidth - w - pad;
    if (top + h > window.innerHeight - pad) top = window.innerHeight - h - pad;
    ctx.style.left = `${Math.max(pad, left)}px`;
    ctx.style.top = `${Math.max(pad, top)}px`;
  }

  async function runCtxAct(act) {
    hideCtx();
    switch (act) {
      case 'open':
        if (selectedType === 'dir') navigateTo(selectedPath);
        else if (selectedType === 'file') openFile(selectedPath);
        break;
      case 'download': downloadFile(selectedPath); break;
      case 'cut': setClipboard('cut'); break;
      case 'copy': setClipboard('copy'); break;
      case 'paste': await pasteClipboard(); break;
      case 'rename': await doRename(); break;
      case 'delete': await doDelete(); break;
      case 'goto': doGoto(); break;
      case 'mkdir': await doMkdir(); break;
      case 'newfile': await doNewFile(); break;
      case 'upload': triggerUpload(); break;
      case 'reveal': await revealInSystem(); break;
      case 'copypath': await copyText(pathToCopy(), '路径已复制'); break;
      default: break;
    }
  }

  function isTypingTarget(el) {
    if (!el) return false;
    const tag = (el.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
    return !!el.isContentEditable;
  }

  function onKeydown(e) {
    if (!e.target?.closest?.('#panel-files')) return;

    if (e.key === 'Escape') {
      hideCtx();
      if (e.target?.id === 'files-search') {
        e.target.value = '';
        renderList();
        return;
      }
      if (!isTypingTarget(e.target) || e.target?.id === 'files-preview') {
        if (e.target?.id !== 'files-preview') {
          clearPreview(true);
          renderList();
        }
      }
      return;
    }

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's' && e.target?.id === 'files-preview') {
      e.preventDefault();
      savePreview();
      return;
    }

    if (isTypingTarget(e.target) && e.target?.id !== 'files-list') {
      if (e.target?.id === 'files-search' && e.key === 'Escape') return;
      if (e.target?.id === 'files-preview') return;
      return;
    }

    if (e.key === 'Backspace' && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      goUp();
      return;
    }
    if (e.key === 'F2') {
      e.preventDefault();
      doRename();
      return;
    }
    if (e.key === 'Delete' || e.key === 'Del') {
      e.preventDefault();
      doDelete();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') {
      e.preventDefault();
      setClipboard('copy');
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'x') {
      e.preventDefault();
      setClipboard('cut');
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') {
      e.preventDefault();
      pasteClipboard();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'l') {
      e.preventDefault();
      doGoto();
      return;
    }
    if (e.key === 'Enter' && selectedPath) {
      e.preventDefault();
      if (selectedType === 'dir') navigateTo(selectedPath);
      else if (selectedType === 'file') downloadFile(selectedPath);
    }
  }

  function persistPrefs() {
    try {
      localStorage.setItem(LS_SORT, getSort());
      localStorage.setItem(LS_HIDDEN, showHidden() ? '1' : '0');
      localStorage.setItem(LS_VIEW, viewMode);
    } catch { /* ignore */ }
  }

  function restorePrefs() {
    try {
      const sort = localStorage.getItem(LS_SORT);
      if (sort && $('files-sort')) $('files-sort').value = sort;
      const hid = localStorage.getItem(LS_HIDDEN);
      if (hid === '1' && $('files-show-hidden')) $('files-show-hidden').checked = true;
      const view = localStorage.getItem(LS_VIEW);
      if (view === 'details' || view === 'icons') viewMode = view;
    } catch { /* ignore */ }
    syncViewButtons();
  }

  function bind() {
    if (bound) return;
    bound = true;
    restorePrefs();

    $('btn-files-back')?.addEventListener('click', goBack);
    $('btn-files-forward')?.addEventListener('click', goForward);
    $('btn-files-refresh')?.addEventListener('click', () => loadList(currentPath));
    $('btn-files-up')?.addEventListener('click', goUp);
    $('btn-files-home')?.addEventListener('click', () => navigateTo(projectRoot || ''));
    $('btn-files-download')?.addEventListener('click', () => downloadFile(selectedPath));
    $('btn-files-copy-path')?.addEventListener('click', () => copyText(pathToCopy(), '路径已复制'));
    $('btn-files-reveal')?.addEventListener('click', revealInSystem);
    $('btn-files-copy-preview')?.addEventListener('click', () => copyText(($('files-preview')?.value) || previewText, '内容已复制'));
    $('btn-files-save-preview')?.addEventListener('click', savePreview);
    $('btn-files-close-preview')?.addEventListener('click', () => {
      clearPreview(true);
      renderList();
    });
    $('btn-files-cut')?.addEventListener('click', () => setClipboard('cut'));
    $('btn-files-copy')?.addEventListener('click', () => setClipboard('copy'));
    $('btn-files-paste')?.addEventListener('click', pasteClipboard);
    $('btn-files-rename')?.addEventListener('click', doRename);
    $('btn-files-delete')?.addEventListener('click', doDelete);
    $('btn-files-goto')?.addEventListener('click', doGoto);
    $('btn-files-mkdir')?.addEventListener('click', doMkdir);
    $('btn-files-newfile')?.addEventListener('click', doNewFile);
    $('btn-files-upload')?.addEventListener('click', triggerUpload);
    $('files-upload-input')?.addEventListener('change', onUploadChange);

    $('btn-files-view-icons')?.addEventListener('click', () => { setView('icons'); persistPrefs(); });
    $('btn-files-view-details')?.addEventListener('click', () => { setView('details'); persistPrefs(); });

    $('files-preview')?.addEventListener('input', () => {
      if (!previewEditable) return;
      previewDirty = ($('files-preview')?.value || '') !== previewText;
      syncActions();
    });

    let searchTimer = 0;
    $('files-search')?.addEventListener('input', () => {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        searchTimer = 0;
        renderList();
        setStatus(`${filteredEntries().length} / ${allEntries.length} 项` + (truncated ? '（已截断）' : ''));
      }, 180);
    });
    $('files-sort')?.addEventListener('change', () => {
      persistPrefs();
      renderList();
    });
    $('files-show-hidden')?.addEventListener('change', () => {
      persistPrefs();
      renderList();
      setStatus(`${filteredEntries().length} / ${allEntries.length} 项`);
    });

    document.querySelector('.files-places')?.addEventListener('click', (e) => {
      const btn = e.target.closest('.files-place[data-jump]');
      if (!btn) return;
      navigateTo(btn.getAttribute('data-jump') || COMPUTER);
    });

    $('files-list')?.addEventListener('contextmenu', (e) => {
      if (e.target.closest('.files-row')) return;
      e.preventDefault();
      selectEntry('', '');
      showCtx(e.clientX, e.clientY, false);
    });

    $('files-ctx')?.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-act]');
      if (!btn || btn.disabled) return;
      runCtxAct(btn.getAttribute('data-act'));
    });

    document.addEventListener('click', (e) => {
      if (!e.target.closest?.('#files-ctx')) hideCtx();
    });
    document.addEventListener('keydown', onKeydown);
  }

  async function load() {
    bind();
    await loadPlaces();
    await loadList(projectRoot || currentPath || '');
  }

  window.tonglingFiles = {
    load,
    refresh: () => loadList(currentPath),
    open: (path) => navigateTo(path || projectRoot || ''),
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
