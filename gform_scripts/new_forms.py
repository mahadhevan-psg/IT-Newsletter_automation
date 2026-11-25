"""
The six IT Matrix Google Forms (as printed on 25 November 2026), as the application understands them.

Each of the faculty forms is "one response, several categories": the person picks a category, fills its section, then picks the next one or
finishes. The response sheet therefore has one "Which ... category ...?" column before each section, and the section's columns after it.
The student participation form is a single set of questions with a category question inside.

This file only DESCRIBES the forms. build_new_forms.py turns it into config/master_forms.json, config/form_mappings.json and the newsletter's
section categories. After that the Admin edits the forms in the portal (Form builder); this file only seeds a new database.

F(title, key, type, ...):  key = the master-database column (or x_something: kept in the raw answers only); nl = the newsletter field it fills;
printed = the title as the Google Form prints it, where the portal shows a corrected one (the sheet column keeps the printed title);
auto = filled in from the signed-in person's record, never asked.
Types: text, para, number, date, choice (buttons), list (drop-down), multi (tick several), url, file (PDF or picture), faculty,
roster_roll (students), roster_any (people).
"""

LEVELS = ["Department", "College", "Inter-college", "State", "National", "International"]
ACCURACY = "Accuracy and Authorization Confirmation"
ACCURACY_CHOICES = ["I confirm the information is accurate and I am authorised to submit it."]
PHOTO_KEY = "media_url"


def F(title, key=None, type="text", req=False, nl=None, choices=None, help=None, tf=None, submitter=False, aliases=None, derived=False, printed=None, auto=None, portal_only=False):
    d = {"q": title, "type": type, "req": req}
    d["key"] = key or "x_" + "".join(c if c.isalnum() else "_" for c in title.lower())[:40].strip("_")
    if printed and printed != title:
        aliases = [printed, *(aliases or [])]
    for k, v in (("nl", nl), ("choices", choices), ("help", help), ("tf", tf), ("aliases", aliases), ("auto", auto)):
        if v:
            d[k] = v
    if submitter:
        d["submitter"] = True
    if derived:
        d["derived"] = True
    if portal_only:
        d["portal_only"] = True                            # asked in the portal only: the Google Form and its sheet have no such column
    return d


def printed_title(q):
    return (q.get("aliases") or [q["q"]])[0]


def TITLE(title, printed=None, key="title", req=True):
    return F(title, key, req=req, nl="title", printed=printed)


def PHOTO(title="Upload Supporting Photo", req=False, printed=None):
    return F(title, PHOTO_KEY, "url", req=req, nl="photo_url", printed=printed)


def DOC(title, key=None, req=False, printed=None):
    return F(title, key, "file", req=req, nl="evidence_url" if key == "evidence_url" else None, printed=printed)


def LINK(title="Official Evidence / Certificate / Supporting Document Link", key="evidence_url", req=False):
    return F(title, key, "url", req=req, nl="evidence_url" if key == "evidence_url" else None)


def block(name, description, nav, fields, date_key=None, defaults=None, title_from=None, title_prefix="", date_text_key=None, tile_words="", portal_only=False, copy=None):
    """nav = the title of the 'which category' column that comes before this section in the response sheet."""
    return {"name": name, "description": description, "gate": nav, "fields": fields, "date_key": date_key, "defaults": defaults or {}, "copy": copy or {}, "portal_only": portal_only,
            "title_from": title_from, "title_prefix": title_prefix, "date_text_key": date_text_key, "keywords": tile_words}


FORMS = {}

# ======================================================================================================== Research contributions & innovations
_R1 = "Which research category would you like to fill first?"
_RN = "Which remaining research category would you like to fill next?"
_RS_COAUTHORS = lambda title, req=False, printed=None: F(title, "_contributors", "roster_any", req=req, nl="author_or_person", tf="names_only", printed=printed,
                                                         help="One person per line. Employee ID or Roll No for people of this department, EXT for outsiders, "
                                                              "e.g.\nC6608 - Dr. M. L. Valarmathi\nEXT - Dr. J. Smith - Anna University")

