"""
The five category-based Google Forms (and the placement form's wording), as the application understands them.

Each form is "one response, several categories": a person says YES or NO to each category, fills the YES ones, then answers a few
common questions at the end. The response sheet therefore repeats titles ("Objectives and Rationale" appears in every category), so
its layout is described by position: common columns, then for each category a gate column ("Do you want to submit ...?") followed by
that category's fields, then the closing columns.

This file only DESCRIBES the forms. build_new_forms.py turns it into config/master_forms.json, config/form_mappings.json and the
newsletter's section categories, and tests/test_blocks.py checks every layout against the real response sheets' header rows.

F(title, key, type, ...):  title = the column title in the sheet; key = the master-database column (or x_something: kept in the
raw answers only); nl = the newsletter field it fills; tf = value transform.
"""

LEVELS = ["Department", "College", "Inter-college", "State", "National", "International"]
YES_NO = ["Yes", "No"]
LANDMARK = "Is this a Landmark / Milestone Achievement?"
LANDMARK_CHOICES = ["No (Standard Entry)", "Yes (Nominate for Spotlight Feature)"]
PERMISSION = "Permission to Publish this Submission"
PERMISSION_CHOICES = ["Yes - may be published in the IT Chronicles newsletter", "No - keep for internal records only"]
ACCURACY = "Accuracy and Authorization Confirmation"
ACCURACY_CHOICES = ["I confirm the information is accurate and I am authorised to submit it."]


def F(title, key=None, type="text", req=False, nl=None, choices=None, help=None, tf=None, submitter=False, aliases=None, fill=False, derived=False):
    d = {"q": title, "type": type, "req": req}
    slug = "x_" + "".join(c if c.isalnum() else "_" for c in title.lower())[:40].strip("_")
    d["key"] = key or slug
    for k, v in (("nl", nl), ("choices", choices), ("help", help), ("tf", tf), ("aliases", aliases)):
        if v:
            d[k] = v
    for k, v in (("submitter", submitter), ("fill", fill), ("derived", derived)):
        if v:
            d[k] = True
    return d


def closing_set(badge, photo, caption, evidence, evidence_key="evidence_url", extra_before=()):
    return list(extra_before) + [
        F(badge, "badge_tag", nl="badge_tag"),
        F(photo, "media_url", "url", nl="photo_url"),
        F(caption, "photo_caption", nl="photo_caption"),
        F(evidence, evidence_key, "url", nl="evidence_url" if evidence_key == "evidence_url" else None),
        F(LANDMARK, "is_landmark", "choice", req=True, choices=LANDMARK_CHOICES),
        F(PERMISSION, "publish_permission", "choice", req=True, choices=PERMISSION_CHOICES),
        F(ACCURACY, "authorization_confirmed", "confirm", req=True, choices=ACCURACY_CHOICES),
    ]


def block(name, gate, fields, date_key=None, defaults=None, copy=None, title_from=None, title_prefix="", date_text_key=None):
    return {"name": name, "gate": gate, "fields": fields, "date_key": date_key, "defaults": defaults or {}, "copy": copy or {},
            "title_from": title_from, "title_prefix": title_prefix, "date_text_key": date_text_key}


FORMS = {}

# ======================================================================================================== Student achievements
def _stu_domain(options):
    return F("Achievement Domain", "domain", "list", req=True, choices=options)


_STU_AWARDS_TAIL = [F("Related Awards / Previous Submission Details (type NA if none)", "related_awards")]
_STU_LEVEL = F("Achievement Level", "level", "choice", req=True, choices=LEVELS)
_STU_ORG = F("Organizing Institute / Company / Awarding Body", "organizer", req=True, nl="organization_or_venue")
_STU_NAME = F("Name of Competition / Award / Project / Event", "title", req=True, nl="title")
_STU_POS = F("Position / Rank / Prize / Scholarship", "position", req=True, nl="grant_or_prize_amount",
             help="e.g. 1st Prize, Runner-up, Scholarship. For participation only, type Participated.")
_STU_PRIZE = F("Prize / Scholarship Amount in Rupees (numbers only, 0 if none)", "prize_amount", "number")
_STU_DATE = F("Date of Achievement / Result", "result_date", "date", req=True, nl="event_date")
_STU_START = F("Event Start Date", "event_start", "date")
_STU_END = F("Event End Date", "event_end", "date")
_STU_MENTOR = lambda req: F("Faculty Mentor / Project Guide", "mentor_emp_id", "faculty", req=req)
_STU_RESULT = F("Measurable Result or Impact", "measurable_impact")
_STU_DEMO = F("Project Demo / Repository / Portfolio URL", "demo_url", "url")
_STU_LEARN = F("Learning Outcomes / Skills Demonstrated", "learning_outcomes", "para")

