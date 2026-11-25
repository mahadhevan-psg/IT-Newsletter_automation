/* Add an entry: describe what happened, fill a few fields, submit for approval.
   No forms to hunt for: a search box and tiles, one card with only the essentials (the rest under "More details"), photos taken
   straight from the phone, people picked by name or roll number, and a draft that saves itself.                                              */
(function () {
  'use strict';
  const E = { cat: null, drafts: [], form: null, formId: null, category: null, values: {}, photos: {}, draftId: null, timer: null, saved: '' };
  const uid = () => (crypto.randomUUID ? crypto.randomUUID().replace(/-/g, '') : String(Date.now()) + Math.random().toString(16).slice(2));
  const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

  async function viewEntry() {
    E.cat = await api('/api/entry/catalog'); E.drafts = E.cat.drafts;
    const forms = E.cat.forms;
    $('#view').innerHTML = `<div class="en">
      <div class="card-head"><div><h2>Add an entry</h2><p class="hint" style="margin:2px 0 0">Choose what happened. Your entry goes to the Admin or HoD for approval; nothing is used before that.</p></div></div>
      <div class="en-search"><input class="input" id="en-q" placeholder="What happened? Try “hackathon”, “paper”, “MoU”, “award”" autocomplete="off"></div>
      <div id="en-drafts"></div><div id="en-tiles"></div><div id="en-composer"></div></div>`;
    drawDrafts(); drawTiles('');
    $('#en-q').oninput = e => drawTiles(e.target.value);
    $('#en-q').onkeydown = e => { if (e.key === 'Enter') { const t = $('#en-tiles .en-tile'); if (t) t.click(); } };
    $('#en-q').focus();
  }

  function drawDrafts() {
    const el = $('#en-drafts');
    el.innerHTML = E.drafts.length ? `<div class="en-drafts"><span class="muted">Unfinished:</span> ${E.drafts.map(d => `<span class="en-draft"><button class="btn sm" data-d="${esc(d.draft_id)}">${esc(d.summary || d.category || 'Untitled')} <small class="muted">· ${esc(d.category || '')}</small></button><button class="x" data-del="${esc(d.draft_id)}" aria-label="Delete this draft">×</button></span>`).join('')}</div>` : '';
    el.onclick = go(async e => {
      const o = e.target.closest('[data-d]'), x = e.target.closest('[data-del]');
      if (x) { await api('/api/entry/drafts/' + x.dataset.del, { method: 'DELETE' }); E.drafts = E.drafts.filter(d => d.draft_id !== x.dataset.del); drawDrafts(); }
      else if (o) { const d = await api('/api/entry/drafts/' + o.dataset.d); await openComposer(d.form_id, d.category, d); }
    });
  }

  function drawTiles(q) {
    const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const groups = E.cat.forms.map(f => ({ ...f, cats: f.categories.filter(c => words.every(w => c.keywords.includes(w) || c.name.toLowerCase().includes(w))) })).filter(f => f.cats.length);
    $('#en-tiles').innerHTML = groups.length ? groups.map(f => `<h4 class="en-h">${esc(f.title)}</h4>${f.description ? `<p class="en-hd">${esc(f.description)}</p>` : ''}<div class="en-grid">${f.cats.map(c =>
      `<button class="en-tile ${E.form && E.category === c.name ? 'on' : ''}" data-f="${f.form_id}" data-c="${esc(c.name)}"><b>${esc(c.name)}</b>${c.description ? `<span>${esc(c.description)}</span>` : ''}</button>`).join('')}</div>`).join('') : '<div class="empty">Nothing matches. Try another word, or clear the search.</div>';
    $('#en-tiles').onclick = go(e => { const t = e.target.closest('.en-tile'); if (t) return openComposer(t.dataset.f, t.dataset.c); });
  }

  async function openComposer(formId, category, draft) {
    E.form = await api(`/api/entry/form?form_id=${encodeURIComponent(formId)}&category=${encodeURIComponent(category)}`);
    E.formId = formId; E.category = category; E.values = draft ? draft.values : {}; E.draftId = draft ? draft.draft_id : uid(); E.photos = {};
    for (const f of E.form.fields) if (f.type === 'photo') E.photos[f.fid] = [];
    for (const f of E.form.fields) {
      if (E.values[f.fid] === undefined && f.default) E.values[f.fid] = f.default;
      if (f.type === 'photo' && Array.isArray(E.values[f.fid])) E.photos[f.fid] = E.values[f.fid].map(id => ({ media_id: id, thumb_url: null }));
    }
    drawComposer(); drawTiles($('#en-q').value);
    $('#en-composer').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  const val = f => E.values[f.fid] ?? '';
  const isMain = f => f.req || f.type === 'photo';
  function fieldHtml(f, v = val(f)) {
    const id = 'ef-' + f.fid.replace(/[^\w]/g, '_'), req = f.req ? ' <i class="en-req">*</i>' : '', help = f.help ? `<div class="en-help">${esc(f.help)}</div>` : '';
    let c;
    if (f.type === 'para') c = `<textarea id="${id}" data-f="${esc(f.fid)}" rows="3">${esc(v)}</textarea>`;
    else if (f.type === 'date') c = `<input type="date" id="${id}" data-f="${esc(f.fid)}" value="${esc(v)}">`;
    else if (f.type === 'number') c = `<input id="${id}" data-f="${esc(f.fid)}" inputmode="decimal" value="${esc(v)}">`;
    else if (f.type === 'choice') c = `<div class="en-pills" data-f="${esc(f.fid)}">${(f.choices || []).map(o => `<button type="button" class="en-pill ${v === o ? 'on' : ''}" data-v="${esc(o)}">${esc(o)}</button>`).join('')}</div>`;
    else if (f.type === 'multi') { const on = Array.isArray(v) ? v : String(v || '').split(', ').filter(Boolean); c = `<div class="en-pills" data-f="${esc(f.fid)}" data-multi="1">${(f.choices || []).map(o => `<button type="button" class="en-pill ${on.includes(o) ? 'on' : ''}" data-v="${esc(o)}">${esc(o)}</button>`).join('')}</div>`; }
    else if (f.type === 'file') c = `<div class="en-drop"><label><input type="file" accept="application/pdf,image/*" data-doc="${esc(f.fid)}" hidden><span><b>Upload document</b> · a PDF (up to 5 MB) or a picture of it</span></label></div><div class="en-doc" id="${id}-doc"></div>`;
    else if (f.type === 'list') c = `<select id="${id}" data-f="${esc(f.fid)}"><option value=""></option>${(f.choices || []).map(o => `<option ${v === o ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
    else if (f.type === 'confirm') return `<label class="en-confirm"><input type="checkbox" data-f="${esc(f.fid)}" ${v ? 'checked' : ''}> ${esc((f.choices || [f.q])[0])}${req}</label>`;
    else if (f.type === 'faculty') c = `<input id="${id}" data-f="${esc(f.fid)}" data-pick="faculty" list="${id}-dl" value="${esc(v)}" placeholder="Start typing a name"><datalist id="${id}-dl"></datalist>`;
    else if (f.type === 'roster_roll') c = `<textarea id="${id}" data-f="${esc(f.fid)}" data-roll="1" rows="3" placeholder="One roll number per line">${esc(v)}</textarea><div class="en-chips" id="${id}-chips"></div>
      <input class="input compact" data-find="${esc(f.fid)}" placeholder="Find a student by name or roll number" autocomplete="off"><div class="en-find" id="${id}-find"></div>`;
    else if (f.type === 'roster_any') c = `<textarea id="${id}" data-f="${esc(f.fid)}" rows="3" placeholder="One person per line: ID - Name (EXT for someone outside)">${esc(v)}</textarea>`;
    else if (f.type === 'photo') c = `<div class="en-drop" id="${id}-drop"><label><input type="file" accept="image/*" multiple data-photo="${esc(f.fid)}" hidden><span><b>Add photos</b> · take one or choose from your phone</span></label></div><div class="en-thumbs" id="${id}-thumbs"></div>`;
    else c = `<input id="${id}" data-f="${esc(f.fid)}" value="${esc(v)}">`;
    return `<div class="en-f ${f.type === 'para' || f.type === 'roster_roll' || f.type === 'roster_any' || f.type === 'photo' || f.type === 'multi' || f.type === 'file' ? 'wide' : ''}" data-fid="${esc(f.fid)}"><label class="en-l" for="${id}">${esc(f.q)}${req}</label>${c}${help}</div>`;
  }

  function drawComposer() {
    const fs = E.form.fields, main = fs.filter(isMain), more = fs.filter(f => !isMain(f));
    $('#en-composer').innerHTML = `<div class="en-comp"><div class="card en-card">
        <div class="card-head"><h3>${esc(E.category)}</h3><button class="btn sm" id="en-close">Close</button></div>
        <div class="en-fields">${main.map(f => fieldHtml(f)).join('')}</div>
        ${more.length ? `<details class="en-more"><summary>More details <span class="muted">(${more.length} optional)</span></summary><div class="en-fields">${more.map(f => fieldHtml(f)).join('')}</div></details>` : ''}
        <div class="en-actions"><button class="btn" id="en-save">Save draft</button><button class="btn primary large" id="en-submit">Submit for approval</button><span class="muted" id="en-saved"></span></div></div></div>`;
    $('#en-composer').querySelectorAll('.en-f input:not([type=checkbox]):not([type=file]), .en-chips + input').forEach(i => i.classList.add('input'));
    for (const f of fs) { if (f.type === 'photo') drawThumbs(f.fid); if (f.type === 'file') drawDoc(f.fid); if (f.type === 'roster_roll') checkRolls(f.fid); }
    wire();
    $('#en-close').onclick = () => { $('#en-composer').innerHTML = ''; E.form = null; drawTiles($('#en-q').value); };
    $('#en-save').onclick = go(async () => { await saveDraft(); toast('Draft saved'); });
    $('#en-submit').onclick = go(submit);
  }

  function setValue(fid, v) { E.values[fid] = v; autosave(); }
  function wire() {
    const box = $('#en-composer');
    box.oninput = e => {
      const t = e.target, fid = t.dataset.f; if (!fid) return;
      if (t.type === 'checkbox') return setValue(fid, t.checked ? 'yes' : '');
      setValue(fid, t.value); t.closest('.en-f')?.classList.remove('bad');
      if (t.dataset.roll) checkRolls(fid); if (t.dataset.pick) suggestFaculty(t);
    };
    box.onchange = e => { const t = e.target; if (t.dataset.doc) uploadDoc(t.dataset.doc, t.files[0]).then(() => { t.value = ''; }); else if (t.dataset.photo) uploadPhotos(t.dataset.photo, t.files).then(() => { t.value = ''; }); else if (t.tagName === 'SELECT' && t.dataset.f) setValue(t.dataset.f, t.value); };
    box.onclick = e => {
      const pill = e.target.closest('.en-pill');
      if (pill && pill.parentElement.dataset.multi) { const fid = pill.parentElement.dataset.f, list = Array.isArray(E.values[fid]) ? E.values[fid] : String(E.values[fid] || '').split(', ').filter(Boolean); E.values[fid] = list.includes(pill.dataset.v) ? list.filter(x => x !== pill.dataset.v) : [...list, pill.dataset.v]; pill.classList.toggle('on'); autosave(); }
      else if (pill) { const grp = pill.parentElement, fid = grp.dataset.f, cur = E.values[fid] === pill.dataset.v; E.values[fid] = cur ? '' : pill.dataset.v; grp.querySelectorAll('.en-pill').forEach(p => p.classList.toggle('on', p.dataset.v === E.values[fid])); autosave(); }
      const nodoc = e.target.closest('[data-nodoc]'); if (nodoc) { const fid = nodoc.dataset.nodoc; E.values[fid] = ''; drawDoc(fid); autosave(); }
      const rm = e.target.closest('[data-rm]'); if (rm) { const [fid, id] = rm.dataset.rm.split('|'); E.photos[fid] = E.photos[fid].filter(p => String(p.media_id) !== id); syncPhotos(fid); drawThumbs(fid); }
      const pick = e.target.closest('[data-add]'); if (pick) { const [fid, roll] = pick.dataset.add.split('|'), cur = String(E.values[fid] || '').split('\n').filter(Boolean); if (!cur.includes(roll)) cur.push(roll); E.values[fid] = cur.join('\n'); const ta = box.querySelector(`textarea[data-f="${CSS.escape(fid)}"]`); ta.value = E.values[fid]; checkRolls(fid); autosave(); box.querySelectorAll(`.en-find`).forEach(x => x.innerHTML = ''); }
    };
    box.addEventListener('input', debounce(async e => {
      const f = e.target.dataset?.find; if (!f) return; const q = e.target.value.trim(), out = e.target.nextElementSibling;
      if (q.length < 2) { out.innerHTML = ''; return; }
      const r = await api('/api/entry/people?kind=student&q=' + encodeURIComponent(q));
      out.innerHTML = r.map(s => `<button type="button" class="en-hit" data-add="${esc(f)}|${esc(s.roll_no)}">${esc(s.name)} <span class="muted">${esc(s.roll_no)}${s.class ? ' · ' + esc(s.class) : ''}</span></button>`).join('') || '<span class="muted">No student found</span>';
    }, 250));
  }

  const suggestFaculty = debounce(async t => {
    const r = await api('/api/entry/people?kind=faculty&q=' + encodeURIComponent(t.value.replace(/ - .*/, '')));
    const dl = document.getElementById(t.id + '-dl'); if (dl) dl.innerHTML = r.map(x => `<option value="${esc(x.label)}">`).join('');
  }, 200);

  const checkRolls = debounce(async fid => {
    const f = E.form.fields.find(x => x.fid === fid), id = 'ef-' + fid.replace(/[^\w]/g, '_'), el = document.getElementById(id + '-chips'); if (!el || !f) return;
    const text = String(E.values[fid] || '').trim(); if (!text) { el.innerHTML = ''; return; }
    const r = await api('/api/entry/rolls?text=' + encodeURIComponent(text));
    el.innerHTML = r.map(x => `<span class="en-chip ${x.found ? 'ok' : 'bad'}">${x.found ? esc(x.name) + ' · ' + esc(x.roll_no) : esc(x.roll_no) + ' not found'}</span>`).join('');
  }, 300);

  async function uploadPhotos(fid, files) {
    for (const file of files) {
      const t = $('#en-saved'); if (t) t.textContent = 'Uploading ' + file.name + '…';
      const form = new FormData(); form.append('file', file);
      try { const m = await api('/api/media', { method: 'POST', form }); if (!E.photos[fid].some(p => p.media_id === m.media_id)) E.photos[fid].push(m); }
      catch (e) { toast(e.message, true); }
    }
    syncPhotos(fid); drawThumbs(fid); if ($('#en-saved')) $('#en-saved').textContent = '';
  }
  async function uploadDoc(fid, file) {
    if (!file) return;
    const t = $('#en-saved'); if (t) t.textContent = 'Uploading ' + file.name + '…';
    const form = new FormData(); form.append('file', file);
    try { const m = await api('/api/media?kind=document', { method: 'POST', form }); E.values[fid] = m.link_ref; (E.values._docnames = E.values._docnames || {})[fid] = m.name; autosave(); }
    catch (e) { toast(e.message, true); }
    drawDoc(fid); if ($('#en-saved')) $('#en-saved').textContent = '';
  }
  function drawDoc(fid) {
    const el = document.getElementById('ef-' + fid.replace(/[^\w]/g, '_') + '-doc'); if (!el) return;
    const v = String(E.values[fid] || '');
    el.innerHTML = v ? `<a href="${esc(fileHref(v))}" target="_blank" rel="noopener">${esc((E.values._docnames || {})[fid] || 'Uploaded document')} ↗</a> <button type="button" class="btn sm" data-nodoc="${esc(fid)}">Remove</button>` : '';
  }
  function syncPhotos(fid) { const ids = E.photos[fid].map(p => p.media_id); E.values[fid] = ids; E.values._more_photos = ids.slice(1); autosave(); }
  function drawThumbs(fid) {
    const el = document.getElementById('ef-' + fid.replace(/[^\w]/g, '_') + '-thumbs'); if (!el) return;
    el.innerHTML = E.photos[fid].map((p, i) => `<div class="en-th">${p.thumb_url ? `<img src="${p.thumb_url}" alt="Photo ${i + 1}">` : '<div class="en-th-x">Photo</div>'}<button type="button" data-rm="${esc(fid)}|${p.media_id}" aria-label="Remove photo">×</button>${i === 0 ? '<span>Main</span>' : ''}</div>`).join('');
  }

  const autosave = debounce(() => saveDraft().catch(() => { }), 1200);
  async function saveDraft() {
    const hasAny = Object.values(E.values).some(v => Array.isArray(v) ? v.length : String(v).trim());
    if (!E.form || !hasAny) return;
    await api('/api/entry/drafts/' + E.draftId, { method: 'PUT', body: { form_id: E.formId, category: E.category, values: E.values } });
    const t = $('#en-saved'); if (t) t.textContent = 'Draft saved';
  }

  async function submit() {
    const missing = E.form.fields.filter(f => f.req && !(Array.isArray(val(f)) ? val(f).length : String(val(f)).trim()));
    document.querySelectorAll('.en-f.bad').forEach(x => x.classList.remove('bad'));
    if (missing.length) {
      missing.forEach(f => document.querySelector(`.en-f[data-fid="${CSS.escape(f.fid)}"]`)?.classList.add('bad'));
      const first = document.querySelector('.en-f.bad'); if (first) { first.closest('details')?.setAttribute('open', ''); first.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      return toast('Please fill in: ' + missing.map(f => f.q).join(', '), true);
    }
    const btn = $('#en-submit'); btn.disabled = true;
    try {
      const r = await api('/api/entry/submit', { method: 'POST', body: { form_id: E.formId, category: E.category, values: E.values, draft_id: E.draftId } });
      E.drafts = E.drafts.filter(d => d.draft_id !== E.draftId); refreshReviewBadge && refreshReviewBadge();
      $('#en-composer').innerHTML = `<div class="card en-done"><div class="rv-empty-ico">✓</div><h3>Sent for approval</h3><p class="muted">“${esc(r.title)}” will be used once the Admin or HoD approves it.</p>
        <div class="en-actions" style="justify-content:center"><button class="btn primary" id="en-again">Add another like this</button><button class="btn" id="en-other">Add something else</button><button class="btn" id="en-mine">See my submissions</button></div></div>`;
      const keep = { ...E.values };
      $('#en-again').onclick = go(() => openComposer(E.formId, E.category, { draft_id: uid(), values: Object.fromEntries(Object.entries(keep).filter(([k]) => E.form.fields.find(f => f.fid === k && f.zone === 'common'))) }));
      $('#en-other').onclick = () => { $('#en-composer').innerHTML = ''; E.form = null; drawDrafts(); drawTiles(''); $('#en-q').value = ''; $('#en-q').focus(); };
      $('#en-mine').onclick = () => window.reviewOpen('mine');
    } finally { btn.disabled = false; }
  }

  window.Entry = { viewEntry };
  // The Admin's builder draws fields with exactly this code, so what the Admin edits is what faculty see.
  window.EntryUI = { fieldHtml: f => fieldHtml(f, ''), isMain };
  VIEWS.entry = viewEntry;
})();
