const API = "";

// ---------------------------------------------------------------- state
let sections = [];
let entries = [];
let forms = [];
let canonicalTags = [];
let savedLayouts = [];
let auditLogs = [];
let sectionLayouts = {};   // section_id -> layout template_id
let builtinLayouts = [];   // fixed layouts offered beside the canvas layouts
let issueInfo = null;
const FRONT_PREVIEWS = [{ template_id: "front_cover", name: "Cover page" }, { template_id: "front_hod", name: "HOD's Desk" }, { template_id: "front_editorial", name: "Editorial page" }];
let front = null;          // HOD desk, vision / mission, editorial board

let currentFormId = null;          // shared by Forms + Layout
let respFilter = "";               // "", pending, Approved, Rejected, featured
let layout = [];                   // blocks on the canvas
let layoutLoaded = false;
let currentLayoutId = "";          // "" = unsaved / default
let selectedBlockId = null;
let sample = {};
let dragSrc = null;
let addMode = "csv";

// ---------------------------------------------------------------- tags
const TAG_LABEL = {
  title: "Headline",
  author_or_person: "People / authors",
  organization_or_venue: "Venue / organisation",
  event_date: "Date",
  description: "Description",
  photo_url: "Photo link",
  photo_caption: "Photo caption",
  evidence_url: "Proof / document link",
  badge_tag: "Badge",
  grant_or_prize_amount: "Prize / grant / DOI",
  impact_or_indexing: "Indexing / level",
  featured_flag: "Spotlight flag",
  submitter_email: "Submitter email",
  submission_timestamp: "Timestamp",
  category_id: "Sub-section picker",
  custom: "Other (not shown)"
};
const SHOWN_TAGS = ["title", "author_or_person", "organization_or_venue", "event_date", "description", "photo_url", "photo_caption", "evidence_url", "badge_tag", "grant_or_prize_amount", "impact_or_indexing"];
const INTERNAL_TAGS = ["category_id", "featured_flag", "submitter_email", "submission_timestamp"];
const TAG_TYPE = { description: "textarea", photo_url: "image", evidence_url: "url", event_date: "date", category_id: "select", featured_flag: "select" };

const tagLabel = t => TAG_LABEL[t] || "Other (not shown)";
const isKnownTag = t => t in TAG_LABEL;

// ---------------------------------------------------------------- helpers
const $ = id => document.getElementById(id);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const slug = s => s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

// The studio is for the Admin and the HoD: the portal sign-in token goes with every call.
const authHeader = () => ({ Authorization: "Bearer " + (sessionStorage.getItem("tok") || "") });
function showNoAccess(message) {
  document.body.innerHTML = `<div style="max-width:420px;margin:18vh auto;text-align:center;font-family:Inter,system-ui,sans-serif">
    <h3 style="font-size:18px;margin-bottom:8px">${esc(message)}</h3><p style="color:#6b7684;margin-bottom:16px">You are signed in with an account that cannot use it.</p>
    <a href="/portal/" style="color:#1f4e78;font-weight:600">Back to the portal</a></div>`;
}
function signInAgain() { location.replace("/?next=/newsletter/"); }

async function api(method, url, body) {
  const opts = { method, headers: { ...authHeader() } };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const res = await fetch(API + url, opts);
  let data = null;
  try { data = await res.json(); } catch (e) { /* non-json */ }
  if (res.status === 401) { signInAgain(); throw new Error("Please sign in"); }
  if (res.status === 403 && /newsletter studio/i.test((data && data.detail) || "")) { showNoAccess(data.detail); throw new Error(data.detail); }
  if (!res.ok) throw new Error((data && (data.detail || data.message)) || `Request failed (${res.status})`);
  return data;
}

function toast(msg, isErr) {
  document.querySelector(".toast")?.remove();
  const t = document.createElement("div");
  t.className = "toast" + (isErr ? " err" : "");
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), isErr ? 4500 : 2500);
}

const openDlg = id => $(id).classList.remove("hidden");
const closeDlg = id => $(id).classList.add("hidden");
document.addEventListener("keydown", e => { if (e.key === "Escape") document.querySelectorAll(".overlay").forEach(o => o.classList.add("hidden")); });

const curForm = () => forms.find(f => f.form_id === currentFormId) || null;
const secName = id => sections.find(s => s.section_id === id)?.name || id;

// ---------------------------------------------------------------- boot
document.addEventListener("DOMContentLoaded", init);

async function init() {
  if (!sessionStorage.getItem("tok")) { signInAgain(); return; }
  document.querySelectorAll("#main-tabs .tab").forEach(b => b.addEventListener("click", () => switchTab(b.dataset.tab)));
  await syncMaster();     // quietly, so the Responses tab already shows what the master database holds
  try {
    [canonicalTags, sections, forms, entries, savedLayouts, auditLogs, sectionLayouts, builtinLayouts, front] = await Promise.all([
      api("GET", "/api/forms/canonical-tags"), api("GET", "/api/sections"), api("GET", "/api/forms"),
      api("GET", "/api/entries"), api("GET", "/api/visual-templates"), api("GET", "/api/audit-logs"),
      api("GET", "/api/section-layouts"), api("GET", "/api/builtin-layouts"), api("GET", "/api/front-matter")
    ]);
  } catch (e) { toast("Could not reach the server: " + e.message, true); }
  currentFormId = forms[0]?.form_id || null;
  api("GET", "/api/issues").then(list => {
    const i = list[0];
    issueInfo = i || null;
    if (i) {
      $("issue-chip").textContent = `${i.academic_year} · Vol ${i.volume} No ${i.issue}`;
      $("paper-vol").textContent = `VOL. ${i.volume} · ISSUE ${i.issue}`;
    }
  }).catch(() => {});
  renderOverview();
  renderFormsView();
  renderResponses();
  renderPublish();
  Tours.fetchMe('tok').then(r => { if (r) Tours.studio(r.me, r.token); });     // Help button + first-visit tour
}

async function switchTab(tab) {
  await flushPendingSave();
  document.querySelectorAll("#main-tabs .tab").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === "tab-" + tab));
  if (tab === "layout") initLayoutView();
  if (tab === "front") renderFront();
  if (tab === "overview") renderOverview();
  if (tab === "publish") renderPublish();
}

// Entries come from the master database: bring in whatever it holds that the newsletter does not have yet.
async function syncMaster(btn) {
  if (btn) { btn.disabled = true; btn.textContent = "Syncing…"; }
  try {
    const r = await api("POST", "/api/entries/sync-master", {});
    if (btn) toast(r.created ? `${r.created} new response${r.created > 1 ? "s" : ""} from the master database` : "Already up to date with the master database");
    if (r.failed?.length) toast(`${r.failed.length} could not be imported`, true);
    if (r.created && btn) await reloadEntries();
    return r;
  } catch (e) { if (btn) toast(e.message, true); }
  finally { if (btn) { btn.disabled = false; btn.textContent = "Sync from master database"; } }
}

async function reloadEntries() {
  [entries, auditLogs] = await Promise.all([api("GET", "/api/entries"), api("GET", "/api/audit-logs")]);
  renderOverview(); renderResponses(); renderPublish();
}

async function reloadFormsAndSections() {
  [sections, forms] = await Promise.all([api("GET", "/api/sections"), api("GET", "/api/forms")]);
  if (!forms.some(f => f.form_id === currentFormId)) currentFormId = forms[0]?.form_id || null;
  renderFormsView(); renderOverview(); renderResponses(); renderPublish();
}

// ================================================================ OVERVIEW
const isPending = e => e.approval_status === "Draft" || e.approval_status === "Reviewed";

function renderOverview() {
  $("stat-total").textContent = entries.length;
  $("stat-pending").textContent = entries.filter(isPending).length;
  $("stat-approved").textContent = entries.filter(e => e.approval_status === "Approved").length;
  $("stat-featured").textContent = entries.filter(e => e.featured_flag).length;

  $("overview-sections").querySelector("tbody").innerHTML = sections.map(s => {
    const own = entries.filter(e => e.section_id === s.section_id);
    return `<tr><td><strong>${esc(s.name)}</strong></td><td class="num">${own.length}</td><td class="num">${own.filter(e => e.approval_status === "Approved").length}</td></tr>`;
  }).join("") || `<tr><td colspan="3" class="empty">No sections yet. Create a form to add one.</td></tr>`;

  $("activity-log").innerHTML = auditLogs.slice(0, 20).map(l =>
    `<div class="log-row"><b>${esc((l.action || "").replace(/_/g, " ").toLowerCase())}</b> ${esc(l.details || "")}<br><small>${esc(new Date(l.timestamp).toLocaleString())}</small></div>`
  ).join("") || `<div class="empty">Nothing yet.</div>`;
}

function openResponses(filter) {
  respFilter = filter;
  switchTab("responses");
  renderResponses();
}

// ================================================================ FORMS
let pendingSave = false;
const flushSave = debounce(() => { if (pendingSave) saveCurrentForm(); }, 700);

function queueSave() {
  pendingSave = true;
  setSaveState("Saving…");
  flushSave();
}

function setSaveState(txt, ok) {
  const el = $("save-state");
  if (el) { el.textContent = txt; el.classList.toggle("ok", !!ok); }
}

async function saveCurrentForm() {
  pendingSave = false;
  const form = curForm();
  if (!form) return;
  const catCol = form.columns.find(c => c.canonical_tag === "category_id");
  form.category_field = catCol ? catCol.name : "";
  try {
    await api("PUT", `/api/forms/${form.form_id}`, {
      form_name: form.form_name,
      section_id: form.section_id,
      category_field: form.category_field,
      category_map: form.category_map || {},
      columns: form.columns.filter(c => c.name.trim())
    });
    setSaveState("Saved", true);
    renderFormsList();
  } catch (e) {
    setSaveState("Not saved");
    toast("Could not save: " + e.message, true);
  }
}

function renderFormsView() {
  renderFormsList();
  renderFormEditor();
}

