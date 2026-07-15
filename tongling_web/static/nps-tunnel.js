(function () {
  'use strict';

  function $(id) { return document.getElementById(id); }

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function apiFetch(path, opts) {
    const fn = window.tonglingApiFetch || window.apiFetch;
    if (typeof fn === 'function') return fn(path, opts);
    const token = new URLSearchParams(location.search).get('token')
      || sessionStorage.getItem('tongling_token') || '';
    const headers = { ...(opts?.headers || {}) };
    if (token) headers['X-Tongling-Token'] = token;
    return fetch(path + (path.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token), {
      ...opts,
      headers,
    });
  }

  function setStatus(text, kind) {
    const el = $('nps-status-box');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'hint-box nps-status-box' + (kind ? ` ${kind}` : '');
    el.hidden = !text;
  }

  let npcBinName = 'npc';

  function fillForm(data) {
    const prefs = data?.prefs || {};
    if ($('nps-server-addr')) $('nps-server-addr').value = prefs.server_addr || '';
    if ($('nps-vkey')) $('nps-vkey').value = prefs.vkey || '';
    if (data?.npc_path) {
      const parts = String(data.npc_path).split(/[/\\]/);
      npcBinName = parts[parts.length - 1] || 'npc';
    }
    if ($('nps-local-port')) $('nps-local-port').textContent = String(data?.api_port || '—');
    if ($('nps-local-target')) $('nps-local-target').textContent = data?.local_target || '—';

    const badge = $('nps-run-badge');
    if (badge) {
      if (!data?.ready) {
        badge.textContent = 'npc 未安装';
        badge.className = 'nps-badge warn';
      } else if (data?.running) {
        badge.textContent = `运行中 · PID ${data.pid || ''}`.trim();
        badge.className = 'nps-badge ok';
      } else {
        badge.textContent = '已停止';
        badge.className = 'nps-badge idle';
      }
    }

    const cmdPrev = $('nps-cmd-preview');
    if (cmdPrev) {
      if (data?.command_preview) {
        cmdPrev.innerHTML = `启动命令：<code class="mono">${escapeHtml(data.command_preview)}</code>`;
        cmdPrev.hidden = false;
      } else {
        cmdPrev.hidden = true;
        cmdPrev.textContent = '';
      }
    }

    const missing = $('nps-missing-box');
    if (missing) {
      if (data?.ready) {
        missing.hidden = true;
      } else {
        missing.hidden = false;
        missing.innerHTML =
          '未检测到 <code>storage/nps/npc</code>。请在统领桌面端打开「AI 渗透终端」时按提示下载 <strong>nps</strong> 工具包，或在工具箱中手动下载解压到 storage/nps。';
      }
    }

    const log = $('nps-log');
    if (log) log.textContent = data?.log_tail || '（暂无日志）';

    const btnStart = $('btn-nps-start');
    const btnStop = $('btn-nps-stop');
    if (btnStart) btnStart.disabled = !data?.ready || !!data?.running;
    if (btnStop) btnStop.disabled = !data?.running;
  }

  async function refresh() {
    setStatus('加载中…', '');
    try {
      const r = await apiFetch('/tongling/api/nps/status');
      const d = await r.json();
      if (!d.success) {
        setStatus(d.error || '加载失败', 'err');
        return;
      }
      fillForm(d);
      updateCmdPreview();
      setStatus('', '');
    } catch (e) {
      setStatus('加载失败: ' + e.message, 'err');
    }
  }

  function collectPrefs() {
    return {
      server_addr: ($('nps-server-addr')?.value || '').trim(),
      vkey: ($('nps-vkey')?.value || '').trim(),
      tunnel_type: 'tcp',
    };
  }

  function updateCmdPreview() {
    const addr = ($('nps-server-addr')?.value || '').trim();
    const vkey = ($('nps-vkey')?.value || '').trim();
    const el = $('nps-cmd-preview');
    if (!el) return;
    if (addr && vkey) {
      el.innerHTML = `启动命令：<code class="mono">${escapeHtml(npcBinName)} -server=${escapeHtml(addr)} -vkey=${escapeHtml(vkey)} -type=tcp</code>`;
      el.hidden = false;
    }
  }

  async function savePrefs() {
    setStatus('保存配置…', '');
    try {
      const r = await apiFetch('/tongling/api/nps/prefs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(collectPrefs()),
      });
      const d = await r.json();
      if (!d.success) {
        setStatus(d.error || '保存失败', 'err');
        return;
      }
      setStatus('配置已保存', 'ok');
      await refresh();
    } catch (e) {
      setStatus('保存失败: ' + e.message, 'err');
    }
  }

  async function startTunnel() {
    setStatus('启动 npc…', '');
    try {
      const r = await apiFetch('/tongling/api/nps/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(collectPrefs()),
      });
      const d = await r.json();
      if (!d.success) {
        setStatus(d.error || '启动失败', 'err');
        await refresh();
        return;
      }
      setStatus(d.message || '已启动', 'ok');
      await refresh();
    } catch (e) {
      setStatus('启动失败: ' + e.message, 'err');
    }
  }

  async function stopTunnel() {
    setStatus('停止 npc…', '');
    try {
      const r = await apiFetch('/tongling/api/nps/stop', { method: 'POST' });
      const d = await r.json();
      setStatus(d.message || '已停止', 'ok');
      await refresh();
    } catch (e) {
      setStatus('停止失败: ' + e.message, 'err');
    }
  }

  function bind() {
    $('btn-nps-refresh')?.addEventListener('click', refresh);
    $('btn-nps-save')?.addEventListener('click', savePrefs);
    $('btn-nps-start')?.addEventListener('click', startTunnel);
    $('btn-nps-stop')?.addEventListener('click', stopTunnel);
    $('btn-nps-start-m')?.addEventListener('click', startTunnel);
    $('btn-nps-stop-m')?.addEventListener('click', stopTunnel);
    ['nps-server-addr', 'nps-vkey'].forEach((id) => {
      $(id)?.addEventListener('input', updateCmdPreview);
    });
  }

  window.tonglingNpsTunnel = { refresh, bind };
  bind();
})();