FORMS["form_research"] = {
    "form_type": "RESEARCH", "date_key": "output_date", "date_fallback": "timestamp",
    "title": "Research Contributions & Innovations",
    "description": "Research publications, patents, funded projects, consultancy, research guidance, collaborations, books, book chapters, "
                   "research presentations and technology innovations.",
    "category_q": F("Research Category", "category", "choice", req=True, nl="category_id"),
    "common": ["Timestamp", "Email Address", F("Faculty Name", "_submitter", "faculty", req=True, submitter=True)],
    "blocks": [
        block("Journal Publications", "Enter the details of research articles published in national and international journals.", _R1, [
            TITLE("Title of the Research Paper"),
            F("Name of the Journal", "venue_publisher", req=True, nl="organization_or_venue"),
            F("Type of Journal", "x_journal_type", "choice", req=True, choices=["National", "International"]),
            F("Publisher Name", "x_publisher", req=True),
            F("Indexing", "indexing", "multi", req=True, nl="impact_or_indexing",
              choices=["Scopus", "Web of Science", "UGC CARE", "PubMed", "IEEE", "SCI", "SCIE", "ESCI", "Elsevier", "Springer"]),
            F("ISSN (Print / Online)", "x_issn", req=True),
            F("DOI (Digital Object Identifier)", "identifier", req=True, nl="grant_or_prize_amount"),
            F("Volume Number and Issue Number", "x_volume_issue", printed="Volume Number and Isue number"),
            F("Month and Year of Publication", "output_date", "date", req=True, nl="event_date", help="Pick any day of that month."),
            F("Quartile", "quartile", "choice", req=True, choices=["Q1", "Q2", "Q3", "Q4", "Not Applicable"]),
            _RS_COAUTHORS("Names of Co-authors"),
            F("Impact Factor (if applicable)", "impact_factor", req=True, help="Write NA if it does not apply."),
            DOC("Upload Published Research Paper / Supporting Proof", "evidence_url", req=True),
            F("Published Article URL", "venue_url", "url"),
            F("Journal Website URL", "x_journal_url", "url"),
        ], defaults={"current_status": "Published"}, tile_words="paper article journal scopus"),
        block("Conference Publications", "Enter the details of research papers published in the proceedings of national and international conferences.", _RN, [
            TITLE("Title of the Research Paper"),
            F("Name of the Conference", "venue_publisher", req=True, nl="organization_or_venue"),
            F("Conference Proceedings Indexing", "indexing", "choice", req=True, nl="impact_or_indexing",
              choices=["Scopus", "IEEE Xplore", "Springer", "ACM Digital Library", "Elsevier", "Web of Science", "Others"]),
            F("Conference Organizing Institution", "x_organizing_institution", req=True),
            F("Conference Type", "conference_level", "choice", req=True, choices=["International", "National", "Regional"]),
            F("Conference Mode", "x_conference_mode", "choice", req=True, choices=["Physical", "Virtual", "Hybrid"]),
            F("DOI", "identifier", nl="grant_or_prize_amount"),
            DOC("Upload Published Paper / Proceedings Proof", "evidence_url", req=True),
            DOC("Upload Conference Presentation / Participation Certificate", "x_conference_certificate"),
            F("Published Paper / Proceedings URL", "venue_url", "url"),
            F("Remarks if Any", "x_remarks", "para"),
        ], defaults={"current_status": "Published"}, tile_words="conference paper proceedings"),
        block("Book / Book Chapters", "Enter the details of authored books, edited volumes and book chapters published by faculty members.", _RN, [
            TITLE("Title of the Book / Edited Volume / Book Chapter"),
            F("Type of Publication", "x_publication_type", "choice", req=True, choices=["Authored Book", "Edited Volume", "Book Chapter", "Others"]),
            F("ISBN / e-ISBN", "identifier", req=True, nl="grant_or_prize_amount"),
            _RS_COAUTHORS("Names of Co-authors / Contributors", req=True),
            F("Date of Publication", "output_date", "date", req=True, nl="event_date"),
            DOC("Upload Book Cover / Publication Proof", "evidence_url"),
            F("Publisher Website / Publication URL", "venue_url", "url"),
        ], defaults={"current_status": "Published"}, tile_words="book chapter isbn"),
        block("Funded Research Projects", "Enter the details of research projects funded or sponsored by government agencies, industries, research organizations "
                                          "and other funding bodies.", _RN, [
            TITLE("Title of the Research Project"),
            F("Name of the Funding Agency / Sponsoring Organization", "venue_publisher", req=True, nl="organization_or_venue"),
            F("Category of Funding Agency", "x_agency_category", "list", req=True, choices=[
                "Central Government Funding Agency", "State Government Funding Agency", "Government Research Organization", "Industry / Corporate Organization",
                "International Funding Agency", "Private Funding Organization", "University / Institutional Funding", "Others"]),
            F("Role in the Project", "contribution_statement", "choice", req=True, choices=[
                "Principal Investigator (PI)", "Co-Principal Investigator (Co-PI)", "Project Coordinator", "Co-Investigator", "Research Collaborator"]),
            _RS_COAUTHORS("Names of Co-Principal Investigators / Collaborators", req=True),
            F("Date of Project Proposal Submission", "x_proposal_date", "date", req=True),
            F("Date of Project Sanction", "output_date", "date", req=True, nl="event_date"),
            F("Project Duration", "x_project_duration", req=True),
            F("Total Sanctioned Amount (₹)", "funding_amount", "number", req=True, nl="grant_or_prize_amount"),
            F("Research Domain / Area", "x_research_domain", req=True),
            F("Objectives / Brief Description of the Project", "abstract", "para", req=True, nl="description"),
            F("Expected / Achieved Research Outcomes", "key_findings", "para", req=True),
            F("Industry / Institutional Collaboration (if any)", "collaborators", req=True, help="Write NA if there is none."),
            F("Related Publications / Project References", "related_refs", "para"),
            DOC("Upload Sanction Letter / Approval Document", "evidence_url", req=True),
            F("Project Status", "current_status", req=True),
            F("Project Website / Relevant URL (if any)", "venue_url", "url"),
        ], defaults={"funding_status": "Funded"}, tile_words="grant funding project dst serb"),
        block("Consultancy Projects", "Enter the details of consultancy projects undertaken by faculty members in collaboration with industries, corporate "
                                      "organizations, government departments and other external agencies.", _RN, [
            TITLE("Title of the Consultancy Project"),
            F("Name of the Client Organization / Industry", "venue_publisher", req=True, nl="organization_or_venue"),
            F("Category of Client Organization", "x_client_category", "list", req=True, choices=[
                "Private Industry", "Public Sector Undertaking (PSU)", "Government Department", "Startup", "MSME", "Educational Institution", "Research Organization", "Other"]),
            F("Nature of Consultancy", "x_nature_of_consultancy", "list", req=True, choices=[
                "Software Development", "AI / Machine Learning Solutions", "Data Analytics", "Cybersecurity Solutions", "Technical Consultancy",
                "Testing and Evaluation", "Training and Technical Support", "Research and Development"]),
            F("Role", "contribution_statement"),
            F("Date of Commencement", "output_date", "date", req=True, nl="event_date"),
            F("Project Duration", "x_project_duration", req=True),
            F("Total Consultancy Amount (₹)", "funding_amount", "number", req=True, nl="grant_or_prize_amount"),
            _RS_COAUTHORS("Names of Other Faculty Members / Collaborators Involved", req=True),
            F("Industry Contact Person / Designation", "x_industry_contact", req=True),
            F("Related Publications / Project References", "related_refs", "para"),
            F("Project Status", "current_status"),
            DOC("Upload Consultancy Agreement / Work Order", "evidence_url", req=True),
        ], defaults={"funding_status": "Funded"}, tile_words="consultancy industry client"),
        block("Patents & Intellectual Property Rights (IPR)", "Enter the details of patents and other intellectual property rights filed, published, registered "
                                                              "or granted by faculty members.", _RN, [
            TITLE("Title / Name of the Intellectual Property"),
            F("Application / Registration Number", "identifier", req=True, nl="grant_or_prize_amount"),
            F("Brief Description of the Invention / Intellectual Property", "abstract", "para", req=True, nl="description"),
            F("Revenue Generated through Commercialization (₹), if applicable", "x_revenue", "number"),
            F("Commercialization / Licensing Details", "ip_status", "para"),
            F("Type of Intellectual Property", "x_ip_type", "choice", choices=["Patent", "Copyright", "Industrial Design", "Trademark", "Software Copyright", "Other"]),
            _RS_COAUTHORS("Names of Inventors / Creators", req=True),
            F("Date of Filing / Application", "output_date", "date", req=True, nl="event_date"),
            F("Date of Publication (if applicable)", "x_publication_date", "date"),
            F("Date of Grant / Registration (if applicable)", "x_grant_date", "date"),
            F("Current Status", "current_status", "list", req=True, choices=[
                "Patents filed", "Patent published", "Patent granted", "Copyright registered", "Patent commercialized / licensed", "Design and trademark registered"]),
            F("Patent Classification / Technology Domain", "x_technology_area", req=True),
            F("Name of Co-applicant Institution / Organization (if any)", "collaborators", req=True, help="Write NA if there is none."),
            F("Country of Filing / Registration", "x_country", req=True),
            DOC("Upload Application / Publication / Grant Certificate", "evidence_url", req=True),
        ], tile_words="patent ip copyright design trademark"),
        block("Key Research Innovations & Technical Accomplishments", "Enter the details of significant research innovations, technical developments and "
                                                                      "technology-driven accomplishments achieved by faculty members.", _RN, [
            TITLE("Title of the Innovation / Technical Accomplishment"),
            F("Brief Description of the Innovation / Technical Achievement", "abstract", "para", req=True, nl="description"),
            F("Research Domain / Technology Area", "x_research_domain", req=True),
            F("Problem Addressed / Motivation Behind the Innovation", "problem", "para", req=True),
            _RS_COAUTHORS("Faculty Members Involved"),
            F("Student Contributors (if any)", "x_student_contributors", "para"),
            PHOTO("Upload Achievement Photo"),
            F("Has the innovation been implemented or deployed?", "x_deployed", "choice", choices=["Yes", "No"]),
            LINK("Supporting Document Link"),
        ], defaults={"current_status": "Completed"}, tile_words="innovation prototype technical"),
        block("Research Seminar", "Enter details about the research seminars hosted by the department.", _RN, [
            F("Research Scholar ID and Name", "x_scholar", req=True),
            F("Supervisor Name", "x_supervisor", req=True),
            TITLE("Title / Topic of the Research Seminar"),
            F("Date of the Seminar", "output_date", "date", req=True, nl="event_date"),
            F("Research Area / Domain", "x_research_domain", req=True),
            DOC("Upload Seminar Invitation / Circular", "evidence_url", req=True),
            PHOTO("Supporting Photographs"),
            F("Target Audience", "x_target_audience"),
            F("Number of participants", "x_participants", "number"),
        ], tile_words="seminar scholar phd"),
    ],
    "closing": [F(ACCURACY, "authorization_confirmed", "confirm", req=True, choices=ACCURACY_CHOICES)],
}

