/* "Enter placement experience": reached from the button at the top of the Placements Diary. The student goes straight to their offers and experiences
   (nothing about year, opting in or out, or consent: the class tutor records the first two, and what students share is always shown anonymously).
   The class tutor approves the record before anything is added to the diary.                                                                       */
(function () {
  'use strict';
  const S = { form: null, record: null, offers: [] };
  const STATUS = { PENDING: ['Waiting for your class tutor to approve it', 'warn'], APPROVED: ['Approved by your class tutor', 'ok'], REJECTED: ['Not approved', 'bad'], RETURNED: ['Sent back', 'warn'] };

  async function open() {
    const d = await api('/api/diary/my-record');
    S.form = d.sections; S.record = d.record;
    S.offers = d.record && d.record.offers.length ? d.record.offers.map(o => ({ ...o })) : [{}];
    draw();
  }
  const strip = t => t.replace(/^[A-E]\.\s*/, '');

  function input(f, o) {
    const v = o[f.key] ?? '', help = f.help ? `<div class="hint" style="margin:2px 0 0">${esc(f.help)}</div>` : '';
    let c;
    if (f.type === 'choice') c = `<div class="en-pills">${(f.choices || []).map(x => `<button type="button" class="en-pill ${v === x ? 'on' : ''}" data-k="${f.key}" data-v="${esc(x)}">${esc(x)}</button>`).join('')}</div>`;
    else if (f.type === 'list') c = `<select data-k="${f.key}"><option value=""></option>${(f.choices || []).map(x => `<option ${v === x ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>`;
    else if (f.type === 'para') c = `<textarea data-k="${f.key}" rows="3">${esc(v)}</textarea>`;
    else if (f.type === 'date') c = `<input class="input" type="date" data-k="${f.key}" value="${esc(v)}">`;
    else c = `<input class="input" data-k="${f.key}" ${f.type === 'number' ? 'inputmode="decimal"' : ''} value="${esc(v)}">`;
    return `<div class="en-f ${f.type === 'para' ? 'wide' : ''}"><label class="en-l">${esc(f.q)}${f.key === 'company' || f.key === 'offer_type' ? ' <i style="color:var(--bad);font-style:normal">*</i>' : ''}</label>${c}${help}</div>`;
  }

  function draw() {
    const f = S.form, rec = S.record, st = rec && STATUS[rec.status];
    const block = (sec, o, open) => `<details class="en-more" ${open ? 'open' : ''}><summary>${esc(strip(sec.title))} <span class="muted">(optional: helps juniors)</span></summary><div class="en-fields">${sec.fields.map(q => input(q, o)).join('')}</div></details>`;
    $('#view').innerHTML = `<a class="btn back" href="#" id="pe-back">← Back to the diary</a>
      <div class="card" style="max-width:860px"><div class="card-head"><div><h2>Enter placement experience</h2><p class="hint" style="margin:2px 0 0">Add each offer you received, and share how the interview and any internship went. Your class tutor approves it before it is added; juniors only ever see it without your name.</p></div></div>
        ${st ? `<div class="banner" style="background:var(--${st[1] === 'ok' ? 'ok' : 'warn'}-soft);color:var(--${st[1] === 'ok' ? 'ok' : 'warn'});border-color:currentColor">Your last record: <b>${st[0]}</b>${rec.reason ? ' · ' + esc(rec.reason) : ''}. If you change it, it goes to your tutor again.</div>` : ''}
        ${S.offers.map((o, i) => `<div class="card" style="margin-bottom:12px" data-o="${i}"><div class="card-head"><h3>${S.offers.length > 1 ? 'Offer ' + (i + 1) : esc(strip(f[1].title).replace(/\s*\(.*\)$/, ''))}</h3>${S.offers.length > 1 ? `<button class="btn sm" data-rm="${i}">Remove</button>` : ''}</div>
          <div class="en-fields">${f[1].fields.map(q => input(q, o)).join('')}</div>
          ${block(f[2], o, f[2].fields.some(q => o[q.key]))}${f.length > 4 ? block(f[3], o, f[3].fields.some(q => o[q.key])) : ''}</div>`).join('')}
        <button class="btn" id="pe-add">+ Add another offer</button>
        <p class="hint" style="margin-top:8px">Your placement year and whether you opted in or out are recorded by your class tutor.</p>
        <div class="en-actions"><span class="spacer"></span><button class="btn primary large" id="pe-send">Send for approval</button></div></div>`;
    wire();
  }

  const slot = el => S.offers[+el.closest('[data-o]').dataset.o];
  function wire() {
    const view = $('#view');
    view.oninput = e => { const t = e.target; if (t.dataset.k) slot(t)[t.dataset.k] = t.value; };
    view.onchange = e => { const t = e.target; if (t.dataset.k && t.tagName === 'SELECT') slot(t)[t.dataset.k] = t.value; };
    view.onclick = go(async e => {
      const t = e.target, pill = t.closest('.en-pill');
      if (pill) { const o = slot(pill), k = pill.dataset.k; o[k] = o[k] === pill.dataset.v ? '' : pill.dataset.v; pill.parentElement.querySelectorAll('.en-pill').forEach(p => p.classList.toggle('on', p.dataset.v === o[k])); return; }
      if (t.closest('#pe-back')) { e.preventDefault(); location.hash = '#'; return; }
      if (t.closest('#pe-add')) { S.offers.push({}); draw(); window.scrollTo(0, document.body.scrollHeight); return; }
      const rm = t.closest('[data-rm]'); if (rm) { S.offers.splice(+rm.dataset.rm, 1); draw(); return; }
      if (t.closest('#pe-send')) {
        if (!S.offers.some(o => o.company)) return toast('Add at least one offer: the company and the offer type', true);
        const r = await api('/api/diary/my-record', { method: 'POST', body: { offers: S.offers } });
        $('#view').innerHTML = `<div class="card" style="max-width:560px;margin:20px auto;text-align:center"><div class="rv-empty-ico" style="margin:0 auto 8px">✓</div><h2>Sent to your class tutor</h2>
          <p class="muted">${r.offers} offer${r.offers === 1 ? '' : 's'} recorded. It will show in the diary once your tutor approves it.</p><button class="btn primary" id="pe-done">Back to the diary</button></div>`;
        $('#pe-done').onclick = () => { location.hash = '#'; };
      }
    });
  }

  window.PlacementEntry = { open };
})();
