# IT Chronicles - Google Forms

Everything here is generated from **one file**, [build_forms.py](build_forms.py). Edit a question there, run

```bash
python gform_scripts/build_forms.py
```

and it rewrites, in one go:

| Output | Used for |
|---|---|
| **`AllFormsCreator.gs`** | **All 6 forms in one run** (paste it, run `buildAllForms`): the 5 submission forms and the placement form |
| `MasterFormsCreator.gs` | The 5 submission forms only (Student, Research, Faculty, Departmental, Industry/Outreach) |
| `PlacementFormCreator.gs` | The student placement form (collected by tutors) |
| `config/master_forms.json` | The master-database importer (which column goes where) |
| `config/form_mappings.json` | The newsletter studio mappings (merged - old headers keep working) |

Because all four come from the same spec, a form and its importer cannot drift apart.

## Creating the forms

1. Open <https://script.google.com> → **New project** → paste the whole `.gs` file.
2. In the **CONFIG** block at the top:
   - `FACULTY_CHOICES` - in the portal (Admin) open **Faculty & roles → Copy list for the Apps Script** and paste it over the list. People then *select* their name instead of typing it, which is what links every submission to the right faculty.
   - `ROLL_ID` - the regular expression for your roll numbers (default: 6-15 letters/digits).
3. Run `buildAllMasterForms` (or `createPlacementForm`) and approve the permissions.
4. The Execution log lists the fill-in link, edit link and responses spreadsheet of every form.

## What changed from the first version

- **People are linked by ID, not typed names.** Faculty are picked from a drop-down; students are entered one per line by **roll number only** (names come from the college records), validated by the form itself. The placement form no longer asks for a name either.
- Research authors: `ID - Name` per line - employee ID, roll number, or `EXT` for outsiders.
- Duplicate questions from the old sheets were removed (research subcategory, venue, indexing, photo, accuracy; faculty outcome).
- Dates use date pickers; amounts and counts are validated numbers; links are validated URLs.
- Newsletter fields are unchanged (category, badge, photo caption, landmark nomination), so the newsletter still builds from the same responses.
- Departmental and Outreach forms take an optional **student roster**, so students' participation shows in their class record.

## Getting responses into the system

Each form writes to its own Google Sheet. Download it (**File → Download → Microsoft Excel**) and upload it:

- **IT Portal → Data upload** - tutors and the Admin; goes into the master database (students, faculty, analytics).
- **Newsletter studio → Responses → Import** - goes into the newsletter *and* the master database.

Uploading the same file twice never creates duplicates. Rows whose roll number or employee ID matches nobody are kept and listed under **Needs attention**.

## Placement form

Students fill one response per offer (or one with the company blank if they have none). Export the sheet and upload it under **Data upload → Placement data**. A student already in the database is **replaced** by the rows in the new file for that academic year.
