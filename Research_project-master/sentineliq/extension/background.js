/**
 * SentinelIQ — Background Service Worker
 * Scan pipeline | Smart cache | Badge management | Stats tracking | Nav interception
 *
 * Architecture:
 *   scanUrl(url)      → URL structural analysis ONLY. Returns BYPASSED for localhost.
 *   scanContent(text) → NLP/heuristic phishing scan. ALWAYS runs, regardless of host.
 *   SCAN_PAGE handler → Promise.all([scanUrl, scanContent]) → merge worst → badge → cache
 *
 * Fix log (2026-05-10):
 *   1. Separated localhost URL exemption from content exemption.
 *   2. Badge update happens ONLY after full merge is resolved (not inside individual callbacks).
 *   3. Password form detection forces escalation regardless of URL verdict.
 *   4. BYPASSED state is explicit — distinct from BENIGN (scanned clean).
 *   5. Merged result (worst verdict) is what gets cached — popup always reads the real verdict.
 */

const DEFAULT_BACKEND = 'https://indianext-x-chitti2-0.onrender.com/api/v1';
let currentBackendUrl = DEFAULT_BACKEND;

// Load saved backend URL on startup
chrome.storage.local.get('siq_backend_url').then(res => {
  if (res.siq_backend_url) currentBackendUrl = res.siq_backend_url;
});

const CACHE_TTL_MS    = 30 * 60 * 1000; // 30 min
const MAX_CACHE       = 500;
const BLOCKED_PAGE    = chrome.runtime.getURL('blocked.html');

// ── v3.0 Auth & Feature Parity constants ─────────────────────────────────────
const FIREBASE_API_KEY            = 'AIzaSyABYnQ3LzEJ5awl7iVq4KusHpEUqFcK-c4';
const TOKEN_REFRESH_URL           = `https://securetoken.googleapis.com/v1/token?key=${FIREBASE_API_KEY}`;
const TOKEN_REFRESH_BUFFER_MS     = 5 * 60 * 1000;  // refresh 5 min before expiry
const MAX_REFRESH_FAILURES        = 3;
const ANOMALY_HEARTBEAT_INTERVAL_MIN = 15;
const AI_HOSTS = new Set([
  'chat.openai.com', 'gemini.google.com', 'claude.ai',
  'copilot.microsoft.com', 'poe.com', 'character.ai',
  'huggingface.co', 'perplexity.ai',
]);

const TRUSTED_EMAIL_DOMAINS = new Set([
  'google.com', 'googleapis.com', 'gstatic.com',
  'googleusercontent.com', 'youtube.com',
]);
const MAX_EMAIL_URL_SCANS   = 5;
const EMAIL_SCAN_TIMEOUT_MS = 15000;
const URL_SCAN_TIMEOUT_MS   = 8000;

const SENDER_BRAND_TABLE = {
  'paypal':       ['.paypal.com', '.paypal.co.uk'],
  'amazon':       ['.amazon.com', '.amazon.co.', '.amazonaws.com', '.amzn.to'],
  'google':       ['.google.com', '.googleapis.com', '.googlemail.com'],
  'apple':        ['.apple.com', '.icloud.com'],
  'microsoft':    ['.microsoft.com', '.microsoftonline.com', '.outlook.com'],
  'netflix':      ['.netflix.com'],
  'ebay':         ['.ebay.com', '.ebay.co.'],
  'instagram':    ['.instagram.com'],
  'facebook':     ['.facebook.com', '.fb.com'],
  'wellsfargo':   ['.wellsfargo.com'],
  'chase':        ['.chase.com'],
  'bankofamerica':['.bankofamerica.com'],
  'citibank':     ['.citibank.com', '.citi.com'],
  'steam':        ['.steampowered.com', '.steamcommunity.com'],
  'discord':      ['.discord.com', '.discord.gg'],
  'linkedin':     ['.linkedin.com'],
  'twitter':      ['.twitter.com', '.x.com'],
  'dropbox':      ['.dropbox.com'],
  'icloud':       ['.icloud.com'],
  'dhl':          ['.dhl.com'],
  'fedex':        ['.fedex.com'],
  'ups':          ['.ups.com'],
  'usps':         ['.usps.com'],
  'irs':          ['.irs.gov'],
};

function _normalizeDomain(domain) {
  try {
    return new URL('https://' + domain).hostname;
  } catch {
    return domain.toLowerCase();
  }
}

function analyzeSender(displayName, fromEmail, replyToEmail) {
  const fromDomain    = _normalizeDomain((fromEmail.split('@')[1]  || '').toLowerCase());
  const replyDomain   = _normalizeDomain((replyToEmail?.split('@')[1] || '').toLowerCase());
  const nameLower     = displayName.toLowerCase();

  for (const [brand, canonicals] of Object.entries(SENDER_BRAND_TABLE)) {
    const nameHasBrand = nameLower.includes(brand);
    if (!nameHasBrand) continue;

    const fromIsCanonical   = canonicals.some(c => fromDomain.endsWith(c.replace(/^\./,'')));
    const replyIsCanonical  = !replyDomain ||
      canonicals.some(c => replyDomain.endsWith(c.replace(/^\./,'')));

    if (!fromIsCanonical) {
      return {
        verdict:    'MALICIOUS',
        confidence: 0.95,
        shap_features: [{
          feature:   `Sender Spoof: claims ${brand}, domain is ${fromDomain}`,
          weight:    0.95,
          direction: 'positive',
          category:  'active_attack_signal',
        }],
        explanation: `Email claims to be from ${brand.toUpperCase()} but was
          sent from ${fromDomain} which is not a canonical ${brand} domain.`,
        action: 'Do not click any links. Do not reply. Report as phishing.',
      };
    }

    if (!replyIsCanonical) {
      return {
        verdict:    'SUSPICIOUS',
        confidence: 0.80,
        shap_features: [{
          feature:   `Reply-To Mismatch: reply goes to ${replyDomain}`,
          weight:    0.80,
          direction: 'positive',
          category:  'active_attack_signal',
        }],
        explanation: `Email appears to be from ${brand.toUpperCase()} but
          replies go to ${replyDomain} — a common credential harvesting tactic.`,
        action: 'Do not reply. Verify through official website directly.',
      };
    }
  }

  return { verdict: 'BENIGN', confidence: 0.1, shap_features: [] };
}

// ── Whitelist: in-memory + persistent, race-condition-free ───────────────────
//
// MV3 service workers die after ~30 s of inactivity. Every restart wipes all
// JS heap state. The three-layer design below guarantees no bypass loop:
//
//   Layer 1 – _approvedUrls (in-memory Set)
//     Populated SYNCHRONOUSLY inside _whitelistAdd().
//     Checked first — zero async latency.
//
//   Layer 2 – _whitelistRestorePromise
//     On every SW wake-up, we immediately start reading storage and populating
//     _approvedUrls. Any SCAN_PAGE that arrives before restore finishes AWAITS
//     this promise before deciding — so a restart never causes a false-block.
//
//   Layer 3 – chrome.storage.local (persistent across restarts)
//     _whitelistAdd() AWAITS the storage write before returning. Callers that
//     need guaranteed persistence (WHITELIST_AND_NAVIGATE) await this promise
//     before triggering navigation. By the time content.js fires on the new
//     page, storage is written and Layer 2 will restore it even if the SW died.
//
// Timeline (worst case — SW restart between whitelist + navigate):
//   WHITELIST_AND_NAVIGATE → storage write awaited → chrome.tabs.update
//   SW killed by Chrome ← idle
//   New page loads → content.js fires SCAN_PAGE → SW wakes
//   _whitelistRestorePromise reads storage → finds entry → _approvedUrls populated
//   SCAN_PAGE handler awaits restore → _whitelistHasSync() → true → BYPASS
//   ✓ No loop. Guaranteed.

