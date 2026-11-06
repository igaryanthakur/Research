/**
 * SentinelIQ — Popup Controller
 * Tabs | Risk ring animation | Signals | History | Settings
 */

'use strict';

// ── Firebase config (A16: use public API only, no stsTokenManager) ─────────────
const FIREBASE_CONFIG = {
  apiKey:     'AIzaSyABYnQ3LzEJ5awl7iVq4KusHpEUqFcK-c4',
  authDomain: 'cybershield-e57d9.firebaseapp.com',
  projectId:  'cybershield-e57d9',
};
const TOKEN_REFRESH_URL = `https://securetoken.googleapis.com/v1/token?key=${FIREBASE_CONFIG.apiKey}`;

let fbApp = null;
let fbAuth = null;

function safeCacheKey(url) {
  return `c_${url.substring(0, 400)}`;
}

function _normalizeUrl(url) {
  try {
    return decodeURIComponent(url.split('#')[0].split('?')[0])
      .toLowerCase()
      .replace(/\/+$/, '');
  } catch { return url.toLowerCase(); }
}

async function getCachedFromPopup(url) {
  const norm = _normalizeUrl(url);
  // Matches background.js safeCacheKey('c_', url) which just does prefix + url
  const key = `c_${norm}`;
  const res = await chrome.storage.local.get(key);
  return res[key] ? res[key].d : null;
}

// ── Ring constants ─────────────────────────────────────────────────────────
const RING_CIRCUMFERENCE = 289; // 2π × r(46)

const VERDICT_COLORS = {
  MALICIOUS:  '#ef4444',
  SUSPICIOUS: '#f59e0b',
  BENIGN:     '#10b981',
  BYPASSED:   '#10b981', // same as BENIGN — URL bypassed, content clean
  ERROR:      '#6b7280',
  SCANNING:   '#6366f1',
};

// ── Helpers ────────────────────────────────────────────────────────────────
const $  = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

function timeAgo(ts) {
  // Math.max guards against clock skew / future timestamps producing negative diff
  const diff = Math.max(0, (Date.now() - ts) / 1000);
  if (diff < 60)   return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  return `${Math.round(diff / 3600)}h ago`;
}

function truncate(str, n) {
  return str.length > n ? str.slice(0, n) + '…' : str;
}

// ── Risk ring animation ────────────────────────────────────────────────────
function animateRing(score, verdict) {
  const fill = $('#ring-fill');
  const color = VERDICT_COLORS[verdict] || '#6b7280';
  const offset = RING_CIRCUMFERENCE - (score / 100) * RING_CIRCUMFERENCE;
  fill.style.stroke = color;
  fill.style.strokeDashoffset = offset;
  $('#risk-score').style.color = color;
}

