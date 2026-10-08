const API_BASE = "";

let sectionsData = [];
let entriesData = [];

document.addEventListener("DOMContentLoaded", () => {
  initApp();
});

async function initApp() {
  await loadSections();
  await loadEntries();
  await loadAuditLogs();
  await loadFormMappings();
  updateFormQuestions();
}

function switchTab(tabId) {
  document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));
  
  document.getElementById(tabId).classList.add("active");
  event.target.classList.add("active");
}

async function loadSections() {
  try {
    const res = await fetch(`${API_BASE}/api/sections`);
    sectionsData = await res.json();
    
    // Populate Dashboard table
    const tbody = document.querySelector("#dashboard-sections-table tbody");
    tbody.innerHTML = "";
    
    // Populate Filter dropdowns
    const secSelect = document.getElementById("filter-section");
    const genSelect = document.getElementById("gen-section-id");
    secSelect.innerHTML = '<option value="">All Sections</option>';
    genSelect.innerHTML = '';
    
    const masterSecBox = document.getElementById("master-sections-selector");
    masterSecBox.innerHTML = '';

    sectionsData.forEach(sec => {
      // Dashboard row
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${sec.name}</strong></td>
        <td>${sec.subcategories.map(c => c.name).join(", ")}</td>
        <td><span class="status-tag Approved">Active</span></td>
        <td id="sec-total-${sec.section_id}">0</td>
        <td id="sec-appr-${sec.section_id}">0</td>
      `;
      tbody.appendChild(tr);

      // Filters
      secSelect.innerHTML += `<option value="${sec.section_id}">${sec.name}</option>`;
      genSelect.innerHTML += `<option value="${sec.section_id}">${sec.name}</option>`;

      // Master checkboxes
      masterSecBox.innerHTML += `
        <div class="form-group" style="display:flex; align-items:center; gap:0.5rem;">
          <input type="checkbox" id="m-sec-${sec.section_id}" value="${sec.section_id}" checked>
          <label for="m-sec-${sec.section_id}" style="margin:0;">${sec.name}</label>
        </div>
      `;
    });
  } catch (err) {
    console.error("Failed to load sections", err);
  }
}

async function loadEntries() {
  const secFilter = document.getElementById("filter-section").value;
  const statusFilter = document.getElementById("filter-status").value;

  let url = `${API_BASE}/api/entries?`;
  if (secFilter) url += `section_id=${secFilter}&`;
  if (statusFilter) url += `approval_status=${statusFilter}&`;

  try {
    const res = await fetch(url);
    entriesData = await res.json();
    renderEntriesTable(entriesData);
    updateStats(entriesData);
  } catch (err) {
    console.error("Failed to load entries", err);
  }
}

function updateStats(entries) {
  document.getElementById("stat-total-entries").innerText = entries.length;
  const approved = entries.filter(e => e.approval_status === "Approved").length;
  const pending = entries.filter(e => e.approval_status === "Draft" || e.approval_status === "Reviewed").length;
  const featured = entries.filter(e => e.featured_flag).length;

  document.getElementById("stat-approved-entries").innerText = approved;
  document.getElementById("stat-pending-entries").innerText = pending;
  document.getElementById("stat-featured-entries").innerText = featured;
}

function renderEntriesTable(entries) {
  const tbody = document.querySelector("#entries-table tbody");
  tbody.innerHTML = "";

  if (entries.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#94a3b8;">No canonical entries found. Ingest form data or upload CSV.</td></tr>`;
    return;
  }

  entries.forEach(e => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>
        <div style="font-weight:700; color:#1f4e78;">${e.entry_id}</div>
        <div style="font-size:0.75rem; color:#64748b;">${e.category_id}</div>
      </td>
      <td>
        <div style="font-weight:600;">${e.title}</div>
        <div style="font-size:0.8rem; color:#475569;">By: ${e.author_or_person}</div>
      </td>
      <td>
        <div>${e.organization_or_venue || '-'}</div>
        <div style="font-size:0.75rem; color:#64748b;">${e.event_date}</div>
      </td>
      <td>
        <div style="max-width:250px; font-size:0.8rem;">${e.description}</div>
        ${e.evidence_url ? `<a href="${e.evidence_url}" target="_blank" style="font-size:0.75rem;">Link</a>` : ''}
      </td>
      <td>
        <button class="action-btn btn-star" onclick="toggleFeatured('${e.entry_id}', ${!e.featured_flag})">
          ${e.featured_flag ? '★ Featured' : '☆ Feature'}
        </button>
      </td>
      <td><span class="status-tag ${e.approval_status}">${e.approval_status}</span></td>
      <td>
        <button class="action-btn btn-approve" onclick="updateStatus('${e.entry_id}', 'Approved')">Approve</button>
        <button class="action-btn btn-reject" onclick="updateStatus('${e.entry_id}', 'Rejected')">Reject</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

async function updateStatus(entryId, newStatus) {
  let reason = null;
  if (newStatus === "Rejected") {
    reason = prompt("Enter rejection reason:");
    if (reason === null) return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/entries/${entryId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        approval_status: newStatus,
        rejection_reason: reason
      })
    });
    if (res.ok) {
      await loadEntries();
    }
  } catch (err) {
    alert("Failed to update status");
  }
}

async function toggleFeatured(entryId, isFeatured) {
  try {
    const current = entriesData.find(e => e.entry_id === entryId);
    if (!current) return;
    const res = await fetch(`${API_BASE}/api/entries/${entryId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        approval_status: current.approval_status,
        featured_flag: isFeatured
      })
    });
    if (res.ok) await loadEntries();
  } catch (err) {
    alert("Failed to toggle featured status");
  }
}

// Ingestion Tab
const formSpecs = {
  form_research: [
    { label: "Research Subcategory", key: "Research Subcategory", type: "select", options: ["Journal Publications", "Conference Publications", "Book / Book Chapters", "Funded Research Projects", "Consultancy Projects", "Patents & Intellectual Property", "Key Research Innovations & Technical Accomplishments"] },
    { label: "Title of Publication / Patent / Project", key: "Title of Publication / Patent / Project / Innovation", type: "text", req: true },
    { label: "Authors / Team Members", key: "Authors / Investigators / Team Members", type: "text", req: true },
    { label: "Venue / Publisher / Agency", key: "Venue / Journal / Publisher / Funding Agency / Organization", type: "text" },
    { label: "Date", key: "Date of Publication / Award / Grant", type: "text" },
    { label: "Impact Factor / Indexing", key: "Impact Factor / Indexing (e.g., Scopus, Web of Science, IEEE, Q1/Q2)", type: "text" },
    { label: "DOI / Patent / Grant Amount", key: "DOI / Patent Number / Grant Amount / URL Link", type: "text" },
    { label: "Abstract / Highlights", key: "Abstract / Executive Summary / Highlights", type: "textarea", req: true },
    { label: "Photo Link", key: "Photo Link (Google Drive / Cloud URL)", type: "text" },
    { label: "Evidence Link", key: "Evidence / Certificate Link (Google Drive / Document URL)", type: "text" }
  ],
  form_faculty: [
    { label: "Achievement Category", key: "Achievement Category", type: "select", options: ["Awards & Honors Received", "Certifications & Upskilling Completed", "Invited Keynote / Expert Lectures Delivered", "Resource Person / Session Chair Roles", "FDP / Workshops Attended", "Professional Body & Editorial Board Roles"] },
    { label: "Faculty Name", key: "Faculty Full Name", type: "text", req: true },
    { label: "Title of Award / Keynote / Workshop", key: "Title of Award / Certification / Keynote / Workshop", type: "text", req: true },
    { label: "Host Institution / Organization", key: "Organization / Host Institution / Awarding Body", type: "text" },
    { label: "Date", key: "Date of Event / Award / Completion", type: "text" },
    { label: "Level (International/National)", key: "Level (International / National / State / University)", type: "text" },
    { label: "Description & Highlights", key: "Description & Key Highlights", type: "textarea", req: true }
  ],
  form_student: [
    { label: "Student Category", key: "Student Achievement Category", type: "select", options: ["Academic Excellence & Ranks", "Hackathons & Coding Competitions", "Higher Education & Top Placements", "Technical Projects & Innovations", "Sports, Cultural & Co-Curricular Accomplishments"] },
    { label: "Student Name(s)", key: "Student Name(s)", type: "text", req: true },
    { label: "Competition / Project Title", key: "Name of Competition / Award / Project / Event", type: "text", req: true },
    { label: "Organizing Body", key: "Organizing Institute / Company / Body", type: "text" },
    { label: "Position / Prize / CTC", key: "Position / Rank / Prize / CTC (e.g. 1st Place, Cash Prize of $1000)", type: "text" },
    { label: "Date", key: "Date of Event / Award", type: "text" },
    { label: "Abstract / Details", key: "Project Abstract / Achievement Details", type: "textarea", req: true }
  ],
  form_industry: [
    { label: "Outreach Category", key: "Outreach Category", type: "select", options: ["Industrial Visits & Field Tours", "Industry Expert Lectures & Technical Talks", "MoUs Signed & Industrial Collaborations", "Alumni Interactions & Mentorship Sessions", "Community & Social Outreach Initiatives"] },
    { label: "Coordinator Name", key: "Coordinator / Faculty Name", type: "text", req: true },
    { label: "Event Title", key: "Title of Event / Visit / MoU Partner", type: "text", req: true },
    { label: "Company / Organization Details", key: "Company / Organization / Alumni Details", type: "text" },
    { label: "Date", key: "Date of Event / Execution", type: "text" },
    { label: "Executive Summary", key: "Executive Summary & Outcomes", type: "textarea", req: true }
  ],
  form_departmental: [
    { label: "Highlight Category", key: "Department Highlight Category", type: "select", options: ["Workshops & FDPs Organized", "Conferences & Symposia Organized", "Infrastructure & Lab Upgrades", "Student Club & Society Activities", "Department Statistics & Major Milestones"] },
    { label: "Convener Name", key: "Convener / Coordinator Name", type: "text", req: true },
    { label: "Event / Milestone Title", key: "Title of Event / Upgrade / Milestone", type: "text", req: true },
    { label: "Dates", key: "Dates & Duration", type: "text" },
    { label: "Event Overview", key: "Event Overview & Highlights", type: "textarea", req: true }
  ]
};

function updateFormQuestions() {
  const formId = document.getElementById("ingest-form-id").value;
  const spec = formSpecs[formId] || [];
  const container = document.getElementById("dynamic-form-fields");
  container.innerHTML = "";

  spec.forEach(f => {
    const group = document.createElement("div");
    group.className = "form-group";

    let inputHtml = "";
    if (f.type === "select") {
      inputHtml = `<select name="${f.key}" class="form-control">${f.options.map(o => `<option value="${o}">${o}</option>`).join("")}</select>`;
    } else if (f.type === "textarea") {
      inputHtml = `<textarea name="${f.key}" class="form-control" rows="3" ${f.req ? 'required' : ''}></textarea>`;
    } else {
      inputHtml = `<input type="text" name="${f.key}" class="form-control" ${f.req ? 'required' : ''}>`;
    }

    group.innerHTML = `<label>${f.label} ${f.req ? '*' : ''}</label>${inputHtml}`;
    container.appendChild(group);
  });
}

async function handleSingleIngest(event) {
  event.preventDefault();
  const formId = document.getElementById("ingest-form-id").value;
  const formData = new FormData(event.target);
  const rawData = {};
  formData.forEach((val, key) => rawData[key] = val);

  try {
    const res = await fetch(`${API_BASE}/api/entries/ingest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        form_id: formId,
        raw_data: rawData
      })
    });
    const result = await res.json();
    alert(`Entry successfully ingested! Assigned ID: ${result.entry_id}`);
    event.target.reset();
    updateFormQuestions();
    await loadEntries();
  } catch (err) {
    alert("Ingestion failed");
  }
}

