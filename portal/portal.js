/* IT Department Portal: staff (tutors, coordinators, HoD, Admin, faculty). Pages shown depend on the signed-in person's roles. */
const $ = (s, r = document) => r.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let token = sessionStorage.getItem('tok'), me = null, meta = null, current = 'dash';

// ---------------------------------------------------------------- helpers
function toast(msg, bad) {
  const t = document.createElement('div'); t.className = 'toast' + (bad ? ' bad' : ''); t.textContent = msg;
  document.body.appendChild(t); setTimeout(() => t.remove(), bad ? 6000 : 3000);
}
async function api(path, o = {}) {
  const init = { method: o.method || 'GET', headers: token ? { Authorization: 'Bearer ' + token } : {} };
  if (o.form) init.body = o.form;
  else if (o.body !== undefined) { init.body = JSON.stringify(o.body); init.headers['Content-Type'] = 'application/json'; }
  const r = await fetch(path, init);
  if (r.status === 401 && token) { logout(); throw new Error('Please sign in again'); }
  if (!r.ok) {
    let d = r.statusText; try { const j = await r.json(); d = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch (e) { }
    throw new Error(d);
  }
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : r.text();
}
const go = (fn) => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, true); } };
async function download(path, name) {
  const r = await fetch(path, { headers: { Authorization: 'Bearer ' + token } });
  if (!r.ok) return toast('Download failed', true);
  const a = document.createElement('a'); a.href = URL.createObjectURL(await r.blob()); a.download = name; a.click();
}
function modal(title, html, onSave, saveLabel = 'Save', wide) {
  const o = document.createElement('div'); o.className = 'overlay';
  o.innerHTML = `<div class="dialog ${wide ? 'wide' : ''}"><div class="dialog-head"><h3>${esc(title)}</h3><button class="x">×</button></div>
    <div class="dialog-body">${html}</div><div class="dialog-foot"><button class="btn cancel">${onSave ? 'Cancel' : 'Close'}</button>${onSave ? `<button class="btn primary save">${saveLabel}</button>` : ''}</div></div>`;
  document.body.appendChild(o);
  const close = () => o.remove();
  $('.x', o).onclick = $('.cancel', o).onclick = close;
  if (onSave) $('.save', o).onclick = go(async () => { if ((await onSave(o)) !== false) close(); });
  return o;
}
const opts = (list, val, lab, sel, blank) => (blank !== undefined ? `<option value="">${esc(blank)}</option>` : '') +
  list.map(x => `<option value="${esc(val(x))}" ${String(val(x)) === String(sel) ? 'selected' : ''}>${esc(lab(x))}</option>`).join('');
// A class is known by its tutor and semester; the code (UG-G1-2 ...) follows the semester.
const classLabel = c => `${c.tutor_name || 'No tutor'} · Sem ${c.current_semester} (${c.class_code})`;
const classOpts = (sel, blank, onlyEditable) => opts(meta.classes.filter(c => !onlyEditable || c.can_edit), c => c.class_id, classLabel, sel, blank);
// A person with exactly one class (a tutor) is never offered an "all classes" choice: the filter is fixed to her class.
// Only people who can see UG classes of both groups (coordinators, HoD, Admin) get the Both / G1 / G2 filter.
const hasBothGroups = () => new Set(meta.classes.map(c => c.grp).filter(Boolean)).size > 1;
const singleClass = () => !me.all_access && meta.classes.length === 1;
const classFilter = (id, blank) => singleClass() ? `<input type="hidden" id="${id}" value="${meta.classes[0].class_id}">` : `<select class="compact" id="${id}">${classOpts('', blank)}</select>`;
const ayOpts = (sel, blank) => opts(meta.academic_years, a => a, a => a, sel, blank);
function table(cols, rows, o = {}) {
  if (!rows.length) return '<div class="empty">Nothing to show.</div>';
  return `<div class="scroll"><table class="table"><thead><tr>${cols.map(c => `<th class="${c.num ? 'num' : ''}">${esc(c.h)}</th>`).join('')}</tr></thead><tbody>` +
    rows.map((r, i) => `<tr class="${o.click ? 'click' : ''}" data-i="${i}">${cols.map(c => `<td class="${c.num ? 'num' : ''}">${c.html ? c.html(r) : esc(c.f ? c.f(r) : r[c.k])}</td>`).join('')}</tr>`).join('') + '</tbody></table></div>';
}
function bars(series, unit = '') {
  if (!series || !series.length) return '<div class="empty">No data yet.</div>';
  const max = Math.max(...series.map(s => s.value), 1);
  return '<div class="bars">' + series.map(s => `<div class="bar-row"><span class="lbl" title="${esc(s.label)}">${esc(s.label)}</span><div class="bar"><i style="width:${Math.round(100 * s.value / max)}%"></i></div><span class="val">${esc(s.value)}${unit}</span></div>`).join('') + '</div>';
}
const kpi = (n, l) => `<div class="kpi"><b>${esc(n ?? '–')}</b><span>${esc(l)}</span></div>`;
// The Submissions tab is called what it holds: everything (Admin, HoD, coordinators), a tutor's class, or just your own
const seesAll = () => me.roles.some(r => ['ADMIN', 'HOD', 'PC'].includes(r));
const subsLabel = () => seesAll() ? 'All submissions' : me.tutor_class_ids.length ? 'Class submissions' : 'My submissions';
const isEditor = () => me.roles.includes('ADMIN') || me.tutor_class_ids.length > 0;
const hasClasses = () => me.all_access || me.class_ids.length > 0;
const fmtMoney = n => n == null ? '' : Number(n).toLocaleString('en-IN');

function resultBox(res) {
  const nums = Object.entries(res).filter(([, v]) => typeof v === 'number').map(([k, v]) => `<span class="pill ok">${esc(k.replace(/_/g, ' '))}: ${v}</span>`).join(' ');
  const probs = (res.errors || res.needs_attention || []);
  let h = `<div style="margin:10px 0">${nums}</div>`;
  if (probs.length) h += `<h4>Needs attention (${probs.length})</h4>` + table(
    [{ h: 'Row / ID', f: p => p.row ?? p.roll_no ?? p.emp_id ?? '' }, { h: 'Problem', f: p => [].concat(p.messages || p.message || '').join('; ') }], probs);
  if (res.credentials && res.credentials.length) {
    h += `<h4 style="margin-top:12px">New logins (shown once - share privately)</h4>` + table([{ h: 'Employee ID', k: 'emp_id' }, { h: 'Temporary password', k: 'temp_password' }], res.credentials) +
      `<button class="btn sm" id="dl-creds" style="margin-top:8px">Download CSV</button>`;
  }
  return h;
}
function uploadCard(o) {
  const id = 'up' + Math.random().toString(36).slice(2, 7);
  const html = `<div class="card" id="${id}"><div class="card-head"><h3>${esc(o.title)}</h3>${o.template ? `<button class="btn sm tpl">Download Excel template</button>` : ''}</div>
    <p class="hint">${o.hint || ''}</p><div class="filters">${o.extra || ''}</div>
    <label class="drop"><input type="file" accept=".xlsx" class="file" style="display:none"><strong class="fl">Choose an Excel (.xlsx) file</strong></label>
    <button class="btn primary go">Upload</button><div class="out"></div></div>`;
  setTimeout(() => {
    const el = $('#' + id); if (!el) return;
    const f = $('.file', el); f.onchange = () => $('.fl', el).textContent = f.files[0] ? f.files[0].name : 'Choose an Excel (.xlsx) file';
    if (o.template) $('.tpl', el).onclick = () => download(o.template[0], o.template[1]);
    $('.go', el).onclick = go(async () => {
      if (!f.files[0]) return toast('Choose a file first', true);
      const form = new FormData(); form.append('file', f.files[0]); if (o.fields) o.fields(el, form);
      $('.go', el).disabled = true;
      try {
        const res = await api(o.path, { method: 'POST', form });
        $('.out', el).innerHTML = resultBox(res);
        const dl = $('#dl-creds', el);
        if (dl) dl.onclick = () => { const a = document.createElement('a'); a.href = 'data:text/csv,' + encodeURIComponent('Employee ID,Temporary password\n' + res.credentials.map(c => c.emp_id + ',' + c.temp_password).join('\n')); a.download = 'new_logins.csv'; a.click(); };
        toast('Upload finished'); if (o.done) o.done(res);
      } finally { $('.go', el).disabled = false; }
    });
  }, 0);
  return html;
}

