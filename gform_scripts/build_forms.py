"""
Single source of truth for the IT Chronicles Google Forms.

Run:  python gform_scripts/build_forms.py

It writes
  gform_scripts/AllFormsCreator.gs         ALL 6 forms in one run (paste into script.google.com, run buildAllForms)
  gform_scripts/MasterFormsCreator.gs      the 5 submission forms only
  gform_scripts/PlacementFormCreator.gs    the student placement form
  config/master_forms.json                 what the master-database importer reads (header -> field)
  config/form_mappings.json                newsletter mappings, MERGED (old headers keep working)

Question fields:  q=title shown on the form / Excel header, type, req, help, choices,
  key = master-DB column (or a _special handler), nl = newsletter canonical field, tf = value transform.
"""
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = os.path.join(ROOT, "config")

LANDMARK = "Is this a Landmark / Milestone Achievement?"
LANDMARK_CHOICES = ["No (Standard Entry)", "Yes (Nominate for Spotlight Feature)"]
LEVELS = ["Department", "College", "Inter-college", "State", "National", "International"]
YES_NO = ["Yes", "No"]


def Q(q, type="text", key=None, req=False, help=None, choices=None, nl=None, tf=None, submitter=False, aliases=None):
    """aliases: earlier titles of this question, so sheets exported from the previous version of the form still import."""
    d = {"q": q, "type": type, "req": req}
    for k, v in (("help", help), ("choices", choices), ("key", key), ("nl", nl), ("tf", tf), ("aliases", aliases)):
        if v:
            d[k] = v
    if submitter:
        d["submitter"] = True
    return d


def S(title):
    return {"q": title, "type": "section"}


def tail(evidence_q="Official Evidence / Certificate / Supporting Document Link", evidence_nl="evidence_url"):
    return [
        S("Media, evidence and consent"),
        Q("Key Impact Badge / Metric", key="badge_tag", nl="badge_tag",
          help="Short badge for the newsletter (e.g. 1st Prize, Scopus Q1, MoU Signed, 150+ Attendees)"),
        Q("Photo Link (Google Drive / Cloud URL)", "url", key="media_url", nl="photo_url",
          help="High-resolution photo. Set sharing to 'Anyone with the link can view'."),
        Q("Photo Caption & Persons in Image", key="photo_caption", nl="photo_caption",
          help="Names of the people shown, left to right"),
        Q(evidence_q, "url", key="evidence_url", nl=evidence_nl),
        Q(LANDMARK, "choice", key="is_landmark", req=True, choices=LANDMARK_CHOICES,
          help="Nominate for the Spotlight / Hero story card in the newsletter"),
        Q("Permission to Publish this Submission", "choice", key="publish_permission", req=True,
          choices=["Yes - may be published in the IT Chronicles newsletter", "No - keep for internal records only"]),
        Q("Accuracy and Authorization Confirmation", "confirm", key="authorization_confirmed", req=True,
          choices=["I confirm the information is accurate and I am authorised to submit it."]),
    ]


FORMS = {}

