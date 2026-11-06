/* Guided tour engine. A dimmed screen with a spotlight on one part of the page and a card explaining it; "Next" glides the
   spotlight to the next part, switching tabs for you where a step lives on another page. Skippable at any moment.

   Tour.run({ steps, onEnd(reason) })          reason is 'done' or 'skipped'
   TourKit.mount({ app, host, me, token, ... }) adds the Help button and starts the welcome tour on a person's first visit

   A step:  { target: '#css selector' | () => element, title, body (HTML, ours), place: 'bottom'|'top'|'left'|'right',
              pad, before: async () => {...navigate...}, optional: skip when the target is not on screen, welcome: true }
*/
(function () {
  'use strict';
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  // two animation frames (so layout has settled), but never wait on them forever: a page in a background tab does not paint
  const frame = () => Promise.race([new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))), sleep(150)]);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const resolve = t => (typeof t === 'function' ? t() : t ? document.querySelector(t) : null);
  const visible = e => { if (!e) return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
  async function waitFor(target, ms = 5000) {
    const end = Date.now() + ms;
    while (Date.now() < end) { const e = resolve(target); if (visible(e)) return e; await sleep(100); }
    return null;
  }

  let S = null;                                                        // the tour that is running, if any

  function build() {
    const root = document.createElement('div');
    root.className = 'tour-root';
    root.innerHTML = '<div class="tour-shade"></div><div class="tour-spot none"></div><div class="tour-card first" role="dialog" aria-modal="true" aria-live="polite"></div>';
    document.body.appendChild(root);
    const stop = e => e.preventDefault();
    root.querySelector('.tour-shade').addEventListener('wheel', stop, { passive: false });     // the tour scrolls the page, not the reader
    root.querySelector('.tour-shade').addEventListener('touchmove', stop, { passive: false });
    return { root, spot: root.querySelector('.tour-spot'), card: root.querySelector('.tour-card') };
  }

  async function run(cfg) {
    stop();
    const steps = (cfg.steps || []).filter(Boolean);
    if (!steps.length) return;
    S = { cfg, steps, i: -1, token: 0, ...build() };
    document.addEventListener('keydown', onKey, true);
    window.addEventListener('resize', onResize);
    await show(cfg.start || 0, 1);
  }

  function stop() {
    if (!S) return;
    document.removeEventListener('keydown', onKey, true);
    window.removeEventListener('resize', onResize);
    S.root.remove();
    S = null;
  }

  function finish(reason) {
    if (!S) return;
    const cb = S.cfg.onEnd;
    stop();
    if (cb) { try { cb(reason); } catch (e) { console.warn(e); } }
  }

  async function show(i, dir) {
    if (!S) return;
    const mine = ++S.token;
    S.card.classList.add('busy');
    while (i >= 0 && i < S.steps.length) {
      const st = S.steps[i];
      if (st.skipIf && st.skipIf()) { i += dir; continue; }
      if (st.before) { try { await st.before(); } catch (e) { console.warn('tour step failed', e); } }
      if (!S || mine !== S.token) return;
      let el = null;
      if (st.target) {
        el = await waitFor(st.target, st.timeout || (st.optional ? 1500 : 5500));      // a part that may simply not exist (no data yet) is not worth a long wait
        if (!S || mine !== S.token) return;
        if (!el && st.optional) { i += dir; continue; }                // e.g. "the first company" when there is no data yet
      }
      S.i = i;
      await render(st, el);
      return;
    }
    if (!S || mine !== S.token) return;
    if (i < 0) return show(0, 1);
    finish('done');
  }

  async function render(st, el) {
    const n = S.steps.length, i = S.i;
    S.step = st; S.el = el;
    if (el) { el.scrollIntoView({ block: 'center', inline: 'nearest' }); await frame(); }
    const last = i === n - 1;
    S.card.className = 'tour-card' + (st.welcome ? ' welcome' : '') + (S.card.dataset.ready ? '' : ' first');
    S.card.innerHTML = `<div class="tour-prog"><i style="width:${Math.round(100 * (i + 1) / n)}%"></i></div><div class="tour-in">
      <div class="tour-step">${st.welcome ? 'Guided tour' : esc(st.section || 'Tour') + ' · ' + (i + 1) + ' of ' + n}</div>
      <h3>${esc(st.title || '')}</h3><div class="tour-body">${st.body || ''}</div>
      <div class="tour-foot">${last && !st.welcome ? '' : `<button class="tour-skip" type="button">${st.welcome ? 'Skip for now' : 'Skip tour'}</button>`}<span class="sp"></span>
        ${st.welcome || i === 0 ? '' : '<button class="tour-back" type="button">Back</button>'}<button class="tour-next" type="button">${st.welcome ? 'Start the tour' : last ? 'Finish' : 'Next'}</button></div>
      ${st.welcome ? '<div class="tour-hint">You can replay this any time from the Help button at the top.</div>' : '<div class="tour-hint">← → keys to move · Esc to skip</div>'}</div>`;
    const skip = S.card.querySelector('.tour-skip'); if (skip) skip.onclick = () => finish('skipped');
    const back = S.card.querySelector('.tour-back'); if (back) back.onclick = () => show(S.i - 1, -1);
    S.card.querySelector('.tour-next').onclick = () => (last ? finish('done') : show(S.i + 1, 1));
    place();
    S.card.dataset.ready = '1';
    S.card.classList.remove('busy');
    S.card.querySelector('.tour-next').focus({ preventScroll: true });
  }

  // spotlight on the target (or dim everything for a step with no target), card beside it
  function place() {
    if (!S || !S.step) return;
    const vw = innerWidth, vh = innerHeight, st = S.step, el = S.el, spot = S.spot, card = S.card;
    const w = card.offsetWidth, h = card.offsetHeight;
    if (!el) {
      spot.className = 'tour-spot none';
      Object.assign(spot.style, { left: vw / 2 + 'px', top: vh / 2 + 'px', width: '0px', height: '0px' });
      Object.assign(card.style, { left: Math.max(10, (vw - w) / 2) + 'px', top: Math.max(10, (vh - h) / 2) + 'px' });
      return;
    }
    const pad = st.pad ?? 8, r = el.getBoundingClientRect();
    const L = Math.max(6, r.left - pad), T = Math.max(6, r.top - pad), R = Math.min(vw - 6, r.right + pad), B = Math.min(vh - 6, r.bottom + pad);
    spot.className = 'tour-spot';
    Object.assign(spot.style, { left: L + 'px', top: T + 'px', width: R - L + 'px', height: B - T + 'px' });
    const gap = 16, cx = L + (R - L) / 2 - w / 2, cy = T + (B - T) / 2 - h / 2, clampX = x => Math.min(Math.max(10, x), vw - w - 10), clampY = y => Math.min(Math.max(10, y), vh - h - 10);
    const spots = {
      bottom: { ok: B + gap + h <= vh - 10, left: clampX(cx), top: B + gap }, top: { ok: T - gap - h >= 10, left: clampX(cx), top: T - gap - h },
      right: { ok: R + gap + w <= vw - 10, left: R + gap, top: clampY(cy) }, left: { ok: L - gap - w >= 10, left: L - gap - w, top: clampY(cy) },
    };
    const order = [st.place, 'bottom', 'top', 'right', 'left'].filter(Boolean);
    const pick = order.find(p => spots[p] && spots[p].ok);
    const at = pick ? spots[pick] : { left: clampX(vw - w - 20), top: clampY(vh - h - 20) };       // target too big to sit beside: float over a corner
    Object.assign(card.style, { left: at.left + 'px', top: at.top + 'px' });
  }

  let resizeTimer;
  function onResize() { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (S && S.el) { S.el.scrollIntoView({ block: 'center' }); } place(); }, 120); }
  function onKey(e) {
    if (!S) return;
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); finish('skipped'); }
    else if (e.key === 'ArrowRight' || e.key === 'Enter') { if (e.target.closest && e.target.closest('.tour-skip, .tour-back')) return; e.preventDefault(); const nx = S.card.querySelector('.tour-next'); if (!S.card.classList.contains('busy')) nx.click(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); const b = S.card.querySelector('.tour-back'); if (b && !S.card.classList.contains('busy')) b.click(); }
  }

  window.Tour = { run, stop, waitFor, active: () => !!S };

  // ---------------------------------------------------------------- Help button + first-visit welcome
  const TourKit = {
    /*  app       'home' | 'portal' | 'diary' | 'studio' (what is remembered as seen)
        host      element the Help button goes into
        me        the signed-in person ({ tours_seen: [...] }); token: their session token
        welcome   () => steps shown first in the full tour (the "who you are and what you can do" card)
        sections  () => [{ id, label, hint, steps: () => [...] }]
        current   () => id of the section on screen, so "Explain this page" can be offered
        snapshot  () => a function that puts the app back where the person was when the tour ends   */
    mount(o) {
      const sections = () => (o.sections ? o.sections() : []);
      const tag = (steps, label) => steps.map(s => ({ section: label, ...s }));
      const fullSteps = () => [...(o.welcome ? o.welcome() : []), ...sections().flatMap(s => tag(s.steps(), s.label))];
      const markSeen = async () => {
        if (o.me && (o.me.tours_seen || []).includes(o.app)) return;
        try {
          const r = await fetch('/api/auth/tour-seen', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + o.token }, body: JSON.stringify({ tour: o.app }) });
          if (r.ok && o.me) o.me.tours_seen = (await r.json()).tours_seen;
        } catch (e) { /* offline: the tour will simply be offered again next time */ }
      };
      const launch = (steps, countsAsSeen) => {
        const back = o.snapshot ? o.snapshot() : null;
        Tour.run({ steps, onEnd: () => { if (countsAsSeen) markSeen(); if (back) back(); } });
      };
      const startFull = auto => launch(fullSteps(), true);

      const wrap = document.createElement('span');
      wrap.className = 'tour-help' + (o.iconOnly ? ' icon-only' : '');
      wrap.innerHTML = '<button type="button" class="tour-help-btn" aria-haspopup="menu" aria-expanded="false" title="Help and guided tours"><span class="q">?</span><span class="lbl">Help</span></button><div class="tour-menu" role="menu" hidden></div>';
      o.host.appendChild(wrap);
      const btn = wrap.querySelector('button'), menu = wrap.querySelector('.tour-menu');
      const close = () => { menu.hidden = true; btn.setAttribute('aria-expanded', 'false'); };
      const openMenu = () => {
        const list = sections(), cur = o.current ? o.current() : null, here = list.find(s => s.id === cur);
        menu.innerHTML = (here ? `<button class="hot" data-s="${esc(here.id)}"><span class="go">▶</span><span>Explain this page<small>${esc(here.label)}</small></span></button>` : '') +
          `<button data-s="__full"><span class="go">▶</span><span>Take the full tour<small>Everything you can use, step by step</small></span></button>` +
          (list.length ? '<hr><h6>Explain a section</h6>' + list.map(s => `<button data-s="${esc(s.id)}"><span class="go">›</span><span>${esc(s.label)}${s.hint ? `<small>${esc(s.hint)}</small>` : ''}</span></button>`).join('') : '');
        menu.hidden = false; btn.setAttribute('aria-expanded', 'true');
      };
      btn.addEventListener('click', e => { e.stopPropagation(); menu.hidden ? openMenu() : close(); });
      document.addEventListener('click', e => { if (!wrap.contains(e.target)) close(); });
      document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
      menu.addEventListener('click', e => {
        const b = e.target.closest('button[data-s]'); if (!b) return;
        close();
        if (b.dataset.s === '__full') return startFull();
        const s = sections().find(x => x.id === b.dataset.s);
        if (s) launch(tag(s.steps(), s.label), false);
      });
      return { startFull, markSeen, autoStart() { if (o.me && !(o.me.tours_seen || []).includes(o.app)) setTimeout(() => !Tour.active() && startFull(true), 700); } };
    },
  };
  window.TourKit = TourKit;
  window.TourUtil = { esc, sleep, waitFor, visible };
})();
