/* Approvals and Sheet sync screens for the staff portal. Uses portal.js's helpers (api, esc, toast, modal, go, show, kpi ...).

   Approvals: a queue on the left, the chosen response on the right, laid out so that correcting something takes two clicks:
     - answers are shown as a clean read-out; click any value (or "Edit & approve") and it turns into the right kind of input
     - while you type, the problems and the people the IDs turn out to be are re-checked live
     - four decisions: Approve, Edit & approve, Reject with reason (sent back to a faculty member), Reject without reason         */
(function () {
  'use strict';
  const STATUS = { PENDING: ['Waiting for approval', 'warn'], APPROVED: ['Approved', 'ok'], RETURNED: ['Sent back for correction', 'orange'], REJECTED: ['Rejected', 'bad'] };
  const ACTION_TEXT = { pulled: 'Pulled from the Google Sheet', updated: 'Changed in the sheet before review', already_live: 'Already in the system', edited: 'Edited', approved: 'Approved',
                        approved_edited: 'Edited and approved', returned: 'Sent back for correction', rejected: 'Rejected', resubmitted: 'Corrected and sent for approval again', revoked: 'Approval withdrawn', reopened: 'Brought back for review' };
  const QUICK_REASONS = ['Some details are unclear', 'Evidence link is missing or does not open', 'Wrong category', 'The date looks wrong', 'Looks like a duplicate entry', 'Names or roll numbers need checking'];
  const RV = { scope: '', items: [], total: 0, sel: null, detail: null, edit: false, edits: {}, checked: new Set(), form: '', q: '', flagged: false, summary: {}, showEmpty: false, timer: null };

  const canDecide = () => me.roles.includes('ADMIN') || me.roles.includes('HOD') || me.tutor_class_ids.length > 0;
  const fmtDate = s => { if (!s) return ''; const d = new Date(String(s).replace(' ', 'T')); return isNaN(d) ? esc(s) : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }); };
  const fmtTime = s => { const d = new Date(String(s).replace(' ', 'T') + (String(s).includes('Z') ? '' : 'Z')); return isNaN(d) ? esc(s || '') : d.toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }); };
  const chip = (text, tone) => `<span class="pill ${tone || ''}">${esc(text)}</span>`;
  const statusChip = s => chip(STATUS[s][0], STATUS[s][1]);
  const isUrl = v => /^https?:\/\/\S+$/i.test(v || '');
  const linkify = v => isUrl(v) ? `<a href="${esc(v)}" target="_blank" rel="noopener noreferrer">${esc(v)}</a>` : esc(v);
  // a date as the date-picker needs it: 2026-09-20 (sheets may hold 20/09/2026 or 9/20/2026)
  const toIso = v => { const t = String(v || '').trim(); let m;
    if ((m = t.match(/^(\d{4})-(\d{2})-(\d{2})/))) return `${m[1]}-${m[2]}-${m[3]}`;
    if ((m = t.match(/^(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{4})/))) { const a = +m[1], b = +m[2], [d, mo] = a > 12 ? [a, b] : b > 12 ? [b, a] : [a, b]; return `${m[3]}-${String(mo).padStart(2, '0')}-${String(d).padStart(2, '0')}`; }
    return ''; };

  // ------------------------------------------------------------------ badge on the tab
  window.refreshReviewBadge = async function () {
    try {
      const s = await api('/api/review/summary'); RV.summary = s;
      const b = document.querySelector('.tab[data-t="review"]'); if (!b) return;
      b.innerHTML = 'Approvals' + (s.badge ? ` <span class="tab-badge">${s.badge > 99 ? '99+' : s.badge}</span>` : '');
    } catch (e) { /* the badge is a convenience */ }
  };

  // ------------------------------------------------------------------ the Approvals screen
  function scopes() {
    const s = RV.summary, list = [];
    if (canDecide()) list.push({ id: 'review', label: 'To review', n: s.to_review });
    list.push({ id: 'returned', label: canDecide() ? 'Sent back' : 'Sent back to me', n: (s.returned_to_me || 0) + (canDecide() ? (s.returned_open || 0) : 0) });
    if (canDecide()) list.push({ id: 'decided', label: 'Decided' });
    list.push({ id: 'mine', label: 'My submissions' });
    return list;
  }
  async function viewReview() {
    RV.summary = await api('/api/review/summary');
    const first = scopes();
    RV.scope = RV.scope && first.some(x => x.id === RV.scope) ? RV.scope : (RV.summary.returned_to_me ? 'returned' : canDecide() ? 'review' : 'mine');
    RV.sel = null; RV.detail = null; RV.edit = false; RV.edits = {}; RV.checked = new Set();
    $('#view').innerHTML = `<div class="card-head"><div><h2>Approvals</h2><p class="hint" style="margin:2px 0 0" id="rv-sub"></p></div><div id="rv-head-actions"></div></div>
      <div class="rv-tabs" id="rv-tabs"></div><div class="rv-filters" id="rv-filters"></div>
      <div class="rv"><aside class="rv-list" id="rv-list"></aside><section class="rv-detail" id="rv-detail"></section></div>`;
    drawTabs(); await loadList(true);
  }
  function drawTabs() {
    $('#rv-tabs').innerHTML = scopes().map(s => `<button class="rv-tab ${RV.scope === s.id ? 'on' : ''}" data-s="${s.id}">${s.label}${s.n ? ` <span class="tab-badge">${s.n}</span>` : ''}</button>`).join('');
    $('#rv-tabs').onclick = go(async e => { const b = e.target.closest('[data-s]'); if (!b) return; RV.scope = b.dataset.s; RV.sel = null; RV.detail = null; RV.checked = new Set(); RV.edit = false; drawTabs(); await loadList(true); });
    const sub = { review: me.roles.includes('ADMIN') || me.roles.includes('HOD') ? 'Responses pulled from the Google Sheets wait here. Nothing is used in the application until you approve it.' : 'Your students\' placement details wait here for your approval.',
                  returned: 'Responses sent back with a reason so the faculty member can correct them.', decided: 'Everything already approved or rejected.', mine: 'Everything you submitted, and where it stands.' }[RV.scope];
    $('#rv-sub').textContent = sub;
  }
  async function loadList(selectFirst) {
    const qs = new URLSearchParams({ scope: RV.scope, limit: 200 });
    if (RV.form) qs.set('form_id', RV.form); if (RV.q) qs.set('q', RV.q); if (RV.flagged) qs.set('flagged', 'true');
    const r = await api('/api/review/items?' + qs); RV.items = r.items; RV.total = r.total;
    drawFilters(); drawList();
    if (selectFirst || (RV.sel && !RV.items.some(i => i.item_id === RV.sel))) { if (RV.items.length) await openItem(RV.items[0].item_id); else { RV.sel = null; RV.detail = null; drawDetail(); } }
  }
  function drawFilters() {
    const forms = [['form_student', 'Student'], ['form_research', 'Research'], ['form_faculty', 'Faculty'], ['form_departmental', 'Department'], ['form_industry', 'Outreach'], ['placement', 'Placement']];
    const bulk = RV.scope === 'review' && RV.items.some(i => i.can_decide);
    const clean = RV.items.filter(i => i.can_decide && !i.warnings.length && !i.blockers.length).length;
    $('#rv-filters').innerHTML = `<input class="input compact" id="rv-q" placeholder="Search title, category or roll number" value="${esc(RV.q)}" style="min-width:240px">
      <select class="compact" id="rv-form"><option value="">All kinds</option>${forms.map(([v, l]) => `<option value="${v}" ${RV.form === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
      ${RV.scope === 'review' ? `<label class="rv-check"><input type="checkbox" id="rv-flag" ${RV.flagged ? 'checked' : ''}> Only those needing a look</label>` : ''}
      <span class="spacer"></span>${bulk ? `<button class="btn sm" id="rv-clean" ${clean ? '' : 'disabled'} title="Approves every response below that has no problems flagged">Approve all clean (${clean})</button>
      <button class="btn sm primary" id="rv-sel" ${RV.checked.size ? '' : 'disabled'}>Approve selected (${RV.checked.size})</button>` : ''}`;
    let t; $('#rv-q').oninput = e => { RV.q = e.target.value; clearTimeout(t); t = setTimeout(go(() => loadList(true)), 300); };
    $('#rv-form').onchange = go(e => { RV.form = e.target.value; return loadList(true); });
    const fl = $('#rv-flag'); if (fl) fl.onchange = go(e => { RV.flagged = e.target.checked; return loadList(true); });
    const cl = $('#rv-clean'); if (cl) cl.onclick = go(async () => {
      if (!confirm(`Approve the ${clean} response${clean === 1 ? '' : 's'} that have no problems flagged? Those that need a look stay for you to check.`)) return;
      const r = await api('/api/review/bulk-approve', { method: 'POST', body: { all_clean: true, form_id: RV.form || undefined } }); await afterBulk(r);
    });
    const sl = $('#rv-sel'); if (sl) sl.onclick = go(async () => { const r = await api('/api/review/bulk-approve', { method: 'POST', body: { ids: [...RV.checked] } }); RV.checked = new Set(); await afterBulk(r); });
  }
  async function afterBulk(r) {
    toast(`${r.approved} approved${r.skipped.length ? `, ${r.skipped.length} could not be (open them to see why)` : ''}`, r.skipped.length > 0 && !r.approved);
    RV.sel = null; await refreshReviewBadge(); await reloadScopes(); await loadList(true);
  }
  async function reloadScopes() { RV.summary = await api('/api/review/summary'); drawTabs(); }

  function drawList() {
    const el = $('#rv-list');
    if (!RV.items.length) {
      el.innerHTML = `<div class="rv-empty"><div class="rv-empty-ico">${RV.scope === 'review' ? '✓' : '…'}</div><b>${RV.scope === 'review' ? 'All caught up' : 'Nothing here'}</b>
        <p>${{ review: 'Nothing is waiting for your approval. New responses arrive when the Google Sheets are pulled.', returned: 'Nothing has been sent back.', decided: 'Nothing has been decided yet.', mine: 'You have not submitted anything yet.' }[RV.scope]}</p></div>`;
      return;
    }
    el.innerHTML = `<div class="rv-count">${RV.total} response${RV.total === 1 ? '' : 's'}</div>` + RV.items.map(i => `
      <div class="rv-card ${RV.sel === i.item_id ? 'on' : ''} ${i.blockers.length ? 'block' : i.warnings.length ? 'flag' : ''}" data-id="${i.item_id}">
        ${RV.scope === 'review' && i.can_decide ? `<input type="checkbox" class="rv-pick" data-id="${i.item_id}" ${RV.checked.has(i.item_id) ? 'checked' : ''} aria-label="Select">` : ''}
        <div class="rv-card-body"><div class="rv-card-top">${chip(i.label)}${i.blockers.length ? chip('Needs fixing', 'bad') : i.warnings.length ? chip(i.warnings.length + ' to check', 'warn') : ''}${RV.scope !== 'review' ? statusChip(i.status) : ''}</div>
          <div class="rv-card-title">${esc(i.title)}</div>
          <div class="rv-card-sub">${[i.category, i.event_date ? fmtDate(i.event_date) : '', i.submitter ? 'by ' + esc(i.submitter) : '', i.assigned_to && RV.scope === 'returned' ? 'sent to ' + esc(i.assigned_to) : ''].filter(Boolean).join(' · ')}</div></div></div>`).join('');
    el.onclick = go(async e => {
      const pick = e.target.closest('.rv-pick');
      if (pick) { const id = +pick.dataset.id; pick.checked ? RV.checked.add(id) : RV.checked.delete(id); drawFilters(); return; }
      const c = e.target.closest('.rv-card'); if (c) await openItem(+c.dataset.id);
    });
  }

  async function openItem(id) {
    RV.detail = await api('/api/review/items/' + id); RV.sel = id; RV.edits = {}; RV.showEmpty = false;
    RV.edit = !!RV.detail.permissions.resubmit;                                           // a faculty member correcting a returned response starts in edit mode
    document.querySelectorAll('.rv-card').forEach(c => c.classList.toggle('on', +c.dataset.id === id));
    document.querySelector('.rv')?.classList.add('rv-open');
    drawDetail();
  }

  // ------------------------------------------------------------------ the detail pane
  const curValue = (ri, f) => (RV.edits[ri] && f.q in RV.edits[ri]) ? RV.edits[ri][f.q] : f.value;
  const dirtyCount = () => Object.values(RV.edits).reduce((n, o) => n + Object.keys(o).length, 0);
  function drawDetail() {
    const el = $('#rv-detail'), d = RV.detail;
    if (!d) { el.innerHTML = '<div class="rv-empty"><div class="rv-empty-ico">←</div><b>Pick a response</b><p>Choose one from the list to read it and decide.</p></div>'; return; }
    const it = d.item, p = d.permissions, st = STATUS[it.status];
    const banner = it.status === 'RETURNED'
      ? `<div class="rv-banner orange"><b>${p.resubmit ? 'Sent back to you for correction' : 'Sent back to ' + esc(it.assigned_to || 'a faculty member')}</b>${it.reason ? `<p>"${esc(it.reason)}"</p>` : ''}
          <small>${p.resubmit ? 'Fix what is asked below, then press <b>Resubmit for approval</b>.' : 'It comes back to you for approval once they have corrected it.'}</small></div>`
      : it.status === 'REJECTED' ? `<div class="rv-banner bad"><b>Rejected</b>${it.reason ? `<p>"${esc(it.reason)}"</p>` : '<p>No reason was given.</p>'}</div>` : '';
    const problems = (d.blockers.length || d.warnings.length) ? `<div class="rv-problems">${d.blockers.map(b => `<div class="rv-prob bad">⛔ ${esc(b)}</div>`).join('')}${d.warnings.map(w => `<div class="rv-prob warn">⚠ ${esc(w)}</div>`).join('')}</div>` : '';
    const people = d.people.length ? `<div class="rv-people">${d.people.map(g => `<div><span class="rv-people-l">${esc(g.label)}</span>${g.items.map(i => `<span class="rv-person ${i.ok ? 'ok' : 'bad'}">${i.ok ? '✓' : '✗'} ${esc(i.text)}</span>`).join('')}</div>`).join('')}</div>` : '';
    const summary = d.summary.length ? `<div class="rv-summary">${d.summary.map(s => `<div>• ${esc(s)}</div>`).join('')}</div>` : '';
    el.innerHTML = `<div class="rv-detail-in">
      <button class="btn sm rv-back" id="rv-back">← Back to the list</button>
      <div class="rv-dhead"><div>${chip(it.label)} ${it.category ? chip(it.category) : ''} ${statusChip(it.status)}</div><h3>${esc(it.title)}</h3>
        <div class="rv-meta">${[it.submitter ? 'Entered by <b>' + esc(it.submitter) + '</b>' : '', d.student_name ? 'Student <b>' + esc(d.student_name) + '</b>' + (it.roll_no ? ' (' + esc(it.roll_no) + ')' : '') : '', it.event_date ? fmtDate(it.event_date) : '', d.rows[0]?.meta?.Timestamp ? 'submitted ' + esc(d.rows[0].meta.Timestamp) : ''].filter(Boolean).join(' · ')}</div></div>
      ${banner}${problems}${summary}${people}
      <div id="rv-rows">${rowsHtml()}</div>
      ${historyHtml()}</div>
      <div class="rv-foot" id="rv-foot">${footHtml()}</div>`;
    wireDetail();
  }

  function rowsHtml() {
    const d = RV.detail, many = d.rows.length > 1;
    return d.rows.map((row, ri) => {
      let html = '', empties = 0, sectionOpen = false, buf = '', head = '';
      const flush = () => { if (buf) { html += head + `<div class="rv-fields">${buf}</div>`; } buf = ''; head = ''; };
      row.fields.forEach((f, fi) => {
        if (f.type === 'section') { flush(); head = `<h5 class="rv-sec">${esc(f.q)}</h5>`; return; }
        const val = curValue(ri, f), empty = !String(val || '').trim();
        const edited = (RV.edits[ri] && f.q in RV.edits[ri] ? norm(val) !== norm(f.value) : false) || f.changed;
        if (empty && !RV.edit && !f.req) { empties++; return; }
        buf += RV.edit ? inputHtml(ri, fi, f, val, edited) : readHtml(ri, fi, f, val, edited);
      });
      flush();
      const extras = row.extras.length ? `<h5 class="rv-sec">Other columns in the sheet</h5><div class="rv-fields">${row.extras.map(x => `<div class="rv-f"><div class="rv-l">${esc(x.q)}</div><div class="rv-v">${linkify(x.value)}</div></div>`).join('')}</div>` : '';
      return `<div class="rv-row">${many ? `<div class="rv-row-h">Entry ${ri + 1}${row.fields.find(f => f.q && /company/i.test(f.q))?.value ? ' · ' + esc(row.fields.find(f => /company/i.test(f.q)).value) : ''}</div>` : ''}${html}${extras}
        ${!RV.edit && empties ? `<button class="btn sm rv-more" data-empties="1">Show ${empties} empty field${empties === 1 ? '' : 's'}</button>` : ''}</div>`;
    }).join('');
  }
  const norm = v => String(v || '').trim().toLowerCase().replace(/\s+/g, ' ');
  const wide = f => ['para', 'roster_roll', 'roster_any'].includes(f.type);
  function readHtml(ri, fi, f, val, edited) {
    return `<div class="rv-f ${wide(f) ? 'wide' : ''} ${edited ? 'edited' : ''}"><div class="rv-l">${esc(f.q)}${f.req ? ' <i>*</i>' : ''}${edited ? ' <span class="rv-edited">edited</span>' : ''}</div>
      <div class="rv-v">${linkify(val) || '<span class="muted">—</span>'}${RV.detail.permissions.decide ? `<button class="rv-pen" data-r="${ri}" data-f="${fi}" title="Edit this" aria-label="Edit ${esc(f.q)}">✎</button>` : ''}</div>
      ${edited && f.original && f.original !== val ? `<div class="rv-was">was: ${esc(f.original)}</div>` : ''}</div>`;
  }
  function inputHtml(ri, fi, f, val, edited) {
    const id = `rvf-${ri}-${fi}`, req = f.req && !String(val || '').trim();
    let control;
    if (f.type === 'confirm') control = `<div class="rv-v">${linkify(val) || '—'}</div>`;
    else if (f.type === 'choice' || f.type === 'list') {
      const opts = [...(f.choices || [])]; if (val && !opts.includes(val)) opts.unshift(val);
      control = `<select id="${id}" data-r="${ri}" data-f="${fi}"><option value="">—</option>${opts.map(o => `<option ${o === val ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
    } else if (f.type === 'date') control = `<input type="date" id="${id}" data-r="${ri}" data-f="${fi}" value="${esc(toIso(val))}">${val && !toIso(val) ? `<div class="rv-was">sheet says: ${esc(val)}</div>` : ''}`;
    else if (wide(f)) control = `<textarea id="${id}" data-r="${ri}" data-f="${fi}" rows="${f.type === 'para' ? 3 : 4}" placeholder="${esc(f.help || '')}">${esc(val)}</textarea>`;
    else if (f.type === 'faculty') control = `<input id="${id}" data-r="${ri}" data-f="${fi}" list="rv-fac" value="${esc(val)}" placeholder="Start typing a name">`;
    else control = `<input id="${id}" data-r="${ri}" data-f="${fi}" value="${esc(val)}" ${f.type === 'number' ? 'inputmode="decimal"' : ''}>`;
    return `<div class="rv-f ${wide(f) ? 'wide' : ''} ${edited ? 'edited' : ''} ${req ? 'need' : ''}"><label class="rv-l" for="${id}">${esc(f.q)}${f.req ? ' <i>*</i>' : ''}${edited ? ' <span class="rv-edited">edited</span>' : ''}</label>${control}
      ${f.help && !wide(f) ? `<div class="rv-help">${esc(f.help)}</div>` : ''}${edited && f.original !== undefined && f.original !== val ? `<div class="rv-was">was: ${esc(f.original) || '(empty)'}</div>` : ''}</div>`;
  }
  function historyHtml() {
    const t = RV.detail.timeline; if (!t.length) return '';
    return `<details class="rv-hist"><summary>History (${t.length})</summary>${t.map(e => `<div class="rv-ev"><span class="rv-ev-t">${fmtTime(e.at)}</span> <b>${esc(ACTION_TEXT[e.action] || e.action)}</b>${e.actor ? ' by ' + esc(e.actor) : ''}
      ${e.note ? `<div class="rv-ev-n">"${esc(e.note)}"</div>` : ''}${Array.isArray(e.detail) && e.action === 'edited' ? `<ul class="rv-ev-c">${e.detail.map(c => `<li><b>${esc(c.field)}</b>: ${esc(c.from) || '(empty)'} → ${esc(c.to) || '(empty)'}</li>`).join('')}</ul>` : ''}</div>`).join('')}</details>`;
  }

  function footHtml() {
    const p = RV.detail.permissions, it = RV.detail.item, n = dirtyCount();
    if (p.resubmit) return `<div class="rv-foot-note"><input id="rv-note" class="input" placeholder="What did you change? (optional if you changed something)"></div>
      <button class="btn primary large" id="act-resubmit">Resubmit for approval${n ? ` (${n} change${n === 1 ? '' : 's'})` : ''}</button>`;
    if (p.decide) {
      if (RV.edit) return `<span class="rv-foot-msg">${n ? `<b>${n}</b> change${n === 1 ? '' : 's'} made` : 'Change anything that needs fixing'}</span><span class="spacer"></span>
        <button class="btn" id="act-cancel-edit">Cancel</button><button class="btn primary large" id="act-save-approve" ${RV.detail.blockers.length && !n ? 'disabled title="Fix the problem first"' : ''}>${n ? 'Save changes & approve' : 'Approve'}</button>`;
      const returns = it.kind === 'FORM';
      return `<button class="btn primary" id="act-approve" ${RV.detail.blockers.length ? 'disabled title="Fix the problem first (Edit & approve)"' : ''}>✓ Approve</button>
        <button class="btn" id="act-edit">✎ Edit &amp; approve</button><span class="spacer"></span>
        <button class="btn warnbtn" id="act-reject-reason">${returns ? '↩ Reject with reason' : '↩ Reject with reason'}</button><button class="btn danger" id="act-reject">✕ Reject without reason</button>`;
    }
    if (p.revoke) return `<span class="rv-foot-msg">Approved. It is part of the application now.</span><span class="spacer"></span><button class="btn danger" id="act-revoke">Withdraw approval</button>`;
    if (p.reopen) return `<span class="rv-foot-msg">Rejected.</span><span class="spacer"></span><button class="btn" id="act-reopen">Bring back for review</button>`;
    const who = it.kind === 'PLACEMENT' ? "the student's class tutor" : 'the Admin or HoD';
    return `<span class="rv-foot-msg">${it.status === 'PENDING' ? `View only. ${who[0].toUpperCase() + who.slice(1)} approves this.` : it.status === 'RETURNED' ? 'Waiting for the faculty member to correct it.' : STATUS[it.status][0] + '.'}</span>`;
  }

  function currentAnswers() {                                              // the answers as they stand now, in the shape the server's checker expects
    return RV.detail.rows.map((row, ri) => { const a = { ...row.meta }; row.fields.forEach(f => { if (f.type !== 'section') a[f.q] = curValue(ri, f); }); row.extras.forEach(x => a[x.q] = x.value); return a; });
  }
  const editsList = () => RV.detail.rows.map((_, ri) => ({ ...(RV.edits[ri] || {}) }));

  function wireDetail() {
    const d = RV.detail;
    $('#rv-back').onclick = () => document.querySelector('.rv')?.classList.remove('rv-open');
    const rows = $('#rv-rows');
    rows.onclick = e => {
      const pen = e.target.closest('.rv-pen'); if (pen) { RV.edit = true; drawDetail(); const el = document.getElementById(`rvf-${pen.dataset.r}-${pen.dataset.f}`); if (el) { el.focus(); el.scrollIntoView({ block: 'center' }); } return; }
      if (e.target.closest('[data-empties]')) { RV.edit = RV.edit; RV.showEmpty = true; RV.edit = d.permissions.decide ? true : RV.edit; drawDetail(); }
    };
    const onChange = e => {
      const t = e.target; if (!t.dataset || t.dataset.r === undefined) return;
      const f = d.rows[+t.dataset.r].fields[+t.dataset.f], ri = +t.dataset.r;
      let v = t.value; (RV.edits[ri] = RV.edits[ri] || {})[f.q] = v;
      if (norm(v) === norm(f.value)) delete RV.edits[ri][f.q];
      if (t.tagName === 'TEXTAREA') { t.style.height = 'auto'; t.style.height = t.scrollHeight + 'px'; }
      t.closest('.rv-f')?.classList.toggle('edited', norm(v) !== norm(f.value)); $('#rv-foot').innerHTML = footHtml(); wireFoot();
      clearTimeout(RV.timer); RV.timer = setTimeout(recheck, 450);
    };
    rows.oninput = onChange; rows.onchange = onChange;
    rows.querySelectorAll('textarea').forEach(t => { t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 320) + 'px'; });
    if (!document.getElementById('rv-fac')) { const dl = document.createElement('datalist'); dl.id = 'rv-fac'; dl.innerHTML = d.faculty.map(f => `<option value="${esc(f.emp_id)} - ${esc(f.full_name)}">`).join(''); document.body.appendChild(dl); }
    wireFoot();
  }
  async function recheck() {                                                // fresh problems and names while the approver types
    try {
      const r = await api('/api/review/preview', { method: 'POST', body: { form_id: RV.detail.item.form_id, answers: currentAnswers() } });
      RV.detail.warnings = r.warnings; RV.detail.blockers = r.blockers; RV.detail.people = r.people; RV.detail.summary = r.summary || [];
      const keep = RV.detail.rows; const top = document.querySelector('.rv-detail')?.scrollTop;
      document.querySelector('.rv-problems')?.remove(); document.querySelector('.rv-people')?.remove(); document.querySelector('.rv-summary')?.remove();
      const head = document.querySelector('.rv-dhead'); if (head) head.insertAdjacentHTML('afterend', problemsHtml() + summaryHtml() + peopleHtml());
      $('#rv-foot').innerHTML = footHtml(); wireFoot(); if (top !== undefined) document.querySelector('.rv-detail').scrollTop = top; void keep;
    } catch (e) { /* the live check is a help, not a gate */ }
  }
  const problemsHtml = () => { const d = RV.detail; return (d.blockers.length || d.warnings.length) ? `<div class="rv-problems">${d.blockers.map(b => `<div class="rv-prob bad">⛔ ${esc(b)}</div>`).join('')}${d.warnings.map(w => `<div class="rv-prob warn">⚠ ${esc(w)}</div>`).join('')}</div>` : ''; };
  const summaryHtml = () => RV.detail.summary.length ? `<div class="rv-summary">${RV.detail.summary.map(s => `<div>• ${esc(s)}</div>`).join('')}</div>` : '';
  const peopleHtml = () => RV.detail.people.length ? `<div class="rv-people">${RV.detail.people.map(g => `<div><span class="rv-people-l">${esc(g.label)}</span>${g.items.map(i => `<span class="rv-person ${i.ok ? 'ok' : 'bad'}">${i.ok ? '✓' : '✗'} ${esc(i.text)}</span>`).join('')}</div>`).join('')}</div>` : '';

  // ------------------------------------------------------------------ the four decisions (and friends)
  function wireFoot() {
    const id = RV.sel, on = (sel, fn) => { const b = $(sel); if (b) b.onclick = go(fn); };
    on('#act-approve', async () => { await api(`/api/review/items/${id}/approve`, { method: 'POST', body: {} }); await done('Approved'); });
    on('#act-edit', async () => { RV.edit = true; drawDetail(); const first = document.querySelector('#rv-rows input, #rv-rows select, #rv-rows textarea'); if (first) first.focus(); });
    on('#act-cancel-edit', async () => { RV.edit = false; RV.edits = {}; await openItem(id); });
    on('#act-save-approve', async () => { const n = dirtyCount(); await api(`/api/review/items/${id}/approve`, { method: 'POST', body: { answers: editsList() } }); await done(n ? `Saved ${n} change${n === 1 ? '' : 's'} and approved` : 'Approved'); });
    on('#act-reject', async () => { if (!confirm('Reject this without giving a reason?\n\nIt will not be used anywhere and nobody is asked to fix it. You can bring it back later.')) return; await api(`/api/review/items/${id}/reject`, { method: 'POST', body: {} }); await done('Rejected'); });
    on('#act-reject-reason', async () => rejectDialog());
    on('#act-resubmit', async () => { const n = dirtyCount(); await api(`/api/review/items/${id}/resubmit`, { method: 'POST', body: { answers: editsList(), note: $('#rv-note')?.value } }); await done('Sent for approval again'); });
    on('#act-revoke', async () => { if (!confirm('Withdraw the approval?\n\nThe record leaves the application (charts, profiles, newsletter) and waits for approval again.')) return; await api(`/api/review/items/${id}/revoke`, { method: 'POST' }); await done('Approval withdrawn', true); });
    on('#act-reopen', async () => { await api(`/api/review/items/${id}/reopen`, { method: 'POST' }); await done('Brought back for review', true); });
  }
  function rejectDialog() {
    const d = RV.detail, it = d.item, returns = it.kind === 'FORM';
    const o = modal(returns ? 'Reject with a reason' : 'Reject with a reason', `
      <p class="hint" style="margin-top:0">${returns ? 'The response goes back to a faculty member, who sees your reason, corrects it and sends it for approval again.' : 'The reason is kept with the record. Students do not correct it here; they can submit again through the form.'}</p>
      <div class="field"><label>What needs to be fixed?</label><textarea id="rj-reason" class="input" rows="3" placeholder="e.g. The journal name looks wrong: please check it against the certificate."></textarea>
        <div class="rv-quick">${QUICK_REASONS.map(r => `<button type="button" class="rv-chipbtn">${esc(r)}</button>`).join('')}</div></div>
      ${returns ? `<div class="field"><label>Send it to</label><select id="rj-to"><option value="">Choose a faculty member…</option>${d.faculty.map(f => `<option value="${esc(f.emp_id)}" ${f.emp_id === d.suggested_send_to ? 'selected' : ''}>${esc(f.full_name)} (${esc(f.emp_id)})${f.emp_id === d.suggested_send_to ? ' - entered it' : ''}</option>`).join('')}</select></div>` : ''}`,
      async dlg => {
        const reason = $('#rj-reason', dlg).value.trim(), to = returns ? $('#rj-to', dlg).value : null;
        if (!reason) { toast('Please write the reason (or use "Reject without reason")', true); return false; }
        if (returns && !to) { toast('Choose who it should go to', true); return false; }
        const r = await api(`/api/review/items/${RV.sel}/reject`, { method: 'POST', body: { reason, send_to: to || undefined } });
        await done(returns ? `Sent back to ${r.assigned_to}` : 'Rejected with your reason');
      }, returns ? 'Send back' : 'Reject');
    o.querySelectorAll('.rv-chipbtn').forEach(b => b.onclick = () => { const t = $('#rj-reason', o); t.value = (t.value ? t.value.replace(/\s*$/, '. ') : '') + b.textContent; t.focus(); });
  }
  async function done(msg, stay) {                                          // after a decision: say so, then move on to the next one
    const was = RV.sel, idx = RV.items.findIndex(i => i.item_id === was);
    await refreshReviewBadge(); RV.summary = await api('/api/review/summary'); drawTabs();
    await loadList(false);
    const next = stay && RV.items.some(i => i.item_id === was) ? was : (RV.items[Math.min(idx, RV.items.length - 1)] || {}).item_id;
    RV.edit = false; RV.edits = {};
    if (next) await openItem(next); else { RV.sel = null; RV.detail = null; drawDetail(); }
    toast(`✓ ${msg}${RV.scope === 'review' ? ` · ${RV.total} left` : ''}`);
  }

  // keyboard: up and down move through the list (not while typing)
  document.addEventListener('keydown', e => {
    if (current !== 'review' || !RV.items.length || /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '') || document.querySelector('.overlay')) return;
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    const i = RV.items.findIndex(x => x.item_id === RV.sel), j = Math.max(0, Math.min(RV.items.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)));
    e.preventDefault(); if (j !== i) go(openItem)(RV.items[j].item_id);
  });

  // ================================================================== Sheet sync
  async function viewSync() {
    const o = await api('/api/sync/overview'), s = o.settings;
    const tzs = ['Asia/Kolkata', 'UTC', 'Asia/Dubai', 'Asia/Singapore', 'Europe/London', 'America/New_York'];
    const ro = o.can_configure ? '' : 'disabled';
    const result = r => !r ? '<span class="muted">Not pulled yet</span>' : r.error ? `<span class="rv-bad">⚠ ${esc(r.error)}</span>` : `<span class="rv-ok">${r.new || 0} new</span> · ${r.unchanged || 0} unchanged${r.already_in_system ? ` · ${r.already_in_system} already in the system` : ''}${r.updated ? ` · ${r.updated} changed` : ''}`;
    $('#view').innerHTML = `<div class="card-head"><div><h2>Sheet sync</h2><p class="hint" style="margin:2px 0 0">Pull the form responses from Google Sheets into the Approvals queue. The sheets are only <b>read</b>: nothing is changed or deleted in Google.</p></div></div>
      <div class="grid-2">
      <div class="card"><h3>Pull now</h3><p class="hint">Fetch every new response straight away.${o.can_pull_forms ? '' : ' (You can pull the placement sheet.)'}</p>
        <button class="btn primary large" id="sy-run" ${o.can_pull_placements ? '' : 'disabled'}>⟳ Pull from Google Sheets now</button><div id="sy-out" style="margin-top:12px"></div></div>
      <div class="card"><h3>Automatic pull</h3>
        <label class="rv-switch"><input type="checkbox" id="sy-on" ${s.enabled ? 'checked' : ''} ${ro}> <span>Pull automatically</span></label>
        <div class="sy-sched ${s.enabled ? '' : 'off'}" id="sy-sched">
          <div class="filters" style="margin:10px 0 6px"><label class="rv-radio"><input type="radio" name="sy-mode" value="days" ${s.mode === 'days' ? 'checked' : ''} ${ro}> Every <input type="number" min="1" max="60" id="sy-days" class="input compact" style="width:64px" value="${s.every_days}" ${ro}> day(s)</label></div>
          <div class="filters" style="margin:0 0 6px"><label class="rv-radio"><input type="radio" name="sy-mode" value="week" ${s.mode === 'week' ? 'checked' : ''} ${ro}> Once a week on <select id="sy-wd" class="compact" ${ro}>${s.weekdays.map((w, i) => `<option value="${i}" ${s.weekday === i ? 'selected' : ''}>${w}</option>`).join('')}</select></label></div>
          <div class="filters" style="margin:0"><label>at <input type="time" id="sy-time" class="input compact" value="${String(s.hour).padStart(2, '0')}:${String(s.minute).padStart(2, '0')}" ${ro}></label>
            <label>time zone <input list="sy-tz" id="sy-zone" class="input compact" value="${esc(s.timezone)}" style="width:150px" ${ro}><datalist id="sy-tz">${tzs.map(z => `<option value="${z}">`).join('')}</datalist></label></div></div>
        <p class="sy-next" id="sy-next">${s.enabled && s.next_run_local ? `Next pull: <b>${esc(s.next_run_local)}</b>` : esc(s.describe)}</p>
        ${o.can_configure ? '<button class="btn" id="sy-save">Save schedule</button>' : '<p class="hint">Only the Admin changes the schedule.</p>'}</div></div>
      <div class="card"><div class="card-head"><h3>Your Google Sheets</h3></div>
        <p class="hint">Paste the link of each form's <b>responses</b> sheet. ${o.service_account ? 'A Google service account is connected: share each sheet with its e-mail address (Viewer) and the sheets can stay private.' : 'Share each sheet as <b>Anyone with the link can view</b>, or connect a Google service account for private sheets (see below).'}</p>
        <div class="scroll"><table class="table"><thead><tr><th>Form</th><th>Sheet link</th><th></th><th>Last pull</th><th class="num">Waiting</th></tr></thead><tbody>
        ${o.sources.map(x => `<tr data-f="${x.form_id}"><td><b>${esc(x.title)}</b></td><td><input class="input compact sy-url" style="width:100%;min-width:260px" value="${esc(x.sheet_url)}" placeholder="https://docs.google.com/spreadsheets/d/…" ${ro}></td>
          <td style="white-space:nowrap">${o.can_configure ? '<button class="btn sm sy-test">Test</button> <button class="btn sm sy-save1">Save</button>' : ''}<div class="sy-testout"></div></td>
          <td>${result(x.last_result)}${x.last_pulled_at ? `<div class="muted" style="font-size:11px">${fmtTime(x.last_pulled_at)}</div>` : ''}</td><td class="num">${x.pending || ''}</td></tr>`).join('')}</tbody></table></div>
        <details class="rv-hist" style="margin-top:12px"><summary>How to connect a private sheet (service account)</summary><ol class="sy-howto"><li>In Google Cloud, create a <b>service account</b> and a JSON key; enable the <b>Google Sheets API</b>.</li><li>Put the key's whole contents in the server setting <code>GOOGLE_SERVICE_ACCOUNT_JSON</code> and restart.</li><li>Share each responses sheet with the service account's e-mail address as <b>Viewer</b>.</li></ol></details></div>
      <div class="card"><h3>Recent pulls</h3>${o.runs.length ? `<div class="scroll"><table class="table"><thead><tr><th>When</th><th>How</th><th>Result</th><th class="num">New / changed</th></tr></thead><tbody>${o.runs.map(r => `<tr><td>${fmtTime(r.started_at)}</td><td>${r.trigger === 'schedule' ? 'Automatic' : 'By ' + esc(r.actor || 'someone')}</td>
        <td>${r.status === 'done' ? chip('Done', 'ok') : r.status === 'running' ? chip('Running', 'warn') : chip('Failed', 'bad')}${r.summary && r.summary.none_configured ? ' <span class="muted">no sheets set up</span>' : ''}${r.summary && r.summary.failed && r.summary.failed.length ? ` <span class="rv-bad">${r.summary.failed.length} sheet(s) could not be read</span>` : ''}</td><td class="num">${r.summary ? r.summary.new_or_updated : ''}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Nothing has been pulled yet.</div>'}</div>`;
    const runBtn = $('#sy-run');
    runBtn.onclick = go(async () => {
      runBtn.disabled = true; runBtn.textContent = '⟳ Pulling…';
      try {
        const r = await api('/api/sync/run', { method: 'POST', body: {} });
        const lines = Object.entries(r.sources).map(([f, v]) => `<div><b>${esc(o.sources.find(x => x.form_id === f)?.title || f)}</b>: ${result(v)}</div>`).join('');
        $('#sy-out').innerHTML = r.none_configured ? '<div class="rv-banner warn"><b>No sheets are set up yet.</b><p>Paste a sheet link below first.</p></div>' : `<div class="rv-banner ${r.status === 'failed' ? 'bad' : 'ok'}"><b>${r.new_or_updated ? r.new_or_updated + ' new or changed response' + (r.new_or_updated === 1 ? '' : 's') + ' are waiting in Approvals' : 'Nothing new this time'}</b>${lines}</div>`;
        refreshReviewBadge();
      } finally { runBtn.disabled = false; runBtn.textContent = '⟳ Pull from Google Sheets now'; }
    });
    if (!o.can_configure) return;
    const toggle = () => $('#sy-sched').classList.toggle('off', !$('#sy-on').checked); $('#sy-on').onchange = toggle;
    $('#sy-save').onclick = go(async () => {
      const [h, m] = $('#sy-time').value.split(':').map(Number);
      const r = await api('/api/sync/settings', { method: 'PUT', body: { enabled: $('#sy-on').checked, mode: document.querySelector('[name=sy-mode]:checked').value, every_days: +$('#sy-days').value, weekday: +$('#sy-wd').value, hour: h, minute: m, timezone: $('#sy-zone').value } });
      $('#sy-next').innerHTML = r.enabled && r.next_run_local ? `Next pull: <b>${esc(r.next_run_local)}</b> <span class="muted">(${esc(r.describe)})</span>` : esc(r.describe); toast('Schedule saved');
    });
    $('#view').onclick = go(async e => {
      const tr = e.target.closest('tr[data-f]'); if (!tr) return; const url = $('.sy-url', tr).value.trim(), out = $('.sy-testout', tr);
      if (e.target.classList.contains('sy-save1')) { await api(`/api/sync/sources/${tr.dataset.f}`, { method: 'PUT', body: { sheet_url: url } }); toast('Saved'); }
      if (e.target.classList.contains('sy-test')) {
        out.innerHTML = '<span class="muted">Checking…</span>';
        try { const r = await api('/api/sync/test', { method: 'POST', body: { form_id: tr.dataset.f, sheet_url: url } });
          out.innerHTML = `<span class="rv-ok">✓ ${r.rows} response${r.rows === 1 ? '' : 's'} found</span>${r.missing_required.length ? `<div class="rv-bad">Missing columns: ${r.missing_required.map(esc).join(', ')}</div>` : ''}${r.rows === 0 ? '<div class="muted">No responses yet, but the column titles were read.</div>' : ''}${r.unknown_columns.length ? `<details><summary class="muted">Columns not recognised (${r.unknown_columns.length})</summary><div class="muted">${r.unknown_columns.map(esc).join('<br>')}</div></details>` : ''}`;
        } catch (err) { out.innerHTML = `<span class="rv-bad">⚠ ${esc(err.message)}</span>`; }
      }
    });
  }

  window.Review = { viewReview, viewSync };
  VIEWS.review = viewReview; VIEWS.sync = viewSync;
})();
