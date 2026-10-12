const API = "";

// ---------------------------------------------------------------- state
let sections = [];
let entries = [];
let forms = [];
let canonicalTags = [];
let savedLayouts = [];
let auditLogs = [];
let sectionLayouts = {};   // section_id -> layout template_id

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

async function api(method, url, body) {
  const opts = { method, headers: {} };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const res = await fetch(API + url, opts);
  let data = null;
  try { data = await res.json(); } catch (e) { /* non-json */ }
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
  document.querySelectorAll("#main-tabs .tab").forEach(b => b.addEventListener("click", () => switchTab(b.dataset.tab)));
  try {
    [canonicalTags, sections, forms, entries, savedLayouts, auditLogs, sectionLayouts] = await Promise.all([
      api("GET", "/api/forms/canonical-tags"), api("GET", "/api/sections"), api("GET", "/api/forms"),
      api("GET", "/api/entries"), api("GET", "/api/visual-templates"), api("GET", "/api/audit-logs"),
      api("GET", "/api/section-layouts")
    ]);
  } catch (e) { toast("Could not reach the server: " + e.message, true); }
  currentFormId = forms[0]?.form_id || null;
  api("GET", "/api/issues").then(list => {
    const i = list[0];
    if (i) {
      $("issue-chip").textContent = `${i.academic_year} · Vol ${i.volume} No ${i.issue}`;
      $("paper-vol").textContent = `VOL. ${i.volume} · ISSUE ${i.issue}`;
    }
  }).catch(() => {});
  renderOverview();
  renderFormsView();
  renderResponses();
  renderPublish();
}

async function switchTab(tab) {
  await flushPendingSave();
  document.querySelectorAll("#main-tabs .tab").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === "tab-" + tab));
  if (tab === "layout") initLayoutView();
  if (tab === "overview") renderOverview();
  if (tab === "publish") renderPublish();
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
          <textarea id="add-q-text" class="input" rows="2" placeholder="Type a question, or paste the whole header row from your responses sheet"></textarea>
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
    await api("POST", `/api/forms/${form.form_id}/columns/bulk`, { headers_text: text });
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
const BLOCK_TYPES = {
  image:    { label: "Photo",         ico: "▣", tag: "photo_url", style: { aspectRatio: "16:9", float: "none" } },
  headline: { label: "Headline",      ico: "H", tag: "title", style: { textAlign: "left" } },
  byline:   { label: "Authors",       ico: "By", tag: "author_or_person", style: {} },
  meta:     { label: "Venue & date",  ico: "Vn", tag: "organization_or_venue", style: {} },
  badge:    { label: "Badge",         ico: "◖◗", tag: "badge_tag", style: { badgeColor: "navy" } },
  text:     { label: "Description",   ico: "¶", tag: "description", style: { textAlign: "left" } },
  link:     { label: "Button link",   ico: "↗", tag: "evidence_url", style: { buttonStyle: "solid" }, linkText: "View details" },
  stats:    { label: "Stat callout",  ico: "#", tag: "grant_or_prize_amount", style: {} },
  divider:  { label: "Divider",       ico: "—", tag: "", style: {} }
};

const DEFAULT_LAYOUT = () => [
  mkBlock("badge"), mkBlock("headline"), mkBlock("byline"), mkBlock("image"), mkBlock("text"), mkBlock("link")
];

function mkBlock(type) {
  const t = BLOCK_TYPES[type];
  const b = { id: "b" + Date.now().toString(36) + Math.random().toString(36).slice(2, 5), type, label: t.label, tag: t.tag, style: { ...t.style } };
  if (type === "image") b.captionTag = "photo_caption";
  if (t.linkText) b.linkText = t.linkText;
  return b;
}