# ---------------------------------------------------------------- Student achievements
FORMS["form_student"] = {
    "form_type": "STUDENT", "date_key": "result_date",
    "title": "IT Chronicles - Student Achievements Submission Form",
    "description": "Student competitions, hackathons, projects, higher studies and co-curricular achievements. "
                   "Enter roll numbers only: names and class details are filled in from the college records.",
    "questions": [
        S("A. Students"),
        Q("Achievement or Participation", "choice", key="entry_kind", req=True,
          choices=["Achievement (won, ranked or awarded)", "Participation only"],
          help="Choose 'Participation only' when the students took part (an event, workshop, competition, activity) without winning or ranking. "
               "List every participant's roll number below so it appears in their class record."),
        Q("Participants (one roll number per line)", "roster_roll", key="_participants", req=True, nl="author_or_person", tf="names_only",
          aliases=["Participants (one per line: ROLLNO - Student Name)"],
          help="One student per line, roll number only, e.g.\n21IT001\n21IT014\nNames are filled in from the college records."),
        Q("Lead Student Roll Number", "roll", key="_lead_roll", req=True),
        Q("Individual or Team Achievement", "choice", key="is_team", req=True, choices=["Individual", "Team"]),
        S("B. Achievement"),
        Q("Student Achievement Category", "choice", key="category", req=True, nl="category_id", choices=[
            "Academic Excellence & Ranks", "Hackathons & Coding Competitions", "Higher Education & Top Placements",
            "Technical Projects & Innovations", "Sports, Cultural & Co-Curricular Accomplishments"]),
        Q("Name of Competition / Award / Project / Event", key="title", req=True, nl="title"),
        Q("Organizing Institute / Company / Awarding Body", key="organizer", req=True, nl="organization_or_venue"),
        Q("Achievement Level", "choice", key="level", req=True, choices=LEVELS),
        Q("Position / Rank / Prize / Scholarship", key="position", req=True, nl="grant_or_prize_amount",
          help="e.g. 1st Prize, Runner-up, Scholarship. For participation only, type Participated."),
        Q("Prize / Scholarship Amount in Rupees (numbers only, 0 if none)", "number", key="prize_amount"),
        Q("Date of Achievement / Result", "date", key="result_date", req=True, nl="event_date"),
        Q("Event Start Date", "date", key="event_start"),
        Q("Event End Date", "date", key="event_end"),
        Q("Achievement Domain", "list", key="domain", req=True, choices=[
            "AI / Machine Learning", "Web / App Development", "Cyber Security", "IoT / Embedded", "Cloud / DevOps",
            "Data Science / Analytics", "Algorithms / Competitive Coding", "Sports", "Cultural", "Entrepreneurship", "Other"]),
        Q("Faculty Mentor / Project Guide", "faculty", key="mentor_emp_id", req=True),
        S("C. Details"),
        Q("Project Statement / Objective", "para", key="project_statement"),
        Q("Project Abstract / Achievement Details", "para", key="abstract", req=True, nl="description"),
        Q("Tools / Technologies / Methods Used", key="tools_used"),
        Q("Measurable Result or Impact", key="measurable_impact"),
        Q("Project Demo / Repository / Portfolio URL", "url", key="demo_url"),
        Q("Learning Outcomes / Skills Demonstrated", "para", key="learning_outcomes"),
        Q("Has this Work Received Other Awards or Been Reported Previously?", "choice", key="previously_reported", choices=YES_NO),
        Q("Related Awards / Previous Submission Details (type NA if none)", key="related_awards"),
    ] + tail("Certificate / Proof Link"),
}

# ---------------------------------------------------------------- Research & innovation
FORMS["form_research"] = {
    "form_type": "RESEARCH", "date_key": "output_date",
    "title": "IT Chronicles - Research & Innovation Submission Form",
    "description": "Publications, patents, funded projects, consultancy and innovations. Select your name from the list.",
    "questions": [
        S("A. Submitter"),
        Q("Submitting Faculty (select your name)", "faculty", key="_submitter", req=True, submitter=True),
        S("B. Output"),
        Q("Research Subcategory", "choice", key="category", req=True, nl="category_id", choices=[
            "Journal Publications", "Conference Publications", "Book / Book Chapters", "Funded Research Projects",
            "Consultancy Projects", "Patents & Intellectual Property", "Key Research Innovations & Technical Accomplishments"]),
        Q("Title of Publication / Patent / Project / Innovation", key="title", req=True, nl="title"),
        Q("Current Status", "list", key="current_status", req=True, choices=[
            "Published", "Accepted", "Under Review", "Filed", "Granted", "Ongoing", "Completed"]),
        Q("Authors / Investigators (one per line: ID - Name)", "roster_any", key="_contributors", req=True, nl="author_or_person", tf="names_only",
          help="In publication order, first = lead. Use the faculty Employee ID or student Roll No for people of this department, "
               "and EXT for outsiders, e.g.\nEMP012 - Dr. A. Kumar\n21IT001 - Asha K\nEXT - Dr. J. Smith - Anna University"),
        Q("Your Individual Contribution", key="contribution_statement"),
        Q("Collaborating Institutions / Organizations", key="collaborators"),
        S("C. Venue, dates and identifiers"),
        Q("Venue / Journal / Publisher / Funding Agency / Organization", key="venue_publisher", req=True, nl="organization_or_venue"),
        Q("Journal / Conference / Publisher / Funding Agency Website", "url", key="venue_url"),
        Q("Date of Publication / Filing / Award / Grant", "date", key="output_date", req=True, nl="event_date"),
        Q("Project Start Date", "date", key="project_start"),
        Q("DOI / ISBN / ISSN / Patent Number / Grant Reference", key="identifier", nl="grant_or_prize_amount"),
        Q("Indexing", "list", key="indexing", nl="impact_or_indexing", choices=[
            "Scopus", "Web of Science", "IEEE Xplore", "UGC-CARE", "PubMed", "Not indexed", "Not applicable"]),
        Q("Quartile", "list", key="quartile", choices=["Q1", "Q2", "Q3", "Q4", "Not applicable"]),
        Q("Impact Factor (number, leave blank if none)", "number", key="impact_factor"),
        Q("Conference Level", "list", key="conference_level", choices=["Not applicable", "National", "International"]),
        Q("Review Status", "list", key="review_status", choices=["Peer reviewed", "Not reviewed", "Not applicable"]),
        Q("Funding Status", "list", key="funding_status", choices=["Not funded", "Applied", "Funded"]),
        Q("Funding Amount in Rupees (numbers only)", "number", key="funding_amount"),
        S("D. Content"),
        Q("Research Problem / Motivation", "para", key="problem"),
        Q("Abstract / Executive Summary", "para", key="abstract", req=True, nl="description"),
        Q("Methodology / Technical Approach", "para", key="methodology"),
        Q("Key Findings / Novelty / Original Contribution", "para", key="key_findings"),
        Q("Impact, Application and Beneficiaries", "para", key="impact"),
        Q("IP Ownership / Licensing / Commercialization Status", key="ip_status"),
        Q("Dataset / Code / Supplementary Material Link", "url", key="dataset_url"),
        Q("Related Publications / Project References", "para", key="related_refs"),
    ] + tail(),
}