# ======================================================================================================== Faculty participation and achievements
_F1 = "Which achievement category would you like to fill first?"
_FN = "Which remaining achievement category would you like to fill next?"

FORMS["form_faculty"] = {
    "form_type": "FACULTY", "date_key": "start_date", "date_fallback": "timestamp",
    "title": "Faculty Participation and Achievements",
    "description": "Awards, certifications, invited lectures given, FDPs attended and professional roles.",
    "category_q": F("Achievement Category", "category", "choice", req=True, nl="category_id"),
    "common": ["Timestamp", "Email Address",
               F("Faculty Full Name", "emp_id", "faculty", req=True, submitter=True, nl="author_or_person", tf="names_only"),
               F("Designation", "designation_at_time", auto="designation")],
    "blocks": [
        block("Awards & Honors Received", "Awards, honors, recognitions, prizes and distinctions received by faculty members for their academic excellence, research "
                                          "contributions, professional achievements, innovation, leadership and contributions to society.", _F1, [
            TITLE("Exact Title of Award / Recognition"),
            F("Awarding Authority / Recognizing Institution / Organizing Organization", "host_org", req=True, nl="organization_or_venue"),
            F("Level", "level", "choice", req=True, choices=LEVELS, nl="impact_or_indexing"),
            F("Names, Affiliations and Roles of Other Contributors", "other_contributors", "para", help="Enter NA if none."),
            F("Name of the Organizing Institution / Conducting Agency", "x_conducting_agency", req=True),
            F("Date and Venue of the Award / Recognition Ceremony", "city_venue", help="Write the date and the venue, e.g. 12 March 2026, Chennai."),
            F("Additional highlights of the recognition if any.", "description", "para", nl="description"),
            PHOTO("Upload Achievement Photo"),
            LINK(),
        ], defaults={"recognition_type": "Award"}, date_text_key="city_venue", tile_words="award honour prize recognition"),
        block("Certifications & Upskilling Completed", "Certifications, professional training, online courses and other upskilling activities completed by faculty members "
                                                       "to enhance their technical, professional and domain-specific competencies.", _FN, [
            TITLE("Title of the Certification / Course Completed"),
            F("Mode of Learning", "x_mode", "choice", req=True, choices=["Online", "Offline", "Hybrid", "Self-paced Learning"]),
            F("Duration of the Course / Training", "x_duration", req=True),
            F("Date of Commencement", "start_date", "date", req=True),
            F("Date of Completion", "end_date", "date", req=True, nl="event_date"),
            F("Certification Level", "x_certification_level", "choice", req=True, choices=["Beginner", "Intermediate", "Advanced", "Expert"]),
            F("Key Skills / Competencies Acquired", "outcome_impact", "para", req=True),
            F("Conducting Body / Organizing Institution / Host Organization", "host_org", req=True, nl="organization_or_venue"),
            F("Score / Grade / Percentage Obtained (if applicable)", "x_score", req=True, help="Write NA if it does not apply."),
            F("How has this certification contributed to professional development or skill enhancement?", "description", "para", req=True, nl="description"),
            F("Level", "level", "choice", req=True, choices=LEVELS, nl="impact_or_indexing"),
            F("Official Webpage of the Organizing Institution / Certification Provider (URL)", "organizer_url", "url"),
            DOC("Upload Completion Certificate", "evidence_url", req=True, printed="Upload Completion certificate"),
        ], defaults={"recognition_type": "Certification"}, date_key="end_date", tile_words="certificate nptel course upskilling"),
        block("Invited Keynote / Expert Lectures Delivered", "Keynote addresses, invited talks, expert lectures, guest lectures and technical sessions delivered by faculty "
                                                             "members at academic institutions, professional bodies, industries and other organizations.", _FN, [
            TITLE("Title of the Keynote Address / Expert Lecture"),
            F("Nature of the Engagement", "recognition_type", "list", req=True, choices=[
                "Keynote Address", "Invited Talk", "Expert Lecture", "Guest Lecture", "Technical Talk", "Distinguished Lecture", "Panel Discussion", "Resource Person",
                "Workshop / Seminar Speaker", "Others"]),
            F("Topic / Area of Expertise", "x_topic", req=True),
            F("Name of the Event / Programme", "x_event_name", req=True),
            F("Organizing Institution / Host Organization", "host_org", req=True, nl="organization_or_venue"),
            F("Date of the Lecture", "start_date", "date", req=True, nl="event_date"),
            F("Venue of the Lecture", "city_venue", req=True),
            F("Mode of Delivery", "x_mode", "choice", req=True, choices=["Physical", "Online", "Hybrid"]),
            F("Duration of the Lecture (in Hours)", "duration_hours", "number", req=True),
            F("Approximate Number of Participants", "x_participants", "number", req=True),
            F("Target Audience", "x_target_audience", "multi", req=True, choices=[
                "Undergraduate Students", "Postgraduate Students", "Research Scholars", "Faculty Members", "Industry Professionals", "Others"]),
            F("Level of the Event", "level", "choice", req=True, nl="impact_or_indexing", choices=["International", "National", "State", "Regional", "Institutional"]),
            F("Organizer's Official Webpage / Event URL", "organizer_url", "url", req=True),
            DOC("Upload the Event Brochure / Programme Schedule", "x_brochure"),
            DOC("Upload Certificate of Appreciation / Recognition", "evidence_url"),
        ], tile_words="keynote lecture talk invited resource person"),
        # listed in the form's category question, but the form has no section for it yet: asked in the portal only, so the sheet's columns stay as they are
        block("Resource Person / Session Chair Roles", "Roles as a resource person, session chair or panel moderator at conferences, workshops and other academic events.", _FN, [
            TITLE("Title of the Session / Event"),
            F("Role", "recognition_type", "choice", req=True, choices=["Resource Person", "Session Chair", "Panel Moderator", "Others"]),
            F("Organizing Institution / Host Organization", "host_org", req=True, nl="organization_or_venue"),
            F("Level of the Event", "level", "choice", req=True, nl="impact_or_indexing", choices=["International", "National", "State", "Regional", "Institutional"]),
            F("Date of the Session", "start_date", "date", req=True, nl="event_date"),
            F("Venue", "city_venue", req=True),
            F("Mode of Participation", "x_mode", "choice", req=True, choices=["Physical", "Online", "Hybrid"]),
            F("Topic / Brief Description", "description", "para", req=True, nl="description"),
            DOC("Upload Certificate / Invitation Letter", "evidence_url"),
        ], portal_only=True, tile_words="resource person session chair moderator"),
        block("FDP / Workshops Attended", "Faculty Development Programmes (FDPs), workshops, seminars, training programmes, conferences and other professional development "
                                          "activities attended by faculty members to enhance their teaching, research, technical and professional competencies.", _FN, [
            TITLE("Title of the FDP / Workshop / Training Programme"),
            F("Nature of the Programme", "recognition_type", "list", req=True, choices=[
                "Faculty Development Programme (FDP)", "Short-Term Training Programme (STTP)", "Workshop", "Technical Workshop", "Seminar", "Conference", "Hands-on Training",
                "Training Programme", "Refresher Course", "Orientation Programme", "Online Certification Programme", "Others"]),
            F("Organizing Institution / Host Organization", "host_org", req=True, nl="organization_or_venue"),
            F("Programme Level", "level", "choice", req=True, choices=LEVELS, nl="impact_or_indexing"),
            F("Conducting Body / Sponsoring Agency", "x_conducting_body"),
            F("Collaborating Institution / Industry (if applicable)", "x_collaborating", req=True, help="Write NA if there is none."),
            F("Mode of Participation", "x_mode", "choice", req=True, choices=["Online", "Offline", "Hybrid"]),
            F("Venue / Location (If Applicable)", "city_venue", req=True, help="Write NA if there is none."),
            F("Start Date", "start_date", "date", req=True, nl="event_date"),
            F("End Date", "end_date", "date", req=True),
            F("Major Topics / Domains Covered", "x_topic", "para"),
            F("Relevance to Teaching, Research or Professional Development", "description", "para", req=True, nl="description"),
            DOC("Upload Participation / Completion Certificate", "x_participation_certificate"),
            LINK(),
            F("Additional Remarks", "extra_notes", "para"),
        ], tile_words="fdp workshop training attended sttp"),
        block("Membership in Professional Body & Editorial Board Roles", "Details related to professional body memberships and editorial board roles.", _FN, [
            F("Name of the Professional Body / Society / Association", "x_professional_body"),
            F("Type of Membership", "recognition_type", "list", choices=[
                "Annual Membership", "Life Membership", "Fellow", "Senior Member", "Associate Member", "Student Member", "Institutional Representative", "Others"]),
            F("Membership ID / Registration Number", "credential_no"),
            F("Membership Category / Grade", "x_membership_grade"),
            F("Date of Membership", "start_date", "date", nl="event_date"),
            F("Membership Validity", "x_validity", "choice", choices=["Lifetime", "Annual", "Multi-year", "Not Applicable"]),
            F("Official Website of the Professional Body", "organizer_url", "url"),
            DOC("Upload Supporting Document", "evidence_url"),
            F("Nature of Professional Role", "role_contribution", "list", choices=[
                "Editor-in-Chief", "Associate Editor", "Managing Editor", "Editorial Board Member", "Guest Editor", "Section Editor", "Reviewer / Peer Reviewer",
                "Advisory Board Member", "Conference Editorial Committee Member", "Technical Programme Committee Member", "Others"]),
            F("Name of the Journal / Publication / Conference", "x_journal_name"),
            F("Publisher / Organizing Institution", "host_org", nl="organization_or_venue"),
            F("ISSN / ISBN / DOI (if applicable)", "x_issn"),
            F("Subject Area / Editorial Domain", "x_subject_area"),
            F("Date of Appointment / Joining", "x_appointment_date", "date"),
            F("Tenure / Duration of the Role", "x_tenure"),
            F("Official Journal / Editorial Board Webpage (URL)", "x_editorial_url", "url"),
            DOC("Upload Editorial Board Appointment Letter / Confirmation", "x_appointment_letter"),
        ], title_from=["x_professional_body", "x_journal_name", "role_contribution", "recognition_type"], tile_words="membership editorial reviewer ieee professional body"),
    ],
    "closing": [F(ACCURACY, "authorization_confirmed", "confirm", req=True, choices=ACCURACY_CHOICES)],
}