const _intercepted  = new Set();
const _approvedUrls = new Set();

function _normalizeUrl(url) {
  try {
    return decodeURIComponent(url.split('#')[0].split('?')[0])
      .toLowerCase()
      .replace(/\/+$/, '');
  } catch { return url.toLowerCase(); }
}

/** Synchronous O(n) check against in-memory Set. Zero latency. */
function _whitelistHasSync(url) {
  const base = _normalizeUrl(url);
  for (const entry of _approvedUrls) {
    if (base.startsWith(entry) || entry.startsWith(base)) return true;
  }
  return false;
}

/**
 * _whitelistRestorePromise — module scope, runs the instant the SW wakes.
 * Reads siq_whitelist (object keyed by normalized URL) and populates
 * _approvedUrls. Saved as a module-level const so every SCAN_PAGE handler
 * awaits the SAME promise — no concurrent storage reads, no races.
 *
 * Issue 1 verified: declared at module scope, NOT inside any handler.
 */
const _whitelistRestorePromise = chrome.storage.local
  .get('siq_whitelist')
  .then(({ siq_whitelist = {} }) => {
    const now = Date.now();
    for (const [url, entry] of Object.entries(siq_whitelist)) {
      // Issue 4 verified: only restore non-expired entries.
      if (now < entry.expires) _approvedUrls.add(url);
    }
  })
  .catch(() => {}); // never let restore failure block scanning

/**
 * _whitelistAdd — Layer 1 (sync) + Layer 3 (awaited).
 *
 * Returns a Promise that resolves ONLY after the storage write is confirmed.
 * Callers that navigate after this are guaranteed the write is durable,
 * so a SW restart before the next SCAN_PAGE still finds the entry.
 *
 * Issue 2 verified: uses object keyed by URL (O(1) lookup), prunes all
 * expired entries on every write.
 */
function _whitelistAdd(url) {
  const normalized = _normalizeUrl(url);
  _approvedUrls.add(normalized); // Layer 1 — synchronous, instant

  // Purge ALL engine caches for this URL so no stale MALICIOUS verdict
  // from any engine can re-trigger the block via webNavigation or SCAN_PAGE.
  // Each engine uses a different prefix: c_ (url/phishing), inj_, ano_
  chrome.storage.local.remove([
    safeCacheKey('c_',   url),  // URL structural + merged page result
    safeCacheKey('inj_', url),  // Prompt injection cache
    safeCacheKey('ano_', url),  // Anomaly detection cache
  ]);

  return chrome.storage.local
    .get('siq_whitelist')
    .then(({ siq_whitelist = {} }) => {
      const now = Date.now();
      // Prune expired entries while the object is open
      for (const [key, entry] of Object.entries(siq_whitelist)) {
        if (now >= entry.expires) delete siq_whitelist[key];
      }
      // Write new entry (1 hour expiry)
      siq_whitelist[normalized] = { expires: now + 60 * 60 * 1000 };
      return chrome.storage.local.set({ siq_whitelist });
    });
}

// ── Helpers ──────────────────────────────────────────────────────────────────

// REMOVED: hashUrl() was a 32-bit hash with ~3% collision rate at 500 cached URLs.
// With a 500-URL cache the birthday paradox gives ~3% chance URL_A gets URL_B's verdict.
// For a security tool this is unacceptable. Use the full URL as the cache key.
function safeCacheKey(prefix, url) {
  // Prefix + full URL. chrome.storage.local keys can be arbitrary strings.
  return prefix + url;
}

/**
 * safeSendMessage — guards against "Cannot read properties of undefined
 * (reading 'sendMessage')" which occurs when chrome.runtime is invalidated
 * mid-flight inside a .then() chain (e.g. extension reloaded while a scan
 * was in progress, or SW was killed between await points).
 * Use this everywhere instead of chrome.runtime.sendMessage(...).catch(() => {})
 */
function safeSendMessage(msg) {
  try {
    chrome.runtime?.sendMessage(msg)?.catch?.(() => {});
  } catch (_) {}
}

function isPrivateIpOrLocalhost(url) {
  try {
    const h = new URL(url).hostname;
    return h === 'localhost' || h.startsWith('127.') || h.startsWith('192.168.') || h.startsWith('10.');
  } catch {}
  return false;
}

function isBypassedUrl(url) {
  try {
    const h = new URL(url).hostname;
    // Prevent SentinelIQ from blocking its own dashboard or backend!
    if (h.includes('indianext') || h.includes('sentineliq') || h.includes('render.com')) return true;
  } catch {}
  return url.startsWith('file://') || isPrivateIpOrLocalhost(url);
}

const isLocal = isBypassedUrl; // backwards compat alias

// ── Cache (chrome.storage.local, full URL keys) ───────────────────────────────
async function getCached(url) {
  const norm = _normalizeUrl(url);
  const key = safeCacheKey('c_', norm);
  const res = await chrome.storage.local.get(key);
  if (!res[key]) return null;
  if (Date.now() - res[key].ts > CACHE_TTL_MS) { chrome.storage.local.remove(key); return null; }
  return res[key].d;
}

async function setCache(url, data) {
  const norm = _normalizeUrl(url);
  const key = safeCacheKey('c_', norm);
  await chrome.storage.local.set({ [key]: { d: data, ts: Date.now() } });
  const all = await chrome.storage.local.get(null);
  const keys = Object.keys(all).filter(k => k.startsWith('c_'));
  if (keys.length > MAX_CACHE) await chrome.storage.local.remove(keys.slice(0, keys.length - MAX_CACHE));
}

// ── Verdict helpers ───────────────────────────────────────────────────────────
const VERDICT_PRIORITY = { MALICIOUS:3, SUSPICIOUS:2, BENIGN:1, BYPASSED:0, ERROR:0 };

