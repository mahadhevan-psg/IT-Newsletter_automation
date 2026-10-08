/**
 * IT Chronicles - Student Achievements Form Creator Script
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
  form.addTextItem().setTitle("Date of Event / Award").setRequired(true);
  form.addParagraphTextItem().setTitle("Project Abstract / Achievement Details").setRequired(true);
  form.addTextItem().setTitle("Photo Link (Google Drive / Cloud URL)").setRequired(false);
  form.addTextItem().setTitle("Certificate / Proof Link").setRequired(false);

  Logger.log("Student Achievements Form Created successfully!");
  Logger.log("Form Edit URL: " + form.getEditUrl());
}