FORMS["form_student"] = {
    "form_type": "STUDENT", "date_key": "result_date",
    "title": "IT Chronicles - Student Achievements Submission Form",
    "description": "Student competitions, hackathons, projects, higher studies and co-curricular achievements. "
                   "Enter roll numbers only: names and class details are filled in from the college records.",
    "category_q": F("Student Achievement Category", "category", "choice", req=True, nl="category_id"),
    "common": [
        "Timestamp", "Email Address",
        F("Achievement or Participation", "entry_kind", "choice", req=True, choices=["Achievement (won, ranked or awarded)", "Participation only"],
          help="Choose 'Participation only' when the students took part without winning or ranking."),
        F("Participants (One roll number per line)", "_participants", "roster_roll", req=True, nl="author_or_person", tf="names_only",
          aliases=["Participants (one per line: ROLLNO - Student Name)"], help="One student per line, roll number only, e.g.\n21IT001\n21IT014\nNames are filled in from the college records."),
        F("Lead Student Roll Number", "_lead_roll", "roll", req=True),
        F("Individual or Team Achievement", "is_team", "choice", req=True, choices=["Individual", "Team"]),
    ],
    "blocks": [
        block("Academic Excellence & Ranks", "Do you want to submit Academic Excellence & Ranks?", [
            _STU_NAME, _STU_ORG, _STU_LEVEL, _STU_POS, _STU_PRIZE, _STU_DATE,
            _stu_domain(["Academic Excellence", "University Rank", "Semester / Subject Topper", "Academic Scholarship", "Competitive Examination", "Other"]),
            _STU_MENTOR(False), F("Academic Year / Semester"), F("Measurable Academic Result or Impact", "measurable_impact"),
        ] + _STU_AWARDS_TAIL, defaults={"abstract": ""}),
        block("Hackathons & Coding Competitions", "Do you want to submit Hackathons & Coding Competitions?", [
            _STU_NAME, _STU_ORG, _STU_LEVEL, _STU_POS, _STU_PRIZE, _STU_DATE, _STU_START, _STU_END,
            _stu_domain(["Hackathon", "Coding Competition", "Programming Contest", "Artificial Intelligence / Machine Learning", "Cybersecurity", "Web / App Development", "Other"]),
            _STU_MENTOR(True), F("Problem Statement / Challenge Addressed", "project_statement", "para"),
            F("Project Abstract / Solution Details", "abstract", "para", req=True, nl="description"),
            F("Tools / Technologies / Programming Languages Used", "tools_used"), _STU_RESULT, _STU_DEMO, _STU_LEARN,
        ] + _STU_AWARDS_TAIL),
        block("Higher Education & Top Placements", "Do you want to submit Higher Education & Top Placements?", [
            F("Name of Institution / Company / Examination", "title", req=True, nl="title"), _STU_ORG, _STU_LEVEL,
            F("Admission / Placement / Scholarship / Rank Details", "position", req=True, nl="grant_or_prize_amount"),
            F("Scholarship / Offer Amount in Rupees (numbers only, 0 if none)", "prize_amount", "number"), _STU_DATE,
            _stu_domain(["Higher Education Admission", "Top Placement", "Competitive Examination", "Scholarship / Fellowship", "International Admission", "Other"]),
            _STU_MENTOR(False), F("Programme / Degree / Job Role", "abstract", nl="description"), F("Institution / Company / University Name"),
            _STU_RESULT,
        ] + _STU_AWARDS_TAIL),
        block("Technical Projects & Innovations", "Do you want to submit Technical Projects & Innovations?", [
            _STU_NAME, _STU_ORG, _STU_LEVEL, _STU_POS, _STU_PRIZE, _STU_DATE, _STU_START, _STU_END,
            _stu_domain(["Software Development", "Hardware / Embedded Systems", "Artificial Intelligence / Machine Learning", "Research Innovation", "Prototype Development",
                         "Patent / Intellectual Property", "Startup / Entrepreneurship", "Other"]),
            _STU_MENTOR(True), F("Project Statement / Objective", "project_statement", "para", req=True),
            F("Project Abstract / Achievement Details", "abstract", "para", req=True, nl="description"),
            F("Tools / Technologies / Methods Used", "tools_used"), _STU_RESULT, _STU_DEMO, _STU_LEARN,
            F("Has this Work Received Other Awards or Been Reported Previously?", "previously_reported", "choice", req=True, choices=YES_NO),
        ] + _STU_AWARDS_TAIL),
        block("Sports, Cultural & Co-Curricular Accomplishments", "Do you want to submit Sports, Cultural & Co-Curricular Accomplishments?", [
            _STU_NAME, _STU_ORG, _STU_LEVEL, _STU_POS, _STU_PRIZE, _STU_DATE, _STU_START, _STU_END,
            _stu_domain(["Sports", "Cultural", "Dance / Music / Arts", "Literary Activities", "Student Clubs", "Leadership", "Social Outreach", "Volunteering", "Other"]),
            _STU_MENTOR(False), F("Activity / Event / Performance Details", "abstract", "para", req=True, nl="description"), _STU_RESULT, _STU_LEARN,
        ] + _STU_AWARDS_TAIL),
    ],
    "closing": closing_set("Key Impact Badge / Metric (e.g. 1st Prize, Winner, National Finalist, ₹50,000 Scholarship)", "Photo Link (Google Drive / Cloud URL)",
                           "Photo Caption & Persons in Image (Names from left to right)", "Certificate / Proof Link"),
}

# ======================================================================================================== Research & innovation
_RS_AUTHORS = lambda title, req=True: F(title, "_contributors", "roster_any", req=req, nl="author_or_person", tf="names_only",
                                         help="In publication order, first = lead. Employee ID or Roll No for people of this department, EXT for outsiders, "
                                              "e.g.\nC6608 - Dr. M. L. Valarmathi\nEXT - Dr. J. Smith - Anna University")