# ---------------------------------------------------------------- Faculty achievements
FORMS["form_faculty"] = {
    "form_type": "FACULTY", "date_key": "start_date",
    "title": "IT Chronicles - Faculty Achievements Submission Form",
    "description": "Awards, certifications, invited lectures, FDPs and professional roles. Select your name from the list.",
    "questions": [
        S("A. Faculty"),
        Q("Faculty Full Name (select your name)", "faculty", key="emp_id", req=True, submitter=True, nl="author_or_person", tf="names_only"),
        Q("Designation at the Time of Achievement", key="designation_at_time"),
        S("B. Achievement"),
        Q("Achievement Category", "choice", key="category", req=True, nl="category_id", choices=[
            "Awards & Honors Received", "Certifications & Upskilling Completed", "Invited Keynote / Expert Lectures Delivered",
            "Resource Person / Session Chair Roles", "FDP / Workshops Attended", "Professional Body & Editorial Board Roles"]),
        Q("Exact Title of Award / Certification / Lecture / Role", key="title", req=True, nl="title"),
        Q("Type of Recognition or Engagement", "list", key="recognition_type", choices=[
            "Award", "Certification", "Invited lecture / Keynote", "Resource person", "Session chair", "FDP / Workshop attended",
            "Editorial / Reviewer role", "Professional membership", "Other"]),
        Q("Awarding Body / Host Institution / Organizing Organization", key="host_org", req=True, nl="organization_or_venue"),
        Q("Level", "choice", key="level", req=True, choices=LEVELS, nl="impact_or_indexing"),
        Q("Date of Achievement / Start Date", "date", key="start_date", req=True, nl="event_date"),
        Q("End Date", "date", key="end_date"),
        Q("City / Venue", key="city_venue"),
        Q("Credential / Certificate Number (if any)", key="credential_no"),
        Q("Duration / Training Hours (number)", "number", key="duration_hours"),
        S("C. Details"),
        Q("Role and Specific Contribution", "para", key="role_contribution"),
        Q("Selection Criteria / Eligibility / Competitiveness", "para", key="selection_criteria"),
        Q("Description & Key Highlights", "para", key="description", req=True, nl="description"),
        Q("Outcome and Professional Impact", "para", key="outcome_impact"),
        Q("Individual or Team Achievement", "choice", key="is_team", choices=["Individual", "Team"]),
        Q("Names, Affiliations and Roles of Other Contributors (NA if none)", "para", key="other_contributors"),
        Q("Organizer Webpage (URL)", "url", key="organizer_url"),
        Q("Has this Achievement Been Reported Previously?", "choice", key="previously_reported", choices=YES_NO),
        Q("Additional Information for the Review Team", "para", key="extra_notes"),
    ] + tail(),
}