# ======================================================================================================== Department milestones & achievements
_D = "Select the category you want to complete"
_D_PHOTO = lambda title="Upload Supporting Photo", req=False, printed=None: PHOTO(title, req, printed)

FORMS["form_departmental"] = {
    "form_type": "DEPARTMENT", "date_key": "start_date", "date_fallback": "timestamp",
    "title": "Department Milestones & Achievements",
    "description": "Department of Information Technology: milestones, events, infrastructure, partnerships and other highlights of the department.",
    "category_q": F("Department Highlight Category", "category", "choice", req=True, nl="category_id"),
    "common": ["Timestamp", "Email Address", F("Faculty Name", "_submitter", req=True, submitter=True, nl="author_or_person"),
               F("Designation", "x_department_designation", auto="designation"), F("Faculty Email", "x_faculty_email", auto="email")],
    "blocks": [
        block("Departmental Achievements / Awards / Recognitions", "Awards, recognitions, prizes and significant achievements of the department.", _D, [
            F("Overview and Key Highlights of the recognition / achievement / award", "overview", "para", req=True, nl="description",
              printed="Overview and Key Highlights of the recognition/achievement/ award"),
            F("Validity period with date (mention NA if not applicable)", "x_validity", req=True, printed="Validity period with date ( mention NA if not applicable)"),
            F("Enter the name of the organization or institution that conferred the award.", "partner_bodies", req=True, nl="organization_or_venue"),
            F("Members involved from department", "x_members", "para", req=True),
            _D_PHOTO(),
            LINK(),
        ], title_from=["overview"], tile_words="award recognition achievement"),
        block("Events / Programs Conducted", "Workshops, seminars, guest lectures, expert talks, training programmes and other short-term programmes conducted by the department.", _D, [
            TITLE("Title of the Event"),
            F("Event Overview and Key Highlights", "overview", "para", req=True, nl="description"),
            F("Objectives and Rationale", "objectives", "para", req=True),
            F("Event Date and Venue", "venue", req=True, help="Write the date and the venue, e.g. 12 March 2026, Seminar Hall."),
            F("Organising Department(s)", "units_involved", req=True),
            F("Faculty Coordinators", "x_coordinators", "para", req=True),
            F("Number of Participants", "participant_count", "number", req=True),
            F("Category of Participants (Students / Faculty Members / Non-teaching staff)", "target_audience", req=True,
              printed="Category of Participants (Students/Faculty Members/Non teaching staffs)"),
            F("Name of the Resource Person", "x_resource_person", req=True, printed="Name of the Resource person"),
            F("Designation and Institution / Organisation / Industry name of the Resource person(s)", "x_resource_designation", "para", req=True,
              printed="Designation and Institution/organistion/industry name of the Resource person(s)"),
            F("Key Outputs / Deliverables", "outputs", "para"),
            F("Measurable Impact / Success Indicators", "success_indicators", "para"),
            F("Sustainability / Continuation Plan", "sustainability", "para"),
            F("Related Initiatives / Previous Milestones", "related_initiatives", "para"),
            _D_PHOTO(),
            DOC("Official Evidence / Brochure / Attendance / Supporting Document", "evidence_url", req=True, printed="Official Evidence / Brochure/ Attandance / Supporting Document"),
        ], date_text_key="venue", tile_words="event workshop seminar guest lecture training programme"),
        block("Infrastructure / Laboratory Development", "Laboratory upgrades, equipment procurement and infrastructure development activities.", _D, [
            F("Infrastructure / Laboratory Upgrade Details", "infra_upgrade", "para", req=True, nl="description"),
            F("Objectives and Rationale", "objectives", "para"),
            F("Equipment / Software / Facilities Procured", "x_equipment_procured", "para"),
            F("Installation / Commissioning Date", "start_date", "date", nl="event_date"),
            F("Budget Allocated (in Rs.) and Source of Funding", "x_budget_and_source", req=True),
            F("Measurable Impact", "success_indicators", "para"),
            F("Challenges and Mitigation", "challenges", "para"),
            F("Sustainability / Maintenance Plan", "sustainability", "para"),
            F("Related Infrastructure Initiatives", "related_initiatives", "para"),
            _D_PHOTO(),
            DOC("Official Evidence / Bills / Supporting Document", "evidence_url", req=True, printed="Official Evidence / Bills / Supporting Document Link"),
        ], title_from=["infra_upgrade"], tile_words="lab infrastructure equipment"),
        block("MoU / Industry Collaboration / Partnerships", "Industry partnerships, institutional collaborations and MoUs.", _D, [
            F("Industry / Organisation Details", "partner_bodies", "para", req=True, nl="organization_or_venue", printed="Industry/Organisation Details"),
            F("Key Objectives of collaboration", "objectives", "para", req=True, nl="description"),
            F("Validity Period with date", "x_validity", req=True),
            F("MoU Start Date", "agreement_effective", "date", req=True, nl="event_date", portal_only=True),
            F("MoU Expiry Date", "agreement_expiry", "date", help="Leave empty if the agreement has no end date. The dashboard flags MoUs that expire within 90 days.", portal_only=True),
            F("Faculty In-charge / Co-ordinators Detail", "x_coordinators", "para", req=True, printed="Favulty In-charge / Co-ordinators Detail"),
            _D_PHOTO("Upload Supporting Photos"),
            DOC("Official Evidence / Certificate / Supporting Document", "evidence_url", printed="Official Evidence / Certificate / Supporting Document Link"),
        ], date_key="agreement_effective", title_from=["partner_bodies"], title_prefix="Collaboration with ", tile_words="mou partnership collaboration"),
        block("Faculty Development Programmes (FDPs), Conferences, and Other Long-Term Programmes Organised",
              "FDPs, conferences and professional training programmes conducted by the department.", _D, [
            TITLE("Title of the Programme"),
            F("Details of Organising Committee", "x_committee", "para", req=True),
            F("Key highlights / Objectives of the Programme", "overview", "para", req=True, nl="description"),
            F("Sponsorship Details", "x_sponsorship", "para", req=True),
            F("Date(s) and Venue of the Programme", "venue", req=True, printed="Date(s) and Venue the Programme"),
            F("Resource persons' details with designation and organisation (date wise)", "x_resource_persons", "para", req=True,
              printed="Resource persons Details with designation and organisation (Date wise)"),
            DOC("Upload all supporting photographs combined into a single file.", "x_photo_collection", req=True),
            DOC("Official Evidence / Brochure / Supporting Documents", "evidence_url", req=True, printed="Official Evidence / Brochure/ Supporting Documents"),
        ], date_text_key="venue", tile_words="fdp conference long term programme organised"),
        block("Student Development, Outreach, and Social Initiatives Undertaken by the Department",
              "Student development, outreach, social initiatives and community engagement.", _D, [
            F("Key objectives of the Initiative", "overview", "para", req=True, nl="description"),
            F("Partnership / Sponsorship / Other Organisations involved", "partner_bodies", req=True, nl="organization_or_venue",
              printed="Partnership/Sponsorship/Other Organisations involved"),
            F("Number of students participated", "participant_count", "number", req=True),
            F("Date and Venue of the Programme", "venue", req=True),
            DOC("Official Evidence / Certificate / Attendance / Supporting Document", "evidence_url", req=True,
                printed="Official Evidence / Certificate/Attandence / Supporting Document"),
        ], title_from=["overview"], date_text_key="venue", tile_words="student development outreach social community"),
        block("Accreditation / Quality Assurance / Institutional Initiatives",
              "NBA, NAAC, NIRF accreditation, ranking and other institutional quality assessment visits.", _D, [
            F("What was the nature of the institutional visit?", "highlight_type", "list", req=True, choices=[
                "NBA Accreditation Visit", "NAAC Assessment Visit", "NIRF-related Visit", "ISO Audit", "Anna University Inspection / Affiliation Visit",
                "Academic and Institutional Quality Audit", "Other Quality Assessment Visits"]),
            F("Date of Visit", "start_date", "date", req=True, nl="event_date"),
            F("What was the outcome / status of the visit?", "impl_status", req=True, printed="What was the outcome/status of the visit?"),
            F("Enter additional remarks or significant outcomes of the visit.", "overview", "para", req=True, nl="description"),
            _D_PHOTO(),
        ], title_from=["highlight_type"], tile_words="nba naac nirf accreditation audit quality"),
        block("Other Significant Highlights", "Important activities not covered by the above categories.", _D, [
            F("Key objectives of the Highlights", "overview", "para", req=True, nl="description"),
            _D_PHOTO(),
            LINK(),
        ], title_from=["overview"], tile_words="other highlight"),
    ],
    "closing": [
        F("Budget / Investment in Rupees (numbers only)", "budget_amount", "number", req=True),
        F("Funding Source", "funding_source", req=True),
        F(ACCURACY, "authorization_confirmed", "confirm", req=True, choices=ACCURACY_CHOICES),
    ],
}