function initLayoutView() {
  if (!$("palette-items").children.length) {
    $("palette-items").innerHTML = Object.entries(BLOCK_TYPES).map(([k, t]) =>
      `<button class="pal-item" draggable="true" data-type="${k}"><span class="pal-ico">${t.ico}</span>${t.label}</button>`).join("");
    $("palette-items").querySelectorAll(".pal-item").forEach(p => {
      p.addEventListener("click", () => addBlock(p.dataset.type));
      p.addEventListener("dragstart", e => { dragSrc = { kind: "new", type: p.dataset.type }; e.dataTransfer.setData("text/plain", p.dataset.type); e.dataTransfer.effectAllowed = "copy"; });
      p.addEventListener("dragend", clearDrag);
    });
    wireCanvasDnD();
  }
  $("lay-form").innerHTML = forms.map(f => `<option value="${f.form_id}" ${f.form_id === currentFormId ? "selected" : ""}>${esc(f.form_name.replace(/^IT Chronicles\s*[-–]\s*/, ""))}</option>`).join("");
  fillLayoutSelect(currentLayoutId);
  if (!layoutLoaded) { layoutLoaded = true; onSavedLayoutChange(); }
}

// The form is only used for example content and the field list; the layout itself belongs to no section.
async function onLayoutFormChange() {
  await flushPendingSave();
  currentFormId = $("lay-form").value;
  renderFormsList();
  renderSampleOptions();
  renderCanvas();
  renderInspector();
}

function fillLayoutSelect(selectId) {
  $("lay-saved").innerHTML = `<option value="">New layout</option>` +
    savedLayouts.map(t => `<option value="${esc(t.template_id)}">${esc(t.name)}</option>`).join("");
  $("lay-saved").value = savedLayouts.some(t => t.template_id === selectId) ? selectId : "";
}

// Presets store headline / byline / venue as generic text blocks; give them their proper role
const TEXT_ROLE = { title: "headline", author_or_person: "byline", organization_or_venue: "meta" };
const normalizeLayout = blocks => blocks.map(b => b.type === "text" && TEXT_ROLE[b.tag] ? { ...b, type: TEXT_ROLE[b.tag] } : b);

function onSavedLayoutChange() {
  currentLayoutId = $("lay-saved").value;
  const tpl = savedLayouts.find(t => t.template_id === currentLayoutId);
  layout = tpl && tpl.layout?.length ? normalizeLayout(JSON.parse(JSON.stringify(tpl.layout))) : DEFAULT_LAYOUT();
  $("lay-name").value = tpl ? tpl.name : "New layout";
  selectedBlockId = null;
  renderSampleOptions();
  renderCanvas();
  renderInspector();
}

function resetLayout() { onSavedLayoutChange(); toast("Layout reset"); }

function togglePreviewMode() {
  const on = $("lay-preview").checked;
  $("paper").classList.toggle("preview", on);
  $("paper").querySelectorAll(".cb").forEach(c => c.draggable = !on);
}