# ---------------------------------------------------------------- Departmental highlights
FORMS["form_departmental"] = {
    "form_type": "DEPARTMENT", "date_key": "start_date",
    "title": "IT Chronicles - Departmental Highlights Submission Form",
    "description": "Workshops, conferences, lab upgrades, club activities and milestones.",
    "questions": [
        S("A. People"),
        Q("Submitting Faculty (select your name)", "faculty", key="_submitter", req=True, submitter=True),
        Q("Convener / Coordinator", "faculty", key="convener_emp_id", req=True, nl="author_or_person", tf="names_only"),
        Q("Other Faculty Involved (optional, one per line: EmployeeID - Name)", "roster_any", key="_faculty_involved"),
        S("B. Highlight"),
        Q("Department Highlight Category", "choice", key="category", req=True, nl="category_id", choices=[
            "Workshops & FDPs Organized", "Conferences & Symposia Organized", "Infrastructure & Lab Upgrades",
            "Student Club & Society Activities", "Department Statistics & Major Milestones"]),
        Q("Official Title of Event / Upgrade / Milestone", key="title", req=True, nl="title"),
        Q("Highlight Type", "list", key="highlight_type", choices=["Event", "Infrastructure upgrade", "Milestone", "Student activity", "Other"]),
        Q("Department / Programme / Unit Involved", key="units_involved"),
        Q("Start Date / Event Date", "date", key="start_date", req=True, nl="event_date"),
        Q("End Date", "date", key="end_date"),
        Q("Implementation Status", "list", key="impl_status", choices=["Planned", "Ongoing", "Completed"]),
        Q("Venue / Campus / Facility", key="venue"),
        Q("Organizing / Funding / Partner Bodies", key="partner_bodies"),
        Q("Target Audience / Beneficiaries", key="target_audience"),
        Q("Total Participants / Direct Beneficiaries (number)", "number", key="participant_count"),
        S("C. Details"),
        Q("Event Overview and Key Highlights", "para", key="overview", req=True, nl="description"),
        Q("Objectives and Rationale", "para", key="objectives"),
        Q("Key Outputs / Deliverables", "para", key="outputs"),
        Q("Measurable Impact / Success Indicators", "para", key="success_indicators"),
        Q("Infrastructure / Laboratory Upgrade Details", "para", key="infra_upgrade"),
        Q("Budget / Investment in Rupees (numbers only)", "number", key="budget_amount"),
        Q("Funding Source", key="funding_source"),
        Q("Approvals / Compliance / Accreditation Linkage (NBA, NAAC, NIRF)", key="accreditation_link"),
        Q("Challenges and Mitigation", "para", key="challenges"),
        Q("Sustainability / Maintenance / Continuation Plan", "para", key="sustainability"),
        Q("Recognition / Ranking / External Validation", key="recognition"),
        Q("Related Initiatives / Previous Milestones", "para", key="related_initiatives"),
        Q("Event Report / Brochure / Flyer Link", "url", key="report_url", nl="evidence_url"),
    ] + tail(evidence_q="Official Evidence / Certificate / Supporting Document Link", evidence_nl=None),
}