function renderFormsList() {
  $("forms-list").innerHTML = forms.map(f => `
    <button class="form-item ${f.form_id === currentFormId ? "active" : ""}" onclick="selectForm('${f.form_id}')">
      <span class="fi-name">${esc(f.form_name.replace(/^IT Chronicles\s*[-–]\s*/, ""))}</span>
      <span class="fi-sub">${esc(secName(f.section_id))} · ${f.columns.length} questions</span>
    </button>`).join("");
}

async function selectForm(id) {
  await flushPendingSave();
  currentFormId = id;
  renderFormsView();
}

function tagSelectHtml(col) {
  const known = isKnownTag(col.canonical_tag) && col.canonical_tag !== "custom";
  const otherVal = known ? "custom" : col.canonical_tag;
  const opt = t => `<option value="${t}" ${t === col.canonical_tag ? "selected" : ""}>${tagLabel(t)}</option>`;
  return `
    <optgroup label="Shown in newsletter">${SHOWN_TAGS.map(opt).join("")}</optgroup>
    <optgroup label="Used behind the scenes">${INTERNAL_TAGS.map(opt).join("")}</optgroup>
    <option value="${esc(otherVal)}" ${!known ? "selected" : ""}>Other (not shown)</option>`;
}

function renderFormEditor() {
  const el = $("form-editor");
  const form = curForm();
  if (!form) {
    el.innerHTML = `<div class="card empty"><p>No forms yet.</p><p style="margin-top:10px"><button class="btn primary" onclick="openNewForm()">Create your first form</button></p></div>`;
    return;
  }
  const hasCat = form.columns.some(c => c.canonical_tag === "category_id");
  el.innerHTML = `
    <div class="editor-head">
      <input class="title-input" id="form-title" value="${esc(form.form_name)}" oninput="onFormTitle(this.value)">
      <span class="save-state" id="save-state"></span>
      <button class="btn danger-ghost sm" onclick="deleteForm()">Delete form</button>
    </div>
    <div class="meta-row">
      <span>Goes into section</span>
      <select onchange="onFormSection(this.value)">
        ${sections.map(s => `<option value="${s.section_id}" ${s.section_id === form.section_id ? "selected" : ""}>${esc(s.name)}</option>`).join("")}
      </select>
    </div>

    <div class="card">
      <div class="card-head"><h3>Questions <span class="muted">(${form.columns.length})</span></h3></div>
      <p class="hint" style="margin-top:-6px">Each question from your Google Form, and where its answer appears in the newsletter. We guess this automatically — fix only what looks wrong.</p>
      <div id="q-list">${form.columns.map((c, i) => questionRowHtml(c, i)).join("") || `<div class="empty">No questions yet — add some below.</div>`}</div>
      <div class="add-q">
        <div class="row">
          <textarea id="add-q-text" class="input" rows="2" placeholder="Type a question, paste a header row, or paste the form’s Apps Script"></textarea>
          <button class="btn primary" onclick="addQuestions()">Add &amp; detect</button>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head"><h3>Sub-sections</h3></div>
      <p class="hint" style="margin-top:-6px">${hasCat
        ? "Answers to the question marked “Sub-section picker” are sorted into these groups."
        : "Mark one question as “Sub-section picker” to sort responses into groups."}</p>
      <div class="chips" id="subcat-chips">${subcatChipsHtml(form)}</div>
      <div style="display:flex; gap:8px; max-width:420px">
        <input id="subcat-input" class="input" placeholder="Add a sub-section and press Enter" onkeydown="if(event.key==='Enter'){event.preventDefault();addSubcat();}">
        <button class="btn" onclick="addSubcat()">Add</button>
      </div>
    </div>`;
}

function questionRowHtml(c, i) {
  const unsure = !isKnownTag(c.canonical_tag) || c.canonical_tag === "custom";
  return `
    <div class="q-row ${unsure ? "unsure" : ""}" id="q-${i}">
      <input class="input" value="${esc(c.name)}" onchange="onQName(${i}, this.value)">
      <span class="q-arrow">→</span>
      <select class="input q-sel" onchange="onQTag(${i}, this.value)">${tagSelectHtml(c)}</select>
      <button class="icon-x" title="Remove question" onclick="removeQ(${i})">×</button>
      ${unsure ? `<div class="q-note">Not recognised. Pick what this question is, or leave it as Other to keep it out of the newsletter.</div>` : ""}
    </div>`;
}

function subcatChipsHtml(form) {
  const labels = Object.keys(form.category_map || {});
  return labels.length
    ? labels.map(l => `<span class="chip">${esc(l)}<button title="Remove" onclick="removeSubcat(this.dataset.l)" data-l="${esc(l)}">×</button></span>`).join("")
    : `<span class="muted">None yet</span>`;
}

function onFormTitle(v) {
  const form = curForm(); if (!form) return;
  form.form_name = v;
  queueSave();
}
function onFormSection(v) {
  const form = curForm(); if (!form) return;
  form.section_id = v;
  queueSave();
}
function onQName(i, v) {
  const form = curForm(); if (!form) return;
  form.columns[i].name = v.trim();
  queueSave();
}
function onQTag(i, tag) {
  const form = curForm(); if (!form) return;
  const col = form.columns[i];
  col.canonical_tag = tag;
  col.type = TAG_TYPE[tag] || "text";
  if (tag === "category_id") {
    form.columns.forEach((c, j) => { if (j !== i && c.canonical_tag === "category_id") { c.canonical_tag = "custom"; c.type = "text"; } });
    col.required = true;
    renderFormEditor();
  } else {
    $("q-" + i).outerHTML = questionRowHtml(col, i);
  }
  queueSave();
}
function removeQ(i) {
  const form = curForm(); if (!form) return;
  form.columns.splice(i, 1);
  renderFormEditor();
  queueSave();
}
function addSubcat() {
  const form = curForm(); const inp = $("subcat-input");
  const v = inp.value.trim();
  if (!form || !v) return;
  form.category_map = form.category_map || {};
  if (!form.category_map[v]) form.category_map[v] = "cat_" + slug(v).slice(0, 24);
  inp.value = "";
  $("subcat-chips").innerHTML = subcatChipsHtml(form);
  inp.focus();
  queueSave();
}
function removeSubcat(label) {
  const form = curForm(); if (!form) return;
  delete form.category_map[label];
  $("subcat-chips").innerHTML = subcatChipsHtml(form);
  queueSave();
}

async function addQuestions() {
  const form = curForm(); const box = $("add-q-text");
  const text = box.value.trim();
  if (!form || !text) return;
  const before = form.columns.length;
  try {
    await flushPendingSave();
    if (/FormApp/.test(text)) {   // the Apps Script itself was pasted: take its questions
      const parsed = await api("POST", "/api/forms/parse-script", { script: text });
      const src = parsed.find(p => p.existing_form_id === form.form_id) || parsed[0];
      const have = new Set(form.columns.map(c => c.name));
      await api("PUT", `/api/forms/${form.form_id}`, {
        columns: form.columns.concat(src.columns.filter(c => !have.has(c.name))),
        category_map: { ...src.category_map, ...(form.category_map || {}) },
        category_field: form.category_field || src.category_field
      });
    } else {
      await api("POST", `/api/forms/${form.form_id}/columns/bulk`, { headers_text: text });
    }
    await reloadFormsAndSections();
    await autoPickCategory(currentFormId);
    toast(`Added ${curForm().columns.length - before} question(s)`);
  } catch (e) { toast(e.message, true); }
}

// If a pasted header was detected as the sub-section picker, make it the form's category field
async function autoPickCategory(formId) {
  const form = forms.find(f => f.form_id === formId);
  const cat = form?.columns.find(c => c.canonical_tag === "category_id");
  if (form && cat && form.category_field !== cat.name) {
    await api("PUT", `/api/forms/${formId}`, { category_field: cat.name });
    form.category_field = cat.name;
  }
}

async function flushPendingSave() { if (pendingSave) await saveCurrentForm(); }

async function deleteForm() {
  const form = curForm(); if (!form) return;
  if (!confirm(`Delete “${form.form_name}”? Responses already collected are kept.`)) return;
  pendingSave = false;
  try {
    await api("DELETE", `/api/forms/${form.form_id}`);
    currentFormId = null;
    await reloadFormsAndSections();
    toast("Form deleted");
  } catch (e) { toast(e.message, true); }
}

// ---- import from a Google Apps Script (the one that builds the form)
let scriptForms = [];

function openScriptImport() {
  $("script-text").value = "";
  $("script-file").value = "";
  $("script-results").innerHTML = "";
  $("script-go").disabled = true;
  scriptForms = [];
  openDlg("dlg-script");
}

async function onScriptFile() {
  const f = $("script-file").files[0];
  if (!f) return;
  $("script-text").value = await f.text();
  detectScript();
}

async function detectScript() {
  const script = $("script-text").value.trim();
  if (!script) { toast("Paste your Apps Script first", true); return; }
  try {
    scriptForms = await api("POST", "/api/forms/parse-script", { script });
  } catch (e) { $("script-results").innerHTML = `<p class="result err">${esc(e.message)}</p>`; $("script-go").disabled = true; return; }
  const sectionOpts = `<option value="__new__">New section</option>` + sections.map(s => `<option value="${s.section_id}">${esc(s.name)}</option>`).join("");
  $("script-results").innerHTML = scriptForms.map((f, i) => {
    const existing = forms.find(x => x.form_id === f.existing_form_id);
    const missing = existing ? f.columns.filter(c => !existing.columns.some(x => x.name === c.name)).length : f.columns.length;
    return `
      <div class="script-form">
        <label class="sf-head"><input type="checkbox" id="sf-on-${i}" checked>
          <span><strong>${esc(f.title.replace(/^IT Chronicles\s*[-–]\s*/, ""))}</strong>
          <span class="muted">${f.columns.length} questions${f.category_field ? ` · sub-sections from “${esc(f.category_field)}” (${Object.keys(f.category_map).length})` : ""}</span></span></label>
        <div class="sf-meta">${existing
          ? `<span class="tag Approved">Already exists</span> <span class="muted">${missing ? `${missing} new question(s) will be added` : "nothing new to add"}</span>`
          : `<span class="tag">New form</span> <select class="input compact" id="sf-sec-${i}">${sectionOpts}</select>`}</div>
      </div>`;
  }).join("");
  $("script-go").disabled = false;
}