_RS_FUND_ACK = F("Funding Acknowledgement", "x_funding_ack")
_RS_REFS = F("Related Publications / Project References", "related_refs", "para")
_RS_DATASET = F("Dataset / Code / Supplementary Material Link", "dataset_url", "url")
_RS_INDEX = lambda: F("Indexing", "indexing", "list", nl="impact_or_indexing", choices=["Scopus", "Web of Science", "SCI", "ESCI", "UGC CARE", "Other", "Not Indexed"])
_RS_STATUS = lambda title, opts: F(title, "current_status", "list", choices=opts)

FORMS["form_research"] = {
    "form_type": "RESEARCH", "date_key": "output_date",
    "title": "IT Chronicles - Research & Innovation Submission Form",
    "description": "Publications, patents, funded projects, consultancy and innovations. Select your name from the list.",
    "category_q": F("Research Subcategory", "category", "choice", req=True, nl="category_id"),
    "common": ["Timestamp", "Email Address", F("Submitting Faculty (Select your name)", "_submitter", "faculty", req=True, submitter=True)],
    "blocks": [
        block("Journal Publications", "Do you want to submit Journal Publications?", [
            F("Research Paper / Article Title", "title", req=True, nl="title"), F("Journal Name", "venue_publisher", req=True, nl="organization_or_venue"),
            F("Publisher", "x_publisher"), _RS_AUTHORS("Author Names and Affiliations"), F("Corresponding Author", "x_corresponding_author"),
            F("Volume / Issue / Page Numbers", "x_volume_issue_pages"), F("Project Start Date", "project_start", "date"),
            F("Publication Date", "output_date", "date", nl="event_date"), F("DOI / ISSN", "identifier", nl="grant_or_prize_amount"), _RS_INDEX(),
            F("Quartile", "quartile", "list", choices=["Q1", "Q2", "Q3", "Q4", "Not Applicable"]), F("Citation Count (if available)", "x_citations"),
            _RS_FUND_ACK, _RS_REFS, _RS_DATASET,
        ], defaults={"current_status": "Published", "review_status": "Peer reviewed"}, title_from=None),
        block("Conference Publications", "Do you want to submit Conference Publications?", [
            F("Conference Paper Title", "title", req=True, nl="title"), F("Conference Name", "venue_publisher", req=True, nl="organization_or_venue"),
            F("Organizing Institution", "x_organizing_institution"), F("Conference Location", "x_conference_location"),
            F("Conference Date", "output_date", "date", nl="event_date"), F("Publication Date", "x_publication_date", "date"),
            _RS_AUTHORS("Author Names and Affiliations"), F("Publisher / Proceedings Name", "x_publisher"), F("DOI / ISBN / ISSN", "identifier", nl="grant_or_prize_amount"),
            F("Conference Type", "conference_level", "list", choices=["International", "National", "State", "Other"]), _RS_INDEX(),
            F("Presentation Type", "x_presentation_type", "list", choices=["Oral Presentation", "Poster Presentation", "Invited Presentation", "Other"]),
            _RS_FUND_ACK, _RS_REFS, _RS_DATASET,
        ], defaults={"current_status": "Published", "review_status": "Peer reviewed"}),
        block("Book / Book Chapters", "Do you want to submit Book / Book Chapters?", [
            F("Book / Book Chapter Title", "title", req=True, nl="title"), F("Book Title", "x_book_title"), F("Chapter Number / Chapter Title", "x_chapter"),
            _RS_AUTHORS("Author / Editor Names"), F("Publisher", "venue_publisher", req=True, nl="organization_or_venue"),
            F("Publication Date", "output_date", "date", nl="event_date"), F("ISBN", "identifier", nl="grant_or_prize_amount"), F("Edition / Volume", "x_edition"),
            F("Book / Publisher Website", "venue_url", "url"), F("Indexing / Recognition", "indexing", nl="impact_or_indexing"), _RS_FUND_ACK, _RS_REFS,
        ], defaults={"current_status": "Published"}),
        block("Funded Research Projects", "Do you want to submit Funded Research Projects?", [
            F("Project Title", "title", req=True, nl="title"), _RS_AUTHORS("Principal Investigator"), F("Co-Principal Investigators / Collaborators", "collaborators"),
            F("Funding Agency", "venue_publisher", req=True, nl="organization_or_venue"),
            F("Sanctioned Grant Amount (INR)", "funding_amount", "number", req=True, nl="grant_or_prize_amount"),
            F("Project Start Date", "output_date", "date", nl="event_date"), F("Project End Date", "x_project_end_date", "date"), F("Project Duration", "x_project_duration"),
            F("Grant Reference / Sanction Number", "identifier"), F("Project Objectives and Rationale", "abstract", "para", req=True, nl="description"),
            F("Key Research Outcomes / Deliverables", "key_findings", "para"), F("Measurable Impact", "impact", "para"),
            _RS_STATUS("Project Status", ["Proposed", "Sanctioned", "Ongoing", "Completed", "On Hold"]), _RS_REFS,
            F("Project Webpage / Supporting Link", "venue_url", "url"),
        ], defaults={"funding_status": "Funded"}),
        block("Consultancy Projects", "Do you want to submit Consultancy Projects?", [
            F("Consultancy Project Title", "title", req=True, nl="title"), F("Client / Organization Name", "venue_publisher", req=True, nl="organization_or_venue"),
            _RS_AUTHORS("Project Coordinator / Faculty Members", req=False), F("Nature of Consultancy", "x_nature_of_consultancy"),
            F("Project Start Date", "output_date", "date", nl="event_date"), F("Project Completion Date", "x_project_end_date", "date"),
            F("Consultancy Amount (INR)", "funding_amount", "number", req=True, nl="grant_or_prize_amount"), F("Project Reference Number", "identifier"),
            F("Objectives and Scope of Work", "abstract", "para", req=True, nl="description"), F("Key Deliverables", "key_findings", "para"),
            F("Industry / Institutional Impact", "impact", "para"),
            _RS_STATUS("Project Status", ["Proposed", "Sanctioned", "Ongoing", "Completed", "On Hold"]), F("Supporting Project Link", "venue_url", "url"),
        ], defaults={"funding_status": "Funded"}),
        block("Patents & Intellectual Property", "Do you want to submit Patents & Intellectual Property?", [
            F("Patent / Intellectual Property Title", "title", req=True, nl="title"), _RS_AUTHORS("Inventor Names and Affiliations"),
            F("Patent / IP Type", "x_ip_type", "list", choices=["Patent", "Copyright", "Industrial Design", "Trademark", "Other"]),
            F("Application / Registration Number", "identifier", req=True, nl="grant_or_prize_amount"), F("Filing Date", "output_date", "date", nl="event_date"),
            F("Publication Date", "x_publication_date", "date"), F("Grant / Registration Date", "x_grant_date", "date"),
            F("Patent Office / Registration Authority", "venue_publisher", nl="organization_or_venue"), F("Country / Jurisdiction", "x_country"),
            F("Patent / IP Status", "current_status", "list", nl="impact_or_indexing", choices=["Filed", "Published", "Under Examination", "Granted", "Registered", "Rejected", "Abandoned"]),
            F("Technology / Application Area", "x_technology_area"), F("Innovation Overview and Significance", "abstract", "para", nl="description"),
            F("Patent / IP Webpage", "venue_url", "url"), _RS_REFS,
        ]),
        block("Key Research Innovations & Technical Accomplishments", "Do you want to submit Key Research Innovations & Technical Accomplishments?", [
            F("Innovation / Technical Accomplishment Title", "title", req=True, nl="title"), F("Innovation Overview", "abstract", "para", req=True, nl="description"),
            F("Problem Addressed / Research Gap", "problem", "para"), F("Novelty and Technical Significance", "key_findings", "para", req=True),
            _RS_AUTHORS("Faculty / Research Team Members", req=False), F("Technology / Tools / Methodologies Used", "methodology", "para"),
            F("Prototype / Product / Solution Developed", "x_prototype"), F("Development Date", "output_date", "date", nl="event_date"),
            F("Testing / Validation Results", "x_validation_results", "para"), F("Industry / Societal / Academic Impact", "impact", "para"),
            F("Commercialisation / Technology Transfer Status", "ip_status"), F("Patent / Copyright / IP Reference", "identifier"), _RS_DATASET, _RS_REFS,
        ], defaults={"current_status": "Completed"}),
    ],
    "closing": closing_set("Key Impact Badge / Metric (e.g. Scopus Q1, Patent Granted, ₹25 Lakh Grant, Best Paper Award)", "Photo Link (Google Drive / Cloud URL)",
                           "Photo Caption & Persons in Image – Names from left to right", "Official Evidence / Certificate / Supporting Document Link"),
}