# ---------------------------------------------------------------- Industry, alumni & outreach
FORMS["form_industry"] = {
    "form_type": "OUTREACH", "date_key": "start_date",
    "title": "IT Chronicles - Industry, Alumni & Outreach Submission Form",
    "description": "Industry visits, expert talks, MoUs, alumni interactions and community outreach.",
    "questions": [
        S("A. People"),
        Q("Submitting Faculty (select your name)", "faculty", key="_submitter", req=True, submitter=True),
        Q("Lead Coordinator", "faculty", key="lead_emp_id", req=True, nl="author_or_person", tf="names_only"),
        Q("Other Faculty Involved (optional, one per line: EmployeeID - Name)", "roster_any", key="_faculty_involved"),
        S("B. Activity"),
        Q("Outreach Category", "choice", key="category", req=True, nl="category_id", choices=[
            "Industrial Visits & Field Tours", "Industry Expert Lectures & Technical Talks", "MoUs Signed & Industrial Collaborations",
            "Alumni Interactions & Mentorship Sessions", "Community & Social Outreach Initiatives"]),
        Q("Official Title of Event / Visit / MoU / Partnership", key="title", req=True, nl="title"),
        Q("Activity Format", "list", key="activity_format", choices=[
            "Industrial visit", "Guest lecture / Talk", "Workshop", "MoU / Partnership", "Alumni meet / Mentoring", "Community camp", "Other"]),
        Q("Participating Departments / Units", key="units_involved"),
        Q("Partner Company / Organization / Alumni Group", key="_partner", req=True, nl="organization_or_venue"),
        Q("Partner Type", "list", key="partner_type", choices=["Industry", "Academic institution", "Alumni", "Government", "NGO / Community", "Other"]),
        Q("Event / Execution Start Date", "date", key="start_date", req=True, nl="event_date"),
        Q("End Date", "date", key="end_date"),
        Q("Venue", key="venue"),
        Q("Target Audience", key="target_audience", nl="impact_or_indexing"),
        Q("Expected Participant Count (number)", "number", key="expected_count"),
        Q("Actual Attendance / Participation Count (number)", "number", key="actual_count"),
        Q("Student Participants (optional, one roll number per line)", "roster_roll", key="_event_participants",
          aliases=["Student Participants (optional, one per line: ROLLNO - Name)"],
          help="Roll numbers only. Lets each student's participation show in their class record."),
        S("C. Details"),
        Q("Objective and Institutional Need", "para", key="objective"),
        Q("Executive Summary and Outcomes", "para", key="summary_outcomes", req=True, nl="description"),
        Q("Agenda / Key Activities", "para", key="agenda"),
        Q("Speakers / Mentors / Partner Representatives", "para", key="speakers"),
        Q("MoU / Partnership Scope (if applicable)", "para", key="mou_scope"),
        Q("Agreement Effective Date", "date", key="agreement_effective"),
        Q("Agreement Expiry / Renewal Date", "date", key="agreement_expiry"),
        Q("Outputs and Follow-up Commitments", "para", key="follow_up"),
        Q("Measurable Outcomes", "para", key="measurable_outcomes"),
        Q("Budget / Sponsorship / In-kind Support in Rupees (numbers only)", "number", key="budget_amount"),
        Q("Feedback / Satisfaction Summary", "para", key="feedback_summary"),
        Q("Event Report / Brochure / Partner Announcement Link", "url", key="report_url", nl="evidence_url"),
    ] + tail(evidence_nl=None),
}

# ---------------------------------------------------------------- Placement data (filled by students, uploaded by the Admin)
PLACEMENT = {
    "title": "IT Department - Student Placement Data Collection Form",
    "description": "Collected for the IT Department placement records. Submit one response per offer "
                   "(if you hold no offer, submit once with the company left blank). Your roll number and class are "
                   "never shown to other students - only company-level statistics and anonymous experiences are.",
    "questions": [
        S("A. You"),
        Q("Roll Number", "roll", key="roll_no", req=True),
        Q("Placement Academic Year", "years", key="ay_id", req=True),
        Q("Placement Preference", "choice", key="opt_status", req=True, choices=["Opted In", "Opted Out"]),
        Q("Reason for Opting Out (only if Opted Out)", "list", key="opt_out_reason",
          choices=["Higher studies", "Entrepreneurship", "Family business", "Government exam preparation", "Other"]),
        S("B. Offer (leave the company blank if you have no offer)"),
        Q("Company Name", key="company"),
        Q("Company Sector", "list", key="sector", choices=["Product", "IT Services", "Core / Engineering", "Startup", "BFSI", "Consulting", "Other"]),
        Q("Offer Type", "choice", key="offer_type", choices=["FTE", "Intern", "FTE+Intern", "Intern-Converted FTE"]),
        Q("Package in LPA (numbers only, for FTE offers)", "number", key="package_lpa"),
        Q("Internship Stipend in Rupees per Month (numbers only)", "number", key="stipend_per_month"),
        Q("Job Role", key="job_role"),
        Q("Work Location", key="work_location"),
        Q("Offer Status", "choice", key="offer_status", choices=["Accepted", "Declined", "Pending"]),
        Q("Recruitment Mode", "choice", key="recruitment_mode", choices=["On-campus", "Off-campus"]),
        Q("Offer Date", "date", key="offer_date"),
        S("C. Interview experience"),
        Q("Number of Interview Rounds", "number", key="rounds_count"),
        Q("Round-wise Details", "para", key="round_details", help="e.g. Online test, Technical 1, Technical 2, HR"),
        Q("Interview Difficulty", "choice", key="difficulty", choices=["Easy", "Medium", "Hard"]),
        Q("Questions Asked", "para", key="questions_asked"),
        Q("Interview Result", "choice", key="result", choices=["Selected", "Rejected", "Waitlisted"]),
        Q("Your Interview Experience", "para", key="interview_experience"),
        Q("Tips for Juniors", "para", key="tips"),
        S("D. Internship experience"),
        Q("Internship Duration", key="intern_duration", help="e.g. 6 months"),
        Q("Internship Mode", "choice", key="intern_mode", choices=["Onsite", "Remote", "Hybrid"]),
        Q("Internship Role", key="intern_role"),
        Q("Technologies Used in Internship", key="tech_stack"),
        Q("Work Summary", "para", key="work_summary"),
        Q("Key Learnings", "para", key="learnings"),
        Q("Internship Rating (1 = poor, 5 = excellent)", "choice", key="rating", choices=["1", "2", "3", "4", "5"]),
        Q("Your Internship Experience", "para", key="internship_experience"),
        S("E. Consent"),
        Q("Consent to Share Experience Anonymously", "choice", key="consent", req=True,
          choices=["Yes - share anonymously with juniors", "No - keep private"],
          help="Your name, roll number and photo are never shown, whatever you choose."),
        Q("Accuracy Confirmation", "confirm", key="authorization_confirmed", req=True,
          choices=["I confirm the information is accurate."]),
    ],
}