// ---------------------------------------------------------------- login / shell
async function start() {
  $('#logout').onclick = logout;
  if (token) { try { await boot(); return; } catch (e) { sessionStorage.removeItem('tok'); } }
  location.replace('/');            // not signed in: / is the sign-in page
}
function logout() { sessionStorage.removeItem('tok'); location.replace('/'); }
async function boot() {
  me = await api('/api/auth/me'); if (me.kind !== 'STAFF') throw new Error('staff only');
  meta = await api('/api/master/meta');
  $('#app').classList.remove('hidden');
  $('#who').textContent = `${me.name} · ${me.roles.filter(r => r !== 'FACULTY').join(', ') || 'Faculty'}`;
  if (me.roles.includes('ADMIN') || me.roles.includes('HOD')) $('#who').insertAdjacentHTML('beforeend', ' <a class="btn sm" href="/newsletter/">Newsletter studio</a>');
  const tabs = [
    ['dash', 'Dashboard', () => true], ['review', 'Approvals', () => true], ['sync', 'Data sync', () => me.roles.includes('ADMIN') || me.roles.includes('HOD') || me.tutor_class_ids.length > 0],
    ['students', 'Students', hasClasses], ['classes', 'Classes', hasClasses], ['uploads', 'Data upload', () => me.roles.includes('ADMIN')],
    ['placements', 'Placements', hasClasses], ['subs', subsLabel(), () => true], ['faculty', me.roles.includes('ADMIN') ? 'Faculty & roles' : 'Faculty', () => me.all_access], ['works', 'Reports', seesAll], ['mine', 'My activities', () => true], ['account', 'Account', () => true]]
    .filter(t => t[2]());
  $('#tabs').innerHTML = tabs.map(t => `<button class="tab" data-t="${t[0]}">${t[1]}</button>`).join('');
  $('#tabs').onclick = e => { const b = e.target.closest('[data-t]'); if (b) show(b.dataset.t); };
  if (window.refreshReviewBadge) refreshReviewBadge();
  const deep = location.hash.match(/^#\/(faculty|student)\/([^/]+)$/);       // a copied link to someone's page opens it directly
  show(me.must_change ? 'account' : tabs[0][0]);
  if (deep && !me.must_change) go(openProfile)(deep[1], decodeURIComponent(deep[2]));
  Tours.portal(me, token);                    // Help button; the welcome tour the first time this person opens the portal
}
function show(id) {
  current = id;
  if (location.hash) history.replaceState(null, '', location.pathname);
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.t === id));
  $('#banner').innerHTML = me.must_change ? '<div class="banner">Please set a new password (Account tab) - you are still using a temporary one.</div>' : '';
  $('#view').onclick = null;
  $('#view').innerHTML = '<div class="empty">Loading…</div>';
  go(VIEWS[id])();
}

// ---------------------------------------------------------------- dashboard
async function viewDash() {
  const st = { ay: '', cls: '', prog: '' };
  const draw = async () => {
    const qs = new URLSearchParams(); if (st.ay) qs.set('ay_id', st.ay); if (st.cls) qs.set('class_id', st.cls); if (st.prog) qs.set('programme', st.prog);
    const a = await api('/api/master/analytics?' + qs);
    const s = a.students, p = a.placements, d = a.department;
    $('#dash-out').innerHTML = `
      <div class="kpis">${kpi(s.active_students, 'Active students')}${kpi(s.students_with_achievements, 'Students with achievements')}${kpi(s.participation_rate + '%', 'Participation rate')}
        ${kpi(p.placement_percent + '%', 'Placed of opted-in')}${kpi(p.placed, 'Students placed')}${kpi(p.highest_lpa ? p.highest_lpa + ' LPA' : '–', 'Highest package')}${kpi(p.average_lpa ? p.average_lpa + ' LPA' : '–', 'Average package')}</div>
      <h2 style="margin:6px 0 12px">Student achievements</h2>
      <div class="grid-2"><div class="card"><h4>By category</h4>${bars(s.by_category)}</div><div class="card"><h4>By level</h4>${bars(s.by_level)}</div></div>
      <div class="grid-2"><div class="card"><h4>By domain</h4>${bars(s.by_domain)}</div><div class="card"><h4>By academic year</h4>${bars(s.by_year)}</div></div>
      <div class="grid-2"><div class="card"><h4>Class-wise participation</h4>${table([{ h: 'Class', k: 'label' }, { h: 'Students', k: 'students', num: 1 }, { h: 'Achievers', k: 'achievers', num: 1 }, { h: 'Achievements', k: 'achievements', num: 1 }], s.per_class)}</div>
        <div class="card"><h4>Top students</h4>${table([{ h: 'Roll no', html: r => profileLink('student', r.roll_no) }, { h: 'Name', k: 'name' }, { h: 'Class', k: 'class_code' }, { h: 'Count', k: 'achievements', num: 1 }], s.top_students)}</div></div>
      <h2 style="margin:6px 0 12px">Placements</h2>
      <div class="kpis">${kpi(p.opted_in, 'Opted in')}${kpi(p.opted_out, 'Opted out')}${kpi(p.unplaced_opted_in, 'Opted in, not placed')}${kpi(p.median_lpa ? p.median_lpa + ' LPA' : '–', 'Median package')}</div>
      <div class="grid-2"><div class="card"><h4>Package distribution (LPA)</h4>${bars(p.package_distribution)}</div><div class="card"><h4>Offer type</h4>${bars(p.by_offer_type)}</div></div>
      <div class="grid-2"><div class="card"><h4>Top recruiters</h4>${bars(p.by_company)}</div><div class="card"><h4>Placed per year</h4>${bars(p.by_year)}</div></div>
      <div class="card"><h4>Reasons for opting out</h4>${bars(p.opt_out_reasons)}</div>
      ${d ? `<h2 style="margin:6px 0 12px">Department</h2>
        <div class="kpis">${kpi(fmtMoney(d.funding_total_inr), 'Research funding (₹)')}${kpi(d.department_participants, 'Event participants')}${kpi(d.outreach_attendance, 'Outreach attendance')}</div>
        <div class="grid-2"><div class="card"><h4>Submissions by form</h4>${bars(d.submissions_by_form)}</div><div class="card"><h4>Submissions by year</h4>${bars(d.submissions_by_year)}</div></div>
        <div class="grid-2"><div class="card"><h4>Research by type</h4>${bars(d.research_by_category)}</div><div class="card"><h4>Research by indexing</h4>${bars(d.research_by_indexing)}</div></div>
        <div class="grid-2"><div class="card"><h4>Research by quartile</h4>${bars(d.research_by_quartile)}</div><div class="card"><h4>Faculty achievements by category</h4>${bars(d.faculty_by_category)}</div></div>
        <div class="grid-2"><div class="card"><h4>Faculty achievements by level</h4>${bars(d.faculty_by_level)}</div><div class="card"><h4>Department highlights</h4>${bars(d.department_by_category)}</div></div>
        <div class="grid-2"><div class="card"><h4>Outreach by category</h4>${bars(d.outreach_by_category)}</div><div class="card"><h4>Top partners</h4>${bars(d.top_partners)}</div></div>
        <div class="grid-2"><div class="card"><h4>Most active faculty</h4>${table([{ h: 'ID', html: r => profileLink('faculty', r.emp_id) }, { h: 'Name', k: 'name' }, { h: 'Submissions', k: 'submissions', num: 1 }], d.top_faculty)}</div>
          <div class="card"><h4>MoU status</h4>${table([{ h: 'Partner', k: 'partner' }, { h: 'Expiry', k: 'expiry' }, { h: 'Status', html: r => `<span class="pill ${r.status === 'Active' ? 'ok' : r.status === 'Expired' ? 'bad' : 'warn'}">${r.status}</span>` }], d.mou_status)}</div></div>` : ''}`;
  };
  $('#view').innerHTML = `<div class="filters"><h2>Dashboard</h2><span class="spacer"></span>
    <select class="compact" id="d-ay">${ayOpts('', 'All years')}</select>
    ${me.all_access ? '<select class="compact" id="d-prog"><option value="">UG + PG</option><option>UG</option><option>PG</option></select>' : '<input type="hidden" id="d-prog" value="">'}
    ${classFilter('d-cls', 'All Classes')}</div><div id="dash-out"></div>`;
  for (const [id, k] of [['d-ay', 'ay'], ['d-prog', 'prog'], ['d-cls', 'cls']]) $('#' + id).onchange = go(async e => { st[k] = e.target.value; await draw(); });
  await draw();
}

