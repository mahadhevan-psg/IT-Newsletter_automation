/**
 * IT Chronicles - Faculty Achievements Form Creator Script
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
  form.addParagraphTextItem().setTitle("Description & Key Highlights").setRequired(true);
  form.addTextItem().setTitle("Photo Link (Google Drive / Cloud URL)").setRequired(false);
  form.addTextItem().setTitle("Evidence / Certificate Link (Google Drive URL)").setRequired(false);

  Logger.log("Faculty Achievements Form Created successfully!");
  Logger.log("Form Edit URL: " + form.getEditUrl());
}
