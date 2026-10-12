/**
 * ==============================================================================
 * IT CHRONICLES - MASTER GOOGLE FORMS GENERATOR (SINGLE SCRIPT FILE)
 * ==============================================================================
 * 
 * INSTRUCTIONS FOR GOOGLE APPS SCRIPT:
 * 1. Open Google Apps Script: https://script.google.com
 * 2. Click "+ New project".
 * 3. Delete any default code in 'Code.gs' and paste this ENTIRE file.
 * 4. Select 'buildAllMasterForms' from the function dropdown at the top.
 * 5. Click "Run" (Grant permissions if requested by Google).
 * 6. Check the Execution Log at the bottom for all generated Edit & Public URLs.
 * 
 * ==============================================================================
 */

/**
 * Master execution function to generate all 5 IT Chronicles Google Forms in one go.
 */
function buildAllMasterForms() {
  Logger.log("=================================================");
  Logger.log(" Starting Automated Master Forms Creation Process");
  Logger.log("=================================================\n");

  const results = [];

  results.push(createResearchForm());
  results.push(createFacultyForm());
  results.push(createStudentForm());
  results.push(createIndustryForm());
  results.push(createDepartmentalForm());

  Logger.log("\n=================================================");
  Logger.log("   ALL 5 MASTER GOOGLE FORMS CREATED SUCCESSFULLY  ");
  Logger.log("=================================================\n");

  results.forEach((item, index) => {
    Logger.log(`[Form ${index + 1}] ${item.title}`);
    Logger.log(` -> Edit URL:      ${item.editUrl}`);
    Logger.log(` -> Published URL: ${item.publishedUrl}\n`);
  });

  return results;
}

/**
 * 1. Research & Innovation Submission Form Creator
 */
function createResearchForm() {
  const form = FormApp.create("IT Chronicles - Research & Innovation Submission Form");
  form.setDescription("Official submission form for Research & Innovation content for the IT Chronicles Newsletter.\nData submitted here will be automatically formatted into the modern newsletter magazine layout.");
  form.setCollectEmail(true);
  form.setAllowResponseEdits(true);

  // Submitter Info
  form.addTextItem().setTitle("Submitter Full Name").setRequired(true);
  form.addTextItem().setTitle("Submitter Email").setRequired(true);
  form.addTextItem().setTitle("Submitter Department / Designation").setRequired(true);

  // Category Selection
  const categoryItem = form.addMultipleChoiceItem();
  categoryItem.setTitle("Research Subcategory")
    .setRequired(true)
    .setChoiceValues([
      "Journal Publications",
      "Conference Publications",
      "Book / Book Chapters",
      "Funded Research Projects",
      "Consultancy Projects",
      "Patents & Intellectual Property",
      "Key Research Innovations & Technical Accomplishments"
    ]);

  // Common Entry Fields
  form.addTextItem().setTitle("Title of Publication / Patent / Project / Innovation").setRequired(true);
  form.addParagraphTextItem().setTitle("Authors / Investigators / Team Members").setHelpText("List names separated by commas").setRequired(true);
  form.addTextItem().setTitle("Venue / Journal / Publisher / Funding Agency / Organization").setRequired(true);
  form.addTextItem().setTitle("Date of Publication / Award / Grant").setHelpText("Format: YYYY-MM-DD or Month YYYY").setRequired(true);

  // Impact / Indexing / Financial Info
  form.addTextItem().setTitle("Impact Factor / Indexing (e.g., Scopus, Web of Science, IEEE, Q1/Q2)").setRequired(false);
  form.addTextItem().setTitle("Key Impact Badge / Metric").setHelpText("Short badge tag for newsletter pills (e.g. Scopus Q1, IEEE Xplore, Patent Granted, ₹15 Lakhs)").setRequired(false);
  form.addTextItem().setTitle("DOI / Patent Number / Grant Amount / URL Link").setRequired(false);

  // Description / Abstract
  form.addParagraphTextItem().setTitle("Abstract / Executive Summary / Highlights").setRequired(true);

  // Media & Visuals
  form.addTextItem().setTitle("Photo Link (Google Drive / Cloud URL)").setHelpText("High-resolution image link for newsletter inclusion (Set sharing to 'Anyone with link can view')").setRequired(false);
  form.addTextItem().setTitle("Photo Caption & Persons in Image").setHelpText("Brief description of image or names of persons shown (e.g., 'Left to Right: Dr. Smith, Dr. Jenkins receiving award')").setRequired(false);
  form.addTextItem().setTitle("Evidence / Certificate Link (Google Drive / Document URL)").setRequired(false);

  // Spotlight nomination
  const milestoneItem = form.addMultipleChoiceItem();
  milestoneItem.setTitle("Is this a Landmark / Milestone Achievement?")
    .setHelpText("Nominate for top Spotlight / Hero story card in the newsletter")
    .setRequired(true)
    .setChoiceValues([
      "No (Standard Entry)",
      "Yes (Nominate for Spotlight Feature)"
    ]);

  const editUrl = form.getEditUrl();
  const publishedUrl = form.getPublishedUrl();

  Logger.log("✓ Research & Innovation Form Created!");
  Logger.log("  Edit URL: " + editUrl);

  return {
    title: form.getTitle(),
    editUrl: editUrl,
    publishedUrl: publishedUrl
  };
}