async function importScriptForms() {
  let done = 0, last = null;
  try {
    for (let i = 0; i < scriptForms.length; i++) {
      if (!$(`sf-on-${i}`).checked) continue;
      const f = scriptForms[i];
      const existing = forms.find(x => x.form_id === f.existing_form_id);
      if (existing) {
        const have = new Set(existing.columns.map(c => c.name));
        const columns = existing.columns.concat(f.columns.filter(c => !have.has(c.name)));
        const map = { ...f.category_map, ...(existing.category_map || {}) };
        await api("PUT", `/api/forms/${existing.form_id}`, {
          columns, category_map: map, category_field: existing.category_field || f.category_field
        });
        last = existing.form_id;
      } else {
        let id = "form_" + (slug(f.title.replace(/^IT Chronicles\s*[-–]\s*/, "")) || "new");
        for (let n = 2; forms.some(x => x.form_id === id); n++) id += "_" + n;
        const sec = $(`sf-sec-${i}`).value;
        const payload = { form_id: id, form_name: f.title, section_name: f.title.replace(/^IT Chronicles\s*[-–]\s*/, "").replace(/\s*Submission Form$/i, ""),
          columns: f.columns, category_field: f.category_field, category_map: f.category_map };
        if (sec !== "__new__") payload.section_id = sec;
        await api("POST", "/api/forms", payload);
        last = id;
      }
      done++;
    }
    closeDlg("dlg-script");
    if (last) currentFormId = last;
    await reloadFormsAndSections();
    toast(`Imported ${done} form(s) from the script`);
  } catch (e) { toast(e.message, true); }
}

// ---- new form dialog
const STANDARD_QUESTIONS = [
  ["Timestamp", "submission_timestamp"], ["Email Address", "submitter_email"], ["Contributor / Full Name", "author_or_person"],
  ["Title of Achievement / Event / Initiative", "title"], ["Host Organization / Venue / Agency", "organization_or_venue"],
  ["Date of Occurrence", "event_date"], ["Key Impact Badge / Metric", "badge_tag"], ["Grant / Prize / Registration Number", "grant_or_prize_amount"],
  ["Executive Summary / Description", "description"], ["Photo Cloud URL", "photo_url"], ["Photo Caption & Persons in Picture", "photo_caption"],
  ["Evidence / Proof Document Link", "evidence_url"]
].map(([name, tag]) => ({ name, canonical_tag: tag, type: TAG_TYPE[tag] || "text", required: ["submitter_email", "author_or_person", "title", "event_date", "description"].includes(tag) }));

function openNewForm() {
  $("nf-name").value = "";
  $("nf-headers").value = "";
  $("nf-section").innerHTML = `<option value="__new__">Create a new section for it</option>` +
    sections.map(s => `<option value="${s.section_id}">${esc(s.name)}</option>`).join("");
  openDlg("dlg-new-form");
  $("nf-name").focus();
}

async function createForm() {
  const name = $("nf-name").value.trim();
  const headers = $("nf-headers").value.trim();
  const secVal = $("nf-section").value;
  if (!name) { toast("Give the form a name", true); return; }

  let id = "form_" + (slug(name) || "new");
  for (let n = 2; forms.some(f => f.form_id === id); n++) id = `form_${slug(name)}_${n}`;

  try {
    const payload = { form_id: id, form_name: name, section_name: name, columns: headers ? [] : STANDARD_QUESTIONS };
    if (secVal !== "__new__") payload.section_id = secVal;
    await api("POST", "/api/forms", payload);
    if (headers) await api("POST", `/api/forms/${id}/columns/bulk`, { headers_text: headers });
    currentFormId = id;
    closeDlg("dlg-new-form");
    await reloadFormsAndSections();
    await autoPickCategory(id);
    renderFormEditor();
    toast(`“${name}” created`);
  } catch (e) { toast(e.message, true); }
}

// ================================================================ LAYOUT (canvas)
// A layout is a 12-column grid. Every element has a position (x, y) and size (w, h) in cells,
// is linked to a form column by its header, and carries its own styling.
const COLS = 12;
const ROW_PX = 28;

const BLOCK_TYPES = {
  headline: { label: "Headline",     ico: "H",  tags: ["title"], w: 12, h: 3, style: {} },
  byline:   { label: "Authors",      ico: "By", tags: ["author_or_person"], w: 12, h: 1, style: {} },
  meta:     { label: "Venue & date", ico: "Vn", tags: ["organization_or_venue"], w: 12, h: 1, style: {} },
  text:     { label: "Description",  ico: "¶",  tags: ["description"], w: 12, h: 6, style: {} },
  badge:    { label: "Badge",        ico: "◖◗", tags: ["badge_tag", "impact_or_indexing"], w: 6, h: 1, style: {} },
  image:    { label: "Photo",        ico: "▣",  tags: ["photo_url"], w: 12, h: 12, style: { showCaption: true } },
  link:     { label: "Link",         ico: "↗",  tags: ["evidence_url"], w: 6, h: 2, style: {} },
  stats:    { label: "Stat callout", ico: "#",  tags: ["grant_or_prize_amount"], w: 6, h: 2, style: {} },
  label:    { label: "Text label",   ico: "T",  tags: [], w: 12, h: 2, style: {}, text: "Your text" },
  divider:  { label: "Divider",      ico: "—",  tags: [], w: 12, h: 1, style: {} }
};
const TEXTISH = ["headline", "byline", "meta", "text", "badge", "stats", "link", "label"];

let undoStack = [];

const byId = id => layout.find(b => b.id === id);
const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
const cloneLayout = () => JSON.parse(JSON.stringify(layout));

// ---- default / migrated layouts
function mkBlock(type, x = 1, y = 999) {
  const t = BLOCK_TYPES[type];
  const b = { id: "b" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6), type, x, y, w: t.w, h: t.h, style: { ...t.style } };
  if (t.linkText) b.linkText = t.linkText;
  if (t.text) b.text = t.text;
  const col = columnForTags(t.tags);
  if (col) { b.column = col.name; b.tag = col.canonical_tag; } else if (t.tags[0]) { b.tag = t.tags[0]; }
  return b;
}

function columnForTags(tags) {
  const cols = curForm()?.columns || [];
  for (const t of tags) { const c = cols.find(c => c.canonical_tag === t); if (c) return c; }
  return null;
}

const DEFAULT_LAYOUT = () => {
  const list = ["badge", "headline", "byline", "image", "text", "link"].map((t, i) => mkBlock(t, 1, 100 + i));
  list[0].w = 12;
  return compactAll(list);
};

// Presets store headline / byline / venue as generic text blocks; give them their proper role
const TEXT_ROLE = { title: "headline", author_or_person: "byline", organization_or_venue: "meta" };

// Layouts saved before the canvas existed are flat lists: stack them top to bottom (same rules as the Word export)
function ensureGrid(blocks) {
  blocks = blocks.map(b => ({ ...b, type: b.type === "text" && TEXT_ROLE[b.tag] ? TEXT_ROLE[b.tag] : b.type, style: { ...(b.style || {}) } }));
  if (!blocks.every(b => ["x", "y", "w", "h"].every(k => typeof b[k] === "number"))) {
    let y = 1;
    for (let i = 0; i < blocks.length; i++) {
      const b = blocks[i];
      const ratio = { "16:9": 16 / 9, "4:3": 4 / 3, "1:1": 1 }[b.style.aspectRatio] || 16 / 9;
      if (b.type === "image" && b.style.float === "left") {
        Object.assign(b, { x: 1, y, w: 4, h: Math.max(3, Math.round(4 * 50 / ratio / ROW_PX)) });
        let ry = y;
        for (const r of blocks.slice(i + 1)) { Object.assign(r, { x: 5, y: ry, w: 8, h: BLOCK_TYPES[r.type]?.h || 2 }); ry += r.h; }
        break;
      }
      const h = b.type === "image" ? Math.round(600 / ratio / ROW_PX) : (BLOCK_TYPES[b.type]?.h || 2);
      Object.assign(b, { x: 1, y, w: COLS, h });
      y += h;
    }
  }
  const cols = curForm()?.columns || [];
  blocks.forEach(b => {   // link older blocks to the column that feeds their field
    if (!b.column && b.tag) { const c = cols.find(c => c.canonical_tag === b.tag); if (c) b.column = c.name; }
    b.id = b.id || mkBlock("divider").id;
  });
  return compactAll(blocks);
}

// ---- placement: elements never overlap and float up until they rest on another
function settle(pinned, list = layout) {
  const placed = pinned ? [pinned] : [];
  list.filter(b => b !== pinned).sort((a, b) => a.y - b.y || a.x - b.x).forEach(b => {
    b.y = 1;
    for (;;) { const hit = placed.find(p => overlap(p, b)); if (!hit) break; b.y = hit.y + hit.h; }
    placed.push(b);
  });
  return list;
}
const compactAll = list => settle(null, list);

function pushHistory() { undoStack.push(JSON.stringify(layout)); if (undoStack.length > 60) undoStack.shift(); }
function undoLayout() {
  if (!undoStack.length) { toast("Nothing to undo"); return; }
  layout = JSON.parse(undoStack.pop());
  if (!byId(selectedBlockId)) selectedBlockId = null;
  renderCanvas(); renderInspector();
}
function mutate(fn, pinnedSettle = true) {
  const b = byId(selectedBlockId); if (!b) return;
  pushHistory();
  fn(b);
  b.w = Math.max(1, Math.min(COLS, b.w)); b.x = Math.max(1, Math.min(COLS - b.w + 1, b.x)); b.h = Math.max(1, b.h); b.y = Math.max(1, b.y);
  if (pinnedSettle) settle(b);
  compactAll(layout);
  renderCanvas(); renderInspector();
}

