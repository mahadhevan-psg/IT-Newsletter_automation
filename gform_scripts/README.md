# IT Chronicles - Google Forms

> **Current forms (category-based).** The five submission forms and the placement form now work like this: a person says YES or NO to each
> category, fills the YES ones, and answers a few common questions at the end, all in **one response**. The Google Form scripts are the
> source of the questions; the application's description of them lives here:
>
> | File | What it is |
> |---|---|
> | [new_forms.py](new_forms.py) | Every form's common questions, categories, fields and closing questions, with the master-database column and newsletter field each one fills |
> | [build_new_forms.py](build_new_forms.py) | `python gform_scripts/build_new_forms.py` writes `config/master_forms.json`, `config/form_mappings.json` and the newsletter's section categories |
> | `legacy_*.json` | The earlier single-category forms, kept so sheets exported from them still import |
> | `../tests/fixtures/sheet_headers.json` | The header rows of the six real response sheets; `tests/test_blocks.py` checks the layouts against them |
>
> **A response sheet repeats titles** ("Objectives and Rationale" appears in every category), so the application reads each row **by column
> position** (`backend/master/blocks.py`) and cuts it into one entry per category answered. Each entry is reviewed, approved, stored and
> published on its own.
>
> **When a form changes:** edit `new_forms.py` (a question, a category, the order of columns), run the builder, then run
> `pytest tests/test_blocks.py`. Replace the sheet header fixture with the new sheet's header row. If the layout in the application and the
> sheet differ, **Data sync -> Test** names the first columns that do not match.
>
> **The faculty drop-downs:** in the Apps Scripts, paste the list from *Faculty & roles -> Copy list for the Apps Script* (`C6608 - Dr. M. L.
> Valarmathi`) over `FACULTY_NAMES` and `EMPLOYEE_LIST`. People are then matched by employee ID.
>
> Forms that have no date question (Faculty Achievements, and several categories of the faculty highlights form) use the day the response was
> submitted. A date written inside the "Event Date and Venue" answer is read from the text.
>
> Everything below describes the **first, single-category forms** (`build_forms.py`, `AllFormsCreator.gs` ...). Those files are no longer used by the application.

---


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