/**
 * 2. Faculty Achievements Submission Form Creator
 */
function createFacultyForm() {
  const form = FormApp.create("IT Chronicles - Faculty Achievements Submission Form");
  form.setDescription("Official submission form for Faculty Achievements, Awards, Certifications, & Guest Lectures.");
  form.setCollectEmail(true);

  form.addTextItem().setTitle("Faculty Full Name").setRequired(true);
  form.addTextItem().setTitle("Designation & Department").setRequired(true);

  const categoryItem = form.addMultipleChoiceItem();
  categoryItem.setTitle("Achievement Category")
    .setRequired(true)
    .setChoiceValues([
      "Awards & Honors Received",
      "Certifications & Upskilling Completed",
      "Invited Keynote / Expert Lectures Delivered",
      "Resource Person / Session Chair Roles",
      "FDP / Workshops Attended",
      "Professional Body & Editorial Board Roles"
    ]);

  form.addTextItem().setTitle("Title of Award / Certification / Keynote / Workshop").setRequired(true);
  form.addTextItem().setTitle("Organization / Host Institution / Awarding Body").setRequired(true);
  form.addTextItem().setTitle("Date of Event / Award / Completion").setRequired(true);
  form.addTextItem().setTitle("Level (International / National / State / University)").setRequired(false);
  form.addTextItem().setTitle("Key Impact Badge / Metric").setHelpText("Short badge tag for newsletter pill (e.g. Best Faculty Award, Keynote Speaker, NPTEL Gold)").setRequired(false);
  form.addParagraphTextItem().setTitle("Description & Key Highlights").setRequired(true);
  form.addTextItem().setTitle("Photo Link (Google Drive / Cloud URL)").setHelpText("High-resolution photograph (Ensure sharing is public)").setRequired(false);
  form.addTextItem().setTitle("Photo Caption & Persons in Image").setHelpText("Names of individuals in photograph or event scene").setRequired(false);
  form.addTextItem().setTitle("Evidence / Certificate Link (Google Drive URL)").setRequired(false);

  const milestoneItem = form.addMultipleChoiceItem();
  milestoneItem.setTitle("Is this a Landmark / Milestone Achievement?")
    .setHelpText("Nominate for top Spotlight / Hero story card in the newsletter")
    .setRequired(true)
    .setChoiceValues([
      "No (Standard Entry)",
      "Yes (Nominate for Spotlight Feature)"
    ]);

  const editUrl = form.getEditUrl();
  const publishedUrl = form.getPublishedUrl();

  Logger.log("✓ Faculty Achievements Form Created!");
  Logger.log("  Edit URL: " + editUrl);

  return {
    title: form.getTitle(),
    editUrl: editUrl,
    publishedUrl: publishedUrl
  };
}

