/**
 * SentinelIQ - Dynamic Email Content Script
 * Monitors the DOM for new visible emails and scans them concurrently.
 */

const _isOutlook = location.hostname.includes('outlook');

function _safeQuery(selector, context = document) {
  try { return context.querySelector(selector); } catch { return null; }
}

function _safeQueryAll(selector, context = document) {
  try { return [...context.querySelectorAll(selector)]; } catch { return []; }
}

function _hashEmail(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = Math.imul(31, h) + str.charCodeAt(i) | 0;
  }
  return 'email_' + Math.abs(h).toString(36);
}

// ── Polling & Deduplication ──
const IDENTITY_SNIPPET_LENGTH = 100;
const _processedEmails = new Set();
let _dynamicObserver = null;
let _pollDebounce = null;

function _initDynamicObserver() {
  if (_dynamicObserver) return;
  
  // Gmail: .AO is the main reading pane, Outlook: [role="main"]
  // If not immediately available, fallback to document.body
  const container = _isOutlook ? (_safeQuery('[role="main"]') || document.body) : (_safeQuery('.AO') || document.body);
  
  _dynamicObserver = new MutationObserver(() => {
    if (!_isOutlook && !location.href.includes('#')) return;
    clearTimeout(_pollDebounce);
    _pollDebounce = setTimeout(_pollVisibleEmails, 200);
  });

  _dynamicObserver.observe(container, {
    childList: true,
    subtree: true,
    attributes: false,
    characterData: false
  });
}

// Start observer, but delay slightly to let Gmail's initial layout load
setTimeout(_initDynamicObserver, 500);

// Prevent memory leaks on SPA unload/reload
window.addEventListener('unload', () => {
  if (_dynamicObserver) _dynamicObserver.disconnect();
});

function _pollVisibleEmails() {
  let wrappers = [];

  if (_isOutlook) {
    const body = _getOutlookBody();
    if (body) wrappers = [{ body, container: document.body }];
  } else {
    // Gmail groups emails in `.h7` (collapsed or expanded)
    const h7s = _safeQueryAll('.h7');
    if (h7s.length) {
      wrappers = h7s.map(h7 => ({
        body: h7.querySelector('.a3s.aiL') || h7.querySelector('.ii.gt div[dir="ltr"]') || h7.querySelector('.a3s'),
        container: h7
      }));
    } else {
      // Single email fallback
      const body = _safeQuery('.a3s.aiL') || _safeQuery('.ii.gt div[dir="ltr"]') || _safeQuery('.a3s');
      if (body) wrappers = [{ body, container: document.body }];
    }
  }

  for (const w of wrappers) {
    const { body, container } = w;
    
    if (!body || body.offsetParent === null) continue; // Not visible
    if (body.hasAttribute('data-siq-status')) continue; // Already processed
    
    const data = _extractEmailData(body, container);
    if (!data || data.bodyText.trim().length < 20) {
        // Not enough content yet, might be rendering. Wait for next tick.
        continue;
    }

    const identity = _hashEmail(data.senderEmail + '|' + data.bodyText.substring(0, IDENTITY_SNIPPET_LENGTH));
    if (_processedEmails.has(identity)) {
        body.setAttribute('data-siq-status', 'done'); // Visual flag to ignore in future DOM loops
        continue; 
    }
    _processedEmails.add(identity);

    // Mark as scanning
    body.setAttribute('data-siq-status', 'scanning');
    const scanId = 'scan_' + Math.random().toString(36).substr(2, 9);
    body.setAttribute('data-siq-id', scanId);

    _injectScanningIndicator(body, container);
    
    if (typeof chrome !== 'undefined' && chrome?.runtime?.sendMessage) {
      chrome.runtime.sendMessage({
        type:        'SCAN_EMAIL_FULL',
        scanId:      scanId,
        bodyText:    data.bodyText,
        subject:     data.subject,
        senderName:  data.senderName,
        senderEmail: data.senderEmail,
        replyTo:     data.replyTo,
        attachments: data.attachments,
        links:       data.links,
        url:         data.url,
      }).catch(() => {});
    }
  }
}

