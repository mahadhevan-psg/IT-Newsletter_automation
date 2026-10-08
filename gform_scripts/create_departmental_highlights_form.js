/**
 * IT Chronicles - Departmental Highlights Form Creator Script
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
  form.addParagraphTextItem().setTitle("Event Overview & Highlights").setRequired(true);
  form.addTextItem().setTitle("Photo Link (Google Drive / Cloud URL)").setRequired(false);
  form.addTextItem().setTitle("Event Report / Flyer Link").setRequired(false);

  Logger.log("Departmental Highlights Form Created successfully!");
  Logger.log("Form Edit URL: " + form.getEditUrl());
}