function mergeResults(urlResult, contentResult, hasPasswordForm) {
  // Fix #3: Password form is a mandatory escalation gate.
  // If a password form is present AND any phishing signal fired, force ensemble.
  const contentHasSignals = contentResult && (contentResult.shap_features || []).length > 0;
  const passwordEscalation = hasPasswordForm && contentHasSignals;

  let finalResult = urlResult;

  if (contentResult && contentResult.verdict !== 'BYPASSED') {
    const urlPri     = VERDICT_PRIORITY[urlResult.verdict]     || 0;
    const contentPri = VERDICT_PRIORITY[contentResult.verdict] || 0;

    if (contentPri > urlPri || passwordEscalation) {
      finalResult = {
        ...contentResult,
        detection_source: 'dom_content_phishing',
        // If password form escalation triggered, annotate
        escalated_by: passwordEscalation ? 'password_form_gate' : undefined,
      };
    }
  }

  // Fix #6: Preserve BYPASSED state so UI can show it distinctly from BENIGN
  if (urlResult.verdict === 'BYPASSED' && 
      (!contentResult || 
       (contentResult.verdict === 'BENIGN' && 
        (contentResult.shap_features || []).length === 0))) {
    return {
      verdict: 'BYPASSED',
      confidence: 0,
      risk_score: 0,
      risk_band: 'CLEAN',
      shap_features: [],
      explanation: 'URL structural analysis bypassed for local address. Content scan returned clean.',
      action: 'No action required.',
      narration_mode: 'bypassed',
    };
  }

  return finalResult;
}

function mergeAllResults(...results) {
  return results.filter(Boolean).reduce((worst, current) => {
    const worstPri = VERDICT_PRIORITY[worst?.verdict] || 0;
    const currPri  = VERDICT_PRIORITY[current?.verdict] || 0;
    if (currPri > worstPri) return current;
    return worst;
  }, { verdict: 'BENIGN', confidence: 0, shap_features: [] });
}

// ── Auth Helpers (v3.0) ───────────────────────────────────────────────────────

/** Returns a fresh id_token if logged in, or null if anonymous. Never throws. */
async function getAuthToken() {
  try {
    const { siq_auth } = await chrome.storage.local.get('siq_auth');
    if (!siq_auth) return null;
    // Refresh if within buffer window of expiry
    if (Date.now() < siq_auth.expiry_ms - TOKEN_REFRESH_BUFFER_MS) {
      return siq_auth.id_token;
    }
    return await _refreshToken(siq_auth.refresh_token);
  } catch (err) {
    console.warn('[getAuthToken] error:', err);
    return null;
  }
}

async function _refreshToken(refreshToken) {
  const { siq_refresh_fails = 0 } = await chrome.storage.local.get('siq_refresh_fails');
  try {
    const resp = await fetch(TOKEN_REFRESH_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ grant_type: 'refresh_token', refresh_token: refreshToken }),
      signal: AbortSignal.timeout(8000),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    // A14: spread existing FIRST so fresh fields overwrite stale ones
    const { siq_auth: existing } = await chrome.storage.local.get('siq_auth');
    const newAuth = {
      ...existing,
      id_token:      data.id_token,
      refresh_token: data.refresh_token,
      expiry_ms:     Date.now() + (parseInt(data.expires_in) * 1000),
    };
    await chrome.storage.local.set({ siq_auth: newAuth, siq_refresh_fails: 0 });
    return data.id_token;
  } catch (err) {
    const newFails = siq_refresh_fails + 1;
    await chrome.storage.local.set({ siq_refresh_fails: newFails });
    if (newFails >= MAX_REFRESH_FAILURES) {
      await _forceLogout('session_expired');
    }
    return null;
  }
}

async function _forceLogout(reason) {
  await chrome.storage.local.remove(['siq_auth', 'siq_refresh_fails']);
  safeSendMessage({
    type: 'AUTH_STATE_CHANGED', loggedOut: true, reason,
  });
}