// ---------------------------------------------------------------- students
async function viewStudents() {
  const st = { class_id: '', status: 'Active', q: '', offset: 0 };
  $('#view').innerHTML = `<div class="card-head"><h2>Students</h2><div>${isEditor() ? '<button class="btn primary" id="add-st">+ Add student</button>' : ''}</div></div>
    <div class="filters">${hasBothGroups() ? '<select class="compact" id="f-grp"><option value="">Both groups (G1 + G2)</option><option value="G1">G1 only</option><option value="G2">G2 only</option></select>' : ''}${classFilter('f-class', 'All Classes')}
      <select class="compact" id="f-status"><option>Active</option><option>Graduated</option><option>Removed</option><option value="">Any status</option></select>
      <input class="input compact" id="f-q" placeholder="Search roll no / name"></div>
    <div class="card" id="st-list"></div>
    ${isEditor() ? uploadCard({ title: 'Upload students from Excel', hint: 'One row per student: Roll No and Full Name (only these are kept; academic details stay in the college main database). The students go into the class chosen below; a tutor\'s own class is used automatically. Existing roll numbers are updated.',
      template: ['/api/master/students/template', 'students_template.xlsx'], path: '/api/master/students/upload',
      extra: (() => { const mine = meta.classes.filter(c => c.can_edit); return `<select class="compact" id="up-class">${classOpts(mine.length === 1 ? mine[0].class_id : '', mine.length === 1 ? undefined : 'Choose the class for this sheet', true)}</select>`; })(),
      fields: (el, f) => { const v = $('#up-class', el).value; if (v) f.append('class_id', v); }, done: () => draw() }) : ''}`;
  const draw = async () => {
    const qs = new URLSearchParams({ limit: 100, offset: st.offset, status: st.status });
    for (const [k, id] of [['class_id', 'f-class'], ['grp', 'f-grp'], ['q', 'f-q']]) { const el = $('#' + id); if (el && el.value) qs.set(k, el.value); }
    const r = await api('/api/master/students?' + qs);
    const rows = r.rows;
    $('#st-list').innerHTML = `<p class="hint">${r.total} students${r.total > 100 ? ' (showing the first 100 - narrow the filters)' : ''}</p>` + table([
      { h: 'Roll no', html: s => `<a href="#" data-roll="${esc(s.roll_no)}">${esc(s.roll_no)}</a>` }, { h: 'Name', k: 'full_name' }, { h: 'Class', k: 'class_code' },
      { h: 'Sem', k: 'current_semester' }, { h: 'Status', k: 'status' },
      { h: '', html: s => isEditor() && s.status === 'Active' ? `<button class="btn sm" data-tr="${esc(s.roll_no)}">Move</button> <button class="btn sm danger" data-rm="${esc(s.roll_no)}">Remove</button>` : '' }], rows);
    $('#st-list').onclick = go(async e => {
      const t = e.target;
      if (t.dataset.roll) { e.preventDefault(); return openProfile('student', t.dataset.roll); }
      if (t.dataset.rm && confirm(`Remove ${t.dataset.rm} from the class? Their records are kept.`)) { await api(`/api/master/students/${t.dataset.rm}/remove`, { method: 'POST' }); toast('Removed'); await draw(); }
      if (t.dataset.tr) modal('Move ' + t.dataset.tr, `<div class="field"><label>New class</label><select id="mv-class">${classOpts('', undefined)}</select></div>`, async o => {
        await api(`/api/master/students/${t.dataset.tr}/transfer`, { method: 'POST', body: { class_id: $('#mv-class', o).value } }); toast('Moved'); await draw();
      }, 'Move');
    });
  };
  for (const id of ['f-class', 'f-status']) $('#' + id).onchange = go(draw);
  const grp = $('#f-grp');
  if (grp) grp.onchange = go(async () => {          // narrow the class drop-down to the chosen group, then reload the list
    const cls = $('#f-class');
    if (cls && cls.tagName === 'SELECT') cls.innerHTML = opts(meta.classes.filter(c => !grp.value || c.grp === grp.value), c => c.class_id, classLabel, '', 'All classes');
    await draw();
  });
  $('#f-q').oninput = go(draw);
  $('#f-status').value = 'Active';
  const add = $('#add-st');
  if (add) add.onclick = () => modal('Add student', `
    <div class="field"><label>Class</label><select id="a-class">${classOpts('', undefined, true)}</select></div>
    <div class="grid-2"><div class="field"><label>Roll no *</label><input class="input" id="a-roll"></div><div class="field"><label>Full name *</label><input class="input" id="a-name"></div></div>
    <p class="hint">Only the roll number and name are kept here. Marks, attendance and other academic details stay in the college main database.</p>`,
    async o => {
      await api('/api/master/students', { method: 'POST', body: { class_id: $('#a-class', o).value, roll_no: $('#a-roll', o).value, full_name: $('#a-name', o).value } });
      toast('Student added'); await draw();
    }, 'Add');
  await draw();
}
// ---------------------------------------------------------------- classes
async function viewClasses() {
  const classes = await api('/api/master/classes'); meta.classes = classes;
  const admin = me.roles.includes('ADMIN');
  $('#view').innerHTML = `<div class="card-head"><h2>Classes</h2>${admin ? '<button class="btn primary" id="add-class">+ Add class</button>' : ''}</div>
    <p class="hint">A class is known by its tutor and its semester. Two semesters make a year (UG has 8 semesters, PG has 4), so the year and the class code follow the semester the tutor sets: nobody is promoted, the students simply stay in their class as it moves up. Two classes can be in the same year at once. Only the Admin changes a class's tutor or adds a class.</p>` +
    (classes.map(c => `<div class="card" data-c="${c.class_id}"><div class="card-head"><div><h3>${esc(c.class_code)} · ${esc(c.ay_id)}</h3>
      <span class="muted">${c.student_count} active students</span></div>
      <div class="filters" style="margin:0">
        ${admin ? `<select class="compact tutor">${opts(meta.faculty, f => f.emp_id, f => f.emp_id + ' - ' + f.full_name, c.tutor_id, '(no tutor)')}</select><button class="btn sm save-tutor">Set tutor</button>` : ''}
      </div></div>
      ${c.can_edit ? `<div class="filters"><label>Semester</label><select class="compact sem">${Array.from({ length: c.max_semester }, (_, i) => i + 1).map(n => `<option ${n === c.current_semester ? 'selected' : ''}>${n}</option>`).join('')}</select>
        <label>Academic year</label><select class="compact ay">${ayOpts(c.ay_id)}</select><button class="btn sm save-term">Save</button><span class="spacer"></span>
        ${c.current_semester === c.max_semester ? '<button class="btn sm danger graduate">Mark class as graduated</button>' : ''}</div>` : ''}</div>`).join('') || '<div class="empty">No classes yet.</div>');
  const add = $('#add-class');
  if (add) add.onclick = () => modal('Add class', `
    <div class="grid-2"><div class="field"><label>Programme</label><select id="ac-prog"><option>UG</option><option>PG</option></select></div>
    <div class="field"><label>Group (UG)</label><select id="ac-grp"><option>G1</option><option>G2</option></select></div>
    <div class="field"><label>Current semester</label><input class="input" id="ac-sem" type="number" min="1" max="8" value="1"></div>
    <div class="field"><label>Tutor</label><select id="ac-tutor">${opts(meta.faculty, f => f.emp_id, f => f.emp_id + ' - ' + f.full_name, '', '(no tutor yet)')}</select></div></div>
    <p class="hint">UG classes have semesters 1-8, PG classes 1-4. The year and the class code are worked out from the semester.</p>`,
    async o => {
      await api('/api/master/classes', { method: 'POST', body: { programme: $('#ac-prog', o).value, grp: $('#ac-grp', o).value, semester: $('#ac-sem', o).value, tutor_id: $('#ac-tutor', o).value } });
      toast('Class added'); show('classes');
    }, 'Add');
  $('#view').onclick = go(async e => {
    const card = e.target.closest('[data-c]'); if (!card) return; const id = card.dataset.c, c = classes.find(x => x.class_id == id);
    if (e.target.classList.contains('save-term')) {
      const r = await api(`/api/master/classes/${id}/term`, { method: 'PUT', body: { semester: $('.sem', card).value, ay_id: $('.ay', card).value } });
      toast(`Saved: year ${r.year_no}, class code ${r.class_code}`); show('classes');
    }
    if (e.target.classList.contains('save-tutor')) { await api(`/api/master/classes/${id}/tutor`, { method: 'PUT', body: { emp_id: $('.tutor', card).value } }); toast('Tutor updated'); show('classes'); }
    if (e.target.classList.contains('graduate') && confirm(`Mark ${c.class_code} as graduated? Its ${c.student_count} active students become Graduated and the class closes (their records are kept).`)) {
      const r = await api(`/api/master/classes/${id}/graduate`, { method: 'POST' }); toast(`${r.graduated} students graduated`); show('classes');
    }
  });
}