# ======================================================================================================== Faculty achievements
_FA_FIELDS = [
    F("Exact Title of Award / Certification / Lecture / Role", "title", req=True, nl="title"),
    F("Type of Recognition or Engagement", "recognition_type", "list", choices=[
        "Award", "Honor", "Prize", "Certification", "Keynote Lecture", "Expert Lecture", "Guest Lecture", "Resource Person", "Session Chair", "Panel Moderator", "FDP",
        "Workshop", "Professional Membership", "Editorial Board Appointment", "Office Bearer / Leadership Role", "Other"]),
    F("Awarding Body / Host Institution / Organizing Organization", "host_org", req=True, nl="organization_or_venue"),
    F("Level", "level", "choice", req=True, choices=LEVELS, nl="impact_or_indexing"),
    F("Names, Affiliations and Roles of Other Contributors (NA if none)", "other_contributors", "para"),
    F("Organizer Webpage (URL)", "organizer_url", "url"),
    F("Has this Achievement Been Reported Previously?", "previously_reported", "choice", req=True, choices=YES_NO),
    F("Additional Information for the Review Team", "description", "para", nl="description"),
]
_FA_CATS = [("Awards & Honors Received", "Awards & Honors Received"), ("Certifications & Upskilling Completed", "Certifications & Upskilling Completed"),
            ("Invited Keynote / Expert Lectures Delivered", "Invited Keynote / Expert Lectures Delivered"),
            ("Resource Person / Session Chair Roles", "Resource Person / Session Chair Roles"), ("FDP / Workshops Attended", "FDP / Workshops Attended"),
            ("Professional Body & Editorial Board Roles", "Professional Body & Editorial Board Roles")]