// ---- tab setup
let canvasWired = false;

function initLayoutView() {
  if (!canvasWired) {
    canvasWired = true;
    $("palette-items").innerHTML = Object.entries(BLOCK_TYPES).map(([k, t]) =>
      `<button class="pal-item" draggable="true" data-type="${k}"><span class="pal-ico">${t.ico}</span>${t.label}</button>`).join("");
    $("palette-items").querySelectorAll(".pal-item").forEach(p => {
      p.addEventListener("click", () => addBlock(p.dataset.type));
      p.addEventListener("dragstart", e => { dragSrc = p.dataset.type; e.dataTransfer.setData("text/plain", dragSrc); e.dataTransfer.effectAllowed = "copy"; });
      p.addEventListener("dragend", () => { dragSrc = null; clearGhost(); });
    });
    wireCanvas();
  }
  $("lay-form").innerHTML = forms.map(f => `<option value="${f.form_id}" ${f.form_id === currentFormId ? "selected" : ""}>${esc(f.form_name.replace(/^IT Chronicles\s*[-–]\s*/, ""))}</option>`).join("");
  fillLayoutSelect(currentLayoutId);
  if (!layoutLoaded) { layoutLoaded = true; onSavedLayoutChange(); }
}

// The form supplies the column list and example content; the layout itself belongs to no form or section.
async function onLayoutFormChange() {
  await flushPendingSave();
  currentFormId = $("lay-form").value;
  renderFormsList();
  renderSampleOptions();
  renderCanvas();
  renderInspector();
}

function fillLayoutSelect(selectId) {
  $("lay-saved").innerHTML = `<optgroup label="Front pages">${FRONT_PREVIEWS.map(t => `<option value="${esc(t.template_id)}">${esc(t.name)}</option>`).join("")}</optgroup>` +
    `<optgroup label="Fixed layouts">${builtinLayouts.map(t => `<option value="${esc(t.template_id)}">${esc(t.name)}</option>`).join("")}</optgroup>` +
    `<optgroup label="Editable canvas"><option value="">New layout</option>${savedLayouts.map(t => `<option value="${esc(t.template_id)}">${esc(t.name)}</option>`).join("")}</optgroup>`;
  $("lay-saved").value = [...FRONT_PREVIEWS, ...builtinLayouts, ...savedLayouts].some(t => t.template_id === selectId) ? selectId : "";
}

const isFrontPreview = () => FRONT_PREVIEWS.some(t => t.template_id === currentLayoutId);
const isFixedLayout = () => isFrontPreview() || builtinLayouts.some(t => t.template_id === currentLayoutId);

function onSavedLayoutChange() {
  currentLayoutId = $("lay-saved").value;
  $("tab-layout").classList.toggle("fixed-mode", isFixedLayout());
  if (isFixedLayout()) {
    $("lay-name").value = [...FRONT_PREVIEWS, ...builtinLayouts].find(t => t.template_id === currentLayoutId).name;
    selectedBlockId = null; undoStack = [];
    renderSampleOptions(); renderCanvas(); renderInspector();
    return;
  }
  const tpl = savedLayouts.find(t => t.template_id === currentLayoutId);
  layout = tpl && tpl.layout?.length ? ensureGrid(JSON.parse(JSON.stringify(tpl.layout))) : DEFAULT_LAYOUT();
  $("lay-name").value = tpl ? tpl.name : "New layout";
  selectedBlockId = null;
  undoStack = [];
  renderSampleOptions();
  renderCanvas();
  renderInspector();
}

function resetLayout() { onSavedLayoutChange(); toast("Layout reset"); }

function togglePreviewMode() {
  if ($("lay-preview").checked) selectedBlockId = null;
  renderCanvas(); renderInspector();
}

// ---- sample data
function demoSample() {
  const f = curForm();
  return JSON.parse(JSON.stringify(SAMPLE_DATA[f?.form_id] || SAMPLE_DATA.form_research));
}

function renderSampleOptions() {
  const f = curForm();
  const own = entries.filter(e => e.section_id === f?.section_id).slice(0, 8);
  $("lay-sample").innerHTML = `<option value="demo">Example content</option>` +
    (own.length ? `<optgroup label="Real responses">${own.map(e => `<option value="${esc(e.entry_id)}">${esc((e.title || e.entry_id).slice(0, 40))}</option>`).join("")}</optgroup>` : "");
  sample = demoSample();
  renderSampleFields();
}

function onSampleChange() {
  const v = $("lay-sample").value;
  sample = v === "demo" ? demoSample() : { ...(entries.find(e => e.entry_id === v) || demoSample()) };
  renderSampleFields();
  renderCanvas();
}

function renderSampleFields() {
  const fields = [["title", "Headline"], ["author_or_person", "Authors"], ["organization_or_venue", "Venue"], ["event_date", "Date"], ["badge_tag", "Badge"], ["grant_or_prize_amount", "Prize / grant"], ["photo_url", "Photo link"], ["photo_caption", "Photo caption"], ["description", "Description"], ["evidence_url", "Proof link"]];
  $("sample-fields").innerHTML = fields.map(([k, l]) =>
    `<div class="field"><label>${l}</label><input class="input" value="${esc(sample[k] || "")}" oninput="sample['${k}']=this.value; renderCanvas()"></div>`).join("");
}

// ---- rendering
const ph = txt => `<span class="ph">${esc(txt)}</span>`;

function fontCss(st) {
  let css = "";
  if (st.fontSize) css += `font-size:${/^\d+(\.\d+)?$/.test(st.fontSize) ? st.fontSize + "px" : esc(st.fontSize)};`;
  if (st.fontWeight) css += `font-weight:${esc(st.fontWeight)};`;
  return css;
}

function valueOf(b) {
  if (b.type === "label") return b.text || "";
  return sample[b.tag] ?? sample[b.column] ?? "";
}

function blockHtml(b) {
  const v = valueOf(b);
  const st = b.style || {};
  const none = ph(b.column || "Link a column");
  const align = `text-align:${esc(st.textAlign || "left")};`;
  switch (b.type) {
    case "badge": return `<span class="nl-badge" style="${fontCss(st)}">${v ? esc(v) : none}</span>`;
    case "headline": return `<div class="nl-h" style="${align}${fontCss(st)}">${v ? esc(v) : none}</div>`;
    case "label": return `<div class="nl-h lbl" style="${align}${fontCss(st)}">${v ? esc(v) : ph("Your text")}</div>`;
    case "byline": return `<div class="nl-by" style="${align}${fontCss(st)}">By ${v ? esc(v) : none}</div>`;
    case "meta": return `<div class="nl-meta" style="${align}${fontCss(st)}">${v ? esc(v) : none}${v && sample.event_date ? " · " + esc(sample.event_date) : ""}</div>`;
    case "text": return `<p class="nl-p" style="${align}${fontCss(st)}">${v ? esc(v) : none}</p>`;
    case "link": return `<div style="${align}"><span class="nl-link" style="${fontCss(st)}">${v ? esc(v) : none}</span></div>`;
    case "stats": return `<div class="nl-stat"><b>${v ? esc(v) : none}</b><span>${esc(sample.badge_tag || "")}</span></div>`;
    case "divider": return `<div class="nl-hr"></div>`;
    case "image": {
      const cap = st.showCaption !== false ? sample.photo_caption : "";
      return `<div class="nl-img fill">
        ${v ? `<img src="${esc(v)}" alt="" draggable="false" onerror="this.style.visibility='hidden'">` : `<div class="ph-box">${none}</div>`}
        ${cap ? `<div class="nl-cap">${esc(cap)}</div>` : ""}</div>`;
    }
  }
  return "";
}

const V_ALIGN = { top: "flex-start", middle: "center", bottom: "flex-end" };

function renderCanvas() {
  const fixed = isFixedLayout();
  $("paper").classList.toggle("no-head", isFrontPreview());
  $("grid").classList.toggle("hidden", fixed);
  $("fixed-preview").classList.toggle("hidden", !fixed);
  if (fixed) { renderFixedPreview(); return; }
  const f = curForm();
  const sec = sections.find(s => s.section_id === f?.section_id);
  $("paper-title").textContent = "IT CHRONICLES" + (sec ? " · " + sec.name.toUpperCase() : "");
  const preview = $("lay-preview").checked;
  const bottom = layout.reduce((m, b) => Math.max(m, b.y + b.h - 1), 0);
  const rows = Math.max(22, bottom + 6);
  const grid = $("grid");
  grid.style.gridTemplateRows = `repeat(${rows}, ${ROW_PX}px)`;
  grid.classList.toggle("edit", !preview);
  $("paper").classList.toggle("preview", preview);
  grid.innerHTML = layout.map(b => {
    const sel = !preview && b.id === selectedBlockId;
    const st = b.style || {};
    return `<div class="gb gb-${b.type} ${sel ? "sel" : ""}" data-id="${b.id}" style="${posCss(b)}justify-content:${V_ALIGN[st.vAlign] || "flex-start"}">
      <div class="gb-in">${blockHtml(b)}</div>
      ${sel ? `<span class="gb-tag">${esc(b.type === "label" ? "Text label" : b.column || "Not linked to a column")}</span>${["n", "s", "e", "w", "ne", "nw", "se", "sw"].map(h => `<i class="hd hd-${h}" data-h="${h}"></i>`).join("")}` : ""}
    </div>`;
  }).join("");
}

const posCss = b => `grid-column:${b.x} / span ${b.w}; grid-row:${b.y} / span ${b.h};`;

