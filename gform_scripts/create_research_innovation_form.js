/**
 * IT Chronicles - Research & Innovation Form Creator Script
 * Run this in Google Apps Script (https://script.google.com) to automatically
 * create the "IT Chronicles: Research & Innovation" Master Google Form.
 */

function createResearchForm() {
  const form = FormApp.create("IT Chronicles - Research & Innovation Submission Form");
  form.setDescription("Official submission form for Research & Innovation content for the IT Chronicles Newsletter.\nData submitted here will be automatically normalized into the Newsletter System.");
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
  form.addTextItem().setTitle("DOI / Patent Number / Grant Amount / URL Link").setRequired(false);

  // Description / Abstract
  form.addParagraphTextItem().setTitle("Abstract / Executive Summary / Highlights").setRequired(true);

  // Media links
  form.addTextItem().setTitle("Photo Link (Google Drive / Cloud URL)").setHelpText("High-resolution image link for newsletter inclusion").setRequired(false);
  form.addTextItem().setTitle("Evidence / Certificate Link (Google Drive / Document URL)").setRequired(false);

  Logger.log("Research & Innovation Form Created successfully!");
  Logger.log("Form Edit URL: " + form.getEditUrl());
  Logger.log("Form Published URL: " + form.getPublishedUrl());
}