# ======================================================================================================== Industry, alumni & outreach
_I1 = "Which activity category would you like to fill first?"
_IN = "Which remaining activity category would you like to fill next?"

FORMS["form_industry"] = {
    "form_type": "OUTREACH", "date_key": "start_date", "date_fallback": "timestamp",
    "title": "Industry, Alumni & Outreach",
    "description": "Industry visits organized for students, interactions and engagements with department alumni, and community outreach initiatives "
                   "undertaken by the Department of Information Technology.",
    "category_q": F("Activity Category", "category", "choice", req=True, nl="category_id"),
    "common": ["Timestamp", "Email Address", F("Faculty name", "_submitter", "faculty", req=True, submitter=True, nl="author_or_person", tf="names_only")],
    "blocks": [
        block("Industrial Visits & Field Tours", "Industrial visits and field tours organized by the Department.", _I1, [
            TITLE("Title / Name of the Visit"),
            F("Name of the Industry / Organization Visited", "_partner", req=True, nl="organization_or_venue"),
            F("Location of the Organization", "venue", req=True),
            F("Date of Visit", "start_date", "date", req=True, nl="event_date"),
            F("Objective / Purpose of the Visit", "objective", "para", req=True, nl="description"),
            F("Class / Year of Students", "target_audience", req=True),
            F("Number of Students Participated", "actual_count", "number", req=True),
            F("Number of Faculty Coordinators", "x_faculty_coordinators", "number", req=True),
            F("Measurable Outcomes", "measurable_outcomes", "para", req=True),
            PHOTO("Upload Supporting Photographs", req=True),
            DOC("Upload Visit Report (if available)", "evidence_url"),
        ], tile_words="industrial visit tour field"),
        block("Industry Expert Lectures & Technical Talks", "Expert lectures, technical talks, invited sessions and knowledge-sharing interactions delivered by industry professionals.", _IN, [
            TITLE("Title / Topic of the Lecture or Technical Talk"),
            F("Name of the Resource Person", "speakers", req=True),
            F("Designation of the Resource Person", "x_speaker_designation", req=True),
            F("Organization / Company / Institution", "_partner", req=True, nl="organization_or_venue"),
            F("Professional Profile / Area of Expertise", "summary_outcomes", "para", req=True, nl="description"),
            F("Nature of the Session", "activity_format", "list", req=True, choices=[
                "Industry Expert Lecture", "Technical Talk", "Invited Lecture", "Expert Interaction", "Emerging Technology Session", "Career Guidance / Industry Insights",
                "Hands-on Technical Session", "Panel Discussion", "Other"]),
            F("Venue / Mode of Delivery", "venue", "choice", req=True, choices=["On-campus – Physical", "Online", "Hybrid"]),
            F("Target Audience", "target_audience", req=True),
            PHOTO("Upload Event Photo"),
        ], tile_words="expert talk lecture guest technical"),
        block("MoUs Signed & Industrial Collaborations", "Memoranda of Understanding signed and collaborations established with industries and other organizations.", _IN, [
            TITLE("Title of the MoU / Collaboration"),
            F("Industry / Organization Name", "_partner", req=True, nl="organization_or_venue"),
            F("Nature of Collaboration", "activity_format", req=True),
            F("Scope and Objectives of the Collaboration", "mou_scope", "para", req=True, nl="description"),
            F("MoU Start Date", "agreement_effective", "date", req=True, nl="event_date"),
            F("MoU Expiry Date", "agreement_expiry", "date", help="Leave empty if the agreement has no end date. The dashboard flags MoUs that expire within 90 days."),
            F("Signatories / Partner Representatives", "speakers", "para"),
            F("Faculty Coordinator(s)", "x_coordinators", "para", req=True),
            PHOTO("Upload Supporting Photographs"),
            DOC("Upload Signed MoU / Supporting Document", "evidence_url"),
        ], date_key="agreement_effective", copy={"start_date": "agreement_effective"}, portal_only=True, tile_words="mou collaboration partnership agreement"),
        block("Alumni Interactions & Mentorship Sessions", "Alumni interactions and mentorship sessions organized by the department.", _IN, [
            TITLE("Title / Topic of the Alumni Interaction or Mentorship Session"),
            F("Name of the Alumni", "speakers", req=True),
            F("Batch / Year of Graduation", "x_alumni_batch", req=True),
            F("Current Designation", "x_speaker_designation", req=True),
            F("Organization / Company", "_partner", req=True, nl="organization_or_venue"),
            F("Area of Expertise / Professional Domain", "x_expertise", req=True),
            F("Nature of Alumni Engagement", "activity_format", req=True),
            F("Date of the Session", "start_date", "date", req=True, nl="event_date"),
            F("Target Audience", "target_audience", req=True),
            F("Duration of the Session", "x_duration", req=True),
            PHOTO("Upload Supporting Photographs", req=True),
            F("Brief Description of the Interaction / Mentorship Activity", "summary_outcomes", "para", req=True, nl="description"),
        ], defaults={"partner_type": "Alumni"}, tile_words="alumni mentor interaction"),
        block("Community & Social Outreach Initiatives", "Community engagement and social outreach initiatives undertaken by the Department to create awareness, promote "
                                                         "social responsibility and contribute to societal development.", _IN, [
            TITLE("Title / Name of the Outreach Activity"),
            F("Category of Outreach Initiative", "activity_format", req=True),
            F("Organizing / Collaborating Organization", "_partner", req=True, nl="organization_or_venue"),
            F("Date of the Activity", "start_date", "date", req=True, nl="event_date"),
            F("Venue / Location", "venue", req=True),
            F("Objective / Purpose of the Activity", "objective", "para", req=True),
            F("Key Outcomes / Social Impact", "summary_outcomes", "para", req=True, nl="description"),
            F("Faculty Coordinator(s)", "x_coordinators", "para", req=True),
            PHOTO("Upload Supporting Photographs"),
            DOC("Upload Activity Report / Supporting Documents", "evidence_url"),
        ], tile_words="outreach community social camp"),
    ],
    "closing": [F(ACCURACY, "authorization_confirmed", "confirm", req=True, choices=ACCURACY_CHOICES)],
}