function positionDom() {
  layout.forEach(b => {
    const el = $("grid").querySelector(`[data-id="${b.id}"]`);
    if (el) { el.style.gridColumn = `${b.x} / span ${b.w}`; el.style.gridRow = `${b.y} / span ${b.h}`; }
  });
}

// ---- pointer handling: select, move, resize
function cellAt(clientX, clientY) {
  const r = $("grid").getBoundingClientRect();
  return {
    col: Math.max(1, Math.min(COLS, Math.floor((clientX - r.left) / (r.width / COLS)) + 1)),
    row: Math.max(1, Math.floor((clientY - r.top) / ROW_PX) + 1)
  };
}

function wireCanvas() {
  const grid = $("grid");

  grid.addEventListener("pointerdown", e => {
    if ($("lay-preview").checked || e.button !== 0) return;
    const gb = e.target.closest(".gb");
    if (!gb) { if (selectedBlockId) { selectedBlockId = null; renderCanvas(); renderInspector(); } return; }
    const id = gb.dataset.id;
    const handle = e.target.closest(".hd")?.dataset.h || null;
    if (id !== selectedBlockId) { selectedBlockId = id; renderCanvas(); renderInspector(); }
    startGesture(e, id, handle);
  });

  grid.addEventListener("dragover", e => {
    if (!dragSrc) return;
    e.preventDefault();
    const { col, row } = cellAt(e.clientX, e.clientY);
    const t = BLOCK_TYPES[dragSrc];
    showGhost(Math.min(col, COLS - t.w + 1), row, t.w, t.h);
  });
  grid.addEventListener("drop", e => {
    if (!dragSrc) return;
    e.preventDefault();
    const { col, row } = cellAt(e.clientX, e.clientY);
    const b = mkBlock(dragSrc, 1, row);
    b.x = Math.min(col, COLS - b.w + 1);
    pushHistory();
    layout.push(b);
    selectedBlockId = b.id;
    settle(b); compactAll(layout);
    dragSrc = null; clearGhost();
    renderCanvas(); renderInspector();
  });
  grid.addEventListener("dragleave", e => { if (!grid.contains(e.relatedTarget)) clearGhost(); });

  document.addEventListener("keydown", onCanvasKey);
}

function showGhost(x, y, w, h) {
  let g = $("grid").querySelector(".ghost");
  if (!g) { g = document.createElement("div"); g.className = "ghost"; $("grid").appendChild(g); }
  g.style.gridColumn = `${x} / span ${w}`; g.style.gridRow = `${y} / span ${h}`;
}
function clearGhost() { $("grid")?.querySelector(".ghost")?.remove(); }

function startGesture(e, id, handle) {
  e.preventDefault();
  const b = byId(id); if (!b) return;
  const before = JSON.stringify(layout);
  const start = { x: b.x, y: b.y, w: b.w, h: b.h };
  const c0 = cellAt(e.clientX, e.clientY);
  let moved = false;

  const onMove = ev => {
    const c = cellAt(ev.clientX, ev.clientY);
    if (!moved && c.col === c0.col && c.row === c0.row) return;
    moved = true;
    if (!handle) {                                   // move
      b.x = Math.max(1, Math.min(COLS - start.w + 1, start.x + c.col - c0.col));
      b.y = Math.max(1, start.y + c.row - c0.row);
    } else {                                         // resize from any edge or corner
      let { x, y, w, h } = start;
      if (handle.includes("e")) w = Math.max(1, c.col - x + 1);
      if (handle.includes("w")) { const nx = Math.min(c.col, x + w - 1); w = x + w - nx; x = nx; }
      if (handle.includes("s")) h = Math.max(1, c.row - y + 1);
      if (handle.includes("n")) { const ny = Math.min(c.row, y + h - 1); h = y + h - ny; y = ny; }
      Object.assign(b, { x, y, w, h });
    }
    settle(b);
    positionDom();
  };
  const onUp = () => {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
    if (!moved) return;
    compactAll(layout);
    if (JSON.stringify(layout) !== before) undoStack.push(before);
    renderCanvas(); renderInspector();
  };
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp);
}

function onCanvasKey(e) {
  if (!$("tab-layout").classList.contains("active")) return;
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); undoLayout(); return; }
  const b = byId(selectedBlockId); if (!b) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "d") { e.preventDefault(); duplicateBlock(); return; }
  if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); deleteBlock(); return; }
  const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
  if (!d) return;
  e.preventDefault();
  mutate(x => { if (e.shiftKey) { x.w += d[0]; x.h += d[1]; } else { x.x += d[0]; x.y += d[1]; } });
}

// ---- adding / removing
function addBlock(type) {
  pushHistory();
  const b = mkBlock(type, 1, 999);
  layout.push(b);
  selectedBlockId = b.id;
  compactAll(layout);
  renderCanvas(); renderInspector();
  $("grid").querySelector(".gb.sel")?.scrollIntoView({ block: "nearest" });
}
function duplicateBlock() {
  const b = byId(selectedBlockId); if (!b) return;
  pushHistory();
  const c = JSON.parse(JSON.stringify(b));
  c.id = mkBlock("divider").id; c.y = b.y + b.h;
  layout.push(c); selectedBlockId = c.id;
  compactAll(layout);
  renderCanvas(); renderInspector();
}
function deleteBlock() {
  if (!byId(selectedBlockId)) return;
  pushHistory();
  layout = layout.filter(b => b.id !== selectedBlockId);
  selectedBlockId = null;
  compactAll(layout);
  renderCanvas(); renderInspector();
}

// ---- inspector
function seg(options, current, fn) {
  return `<div class="seg">${options.map(([v, l]) => `<button class="${current === v ? "on" : ""}" onclick="${fn}('${v}')">${l}</button>`).join("")}</div>`;
}
const setStyle = (key, val) => mutate(b => { b.style = b.style || {}; b.style[key] = val; });
const setLinkText = v => { const b = byId(selectedBlockId); if (b) { b.linkText = v; renderCanvas(); } };
const setLabelText = v => { const b = byId(selectedBlockId); if (b) { b.text = v; renderCanvas(); } };
const setNum = (k, v) => { const n = parseInt(v, 10); if (!isNaN(n)) mutate(b => { b[k] = n; }); };

function setColumn(name) {
  mutate(b => {
    const c = (curForm()?.columns || []).find(c => c.name === name);
    b.column = name || undefined;
    b.tag = c ? c.canonical_tag : (name ? b.tag : "");
  }, false);
}

function alignOnPage(mode) {
  mutate(b => {
    if (mode === "full") { b.x = 1; b.w = COLS; }
    else if (mode === "left") b.x = 1;
    else if (mode === "center") b.x = Math.round((COLS - b.w) / 2) + 1;
    else if (mode === "right") b.x = COLS - b.w + 1;
  });
}

// Image + text arrangements: the text blocks that follow the photo are moved beside it or below it
function arrangeImage(mode) {
  const img = byId(selectedBlockId); if (!img || img.type !== "image") return;
  pushHistory();
  const order = [...layout].sort((a, b) => a.y - b.y || a.x - b.x);
  const at = order.indexOf(img);
  let group = [];
  for (const b of order.slice(at + 1)) { if (!TEXTISH.includes(b.type)) break; group.push(b); }
  if (!group.length) for (const b of order.slice(0, at).reverse()) { if (!TEXTISH.includes(b.type)) break; group.unshift(b); }
  const y0 = Math.min(img.y, ...group.map(b => b.y));
  if (mode === "top") {
    Object.assign(img, { x: 1, w: COLS, y: y0, h: Math.max(img.h, 8) });
    let y = y0 + img.h; group.forEach(b => { Object.assign(b, { x: 1, w: COLS, y }); y += b.h; });
  } else {
    const iw = 5, tw = COLS - iw;
    const ix = mode === "left" ? 1 : tw + 1, tx = mode === "left" ? iw + 1 : 1;
    Object.assign(img, { x: ix, w: iw, y: y0, h: 8 });
    let y = y0; group.forEach(b => { Object.assign(b, { x: tx, w: tw, y }); y += b.h; });
  }
  compactAll(layout);
  renderCanvas();
  // narrower columns wrap text onto more lines: grow each text box to fit, then restack
  let y = mode === "top" ? y0 + img.h : y0;
  group.forEach(b => {
    const inner = $("grid").querySelector(`[data-id="${b.id}"] .gb-in`);
    if (inner && ["headline", "byline", "meta", "text", "label"].includes(b.type)) b.h = Math.max(1, Math.ceil((inner.scrollHeight + 8) / ROW_PX));
    b.y = y; y += b.h;
  });
  compactAll(layout);
  renderCanvas(); renderInspector();
}

function fitHeight() {
  const el = $("grid").querySelector(".gb.sel .gb-in");
  if (!el) return;
  mutate(b => { b.h = Math.max(1, Math.ceil((el.scrollHeight + 8) / ROW_PX)); });
}

