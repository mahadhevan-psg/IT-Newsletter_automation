/**
 * IT Chronicles - Master Form Generation Script
 * Run this function in Google Apps Script to create all 5 Master Google Forms at once.
 */

function buildAllMasterForms() {
  Logger.log("=== Starting Master Google Forms Creation ===");
  
  createResearchForm();
  createFacultyForm();
  createStudentForm();
  createIndustryForm();
  createDepartmentalForm();

  Logger.log("=== All 5 Master Google Forms successfully created! ===");
}