# ======================================================================================================== Student participation and achievements
STUDENT_CATEGORIES = [
    ("Technical Competitions", "technical competition contest"), ("Hackathons / Coding Competitions", "hackathon coding contest"),
    ("Paper Presentations", "paper presentation"), ("Project Presentations / Exhibitions", "project exhibition expo"), ("Technical Symposiums", "symposium"),
    ("Innovation / Startup Competitions", "innovation startup"), ("Research Publications / Patents", "research publication patent"),
    ("Professional Certifications", "certificate certification nptel"), ("Internships / Industrial Training", "internship industrial training"),
    ("Workshops / Technical Training", "workshop training"), ("Sports Achievements", "sports"), ("Cultural Activities", "cultural dance music arts"),
    ("NSS / NCC / Social Service", "nss ncc social service volunteering"), ("Leadership / Student Association Activities", "leadership association club"), ("Others", "other"),
]
_STUDENT_FIELDS = [
    F("Achievement or Participation", "entry_kind", "choice", req=True, choices=["Achievement (won, ranked or awarded)", "Participation only"],
      help="Choose Participation only when students participated without winning or ranking."),
    F("Student Roll Numbers", "_participants", "roster_roll", req=True, nl="author_or_person", tf="names_only", printed="Name of the Student and Roll Number",
      help="Enter roll numbers only, one per line (the first is the lead). Names are filled in from the college records."),
    F("Faculty Mentor / Coordinator", "mentor_emp_id", "faculty"),
    F("Year of Study", "x_year_of_study", req=True),
    F("Programme / Section", "x_programme_section", req=True),
    F("Academic Year", "x_academic_year", req=True),
    F("Student's LinkedIn Profile / Portfolio URL", "demo_url", req=True, help="Enter NA if there is none."),
    F("Title of the Event / Certification Programme / Competition", "title", req=True, nl="title"),
    F("Nature of Participation", "x_nature_of_participation", "list", req=True, choices=[
        "Participant", "Winner", "Runner-up", "Prize Winner", "Finalist", "Presenter", "Organizer / Volunteer", "Team Leader", "Certification Candidate", "Others"]),
    F("Level of Participation", "level", "choice", req=True, nl="impact_or_indexing", choices=[
        "Department Level", "Institution Level", "Inter-College Level", "District Level", "State Level", "National Level", "International Level"]),
    F("Name of the Organizing Institution / Organization", "organizer", req=True, nl="organization_or_venue"),
    F("Venue / Location", "x_venue", req=True),
    F("Date of the Event", "result_date", "date", req=True, nl="event_date"),
    F("Duration of the event", "x_duration", req=True),
    F("Was any prize money / cash award received?", "x_prize_received", "choice", req=True, choices=["Yes", "No"]),
    F("Award Amount (in ₹), if applicable", "prize_amount", "number"),
    F("Key Skills / Competencies Demonstrated / Skills Developed", "learning_outcomes", "para", req=True),
    F("Brief Description of the Activity / Achievement", "abstract", "para", req=True, nl="description"),
    F("Position / Award / Recognition Received", "position", req=True, nl="grant_or_prize_amount", help="Enter NA if it does not apply."),
    DOC("Upload Supporting Certificate / Evidence", "evidence_url", req=True),
]