// ── Render verdict result ──────────────────────────────────────────────────
function renderResult(result, url) {
  const verdict = result.verdict || 'ERROR';
  const score   = result.risk_score ?? 0;
  const band    = result.risk_band  || (verdict === 'BYPASSED' ? 'URL BYPASSED' : '—');
  const ms      = result.processing_time_ms;

  // Switch states
  $('#state-scanning').classList.add('hidden');
  $('#state-result').classList.remove('hidden');

  // Ring + score
  $('#risk-score').textContent = score;
  animateRing(score, verdict);

  // Chip
  const chip = $('#verdict-chip');
  // Fix #6: BYPASSED shows as CLEAN (not scanned) with distinct label
  chip.textContent = verdict === 'BYPASSED' ? 'CLEAN ✓' : verdict;
  chip.className = `verdict-chip ${verdict === 'BYPASSED' ? 'BENIGN' : verdict}`;

  // Band + meta
  $('#verdict-band').textContent = band;
  $('#verdict-meta').textContent = ms ? `${ms}ms · ${result.narration_mode || ''}` : (result.narration_mode || '');

  // URL bar
  if (url) {
    const bar = $('#url-bar');
    bar.textContent = truncate(url, 55);
    bar.title = url;
  }

  // Analyst Briefing
  // Fix #5: Never show static "Local address — safe" if content signals fired
  const hasSignals = (result.shap_features || []).length > 0;
  if (result.explanation && (result.explanation !== 'No action required.' || hasSignals)) {
    $('#section-briefing').classList.remove('hidden');
    $('#briefing-card').style.borderLeftColor = VERDICT_COLORS[verdict] || '#6366f1';
    // Fix #5: If BYPASSED with no signals, show a clear bypass message — not BENIGN scan message
    const explanation = verdict === 'BYPASSED' && !hasSignals
      ? 'URL structural scan bypassed for local/internal address. Content phishing scan ran and found no threats.'
      : (result.explanation || '');
    $('#briefing-explanation').textContent = explanation;
    $('#briefing-action').textContent = result.action || '';
  }

  // Fix #7: Signal panel populates on ALL verdicts — show what was evaluated
  const signals = (result.shap_features || []).slice(0, 8);
  $('#section-signals').classList.remove('hidden');
  if (signals.length) {
    $('#signals-list').innerHTML = signals.map(s => {
      const pct      = Math.round((s.weight || 0) * 100);
      const isAbsence = (s.category === 'trust_signal_absence');
      const barColor  = isAbsence ? '#f59e0b' : '#6366f1';
      const labelColor = isAbsence ? 'color:#f59e0b' : '';
      return `<div class="signal-row">
        <div class="signal-name" style="${labelColor}">${s.feature || ''}</div>
        <div class="signal-bar-wrap"><div class="signal-bar-fill" style="width:${pct}%;background:${barColor}"></div></div>
        <div class="signal-pct">${pct}%</div>
      </div>`;
    }).join('');
  } else {
    // Fix #7: Show "clean" state with what was checked — never an empty panel.
    // Prevent contradiction: if verdict is bad but no signals, say it was a fallback/rule match.
    if (verdict === 'MALICIOUS' || verdict === 'SUSPICIOUS') {
      $('#signals-list').innerHTML = `<div style="padding:8px 0;color:#ef4444;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em">Heuristic Match · Threat Detected</div><div style="color:#fca5a5;font-size:10px;line-height:1.8">Engine matched known threat patterns or exact heuristics. Deep signal attribution unavailable for this rule.</div>`;
    } else {
      const checkedList = verdict === 'BYPASSED'
        ? 'Content phishing scan · Brand spoof check · Password form detection'
        : 'URL structure · TLD reputation · Brand keywords · Urgency language · Credential forms';
      $('#signals-list').innerHTML = `<div style="padding:8px 0;color:#4b5563;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em">Evaluated · No threats detected</div><div style="color:#374151;font-size:10px;line-height:1.8">${checkedList}</div>`;
    }
  }
}

