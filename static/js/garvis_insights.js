// static/js/garvis_insights.js
// Fetches and renders Garvis AI insight cards on the homepage.

(function () {
  'use strict';

  const API = {
    latest:   '/api/ai/insights/latest/',
    feedback: (id) => `/api/ai/insights/${id}/feedback/`,
  };

  function getCsrf() {
    const v = document.cookie.split('; ').find(r => r.startsWith('csrftoken='));
    return v ? decodeURIComponent(v.split('=')[1]) : '';
  }

  function fmtInr(n) {
    if (n == null) return null;
    return '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 });
  }

  // ── Confidence badge ──────────────────────────────────────────────
  function confidenceBadge(level) {
    const map = {
      high:   { label: 'High confidence',   cls: 'garvis-conf-high'   },
      medium: { label: 'Medium confidence', cls: 'garvis-conf-medium' },
      low:    { label: 'Low confidence',    cls: 'garvis-conf-low'    },
    };
    const d = map[level] || map.medium;
    return `<span class="garvis-confidence ${d.cls}">${d.label}</span>`;
  }

  // ── Build one card ────────────────────────────────────────────────
  function buildCard(insight) {
    const saving = insight.estimated_monthly_saving != null
      ? `<div class="garvis-saving">
           <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
             <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>
           </svg>
           Potential saving: <strong>${fmtInr(insight.estimated_monthly_saving)}/mo</strong>
         </div>`
      : '';

    const tags = (insight.tags || []).map(t =>
      `<span class="garvis-tag">${t}</span>`
    ).join('');

    const card = document.createElement('div');
    card.className = 'garvis-card';
    card.dataset.id = insight.id;

    // Already actioned?
    if (insight.feedback === 'accept') {
      card.classList.add('garvis-card--accepted');
    } else if (insight.feedback === 'reject') {
      card.classList.add('garvis-card--rejected');
    }

    card.innerHTML = `
      <div class="garvis-card-header">
        <div class="garvis-card-icon">✦</div>
        <div class="garvis-card-title">${escHtml(insight.action)}</div>
        ${confidenceBadge(insight.confidence)}
      </div>
      <p class="garvis-card-body">${escHtml(insight.explanation)}</p>
      ${saving}
      <div class="garvis-next-step">
        <span class="garvis-next-label">Next step:</span> ${escHtml(insight.next_step)}
      </div>
      ${tags ? `<div class="garvis-tags">${tags}</div>` : ''}
      <div class="garvis-actions">
        <button class="garvis-btn garvis-btn-accept" data-id="${insight.id}" data-action="accept"
          ${insight.feedback ? 'disabled' : ''}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          Accept
        </button>
        <button class="garvis-btn garvis-btn-dismiss" data-id="${insight.id}" data-action="reject"
          ${insight.feedback ? 'disabled' : ''}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
          Dismiss
        </button>
        <div class="garvis-feedback-msg" aria-live="polite"></div>
      </div>
    `;
    return card;
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Render states ─────────────────────────────────────────────────
  function renderLoading(container) {
    container.innerHTML = `
      <div class="garvis-state-loading">
        <div class="garvis-spinner"></div>
        <span>Loading your insights…</span>
      </div>`;
  }

  function renderEmpty(container) {
    container.innerHTML = `
      <div class="garvis-state-empty">
        <div class="garvis-empty-icon">🤖</div>
        <p>No AI insights yet.</p>
        <p class="garvis-empty-sub">Run the Garvis pipeline to generate personalised suggestions.</p>
      </div>`;
  }

  function renderError(container) {
    container.innerHTML = `
      <div class="garvis-state-error">
        <span>⚠</span> Could not load insights right now.
      </div>`;
  }

  // ── Feedback handler ──────────────────────────────────────────────
  async function sendFeedback(btn) {
    const id     = btn.dataset.id;
    const action = btn.dataset.action;   // "accept" | "reject"
    const card   = btn.closest('.garvis-card');
    const msg    = card.querySelector('.garvis-feedback-msg');

    // Disable both buttons immediately
    card.querySelectorAll('.garvis-btn').forEach(b => { b.disabled = true; });
    if (msg) msg.textContent = 'Saving…';

    try {
      const res = await fetch(API.feedback(id), {
        method:  'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken':  getCsrf(),
        },
        body: JSON.stringify({ feedback: action }),
      });

      if (!res.ok) throw new Error(res.statusText);

      // Visual confirmation then fade out
      card.classList.add(action === 'accept' ? 'garvis-card--accepted' : 'garvis-card--rejected');
      if (msg) msg.textContent = action === 'accept' ? '✓ Accepted' : '✕ Dismissed';

      setTimeout(() => {
        card.style.transition = 'opacity 0.5s, transform 0.5s';
        card.style.opacity    = '0';
        card.style.transform  = 'scale(0.96)';
        setTimeout(() => card.remove(), 500);
      }, 900);

    } catch (err) {
      if (msg) msg.textContent = 'Failed — try again.';
      card.querySelectorAll('.garvis-btn').forEach(b => { b.disabled = false; });
    }
  }

  // ── Main ──────────────────────────────────────────────────────────
  async function init() {
    const container = document.getElementById('garvis-insights-container');
    if (!container) return;

    renderLoading(container);

    let data;
    try {
      const res = await fetch(API.latest);
      if (!res.ok) throw new Error(res.statusText);
      data = await res.json();
    } catch {
      renderError(container);
      return;
    }

    const insights = data.insights || [];
    if (!insights.length) {
      renderEmpty(container);
      return;
    }

    container.innerHTML = '';
    insights.forEach(insight => {
      const card = buildCard(insight);
      container.appendChild(card);
    });

    // Event delegation for feedback buttons
    container.addEventListener('click', e => {
      const btn = e.target.closest('.garvis-btn[data-action]');
      if (btn && !btn.disabled) sendFeedback(btn);
    });
  }

  // Run after DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();