function _getOutlookBody() {
  // NOTE: Outlook DOM selectors verified on 2026-05-26. 
  // Outlook Web frequently changes its DOM structure. This fallback chain should be periodically reviewed.
  let el = _safeQuery('.rps_Body');
  if (el) return el;

  el = _safeQuery('[data-testid="message-body"]') ||
         _safeQuery('[aria-label="Message body"]') ||
         _safeQuery('[aria-label="Message Body"]') ||
         _safeQuery('[data-automation-id="MessageBody"]') ||
         _safeQuery('div[id^="UniqueMessageBody"]') ||
         _safeQuery('div.BodyFragment') ||
         _safeQuery('div.item-body') ||
         _safeQuery('div.allowTextSelection') ||
         _safeQuery('.x_BodyFragment') ||
         _safeQuery('.x_rps_Body') ||
         _safeQuery('div.wide-content-host') ||
         _safeQuery('div[data-testid="reading-pane"]') ||
         _safeQuery('[data-app-section="ReadingPane"] .rps_Body') ||
         _safeQuery('[data-app-section="ReadingPane"] [role="main"]') ||
         _safeQuery('[aria-label="Reading Pane"] [role="main"]') ||
         _safeQuery('[data-app-section="ReadingPane"]') ||
         _safeQuery('[data-automation-id="ReadingPane"]') ||
         _safeQuery('[aria-label="Reading Pane"]'); // Last resort scoped to reading pane

  if (el) {
    console.warn('[SentinelIQ] Primary Outlook selector .rps_Body failed. Fallback chain engaged. DOM may have changed.');
    return el;
  }
  if (location.href.includes('deeplink=mail')) {
    const fallback = _safeQuery('[role="main"]') || document.body;
    if (fallback && fallback.innerText && fallback.innerText.includes('Select an item to read')) return null;
    return fallback;
  }
  return null;
}

function _extractEmailData(bodyEl, container) {
  let subject = '';
  let senderName = '';
  let senderEmail = '';
  let replyTo = '';
  let attachments = [];

  if (_isOutlook) {
    subject = _safeQuery('[data-testid="subject"]')?.innerText?.trim() || 
              _safeQuery('.rps_subjectLine')?.innerText?.trim() || 
              _safeQuery('[aria-label="Message subject"]')?.innerText?.trim() || 
              _safeQuery('h1[role="heading"]')?.innerText?.trim() || '';
    
    const senderEl = _safeQuery('[data-testid="senderEmail"]', container) || 
                     _safeQuery('.rps_senderName', container) || 
                     _safeQuery('[aria-label*="From"]', container);
                     
    senderName = senderEl?.innerText?.trim() || '';
    senderEmail = senderName; // fallback
    
    const fromAria = _safeQuery('[aria-label*="From"]', container)?.getAttribute('aria-label') || '';
    const emailMatch = fromAria.match(/<([^>]+)>/);
    if (emailMatch) {
      senderEmail = emailMatch[1].trim();
      senderName = fromAria.replace(/From[:]?/, '').replace(/<[^>]+>/, '').trim();
    }
    
    const attachmentEls = _safeQueryAll('.AttachmentCard, [aria-label="Attachments"] [role="listitem"]', container);
    attachments = attachmentEls.map(el => el.innerText.trim());
  } else {
    // Gmail logic scoped to the specific .h7 container
    subject = _safeQuery('h2.hP')?.innerText?.trim() || ''; // Subject is global
    const senderEl    = _safeQuery('.go .gD[email]', container) || _safeQuery('.from span[email]', container) || _safeQuery('span[email]', container);
    senderName  = senderEl?.innerText?.trim() || '';
    senderEmail = senderEl?.getAttribute('email')?.trim() || '';
    const replyEl    = _safeQuery('.ajv .g2', container);
    replyTo    = replyEl?.getAttribute('email')?.trim() || replyEl?.innerText?.trim() || '';
    const attachmentEls = _safeQueryAll('.aQA .aV3', container);
    attachments   = attachmentEls.map(el => el.innerText.trim());
  }

  const SKIP_PROTOCOLS = ['mailto:', 'tel:', 'javascript:', 'data:', '#'];
  const TRUSTED_DOMAINS = new Set([
    'google.com', 'googleapis.com', 'gstatic.com',
    'googleusercontent.com', 'youtube.com', 'accounts.google.com',
    'support.google.com', 'mail.google.com',
    'microsoft.com', 'outlook.com', 'office.com', 'live.com'
  ]);

  function isTrustedDomain(url) {
    try {
      const hostname = new URL(url).hostname.replace(/^www\./, '');
      return TRUSTED_DOMAINS.has(hostname) || [...TRUSTED_DOMAINS].some(d => hostname.endsWith('.' + d));
    } catch { return false; }
  }

  const rawLinks = _safeQueryAll('a[href]', bodyEl)
    .map(a => { try { return new URL(a.href).href; } catch { return null; } })
    .filter(href => href && !SKIP_PROTOCOLS.some(p => href.startsWith(p)) && !isTrustedDomain(href));

  const URL_REGEX = /https?:\/\/[^\s\])"'>]{10,}/gi;
  const rawTextMatches = (bodyEl.innerText.match(URL_REGEX) || [])
    .map(u => { try { return new URL(u).href; } catch { return null; } })
    .filter(href => href && !SKIP_PROTOCOLS.some(p => href.startsWith(p)) && !isTrustedDomain(href));

  const links = [...new Set([...rawLinks, ...rawTextMatches])].slice(0, 10);

  const bodyText = bodyEl.innerText
    .replace(/\S+@\S+\.\S+/g, '[email]')
    .substring(0, 3000);

  return { subject, senderName, senderEmail, replyTo, attachments, links, bodyText, url: location.href };
}