// ── Load result for active tab ─────────────────────────────────────────────
// The popup cannot extract DOM content itself — content.js does that and pushes
// PAGE_RESULT when done. On popup open, we read the last cached scan for this tab's URL.
async function scanActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url || tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://')) {
    renderResult({ verdict:'BENIGN', risk_score:0, risk_band:'CLEAN', explanation:'Browser internal page — not scannable.', action:'', shap_features:[] }, tab?.url);
    return;
  }

  const isEmailClient = tab.url.includes('mail.google.com') || tab.url.includes('outlook.live.com') || tab.url.includes('outlook.office.com') || tab.url.includes('outlook.cloud.microsoft') || tab.url.includes('mail.yahoo.com');
  
  if (isEmailClient) {
    const isListView = tab.url.endsWith('#inbox') || tab.url.includes('#category/') || tab.url.endsWith('#starred') || tab.url.endsWith('#snoozed') || tab.url.endsWith('#sent') || tab.url.endsWith('#drafts') || tab.url.endsWith('#all') || tab.url.endsWith('#spam') || tab.url.endsWith('#trash') || (tab.url.includes('outlook') && !tab.url.includes('/id/')) || (tab.url.includes('yahoo') && !tab.url.includes('/messages/'));

    if (isListView) {
      renderResult({
        verdict: 'PENDING',
        risk_score: 0,
        explanation: 'SentinelIQ is monitoring your inbox. Please open an email to run a deep content scan.',
        action: 'No email currently opened.',
        shap_features: []
      }, tab.url);
      const engines = ['url', 'phishing', 'injection', 'anomaly', 'email'];
      engines.forEach(e => updateEngineRow(e, null)); // Sets them to PENDING
      return;
    }

    // First, try to get the result from the actual visible banner in the DOM
    // This perfectly solves race conditions if multiple emails are in the same tab.
    try {
      const bannerResp = await chrome.tabs.sendMessage(tab.id, { type: 'GET_VISIBLE_BANNER_RESULT' });
      if (bannerResp && bannerResp.result) {
        renderResult(bannerResp.result, tab.url);
        const engines = ['url', 'phishing', 'injection', 'anomaly', 'email'];
        engines.forEach(e => updateEngineRow(e, bannerResp.result));
        return;
      }
    } catch (e) {
      // Content script not ready or no banner visible, fall through to cache
    }

    const key = `c_email_tab_${tab.id}`;
    const res = await chrome.storage.local.get(key);
    if (res[key] && res[key].d) {
      renderResult(res[key].d, tab.url);
      
      const engines = ['url', 'phishing', 'injection', 'anomaly', 'email'];
      engines.forEach(e => updateEngineRow(e, res[key].d));
      return;
    } else {
      // User is in the inbox but hasn't opened an email (or scan hasn't finished)
      renderResult({
        verdict: 'PENDING',
        risk_score: 0,
        explanation: 'SentinelIQ is monitoring your inbox. Please open an email to run a deep content scan.',
        action: 'No email currently opened.',
        shap_features: []
      }, tab.url);
      const engines = ['url', 'phishing', 'injection', 'anomaly', 'email'];
      engines.forEach(e => updateEngineRow(e, null)); // Sets them to PENDING
      return;
    }
  }

  chrome.runtime.sendMessage({ type: 'SCAN_URL', url: tab.url }, resp => {
    if (resp?.result) renderResult(resp.result, tab.url);
    refreshMainRing(tab.url);
  });
}

// ── Feature Parity ─────────────────────────────────────────────────────────
function updateEngineRow(engine, result) {
  const chip = $(`#chip-${engine}`);
  if (!chip) return;
  if (!result) {
    chip.textContent = 'PENDING';
    chip.className = 'engine-chip';
    return;
  }
  const v = result.verdict || 'ERROR';
  chip.textContent = v === 'BYPASSED' ? 'CLEAN ✓' : v;
  chip.className = `engine-chip ${v === 'BYPASSED' ? 'BENIGN' : v}`;
}

async function refreshMainRing(url) {
  const cached = await getCachedFromPopup(url);
  
  if (!cached || !cached.verdict) {
    // DO NOT wipe engines to PENDING here. 
    // They are either already PENDING from HTML init, or they have live data.
    return;
  }

  // Set specific engines if they exist in the cached response
  if (cached.detection_source === 'dom_content_phishing') {
    updateEngineRow('phishing', cached);
  } else if (cached.detection_source === 'url_structural') {
    updateEngineRow('url', cached);
  }

  renderResult(cached, url);
}

