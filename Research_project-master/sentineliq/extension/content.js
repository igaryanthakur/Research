/**
 * SentinelIQ — Content Script
 * Hover pre-caching | Pre-click interception | 3-level email escalation | Inline link badges
 */

'use strict';

// ── Self-page guard ───────────────────────────────────────────────────────────
// Never scan the extension's own pages (blocked.html, popup, etc.) or our own project domains.
// If we do, the popup shows PENDING and background may re-trigger a block loop.
(() => {
if (location.href.startsWith('chrome-extension://') || location.protocol === 'chrome-extension:' || location.hostname.includes('indianext') || location.hostname.includes('sentineliq') || location.hostname.includes('render.com')) {
  // Halt content script execution for all extension pages and project dashboards
  console.info('[SentinelIQ] Skipping scan on own extension page or project domain.');
  return;
}

const DEBOUNCE_MS = 250;
let scanned = new Map();   // url → result (in-tab cache)
let activeTooltip = null;
let formWarned = false;

const AI_HOSTS = new Set(['chatgpt.com', 'claude.ai', 'gemini.google.com', 'perplexity.ai']);
const isAiInterface = (() => {
  try { return AI_HOSTS.has(location.hostname.replace('www.', '')); } catch (err) { return false; }
})();
const monitoredInputs = new WeakSet();

// ── Context Invalidation Guard ───────────────────────────────────────────────
// Prevent "Extension context invalidated" errors when the extension updates
// but this old content script is still running in an unrefreshed tab.
const _originalSendMessage = chrome.runtime.sendMessage.bind(chrome.runtime);
chrome.runtime.sendMessage = function(message, callback) {
  if (!chrome.runtime?.id) {
    console.warn('[SentinelIQ] Extension context invalidated. Please refresh the page.');
    if (callback) callback(null);
    return;
  }
  try {
    let p;
    if (callback) {
      p = _originalSendMessage(message, (resp) => {
        if (chrome.runtime.lastError) { /* ignore to suppress console error */ }
        callback(resp);
      });
    } else {
      p = _originalSendMessage(message);
    }
    if (p && typeof p.catch === 'function') p.catch(() => {});
    return p;
  } catch (err) {
    if (callback) callback(null);
  }
};

// ── Helpers ───────────────────────────────────────────────────────────────────
function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
function absUrl(href) {
  try { return new URL(href, location.href).href; } catch (err) { return null; }
}
function isLocalUrl(url) {
  try { const h = new URL(url).hostname; return h === 'localhost' || h.startsWith('127.') || h.startsWith('192.168.'); } catch (err) {} return false;
}

// ── Scan via background (with in-tab cache) ───────────────────────────────────
function scanUrl(url) {
  return new Promise(resolve => {
    if (scanned.has(url)) { resolve(scanned.get(url)); return; }
    try {
      if (typeof chrome === 'undefined' || !chrome?.runtime?.sendMessage) {
        resolve({ verdict: 'ERROR', shap_features: [], explanation: 'Extension reloaded. Please refresh the page.', risk_score: 0 });
        return;
      }
      chrome.runtime.sendMessage({ type: 'SCAN_URL', url }, resp => {
        if (chrome?.runtime?.lastError) {
          console.warn('[SentinelIQ] Extension context invalidated (reload page).', chrome.runtime.lastError.message);
          resolve({ verdict: 'ERROR', shap_features: [], explanation: 'Extension reloaded. Please refresh the page.', risk_score: 0 });
          return;
        }
        const r = resp?.result || { verdict: 'ERROR', shap_features: [], explanation: 'Scan failed.', action: '', risk_score: 0 };
        scanned.set(url, r);
        resolve(r);
      });
    } catch (err) {
      console.warn('[SentinelIQ] Cannot send message, context invalidated. Please refresh the page.', err);
      resolve({ verdict: 'ERROR', shap_features: [], explanation: 'Extension reloaded. Please refresh the page.', risk_score: 0 });
    }
  });
}

// ── Pre-click interception: intercept click if verdict already cached MALICIOUS ──
// This fires BEFORE navigation — zero latency because verdict was pre-cached on hover.
document.addEventListener('click', e => {
  const a = e.target.closest('a[href]');
  if (!a) return;
  const url = absUrl(a.href);
  if (!url || isLocalUrl(url) || /^(mailto|tel|javascript|#)/.test(a.href)) return;
  const cached = scanned.get(url);
  if (cached && cached.verdict === 'MALICIOUS' && (cached.risk_score || 0) >= 65) {
    e.preventDefault();
    e.stopImmediatePropagation();
    // Redirect to blocked page with threat context
    const params = new URLSearchParams({
      url:         url,
      verdict:     cached.verdict,
      risk:        String(cached.risk_score || 0),
      explanation: cached.explanation || 'Malicious URL detected.',
      action:      cached.action || 'Do not proceed.',
      signals:     JSON.stringify((cached.shap_features || []).slice(0, 3).map(f => f.feature)),
    });
    window.location.href = chrome.runtime.getURL('blocked.html') + '?' + params.toString();
  }
}, true); // capture phase — fires before page handlers

// ── Tooltip ───────────────────────────────────────────────────────────────────
function removeTooltip() {
  if (activeTooltip) { activeTooltip.remove(); activeTooltip = null; }
}

function showTooltip(anchor, result) {
  removeTooltip();
  const v = (result.verdict || 'ERROR').toUpperCase();
  const score = result.risk_score || 0;
  const signals = (result.shap_features || []).slice(0, 4);
  const colorMap = { MALICIOUS: '#ef4444', SUSPICIOUS: '#f59e0b', BENIGN: '#10b981', ERROR: '#6b7280' };
  const color = colorMap[v] || '#6b7280';
  const iconMap = { MALICIOUS: '🛡', SUSPICIOUS: '⚠', BENIGN: '✓', ERROR: '?' };

  const tip = document.createElement('div');
  tip.setAttribute('data-siq', 'tooltip');
  tip.style.cssText = `
    position:fixed;z-index:2147483647;width:310px;border-radius:14px;overflow:hidden;
    background:#0f172a;border:1px solid ${color}44;
    box-shadow:0 24px 48px #00000088,0 0 0 1px ${color}22;
    font-family:-apple-system,system-ui,sans-serif;font-size:12px;
    pointer-events:none;animation:siq-in .15s ease;
  `;

  const signalsHtml = signals.map(s => {
    const pct = Math.round((s.weight || 0) * 100);
    return `<div style="display:flex;align-items:center;gap:8px;margin-bottom:5px" title="Feature Attribution Score">
      <span style="flex:0 0 130px;color:#94a3b8;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.feature||''}</span>
      <div style="flex:1;height:4px;background:#1e293b;border-radius:2px;overflow:hidden">
        <div style="width:${pct}%;height:100%;background:linear-gradient(90deg,#6366f1,#a78bfa);border-radius:2px"></div>
      </div>
      <span style="color:#64748b;font-size:10px;flex:0 0 28px;text-align:right">${pct}%</span>
    </div>`;
  }).join('');

  tip.innerHTML = `
    <div style="background:linear-gradient(135deg,${color}33,${color}11);border-bottom:1px solid ${color}33;padding:11px 14px;display:flex;justify-content:space-between;align-items:center">
      <span style="color:${color};font-weight:700;font-size:13px;display:flex;align-items:center;gap:6px">
        <span>${iconMap[v]||'?'}</span><span>${v}</span>
      </span>
      <span style="background:${color}22;color:${color};font-size:11px;font-weight:600;padding:2px 8px;border-radius:99px">Risk ${score}/100</span>
    </div>
    <div style="padding:12px 14px">
      <p style="color:#cbd5e1;line-height:1.55;margin:0 0 10px;font-size:12px">${result.explanation||'No details available.'}</p>
      ${signals.length ? `<div style="margin-bottom:10px">${signalsHtml}</div>` : ''}
      ${result.action ? `<div style="color:#818cf8;font-size:11px;border-top:1px solid #1e293b;padding-top:8px;font-style:italic">${result.action}</div>` : ''}
    </div>
  `;

  document.body.appendChild(tip);
  activeTooltip = tip;

  // Position below anchor, stay within viewport
  const rect = anchor.getBoundingClientRect();
  let left = rect.left;
  let top  = rect.bottom + 6;
  if (left + 310 > window.innerWidth) left = window.innerWidth - 318;
  if (left < 4) left = 4;
  if (top + 200 > window.innerHeight) top = rect.top - 210;
  tip.style.left = left + 'px';
  tip.style.top  = top  + 'px';
}

// ── Inline badge on links (all verdicts shown in email context) ───────────────
function injectBadge(anchor, verdict, score, emailContext) {
  if (anchor.querySelector('[data-siq-badge]')) return;
  const b = document.createElement('span');
  b.setAttribute('data-siq-badge', verdict);
  const cfg = {
    MALICIOUS:  { bg: '#ef4444', text: `🛡 ${score}` },
    SUSPICIOUS: { bg: '#f59e0b', text: `⚠ ${score}` },
    BENIGN:     { bg: emailContext ? '#10b981' : 'transparent', text: emailContext ? `✓` : '' },
    BYPASSED:   { bg: 'transparent', text: '' },
    ERROR:      { bg: '#6b7280', text: '?' },
  };
  const c = cfg[verdict] || cfg.ERROR;
  if (!c.text) return; // don't show badge for non-email BENIGN
  b.style.cssText = `
    display:inline-flex;align-items:center;gap:2px;font-size:9px;padding:1px 5px;
    border-radius:4px;margin-left:4px;font-weight:700;vertical-align:middle;
    background:${c.bg};color:#fff;font-family:-apple-system,system-ui,sans-serif;
    pointer-events:none;line-height:1.4;
  `;
  b.textContent = c.text;
  b.title = `SentinelIQ: ${verdict} (Risk ${score})`;
  anchor.appendChild(b);
}

// ── Hover scanning + pre-caching ─────────────────────────────────────────────
// Pre-caches verdicts on hover so click interception is instant (zero latency).
const onHover = debounce(async (anchor, url) => {
  const r = await scanUrl(url);
  injectBadge(anchor, r.verdict, r.risk_score || 0, false);
  if (r.verdict !== 'BENIGN' && r.verdict !== 'BYPASSED') showTooltip(anchor, r);
}, DEBOUNCE_MS);

// Silent pre-cache on first mouseover (no debounce — fires immediately to build cache)
document.addEventListener('mouseover', e => {
  const a = e.target.closest('a[href]');
  if (!a) return;
  const url = absUrl(a.href);
  if (!url || /^(javascript|mailto|tel|#)/.test(url) || isLocalUrl(url)) return;
  if (!scanned.has(url)) scanUrl(url); // fire and forget — just builds cache
  onHover(a, url);
}, { passive: true });

document.addEventListener('mouseout', e => {
  if (e.target.closest('a[href]')) removeTooltip();
}, { passive: true });

// ── Password form detection ───────────────────────────────────────────────────
function warnIfPasswordPage() {
  if (formWarned || !document.querySelector('input[type="password"]')) return;
  formWarned = true;
  
  // Extract full DOM content for content-based phishing detection
  const content = [
    `Title: ${document.title}`,
    `URL: ${location.href}`,
    `[PASSWORD FORM PRESENT]`,
    document.querySelector('h1,h2,h3')?.textContent || '',
    document.body?.innerText?.substring(0, 1500) || ''
  ].join('\n');

  // Send DOM content for phishing analysis instead of just URL
  chrome.runtime.sendMessage({ type: 'SCAN_CONTENT', content, url: location.href }, resp => {
    const r = resp?.result;
    if (!r || r.verdict === 'BENIGN' || r.verdict === 'ERROR') return;
    showPageBanner(r);
  });
}

function showPageBanner(result) {
  if (document.querySelector('[data-siq-banner]')) return;
  const v     = result.verdict || 'SUSPICIOUS';
  const score = result.risk_score || 0;

  // MALICIOUS: redirect to full blocked page (pre-click interception may not have fired)
  if (v === 'MALICIOUS' && score >= 65) {
    const params = new URLSearchParams({
      url:         location.href,
      verdict:     v,
      risk:        String(score),
      explanation: result.explanation || 'Malicious page detected.',
      action:      result.action || 'Close this tab immediately.',
      signals:     JSON.stringify((result.shap_features || []).slice(0, 4).map(f => f.feature)),
    });
    window.location.replace(chrome.runtime.getURL('blocked.html') + '?' + params.toString());
    return;
  }

  // SUSPICIOUS: full-width persistent amber strip — cannot be scrolled away
  const signals = (result.shap_features || []).filter(s => s.category === 'active_attack_signal').slice(0, 2).map(s => s.feature).join(' · ');
  const banner = document.createElement('div');
  banner.setAttribute('data-siq-banner', '1');
  banner.style.cssText = `
    position:fixed;top:0;left:0;right:0;z-index:2147483647;
    background:linear-gradient(90deg,#78350f,#92400e,#78350f);
    border-bottom:2px solid #f59e0b;
    font-family:-apple-system,system-ui,sans-serif;
    display:flex;align-items:center;gap:14px;padding:10px 20px;
    box-shadow:0 4px 24px #00000088;
    animation:siq-in .2s ease;
  `;
  banner.innerHTML = `
    <span style="font-size:20px;flex-shrink:0">⚠️</span>
    <div style="flex:1;min-width:0">
      <div style="color:#fef3c7;font-weight:800;font-size:13px;letter-spacing:0.02em">
        SENTINELIQ WARNING — SUSPICIOUS PAGE · Risk ${score}/100
      </div>
      <div style="color:rgba(254,243,199,.75);font-size:11px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
        ${signals || result.explanation || 'Credential-harvesting signals detected.'} · Do not enter passwords.
      </div>
    </div>
    <span style="background:#f59e0b22;color:#fbbf24;font-size:10px;font-weight:800;padding:3px 10px;border-radius:99px;border:1px solid #f59e0b55;flex-shrink:0">SUSPICIOUS</span>
  `;
  // Persistent — no close button for SUSPICIOUS
  document.body.prepend(banner);
  document.body.style.paddingTop = (parseInt(document.body.style.paddingTop) || 0) + 48 + 'px';
}

// ── Init ──────────────────────────────────────────────────────────────────────
const style = document.createElement('style');
style.textContent = `@keyframes siq-in{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}`;
document.head.appendChild(style);

function isLoginPage() {
  const isPathLogin = /login|signin|auth/i.test(location.pathname);
  const hasPasswd = !!document.querySelector('input[type="password"]');
  return isPathLogin || hasPasswd;
}

if (isLoginPage()) {
  chrome.runtime.sendMessage({ type: 'SCAN_ANOMALY', url: location.href, trigger: 'page_load' });
}

// ── Structured Semantic Divergence Engine v2 ─────────────────────────────────
function detectSemanticDivergence() {
  const signals = [];
  let totalScore = 0.0;
  const bodyEl = document.body || document.documentElement;

  const WEIGHTS = {
    invisible_clickable_overlay: 0.95,
    svg_semantic_mismatch: 0.80,
    zero_width_fragmentation: 0.75,
    zero_font_size: 0.50,
    transparent_text: 0.45,
    offscreen_legitimacy_text: 0.35,
    aria_hidden_mismatch: 0.20
  };

  function addSignal(type, extra = {}) {
    signals.push({ type, ...extra });
    totalScore += WEIGHTS[type] || 0;
  }

  // 1. Unicode Obfuscation (Zero-width characters)
  const zeroWidthRegex = /[\u200B\u200C\u200D\uFEFF\u00AD]/g;
  const rawBodyText = bodyEl.innerText || '';
  const zeroWidthCount = (rawBodyText.match(zeroWidthRegex) || []).length;
  if (zeroWidthCount > 10) {
    addSignal('zero_width_fragmentation', { count: zeroWidthCount });
  }

  // 2. Clickability Divergence (Massive transparent overlays capturing clicks)
  document.querySelectorAll('a, button, [onclick]').forEach(el => {
    const style = window.getComputedStyle(el);
    if (style.opacity === '0' || style.color === 'rgba(0, 0, 0, 0)' || style.color === 'transparent') {
      const rect = el.getBoundingClientRect();
      const area = rect.width * rect.height;
      // To be a clickjacking overlay, it must cover a huge area (e.g., 300x300+)
      // AND be positioned out of standard document flow.
      if (area > 100000 && (style.position === 'absolute' || style.position === 'fixed')) {
        addSignal('invisible_clickable_overlay', { tag: el.tagName });
      }
    }
  });

  // 3. CSS & AOM Obfuscation (Sample up to 500 text-containing leaf nodes)
  const walker = document.createTreeWalker(bodyEl, NodeFilter.SHOW_TEXT, null, false);
  let node;
  let nodesScanned = 0;
  
  while ((node = walker.nextNode()) && nodesScanned < 500) {
    const text = node.nodeValue.trim();
    if (text.length < 3) continue; // Ignore trivial whitespace/punctuation
    
    const el = node.parentElement;
    if (!el || el.tagName === 'SCRIPT' || el.tagName === 'STYLE' || el.tagName === 'NOSCRIPT' || el.tagName === 'SVG') continue;
    
    nodesScanned++;
    const style = window.getComputedStyle(el);
    
    // A. Transparent Text
    const isTransparent = style.opacity === '0' || style.color === 'rgba(0, 0, 0, 0)' || style.color === 'transparent';
    if (isTransparent) {
      addSignal('transparent_text');
    }
    
    // B. Off-screen Text
    if (style.position === 'absolute' || style.position === 'fixed') {
      const left = parseInt(style.left, 10);
      const top = parseInt(style.top, 10);
      if (left < -900 || top < -900) {
        addSignal('offscreen_legitimacy_text');
      }
    }
    
    // C. Font-size 0
    if (style.fontSize === '0px') {
      addSignal('zero_font_size');
    }

    // D. AOM Divergence (aria-hidden="true" but element is visibly rendered)
    const hiddenParent = el.closest('[aria-hidden="true"]');
    if (hiddenParent) {
      if (!isTransparent && style.display !== 'none' && style.visibility !== 'hidden' && style.fontSize !== '0px') {
        addSignal('aria_hidden_mismatch');
      }
    }
  }

  return { score: Math.min(totalScore, 1.0), signals };
}

// Fix #2 + #3: Full DOM extraction — captures countdown timers, brand spoofing,
// password forms, urgency language. Returns {content, hasPasswordForm}.
function extractPageContent() {
  const titleText = document.title || '';
  const metaDesc  = document.querySelector('meta[name="description"]')?.content || '';
  const hasPasswd = !!document.querySelector('input[type="password"]');
  const hasEmail  = !!document.querySelector('input[type="email"]');
  const h1text    = document.querySelector('h1,h2')?.textContent?.trim() || '';
  let bodyText  = document.body?.innerText?.substring(0, 2500) || '';

  // 4. SVG Semantic Extraction (Append to body so NLP models can read it)
  let svgTextContent = '';
  document.querySelectorAll('svg text').forEach(t => {
    svgTextContent += ' ' + (t.textContent || '');
  });
  if (svgTextContent.trim()) {
    bodyText += '\n[SVG TEXT CONTENT]\n' + svgTextContent.trim();
  }

  // Detect countdown timers (e.g. "23:47:12" or "24:00")
  const countdownMatch = bodyText.match(/\d{1,2}:\d{2}(:\d{2})?/);
  const hasCountdown   = !!countdownMatch;

  let content = `Title: ${titleText}\n`;
  content += `URL: ${location.href}\n`;
  if (hasPasswd)    content += `[PASSWORD FORM PRESENT]\n`;
  if (hasEmail)     content += `[EMAIL INPUT PRESENT]\n`;
  if (hasCountdown) content += `[COUNTDOWN TIMER: ${countdownMatch[0]}]\n`;
  
  const semanticDivergence = detectSemanticDivergence();
  
  // SVG Semantic Mismatch (if SVG contains auth keywords)
  if (svgTextContent.trim() && /(login|signin|verify|password|secure|account)/i.test(svgTextContent)) {
    semanticDivergence.signals.push({ type: 'svg_semantic_mismatch' });
    semanticDivergence.score = Math.min(semanticDivergence.score + 0.80, 1.0);
  }

  content += h1text   ? `H1: ${h1text}\n`    : '';
  content += metaDesc ? `Meta: ${metaDesc}\n` : '';
  content += bodyText;

  return { content, hasPasswordForm: hasPasswd, semanticDivergence };
}

const isEmailClientPage = location.hostname.includes('mail.google.com') || location.hostname.includes('outlook.live') || location.hostname.includes('outlook.office') || location.hostname.includes('outlook.cloud.microsoft') || location.hostname.includes('mail.yahoo.com');

if (!isEmailClientPage) {
  // Initial pass — fires at document_idle
  const _initial = extractPageContent();
  chrome.runtime.sendMessage({
    type: 'SCAN_PAGE',
    url: location.href,
    content: _initial.content,
    hasPasswordForm: _initial.hasPasswordForm,
    semanticDivergence: _initial.semanticDivergence
  });

  // Fix #2: Delayed second pass — catches dynamically injected content (SPA, JS-rendered forms)
  setTimeout(() => {
    const _delayed = extractPageContent();
    const grew     = _delayed.content.length > _initial.content.length + 80;
    const newForm  = _delayed.hasPasswordForm && !_initial.hasPasswordForm;
    if (grew || newForm) {
      chrome.runtime.sendMessage({
        type: 'SCAN_PAGE',
        url: location.href,
        content: _delayed.content,
        hasPasswordForm: _delayed.hasPasswordForm,
        semanticDivergence: _delayed.semanticDivergence
      });
    }
  }, 1500);
}

// Watch for password inputs dynamically added (SPA-friendly)
warnIfPasswordPage();
new MutationObserver(warnIfPasswordPage).observe(document.body || document.documentElement, { childList: true, subtree: true });

// ── Prompt Injection Monitoring ───────────────────────────────────────────────
const injectionDebounce = debounce((text) => {
  chrome.runtime.sendMessage({ type: 'SCAN_INJECTION', content: text, url: location.href });
}, 800);

function attachInjectionMonitor() {
  document.querySelectorAll('textarea, input[type="text"]').forEach(el => {
    if (monitoredInputs.has(el)) return;
    if (el.type === 'password') return; // S1: NEVER log password fields
    
    monitoredInputs.add(el);
    el.addEventListener('input', (e) => {
      const text = e.target.value;
      if (text.length > 10) injectionDebounce(text);
    });
    
    if (isAiInterface) {
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          const text = e.target.value;
          if (text.length > 10) {
            chrome.runtime.sendMessage({ type: 'SCAN_INJECTION', content: text, url: location.href });
          }
        }
      });
    }
  });
}
attachInjectionMonitor();
new MutationObserver(attachInjectionMonitor).observe(document.body || document.documentElement, { childList: true, subtree: true });



// ── v3.0: Prompt Injection Monitor ───────────────────────────────────────────
// Monitors text inputs (excluding password fields — S8) with an 800ms debounce.
// Escalates automatically when user is on a known AI chat interface.

const _AI_HOSTS_INJECTION = new Set([
  'chat.openai.com', 'gemini.google.com', 'claude.ai',
  'copilot.microsoft.com', 'poe.com', 'character.ai',
  'huggingface.co', 'perplexity.ai',
]);
const _isAiInterface = _AI_HOSTS_INJECTION.has(location.hostname.replace('www.', ''));
const _monitoredInputs = new WeakSet();
let _injectionDebounce = null;

function _attachInjectionMonitor() {
  // S8 invariant: never monitor password fields
  const selector = [
    'textarea',
    'input:not([type="password"]):not([type="hidden"]):not([type="submit"])',
    '[contenteditable="true"]',
  ].join(',');

  function _scanNewInputs() {
    document.querySelectorAll(selector).forEach(el => {
      if (_monitoredInputs.has(el)) return;
      _monitoredInputs.add(el);

      el.addEventListener('input', () => {
        clearTimeout(_injectionDebounce);
        _injectionDebounce = setTimeout(() => {
          const text = (el.value !== undefined ? el.value : el.innerText) || '';
          if (text.trim().length < 30) return;
          chrome.runtime.sendMessage({
            type:            'SCAN_INJECTION',
            content:         text.substring(0, 2000),
            url:             location.href,
            is_ai_interface: _isAiInterface,
            field_type:      el.tagName.toLowerCase(),
          });
        }, 800); // MANDATORY 800ms debounce — never scan on every keystroke
      });

      // AI interfaces: also intercept Enter-to-submit (prompt submission)
      if (_isAiInterface) {
        el.addEventListener('keydown', e => {
          if (e.key !== 'Enter' || e.shiftKey) return;
          const text = (el.value !== undefined ? el.value : el.innerText) || '';
          if (text.trim().length < 10) return;
          chrome.runtime.sendMessage({
            type:            'SCAN_INJECTION',
            content:         text.substring(0, 2000),
            url:             location.href,
            is_ai_interface: true,
            field_type:      el.tagName.toLowerCase(),
          });
        });
      }
    });
  }

  // Observe for dynamically added inputs (SPAs inject them after load)
  const observer = new MutationObserver(_scanNewInputs);
  observer.observe(document.body, { childList: true, subtree: true });
  _scanNewInputs(); // Scan inputs already in the DOM at attach time
}

_attachInjectionMonitor();

// ── v3.0: Login Page Anomaly Trigger ─────────────────────────────────────────
// When the current page looks like a login page, fire SCAN_ANOMALY so the
// anomaly engine can assess session context (velocity, device, time-of-day).

function _isLoginPage() {
  return (
    !!document.querySelector('input[type="password"]') &&
    !!document.querySelector('button[type="submit"], input[type="submit"]') &&
    /\/(login|signin|sign-in|auth|account|session)/i.test(location.pathname)
  );
}

if (_isLoginPage()) {
  chrome.runtime.sendMessage({
    type:    'SCAN_ANOMALY',
    url:     location.href,
    trigger: 'login_page',
    partial_vector: {
      hour:        new Date().getHours(),
      day_of_week: new Date().getDay(),
    },
  });
}

})();