/**
 * 3. Student Achievements Submission Form Creator
 */
function createStudentForm() {
  const form = FormApp.create("IT Chronicles - Student Achievements Submission Form");
  form.setDescription("Official submission form for Student Competitions, Hackathons, Placements, and Co-Curricular Achievements.");
  form.setCollectEmail(true);

  form.addTextItem().setTitle("Student Name(s)").setHelpText("List names of all team members").setRequired(true);
  form.addTextItem().setTitle("Roll Number / USN & Semester/Section").setRequired(true);

  const categoryItem = form.addMultipleChoiceItem();
  categoryItem.setTitle("Student Achievement Category")
    .setRequired(true)
    .setChoiceValues([
      "Academic Excellence & Ranks",
      "Hackathons & Coding Competitions",
      "Higher Education & Top Placements",
      "Technical Projects & Innovations",
      "Sports, Cultural & Co-Curricular Accomplishments"
    ]);

  form.addTextItem().setTitle("Name of Competition / Award / Project / Event").setRequired(true);
  form.addTextItem().setTitle("Organizing Institute / Company / Body").setRequired(true);
  form.addTextItem().setTitle("Position / Rank / Prize / CTC (e.g. 1st Place, Cash Prize of $1000)").setRequired(true);
  form.addTextItem().setTitle("Key Impact Badge / Metric").setHelpText("Short badge pill (e.g. 1st Prize, Cash Award ₹50k, 24 LPA CTC)").setRequired(false);
  form.addTextItem().setTitle("Date of Event / Award").setRequired(true);
  form.addParagraphTextItem().setTitle("Project Abstract / Achievement Details").setRequired(true);
  form.addTextItem().setTitle("Photo Link (Google Drive / Cloud URL)").setHelpText("High-resolution team/award photograph").setRequired(false);
  form.addTextItem().setTitle("Photo Caption & Persons in Image").setHelpText("List student names in photo from left to right").setRequired(false);
  form.addTextItem().setTitle("Certificate / Proof Link").setRequired(false);

  const milestoneItem = form.addMultipleChoiceItem();
  milestoneItem.setTitle("Is this a Landmark / Milestone Achievement?")
    .setHelpText("Nominate for top Spotlight / Hero story card in the newsletter")
    .setRequired(true)
    .setChoiceValues([
      "No (Standard Entry)",
      "Yes (Nominate for Spotlight Feature)"
    ]);

  const editUrl = form.getEditUrl();
  const publishedUrl = form.getPublishedUrl();

  Logger.log("✓ Student Achievements Form Created!");
  Logger.log("  Edit URL: " + editUrl);

  return {
    title: form.getTitle(),
    editUrl: editUrl,
    publishedUrl: publishedUrl
  };
}

/**
 * 4. Industry, Alumni & Outreach Submission Form Creator
 */