# ======================================================================== .gs generation
GS_HEAD = '''/**
 * ==============================================================================
 * {heading}
 * ==============================================================================
 * GENERATED by gform_scripts/build_forms.py - edit that file, not this one.
 *
 * 1. Open https://script.google.com -> New project -> paste this ENTIRE file.
 * 2. Edit the CONFIG block below{faculty_note}.
 * 3. Run {entry} (grant permissions). Each form also gets its own responses spreadsheet.
 * 4. Open the Execution log for the form links.
 * 5. Download each responses sheet as .xlsx and give it to the Admin, who uploads it in the IT Portal.
 * ==============================================================================
 */

// ---------------------------- CONFIG ----------------------------------------
// Roll-number format as a regular expression (RE2). Default: 6-15 letters/digits.
const ROLL_ID = '[A-Za-z0-9]{{6,15}}';
// Any person id (employee id, roll number or EXT for outsiders).
const ANY_ID = '[A-Za-z0-9]{{2,15}}';
{faculty_block}
// ---------------------------- VALIDATION ------------------------------------
function linesValidation_(idPattern, help, nameOptional) {{
  const line = idPattern + (nameOptional ? '(\\\\s*-\\\\s*[^\\\\n]+)?' : '\\\\s*-\\\\s*[^\\\\n]+');
  const re = '^\\\\s*' + line + '(\\\\n\\\\s*' + line + ')*\\\\s*$';
  return FormApp.createParagraphTextValidation().requireTextMatchesPattern(re).setHelpText(help).build();
}}
const V_ROLL = FormApp.createTextValidation().requireTextMatchesPattern('^' + ROLL_ID + '$')
  .setHelpText('Enter your roll number exactly as on your ID card (letters and digits only).').build();
const V_URL = FormApp.createTextValidation().requireTextIsUrl()
  .setHelpText('Enter a full link starting with https://').build();
const V_NUMBER = FormApp.createTextValidation().requireNumberGreaterThanOrEqualTo(0)
  .setHelpText('Numbers only, e.g. 12.5').build();
const V_ROSTER_ROLL = linesValidation_(ROLL_ID, 'One roll number per line, e.g. 21IT001', true);
const V_ROSTER_ANY = linesValidation_(ANY_ID, 'One per line: ID - Name  (outsiders: EXT - Name - Organization)');

'''

FACULTY_BLOCK = '''// Faculty drop-down: one entry per faculty as "EMPLOYEEID - Full Name".
// In the IT Portal (Admin) use Faculty -> "Copy form list" and paste the result here.
const FACULTY_CHOICES = [
  "EMP001 - Replace with your faculty list",
];
'''


def js(s):
    return json.dumps(s, ensure_ascii=False)