// ---------------------------------------------------------------- uploads
async function viewUploads() {
  $('#view').innerHTML = `<div class="card-head"><h2>Data upload</h2></div>
    <p class="hint">Download each template, fill it (or export the Google Form responses sheet as .xlsx), then upload. Re-uploading the same file never creates duplicates.</p>
    ${uploadCard({ title: 'Placement data', hint: 'One row per offer. <b>A student who is already in the database is replaced</b> by the rows in this file (for that academic year).',
      template: ['/api/master/placements/template', 'placements_template.xlsx'], path: '/api/master/placements/upload',
      extra: `<select class="compact" id="pl-ay">${ayOpts(meta.current_ay, 'Academic year if the sheet has none')}</select>`,
      fields: (el, f) => { const v = $('#pl-ay', el).value; if (v) f.append('ay_id', v); } })}
    <h3 style="margin:18px 0 10px">Form responses</h3>` +
    meta.forms.map(f => uploadCard({ title: f.title.replace('IT Chronicles - ', ''), hint: 'Export the form\'s responses sheet as .xlsx. Roll numbers / employee IDs link each row to the right people.',
      template: [`/api/master/forms/${f.form_id}/template`, f.form_id + '_template.xlsx'], path: `/api/master/forms/${f.form_id}/upload` })).join('') +
    `<div class="card"><div class="card-head"><h3>Roll numbers that matched nobody</h3></div><div id="unmatched"></div></div>`;
  const u = await api('/api/master/submissions/unmatched');
  $('#unmatched').innerHTML = table([{ h: 'Submission', k: 'submission_id' }, { h: 'Entry as typed', k: 'raw_text' }, { h: 'Title', k: 'title' }], u);
}

// ---------------------------------------------------------------- placements
async function viewPlacements() {
  let mode = 'offers';
  $('#view').innerHTML = `<div class="card-head"><h2>Placements</h2><div class="filters" style="margin:0"><button class="btn sm" data-m="offers">Offers</button><button class="btn sm" data-m="profiles">Opt-in / opt-out</button></div></div>
    <div class="filters"><select class="compact" id="p-ay">${ayOpts('', 'All years')}</select>${classFilter('p-class', 'All Classes')}
      <span id="p-extra" class="filters" style="margin:0"></span></div><div class="card" id="p-out"></div>`;
  const draw = async () => {
    const qs = new URLSearchParams({ limit: 200 });
    for (const [k, id] of [['ay_id', 'p-ay'], ['class_id', 'p-class'], ['org_id', 'p-org'], ['offer_type', 'p-type'], ['opt_status', 'p-opt'], ['min_package', 'p-min'], ['max_package', 'p-max'], ['q', 'p-q']]) { const el = $('#' + id); if (el && el.value) qs.set(k, el.value); }
    if (mode === 'offers') {
      const r = await api('/api/master/placements/offers?' + qs);
      $('#p-out').innerHTML = `<p class="hint">${r.total} offers</p>` + table([{ h: 'Roll no', html: r => profileLink('student', r.roll_no) }, { h: 'Name', k: 'full_name' }, { h: 'Class', k: 'class_code' }, { h: 'Year', k: 'ay_id' }, { h: 'Company', k: 'company' }, { h: 'Type', k: 'offer_type' },
        { h: 'LPA', k: 'package_lpa', num: 1 }, { h: 'Stipend/mo', f: r => fmtMoney(r.stipend_per_month), num: 1 }, { h: 'Role', k: 'job_role' }, { h: 'Status', k: 'offer_status' }], r.rows);
    } else {
      const r = await api('/api/master/placements/profiles?' + qs);
      $('#p-out').innerHTML = `<p class="hint">${r.total} students</p>` + table([{ h: 'Roll no', k: 'roll_no' }, { h: 'Name', k: 'full_name' }, { h: 'Class', k: 'class_code' }, { h: 'Year', k: 'ay_id' },
        { h: 'Preference', html: p => `<span class="pill ${p.opt_status === 'OPTED_IN' ? 'ok' : 'warn'}">${p.opt_status === 'OPTED_IN' ? 'Opted in' : 'Opted out'}</span>` }, { h: 'Reason', k: 'opt_out_reason' }, { h: 'Offers', k: 'offers', num: 1 }, { h: 'Best LPA', k: 'best_package_lpa', num: 1 }], r.rows);
    }
  };
  const extras = () => {
    $('#p-extra').innerHTML = mode === 'offers'
      ? `<select class="compact" id="p-org">${opts(meta.organizations, o => o.org_id, o => o.name, '', 'All companies')}</select><select class="compact" id="p-type"><option value="">All types</option><option>FTE</option><option>INTERN</option><option>FTE+INTERN</option><option>INTERN_CONVERTED_FTE</option></select>
         <input class="input compact" id="p-min" type="number" placeholder="Min LPA" style="width:90px"><input class="input compact" id="p-max" type="number" placeholder="Max LPA" style="width:90px"><input class="input compact" id="p-q" placeholder="Search">`
      : `<select class="compact" id="p-opt"><option value="">Opted in + out</option><option value="OPTED_IN">Opted in</option><option value="OPTED_OUT">Opted out</option></select>`;
    $('#p-extra').querySelectorAll('select,input').forEach(el => el.onchange = el.oninput = go(draw));
  };
  $('#view').onclick = go(async e => { if (e.target.dataset.m) { mode = e.target.dataset.m; extras(); await draw(); } });
  for (const id of ['p-ay', 'p-class']) $('#' + id).onchange = go(draw);
  extras(); await draw();
}