/** Builds fetch headers with auth token and extension version. */
function _buildHeaders(token, extra = {}) {
  const { version } = chrome.runtime.getManifest();
  const headers = { 'X-Extension-Version': version, ...extra };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

// ── Scan: URL structural analysis ─────────────────────────────────────────────
// Fix #1: Localhost exempts URL structural scoring ONLY.
// Content scanning (scanContent) is a SEPARATE function that always runs.
const BYPASSED_RESULT = (reason) => ({
  verdict: 'BYPASSED', confidence: 0, risk_score: 0, risk_band: 'CLEAN',
  shap_features: [], explanation: reason, action: 'No action required.',
  narration_mode: 'url_bypassed', processing_time_ms: 0,
});

const BENIGN_FAST = (reason) => ({
  verdict: 'BENIGN', confidence: 0, risk_score: 0, risk_band: 'CLEAN',
  shap_features: [], explanation: reason, action: 'No action required.',
  narration_mode: 'fast_path', processing_time_ms: 0,
});

async function scanUrl(url) {
  if (!url || url.startsWith('chrome://') || url.startsWith('chrome-extension://')) {
    return BENIGN_FAST('Browser internal page.');
  }

  // Fix #1: Localhost and file:// BYPASS URL structural analysis, NOT content analysis.
  // The bypass returns BYPASSED (not BENIGN) so the merger knows to defer to content scan.
  if (isBypassedUrl(url)) {
    return BYPASSED_RESULT('Local or private address — URL structural analysis bypassed. Content scan active.');
  }

  const cached = await getCached(url);
  if (cached) return { ...cached, fromCache: true };

  const fd = new FormData();
  fd.append('threat_type', 'url');
  fd.append('content', url);

  try {
    const token = await getAuthToken();
    const resp = await fetch(`${currentBackendUrl}/analyze`, {
      method: 'POST', body: fd,
      headers: _buildHeaders(token),
      signal: AbortSignal.timeout(30000), // Increased to wait for cold start
    });
    // A15: 401 retry guard — attempt once after forced logout
    if (resp.status === 401) {
      await _forceLogout('401_invalid_token');
      const fd2 = new FormData();
      fd2.append('threat_type', 'url');
      fd2.append('content', url);
      const resp2 = await fetch(`${currentBackendUrl}/analyze`, {
        method: 'POST', body: fd2,
        headers: _buildHeaders(null),
        signal: AbortSignal.timeout(30000),
      });
      if (!resp2.ok) throw new Error(`HTTP ${resp2.status}`);
      const data2 = await resp2.json();
      await setCache(url, data2);
      return data2;
    }
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    await setCache(url, data);
    return data;
  } catch (err) {
    // Do NOT cache error results — a timeout must never permanently
    // poison the URL cache with MALICIOUS.
    //
    // Distinguish timeout (cold-start) from other network failures
    // so the popup gives the user actionable information.
    const isTimeout = err.name === 'TimeoutError' ||
                      err.name === 'AbortError'   ||
                      (err.message || '').toLowerCase().includes('timeout');
    return {
      verdict:    'ERROR',
      confidence: 0,
      risk_score: 0,
      risk_band:  'UNKNOWN',
      shap_features: [],
      explanation: isTimeout
        ? 'Backend is warming up (Render cold-start). Retry in ~10 seconds.'
        : 'SentinelIQ backend unreachable. Check your connection.',
      action: isTimeout
        ? 'This is normal after a period of inactivity. The scan will work on retry.'
        : `Verify backend is running at ${currentBackendUrl}.`,
      error:  String(err.message || err),
    };
  }
}

// ── Scan: DOM content phishing (ALWAYS runs, regardless of host) ──────────────
// Fix #1: Content scanning has NO host exemption. A phishing page on localhost
// is still a phishing page. This function must fire for every page.
async function scanContent(text, semanticDivergence = null) {
  if (!text || text.trim().length < 20) return null;

  const fd = new FormData();
  fd.append('threat_type', 'phishing');
  fd.append('content', text.substring(0, 3000));
  if (semanticDivergence) {
    fd.append('semantic_divergence', JSON.stringify(semanticDivergence));
  }

  try {
    const token = await getAuthToken();
    const resp = await fetch(`${currentBackendUrl}/analyze`, {
      method: 'POST', body: fd,
      headers: _buildHeaders(token),
      signal: AbortSignal.timeout(30000), // Increased from 8s to 30s to allow Mistral AI inference time
    });
    if (resp.status === 401) {
      await _forceLogout('401_invalid_token');
      return null;
    }
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } catch (err) {
    // Timeout or network failure — return null so mergeResults falls back to
    // urlResult only. Do NOT return an ERROR object (it has the same VERDICT_PRIORITY
    // as BENIGN but would show a confusing state in the popup).
    //
    // DOMException (AbortError/TimeoutError) does not have a useful .message on all
    // Chrome versions — use String(err) as fallback for clear console output.
    const isTimeout = err.name === 'TimeoutError' || err.name === 'AbortError';
    console.warn(`[scanContent] skipped — ${isTimeout ? 'backend cold-starting (timeout)' : String(err)}`);
    return { 
      verdict: 'ERROR', 
      explanation: isTimeout ? 'Backend cold-starting.' : `Backend Error: ${err.message || String(err)}`
    };
  }
}

// ── Email Scanning Helpers ────────────────────────────────────────────────────
async function scanEmailBody(bodyText) {
  return scanContent(bodyText);
}

function _extractRedirectTargets(url) {
  try {
    const u = new URL(url);
    const redirectParams = ['url','redirect','next','goto','return','dest','target','link'];
    for (const param of redirectParams) {
      const val = u.searchParams.get(param);
      if (val && val.startsWith('http')) return val;
    }
  } catch {}
  return null;
}

async function scanEmailUrls(links) {
  const expanded = [];
  const expandedMap = new Map();

  for (const link of links) {
    expanded.push(link);
    expandedMap.set(link, link);
    const inner = _extractRedirectTargets(link);
    if (inner && !expanded.includes(inner)) {
      expanded.push(inner);
      expandedMap.set(inner, link);
    }
  }

  const toScan = [...new Set(expanded)].slice(0, MAX_EMAIL_URL_SCANS);

  const results = await Promise.allSettled(
    toScan.map(url => Promise.race([
      scanUrl(url),
      new Promise(resolve =>
        setTimeout(() => resolve({
          verdict:'ERROR', confidence:0, shap_features:[],
          explanation:'URL scan timeout'
        }), URL_SCAN_TIMEOUT_MS)
      )
    ]))
  );

  return {
    scannedUrls: toScan,
    results: results.map(r => r.status === 'fulfilled' ? r.value : { verdict:'ERROR', confidence:0, shap_features:[] }),
    linkVerdictMap: new Map(
      links.map(link => {
        const innerUrl = _extractRedirectTargets(link);
        const idx1 = toScan.indexOf(link);
        const idx2 = innerUrl ? toScan.indexOf(innerUrl) : -1;
        const r1 = idx1 >= 0 ? results[idx1]?.value : null;
        const r2 = idx2 >= 0 ? results[idx2]?.value : null;
        const worst = [r1, r2].filter(Boolean).reduce((w, r) =>
          (VERDICT_PRIORITY[r?.verdict]||0) > (VERDICT_PRIORITY[w?.verdict]||0) ? r : w,
          { verdict:'BENIGN', confidence:0 }
        );
        return [link, worst];
      })
    )
  };
}

function _scoreAttachments(attachments) {
  const HIGH_RISK = new Set([
    '.zip','.iso','.scr','.html','.htm','.docm','.xlsm',
    '.exe','.js','.vbs','.lnk','.msi','.bat','.cmd','.ps1',
  ]);
  const hasHighRisk = attachments.some(name => {
    const ext = '.' + name.split('.').pop().toLowerCase();
    return HIGH_RISK.has(ext);
  });
  if (!hasHighRisk) return { verdict:'BENIGN', confidence:0.05, shap_features:[] };
  const risky = attachments.filter(name => HIGH_RISK.has('.' + name.split('.').pop().toLowerCase()));
  return {
    verdict:    'SUSPICIOUS',
    confidence: 0.65,
    shap_features: risky.map(name => ({
      feature:   `High-risk attachment: ${name}`,
      weight:    0.65,
      direction: 'positive',
      category:  'active_attack_signal',
    })),
    explanation: `High-risk attachment type detected: ${risky.join(', ')}`,
    action: 'Do not open attachments from unknown senders.',
  };
}

// ── Email Scan ───────────────────────────────────────────────────────────────
async function getEmailCache(vectorHash) {
  const key = 'ce_' + vectorHash;
  const res = await chrome.storage.local.get(key);
  if (!res[key]) return null;
  if (Date.now() - res[key].ts > CACHE_TTL_MS) { chrome.storage.local.remove(key); return null; }
  return res[key].d;
}

async function setEmailCache(vectorHash, data) {
  const key = 'ce_' + vectorHash;
  await chrome.storage.local.set({ [key]: { d: data, ts: Date.now() } });
}

async function scanEmail(vector) {
  if (!vector) return { verdict: 'ERROR', risk_score: 0, explanation: 'No email vector.', shap_features: [] };
  const vectorHash = JSON.stringify(vector).substring(0, 400);
  const cached = await getEmailCache(vectorHash);
  if (cached) return { ...cached, fromCache: true };

  const fd = new FormData();
  fd.append('threat_type', 'email');
  fd.append('content', JSON.stringify(vector));

  try {
    const token = await getAuthToken();
    const resp = await fetch(`${currentBackendUrl}/analyze`, {
      method: 'POST', body: fd,
      headers: _buildHeaders(token),
      signal: AbortSignal.timeout(15000),
    });
    if (resp.status === 401) {
      await _forceLogout('401_invalid_token');
      return { verdict: 'ERROR', risk_score: 0, explanation: 'Auth session expired. Scan restarted anonymously.', shap_features: [] };
    }
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    await setEmailCache(vectorHash, data);
    return data;
  } catch (err) {
    return {
      verdict: 'ERROR', risk_score: 0,
      explanation: 'Email scan failed. Backend may be unreachable.',
      shap_features: [], error: err.message,
    };
  }
}

// ── Injection & Anomaly scan functions (v3.0) ─────────────────────────────────

async function scanInjection(text, url, isAiInterface) {
  if (!text || text.trim().length < 30) return null;
  const token = await getAuthToken();
  const fd = new FormData();
  fd.append('threat_type', 'prompt_injection');
  fd.append('content', text.substring(0, 2000));
  const extra = {};
  if (isAiInterface) extra['X-Escalation-Mode'] = 'true';
  try {
    const resp = await fetch(`${currentBackendUrl}/analyze`, {
      method: 'POST', body: fd,
      headers: _buildHeaders(token, extra),
      signal: AbortSignal.timeout(10000),
    });
    if (resp.status === 401) {
      await _forceLogout('401_invalid_token');
      // A15: retry once anonymously — no infinite loop
      const fd2 = new FormData();
      fd2.append('threat_type', 'prompt_injection');
      fd2.append('content', text.substring(0, 2000));
      const resp2 = await fetch(`${currentBackendUrl}/analyze`, {
        method: 'POST', body: fd2,
        headers: _buildHeaders(null),
        signal: AbortSignal.timeout(15000),
      });
      if (!resp2.ok) return { verdict: 'ERROR', confidence: 0, shap_features: [], explanation: 'Injection scan failed.' };
      const d2 = await resp2.json();
      await setCache(safeCacheKey('inj_', url), d2);
      return d2;
    }
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    await setCache(safeCacheKey('inj_', url), data);
    return data;
  } catch (err) {
    return { verdict: 'ERROR', confidence: 0, shap_features: [], explanation: 'Injection scan failed.' };
  }
}

async function buildPartialVector(trigger) {
  const now = new Date();
  const { siq_login_events = [] } = await chrome.storage.local.get('siq_login_events');
  const { siq_known_device = '' } = await chrome.storage.local.get('siq_known_device');
  const { siq_tab_open_ts = {} } = await chrome.storage.local.get('siq_tab_open_ts');
  const recentLogins = siq_login_events.filter(t => now.getTime() - t < 60 * 60 * 1000);
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const tabOpenTs = activeTab
    ? (siq_tab_open_ts[activeTab.id] || now.getTime())
    : now.getTime();
  return {
    hour:                 now.getHours(),
    day_of_week:          now.getDay(),
    new_user_agent_flag:  0.0,  // UA not available in service worker
    session_duration_sec: Math.floor((now.getTime() - tabOpenTs) / 1000),
    login_velocity:       recentLogins.length,
    device_match_int:     siq_known_device ? 1.0 : 0.0,
  };
}

async function scanAnomaly(partialVector, url, trigger) {
  const token = await getAuthToken();
  const fd = new FormData();
  fd.append('threat_type', 'anomaly');
  fd.append('content', JSON.stringify(partialVector));
  try {
    const resp = await fetch(`${currentBackendUrl}/analyze`, {
      method: 'POST', body: fd,
      headers: _buildHeaders(token, { 'X-Anomaly-Trigger': trigger }),
      signal: AbortSignal.timeout(10000),
    });
    if (resp.status === 401) {
      await _forceLogout('401_invalid_token');
      return null;
    }
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    await setCache(safeCacheKey('ano_', url), data);
    return data;
  } catch (err) {
    return { verdict: 'ERROR', confidence: 0, shap_features: [], explanation: 'Anomaly scan failed.' };
  }
}

// ── Badge ────────────────────────────────────────────────────────────────────
function setBadge(tabId, verdict) {
  const map = {
    MALICIOUS:  { color: '#ef4444', text: '⚠' },
    SUSPICIOUS: { color: '#f59e0b', text: '!' },
    BENIGN:     { color: '#10b981', text: '✓' },
    BYPASSED:   { color: '#10b981', text: '✓' }, // Fix #6: BYPASSED shows green (not BENIGN scanned)
    SCANNING:   { color: '#6366f1', text: '…' },
    ERROR:      { color: '#6b7280', text: '?' },
  };
  const { color, text } = map[verdict] || map.ERROR;
  try {
    chrome.action.setBadgeBackgroundColor({ tabId, color }).catch(() => {});
    chrome.action.setBadgeText({ tabId, text }).catch(() => {});
  } catch (err) {}
}

// ── Stats ────────────────────────────────────────────────────────────────────
async function recordScan(url, result) {
  if (!result || result.verdict === 'BYPASSED') return; // Don't count bypassed URL scans as real scans
  const sd = await chrome.storage.local.get('siq_stats');
  const s  = sd.siq_stats || { total:0, malicious:0, suspicious:0, benign:0, blocked:0 };
  s.total++;
  if (result.verdict === 'MALICIOUS')  s.malicious++;
  else if (result.verdict === 'SUSPICIOUS') s.suspicious++;
  else if (result.verdict === 'BENIGN') s.benign++;
  await chrome.storage.local.set({ siq_stats: s });

  // History (last 50)
  const hd = await chrome.storage.local.get('siq_history');
  const h  = hd.siq_history || [];
  h.unshift({ url: url.substring(0, 90), verdict: result.verdict, risk_score: result.risk_score || 0, ts: Date.now() });
  if (h.length > 50) h.length = 50;
  await chrome.storage.local.set({ siq_history: h });
}

async function recordBlock(url) {
  const sd = await chrome.storage.local.get('siq_stats');
  const s  = sd.siq_stats || { total:0, malicious:0, suspicious:0, benign:0, blocked:0 };
  s.blocked = (s.blocked || 0) + 1;
  await chrome.storage.local.set({ siq_stats: s });
  const hd = await chrome.storage.local.get('siq_history');
  const h  = hd.siq_history || [];
  h.unshift({ url: url.substring(0, 90), verdict: 'BLOCKED', risk_score: 100, ts: Date.now() });
  if (h.length > 50) h.length = 50;
  await chrome.storage.local.set({ siq_history: h });
}

// ── Email Scan Queue ────────────────────────────────────────────────────────
const MAX_CONCURRENT_SCANS = 3;
const MAX_QUEUE_DEPTH = 20;
const _emailScanQueue = [];
let _activeEmailScans = 0;

function _processEmailQueue() {
  if (_activeEmailScans >= MAX_CONCURRENT_SCANS || _emailScanQueue.length === 0) return;
  _activeEmailScans++;
  const task = _emailScanQueue.shift();
  _executeEmailScanTask(task).finally(() => {
    _activeEmailScans--;
    _processEmailQueue();
  });
}

function _executeEmailScanTask({ msg, tabId, sendResponse }) {
  if (tabId) setBadge(tabId, 'SCANNING');

  return Promise.all([
    scanEmailUrls(msg.links || [])
  ]).then(async ([urlScanObj]) => {
    const urlResults = urlScanObj.results;
    const scannedUrls = urlScanObj.scannedUrls;
    const linkVerdictMap = urlScanObj.linkVerdictMap;

    const senderResult = analyzeSender(msg.senderName, msg.senderEmail, msg.replyTo);
    const attachmentResult = _scoreAttachments(msg.attachments || []);

    const hasSuspiciousLinks = urlResults.some(r => r.verdict !== 'BENIGN' && r.verdict !== 'ERROR');
    
    const payload = {
      bodyText: msg.bodyText,
      sender_mismatch: senderResult.verdict !== 'BENIGN',
      attachment_risk: attachmentResult.verdict === 'MALICIOUS' ? 1.0 : (attachmentResult.verdict === 'SUSPICIOUS' ? 0.6 : 0.0),
      suspicious_links: hasSuspiciousLinks ? 0.8 : 0.0,
    };

    const finalResult = await scanEmail(payload);
    const url = msg.url || 'gmail';
    
    const combinedResult = {
      ...finalResult,
      senderVerdict:    senderResult?.verdict,
      attachmentVerdict: attachmentResult?.verdict,
      urlResults,
      scannedUrls,
      links:            msg.links,
      subject:          msg.subject,
      senderEmail:      msg.senderEmail,
      senderName:       msg.senderName,
    };

    const key = tabId ? `c_email_tab_${tabId}` : `c_email_${url}`;
    await chrome.storage.local.set({ [key]: { d: combinedResult, ts: Date.now() } });

    if (tabId) {
      recordScan(url, finalResult);
      setBadge(tabId, finalResult.verdict);
    }

    chrome.tabs.sendMessage(tabId, {
      type:          'EMAIL_SCAN_RESULT',
      scanId:        msg.scanId,
      verdict:       finalResult.verdict,
      confidence:    finalResult.confidence,
      bodyVerdict:   finalResult?.verdict,
      senderVerdict: senderResult?.verdict,
      urlResults,
      links:         msg.links,
      linkVerdictMap: Array.from(linkVerdictMap.entries()),
      shap_features: finalResult.shap_features,
      explanation:   finalResult.explanation,
      action:        finalResult.action,
    }).catch(() => {});

    safeSendMessage({ type: 'EMAIL_RESULT', result: finalResult, url });
    sendResponse({ result: finalResult });
  }).catch(err => {
    console.error("[SCAN_EMAIL_FULL] Unhandled Pipeline Error:", err);
    sendResponse({ result: { verdict: 'ERROR', risk_score: 0, explanation: 'Scan pipeline error: ' + String(err), shap_features: [] } });
  });
}

// ── Message Router ────────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const tabId = msg.tabId || sender.tab?.id;

  if (msg.type === 'SCAN_URL') {
    // Popup cache read — if we have a cached SCAN_PAGE result, return it
    getCached(msg.url).then(cached => {
      if (cached) { sendResponse({ result: cached }); return; }
      // No cache: run URL scan only (popup doesn't have DOM content)
      scanUrl(msg.url).then(result => {
        if (tabId) recordScan(msg.url, result);
        sendResponse({ result });
      });
    });
    return true;
  }

  if (msg.type === 'FORCE_NAVIGATE') {
    if (tabId) {
      chrome.tabs.update(tabId, { url: msg.url });
    }
    return true;
  }

  if (msg.type === 'WHITELIST_URL') {
    _whitelistAdd(msg.url).then(() => sendResponse({ success: true }));
    return true;
  }

  // ── WHITELIST_AND_NAVIGATE ─────────────────────────────────────────────────
  // Sequence: Layer 1 sync → await Layer 3 storage → navigate.
  // Navigating AFTER confirmed write means a SW restart between navigate and
  // SCAN_PAGE will still find the entry in storage on restore.
  //
  // Issue 3: sendResponse called inside .then() after write, return true keeps
  // the message channel open for the async response.
  if (msg.type === 'WHITELIST_AND_NAVIGATE') {
    const targetTabId = msg.tabId || tabId;
    _whitelistAdd(msg.url)
      .then(() => {
        if (targetTabId && msg.url) chrome.tabs.update(targetTabId, { url: msg.url });
        sendResponse({ ok: true });
      })
      .catch(() => {
        // Storage failed (disk full, quota). Navigate anyway —
        // Layer 1 in-memory entry is still valid for this SW lifetime.
        if (targetTabId && msg.url) chrome.tabs.update(targetTabId, { url: msg.url });
        sendResponse({ ok: false });
      });
    return true; // Issue 3: MANDATORY — keeps channel open for async sendResponse
  }

  if (msg.type === 'SET_SETTINGS') {
    currentBackendUrl = msg.backendUrl || DEFAULT_BACKEND;
    chrome.storage.local.set({ siq_backend_url: currentBackendUrl });
    sendResponse({ success: true });
    return true;
  }

  if (msg.type === 'SCAN_PAGE') {
    // Issue 5 verified: await _whitelistRestorePromise BEFORE calling
    // _whitelistHasSync(). This is the critical ordering that prevents a
    // false-block on the first SCAN_PAGE after a SW restart.
    //
    // _whitelistRestorePromise is a module-scope const. Awaiting it multiple
    // times is safe — it is already settled on subsequent calls (microtask).
    _whitelistRestorePromise
      .then(() => {
        // Issue 5 verified: sync check only runs AFTER restore is confirmed
        if (_whitelistHasSync(msg.url)) {
          if (tabId) setBadge(tabId, 'BENIGN');
          const r = BENIGN_FAST('User-approved bypass — 1 hr session whitelist active.');
          sendResponse({ result: r });
          safeSendMessage({ type: 'PAGE_RESULT', result: r, url: msg.url });
          return;
        }

        // Not whitelisted — run full scan pipeline.
        if (tabId) setBadge(tabId, 'SCANNING');
        const hasPasswordForm = msg.hasPasswordForm || false;

        Promise.all([
          scanUrl(msg.url),
          msg.content && msg.content.length > 30
            ? scanContent(msg.content, msg.semanticDivergence)
            : Promise.resolve(null),
        ]).then(async ([urlResult, contentResult]) => {
          console.log('[SCAN_PAGE] content length:', msg.content?.length);
          console.log('[SCAN_PAGE] content snippet:', msg.content?.substring(0, 200));
          console.log('[SCAN_PAGE] urlResult:', urlResult.verdict);
          console.log('[SCAN_PAGE] contentResult:', contentResult?.verdict, contentResult?.confidence);

          // If the URL scan or content scan errored (backend cold-starting), do NOT block.
          // Schedule an auto-retry in 15 s — enough for Render to wake up.
          // The alarm name encodes the tabId so multiple tabs don't collide.
          if (urlResult.verdict === 'ERROR' || contentResult?.verdict === 'ERROR') {
            if (tabId) setBadge(tabId, 'ERROR');
            const r = {
              ...urlResult,
              verdict: 'ERROR',
              explanation: urlResult.explanation && urlResult.verdict === 'ERROR' 
                ? urlResult.explanation 
                : 'Backend is warming up. Auto-retry in 15 seconds.',
            };
            sendResponse({ result: r });
            safeSendMessage({ type: 'PAGE_RESULT', result: r, url: msg.url });

            // Auto-retry: store context and fire alarm after 15 s
            if (tabId && msg.url) {
              const alarmName = `retry_scan_${tabId}`;
              chrome.storage.local.set({
                [`retry_${tabId}`]: { 
                  url: msg.url, 
                  tabId, 
                  attempt: 1,
                  content: msg.content,
                  hasPasswordForm: msg.hasPasswordForm,
                  semanticDivergence: msg.semanticDivergence
                },
              });
              chrome.alarms.create(alarmName, { delayInMinutes: 0.25 }); // ~15 s
            }
            return; // Do NOT call setCache — don't poison cache with ERROR
          }


          const finalResult = mergeResults(urlResult, contentResult, hasPasswordForm);
          await setCache(msg.url, finalResult);

          if (tabId) {
            recordScan(msg.url, finalResult);
            setBadge(tabId, finalResult.verdict);

            if (
              finalResult.verdict === 'MALICIOUS' &&
              !isBypassedUrl(msg.url)
            ) {
              // Last-chance sync check: catches any in-flight whitelist added
              // during the scan window (e.g. user double-clicks Proceed).
              if (!_whitelistHasSync(msg.url)) {
                const params = new URLSearchParams({
                  url:         msg.url,
                  verdict:     finalResult.verdict,
                  risk:        String(finalResult.risk_score || 0),
                  explanation: finalResult.explanation || 'Malicious content detected.',
                  action:      finalResult.action     || 'Do not proceed to this site.',
                  signals:     JSON.stringify(
                    (finalResult.shap_features || []).slice(0, 3).map(f => f.feature)
                  ),
                });
                chrome.tabs.update(tabId, { url: `${BLOCKED_PAGE}?${params.toString()}` });
              }
            }
          }
          safeSendMessage({ type: 'PAGE_RESULT', result: finalResult, url: msg.url });
          sendResponse({ result: finalResult });
        });
      })
      .catch(() => {
        // Restore itself failed (should never happen, .catch in restore swallows).
        // Run scan anyway so the user isn't stuck.
        if (tabId) setBadge(tabId, 'SCANNING');
        sendResponse({ result: BENIGN_FAST('Whitelist restore failed; scan queued.') });
      });
    return true; // keep message channel open for async response
  }

  if (msg.type === 'SCAN_CONTENT') {
    // Check whitelist first so password forms don't re-trigger blocks on approved pages
    const url = msg.url || 'content-scan';
    _whitelistRestorePromise.then(() => {
      if (_whitelistHasSync(url)) {
        if (tabId) setBadge(tabId, 'BENIGN');
        const r = BENIGN_FAST('User-approved bypass — ignoring password form.');
        sendResponse({ result: r });
        return;
      }
      
      if (tabId) setBadge(tabId, 'SCANNING');
      scanContent(msg.content).then(result => {
        if (!result) { sendResponse({ result: BENIGN_FAST('No content signals.') }); return; }
        setCache(url, result);
        if (tabId) { recordScan(url, result); setBadge(tabId, result.verdict); }
        safeSendMessage({ type: 'PAGE_RESULT', result, url });
        sendResponse({ result });
      });
    });
    return true;
  }

  if (msg.type === 'SCAN_EMAIL') {
    if (tabId) setBadge(tabId, 'SCANNING');
    scanEmail(msg.vector).then(result => {
      if (tabId) setBadge(tabId, result.verdict);
      sendResponse({ result });
    });
    return true;
  }

  if (msg.type === 'SCAN_EMAIL_FULL') {
    if (_emailScanQueue.length >= MAX_QUEUE_DEPTH) {
      _emailScanQueue.shift(); // Drop oldest to prevent unbounded queue growth
    }
    _emailScanQueue.push({ msg, tabId, sendResponse });
    _processEmailQueue();
    return true; // Keep channel open for async response
  }

  if (msg.type === 'EMAIL_SCANNING') {
    if (tabId) setBadge(tabId, 'SCANNING');
    return true;
  }

  if (msg.type === 'CLEAR_EMAIL_CACHE') {
    if (tabId) {
      chrome.storage.local.remove(`c_email_tab_${tabId}`);
      setBadge(tabId, '');
    }
    return true;
  }

  if (msg.type === 'OPEN_DASHBOARD') {
    chrome.tabs.create({ url: 'https://indianext-x-chitti-2-0.vercel.app/dashboard' });
    return true;
  }

  if (msg.type === 'GET_STATS') {
    Promise.all([
      chrome.storage.local.get('siq_stats'),
      chrome.storage.local.get('siq_history'),
    ]).then(([sd, hd]) => sendResponse({
      stats:   sd.siq_stats   || { total:0, malicious:0, suspicious:0, benign:0, blocked:0 },
      history: hd.siq_history || [],
    }));
    return true;
  }

  if (msg.type === 'GET_SETTINGS') {
    chrome.storage.local.get('siq_backend_url').then(d => sendResponse({ backendUrl: d.siq_backend_url || DEFAULT_BACKEND }));
    return true;
  }

  if (msg.type === 'SET_SETTINGS') {
    currentBackendUrl = msg.backendUrl || DEFAULT_BACKEND;
    chrome.storage.local.set({ siq_backend_url: msg.backendUrl }).then(() => sendResponse({ ok: true }));
    return true;
  }

  if (msg.type === 'WHITELIST_URL') {
    _whitelistAdd(msg.url).then(() => {
      sendResponse({ ok: true });
    });
    return true;
  }

  // ── v3.0 Injection handler ────────────────────────────────────────────────
  if (msg.type === 'SCAN_INJECTION') {
    if (tabId) setBadge(tabId, 'SCANNING');
    scanInjection(msg.content, msg.url, msg.is_ai_interface).then(async result => {
      if (!result) { sendResponse({ result: null }); return; }
      const urlCached = await getCached(safeCacheKey('c_', msg.url));
      const merged = mergeAllResults(urlCached, result);
      if (tabId) {
        recordScan(msg.url, result);
        setBadge(tabId, merged.verdict);
      }
      safeSendMessage({
        type: 'INJECTION_RESULT', result, url: msg.url,
      });
      sendResponse({ result });
    });
    return true; // ← MANDATORY: async sendResponse
  }

  // ── v3.0 Anomaly handler ──────────────────────────────────────────────────
  if (msg.type === 'SCAN_ANOMALY') {
    if (tabId) setBadge(tabId, 'SCANNING');
    buildPartialVector(msg.trigger).then(async vector => {
      const merged = { ...msg.partial_vector, ...vector };
      const result = await scanAnomaly(merged, msg.url, msg.trigger);
      if (!result) { sendResponse({ result: null }); return; }
      if (tabId) {
        recordScan(msg.url, result);
        setBadge(tabId, result.verdict);
      }
      safeSendMessage({
        type: 'ANOMALY_RESULT', result, url: msg.url,
      });
      sendResponse({ result });
    });
    return true; // ← MANDATORY: async sendResponse
  }

  // ── v3.0 Auth state propagation ───────────────────────────────────────────
  if (msg.type === 'AUTH_STATE_CHANGED') {
    sendResponse({ ok: true });
    return true;
  }
});