function _injectScanningIndicator(bodyEl, container) {
  if (typeof chrome !== 'undefined' && chrome?.runtime?.sendMessage) {
    chrome.runtime.sendMessage({ type: 'EMAIL_SCANNING' }).catch(() => {});
  }
}

// ── Handle Results ──
if (typeof chrome !== 'undefined' && chrome.runtime?.onMessage) {
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'EMAIL_SCAN_RESULT') {
      _handleScanResult(msg);
    }
    if (msg.type === 'GET_VISIBLE_BANNER_RESULT') {
      // Find the first visible banner
      const banners = [...document.querySelectorAll('.siq-email-banner')];
      const visibleBanner = banners.find(b => b.offsetParent !== null);
      if (visibleBanner) {
        try {
          const resultStr = visibleBanner.getAttribute('data-siq-result');
          if (resultStr) {
            sendResponse({ result: JSON.parse(resultStr) });
            return;
          }
        } catch (e) {}
      }
      sendResponse({ result: null });
    }
  });
}

function _handleScanResult(msg) {
  const bodyEl = document.querySelector(`[data-siq-id="${msg.scanId}"]`);
  if (!bodyEl) return;
  bodyEl.setAttribute('data-siq-status', 'done');

  if (msg.verdict === 'MALICIOUS' || msg.verdict === 'SUSPICIOUS' || msg.verdict === 'BENIGN') {
    _injectWarningBanner(msg, bodyEl);
    if (msg.verdict !== 'BENIGN') {
      _highlightDangerousLinks(msg.linkVerdictMap, bodyEl);
    }
  }
}