// ---------------------------------------------------------------- submissions
async function viewSubs() {
  const catOpts = [...new Set(Object.values(meta.categories).flat())];
  $('#view').innerHTML = `<div class="card-head"><h2>${subsLabel()}</h2></div>
    <div class="filters"><select class="compact" id="s-type"><option value="">All forms</option><option value="STUDENT">Student</option><option value="RESEARCH">Research</option><option value="FACULTY">Faculty</option><option value="DEPARTMENT">Department</option><option value="OUTREACH">Outreach</option></select>
      <select class="compact" id="s-ay">${ayOpts('', 'All years')}</select><select class="compact" id="s-cat">${opts(catOpts, x => x, x => x, '', 'All categories')}</select>
      ${classFilter('s-class', 'All Classes')}
      <select class="compact" id="s-level"><option value="">Any level</option>${['Department', 'College', 'Inter-college', 'State', 'National', 'International'].map(l => `<option>${l}</option>`).join('')}</select>
      <input class="input compact" id="s-roll" placeholder="Roll no" style="width:110px"><input class="input compact" type="date" id="s-from"><input class="input compact" type="date" id="s-to">
      <input class="input compact" id="s-q" placeholder="Title contains"></div><div class="card" id="s-out"></div>`;
  let rows = [];
  const draw = async () => {
    const qs = new URLSearchParams({ limit: 200 });
    for (const [k, id] of [['form_type', 's-type'], ['ay_id', 's-ay'], ['category', 's-cat'], ['class_id', 's-class'], ['level', 's-level'], ['roll_no', 's-roll'], ['date_from', 's-from'], ['date_to', 's-to'], ['q', 's-q']]) if ($('#' + id).value) qs.set(k, $('#' + id).value);
    const r = await api('/api/master/submissions?' + qs); rows = r.rows;
    $('#s-out').innerHTML = `<p class="hint">${r.total} submissions</p>` + table([{ h: 'Date', k: 'event_date' }, { h: 'Form', k: 'form_type' }, { h: 'Category', k: 'category' }, { h: 'Title', k: 'title' }, { h: 'Submitted by', f: x => x.submitter || x.submitter_email || '' }], rows, { click: 1 });
    $('#s-out').onclick = go(async e => { const tr = e.target.closest('tr.click'); if (tr) submissionDetail(rows[tr.dataset.i].submission_id); });
  };
  document.querySelectorAll('#view .filters select, #view .filters input').forEach(el => el.onchange = el.oninput = go(draw));
  await draw();
}
async function submissionDetail(id) {
  const d = await api('/api/master/submissions/' + id);
  const kv = o => '<dl class="kv">' + Object.entries(o).filter(([, v]) => v !== null && v !== '').map(([k, v]) => `<dt>${esc(k.replace(/_/g, ' '))}</dt><dd>${esc(v)}</dd>`).join('') + '</dl>';
  modal(d.header.title, kv(d.header) + '<h4 style="margin-top:14px">Details</h4>' + kv(d.detail) +
    (d.participants.length ? '<h4 style="margin-top:14px">Students</h4>' + table([{ h: 'Roll no', f: p => p.roll_no || '⚠ ' + p.raw_text }, { h: 'Name', k: 'name' }, { h: 'Role', k: 'role' }, { h: 'Class then', k: 'class_code' }, { h: 'Lead', f: p => p.is_lead ? 'Yes' : '' }], d.participants) : '') +
    (d.contributors.length ? '<h4 style="margin-top:14px">Authors</h4>' + table([{ h: '#', k: 'author_order' }, { h: 'Type', k: 'person_type' }, { h: 'Name', k: 'name' }, { h: 'ID', f: c => c.emp_id || c.roll_no || '' }, { h: 'Affiliation', k: 'affiliation' }], d.contributors) : '') +
    (d.faculty.length ? '<h4 style="margin-top:14px">Faculty involved</h4>' + table([{ h: 'ID', k: 'emp_id' }, { h: 'Name', k: 'full_name' }, { h: 'Role', k: 'role' }], d.faculty) : '') +
    (d.event_students.length ? '<h4 style="margin-top:14px">Student participants</h4>' + table([{ h: 'Roll no', k: 'roll_no' }, { h: 'Name', k: 'full_name' }], d.event_students) : ''), null, '', true);
}

// ---------------------------------------------------------------- faculty (Admin)
async function viewFaculty() {
  const list = await api('/api/master/faculty');
  const admin = me.roles.includes('ADMIN');
  const rolesText = f => [...f.roles.map(r => r.role + (r.programme ? ' ' + r.programme + (r.grp ? '-' + r.grp : '') : '')), ...f.tutor_of.map(c => 'Tutor ' + c)].join(', ');
  const desigs = [...new Set(list.map(f => f.designation).filter(Boolean))].sort();
  const count = (f, k) => (f.counts || {})[k] || 0;
  const hasRole = (f, r) => r === 'TUTOR' ? f.tutor_of.length > 0 : f.roles.some(x => x.role === r);
  $('#view').innerHTML = `<div class="card-head"><h2>${admin ? 'Faculty & roles' : 'Faculty'}</h2>${admin ? '<div><button class="btn" id="copy-choices">Copy list for the Apps Script</button> <button class="btn primary" id="add-fac">+ Add faculty</button></div>' : ''}</div>
    <div class="filters">
      <input class="input compact" id="ff-q" placeholder="Search name, ID or email" style="min-width:220px">
      <select class="compact" id="ff-desig">${opts(desigs, d => d, d => d, '', 'Any designation')}</select>
      <select class="compact" id="ff-status"><option value="">Any status</option><option>Active</option><option>OnLeave</option><option>Relieved</option></select>
      <select class="compact" id="ff-role"><option value="">Any role</option><option value="ADMIN">Admin</option><option value="HOD">Head of Department</option><option value="PC">Programme Coordinator</option><option value="TUTOR">Class tutor</option><option value="NONE">No special role</option></select>
      <select class="compact" id="ff-has"><option value="">Any activity</option><option value="research">Has research / innovation</option><option value="achievements">Has professional achievements</option><option value="events">Has organised events</option><option value="outreach">Has industry / outreach</option><option value="mentored">Has mentored students</option><option value="none">Nothing entered yet</option></select>
      <button class="btn sm" id="ff-clear">Clear filters</button></div>
    <div class="card" id="fac-list"></div>
    ${!admin ? '' : uploadCard({ title: 'Upload faculty from Excel', hint: 'Existing employee IDs are updated; new ones get a temporary password (shown once below).',
      template: ['/api/master/faculty-template', 'faculty_template.xlsx'], path: '/api/master/faculty/upload', done: () => setTimeout(() => meta && go(async () => { meta = await api('/api/master/meta'); })(), 0) })}`;
  const drawFac = () => {
    const v = id => $('#' + id).value, q = v('ff-q').trim().toLowerCase();
    const rows = list.filter(f => (!q || [f.emp_id, f.full_name, f.email].some(x => (x || '').toLowerCase().includes(q))) && (!v('ff-desig') || f.designation === v('ff-desig')) &&
      (!v('ff-status') || f.status === v('ff-status')) &&
      (!v('ff-role') || (v('ff-role') === 'NONE' ? !f.roles.length && !f.tutor_of.length : hasRole(f, v('ff-role')))) &&
      (!v('ff-has') || (v('ff-has') === 'none' ? !['research', 'achievements', 'events', 'outreach', 'mentored'].some(k => count(f, k)) : count(f, v('ff-has')) > 0)));
    $('#fac-list').innerHTML = `<p class="hint">Showing ${rows.length} of ${list.length} faculty</p>` + table([
      { h: 'ID', k: 'emp_id' }, { h: 'Name', html: f => profileLink('faculty', f.emp_id, f.full_name) }, { h: 'Designation', k: 'designation' }, { h: 'Roles', f: rolesText },
      { h: 'Research', f: f => count(f, 'research'), num: 1 }, { h: 'Achievements', f: f => count(f, 'achievements'), num: 1 }, { h: 'Events', f: f => count(f, 'events'), num: 1 },
      { h: 'Outreach', f: f => count(f, 'outreach'), num: 1 }, { h: 'Mentored', f: f => count(f, 'mentored'), num: 1 }, { h: 'Status', k: 'status' },
      { h: '', html: f => `<button class="btn sm" data-profile="faculty:${esc(f.emp_id)}">Activities</button>` + (!admin ? '' : ` <button class="btn sm" data-roles="${esc(f.emp_id)}">Roles</button> <button class="btn sm" data-edit="${esc(f.emp_id)}">Edit</button> <button class="btn sm" data-pw="${esc(f.emp_id)}">Reset password</button> ${f.status !== 'Relieved' ? `<button class="btn sm danger" data-rel="${esc(f.emp_id)}">Relieve</button>` : ''}`) }], rows);
  };
  for (const id of ['ff-desig', 'ff-status', 'ff-role', 'ff-has']) $('#' + id).onchange = drawFac;
  $('#ff-q').oninput = drawFac;
  $('#ff-clear').onclick = () => { for (const id of ['ff-q', 'ff-desig', 'ff-status', 'ff-role', 'ff-has']) $('#' + id).value = ''; drawFac(); };
  drawFac();
  if (admin) $('#copy-choices').onclick = go(async () => { await navigator.clipboard.writeText(await api('/api/master/faculty-form-choices')); toast('Copied - paste it over FACULTY_CHOICES in the Apps Script'); });
  const facForm = (f = {}) => `<div class="grid-2">${[['emp_id', 'Employee ID'], ['full_name', 'Full name'], ['email', 'Email'], ['phone', 'Phone'], ['designation', 'Designation'], ['qualification', 'Qualification']]
    .map(([k, l]) => `<div class="field"><label>${l}</label><input class="input" data-k="${k}" value="${esc(f[k] || '')}" ${k === 'emp_id' && f.emp_id ? 'disabled' : ''}></div>`).join('')}</div>`;
  const collect = o => Object.fromEntries([...o.querySelectorAll('[data-k]')].map(i => [i.dataset.k, i.value]));
  if (admin) $('#add-fac').onclick = () => modal('Add faculty', facForm(), async o => {
    const r = await api('/api/master/faculty', { method: 'POST', body: collect(o) });
    alert(`Login created.\nID: ${r.emp_id}\nTemporary password: ${r.temp_password}\n\nShare it privately; they must change it at first sign-in.`); show('faculty');
  }, 'Add');
  $('#view').onclick = go(async e => {
    const t = e.target, f = list.find(x => x.emp_id === (t.dataset.roles || t.dataset.edit || t.dataset.pw || t.dataset.rel));
    if (t.dataset.edit) modal('Edit ' + f.full_name, facForm(f), async o => { await api('/api/master/faculty/' + f.emp_id, { method: 'PUT', body: collect(o) }); toast('Saved'); show('faculty'); });
    if (t.dataset.pw && confirm('Reset the password for ' + f.full_name + '?')) { const r = await api(`/api/master/faculty/${f.emp_id}/reset-password`, { method: 'POST' }); alert('Temporary password: ' + r.temp_password); }
    if (t.dataset.rel && confirm('Relieve ' + f.full_name + '? Their records stay; they can no longer sign in.')) { await api('/api/master/faculty/' + f.emp_id, { method: 'PUT', body: { status: 'Relieved' } }); toast('Relieved'); show('faculty'); }
    if (t.dataset.roles) {
      const has = (role, p, g) => f.roles.some(r => r.role === role && (r.programme || '') === (p || '') && (r.grp || '') === (g || ''));
      modal('Roles for ' + f.full_name, `<p class="hint">Tutor is set on the Classes page.</p>${[['ADMIN', '', ''], ['HOD', '', ''], ['PC', 'UG', 'G1'], ['PC', 'UG', 'G2'], ['PC', 'PG', '']]
        .map(([r, p, g]) => `<label style="display:block;margin:6px 0"><input type="checkbox" data-r="${r}" data-p="${p}" data-g="${g}" ${has(r, p, g) ? 'checked' : ''}> ${r === 'PC' ? 'Programme Coordinator – ' + p + (g ? ' ' + g : '') : r === 'HOD' ? 'Head of Department' : 'Admin'}</label>`).join('')}`,
        async o => { await api(`/api/master/faculty/${f.emp_id}/roles`, { method: 'PUT', body: { roles: [...o.querySelectorAll('input:checked')].map(i => ({ role: i.dataset.r, programme: i.dataset.p, grp: i.dataset.g })) } }); toast('Roles saved'); show('faculty'); });
    }
  });
}