function createIndustryForm() {
  const form = FormApp.create("IT Chronicles - Industry, Alumni & Outreach Submission Form");
  form.setDescription("Official submission form for Industry Visits, Guest Lectures, MoUs, Alumni Mentorship, and Social Outreach.");
  form.setCollectEmail(true);

  form.addTextItem().setTitle("Coordinator / Faculty Name").setRequired(true);

  const categoryItem = form.addMultipleChoiceItem();
  categoryItem.setTitle("Outreach Category")
    .setRequired(true)
    .setChoiceValues([
      "Industrial Visits & Field Tours",
      "Industry Expert Lectures & Technical Talks",
      "MoUs Signed & Industrial Collaborations",
      "Alumni Interactions & Mentorship Sessions",
      "Community & Social Outreach Initiatives"
    ]);

  form.addTextItem().setTitle("Title of Event / Visit / MoU Partner").setRequired(true);
  form.addTextItem().setTitle("Company / Organization / Alumni Details").setRequired(true);
  form.addTextItem().setTitle("Date of Event / Execution").setRequired(true);
  form.addTextItem().setTitle("Target Audience & Number of Participants").setRequired(true);
  form.addTextItem().setTitle("Key Impact Badge / Metric").setHelpText("Short badge tag (e.g. MoU Signed, 150+ Attendees, Global Speaker)").setRequired(false);
  form.addParagraphTextItem().setTitle("Executive Summary & Outcomes").setRequired(true);
  form.addTextItem().setTitle("Photo Link (Google Drive / Cloud URL)").setHelpText("High-resolution photo of event or MoU signing").setRequired(false);
  form.addTextItem().setTitle("Photo Caption & Persons in Image").setHelpText("Description of photo scene and VIPs present").setRequired(false);
  form.addTextItem().setTitle("Event Report / Brochure Link").setRequired(false);

  const milestoneItem = form.addMultipleChoiceItem();
  milestoneItem.setTitle("Is this a Landmark / Milestone Achievement?")
    .setHelpText("Nominate for top Spotlight / Hero story card in the newsletter")
    .setRequired(true)
    .setChoiceValues([
      "No (Standard Entry)",
      "Yes (Nominate for Spotlight Feature)"
    ]);

  const editUrl = form.getEditUrl();
  const publishedUrl = form.getPublishedUrl();

  Logger.log("✓ Industry & Outreach Form Created!");
  Logger.log("  Edit URL: " + editUrl);

  return {
    title: form.getTitle(),
    editUrl: editUrl,
    publishedUrl: publishedUrl
  };
}

/**
 * 5. Departmental Highlights Submission Form Creator
 */
function createDepartmentalForm() {
  const form = FormApp.create("IT Chronicles - Departmental Highlights Submission Form");
  form.setDescription("Official submission form for Department Workshops, Conferences, Infrastructure Upgrades, and Milestones.");
  form.setCollectEmail(true);

  form.addTextItem().setTitle("Convener / Coordinator Name").setRequired(true);

  const categoryItem = form.addMultipleChoiceItem();
  categoryItem.setTitle("Department Highlight Category")
    .setRequired(true)
    .setChoiceValues([
      "Workshops & FDPs Organized",
      "Conferences & Symposia Organized",
      "Infrastructure & Lab Upgrades",
      "Student Club & Society Activities",
      "Department Statistics & Major Milestones"
    ]);

  form.addTextItem().setTitle("Title of Event / Upgrade / Milestone").setRequired(true);
  form.addTextItem().setTitle("Coordinators / Department Leads").setRequired(true);
  form.addTextItem().setTitle("Dates & Duration").setRequired(true);
  form.addTextItem().setTitle("Resource Persons / Keynote Speakers").setRequired(false);
  form.addTextItem().setTitle("Total Participants Count").setRequired(false);
  form.addTextItem().setTitle("Key Impact Badge / Metric").setHelpText("Short badge tag (e.g. 5-Day FDP, New AI Lab, 300+ Delegates)").setRequired(false);
  form.addParagraphTextItem().setTitle("Event Overview & Highlights").setRequired(true);
  form.addTextItem().setTitle("Photo Link (Google Drive / Cloud URL)").setHelpText("High-resolution photograph of the event").setRequired(false);
  form.addTextItem().setTitle("Photo Caption & Persons in Image").setHelpText("Caption explaining the photo and participants").setRequired(false);
  form.addTextItem().setTitle("Event Report / Flyer Link").setRequired(false);

  const milestoneItem = form.addMultipleChoiceItem();
  milestoneItem.setTitle("Is this a Landmark / Milestone Achievement?")
    .setHelpText("Nominate for top Spotlight / Hero story card in the newsletter")
    .setRequired(true)
    .setChoiceValues([
      "No (Standard Entry)",
      "Yes (Nominate for Spotlight Feature)"
    ]);

  const editUrl = form.getEditUrl();
  const publishedUrl = form.getPublishedUrl();

  Logger.log("✓ Departmental Highlights Form Created!");
  Logger.log("  Edit URL: " + editUrl);

  return {
    title: form.getTitle(),
    editUrl: editUrl,
    publishedUrl: publishedUrl
  };
}
