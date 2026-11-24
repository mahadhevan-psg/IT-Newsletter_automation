/* Form builder (Admin): add, change, move, retire or delete fields and categories, and manage the newsletter's sections.
   Changes are made in a DRAFT; nothing changes for anyone until "Publish changes". Old entries keep the answers they were saved with.   */
(function () {
  'use strict';
  const B = { forms: [], formId: null, v: null, cat: null, sel: null, adding: false, after: null };
  const NAMES = { text: 'Short text', para: 'Long text', number: 'Number', date: 'Date', choice: 'Pick one (buttons)', list: 'Pick one (drop-down)', url: 'Link', faculty: 'Faculty member', roster_roll: 'Students', roster_any: 'People', photo: 'Photo', confirm: 'Tick box' };

  async function viewBuilder() {
    B.forms = await api('/api/defs/forms');
    if (!B.formId) B.formId = B.forms[0].form_id;
    await load();
  }
  async function load(v) {
    B.v = v || await api('/api/defs/forms/' + B.formId);
    if (!B.v.placement && (!B.cat || !B.v.categories.some(c => c.name === B.cat))) B.cat = B.v.categories[0]?.name || null;
    draw();
  }
  async function op(body) { B.v = await api(`/api/defs/forms/${B.formId}/ops`, { method: 'POST', body }); if (!B.v.categories.some(c => c.name === B.cat)) B.cat = B.v.categories[0]?.name; draw(); }
  const inCat = f => !f.cats || f.cats.includes(B.cat);
  const live = () => B.v.fields.filter(f => !f.retired && inCat(f));

  function draw() {
    const v = B.v;
    $('#view').innerHTML = `<div class="card-head"><div><h2>Form builder</h2><p class="hint" style="margin:2px 0 0">Change what people are asked when they add an entry. Your changes stay in a draft until you publish them.</p></div></div>
      <div class="bd-forms">${B.forms.map(f => `<button class="rv-tab ${f.form_id === B.formId ? 'on' : ''}" data-form="${f.form_id}">${esc(f.title)}${f.has_draft ? ' <span class="bd-dot" title="Unpublished changes"></span>' : ''}</button>`).join('')}</div>
      ${v.has_draft ? `<div class="rv-banner warn bd-draft"><div><b>You have changes that are not live yet.</b>${v.problems.length ? `<div class="bd-prob">${v.problems.map(p => '⚠ ' + esc(p)).join('<br>')}</div>` : ' <span class="muted">Everyone still sees the published version.</span>'}</div>
        <div><button class="btn" id="bd-discard">Discard</button> <button class="btn primary" id="bd-publish">Publish changes</button></div></div>` : ''}
      ${v.placement ? placementHtml() : `${sectionsHtml()}<div class="bd2-lab">Faculty choose what happened</div>${tilesHtml()}<div class="bd2-lab">Then they see this (click anything to change it)</div>
        <div class="bd2"><div class="bd2-main">${canvasHtml()}</div><aside class="bd-edit bd2-side" id="bd-edit">${editorHtml()}</aside></div>`}
      <p class="hint" style="margin-top:14px">Published version ${v.version} · <a href="#" id="bd-hist">History and earlier versions</a></p>`;
    $('#view').querySelectorAll('.bd-canvas .en-f input:not([type=checkbox]):not([type=file])').forEach(i => i.classList.add('input'));
    wire();
  }

  function placementHtml() {
    return `<div class="card"><p class="hint">The placement record is filled in by students in steps. Its fields are tied to the placement tables, so this list is for reading; ask for a change if a question must be added.</p>
      ${B.v.fields.map(f => f.section ? `<h4 style="margin-top:12px">${esc(f.label)}</h4>` : `<div class="bd-field"><span>${esc(f.label)}</span><span class="pill">${esc(NAMES[f.type] || f.type)}</span>${f.required ? '<span class="muted">Required</span>' : ''}</div>`).join('')}</div>`;
  }

  const byFid = fid => B.v.fields.find(f => f.fid === fid);
  const asEntry = f => ({ fid: f.fid, q: f.display, type: f.widget, req: f.required, help: f.help, choices: f.choices });

  function sectionsHtml() {
    return `<div class="bd2-secs"><span class="muted">Newsletter sections:</span>${B.v.sections.map(s => `<span class="bd-sec ${s.enabled ? '' : 'off'}"><button class="bd-secname" data-smenu="${s.section_id}" title="Rename, switch off or delete">${esc(s.name)}</button>
        <span class="bd-ctl"><button data-sup="${s.section_id}" title="Earlier in the newsletter">←</button><button data-sdn="${s.section_id}" title="Later in the newsletter">→</button></span></span>`).join('')}
      <button class="btn sm" id="bd-addsec">+ Section</button></div>`;
  }

  function tilesHtml() {
    const secName = id => (B.v.sections.find(s => s.section_id === id) || {}).name || '';
    return `<div class="en-grid">${B.v.categories.map(c => `<div class="bd-tilew"><button class="en-tile ${c.name === B.cat ? 'on' : ''}" data-cat="${esc(c.name)}"><b>${esc(c.tile || c.name)}</b><span>${esc(c.name)} · ${esc(secName(c.section_id))}</span></button>
        <span class="bd-ctl"><button data-cup="${esc(c.name)}" title="Move earlier">↑</button><button data-cdn="${esc(c.name)}" title="Move later">↓</button><button data-cmenu="${esc(c.name)}" title="Rename, wording, section, delete">⋯</button></span></div>`).join('')}
      <button class="en-tile bd-new" id="bd-addcat"><b>+ New category</b><span>A new kind of entry</span></button></div>`;
  }

  // One field exactly as faculty see it (same renderer), wrapped so it can be selected and changed in place.
  function fieldBox(f, i, n) {
    const tools = f.locked ? '<span class="bd-tools"><span class="muted">System field</span></span>' : `<span class="bd-tools"><button data-fup="${esc(f.fid)}" title="Move up" ${i === 0 ? 'disabled' : ''}>↑</button><button data-fdn="${esc(f.fid)}" title="Move down" ${i === n - 1 ? 'disabled' : ''}>↓</button>
      <button data-freq="${esc(f.fid)}" title="Required or optional">${f.required ? 'Required ✓' : 'Optional'}</button></span>`;
    return `<div class="bd-fw${B.sel === f.fid ? 'on' : ''}" data-fid="${esc(f.fid)}">${tools}<div class="bd-body">${window.EntryUI.fieldHtml(asEntry(f))}</div>
</div>
      <button class="bd-ins" data-after="${esc(f.fid)}">+ Add a field here</button>`;
  }
  function canvasHtml() {
    const c = B.v.categories.find(x => x.name === B.cat);
    if (!c) return '<div class="empty">This form has no categories. Add one.</div>';
    const fs = c.fids.map(byFid).filter(Boolean), main = fs.filter(f => window.EntryUI.isMain(asEntry(f))), more = fs.filter(f => !window.EntryUI.isMain(asEntry(f)));
    const list = [...main, ...more], idx = f => list.indexOf(f);
    const box = f => fieldBox(f, idx(f), list.length);
    const auto = c.automatic.map(byFid).filter(Boolean), retired = c.retired_fids.map(byFid).filter(Boolean);
    return `<div class="en-comp bd-canvas"><div class="card en-card"><div class="card-head"><h3>${esc(c.name)}</h3></div>
        <div class="en-fields">${main.map(box).join('')}</div>
        <button class="bd-ins show" data-after="">+ Add a field</button>
        ${more.length ? `<details class="en-more" open><summary>More details <span class="muted">(${more.length} optional)</span></summary><div class="en-fields">${more.map(box).join('')}</div></details>` : ''}
        <div class="en-actions"><button class="btn" disabled>Save draft</button><button class="btn primary large" disabled>Submit for approval</button><span class="muted">Buttons are switched off while editing</span></div>
        ${auto.length ? `<p class="hint bd-auto">Filled in automatically: ${auto.map(f => esc(f.display)).join(', ')}</p>` : ''}
        ${retired.length ? `<details class="bd-retired"><summary>Retired fields (${retired.length}) <span class="muted">hidden from new entries; old answers stay readable</span></summary>${retired.map(f => `<div class="bd-field"><span class="bd-name muted">${esc(f.label)}</span><button class="btn sm" data-restore="${esc(f.fid)}">Bring back</button></div>`).join('')}</details>` : ''}</div></div>`;
  }

  function editorHtml() {
    if (B.adding) return fieldForm(null);
    const f = B.v.fields.find(x => x.fid === B.sel);
    if (!f) return '<div class="empty" style="padding:30px 10px">Click any field on the left to change its name, choices, help text or newsletter use. Use “+ Add a field here” to put a new one exactly where you want it.</div>';
    return fieldForm(f);
  }
  const GUESS = [[/\b(date|when|day)\b/i, 'date'], [/\b(count|number of|amount|how many)\b/i, 'number'], [/\b(link|url|website|proof|certificate)\b/i, 'url'], [/\b(description|details|summary|remarks|abstract|outcome)\b/i, 'para']];
  function fieldForm(f) {
    const nu = !f, locked = f && f.locked, cats = B.v.categories, simple = ['text', 'para', 'number', 'date', 'url', 'choice', 'list'];
    const types = nu || simple.includes(f.type) ? Object.entries(B.v.types).filter(([k]) => nu ? true : simple.includes(k)) : [[f.type, NAMES[f.type] || f.type]];
    const shared = f && f.cats && f.cats.length > 1;
    return `<h4>${nu ? 'New field' : 'Field'}</h4>${locked ? '<p class="hint">This is a system field. The application fills or needs it, so it cannot be changed here.</p>' : ''}
      <div class="field"><label>Name people see</label><input class="input" id="fe-label" value="${esc(f?.label || '')}" ${locked ? 'disabled' : ''} placeholder="${nu ? 'e.g. Event venue' : ''}"></div>
      <div class="field"><label>Kind of answer</label><select id="fe-type" ${locked ? 'disabled' : ''}>${types.map(([k, l]) => `<option value="${k}" ${(f?.type || 'text') === k ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></div>
      <div class="field" id="fe-choices-box" style="display:none"><label>Choices (one per line)</label><textarea class="input" id="fe-choices" rows="4">${esc((f?.choices || []).join('\n'))}</textarea></div>
      <label class="rv-check"><input type="checkbox" id="fe-req" ${f?.required ? 'checked' : ''} ${locked ? 'disabled' : ''}> Required</label>
      ${shared ? `<p class="hint">This field is shared by ${f.cats.length} categories; a change here applies to all of them.</p>` : ''}
      ${locked ? '' : `<div class="bd-btns"><button class="btn primary" id="fe-save">${nu ? 'Add field' : 'Save field'}</button>${nu ? '<button class="btn" id="fe-cancel">Cancel</button>' : ''}</div>`}
      ${locked ? '' : `<details class="bd-more"><summary>More options</summary>
        <div class="field"><label>Help text (optional)</label><input class="input" id="fe-help" value="${esc(f?.help || '')}"></div>
        <div class="field"><label>In the newsletter as</label><select id="fe-nl"><option value="">Not used in the newsletter</option>${Object.entries(B.v.roles).map(([k, l]) => `<option value="${k}" ${f?.newsletter === k ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></div>
        ${nu ? `<div class="field"><label>Where it appears</label><select id="fe-where"><option value="this">Only in ${esc(B.cat || '')}</option><option value="all">In every category of this form</option></select></div>`
          : `<div class="bd-btns"><button class="btn" id="fe-retire">${shared ? 'Remove from this category' : 'Remove from the form'}</button><button class="btn danger" id="fe-delete">Delete for good</button></div>
        <p class="hint">Removing hides it from new entries; answers already given stay and still show. Delete removes it entirely (the answers stay stored).</p>`}</details>`}`;
  }

  function showChoices() { const t = $('#fe-type'); if (t) $('#fe-choices-box').style.display = ['choice', 'list'].includes(t.value) ? 'block' : 'none'; }

  function wire() {
    const view = $('#view');
    view.onclick = go(async e => {
      const t = e.target, q = s => t.closest(s);
      if (q('[data-form]')) { B.formId = q('[data-form]').dataset.form; B.cat = null; B.sel = null; B.adding = false; return load(); }
      if (q('[data-cup]')) return op({ op: 'move_category', name: q('[data-cup]').dataset.cup, direction: -1 });
      if (q('[data-cdn]')) return op({ op: 'move_category', name: q('[data-cdn]').dataset.cdn, direction: 1 });
      if (q('[data-cmenu]')) return categoryMenu(q('[data-cmenu]').dataset.cmenu);
      if (q('[data-cat]')) { B.cat = q('[data-cat]').dataset.cat; B.sel = null; B.adding = false; return draw(); }
      if (q('#bd-addcat')) return addCategory();
      if (q('#bd-addsec')) return sectionDialog();
      if (q('[data-sup]')) return secOp({ op: 'move', section_id: q('[data-sup]').dataset.sup, direction: -1 });
      if (q('[data-sdn]')) return secOp({ op: 'move', section_id: q('[data-sdn]').dataset.sdn, direction: 1 });
      if (q('[data-smenu]')) return sectionDialog(q('[data-smenu]').dataset.smenu);
      if (q('[data-fup]')) return op({ op: 'move_field', fid: q('[data-fup]').dataset.fup, direction: -1, category: B.cat });
      if (q('[data-fdn]')) return op({ op: 'move_field', fid: q('[data-fdn]').dataset.fdn, direction: 1, category: B.cat });
      if (q('[data-restore]')) return op({ op: 'restore_field', fid: q('[data-restore]').dataset.restore });
      if (q('[data-freq]')) { const f = byFid(q('[data-freq]').dataset.freq); B.sel = f.fid; return op({ op: 'update_field', fid: f.fid, changes: { required: !f.required } }); }
      if (q('.bd-tools')) return;
      if (q('[data-after]')) { B.adding = true; B.after = q('[data-after]').dataset.after || null; B.sel = null; draw(); $('#fe-label').focus(); return; }
      if (q('.bd-fw[data-fid]')) { B.sel = q('.bd-fw[data-fid]').dataset.fid; B.adding = false; draw(); return; }
      if (q('#bd-publish')) return publish();
      if (q('#bd-discard')) { if (!confirm('Throw away all the unpublished changes to this form?')) return; B.v = await api(`/api/defs/forms/${B.formId}/discard`, { method: 'POST' }); B.sel = null; draw(); toast('Changes discarded'); return; }
      if (q('#bd-hist')) { e.preventDefault(); return history(); }
    });
    wireEditor();
  }
  function wireEditor() {
    showChoices(); const t = $('#fe-type'); if (t) t.onchange = showChoices;
    const lab = $('#fe-label'); if (lab && !lab.disabled) { lab.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); $('#fe-save')?.click(); } };
      if (B.adding) lab.oninput = () => { const g = GUESS.find(([re]) => re.test(lab.value)); if (g && t) { t.value = g[1]; showChoices(); } }; }
    const body = () => ({ label: $('#fe-label').value, type: $('#fe-type').value, required: $('#fe-req').checked, help: $('#fe-help').value, choices: $('#fe-choices').value.split('\n'), newsletter: $('#fe-nl').value || null });
    const save = $('#fe-save'); if (save) save.onclick = go(async () => {
      const b = body();
      if (B.adding) { await op({ op: 'add_field', label: b.label, type: b.type, categories: ($('#fe-where')?.value === 'all') ? null : [B.cat], required: b.required, choices: b.choices, help: b.help, newsletter: b.newsletter, after: B.after }); B.adding = false; B.after = null; B.sel = null; draw(); toast('Field added to the draft'); }
      else { await op({ op: 'update_field', fid: B.sel, changes: { label: b.label, type: b.type, required: b.required, help: b.help, choices: b.choices, newsletter: b.newsletter || '' } }); toast('Saved in the draft'); }
    });
    const cancel = $('#fe-cancel'); if (cancel) cancel.onclick = () => { B.adding = false; B.after = null; draw(); };
    const ret = $('#fe-retire'); if (ret) ret.onclick = go(async () => { await op({ op: 'retire_field', fid: B.sel, category: B.cat }); B.sel = null; draw(); toast('Retired in the draft'); });
    const del = $('#fe-delete'); if (del) del.onclick = go(async () => { if (!confirm('Delete this field from the form?\n\nAnswers already given stay stored, but the field is no longer asked or shown. Retire it instead if you may want it back.')) return; await op({ op: 'delete_field', fid: B.sel }); B.sel = null; draw(); toast('Deleted in the draft'); });
  }

  function addCategory() {
    const secs = B.v.sections;
    modal('Add a category', `<div class="field"><label>Name</label><input class="input" id="ac-name" placeholder="e.g. Technical reports"></div>
      <div class="field"><label>Newsletter section</label><select id="ac-sec">${secs.map(s => `<option value="${s.section_id}" ${s.section_id === B.v.section_id ? 'selected' : ''}>${esc(s.name)}</option>`).join('')}</select></div>
      <p class="hint">It starts with a title, a date and a description. Add or change fields afterwards.</p>`,
      async o => { const name = $('#ac-name', o).value; await op({ op: 'add_category', name, section_id: $('#ac-sec', o).value }); B.cat = name.trim(); draw(); }, 'Add');
  }
  function categoryMenu(name) {
    const c = B.v.categories.find(x => x.name === name);
    const o = modal('Category: ' + name, `<div class="field"><label>Name</label><input class="input" id="cm-name" value="${esc(name)}"></div>
      <div class="field"><label>Wording on the “What happened?” tile</label><input class="input" id="cm-tile" value="${esc(c.tile || '')}" placeholder="e.g. I published a journal paper"></div>
      <div class="field"><label>Words that find it in the search</label><input class="input" id="cm-kw" value="${esc(c.keywords || '')}"></div>
      <div class="field"><label>Newsletter section</label><select id="cm-sec">${B.v.sections.map(s => `<option value="${s.section_id}" ${s.section_id === c.section_id ? 'selected' : ''}>${esc(s.name)}</option>`).join('')}</select></div>
      <div><button class="btn danger" id="cm-del">Delete this category…</button></div>`,
      async o => {
        const nn = $('#cm-name', o).value.trim();
        if (nn && nn !== name) await op({ op: 'rename_category', name, new_name: nn });
        await op({ op: 'category_meta', name: nn || name, tile: $('#cm-tile', o).value, keywords: $('#cm-kw', o).value, section_id: $('#cm-sec', o).value });
      }, 'Save');
    $('#cm-del', o).onclick = go(async () => {
      if (!confirm(`Delete “${name}”?\n\nEntries already saved in it stay, with all their answers. New entries can no longer be made in it. Fields only this category used are retired.`)) return;
      await op({ op: 'delete_category', name }); o.remove();
    });
  }
  async function secOp(body) { await api('/api/defs/sections', { method: 'POST', body }); await load(); }
  function sectionDialog(id) {
    const s = id && B.v.sections.find(x => x.section_id === id);
    const o = modal(s ? 'Section: ' + s.name : 'Add a newsletter section', `<div class="field"><label>Name</label><input class="input" id="sd-name" value="${esc(s?.name || '')}"></div>
      ${s ? `<label class="rv-check"><input type="checkbox" id="sd-on" ${s.enabled ? 'checked' : ''}> Include this section in the newsletter</label><div style="margin-top:12px"><button class="btn danger" id="sd-del">Delete this section…</button></div>` : '<p class="hint">Sections take effect at once. Then move categories into it from a category’s menu.</p>'}`,
      async o => {
        if (!s) return secOp({ op: 'add', name: $('#sd-name', o).value });
        if ($('#sd-name', o).value.trim() !== s.name) await api('/api/defs/sections', { method: 'POST', body: { op: 'rename', section_id: id, name: $('#sd-name', o).value } });
        if ($('#sd-on', o).checked !== s.enabled) await api('/api/defs/sections', { method: 'POST', body: { op: 'toggle', section_id: id, enabled: $('#sd-on', o).checked } });
        await load();
      }, 'Save');
    const del = $('#sd-del', o); if (del) del.onclick = go(async () => { if (!confirm('Delete this section? It must be empty of categories.')) return; await secOp({ op: 'delete', section_id: id }); o.remove(); });
  }

  async function publish() {
    if (B.v.problems.length) return toast(B.v.problems[0], true);
    const r = await api(`/api/defs/forms/${B.formId}/publish`, { method: 'POST', body: { note: '' } });
    B.forms = await api('/api/defs/forms'); B.sel = null; B.adding = false; load(r.form);
    const a = r.impact || {}, n = (a.added_fields || []).length, rn = (a.renamed_fields || []).length, rt = (a.retired_fields || []).length, nc = (a.new_categories || []).length;
    toast(`Published (version ${r.version})` + [n && `${n} new field${n > 1 ? 's' : ''}`, rn && `${rn} renamed`, rt && `${rt} removed`, nc && `${nc} new categor${nc > 1 ? 'ies' : 'y'}`].filter(Boolean).map((x, k) => (k ? ', ' : ': ') + x).join(''));
  }
  async function history() {
    const h = await api(`/api/defs/forms/${B.formId}/history`);
    const o = modal('History', `<table class="table"><thead><tr><th>Version</th><th>State</th><th>When</th><th>Note</th><th></th></tr></thead><tbody>${h.map(x => `<tr><td>${x.version}</td><td>${esc(x.status)}</td><td>${esc(x.published_at || x.created_at || '')}</td><td>${esc(x.note || '')}</td>
      <td>${x.status === 'archived' ? `<button class="btn sm" data-rs="${x.version}">Edit from this version</button>` : ''}</td></tr>`).join('')}</tbody></table>
      <p class="hint">“Edit from this version” puts it in your draft; publish it to bring it back.</p>`, null, '', true);
    o.onclick = go(async e => { const b = e.target.closest('[data-rs]'); if (!b) return; B.v = await api(`/api/defs/forms/${B.formId}/restore`, { method: 'POST', body: { version: +b.dataset.rs } }); o.remove(); draw(); toast('Earlier version loaded into your draft'); });
  }

  window.Builder = { viewBuilder };
  VIEWS.builder = viewBuilder;
})();