// ---------------------------------------------------------------- Reports: one kind of work, within the signed-in person's scope
async function viewWorks() {
  const sel = { group: '', category: '' };            // what is being looked at
  const fv = { ay_id: '', date_from: '', date_to: '', q: '', has_media: false, class_id: '' };   // filters on the work
  let tv = {}, cat = null, items = [], total = 0, labels = {};
  const loadCatalog = async () => {
    cat = await api('/api/master/works/catalog' + (fv.ay_id ? '?ay_id=' + encodeURIComponent(fv.ay_id) : ''));
    labels = Object.fromEntries(cat.groups.flatMap(g => g.types.map(t => [t.category, t.label])));
    if (!sel.group) { const first = cat.groups.find(g => g.count) || cat.groups[0]; sel.group = first.id; }
  };
  const group = () => cat.groups.find(g => g.id === sel.group);
  // One drop-down per group of work, in a bar under the main navigation. The group in use is highlighted; the others show their name.
  const drawBar = () => {
    $('#wk-bar').innerHTML = cat.groups.map(g => `<select class="wk-sel ${sel.group === g.id ? 'on' : ''}" data-g="${g.id}" title="${esc(g.title)}">
        <option value="" ${sel.group === g.id ? 'hidden' : ''}>${esc(g.title)} (${g.count})</option>
        <option value="${g.id}|" ${sel.group === g.id && !sel.category ? 'selected' : ''}>All ${esc(g.title.toLowerCase())} (${g.count})</option>
        ${g.types.map(t => `<option value="${g.id}|${esc(t.category)}" ${sel.group === g.id && sel.category === t.category ? 'selected' : ''}>${esc(t.label)} (${t.count})</option>`).join('')}</select>`).join('') +
      '';
    $('#wk-hint').textContent = `${cat.total} entr${cat.total === 1 ? 'y' : 'ies'} in the department${fv.ay_id ? ' in ' + fv.ay_id : ''}. Every filter describes the work itself, not a person.`;
  };
  const drawFilters = () => {
    const g = group();
    $('#wk-filters').innerHTML = `<select class="compact" id="w-ay">${ayOpts(fv.ay_id, 'All academic years')}</select>
      <label class="muted">from <input class="input compact" type="date" id="w-from" value="${esc(fv.date_from)}"></label><label class="muted">to <input class="input compact" type="date" id="w-to" value="${esc(fv.date_to)}"></label>
      <input class="input compact" id="w-q" placeholder="${{ RESEARCH: 'Title or venue / publisher', FACULTY: 'Title or awarding body', DEPARTMENT: 'Title or partner', OUTREACH: 'Title or partner organisation', STUDENT: 'Title or organiser' }[g.id]}" value="${esc(fv.q)}" style="min-width:200px">
      ${g.filters.map(f => f.type === 'select'
        ? `<select class="compact wf" data-p="${f.param}"><option value="">Any ${esc(f.label.toLowerCase())}</option>${f.options.map(o => `<option value="${esc(o.value)}" ${tv[f.param] === o.value ? 'selected' : ''}>${esc(o.label)}</option>`).join('')}</select>`
        : `<input class="input compact wf" type="number" min="0" data-p="${f.param}" placeholder="${esc(f.label)}" value="${esc(tv[f.param] || '')}" style="width:${Math.max(120, f.label.length * 7.5)}px">`).join('')}
      ${g.id === 'STUDENT' ? `<select class="compact" id="w-class"><option value="">Any class</option>${meta.classes.map(c => `<option value="${c.class_id}" ${String(fv.class_id) === String(c.class_id) ? 'selected' : ''}>${esc(classLabel(c))}</option>`).join('')}</select>` : ''}
      <label><input type="checkbox" id="w-media" ${fv.has_media ? 'checked' : ''}> Has photo</label>
      <button class="btn sm" id="w-clear">Clear filters</button>`;
    let timer;
    const reload = () => go(load)(true);
    $('#w-ay').onchange = go(async e => { fv.ay_id = e.target.value; await loadCatalog(); drawBar(); await load(true); });
    $('#w-from').onchange = e => { fv.date_from = e.target.value; reload(); };
    $('#w-to').onchange = e => { fv.date_to = e.target.value; reload(); };
    $('#w-q').oninput = e => { fv.q = e.target.value; clearTimeout(timer); timer = setTimeout(reload, 300); };
    document.querySelectorAll('.wf').forEach(el => el.onchange = el.oninput = e => { tv[el.dataset.p] = e.target.value; clearTimeout(timer); timer = setTimeout(reload, 300); });
    const cls = $('#w-class'); if (cls) cls.onchange = e => { fv.class_id = e.target.value; reload(); };
    $('#w-media').onchange = e => { fv.has_media = e.target.checked; reload(); };
    $('#w-clear').onclick = go(async () => { Object.assign(fv, { ay_id: '', date_from: '', date_to: '', q: '', has_media: false, class_id: '' }); tv = {}; await loadCatalog(); drawBar(); drawFilters(); await load(true); });
  };
  const query = (limit, offset) => {
    const qs = new URLSearchParams({ group: sel.group, category: sel.category, limit, offset });
    for (const [k, v] of Object.entries({ ...fv, ...tv })) if (v) qs.set(k, v === true ? 'true' : v);
    return qs;
  };
  const load = async (reset) => {
    const r = await api('/api/master/works?' + query(50, reset ? 0 : items.length));
    items = reset ? r.items : items.concat(r.items); total = r.total;
    $('#wk-title').innerHTML = `${esc(r.title)} <span class="pill">${r.total}</span>`;
    $('#wk-stats').innerHTML = r.stats.map(x => kpi(typeof x.value === 'number' && /₹/.test(x.label) ? fmtMoney(x.value) : x.value, x.label)).join('');
    const shown = items.map(i => ({ ...i, badges: sel.category ? i.badges : [{ text: labels[i.category] || i.category }, ...i.badges] }));
    $('#wk-results').innerHTML = items.length
      ? `<div class="acts">${shown.map(actCard).join('')}</div>${items.length < total ? `<div style="text-align:center;margin:16px"><button class="btn" id="w-more">Show more (${total - items.length} left)</button></div>` : ''}`
      : '<div class="card"><div class="empty">Nothing matches these filters.</div></div>';
    const more = $('#w-more'); if (more) more.onclick = go(() => load(false));
  };
  $('#view').innerHTML = `<div class="wk-bar" id="wk-bar"></div>
    <div class="card"><div class="card-head"><div><h3 id="wk-title"></h3><p class="hint" id="wk-hint" style="margin:2px 0 0"></p></div>
      <div><button class="btn sm" id="w-open">Expand all</button> <button class="btn sm" id="w-csv">Download CSV</button></div></div>
      <div class="filters" id="wk-filters"></div><div class="kpis" id="wk-stats" style="margin:0"></div></div><div id="wk-results"></div>`;
  await loadCatalog(); drawBar(); drawFilters(); await load(true);
  $('#wk-bar').onchange = go(async e => {
    const el = e.target.closest('select[data-g]'); if (!el || !el.value) return;
    const [g, c] = el.value.split('|');
    if (g !== sel.group) tv = {};                          // the work-specific filters belong to one form
    sel.group = g; sel.category = c; if (g !== 'STUDENT') fv.class_id = '';
    drawBar(); drawFilters(); await load(true);
  });
  let open = false;
  $('#w-open').onclick = () => { open = !open; document.querySelectorAll('#wk-results details.act').forEach(d => d.open = open); $('#w-open').textContent = open ? 'Collapse all' : 'Expand all'; };
  // Download CSV: a pop-up where the user sets the dates first, then ticks the columns wanted (Select all ticks / clears every box).
  $('#w-csv').onclick = () => {
    const g = group(), kind = sel.category ? labels[sel.category] : g.title;
    const valid = new Set(g.columns.map(c => c.key)), storeKey = 'wk-columns-' + g.id;
    let saved = null; try { saved = JSON.parse(localStorage.getItem(storeKey) || 'null'); } catch (e) { }       // remember the last choice for this kind of work
    const chosen = new Set((Array.isArray(saved) ? saved : g.default_columns).filter(k => valid.has(k)));
    const present = new Set(g.columns.map(c => c.part)), parts = ['Basics', 'People', 'Details', 'Numbers', 'Submission', 'Links'].filter(x => present.has(x));
    const o = modal('Download CSV · ' + kind, `
      <h4>Dates</h4>
      <div class="filters" style="margin-bottom:4px"><select class="compact" id="dl-ay">${ayOpts(fv.ay_id, 'All academic years')}</select>
        <label class="muted">from <input class="input compact" type="date" id="dl-from" value="${esc(fv.date_from)}"></label><label class="muted">to <input class="input compact" type="date" id="dl-to" value="${esc(fv.date_to)}"></label>
        <span class="muted" id="dl-rows"></span></div>
      <p class="hint" style="margin-top:0">The filters set on the page (status, level, search …) also apply. Leave the dates empty for everything.</p>
      <h4 style="margin-top:14px">Columns</h4>
      <label class="dl-all"><input type="checkbox" id="dl-all"> <b>Select all columns</b> <span class="muted" id="dl-n"></span></label>
      <div class="dl-cols">${parts.map(part => `<div class="dl-part"><h5>${esc(part)}</h5><div class="dl-grid">${g.columns.filter(c => c.part === part).map(c =>
        `<label><input type="checkbox" class="dl-c" value="${esc(c.key)}" ${chosen.has(c.key) ? 'checked' : ''}> ${esc(c.label)}</label>`).join('')}</div></div>`).join('')}</div>`,
      async dlg => {
        const cols = [...dlg.querySelectorAll('.dl-c:checked')].map(i => i.value);
        if (!cols.length) { toast('Tick at least one column', true); return false; }
        try { localStorage.setItem(storeKey, JSON.stringify(cols)); } catch (e) { }
        const qs = exportQuery(dlg, 2000, 0); qs.delete('limit'); qs.delete('offset'); qs.set('columns', cols.join(','));
        await download('/api/master/works/export?' + qs, `work_${sel.group.toLowerCase()}${sel.category ? '_' + sel.category.replace(/\W+/g, '_').toLowerCase() : ''}_${new Date().toISOString().slice(0, 10)}.csv`);
      }, 'Download CSV', true);
    const boxes = () => [...o.querySelectorAll('.dl-c')], all = $('#dl-all', o), save = $('.save', o);
    const sync = () => {
      const n = boxes().filter(b => b.checked).length;
      all.checked = n === boxes().length; all.indeterminate = n > 0 && n < boxes().length;
      $('#dl-n', o).textContent = `${n} of ${boxes().length} selected`; save.disabled = n === 0;
    };
    all.onchange = () => { boxes().forEach(b => b.checked = all.checked); sync(); };
    boxes().forEach(b => b.onchange = sync); sync();
    // how many rows the chosen dates give, so nobody downloads an empty file by surprise
    let timer;
    const count = () => go(async () => { const r = await api('/api/master/works?' + exportQuery(o, 1, 0)); $('#dl-rows', o).textContent = `${r.total} row${r.total === 1 ? '' : 's'} will be downloaded`; })();
    const later = () => { clearTimeout(timer); timer = setTimeout(count, 250); };
    for (const id of ['dl-ay', 'dl-from', 'dl-to']) $('#' + id, o).onchange = later;
    count();
  };
  // the page's filters, with the pop-up's three date fields taking over from the page's own
  const exportQuery = (dlg, limit, offset) => {
    const qs = query(limit, offset);
    for (const k of ['ay_id', 'date_from', 'date_to']) qs.delete(k);
    for (const [k, id] of [['ay_id', 'dl-ay'], ['date_from', 'dl-from'], ['date_to', 'dl-to']]) { const v = $('#' + id, dlg).value; if (v) qs.set(k, v); }
    return qs;
  };
}