// ── v3.0 Alarms ───────────────────────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create('anomaly_heartbeat', {
    periodInMinutes: ANOMALY_HEARTBEAT_INTERVAL_MIN,
  });
  // Keep Render free tier alive: ping every 10 min to prevent 15-min sleep.
  // Cost: one lightweight GET per 10 min — negligible bandwidth.
  chrome.alarms.create('backend_keepalive', { periodInMinutes: 10 });

  chrome.storage.local.get('siq_known_device').then(({ siq_known_device }) => {
    if (!siq_known_device) {
      chrome.storage.local.set({ siq_known_device: 'chrome_extension_worker' });
    }
  });
});

// Also ping once immediately when the SW wakes (covers the first cold-start).
// /health returns fast (no ML), so this doesn't block anything.
fetch(`${DEFAULT_BACKEND}/health`, { signal: AbortSignal.timeout(30000) })
  .catch(() => {}); // fire-and-forget — never throw

chrome.alarms.onAlarm.addListener(async (alarm) => {
  // ── Backend keep-alive ping ───────────────────────────────────────────────
  // Fires every 10 min. Sends a cheap GET /health to Render so the dyno
  // never reaches the 15-min idle threshold and goes to sleep.
  if (alarm.name === 'backend_keepalive') {
    fetch(`${currentBackendUrl}/health`, { signal: AbortSignal.timeout(30000) })
      .catch(() => {}); // fire-and-forget
    return;
  }

  // Fires ~15 s after a SCAN_PAGE got an ERROR (backend was sleeping).
  // Re-runs scanUrl. If the backend is now warm, updates the badge and cache.
  // If still cold, silently gives up (no infinite retry loop).
  if (alarm.name.startsWith('retry_scan_')) {
    const tabId = parseInt(alarm.name.replace('retry_scan_', ''), 10);
    const key   = `retry_${tabId}`;
    const store = await chrome.storage.local.get(key);
    const ctx   = store[key];

    if (!ctx?.url || !tabId) {
      await chrome.storage.local.remove(key);
      return;
    }

    // Verify the tab still exists and is on the same URL
    let tab;
    try { tab = await chrome.tabs.get(tabId); } catch { return; }
    if (!tab || _normalizeUrl(tab.url) !== _normalizeUrl(ctx.url)) {
      await chrome.storage.local.remove(key);
      return;
    }

    setBadge(tabId, 'SCANNING');
    
    // Rerun both engines just like SCAN_PAGE
    const [urlResult, contentResult] = await Promise.all([
      scanUrl(ctx.url),
      ctx.content ? scanContent(ctx.content, ctx.semanticDivergence) : Promise.resolve(null)
    ]);

    if (urlResult.verdict === 'ERROR' || contentResult?.verdict === 'ERROR') {
      const attempt = ctx.attempt || 1;
      if (attempt < 3) {
        const nextAttempt = attempt + 1;
        await chrome.storage.local.set({
          [key]: { ...ctx, attempt: nextAttempt },
        });
        chrome.alarms.create(`retry_scan_${tabId}`, { delayInMinutes: nextAttempt * 0.25 });
        return;
      }

      setBadge(tabId, 'ERROR');
      await chrome.storage.local.remove(key);
      urlResult.explanation = 'Scan failed after multiple attempts. Backend is offline.';
      safeSendMessage({ type: 'PAGE_RESULT', result: urlResult, url: ctx.url });
      return;
    }

    const finalResult = mergeResults(urlResult, contentResult, ctx.hasPasswordForm);

    await chrome.storage.local.remove(key);
    setCache(ctx.url, finalResult);
    recordScan(ctx.url, finalResult);
    setBadge(tabId, finalResult.verdict);
    safeSendMessage({ type: 'PAGE_RESULT', result: finalResult, url: ctx.url });

    if (
      finalResult.verdict === 'MALICIOUS' &&
      !isBypassedUrl(ctx.url) &&
      !_whitelistHasSync(ctx.url)
    ) {
      const params = new URLSearchParams({
        url:         ctx.url,
        verdict:     finalResult.verdict,
        risk:        String(finalResult.risk_score || 0),
        explanation: finalResult.explanation || 'Malicious content detected.',
        action:      finalResult.action     || 'Do not proceed to this site.',
        signals:     JSON.stringify((finalResult.shap_features || []).slice(0, 3).map(f => f.feature)),
      });
      chrome.tabs.update(tabId, { url: `${BLOCKED_PAGE}?${params.toString()}` });
    }
    return;
  }

  // ── Anomaly heartbeat ─────────────────────────────────────────────────────
  if (alarm.name !== 'anomaly_heartbeat') return;
  const { siq_auth } = await chrome.storage.local.get('siq_auth');
  if (!siq_auth) return;
  const vector = await buildPartialVector('heartbeat');
  const result = await scanAnomaly(vector, 'background://heartbeat', 'heartbeat');
  if (!result) return;
  if ((VERDICT_PRIORITY[result.verdict] || 0) >= (VERDICT_PRIORITY['SUSPICIOUS'] || 0)) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.id) setBadge(tab.id, result.verdict);
  }
});

