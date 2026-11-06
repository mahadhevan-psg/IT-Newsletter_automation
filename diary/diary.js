/* IT Department Placements Diary - student view. Everything shown is company-level or anonymous; the API carries no names, roll numbers or photos. */
const $ = (s, r = document) => r.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let token = sessionStorage.getItem('dtok'), me = null;

function toast(msg, bad) { const t = document.createElement('div'); t.className = 'toast' + (bad ? ' bad' : ''); t.textContent = msg; document.body.appendChild(t); setTimeout(() => t.remove(), 4000); }
async function api(path, o = {}) {
  const init = { method: o.method || 'GET', headers: token ? { Authorization: 'Bearer ' + token } : {} };
  if (o.body !== undefined) { init.body = JSON.stringify(o.body); init.headers['Content-Type'] = 'application/json'; }
  const r = await fetch(path, init);
  if (r.status === 401 && token) { logout(); throw new Error('Please sign in again'); }
  if (!r.ok) { let d = r.statusText; try { d = (await r.json()).detail; } catch (e) { } throw new Error(d); }
  return r.json();
}
const go = fn => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, true); } };
const lpa = n => n == null ? '–' : n + ' LPA';
const stars = n => n ? '★'.repeat(n) + '☆'.repeat(5 - n) : '';

async function start() {
  $('#logout').onclick = logout; $('#chpw').onclick = changePassword;
  window.onhashchange = go(route);
  if (token) { try { await boot(); return; } catch (e) { sessionStorage.removeItem('dtok'); } }
  location.replace('/');            // not signed in: / is the sign-in page
}
function logout() { sessionStorage.removeItem('dtok'); location.replace('/'); }
async function boot() {
  me = await api('/api/auth/me');
  $('#app').classList.remove('hidden');
  $('#banner').innerHTML = me.must_change ? '<div class="banner">Please change your password (top right) - you are still using your roll number.</div>' : '';
  await route();
  Tours.diary(me, token);                     // Help button; the welcome tour the first time this student opens the diary
}
function changePassword() {
  const o = document.createElement('div'); o.className = 'overlay';
  o.innerHTML = `<div class="dialog"><div class="dialog-head"><h3>Change password</h3><button class="x">×</button></div><div class="dialog-body">
    <div class="field"><label>Current password</label><input type="password" class="input" id="o"></div>
    <div class="field"><label>New password (min 8 characters)</label><input type="password" class="input" id="n"></div></div>
    <div class="dialog-foot"><button class="btn" id="c">Cancel</button><button class="btn primary" id="s">Change</button></div></div>`;
  document.body.appendChild(o); $('.x', o).onclick = $('#c', o).onclick = () => o.remove();
  $('#s', o).onclick = go(async () => { await api('/api/auth/change-password', { method: 'POST', body: { old_password: $('#o', o).value, new_password: $('#n', o).value } }); me.must_change = false; $('#banner').innerHTML = ''; o.remove(); toast('Password changed'); });
}