async function handleCsvIngest(event) {
  event.preventDefault();
  const formId = document.getElementById("csv-form-id").value;
  const fileInput = document.getElementById("csv-file-input");
  
  if (!fileInput.files[0]) return;

  const bodyData = new FormData();
  bodyData.append("form_id", formId);
  bodyData.append("file", fileInput.files[0]);

  try {
    const res = await fetch(`${API_BASE}/api/entries/ingest-csv`, {
      method: "POST",
      body: bodyData
    });
    const data = await res.json();
    
    const box = document.getElementById("csv-result-box");
    box.classList.remove("hidden");
    box.innerHTML = `<strong>Batch Ingestion Complete:</strong> Ingested ${data.total_ingested} entries from CSV file.`;
    await loadEntries();
  } catch (err) {
    alert("CSV batch ingestion failed");
  }
}

// Section Generation
async function generateSectionDocx() {
  const sectionId = document.getElementById("gen-section-id").value;
  try {
    const res = await fetch(`${API_BASE}/api/generate/section/${sectionId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section_id: sectionId })
    });
    const result = await res.json();

    const box = document.getElementById("section-gen-result");
    box.classList.remove("hidden");
    box.innerHTML = `
      <strong>Section DOCX Generated Successfully!</strong><br>
      Total Approved Entries Included: ${result.total_entries}<br>
      <a href="${API_BASE}/api/downloads/${result.filename}" class="btn btn-success" style="display:inline-block; margin-top:0.5rem; text-decoration:none;">⬇️ Download ${result.filename}</a>
    `;
    await loadAuditLogs();
  } catch (err) {
    alert("Section generation failed");
  }
}

// Master Assembly
async function assembleMasterNewsletter() {
  const selectedSections = [];
  sectionsData.forEach(sec => {
    const chk = document.getElementById(`m-sec-${sec.section_id}`);
    if (chk && chk.checked) selectedSections.push(sec.section_id);
  });

  try {
    const res = await fetch(`${API_BASE}/api/generate/master`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selected_section_ids: selectedSections
      })
    });
    const result = await res.json();

    const box = document.getElementById("master-gen-result");
    box.classList.remove("hidden");
    box.innerHTML = `
      <strong>Master Newsletter Assembled Successfully!</strong><br>
      Sections Included: ${result.total_sections_included} | Total Entries: ${result.total_entries_included}<br>
      <a href="${API_BASE}/api/downloads/${result.filename}" class="btn btn-success btn-large" style="display:inline-block; margin-top:0.75rem; text-decoration:none;">⬇️ Download Master ${result.filename}</a>
    `;
    await loadAuditLogs();
  } catch (err) {
    alert("Master newsletter assembly failed");
  }
}

// Admin Tab
async function loadFormMappings() {
  try {
    const res = await fetch(`${API_BASE}/api/config/mappings`);
    const data = await res.json();
    document.getElementById("admin-mappings-json").innerText = JSON.stringify(data, null, 2);
  } catch (err) {
    console.error("Failed to load mappings");
  }
}

async function loadAuditLogs() {
  try {
    const res = await fetch(`${API_BASE}/api/audit-logs`);
    const logs = await res.json();
    const box = document.getElementById("admin-audit-logs");
    box.innerHTML = logs.map(l => `
      <div class="log-item">
        <span class="log-time">${new Date(l.timestamp).toLocaleTimeString()}</span>
        <strong>[${l.action}]</strong> ${l.details || ''}
      </div>
    `).join("");
  } catch (err) {
    console.error("Failed to load audit logs");
  }
}