function renderInspector() {
  const el = $("inspector-element");
  const b = byId(selectedBlockId);
  if (!b) {
    el.innerHTML = `<div class="insp-head"><h3>Page</h3></div>
      <p class="insp-empty">Drag elements from the left onto the page. Click one to link it to a form column, move or resize it, and set how it aligns.</p>
      <p class="hint">Arrow keys nudge, Shift+arrows resize, Delete removes, Ctrl+Z undoes.</p>`;
    return;
  }
  const st = b.style || {};
  const t = BLOCK_TYPES[b.type];
  const cols = curForm()?.columns || [];
  const known = !b.column || cols.some(c => c.name === b.column);
  const colOpts = `<option value="">Not linked</option>` +
    (known ? "" : `<option value="${esc(b.column)}" selected>${esc(b.column)} (other form)</option>`) +
    cols.filter(c => c.canonical_tag !== "submission_timestamp").map(c => `<option value="${esc(c.name)}" ${c.name === b.column ? "selected" : ""}>${esc(c.name)}</option>`).join("");
  const isText = ["headline", "byline", "meta", "text", "label", "badge", "link"].includes(b.type);

  let typeOpts = "";
  if (b.type === "image") typeOpts = `
    <div class="field"><label>Caption</label>${seg([["on", "Show"], ["off", "Hide"]], st.showCaption === false ? "off" : "on", "setCaption")}</div>
    <div class="field"><label>Arrange photo with text</label>
      <div class="arrange">
        <button onclick="arrangeImage('top')" title="Photo on top, text below"><span class="ar ar-top"></span>Top</button>
        <button onclick="arrangeImage('left')" title="Photo left, text wraps on the right"><span class="ar ar-left"></span>Left</button>
        <button onclick="arrangeImage('right')" title="Photo right, text wraps on the left"><span class="ar ar-right"></span>Right</button>
      </div></div>`;
  if (b.type === "label") typeOpts = `<div class="field"><label>Text</label><input class="input" value="${esc(b.text || "")}" oninput="setLabelText(this.value)"></div>`;

  el.innerHTML = `
    <div class="insp-head"><h3>${esc(t.label)}</h3>
      <span><button class="icon-x" title="Duplicate (Ctrl+D)" onclick="duplicateBlock()">⧉</button><button class="icon-x" title="Delete" onclick="deleteBlock()">×</button></span></div>

    ${["divider", "label"].includes(b.type) ? "" : `
    <div class="field"><label>Linked form column</label>
      <select class="input" onchange="setColumn(this.value)">${colOpts}</select>
      <p class="hint" style="margin:4px 0 0">${b.column ? `Fills with the answer to this question${b.tag ? ` (${esc(tagLabel(b.tag))})` : ""}. Other forms use the matching field.` : "Pick the question this element should show."}</p>
    </div>`}
    ${typeOpts}

    <div class="field"><label>Align on page</label>
      <div class="seg">
        <button onclick="alignOnPage('left')">Left</button><button onclick="alignOnPage('center')">Centre</button>
        <button onclick="alignOnPage('right')">Right</button><button onclick="alignOnPage('full')">Full width</button>
      </div></div>
    ${b.type === "divider" ? "" : `
    <div class="field"><label>Text alignment</label>${seg([["left", "Left"], ["center", "Centre"], ["right", "Right"], ["justify", "Justify"]], st.textAlign || "left", "setAlign")}</div>
    <div class="field"><label>Vertical position</label>${seg([["top", "Top"], ["middle", "Middle"], ["bottom", "Bottom"]], st.vAlign || "top", "setVAlign")}</div>`}

    ${isText ? `
    <div class="field"><label>Weight</label>${seg([["", "Auto"], ["400", "Regular"], ["700", "Bold"]], st.fontWeight || "", "setWeight")}</div>` : ""}

    <div class="field"><label>Position &amp; size <span class="muted">(grid cells)</span></label>
      <div class="num4">
        ${[["x", "Col", b.x], ["y", "Row", b.y], ["w", "Wide", b.w], ["h", "High", b.h]].map(([k, l, v]) =>
          `<label>${l}<input class="input" type="number" min="1" value="${v}" onchange="setNum('${k}', this.value)"></label>`).join("")}
      </div>
      ${["headline", "byline", "meta", "text", "label"].includes(b.type) ? `<button class="btn sm" style="margin-top:8px" onclick="fitHeight()">Fit height to text</button>` : ""}
    </div>`;
}
const setCaption = v => setStyle("showCaption", v === "on");
const setAlign = v => setStyle("textAlign", v);
const setVAlign = v => setStyle("vAlign", v);
const setWeight = v => setStyle("fontWeight", v);

// ---- save
async function saveLayout() {
  const name = $("lay-name").value.trim() || "Untitled layout";
  const existing = savedLayouts.find(t => t.template_id === currentLayoutId);
  // Built-in presets are never overwritten; saving one makes a copy
  const id = existing && !existing.is_default ? existing.template_id : "tpl_" + Date.now();
  try {
    await api("POST", "/api/visual-templates", { template_id: id, name, layout });
    savedLayouts = await api("GET", "/api/visual-templates");
    currentLayoutId = id;
    fillLayoutSelect(id);
    renderPublish();
    toast("Layout saved. Choose where to use it in Publish");
  } catch (e) { toast(e.message, true); }
}

// ================================================================ RESPONSES
// ---- date range (Responses: what you look at; Publish: what goes into the newsletter). Each tab keeps its own range.
const ranges = { resp: { from: "", to: "" }, pub: { from: "", to: "" } };
const inRange = (e, r) => (!r.from && !r.to) || (!!e.date_iso && (!r.from || e.date_iso >= r.from) && (!r.to || e.date_iso <= r.to));
function setRange(k) {
  ranges[k] = { from: $(k + "-from").value, to: $(k + "-to").value };
  if (ranges[k].from && ranges[k].to && ranges[k].from > ranges[k].to) { toast("The start date is after the end date", true); }
  if (k === "resp") renderResponses(); else renderPublish();
}
function clearRange(k) { $(k + "-from").value = ""; $(k + "-to").value = ""; setRange(k); }
const rangeText = r => r.from && r.to ? `${r.from} to ${r.to}` : r.from ? `from ${r.from}` : r.to ? `up to ${r.to}` : "";

function renderResponses() {
  $("resp-clear").hidden = !(ranges.resp.from || ranges.resp.to);
  const secSel = $("filter-section");
  const prevSec = secSel.value;
  secSel.innerHTML = `<option value="">All sections</option>` + sections.map(s => `<option value="${s.section_id}">${esc(s.name)}</option>`).join("");
  secSel.value = sections.some(s => s.section_id === prevSec) ? prevSec : "";

  const inSec = entries.filter(e => (!secSel.value || e.section_id === secSel.value) && inRange(e, ranges.resp));
  const pills = [
    ["", "All", inSec.length],
    ["pending", "Needs review", inSec.filter(isPending).length],
    ["Approved", "Approved", inSec.filter(e => e.approval_status === "Approved").length],
    ["Rejected", "Rejected", inSec.filter(e => e.approval_status === "Rejected").length],
    ["featured", "Featured", inSec.filter(e => e.featured_flag).length]
  ];
  $("status-pills").innerHTML = pills.map(([k, l, n]) =>
    `<button class="pill ${respFilter === k ? "on" : ""}" onclick="setRespFilter('${k}')">${l}<span class="n">${n}</span></button>`).join("");

  const shown = inSec.filter(e =>
    !respFilter ? true : respFilter === "pending" ? isPending(e) : respFilter === "featured" ? e.featured_flag : e.approval_status === respFilter);

  $("responses-list").innerHTML = shown.map(e => `
    <article class="resp">
      <div>
        <div class="resp-title">${esc(e.title)}</div>
        <div class="resp-meta">${esc(e.author_or_person || "—")} · ${esc(e.organization_or_venue || "—")} · ${esc(e.event_date || "")} · ${esc(secName(e.section_id))}${e.badge_tag ? ` · <span class="tag">${esc(e.badge_tag)}</span>` : ""}</div>
        <div class="resp-desc">${esc(e.description || "")}</div>
      </div>
      <div class="resp-side">
        <div style="display:flex; align-items:center; gap:8px">
          <button class="star ${e.featured_flag ? "on" : ""}" title="${e.featured_flag ? "Remove from featured" : "Feature this"}" onclick="toggleFeatured('${esc(e.entry_id)}')">★</button>
          <span class="tag ${esc(e.approval_status)}">${esc(e.approval_status)}</span>
        </div>
        <div class="resp-actions">
          ${e.approval_status !== "Approved" ? `<button class="btn sm primary" onclick="setStatus('${esc(e.entry_id)}','Approved')">Approve</button>` : ""}
          ${e.approval_status !== "Rejected" ? `<button class="btn sm" onclick="setStatus('${esc(e.entry_id)}','Rejected')">Reject</button>` : ""}
        </div>
      </div>
    </article>`).join("") || `<div class="card empty">${entries.length ? "Nothing matches this filter." : "No responses yet. Use Import CSV or Add response."}</div>`;
}

function setRespFilter(k) { respFilter = k; renderResponses(); }

async function setStatus(id, status) {
  let reason = null;
  if (status === "Rejected") { reason = prompt("Reason for rejecting (optional):"); if (reason === null) return; }
  try {
    await api("POST", `/api/entries/${id}/status`, { approval_status: status, rejection_reason: reason || null });
    await reloadEntries();
  } catch (e) { toast(e.message, true); }
}

async function toggleFeatured(id) {
  const e = entries.find(x => x.entry_id === id); if (!e) return;
  try {
    await api("POST", `/api/entries/${id}/status`, { approval_status: e.approval_status, featured_flag: !e.featured_flag });
    await reloadEntries();
  } catch (err) { toast(err.message, true); }
}

// ---- add responses dialog
function openAddResponses(mode) {
  const opts = forms.map(f => `<option value="${f.form_id}" ${f.form_id === currentFormId ? "selected" : ""}>${esc(f.form_name.replace(/^IT Chronicles\s*[-–]\s*/, ""))}</option>`).join("");
  $("csv-form").innerHTML = opts;
  $("single-form").innerHTML = opts;
  $("csv-file").value = "";
  $("csv-file-label").textContent = "Choose a CSV or Excel file";
  $("csv-drop").classList.remove("has");
  $("csv-detect-note").textContent = "";
  setAddMode(mode);
  openDlg("dlg-add");
}

function setAddMode(mode) {
  addMode = mode;
  document.querySelectorAll("#add-mode button").forEach(b => b.classList.toggle("on", b.dataset.mode === mode));
  $("add-csv").classList.toggle("hidden", mode !== "csv");
  $("add-single").classList.toggle("hidden", mode !== "single");
  $("add-submit").textContent = mode === "csv" ? "Import" : "Add response";
  if (mode === "single") renderSingleFields();
}