def gs_item(q):
    t = q["type"]
    title = js(q["q"])
    req = ".setRequired(true)" if q.get("req") else ".setRequired(false)"
    help_ = ".setHelpText(%s)" % js(q["help"]) if q.get("help") else ""
    ch = js(q.get("choices", []))
    if t == "section":
        return "  form.addSectionHeaderItem().setTitle(%s);\n" % title
    if t in ("text", "roll", "url", "number"):
        val = {"roll": ".setValidation(V_ROLL)", "url": ".setValidation(V_URL)", "number": ".setValidation(V_NUMBER)"}.get(t, "")
        return "  form.addTextItem().setTitle(%s)%s%s%s;\n" % (title, help_, req, val)
    if t in ("para", "roster_roll", "roster_any"):
        val = {"roster_roll": ".setValidation(V_ROSTER_ROLL)", "roster_any": ".setValidation(V_ROSTER_ANY)"}.get(t, "")
        return "  form.addParagraphTextItem().setTitle(%s)%s%s%s;\n" % (title, help_, req, val)
    if t == "date":
        return "  form.addDateItem().setTitle(%s)%s%s;\n" % (title, help_, req)
    if t == "choice":
        return "  form.addMultipleChoiceItem().setTitle(%s)%s%s.setChoiceValues(%s);\n" % (title, help_, req, ch)
    if t == "list":
        return "  form.addListItem().setTitle(%s)%s%s.setChoiceValues(%s);\n" % (title, help_, req, ch)
    if t == "faculty":
        return "  form.addListItem().setTitle(%s)%s%s.setChoiceValues(FACULTY_CHOICES);\n" % (title, help_, req)
    if t == "years":
        return "  form.addListItem().setTitle(%s)%s%s.setChoiceValues(placementYears_());\n" % (title, help_, req)
    if t == "confirm":
        return "  form.addCheckboxItem().setTitle(%s)%s%s.setChoiceValues(%s);\n" % (title, help_, req, ch)
    raise ValueError(t)


def gs_form(fn, spec):
    out = ["/** %s */\nfunction %s() {\n" % (spec["title"], fn)]
    out.append("  const form = FormApp.create(%s);\n" % js(spec["title"]))
    out.append("  form.setDescription(%s);\n  form.setCollectEmail(true);\n  form.setLimitOneResponsePerUser(false);\n\n" % js(spec["description"]))
    for q in spec["questions"]:
        out.append(gs_item(q))
    out.append('''
  const sheet = SpreadsheetApp.create(form.getTitle() + " (Responses)");
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());
  Logger.log("%s\\n  Fill-in link : " + form.getPublishedUrl() + "\\n  Edit link    : " + form.getEditUrl() + "\\n  Responses    : " + sheet.getUrl() + "\\n");
  return form;
}

''' % spec["title"])
    return "".join(out)


def build_master_gs():
    fns = {"form_student": "createStudentForm", "form_research": "createResearchForm", "form_faculty": "createFacultyForm",
           "form_departmental": "createDepartmentalForm", "form_industry": "createIndustryForm"}
    text = GS_HEAD.format(heading="IT CHRONICLES - MASTER GOOGLE FORMS GENERATOR (5 FORMS)", entry="buildAllMasterForms",
                          faculty_note=" (faculty list and roll-number format)", faculty_block=FACULTY_BLOCK)
    text += "/** Creates all five submission forms in one go. */\nfunction buildAllMasterForms() {\n"
    text += "".join("  %s();\n" % fn for fn in fns.values())
    text += '  Logger.log("All 5 forms created. Links are listed above.");\n}\n\n'
    for fid, fn in fns.items():
        text += gs_form(fn, FORMS[fid])
    return text


PLACEMENT_YEARS_JS = '''/** Academic years offered in the drop-down: last year, this year and next year. */
function placementYears_() {
  const now = new Date();
  const start = now.getMonth() >= 5 ? now.getFullYear() : now.getFullYear() - 1;
  const label = function (y) { return y + "-" + String((y + 1) % 100).padStart(2, "0"); };
  return [label(start - 1), label(start), label(start + 1)];
}

'''


def build_placement_gs():
    text = GS_HEAD.format(heading="IT DEPARTMENT - STUDENT PLACEMENT DATA FORM", entry="createPlacementForm",
                          faculty_note="", faculty_block="")
    text += PLACEMENT_YEARS_JS
    text += gs_form("createPlacementForm", PLACEMENT)
    return text


