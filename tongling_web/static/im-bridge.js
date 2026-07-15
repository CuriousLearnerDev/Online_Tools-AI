(function () {
  'use strict';

  const PLATFORMS = [
    {
      id: 'telegram',
      title: 'Telegram',
      tip: '向 @BotFather 创建 Bot 获取 Token。统领使用 getUpdates 长轮询收消息、sendMessage 回复（无需公网 Webhook）。',
      testTarget: { label: '测试 Chat ID（可选，发测试消息）', placeholder: '123456789' },
      fields: [
        { key: 'bot_token', label: 'Bot Token', type: 'password', placeholder: '123456:ABC…' },
        { key: 'allowed_chat_ids', label: '允许的 Chat ID（逗号分隔，留空=全部）', placeholder: '123456789' },
      ],
    },
    {
      id: 'dingtalk',
      title: '钉钉',
      tip: '填 AppKey/AppSecret 即可，dingtalk-stream 会在启动时自动安装。回复走消息自带 sessionWebhook；下方 Webhook 仅作备用。',
      canSendTest: true,
      fields: [
        { key: 'app_key', label: 'AppKey', placeholder: 'dingxxx' },
        { key: 'app_secret', label: 'AppSecret', type: 'password' },
        { key: 'webhook_url', label: '备用群机器人 Webhook（可选，勿填下方统领回调地址）', placeholder: 'https://oapi.dingtalk.com/robot/send?access_token=…' },
      ],
      webhook: 'dingtalk',
      webhookLabel: '统领 HTTP 回调（钉钉 HTTP 模式用；Stream 模式可不配）',
    },
    {
      id: 'qq',
      title: 'QQ（OneBot / NapCat）',
      tip: 'NapCat 配置反向 HTTP 上报到下方 Webhook；OneBot HTTP API（默认 :3000）发私聊/群聊回复，群聊需 @ 机器人。Token 与 NapCat 一致。',
      fields: [
        { key: 'onebot_http_url', label: 'OneBot HTTP API', placeholder: 'http://127.0.0.1:3000' },
        { key: 'access_token', label: 'Access Token（与 OneBot 一致）', type: 'password' },
      ],
      webhook: 'qq',
      webhookLabel: 'NapCat 反向 HTTP 上报地址',
    },
  ];

  let state = { config: null, webhooks: {}, status: null, testResults: {} };

  function $(id) { return document.getElementById(id); }

  function apiFetch(url, options) {
    if (typeof window.apiFetch === 'function') return window.apiFetch(url, options);
    const t = sessionStorage.getItem('tongling_token') || new URLSearchParams(location.search).get('token') || '';
    const sep = url.includes('?') ? '&' : '?';
    return fetch(t ? `${url}${sep}token=${encodeURIComponent(t)}` : url, options);
  }

  function escapeHtml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function platCfg(id) {
    return (state.config?.platforms || {})[id] || {};
  }

  function fieldValue(id, key) {
    const el = document.querySelector(`[data-im-plat="${id}"][data-im-key="${key}"]`);
    if (!el) return '';
    if (key === 'allowed_chat_ids') {
      return el.value.split(/[,，\s]+/).map((s) => s.trim()).filter(Boolean);
    }
    return el.value.trim();
  }

  function collectPlatformConfig(id) {
    const p = PLATFORMS.find((x) => x.id === id);
    if (!p) return {};
    const row = {};
    p.fields.forEach((f) => {
      row[f.key] = fieldValue(id, f.key);
    });
    return row;
  }

  function renderTestBlock(id) {
    const tr = state.testResults[id];
    if (!tr) return '';
    const cls = tr.success ? 'ok' : 'err';
    const checks = (tr.checks || []).map((c) => {
      const icon = c.ok ? (c.warn ? '⚠' : '✓') : '✗';
      const lineCls = c.ok ? (c.warn ? ' warn' : '') : ' fail';
      return `<li class="im-test-check${lineCls}"><span class="im-test-icon">${icon}</span><span>${escapeHtml(c.name)}</span><span class="im-test-detail">${escapeHtml(c.detail)}</span></li>`;
    }).join('');
    return `<div class="im-test-result ${cls}" data-im-test-result="${id}">
      <div class="im-test-summary">${escapeHtml(tr.message || (tr.success ? '测试通过' : '测试失败'))}</div>
      ${checks ? `<ul class="im-test-checks">${checks}</ul>` : ''}
    </div>`;
  }

  function renderTestControls(p) {
    let html = `<div class="im-test-row">
      <button type="button" class="btn btn-ghost btn-sm" data-im-test="${p.id}">测试连接</button>`;
    if (p.testTarget) {
      html += `<input class="input mono im-test-target" type="text" data-im-test-target="${p.id}"
        placeholder="${escapeHtml(p.testTarget.placeholder || '')}" title="${escapeHtml(p.testTarget.label || '')}" />`;
    }
    if (p.canSendTest) {
      html += `<label class="im-test-send"><input type="checkbox" data-im-send-test="${p.id}" /> 发送测试消息</label>`;
    }
    html += `<span class="im-test-busy" data-im-test-busy="${p.id}" hidden>测试中…</span></div>`;
    html += renderTestBlock(p.id);
    return html;
  }

  function collectConfig() {
    const platforms = {};
    PLATFORMS.forEach((p) => {
      const enabled = document.querySelector(`[data-im-enable="${p.id}"]`)?.checked || false;
      const row = { enabled };
      p.fields.forEach((f) => {
        row[f.key] = fieldValue(p.id, f.key);
      });
      platforms[p.id] = row;
    });
    return {
      enabled: $('im-bridge-enabled')?.checked ?? true,
      workdir: $('im-workdir')?.value.trim() || '',
      proxy: $('im-proxy')?.value.trim() || '',
      reply_timeout_sec: parseInt($('im-timeout')?.value || '300', 10) || 300,
      mirror_to_terminal: $('im-mirror-terminal')?.checked ?? true,
      terminal_proxy_enabled: $('im-terminal-proxy')?.checked ?? true,
      default_terminal_id: $('im-default-terminal')?.value.trim() || '',
      platforms,
    };
  }

  function render() {
    const root = $('im-bridge-root');
    if (!root) return;

    const st = state.status || {};
    const bridgeOn = st.bridge_enabled || st.started;

    let html = `
      <div class="im-toolbar mobile-only">
        <button type="button" class="btn btn-accent btn-sm" id="btn-im-save-m">保存并启动</button>
        <button type="button" class="btn btn-ghost btn-sm" id="btn-im-stop-m">停止</button>
      </div>
      <div class="im-toolbar">
        <span class="im-status-pill${bridgeOn ? ' on' : ''}">${bridgeOn ? '桥接运行中' : '桥接未启动'}</span>
        <span class="im-status-pill mono">超时 ${state.config?.reply_timeout_sec || 300}s</span>
      </div>
      <div class="im-global">
        <label class="cp-check-row">
          <input type="checkbox" id="im-bridge-enabled" ${state.config?.enabled ? 'checked' : ''} />
          <span>启用社交消息桥接（收到消息 → Claude Code -p/-c）</span>
        </label>
        <div class="im-grid" style="margin-top:10px">
          <label class="field im-field">
            <span class="field-label">Claude 工作目录</span>
            <input class="input" id="im-workdir" value="${escapeHtml(state.config?.workdir || '')}" placeholder="storage/node_ai/claude-code" />
          </label>
          <label class="field im-field">
            <span class="field-label">HTTP 代理（可选）</span>
            <input class="input" id="im-proxy" value="${escapeHtml(state.config?.proxy || '')}" placeholder="http://127.0.0.1:7890" />
          </label>
          <label class="field im-field">
            <span class="field-label">Claude 回复超时（秒）</span>
            <input class="input mono" id="im-timeout" type="number" min="30" max="900" value="${state.config?.reply_timeout_sec || 300}" />
          </label>
          <label class="field im-field">
            <span class="field-label">默认遥控终端 ID（可选，如 4 → 终端四，全平台共用）</span>
            <input class="input mono" id="im-default-terminal" value="${escapeHtml(state.config?.default_terminal_id || '')}" placeholder="4" />
          </label>
        </div>
        <label class="cp-check-row" style="margin-top:10px">
          <input type="checkbox" id="im-terminal-proxy" ${state.config?.terminal_proxy_enabled !== false ? 'checked' : ''} />
          <span>允许 <code>ID：1</code> 遥控 AI 终端（终端一 = ID：1，需先在 Web 新建该终端）</span>
        </label>
        <label class="cp-check-row" style="margin-top:6px">
          <input type="checkbox" id="im-mirror-terminal" ${state.config?.mirror_to_terminal !== false ? 'checked' : ''} />
          <span>社交对话同步显示到「AI 智能体」终端（需先打开/连接终端）</span>
        </label>
        <p class="im-tip">遥控示例：<code>ID：1</code> 换行 <code>你好</code>。也可填「默认遥控终端 ID」与钉钉共用同一终端（如填 4 = 终端四）。</p>
      </div>
      <div class="im-grid">
    `;

    PLATFORMS.forEach((p) => {
      const cfg = platCfg(p.id);
      const pst = (st.platforms || {})[p.id] || {};
      const wh = p.webhook ? state.webhooks[p.webhook] : '';
      html += `
        <div class="im-platform-card${cfg.enabled ? ' enabled' : ''}">
          <div class="im-platform-head">
            <h3>${escapeHtml(p.title)}</h3>
            <label><input type="checkbox" data-im-enable="${p.id}" ${cfg.enabled ? 'checked' : ''} /> 启用</label>
          </div>
          <p class="im-tip">${escapeHtml(p.tip)}</p>
          ${p.fields.map((f) => {
            let val = cfg[f.key];
            if (Array.isArray(val)) val = val.join(', ');
            return `<label class="field im-field">
              <span class="field-label">${escapeHtml(f.label)}</span>
              <input class="input" type="${f.type || 'text'}" data-im-plat="${p.id}" data-im-key="${f.key}"
                value="${escapeHtml(val || '')}" placeholder="${escapeHtml(f.placeholder || '')}" />
            </label>`;
          }).join('')}
          ${wh ? `<div class="im-webhook-label">${escapeHtml(p.webhookLabel || 'Webhook 回调地址')}</div><div class="im-webhook mono" title="复制到平台配置">${escapeHtml(wh)}</div>` : ''}
          ${renderTestControls(p)}
          <p class="im-tip mono">已处理 ${pst.processed || 0} 条 · ${pst.mode || '—'}${pst.last_error ? ' · ' + escapeHtml(pst.last_error) : ''}</p>
        </div>`;
    });

    html += '</div><div class="hint-box im-result" id="im-result" hidden></div>';
    root.innerHTML = html;

    $('btn-im-save-m')?.addEventListener('click', save);
    $('btn-im-stop-m')?.addEventListener('click', stop);
    document.querySelectorAll('[data-im-test]').forEach((btn) => {
      btn.addEventListener('click', () => testPlatform(btn.getAttribute('data-im-test')));
    });
  }

  function patchTestResult(id) {
    const card = document.querySelector(`[data-im-test="${id}"]`)?.closest('.im-platform-card');
    if (!card) return;
    const old = card.querySelector(`[data-im-test-result="${id}"]`);
    if (old) old.remove();
    const row = card.querySelector('.im-test-row');
    if (row) row.insertAdjacentHTML('afterend', renderTestBlock(id));
  }

  async function testPlatform(id) {
    const busy = document.querySelector(`[data-im-test-busy="${id}"]`);
    const btn = document.querySelector(`[data-im-test="${id}"]`);
    if (busy) busy.hidden = false;
    if (btn) btn.disabled = true;

    const testTarget = document.querySelector(`[data-im-test-target="${id}"]`)?.value.trim() || '';
    const sendChecked = document.querySelector(`[data-im-send-test="${id}"]`)?.checked || false;
    const sendTest = sendChecked || (id === 'telegram' && !!testTarget);

    try {
      const r = await apiFetch('/tongling/api/im/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          platform: id,
          config: collectPlatformConfig(id),
          send_test: sendTest,
          test_target: testTarget,
        }),
      });
      const d = await r.json();
      state.testResults[id] = {
        success: !!d.success,
        message: d.message || d.error || '',
        checks: d.checks || [],
      };
      patchTestResult(id);
      showResult(d.message || (d.success ? '测试通过' : '测试失败'), !!d.success);
    } catch (e) {
      state.testResults[id] = { success: false, message: String(e), checks: [] };
      patchTestResult(id);
      showResult(String(e), false);
    } finally {
      if (busy) busy.hidden = true;
      if (btn) btn.disabled = false;
    }
  }

  function showResult(text, ok) {
    const el = $('im-result');
    if (!el) return;
    el.hidden = false;
    el.textContent = text;
    el.className = 'hint-box im-result' + (ok ? ' ok' : ' err');
  }

  async function load() {
    try {
      const [cr, sr] = await Promise.all([
        apiFetch('/tongling/api/im/config'),
        apiFetch('/tongling/api/im/status'),
      ]);
      const cd = await cr.json();
      const sd = await sr.json();
      if (cd.success) {
        state.config = cd.config;
        state.webhooks = cd.webhooks || sd.webhooks || {};
      }
      if (sd.success) state.status = sd;
      render();
    } catch (e) {
      const root = $('im-bridge-root');
      if (root) root.innerHTML = `<p class="im-loading">加载失败: ${escapeHtml(e.message)}</p>`;
    }
  }

  async function save() {
    showResult('保存中…', true);
    try {
      const r = await apiFetch('/tongling/api/im/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(collectConfig()),
      });
      const d = await r.json();
      if (!d.success) {
        showResult(d.error || '保存失败', false);
        return;
      }
      state.config = d.config;
      await load();
      showResult('已保存并启动桥接（启用的平台已开始监听）', true);
    } catch (e) {
      showResult(String(e), false);
    }
  }

  async function stop() {
    try {
      await apiFetch('/tongling/api/im/stop', { method: 'POST' });
      await load();
      showResult('桥接已停止', true);
    } catch (e) {
      showResult(String(e), false);
    }
  }

  $('btn-im-save')?.addEventListener('click', save);
  $('btn-im-stop')?.addEventListener('click', stop);
  $('btn-im-refresh')?.addEventListener('click', load);

  window.TonglingImBridge = { load, save, stop, testPlatform };
})();