// ── Load dashboard stats ───────────────────────────────────────────────────
function loadDashboard() {
  chrome.runtime.sendMessage({ type: 'GET_STATS' }, resp => {
    if (!resp) return;
    // Guard: background worker may restart and siq_stats may be missing from resp
    const stats = resp?.stats || { total: 0, malicious: 0, suspicious: 0, benign: 0, blocked: 0 };
    $('#stat-total').textContent      = stats.total     || 0;
    $('#stat-malicious').textContent  = stats.malicious || 0;
    const suspiciousEl = $('#stat-suspicious');
    if (suspiciousEl) suspiciousEl.textContent = stats.suspicious || 0;
    $('#stat-benign').textContent     = stats.benign    || 0;
    // Threats Blocked counter
    const blockedEl = $('#stat-blocked');
    if (blockedEl) blockedEl.textContent = stats.blocked || 0;

    const total = stats.total || 1;
    $('#seg-m').style.width = ((stats.malicious  || 0) / total * 100) + '%';
    $('#seg-s').style.width = ((stats.suspicious || 0) / total * 100) + '%';
    $('#seg-b').style.width = ((stats.benign     || 0) / total * 100) + '%';
  });
}

// ── Load history ───────────────────────────────────────────────────────────
function loadHistory() {
  chrome.runtime.sendMessage({ type: 'GET_STATS' }, resp => {
    if (!resp) return;
    const { history } = resp;
    const list = $('#history-list');
    $('#history-count').textContent = `${history.length} scan${history.length !== 1 ? 's' : ''}`;

    if (!history.length) {
      list.innerHTML = '<div class="empty-state">No scans recorded yet.</div>';
      return;
    }

    list.innerHTML = history.map(h => `
      <div class="history-item">
        <div class="history-verdict ${h.verdict}"></div>
        <div class="history-url" title="${h.url}">${truncate(h.url, 45)}</div>
        <div class="history-score">${h.risk_score ?? 0}</div>
        <div class="history-time">${timeAgo(h.ts)}</div>
      </div>
    `).join('');
  });
}

// ── Tabs ───────────────────────────────────────────────────────────────────
$$('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    $$('.tab').forEach(t => t.classList.remove('active'));
    $$('.tab-content').forEach(c => c.classList.add('hidden'));
    tab.classList.add('active');
    const id = 'tab-' + tab.dataset.tab;
    $(`#${id}`).classList.remove('hidden');

    if (tab.dataset.tab === 'dashboard') loadDashboard();
    if (tab.dataset.tab === 'history')   loadHistory();
  });
});