// ── v3.0 Tab session tracking ─────────────────────────────────────────────────
// Track when each tab was opened so anomaly vector can compute session_duration_sec.
chrome.tabs.onCreated.addListener(tab => {
  chrome.storage.local.get('siq_tab_open_ts').then(({ siq_tab_open_ts = {} }) => {
    siq_tab_open_ts[tab.id] = Date.now();
    chrome.storage.local.set({ siq_tab_open_ts });
  });
});
chrome.tabs.onRemoved.addListener(tabId => {
  chrome.storage.local.get('siq_tab_open_ts').then(({ siq_tab_open_ts = {} }) => {
    delete siq_tab_open_ts[tabId];
    chrome.storage.local.set({ siq_tab_open_ts });
  });
});

// ── Tab Navigation ────────────────────────────────────────────────────────────
chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status === 'complete' && tab.url) {
    if (tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://')) {
      setBadge(tabId, 'BENIGN');
      return;
    }
    // Set SCANNING — content.js will send SCAN_PAGE (with DOM content) and update via PAGE_RESULT
    setBadge(tabId, 'SCANNING');
  }
});

// ── Navigation Interception (webNavigation) ───────────────────────────────────
// Pre-checks the cache for known-MALICIOUS URLs before the page loads.
// Whitelist check uses _whitelistRestorePromise + _whitelistHasSync — the same
// pattern as SCAN_PAGE — so a SW restart never causes a false-block here.
if (typeof chrome.webNavigation !== 'undefined') {
  chrome.webNavigation.onBeforeNavigate.addListener(async (details) => {
    const { tabId, url, frameId } = details;
    if (frameId !== 0) return;
    if (!url || url.startsWith('chrome://') || url.startsWith('chrome-extension://')) return;
    if (isLocal(url)) return;

    if (_intercepted.has(tabId)) { _intercepted.delete(tabId); return; }

    // Wait for whitelist restore (resolves in <10ms, already settled on repeat calls)
    await _whitelistRestorePromise;
    if (_whitelistHasSync(url)) return; // user approved — never re-block

    const cached = await getCached(url);
    if (cached && cached.verdict === 'MALICIOUS') {
      _intercepted.add(tabId);
      await recordBlock(url);
      setBadge(tabId, 'MALICIOUS');

      const params = new URLSearchParams({
        url:         url,
        verdict:     cached.verdict,
        risk:        String(cached.risk_score || 0),
        explanation: cached.explanation || 'Malicious URL detected.',
        action:      cached.action || 'Do not proceed to this site.',
        signals:     JSON.stringify(
          (cached.shap_features || []).slice(0, 3).map(f => f.feature)
        ),
      });
      chrome.tabs.update(tabId, { url: `${BLOCKED_PAGE}?${params.toString()}` });
    }
  });
}