// ---- sample data
function demoSample() {
  const f = curForm();
  return JSON.parse(JSON.stringify(SAMPLE_DATA[f?.form_id] || SAMPLE_DATA[Object.keys(SAMPLE_DATA).find(k => f?.section_id && k.includes(f.section_id.replace("sec_", "")))] || SAMPLE_DATA.form_research));
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

// ---- field options for a block
function fieldOptionsHtml(selTag) {
  const form = curForm();
  const seen = new Set();
  let mine = "";
  (form?.columns || []).forEach(c => {
    const t = c.canonical_tag;
    if (!t || t === "custom" || INTERNAL_TAGS.includes(t) || seen.has(t)) return;
    seen.add(t);
    mine += `<option value="${esc(t)}" ${t === selTag ? "selected" : ""}>${esc(isKnownTag(t) ? tagLabel(t) : c.name)}</option>`;
  });
  const others = SHOWN_TAGS.filter(t => !seen.has(t)).map(t => `<option value="${t}" ${t === selTag ? "selected" : ""}>${tagLabel(t)}</option>`).join("");
  return `${mine ? `<optgroup label="From this form">${mine}</optgroup>` : ""}${others ? `<optgroup label="Not asked by this form">${others}</optgroup>` : ""}`;
}

// ---- rendering
const ph = txt => `<span class="ph">${esc(txt)}</span>`;

// Font settings carried by preset layouts (the palette's own blocks rely on defaults)
function fontCss(st) {
  let css = "";
  if (st.fontSize) css += `font-size:${esc(st.fontSize)};`;
  if (st.fontWeight) css += `font-weight:${esc(st.fontWeight)};`;
  if (/^#[0-9a-f]{6}$/i.test(st.textColor || "")) css += `color:${st.textColor};`;
  return css;
}

function blockHtml(b, d) {
  const v = d[b.tag];
  const st = b.style || {};
  switch (b.type) {
    case "badge": return `<span class="nl-badge ${esc(st.badgeColor || "navy")}">${v ? esc(v) : ph("Badge")}</span>`;
    case "headline": return `<div class="nl-h" style="text-align:${esc(st.textAlign || "left")};${fontCss(st)}">${v ? esc(v) : ph("Headline")}</div>`;
    case "byline": return `<div class="nl-by" style="${fontCss(st)}">By ${v ? esc(v) : ph("authors")}</div>`;
    case "meta": return `<div class="nl-meta" style="${fontCss(st)}">${v ? esc(v) : ph("Venue")}${d.event_date ? " · " + esc(d.event_date) : ""}</div>`;
    case "text": return `<p class="nl-p" style="text-align:${esc(st.textAlign || "left")};${fontCss(st)}">${v ? esc(v) : ph("Description appears here…")}</p>`;
    case "link": return `<span class="nl-btn ${esc(st.buttonStyle || "solid")}">${esc(b.linkText || "View details")}</span>`;
    case "stats": return `<div class="nl-stat"><b>${v ? esc(v) : ph("Value")}</b><span>${esc(d.badge_tag || "")}</span></div>`;
    case "divider": return `<div class="nl-hr"></div>`;
    case "image": {
      const ratio = { "1:1": "1/1", "4:3": "4/3", "16:9": "16/9" }[st.aspectRatio] || "16/9";
      const cap = d[b.captionTag] || d.photo_caption;
      const float = st.float === "left";
      return `<div class="nl-img" style="${float ? "float:left; width:220px; margin:0 16px 8px 0;" : ""}">
        ${v ? `<img src="${esc(v)}" alt="" draggable="false" style="aspect-ratio:${ratio}" onerror="this.style.visibility='hidden'">` : `<div style="aspect-ratio:${ratio}; display:grid; place-items:center">${ph("Photo")}</div>`}
        ${cap ? `<div class="nl-cap">${esc(cap)}</div>` : ""}</div>`;
    }
  }
  return "";
}

function renderCanvas() {
  const f = curForm();
  const sec = sections.find(s => s.section_id === f?.section_id);
  $("paper-title").textContent = "IT CHRONICLES" + (sec ? " · " + sec.name.toUpperCase() : "");
  const preview = $("lay-preview").checked;
  $("canvas-blocks").innerHTML = layout.map(b => `
    <div class="cb ${b.id === selectedBlockId ? "sel" : ""}" data-id="${b.id}" draggable="${!preview}">
      <div class="cb-tools">
        <button title="Move up" data-act="up">▲</button><button title="Move down" data-act="down">▼</button>
        <button title="Duplicate" data-act="dup">⧉</button><button title="Remove" data-act="del">✕</button>
      </div>
      ${blockHtml(b, sample)}
    </div>`).join("");
  $("paper").classList.toggle("preview", preview);
}

function wireCanvasDnD() {
  const blocks = $("canvas-blocks");
  const area = $("canvas-area");

  blocks.addEventListener("click", e => {
    const tool = e.target.closest("[data-act]");
    const cb = e.target.closest(".cb");
    if (!cb) return;
    const idx = layout.findIndex(b => b.id === cb.dataset.id);
    if (tool) {
      e.stopPropagation();
      const act = tool.dataset.act;
      if (act === "up" && idx > 0) [layout[idx - 1], layout[idx]] = [layout[idx], layout[idx - 1]];
      else if (act === "down" && idx < layout.length - 1) [layout[idx + 1], layout[idx]] = [layout[idx], layout[idx + 1]];
      else if (act === "dup") { const c = JSON.parse(JSON.stringify(layout[idx])); c.id = mkBlock("divider").id; layout.splice(idx + 1, 0, c); selectedBlockId = c.id; }
      else if (act === "del") { layout.splice(idx, 1); if (selectedBlockId === cb.dataset.id) selectedBlockId = null; }
      renderCanvas(); renderInspector();
      return;
    }
    if ($("lay-preview").checked) return;
    selectedBlockId = cb.dataset.id;
    renderCanvas(); renderInspector();
  });

  area.addEventListener("click", e => {
    if (!e.target.closest(".cb") && selectedBlockId) { selectedBlockId = null; renderCanvas(); renderInspector(); }
  });

  blocks.addEventListener("dragstart", e => {
    const cb = e.target.closest(".cb");
    if (!cb) return;
    dragSrc = { kind: "move", id: cb.dataset.id };
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", cb.dataset.id);
    setTimeout(() => cb.classList.add("dragging"), 0);
  });
  blocks.addEventListener("dragend", clearDrag);

  area.addEventListener("dragover", e => {
    if (!dragSrc) return;
    e.preventDefault();
    markDropTarget(dropIndex(e.clientY));
  });
  area.addEventListener("drop", e => {
    if (!dragSrc) return;
    e.preventDefault();
    let idx = dropIndex(e.clientY);
    if (dragSrc.kind === "move") {
      const from = layout.findIndex(b => b.id === dragSrc.id);
      if (from >= 0) {
        const [b] = layout.splice(from, 1);
        if (from < idx) idx--;
        layout.splice(idx, 0, b);
      }
    } else {
      const b = mkBlock(dragSrc.type);
      layout.splice(idx, 0, b);
      selectedBlockId = b.id;
    }
    clearDrag();
    renderCanvas(); renderInspector();
  });
}

function dropIndex(y) {
  const kids = [...$("canvas-blocks").children];
  let idx = 0;
  kids.forEach((k, i) => { const r = k.getBoundingClientRect(); if (y > r.top + r.height / 2) idx = i + 1; });
  return idx;
}
function markDropTarget(idx) {
  const kids = [...$("canvas-blocks").children];
  kids.forEach(k => k.classList.remove("drop-before", "drop-after"));
  if (!kids.length) return;
  if (idx < kids.length) kids[idx].classList.add("drop-before"); else kids[kids.length - 1].classList.add("drop-after");
}
function clearDrag() {
  dragSrc = null;
  $("canvas-blocks").querySelectorAll(".cb").forEach(k => k.classList.remove("dragging", "drop-before", "drop-after"));
}

function addBlock(type) {
  const b = mkBlock(type);
  const at = selectedBlockId ? layout.findIndex(x => x.id === selectedBlockId) + 1 : layout.length;
  layout.splice(at, 0, b);
  selectedBlockId = b.id;
  renderCanvas(); renderInspector();
}

// ---- inspector
function segHtml(key, current, options) {
  return `<div class="seg">${options.map(([v, l]) => `<button class="${(current ?? options[0][0]) === v ? "on" : ""}" onclick="setStyle('${key}','${v}')">${l}</button>`).join("")}</div>`;
}
function setStyle(key, val) {
  const b = layout.find(x => x.id === selectedBlockId); if (!b) return;
  b.style = b.style || {};
  b.style[key] = val;
  renderCanvas(); renderInspector();
}
function setBlockTag(tag) {
  const b = layout.find(x => x.id === selectedBlockId); if (!b) return;
  b.tag = tag;
  renderCanvas();
}
function setLinkText(v) {
  const b = layout.find(x => x.id === selectedBlockId); if (!b) return;
  b.linkText = v;
  renderCanvas();
}

function renderInspector() {
  const el = $("inspector-element");
  const b = layout.find(x => x.id === selectedBlockId);
  if (!b) {
    el.innerHTML = `<div class="insp-head"><h3>Page</h3></div><p class="insp-empty">Click any element on the page to change what it shows and how it looks.</p>`;
    return;
  }
  const st = b.style || {};
  let opts = "";
  if (b.type === "image") opts = `
    <div class="field"><label>Shape</label>${segHtml("aspectRatio", st.aspectRatio, [["16:9", "Wide"], ["4:3", "Photo"], ["1:1", "Square"]])}</div>
    <div class="field"><label>Placement</label>${segHtml("float", st.float, [["none", "Full width"], ["left", "Beside text"]])}</div>`;
  if (b.type === "headline" || b.type === "text") opts = `<div class="field"><label>Alignment</label>${segHtml("textAlign", st.textAlign, [["left", "Left"], ["center", "Centre"]])}</div>`;
  if (b.type === "badge") opts = `<div class="field"><label>Colour</label>${segHtml("badgeColor", st.badgeColor, [["navy", "Navy"], ["amber", "Amber"], ["slate", "Slate"], ["green", "Green"]])}</div>`;
  if (b.type === "link") opts = `
    <div class="field"><label>Button text</label><input class="input" value="${esc(b.linkText || "")}" oninput="setLinkText(this.value)"></div>
    <div class="field"><label>Style</label>${segHtml("buttonStyle", st.buttonStyle, [["solid", "Solid"], ["accent", "Accent"], ["outline", "Outline"]])}</div>`;

  el.innerHTML = `
    <div class="insp-head"><h3>${esc(BLOCK_TYPES[b.type]?.label || b.type)}</h3></div>
    ${b.type === "divider" ? `<p class="insp-empty">A thin line between parts of the article.</p>` : `
      <div class="field"><label>Shows</label>
        <select class="input" onchange="setBlockTag(this.value)">${fieldOptionsHtml(b.tag)}</select>
      </div>`}
    ${opts}`;
}

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
function renderResponses() {
  const secSel = $("filter-section");
  const prevSec = secSel.value;
  secSel.innerHTML = `<option value="">All sections</option>` + sections.map(s => `<option value="${s.section_id}">${esc(s.name)}</option>`).join("");
  secSel.value = sections.some(s => s.section_id === prevSec) ? prevSec : "";

  const inSec = entries.filter(e => !secSel.value || e.section_id === secSel.value);
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
  const rows = sections.map(s => {
    const own = entries.filter(e => e.section_id === s.section_id);
    const appr = own.filter(e => e.approval_status === "Approved").length;
    const chosen = savedLayouts.some(t => t.template_id === sectionLayouts[s.section_id]) ? sectionLayouts[s.section_id] : "";
    return `
      <div class="pub-row ${appr ? "" : "empty-sec"}">
        <input type="checkbox" id="pub-${s.section_id}" value="${s.section_id}" ${appr ? "checked" : ""} ${appr ? "" : "disabled"}>
        <label for="pub-${s.section_id}"><span class="pub-name">${esc(s.name)}</span>
          <span class="muted">${appr ? `${appr} approved` : "Nothing approved yet"}${own.length - appr ? ` · ${own.length - appr} not approved` : ""}</span></label>
        <select class="input compact layout-pick" title="Layout used for this section's entries" onchange="setSectionLayout('${s.section_id}', this.value)">
          <option value="">Default layout</option>
          ${savedLayouts.map(t => `<option value="${esc(t.template_id)}" ${t.template_id === chosen ? "selected" : ""}>${esc(t.name)}</option>`).join("")}
        </select>
        <button class="btn sm" ${appr ? "" : "disabled"} onclick="buildSection('${s.section_id}', this)">Download section</button>
      </div>`;
  });
  $("publish-sections").innerHTML = rows.join("") || `<div class="empty">No sections yet.</div>`;
  $("publish-count").textContent = `${entries.filter(e => e.approval_status === "Approved").length} approved responses`;
}

async function setSectionLayout(sectionId, templateId) {
  try {
    await api("PUT", `/api/section-layouts/${sectionId}`, { template_id: templateId || null });
    if (templateId) sectionLayouts[sectionId] = templateId; else delete sectionLayouts[sectionId];
    toast(templateId ? "Layout applied to this section" : "Using the default layout");
  } catch (e) { toast(e.message, true); renderPublish(); }
}

function triggerDownload(filename) {
  const a = document.createElement("a");
  a.href = `${API}/api/downloads/${encodeURIComponent(filename)}`;
  a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
}

async function buildSection(id, btn) {
  btn.disabled = true; const old = btn.textContent; btn.textContent = "Building…";
  try {
    const r = await api("POST", `/api/generate/section/${id}`, { section_id: id });
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
    const r = await api("POST", "/api/generate/master", { selected_section_ids: chosen });
    box.className = "result";
    box.innerHTML = `${r.total_entries_included} entries from ${r.total_sections_included} sections.<br><a href="${API}/api/downloads/${encodeURIComponent(r.filename)}" download>Download ${esc(r.filename)}</a>`;
    triggerDownload(r.filename);
    api("GET", "/api/audit-logs").then(l => { auditLogs = l; });
  } catch (e) {
    box.className = "result err"; box.textContent = e.message;
  }
  btn.disabled = false; btn.textContent = "Build master document";
}