function parseCsvLine(line) {
  const out = []; let cur = ""; let q = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (c === '"') { if (q && line[i + 1] === '"') { cur += '"'; i++; } else q = !q; }
    else if (c === "," && !q) { out.push(cur); cur = ""; }
    else cur += c;
  }
  out.push(cur);
  return out.map(s => s.trim().replace(/^﻿/, ""));
}

// Pick the form whose questions best match the file's header row
async function onCsvPicked() {
  const file = $("csv-file").files[0];
  if (!file) return;
  $("csv-file-label").textContent = file.name;
  $("csv-drop").classList.add("has");
  $("csv-detect-note").textContent = "";
  if (!/\.csv$/i.test(file.name)) return;
  const head = (await file.slice(0, 8192).text()).split(/\r?\n/)[0];
  const headers = new Set(parseCsvLine(head).map(h => h.toLowerCase()));
  let best = null, bestScore = 0;
  forms.forEach(f => {
    const score = f.columns.filter(c => headers.has(c.name.toLowerCase())).length;
    if (score > bestScore) { best = f; bestScore = score; }
  });
  if (best && bestScore >= 2) {
    $("csv-form").value = best.form_id;
    $("csv-detect-note").textContent = "— matched automatically";
  }
}

function renderSingleFields() {
  const form = forms.find(f => f.form_id === $("single-form").value);
  $("single-fields").innerHTML = (form?.columns || []).filter(c => c.canonical_tag !== "submission_timestamp").map(c => {
    const label = `<label>${esc(c.name)}${c.required ? " *" : ""}</label>`;
    if (c.name === form.category_field && Object.keys(form.category_map || {}).length)
      return `<div class="field">${label}<select class="input" data-q="${esc(c.name)}">${Object.keys(form.category_map).map(o => `<option>${esc(o)}</option>`).join("")}</select></div>`;
    if (c.type === "textarea") return `<div class="field">${label}<textarea class="input" rows="3" data-q="${esc(c.name)}"></textarea></div>`;
    return `<div class="field">${label}<input class="input" type="${c.type === "date" ? "date" : "text"}" data-q="${esc(c.name)}"></div>`;
  }).join("");
}

async function submitAdd() {
  try {
    if (addMode === "csv") {
      const file = $("csv-file").files[0];
      if (!file) { toast("Choose a file first", true); return; }
      const body = new FormData();
      body.append("form_id", $("csv-form").value);
      body.append("file", file);
      const r = await api("POST", "/api/entries/ingest-csv", body);
      toast(`Imported ${r.total_ingested} response(s)` + (r.duplicates_skipped ? `, skipped ${r.duplicates_skipped} already in the list` : ""));
    } else {
      const form = forms.find(f => f.form_id === $("single-form").value);
      const raw = {};
      let missing = false;
      $("single-fields").querySelectorAll("[data-q]").forEach(i => {
        raw[i.dataset.q] = i.value;
        const col = form.columns.find(c => c.name === i.dataset.q);
        if (col?.required && !i.value.trim()) missing = true;
      });
      if (missing) { toast("Please fill in the required fields (*)", true); return; }
      await api("POST", "/api/entries/ingest", { form_id: form.form_id, raw_data: raw });
      toast("Response added");
    }
    closeDlg("dlg-add");
    respFilter = "pending";
    await reloadEntries();
  } catch (e) { toast(e.message, true); }
}

// ================================================================ PUBLISH
function renderPublish() {
  const r = ranges.pub, ranged = !!(r.from || r.to);
  $("pub-clear").hidden = !ranged;
  const noDate = entries.filter(e => e.approval_status === "Approved" && !e.date_iso).length;
  $("pub-range-note").textContent = ranged
    ? `Only responses dated ${rangeText(r)} go into the newsletter.${noDate ? ` ${noDate} approved ${noDate === 1 ? "response has" : "responses have"} no readable date and ${noDate === 1 ? "is" : "are"} left out.` : ""}`
    : "No dates chosen: every approved response is used. Pick a start and an end date to use only that period.";
  const rows = sections.map(s => {
    const own = entries.filter(e => e.section_id === s.section_id && inRange(e, r));
    const appr = own.filter(e => e.approval_status === "Approved").length;
    const chosen = [...builtinLayouts, ...savedLayouts].some(t => t.template_id === sectionLayouts[s.section_id]) ? sectionLayouts[s.section_id] : "builtin_centered";
    const opt = t => `<option value="${esc(t.template_id)}" ${t.template_id === chosen ? "selected" : ""}>${esc(t.name)}</option>`;
    return `
      <div class="pub-row ${appr ? "" : "empty-sec"}">
        <input type="checkbox" id="pub-${s.section_id}" value="${s.section_id}" ${appr ? "checked" : ""} ${appr ? "" : "disabled"}>
        <label for="pub-${s.section_id}"><span class="pub-name">${esc(s.name)}</span>
          <span class="muted">${appr ? `${appr} approved` : "Nothing approved yet"}${own.length - appr ? ` · ${own.length - appr} not approved` : ""}</span></label>
        <select class="input compact layout-pick" title="Layout used for this section's entries" onchange="setSectionLayout('${s.section_id}', this.value)">
          <optgroup label="Fixed layouts">${builtinLayouts.map(opt).join("")}</optgroup>
          ${savedLayouts.length ? `<optgroup label="Your canvas layouts">${savedLayouts.map(opt).join("")}</optgroup>` : ""}
        </select>
        <button class="btn sm" ${appr ? "" : "disabled"} onclick="buildSection('${s.section_id}', this)">Download section</button>
      </div>`;
  });
  $("publish-sections").innerHTML = rows.join("") || `<div class="empty">No sections yet.</div>`;
  $("publish-count").textContent = `${entries.filter(e => e.approval_status === "Approved" && inRange(e, r)).length} approved responses${ranged ? " in this range" : ""}`;
}

async function setSectionLayout(sectionId, templateId) {
  try {
    await api("PUT", `/api/section-layouts/${sectionId}`, { template_id: templateId || null });
    if (templateId) sectionLayouts[sectionId] = templateId; else delete sectionLayouts[sectionId];
    toast("Layout applied to this section");
  } catch (e) { toast(e.message, true); renderPublish(); }
}

async function triggerDownload(filename) {
  const res = await fetch(`${API}/api/downloads/${encodeURIComponent(filename)}`, { headers: authHeader() });
  if (!res.ok) { toast("Could not download the file", true); return; }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await res.blob());
  a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}

async function buildSection(id, btn) {
  btn.disabled = true; const old = btn.textContent; btn.textContent = "Building…";
  try {
    const r = await api("POST", `/api/generate/section/${id}`, { section_id: id, date_from: ranges.pub.from || null, date_to: ranges.pub.to || null });
    triggerDownload(r.filename);
    toast(`${r.total_entries} entries · ${r.layout_used ? "layout: " + r.layout_used : "default layout"}`);
    api("GET", "/api/audit-logs").then(l => { auditLogs = l; });
  } catch (e) { toast(e.message, true); }
  btn.disabled = false; btn.textContent = old;
}

async function buildMaster() {
  const chosen = [...document.querySelectorAll("#publish-sections input[type=checkbox]:checked")].map(c => c.value);
  const box = $("master-result");
  if (!chosen.length) { toast("Tick at least one section", true); return; }
  const btn = $("btn-master");
  btn.disabled = true; btn.textContent = "Building…";
  try {
    const r = await api("POST", "/api/generate/master", { selected_section_ids: chosen, include_front_pages: $("pub-front").checked, date_from: ranges.pub.from || null, date_to: ranges.pub.to || null });
    box.className = "result";
    box.innerHTML = `${r.total_entries_included} entries from ${r.total_sections_included} sections.<br><a href="#" onclick="triggerDownload('${esc(r.filename)}'); return false;">Download ${esc(r.filename)}</a>`;
    triggerDownload(r.filename);
    api("GET", "/api/audit-logs").then(l => { auditLogs = l; });
  } catch (e) {
    box.className = "result err"; box.textContent = e.message;
  }
  btn.disabled = false; btn.textContent = "Build master document";
}

// ================================================================ FRONT PAGES
const photoUrl = p => !p ? "" : /^https?:/.test(p) ? p : `${API}/api/uploads/${encodeURIComponent(p.split("/").pop())}`;

function frontGet(path) { return path.split(".").reduce((o, k) => o?.[k], front) ?? ""; }
function setFront(path, val) {
  const keys = path.split("."); const last = keys.pop();
  keys.reduce((o, k) => o[k], front)[last] = val;
}

function photoField(path, label) {
  const url = photoUrl(frontGet(path));
  return `<div class="photo-field">
    <div class="photo-thumb">${url ? `<img src="${esc(url)}" alt="">` : "<span>No photo</span>"}</div>
    <div class="photo-actions">
      <label class="btn sm">${url ? "Replace" : "Upload"} ${esc(label)}<input type="file" accept="image/*" hidden onchange="uploadFrontPhoto('${path}', this)"></label>
      ${url ? `<button class="btn sm ghost" onclick="setFront('${path}', ''); renderFront()">Remove</button>` : ""}
    </div>
  </div>`;
}

const frontInput = (path, label, ph = "") => `<div class="field"><label>${label}</label><input class="input" value="${esc(frontGet(path))}" placeholder="${esc(ph)}" oninput="setFront('${path}', this.value)"></div>`;