FORMS["form_faculty"] = {
    "form_type": "FACULTY", "date_key": "start_date", "date_fallback": "timestamp",
    "title": "IT Chronicles - Faculty Achievements Submission Form",
    "description": "Awards, certifications, invited lectures, FDPs and professional roles. Select your name from the list. "
                   "(The form has no date question: the day the response was submitted is used.)",
    "category_q": F("Achievement Category", "category", "choice", req=True, nl="category_id"),
    "common": ["Timestamp", "Email Address",
               F("Faculty Full Name (Select your name)", "emp_id", "faculty", req=True, submitter=True, nl="author_or_person", tf="names_only"),
               F("Designation at the Time of Achievement", "designation_at_time", req=True)],
    "blocks": [block(name, f"Do you want to submit {gate}?", _FA_FIELDS) for name, gate in _FA_CATS],
    "closing": closing_set("Key Impact Badge / Metric (e.g. 1st Prize, Best Faculty Award, International Recognition)", "Photo Link (Google Drive / Cloud URL)",
                           "Photo Caption & Persons in Image", "Official Evidence / Certificate / Supporting Document Link"),
}

# ======================================================================================================== Industry, alumni & outreach
_IN_UNITS = F("Participating Departments / Units", "units_involved")
_IN_PTYPE = F("Partner Type", "partner_type", "list", choices=[
    "Industry / Corporate", "Government Organization", "Academic Institution", "Startup / Entrepreneur", "Alumni Association", "NGO / Non-profit",
    "Community Organization", "Professional Body", "Other"])
_IN_OUTPUTS = F("Outputs and Follow-up Commitments", "follow_up", "para")
_IN_MEASURE = F("Measurable Outcomes", "measurable_outcomes", "para")
_IN_FEEDBACK = F("Feedback / Satisfaction Summary", "feedback_summary", "para")
_IN_BUDGET = F("Budget / Sponsorship / In-kind Support in Rupees (numbers only)", "budget_amount", "number")
_IN_OBJ = F("Objectives and Rationale", "objective", "para")
_IN_STUDENTS = F("Number of Student Participants", "actual_count", "number")
_IN_FACULTY = F("Number of Faculty Participants", "x_faculty_participants", "number")