function _injectWarningBanner(msg, bodyEl) {
  const isMalicious = msg.verdict === 'MALICIOUS';
  const isSuspicious = msg.verdict === 'SUSPICIOUS';
  
  const color       = isMalicious ? '#ef4444' : isSuspicious ? '#f59e0b' : '#10b981';
  const bgColor     = isMalicious ? '#fef2f2' : isSuspicious ? '#fffbeb' : '#ecfdf5';
  const borderColor = isMalicious ? '#fca5a5' : isSuspicious ? '#fde68a' : '#6ee7b7';
  const icon        = isMalicious ? '🚨' : isSuspicious ? '⚠️' : '✅';
  const title       = isMalicious
    ? 'SentinelIQ: Malicious Email Detected'
    : isSuspicious
    ? 'SentinelIQ: Suspicious Email Detected'
    : 'SentinelIQ: Legit Email (Safe to open links)';

  const signals = (msg.shap_features || [])
    .slice(0, 4)
    .map(f => `<li style="margin:2px 0;color:#374151;font-size:12px">${f.feature}</li>`)
    .join('');

  const badUrls = (msg.urlResults || [])
    .filter(r => r && (r.verdict === 'MALICIOUS' || r.verdict === 'SUSPICIOUS'))
    .slice(0, 3)
    .map((r, i) => {
      const urlShort = (msg.links[i] || '').substring(0, 60);
      return `<li style="margin:2px 0;color:#ef4444;font-size:12px;font-family:monospace">${urlShort}</li>`;
    })
    .join('');

  const banner = document.createElement('div');
  banner.className = 'siq-email-banner';
  banner.setAttribute('data-siq-result', JSON.stringify(msg));
  banner.style.cssText = `
    all: initial;
    display: block;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: ${bgColor};
    border: 1px solid ${borderColor};
    border-left: 4px solid ${color};
    border-radius: 8px;
    padding: 12px 16px;
    margin: 0 0 12px 0;
    position: relative;
    z-index: 1000;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    box-sizing: border-box;
    width: 100%;
    max-width: 800px;
    line-height: 1.5;
  `;
  banner.innerHTML = `
    <div style="display:flex;align-items:flex-start;gap:10px">
      <span style="font-size:18px;line-height:1">${icon}</span>
      <div style="flex:1">
        <div style="font-weight:700;color:${color};font-size:13px;margin-bottom:6px">${title}</div>
        ${signals ? `<ul style="margin:0 0 6px 16px;padding:0">${signals}</ul>` : ''}
        ${badUrls ? `
          <div style="font-weight:600;color:#374151;font-size:12px;margin-bottom:4px">Dangerous links detected:</div>
          <ul style="margin:0 0 0 16px;padding:0">${badUrls}</ul>
        ` : ''}
        <div style="margin-top:8px;display:flex;gap:8px">
          <button class="siq-banner-details" style="
            background:${color};color:white;border:none;border-radius:4px;
            padding:4px 10px;font-size:11px;cursor:pointer;font-weight:600">
            View in SentinelIQ
          </button>
          <button class="siq-banner-safe" style="
            background:transparent;color:#6b7280;border:1px solid #d1d5db;
            border-radius:4px;padding:4px 10px;font-size:11px;cursor:pointer">
            Mark as Safe
          </button>
        </div>
      </div>
      <button class="siq-banner-close" style="
        background:none;border:none;color:#9ca3af;cursor:pointer;
        font-size:18px;line-height:1;padding:0;margin:-2px -4px 0 0">×</button>
    </div>
  `;

  bodyEl.parentElement?.insertBefore(banner, bodyEl);

  banner.querySelector('.siq-banner-close')?.addEventListener('click', () => {
    banner.remove();
  });

  banner.querySelector('.siq-banner-safe')?.addEventListener('click', async () => {
    banner.remove();
  });

  banner.querySelector('.siq-banner-details')?.addEventListener('click', () => {
    if (typeof chrome !== 'undefined' && chrome?.runtime?.sendMessage) {
      chrome.runtime.sendMessage({ type: 'OPEN_DASHBOARD' });
    }
  });
}

function _highlightDangerousLinks(linkVerdictMapEntries, bodyEl) {
  if (!linkVerdictMapEntries || linkVerdictMapEntries.length === 0) return;

  const verdictMap = new Map(linkVerdictMapEntries);

  _safeQueryAll('a[href]', bodyEl).forEach(linkEl => {
    let href;
    try { href = new URL(linkEl.href).href; } catch { return; }
    
    const result = verdictMap.get(href);
    if (!result) return;
    if (result.verdict !== 'MALICIOUS' && result.verdict !== 'SUSPICIOUS') return;

    if (linkEl.parentElement?.classList?.contains('siq-link-wrapper')) return;

    const isMalicious = result.verdict === 'MALICIOUS';
    const wrapColor   = isMalicious ? '#ef4444' : '#f59e0b';

    const wrapper = document.createElement('span');
    wrapper.className = 'siq-link-wrapper';
    wrapper.style.cssText = `
      display: inline;
      outline: 2px solid ${wrapColor};
      outline-offset: 1px;
      border-radius: 2px;
      position: relative;
    `;

    const tooltip = document.createElement('span');
    tooltip.className = 'siq-link-tooltip';
    tooltip.style.cssText = `
      display: none;
      position: absolute;
      bottom: 100%;
      left: 0;
      background: #1f2937;
      color: white;
      font-size: 11px;
      padding: 4px 8px;
      border-radius: 4px;
      white-space: nowrap;
      z-index: 9999;
      pointer-events: none;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    `;
    tooltip.textContent = isMalicious
      ? `⚠ SentinelIQ: Malicious URL (${Math.round((result.confidence||0)*100)}% confidence)`
      : `⚠ SentinelIQ: Suspicious URL (${Math.round((result.confidence||0)*100)}% confidence)`;

    wrapper.appendChild(tooltip);
    linkEl.parentNode?.insertBefore(wrapper, linkEl);
    wrapper.appendChild(linkEl);

    wrapper.addEventListener('mouseenter', () => { tooltip.style.display = 'block'; });
    wrapper.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });
  });
}
