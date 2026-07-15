(function () {
  'use strict';

  function t(key) {
    return window.tonglingI18n?.t?.(key) || key;
  }

  /** @type {Record<string, { title: string, crumbTitle?: string, sub?: string }>} */
  let TAB_META = window.tonglingI18n?.tabMetaMap?.() || {
    agent: { title: 'AI 智能体', sub: '' },
    control: { title: '控制面板', crumbTitle: '控制面板', sub: 'API · 会话 · 审计' },
    tasks: { title: '任务监控', sub: '' },
    run: { title: '接口运行', sub: '' },
    tools: { title: '工具目录', sub: '' },
    reports: { title: '扫描报告', sub: '' },
    scanviz: { title: '扫描图谱', crumbTitle: '扫描结果图谱', sub: '' },
    skills: { title: 'Skills', sub: '' },
    prompts: { title: '提示词库', crumbTitle: '提示词库', sub: '' },
    fplib: { title: '指纹库', crumbTitle: 'HFinger 指纹库', sub: '' },
    vulnlib: { title: '漏洞库', crumbTitle: 'Nuclei 漏洞库', sub: '' },
    mcp: { title: 'MCP 连接', sub: '' },
    im: { title: '社交接入', sub: '' },
    nps: { title: '内网穿透', sub: '' },
    files: { title: '文件管理', crumbTitle: '文件管理', sub: '统领项目目录' },
    logs: { title: '服务日志', sub: '' },
    settings: { title: '设置', sub: '' },
    help: { title: '工具说明', sub: '' },
  };

  function rebuildTabMeta() {
    if (window.tonglingI18n?.tabMetaMap) TAB_META = window.tonglingI18n.tabMetaMap();
  }

  const HS_EMBED = '/tongling/hs';
  const LS_TASKS_VIEW = 'tongling_tasks_view';
  const TASKS_IFRAME_VIEWS = {
    monitor: `${HS_EMBED}/#/tasks`,
    sessions: `${HS_EMBED}/#/sessions`,
  };
  const IFRAME_ROUTES = {
    tasks: TASKS_IFRAME_VIEWS.monitor,
    run: `${HS_EMBED}/#/run`,
    tools: `${HS_EMBED}/#/tools`,
    scanviz: '/tongling/scan',
    logs: `${HS_EMBED}/#/logs`,
    settings: `${HS_EMBED}/#/settings`,
    help: `${HS_EMBED}/#/help`,
  };
  let tasksIframeView = localStorage.getItem(LS_TASKS_VIEW) || 'monitor';

  const HS_EMBED_LAYOUT_CSS = `
    .topbar, .demo-banner { display: none !important; }
    .main--flush {
      top: 0 !important;
      position: absolute !important;
      height: 100% !important;
    }
    .layout--demo .main--flush { top: 0 !important; }
    .main {
      max-width: 100% !important;
      padding: 8px 10px 12px !important;
      gap: 12px !important;
    }
    .layout {
      min-height: 100% !important;
      height: 100% !important;
    }
    .card, .panel, .table-wrap, .tool-card, .session-card, .task-card,
    .settings-section, .help-section, .log-view, .run-panel {
      border-color: var(--border) !important;
    }
    input, select, textarea, .input, .select {
      background: var(--input-bg, var(--bg-card)) !important;
      border-color: var(--border) !important;
      color: var(--text-h) !important;
    }
    ::-webkit-scrollbar-track { background: var(--bg) !important; }
    ::-webkit-scrollbar-thumb { background: var(--border) !important; }
  `;

  const EMBED_THEME_VARS = [
    '--bg', '--bg-card', '--bg-card2', '--bg-elevated', '--border', '--border-bright',
    '--text', '--text-h', '--text-dim',
    '--green', '--green-dim', '--red', '--red-dim', '--amber', '--amber-dim',
    '--blue', '--blue-dim', '--cyan', '--cyan-dim',
    '--purple', '--purple-dim', '--pink', '--pink-dim', '--orange', '--orange-dim',
    '--lime', '--lime-dim', '--teal', '--teal-dim', '--indigo', '--indigo-dim',
    '--gray', '--gray-dim', '--white-dim',
    '--accent', '--accent-alt', '--accent-warm',
    '--surface-hover', '--surface-muted', '--input-bg', '--code-bg', '--shadow',
  ];

  function buildEmbedThemeCss() {
    const root = document.documentElement;
    const cs = getComputedStyle(root);
    const themeId = getWebThemeId();
    const lines = EMBED_THEME_VARS.map((name) => {
      const val = cs.getPropertyValue(name).trim();
      return val ? `${name}:${val};` : '';
    }).filter(Boolean);
    const bg = cs.getPropertyValue('--bg').trim();
    const text = cs.getPropertyValue('--text').trim();
    const scheme = themeId === 'light' ? 'light' : 'dark';
    return `
      :root, html {
        color-scheme: ${scheme};
        ${lines.join('')}
      }
      html, body, #root, .layout, .scan-viz-page {
        background: ${bg} !important;
        color: ${text} !important;
        font-family: 'Plus Jakarta Sans', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei UI', system-ui, sans-serif !important;
      }
      .card, .panel, .topbar, .bg-card, [class*="card"] {
        background-color: var(--bg-card) !important;
      }
      ${HS_EMBED_LAYOUT_CSS}
    `;
  }

  function injectHexStrikeEmbedStyles(frame) {
    if (!frame) return;
    try {
      const doc = frame.contentDocument;
      if (!doc || !doc.head) return;
      const themeId = getWebThemeId();
      if (doc.documentElement) doc.documentElement.setAttribute('data-theme', themeId);
      let el = doc.getElementById('tongling-embed-style');
      if (!el) {
        el = doc.createElement('style');
        el.id = 'tongling-embed-style';
        doc.head.appendChild(el);
      }
      el.textContent = buildEmbedThemeCss();
    } catch (e) { /* 非同源时忽略 */ }
  }

  function refreshEmbedThemes() {
    injectHexStrikeEmbedStyles($('hs-frame'));
  }

  function setupHexStrikeFrame(frame) {
    if (!frame) return;
    frame.addEventListener('load', () => injectHexStrikeEmbedStyles(frame));
  }

  let config = null;
  let ws = null;
  let term = null;
  let fitAddon = null;
  let fitTerminalTimer = null;
  let termOutputBuf = '';
  let termOutputTimer = 0;
  let termScrollRaf = 0;
  let termScrollSyncRaf = 0;
  /** 用户是否跟随输出滚底（上滑阅读时为 false） */
  let termStickBottom = true;

  /**
   * 每会话独立 xterm（mac 多窗口可同时显示）
   * @type {Record<string, {
   *   term: any, fitAddon: any, host: HTMLElement,
   *   stickBottom: boolean, outputBuf: string, outputTimer: number
   * }>}
   */
  const sessionTerms = Object.create(null);
  /** 已向服务端订阅输出的终端 id */
  const subscribedSessions = new Set();
  /** mac 桌面：sessionId → 窗口 DOM（增量同步，避免整桌重建） */
  const macWinBySession = Object.create(null);
  let macActiveWinEl = null;

  const TERM_WRITE_MAX = 48000;
  /** 用户刚敲过键：此窗口内合并写屏，避免 TUI 回刷抢输入 */
  let termTypingUntil = 0;

  /** TUI 原地刷新（计时、spinner、进度条）：含 \\r / ANSI 光标控制 */
  function isInPlaceTermUpdate(data) {
    return /[\r\x08]|\x1b\[|\x1b\][\s\S]*?(?:\x07|\x1b\\)/.test(data);
  }

  function markTermTyping() {
    termTypingUntil = performance.now() + 160;
    // 打字时把后台会话的待刷输出再推迟，给当前输入让路
    Object.keys(sessionTerms).forEach((id) => {
      if (id === activeSessionId) return;
      const st = sessionTerms[id];
      if (!st?.outputBuf) return;
      if (st.outputTimer) {
        clearTimeout(st.outputTimer);
        st.outputTimer = 0;
      }
      if (!st.outputTimer) {
        st.outputTimer = setTimeout(() => {
          st.outputTimer = 0;
          drainTermOutputQueueFor(id);
        }, 120);
      }
    });
  }

  function isTermTypingHot() {
    return performance.now() < termTypingUntil;
  }

  function isMacDesktopInteracting() {
    return document.body.classList.contains('term-dragging')
      || document.body.classList.contains('term-resizing');
  }

  function termFlushDelayMs(sessionId) {
    // 拖窗/改尺寸时大幅推迟刷屏，优先跟手
    if (isMacDesktopInteracting()) {
      if (sessionId && sessionId !== activeSessionId) return 240;
      return 40;
    }
    // 打字时后台终端尽量让路；当前会话用 rAF，这里只服务后台
    if (isTermTypingHot() && sessionId && sessionId !== activeSessionId) return 120;
    if (sessionId && sessionId !== activeSessionId) return isMobileView() ? 64 : 48;
    return isMobileView() ? 20 : 12;
  }

  let skillState = {
    skills: [],
    packs: [],
    recommendedIds: new Set(),
    checkedIds: new Set(),
    loadedSkills: [],
    loadedLoading: false,
  };

  let providerState = {
    providers: [],
    active_id: '',
    active_name: '',
    active_summary: '',
    live_model: '',
  };

  const CLI_MODEL_KEY = 'tongling_cli_model';
  const LS_CLAUDE_SESSION = 'tongling_claude_session_id';
  const LS_SIDE_COLLAPSED = 'tongling_side_collapsed';
  const LS_TOKEN_STATS = 'tongling_token_stats_v1';
  const LS_TOKEN_BILLING = 'tongling_token_billing_v1';
  const LS_BURP_MCP = 'tongling_burp_mcp_v1';
  const LS_THEME = 'tongling_web_theme';
  const LS_SKIP_ANTHROPIC_BANNER = 'tongling_skip_anthropic_banner';

  const ANTHROPIC_CONNECT_ERR_RES = [
    /Unable to connect to Anthropic services/i,
    /Failed to connect to api\.anthropic\.com/i,
    /api\.anthropic\.com[\s\S]{0,220}ERR_BAD_REQUEST/i,
    /ERR_BAD_REQUEST[\s\S]{0,220}api\.anthropic\.com/i,
    /api\.anthropic\.com[\s\S]{0,160}ECONNREFUSED/i,
    /ECONNREFUSED[\s\S]{0,160}api\.anthropic\.com/i,
    /api\.anthropic\.com[\s\S]{0,160}(ENOTFOUND|ETIMEDOUT|ECONNRESET|ERR_CONNECTION)/i,
  ];

  let termTextProbeBuf = '';
  let anthropicBannerShown = false;
  let anthropicTermTipWritten = false;

  const WEB_THEMES = {
    deep: {
      label: '深邃',
      term: {
        background: '#0a0c10',
        foreground: '#c9d1d9',
        cursor: '#00e676',
        cursorAccent: '#0a0c10',
        selectionBackground: 'rgba(0, 230, 118, 0.25)',
      },
    },
    dark: {
      label: '暗色',
      term: {
        background: '#0f1218',
        foreground: '#d4dbe6',
        cursor: '#3dffa0',
        cursorAccent: '#0f1218',
        selectionBackground: 'rgba(61, 255, 160, 0.22)',
      },
    },
    light: {
      label: '浅色',
      term: {
        background: '#3a404c',
        foreground: '#e8ecf1',
        cursor: '#34d399',
        cursorAccent: '#3a404c',
        selectionBackground: 'rgba(52, 211, 153, 0.28)',
      },
    },
  };

  function getWebThemeId() {
    const id = document.documentElement.getAttribute('data-theme') || 'deep';
    return WEB_THEMES[id] ? id : 'deep';
  }

  function getTermTheme() {
    return WEB_THEMES[getWebThemeId()].term;
  }

  function syncThemeSelects(themeId) {
    document.querySelectorAll('#theme-select, #theme-select-mobile').forEach((el) => {
      if (el) el.value = themeId;
    });
  }

  function updateThemeColorMeta() {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) return;
    const color = getComputedStyle(document.documentElement).getPropertyValue('--theme-color').trim();
    if (color) meta.setAttribute('content', color);
  }

  function applyTermTheme() {
    const theme = { ...getTermTheme() };
    if (term) term.options.theme = theme;
    Object.values(sessionTerms).forEach((st) => {
      if (st?.term) st.term.options.theme = theme;
    });
  }

  function applyWebTheme(themeId, persist) {
    const id = WEB_THEMES[themeId] ? themeId : 'deep';
    document.documentElement.setAttribute('data-theme', id);
    if (persist !== false) {
      try {
        localStorage.setItem(LS_THEME, id);
      } catch (e) { /* ignore */ }
    }
    syncThemeSelects(id);
    updateThemeColorMeta();
    applyTermTheme();
    refreshEmbedThemes();
  }

  function initWebTheme() {
    let saved = 'deep';
    try {
      saved = localStorage.getItem(LS_THEME) || 'deep';
    } catch (e) { /* ignore */ }
    applyWebTheme(saved, false);
  }

  function onThemeSelectChange(themeId) {
    applyWebTheme(themeId, true);
  }

  /** @type {Record<string, { input: number, output: number }>} */
  let tokenStatsBySession = {};
  /** 当前 Web 终端标签页内 Claude 状态行解析值 */
  let currentTokenStats = { input: 0, output: 0 };
  /** 累计计费（跨重启、跨会话持久化） */
  let billingTotals = { input: 0, output: 0 };
  /** 本会话首条状态行基准，避免恢复会话时重复计入 */
  let sessionBillingBaseline = null;

  const TOKEN_INPUT_RES = [
    /↓\s*([\d.,]+[kKmM]?)(?:\s*tokens?)?/gi,
    /([\d.,]+[kKmM]?)↓/gi,
    /in\s+↑?\s*([\d.,]+[kKmM]?)(?:\s*tokens?)?/gi,
    /input[:\s]+([\d.,]+[kKmM]?)/gi,
  ];
  const TOKEN_OUTPUT_RES = [
    /↑\s*([\d.,]+[kKmM]?)(?:\s*tokens?)?/gi,
    /([\d.,]+[kKmM]?)↑/gi,
    /out\s+↓?\s*([\d.,]+[kKmM]?)(?:\s*tokens?)?/gi,
    /output[:\s]+([\d.,]+[kKmM]?)/gi,
  ];
  const TOKEN_COST_RES = [
    /(\d[\d,]*)\s*input[^\d]{0,24}(\d[\d,]*)\s*output/gi,
    /input[:\s]+([\d.,]+[kKmM]?).{0,40}output[:\s]+([\d.,]+[kKmM]?)/gi,
  ];

  function loadTokenStatsStore() {
    try {
      tokenStatsBySession = JSON.parse(localStorage.getItem(LS_TOKEN_STATS) || '{}') || {};
    } catch (e) {
      tokenStatsBySession = {};
    }
  }

  function loadTokenBilling() {
    try {
      const raw = JSON.parse(localStorage.getItem(LS_TOKEN_BILLING) || '{}') || {};
      billingTotals = {
        input: Math.max(0, Number(raw.input) || 0),
        output: Math.max(0, Number(raw.output) || 0),
      };
    } catch (e) {
      billingTotals = { input: 0, output: 0 };
    }
  }

  function saveTokenBilling() {
    localStorage.setItem(LS_TOKEN_BILLING, JSON.stringify(billingTotals));
  }

  function saveTokenStatsStore() {
    localStorage.setItem(LS_TOKEN_STATS, JSON.stringify(tokenStatsBySession));
  }

  function resetSessionBillingBaseline() {
    sessionBillingBaseline = null;
  }

  function applyTokenDeltaToBilling(prevIn, prevOut) {
    if (sessionBillingBaseline === null) {
      sessionBillingBaseline = {
        input: currentTokenStats.input,
        output: currentTokenStats.output,
      };
      return;
    }
    const dIn = Math.max(0, currentTokenStats.input - prevIn);
    const dOut = Math.max(0, currentTokenStats.output - prevOut);
    if (dIn || dOut) {
      billingTotals.input += dIn;
      billingTotals.output += dOut;
      saveTokenBilling();
    }
  }

  function stripAnsi(text) {
    return String(text || '')
      .replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, '')
      .replace(/\x1b\][^\x07\\]*(?:\x07|\\)/g, '');
  }

  function probeAnthropicConnectError(raw) {
    if (!raw || localStorage.getItem(LS_SKIP_ANTHROPIC_BANNER) === '1') return;
    const chunk = stripAnsi(raw).replace(/\r/g, '');
    if (!chunk) return;
    termTextProbeBuf = (termTextProbeBuf + chunk).slice(-8000);
    const hit = ANTHROPIC_CONNECT_ERR_RES.some((re) => {
      re.lastIndex = 0;
      return re.test(termTextProbeBuf);
    });
    if (hit) showAnthropicConnectBanner();
  }

  function writeAnthropicTipToTerminal() {
    if (anthropicTermTipWritten) return;
    anthropicTermTipWritten = true;
    const tip = t('banner.termTip');
    try {
      const st = activeSessionId ? sessionTerms[activeSessionId] : null;
      const target = st?.term || term;
      target?.writeln?.(tip.replace(/\r\n/g, '\n').replace(/\r/g, '\n'));
    } catch (e) { /* ignore */ }
  }

  function showAnthropicConnectBanner() {
    const termBanner = $('term-connect-banner');
    const macBanner = $('mac-connect-banner');
    const alreadyVisible = (
      (termBanner && !termBanner.classList.contains('hidden'))
      || (macBanner && !macBanner.classList.contains('hidden'))
    );
    if (anthropicBannerShown && alreadyVisible) return;
    anthropicBannerShown = true;

    // 工作台时 agent-layout 被隐藏，必须用 mac 置顶条；普通布局用终端内横幅
    if (isTermFullscreen()) {
      macBanner?.classList.remove('hidden');
      termBanner?.classList.add('hidden');
      try { openMacAppWindow('control'); } catch (e) { /* ignore */ }
    } else {
      termBanner?.classList.remove('hidden');
      macBanner?.classList.add('hidden');
      applySidePanelCollapsed(false);
      const section = $('cp-section-model');
      if (section) {
        section.open = true;
        section.classList.add('cp-section-highlight');
        setTimeout(() => section.classList.remove('cp-section-highlight'), 2200);
      }
    }

    writeAnthropicTipToTerminal();
    setSideHint(t('banner.hint'), 'err');
    if (!providerState.providers.length) loadProviders();
    setTimeout(fitTerminal, 80);
  }

  function hideAnthropicConnectBanner() {
    const termBanner = $('term-connect-banner');
    const macBanner = $('mac-connect-banner');
    let changed = false;
    if (termBanner && !termBanner.classList.contains('hidden')) {
      termBanner.classList.add('hidden');
      changed = true;
    }
    if (macBanner && !macBanner.classList.contains('hidden')) {
      macBanner.classList.add('hidden');
      changed = true;
    }
    if (changed) setTimeout(fitTerminal, 80);
  }

  function dismissAnthropicConnectBanner(persist) {
    hideAnthropicConnectBanner();
    if (persist) {
      try { localStorage.setItem(LS_SKIP_ANTHROPIC_BANNER, '1'); } catch (e) { /* ignore */ }
    }
  }

  function openProviderGuideFromBanner() {
    hideAnthropicConnectBanner();
    if (isMobileView()) {
      openControlSheet();
      const section = $('cp-section-model-sheet');
      if (section) {
        section.open = true;
        setTimeout(() => section.scrollIntoView({ behavior: 'smooth', block: 'start' }), 220);
      }
      $('select-provider-sheet')?.focus();
    } else if (isTermFullscreen()) {
      try { openMacAppWindow('control'); } catch (e) { /* ignore */ }
      const section = $('cp-section-model');
      if (section) {
        section.open = true;
        section.classList.add('cp-section-highlight');
        setTimeout(() => section.classList.remove('cp-section-highlight'), 2200);
      }
      $('select-provider')?.focus();
    } else {
      applySidePanelCollapsed(false);
      const section = $('cp-section-model');
      if (section) {
        section.open = true;
        section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        section.classList.add('cp-section-highlight');
        setTimeout(() => section.classList.remove('cp-section-highlight'), 2200);
      }
      $('select-provider')?.focus();
    }
    setSideHint(t('banner.guide'), 'ok');
  }

  function parseTokenCount(raw) {
    if (raw == null || raw === '') return 0;
    const s = String(raw).trim().replace(/,/g, '');
    const m = s.match(/^([\d.]+)\s*([kKmM])?$/);
    if (!m) {
      const n = parseInt(s, 10);
      return Number.isFinite(n) ? n : 0;
    }
    let n = parseFloat(m[1]);
    if (!Number.isFinite(n)) return 0;
    const u = (m[2] || '').toLowerCase();
    if (u === 'k') n *= 1000;
    else if (u === 'm') n *= 1000000;
    return Math.round(n);
  }

  function collectTokenMatches(text, patterns) {
    let max = 0;
    patterns.forEach((re) => {
      re.lastIndex = 0;
      let m;
      while ((m = re.exec(text)) !== null) {
        const v = parseTokenCount(m[1]);
        if (v > max) max = v;
      }
    });
    return max;
  }

  function formatTokenCount(n) {
    const v = Math.max(0, Number(n) || 0);
    if (v >= 1000000) return `${(v / 1000000).toFixed(1).replace(/\.0$/, '')}M`;
    if (v >= 1000) return `${(v / 1000).toFixed(1).replace(/\.0$/, '')}k`;
    return String(v);
  }

  function getTokenTotal(stats) {
    return (stats?.input || 0) + (stats?.output || 0);
  }

  function updateTokenStatsUI() {
    const stats = billingTotals;
    const total = getTokenTotal(stats);
    const sessionTotal = getTokenTotal(currentTokenStats);
    const has = total > 0 || sessionTotal > 0;
    const summary = `累计 ↓ ${formatTokenCount(stats.input)} · ↑ ${formatTokenCount(stats.output)} · 计 ${formatTokenCount(total)}`;
    const short = `↓${formatTokenCount(stats.input)}·${formatTokenCount(total)}`;

    const bar = $('term-token-stats');
    if (bar) {
      const sessionHint = sessionTotal > 0
        ? ` · 本会话 ${formatTokenCount(sessionTotal)}`
        : '';
      bar.textContent = summary + sessionHint;
      bar.hidden = !has;
      bar.classList.toggle('has-tokens', has);
    }
    const mBar = $('m-token-stats');
    if (mBar) {
      mBar.textContent = short;
      mBar.hidden = !has || !isMobileView() || !$('panel-agent')?.classList.contains('active');
    }
    ['desktop', 'sheet'].forEach((suffix) => {
      const sumEl = $(`token-summary-${suffix}`);
      if (sumEl) sumEl.textContent = summary;
      const inEl = $(`token-input-${suffix}`);
      const outEl = $(`token-output-${suffix}`);
      const totEl = $(`token-total-${suffix}`);
      if (inEl) inEl.textContent = formatTokenCount(stats.input);
      if (outEl) outEl.textContent = formatTokenCount(stats.output);
      if (totEl) totEl.textContent = formatTokenCount(total);
    });
  }

  function persistTokenStatsForSession(sessionId) {
    if (!sessionId) return;
    tokenStatsBySession[sessionId] = {
      input: currentTokenStats.input,
      output: currentTokenStats.output,
    };
    saveTokenStatsStore();
  }

  function loadTokenStatsForSession(sessionId) {
    const saved = sessionId ? tokenStatsBySession[sessionId] : null;
    currentTokenStats = {
      input: saved?.input || 0,
      output: saved?.output || 0,
    };
    resetSessionBillingBaseline();
    updateTokenStatsUI();
  }

  function resetTokenStatsForActiveSession() {
    currentTokenStats = { input: 0, output: 0 };
    resetSessionBillingBaseline();
    if (activeSessionId) {
      tokenStatsBySession[activeSessionId] = { input: 0, output: 0 };
      saveTokenStatsStore();
    }
    updateTokenStatsUI();
  }

  function resetBillingTotals() {
    billingTotals = { input: 0, output: 0 };
    saveTokenBilling();
    updateTokenStatsUI();
  }

  function trackTermTokensFromOutput(raw) {
    if (!raw) return;
    const text = stripAnsi(raw);
    if (!text) return;

    const prevIn = currentTokenStats.input;
    const prevOut = currentTokenStats.output;
    let changed = false;
    const inputMax = collectTokenMatches(text, TOKEN_INPUT_RES);
    const outputMax = collectTokenMatches(text, TOKEN_OUTPUT_RES);
    if (inputMax > currentTokenStats.input) {
      currentTokenStats.input = inputMax;
      changed = true;
    }
    if (outputMax > currentTokenStats.output) {
      currentTokenStats.output = outputMax;
      changed = true;
    }

    TOKEN_COST_RES.forEach((re) => {
      re.lastIndex = 0;
      let m;
      while ((m = re.exec(text)) !== null) {
        const inV = parseTokenCount(m[1]);
        const outV = parseTokenCount(m[2]);
        if (inV > currentTokenStats.input) {
          currentTokenStats.input = inV;
          changed = true;
        }
        if (outV > currentTokenStats.output) {
          currentTokenStats.output = outV;
          changed = true;
        }
      }
    });

    if (changed) {
      applyTokenDeltaToBilling(prevIn, prevOut);
      persistTokenStatsForSession(activeSessionId);
      updateTokenStatsUI();
    }
  }

  loadTokenStatsStore();
  loadTokenBilling();

  /** @type {{ session_id: string, title: string, modified_text?: string, message_count?: number }[]} */
  let claudeSessions = [];
  /** @type {{ audit_id: string, title?: string, status?: string, started_at_text?: string, tool_run_count?: number }[]} */
  let auditRecords = [];
  let activeAuditId = '';
  let selectedClaudeSessionId = localStorage.getItem(LS_CLAUDE_SESSION) || '';
  /** @type {{ sessionId?: string, host?: string, tool?: string, q?: string } | null} */
  let pendingScanVizOpts = null;
  /** 下一次 WS start 要恢复的 Claude 会话 ID（点击历史时设置） */
  let wsStartResumeId = null;
  /** 扫描摘要绑定的「当前终端」Claude UUID（不使用历史上一次选中的会话） */
  let liveClaudeSessionId = '';
  /** @type {Record<string, string>} */
  const claudeSessionByTerm = Object.create(null);
  let pendingLiveClaudeSessionId = '';
  let liveClaudeDiscoverTimer = 0;
  let liveClaudeDiscoverUntil = 0;
  let liveClaudeDiscoverSince = 0;

  const $ = (id) => document.getElementById(id);

  const AUTH_TOKEN_KEY = 'tongling_token';

  function getAuthToken() {
    const fromUrl = new URLSearchParams(window.location.search).get('token');
    if (fromUrl) sessionStorage.setItem(AUTH_TOKEN_KEY, fromUrl);
    return fromUrl || sessionStorage.getItem(AUTH_TOKEN_KEY) || '';
  }

  function withAuth(url) {
    const t = getAuthToken();
    if (!t) return url;
    const hashIdx = url.indexOf('#');
    const base = hashIdx >= 0 ? url.slice(0, hashIdx) : url;
    const hash = hashIdx >= 0 ? url.slice(hashIdx) : '';
    const sep = base.includes('?') ? '&' : '?';
    return `${base}${sep}token=${encodeURIComponent(t)}${hash}`;
  }

  function apiFetch(url, options) {
    return fetch(withAuth(url), options);
  }

  function isMobileView() {
    return window.matchMedia('(max-width: 768px)').matches;
  }

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  let reportMarkdownReady = false;

  function ensureReportMarkdownRenderer() {
    if (reportMarkdownReady || typeof marked === 'undefined') return;
    marked.use({
      breaks: true,
      gfm: true,
      renderer: {
        // marked 12 浏览器全局实例仍使用旧版 (href, title, text) 签名
        link(href, title, text) {
          const safeHref = escapeHtml(href || '');
          const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
          return `<a href="${safeHref}" target="_blank" rel="noopener noreferrer"${titleAttr}>${text}</a>`;
        },
      },
    });
    reportMarkdownReady = true;
  }

  function renderReportMarkdown(text) {
    const raw = String(text || '');
    if (!raw.trim()) return '';
    if (typeof marked === 'undefined') {
      return `<pre class="reports-md-fallback">${escapeHtml(raw)}</pre>`;
    }
    ensureReportMarkdownRenderer();
    const html = marked.parse(raw);
    if (typeof DOMPurify !== 'undefined') {
      return DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
    }
    return escapeHtml(raw);
  }

  function setReportPreviewPlain(preview, text) {
    if (!preview) return;
    preview.classList.remove('md-rendered');
    preview.textContent = text || '';
    clearReportOutline();
  }

  function slugifyReportHeading(text, used) {
    let base = String(text || '')
      .trim()
      .toLowerCase()
      .replace(/[^\w\u4e00-\u9fff]+/gu, '-')
      .replace(/^-+|-+$/g, '');
    if (!base) base = 'section';
    let id = base;
    let n = 1;
    while (used.has(id)) {
      id = `${base}-${n++}`;
    }
    used.add(id);
    return id;
  }

  function clearReportOutline() {
    const outline = $('reports-outline');
    if (!outline) return;
    outline.hidden = true;
    outline.innerHTML = '';
    setReportOutlineResizerVisible(false);
  }

  function bindReportOutline(preview) {
    const outline = $('reports-outline');
    if (!outline || !preview) return;
    outline.querySelectorAll('.reports-outline-item').forEach((link) => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const id = link.getAttribute('data-heading-id');
        if (!id) return;
        const target = preview.querySelector(`#${CSS.escape(id)}`);
        if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        outline.querySelectorAll('.reports-outline-item').forEach((x) => x.classList.remove('active'));
        link.classList.add('active');
      });
    });
  }

  function renderReportOutline(preview) {
    const outline = $('reports-outline');
    if (!outline || !preview) return;
    const headings = preview.querySelectorAll('h1, h2, h3, h4, h5, h6');
    if (!headings.length) {
      clearReportOutline();
      return;
    }
    const used = new Set();
    const items = [];
    headings.forEach((h) => {
      const level = parseInt(h.tagName.slice(1), 10) || 1;
      const text = (h.textContent || '').trim();
      if (!text) return;
      if (!h.id) h.id = slugifyReportHeading(text, used);
      else used.add(h.id);
      items.push({ level, id: h.id, text });
    });
    if (!items.length) {
      clearReportOutline();
      return;
    }
    outline.hidden = false;
    outline.innerHTML = `<div class="reports-outline-title">大纲</div>${items.map((it) =>
      `<a href="#${escapeHtml(it.id)}" class="reports-outline-item depth-${it.level}" data-heading-id="${escapeHtml(it.id)}">${escapeHtml(it.text)}</a>`
    ).join('')}`;
    setReportOutlineResizerVisible(true);
    bindReportOutline(preview);
  }

  function setReportPreviewMarkdown(preview, text) {
    if (!preview) return;
    preview.classList.add('md-rendered');
    preview.innerHTML = renderReportMarkdown(text);
    renderReportOutline(preview);
  }

  function setStatusDot(ok) {
    const cls = 'status-dot' + (ok === true ? ' online' : ok === false ? ' error' : '');
    const dot = $('status-dot');
    if (dot) dot.className = cls;
    const mDot = $('m-status-dot');
    if (mDot) mDot.className = cls;
  }

  function setGlobalStatus(text, ok) {
    const t = text || '';
    if ($('global-status')) $('global-status').textContent = t;
    if ($('m-header-status')) $('m-header-status').textContent = t;
    setStatusDot(ok);
  }

  function setHint(el, text, type) {
    if (!el) return;
    el.textContent = text || '';
    el.className = 'hint-box' + (type ? ' ' + type : '');
  }

  function setMcpHint(text, type) {
    setHint($('mcp-status'), text, type);
  }

  function setSideHint(text, type) {
    setHint($('side-status'), text, type);
    setHint($('side-status-sheet'), text, type);
  }

  function setTermStatus(text) {
    const el = $('term-status');
    const fallback = t('status.disconnected');
    const display = text || fallback;
    if (el) el.textContent = display;
    const pill = $('m-term-status');
    if (!pill) return;
    pill.textContent = display;
    pill.hidden = !isMobileView() || !$('panel-agent')?.classList.contains('active');
    pill.classList.remove('running', 'error');
    if (/运行|启动|Running|Started/i.test(display)) pill.classList.add('running');
    else if (/错误|失败|Error|Fail/i.test(display)) pill.classList.add('error');
  }

  const MOBILE_TERM_KEYS = [
    { label: '⇈', scroll: -24, scrollBtn: true },
    { label: '⇊', scroll: 24, scrollBtn: true },
    { label: 'Tab', data: '\t' },
    { label: 'Esc', data: '\x1b' },
    { label: 'Ctrl+C', data: '\x03' },
    { label: 'Ctrl+L', data: '\x0c' },
    { label: '↑', data: '\x1b[A' },
    { label: '↓', data: '\x1b[B' },
    { label: 'Enter', data: '\r', accent: true },
  ];

  function sendTermInput(data) {
    if (ws && ws.readyState === WebSocket.OPEN && activeSessionId) {
      ws.send(JSON.stringify({ type: 'input', session_id: activeSessionId, data }));
    }
    if (term) term.focus();
  }

  let termClipHintTimer = null;
  let termClipboardBound = false;

  function isTermFocused() {
    const host = $('terminal-host');
    if (!host || !term) return false;
    const ae = document.activeElement;
    return !!(ae && (host === ae || host.contains(ae)));
  }

  function flashTermClipHint(msg, type) {
    const el = $('term-clip-hint');
    if (!el) return;
    el.textContent = msg || '';
    el.classList.toggle('err', type === 'err');
    el.classList.add('show');
    clearTimeout(termClipHintTimer);
    termClipHintTimer = setTimeout(() => el.classList.remove('show'), 2200);
  }

  function termCopySelection() {
    if (!term) return;
    const text = term.getSelection();
    if (!text) {
      flashTermClipHint('请先选中要复制的文字', 'err');
      return;
    }
    const write = navigator.clipboard?.writeText
      ? navigator.clipboard.writeText(text)
      : Promise.reject(new Error('clipboard unavailable'));
    write.then(() => flashTermClipHint(`已复制 ${text.length} 字符`))
      .catch(() => flashTermClipHint('复制失败', 'err'));
  }

  function termPasteFromClipboard() {
    if (!term) return;
    if (!ws || ws.readyState !== WebSocket.OPEN || !activeSessionId) {
      flashTermClipHint('终端未连接', 'err');
      return;
    }
    const read = navigator.clipboard?.readText
      ? navigator.clipboard.readText()
      : Promise.reject(new Error('clipboard unavailable'));
    read.then((text) => {
      if (text == null || text === '') return;
      const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
      const payload = normalized.includes('\n')
        ? `\x1b[200~${normalized}\x1b[201~`
        : normalized;
      sendTermInput(payload);
      flashTermClipHint(`已粘贴 ${normalized.length} 字符`);
    }).catch(() => flashTermClipHint('无法读取剪贴板', 'err'));
  }

  function handleTermClipboardKey(ev) {
    if (ev.type !== 'keydown' || !term) return false;
    const mod = ev.ctrlKey || ev.metaKey;
    if (!mod || !ev.shiftKey) return false;
    if (ev.code === 'KeyC') {
      ev.preventDefault();
      ev.stopPropagation();
      if (typeof ev.stopImmediatePropagation === 'function') ev.stopImmediatePropagation();
      termCopySelection();
      return true;
    }
    if (ev.code === 'KeyV') {
      ev.preventDefault();
      ev.stopPropagation();
      if (typeof ev.stopImmediatePropagation === 'function') ev.stopImmediatePropagation();
      termPasteFromClipboard();
      return true;
    }
    return false;
  }

  function bindTermClipboardKeys() {
    if (termClipboardBound) return;
    termClipboardBound = true;
    document.addEventListener('keydown', (ev) => {
      if (!isTermFocused()) return;
      handleTermClipboardKey(ev);
    }, true);
  }

  function initMobileTermKeys() {
    const container = $('m-term-keys');
    if (!container) return;
    container.innerHTML = MOBILE_TERM_KEYS.map((k, i) =>
      `<button type="button" class="m-tkey${k.accent ? ' m-tkey-accent' : ''}" data-idx="${i}">${escapeHtml(k.label)}</button>`
    ).join('');
    container.querySelectorAll('.m-tkey').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const idx = parseInt(btn.getAttribute('data-idx'), 10);
        const key = MOBILE_TERM_KEYS[idx];
        if (!key) return;
        if (key.scrollBtn) {
          scrollTermViewport(key.scroll);
          return;
        }
        if (key.data) sendTermInput(key.data);
      });
    });
  }

  function getProxy() {
    return ($('input-proxy')?.value || $('input-proxy-sheet')?.value || '').trim();
  }

  function getPrompt() {
    return ($('input-prompt')?.value || $('input-prompt-sheet')?.value || '').trim();
  }

  function getCliModel() {
    return ($('select-cli-model')?.value || $('select-cli-model-sheet')?.value || '').trim();
  }

  function highlightClaudeSession(sessionId) {
    selectedClaudeSessionId = sessionId || '';
    if (selectedClaudeSessionId) {
      localStorage.setItem(LS_CLAUDE_SESSION, selectedClaudeSessionId);
    } else {
      localStorage.removeItem(LS_CLAUDE_SESSION);
    }
    renderClaudeSessionLists();
  }

  function resumeClaudeSession(sessionId) {
    if (!sessionId) return;
    wsStartResumeId = sessionId;
    pendingLiveClaudeSessionId = sessionId;
    highlightClaudeSession(sessionId);
    setSideHint('正在恢复会话并打开终端…', 'ok');
    closeControlSheet();
    connectAndStart();
  }

  function bindScanDockToLiveClaude(claudeSessionId, termId) {
    const sid = (claudeSessionId || '').trim();
    const tid = termId || activeSessionId || '';
    if (tid && sid) claudeSessionByTerm[tid] = sid;
    liveClaudeSessionId = sid;
    window.tonglingAgentScanDock?.setSessionId(liveClaudeSessionId);
  }

  function syncScanDockForActiveTerminal() {
    const tid = activeSessionId || '';
    liveClaudeSessionId = tid ? (claudeSessionByTerm[tid] || '') : '';
    window.tonglingAgentScanDock?.setSessionId(liveClaudeSessionId);
  }

  function stopLiveClaudeDiscover() {
    if (liveClaudeDiscoverTimer) {
      clearTimeout(liveClaudeDiscoverTimer);
      liveClaudeDiscoverTimer = 0;
    }
    liveClaudeDiscoverUntil = 0;
  }

  function notifyServerClaudeBound(termId, claudeSid) {
    if (!ws || ws.readyState !== WebSocket.OPEN || !termId || !claudeSid) return;
    try {
      ws.send(JSON.stringify({
        type: 'bind_claude',
        session_id: termId,
        claude_session_id: claudeSid,
      }));
    } catch (e) { /* ignore */ }
  }

  async function discoverLiveClaudeSessionOnce() {
    if (!config?.claude_workdir || !activeSessionId) return false;
    if (claudeSessionByTerm[activeSessionId]) {
      bindScanDockToLiveClaude(claudeSessionByTerm[activeSessionId], activeSessionId);
      return true;
    }
    try {
      const q = new URLSearchParams({ workdir: config.claude_workdir });
      const r = await apiFetch(`/tongling/api/claude/sessions?${q}`);
      const d = await r.json();
      if (!r.ok || d.success === false) return false;
      const sessions = d.sessions || [];
      const since = liveClaudeDiscoverSince || (Date.now() - 30000);
      const fresh = sessions.filter((s) => {
        const t = Date.parse(s.modified || '');
        return t && t >= since - 8000;
      });
      const pick = fresh[0];
      if (!pick?.session_id) return false;
      bindScanDockToLiveClaude(pick.session_id, activeSessionId);
      notifyServerClaudeBound(activeSessionId, pick.session_id);
      highlightClaudeSession(pick.session_id);
      return true;
    } catch {
      return false;
    }
  }

  function scheduleLiveClaudeDiscover(sinceMs) {
    stopLiveClaudeDiscover();
    liveClaudeDiscoverSince = sinceMs || Date.now();
    liveClaudeDiscoverUntil = Date.now() + 120000;
    const tick = async () => {
      liveClaudeDiscoverTimer = 0;
      if (!activeSessionId || Date.now() > liveClaudeDiscoverUntil) return;
      if (await discoverLiveClaudeSessionOnce()) return;
      liveClaudeDiscoverTimer = setTimeout(tick, 3500);
    };
    liveClaudeDiscoverTimer = setTimeout(tick, 1200);
  }

  function openScanVizFromApp(opts = {}) {
    pendingScanVizOpts = {
      sessionId: opts.sessionId != null
        ? opts.sessionId
        : (liveClaudeSessionId || ''),
      host: opts.host || '',
      tool: opts.tool || '',
      q: opts.q || '',
    };
    if (pendingScanVizOpts.sessionId) {
      selectedClaudeSessionId = pendingScanVizOpts.sessionId;
      localStorage.setItem(LS_CLAUDE_SESSION, selectedClaudeSessionId);
      renderClaudeSessionLists();
    }
    switchTab('scanviz');
  }

  function updateCpSectionHints() {
    const count = claudeSessions.length;
    ['cp-section-launch', 'cp-section-launch-sheet'].forEach((id) => {
      const el = $(id);
      if (el && count > 0) el.open = true;
    });
  }

  function renderClaudeSessionLists() {
    const countText = claudeSessions.length ? `${claudeSessions.length} 个` : '0 个';
    ['claude-session-count', 'claude-session-count-sheet'].forEach((id) => {
      const el = $(id);
      if (el) el.textContent = countText;
    });

    const html = claudeSessions.map((s) => {
      const active = s.session_id === selectedClaudeSessionId ? ' active' : '';
      const meta = [s.modified_text, s.message_count ? `${s.message_count} 条` : '', s.git_branch].filter(Boolean).join(' · ');
      return `<button type="button" class="claude-session-item${active}" data-session-id="${escapeHtml(s.session_id)}" role="option" aria-selected="${active ? 'true' : 'false'}">
        <div class="cs-title">${escapeHtml(s.title || s.session_id.slice(0, 8))}</div>
        <div class="cs-meta">${escapeHtml(meta || s.session_id.slice(0, 12))}</div>
      </button>`;
    }).join('');

    ['claude-session-list', 'claude-session-list-sheet'].forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.innerHTML = html;
      el.querySelectorAll('.claude-session-item').forEach((btn) => {
        btn.addEventListener('click', () => {
          const sid = btn.getAttribute('data-session-id');
          if (sid) resumeClaudeSession(sid);
        });
      });
    });
  }

  function restoreClaudeSessionPreference() {
    const fromUrl = new URLSearchParams(window.location.search).get('claude_session');
    if (fromUrl) {
      selectedClaudeSessionId = fromUrl;
      localStorage.setItem(LS_CLAUDE_SESSION, fromUrl);
    }
    if (selectedClaudeSessionId) renderClaudeSessionLists();
  }

  function applyClaudeSessionFromUrl() {
    const sid = new URLSearchParams(window.location.search).get('claude_session');
    if (!sid || !claudeSessions.some((s) => s.session_id === sid)) return;
    resumeClaudeSession(sid);
  }

  async function loadClaudeSessions() {
    if (!config?.claude_workdir) return;
    ['btn-claude-sessions-refresh', 'btn-claude-sessions-refresh-sheet'].forEach((id) => {
      const btn = $(id);
      if (btn) btn.disabled = true;
    });
    try {
      const q = new URLSearchParams({ workdir: config.claude_workdir });
      const r = await apiFetch(`/tongling/api/claude/sessions?${q}`);
      const d = await r.json();
      if (!d.success) {
        setSideHint(d.error || '会话列表加载失败', 'err');
        return;
      }
      claudeSessions = d.sessions || [];
      if (selectedClaudeSessionId && !claudeSessions.some((s) => s.session_id === selectedClaudeSessionId)) {
        selectedClaudeSessionId = '';
        localStorage.removeItem(LS_CLAUDE_SESSION);
      }
      renderClaudeSessionLists();
      updateCpSectionHints();
      applyClaudeSessionFromUrl();
      if (!claudeSessions.length) {
        const dirs = (d.storage_dirs || []).join(', ') || '未找到';
        setSideHint(`暂无 Claude 会话。已搜索 projects/${dirs} · 请先新建终端对话`, 'err');
      } else if (d.storage_dirs?.includes('Z--')) {
        setSideHint(`已加载 ${claudeSessions.length} 条会话（含 subst Z: 目录）`, 'ok');
      }
    } catch (e) {
      setSideHint(String(e), 'err');
    } finally {
      ['btn-claude-sessions-refresh', 'btn-claude-sessions-refresh-sheet'].forEach((id) => {
        const btn = $(id);
        if (btn) btn.disabled = false;
      });
    }
  }

  /** @type {{ id: string, title?: string, target?: string, source?: string, path?: string }[]} */
  let reportRecords = [];
  let activeReportId = '';
  let activeReportContent = '';
  let pendingScanMeta = null;

  function setReportsStatus(text, kind) {
    const el = $('reports-status');
    if (!el) return;
    el.textContent = text || '';
    el.classList.remove('ok', 'err');
    if (kind === 'ok') el.classList.add('ok');
    if (kind === 'err') el.classList.add('err');
  }

  const LS_OUTLINE_W = 'tongling_reports_outline_w';

  function applyReportOutlineWidth(widthPx) {
    const body = $('reports-preview-body');
    if (!body) return;
    body.style.setProperty('--reports-outline-w', `${widthPx}px`);
  }

  function setReportOutlineResizerVisible(visible) {
    const resizer = $('reports-outline-resizer');
    if (resizer) resizer.hidden = !visible;
  }

  function initReportOutlineResizer() {
    const resizer = $('reports-outline-resizer');
    const body = $('reports-preview-body');
    if (!resizer || !body || resizer.dataset.bound) return;
    resizer.dataset.bound = '1';
    const DEFAULT_OUTLINE_W = 240;
    const saved = parseInt(localStorage.getItem(LS_OUTLINE_W) || String(DEFAULT_OUTLINE_W), 10);
    if (saved === 168) {
      applyReportOutlineWidth(DEFAULT_OUTLINE_W);
      try { localStorage.setItem(LS_OUTLINE_W, String(DEFAULT_OUTLINE_W)); } catch (e) { /* ignore */ }
    } else if (saved >= 120 && saved <= 480) {
      applyReportOutlineWidth(saved);
    }

    let startX = 0;
    let startW = 0;
    const onMove = (e) => {
      const w = Math.min(480, Math.max(120, startW + (e.clientX - startX)));
      applyReportOutlineWidth(w);
    };
    const onUp = () => {
      resizer.classList.remove('dragging');
      document.body.classList.remove('reports-outline-dragging');
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      const w = parseInt(getComputedStyle(body).getPropertyValue('--reports-outline-w'), 10);
      if (w) {
        try { localStorage.setItem(LS_OUTLINE_W, String(w)); } catch (e) { /* ignore */ }
      }
    };
    resizer.addEventListener('mousedown', (e) => {
      if (resizer.hidden) return;
      e.preventDefault();
      startX = e.clientX;
      startW = parseInt(getComputedStyle(body).getPropertyValue('--reports-outline-w') || '240', 10);
      resizer.classList.add('dragging');
      document.body.classList.add('reports-outline-dragging');
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  }

  function renderReportSelect() {
    const el = $('reports-select');
    if (!el) return;
    if (!reportRecords.length) {
      el.innerHTML = '<option value="">暂无报告</option>';
      el.disabled = true;
      return;
    }
    el.disabled = false;
    const placeholder = activeReportId ? '' : '<option value="">选择报告…</option>';
    el.innerHTML = placeholder + reportRecords.map((r) => {
      const src = r.source === 'audit' ? '审计' : 'Claude';
      const target = r.target ? ` · ${r.target}` : '';
      const label = `${r.title || r.id} (${src}${target} · ${r.mtime_text || ''})`;
      const selected = r.id === activeReportId ? ' selected' : '';
      return `<option value="${escapeHtml(r.id)}"${selected}>${escapeHtml(label)}</option>`;
    }).join('');
    if (activeReportId) el.value = activeReportId;
  }

  async function loadReportsPanel() {
    try {
      const r = await apiFetch('/tongling/api/reports?limit=80');
      const d = await r.json();
      if (!d.success) {
        setReportsStatus(d.error || '加载失败', 'err');
        return;
      }
      reportRecords = d.reports || [];
      renderReportSelect();
      const keepCurrent = activeReportId && reportRecords.some((x) => x.id === activeReportId);
      if (keepCurrent) {
        loadReportPreview(activeReportId, true);
      } else if (reportRecords.length) {
        loadReportPreview(reportRecords[0].id, true);
      }
    } catch (e) {
      setReportsStatus(String(e), 'err');
    }
  }

  function reportExportBasename() {
    const rec = reportRecords.find((r) => r.id === activeReportId);
    const raw = rec?.title || activeReportId || 'report';
    const safe = String(raw)
      .replace(/[\\/:*?"<>|]+/g, '_')
      .replace(/\s+/g, '_')
      .replace(/_+/g, '_')
      .replace(/^_|_$/g, '')
      .slice(0, 80);
    return safe || 'report';
  }

  function setReportExportVisible(visible) {
    const wrap = $('reports-export-wrap');
    if (wrap) wrap.hidden = !visible;
    if (!visible) closeReportExportMenu();
  }

  function closeReportExportMenu() {
    const menu = $('reports-export-menu');
    const btn = $('btn-report-export');
    if (menu) menu.hidden = true;
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }

  function toggleReportExportMenu() {
    const menu = $('reports-export-menu');
    const btn = $('btn-report-export');
    if (!menu || !btn) return;
    const open = menu.hidden;
    menu.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  function downloadTextFile(filename, text, mime) {
    const blob = new Blob([text], { type: mime || 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function exportReportAsMd() {
    closeReportExportMenu();
    if (!activeReportId || !activeReportContent) {
      setReportsStatus('暂无可导出的报告内容', 'err');
      return;
    }
    const name = reportExportBasename();
    downloadTextFile(name.endsWith('.md') ? name : `${name}.md`, activeReportContent, 'text/markdown;charset=utf-8');
    setReportsStatus('已导出 Markdown', 'ok');
  }

  function exportReportAsPdf() {
    closeReportExportMenu();
    if (!activeReportId || !activeReportContent) {
      setReportsStatus('暂无可导出的报告内容', 'err');
      return;
    }
    const title = reportRecords.find((r) => r.id === activeReportId)?.title || reportExportBasename();
    const bodyHtml = renderReportMarkdown(activeReportContent);
    const win = window.open('', '_blank');
    if (!win) {
      setReportsStatus('无法打开新窗口，请允许弹出窗口后重试', 'err');
      return;
    }
    const doc = win.document;
    doc.open();
    doc.write(`<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>${escapeHtml(title)}</title>
  <style>
    @page { margin: 18mm 16mm; }
    body {
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      font-size: 14px;
      line-height: 1.65;
      color: #1a1a1a;
      margin: 0;
      padding: 24px;
    }
    h1, h2, h3, h4, h5, h6 { margin: 1.2em 0 0.5em; line-height: 1.35; }
    h1 { font-size: 1.45em; border-bottom: 1px solid #ddd; padding-bottom: 0.35em; }
    h2 { font-size: 1.22em; }
    h3 { font-size: 1.08em; color: #0d7377; }
    p, ul, ol, blockquote, pre, table { margin: 0.65em 0; }
    ul, ol { padding-left: 1.4em; }
    a { color: #0d7377; text-decoration: none; word-break: break-all; }
    blockquote { border-left: 3px solid #ddd; padding-left: 12px; color: #555; }
    code {
      font-family: Consolas, "Courier New", monospace;
      font-size: 0.92em;
      background: #f4f4f4;
      padding: 0.1em 0.35em;
      border-radius: 3px;
    }
    pre {
      background: #f6f8fa;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      padding: 12px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }
    pre code { background: transparent; padding: 0; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
    th { background: #f3f4f6; }
    .print-hint {
      margin: 0 0 16px;
      padding: 10px 12px;
      border: 1px dashed #ccc;
      border-radius: 6px;
      background: #fafafa;
      color: #555;
      font-size: 13px;
    }
    @media print {
      .print-hint { display: none; }
      body { padding: 0; }
      a { color: inherit; }
    }
  </style>
</head>
<body>
  <p class="print-hint">请在打印对话框中选择「另存为 PDF」或「Microsoft Print to PDF」完成导出。</p>
  <article class="md-body md-rendered">${bodyHtml}</article>
</body>
</html>`);
    doc.close();
    win.focus();
    const triggerPrint = () => {
      try { win.print(); } catch (_) { /* ignore */ }
    };
    if (win.document.readyState === 'complete') {
      setTimeout(triggerPrint, 120);
    } else {
      win.addEventListener('load', () => setTimeout(triggerPrint, 120));
    }
    setReportsStatus('已打开 PDF 导出预览，请在打印对话框中保存', 'ok');
  }

  async function loadReportPreview(reportId, quiet) {
    activeReportId = reportId || '';
    activeReportContent = '';
    renderReportSelect();
    const preview = $('reports-preview');
    const openBtn = $('btn-report-open-tab');
    const selectEl = $('reports-select');
    if (selectEl && activeReportId) selectEl.value = activeReportId;
    if (preview && !quiet) setReportPreviewPlain(preview, '加载中…');
    if (!activeReportId) {
      if (preview) setReportPreviewPlain(preview, '暂无内容');
      if (openBtn) openBtn.hidden = true;
      setReportExportVisible(false);
      clearReportOutline();
      return;
    }
    try {
      const r = await apiFetch(`/tongling/api/reports/${encodeURIComponent(activeReportId)}?format=json`);
      const d = await r.json();
      if (!d.success) {
        if (preview) setReportPreviewPlain(preview, d.error || '加载失败');
        setReportExportVisible(false);
        return;
      }
      activeReportContent = d.content || '';
      if (preview) setReportPreviewMarkdown(preview, activeReportContent);
      if (openBtn) {
        openBtn.hidden = false;
        openBtn.onclick = () => {
          window.open(withAuth(`/tongling/api/reports/${encodeURIComponent(activeReportId)}`), '_blank');
        };
      }
      setReportExportVisible(!!activeReportContent.trim());
    } catch (e) {
      if (preview) setReportPreviewPlain(preview, String(e));
      setReportExportVisible(false);
    }
  }

  async function startScanFromReports() {
    const target = ($('scan-target-input')?.value || '').trim();
    if (!target) {
      setReportsStatus('请填写扫描目标', 'err');
      return;
    }
    const scenario = ($('scan-scenario-select')?.value || 'vuln_scan').trim();
    const btn = $('btn-scan-start');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '准备中…';
    }
    setReportsStatus('正在准备 Claude 扫描环境…');
    try {
      const r = await apiFetch('/tongling/api/scan/prepare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target, scenario }),
      });
      const d = await r.json();
      if (!d.success) {
        setReportsStatus(d.error || '准备失败', 'err');
        return;
      }
      pendingScanMeta = {
        target: d.target,
        scenario: d.scenario,
        report_path: d.report_path,
        initial_prompt: d.initial_prompt,
      };
      ['input-prompt', 'input-prompt-sheet'].forEach((id) => {
        const el = $(id);
        if (el) el.value = d.initial_prompt || '';
      });
      setReportsStatus(`已准备 · 报告将写入 ${d.report_path} · 正在打开终端…`, 'ok');
      switchTab('agent');
      connectAndStart();
    } catch (e) {
      setReportsStatus(String(e), 'err');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '开始扫描';
      }
    }
  }

  function auditStatusLabel(status) {
    const map = { running: '进行中', completed: '已完成', stopped: '已停止' };
    return map[status] || status || '—';
  }

  function renderAuditLists() {
    const countText = auditRecords.length ? `${auditRecords.length} 条` : '0 条';
    ['audit-count', 'audit-count-sheet'].forEach((id) => {
      const el = $(id);
      if (el) el.textContent = countText;
    });

    const html = auditRecords.length
      ? auditRecords.map((a) => {
          const active = a.audit_id === activeAuditId ? ' active' : '';
          const meta = [
            a.started_at_text || '',
            auditStatusLabel(a.status),
            a.tool_run_count ? `${a.tool_run_count} 工具` : '',
          ].filter(Boolean).join(' · ');
          return `<button type="button" class="claude-session-item audit-item${active}" data-audit-id="${escapeHtml(a.audit_id)}" role="option">
            <div class="cs-title">${escapeHtml(a.title || a.audit_id)}</div>
            <div class="cs-meta">${escapeHtml(meta)}</div>
          </button>`;
        }).join('')
      : '<p class="cp-tip">暂无审计记录。新建终端并使用后自动落盘。</p>';

    ['audit-list', 'audit-list-sheet'].forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.innerHTML = html;
      el.querySelectorAll('.audit-item').forEach((btn) => {
        btn.addEventListener('click', () => {
          const aid = btn.getAttribute('data-audit-id');
          if (aid) openAuditReport(aid);
        });
      });
    });
  }

  async function loadAudits() {
    ['btn-audit-refresh', 'btn-audit-refresh-sheet'].forEach((id) => {
      const btn = $(id);
      if (btn) btn.disabled = true;
    });
    try {
      const r = await apiFetch('/tongling/api/audit?limit=40');
      const d = await r.json();
      if (!d.success) {
        setSideHint(d.error || '审计列表加载失败', 'err');
        return;
      }
      auditRecords = d.audits || [];
      renderAuditLists();
    } catch (e) {
      setSideHint(String(e), 'err');
    } finally {
      ['btn-audit-refresh', 'btn-audit-refresh-sheet'].forEach((id) => {
        const btn = $(id);
        if (btn) btn.disabled = false;
      });
    }
  }

  function openAuditReport(auditId) {
    activeAuditId = auditId;
    renderAuditLists();
    const url = withAuth(`/tongling/api/audit/${encodeURIComponent(auditId)}/report`);
    window.open(url, '_blank', 'noopener');
    setSideHint(`审计 ${auditId} · 报告已在新标签页打开`, 'ok');
  }

  function getLaunchPayloadExtras() {
    if (wsStartResumeId) {
      const id = wsStartResumeId;
      wsStartResumeId = null;
      pendingLiveClaudeSessionId = id;
      return { launch_mode: 'resume', resume_id: id };
    }
    pendingLiveClaudeSessionId = '';
    return { launch_mode: 'interactive' };
  }

  function getSelectedProviderId() {
    return ($('select-provider')?.value || $('select-provider-sheet')?.value || '').trim();
  }

  function linkSelects(id1, id2) {
    const a = $(id1);
    const b = $(id2);
    if (!a || !b) return;
    const sync = (src, dst) => {
      if (dst.value !== src.value) dst.value = src.value;
    };
    a.addEventListener('change', () => sync(a, b));
    b.addEventListener('change', () => sync(b, a));
  }

  function providerLiveText() {
    const parts = [];
    if (providerState.active_name) parts.push(providerState.active_name);
    const model = providerState.live_model || providerState.active_summary;
    if (model) parts.push(model);
    return parts.join(' · ') || '未配置';
  }

  function setProviderStatus(text, isErr) {
    ['provider-live-desktop', 'provider-live-sheet'].forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.textContent = text || '';
      el.classList.toggle('provider-live-err', !!isErr);
      el.classList.toggle('cp-section-live-err', !!isErr);
    });
  }

  function applyProviderPayload(d) {
    if (!d || !Array.isArray(d.providers) || !d.providers.length) return false;
    providerState = {
      providers: d.providers,
      active_id: d.active_id || '',
      active_name: d.active_name || '',
      active_summary: d.active_summary || '',
      live_model: d.live_model || '',
    };
    renderProviderUI();
    updateMobileChrome(tabFromPath());
    return true;
  }

  function fillProviderSelect(el) {
    if (!el) return;
    const prev = el.value;
    el.innerHTML = providerState.providers.map((p) =>
      `<option value="${escapeHtml(p.id)}" title="${escapeHtml(p.summary || p.notes || '')}">${escapeHtml(p.name)}</option>`
    ).join('');
    const active = providerState.active_id || prev;
    if (active && [...el.options].some((o) => o.value === active)) el.value = active;
  }

  function renderProviderUI() {
    fillProviderSelect($('select-provider'));
    fillProviderSelect($('select-provider-sheet'));
    setProviderStatus(providerLiveText(), false);

    const bar = $('m-provider-bar');
    if (!bar) return;
    bar.innerHTML = providerState.providers.map((p) =>
      `<button type="button" class="provider-chip${p.id === providerState.active_id ? ' active' : ''}" data-provider-id="${escapeHtml(p.id)}" title="${escapeHtml(p.summary || '')}">${escapeHtml(p.name)}</button>`
    ).join('');
    bar.querySelectorAll('.provider-chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        const id = chip.getAttribute('data-provider-id');
        if (id && id !== providerState.active_id) applyProvider(id, chip);
      });
    });
  }

  async function loadProviders() {
    try {
      const r = await apiFetch('/tongling/api/providers');
      let d;
      try {
        d = await r.json();
      } catch (parseErr) {
        setProviderStatus(
          r.status === 404 ? '接口未就绪，请重启 Server' : `响应无效 (${r.status})`,
          true
        );
        return;
      }
      if (!r.ok || !d.success) {
        const msg = d.error || `加载失败 (HTTP ${r.status})`;
        setProviderStatus(msg, true);
        if (r.status === 401) {
          setSideHint('Token 已失效，请从桌面重新打开 Web 控制台', 'err');
        }
        return;
      }
      applyProviderPayload(d);
    } catch (e) {
      setProviderStatus('网络错误: ' + (e.message || e), true);
    }
  }

  async function applyProvider(providerId, chipEl) {
    const id = (providerId || getSelectedProviderId() || '').trim();
    if (!id) {
      setSideHint('请选择提供商', 'err');
      return;
    }
    if (chipEl) chipEl.classList.add('busy');
    $('btn-provider-apply') && ($('btn-provider-apply').disabled = true);
    $('btn-provider-apply-sheet') && ($('btn-provider-apply-sheet').disabled = true);
    setSideHint('正在切换模型…');
    try {
      const r = await apiFetch('/tongling/api/providers/active', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id }),
      });
      const d = await r.json();
      if (!d.success) {
        setSideHint(d.error || '切换失败', 'err');
        return;
      }
      providerState.active_id = d.active_id || id;
      providerState.active_name = d.active_name || '';
      providerState.active_summary = d.active_summary || '';
      providerState.live_model = d.live_model || '';
      renderProviderUI();
      setSideHint((d.message || '已切换') + ' · 请新建终端使配置生效', 'ok');
    } catch (e) {
      setSideHint(String(e), 'err');
    } finally {
      if (chipEl) chipEl.classList.remove('busy');
      $('btn-provider-apply') && ($('btn-provider-apply').disabled = false);
      $('btn-provider-apply-sheet') && ($('btn-provider-apply-sheet').disabled = false);
    }
  }

  function restoreCliModelPreference() {
    const saved = localStorage.getItem(CLI_MODEL_KEY) || '';
    ['select-cli-model', 'select-cli-model-sheet'].forEach((id) => {
      const el = $(id);
      if (el && [...el.options].some((o) => o.value === saved)) el.value = saved;
    });
  }

  function persistCliModelPreference() {
    localStorage.setItem(CLI_MODEL_KEY, getCliModel());
  }

  function clearProviderForm() {
    ['pf-id', 'pf-name', 'pf-base-url', 'pf-token', 'pf-model', 'pf-sonnet', 'pf-opus', 'pf-haiku', 'pf-notes'].forEach((id) => {
      const el = $(id);
      if (el) el.value = '';
    });
    if ($('pf-builtin')) $('pf-builtin').value = '0';
    if ($('pf-token-hint')) $('pf-token-hint').textContent = '';
    setProviderTestResult('');
    if ($('provider-modal-delete')) $('provider-modal-delete').hidden = true;
  }

  function setProviderTestResult(text, kind) {
    const el = $('pf-test-result');
    if (!el) return;
    const msg = (text || '').trim();
    if (!msg) {
      el.hidden = true;
      el.textContent = '';
      el.classList.remove('ok', 'err');
      return;
    }
    el.hidden = false;
    el.textContent = msg;
    el.classList.remove('ok', 'err');
    if (kind === 'ok') el.classList.add('ok');
    if (kind === 'err') el.classList.add('err');
  }

  function fillProviderForm(p) {
    clearProviderForm();
    if (!p) return;
    if ($('pf-id')) $('pf-id').value = p.id || '';
    if ($('pf-builtin')) $('pf-builtin').value = p.builtin ? '1' : '0';
    if ($('pf-name')) $('pf-name').value = p.name || '';
    const env = p.env_form || {};
    if ($('pf-base-url')) $('pf-base-url').value = env.ANTHROPIC_BASE_URL || '';
    if ($('pf-model')) $('pf-model').value = env.ANTHROPIC_MODEL || '';
    if ($('pf-sonnet')) $('pf-sonnet').value = env.ANTHROPIC_DEFAULT_SONNET_MODEL || '';
    if ($('pf-opus')) $('pf-opus').value = env.ANTHROPIC_DEFAULT_OPUS_MODEL || '';
    if ($('pf-haiku')) $('pf-haiku').value = env.ANTHROPIC_DEFAULT_HAIKU_MODEL || '';
    if ($('pf-notes')) $('pf-notes').value = p.notes || '';
    if ($('pf-token-hint')) {
      $('pf-token-hint').textContent = env.token_set
        ? `当前 Key: ${env.token_masked}（留空 Token 字段则保留）`
        : '尚未配置 Key';
    }
    if ($('provider-modal-delete')) $('provider-modal-delete').hidden = !!p.builtin;
    if ($('provider-modal-title')) {
      $('provider-modal-title').textContent = p.builtin
        ? `配置：${p.name}`
        : (p.id ? `编辑：${p.name}` : '添加自定义提供商');
    }
    if ($('provider-modal-hint')) {
      $('provider-modal-hint').textContent = p.builtin
        ? '内置预设：修改后「保存并应用」写入 settings.json，不会改预设文件本身'
        : '自定义提供商保存在 storage/claude_agent_providers.json';
    }
  }

  function collectProviderPayload() {
    const token = ($('pf-token')?.value || '').trim();
    const env = {
      ANTHROPIC_BASE_URL: ($('pf-base-url')?.value || '').trim(),
      ANTHROPIC_MODEL: ($('pf-model')?.value || '').trim(),
      ANTHROPIC_DEFAULT_SONNET_MODEL: ($('pf-sonnet')?.value || '').trim(),
      ANTHROPIC_DEFAULT_OPUS_MODEL: ($('pf-opus')?.value || '').trim(),
      ANTHROPIC_DEFAULT_HAIKU_MODEL: ($('pf-haiku')?.value || '').trim(),
    };
    if (token) env.ANTHROPIC_AUTH_TOKEN = token;
    return {
      id: ($('pf-id')?.value || '').trim(),
      name: ($('pf-name')?.value || '').trim(),
      notes: ($('pf-notes')?.value || '').trim(),
      env,
    };
  }

  async function openProviderModal(mode) {
    closeControlSheet();
    const modal = $('provider-modal');
    if (!modal) return;
    if (mode === 'add') {
      fillProviderForm({ id: '', name: '', builtin: false, env_form: {}, notes: '' });
    } else {
      const id = getSelectedProviderId();
      if (!id) {
        setSideHint('请先选择提供商', 'err');
        return;
      }
      await loadProviderIntoForm(id);
    }
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeProviderModal() {
    const modal = $('provider-modal');
    if (!modal) return;
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  }

  async function loadProviderIntoForm(id) {
    try {
      const r = await apiFetch(`/tongling/api/providers/${encodeURIComponent(id)}`);
      const d = await r.json();
      if (!d.success || !d.provider) {
        setSideHint(d.error || '加载失败', 'err');
        return;
      }
      fillProviderForm(d.provider);
    } catch (e) {
      setSideHint(String(e), 'err');
    }
  }

  async function testProviderKey(fromModal) {
    const payload = fromModal ? collectProviderPayload() : { id: getSelectedProviderId(), env: {} };
    const id = (payload.id || getSelectedProviderId() || '').trim();
    if (!fromModal && !id) {
      setSideHint('请先选择提供商', 'err');
      return;
    }
    const btnIds = fromModal
      ? ['provider-modal-test']
      : ['btn-provider-test', 'btn-provider-test-sheet'];
    btnIds.forEach((bid) => {
      const b = $(bid);
      if (b) {
        b.disabled = true;
        b.dataset.prevLabel = b.textContent;
        b.textContent = '测试中…';
      }
    });
    if (fromModal) setProviderTestResult('正在验证 Key…');
    else setSideHint('正在验证 Key…');

    try {
      const r = await apiFetch('/tongling/api/providers/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, env: payload.env || {} }),
      });
      const d = await r.json();
      const msg = d.message || (d.valid ? 'Key 有效' : '验证失败');
      if (d.valid) {
        if (fromModal) setProviderTestResult(msg, 'ok');
        else setSideHint(msg, 'ok');
      } else {
        if (fromModal) setProviderTestResult(msg, 'err');
        else setSideHint(msg, 'err');
      }
    } catch (e) {
      const errMsg = String(e);
      if (fromModal) setProviderTestResult(errMsg, 'err');
      else setSideHint(errMsg, 'err');
    } finally {
      btnIds.forEach((bid) => {
        const b = $(bid);
        if (b) {
          b.disabled = false;
          b.textContent = b.dataset.prevLabel || '测试 Key';
        }
      });
    }
  }

  async function saveProvider(apply) {
    const payload = collectProviderPayload();
    if (!payload.name) {
      setSideHint('请填写名称', 'err');
      return;
    }
    if (!payload.id && !payload.env.ANTHROPIC_BASE_URL && !payload.env.ANTHROPIC_MODEL) {
      setSideHint('请至少填写 API 地址或主模型', 'err');
      return;
    }
    try {
      const r = await apiFetch('/tongling/api/providers/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payload, apply: !!apply }),
      });
      const d = await r.json();
      if (!d.success) {
        setSideHint(d.error || '保存失败', 'err');
        return;
      }
      applyProviderPayload(d);
      closeProviderModal();
      setSideHint(d.message || '已保存', 'ok');
    } catch (e) {
      setSideHint(String(e), 'err');
    }
  }

  async function deleteProviderFromModal() {
    const id = ($('pf-id')?.value || '').trim();
    if (!id || $('pf-builtin')?.value === '1') return;
    if (!confirm('确定删除此自定义提供商？')) return;
    try {
      const r = await apiFetch(`/tongling/api/providers/${encodeURIComponent(id)}`, {
        method: 'DELETE',
      });
      const d = await r.json();
      if (!d.success) {
        setSideHint(d.error || '删除失败', 'err');
        return;
      }
      applyProviderPayload(d);
      closeProviderModal();
      setSideHint(d.message || '已删除', 'ok');
    } catch (e) {
      setSideHint(String(e), 'err');
    }
  }

  async function importProviderFromSettings() {
    try {
      const r = await apiFetch('/tongling/api/providers/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: '从当前配置导入' }),
      });
      const d = await r.json();
      if (!d.success) {
        setSideHint(d.error || '导入失败', 'err');
        return;
      }
      applyProviderPayload(d);
      if (d.provider) {
        fillProviderForm(d.provider);
        const modal = $('provider-modal');
        if (modal) {
          modal.classList.remove('hidden');
          modal.setAttribute('aria-hidden', 'false');
        }
      }
      setSideHint(d.message || '已导入', 'ok');
    } catch (e) {
      setSideHint(String(e), 'err');
    }
  }

  function linkInputs(id1, id2) {
    const a = $(id1);
    const b = $(id2);
    if (!a || !b) return;
    a.addEventListener('input', () => { b.value = a.value; });
    b.addEventListener('input', () => { a.value = b.value; });
  }

  function linkCheckboxes(id1, id2) {
    const a = $(id1);
    const b = $(id2);
    if (!a || !b) return;
    a.addEventListener('change', () => {
      b.checked = a.checked;
      updateBurpMcpUi();
      persistBurpMcpPrefs();
    });
    b.addEventListener('change', () => {
      a.checked = b.checked;
      updateBurpMcpUi();
      persistBurpMcpPrefs();
    });
  }

  function loadBurpMcpPrefs() {
    try {
      return JSON.parse(localStorage.getItem(LS_BURP_MCP) || '{}') || {};
    } catch (e) {
      return {};
    }
  }

  function persistBurpMcpPrefs() {
    localStorage.setItem(LS_BURP_MCP, JSON.stringify(getBurpMcpPayload()));
  }

  function getBurpMcpPayload() {
    const enabled = !!$('chk-burp-mcp')?.checked;
    return {
      enabled,
      sse_url: ($('input-burp-sse')?.value || 'http://127.0.0.1:9876').trim(),
      proxy_jar: ($('input-burp-jar')?.value || '').trim(),
      java: ($('input-burp-java')?.value || 'java').trim() || 'java',
    };
  }

  function applyBurpMcpPrefs(prefs, serverStatus) {
    const p = { ...loadBurpMcpPrefs(), ...(prefs || {}) };
    const st = serverStatus || config?.burp_mcp || {};
    const enabled = p.enabled ?? st.enabled ?? false;
    const sse = p.sse_url || st.sse_url || st.default_sse_url || 'http://127.0.0.1:9876';
    const jar = p.proxy_jar || st.proxy_jar || '';
    const java = p.java || st.java || 'java';

    const chk = $('chk-burp-mcp');
    if (chk) chk.checked = enabled;
    const sseEl = $('input-burp-sse');
    if (sseEl) sseEl.value = sse;
    const jarEl = $('input-burp-jar');
    if (jarEl) jarEl.value = jar;
    const javaEl = $('input-burp-java');
    if (javaEl) javaEl.value = java;
    updateBurpMcpUi();
  }

  function updateBurpMcpUi() {
    const enabled = !!$('chk-burp-mcp')?.checked;
    const el = $('burp-mcp-block');
    if (el) el.classList.toggle('burp-enabled', enabled);
  }

  function updateTermButtons() {
    const canStart = config && config.pty_available;
    const running = ws && ws.readyState === WebSocket.OPEN && wsStarted && activeSessionId;
    ['btn-term-start', 'm-btn-start', 'btn-term-new'].forEach((id) => {
      const el = $(id);
      if (el) el.disabled = !canStart;
    });
    ['btn-term-stop', 'm-btn-stop'].forEach((id) => {
      const el = $(id);
      if (el) el.disabled = !running;
    });
  }

  function openSheet(sheetId, backdropId) {
    const sheet = $(sheetId);
    const backdrop = $(backdropId);
    if (backdrop) backdrop.classList.remove('hidden');
    if (sheet) {
      sheet.classList.add('open');
      sheet.setAttribute('aria-hidden', 'false');
    }
  }

  function closeSheet(sheetId, backdropId) {
    const sheet = $(sheetId);
    const backdrop = $(backdropId);
    if (sheet) {
      sheet.classList.remove('open');
      sheet.setAttribute('aria-hidden', 'true');
    }
    if (backdrop) backdrop.classList.add('hidden');
  }

  function openControlSheet() {
    openSheet('control-sheet', 'control-backdrop');
  }

  function closeControlSheet() {
    closeSheet('control-sheet', 'control-backdrop');
  }

  function openMoreSheet() {
    openSheet('more-sheet', 'more-backdrop');
    document.querySelectorAll('.m-tab').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.tab === 'more');
    });
  }

  function closeMoreSheet() {
    closeSheet('more-sheet', 'more-backdrop');
  }

  function tabFromPath() {
    const p = window.location.pathname.replace(/\/+$/, '');
    if (p.endsWith('/skills')) return 'skills';
    if (p.endsWith('/fingerprint') || p.endsWith('/fplib')) return 'fplib';
    if (p.endsWith('/vulnlib') || p.endsWith('/nuclei-lib')) return 'vulnlib';
    if (p.endsWith('/im')) return 'im';
    if (p.endsWith('/mcp')) return 'mcp';
    const hashTab = (window.location.hash.replace(/^#\/?/, '') || 'agent').split('/')[0] || 'agent';
    if (hashTab === 'sessions') {
      tasksIframeView = 'sessions';
      localStorage.setItem(LS_TASKS_VIEW, tasksIframeView);
      return 'tasks';
    }
    return hashTab;
  }

  function tasksViewLabel(view) {
    return view === 'sessions' ? '扫描会话' : '任务监控';
  }

  function updateTasksSubnav(tab) {
    const subnav = $('tasks-subnav');
    if (!subnav) return;
    const show = tab === 'tasks';
    subnav.hidden = !show;
    subnav.querySelectorAll('[data-tasks-view]').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-tasks-view') === tasksIframeView);
    });
  }

  function resolveIframeRoute(tab) {
    if (tab === 'tasks') {
      return TASKS_IFRAME_VIEWS[tasksIframeView] || TASKS_IFRAME_VIEWS.monitor;
    }
    return IFRAME_ROUTES[tab];
  }

  function setTasksIframeView(view, { reload = true } = {}) {
    tasksIframeView = view === 'sessions' ? 'sessions' : 'monitor';
    localStorage.setItem(LS_TASKS_VIEW, tasksIframeView);
    updateTasksSubnav('tasks');
    const titleEl = $('page-crumb-title');
    if (titleEl) titleEl.textContent = tasksViewLabel(tasksIframeView);
    const mTitle = $('m-page-title');
    if (mTitle) mTitle.textContent = tasksViewLabel(tasksIframeView);
    if (!reload) return;
    const frame = $('hs-frame');
    const raw = resolveIframeRoute('tasks');
    if (!frame || !raw) return;
    const src = withAuth(raw.startsWith('/tongling/') ? raw : raw);
    frame.src = src;
    frame.setAttribute('data-src', src);
    setTimeout(() => injectHexStrikeEmbedStyles(frame), 50);
    setTimeout(() => injectHexStrikeEmbedStyles(frame), 350);
  }

  function updatePageCrumb(tab) {
    const bar = $('page-crumb-bar');
    const titleEl = $('page-crumb-title');
    if (!bar) return;
    const isAgent = tab === 'agent';
    bar.hidden = isAgent;
    bar.classList.toggle('visible', !isAgent);
    bar.setAttribute('aria-hidden', isAgent ? 'true' : 'false');
    if (!isAgent && titleEl) {
      if (tab === 'tasks') {
        titleEl.textContent = tasksViewLabel(tasksIframeView);
      } else if (TAB_META[tab]) {
        titleEl.textContent = TAB_META[tab].crumbTitle || TAB_META[tab].title;
      }
    }
  }

  function updateMobileChrome(tab) {
    const bar = $('mobile-agent-bar');
    if (bar) bar.classList.toggle('visible', tab === 'agent' && isMobileView());

    const providerBar = $('m-provider-bar');
    if (providerBar) {
      providerBar.classList.toggle(
        'visible',
        tab === 'agent' && isMobileView() && providerState.providers.length > 0
      );
    }

    const pill = $('m-term-status');
    if (pill) pill.hidden = tab !== 'agent' || !isMobileView();

    updateTokenStatsUI();

    document.querySelectorAll('.m-tab').forEach((btn) => {
      const t = btn.dataset.tab;
      if (t === 'more') return;
      btn.classList.toggle('active', t === tab);
    });

    const mTitle = $('m-page-title');
    if (mTitle) {
      if (tab === 'tasks') {
        mTitle.textContent = tasksViewLabel(tasksIframeView);
      } else {
        mTitle.textContent = tab === 'agent'
          ? TAB_META[tab].title
          : (TAB_META[tab].crumbTitle || TAB_META[tab].title);
      }
    }
  }

  function switchTab(tab) {
    if (tab === 'sessions') {
      tasksIframeView = 'sessions';
      localStorage.setItem(LS_TASKS_VIEW, tasksIframeView);
      tab = 'tasks';
    }
    // 控制面板：悬浮桌面开独立窗；普通模式回到智能体并展开侧栏
    if (tab === 'control') {
      if (isTermFullscreen()) {
        openMacAppWindow('control');
        syncMacDockActive('control');
        closeMoreSheet();
        return;
      }
      tab = 'agent';
      applySidePanelCollapsed(false);
    }
    if (!TAB_META[tab]) tab = 'agent';
    window.location.hash = tab === 'agent' ? '' : '/' + tab;

    document.querySelectorAll('.nav-item').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    syncMacDockActive(tab);

    // mac 悬浮桌面：功能以独立程序窗口打开，不退出悬浮
    if (isTermFullscreen() && tab !== 'agent') {
      openMacAppWindow(tab);
      closeMoreSheet();
      return;
    }
    if (isTermFullscreen() && tab === 'agent') {
      // Dock 点智能体：优先还原全部已最小化终端
      if (!restoreMinimizedTerminals()) {
        const restoreId = activeSessionId
          || termSessions[termSessions.length - 1]?.id
          || '';
        if (restoreId) focusMacWindow(restoreId, { switchSession: true });
        else {
          const empty = findMacWin('__empty__');
          if (empty) {
            empty.style.display = '';
            setMacDesktopActiveWindow(empty);
          }
        }
      }
      syncMacDockActive('agent');
      closeMoreSheet();
      setTimeout(fitTerminal, 80);
      return;
    }

    updatePageCrumb(tab);

    $('panel-agent').classList.toggle('active', tab === 'agent');
    $('panel-skills').classList.toggle('active', tab === 'skills');
    $('panel-prompts').classList.toggle('active', tab === 'prompts');
    $('panel-fplib').classList.toggle('active', tab === 'fplib');
    $('panel-vulnlib').classList.toggle('active', tab === 'vulnlib');
    $('panel-mcp').classList.toggle('active', tab === 'mcp');
    $('panel-im').classList.toggle('active', tab === 'im');
    $('panel-nps').classList.toggle('active', tab === 'nps');
    $('panel-reports').classList.toggle('active', tab === 'reports');
    $('panel-files')?.classList.toggle('active', tab === 'files');
    $('panel-iframe').classList.toggle('active', resolveIframeRoute(tab) != null);

    window.tonglingAgentScanDock?.setAgentTabActive(tab === 'agent');

    if (tab === 'files' && window.tonglingFiles) window.tonglingFiles.load();

    if (tab === 'agent' && preferMacTermAuto() && !isTermFullscreen()) {
      setTimeout(() => setTermFullscreen(true), 40);
    }

    updateTasksSubnav(tab);
    updateMobileChrome(tab);
    closeMoreSheet();

    const iframeRoute = resolveIframeRoute(tab);
    if (iframeRoute) {
      const frame = $('hs-frame');
      let raw = iframeRoute;
      if (tab === 'scanviz') {
        const pending = pendingScanVizOpts;
        pendingScanVizOpts = null;
        const q = new URLSearchParams();
        const sid = (pending && pending.sessionId != null)
          ? pending.sessionId
          : (selectedClaudeSessionId || '');
        if (sid) q.set('claude_session', sid);
        else q.set('noselect', '1');
        if (pending?.host) q.set('focus_host', pending.host);
        if (pending?.tool) q.set('focus_tool', pending.tool);
        if (pending?.q) q.set('focus_q', pending.q);
        const qs = q.toString();
        raw = qs ? `${raw}${raw.includes('?') ? '&' : '?'}${qs}` : raw;
        // 强制刷新，保证从摘要点过来一定带上新参数
        frame.removeAttribute('data-src');
      }
      const src = withAuth(raw.startsWith('/tongling/') ? raw : raw);
      if (frame.getAttribute('data-src') !== src) {
        frame.src = src;
        frame.setAttribute('data-src', src);
      }
      if (raw.startsWith(`${HS_EMBED}`)) {
        setTimeout(() => injectHexStrikeEmbedStyles(frame), 50);
        setTimeout(() => injectHexStrikeEmbedStyles(frame), 350);
        setTimeout(() => injectHexStrikeEmbedStyles(frame), 900);
      } else {
        setTimeout(() => injectHexStrikeEmbedStyles(frame), 50);
        setTimeout(() => injectHexStrikeEmbedStyles(frame), 350);
      }
    }

    if (tab === 'agent') {
      setTimeout(fitTerminal, 120);
      setTimeout(() => maybeAutoAttach(), 600);
    }
    activateMacAppContent(tab);
  }

  function resolveWsUrls(cfg) {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname;
    const pagePort = parseInt(window.location.port, 10) || 0;
    const portSuffix = window.location.port ? `:${window.location.port}` : '';
    const urls = [];
    const wsPort = cfg.ws_port || (cfg.api_port ? cfg.api_port + 100 : 0);

    // 独立 WS 端口 (15138) 更稳定，优先于 Flask 同端口升级
    if (wsPort && wsPort !== pagePort) {
      urls.push(withAuth(`${proto}//${host}:${wsPort}/claude`));
    }
    if (cfg.ws_same_port && cfg.ws_path) {
      const same = withAuth(`${proto}//${host}${portSuffix}${cfg.ws_path}`);
      if (!urls.includes(same)) urls.push(same);
    }
    if (wsPort && !urls.length) {
      urls.push(withAuth(`${proto}//${host}:${wsPort}/claude`));
    }
    return urls;
  }

  function wsPortHint(cfg) {
    const p = cfg?.ws_port || (cfg?.api_port ? cfg.api_port + 100 : 0);
    if (!p) return '';
    const pagePort = parseInt(window.location.port, 10) || 0;
    if (p !== pagePort) {
      return `请确认已映射 WebSocket 端口 ${p}（与网页端口 ${pagePort || cfg.api_port} 一同放行防火墙）`;
    }
    if (cfg?.ws_same_port) return '终端与网页同端口';
    return `请映射 WebSocket 端口 ${p}`;
  }

  async function loadConfig() {
    const r = await apiFetch('/tongling/api/config');
    config = await r.json();
    if (!r.ok || config.success === false) {
      const err = config.error || `配置加载失败 (HTTP ${r.status})`;
      setGlobalStatus(err, false);
      setSideHint(r.status === 401 ? 'Token 已失效，请从桌面重新打开 Web 控制台' : err, 'err');
      setProviderStatus(r.status === 401 ? 'Token 失效' : err, true);
      return;
    }
    if (config.web_token) {
      sessionStorage.setItem(AUTH_TOKEN_KEY, config.web_token);
    }
    const hs = config.hexstrike_healthy ? '在线' : '未就绪';
    setGlobalStatus(`:${config.api_port} · ${hs}`, config.hexstrike_healthy);

    if (config.providers_data) {
      if (config.providers_data.error && !applyProviderPayload(config.providers_data)) {
        setProviderStatus(config.providers_data.error, true);
      } else {
        applyProviderPayload(config.providers_data);
      }
    }

    const preview = $('config-preview');
    if (preview) {
      preview.textContent = JSON.stringify({
        workdir: config.claude_workdir,
        workdir_ok: config.claude_workdir_exists,
        pty: config.pty_available,
        ws: config.ws_url,
      }, null, 2);
    }

    if (!config.pty_available) {
      setTermStatus('Web 终端不可用（缺少 winpty）');
      if ($('btn-term-start')) $('btn-term-start').disabled = true;
      if ($('m-btn-start')) $('m-btn-start').disabled = true;
    }
    if (!config.claude_workdir_exists) {
      setSideHint('Claude 工作目录不存在，请先安装 AI 智能体资源包', 'err');
    }
    if (config.hexstrike_tool_stats) {
      renderToolStats(config.hexstrike_tool_stats);
    }
    applyBurpMcpPrefs(null, config.burp_mcp);
    restoreClaudeSessionPreference();
    if (window.tonglingAgentScanDock) {
      window.tonglingAgentScanDock.setWorkdir(config.claude_workdir || '');
      // 摘要只跟当前运行终端；页面刚打开时清空，等终端 started 再绑定
      window.tonglingAgentScanDock.setSessionId('');
      window.tonglingAgentScanDock.ready();
    }
    loadClaudeSessions();
    loadAudits();
    applySidePanelCollapsed(localStorage.getItem(LS_SIDE_COLLAPSED) === '1');
    updateTermButtons();
  }

  let termResizeBound = false;

  function getTermPool() {
    let pool = $('session-term-pool');
    if (!pool) {
      pool = document.createElement('div');
      pool.id = 'session-term-pool';
      pool.setAttribute('hidden', '');
      document.body.appendChild(pool);
    }
    return pool;
  }

  function createXtermInstance(host, sessionId) {
    const mobile = isMobileView();
    const fontSize = mobile ? 15 : 16;
    const t = new Terminal({
      cursorBlink: !mobile,
      fontFamily: "'IBM Plex Mono', 'JetBrains Mono', 'Cascadia Code', Consolas, monospace",
      fontSize,
      lineHeight: mobile ? 1.15 : 1.2,
      scrollback: mobile ? 2000 : 3500,
      scrollSensitivity: mobile ? 4 : 2,
      fastScrollSensitivity: mobile ? 8 : 5,
      smoothScrollDuration: 0,
      scrollOnUserInteraction: true,
      allowTransparency: false,
      theme: getTermTheme(),
    });
    const fit = new FitAddon.FitAddon();
    t.loadAddon(fit);
    t.open(host);
    bindTermClipboardKeys();
    t.attachCustomKeyEventHandler((ev) => {
      if (handleTermClipboardKey(ev)) return false;
      return true;
    });
    t.onData((data) => {
      const sid = sessionId || activeSessionId;
      const st = sid ? sessionTerms[sid] : null;
      if (st) st.stickBottom = true;
      if (sid === activeSessionId) termStickBottom = true;
      markTermTyping();
      if (ws && ws.readyState === WebSocket.OPEN && sid) {
        ws.send(JSON.stringify({ type: 'input', session_id: sid, data }));
      }
    });
    let lastSentCols = 0;
    let lastSentRows = 0;
    t.onResize((size) => {
      const sid = sessionId || activeSessionId;
      if (!ws || ws.readyState !== WebSocket.OPEN || !sid) return;
      if (size.cols === lastSentCols && size.rows === lastSentRows) return;
      lastSentCols = size.cols;
      lastSentRows = size.rows;
      ws.send(JSON.stringify({
        type: 'resize',
        session_id: sid,
        cols: size.cols,
        rows: size.rows,
      }));
    });
    return { term: t, fitAddon: fit };
  }

  function disposeBootstrapTerm() {
    if (!term) return;
    if (Object.values(sessionTerms).some((st) => st.term === term)) return;
    try { term.dispose(); } catch (e) { /* ignore */ }
    term = null;
    fitAddon = null;
  }

  function ensureSessionTerm(sessionId) {
    if (!sessionId || sessionId === '__empty__') return null;
    if (sessionTerms[sessionId]) return sessionTerms[sessionId];
    disposeBootstrapTerm();
    const host = document.createElement('div');
    host.className = 'session-term-host';
    host.dataset.sessionId = sessionId;
    getTermPool().appendChild(host);
    const created = createXtermInstance(host, sessionId);
    const st = {
      term: created.term,
      fitAddon: created.fitAddon,
      host,
      stickBottom: true,
      outputBuf: '',
      outputTimer: 0,
      outputRaf: 0,
      viewportEl: null,
      replayApplied: false,
    };
    sessionTerms[sessionId] = st;
    bindTermScrollGuardFor(sessionId);
    if (sessionId === activeSessionId) syncActiveTermPointers();
    return st;
  }

  function disposeSessionTerm(sessionId) {
    const st = sessionTerms[sessionId];
    if (!st) return;
    if (st.outputTimer) clearTimeout(st.outputTimer);
    if (st.outputRaf) cancelAnimationFrame(st.outputRaf);
    try { st.term.dispose(); } catch (e) { /* ignore */ }
    st.host.remove();
    delete sessionTerms[sessionId];
    subscribedSessions.delete(sessionId);
    if (term === st.term) {
      term = null;
      fitAddon = null;
    }
  }

  function syncActiveTermPointers() {
    const st = activeSessionId ? sessionTerms[activeSessionId] : null;
    if (!st) return;
    term = st.term;
    fitAddon = st.fitAddon;
    termStickBottom = st.stickBottom;
  }

  let subscribeAllTimer = 0;
  function requestSubscribeAll() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    // 合并短时间内多次订阅请求，避免重复 replay
    if (subscribeAllTimer) clearTimeout(subscribeAllTimer);
    subscribeAllTimer = setTimeout(() => {
      subscribeAllTimer = 0;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'subscribe_all' }));
      }
    }, 120);
  }

  function mountSessionTerminals() {
    if (isTermFullscreen()) {
      const pool = getTermPool();
      termSessions.forEach((s) => {
        const st = ensureSessionTerm(s.id);
        if (!st) return;
        // 最小化的终端放到隐藏池，减少同时布局的 xterm
        if (macTermMinimized.has(s.id)) {
          if (st.host.parentElement !== pool) pool.appendChild(st.host);
          return;
        }
        const win = findMacWin(s.id);
        const body = win?.querySelector('.mac-term-win-body');
        if (body && st.host.parentElement !== body) {
          body.querySelectorAll('.mac-term-win-idle').forEach((el) => el.remove());
          body.appendChild(st.host);
        }
      });
      return;
    }
    const mount = $('terminal-host');
    Object.keys(sessionTerms).forEach((id) => {
      const st = sessionTerms[id];
      if (!st) return;
      if (id === activeSessionId && mount) {
        if (st.host.parentElement !== mount) mount.appendChild(st.host);
      } else if (st.host.parentElement !== getTermPool()) {
        getTermPool().appendChild(st.host);
      }
    });
  }

  function initTerminal() {
    if (!termResizeBound) {
      termResizeBound = true;
      window.addEventListener('resize', () => setTimeout(fitTerminal, 80));
      window.addEventListener('orientationchange', () => setTimeout(fitTerminal, 200));
    }
    // 尚无会话时：在主区域开一个引导终端用于连接提示
    if (!term && !activeSessionId && !Object.keys(sessionTerms).length) {
      const host = $('terminal-host');
      if (!host) return;
      const created = createXtermInstance(host, null);
      term = created.term;
      fitAddon = created.fitAddon;
      bindTermScrollGuard();
    }
  }

  function isMacTermWinVisible(sessionId) {
    if (!sessionId) return false;
    if (macTermMinimized.has(sessionId)) return false;
    const win = findMacWin(sessionId);
    if (!win) return true;
    if (win.classList.contains('is-minimized') || win.style.display === 'none') return false;
    return true;
  }

  function fitSessionTerm(sessionId) {
    const st = sessionId ? sessionTerms[sessionId] : null;
    if (!st?.fitAddon) return;
    if (isTermFullscreen() && !isMacTermWinVisible(sessionId)) return;
    try { st.fitAddon.fit(); } catch (e) { /* layout hidden */ }
    bindTermScrollGuardFor(sessionId);
  }

  function fitTerminal(onlySessionId) {
    if (fitTerminalTimer) clearTimeout(fitTerminalTimer);
    const delay = isMobileView() ? 160 : 80;
    const targetId = typeof onlySessionId === 'string' ? onlySessionId : '';
    fitTerminalTimer = setTimeout(() => {
      fitTerminalTimer = null;
      if (isTermFullscreen()) {
        if (targetId) {
          fitSessionTerm(targetId);
          return;
        }
        // 优先 fit 当前活跃窗，其它可见窗空闲再 fit，避免 N 路同时 reshape
        if (activeSessionId) fitSessionTerm(activeSessionId);
        const rest = Object.keys(sessionTerms).filter((id) => id !== activeSessionId && isMacTermWinVisible(id));
        if (!rest.length) return;
        let i = 0;
        const step = () => {
          if (i >= rest.length) return;
          fitSessionTerm(rest[i++]);
          if (i < rest.length) {
            if (typeof requestIdleCallback === 'function') requestIdleCallback(step, { timeout: 120 });
            else setTimeout(step, 16);
          }
        };
        if (typeof requestIdleCallback === 'function') requestIdleCallback(step, { timeout: 120 });
        else setTimeout(step, 16);
        return;
      }
      if (targetId) {
        fitSessionTerm(targetId);
        return;
      }
      if (activeSessionId && sessionTerms[activeSessionId]) {
        fitSessionTerm(activeSessionId);
        return;
      }
      if (!fitAddon || !term) return;
      try { fitAddon.fit(); } catch (e) { /* layout hidden */ }
      bindTermScrollGuard();
    }, delay);
  }

  function getTermViewportFor(sessionId) {
    const st = sessionId ? sessionTerms[sessionId] : null;
    if (st) {
      if (st.viewportEl && st.viewportEl.isConnected) return st.viewportEl;
      st.viewportEl = st.host.querySelector('.xterm-viewport');
      return st.viewportEl;
    }
    return $('terminal-host')?.querySelector('.xterm-viewport') || null;
  }

  function getTermViewport() {
    return getTermViewportFor(activeSessionId) || $('terminal-host')?.querySelector('.xterm-viewport') || null;
  }

  /** 根据 DOM 滚动位置判断是否在底部（比 xterm buffer 状态更可靠） */
  function isViewportAtBottom(viewport, fallbackStick) {
    if (!viewport) return fallbackStick !== false;
    const threshold = 16;
    return viewport.scrollTop + viewport.clientHeight >= viewport.scrollHeight - threshold;
  }

  function syncTermStickBottomFor(sessionId) {
    const st = sessionId ? sessionTerms[sessionId] : null;
    const viewport = getTermViewportFor(sessionId);
    if (viewport) {
      const stick = isViewportAtBottom(viewport, st ? st.stickBottom : termStickBottom);
      if (st) st.stickBottom = stick;
      if (!sessionId || sessionId === activeSessionId) termStickBottom = stick;
    }
  }

  function syncTermStickBottom() {
    if (termScrollSyncRaf) return;
    termScrollSyncRaf = requestAnimationFrame(() => {
      termScrollSyncRaf = 0;
      syncTermStickBottomFor(activeSessionId);
    });
  }

  function bindTermScrollGuardFor(sessionId) {
    const viewport = getTermViewportFor(sessionId);
    if (!viewport || viewport._tlScrollGuardBound) return;
    viewport._tlScrollGuardBound = true;
    const onScroll = () => syncTermStickBottomFor(sessionId);
    viewport.addEventListener('scroll', onScroll, { passive: true });
    viewport.addEventListener('wheel', onScroll, { passive: true });
    viewport.addEventListener('touchend', onScroll, { passive: true });
  }

  function bindTermScrollGuard() {
    bindTermScrollGuardFor(activeSessionId);
    const viewport = $('terminal-host')?.querySelector('.xterm-viewport');
    if (!viewport || viewport._tlScrollGuardBound) return;
    viewport._tlScrollGuardBound = true;
    viewport.addEventListener('scroll', syncTermStickBottom, { passive: true });
    viewport.addEventListener('wheel', syncTermStickBottom, { passive: true });
    viewport.addEventListener('touchend', syncTermStickBottom, { passive: true });
  }

  function scheduleTermScrollToBottomFor(sessionId) {
    requestAnimationFrame(() => {
      const st = sessionId ? sessionTerms[sessionId] : null;
      const t = st?.term || term;
      const stick = st ? st.stickBottom : termStickBottom;
      if (!t || !stick) return;
      const viewport = getTermViewportFor(sessionId);
      if (viewport && !isViewportAtBottom(viewport, stick)) {
        if (st) st.stickBottom = false;
        if (!sessionId || sessionId === activeSessionId) termStickBottom = false;
        return;
      }
      try { t.scrollToBottom(); } catch (e) { /* ignore */ }
      if (viewport) viewport.scrollTop = viewport.scrollHeight;
    });
  }

  function scheduleTermScrollToBottom() {
    scheduleTermScrollToBottomFor(activeSessionId);
  }

  /**
   * 写入指定会话终端：用户在底部时跟随输出；上滑阅读时固定视口不跳动。
   */
  function writeTermOutputFor(sessionId, data) {
    if (!data) return;
    const st = sessionId ? sessionTerms[sessionId] : null;
    const t = st?.term || term;
    if (!t) return;
    const stickFlag = st ? st.stickBottom : termStickBottom;
    const inPlace = isInPlaceTermUpdate(data);

    // TUI 原地刷新且跟底：跳过 scroll 测量，避免每帧强制 layout
    if (stickFlag && inPlace) {
      t.write(data);
      return;
    }

    const viewport = getTermViewportFor(sessionId);
    const stick = stickFlag && (!viewport || isViewportAtBottom(viewport, stickFlag));

    if (stick) {
      t.write(data);
      scheduleTermScrollToBottomFor(sessionId);
      return;
    }

    const savedScrollTop = viewport ? viewport.scrollTop : null;
    t.write(data, () => {
      if (viewport && savedScrollTop !== null) {
        viewport.scrollTop = savedScrollTop;
      }
    });
  }

  function writeTermOutput(data) {
    writeTermOutputFor(activeSessionId, data);
  }

  function drainTermOutputQueueFor(sessionId) {
    const st = sessionId ? sessionTerms[sessionId] : null;
    // 桌面交互中：只刷当前会话，后台排队延后
    if (isMacDesktopInteracting() && sessionId && sessionId !== activeSessionId) {
      if (st?.outputBuf) scheduleTermOutputFlushFor(sessionId);
      return;
    }
    if (st) {
      if (!st.outputBuf) return;
      let chunk = st.outputBuf;
      st.outputBuf = '';
      if (chunk.length > TERM_WRITE_MAX) {
        st.outputBuf = chunk.slice(TERM_WRITE_MAX);
        chunk = chunk.slice(0, TERM_WRITE_MAX);
      }
      writeTermOutputFor(sessionId, chunk);
      if (st.outputBuf) scheduleTermOutputFlushFor(sessionId);
      return;
    }
    if (!term || !termOutputBuf) return;
    let chunk = termOutputBuf;
    termOutputBuf = '';
    if (chunk.length > TERM_WRITE_MAX) {
      termOutputBuf = chunk.slice(TERM_WRITE_MAX);
      chunk = chunk.slice(0, TERM_WRITE_MAX);
    }
    writeTermOutput(chunk);
    if (termOutputBuf) scheduleTermOutputFlush();
  }

  function drainTermOutputQueue() {
    drainTermOutputQueueFor(activeSessionId);
  }

  function scheduleTermOutputFlushFor(sessionId) {
    const st = sessionId ? sessionTerms[sessionId] : null;
    if (st) {
      if (st.outputRaf || st.outputTimer) return;
      const run = () => {
        st.outputRaf = 0;
        st.outputTimer = 0;
        drainTermOutputQueueFor(sessionId);
      };
      // 当前会话按动画帧合并；拖窗/改尺寸时也走定时器降频
      if (sessionId === activeSessionId && !isMacDesktopInteracting()) {
        st.outputRaf = requestAnimationFrame(run);
        return;
      }
      st.outputTimer = setTimeout(run, termFlushDelayMs(sessionId));
      return;
    }
    if (termOutputTimer) return;
    termOutputTimer = setTimeout(() => {
      termOutputTimer = 0;
      drainTermOutputQueue();
    }, termFlushDelayMs());
  }

  function scheduleTermOutputFlush() {
    scheduleTermOutputFlushFor(activeSessionId);
  }

  /** 合并高频 output：一律批写，当前会话 rAF，避免逐键同步刷屏卡输入 */
  function queueTermOutputFor(sessionId, data) {
    if (!data) return;
    const isActive = !sessionId || sessionId === activeSessionId || launchingNewSession;
    // 打字高峰跳过 Token 记账；连接探测始终跑（国内未配 API 时需及时提示）
    if (isActive) {
      if (!isTermTypingHot()) trackTermTokensFromOutput(data);
      probeAnthropicConnectError(data);
    }
    if (sessionId) ensureSessionTerm(sessionId);
    const st = sessionId ? sessionTerms[sessionId] : null;
    if (st) {
      st.outputBuf += data;
      scheduleTermOutputFlushFor(sessionId);
      return;
    }
    termOutputBuf += data;
    scheduleTermOutputFlush();
  }

  function queueTermOutput(data) {
    queueTermOutputFor(activeSessionId, data);
  }

  function flushTermOutputFor(sessionId) {
    const st = sessionId ? sessionTerms[sessionId] : null;
    if (st?.outputTimer) {
      clearTimeout(st.outputTimer);
      st.outputTimer = 0;
    }
    if (st?.outputRaf) {
      cancelAnimationFrame(st.outputRaf);
      st.outputRaf = 0;
    }
    drainTermOutputQueueFor(sessionId);
  }

  function flushTermOutput() {
    if (termOutputTimer) {
      clearTimeout(termOutputTimer);
      termOutputTimer = 0;
    }
    drainTermOutputQueue();
    if (activeSessionId) flushTermOutputFor(activeSessionId);
  }

  function applySidePanelCollapsed(collapsed) {
    const layout = $('agent-layout');
    const btn = $('btn-panel-toggle');
    if (!layout) return;
    layout.classList.toggle('side-collapsed', !!collapsed);
    if (btn) {
      btn.classList.toggle('panel-collapsed', !!collapsed);
      btn.title = collapsed ? '展开控制面板' : '收起控制面板';
      btn.textContent = collapsed ? '◨' : '◧';
    }
    localStorage.setItem(LS_SIDE_COLLAPSED, collapsed ? '1' : '0');
    setTimeout(fitTerminal, 60);
  }

  function toggleSidePanel() {
    const layout = $('agent-layout');
    if (!layout) return;
    applySidePanelCollapsed(!layout.classList.contains('side-collapsed'));
  }

  function isTermFullscreen() {
    return document.body.classList.contains('term-fs');
  }

  const LS_MAC_TERM = 'tongling_mac_term_v1';
  const LS_MAC_DOCK = 'tongling_mac_dock_v1';
  const LS_MAC_LAYOUT = 'tongling_mac_layout_v1';
  const LS_MAC_TIP = 'tongling_mac_tip_v1';
  let macWinMaxId = '';
  let macDragState = null;
  let macClockTimer = 0;
  let macMetricsTimer = 0;
  let macMetricsBusy = false;
  /** 全桌面统一 z-order（终端窗 + App 窗共用，点击置顶） */
  let macDeskZ = 40;
  let macAppMaxId = '';
  let macAppDragState = null;
  /** 已最小化的终端会话 id */
  const macTermMinimized = new Set();
  /** App 窗几何持久化 */
  const macAppGeomStore = Object.create(null);
  /** @type {Record<string, { left: number, top: number, width: number, height: number, z: number }>} */
  const macWinGeom = Object.create(null);
  let macLayoutSaveTimer = 0;

  function getMacDesktopStage() {
    return $('mac-term-stage');
  }

  function macPrefersReducedMotion() {
    try {
      return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) {
      return false;
    }
  }

  function playMacWinEnter(el) {
    if (!el || macPrefersReducedMotion()) return;
    el.classList.remove('mac-win-exit');
    el.classList.remove('mac-win-enter');
    // 强制重启动画
    void el.offsetWidth;
    el.classList.add('mac-win-enter');
    const done = () => {
      el.classList.remove('mac-win-enter');
      el.removeEventListener('animationend', done);
    };
    el.addEventListener('animationend', done);
  }

  function playMacWinExit(el, onDone) {
    if (!el) {
      onDone?.();
      return;
    }
    if (macPrefersReducedMotion()) {
      onDone?.();
      return;
    }
    el.classList.remove('mac-win-enter');
    el.classList.add('mac-win-exit');
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      el.classList.remove('mac-win-exit');
      el.removeEventListener('animationend', finish);
      onDone?.();
    };
    el.addEventListener('animationend', finish);
    setTimeout(finish, 220);
  }

  function loadMacLayout() {
    try {
      const raw = JSON.parse(localStorage.getItem(LS_MAC_LAYOUT) || '{}');
      if (raw && typeof raw === 'object') {
        if (raw.terms && typeof raw.terms === 'object') {
          Object.keys(raw.terms).forEach((id) => {
            const g = raw.terms[id];
            if (!g || typeof g !== 'object') return;
            macWinGeom[id] = {
              left: Number(g.left) || 36,
              top: Number(g.top) || 28,
              width: Number(g.width) || 640,
              height: Number(g.height) || 420,
              z: Number(g.z) || 40,
            };
            if ((macWinGeom[id].z || 0) > macDeskZ) macDeskZ = macWinGeom[id].z;
          });
        }
        if (raw.apps && typeof raw.apps === 'object') {
          Object.keys(raw.apps).forEach((tab) => {
            const g = raw.apps[tab];
            if (!g || typeof g !== 'object') return;
            macAppGeomStore[tab] = {
              left: Number(g.left) || 48,
              top: Number(g.top) || 36,
              width: Number(g.width) || 720,
              height: Number(g.height) || 480,
              z: Number(g.z) || 40,
            };
            if ((macAppGeomStore[tab].z || 0) > macDeskZ) macDeskZ = macAppGeomStore[tab].z;
          });
        }
      }
    } catch (e) { /* ignore */ }
  }

  function scheduleSaveMacLayout() {
    if (macLayoutSaveTimer) clearTimeout(macLayoutSaveTimer);
    macLayoutSaveTimer = setTimeout(() => {
      macLayoutSaveTimer = 0;
      try {
        // 同步可见 App 窗当前位置
        Object.keys(macAppWindows).forEach((tab) => {
          const el = macAppWindows[tab]?.el;
          if (!el || el.classList.contains('maximized')) return;
          macAppGeomStore[tab] = {
            left: parseFloat(el.style.left) || 0,
            top: parseFloat(el.style.top) || 0,
            width: parseFloat(el.style.width) || el.offsetWidth,
            height: parseFloat(el.style.height) || el.offsetHeight,
            z: parseInt(el.style.zIndex || '40', 10) || 40,
          };
        });
        localStorage.setItem(LS_MAC_LAYOUT, JSON.stringify({
          terms: macWinGeom,
          apps: macAppGeomStore,
        }));
      } catch (e) { /* ignore */ }
    }, 360);
  }

  function showMacDesktopTip() {
    if (localStorage.getItem(LS_MAC_TIP) === '1') return;
    const tip = $('mac-desktop-tip');
    if (!tip) return;
    tip.hidden = false;
  }

  function dismissMacDesktopTip() {
    localStorage.setItem(LS_MAC_TIP, '1');
    const tip = $('mac-desktop-tip');
    if (tip) tip.hidden = true;
  }

  function isMacTypingTarget(el) {
    if (!el) return false;
    const tag = (el.tagName || '').toUpperCase();
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
    if (el.isContentEditable) return true;
    if (el.closest?.('.xterm')) return true;
    return false;
  }

  function minimizeMacTermWindow(sid, win) {
    if (!sid || sid === '__empty__' || !win) return;
    playMacWinExit(win, () => {
      macTermMinimized.add(sid);
      win.classList.add('is-minimized');
      win.style.display = 'none';
      if (macWinMaxId === sid) macWinMaxId = '';
      win.classList.remove('maximized');
      const st = sessionTerms[sid];
      if (st?.host) getTermPool().appendChild(st.host);
      syncMacDockActive('agent');
      scheduleSaveMacLayout();
    });
  }

  function minimizeMacAppByTab(tab) {
    const state = macAppWindows[tab];
    if (!state?.el) return;
    const win = state.el;
    playMacWinExit(win, () => {
      win.classList.add('is-minimized');
      win.style.display = 'none';
      if (macAppMaxId === tab) macAppMaxId = '';
      win.classList.remove('maximized');
      syncMacDockActive(tab);
    });
  }

  function cycleMacDesktopWindows() {
    const wins = listVisibleMacDesktopWindows();
    if (wins.length < 2) {
      if (wins[0]) setMacDesktopActiveWindow(wins[0]);
      return;
    }
    const front = getFrontMacDesktopWindow();
    const idx = Math.max(0, wins.indexOf(front));
    const next = wins[(idx + 1) % wins.length];
    if (next.classList.contains('mac-app-win') && next.dataset.appTab) {
      focusMacAppWindow(next.dataset.appTab);
    } else {
      const sid = next.getAttribute('data-session-id');
      if (sid && sid !== '__empty__') focusMacWindow(sid, { switchSession: true });
      else setMacDesktopActiveWindow(next);
    }
  }

  function raiseMacDesktopWindow(el) {
    if (!el) return;
    macDeskZ += 1;
    el.style.zIndex = String(macDeskZ);
  }

  function setMacDesktopActiveWindow(el) {
    if (!el) return;
    raiseMacDesktopWindow(el);
    if (macActiveWinEl === el) {
      el.classList.add('active');
      syncMacMenubarAppName();
      return;
    }
    if (macActiveWinEl) macActiveWinEl.classList.remove('active');
    el.classList.add('active');
    macActiveWinEl = el;
    syncMacMenubarAppName();
  }

  function listVisibleMacDesktopWindows() {
    const stage = getMacDesktopStage();
    if (!stage) return [];
    return Array.from(stage.querySelectorAll('.mac-term-win, .mac-app-win')).filter((w) => {
      if (w.classList.contains('is-minimized')) return false;
      if (w.style.display === 'none') return false;
      return true;
    });
  }

  function getFrontMacDesktopWindow() {
    const wins = listVisibleMacDesktopWindows();
    if (!wins.length) return null;
    return wins.reduce((best, w) => {
      const z = parseInt(w.style.zIndex || '0', 10) || 0;
      const bz = parseInt(best.style.zIndex || '0', 10) || 0;
      return z >= bz ? w : best;
    });
  }

  /** Esc：关菜单 → 关/藏前置窗 → 无可见窗再退出悬浮 */
  function handleMacDesktopEscape() {
    if (!$('mac-menu-window-panel')?.hidden || !$('mac-menu-apple-panel')?.hidden) {
      closeAllMacMenus();
      return;
    }
    const front = getFrontMacDesktopWindow();
    if (!front) {
      setTermFullscreen(false);
      return;
    }
    if (front.classList.contains('mac-app-win')) {
      const tab = front.dataset.appTab;
      if (tab) closeMacAppWindow(tab);
      return;
    }
    const sid = front.getAttribute('data-session-id');
    if (!sid || sid === '__empty__') {
      setTermFullscreen(false);
      return;
    }
    minimizeMacTermWindow(sid, front);
  }

  function restoreMinimizedTerminals() {
    const ids = Array.from(macTermMinimized);
    if (!ids.length) return false;
    const focusId = ids.includes(activeSessionId)
      ? activeSessionId
      : (ids[ids.length - 1] || '');
    ids.forEach((id) => {
      macTermMinimized.delete(id);
      const win = findMacWin(id);
      if (win) {
        win.classList.remove('is-minimized');
        win.style.display = '';
        playMacWinEnter(win);
      }
    });
    // 最小化时 host 已挪到隐藏池；必须先 remount，再 focus（否则 wasMin=false 会跳过挂载）
    mountSessionTerminals();
    if (focusId) focusMacWindow(focusId, { switchSession: true });
    // remount 后必须 fit，否则 canvas 尺寸可能为 0 / 内容看似空白
    fitTerminal(focusId || undefined);
    return true;
  }

  function refreshMacWindowMenu() {
    const list = $('mac-menu-win-list');
    if (!list) return;
    const front = getFrontMacDesktopWindow();
    const frontSid = front?.classList.contains('mac-term-win')
      ? front.getAttribute('data-session-id')
      : '';
    const frontTab = front?.classList.contains('mac-app-win')
      ? front.dataset.appTab
      : '';

    const rows = [];
    if (termSessions.length) {
      termSessions.forEach((s, i) => {
        const min = macTermMinimized.has(s.id);
        const label = s.title || `终端 ${i + 1}`;
        rows.push({
          kind: 'term',
          id: s.id,
          label,
          min,
          front: !min && s.id === frontSid,
        });
      });
    } else {
      rows.push({
        kind: 'term',
        id: '__empty__',
        label: '终端',
        min: false,
        front: frontSid === '__empty__',
      });
    }
    Object.keys(macAppWindows).forEach((tab) => {
      const el = macAppWindows[tab]?.el;
      if (!el) return;
      const min = el.classList.contains('is-minimized') || el.style.display === 'none';
      rows.push({
        kind: 'app',
        id: tab,
        label: TAB_META[tab]?.title || tab,
        min,
        front: !min && tab === frontTab,
      });
    });

    if (!rows.length) {
      list.innerHTML = `<div class="mac-menu-empty">${t('status.noWindow')}</div>`;
      return;
    }
    list.innerHTML = rows.map((r) => {
      const mark = r.min ? '<span class="mac-menu-win-mark">已最小化</span>' : '';
      const cls = [
        r.min ? 'is-min' : '',
        r.front ? 'is-front' : '',
      ].filter(Boolean).join(' ');
      return `<button type="button" role="menuitem" class="${cls}" data-mac-win-kind="${r.kind}" data-mac-win-id="${escapeHtml(r.id)}">${escapeHtml(r.label)}${mark}</button>`;
    }).join('');
  }

  function activateMacWindowMenuItem(kind, id) {
    if (kind === 'app') {
      if (macAppWindows[id]) {
        focusMacAppWindow(id);
      } else {
        switchTab(id);
      }
      return;
    }
    if (id === '__empty__') {
      const win = findMacWin('__empty__');
      if (win) {
        win.classList.remove('is-minimized');
        win.style.display = '';
        setMacDesktopActiveWindow(win);
      }
      return;
    }
    focusMacWindow(id, { switchSession: true });
  }

  function fillMacEmptyIdle(win) {
    const body = win?.querySelector('.mac-term-win-body');
    if (!body || body.querySelector('.mac-term-win-idle')) return;
    body.innerHTML = `
      <div class="mac-term-win-idle">
        <strong>尚无终端会话</strong>
        <span>在多窗口工作台中新建一个终端会话</span>
        <button type="button" class="btn btn-primary btn-sm mac-idle-new">新建窗口</button>
      </div>`;
    const go = (e) => {
      e?.preventDefault?.();
      e?.stopPropagation?.();
      connectAndStart({ fresh: true });
    };
    body.querySelector('.mac-idle-new')?.addEventListener('click', go);
  }
  /** @type {Record<string, { el: HTMLElement, panel?: HTMLElement|null, marker?: Comment|null, iframe?: HTMLIFrameElement|null }>} */
  const macAppWindows = Object.create(null);

  const MAC_NATIVE_PANELS = {
    control: 'side-card-desktop',
    files: 'panel-files',
    skills: 'panel-skills',
    prompts: 'panel-prompts',
    fplib: 'panel-fplib',
    vulnlib: 'panel-vulnlib',
    mcp: 'panel-mcp',
    im: 'panel-im',
    nps: 'panel-nps',
    reports: 'panel-reports',
  };

  function preferMacTermAuto() {
    const v = localStorage.getItem(LS_MAC_TERM);
    if (v === '0') return false;
    if (v === '1') return true;
    // 未设置时：PC 默认打开多窗口工作台；手机仍用普通终端布局
    return !isMobileView();
  }

  function preferMacDockOpen() {
    return localStorage.getItem(LS_MAC_DOCK) !== '0';
  }

  function syncMacDockActive(tab) {
    const active = tab || 'agent';
    document.querySelectorAll('#mac-dock-inner .mac-dock-item').forEach((btn) => {
      const t = btn.dataset.tab;
      btn.classList.toggle('active', t === active);
      btn.classList.toggle('open', !!(t && macAppWindows[t]));
      if (t === 'agent') btn.classList.toggle('open', isTermFullscreen());
    });
  }

  function closeMacWindowMenu() {
    const panel = $('mac-menu-window-panel');
    const btn = $('btn-mac-menu-window');
    if (panel) panel.hidden = true;
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }

  function closeMacAppleMenu() {
    const panel = $('mac-menu-apple-panel');
    const btn = $('btn-mac-apple');
    if (panel) panel.hidden = true;
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }

  function closeAllMacMenus() {
    closeMacWindowMenu();
    closeMacAppleMenu();
  }

  function syncMacMenubarAppName() {
    const el = $('mac-menubar-app');
    if (!el) return;
    const front = getFrontMacDesktopWindow();
    if (!front) {
      el.textContent = t('menubar.terminal');
      return;
    }
    if (front.classList.contains('mac-app-win')) {
      const tab = front.dataset.appTab;
      el.textContent = (tab && TAB_META[tab]?.title) || t('tab.app');
      return;
    }
    const sid = front.getAttribute('data-session-id');
    if (!sid || sid === '__empty__') {
      el.textContent = '终端';
      return;
    }
    const s = termSessions.find((x) => x.id === sid);
    el.textContent = s?.title || '终端';
  }

  function setMacDockOpen(on) {
    const open = !!on;
    document.body.classList.toggle('mac-dock-collapsed', !open);
    localStorage.setItem(LS_MAC_DOCK, open ? '1' : '0');
    const dock = $('mac-dock');
    const apple = $('btn-mac-apple');
    const prog = $('btn-mac-menu-programs');
    if (apple) apple.setAttribute('aria-pressed', open ? 'true' : 'false');
    if (prog) prog.classList.toggle('active', open);
    if (isTermFullscreen() && dock) dock.hidden = false;
    setTimeout(fitTerminal, 80);
  }

  function toggleMacDock() {
    setMacDockOpen(document.body.classList.contains('mac-dock-collapsed'));
  }

  function defaultMacAppGeom(index) {
    const width = Math.min(960, Math.max(520, window.innerWidth * 0.58));
    const height = Math.min(640, Math.max(360, window.innerHeight * 0.62));
    return {
      left: 48 + (index % 5) * 36,
      top: 36 + (index % 5) * 28,
      width,
      height,
      z: ++macDeskZ,
    };
  }

  function restoreMacAppPanel(tab) {
    const state = macAppWindows[tab];
    if (!state?.panel) return;
    const panel = state.panel;
    panel.classList.remove('active');
    if (tab === 'control') panel.classList.add('desktop-only');
    if (state.marker?.parentNode) {
      state.marker.parentNode.insertBefore(panel, state.marker);
      state.marker.remove();
    } else {
      const layout = $('agent-layout');
      if (tab === 'control' && layout) layout.appendChild(panel);
      else {
        const main = document.querySelector('.shell-main');
        if (main) main.appendChild(panel);
      }
    }
    state.panel = null;
    state.marker = null;
  }

  function closeMacAppWindow(tab) {
    const state = macAppWindows[tab];
    if (!state) return;
    restoreMacAppPanel(tab);
    state.el.remove();
    delete macAppWindows[tab];
    if (macAppMaxId === tab) macAppMaxId = '';
    syncMacDockActive(Object.keys(macAppWindows)[0] || 'agent');
  }

  function closeAllMacAppWindows() {
    Object.keys(macAppWindows).forEach((tab) => closeMacAppWindow(tab));
  }

  function focusMacAppWindow(tab) {
    const state = macAppWindows[tab];
    if (!state) return;
    state.el.classList.remove('is-minimized');
    state.el.style.display = '';
    setMacDesktopActiveWindow(state.el);
    syncMacDockActive(tab);
  }

  function bindMacAppWinDrag(win, tab) {
    const bar = win.querySelector('.mac-app-win-bar');
    if (!bar || bar.dataset.macDragBound === '1') return;
    bar.dataset.macDragBound = '1';

    bar.addEventListener('pointerdown', (e) => {
      if (!isTermFullscreen()) return;
      if (e.button != null && e.button !== 0) return;
      if (e.target.closest('.mac-traffic, .mac-dot, button.mac-dot')) return;
      if (macAppMaxId === tab) {
        focusMacAppWindow(tab);
        return;
      }

      const stage = getMacDesktopStage();
      const baseLeft = parseFloat(win.style.left || '0') || 0;
      const baseTop = parseFloat(win.style.top || '0') || 0;
      const startClientX = e.clientX;
      const startClientY = e.clientY;
      let pendingLeft = baseLeft;
      let pendingTop = baseTop;
      let moved = false;
      let raf = 0;

      focusMacAppWindow(tab);
      win.classList.add('mac-dragging');
      document.body.classList.add('term-dragging');

      macAppDragState = { tab, pointerId: e.pointerId };

      const flush = () => {
        raf = 0;
        const dx = pendingLeft - baseLeft;
        const dy = pendingTop - baseTop;
        win.style.transform = `translate3d(${dx}px,${dy}px,0)`;
      };

      const onMove = (ev) => {
        if (!macAppDragState || macAppDragState.tab !== tab) return;
        if (macAppDragState.pointerId != null && ev.pointerId !== macAppDragState.pointerId) return;
        if (Math.abs(ev.clientX - startClientX) + Math.abs(ev.clientY - startClientY) > 3) moved = true;
        const maxL = Math.max(0, (stage?.clientWidth || window.innerWidth) - 120);
        const maxT = Math.max(0, (stage?.clientHeight || window.innerHeight) - 48);
        pendingLeft = Math.min(Math.max(0, baseLeft + (ev.clientX - startClientX)), maxL);
        pendingTop = Math.min(Math.max(0, baseTop + (ev.clientY - startClientY)), maxT);
        if (!raf) raf = requestAnimationFrame(flush);
      };

      const onUp = (ev) => {
        if (!macAppDragState || macAppDragState.tab !== tab) return;
        if (macAppDragState.pointerId != null && ev.pointerId !== macAppDragState.pointerId) return;
        if (raf) cancelAnimationFrame(raf);
        win.style.left = `${pendingLeft}px`;
        win.style.top = `${pendingTop}px`;
        win.style.transform = '';
        win.classList.remove('mac-dragging');
        macAppDragState = null;
        document.body.classList.remove('term-dragging');
        window.removeEventListener('pointermove', onMove, true);
        window.removeEventListener('pointerup', onUp, true);
        window.removeEventListener('pointercancel', onUp, true);
        if (!moved) focusMacAppWindow(tab);
        scheduleSaveMacLayout();
      };

      window.addEventListener('pointermove', onMove, true);
      window.addEventListener('pointerup', onUp, true);
      window.addEventListener('pointercancel', onUp, true);
      try { bar.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
      e.preventDefault();
      e.stopPropagation();
    });

    bar.addEventListener('dblclick', (e) => {
      if (!isTermFullscreen()) return;
      if (e.target.closest('.mac-traffic, .mac-dot, button.mac-dot')) return;
      e.preventDefault();
      macAppMaxId = macAppMaxId === tab ? '' : tab;
      win.classList.toggle('maximized', macAppMaxId === tab);
      win.classList.remove('is-minimized');
      win.style.display = '';
      win.style.transform = '';
      focusMacAppWindow(tab);
      setTimeout(() => window.dispatchEvent(new Event('resize')), 40);
    });
  }

  function loadMacAppFrame(iframe, tab) {
    let raw = resolveIframeRoute(tab);
    if (!raw || !iframe) return;
    if (tab === 'scanviz') {
      const pending = pendingScanVizOpts;
      pendingScanVizOpts = null;
      const q = new URLSearchParams();
      const sid = (pending && pending.sessionId != null)
        ? pending.sessionId
        : (selectedClaudeSessionId || '');
      if (sid) q.set('claude_session', sid);
      else q.set('noselect', '1');
      if (pending?.host) q.set('focus_host', pending.host);
      if (pending?.tool) q.set('focus_tool', pending.tool);
      if (pending?.q) q.set('focus_q', pending.q);
      const qs = q.toString();
      raw = qs ? `${raw}${raw.includes('?') ? '&' : '?'}${qs}` : raw;
    }
    const src = withAuth(raw.startsWith('/tongling/') ? raw : raw);
    if (iframe.getAttribute('data-src') !== src) {
      iframe.src = src;
      iframe.setAttribute('data-src', src);
    }
    const inject = () => injectHexStrikeEmbedStyles(iframe);
    iframe.addEventListener('load', inject, { once: true });
    setTimeout(inject, 80);
    setTimeout(inject, 400);
  }

  function activateMacAppContent(tab) {
    if (tab === 'skills') {
      ensureSkillsLoaded().then(() => {
        renderSkillList('page');
        loadLoadedSkills('page');
      });
    }
    if (tab === 'prompts' && window.tonglingPrompts) window.tonglingPrompts.load();
    if (tab === 'mcp') loadMcpPanel();
    if (tab === 'fplib' && window.tonglingLibraries) window.tonglingLibraries.loadFingerprintPanel();
    if (tab === 'vulnlib' && window.tonglingLibraries) window.tonglingLibraries.loadNucleiPanel();
    if (tab === 'im' && window.TonglingImBridge) window.TonglingImBridge.load();
    if (tab === 'nps' && window.tonglingNpsTunnel) window.tonglingNpsTunnel.refresh();
    if (tab === 'reports') loadReportsPanel();
    if (tab === 'files' && window.tonglingFiles) window.tonglingFiles.load();
  }

  function openMacAppWindow(tab) {
    if (!tab || tab === 'agent' || !TAB_META[tab] || !isTermFullscreen()) return;
    const stage = getMacDesktopStage();
    if (!stage) return;
    stage.hidden = false;

    if (macAppWindows[tab]) {
      focusMacAppWindow(tab);
      const st = macAppWindows[tab];
      if (st.iframe) loadMacAppFrame(st.iframe, tab);
      activateMacAppContent(tab);
      return;
    }

    const title = TAB_META[tab].title || tab;
    const idx = Object.keys(macAppWindows).length;
    const saved = macAppGeomStore[tab];
    const g = saved
      ? {
        left: saved.left,
        top: saved.top,
        width: saved.width,
        height: saved.height,
        z: ++macDeskZ,
      }
      : (tab === 'control'
        ? {
          left: 28,
          top: 28,
          width: Math.min(400, Math.max(320, window.innerWidth * 0.32)),
          height: Math.min(720, Math.max(420, window.innerHeight * 0.78)),
          z: ++macDeskZ,
        }
        : defaultMacAppGeom(idx));
    const win = document.createElement('div');
    win.className = 'mac-app-win active';
    win.dataset.appTab = tab;
    win.style.cssText = `left:${g.left}px;top:${g.top}px;width:${g.width}px;height:${g.height}px;z-index:${g.z}`;
    win.innerHTML = `
      <div class="mac-app-win-bar">
        <div class="mac-app-win-spacer"></div>
        <div class="mac-app-win-title">${escapeHtml(title)}</div>
        <div class="mac-traffic">
          <button type="button" class="mac-dot mac-min" data-act="min" title="最小化到程序栏"></button>
          <button type="button" class="mac-dot mac-max" data-act="max" title="铺满 / 还原"></button>
          <button type="button" class="mac-dot mac-close" data-act="close" title="关闭"></button>
        </div>
      </div>
      <div class="mac-app-win-body"></div>
    `;
    const body = win.querySelector('.mac-app-win-body');
    /** @type {HTMLElement|null} */
    let panel = null;
    /** @type {Comment|null} */
    let marker = null;
    /** @type {HTMLIFrameElement|null} */
    let iframe = null;

    const nativeId = MAC_NATIVE_PANELS[tab];
    if (nativeId) {
      panel = $(nativeId);
      if (panel && body) {
        marker = document.createComment(`mac-app-home:${tab}`);
        if (panel.parentNode) panel.parentNode.insertBefore(marker, panel);
        body.appendChild(panel);
        panel.classList.add('active');
        if (tab === 'control') {
          panel.classList.remove('desktop-only');
        }
      }
    } else if (resolveIframeRoute(tab) && body) {
      iframe = document.createElement('iframe');
      iframe.className = 'mac-app-frame';
      iframe.title = title;
      body.appendChild(iframe);
      loadMacAppFrame(iframe, tab);
    }

    stage.appendChild(win);
    macAppWindows[tab] = { el: win, panel, marker, iframe };
    setMacDesktopActiveWindow(win);
    bindMacAppWinDrag(win, tab);
    bindMacWinResize(win, {
      persist: () => scheduleSaveMacLayout(),
      onDone: () => scheduleSaveMacLayout(),
    });

    bindMacWinChromeControls(win, {
      onClose: () => closeMacAppWindow(tab),
      onMin: () => minimizeMacAppByTab(tab),
      onMax: () => {
        macAppMaxId = macAppMaxId === tab ? '' : tab;
        win.classList.toggle('maximized', macAppMaxId === tab);
        win.classList.remove('is-minimized');
        win.style.display = '';
        win.style.transform = '';
        focusMacAppWindow(tab);
        setTimeout(() => window.dispatchEvent(new Event('resize')), 40);
      },
    });
    // 捕获阶段：点标题栏/内容立刻置顶
    win.addEventListener('pointerdown', () => {
      focusMacAppWindow(tab);
    }, true);

    playMacWinEnter(win);
    activateMacAppContent(tab);
    syncMacDockActive(tab);
    scheduleSaveMacLayout();
  }

  function syncMacTermToggles() {
    const on = preferMacTermAuto();
    const a = $('toggle-mac-term');
    const b = $('toggle-mac-term-mobile');
    if (a) a.checked = on;
    if (b) b.checked = on;
  }

  function setMacTermAuto(on) {
    localStorage.setItem(LS_MAC_TERM, on ? '1' : '0');
    syncMacTermToggles();
    if (on && $('panel-agent')?.classList.contains('active')) {
      setTermFullscreen(true);
    }
  }

  function updateMacMenubarClock() {
    const el = $('mac-menubar-clock');
    if (!el) return;
    el.textContent = new Date().toLocaleString('zh-CN', {
      weekday: 'short',
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  }

  function setMacMetricLevel(el, pct) {
    if (!el) return;
    el.classList.remove('is-warn', 'is-hot');
    if (pct >= 90) el.classList.add('is-hot');
    else if (pct >= 75) el.classList.add('is-warn');
  }

  async function updateMacMenubarMetrics() {
    if (!isTermFullscreen() || macMetricsBusy) return;
    const cpuEl = $('mac-metric-cpu');
    const memEl = $('mac-metric-mem');
    const wrap = $('mac-menubar-metrics');
    if (!cpuEl || !memEl) return;
    macMetricsBusy = true;
    try {
      const r = await apiFetch('/tongling/api/host/metrics');
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d?.success) {
        cpuEl.innerHTML = '<span class="mac-metric-k">CPU</span> —';
        memEl.innerHTML = `<span class="mac-metric-k">${t('menubar.mem')}</span> —`;
        if (wrap) wrap.title = d?.error || '无法读取本机资源';
        return;
      }
      const cpu = Number(d.cpu_percent);
      const mem = Number(d.mem_percent);
      const cpuSafe = Number.isFinite(cpu) ? cpu : 0;
      const memSafe = Number.isFinite(mem) ? mem : 0;
      cpuEl.innerHTML = `<span class="mac-metric-k">CPU</span> ${cpuSafe.toFixed(0)}%`;
      const used = Number(d.mem_used_gb);
      const total = Number(d.mem_total_gb);
      const memDetail = Number.isFinite(used) && Number.isFinite(total)
        ? `${memSafe.toFixed(0)}% · ${used.toFixed(1)}/${total.toFixed(0)}G`
        : `${memSafe.toFixed(0)}%`;
      memEl.innerHTML = `<span class="mac-metric-k">${t('menubar.mem')}</span> ${memDetail}`;
      setMacMetricLevel(cpuEl, cpuSafe);
      setMacMetricLevel(memEl, memSafe);
      if (wrap) {
        wrap.title = `本机资源 · CPU ${cpuSafe.toFixed(1)}% · 内存 ${memSafe.toFixed(1)}%`
          + (Number.isFinite(used) && Number.isFinite(total) ? `（已用 ${used.toFixed(2)} / 共 ${total.toFixed(2)} GB）` : '');
      }
    } catch (e) {
      cpuEl.innerHTML = '<span class="mac-metric-k">CPU</span> —';
      memEl.innerHTML = `<span class="mac-metric-k">${t('menubar.mem')}</span> —`;
      if (wrap) wrap.title = '无法读取本机资源';
    } finally {
      macMetricsBusy = false;
    }
  }

  function startMacMenubarMetrics() {
    updateMacMenubarMetrics();
    // 首次后再取一次，避开 cpu_percent priming 为 0
    setTimeout(() => { if (isTermFullscreen()) updateMacMenubarMetrics(); }, 800);
    if (!macMetricsTimer) {
      macMetricsTimer = setInterval(updateMacMenubarMetrics, 2500);
    }
  }

  function stopMacMenubarMetrics() {
    if (macMetricsTimer) {
      clearInterval(macMetricsTimer);
      macMetricsTimer = 0;
    }
    macMetricsBusy = false;
  }

  function syncTermFullscreenButtons(on) {
    const desk = $('btn-term-fullscreen');
    const mob = $('m-btn-fullscreen');
    const menubar = $('mac-menubar');
    const dock = $('mac-dock');
    const wallpaper = $('mac-wallpaper-brand');
    if (desk) {
      desk.setAttribute('aria-pressed', on ? 'true' : 'false');
      desk.textContent = on ? '退出' : '工作台';
      desk.title = on ? '退出多窗口工作台（Esc）' : '多窗口工作台（Esc 退出）';
      desk.setAttribute('aria-label', on ? '退出多窗口工作台' : '多窗口工作台');
    }
    if (mob) {
      mob.classList.toggle('active', !!on);
      const label = mob.querySelector('span');
      if (label) label.textContent = on ? '退出' : '工作台';
      mob.title = on ? '退出多窗口工作台' : '多窗口工作台（Esc 退出）';
      mob.setAttribute('aria-label', on ? '退出多窗口工作台' : '多窗口工作台');
    }
    if (menubar) {
      menubar.hidden = !on;
      menubar.setAttribute('aria-hidden', on ? 'false' : 'true');
    }
    if (dock) {
      dock.hidden = !on;
      if (on) setMacDockOpen(preferMacDockOpen());
      else {
        closeMacWindowMenu();
        document.body.classList.remove('mac-dock-collapsed');
      }
    }
    if (wallpaper) {
      wallpaper.hidden = !on;
      wallpaper.setAttribute('aria-hidden', on ? 'false' : 'true');
    }
    if (!on) closeAllMacAppWindows();
    if (on) syncMacDockActive('agent');
  }

  function defaultMacGeom(index) {
    const width = Math.min(920, Math.max(480, window.innerWidth * 0.62));
    const height = Math.min(620, Math.max(320, window.innerHeight * 0.62));
    return {
      left: 36 + (index % 6) * 40,
      top: 28 + (index % 6) * 34,
      width,
      height,
      z: ++macDeskZ,
    };
  }

  function ensureMacGeom(sessionId, index) {
    if (!macWinGeom[sessionId]) {
      macWinGeom[sessionId] = defaultMacGeom(index ?? Object.keys(macWinGeom).length);
    }
    return macWinGeom[sessionId];
  }

  function findMacWin(sessionId) {
    if (!sessionId) return null;
    return macWinBySession[sessionId] || null;
  }

  function parkSessionHostsBeforeStageRebuild() {
    const stage = $('mac-term-stage');
    if (!stage) return;
    Object.values(sessionTerms).forEach((st) => {
      if (st?.host && stage.contains(st.host)) getTermPool().appendChild(st.host);
    });
  }

  function focusMacWindow(sessionId, { switchSession = true } = {}) {
    if (!sessionId || sessionId === '__empty__') return;
    const g = ensureMacGeom(sessionId);
    const wasMin = macTermMinimized.has(sessionId);
    macTermMinimized.delete(sessionId);
    const win = findMacWin(sessionId);
    if (win) {
      win.classList.remove('is-minimized');
      win.style.display = '';
      win.classList.toggle('maximized', macWinMaxId === sessionId);
      setMacDesktopActiveWindow(win);
      g.z = macDeskZ;
    } else {
      g.z = ++macDeskZ;
    }
    syncMacDockActive('agent');
    // remount 前先判定 host 是否还在窗口里（批量还原会先清掉 minimized 标记）
    const stPre = sessionTerms[sessionId];
    const bodyPre = win?.querySelector('.mac-term-win-body');
    const hostMissing = !!(stPre?.host && bodyPre && !bodyPre.contains(stPre.host));
    mountSessionTerminals();
    const needRefit = wasMin || hostMissing;
    if (!switchSession) {
      if (needRefit) fitTerminal(sessionId);
      return;
    }
    if (sessionId === activeSessionId) {
      if (needRefit) fitTerminal(sessionId);
      try { sessionTerms[sessionId]?.term?.focus(); } catch (e) { /* ignore */ }
      return;
    }
    switchToSession(sessionId);
  }

  function bindMacWinResize(win, { onDone, persist } = {}) {
    if (!win || win.dataset.macResizeBound === '1') return;
    win.dataset.macResizeBound = '1';

    let layer = win.querySelector('.mac-win-resizers');
    if (!layer) {
      layer = document.createElement('div');
      layer.className = 'mac-win-resizers';
      layer.innerHTML = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']
        .map((d) => `<div class="mac-win-resize mac-win-resize-${d}" data-dir="${d}"></div>`)
        .join('');
      win.appendChild(layer);
    }

    const MIN_W = 420;
    const MIN_H = 280;

    layer.addEventListener('pointerdown', (e) => {
      const handle = e.target.closest('[data-dir]');
      if (!handle || !isTermFullscreen()) return;
      if (e.button != null && e.button !== 0) return;
      if (win.classList.contains('maximized')) return;

      const dir = handle.getAttribute('data-dir') || '';
      const stage = getMacDesktopStage();
      const stageW = stage?.clientWidth || window.innerWidth;
      const stageH = stage?.clientHeight || window.innerHeight;

      let left = parseFloat(win.style.left) || 0;
      let top = parseFloat(win.style.top) || 0;
      let width = parseFloat(win.style.width) || win.offsetWidth;
      let height = parseFloat(win.style.height) || win.offsetHeight;
      const startX = e.clientX;
      const startY = e.clientY;
      const startLeft = left;
      const startTop = top;
      const startW = width;
      const startH = height;
      let raf = 0;

      win.classList.add('mac-resizing');
      document.body.classList.add('term-resizing');
      document.body.style.cursor = getComputedStyle(handle).cursor || 'nwse-resize';

      const flush = () => {
        raf = 0;
        win.style.left = `${left}px`;
        win.style.top = `${top}px`;
        win.style.width = `${width}px`;
        win.style.height = `${height}px`;
      };

      const onMove = (ev) => {
        const dx = ev.clientX - startX;
        const dy = ev.clientY - startY;
        let nextL = startLeft;
        let nextT = startTop;
        let nextW = startW;
        let nextH = startH;

        if (dir.includes('e')) {
          nextW = Math.min(stageW - startLeft, Math.max(MIN_W, startW + dx));
        }
        if (dir.includes('s')) {
          nextH = Math.min(stageH - startTop, Math.max(MIN_H, startH + dy));
        }
        if (dir.includes('w')) {
          const maxDx = startW - MIN_W;
          const clamped = Math.min(Math.max(dx, -startLeft), maxDx);
          nextL = startLeft + clamped;
          nextW = startW - clamped;
        }
        if (dir.includes('n')) {
          const maxDy = startH - MIN_H;
          const clamped = Math.min(Math.max(dy, -startTop), maxDy);
          nextT = startTop + clamped;
          nextH = startH - clamped;
        }

        left = nextL;
        top = nextT;
        width = nextW;
        height = nextH;
        if (!raf) raf = requestAnimationFrame(flush);
      };

      const onUp = () => {
        if (raf) cancelAnimationFrame(raf);
        flush();
        win.classList.remove('mac-resizing');
        document.body.classList.remove('term-resizing');
        document.body.style.cursor = '';
        window.removeEventListener('pointermove', onMove, true);
        window.removeEventListener('pointerup', onUp, true);
        window.removeEventListener('pointercancel', onUp, true);
        persist?.({ left, top, width, height });
        onDone?.();
      };

      window.addEventListener('pointermove', onMove, true);
      window.addEventListener('pointerup', onUp, true);
      window.addEventListener('pointercancel', onUp, true);
      try { handle.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
      e.preventDefault();
      e.stopPropagation();
    });
  }

  function bindMacWinChromeControls(win, {
    onClose,
    onMin,
    onMax,
  } = {}) {
    const traffic = win.querySelector('.mac-traffic');
    if (!traffic || traffic.dataset.chromeBound === '1') return;
    traffic.dataset.chromeBound = '1';

    // 阻止冒泡到标题栏拖动
    const stop = (e) => {
      e.stopPropagation();
      e.stopImmediatePropagation();
    };
    traffic.addEventListener('pointerdown', stop, true);
    traffic.addEventListener('mousedown', stop, true);

    traffic.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-act]');
      if (!btn || !traffic.contains(btn)) return;
      e.preventDefault();
      e.stopPropagation();
      const act = btn.getAttribute('data-act');
      if (act === 'close') onClose?.(e);
      else if (act === 'min') onMin?.(e);
      else if (act === 'max') onMax?.(e);
    }, true);
  }

  function setMacTermWinMaximized(win, sid, on) {
    const next = !!on;
    macWinMaxId = next ? sid : (macWinMaxId === sid ? '' : macWinMaxId);
    win.classList.toggle('maximized', next && macWinMaxId === sid);
    win.style.transform = '';
    if (next) {
      win.classList.remove('is-minimized');
      win.style.display = '';
    }
    if (sid) fitTerminal(sid);
  }

  function bindOneMacWinDrag(win) {
    const bar = win.querySelector('.mac-term-win-bar');
    const sid = win.getAttribute('data-session-id');
    if (!bar || !sid || bar.dataset.macDragBound === '1') return;
    bar.dataset.macDragBound = '1';

    bar.addEventListener('pointerdown', (e) => {
      if (!isTermFullscreen()) return;
      if (e.button != null && e.button !== 0) return;
      // 红绿灯区域绝不进入拖动
      if (e.target.closest('.mac-traffic, .mac-dot, button.mac-dot')) return;
      if (macWinMaxId === sid) {
        focusMacWindow(sid, { switchSession: true });
        return;
      }

      const g = ensureMacGeom(sid);
      // 先抬层，会话切换放到 pointerup，避免拖动卡顿
      setMacDesktopActiveWindow(win);
      g.z = macDeskZ;
      win.classList.add('mac-dragging');
      document.body.classList.add('term-dragging');

      const baseLeft = g.left;
      const baseTop = g.top;
      const startClientX = e.clientX;
      const startClientY = e.clientY;
      let pendingLeft = baseLeft;
      let pendingTop = baseTop;
      let moved = false;
      let raf = 0;

      macDragState = { sid, pointerId: e.pointerId };

      const stage = $('mac-term-stage');
      const flush = () => {
        raf = 0;
        const dx = pendingLeft - baseLeft;
        const dy = pendingTop - baseTop;
        win.style.transform = `translate3d(${dx}px,${dy}px,0)`;
      };

      const onMove = (ev) => {
        if (!macDragState || macDragState.sid !== sid) return;
        if (macDragState.pointerId != null && ev.pointerId !== macDragState.pointerId) return;
        if (Math.abs(ev.clientX - startClientX) + Math.abs(ev.clientY - startClientY) > 3) {
          moved = true;
        }
        const maxL = Math.max(0, (stage?.clientWidth || window.innerWidth) - 120);
        const maxT = Math.max(0, (stage?.clientHeight || window.innerHeight) - 48);
        pendingLeft = Math.min(Math.max(0, baseLeft + (ev.clientX - startClientX)), maxL);
        pendingTop = Math.min(Math.max(0, baseTop + (ev.clientY - startClientY)), maxT);
        if (!raf) raf = requestAnimationFrame(flush);
      };

      const onUp = (ev) => {
        if (!macDragState || macDragState.sid !== sid) return;
        if (macDragState.pointerId != null && ev.pointerId !== macDragState.pointerId) return;
        if (raf) cancelAnimationFrame(raf);
        g.left = pendingLeft;
        g.top = pendingTop;
        win.style.left = `${g.left}px`;
        win.style.top = `${g.top}px`;
        win.style.transform = '';
        win.classList.remove('mac-dragging');
        macDragState = null;
        document.body.classList.remove('term-dragging');
        window.removeEventListener('pointermove', onMove, true);
        window.removeEventListener('pointerup', onUp, true);
        window.removeEventListener('pointercancel', onUp, true);
        // 释放后再切会话，拖动过程不被 attach/清屏打断
        if (sid && sid !== '__empty__') focusMacWindow(sid, { switchSession: true });
        else setMacDesktopActiveWindow(win);
        scheduleSaveMacLayout();
      };

      window.addEventListener('pointermove', onMove, true);
      window.addEventListener('pointerup', onUp, true);
      window.addEventListener('pointercancel', onUp, true);
      try { bar.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
      e.preventDefault();
      e.stopPropagation();
    });

    bar.addEventListener('dblclick', (e) => {
      if (!isTermFullscreen()) return;
      if (e.target.closest('.mac-traffic, .mac-dot, button.mac-dot')) return;
      if (!sid || sid === '__empty__') return;
      e.preventDefault();
      const next = macWinMaxId !== sid;
      macTermMinimized.delete(sid);
      setMacTermWinMaximized(win, sid, next);
      focusMacWindow(sid, { switchSession: true });
    });
  }

  function bindMacTermWinOnce(win, sid) {
    if (!win || win.dataset.macBound === '1') return;
    win.dataset.macBound = '1';
    bindMacWinChromeControls(win, {
      onClose: () => {
        if (!sid || sid === '__empty__') {
          setTermFullscreen(false);
          return;
        }
        closeSession(sid);
      },
      onMin: () => {
        if (!sid || sid === '__empty__') return;
        minimizeMacTermWindow(sid, win);
      },
      onMax: () => {
        if (!sid || sid === '__empty__') return;
        const next = macWinMaxId !== sid;
        macTermMinimized.delete(sid);
        setMacTermWinMaximized(win, sid, next);
        focusMacWindow(sid, { switchSession: true });
      },
    });
    bindOneMacWinDrag(win);
    bindMacWinResize(win, {
      persist: (rect) => {
        if (!sid || sid === '__empty__') return;
        const g = ensureMacGeom(sid);
        g.left = rect.left;
        g.top = rect.top;
        g.width = rect.width;
        g.height = rect.height;
        scheduleSaveMacLayout();
      },
      onDone: () => {
        if (sid && sid !== '__empty__') fitTerminal(sid);
      },
    });
    playMacWinEnter(win);
    win.addEventListener('pointerdown', (e) => {
      if (e.target.closest('.mac-win-resize, .mac-traffic, .mac-dot')) {
        if (sid && sid !== '__empty__') {
          const g = ensureMacGeom(sid);
          setMacDesktopActiveWindow(win);
          g.z = macDeskZ;
        } else setMacDesktopActiveWindow(win);
        return;
      }
      if (sid && sid !== '__empty__') focusMacWindow(sid, { switchSession: true });
      else setMacDesktopActiveWindow(win);
    }, true);
  }

  function renderMacTermStage() {
    const stage = $('mac-term-stage');
    if (!stage) return;
    if (!isTermFullscreen()) {
      stage.hidden = true;
      mountSessionTerminals();
      return;
    }
    stage.hidden = false;

    const sessions = termSessions.length
      ? termSessions
      : [{ id: '__empty__', title: '终端' }];

    const keep = new Set(sessions.map((s) => s.id));
    Object.keys(macWinGeom).forEach((id) => {
      if (!keep.has(id)) delete macWinGeom[id];
    });
    if (macWinMaxId && !keep.has(macWinMaxId)) macWinMaxId = '';

    // 增量：只删多余窗，保留已有窗与 App 窗
    Object.keys(macWinBySession).forEach((id) => {
      if (keep.has(id)) return;
      const win = macWinBySession[id];
      const st = sessionTerms[id];
      if (st?.host && win?.contains(st.host)) getTermPool().appendChild(st.host);
      win?.remove();
      delete macWinBySession[id];
      if (macActiveWinEl === win) macActiveWinEl = null;
    });

    sessions.forEach((s, i) => {
      const g = ensureMacGeom(s.id, i);
      const title = s.id === '__empty__'
        ? '统领 · 终端'
        : (s.title || `终端 ${i + 1}`);
      const active = s.id === (activeSessionId || sessions[sessions.length - 1].id);
      let win = macWinBySession[s.id];
      if (!win) {
        win = document.createElement('div');
        win.className = 'mac-term-win';
        win.setAttribute('data-session-id', s.id);
        win.style.cssText = `left:${g.left}px;top:${g.top}px;width:${g.width}px;height:${g.height}px;z-index:${g.z}`;
        win.innerHTML = `
          <div class="mac-term-win-bar">
            <div class="mac-term-win-spacer"></div>
            <div class="mac-term-win-title">${escapeHtml(title)}</div>
            <div class="mac-traffic">
              <button type="button" class="mac-dot mac-min" data-act="min" title="最小化窗口" aria-label="最小化"></button>
              <button type="button" class="mac-dot mac-max" data-act="max" title="铺满 / 还原" aria-label="最大化"></button>
              <button type="button" class="mac-dot mac-close" data-act="close" title="关闭此终端" aria-label="关闭"></button>
            </div>
          </div>
          <div class="mac-term-win-body"></div>`;
        stage.appendChild(win);
        macWinBySession[s.id] = win;
        bindMacTermWinOnce(win, s.id);
        if (s.id === '__empty__') fillMacEmptyIdle(win);
      } else {
        const titleEl = win.querySelector('.mac-term-win-title');
        if (titleEl && titleEl.textContent !== title) titleEl.textContent = title;
        // 几何只在尚未有内联尺寸时回填（用户拖放过的不动）
        if (!win.style.width) {
          win.style.left = `${g.left}px`;
          win.style.top = `${g.top}px`;
          win.style.width = `${g.width}px`;
          win.style.height = `${g.height}px`;
          win.style.zIndex = String(g.z);
        }
      }
      win.classList.toggle('active', active);
      if (active) macActiveWinEl = win;
      win.classList.toggle('maximized', macWinMaxId === s.id);
      if (s.id !== '__empty__' && macTermMinimized.has(s.id)) {
        win.classList.add('is-minimized');
        win.style.display = 'none';
      } else {
        win.classList.remove('is-minimized');
        if (win.style.display === 'none') win.style.display = '';
      }
    });

    sessions.forEach((s) => {
      if (s.id === '__empty__') return;
      ensureSessionTerm(s.id);
    });
    mountSessionTerminals();
    if (activeSessionId) fitTerminal(activeSessionId);
    else fitTerminal();
  }

  function setTermFullscreen(on) {
    const next = !!on;
    document.body.classList.toggle('term-fs', next);
    syncTermFullscreenButtons(next);
    const stage = $('mac-term-stage');
    if (next) {
      // 保持 agent 桌面，避免 switchTab 递归进其它逻辑
      window.location.hash = '';
      document.querySelectorAll('.nav-item').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.tab === 'agent');
      });
      syncMacDockActive('agent');
      $('panel-agent')?.classList.add('active');
      closeControlSheet();
      if (typeof closeMoreSheet === 'function') closeMoreSheet();
      updateMacMenubarClock();
      if (!macClockTimer) {
        macClockTimer = setInterval(updateMacMenubarClock, 30000);
      }
      startMacMenubarMetrics();
      requestSubscribeAll();
      renderMacTermStage();
      showMacDesktopTip();
      window.tonglingAgentScanDock?.setAgentTabActive(true);
      window.tonglingAgentScanDock?.ready?.();
      // 默认打开控制面板（已打开则置顶）
      setTimeout(() => {
        if (isTermFullscreen()) openMacAppWindow('control');
      }, 60);
    } else {
      macWinMaxId = '';
      macTermMinimized.clear();
      closeMacWindowMenu();
      closeAllMacAppWindows();
      const tip = $('mac-desktop-tip');
      if (tip) tip.hidden = true;
      if (stage) {
        parkSessionHostsBeforeStageRebuild();
        stage.hidden = true;
        stage.innerHTML = '';
      }
      Object.keys(macWinBySession).forEach((k) => delete macWinBySession[k]);
      macActiveWinEl = null;
      mountSessionTerminals();
      if (macClockTimer) {
        clearInterval(macClockTimer);
        macClockTimer = 0;
      }
      stopMacMenubarMetrics();
      scheduleSaveMacLayout();
    }
    fitTerminal(activeSessionId || undefined);
  }

  function toggleTermFullscreen() {
    setTermFullscreen(!isTermFullscreen());
  }

  function scrollTermViewport(lines) {
    if (!term) return;
    const viewport = getTermViewport();
    if (viewport) {
      const linePx = (term.options.fontSize || 11) * (term.options.lineHeight || 1.15);
      viewport.scrollTop += lines * linePx;
      termStickBottom = isViewportAtBottom(viewport);
      return;
    }
    term.scrollLines(lines);
    syncTermStickBottom();
  }

  let wsStarted = false;
  let wsAbortClose = false;
  let wsConnecting = false;
  let autoAttachPromise = null;
  let wsUrlIndex = 0;
  let wsUrlsQueue = [];
  /** @type {'auto'|'start'|'attach'} */
  let wsConnectMode = 'auto';
  /** 用户点了「新建终端」，禁止 autoAttach 抢连 */
  let userStartLocked = false;
  /** WS ready 后需立即 start（避免 ready 被 auto 模式消费） */
  let pendingStartRequest = false;
  /** 已发出 start、等待 started 消息 */
  let launchingNewSession = false;
  const LS_ACTIVE_SESSION = 'tongling-active-session';
  /** @type {{ id: string, title: string, cwd?: string }[]} */
  let termSessions = [];
  let activeSessionId = null;
  let pendingAttachSessionId = null;

  function renderTermTabs() {
    const el = $('term-tabs-list');
    const bar = $('term-tabs-bar');
    if (!el) return;
    if (bar) bar.style.display = termSessions.length ? 'flex' : 'none';
    el.innerHTML = termSessions.map((s) => `
      <div class="term-tab${s.id === activeSessionId ? ' active' : ''}" data-session-id="${escapeHtml(s.id)}">
        <button type="button" class="term-tab-btn">${escapeHtml(s.title)}</button>
        <button type="button" class="term-tab-close" aria-label="关闭">×</button>
      </div>
    `).join('');
    el.querySelectorAll('.term-tab').forEach((tab) => {
      const sid = tab.getAttribute('data-session-id');
      tab.querySelector('.term-tab-btn')?.addEventListener('click', () => switchToSession(sid));
      tab.querySelector('.term-tab-close')?.addEventListener('click', (e) => {
        e.stopPropagation();
        closeSession(sid);
      });
    });
    // 悬浮桌面：集合未变只刷标题/active，避免每次切会话都走全量同步
    if (isTermFullscreen()) {
      const stageIds = Object.keys(macWinBySession).filter((id) => id !== '__empty__').sort().join('\0');
      const sessIds = termSessions.map((s) => s.id).sort().join('\0');
      const needEmpty = !termSessions.length;
      const hasEmpty = !!macWinBySession.__empty__;
      if (stageIds !== sessIds || needEmpty !== hasEmpty) renderMacTermStage();
      else {
        Object.keys(macWinBySession).forEach((id) => {
          const win = macWinBySession[id];
          if (!win) return;
          const on = id === activeSessionId;
          win.classList.toggle('active', on);
          if (on) macActiveWinEl = win;
          const s = termSessions.find((x) => x.id === id);
          if (!s) return;
          const titleEl = win.querySelector('.mac-term-win-title');
          const title = s.title || id;
          if (titleEl && titleEl.textContent !== title) titleEl.textContent = title;
        });
      }
    }
  }

  function persistActiveSession() {
    if (activeSessionId) localStorage.setItem(LS_ACTIVE_SESSION, activeSessionId);
  }

  function pickAttachSession(sessions) {
    if (!sessions?.length) return null;
    const preferred = localStorage.getItem(LS_ACTIVE_SESSION);
    if (preferred && sessions.some((s) => s.id === preferred)) return preferred;
    return sessions[sessions.length - 1].id;
  }

  function syncSessionsFromServer(sessions) {
    const nextIds = new Set();
    termSessions = (sessions || []).map((s) => {
      if (s.id && s.claude_session_id) {
        claudeSessionByTerm[s.id] = s.claude_session_id;
      }
      if (s.id) {
        nextIds.add(s.id);
        ensureSessionTerm(s.id);
      }
      return {
        id: s.id,
        title: s.title || s.id,
        cwd: s.cwd,
      };
    });
    Object.keys(sessionTerms).forEach((id) => {
      if (!nextIds.has(id)) disposeSessionTerm(id);
    });
    renderTermTabs();
    mountSessionTerminals();
    if (activeSessionId) syncScanDockForActiveTerminal();
  }

  function switchToSession(sessionId) {
    if (!sessionId || sessionId === activeSessionId) return;
    flushTermOutput();
    activeSessionId = sessionId;
    persistActiveSession();
    loadTokenStatsForSession(sessionId);
    syncScanDockForActiveTerminal();
    ensureSessionTerm(sessionId);
    syncActiveTermPointers();
    const st = sessionTerms[sessionId];
    if (st) {
      st.stickBottom = true;
      termStickBottom = true;
    }
    macTermMinimized.delete(sessionId);
    mountSessionTerminals();
    renderTermTabs();
    if (ws && ws.readyState === WebSocket.OPEN) {
      if (subscribedSessions.has(sessionId)) {
        wsStarted = true;
        wsConnecting = false;
        setTermStatus('运行中');
        try { st?.term?.focus(); } catch (e) { /* ignore */ }
        fitTerminal(sessionId);
        return;
      }
      wsConnecting = true;
      sendWsAttach(sessionId);
    } else {
      pendingAttachSessionId = sessionId;
      connectTerminal('attach');
    }
  }

  function onSessionRemoved(sessionId, serverSessions) {
    delete claudeSessionByTerm[sessionId];
    macTermMinimized.delete(sessionId);
    if (macWinMaxId === sessionId) macWinMaxId = '';
    disposeSessionTerm(sessionId);
    if (serverSessions) syncSessionsFromServer(serverSessions);
    else {
      termSessions = termSessions.filter((s) => s.id !== sessionId);
      renderTermTabs();
      mountSessionTerminals();
    }
    if (activeSessionId === sessionId) {
      activeSessionId = termSessions.length ? termSessions[termSessions.length - 1].id : null;
      persistActiveSession();
      loadTokenStatsForSession(activeSessionId);
      syncScanDockForActiveTerminal();
      syncActiveTermPointers();
      if (activeSessionId && ws?.readyState === WebSocket.OPEN) {
        if (subscribedSessions.has(activeSessionId)) {
          wsStarted = true;
          wsConnecting = false;
          setTermStatus('运行中');
          try { sessionTerms[activeSessionId]?.term?.focus(); } catch (e) { /* ignore */ }
        } else {
          wsStarted = false;
          wsConnecting = true;
          sendWsAttach(activeSessionId);
        }
      } else {
        wsConnecting = false;
        setTermStatus(termSessions.length ? t('status.selectTerm') : t('status.disconnected'));
        stopLiveClaudeDiscover();
        bindScanDockToLiveClaude('', '');
      }
    }
    updateTermButtons();
  }

  function closeSession(sessionId) {
    if (!sessionId) return;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'stop', session_id: sessionId }));
    } else {
      onSessionRemoved(sessionId, null);
    }
  }

  function sendWsStart() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const extras = getLaunchPayloadExtras();
    const isResume = extras.launch_mode === 'resume' && extras.resume_id;
    setTermStatus(isResume ? '正在恢复历史会话…' : '正在启动 Claude…');
    launchingNewSession = true;
    activeSessionId = null;
    stopLiveClaudeDiscover();
    if (isResume && extras.resume_id) {
      bindScanDockToLiveClaude(extras.resume_id, '');
    } else {
      bindScanDockToLiveClaude('', '');
    }
    resetSessionBillingBaseline();
    // 勿清已有会话的 xterm；用引导终端显示启动提示
    term = null;
    fitAddon = null;
    initTerminal();
    if (term) {
      term.clear();
      writeTermOutput(
        '\r\n\x1b[90m[启动] 正在启动 Claude Code'
        + (isResume ? '（恢复会话）' : '')
        + '，首次可能从 npm 镜像下载（'
        + (config.npm_registry || 'https://registry.npmmirror.com')
        + '）…\x1b[0m\r\n'
      );
    }
    const payload = {
      type: 'start',
      cols: term?.cols || 120,
      rows: term?.rows || 40,
      proxy: getProxy(),
      initial_prompt: getPrompt(),
      workdir: config.claude_workdir,
    };
    if (pendingScanMeta) {
      payload.scan_target = pendingScanMeta.target;
      payload.report_path = pendingScanMeta.report_path;
      payload.scenario = pendingScanMeta.scenario;
      if (pendingScanMeta.initial_prompt) payload.initial_prompt = pendingScanMeta.initial_prompt;
    }
    const model = getCliModel();
    if (model) payload.model = model;
    Object.assign(payload, extras);
    ws.send(JSON.stringify(payload));
    pendingScanMeta = null;
  }

  function sendWsAttach(sessionId) {
    const sid = sessionId || activeSessionId;
    if (!sid || !ws || ws.readyState !== WebSocket.OPEN) return;
    activeSessionId = sid;
    persistActiveSession();
    ensureSessionTerm(sid);
    syncActiveTermPointers();
    mountSessionTerminals();
    renderTermTabs();
    setTermStatus('正在恢复会话…');
    const t = sessionTerms[sid]?.term;
    ws.send(JSON.stringify({
      type: 'attach',
      session_id: sid,
      cols: t?.cols || 120,
      rows: t?.rows || 40,
    }));
  }

  function handleWsReady(msg) {
    syncSessionsFromServer(msg.sessions);
    if (wsConnectMode === 'start' || pendingStartRequest) {
      pendingStartRequest = false;
      sendWsStart();
      return;
    }
    if (wsConnectMode === 'attach' || wsConnectMode === 'auto') {
      const sid = pendingAttachSessionId
        || activeSessionId
        || pickAttachSession(msg.sessions);
      pendingAttachSessionId = null;
      if (sid && msg.sessions?.some((s) => s.id === sid)) {
        sendWsAttach(sid);
        return;
      }
    }
    wsConnecting = false;
    setTermStatus(termSessions.length ? t('status.selectTerm') : t('status.disconnected'));
    updateTermButtons();
    if (termSessions.length) requestSubscribeAll();
  }

  function onTerminalSessionActive(msg) {
    wsStarted = true;
    wsConnecting = false;
    launchingNewSession = false;
    pendingStartRequest = false;
    if (msg.session_id) {
      activeSessionId = msg.session_id;
      subscribedSessions.add(msg.session_id);
      ensureSessionTerm(msg.session_id);
      persistActiveSession();
      loadTokenStatsForSession(activeSessionId);
      syncActiveTermPointers();
    }
    if (msg.sessions) syncSessionsFromServer(msg.sessions);
    else if (msg.session_id && !termSessions.some((s) => s.id === msg.session_id)) {
      termSessions.push({
        id: msg.session_id,
        title: msg.title || msg.session_id,
        cwd: msg.cwd,
      });
      renderTermTabs();
    }
    mountSessionTerminals();
    requestSubscribeAll();

    const fromMsg = (msg.claude_session_id || '').trim();
    const fromPending = (pendingLiveClaudeSessionId || '').trim();
    const fromMap = activeSessionId ? (claudeSessionByTerm[activeSessionId] || '') : '';
    const claudeSid = fromMsg || fromPending || fromMap;
    pendingLiveClaudeSessionId = '';
    if (claudeSid) {
      bindScanDockToLiveClaude(claudeSid, activeSessionId);
      highlightClaudeSession(claudeSid);
      stopLiveClaudeDiscover();
    } else {
      // 新建终端：不要立刻绑旧历史；轮询新建时间后出现的 Claude 会话文件
      bindScanDockToLiveClaude('', activeSessionId);
      scheduleLiveClaudeDiscover(Date.now());
    }

    setTermStatus('运行中');
    if (msg.audit_id) {
      activeAuditId = msg.audit_id;
      setSideHint(`Claude 已启动 · 审计 ${msg.audit_id}`, 'ok');
      loadAudits();
    } else {
      setSideHint(msg.reattach ? '已恢复 Claude 会话' : 'Claude 已启动', 'ok');
    }
    fitTerminal(activeSessionId || undefined);
    updateTermButtons();
  }

  function closeWs() {
    wsAbortClose = true;
    if (ws) {
      try { ws.close(); } catch (e) { /* ignore */ }
      ws = null;
    }
    wsAbortClose = false;
    wsStarted = false;
    wsConnecting = false;
    updateTermButtons();
  }

  function connectWsAttempt() {
    if (!wsUrlsQueue.length || wsUrlIndex >= wsUrlsQueue.length) {
      wsConnecting = false;
      setTermStatus('WebSocket 失败');
      const tried = wsUrlsQueue.join(' → ');
      const hint = wsPortHint(config);
      const errMsg = `无法连接终端 WebSocket。已尝试: ${tried || '无'}. ${hint}`;
      setSideHint(errMsg, 'err');
      initTerminal();
      if (term) {
        term.clear();
        writeTermOutput(
          '\r\n\x1b[31m[终端] WebSocket 连接失败。\x1b[0m\r\n'
          + '\x1b[33m请确认：1) 服务已启动  2) Token 有效（刷新页面或从桌面重新打开）\x1b[0m\r\n'
          + `\x1b[90m${errMsg}\x1b[0m\r\n`
        );
      }
      updateTermButtons();
      return;
    }

    const wsUrl = wsUrlsQueue[wsUrlIndex];
    const n = wsUrlIndex + 1;
    setTermStatus(
      n === 1 ? '连接 WebSocket…' : `备用连接 ${n}/${wsUrlsQueue.length}…`
    );
    $('btn-term-start') && ($('btn-term-start').disabled = true);
    $('m-btn-start') && ($('m-btn-start').disabled = true);

    let opened = false;
    let readyHandled = false;
    // 新连接允许重新应用 scrollback，并清空服务端订阅缓存标记
    subscribedSessions.clear();
    Object.values(sessionTerms).forEach((st) => {
      if (st) st.replayApplied = false;
    });

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      opened = true;
      setTermStatus('连接 WebSocket…');
      fitTerminal();
      updateTermButtons();
    };

    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (e) { queueTermOutput(ev.data); return; }

      if (msg.type === 'ready') {
        if (!readyHandled) {
          readyHandled = true;
          handleWsReady(msg);
        }
        return;
      }
      if (msg.type === 'replay') {
        const sid = msg.session_id;
        if (!sid || !msg.data) return;
        subscribedSessions.add(sid);
        const st = ensureSessionTerm(sid);
        // 同一会话的完整 scrollback 只应用一次，防止内容叠成两份
        if (st?.replayApplied) return;
        if (st) {
          try { st.term.clear(); } catch (e) { /* ignore */ }
          st.outputBuf = '';
          if (st.outputTimer) {
            clearTimeout(st.outputTimer);
            st.outputTimer = 0;
          }
          st.replayApplied = true;
        }
        mountSessionTerminals();
        queueTermOutputFor(sid, msg.data);
        return;
      }
      if (msg.type === 'output') {
        const sid = msg.session_id || activeSessionId;
        if (sid) {
          subscribedSessions.add(sid);
          ensureSessionTerm(sid);
        }
        queueTermOutputFor(sid, msg.data || '');
        return;
      }
      if (msg.type === 'started' || msg.type === 'attached') {
        onTerminalSessionActive(msg);
        return;
      }
      if (msg.type === 'sessions') {
        syncSessionsFromServer(msg.sessions);
        return;
      }
      if (msg.type === 'error') {
        wsConnecting = false;
        launchingNewSession = false;
        pendingStartRequest = false;
        setTermStatus('错误');
        setSideHint(msg.message || '操作失败', 'err');
        if (wsConnectMode === 'start') {
          flushTermOutput();
          writeTermOutput('\r\n\x1b[31m[错误] ' + (msg.message || '') + '\x1b[0m\r\n');
        }
        if (wsConnectMode !== 'auto') closeWs();
        else updateTermButtons();
        return;
      }
      if (msg.type === 'exit' || msg.type === 'stopped') {
        onSessionRemoved(msg.session_id, msg.sessions);
        loadAudits();
        if (msg.audit_id) {
          setSideHint(`终端已结束 · 审计已归档 ${msg.audit_id}`, 'ok');
        }
        if (!termSessions.length) setTermStatus(t('status.disconnected'));
        else if (wsStarted && activeSessionId) setTermStatus('运行中');
        return;
      }
    };

    ws.onerror = () => {
      if (!wsStarted && !opened) {
        ws = null;
      }
    };

    ws.onclose = () => {
      if (wsAbortClose) return;
      if (wsStarted) {
        ws = null;
        wsStarted = false;
        wsConnecting = false;
        updateTermButtons();
        return;
      }
      ws = null;
      if (!opened || (opened && !wsStarted)) {
        wsUrlIndex += 1;
        setTimeout(connectWsAttempt, 120);
        return;
      }
      wsConnecting = false;
      updateTermButtons();
    };
  }

  function connectTerminal(mode) {
    if (wsConnecting && mode !== 'start') return;
    if (mode !== 'start' && ws && ws.readyState === WebSocket.OPEN && wsStarted) return;
    if (mode !== 'start' && ws && ws.readyState === WebSocket.CONNECTING) return;

    wsConnectMode = mode || 'auto';

    if (mode === 'start') {
      if (ws?.readyState === WebSocket.OPEN) {
        sendWsStart();
        return;
      }
      if (ws?.readyState === WebSocket.CONNECTING) {
        setTermStatus('连接 WebSocket…');
        return;
      }
    }

    if (mode === 'auto' && ws && ws.readyState === WebSocket.OPEN && !wsStarted) {
      const sid = pendingAttachSessionId || activeSessionId || pickAttachSession(termSessions);
      if (sid) {
        wsConnecting = true;
        sendWsAttach(sid);
        return;
      }
    }

    wsUrlsQueue = resolveWsUrls(config || {});
    if (!wsUrlsQueue.length) {
      setTermStatus('缺少 WebSocket 地址');
      return;
    }
    initTerminal();
    fitTerminal();
    if (mode === 'start') {
      if (ws) closeWs();
    } else if (!ws || ws.readyState === WebSocket.CLOSED) {
      closeWs();
    }
    wsUrlIndex = 0;
    wsStarted = false;
    wsConnecting = true;
    connectWsAttempt();
  }

  async function connectAndStart(options = {}) {
    userStartLocked = true;
    pendingStartRequest = true;
    if (options.fresh) wsStartResumeId = null;

    if (!config || config.success === false) {
      setTermStatus('加载配置…');
      try { await loadConfig(); } catch (e) { /* ignore */ }
    }

    initTerminal();
    fitTerminal();
    wsConnectMode = 'start';
    if (term) term.focus();

    if (ws?.readyState === WebSocket.OPEN) {
      pendingStartRequest = false;
      sendWsStart();
      return;
    }
    if (ws?.readyState === WebSocket.CONNECTING) {
      setTermStatus('连接 WebSocket…');
      return;
    }
    connectTerminal('start');
  }

  async function maybeAutoAttach() {
    if (userStartLocked) return;
    if (!config?.pty_available) return;
    if (wsConnecting) return;
    if (ws && ws.readyState === WebSocket.OPEN && wsStarted) return;
    if (ws && ws.readyState === WebSocket.CONNECTING) return;
    if (autoAttachPromise) return autoAttachPromise;

    autoAttachPromise = (async () => {
      try {
        const r = await apiFetch('/tongling/api/terminal/status');
        const d = await r.json();
        const sessions = d.sessions || [];
        if (!sessions.length && !d.active) return;
        syncSessionsFromServer(sessions);
        pendingAttachSessionId = pickAttachSession(sessions);
        if (ws && ws.readyState === WebSocket.OPEN && wsStarted) return;
        if (wsConnecting || userStartLocked) return;
        connectTerminal('auto');
      } catch (e) { /* ignore */ }
      finally {
        autoAttachPromise = null;
      }
    })();
    return autoAttachPromise;
  }

  function stopTerminal() {
    if (activeSessionId) closeSession(activeSessionId);
  }

  function clearTerminal() {
    if (term) term.clear();
    if (ws?.readyState === WebSocket.OPEN && activeSessionId) {
      ws.send(JSON.stringify({ type: 'input', session_id: activeSessionId, data: '\x0c' }));
    }
  }

  function formatToolStats(stats) {
    if (!stats || !stats.catalog_total) {
      return 'HexStrike 工具：服务端未就绪或未加载目录';
    }
    const reg = stats.hexstrike_registry_total || '—';
    const inst = stats.installed_count ?? '—';
    return `注册表 ${reg} 个 · 统领目录 ${stats.catalog_total} 个（已安装 ${inst}）`;
  }

  function renderToolStats(stats) {
    const text = formatToolStats(stats);
    const el = $('mcp-tool-stats');
    if (el) el.textContent = text;
  }

  function renderMcpPanel(d) {
    const badge = $('mcp-hexstrike-badge');
    if (badge) {
      if (d.hexstrike_configured && d.hexstrike_enabled) {
        badge.textContent = '已导入';
        badge.className = 'mcp-badge ok';
      } else if (d.hexstrike_configured) {
        badge.textContent = '已禁用';
        badge.className = 'mcp-badge warn';
      } else {
        badge.textContent = '未导入';
        badge.className = 'mcp-badge';
      }
    }

    const statusEl = $('mcp-hexstrike-status');
    if (statusEl) {
      if (!d.workdir_exists) {
        statusEl.textContent = `Claude 工作目录不存在：${d.workdir || '—'}（请先安装 AI 智能体资源包）`;
        statusEl.className = 'cp-tip mcp-status-err';
      } else if (!d.hexstrike_healthy) {
        statusEl.textContent = `HexStrike 未就绪：${d.hexstrike_message || '请先在桌面启动 HexStrike Server'}`;
        statusEl.className = 'cp-tip mcp-status-err';
      } else if (!d.pending_payload?.command) {
        statusEl.textContent = '未找到 Python311 或 hexstrike_mcp.py，无法生成 MCP 配置';
        statusEl.className = 'cp-tip mcp-status-err';
      } else {
        statusEl.textContent = `HexStrike 在线 · 工作目录就绪 · 可一键导入 MCP`;
        statusEl.className = 'cp-tip mcp-status-ok';
      }
    }

    const nameLine = $('mcp-server-name-line');
    if (nameLine) {
      nameLine.textContent = d.mcp_server_name
        ? `MCP 服务名：${d.mcp_server_name}`
        : '';
    }

    renderToolStats(d.tool_stats || {});

    const preview = $('mcp-hexstrike-preview');
    if (preview) {
      if (d.mcp_server_name && d.pending_payload?.command) {
        preview.textContent = JSON.stringify(
          { mcpServers: { [d.mcp_server_name]: d.pending_payload } },
          null,
          2,
        );
      } else {
        preview.textContent = '（无法生成 HexStrike MCP 配置，请检查 HexStrike 与 Python311 环境）';
      }
    }

    const current = $('mcp-json-current');
    if (current) {
      const servers = d.mcp_servers || {};
      current.textContent = Object.keys(servers).length
        ? JSON.stringify({ mcpServers: servers }, null, 2)
        : '（尚未写入 .mcp.json）';
    }

    const canImport = !!(d.workdir_exists && d.hexstrike_healthy && d.pending_payload?.command);
    const label = d.hexstrike_configured ? '重新导入 HexStrike MCP' : '一键导入 HexStrike MCP';
    ['btn-mcp-hexstrike', 'btn-mcp-hexstrike-mobile'].forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.disabled = !canImport;
      el.textContent = label;
    });

    if (d.burp_mcp) applyBurpMcpPrefs(null, d.burp_mcp);
  }

  async function loadMcpPanel() {
    try {
      const r = await apiFetch('/tongling/api/mcp/status');
      const d = await r.json();
      if (!r.ok || d.success === false) {
        setMcpHint(d.error || `加载失败 (HTTP ${r.status})`, 'err');
        return;
      }
      renderMcpPanel(d);
    } catch (e) {
      setMcpHint(String(e), 'err');
    }
  }

  async function connectHexstrikeMcp() {
    setMcpHint('正在一键导入 HexStrike MCP…');
    ['btn-mcp-hexstrike', 'btn-mcp-hexstrike-mobile'].forEach((id) => {
      const el = $(id);
      if (el) el.disabled = true;
    });
    try {
      const r = await apiFetch('/tongling/api/mcp/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: 'full' }),
      });
      const d = await r.json();
      if (d.tool_stats) renderToolStats(d.tool_stats);
      setMcpHint(
        d.success ? (d.detail || 'HexStrike MCP 已导入到 .mcp.json') : (d.error || '导入失败'),
        d.success ? 'ok' : 'err',
      );
      await loadMcpPanel();
    } catch (e) {
      setMcpHint(String(e), 'err');
      await loadMcpPanel();
    }
  }

  async function connectBurpMcp() {
    if (!$('chk-burp-mcp')?.checked) {
      setMcpHint('请先勾选「启用 Burp MCP 集成」', 'err');
      return;
    }
    persistBurpMcpPrefs();
    setMcpHint('正在导入 Burp MCP…');
    const btn = $('btn-mcp-burp');
    if (btn) btn.disabled = true;
    try {
      const r = await apiFetch('/tongling/api/mcp/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile: 'full',
          burp: getBurpMcpPayload(),
        }),
      });
      const d = await r.json();
      if (d.burp_mcp) applyBurpMcpPrefs(getBurpMcpPayload(), d.burp_mcp);
      setMcpHint(
        d.success ? (d.detail || 'Burp MCP 已导入') : (d.error || '导入失败'),
        d.success ? 'ok' : 'err',
      );
      await loadMcpPanel();
    } catch (e) {
      setMcpHint(String(e), 'err');
      await loadMcpPanel();
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function connectMcp() {
    return connectHexstrikeMcp();
  }

  function loadedSkillItemHtml(sk) {
    const name = escapeHtml(sk.name || '');
    const display = escapeHtml(sk.display_name || sk.name || '');
    const pack = sk.pack ? `<span class="skill-pack">${escapeHtml(sk.pack)}</span>` : '';
    const subtitle = sk.display_name && sk.display_name !== sk.name
      ? `<span class="skills-loaded-source">${display}</span>`
      : (sk.source_name && sk.source_name !== sk.name
        ? `<span class="skills-loaded-source">${escapeHtml(sk.source_name)}</span>`
        : '');
    return `
      <div class="skills-loaded-item" data-loaded-name="${name}">
        <div class="skills-loaded-main">
          <span class="skills-loaded-slash">/${name}</span>
          ${pack}
          ${subtitle}
        </div>
        <button type="button" class="btn btn-ghost btn-sm skills-loaded-remove" data-loaded-name="${name}" title="移除">移除</button>
      </div>`;
  }

  function renderLoadedSkills(target) {
    const isModal = target === 'modal';
    const listEl = isModal ? $('modal-skills-loaded-list') : $('skills-loaded-list');
    const countEl = isModal ? $('modal-skills-loaded-count') : $('skills-loaded-count');
    const items = skillState.loadedSkills || [];

    if (!listEl) return;

    if (skillState.loadedLoading) {
      listEl.innerHTML = '<div class="skill-empty skills-loaded-empty">加载中…</div>';
      if (countEl) countEl.textContent = '—';
      return;
    }

    if (!items.length) {
      listEl.innerHTML = '<div class="skill-empty skills-loaded-empty">暂无已加载 Skill，请在下方勾选并导入</div>';
    } else {
      listEl.innerHTML = items.map(loadedSkillItemHtml).join('');
    }

    if (countEl) countEl.textContent = `${items.length} 个`;

    listEl.querySelectorAll('.skills-loaded-remove').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const n = btn.getAttribute('data-loaded-name');
        if (n) removeLoadedSkills([n], target);
      });
    });
  }

  async function loadLoadedSkills(target) {
    const t = target || 'page';
    skillState.loadedLoading = true;
    renderLoadedSkills(t);
    try {
      const r = await apiFetch('/tongling/api/skills/loaded');
      const d = await r.json();
      if (!d.success) {
        skillState.loadedSkills = [];
        const listEl = t === 'modal' ? $('modal-skills-loaded-list') : $('skills-loaded-list');
        if (listEl) {
          listEl.innerHTML = `<div class="skill-empty skills-loaded-empty err">${escapeHtml(d.error || '加载失败')}</div>`;
        }
        return;
      }
      skillState.loadedSkills = d.loaded || [];
    } catch (e) {
      skillState.loadedSkills = [];
      const listEl = t === 'modal' ? $('modal-skills-loaded-list') : $('skills-loaded-list');
      if (listEl) {
        listEl.innerHTML = `<div class="skill-empty skills-loaded-empty err">${escapeHtml(String(e))}</div>`;
      }
    } finally {
      skillState.loadedLoading = false;
      renderLoadedSkills(t);
      if (t === 'page') renderLoadedSkills('modal');
    }
  }

  async function removeLoadedSkills(names, target) {
    const list = (names || []).filter(Boolean);
    if (!list.length) return;
    const label = list.length === 1 ? `/${list[0]}` : `${list.length} 个 Skill`;
    if (!window.confirm(`确定从 Claude 工作区移除 ${label}？\n移除后需重启终端才能完全生效。`)) return;

    const resultEl = target === 'modal' ? $('side-status') : $('skills-sync-result');
    setHint(resultEl, '正在移除…');
    try {
      const r = await apiFetch('/tongling/api/skills/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ names: list }),
      });
      const d = await r.json();
      if (!d.success) {
        setHint(resultEl, d.error || '移除失败', 'err');
        return;
      }
      list.forEach((name) => {
        const loaded = skillState.loadedSkills.find((x) => x.name === name);
        if (loaded?.catalog_id) skillState.checkedIds.delete(loaded.catalog_id);
      });
      updateSkillCounts();
      renderSkillList(target === 'modal' ? 'modal' : 'page');
      await loadLoadedSkills(target === 'modal' ? 'modal' : 'page');
      const msg = `已移除 ${d.count} 个 Skill`;
      if (resultEl?.id === 'side-status') setSideHint(msg, 'ok');
      else setHint(resultEl, msg, 'ok');
    } catch (e) {
      setHint(resultEl, String(e), 'err');
    }
  }

  async function ensureSkillsLoaded() {
    if (skillState.skills.length) return;
    const r = await apiFetch('/tongling/api/skills');
    const d = await r.json();
    skillState.skills = d.skills || [];
    skillState.packs = d.packs || [];
    skillState.recommendedIds = new Set(d.recommended_ids || []);
    fillPackSelect('skills-pack-filter', skillState.packs);
    fillPackSelect('modal-pack-filter', skillState.packs);
  }

  function fillPackSelect(selectId, packs) {
    const sel = $(selectId);
    if (!sel || sel.options.length) return;
    sel.innerHTML = '<option value="">全部技能包</option>' +
      packs.map((p) => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`).join('');
  }

  function skillsForPack(packFilter) {
    const fp = (packFilter || '').trim().toLowerCase();
    if (!fp) return skillState.skills;
    return skillState.skills.filter((s) => (s.pack || '').toLowerCase() === fp);
  }

  function skillItemHtml(sk, checked) {
    const id = escapeHtml(sk.id);
    const pack = escapeHtml(sk.pack || '—');
    return `
      <div class="skill-item">
        <input type="checkbox" data-skill-id="${id}" ${checked ? 'checked' : ''} />
        <label>
          <span class="skill-name">${escapeHtml(sk.name || sk.id)}</span>
          <span class="skill-pack">${pack}</span>
          <span class="skill-path">${escapeHtml(sk.path || '')}</span>
        </label>
      </div>`;
  }

  function renderSkillList(target) {
    const isModal = target === 'modal';
    const listEl = isModal ? $('modal-skill-list') : $('skill-list');
    const countEl = isModal ? $('modal-skills-count') : $('skills-count');
    const packFilter = isModal
      ? ($('modal-pack-filter')?.value || '')
      : ($('skills-pack-filter')?.value || '');

    const items = skillsForPack(packFilter);
    if (!items.length) {
      listEl.innerHTML = '<div class="skill-empty">当前筛选下没有 Skill</div>';
    } else {
      listEl.innerHTML = items.map((sk) =>
        skillItemHtml(sk, skillState.checkedIds.has(sk.id))
      ).join('');
    }

    bindSkillCheckboxes(listEl);
    const n = skillState.checkedIds.size;
    if (countEl) countEl.textContent = `已勾选 ${n} 个 Skill`;
  }

  function bindSkillCheckboxes(container) {
    container.querySelectorAll('input[data-skill-id]').forEach((cb) => {
      cb.addEventListener('change', () => {
        const id = cb.getAttribute('data-skill-id');
        if (cb.checked) skillState.checkedIds.add(id);
        else skillState.checkedIds.delete(id);
        updateSkillCounts();
      });
      const label = cb.nextElementSibling;
      if (label) {
        label.addEventListener('click', (e) => {
          if (e.target.tagName !== 'INPUT') {
            cb.checked = !cb.checked;
            cb.dispatchEvent(new Event('change'));
          }
        });
      }
    });
  }

  function updateSkillCounts() {
    const n = skillState.checkedIds.size;
    const t = `已勾选 ${n} 个 Skill`;
    if ($('skills-count')) $('skills-count').textContent = t;
    if ($('modal-skills-count')) $('modal-skills-count').textContent = t;
  }

  function setAllSkills(checked, target) {
    const packFilter = target === 'modal'
      ? ($('modal-pack-filter')?.value || '')
      : ($('skills-pack-filter')?.value || '');
    skillsForPack(packFilter).forEach((sk) => {
      if (checked) skillState.checkedIds.add(sk.id);
      else skillState.checkedIds.delete(sk.id);
    });
    renderSkillList(target);
  }

  function applyRecommended(target) {
    if (!skillState.recommendedIds.size) {
      alert('未找到匹配的推荐技能，请手动勾选。');
      return;
    }
    const packFilter = target === 'modal'
      ? ($('modal-pack-filter')?.value || '')
      : ($('skills-pack-filter')?.value || '');
    skillsForPack(packFilter).forEach((sk) => {
      if (skillState.recommendedIds.has(sk.id)) skillState.checkedIds.add(sk.id);
      else skillState.checkedIds.delete(sk.id);
    });
    renderSkillList(target);
  }

  async function syncSelectedSkills(resultEl) {
    const ids = [...skillState.checkedIds];
    if (!ids.length) {
      setHint(resultEl, '请至少勾选一个 Skill', 'err');
      return false;
    }
    setHint(resultEl, '正在同步…');
    try {
      const r = await apiFetch('/tongling/api/skills/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skill_ids: ids }),
      });
      const d = await r.json();
      if (d.success) {
        const msg = `已导入 ${d.count} 个 Skills 到 Claude 工作区`;
        if (resultEl?.id === 'side-status') setSideHint(msg, 'ok');
        else setHint(resultEl, msg, 'ok');
        await loadLoadedSkills(resultEl?.id === 'side-status' ? 'modal' : 'page');
        return true;
      }
      setHint(resultEl, d.error || '同步失败', 'err');
      return false;
    } catch (e) {
      setHint(resultEl, String(e), 'err');
      return false;
    }
  }

  function openSkillsModal() {
    closeControlSheet();
    ensureSkillsLoaded().then(() => {
      renderSkillList('modal');
      loadLoadedSkills('modal');
      $('skills-modal').classList.remove('hidden');
      $('skills-modal').setAttribute('aria-hidden', 'false');
    });
  }

  function closeSkillsModal() {
    $('skills-modal').classList.add('hidden');
    $('skills-modal').setAttribute('aria-hidden', 'true');
  }

  /* ── Events ── */
  document.querySelectorAll('.nav-item').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
  document.querySelectorAll('[data-tasks-view]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const view = btn.getAttribute('data-tasks-view') || 'monitor';
      if (view === tasksIframeView) return;
      setTasksIframeView(view);
    });
  });
  $('btn-page-crumb-back')?.addEventListener('click', () => switchTab('agent'));

  document.querySelectorAll('.m-tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      if (tab === 'more') openMoreSheet();
      else switchTab(tab);
    });
  });

  document.querySelectorAll('.more-tile').forEach((btn) => {
    btn.addEventListener('click', () => {
      closeMoreSheet();
      switchTab(btn.dataset.tab);
    });
  });

  window.addEventListener('hashchange', () => switchTab(tabFromPath()));

  linkInputs('input-proxy', 'input-proxy-sheet');
  linkInputs('input-prompt', 'input-prompt-sheet');
  linkInputs('input-prompt-target', 'input-prompt-target-sheet');
  linkSelects('select-prompt', 'select-prompt-sheet');
  $('chk-burp-mcp')?.addEventListener('change', () => {
    updateBurpMcpUi();
    persistBurpMcpPrefs();
  });
  ['input-burp-sse', 'input-burp-jar', 'input-burp-java'].forEach((id) => {
    $(id)?.addEventListener('input', persistBurpMcpPrefs);
  });
  linkSelects('select-provider', 'select-provider-sheet');
  linkSelects('select-cli-model', 'select-cli-model-sheet');

  $('btn-claude-sessions-refresh')?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    loadClaudeSessions();
  });
  $('btn-claude-sessions-refresh-sheet')?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    loadClaudeSessions();
  });

  $('btn-audit-refresh')?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    loadAudits();
  });
  $('btn-audit-refresh-sheet')?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    loadAudits();
  });

  $('btn-provider-apply')?.addEventListener('click', () => applyProvider());
  $('btn-provider-apply-sheet')?.addEventListener('click', () => applyProvider());
  $('btn-provider-config')?.addEventListener('click', () => openProviderModal('config'));
  $('btn-provider-config-sheet')?.addEventListener('click', () => openProviderModal('config'));
  $('btn-provider-add')?.addEventListener('click', () => openProviderModal('add'));
  $('btn-provider-add-sheet')?.addEventListener('click', () => openProviderModal('add'));
  $('btn-provider-import')?.addEventListener('click', importProviderFromSettings);
  $('btn-provider-import-sheet')?.addEventListener('click', importProviderFromSettings);
  $('btn-provider-test')?.addEventListener('click', () => testProviderKey(false));
  $('btn-provider-test-sheet')?.addEventListener('click', () => testProviderKey(false));
  $('provider-modal-test')?.addEventListener('click', () => testProviderKey(true));
  $('provider-modal-close')?.addEventListener('click', closeProviderModal);
  $('provider-modal-cancel')?.addEventListener('click', closeProviderModal);
  $('provider-modal-save')?.addEventListener('click', () => saveProvider(false));
  $('provider-modal-save-apply')?.addEventListener('click', () => saveProvider(true));
  $('provider-modal-delete')?.addEventListener('click', deleteProviderFromModal);
  $('provider-modal')?.addEventListener('click', (e) => {
    if (e.target === $('provider-modal')) closeProviderModal();
  });
  $('select-cli-model')?.addEventListener('change', persistCliModelPreference);
  $('select-cli-model-sheet')?.addEventListener('change', persistCliModelPreference);

  restoreCliModelPreference();

  $('btn-term-start')?.addEventListener('click', () => connectAndStart({ fresh: true }));
  $('btn-term-new')?.addEventListener('click', () => connectAndStart({ fresh: true }));
  $('m-btn-start')?.addEventListener('click', () => connectAndStart({ fresh: true }));
  $('btn-term-stop')?.addEventListener('click', stopTerminal);
  $('m-btn-stop')?.addEventListener('click', stopTerminal);
  $('btn-term-clear')?.addEventListener('click', clearTerminal);
  $('btn-term-banner-provider')?.addEventListener('click', openProviderGuideFromBanner);
  $('btn-term-banner-import')?.addEventListener('click', () => {
    hideAnthropicConnectBanner();
    importProviderFromSettings();
  });
  $('btn-term-banner-close')?.addEventListener('click', () => hideAnthropicConnectBanner());
  $('btn-term-banner-dismiss')?.addEventListener('click', () => dismissAnthropicConnectBanner(true));
  $('btn-mac-banner-provider')?.addEventListener('click', openProviderGuideFromBanner);
  $('btn-mac-banner-import')?.addEventListener('click', () => {
    hideAnthropicConnectBanner();
    importProviderFromSettings();
  });
  $('btn-mac-banner-close')?.addEventListener('click', () => hideAnthropicConnectBanner());
  $('btn-mac-banner-dismiss')?.addEventListener('click', () => dismissAnthropicConnectBanner(true));
  const onLangToggle = () => window.tonglingI18n?.toggleLocale?.();
  $('btn-lang-toggle')?.addEventListener('click', onLangToggle);
  $('btn-lang-toggle-mobile')?.addEventListener('click', onLangToggle);
  $('btn-mac-lang')?.addEventListener('click', onLangToggle);
  window.addEventListener('tongling:locale', () => {
    rebuildTabMeta();
    window.tonglingI18n?.applyDom?.();
    try {
      const tab = document.querySelector('.nav-item.active')?.getAttribute('data-tab')
        || document.querySelector('.mac-dock-item.is-front')?.getAttribute('data-tab')
        || 'agent';
      updatePageCrumb(tab);
      updateMobileChrome(tab);
      syncMacMenubarAppName();
      Object.keys(macAppWindows || {}).forEach((id) => {
        const win = macAppWindows[id]?.el;
        const titleEl = win?.querySelector('.mac-app-win-title');
        if (titleEl && TAB_META[id]) titleEl.textContent = TAB_META[id].title;
      });
    } catch (e) { /* ignore */ }
  });
  $('btn-token-reset')?.addEventListener('click', resetTokenStatsForActiveSession);
  $('btn-token-reset-sheet')?.addEventListener('click', resetTokenStatsForActiveSession);
  $('btn-token-reset-billing')?.addEventListener('click', () => {
    if (confirm('确定清零累计 Token 用量？此操作不可恢复。')) resetBillingTotals();
  });
  $('btn-token-reset-billing-sheet')?.addEventListener('click', () => {
    if (confirm('确定清零累计 Token 用量？此操作不可恢复。')) resetBillingTotals();
  });
  $('btn-panel-toggle')?.addEventListener('click', toggleSidePanel);
  $('btn-term-fullscreen')?.addEventListener('click', toggleTermFullscreen);
  $('m-btn-fullscreen')?.addEventListener('click', toggleTermFullscreen);
  $('btn-mac-close')?.addEventListener('click', () => setTermFullscreen(false));
  $('btn-mac-min')?.addEventListener('click', () => setTermFullscreen(false));
  $('btn-mac-max')?.addEventListener('click', () => {
    if (!activeSessionId) return;
    macWinMaxId = macWinMaxId === activeSessionId ? '' : activeSessionId;
    if (isTermFullscreen()) renderMacTermStage();
    setTimeout(fitTerminal, 60);
  });
  $('btn-mac-term-new')?.addEventListener('click', () => connectAndStart({ fresh: true }));
  $('btn-mac-term-exit')?.addEventListener('click', () => setTermFullscreen(false));
  $('btn-mac-apple')?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeMacWindowMenu();
    const panel = $('mac-menu-apple-panel');
    const btn = $('btn-mac-apple');
    if (!panel || !btn) return;
    const open = panel.hidden;
    panel.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  const PROJECT_REPO_URL = 'https://github.com/CuriousLearnerDev/Online_Tools-AI';

  function openAboutModal() {
    const el = $('about-modal');
    if (!el) {
      setSideHint(`统领 TongLing · ${PROJECT_REPO_URL}`, 'ok');
      return;
    }
    el.classList.remove('hidden');
    el.setAttribute('aria-hidden', 'false');
    window.tonglingI18n?.applyDom?.();
  }

  function closeAboutModal() {
    const el = $('about-modal');
    if (!el) return;
    el.classList.add('hidden');
    el.setAttribute('aria-hidden', 'true');
  }

  async function copyProjectRepoUrl() {
    try {
      await navigator.clipboard.writeText(PROJECT_REPO_URL);
      setSideHint(t('about.copied'), 'ok');
    } catch (e) {
      setSideHint(PROJECT_REPO_URL, 'ok');
    }
  }

  $('btn-mac-apple-about')?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeMacAppleMenu();
    openAboutModal();
  });
  $('about-modal-close')?.addEventListener('click', closeAboutModal);
  $('about-modal-ok')?.addEventListener('click', closeAboutModal);
  $('about-modal-copy')?.addEventListener('click', () => {
    copyProjectRepoUrl();
  });
  $('about-modal')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeAboutModal();
  });
  $('btn-mac-apple-control')?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeMacAppleMenu();
    if (isTermFullscreen()) openMacAppWindow('control');
  });
  $('btn-mac-apple-files')?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeMacAppleMenu();
    if (isTermFullscreen()) openMacAppWindow('files');
    else switchTab('files');
  });
  $('btn-mac-apple-dock')?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeMacAppleMenu();
    toggleMacDock();
  });
  $('btn-mac-apple-exit')?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeMacAppleMenu();
    setTermFullscreen(false);
  });
  $('btn-mac-menu-programs')?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeAllMacMenus();
    toggleMacDock();
  });
  $('btn-mac-menu-window')?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeMacAppleMenu();
    const panel = $('mac-menu-window-panel');
    const btn = $('btn-mac-menu-window');
    if (!panel || !btn) return;
    const open = panel.hidden;
    if (open) refreshMacWindowMenu();
    panel.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  $('mac-menu-win-list')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-mac-win-kind]');
    if (!btn) return;
    e.stopPropagation();
    closeAllMacMenus();
    activateMacWindowMenuItem(
      btn.getAttribute('data-mac-win-kind'),
      btn.getAttribute('data-mac-win-id'),
    );
  });
  $('btn-mac-win-new')?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeAllMacMenus();
    connectAndStart({ fresh: true });
  });
  $('btn-mac-win-cycle')?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeAllMacMenus();
    cycleMacDesktopWindows();
  });
  $('btn-mac-win-exit')?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeAllMacMenus();
    setTermFullscreen(false);
  });
  $('mac-dock-inner')?.addEventListener('click', (e) => {
    const item = e.target.closest('.mac-dock-item[data-tab]');
    if (!item) return;
    e.preventDefault();
    const tab = item.getAttribute('data-tab');
    if (!tab) return;

    // App：已最小化则还原；已前置则再点藏窗；否则置顶
    if (tab !== 'agent' && macAppWindows[tab]) {
      const el = macAppWindows[tab].el;
      if (el.style.display === 'none' || el.classList.contains('is-minimized')) {
        el.classList.remove('is-minimized');
        el.style.display = '';
        focusMacAppWindow(tab);
        playMacWinEnter(el);
        return;
      }
      const front = getFrontMacDesktopWindow();
      if (front === el) {
        minimizeMacAppByTab(tab);
        return;
      }
      focusMacAppWindow(tab);
      return;
    }

    // 智能体：前置终端再点 → 最小化；否则还原/聚焦
    if (tab === 'agent') {
      const front = getFrontMacDesktopWindow();
      if (front?.classList.contains('mac-term-win')) {
        const sid = front.getAttribute('data-session-id');
        if (sid && sid !== '__empty__' && !macTermMinimized.has(sid)) {
          minimizeMacTermWindow(sid, front);
          return;
        }
      }
    }

    switchTab(tab);
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest?.('#mac-menu-window-wrap') && !e.target.closest?.('#mac-menu-apple-wrap')) {
      closeAllMacMenus();
    }
  });
  $('btn-mac-tip-dismiss')?.addEventListener('click', dismissMacDesktopTip);
  const onMacPrefChange = (e) => setMacTermAuto(!!e.target.checked);
  $('toggle-mac-term')?.addEventListener('change', onMacPrefChange);
  $('toggle-mac-term-mobile')?.addEventListener('change', onMacPrefChange);
  syncMacTermToggles();
  loadMacLayout();
  setMacDockOpen(preferMacDockOpen());
  $('m-btn-clear')?.addEventListener('click', clearTerminal);
  $('m-header-controls')?.addEventListener('click', openControlSheet);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !$('about-modal')?.classList.contains('hidden')) {
      e.preventDefault();
      closeAboutModal();
      return;
    }
    if (e.key === 'Escape' && isTermFullscreen()) {
      e.preventDefault();
      handleMacDesktopEscape();
      return;
    }
    // Ctrl+Shift+F：切换终端全屏（避免与浏览器查找冲突过多时仍可用）
    if (e.ctrlKey && e.shiftKey && (e.key === 'F' || e.key === 'f') && $('panel-agent')?.classList.contains('active')) {
      e.preventDefault();
      toggleTermFullscreen();
    }
    if (!isTermFullscreen() || !e.ctrlKey || e.altKey) return;
    const typing = isMacTypingTarget(e.target);

    // Ctrl+N：悬浮桌面新建终端（输入框里不抢）
    if (!e.shiftKey && (e.key === 'n' || e.key === 'N')) {
      if (typing) return;
      e.preventDefault();
      connectAndStart({ fresh: true });
      return;
    }
    // Ctrl+W：关闭前置窗（终端内不抢，避免与 shell 冲突）
    if (!e.shiftKey && (e.key === 'w' || e.key === 'W')) {
      if (typing) return;
      e.preventDefault();
      const front = getFrontMacDesktopWindow();
      if (!front) return;
      if (front.classList.contains('mac-app-win') && front.dataset.appTab) {
        closeMacAppWindow(front.dataset.appTab);
        return;
      }
      const sid = front.getAttribute('data-session-id');
      if (!sid || sid === '__empty__') setTermFullscreen(false);
      else closeSession(sid);
      return;
    }
    // Ctrl+M：最小化前置窗
    if (!e.shiftKey && (e.key === 'm' || e.key === 'M')) {
      if (typing) return;
      e.preventDefault();
      const front = getFrontMacDesktopWindow();
      if (!front) return;
      if (front.classList.contains('mac-app-win') && front.dataset.appTab) {
        minimizeMacAppByTab(front.dataset.appTab);
        return;
      }
      const sid = front.getAttribute('data-session-id');
      if (sid && sid !== '__empty__') minimizeMacTermWindow(sid, front);
      return;
    }
    // Ctrl+`：循环窗口（终端内也可用）
    if (!e.shiftKey && (e.key === '`' || e.code === 'Backquote')) {
      if (e.target?.tagName === 'INPUT' || e.target?.tagName === 'TEXTAREA') return;
      e.preventDefault();
      cycleMacDesktopWindows();
    }
  });

  $('m-btn-keys-toggle')?.addEventListener('click', () => {
    const bar = $('mobile-agent-bar');
    const btn = $('m-btn-keys-toggle');
    if (!bar) return;
    const open = bar.classList.toggle('term-keys-open');
    if (btn) btn.classList.toggle('active', open);
    setTimeout(fitTerminal, 80);
  });

  initMobileTermKeys();

  $('btn-mcp-hexstrike')?.addEventListener('click', connectHexstrikeMcp);
  $('btn-mcp-hexstrike-mobile')?.addEventListener('click', connectHexstrikeMcp);
  $('btn-mcp-burp')?.addEventListener('click', connectBurpMcp);
  $('btn-skills-open')?.addEventListener('click', openSkillsModal);
  $('btn-skills-open-sheet')?.addEventListener('click', openSkillsModal);

  $('control-sheet-close')?.addEventListener('click', closeControlSheet);
  $('control-backdrop')?.addEventListener('click', closeControlSheet);
  $('more-sheet-close')?.addEventListener('click', closeMoreSheet);
  $('more-backdrop')?.addEventListener('click', closeMoreSheet);

  initWebTheme();
  initReportOutlineResizer();
  $('theme-select')?.addEventListener('change', (e) => onThemeSelectChange(e.target.value));
  $('theme-select-mobile')?.addEventListener('change', (e) => onThemeSelectChange(e.target.value));
  $('reports-select')?.addEventListener('change', (e) => {
    loadReportPreview(e.target.value || '');
  });

  $('btn-report-export')?.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleReportExportMenu();
  });
  $('reports-export-menu')?.addEventListener('click', (e) => {
    const item = e.target.closest('[data-export-fmt]');
    if (!item) return;
    const fmt = item.getAttribute('data-export-fmt');
    if (fmt === 'md') exportReportAsMd();
    else if (fmt === 'pdf') exportReportAsPdf();
  });
  document.addEventListener('click', (e) => {
    const wrap = $('reports-export-wrap');
    if (!wrap || wrap.hidden) return;
    if (!wrap.contains(e.target)) closeReportExportMenu();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeReportExportMenu();
  });

  $('skills-pack-filter')?.addEventListener('change', () => renderSkillList('page'));
  $('modal-pack-filter')?.addEventListener('change', () => renderSkillList('modal'));

  $('btn-skills-rec')?.addEventListener('click', () => applyRecommended('page'));
  $('btn-skills-all')?.addEventListener('click', () => setAllSkills(true, 'page'));
  $('btn-skills-none')?.addEventListener('click', () => setAllSkills(false, 'page'));
  $('btn-skills-sync')?.addEventListener('click', () => syncSelectedSkills($('skills-sync-result')));
  $('btn-skills-loaded-refresh')?.addEventListener('click', () => loadLoadedSkills('page'));

  $('modal-skills-rec')?.addEventListener('click', () => applyRecommended('modal'));
  $('modal-skills-all')?.addEventListener('click', () => setAllSkills(true, 'modal'));
  $('modal-skills-none')?.addEventListener('click', () => setAllSkills(false, 'modal'));
  $('skills-modal-close')?.addEventListener('click', closeSkillsModal);
  $('skills-modal-cancel')?.addEventListener('click', closeSkillsModal);
  $('skills-modal-confirm')?.addEventListener('click', async () => {
    const ok = await syncSelectedSkills($('side-status'));
    if (ok) closeSkillsModal();
  });

  $('skills-modal')?.addEventListener('click', (e) => {
    if (e.target === $('skills-modal')) closeSkillsModal();
  });

  loadConfig()
    .then(() => {
      setupHexStrikeFrame($('hs-frame'));
      switchTab(tabFromPath());
      initTerminal();
      setTermStatus(t('status.disconnected'));
      loadTokenStatsForSession(localStorage.getItem(LS_ACTIVE_SESSION));
      updateTokenStatsUI();
      ensureSkillsLoaded();
      if (!providerState.providers.length) loadProviders();
      if (window.tonglingPrompts) window.tonglingPrompts.load(true);
    })
    .catch((e) => setGlobalStatus('无法加载: ' + e, false));

  window.tonglingApiFetch = apiFetch;
  window.tonglingSwitchTab = switchTab;
  window.tonglingResumeClaudeSession = resumeClaudeSession;
  window.tonglingOpenScanViz = openScanVizFromApp;
})();