FORMS["form_student"] = {
    "form_type": "STUDENT", "date_key": "result_date",
    "title": "Student Participation and Achievements",
    "description": "Achievements in technical competitions, hackathons, coding contests, project exhibitions, paper presentations, sports, cultural events, "
                   "professional certifications and other notable activities at institutional, national and international levels.",
    "category_q": F("Category of Participation / Achievement", "category", "choice", req=True, nl="category_id"),
    "flat": True,                                          # one set of questions for every category; the sheet has one column per question
    "common": ["Timestamp", "Email Address"],
    "blocks": [block(name, "", "", [], tile_words=words) for name, words in STUDENT_CATEGORIES],
    "flat_fields": _STUDENT_FIELDS,
    "category_after": "Title of the Event / Certification Programme / Competition",
    "closing": [],
}

# ======================================================================================================== Placement (the student placement diary)
# The sections the student fills are the three cards. "About you" is known from the college records and the class tutor; nothing asks for consent.
_P = lambda key, q, type="text", req=False, choices=None, aliases=None: {k: v for k, v in
    (("key", key), ("q", q), ("type", type), ("req", req), ("choices", choices), ("aliases", aliases)) if v or k == "req"}
_S = lambda q, description="": {"q": q, "type": "section", "description": description}

PLACEMENT = [
    _S("A. You"),
    _P("roll_no", "Roll Number", "roll", True),
    _P("ay_id", "Placement Academic Year", "years", True, ["2024-25", "2025-26", "2026-27", "2027-28", "2028-29", "Other"]),
    _P("opt_status", "Placement Preference", "choice", True, ["Opted In", "Opted Out"]),
    _P("opt_out_reason", "Reason for Opting Out (Complete only if Opted Out)", "list", False,
       ["Higher Studies", "Entrepreneurship / Startup", "Personal Reasons", "Family Reasons", "Competitive Examination Preparation", "Other"],
       ["Reason for Opting Out (only if Opted Out)"]),
    _S("B. Offer Details", "Placement offer details."),
    _P("offer_type", "Type of offer", "choice", False, ["Intern Only", "Intern + Full Time", "Full Time Only", "Intern-Converted FTE"], ["Offer Type"]),
    _P("company", "Company Name"),
    _P("sector", "Company Sector", "list", False, ["IT / Software", "Core Engineering", "Consulting", "Finance / Banking", "Manufacturing", "Healthcare", "Education",
                                                   "Research", "Government / Public Sector", "Others"]),
    _P("package_lpa", "Package in LPA", "number", False, None, ["Package in LPA (numbers only, for FTE offers)"]),
    _P("stipend_per_month", "Internship Stipend in Rupees per Month", "number", False, None, ["Internship Stipend in Rupees per Month (numbers only)"]),
    _P("job_role", "Job Role"),
    _P("work_location", "Work Location"),
    _P("offer_status", "Offer Status", "choice", False, ["Accepted", "Declined", "Pending"]),
    _P("recruitment_mode", "Recruitment Mode", "choice", False, ["On-campus", "Off-campus"]),
    _P("offer_date", "Offer Date", "date"),
    _P("offer_photo", "Upload Supporting Photo (offer)", "photo"),
    _S("C. Interview Experience", "How the selection process went."),
    _P("rounds_count", "Number of Interview Rounds", "number"),
    _P("round_details", "Round-wise Details", "para", False, None, ["Round-wise Details (e.g. Online Test, Technical 1, Technical 2, HR)"]),
    _P("difficulty", "Interview Difficulty", "choice", False, ["Easy", "Medium", "Hard"]),
    _P("questions_asked", "Questions Asked", "para"),
    _P("result", "Interview Result", "choice", False, ["Selected", "Rejected", "Waitlisted"]),
    _P("interview_concepts", "Academic Concepts and Technical Skills Assessed During the Interview", "para"),
    _P("interview_experience", "Your Interview Experience", "para"),
    _P("tips", "Tips for Juniors", "para"),
    _P("interview_photo", "Upload Supporting Photo (interview)", "photo"),
    _S("D. Internship Experience", "What you did and learned in the internship."),
    _P("intern_duration", "Internship Duration", "text", False, None, ["Internship Duration (e.g. 6 months)"]),
    _P("intern_mode", "Internship Mode", "choice", False, ["Onsite", "Remote", "Hybrid"]),
    _P("intern_role", "Internship Role"),
    _P("intern_concepts", "Academic Concepts and Skills Applied in the Internship", "para"),
    _P("tech_stack", "Technologies Used in Internship"),
    _P("work_summary", "Work Summary", "para"),
    _P("learnings", "Key Learnings", "para"),
    _P("rating", "Internship Rating", "choice", False, ["1", "2", "3", "4", "5"], ["Internship Rating (1 = Poor, 5 = Excellent)"]),
    _P("internship_experience", "Your Internship Experience", "para"),
    _P("internship_photo", "Upload Supporting Photo (internship)", "photo"),
    _S("E. Consent"),
    _P("consent", "Consent to Share Experience Anonymously", "choice", False, ["Yes - share anonymously with juniors", "No - keep private"]),
    _P("authorization_confirmed", "Accuracy Confirmation", "confirm", False, ["I confirm the information is accurate."]),
]
PLACEMENT_META = {"title": "Student Placement Diary", "description": "Enter information regarding the placement status and recruitment details of students."}
