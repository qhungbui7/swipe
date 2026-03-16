// ==UserScript==
// @name         Bumble Auto Swipe
// @namespace    https://github.com/qhungbui7/swipe
// @version      2.0.0
// @build        2026-03-16 18:05
// @description  Automatically swipe right on Bumble with configurable delay and like ratio
// @author       qhungbui7
// @match        https://bumble.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  // ─── Config ──────────────────────────────────────────────────────────────────
  const CONFIG = {
    minDelay:    1800,
    maxDelay:    3500,
    likeRatio:   0.85,
    retryDelay:  2000,
    dismissDelay: 800,
  };

  // ─── Selectors ───────────────────────────────────────────────────────────────
  // NOTE: Bumble uses DIV elements, not <button>. data-qa-role uses double-dash.
  const SEL = {
    like: [
      '[data-qa-role="encounters-action--like"]',
      '.encounters-action--like',
      '[aria-label="Like"]',
      '[aria-label="Yes"]',
    ],
    dislike: [
      '[data-qa-role="encounters-action--dislike"]',
      '.encounters-action--dislike',
      '[aria-label="Pass"]',
      '[aria-label="No"]',
    ],
    dismiss: [
      '[data-qa-role="popup-dismiss"]',
      '[data-qa-role="match-action-button"]',
      '.modal__close-btn',
      '.pill-message__close',
      '[aria-label="Close"]',
    ],
  };

  // ─── State ───────────────────────────────────────────────────────────────────
  let running   = false;
  let timeoutId = null;
  let stats     = { liked: 0, passed: 0 };

  // ─── Helpers ─────────────────────────────────────────────────────────────────
  const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

  function findFirst(selectors) {
    for (const sel of selectors) {
      try {
        const el = document.querySelector(sel);
        if (el && el.offsetParent !== null) return el;
      } catch (_) {}
    }
    return null;
  }

  // Dispatch a keyboard shortcut to the document — most reliable for React SPAs
  function keySwipe(isLike) {
    const key   = isLike ? 'ArrowRight' : 'ArrowLeft';
    const kCode = isLike ? 39 : 37;
    ['keydown', 'keyup'].forEach(type =>
      document.dispatchEvent(new KeyboardEvent(type, {
        key, keyCode: kCode, which: kCode,
        bubbles: true, cancelable: true,
      }))
    );
  }

  function makeSyntheticEvent(el, type) {
    const native = new MouseEvent(type, { bubbles: true, cancelable: true, view: window });
    return {
      nativeEvent:          native,
      target:               el,
      currentTarget:        el,
      type,
      bubbles:              true,
      cancelable:           true,
      preventDefault:       () => {},
      stopPropagation:      () => {},
      isPropagationStopped: () => false,
      isDefaultPrevented:   () => false,
      persist:              () => {},
    };
  }

  function fireReactHandler(el, ...handlerNames) {
    let node = el;
    while (node && node !== document.body) {
      const rk = Object.keys(node).find(k => k.startsWith('__reactProps$'));
      if (rk) {
        for (const name of handlerNames) {
          if (typeof node[rk][name] === 'function') {
            const type = name.slice(2).toLowerCase(); // onPointerDown → pointerdown
            console.log(`[BAS] firing ${name} on <${node.tagName.toLowerCase()}> .${(node.className||'').split(' ')[0]}`);
            try {
              node[rk][name](makeSyntheticEvent(el, type));
              return true;
            } catch (e) {
              console.warn('[BAS] handler threw:', e.message);
            }
          }
        }
      }
      node = node.parentElement;
    }
    return false;
  }

  function clickElement(el) {
    // Try React handlers in priority order (Bumble uses pointer/mouse down for swipe detection)
    const fired = fireReactHandler(el, 'onPointerDown', 'onMouseDown', 'onClick', 'onTouchStart');
    if (fired) return;
    // Final fallback: native events
    console.log('[BAS] no React handler found, using native events');
    ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(type =>
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }))
    );
  }

  function updateUI() {
    const badge = document.getElementById('bas-stats');
    if (badge) badge.textContent = `${stats.liked} likes / ${stats.passed} passes`;
  }

  // ─── Core loop ───────────────────────────────────────────────────────────────
  function step() {
    if (!running) return;

    const dismissBtn = findFirst(SEL.dismiss);
    if (dismissBtn) {
      clickElement(dismissBtn);
      timeoutId = setTimeout(step, CONFIG.dismissDelay);
      return;
    }

    const wantLike   = Math.random() < CONFIG.likeRatio;
    const likeBtn    = findFirst(SEL.like);
    const dislikeBtn = findFirst(SEL.dislike);
    const btn        = wantLike ? (likeBtn || dislikeBtn) : (dislikeBtn || likeBtn);

    if (!btn) {
      console.log('[BAS] no swipe button found — retrying');
      timeoutId = setTimeout(step, CONFIG.retryDelay);
      return;
    }

    console.log(`[BAS] ${wantLike ? 'LIKE' : 'PASS'} → clicking`, btn.getAttribute('data-qa-role') || btn.className.slice(0,50));

    // Try button click via React handlers
    clickElement(btn);
    // Also fire keyboard shortcut simultaneously
    keySwipe(wantLike);

    if (wantLike) stats.liked++; else stats.passed++;
    updateUI();

    timeoutId = setTimeout(step, rand(CONFIG.minDelay, CONFIG.maxDelay));
  }

  const start  = () => { if (running) return; running = true;  updateUI(); step(); };
  const stop   = () => { running = false; clearTimeout(timeoutId); updateUI(); };
  const toggle = () => running ? stop() : start();

  // ─── Panel (all inline styles — no GM_addStyle, no external CSS) ─────────────
  function buildPanel() {
    if (document.getElementById('bas-panel')) return;

    const panel = document.createElement('div');
    panel.id = 'bas-panel';
    Object.assign(panel.style, {
      position:       'fixed',
      bottom:         '24px',
      right:          '24px',
      zIndex:         '2147483647',
      display:        'flex',
      flexDirection:  'column',
      gap:            '6px',
      fontFamily:     '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      fontSize:       '13px',
      pointerEvents:  'all',
    });

    // Config box
    const cfg = document.createElement('div');
    Object.assign(cfg.style, {
      background:   'rgba(255,255,255,0.97)',
      borderRadius: '12px',
      padding:      '10px 14px',
      boxShadow:    '0 2px 12px rgba(0,0,0,0.2)',
      display:      'flex',
      flexDirection:'column',
      gap:          '6px',
    });

    function makeSlider(label, id, min, max, step, val, fmt, onChange) {
      const row = document.createElement('label');
      Object.assign(row.style, { display:'flex', justifyContent:'space-between', alignItems:'center', gap:'8px', cursor:'pointer' });
      const span = document.createElement('span');
      span.textContent = label;
      const valSpan = document.createElement('span');
      valSpan.id = id + '-val';
      valSpan.style.minWidth = '42px';
      valSpan.style.textAlign = 'right';
      valSpan.textContent = fmt(val);
      const input = document.createElement('input');
      Object.assign(input, { type:'range', min, max, step, value: val });
      input.style.width = '80px';
      input.addEventListener('input', e => { onChange(+e.target.value); valSpan.textContent = fmt(+e.target.value); });
      row.append(span, input, valSpan);
      return row;
    }

    cfg.append(
      makeSlider('Like ratio', 'bas-ratio', 0, 100, 1, CONFIG.likeRatio * 100,
        v => v + '%', v => { CONFIG.likeRatio = v / 100; }),
      makeSlider('Min delay', 'bas-min', 500, 5000, 100, CONFIG.minDelay,
        v => v + 'ms', v => { CONFIG.minDelay = v; }),
      makeSlider('Max delay', 'bas-max', 1000, 10000, 100, CONFIG.maxDelay,
        v => v + 'ms', v => { CONFIG.maxDelay = v; }),
    );

    // Stats
    const statsEl = document.createElement('div');
    statsEl.id = 'bas-stats';
    Object.assign(statsEl.style, {
      background:   'rgba(0,0,0,0.65)',
      color:        '#fff',
      borderRadius: '10px',
      padding:      '4px 12px',
      textAlign:    'center',
    });
    statsEl.textContent = '0 likes / 0 passes';

    // Toggle button
    const btn = document.createElement('button');
    btn.id = 'bas-toggle';
    btn.textContent = '▶  Start Auto-Swipe';
    Object.assign(btn.style, {
      background:   '#ffc629',
      color:        '#1a1a1a',
      border:       'none',
      borderRadius: '24px',
      padding:      '11px 22px',
      fontSize:     '14px',
      fontWeight:   '700',
      cursor:       'pointer',
      boxShadow:    '0 4px 14px rgba(0,0,0,0.25)',
    });
    btn.addEventListener('mouseenter', () => btn.style.opacity = '0.85');
    btn.addEventListener('mouseleave', () => btn.style.opacity = '1');
    btn.addEventListener('click', () => {
      toggle();
      btn.textContent = running ? '⏸  Stop' : '▶  Start Auto-Swipe';
      btn.style.background = running ? '#ff6b6b' : '#ffc629';
    });

    panel.append(cfg, statsEl, btn);
    document.body.appendChild(panel);
    console.log('[BAS] panel injected ✓');
  }

  // ─── Injection ───────────────────────────────────────────────────────────────
  function tryInject() {
    if (document.getElementById('bas-panel')) return;
    if (document.body) {
      buildPanel();
    } else {
      setTimeout(tryInject, 300);
    }
  }

  // Patch SPA navigation
  ['pushState', 'replaceState'].forEach(method => {
    const orig = history[method].bind(history);
    history[method] = function (...args) { orig(...args); setTimeout(tryInject, 800); };
  });
  window.addEventListener('popstate', () => setTimeout(tryInject, 800));

  // Keyboard shortcut Alt+S
  document.addEventListener('keydown', e => {
    if (e.altKey && e.key === 's') {
      toggle();
      const b = document.getElementById('bas-toggle');
      if (b) { b.textContent = running ? '⏸  Stop' : '▶  Start Auto-Swipe'; b.style.background = running ? '#ff6b6b' : '#ffc629'; }
    }
  });

  console.log('[BAS] Bumble Auto-Swipe v2 loaded ✓  (build 2026-03-16 17:52)');
  tryInject();

})();