// ── Manual URL scan ────────────────────────────────────────────────────────
$('#btn-scan').addEventListener('click', async () => {
  const raw = $('#manual-url').value.trim();
  if (!raw) return;

  // Validate URL before sending to backend — prevents confusing results for non-URLs
  let url = raw;
  try {
    new URL(raw.startsWith('http') ? raw : `https://${raw}`);
    if (!raw.startsWith('http')) url = `https://${raw}`;
  } catch (err) {
    const out = $('#manual-result');
    out.classList.remove('hidden');
    out.textContent = 'Invalid URL — please enter a valid web address (e.g. https://example.com)';
    return;
  }

  const out = $('#manual-result');
  out.classList.remove('hidden');
  out.textContent = 'Scanning...';

  chrome.runtime.sendMessage({ type: 'SCAN_URL', url }, resp => {
    const r = resp?.result;
    if (!r) { out.textContent = 'Scan failed.'; return; }
    const color = VERDICT_COLORS[r.verdict] || '#6b7280';
    out.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
        <span style="color:${color};font-weight:700">${r.verdict}</span>
        <span style="color:#94a3b8;font-size:11px">Risk ${r.risk_score ?? 0}/100</span>
      </div>
      <div style="color:#cbd5e1;font-size:11px;line-height:1.5">${r.explanation||''}</div>
      ${r.action ? `<div style="color:#818cf8;font-size:11px;margin-top:6px">${r.action}</div>` : ''}
    `;
  });
});

$('#manual-url').addEventListener('keydown', e => {
  if (e.key === 'Enter') $('#btn-scan').click();
});

// ── Manual Injection scan ──────────────────────────────────────────────────
$('#btn-scan-injection').addEventListener('click', async () => {
  const text = $('#manual-injection').value.trim();
  if (!text) return;
  
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab?.url || 'chrome-extension://manual-injection';

  $('#btn-scan-injection').textContent = '...';
  
  chrome.runtime.sendMessage({ type: 'SCAN_INJECTION', content: text, url }, resp => {
    $('#btn-scan-injection').textContent = 'Scan';
    if (resp?.result) {
      updateEngineRow('injection', resp.result);
      refreshMainRing(url);
    }
  });
});

// ── Settings ───────────────────────────────────────────────────────────────
$('#btn-settings').addEventListener('click', () => {
  $('#settings-panel').classList.remove('hidden');
  chrome.runtime.sendMessage({ type: 'GET_SETTINGS' }, resp => {
    $('#input-backend').value = resp?.backendUrl || '';
  });
});

$('#btn-settings-close').addEventListener('click', () => {
  $('#settings-panel').classList.add('hidden');
});

$('#btn-save-settings').addEventListener('click', () => {
  const url = $('#input-backend').value.trim();
  chrome.runtime.sendMessage({ type: 'SET_SETTINGS', backendUrl: url }, () => {
    $('#settings-panel').classList.add('hidden');
  });
});

$('#btn-test-backend').addEventListener('click', async () => {
  const url = ($('#input-backend').value.trim() || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '');
  const status = $('#test-status');
  status.textContent = 'Testing…';
  status.className = 'test-status';
  try {
    const resp = await fetch(`${url}/health`, { signal: AbortSignal.timeout(5000) });
    if (resp.ok) {
      status.textContent = '✓ Connected';
      status.className = 'test-status ok';
    } else {
      throw new Error(`HTTP ${resp.status}`);
    }
  } catch (e) {
    status.textContent = '✗ Unreachable';
    status.className = 'test-status err';
  }
});

// ── Clear history ──────────────────────────────────────────────────────────
$('#btn-clear-history').addEventListener('click', async () => {
  await chrome.storage.local.remove(['siq_history', 'siq_stats']);
  loadHistory();
  loadDashboard();
});

function _renderEmailDetail(result) {
  if (!result || !result.subject) return;

  $('#section-email-detail').classList.remove('hidden');

  $('#email-subject').textContent = result.subject || '—';
  const senderStr = result.senderEmail ? `${result.senderName} <${result.senderEmail}>` : '—';
  $('#email-sender').textContent = senderStr;
  $('#email-sender').title = senderStr;
  
  const bVerdict = result.bodyVerdict || 'BENIGN';
  $('#email-body-verdict').textContent = bVerdict;
  $('#email-body-verdict').style.color = VERDICT_COLORS[bVerdict] || '#6b7280';

  const sVerdict = result.senderVerdict || 'BENIGN';
  $('#email-sender-verdict').textContent = sVerdict;
  $('#email-sender-verdict').style.color = VERDICT_COLORS[sVerdict] || '#6b7280';

  const overall = result.verdict || 'BENIGN';
  $('#email-verdict-chip').textContent = overall;
  $('#email-verdict-chip').className = `verdict-chip ${overall}`;

  const urls = result.urlResults || [];
  const links = result.links || [];
  
  if (urls.length === 0) {
    $('#email-url-list').innerHTML = '<div style="color:#6b7280;font-size:11px">No URLs found in email.</div>';
  } else {
    $('#email-url-list').innerHTML = urls.map((u, i) => {
      const v = u.verdict || 'BENIGN';
      const c = VERDICT_COLORS[v] || '#6b7280';
      return `<div style="display:flex; justify-content:space-between; margin-bottom:4px; align-items:center;">
        <span style="font-size:11px; color:#d1d5db; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:200px;" title="${links[i] || ''}">${links[i] || '—'}</span>
        <span style="font-size:10px; font-weight:700; color:${c}; margin-left:8px">${v}</span>
      </div>`;
    }).join('');
  }
}

// ── Listen for background push (page result) ───────────────────────────────
chrome.runtime.onMessage.addListener(msg => {
  if (msg.type === 'PAGE_RESULT') {
    renderResult(msg.result, msg.url);
    const engines = ['url', 'phishing', 'injection', 'anomaly', 'email'];
    engines.forEach(e => updateEngineRow(e, msg.result));
    // refreshMainRing removed to prevent cache mismatch from overwriting live results
  }
  if (msg.type === 'EMAIL_RESULT') {
    renderResult(msg.result, msg.url);
    const engines = ['url', 'phishing', 'injection', 'anomaly', 'email'];
    engines.forEach(e => updateEngineRow(e, msg.result));
    _renderEmailDetail(msg.result);
  }
  if (msg.type === 'OPEN_POPUP_EMAIL_TAB') {
    // Switch to scan tab if not already on it
    $$('.tab').forEach(t => t.classList.remove('active'));
    $$('.tab-content').forEach(c => c.classList.add('hidden'));
    $('[data-tab="scan"]').classList.add('active');
    $('#tab-scan').classList.remove('hidden');
  }
  if (msg.type === 'INJECTION_RESULT') {
    updateEngineRow('injection', msg.result);
  }
  if (msg.type === 'ANOMALY_RESULT') {
    updateEngineRow('anomaly', msg.result);
  }
  if (msg.type === 'AUTH_STATE_CHANGED' && msg.loggedOut) {
    const reasonMsg =
      msg.reason === 'session_expired'    ? 'Session expired — please sign in again.'   :
      msg.reason === '401_invalid_token'  ? 'Session invalidated. Please sign in again.' :
      'Signed out.';
    renderAuthLoggedOut();
    renderAuthError(reasonMsg);
  }
});

// ── Auth UI (v3.0) ───────────────────────────────────────────────────────────────────
function renderAuthError(msg) {
  const err = $('#auth-error');
  err.textContent = msg;
  err.classList.remove('hidden');
  // Auto-hide after 5 seconds so it doesn't persist
  setTimeout(() => err.classList.add('hidden'), 5000);
}

async function refreshTokenFromPopup(refreshToken) {
  try {
    const resp = await fetch(TOKEN_REFRESH_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ grant_type: 'refresh_token', refresh_token: refreshToken }),
    });
    if (!resp.ok) return;
    const data = await resp.json();
    // A14: spread existing FIRST so fresh fields overwrite stale ones
    const { siq_auth } = await chrome.storage.local.get('siq_auth');
    await chrome.storage.local.set({
      siq_auth: {
        ...siq_auth,
        id_token:      data.id_token,
        refresh_token: data.refresh_token,
        expiry_ms:     Date.now() + parseInt(data.expires_in) * 1000,
      },
      siq_refresh_fails: 0,
    });
  } catch (err) { /* non-fatal, background will retry */ }
}

async function handleSignIn() {
  if (!fbAuth) { renderAuthError('Auth not initialized.'); return; }
  try {
    // 1. Ask Chrome for an OAuth token (this triggers the native Google sign-in window)
    chrome.identity.getAuthToken({ interactive: true }, async function(token) {
      if (chrome.runtime.lastError || !token) {
        renderAuthError(`Chrome Identity error: ${chrome.runtime.lastError?.message || 'Unknown'}`);
        return;
      }
      
      try {
        // 2. Pass the access token directly to Firebase REST API (Bypasses SDK limits completely!)
        const body = new URLSearchParams();
        body.append('postBody', `access_token=${token}&providerId=google.com`);
        body.append('requestUri', 'http://localhost');
        body.append('returnIdpCredential', 'true');
        body.append('returnSecureToken', 'true');

        const fbResp = await fetch(`https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key=${FIREBASE_CONFIG.apiKey}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            postBody: `access_token=${token}&providerId=google.com`,
            requestUri: 'http://localhost',
            returnIdpCredential: true,
            returnSecureToken: true
          })
        });

        if (!fbResp.ok) {
          const errData = await fbResp.json();
          throw new Error(errData.error?.message || `HTTP ${fbResp.status}`);
        }

        const data = await fbResp.json();
        const siqAuth = {
          id_token:      data.idToken,
          refresh_token: data.refreshToken,
          expiry_ms:     Date.now() + (parseInt(data.expiresIn) * 1000),
          email:         data.email,
          uid:           data.localId,
        };
        
        await chrome.storage.local.set({ siq_auth: siqAuth, siq_refresh_fails: 0 });
        chrome.runtime.sendMessage({ type: 'AUTH_STATE_CHANGED', loggedIn: true });
        renderAuthLoggedIn(data.email);
        
        // Revoke the chrome token so we don't cache it indefinitely, Firebase manages its own session now
        chrome.identity.removeCachedAuthToken({ token });
        
      } catch (fbErr) {
        renderAuthError(`Firebase rejected token: ${fbErr.code || fbErr.message}`);
        console.error('[SentinelIQ] Firebase auth failed:', fbErr);
      }
    });
  } catch (err) {
    renderAuthError(`Sign in failed: ${err.code || err.message}`);
    console.error('[SentinelIQ] Sign in failed:', err);
  }
}