FORMS["form_industry"] = {
    "form_type": "OUTREACH", "date_key": "start_date",
    "title": "IT Chronicles - Industry, Alumni & Outreach Submission Form",
    "description": "Industry visits, expert talks, MoUs, alumni interactions and community outreach.",
    "category_q": F("Outreach Category", "category", "choice", req=True, nl="category_id"),
    "common": ["Timestamp", "Email Address", F("Submitting Faculty (Select your name)", "_submitter", "faculty", req=True, submitter=True),
               F("Lead Coordinator", "lead_emp_id", "faculty", req=True, nl="author_or_person", tf="names_only"),
               F("Other Faculty Involved (Optional, one per line: EmployeeID - Name)", "_faculty_involved", "roster_any")],
    "blocks": [
        block("Industrial Visits & Field Tours", "Do you want to submit Industrial Visits & Field Tours?", [
            F("Official Title of Industrial Visit / Field Tour", "title", req=True, nl="title"),
            F("Activity Format", "activity_format", "list", choices=["Industrial Visit", "Factory Visit", "Field Tour", "Plant Visit", "Other"]), _IN_UNITS,
            F("Partner Company / Organization", "_partner", req=True, nl="organization_or_venue"), _IN_PTYPE, F("Industry Sector / Domain", "x_industry_sector"),
            F("Visit Date", "start_date", "date", nl="event_date"), _IN_STUDENTS, _IN_FACULTY,
            F("Speakers / Mentors / Partner Representatives", "speakers", "para"), _IN_OBJ,
            F("Key Activities / Areas Visited", "summary_outcomes", "para", nl="description"), _IN_OUTPUTS, _IN_MEASURE, _IN_FEEDBACK, _IN_BUDGET,
        ]),
        block("Industry Expert Lectures & Technical Talks", "Do you want to submit Industry Expert Lectures & Technical Talks?", [
            F("Official Title of Event / Technical Talk", "title", req=True, nl="title"),
            F("Activity Format", "activity_format", "list", choices=["Expert Lecture", "Technical Talk", "Guest Lecture", "Keynote Address", "Panel Discussion", "Webinar", "Other"]),
            _IN_UNITS, F("Partner Company / Organization", "_partner", req=True, nl="organization_or_venue"), _IN_PTYPE, F("Industry Sector / Domain", "x_industry_sector"),
            F("Speakers / Mentors / Partner Representatives", "speakers", "para", req=True), F("Speaker Designation and Organization", "x_speaker_designation"),
            F("Event Date", "start_date", "date", nl="event_date"), _IN_STUDENTS, _IN_FACULTY, F("Topic / Technical Domain Covered", "x_topic"), _IN_OBJ,
            F("Key Takeaways / Learning Outcomes", "summary_outcomes", "para", nl="description"), _IN_OUTPUTS, _IN_MEASURE, _IN_FEEDBACK, _IN_BUDGET,
        ]),
        block("MoUs Signed & Industrial Collaborations", "Do you want to submit MoUs Signed & Industrial Collaborations?", [
            F("Official Title of MoU / Partnership", "title", req=True, nl="title"), F("Partner Company / Organization", "_partner", req=True, nl="organization_or_venue"),
            _IN_PTYPE, _IN_UNITS, F("Nature of Collaboration", "x_nature_of_collaboration"),
            F("MoU / Partnership Scope", "mou_scope", "para", req=True, nl="description"), F("Agreement Effective Date", "agreement_effective", "date", nl="event_date"),
            F("Agreement Expiry / Renewal Date", "agreement_expiry", "date"), F("Signatories / Partner Representatives", "speakers", "para"),
            F("Lead Faculty Coordinator", "x_lead_faculty_coordinator"), F("Proposed Activities Under the Agreement", "agenda", "para"), _IN_OUTPUTS, _IN_MEASURE, _IN_BUDGET,
            F("Feedback / Partnership Review Summary", "feedback_summary", "para"), F("Agreement / Partnership Reference Number", "x_agreement_reference"),
        ], date_key="agreement_effective", copy={"start_date": "agreement_effective"}),
        block("Alumni Interactions & Mentorship Sessions", "Do you want to submit Alumni Interactions & Mentorship Sessions?", [
            F("Official Title of Event / Interaction", "title", req=True, nl="title"),
            F("Activity Format", "activity_format", "list", choices=["Alumni Interaction", "Mentorship Session", "Alumni Guest Lecture", "Career Guidance", "Networking Session", "Alumni Reunion", "Other"]),
            _IN_UNITS, F("Partner Company / Organization / Alumni Group", "_partner", req=True, nl="organization_or_venue"),
            F("Alumni Names and Current Designations", "speakers", "para", req=True), F("Alumni Company / Organization", "x_alumni_company"),
            F("Year of Graduation / Alumni Batch", "x_alumni_batch"), F("Mentorship / Interaction Topic", "x_topic"), F("Event Date", "start_date", "date", nl="event_date"),
            _IN_STUDENTS, F("Number of Alumni Participants", "x_alumni_participants", "number"), _IN_OBJ,
            F("Key Insights / Learning Outcomes", "summary_outcomes", "para", nl="description"), _IN_OUTPUTS, _IN_MEASURE, _IN_FEEDBACK, _IN_BUDGET,
        ], defaults={"partner_type": "Alumni Association"}),
        block("Community & Social Outreach Initiatives", "Do you want to submit Community & Social Outreach Initiatives?", [
            F("Official Title of Outreach Initiative", "title", req=True, nl="title"),
            F("Activity Format", "activity_format", "list", choices=[
                "Community Outreach", "Social Awareness Campaign", "Village / Rural Development", "School Outreach", "Environmental Initiative", "Digital Literacy",
                "Health / Safety Awareness", "Volunteering", "Other"]),
            _IN_UNITS, F("Partner Company / Organization / Community Group", "_partner", req=True, nl="organization_or_venue"), _IN_PTYPE,
            F("Target Community / Beneficiary Group", "target_audience"), F("Location / Venue", "venue"), F("Activity Start Date", "start_date", "date", nl="event_date"),
            F("Activity End Date", "end_date", "date"), F("Number of Student Participants", "x_student_participants", "number"), _IN_FACULTY,
            F("Number of Beneficiaries Reached", "actual_count", "number"), F("Objectives and Social Rationale", "objective", "para"),
            F("Key Activities Conducted", "summary_outcomes", "para", nl="description"), _IN_OUTPUTS, F("Measurable Social Impact", "measurable_outcomes", "para"),
            _IN_FEEDBACK, _IN_BUDGET, F("Sustainability / Continuation Plan", "x_sustainability", "para"),
        ]),
    ],
    "closing": closing_set("Key Impact Badge / Metric (e.g. MoU Signed, 150+ Attendees, 5 Industry Visits)", "Photo Link (Google Drive / Cloud URL)",
                           "Photo Caption & Persons in Image (Names from left to right)", "Official Evidence / Certificate / Supporting Document Link",
                           extra_before=[]),
}
# the event report link comes between the evidence link and the landmark question in this sheet
_ind = FORMS["form_industry"]["closing"]
_ind.insert(4, F("Event Report / Brochure / Partner Announcement Link", "report_url", "url"))

# ======================================================================================================== Faculty submissions (department highlights)
_DH_OBJ = F("Objectives and Rationale", "objectives", "para")
_DH_OUTPUTS = F("Key Outputs / Deliverables", "outputs", "para")
_DH_IMPACT = F("Measurable Impact / Success Indicators", "success_indicators", "para")
_DH_RECOG = F("Recognition / Ranking / External Validation", "recognition", "para")
_DH_RELATED = F("Related Initiatives / Previous Milestones", "related_initiatives", "para")
_DH_CHALL = F("Challenges and Mitigation", "challenges", "para")
_DH_SUSTAIN = F("Sustainability / Continuation Plan", "sustainability", "para")
_DH_TITLE = lambda: F("Title", "title", req=True, nl="title", derived=True, help="Made from the overview; change it if you like.")


def _gate(n):
    return "Do you want to submit this category?"