def build_all_gs():
    """One file, one run: the five submission forms and the placement form."""
    fns = [("form_departmental", "createDepartmentalForm"), ("form_faculty", "createFacultyForm"), ("form_research", "createResearchForm"),
           ("form_student", "createStudentForm"), ("form_industry", "createIndustryForm")]
    text = GS_HEAD.format(heading="IT CHRONICLES - ALL 6 GOOGLE FORMS IN ONE RUN", entry="buildAllForms",
                          faculty_note=" (faculty list and roll-number format)", faculty_block=FACULTY_BLOCK)
    text += PLACEMENT_YEARS_JS
    text += '''/** Creates all six forms (five submission forms + the placement form) and lists every link at the end. */
function buildAllForms() {
  const forms = [
''' + "".join("    %s(),\n" % fn for _, fn in fns) + '''    createPlacementForm(),
  ];
  Logger.log("=================================================");
  Logger.log("  ALL " + forms.length + " FORMS CREATED");
  Logger.log("=================================================");
  forms.forEach(function (f, i) {
    Logger.log("[Form " + (i + 1) + "] " + f.getTitle() + "\\n  Fill-in link : " + f.getPublishedUrl() + "\\n  Edit link    : " + f.getEditUrl());
  });
  return forms.map(function (f) { return { title: f.getTitle(), fillInUrl: f.getPublishedUrl(), editUrl: f.getEditUrl() }; });
}

'''
    for fid, fn in fns:
        text += gs_form(fn, FORMS[fid])
    text += gs_form("createPlacementForm", PLACEMENT)
    return text


# ======================================================================== config generation
# What the Studio's Forms tab calls a column's type, from the Google Form question type
STUDIO_TYPE = {"para": "textarea", "roster_roll": "textarea", "roster_any": "textarea", "date": "date", "choice": "select", "list": "select",
               "url": "url"}


def studio_type(q):
    if q.get("nl") == "photo_url" or "photo link" in q["q"].lower():
        return "image"
    if q.get("nl") == "description":
        return "textarea"
    return STUDIO_TYPE.get(q["type"], "text")


def merge_newsletter_mappings(path):
    """The newsletter's form definitions are exactly the new forms: every question is a column, the ones with a newsletter
    field are mapped. Headers of the earlier form versions are not lost, they move to legacy_* (still understood when an
    old sheet is imported, but not shown as columns)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for fid, spec in FORMS.items():
        old = data["forms"][fid]
        fm = {"Timestamp": "submission_timestamp", "Email Address": "submitter_email"}
        tfs, meta = {}, {"Timestamp": {"canonical_tag": "submission_timestamp", "type": "text", "required": False, "description": "Added by Google Forms"},
                         "Email Address": {"canonical_tag": "submitter_email", "type": "text", "required": False, "description": "Collected by Google Forms"}}
        category_field = old.get("category_field")
        for q in spec["questions"]:
            if q["type"] == "section":
                continue
            tag = q.get("nl")
            if tag == "category_id":
                category_field = q["q"]
            elif tag:
                fm[q["q"]] = tag
            if q.get("tf"):
                tfs[q["q"]] = q["tf"]
            meta[q["q"]] = {"canonical_tag": tag or "custom", "type": studio_type(q), "required": bool(q.get("req")), "description": q.get("help", "")}
        known = set(meta)
        legacy = dict(old.get("legacy_field_mappings", {}))
        legacy.update({k: v for k, v in old.get("field_mappings", {}).items() if k not in known})
        legacy_tf = dict(old.get("legacy_transforms", {}))
        legacy_tf.update({k: v for k, v in old.get("transforms", {}).items() if k not in known})
        new = {"form_name": spec["title"], "section_id": old.get("section_id"), "category_field": category_field,
               "category_map": old.get("category_map", {}), "field_mappings": fm, "column_metadata": meta}
        if tfs:
            new["transforms"] = tfs
        if legacy:
            new["legacy_field_mappings"] = legacy
        if legacy_tf:
            new["legacy_transforms"] = legacy_tf
        data["forms"][fid] = new
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    with open(os.path.join(CONFIG, "form_mappings.json"), encoding="utf-8") as f:
        legacy = json.load(f)["forms"]
    master = {"version": "1.0", "forms": {}, "placement": PLACEMENT}
    for fid, spec in FORMS.items():
        master["forms"][fid] = {**spec, "section_id": legacy[fid]["section_id"]}
    with open(os.path.join(CONFIG, "master_forms.json"), "w", encoding="utf-8") as f:
        json.dump(master, f, indent=1, ensure_ascii=False)
    merge_newsletter_mappings(os.path.join(CONFIG, "form_mappings.json"))
    here = os.path.dirname(__file__)
    for name, text in (("AllFormsCreator.gs", build_all_gs()), ("MasterFormsCreator.gs", build_master_gs()), ("PlacementFormCreator.gs", build_placement_gs())):
        with open(os.path.join(here, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print("Wrote AllFormsCreator.gs, MasterFormsCreator.gs, PlacementFormCreator.gs, config/master_forms.json, merged config/form_mappings.json")


if __name__ == "__main__":
    main()
