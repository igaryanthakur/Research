(function () {
  // ── Parse URL params ────────────────────────────────────────────────────────
  const params      = new URLSearchParams(location.search);
  const destUrl     = params.get('url') || '';           // URLSearchParams.get() already decodes
  const risk        = parseInt(params.get('risk') || '0', 10);
  const explanation = params.get('explanation') || 'This destination has been classified as malicious by SentinelIQ threat engines.';
  const action      = params.get('action')      || 'Do not proceed. Return to a safe page and report this URL to your IT team.';

  let signals = [];
  try { signals = JSON.parse(params.get('signals') || '[]'); } catch {}

  // ── Populate static content ─────────────────────────────────────────────────
  document.getElementById('risk-num').textContent    = risk;
  document.getElementById('url-display').textContent = destUrl || 'Unknown destination';
  document.getElementById('url-display').title       = destUrl;
  document.getElementById('explanation').textContent  = explanation;
  document.getElementById('action-text').textContent  = action;
  document.getElementById('timestamp').textContent    = new Date().toLocaleTimeString();

  setTimeout(() => {
    document.getElementById('risk-bar').style.width = Math.min(risk, 100) + '%';
  }, 200);

  // ── Signals ─────────────────────────────────────────────────────────────────
  const SIGNAL_ICONS = {
    'Account Threat':        '👤',
    'Urgency Deadline':      '⏳',
    'Language Manipulation': '🧠',
    'Credential Harvest':    '🔑',
    'Brand Spoof':           '🎭',
    'Malicious URL pattern': '🔗',
  };
  const sigContainer = document.getElementById('signals-container');
  const sigList = signals.length ? signals : ['Malicious URL pattern'];
  sigContainer.innerHTML = sigList.map(s => {
    const icon = SIGNAL_ICONS[s] || '⚡';
    return `<span class="sig-chip"><span class="sig-icon">${icon}</span>${s}</span>`;
  }).join('');

  // ── Custom checkbox ──────────────────────────────────────────────────────────
  let consented      = false;
  let countdownTimer = null;
  let countdownSec   = 5;
  let navigating     = false;

  const consentBox  = document.getElementById('consent-box');
  const consentRow  = document.getElementById('consent-row');
  const proceedBtn  = document.getElementById('proceed-btn');
  const proceedZone = document.getElementById('proceed-zone');
  const countdownEl = document.getElementById('countdown-badge');

  function toggleConsent() {
    consented = !consented;
    consentBox.classList.toggle('checked', consented);
    proceedZone.classList.toggle('active', consented);
    if (consented) {
      startCountdown();
    } else {
      stopCountdown();
      proceedBtn.classList.remove('ready');
      proceedBtn.disabled = true;
    }
  }

  consentBox.addEventListener('click', toggleConsent);
  consentRow.addEventListener('click', (e) => {
    if (e.target === consentBox) return;
    toggleConsent();
  });

  function startCountdown() {
    countdownSec = 5;
    countdownEl.textContent = countdownSec + 's';
    proceedBtn.disabled = true;
    proceedBtn.classList.remove('ready');
    countdownTimer = setInterval(() => {
      countdownSec--;
      countdownEl.textContent = countdownSec + 's';
      if (countdownSec <= 0) {
        stopCountdown();
        if (consented) enableProceed();
      }
    }, 1000);
  }

  function stopCountdown() {
    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
  }

  function enableProceed() {
    proceedBtn.disabled = false;
    proceedBtn.classList.add('ready');
    countdownEl.textContent = 'GO';
  }

  // ── Proceed: guaranteed loop-free bypass ────────────────────────────────────
  // Architecture:
  //   1. Get our own tab ID synchronously via chrome.tabs.getCurrent().
  //   2. Send ONE message: WHITELIST_AND_NAVIGATE(url, tabId) to background.
  //   3. Background atomically:
  //        a. Adds URL to _approvedUrls in-memory Set (SYNCHRONOUS — no storage wait).
  //        b. Fires chrome.tabs.update() to navigate our tab.
  //   4. When content.js fires SCAN_PAGE on the newly loaded page, background's
  //      sync _whitelistHasSync() returns true IMMEDIATELY — block is bypassed.
  //   No race condition. No loop.
  proceedBtn.addEventListener('click', () => {
    if (proceedBtn.disabled || !consented || navigating || !destUrl) return;
    navigating = true;

    const overlay = document.getElementById('redirect-overlay');
    const msg     = document.getElementById('redirect-msg');
    overlay.classList.add('visible');
    msg.textContent = 'Bypassing protection…';

    chrome.tabs.getCurrent(function (tab) {
      const tabId = tab ? tab.id : null;

      if (!chrome.runtime?.id) {
        msg.textContent = 'Extension updated. Reloading...';
        window.location.reload();
        return;
      }

      try {
        chrome.runtime.sendMessage(
          { type: 'WHITELIST_AND_NAVIGATE', url: destUrl, tabId },
          function () {
            if (chrome.runtime.lastError) {
              msg.textContent = 'Extension updated. Reloading...';
              window.location.reload();
              return;
            }
            // Background has acknowledged — navigation is already in flight.
            msg.textContent = 'Navigating…';
            // If background failed (e.g. no tabId), fall back to direct nav.
            if (!tabId) {
              window.location.href = destUrl;
            }
          }
        );
      } catch (err) {
        msg.textContent = 'Extension updated. Reloading...';
        window.location.reload();
      }
    });
  });

  // ── Return to Safety ─────────────────────────────────────────────────────────
  document.getElementById('safe-btn').addEventListener('click', () => {
    chrome.tabs.getCurrent(function (tab) {
      if (tab && tab.id) {
        chrome.tabs.update(tab.id, { url: 'https://www.google.com' });
      } else {
        window.location.replace('https://www.google.com');
      }
    });
  });
})();