// ---------------------------------------------------------------- account
async function viewAccount() {
  $('#view').innerHTML = `<div class="card" style="max-width:420px"><h3>Change password</h3><div class="field" style="margin-top:12px"><label>Current password</label><input type="password" class="input" id="pw-old"></div>
    <div class="field"><label>New password (min 8 characters)</label><input type="password" class="input" id="pw-new"></div><button class="btn primary" id="pw-go">Change password</button></div>`;
  $('#pw-go').onclick = go(async () => {
    await api('/api/auth/change-password', { method: 'POST', body: { old_password: $('#pw-old').value, new_password: $('#pw-new').value } });
    me.must_change = false; $('#banner').innerHTML = ''; toast('Password changed'); $('#pw-old').value = $('#pw-new').value = '';
  });
}

// ---------------------------------------------------------------- person pages (faculty / student)
let profileBack = null;
const initials = n => (n || '?').replace(/^(Dr|Prof|Mr|Mrs|Ms)\.?\s+/i, '').split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase();
function actCard(i) {
  const facts = i.facts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
  const notes = i.notes.map(([k, v]) => `<h5>${esc(k)}</h5><p>${esc(v)}</p>`).join('');
  const links = i.links.map(l => `<a class="chip-link" href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.label)} ↗</a>`).join('');
  return `<details class="act"><summary><div class="act-top"><span class="act-title">${esc(i.title)}</span><span class="act-date">${esc(i.date || i.ay_id || '')}</span></div>
    <div class="act-badges">${i.role ? `<span class="pill role">${esc(i.role)}</span>` : ''}${i.badges.map(b => `<span class="pill ${b.tone || ''}">${esc(b.text)}</span>`).join('')}</div></summary>
    <div class="act-body">${facts ? `<dl class="facts">${facts}</dl>` : ''}${notes}${links ? `<div class="links">${links}</div>` : ''}${!facts && !notes && !links ? '<p class="muted">No more details were entered.</p>' : ''}</div></details>`;
}
async function openProfile(kind, id, opt = {}) {
  const ay = opt.ay || '', q = opt.q || '';
  if (!opt.keepBack && current !== 'profile') profileBack = opt.mine ? null : current;
  const p = await api(`/api/master/${kind === 'faculty' ? 'faculty' : 'students'}/${encodeURIComponent(id)}/profile${ay ? '?ay_id=' + encodeURIComponent(ay) : ''}`);
  current = 'profile';
  history.replaceState(null, '', `#/${kind}/${encodeURIComponent(id)}`);
  const h = p.person;
  $('#view').onclick = null;
  $('#view').innerHTML = `
    <div class="card"><div class="p-head"><div class="avatar">${esc(initials(h.name))}</div>
      <div class="who-block"><h2>${esc(h.name)}</h2><div class="p-sub">${esc(h.id)} · ${esc(h.subtitle)}${h.status && h.status !== 'Active' ? ` <span class="pill warn">${esc(h.status)}</span>` : ''}</div>
        ${h.tags.length ? `<div class="tags">${h.tags.map(t => `<span class="pill">${esc(t)}</span>`).join('')}</div>` : ''}
        ${h.contact && h.contact.length ? `<div class="journey">${esc(h.contact.join(' · '))}</div>` : ''}
        ${h.journey && h.journey.length ? `<div class="journey">Class journey: ${h.journey.map(j => `<span>${esc(j)}</span>`).join('')}</div>` : ''}</div>
      <div class="p-tools">${profileBack ? '<button class="btn sm" id="p-back">← Back</button>' : ''}
        <select class="compact" id="p-ay"><option value="">All academic years</option>${p.academic_years.map(y => `<option ${y === p.ay_id ? 'selected' : ''}>${esc(y)}</option>`).join('')}</select>
        <input class="input compact" id="p-find" placeholder="Search this page" value="${esc(q)}" style="width:160px">
        <button class="btn sm" id="p-open">Expand all</button><button class="btn sm" id="p-print">Print</button><button class="btn sm" id="p-dl" title="Download everything on this page as a spreadsheet-ready CSV file">⬇ Download</button></div></div></div>
    <div class="kpis">${p.summary.map(s => kpi(s.value, s.label)).join('')}</div>
    ${p.total ? `<div class="snav">${p.sections.map(s => `<a data-jump="sec-${s.id}">${esc(s.title)}<b>${s.count}</b></a>`).join('')}</div>` + p.sections.map(s => `
      <section class="card sec" id="sec-${s.id}"><div class="card-head"><h3>${esc(s.title)} <span class="pill">${s.count}</span></h3></div>${s.note ? `<p class="sec-note">${esc(s.note)}</p>` : ''}
        ${s.groups.map(g => `<div class="grp"><div class="grp-head">${esc(g.title)} <span class="pill">${g.count}</span></div><div class="acts">${g.items.map(actCard).join('')}</div></div>`).join('')}</section>`).join('')
      : `<div class="card"><div class="empty">${ay ? 'Nothing recorded for ' + esc(ay) + '.' : 'No activities have been recorded yet.'} Entries appear here once the person's form responses are uploaded.</div></div>`}`;
  const back = $('#p-back'); if (back) back.onclick = () => { const t = profileBack; profileBack = null; show(t || 'dash'); };
  $('#p-ay').onchange = go(e => openProfile(kind, id, { ay: e.target.value, q: $('#p-find').value, keepBack: true }));
  const filt = () => {
    const t = $('#p-find').value.trim().toLowerCase();
    document.querySelectorAll('details.act').forEach(d => d.classList.toggle('hidden', !!t && !d.textContent.toLowerCase().includes(t)));
    document.querySelectorAll('.grp').forEach(g => g.classList.toggle('hidden', !g.querySelector('details.act:not(.hidden)')));
    document.querySelectorAll('.sec').forEach(sec => sec.classList.toggle('hidden', !sec.querySelector('details.act:not(.hidden)')));
  };
  $('#p-find').oninput = filt; filt();
  let open = false;
  $('#p-open').onclick = () => { open = !open; document.querySelectorAll('details.act').forEach(d => d.open = open); $('#p-open').textContent = open ? 'Collapse all' : 'Expand all'; };
  $('#p-print').onclick = () => { document.querySelectorAll('details.act').forEach(d => d.open = true); window.print(); };
  $('#p-dl').onclick = () => {                                   // everything on the page (for the chosen academic year) as CSV
    const cell = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
    const rows = [['Person', 'ID', 'Section', 'Group', 'Title', 'Date', 'Role', 'Tags', 'Details', 'Notes', 'Links']];
    p.sections.forEach(sec => sec.groups.forEach(g => g.items.forEach(i => rows.push([h.name, h.id, sec.title, g.title, i.title, i.date || i.ay_id || '', i.role || '',
      i.badges.map(b => b.text).join('; '), i.facts.map(([k, v]) => k + ': ' + v).join(' | '), i.notes.map(([k, v]) => k + ': ' + v).join(' | '), i.links.map(l => l.url).join(' ')]))));
    if (rows.length === 1) return toast('There is nothing to download yet', true);
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['\ufeff' + rows.map(r => r.map(cell).join(',')).join('\r\n')], { type: 'text/csv' }));
    a.download = `${h.id}_${h.name.replace(/[^A-Za-z0-9]+/g, '_')}${p.ay_id ? '_' + p.ay_id : ''}.csv`; a.click();
  };
  const nav = $('.snav'); if (nav) nav.onclick = e => { const a = e.target.closest('[data-jump]'); if (a) document.getElementById(a.dataset.jump).scrollIntoView({ behavior: 'smooth' }); };
  window.scrollTo(0, 0);
}
// any element carrying data-profile="faculty:EMP001" or "student:21IT001" opens that person's page
document.addEventListener('click', e => {
  const a = e.target.closest('[data-profile]'); if (!a) return;
  e.preventDefault(); const [k, id] = a.dataset.profile.split(':'); go(openProfile)(k, id);
});
const profileLink = (kind, id, label) => `<a href="#" data-profile="${kind}:${esc(id)}">${esc(label ?? id)}</a>`;

const VIEWS = { dash: viewDash, students: viewStudents, classes: viewClasses, uploads: viewUploads, placements: viewPlacements, subs: viewSubs, faculty: viewFaculty, works: viewWorks, mine: () => openProfile('faculty', me.id, { mine: true }), account: viewAccount };
start();