FORMS["form_departmental"] = {
    "form_type": "DEPARTMENT", "date_key": "start_date", "date_fallback": "timestamp",
    "title": "IT CHRONICLES – Faculty Highlights & Information Collection",
    "description": "Faculty highlights and information collection for the IT Chronicles newsletter: several categories in one response.",
    "category_q": F("Department Highlight Category", "category", "choice", req=True, nl="category_id"),
    "common": ["Timestamp", F("Faculty Name", "_submitter", req=True, submitter=True, nl="author_or_person"), F("Faculty Email", "x_faculty_email", req=True),
               F("Department / Designation", "x_department_designation", "para")],
    "blocks": [
        block("Highlights", _gate(0), [
            F("Event / Initiative Overview and Key Highlights", "overview", "para", req=True, nl="description"), _DH_OBJ, _DH_OUTPUTS, _DH_IMPACT, _DH_RECOG, _DH_RELATED,
        ], title_from=["overview"]),
        block("Achievements / Awards / Recognitions", _gate(1), [
            F("Achievement Overview", "overview", "para", req=True, nl="description"), F("Award / Recognition Name", "title", req=True, nl="title"),
            F("Award Category / Position / Rank", "x_award_category_position"), F("Awarding Organisation", "partner_bodies", nl="organization_or_venue"),
            F("Date of Achievement", "start_date", "date", nl="event_date"), _DH_OBJ, _DH_OUTPUTS, F("Measurable Impact", "success_indicators", "para"),
            F("Recognition / External Validation", "recognition", "para"), F("Related Achievements / Previous Milestones", "related_initiatives", "para"),
        ]),
        block("Events / Programs", _gate(2), [
            F("Event Overview and Key Highlights", "overview", "para", req=True, nl="description"), _DH_OBJ,
            F("Event Date and Venue", "venue", "para", help="Write the date and the venue, e.g. 12 March 2026, Seminar Hall."),
            F("Organising Department / Faculty Coordinators", "units_involved", "para"), F("Number of Participants", "participant_count", "number"), _DH_OUTPUTS, _DH_IMPACT,
            _DH_CHALL, _DH_SUSTAIN, _DH_RELATED,
        ], date_text_key="venue", title_from=["overview"]),
        block("Research / Publications / Innovation", _gate(3), [
            F("Research / Innovation Overview", "overview", "para", req=True, nl="description"), F("Research Paper / Project / Patent Title", "title", nl="title"),
            F("Journal / Conference / Publisher", "partner_bodies", nl="organization_or_venue"),
            F("Publication Indexing (Scopus / Web of Science / SCI / Other)", "x_publication_indexing", nl="impact_or_indexing"),
            F("DOI / Publication / Patent Number", "x_doi_number"), F("Authors / Principal Investigator / Collaborators", "x_authors", "para"),
            F("Objectives and Research Rationale", "objectives", "para"), F("Key Research Outputs / Deliverables", "outputs", "para"),
            F("Measurable Research Impact", "success_indicators", "para"), F("Recognition / External Validation", "recognition", "para"), F("Related Research Initiatives", "related_initiatives", "para"),
        ], title_from=["title", "overview"]),
        block("Infrastructure / Laboratory Development", _gate(4), [
            F("Infrastructure / Laboratory Upgrade Details", "infra_upgrade", "para", req=True, nl="description"), _DH_OBJ,
            F("Equipment / Software / Facilities Procured", "x_equipment_procured", "para"), F("Installation / Commissioning Date", "start_date", "date", nl="event_date"),
            _DH_OUTPUTS, F("Measurable Impact", "success_indicators", "para"), _DH_CHALL, F("Sustainability / Maintenance Plan", "sustainability", "para"),
            F("Related Infrastructure Initiatives", "related_initiatives", "para"),
        ], title_from=["infra_upgrade"]),
        block("MoU / Industry Collaboration / Partnerships", _gate(5), [
            F("Collaboration Overview and Key Highlights", "overview", "para", req=True, nl="description"),
            F("Organisation / Industry / Institution Name", "partner_bodies", req=True, nl="organization_or_venue"),
            F("Nature of Collaboration", "highlight_type"), F("MoU Signing Date", "start_date", "date", nl="event_date"), F("Duration of Agreement", "x_agreement_duration"),
            _DH_OBJ, F("Activities Conducted Under the Collaboration", "x_activities_conducted", "para"), _DH_OUTPUTS, F("Measurable Impact", "success_indicators", "para"),
            _DH_SUSTAIN, F("Related Collaborations / Previous Milestones", "related_initiatives", "para"),
        ], title_from=["partner_bodies"], title_prefix="Collaboration with "),
        block("Faculty Development / Professional Achievements", _gate(6), [
            F("Faculty Development Overview", "overview", "para", req=True, nl="description"), F("Faculty Name / Names", "x_faculty_names"),
            F("Programme / Certification / Training Title", "title", nl="title"), F("Organising Institution / Agency", "partner_bodies", nl="organization_or_venue"),
            F("Date / Duration", "venue"), F("Number of Faculty Participants", "participant_count", "number"), _DH_OBJ,
            F("Skills / Competencies Acquired", "x_skills_acquired", "para"), _DH_OUTPUTS, F("Measurable Impact", "success_indicators", "para"),
            F("Recognition / External Validation", "recognition", "para"),
        ], date_text_key="venue", title_from=["title", "overview"]),
        block("Student Development / Outreach / Social Initiatives", _gate(7), [
            F("Initiative Overview and Key Highlights", "overview", "para", req=True, nl="description"), F("Programme / Initiative Name", "title", nl="title"),
            F("Date and Venue", "venue", "para"), F("Organising Faculty / Coordinators", "units_involved", "para"),
            F("Number of Student Participants", "participant_count", "number"), F("Number of External Beneficiaries", "x_external_beneficiaries", "number"), _DH_OBJ, _DH_OUTPUTS,
            F("Measurable Impact", "success_indicators", "para"), _DH_SUSTAIN, _DH_RELATED,
        ], date_text_key="venue", title_from=["title", "overview"]),
        block("Accreditation / Quality Assurance / Institutional Initiatives", _gate(8), [
            F("Initiative Overview and Key Highlights", "overview", "para", req=True, nl="description"),
            F("Accreditation / Quality Framework (NBA / NAAC / NIRF / Other)", "accreditation_link"), _DH_OBJ, F("Compliance / Improvement Details", "x_compliance_details", "para"),
            _DH_OUTPUTS, _DH_IMPACT, F("Approvals / Compliance / Accreditation Linkage", "x_approvals_linkage", "para"), _DH_CHALL, _DH_SUSTAIN, _DH_RECOG,
        ], title_from=["overview"]),
        block("Other Significant Initiatives", _gate(9), [
            F("Initiative Overview and Key Highlights", "overview", "para", req=True, nl="description"), _DH_OBJ, _DH_OUTPUTS, _DH_IMPACT, _DH_CHALL, _DH_SUSTAIN,
            F("Recognition / External Validation", "recognition", "para"), _DH_RELATED,
        ], title_from=["overview"]),
    ],
    # the closing columns repeat some block titles; the renamed (flat) title is what the importer and the review screen show
    "closing": [
        F("Event Report / Brochure / Flyer Link", "report_url", "url", nl="evidence_url"),
        F("Budget / Investment in Rupees (numbers only)", "budget_amount", "number"), F("Funding Source", "funding_source"),
        F("Common section: Infrastructure / Laboratory Upgrade Details", "infra_upgrade", "para", fill=True),
        F("Approvals / Compliance / Accreditation Linkage (NBA, NAAC, NIRF)", "accreditation_link", "para", fill=True),
        F("Common section: Challenges and Mitigation", "challenges", "para", fill=True),
        F("Sustainability / Maintenance / Continuation Plan", "sustainability", "para", fill=True),
        F("Common section: Recognition / Ranking / External Validation", "recognition", "para", fill=True),
        F("Common section: Related Initiatives / Previous Milestones", "related_initiatives", "para", fill=True),
        F("Key Impact Badge / Metric (Example: 1st Prize, Scopus Q1, MoU Signed, 150+ Attendees)", "badge_tag", nl="badge_tag"),
        F("Photo Link (Google Drive Cloud URL)", "media_url", "url", nl="photo_url"),
        F("Photo Caption & Persons in Image – Names from left to right", "photo_caption", nl="photo_caption"),
        F("Official Evidence / Certificate / Supporting Document Link", "evidence_url", "url", nl="evidence_url"),
        F(LANDMARK, "is_landmark", "choice", req=True, choices=LANDMARK_CHOICES),
        F(PERMISSION, "publish_permission", "choice", req=True, choices=PERMISSION_CHOICES),
        F(ACCURACY, "authorization_confirmed", "confirm", req=True, choices=ACCURACY_CHOICES),
    ],
    # sheet title -> flat title, for the closing columns whose title is also a title inside the category blocks
    "closing_rename": {
        "Infrastructure / Laboratory Upgrade Details": "Common section: Infrastructure / Laboratory Upgrade Details",
        "Challenges and Mitigation": "Common section: Challenges and Mitigation",
        "Recognition / Ranking / External Validation": "Common section: Recognition / Ranking / External Validation",
        "Related Initiatives / Previous Milestones": "Common section: Related Initiatives / Previous Milestones",
    },
}

# ======================================================================================================== Placement (same shape as before; new wording)
PLACEMENT_RENAMES = {
    # master_forms.json title -> (new title, extra aliases): the question is the same, only the wording changed
    "Reason for Opting Out (only if Opted Out)": ("Reason for Opting Out (Complete only if Opted Out)", []),
    "Round-wise Details": ("Round-wise Details (e.g. Online Test, Technical 1, Technical 2, HR)", []),
    "Internship Duration": ("Internship Duration (e.g. 6 months)", []),
    "Internship Rating (1 = poor, 5 = excellent)": ("Internship Rating (1 = Poor, 5 = Excellent)", []),
}
PLACEMENT_CHOICES = {
    "Reason for Opting Out (Complete only if Opted Out)": ["Higher Studies", "Entrepreneurship / Startup", "Personal Reasons", "Family Reasons", "Competitive Examination Preparation", "Other"],
    "Company Sector": ["Information Technology", "Software / Product Development", "IT Services", "Core Engineering", "Consulting", "Finance / Banking", "Manufacturing",
                       "Research / Education", "Healthcare", "Government / Public Sector", "Startup", "Other"],
    "Placement Academic Year": ["2024-25", "2025-26", "2026-27", "2027-28", "2028-29", "Other"],
}