function renderFront() {
  if (!front) return;
  const bullets = key => front[key].map((_, i) => frontInput(`${key}.${i}`, `Point ${i + 1}`)).join("");
  $("front-form").innerHTML = `
    <div class="card">
      <div class="card-head"><h3>Cover page</h3><span class="muted">one large image under the title</span></div>
      ${photoField("cover.photo", "cover image")}
    </div>
    <div class="card">
      <div class="card-head"><h3>The HOD's Desk</h3></div>
      <div class="front-hod">
        <div>${frontInput("hod.name", "Name")}${frontInput("hod.designation", "Designation")}${photoField("hod.photo", "photo")}</div>
        <div class="field"><label>Message <span class="muted">(a new line starts a new paragraph; it is printed to the right of the photo, with the name below the photo)</span></label>
          <textarea class="input" rows="12" oninput="setFront('hod.message', this.value)">${esc(front.hod.message)}</textarea></div>
      </div>
    </div>
    <div class="card">
      <div class="card-head"><h3>Vision &amp; Mission</h3><span class="muted">up to five points each, printed in two columns</span></div>
      <div class="front-cols"><div><h4>Vision</h4>${bullets("vision")}</div><div><h4>Mission</h4>${bullets("mission")}</div></div>
    </div>
    <div class="card">
      <div class="card-head"><h3>Editorial page</h3></div>
      <h4>Faculty advisor</h4>
      <div class="front-person">${frontInput("advisor.name", "Name")}${frontInput("advisor.designation", "Caption", "Faculty Advisor")}${photoField("advisor.photo", "photo")}</div>
      <h4 style="margin-top:14px">Student editors</h4>
      <div class="front-students">${front.students.map((_, i) => `<div class="front-person">
        <strong>Student ${i + 1}</strong>${frontInput(`students.${i}.name`, "Name")}${frontInput(`students.${i}.year`, "Year of study", "e.g. III Year")}${photoField(`students.${i}.photo`, "photo")}</div>`).join("")}</div>
    </div>`;
}

async function uploadFrontPhoto(path, input) {
  const file = input.files[0]; if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  try {
    const res = await fetch(`${API}/api/uploads`, { method: "POST", body: fd, headers: authHeader() });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    setFront(path, data.path); renderFront();
  } catch (e) { toast(e.message, true); }
}

async function saveFront() {
  try { front = await api("PUT", "/api/front-matter", front); renderFront(); toast("Front pages saved"); }
  catch (e) { toast(e.message, true); }
}

// ---- the two fixed layouts: read-only previews of what the Word document will contain
const DEMO_PHOTO = "data:image/svg+xml;utf8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><rect width="400" height="300" fill="#d9d9d9"/><text x="200" y="158" font-family="Arial" font-size="22" text-anchor="middle" fill="#555">Photo</text></svg>');

function renderFixedPreview() {
  if (isFrontPreview()) { renderFrontPreview(); return; }
  const s = sample || {};
  const photo = s.photo_url || DEMO_PHOTO;
  // the text blocks are always left-aligned; only the photo and its caption are ever centred
  const text = () => `${s.badge_tag ? `<div class="fp-badge">${esc(s.badge_tag)}</div>` : ""}
    ${s.title ? `<h4 class="fp-h">${esc(s.title)}</h4>` : ""}
    ${s.author_or_person ? `<div class="fp-sub">By ${esc(s.author_or_person)}</div>` : ""}
    ${s.organization_or_venue ? `<div>${esc(s.organization_or_venue)}${s.event_date ? " · " + esc(s.event_date) : ""}</div>` : ""}
    ${s.description ? `<p>${esc(s.description)}</p>` : ""}
    ${s.evidence_url ? `<a class="fp-link">${esc(s.evidence_url)}</a>` : ""}`;
  const img = (side, cap) => `<div class="fp-img ${side}"><img src="${esc(photo)}" alt="" onerror="this.onerror=null; this.src=DEMO_PHOTO">${cap ? `<div class="fp-cap">${esc(cap)}</div>` : ""}</div>`;
  const note = t => `<div class="fp-note">${t}</div>`;
  let body;
  if (currentLayoutId === "builtin_centered") {
    body = `${note("Story with a photo: photo centred, content below it")}
      <div class="fp-entry fp-centered">${img("center", s.photo_caption)}${text()}</div>
      <hr>${note("Story without a photo: no photo space is left")}
      <div class="fp-entry fp-centered">${text()}</div>`;
  } else {
    body = `${note("First story with a photo: photo on the left, text wrapped")}
      <div class="fp-entry fp-alt">${img("left")}${text()}<div class="fp-clear"></div></div>
      <hr>${note("Second story: photo on the right")}
      <div class="fp-entry fp-alt">${img("right")}${text()}<div class="fp-clear"></div></div>
      <hr>${note("Story without a photo: the text fills the whole width")}
      <div class="fp-entry fp-alt">${text()}</div>
      ${note("Every section starts again with the photo on the left.")}`;
  }
  $("fixed-preview").innerHTML = `<p class="hint">Fixed layout (read-only). Arial Narrow, black text; this is a preview with the example content chosen on the right.</p>${body}`;
}

// ---- front pages preview: the cover, the HOD's Desk and the editorial page as they will print
const DEMO_FRONT = {
  cover: { photo: "demo_images/demo_campus.jpg" },
  hod: { name: "Dr. A. Head", designation: "Head of the Department", photo: "demo_images/demo_award.jpg",
    message: "Dear readers, it is my pleasure to present this issue of IT Chronicles, which captures the achievements of our faculty and students over the past semester.\nOur department continues to grow in research, teaching and industry partnership, and I thank everyone who contributed to this issue." },
  vision: ["To be a centre of excellence in information technology education and research.", "To produce graduates who lead with integrity.", "To build lasting partnerships with industry.", "To advance innovation that serves society.", "To nurture a culture of lifelong learning."],
  mission: ["To deliver quality education through innovative teaching.", "To encourage research and publication.", "To support students through mentoring and training.", "To collaborate with industry and alumni.", "To serve the community through outreach."],
  advisor: { name: "Dr. B. Advisor", designation: "Faculty Advisor", photo: "demo_images/demo_campus.jpg" },
  students: [1, 2, 3, 4].map(i => ({ name: `Student ${i}`, year: ["IV Year", "III Year", "III Year", "II Year"][i - 1], photo: i === 3 ? "" : "demo_images/demo_team.jpg" })),
};

const fpPhoto = p => !p ? "" : p.startsWith("demo_images/") ? p : photoUrl(p);

function renderFrontPreview() {
  const f = front || DEMO_FRONT;
  const sample = [];
  const pick = (key, filled) => { if (filled) return f[key]; sample.push(key); return DEMO_FRONT[key]; };
  const cover = pick("cover", !!(f.cover && f.cover.photo));
  const hod = pick("hod", [f.hod.name, f.hod.message, f.hod.photo].some(v => String(v || "").trim()));
  const vision = pick("vision", f.vision.some(x => x.trim())).filter(x => x.trim());
  const mission = pick("mission", f.mission.some(x => x.trim())).filter(x => x.trim());
  const adv = pick("advisor", [f.advisor.name, f.advisor.photo].some(v => String(v || "").trim()));
  const students = pick("students", f.students.some(s => s.name.trim() || s.photo)).filter(s => s.name.trim() || s.photo);
  const i = issueInfo || {};
  const meta = [i.volume ? `Vol. ${i.volume} Issue ${i.issue}` : "", i.academic_year, i.semester, i.publication_period].filter(Boolean).join(" · ");
  const sub = [i.department_name, i.cover_title].filter(Boolean).join(" · ");
  const photo = (p, style = "") => fpPhoto(p) ? `<img class="fp-frame" style="${style}" src="${esc(fpPhoto(p))}" alt="" onerror="this.onerror=null; this.src=DEMO_PHOTO">` : "";
  const person = (p, name, cap, w) => `<div class="fp-person">${photo(p, `width:${w}px`)}
    ${name ? `<div class="fp-name">${esc(name)}</div>` : ""}${cap ? `<div class="fp-cap">${esc(cap)}</div>` : ""}</div>`;
  const nameplate = `<div class="fp-nameplate"><div class="np-title">IT CHRONICLES</div>${sub ? `<div>${esc(sub)}</div>` : ""}${meta ? `<div>${esc(meta)}</div>` : ""}</div>`;
  const used = { front_cover: ["cover"], front_hod: ["hod", "vision", "mission"], front_editorial: ["advisor", "students"] }[currentLayoutId];
  const shown = sample.filter(k => used.includes(k));
  const note = shown.length ? `<div class="fp-note">Sample content is shown for: ${shown.join(", ")}. Fill these in on the Front pages tab.</div>` : "";

  let body;
  if (currentLayoutId === "front_cover") {
    body = `${nameplate}<div class="fp-cover">${photo(cover.photo, "width:100%")}</div>`;
  } else if (currentLayoutId === "front_hod") {
    const paras = hod.message.split("\n").map(m => m.trim()).filter(Boolean);
    const msg = paras.map(p => `<p>${esc(p)}</p>`).join("");
    body = `${hod.photo || hod.name || paras.length ? `<h3 class="fp-bar">THE HOD'S DESK</h3>` : ""}
      ${hod.photo ? `<div class="fp-hodrow"><div class="fp-hodleft">${person(hod.photo, hod.name, hod.designation, 170)}</div><div class="fp-hodmsg">${msg}</div></div>`
        : `${msg}${hod.name ? `<div class="fp-sign"><b>${esc(hod.name)}</b><br>${esc(hod.designation)}</div>` : ""}`}
      ${(vision.length || mission.length) ? `<div class="fp-panels">${[["Vision", vision], ["Mission", mission]].filter(([, pts]) => pts.length).map(([t, pts]) =>
        `<div class="fp-panel"><h5>${t}</h5><ul>${pts.map(p => `<li>${esc(p)}</li>`).join("")}</ul></div>`).join("")}</div>` : ""}`;
  } else {
    body = `<h3 class="fp-band">EDITORIAL BOARD</h3>
      ${(adv.name || adv.photo) ? `<div class="fp-adv">${person(adv.photo, adv.name, adv.designation, 150)}</div>` : ""}
      ${students.length ? `<h5 class="fp-rule">Student Editors</h5><div class="fp-students">${students.map(s => person(s.photo, s.name, s.year, 105)).join("")}</div>` : ""}`;
  }
  $("fixed-preview").innerHTML = `<p class="hint">Preview of this page in the Word document. It uses the content from the Front pages tab, even before you save it.</p>${note}${body}`;
}
