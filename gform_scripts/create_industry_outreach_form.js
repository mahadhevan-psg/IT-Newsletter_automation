/**
 * IT Chronicles - Industry / Alumni / Outreach Form Creator Script
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
  form.addParagraphTextItem().setTitle("Executive Summary & Outcomes").setRequired(true);
  form.addTextItem().setTitle("Photo Link (Google Drive / Cloud URL)").setRequired(false);
  form.addTextItem().setTitle("Event Report / Brochure Link").setRequired(false);

  Logger.log("Industry & Outreach Form Created successfully!");
  Logger.log("Form Edit URL: " + form.getEditUrl());
}