async function handleSignOut() {
  try {
    if (fbAuth) await FirebaseAuthBundle.signOut(fbAuth);
  } catch (err) { /* ignored */ }
  await chrome.storage.local.remove(['siq_auth', 'siq_refresh_fails']);
  // A6: logout is local to extension only — website session unaffected
  chrome.runtime.sendMessage({ type: 'AUTH_STATE_CHANGED', loggedOut: true }).catch(() => {});
  renderAuthLoggedOut();
}

function renderAuthLoggedIn(email = '') {
  $('#auth-status').innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between">
      <div>
        <div style="color:#10b981;font-size:13px;font-weight:600">✓ Signed in</div>
        <div style="color:#94a3b8;font-size:11px;margin-top:2px">${email}</div>
        <div style="color:#4b5563;font-size:10px;margin-top:2px">● Sync ON — saving to dashboard</div>
      </div>
      <button id="btn-signout" class="clear-btn">Sign Out</button>
    </div>
  `;
  $('#auth-error').classList.add('hidden');
  $('#btn-signout').addEventListener('click', handleSignOut);
}

function renderAuthLoggedOut() {
  $('#auth-status').innerHTML = `
    <div style="margin-bottom:8px;color:#6b7280;font-size:11px">Sign in to sync scan history with dashboard</div>
    <button id="btn-signin" class="scan-btn" style="width:100%">Sign in with Google</button>
    <div style="color:#4b5563;font-size:10px;margin-top:6px">Scans work without sign in — history won't save</div>
  `;
  $('#auth-error').classList.add('hidden');
  $('#btn-signin').addEventListener('click', handleSignIn);
}

async function initAuthUI() {
  if (typeof FirebaseAuthBundle === 'undefined') {
    renderAuthError('Firebase bundle missing. Reload the extension.');
    return;
  }
  try {
    fbApp  = FirebaseAuthBundle.initializeApp(FIREBASE_CONFIG);
    fbAuth = FirebaseAuthBundle.getAuth(fbApp);

    const { siq_auth } = await chrome.storage.local.get('siq_auth');
    if (siq_auth?.id_token) {
      // Refresh token proactively if within 5 minutes of expiry
      if (siq_auth.expiry_ms && Date.now() > siq_auth.expiry_ms - 5 * 60 * 1000) {
        await refreshTokenFromPopup(siq_auth.refresh_token);
      }
      renderAuthLoggedIn(siq_auth.email);
    } else {
      renderAuthLoggedOut();
    }
  } catch (err) {
    renderAuthError('Auth init failed.');
    console.error('[SentinelIQ] initAuthUI error:', err.message);
  }
}

// ── Init ────────────────────────────────────────────────────────────────────
initAuthUI();
scanActiveTab();