async function route() {
  const m = location.hash.match(/^#\/company\/(\d+)/);
  return m ? company(+m[1]) : home();
}

async function home() {
  const [ov, list] = await Promise.all([api('/api/diary/overview'), api('/api/diary/companies')]);
  const draw = (cs) => $('#co-list').innerHTML = cs.length ? cs.map(c => `
    <div class="card co" data-id="${c.org_id}"><h3>${esc(c.name)}</h3><span class="muted">${esc(c.sector || '')}</span>
      <div class="stat-row"><div><b>${c.placed}</b><span>placed (full-time)</span></div><div><b>${c.interns}</b><span>interns</span></div><div><b>${lpa(c.max_lpa)}</b><span>highest</span></div><div><b>${lpa(c.avg_lpa)}</b><span>average</span></div></div>
      <p class="hint" style="margin:10px 0 0">${c.interview_experiences} interview · ${c.internship_experiences} internship experiences</p></div>`).join('') : '<div class="empty">No company matches.</div>';
  $('#view').innerHTML = `<div class="kpis"><div class="kpi"><b>${ov.placed}</b><span>students placed (${esc(ov.years.slice().reverse().join(', ') || 'no data yet')})</span></div>
      <div class="kpi"><b>${ov.recruiters}</b><span>companies recruited</span></div><div class="kpi"><b>${lpa(ov.highest_lpa)}</b><span>highest package</span></div><div class="kpi"><b>${lpa(ov.average_lpa)}</b><span>average package</span></div></div>
    <div class="filters"><input class="input" id="co-q" placeholder="Search a company…" style="flex:1;min-width:220px"></div><div class="cards" id="co-list"></div>`;
  draw(list.companies);
  $('#co-q').oninput = go(async e => draw((await api('/api/diary/companies?q=' + encodeURIComponent(e.target.value))).companies));
  $('#co-list').onclick = e => { const c = e.target.closest('.co'); if (c) location.hash = '#/company/' + c.dataset.id; };
}

async function company(id) {
  const c = await api('/api/diary/companies/' + id);
  const exp = (title, items, render) => `<div class="card"><h3>${title} (${items.length})</h3>${items.length ? items.map(render).join('') : '<p class="empty">Nobody has shared one yet.</p>'}</div>`;
  $('#view').innerHTML = `<a class="btn back" href="#">← All companies</a>
    <div class="card"><h2>${esc(c.name)}</h2><span class="muted">${esc(c.sector || '')} · last three years: ${esc(c.years.slice().reverse().join(', '))}</span>
      <div class="kpis" style="margin:14px 0 0"><div class="kpi"><b>${c.placed}</b><span>placed (full-time)</span></div><div class="kpi"><b>${c.interns}</b><span>interns</span></div>
        <div class="kpi"><b>${lpa(c.min_lpa)}</b><span>lowest package</span></div><div class="kpi"><b>${lpa(c.avg_lpa)}</b><span>average package</span></div><div class="kpi"><b>${lpa(c.max_lpa)}</b><span>highest package</span></div></div></div>
    <div class="grid-2"><div class="card"><h4>Year by year</h4><table class="table"><thead><tr><th>Year</th><th class="num">Placed</th><th class="num">Interns</th><th class="num">Package (LPA)</th><th class="num">Avg stipend/mo</th></tr></thead><tbody>
      ${c.by_year.map(y => `<tr><td>${esc(y.ay_id)}</td><td class="num">${y.placed}</td><td class="num">${y.interns}</td><td class="num">${y.min_lpa == null ? '–' : y.min_lpa === y.max_lpa ? y.max_lpa : y.min_lpa + ' – ' + y.max_lpa}</td><td class="num">${y.avg_stipend ? '₹' + y.avg_stipend.toLocaleString('en-IN') : '–'}</td></tr>`).join('')}</tbody></table></div>
      <div class="card"><h4>Roles offered</h4>${c.roles.length ? c.roles.map(r => `<span class="pill" style="margin:2px">${esc(r.label)} × ${r.value}</span>`).join('') : '<p class="empty">Not recorded.</p>'}
        <h4 style="margin-top:14px">Offer types</h4>${c.offer_types.map(r => `<span class="pill" style="margin:2px">${esc(r.label)} × ${r.value}</span>`).join('') || '<p class="empty">–</p>'}</div></div>
    ${exp('Interview experiences', c.interviews, i => `<div class="exp"><b>${esc(i.ay_id)}</b> ${i.difficulty ? `<span class="pill ${i.difficulty === 'Hard' ? 'bad' : i.difficulty === 'Medium' ? 'warn' : 'ok'}">${esc(i.difficulty)}</span>` : ''} ${i.result ? `<span class="pill">${esc(i.result)}</span>` : ''}
      ${i.rounds_count ? `<p class="muted">${i.rounds_count} rounds${i.round_details ? ': ' + esc(i.round_details) : ''}</p>` : (i.round_details ? `<p class="muted">${esc(i.round_details)}</p>` : '')}
      ${i.questions_asked ? `<p><b>Questions asked:</b> ${esc(i.questions_asked)}</p>` : ''}${i.experience ? `<p>${esc(i.experience)}</p>` : ''}${i.tips ? `<p><b>Tips:</b> ${esc(i.tips)}</p>` : ''}</div>`)}
    ${exp('Internship experiences', c.internships, i => `<div class="exp"><b>${esc(i.ay_id)}</b> ${i.role ? '· ' + esc(i.role) : ''} ${i.duration ? '· ' + esc(i.duration) : ''} ${i.mode ? `<span class="pill">${esc(i.mode)}</span>` : ''} <span style="color:var(--warn)">${stars(i.rating)}</span>
      ${i.tech_stack ? `<p class="muted">Tech: ${esc(i.tech_stack)}</p>` : ''}${i.work_summary ? `<p><b>Work:</b> ${esc(i.work_summary)}</p>` : ''}${i.learnings ? `<p><b>Learnings:</b> ${esc(i.learnings)}</p>` : ''}${i.experience ? `<p>${esc(i.experience)}</p>` : ''}</div>`)}`;
  window.scrollTo(0, 0);
}
start();
